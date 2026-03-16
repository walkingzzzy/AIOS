# AIOS 五团队并行开发分工方案

## 1. 总体拆分原则

1. 只拆分当前**未完成、部分实现、仅有 skeleton/placeholder、文档已规划但未落地**的工作。
2. 以现有代码边界拆分：优先按 `services/`、`runtime/`、`image/`、`shell/`、`compat/`、`hardware/` 的真实目录归属划分主责。
3. 同一能力只设一个**主责团队**，其他团队只能通过冻结接口联调，避免重复开发。
4. 以“谁拥有主目录、谁拥有主实现、谁补主测试”为原则，而不是按抽象概念随意分工。
5. 先冻结共享接口，再并行推进各自目录：重点冻结 RPC、schema、profile、descriptor、worker contract、provider capability、observability event 格式。
6. 每个团队必须同时负责：实现、测试、文档/ADR 同步、验收证据。

## 2. 五个团队总览表

| 团队名称 | 主责模块 | 主要目标 | 上游依赖 | 关键交付物 |
|---|---|---|---|---|
| 团队1：控制面与 Provider 编排团队 | `services/agentd` `services/sessiond` `services/policyd` `providers/system-intent` `providers/system-files` | 把控制面从骨架联调推进到稳定编排/审批/记忆/portal-provider 闭环 | 需冻结 runtime RPC、device state RPC、shell control RPC | 控制面联调闭环、provider 调用链、审批/任务/记忆联调测试 |
| 团队2：运行时与推理后端团队 | `services/runtimed` `runtime/` `providers/runtime-local-inference` | 把 runtime 从 scheduler/budget skeleton 推到真实 GPU/NPU/worker/backend 路线 | 需冻结 runtime schema、worker contract、route/runtime profile | 真实 backend 接入、worker 管理、runtime observability、backend/integration tests |
| 团队3：设备与多模态团队 | `services/deviced` `providers/device-metadata` 及相关 device/runtime helper | 把 deviced 从 adapter skeleton 推到正式 portal/PipeWire/libinput/camera/backend 状态链 | 需冻结 device RPC、capture request schema、policy metadata、shell backend state view | 原生 backend、状态恢复、indicator/backend-state、设备集成测试 |
| 团队4：Shell 与交互界面团队 | `shell/` 及与 shell 直接相关的 provider/runtime | 把 panel/compositor 从 placeholder-only 推到正式 UI 与嵌入/窗口策略 | 依赖控制面 RPC、device backend state、approval/task/portal handle 模型 | 正式 panel host、compositor embedding、GUI 验收、shell acceptance tests |
| 团队5：平台交付与兼容生态团队 | `image/` `services/updated` `compat/` `hardware/` 及交付/验证脚本 | 把镜像/更新/恢复/硬件验证/compat bridge 推到 release-grade 交付基线 | 依赖 shell recovery surface 接口、runtime platform profile、device/hardware profile | Tier 1 bring-up、installer/recovery/update 闭环、compat 正式 bridge、交付证据 |

## 3. 团队 1 详细说明：控制面与 Provider 编排团队

### 3.1 团队名称
控制面与 Provider 编排团队

### 3.2 负责范围
**负责模块**：`aios/services/agentd`、`aios/services/sessiond`、`aios/services/policyd`、`aios/providers/system-intent`、`aios/providers/system-files`、相关 `docs/system-development/13/14/20/21`。

**负责什么**：
- `agentd` 的 planner/replan/provider route/portal 任务编排闭环
- `sessiond` 的 task state、memory、portal handle 持久化与 migration runner 收敛
- `policyd` 的 approval/token/audit/query/control-plane evidence 收敛
- `system-intent`、`system-files` provider 的正式 control-plane 接入与约束落地

**不负责什么**：
- 不负责 GPU/NPU backend 与 runtime worker 实现
- 不负责 device capture backend
- 不负责 shell GUI 具体实现
- 不负责 image/build/recovery/installer/bring-up

