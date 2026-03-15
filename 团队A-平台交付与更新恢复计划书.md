# 团队A-平台交付与更新恢复计划书

## 1. 团队使命

团队 A 负责把 AIOS 当前已经具备的仓库级平台交付基线，推进到“可重复构建、可稳定安装、可真实更新、可失败回退、可恢复取证、可在 Tier 1 硬件验收”的发行级状态。

当前仓库并不是从零开始：`image`、`installer`、`recovery`、`updated`、hardware bring-up kit、QEMU 证据和部分平台 backend 已经落地。团队 A 的工作重点不是重新搭骨架，而是把这些能力收敛成稳定闭环，并恢复成可验收的交付链。

---

## 2. 当前未完成部分

### 2.1 基于仓库事实保留的剩余缺口

根据 `docs/IMPLEMENTATION_PROGRESS.md`、`docs/system-development/19-实现映射与当前进度.md`、`aios/services/updated/README.md`，团队 A 当前只保留下列未完成工作：

1. first-boot 虽已可运行，但发行级幂等、失败留痕、首启后状态收敛与 image-level gate 仍未完全闭合
2. `updated` 虽已有 deployment state、health probe、rollback hint、recovery surface、diagnostic bundle、boot / firmware backend 适配，但仍缺 Tier 1 实机 update / rollback / recovery 成功证据
3. A/B update、boot slot、rollback hint 与 recovery surface 仍缺平台级连续验收，当前更多是仓库级与 QEMU 级基线
4. generic / vendor firmware bridge 已有入口，但目标硬件上的正式 firmware hook、失败注入、超时与回退验证仍未完成
5. bring-up kit、boot evidence service、platform profile 已落地，但至少一份 Tier 1 实机安装、首启、二次启动、更新失败回退的连续证据链仍未形成
6. 团队 A 的构建 / 验证链虽已进入 CI 与 validation report，但与团队 E 的 evidence index、release gate、artifact 命名治理仍需进一步收口

---

## 3. 保留的未完成范围

### 3.1 唯一负责目录

- `aios/image/`
- `aios/hardware/`
- `aios/delivery/`
- `aios/services/updated/`
- 平台交付、构建、更新恢复、bring-up 相关脚本

### 3.2 当前仅保留的未完成能力

- first-boot 发行级收敛
- installer / recovery / update / rollback 平台闭环
- Tier 1 硬件 bring-up 与跨重启 boot evidence 收敛
- vendor-specific firmware hook 与失败注入验证
- 团队 A 验证结果与团队 E 发布门槛的正式对齐

---

## 4. 未完成工作包

### WP1：镜像构建与 first-boot 发行级收敛

**剩余任务**

- 继续收敛 first-boot 幂等逻辑，保证二次启动不会重复破坏状态
- 固化 machine identity、`random-seed`、journald、diagnostic 目录布局与失败留痕
- 强化服务二进制进入 image 后的启用、自检和失败日志保留
- 进一步减少 image 构建对宿主机环境的隐式依赖，优先复用 delivery bundle 与容器化构建链

**完成标志**

- first-boot 在重复启动场景下稳定通过
- image 中关键服务具备固定安装路径、启用状态和首启验证
- first-boot 失败时能保留可归档诊断信息
- `scripts/test-firstboot-hygiene-smoke.py` 与 QEMU bring-up 结果稳定，并能进入团队 E 的固定证据路径

### WP2：installer / recovery / update / rollback 平台闭环

**剩余任务**

- 把当前仓库级 update backend 收敛成平台可执行 runbook，补齐失败分支和状态回写
- 固化 `update.check`、`update.apply`、`update.rollback`、`recovery.surface.get` 的契约和错误口径
- 补强 A/B update、boot slot、rollback hint 在真实平台上的一致性验证
- 为 vendor-specific firmware hook 和 health probe 增加失败注入、超时和回退验证

**完成标志**

