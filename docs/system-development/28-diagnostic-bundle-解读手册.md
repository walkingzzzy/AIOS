# 28 · diagnostic bundle 解读手册

**版本**: 1.0.0  
**更新日期**: 2026-03-13  
**状态**: `P7-REL-011` frozen bundle interpretation guide

---

## 1. 目标

本文用于解释 `aios-updated` 通过 `recovery.bundle.export` 导出的 diagnostic bundle 应该如何阅读、如何判断升级/回退状态，以及它和 recovery point、health probe、release gate 证据之间的关系。

本文重点解决：

1. bundle 文件里每个字段代表什么
2. 哪些字段最值得先看
3. 常见失败模式应该如何从 bundle 里识别
4. bundle 之外还需要补抓哪些证据

## 2. 产出位置与入口

导出入口：

- RPC：`recovery.bundle.export`
- 默认目录：`/var/lib/aios/updated/diagnostics/`

最小返回字段：

- `bundle_id`
- `bundle_path`
- `created_at`
- `deployment_status`
- `recovery_points`
- `diagnostic_bundles`
- `notes`

相关规范与样例：

- schema：`aios/observability/schemas/diagnostic-bundle.schema.json`
- sample：`aios/observability/samples/diagnostic-bundle.sample.json`
- runbook：[`27-升级与恢复交付Runbook.md`](27-升级与恢复交付Runbook.md)
- troubleshooting：[`29-Operator-Troubleshooting-手册.md`](29-Operator-Troubleshooting-手册.md)

## 3. 当前 bundle 结构

当前 exporter 写入的核心结构来自 `aios/services/updated/src/diagnostics.rs`。实际文件至少包含：

| 字段 | 含义 | 来源 |
|------|------|------|
| `bundle_id` | 当前 bundle 唯一 ID，通常形如 `diag-<timestamp>` | exporter 生成 |
| `created_at` | bundle 导出时间 | exporter 生成 |
| `service_id` | 导出服务，当前通常是 `aios-updated` | deployment store |
| `reason` | 导出原因，例如 `manual-export`、`smoke-export` | `recovery.bundle.export` 请求 |
| `deployment` | 当下 deployment snapshot | `deployment-state.json` |
| `probe` | 当前 health probe snapshot，可能为空 | `health-probe.json` |
| `boot_state` | 当前 boot slot / last-good / staged 状态，可能为空 | `boot-control.json` |
| `recovery_points` | 当前 recovery 目录中的 recovery record 列表 | `/var/lib/aios/updated/recovery/` |
| `diagnostic_bundles` | 当前 diagnostics 目录中的 bundle 列表，包含新导出的 bundle | `/var/lib/aios/updated/diagnostics/` |
| `notes` | 导出时附带的解释、路径、缺失项说明 | exporter 拼接 |

说明：

- schema 样例里还有 `schema_version`、`generated_at`、`update_id`、`boot_id`、`artifact_path` 等扩展字段
- 当前 live exporter 不保证把这些扩展字段全部写进 bundle 文件本体
- 因此 operator 必须同时保留 RPC 返回值、bundle 路径、recovery surface 与现场日志，不能只保留单个 JSON

## 4. 推荐阅读顺序

拿到 bundle 后，推荐按以下顺序阅读：

1. `reason`
2. `deployment.status`
3. `probe.overall_status`
4. `boot_state.current_slot` / `last_good_slot` / `staged_slot`
5. `recovery_points`
6. `notes`

这样可以最快判断当前属于：

- 还没重启完成的 staged update
- 已重启但 health probe 失败
- rollback 已经被接受但还没验证
- recovery 点缺失、无法自动回退
- 只是缺 artifact，而不是系统本身损坏

## 5. `deployment` 字段怎么解读

`deployment` 反映的是 `deployment-state.json` 的快照。当前最常见的 `status` 值如下：