### 3.3 具体开发任务
1. 把 `agentd` 的 planner / recovery / multi-step flow 从 skeleton 联调升级为正式任务编排链。
2. 完成 `sessiond` 的 SQLite migration runner、task/working/episodic/procedural memory 持久化收敛。
3. 完成 `policyd` 的 approval state machine 深化、target-bound constraints、跨服务 evidence query/export 接口。
4. 收敛 `provider registry + portal + system-files/system-intent` 的正式控制面调用路径，避免每个调用点重复接 provider 逻辑。
5. 增加 `agentd -> sessiond -> policyd -> provider` integration tests，而不是只保留 smoke。
6. 为 shell/compat/device 提供稳定只读查询接口：任务详情、approval 列表、portal handle、audit/query 结果。

### 3.4 输入与输出边界
**输入依赖**：runtime 的稳定 RPC；device 的稳定 `device.state.get`/capture metadata；shell 需要的 task/approval/query 只读接口需求。

**输出产物**：
- 修改 `services/agentd|sessiond|policyd/src/*`
- 修改 `providers/system-intent/*`、`providers/system-files/*`
- 新增控制面 integration tests、audit/export tests、migration tests
- 更新相关 README、设计文档、必要 ADR/接口文档

### 3.5 并行开发约束
- 独立目录：`services/agentd`、`services/sessiond`、`services/policyd`、`providers/system-intent`、`providers/system-files`
- 必须先冻结：task/approval/portal/audit 查询 RPC、provider capability descriptor、token constraints schema
- 避免冲突：shell 团队不能在 `services/policyd` 内新增 GUI 专用业务逻辑；compat 团队不能重复实现 control-plane registration 审批逻辑

### 3.6 优先级
**高**。因为它是 shell、compat、device、provider 联调的控制面基础。
- 阻塞项：approval/query/token/portal/task 只读接口冻结
- 可并行项：memory 持久化、system-files/system-intent integration、evidence export

## 4. 团队 2 详细说明：运行时与推理后端团队

### 4.1 团队名称
运行时与推理后端团队

### 4.2 负责范围
**负责模块**：`aios/services/runtimed`、`aios/runtime/`、`aios/providers/runtime-local-inference`、相关 runtime schema/profile/platform 资产。

**负责什么**：
- `runtimed` scheduler/queue/budget/backpressure/backend lifecycle
- `runtime/` 下 route-profile/runtime-profile/schema/worker contract
- `runtime-local-inference` provider 从 embedding/rerank skeleton 到正式 backend 接入
- runtime observability 与跨服务 event sink

**不负责什么**：
- 不负责 `agentd` task planning
- 不负责 shell GUI
- 不负责 image build/recovery 实机交付
- 不负责 device capture backend

### 4.3 具体开发任务
1. 将 `local-gpu` / `local-npu` managed worker 从 wrapper baseline 推到真实 vendor runtime 接入。
2. 完成 worker readiness、health、restart、timeout、fallback、budget enforcement 的正式实现。
3. 补齐跨服务 runtime observability sink，向 shell/operator audit/updated 输出稳定事件。
4. 将 `runtime-local-inference` 的 embedding/rerank 从 `provider-skeleton` 升级为正式模型或 vendor-backed 能力。
5. 完成 route/runtime profile 的平台化收敛，避免 image/platform/updated/runtime 各写一套逻辑。
6. 增加 backend/failure injection/image-device integration tests。

### 4.4 输入与输出边界
**输入依赖**：平台 profile、hardware profile、updated 注入的 platform env；控制面对 runtime infer/embed/rerank 的稳定调用契约。

**输出产物**：
- 修改 `services/runtimed/src/*`、`runtime/*`、`providers/runtime-local-inference/*`
- 新增 GPU/NPU backend tests、worker contract tests、budget/fallback tests
- 输出稳定 runtime schema/profile、health notes、observability 事件格式

### 4.5 并行开发约束
- 独立目录：`services/runtimed`、`runtime/`、`providers/runtime-local-inference`
- 必须先冻结：`runtime-*.schema.json`、worker request/response contract、backend health/event 字段
- 避免冲突：平台交付团队只能消费 runtime profile，不应在 `runtimed/src` 内实现 vendor backend；控制面团队不得复制 runtime route/budget 逻辑

