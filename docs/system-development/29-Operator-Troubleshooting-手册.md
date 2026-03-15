# 29 · Operator Troubleshooting 手册

**版本**: 1.0.0  
**更新日期**: 2026-03-13  
**状态**: `P7-REL-010` frozen operator guide

---

## 1. 目标

本文面向在目标机器、恢复介质或交付现场值守的 operator，用于处理 AIOS 团队 A 当前最常见的升级、回退、恢复与交付故障。

本文回答：

1. 现场先看哪些入口
2. 不同症状对应的第一组命令是什么
3. 哪些故障应该先导出 bundle，再决定 rollback
4. 什么情况下应该切到 recovery media 或直接升级为发布阻塞

本文和以下文档配套使用：

- [`27-升级与恢复交付Runbook.md`](27-升级与恢复交付Runbook.md)：正常 upgrade / recovery 执行路径
- [`28-diagnostic-bundle-解读手册.md`](28-diagnostic-bundle-解读手册.md)：bundle 字段解释
- [`24-Boot-Firstboot-Recovery-验证清单.md`](24-Boot-Firstboot-Recovery-验证清单.md)：仓库级验证入口

## 2. 现场前 10 分钟

先不要直接重试 install / apply / rollback。先做最小状态采样：

```bash
systemctl status aios-updated.service --no-pager
journalctl -u aios-updated.service -b --no-pager | tail -n 200
cat /etc/aios/updated/platform.env
cat /var/lib/aios/updated/deployment-state.json
cat /var/lib/aios/updated/boot-control.json
cat /var/lib/aios/updated/recovery-surface.json
python3 /usr/libexec/aios-shell/components/recovery-surface/client.py summary --json
```

如果已经进入 recovery 模式，再执行：

```bash
/usr/libexec/aios/aios-recovery-report.sh
```

这一轮采样后，优先判断：

- `aios-updated.service` 是否起来了
- `/run/aios/updated/updated.sock` 是否存在
- `deployment-state.json.status` 属于哪一类
- `boot-control.json` 是否存在 `staged_slot`
- `recovery-surface.json` 是否还能给出 `available_actions`

## 3. 关键入口速查

| 入口 | 默认路径/命令 | 用途 |
|------|---------------|------|
| `updated` service | `systemctl status aios-updated.service` | 看服务是否启动、是否反复 crash |
| `updated` 日志 | `journalctl -u aios-updated.service -b` | 看平台 profile、probe、boot switch、rollback 错误 |
| platform env | `/etc/aios/updated/platform.env` | 看是否装载了目标平台 profile |
| platform profile | `AIOS_UPDATED_PLATFORM_PROFILE=...` | 看 `sysupdate_binary`、`firmwarectl_binary`、`health_probe_command` |
| socket | `/run/aios/updated/updated.sock` | `system.health.get` / `update.health.get` / `update.rollback` RPC 入口 |
| deployment state | `/var/lib/aios/updated/deployment-state.json` | 版本、pending action、active recovery |
| health probe | `/var/lib/aios/updated/health-probe.json` | probe summary 与 note |
| recovery surface | `/var/lib/aios/updated/recovery-surface.json` | shell/operator 可消费的恢复面 |
| boot control | `/var/lib/aios/updated/boot-control.json` | current / last-good / staged slot |
| recovery points | `/var/lib/aios/updated/recovery/` | rollback 目标来源 |
| diagnostic bundles | `/var/lib/aios/updated/diagnostics/` | `recovery.bundle.export` 输出 |
| recovery shell client | `python3 /usr/libexec/aios-shell/components/recovery-surface/client.py ...` | 直接调用 `check/apply/rollback/bundle` |
| recovery report | `/usr/libexec/aios/aios-recovery-report.sh` | 恢复介质下打印 surface 与 boot control |

## 4. 症状驱动排查

### 4.1 `aios-updated.service` 没起来，或者 socket 缺失

先执行：

```bash
systemctl status aios-updated.service --no-pager
journalctl -u aios-updated.service -b --no-pager | tail -n 200
cat /etc/aios/updated/platform.env
```

优先看这些信号：

- `EnvironmentFile=-/etc/aios/updated/platform.env` 是否存在
- `ExecStart=/usr/libexec/aios/updated` 是否能找到 binary
- 日志里是否有 platform profile 路径错误、权限错误、state dir 创建失败

最常见原因：

- `platform.env` 缺失或内容错误
- 平台 profile 指向的 `sysupdate_binary` / `firmwarectl_binary` / `health_probe_command` 不可执行
- `/var/lib/aios/updated/` 或 `/run/aios/updated/` 未创建成功

直接动作：

- 先修正 `/etc/aios/updated/platform.env`
- 再 `systemctl restart aios-updated.service`
- 仍失败时，把 journal 与 `platform.env` 一并归档

### 4.2 recovery surface 文件不存在或明显过期

先执行：

```bash
ls -l /var/lib/aios/updated/recovery-surface.json
python3 /usr/libexec/aios-shell/components/recovery-surface/client.py status --json
```

判断要点：