| `deployment.status` | 含义 | 常见下一步 |
|---------------------|------|------------|
| `idle` | 还没有跑过有效的 check/apply/rollback 闭环 | 先执行 `update.check` |
| `ready-to-stage` | 已发现可用更新或 sysupdate entry，可进入 apply | 调 `update.apply` |
| `up-to-date` | 当前 deployment 已收敛，无 pending action | 只做健康检查或等待下一次更新 |
| `waiting-for-artifacts` | sysupdate 目录存在，但没有可 stage 的 artifact | 检查平台 profile、sysupdate transfer 与 delivery bundle |
| `missing-sysupdate-dir` | sysupdate 目录本身缺失 | 优先检查 image / platform overlay / updated profile |
| `apply-triggered` | 已调用 apply，外部 sysupdate / boot switch 已触发 | 重启并在新槽位上做 `update.health.get` |
| `staged-update` | 已完成 recovery point 记录与 staged slot 写入，等待重启验证 | 重启到 `staged_slot` |
| `rollback-triggered` | 已触发 rollback，等待回到旧槽位并验证 | 重启并执行 `update.health.get` |
| `rollback-staged` | 已记录 rollback 目标，但还没完成重启验证 | 重启到回退槽位 |
| `apply-failed` | apply 命令或 sysupdate backend 执行失败 | 保留 bundle，检查 sysupdate/backend 日志 |
| `rollback-failed` | rollback 命令执行失败 | 保留 bundle，准备 recovery media |
| `boot-switch-failed` | 切换 boot slot 失败 | 优先检查 bootctl / firmwarectl hook |
| `sysupdate-check-failed` | 检查更新时外部命令失败 | 检查 sysupdate check hook 与平台 profile |

同时注意：

- `active_recovery_id` 表示当前 pending 的 recovery record
- `pending_action=apply|rollback` 说明状态还没有在 reboot 后完全收敛
- `next_version` 在 apply 成功前后通常会出现，收敛后会清空

## 6. `probe` 字段怎么解读

`probe` 来自 `health-probe.json`。它反映的是平台级 probe，而不是 deployment 状态本身。

当前规范化关系为：

| `probe.overall_status` | 对外健康语义 |
|------------------------|--------------|
| `healthy` | `ready` |
| `warning` | `degraded` |
| `failed` / `unhealthy` | `blocked` |

优先看三个字段：

- `overall_status`
- `summary`
- `notes`

常见判断：

- `healthy + summary=probe ok`：平台 probe 没发现明显问题
- `warning`：系统能起来，但某些 backend 或 profile 条件未满足
- `failed`：即使 deployment 看起来已 stage，也不应直接判定升级成功
- `probe` 为空：bundle 导出时没有可用 probe snapshot，这本身就是一个信号

## 7. `boot_state` 字段怎么解读

`boot_state` 反映 boot control 当前看到的槽位状态：

| 字段 | 含义 | 解读 |
|------|------|------|
| `current_slot` | 当前正在运行的槽位 | 现在系统从哪一个 deployment 启动 |
| `last_good_slot` | 上一个确认健康的槽位 | 真正可回退的稳定槽位 |
| `staged_slot` | 下次重启将尝试切换到的槽位 | 非空意味着还没完成 reboot 验证 |
| `boot_success` | 当前 boot 是否已被 verify 为成功 | `false` 或缺失时不要提前宣告升级成功 |

常见模式：

| 模式 | 含义 |
|------|------|
| `current_slot == last_good_slot` 且 `staged_slot` 为空 | 当前系统已稳定收敛 |
| `staged_slot` 非空 | 更新或回退已经 stage，但还没完成 reboot 验证 |
| `current_slot != last_good_slot` | 正在新槽位试运行，或回退后还没 mark-good |
| `boot_success = true` 且 `staged_slot` 为空 | 该槽位已经通过 boot verify |

## 8. `recovery_points` 怎么看

`recovery_points` 只是文件名列表，真实内容在 `/var/lib/aios/updated/recovery/<recovery_id>.json`。

当前 recovery record 的关键字段包括：

- `current_version`
- `target_version`
- `reason`
- `boot_slot_before`
- `boot_slot_after`
- `status`