### 4.6 优先级
**高**。因为 runtime backend 是本地 AI 路由与平台能力的核心阻塞项。
- 阻塞项：worker contract 冻结、platform runtime profile 冻结
- 可并行项：embedding/rerank 正式化、observability sink、budget enforcement

## 5. 团队 3 详细说明：设备与多模态团队

### 5.1 团队名称
设备与多模态团队

### 5.2 负责范围
**负责模块**：`aios/services/deviced`、`aios/providers/device-metadata`、`services/deviced/runtime/*`、相关 device 测试与支持矩阵文档。

**负责什么**：
- screen/audio/input/camera/ui_tree 的正式 backend
- capture request、retention、normalize、indicator/backend-state 状态链
- `device-metadata` provider 与 hardware/profile 能力映射
- `ui_tree`/backend-state 对 shell 的只读输出

**不负责什么**：
- 不负责 shell panel 具体 UI
- 不负责 image/update/recovery
- 不负责 runtime GPU/NPU backend
- 不负责 compat bridge

### 5.3 具体开发任务
1. 把 `deviced` 从 adapter skeleton 推进到正式 portal / PipeWire / libinput / camera backend。
2. 完成 `ui_tree` 支持矩阵与多桌面环境 backend 路线，形成 machine-readable support matrix 与真实实现对应关系。
3. 完成 continuous capture、retention、indicator、backend-state 的状态恢复和长期运行语义。
4. 补齐 `device.capture.*`、`device.state.get`、`device.object.normalize` 的正式集成测试和失败路径。
5. 把 `device-metadata` provider 与 hardware profile、runtime/backend state、support matrix 打通。
6. 提供 shell 可消费的 `backend-state.json` / RPC 只读模型，避免 shell 自己推断设备状态。

### 5.4 输入与输出边界
**输入依赖**：`policyd` 的 approval metadata/taint 约束；shell 对 indicator/backend-status 的展示模型；hardware profile 的能力声明。

**输出产物**：
- 修改 `services/deviced/src/*`、`providers/device-metadata/*`
- 新增原生 backend helper、device integration tests、readiness/failure injection tests
- 更新 `docs/system-development/16/25/30` 与支持矩阵

### 5.5 并行开发约束
- 独立目录：`services/deviced`、`providers/device-metadata`
- 必须先冻结：capture RPC、backend-state schema、support matrix 字段、approval metadata 字段
- 避免冲突：shell 团队不得在 `shell/` 内自行生成设备 readiness 逻辑；平台团队不得复制设备证据采集格式

### 5.6 优先级
**高**。因为正式 device backend 是 shell、agent、policy、hardware 验收的共同阻塞项。
- 阻塞项：native backend contract、backend-state schema
- 可并行项：device-metadata provider、matrix 文档、readiness/failure 测试

## 6. 团队 4 详细说明：Shell 与交互界面团队

### 6.1 团队名称
Shell 与交互界面团队

### 6.2 负责范围
**负责模块**：`aios/shell/` 全目录及 shell 直接相关 provider/runtime。

**负责什么**：
- GTK host、panel clients、panel bridge、shell session
- Smithay compositor baseline 到正式 panel embedding/stacking/window policy
- launcher/task/approval/recovery/operator-audit/device-backend-status/portal-chooser 等交互面
- shell acceptance、stability、compositor 验收路径

**不负责什么**：
- 不负责 control-plane 业务语义本身
- 不负责 device capture backend 实现
- 不负责 runtime backend
- 不负责 image/update/hardware bring-up

### 6.3 具体开发任务
1. 将 `placeholder-only` compositor surface 推到真实 panel embedding 与窗口管理。
2. 完成完整 shell role / xdg toplevel policy / stacking / focus / modal routing 实现。
3. 将 task-surface、approval-panel、recovery-surface、portal-chooser 从 panel skeleton 推到正式 GUI 流程。
4. 接通 `shell_session.py` 的正式 session 入口，收敛 GTK host / compositor host / fallback host 切换。
5. 接通 operator-audit、device-backend-status、notification-center 的长期可用 UI，而不是只读 JSON/text 模型。
6. 为 shell/compositor 增加 acceptance、stability、interactive、nested compositor 测试，并纳入 CI。