- 文件不存在但 RPC 可读：说明 startup sync / surface write 出了问题
- 文件存在但 RPC 返回更新：说明 surface file 落盘过期
- 文件和 RPC 都不可用：先回到 4.1，按 service/socket 故障排查

最常见原因：

- `aios-updated` 没成功完成 startup sync
- health probe 执行失败后 surface 未及时更新
- 状态目录被清理或权限错误

直接动作：

- 优先保留当前 `deployment-state.json`、`boot-control.json` 与 journal
- 以 RPC 返回为准，不要只看旧的 surface file
- 如果 `available_actions` 已无 `rollback`，不要盲目继续回退

### 4.3 `update.check` 返回异常状态

最小命令：

```bash
python3 /usr/libexec/aios-shell/components/recovery-surface/client.py check
cat /var/lib/aios/updated/deployment-state.json
cat /var/lib/aios/updated/health-probe.json
```

关键状态和动作：

| 状态 | 说明 | 先做什么 |
|------|------|----------|
| `ready-to-stage` | 可以进入 apply | 正常继续 |
| `up-to-date` | 没有待升级内容 | 不要重复 apply |
| `waiting-for-artifacts` | sysupdate 目录存在但无 transfer | 检查 delivery bundle / sysupdate transfer / platform profile |
| `missing-sysupdate-dir` | sysupdate 目录不存在 | 优先检查 image overlay、平台 profile、installer/firstboot 集成 |
| `sysupdate-check-failed` | 外部 check hook 失败 | 看 journal 与 hook stderr |

如果看到 `waiting-for-artifacts` 或 `missing-sysupdate-dir`：

- 不要直接改 slot
- 先回查 `sysupdate_definitions_dir` 和平台 profile 是否匹配
- 再回查 `out/aios-system-delivery/` 和 `system-delivery-validation-report.json`

### 4.4 `update.apply` 被接受了，但系统重启后没有收敛

最小命令：

```bash
python3 /usr/libexec/aios-shell/components/recovery-surface/client.py apply --reason operator-check
cat /var/lib/aios/updated/boot-control.json
cat /var/lib/aios/updated/deployment-state.json
python3 /usr/libexec/aios-shell/components/recovery-surface/client.py status --json
```

如果 apply 已经返回 `accepted`，但重启后还不收敛，重点看：

- `boot-control.json.staged_slot` 是否仍存在
- `current_slot` 是否真的切到了目标槽位
- `last_good_slot` 是否更新
- `deployment-state.json.pending_action` 是否一直卡在 `apply`

最常见原因：

- boot switch 已 stage，但机器还没真正从新槽位启动
- 新槽位启动了，但 probe 失败，没有进入 `up-to-date`
- `bootctl` / `firmwarectl` hook 执行了，但 mark-good 没成功

直接动作：

- 先执行 `update.health.get` 触发一次 post-boot 收敛
- 若 `probe.overall_status` 为 `failed` 或 `blocked`，先导出 bundle，再决定 rollback
- 不要在 `staged_slot` 仍存在时就宣告升级成功

### 4.5 `update.rollback` 不可用、blocked 或失败

最小命令：

```bash
python3 /usr/libexec/aios-shell/components/recovery-surface/client.py rollback --reason operator-rollback
ls -l /var/lib/aios/updated/recovery
cat /var/lib/aios/updated/boot-control.json
```

优先看：

- `rollback_ready`
- `recovery_points` 是否为空
- `rollback_target` 是否有值
- `boot-control.json.staged_slot` 是否被写回旧槽位

最常见原因：

- 根本没有 recovery point
- recovery record 存在，但 `boot_slot_before` / `boot_slot_after` 不足以推导回退目标
- `bootctl` / `firmwarectl` rollback hook 失败

直接动作：

- 如果 `recovery_points = []`，不要继续尝试自动 rollback，转入 recovery media
- 如果 rollback 返回 `accepted`，仍要重启并再次检查 `update.health.get`
- 如果 rollback 返回 `failed`，立刻导出 bundle 和 journal，并准备 recovery media

### 4.6 recovery 模式已经起来，但 operator 看不到有效上下文

最小命令：

```bash
/usr/libexec/aios/aios-recovery-report.sh
cat /var/lib/aios/updated/recovery-surface.json
cat /var/lib/aios/updated/boot-control.json
ls -l /var/lib/aios/updated/diagnostics
```

要点：

- recovery report 至少应该打印 `recovery_surface`、`diagnostics_dir`、`boot_control`
- 如果 surface 文件缺失，但系统盘还能挂载，优先把 state 目录整包保存
- 如果 diagnostics 目录为空，说明现场还没有导出过 bundle

直接动作：

- 先保存 state 文件和 recovery shell 输出
- 再判断是否还能从 recovery 环境导出 bundle
- 不能恢复正常系统时，把 recovery log 计入硬件验证报告

### 4.7 release gate / system delivery validation 卡在 Team A 相关检查

最小命令：

```bash
python3 scripts/test-system-delivery-validation.py
python3 scripts/check-release-gate.py
```

优先看这些 blocking checks：