`status` 常见值：

| recovery record status | 含义 |
|------------------------|------|
| `created` | recovery 点刚建立，还没经过成功 boot 或 rollback 收敛 |
| `verified` | apply 后新版本已 boot verify 成功 |
| `rolled-back` | rollback 后旧版本已重新成为 last-good |

如果 bundle 里有 recovery point 文件名，但没有对应 recovery record 内容归档，交付是不完整的。

## 9. 常见场景判断

### 9.1 staged update，尚未重启

典型信号：

- `deployment.status = apply-triggered` 或 `staged-update`
- `boot_state.staged_slot` 非空
- `recovery_points` 至少有 1 个
- `probe.overall_status` 仍可能是 `healthy`

结论：

- 说明 apply 已经接受，但成败还没有通过 reboot 验证
- 不应把这类 bundle 当作“升级成功”证据

### 9.2 已重启，但 probe 失败

典型信号：

- `current_slot` 已切到新槽位
- `probe.overall_status = failed`
- `notes` 里出现 probe 失败或 backend 错误

结论：

- 说明 boot 链已到新 deployment，但平台健康没有通过
- 应先再导出一次 bundle，再决定是否 `update.rollback`

### 9.3 rollback 已 stage，等待验证

典型信号：

- `deployment.status = rollback-triggered` 或 `rollback-staged`
- `boot_state.staged_slot` 指回旧槽位
- `notes` 里有 `rollback_target=...`

结论：

- rollback 已经被接受，但还没有通过 reboot + verify 收敛
- 仍需要下一次启动后的 `update.health.get` 和新的 bundle

### 9.4 recovery 点缺失

典型信号：

- `recovery_points = []`
- `rollback_ready = false` 或 `available_actions` 不含 `rollback`

结论：

- 自动回退条件不足
- 应准备 recovery media，而不是盲目继续切槽

### 9.5 只是没有可更新 artifact

典型信号：

- `deployment.status = waiting-for-artifacts` 或 `missing-sysupdate-dir`
- `probe` 可能仍然是 `healthy`

结论：

- 这类问题更像交付链缺件，不一定是机器已损坏
- 先回到 delivery / platform profile / sysupdate 配置排查

## 10. 从 bundle 到下一步动作

看到 bundle 后，推荐按下面流程走：

1. 先判定是 `apply` 还是 `rollback` 场景：看 `pending_action`、`active_recovery_id`、`reason`
2. 再判定系统是否稳定：看 `probe.overall_status` 和 `boot_state`
3. 决定是继续重启验证，还是立刻导出更多证据并回退
4. 回到 `recovery-surface.json` 对照 `available_actions`
5. 把 bundle、recovery record、health probe、recovery surface、现场日志一起归档

不要单独依据某一个字段作结论：

- 不能只看 `deployment.status`
- 不能只看 `probe.overall_status`
- 也不能只看 `current_slot`

至少要同时交叉看 `deployment + probe + boot_state + recovery_points`。

## 11. 建议与其他证据一起保存的文件

bundle 不是完整现场快照。每次导出 bundle 时，建议同时保存：

- `/var/lib/aios/updated/deployment-state.json`
- `/var/lib/aios/updated/health-probe.json`
- `/var/lib/aios/updated/recovery-surface.json`
- `/var/lib/aios/updated/boot-control.json`
- `/var/lib/aios/updated/recovery/<recovery_id>.json`
- installer / recovery / serial log
- `system-delivery-validation-report.json`
- `release-gate-report.json`

## 12. 当前边界

截至 2026-03-13，diagnostic bundle 已足以支持 release/operator 侧的一线判断，但仍有以下边界：

- live exporter 还没有把 schema sample 中的每一个扩展相关字段都写进 bundle 本体
- bundle 主要聚焦 `updated` 视角，不包含完整 shell、provider、device 侧日志
- 更深的 root-cause 仍需要结合 recovery surface、health event、recovery evidence 与现场日志一起判断