- `updated` 的关键 RPC 能驱动真实状态变化，而不只是返回静态结果
- 至少一条更新失败后的 rollback 或 recovery 路径可复现、可回放、可取证
- recovery surface 输出稳定，可供团队 C 使用
- `scripts/test-updated-smoke.py`、`scripts/test-updated-restart-smoke.py`、`scripts/test-updated-platform-profile-smoke.py`、`scripts/test-updated-firmware-backend-smoke.py` 稳定通过

### WP3：Tier 1 硬件 bring-up 与跨重启证据闭环

**剩余任务**

- 基于 `bringup/` handoff kit 在目标机器执行安装、首启、回退、恢复采样
- 采集至少两次不同 `boot_id` 的真实 evidence，并生成可归档报告
- 为 Tier 1 正式机器建立独立 profile、已知问题清单和 firmware hook 配置
- 将 QEMU 证据口径与实机证据口径统一，避免两套不同报告结构

**完成标志**

- 至少形成一份 Tier 1 实机成功 bring-up 记录
- 至少形成一份实机安装后 second boot 证据
- 至少形成一份真实更新失败后的回退或恢复记录
- `scripts/test-hardware-boot-evidence-smoke.py`、平台介质 smoke 与实机采样报告形成闭环

---

## 5. 未完成里程碑

### M1：first-boot 与 image-level gate 收敛
- first-boot、installer、recovery、cross-reboot 的脚本与日志口径稳定
- delivery bundle 到 image 的 staging 来源固定
- 首启失败留痕与关键服务启用验证固定化

### M2：update / rollback / recovery 最小平台闭环成立
- `update.check` / `update.apply` / `update.rollback` / `recovery.surface.get` 形成稳定链路
- 至少一条失败更新后的 rollback 或 recovery 路径可重放
- 团队 C 消费的 recovery surface 字段冻结

### M3：Tier 1 平台可验收
- 至少一份 Tier 1 bring-up 成功报告
- 至少一份实机安装后 second boot 证据
- 至少一份实机 update / rollback / recovery 证据
- 团队 E 的 release checklist 可以直接引用团队 A 的 artifact 和报告

---

## 6. 当前验收口径（仅未完成部分）

- first-boot 必须达到可重复启动、失败可留痕、结果可归档，而不是仅有一次性 smoke 成功
- `updated` 必须补齐实机 update / rollback / recovery 证据，不能只停留在仓库级与 QEMU 级验证
- firmware hook、boot slot、rollback hint、recovery surface 必须在目标平台形成连续状态链
- 团队 E 必须能直接消费团队 A 输出的日志、JSON、报告和 evidence index 引用


## 7. 跨团队输入输出

### 7.1 依赖输入

- 团队 B：`updated` 相关 policy / health / recovery hooks / RPC 契约冻结
- 团队 C：recovery surface 字段消费需求、installer / recovery shell surface 接口约束
- 团队 E：evidence schema、validation report 模板、CI / release gate 规则

### 7.2 对外输出

- 给团队 C：recovery surface JSON / RPC、失败状态字段、diagnostic bundle 引用
- 给团队 E：image artifact、boot / recovery / update / hardware evidence、validation report 输入
- 给项目层：Tier 1 bring-up 报告、平台差异说明、发布阻塞项

---

## 8. 不负责内容

- 不负责 shell GUI / chooser / portal 交互实现
- 不负责 `agentd` / `sessiond` / `policyd` / `runtimed` 主业务逻辑
- 不负责 provider / runtime backend 主能力实现
- 不负责 `deviced` 多模态采集实现
- 不负责团队 E 的统一报告模板和发布治理主逻辑

---

## 9. 防冲突规则

1. 团队 A 只在平台交付、更新恢复、硬件 bring-up 范围内修改代码，不越权接管控制面和 UI 主逻辑
2. 所有 recovery / update 的用户可见需求优先通过 JSON / RPC 暴露，不直接绑定特定 shell 实现
3. 平台差异优先沉淀到 profile、bridge、hook 和 evidence schema，不散落成脚本分叉
4. 高影响 boot / update / recovery 契约变更需先完成 ADR 或 schema 评审