### 6.4 输入与输出边界
**输入依赖**：控制面团队提供 task/approval/query/portal 只读接口；设备团队提供 backend-state；平台团队提供 recovery/update surface contract。

**输出产物**：
- 修改 `shell/components/*`、`shell/runtime/*`、`shell/compositor/*`
- 新增 shell/compositor acceptance tests、GUI smoke、embedding tests
- 更新 `shell/README.md`、`ACCEPTANCE.md`、必要 ADR/接口说明

### 6.5 并行开发约束
- 独立目录：`shell/`
- 必须先冻结：shell provider capability、panel action event schema、task/approval/device/recovery 只读模型
- 避免冲突：控制面团队不应在 shell 内写业务逻辑；设备团队不应在 shell/components 中实现 backend adapter；平台团队只能定义 recovery surface contract，不能实现 shell host

### 6.6 优先级
**中高**。因为 shell 是用户可见层，但其上游依赖较多，适合在接口冻结后并行推进。
- 阻塞项：approval/task/recovery/device 只读接口冻结
- 可并行项：compositor embedding、panel GUI 化、shell acceptance/CI

## 7. 团队 5 详细说明：平台交付与兼容生态团队

### 7.1 团队名称
平台交付与兼容生态团队

### 7.2 负责范围
**负责模块**：`aios/image/`、`aios/services/updated`、`aios/compat/`、`aios/hardware/`、交付与验证脚本、相关 CI/发布文档。

**负责什么**：
- image/build/installer/recovery/platform media
- `updated` 的 sysupdate/rollback/firmware hook/platform backend
- compat 的 browser/office/mcp-bridge/code-sandbox 正式 bridge/worker/registration 治理
- Tier 1 hardware bring-up、support matrix、evidence/report/export

**不负责什么**：
- 不负责 shell GUI 具体实现
- 不负责 agent/session/policy 控制面语义
- 不负责 runtimed 内部 backend 实现
- 不负责 deviced 原生 backend 实现

### 7.3 具体开发任务
1. 将 image/installer/recovery 从 QEMU 验证推进到 Tier 1 实机安装、首启、回滚、恢复证据闭环。
2. 将 `updated` 的 generic bridge 推到 vendor-specific firmware hook、失败注入、boot-success/rollback 实证。
3. 将 browser/office 从 baseline runtime 推到正式 remote bridge/document worker/conversion pipeline。
4. 将 `mcp-bridge` 从 HTTP baseline 推到 fleet/control-plane registration、attestation、rotation、revoke 闭环。
5. 将 compat shared audit/query/operator-facing evidence 继续推进到长期可用交付与脚本化查询。
6. 将硬件 bring-up kit、Tier 1 nomination、support matrix 与实际证据绑定，产出 release gate 需要的硬件签收材料。
7. 补齐 image/update/compat/hardware 的 CI、nightly、artifact validation、failure injection。

### 7.4 输入与输出边界
**输入依赖**：runtime 团队提供 platform runtime profile；shell 团队提供 recovery/approval/operator-audit 展示接口；控制面团队提供 provider registration / policy verify / token/query 接口。

**输出产物**：
- 修改 `image/*`、`services/updated/*`、`compat/*`、`hardware/*`、相关 `scripts/*`
- 产出 installer/recovery media、Tier 1 bring-up report、rollback evidence、compat bridge/runtime tests、release gate artifacts
- 更新支持矩阵、runbook、release checklist、operator 文档

### 7.5 并行开发约束
- 独立目录：`image/`、`services/updated`、`compat/`、`hardware/`
- 必须先冻结：platform profile、firmware hook contract、compat worker/result contract、provider registration fields、hardware evidence schema
- 避免冲突：runtime 团队不应在 `image/` 内分叉 profile 语义；shell 团队不应改 `updated` 业务逻辑；控制面团队不应重复实现 compat registration 治理