- `qemu-preflight`
- `qemu-bringup-firstboot`
- `qemu-recovery-bringup`
- `installer-media-qemu`
- `updated-recovery-surface`
- `updated-cross-restart`
- `updated-firmware-backend`
- `updated-platform-profile`
- `hardware-boot-evidence`

典型判断：

- 如果是 `updated-platform-profile` 失败，优先看平台 profile、health probe command 与 firmware bridge
- 如果是 `updated-cross-restart` / `updated-firmware-backend` 失败，优先看 boot slot、mark-good、rollback 收敛路径
- 如果是 `hardware-boot-evidence` 失败，通常不是仓库逻辑坏了，而是实机 boot 记录不完整

### 4.8 实机 boot evidence 或最终硬件报告不通过

最小命令：

```bash
./out/platform-media/<platform>/bringup/scripts/evaluate-boot-evidence.sh ./out/hardware-boots
./out/platform-media/<platform>/bringup/scripts/render-hardware-validation.sh \
  ./out/platform-media/<platform>/bringup/reports/hardware-validation-evaluator.json
```

优先看：

- 是否至少有两个不同 `boot_id`
- `expect-slot-transition` 是否符合现场实际
- `expect-last-good-slot` 是否与回退后结果一致

最常见原因：

- 只抓到一次 boot
- 回退前后证据目录混在一起但缺关键信息
- 安装成功了，但没有保存 recovery log / installer log / operator note

## 5. bundle 什么时候先导出

以下场景优先导出 diagnostic bundle，再决定是否 rollback：

- `probe.overall_status = failed` 或 `blocked`
- `deployment.status = apply-failed`
- `deployment.status = rollback-failed`
- `deployment.status = boot-switch-failed`
- recovery surface 仍可用，但系统已经出现不稳定行为

最小命令：

```bash
python3 /usr/libexec/aios-shell/components/recovery-surface/client.py bundle --reason operator-debug
ls -l /var/lib/aios/updated/diagnostics
```

bundle 的阅读顺序见 [`28-diagnostic-bundle-解读手册.md`](28-diagnostic-bundle-解读手册.md)。

## 6. cross-service health report 用法

当问题不只在 `updated`，而是怀疑已经影响到跨服务观测时，建议额外生成一份 health report。

先准备 spec，例如：

```yaml
sources:
  - source_id: updated-rpc
    kind: rpc-update
    component_kind: update
    socket_path: /run/aios/updated/updated.sock
    component_id: updated-health
    artifact_path: /var/lib/aios/updated/health-probe.json
  - source_id: updated-probe
    kind: command-health
    component_kind: update
    command: /usr/libexec/aios-platform/generic-x86_64-uefi/health-probe.sh
    component_id: updated-probe
    artifact_path: /var/lib/aios/updated/health-probe.json
  - source_id: delivery-bundle
    kind: delivery-artifact
    component_kind: platform
    manifest_path: out/aios-system-delivery/manifest.json
    component_id: system-delivery
```

然后执行：

```bash
python3 scripts/build-cross-service-health-report.py \
  --spec out/validation/updated-health-spec.yaml \
  --output-prefix out/validation/cross-service-health-report
```

输出：

- `out/validation/cross-service-health-report.json`
- `out/validation/cross-service-health-report.md`
- `out/validation/cross-service-health-events.jsonl`

适用场景：

- 想确认问题只在 `updated`，还是已经波及 delivery/platform 观测
- 需要给团队 E 一份结构化健康报告
- 需要把 `system.health.get` 与 `update.health.get` 统一到同一份 artifact

## 7. 升级为发布阻塞的条件

出现以下任一情况，应直接升级为发布阻塞，而不是现场继续试：

- `aios-updated.service` 无法稳定启动
- `update.apply` 或 `update.rollback` 连续失败，且原因不明
- `boot-switch-failed` 或 `rollback-failed` 已出现
- recovery media 无法提供基本上下文
- 实机证据无法证明至少两次有效 boot
- `release-gate-report.json` 中 Team A 相关 blocking checks 持续失败

## 8. 交接给团队 E 或上层决策前的最小证据包

升级故障时至少附带：

- `journalctl -u aios-updated.service -b`
- `/etc/aios/updated/platform.env`
- `/var/lib/aios/updated/deployment-state.json`
- `/var/lib/aios/updated/health-probe.json`
- `/var/lib/aios/updated/recovery-surface.json`
- `/var/lib/aios/updated/boot-control.json`
- `/var/lib/aios/updated/recovery/`
- `/var/lib/aios/updated/diagnostics/`
- `system-delivery-validation-report.json`
- `release-gate-report.json`
- 如为实机场景，再附：
  - installer log
  - recovery log
  - hardware validation report
  - boot evidence 目录或 evaluator 输出

## 9. 当前边界

截至 2026-03-13，本手册已覆盖团队 A 当前最常见的 operator 现场问题，但仍有边界：

- 更多 vendor-specific firmware hook 故障仍需按平台 profile 补充
- 这份手册聚焦更新/恢复/交付，不覆盖 Team B/C/D 的业务逻辑排查
- 更深层的根因分析仍需要结合 bundle、recovery record、现场日志和实机证据一起判断