### 7.6 优先级
**高**。因为当前发行级阻塞最集中在 image/update/hardware/compat bridge。
- 阻塞项：Tier 1 实机证据、vendor firmware hook、compat registration 治理闭环
- 可并行项：installer UX、audit/report/export、nightly/CI 收敛

## 8. 跨团队依赖与接口冻结建议

1. **先冻结控制面只读接口**：`task.*`、`approval.*`、`portal.handle.*`、audit/query/export；主责团队1。
2. **冻结 runtime contract**：`runtime-*.schema.json`、worker contract、backend health/event 字段；主责团队2。
3. **冻结 device contract**：`device.capture.*`、`device.state.get`、backend-state schema、support matrix 字段；主责团队3。
4. **冻结 shell UI 输入模型**：panel snapshot、panel action event、recovery surface/task/approval/device status view model；主责团队4。
5. **冻结平台与 compat 交付契约**：platform profile、firmware hook contract、compat worker/result contract、hardware evidence schema；主责团队5。
6. 所有跨团队接口必须先在 `docs/` 或 schema 文件中冻结，再进入并行实现。

## 9. 推荐开发顺序（分阶段并行计划）

### 第一阶段：必须完成（接口冻结 + 阻塞项）
- 团队1：冻结 task/approval/portal/audit/query 接口
- 团队2：冻结 runtime schema、worker contract、platform runtime profile
- 团队3：冻结 device RPC、backend-state schema、support matrix 字段
- 团队5：冻结 platform profile、firmware hook contract、compat worker/result contract、hardware evidence schema
- 团队4：基于冻结接口，先收敛 shell 输入模型与 compositor/panel host 边界

### 第二阶段：可扩展并行推进（主实现）
- 团队1：完成控制面持久化、审批与 provider 编排联调
- 团队2：完成 GPU/NPU/worker/backend 主实现与 observability
- 团队3：完成原生 device backend 与 indicator/backend-state
- 团队4：完成 panel GUI 化、compositor embedding、operator audit/recovery/task/approval UI
- 团队5：完成 updated/vendor hook、compat 正式 bridge、Tier 1 bring-up、installer/recovery/update 闭环

### 第三阶段：收敛与验收
- 跨服务 integration tests、failure injection、nightly image validation、Tier 1 实机签收
- 把 shell acceptance、runtime backend、device backend、compat bridge、updated rollback 纳入统一 release gate
- 更新 README、模块 README、`docs/system-development/*`、runbook、支持矩阵、发布标准

## 10. 潜在冲突点与规避建议

1. **`services/policyd` 与 `compat/` 的 registration/policy 校验冲突**
   - 规避：registration 治理主责团队5；审批/校验语义主责团队1。
2. **`runtime/` profile 与 `image/` platform env 注入冲突**
   - 规避：profile 语义主责团队2；注入与交付主责团队5。
3. **`deviced` 状态模型与 `shell/components/device-backend-status` 冲突**
   - 规避：状态生成主责团队3；UI 展示主责团队4。
4. **`updated` recovery surface 与 `shell/recovery-surface` 冲突**
   - 规避：恢复业务语义主责团队5；界面与交互主责团队4。
5. **`agentd` 编排逻辑与 `system-intent`/`system-files` provider 职责重叠**
   - 规避：能力执行主责 provider；任务编排、route、approval、portal 决策主责团队1。
6. **多个团队同时改 `docs/system-development/*`**
   - 规避：按模块文档归属更新；跨团队共享接口文档只能由主责团队提交，其余团队通过引用方式使用。

## 11. 最终建议

最稳定、冲突最小的拆分方式不是按“产品能力名词”划分，而是按**主目录所有权 + 共享接口冻结 + 测试责任归属**划分。按本方案执行后：

- 团队1拥有控制面与 provider 编排闭环
- 团队2拥有 runtime/backend 正式化
- 团队3拥有 device/backend 正式化
- 团队4拥有 shell/compositor/GUI 正式化
- 团队5拥有 image/updated/compat/hardware 交付闭环

这样 5 个团队可以真正并行推进，同时把当前 AIOS 最明显的未完成区域全部覆盖，并最大限度减少同目录冲突和重复开发。
