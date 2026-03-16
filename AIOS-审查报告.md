# AIOS 项目现状审查报告

生成时间：基于当前工作区 `e:\AIOS` 的静态审查结果

## 1. 审查范围与方法

本次审查覆盖以下范围：

- 核心服务层：`aios/services/`
- Provider 层：`aios/providers/`
- 镜像与启动层：`aios/image/`
- 运行时层：`aios/runtime/`
- Shell 层：`aios/shell/`
- 兼容层：`aios/compat/`
- 硬件支持：`aios/hardware/`
- 设计与架构文档：`aios/README.md`、`aios/adr/*`、`docs/system-development/*`、`docs/AIOS-Project-Architecture.md`
- CI/CD：`.github/workflows/aios-ci.yml`

审查方法：

1. 对比 README / ADR / 架构文档中的“当前状态”“缺口”“下一步”与实际代码实现
2. 检查核心实现文件中的 skeleton / placeholder / fallback / panic / smoke 证据
3. 核查工作区依赖与 CI 测试覆盖情况
4. 汇总已规划但尚未实现或仅部分实现的能力

---

## 2. 总体结论

AIOS 当前已经不是“纯文档仓库”，而是一个**具备可编译核心服务、可运行 smoke harness、可构建镜像与 QEMU 闭环的系统原型仓库**。但从实际证据看，它仍然明显处于 **In Progress / Partial Impl / Skeleton-heavy** 阶段。

最核心的判断如下：

1. **控制面主链路已建立，但很多能力仍是骨架实现**：服务能启动、能走 RPC、能跑 smoke，但不少模块依旧以 `skeleton`、`placeholder`、`baseline` 语义存在。
2. **镜像与交付链进展较大，但“发行级闭环”尚未成立**：QEMU、installer、recovery、sysupdate 路径已存在，但缺 Tier 1 实机成功安装、升级、回滚证据。
3. **Shell / compositor / compat / device backend 是当前最明显的未完成区**：文档与代码都承认大量能力尚未真正落地。
4. **CI 覆盖面广，但深度偏浅**：大量测试是 smoke，缺少实机、长时间稳定性、复杂交互、深度集成和失败注入验证。

---

## 3. 实际存在的问题

# 3.1 严重问题

### S1. 多个核心模块仍以 skeleton / placeholder 形态存在，无法支撑发行级能力宣称

**问题描述**

项目多个关键模块虽然已可编译、可通过 smoke，但实际实现仍停留在骨架阶段，无法证明这些能力达到可发布或稳定可用水平。

**影响范围**

- `aios/services/README.md`
- `aios/runtime/README.md`
- `aios/shell/README.md`
- `aios/compat/README.md`
- `docs/system-development/19-实现映射与当前进度.md`

**证据**

- `aios/services/README.md:19-27` 明确写明核心服务处于“第一批源码骨架阶段”，`updated`、`deviced` 仍是 skeleton。
- `aios/runtime/README.md:20-26` 写明已有 queue / budget / fallback / event surface，但“未有：真实 vendor GPU runtime integration、真实 vendor NPU runtime integration、跨服务 runtime 事件汇聚 sink”。
- `docs/system-development/19-实现映射与当前进度.md:36-41` 将 `agentd`、`runtimed`、`sessiond`、`policyd`、`deviced`、`updated` 全部标记为 `Partial Impl`。

---

### S2. Shell / compositor 仍以 placeholder surface 为主，正式 GUI / 完整窗口管理尚未落地

**问题描述**

Shell 虽然已经有 GTK host、Smithay compositor baseline 和多个 panel，但 compositor 仍保留明显的 placeholder-only 状态，正式桌面能力未真正完成。

**影响范围**

- `aios/shell/README.md`
- `aios/shell/compositor/src/session.rs`
- `aios/shell/compositor/src/main.rs`
- `aios/shell/compositor/default-compositor.conf`

**证据**

- `aios/shell/README.md:27`：明确写明“未有：完整窗口管理、真实 panel 嵌入、以及更完整的 shell role/xdg toplevel policy 组合；当前 renderer/backend 仍是 nested baseline，不是 DRM/KMS 级别完整桌面栈”。
- `aios/shell/compositor/src/main.rs:56`：直接输出 `AIOS shell compositor skeleton`。
- `aios/shell/compositor/src/session.rs:166-168`：`panel_embedding_status: "placeholder-only"`、`stacking_status: "placeholder-only"`。
- `aios/shell/compositor/src/session.rs:922-946`：在无嵌入 surface 时继续落到 `placeholder-only`。
- `aios/shell/compositor/default-compositor.conf:14`：仍使用 `placeholder_surfaces = ...`。

---

### S3. 设备采集与多模态能力缺正式原生 backend，关键硬件能力仍不可宣称稳定支持

**问题描述**

`deviced` 已有 RPC、状态、adapter contract，但正式 portal / PipeWire / libinput / camera backend 仍缺失，意味着屏幕、音频、输入、摄像头、多模态能力缺少真实执行栈。

**影响范围**

- `aios/services/deviced/README.md`
- `aios/services/deviced/service.yaml`
- `docs/system-development/18-开发主计划与任务状态.md`

**证据**

- `aios/services/deviced/service.yaml:38-40`：blockers 包括 `no-formal-native-portal-pipewire-input-backends`、`no-formal-ui-tree-stack`。
- `aios/services/deviced/README.md:66`：明确缺失“真实 portal / PipeWire / libinput / camera backend”。
- `docs/system-development/18-开发主计划与任务状态.md:151-152`：音频采集仍缺正式 PipeWire backend，输入事件仍缺真实 libinput backend。

---

### S4. 更新 / 回滚 / 恢复链虽然存在，但缺真实 Tier 1 硬件成功证据，发行级可靠性不足

**问题描述**

镜像、更新、恢复路径有 QEMU 闭环，但没有 Tier 1 实机成功 boot / rollback / recovery 证据，无法证明真实硬件上成立。

**影响范围**

- `aios/image/README.md`
- `aios/services/updated/README.md`
- `aios/hardware/README.md`
- `docs/system-development/30-支持矩阵与已知限制.md`

**证据**

- `aios/image/README.md:68-73`：明确指出缺真实 Tier 1 硬件上的成功安装 / 回滚记录、更多平台覆盖与实机验证。
- `aios/services/updated/README.md:52`：当前缺口为“真实 Tier 1 硬件 boot-success / rollback 证据、更多厂商特定 firmware hook 与失败注入验证”。
- `aios/hardware/README.md:22`：明确“未有：Tier 1 实机 bring-up 记录、真实平台成功 boot / rollback 报告”。
- `docs/system-development/30-支持矩阵与已知限制.md:56`：Tier 1 仍缺真实安装、首启和恢复证据。

---

### S5. Compat 层的 browser / office / MCP bridge 仍缺真正桥接执行栈

**问题描述**

兼容层已经有 descriptor、runtime、remote registry、审计与 policy 链路，但浏览器和 Office 仍主要停留在受限 fetch / 文本导出 / HTTP bridge 级别，不是完整 bridge。

**影响范围**

- `aios/compat/browser/README.md`
- `aios/compat/office/README.md`
- `aios/compat/mcp-bridge/README.md`
- `aios/compat/README.md`

**证据**

- `aios/compat/README.md:29`：明确“未有：browser / office 真桥接实现、fleet/control-plane 级 remote attestation 与 registration 治理闭环”。
- `aios/compat/browser/README.md:27,41-44`：仍未有 JS-rendered DOM、tab/window 生命周期、登录态、截图、下载、自动化执行栈。
- `aios/compat/office/README.md:29,43-46`：仍未有 `docx/xlsx/pptx` 原生解析、富布局导出、真正 Office 桥接或 GUI 自动化。
- `aios/compat/mcp-bridge/README.md:25-26`：未有 attestation / fleet 级 remote auth 治理、未有正式 remote provider registration control-plane integration。

---

# 3.2 中等问题

### M1. 运行时后端能力与文档目标存在明显落差，GPU/NPU 集成仍是占位实现

**问题描述**

`runtimed` 已有 backend abstraction、managed worker、fallback、budget accounting，但实际 vendor GPU/NPU backend 尚未接通。

**影响范围**

- `aios/runtime/README.md`
- `aios/services/runtimed/src/backend/mod.rs`
- `docs/system-development/18-开发主计划与任务状态.md`

**证据**

- `aios/runtime/README.md:26`：明确未有真实 vendor GPU/NPU integration。
- `aios/services/runtimed/src/backend/mod.rs:268`：测试中通过 `fs::write(..., "ready\n")` 制造 `worker socket placeholder`。
- `docs/system-development/18-开发主计划与任务状态.md:171`：GPU/NPU 仍缺真实硬件级验证。

---

### M2. Provider 层能力不均衡，只有少数 provider 属于“真实 runtime”

**问题描述**

workspace 中只有 `device-metadata`、`runtime-local-inference`、`system-intent`、`system-files` 四个 Rust provider；而更多文档中规划的 provider 仍停留在 descriptor/runtime skeleton 或兼容层脚本实现。

**影响范围**

- `aios/Cargo.toml`
- `docs/system-development/18-开发主计划与任务状态.md`
- `aios/providers/runtime-local-inference/src/ops.rs`

**证据**

- `aios/Cargo.toml:15-18`：workspace provider 成员仅四个。
- `docs/system-development/18-开发主计划与任务状态.md:132`：明确“仍缺更多正式 provider runtime”。
- `aios/providers/runtime-local-inference/src/ops.rs:144,161,233,250`：embedding / rerank 显式标记为 `embedding-skeleton`、`rerank-skeleton`、`provider-skeleton`。

---

### M3. CI 范围很广，但大量验证停留在 smoke，缺少更深层集成和实机验证

**问题描述**

CI 已覆盖 workspace build/test、provider smoke、shell smoke、image smoke，但从 workflow 名称和现有文档看，验证深度主要是 smoke，而非长期稳定性、复杂场景、实机或失败注入。

**影响范围**

- `.github/workflows/aios-ci.yml`
- `docs/system-development/18-开发主计划与任务状态.md`

**证据**

- `.github/workflows/aios-ci.yml:100-253` 中大量 job 名称以 `smoke` 结尾。
- `.github/workflows/aios-ci.yml` 中未检索到 shell compositor 独立 CI 构建 / 测试项。
- `docs/system-development/18-开发主计划与任务状态.md:175`：明确“integration tests 仍不足”。

---

### M4. 文档成熟度高于实现成熟度，存在“规划很完整、代码尚未闭环”的结构性落差

**问题描述**

系统开发文档、ADR、路线图、支持矩阵、发布标准已经很完整，但实际代码普遍仍是 partial impl，这会放大认知偏差和交付预期风险。

**影响范围**

- `docs/system-development/*`
- `aios/README.md`
- `docs/IMPLEMENTATION_PROGRESS.md`

**证据**

- `aios/README.md:55-68` 顶层 README 已直接列出很多当前缺失项。
- `docs/system-development/19-实现映射与当前进度.md` 大量模块标为 `Partial Impl`。
- `docs/IMPLEMENTATION_PROGRESS.md:35,38,39` 也承认 shell、update/recovery、硬件 bring-up 仍未到 release-grade。

---

# 3.3 轻微问题

### L1. 多处实现与测试仍使用 skeleton / placeholder 命名，表明代码质量和完成度尚未收敛

**证据**

- `aios/services/agentd/src/main.rs:70`：`starting aios-agentd skeleton`
- `aios/services/deviced/src/main.rs:242`：`starting aios-deviced skeleton`
- `aios/shell/components/*/panel.py` 多处使用 `shell-panel-skeleton`
- `aios/shell/compositor/src/surfaces.rs`、`session.rs` 多处出现 `placeholder-only`

---

### L2. 一些 panic / expect 用于测试辅助虽不一定是生产缺陷，但暴露实现边界仍偏脆弱

**证据**

- `aios/services/deviced/src/adapters.rs:1843`：`panic!("missing plan for {modality}")`
- `aios/services/deviced/src/backend.rs:1076,1301`：`panic!("missing status for {modality}")`
- `aios/services/policyd/src/rpc.rs:452`：`panic!("RPC {method} failed unexpectedly: {error:?}")`

说明：这些大多位于测试辅助路径，但也说明部分验证依赖强假设，而不是更稳健的断言与错误恢复设计。

---

## 4. 未实现的功能

# 4.1 services/

### agentd
- 功能名称：formal chooser / approval GUI / recovery 深化 / 多步执行流
- 文档描述：`aios/services/agentd/README.md:75`
- 当前实现状态：部分实现
- 相关路径：`aios/services/agentd/README.md`、`aios/services/agentd/src/*`

### runtimed
- 功能名称：真实 GPU worker、真实 NPU worker、跨服务 runtime event sink
- 文档描述：`aios/services/README.md:44`、`aios/runtime/README.md:26`
- 当前实现状态：部分实现 / 骨架
- 相关路径：`aios/services/runtimed/src/*`、`aios/runtime/*`

### sessiond
- 功能名称：SQLite migration runner 与更完整持久化收敛
- 文档描述：`aios/services/README.md:45`
- 当前实现状态：部分实现
- 相关路径：`aios/services/sessiond/src/*`、`aios/services/sessiond/migrations/*`

### policyd
- 功能名称：更广的跨服务 evidence query、统一导出面、更细 target-bound constraints
- 文档描述：`docs/system-development/18-开发主计划与任务状态.md:50,139`
- 当前实现状态：部分实现
- 相关路径：`aios/services/policyd/src/*`、`aios/policy/*`

### deviced
- 功能名称：正式 portal / PipeWire / libinput / camera backend、正式 visible indicator / shell surface
- 文档描述：`aios/services/deviced/README.md:66`
- 当前实现状态：部分实现
- 相关路径：`aios/services/deviced/src/*`、`aios/services/deviced/runtime/*`

### updated
- 功能名称：真实 Tier 1 boot-success / rollback 证据、vendor-specific firmware hook、失败注入验证
- 文档描述：`aios/services/updated/README.md:52-59`
- 当前实现状态：部分实现
- 相关路径：`aios/services/updated/src/*`、`aios/services/updated/platforms/*`

# 4.2 providers/

### runtime-local-inference
- 功能名称：正式 embedding / rerank 模型后端
- 文档描述：`aios/providers/runtime-local-inference/README.md:18`
- 当前实现状态：仅有 skeleton
- 相关路径：`aios/providers/runtime-local-inference/src/ops.rs`

### 更多正式 provider runtime
- 功能名称：扩展 first-party provider fleet
- 文档描述：`docs/system-development/18-开发主计划与任务状态.md:132`
- 当前实现状态：部分实现，现有 workspace provider 数量有限
- 相关路径：`aios/providers/*`、`aios/Cargo.toml`

# 4.3 image/

### 图形化 installer 与实机媒体发现
- 功能名称：真正图形化 installer 与实机媒体发现
- 文档描述：`aios/image/README.md:71`
- 当前实现状态：部分实现
- 相关路径：`aios/image/installer/*`、`scripts/test-installer-ux-smoke.py`

### 真实硬件 update / rollback / recovery 闭环
- 功能名称：Tier 1 实机成功安装、回滚、恢复证据
- 文档描述：`aios/image/README.md:70-73,94-97`
- 当前实现状态：缺失
- 相关路径：`aios/image/*`、`scripts/build-aios-platform-media.py`、`scripts/test-boot-qemu-*`

# 4.4 runtime/

### vendor GPU / NPU integration
- 功能名称：真实 vendor GPU runtime、真实 vendor NPU runtime
- 文档描述：`aios/runtime/README.md:26,47-49`
- 当前实现状态：部分实现 / 骨架
- 相关路径：`aios/runtime/*`、`aios/services/runtimed/src/backend/*`

### 跨服务 runtime observability sink
- 功能名称：runtime 事件汇聚 sink
- 文档描述：`aios/runtime/README.md:26,49`
- 当前实现状态：缺失
- 相关路径：`aios/runtime/*`、`aios/observability/*`

# 4.5 shell/

### 正式 shell GUI / 完整 compositor
- 功能名称：完整窗口管理、真实 panel embedding、正式 GUI / compositor
- 文档描述：`aios/shell/README.md:27,47-49`
- 当前实现状态：部分实现 / placeholder-heavy
- 相关路径：`aios/shell/compositor/*`、`aios/shell/runtime/*`、`aios/shell/components/*`

### workspace manager / 更完整 shell role
- 功能名称：完整 shell role、stacking 调度、窗口策略
- 文档描述：`aios/shell/README.md:49`
- 当前实现状态：部分实现
- 相关路径：`aios/shell/compositor/src/*`

# 4.6 compat/

### browser 真桥接执行栈
- 功能名称：JS-rendered DOM、tab/window session、登录态、多页交互、下载/自动化
- 文档描述：`aios/compat/browser/README.md:27,41-44`
- 当前实现状态：部分实现
- 相关路径：`aios/compat/browser/*`

### office 真文档 worker / 转换 pipeline
- 功能名称：`docx/xlsx/pptx` 原生解析、富布局导出、Office automation worker
- 文档描述：`aios/compat/office/README.md:29,43-46,50`
- 当前实现状态：部分实现
- 相关路径：`aios/compat/office/*`

### MCP / A2A 正式 fleet/control-plane 治理闭环
- 功能名称：attestation、rotation、revoke、正式 registration control-plane integration
- 文档描述：`aios/compat/mcp-bridge/README.md:25-26,38-40`
- 当前实现状态：部分实现
- 相关路径：`aios/compat/mcp-bridge/*`

### operator-facing 持久 audit correlation / query GUI
- 功能名称：更强交互式审计关联查询工作流
- 文档描述：`aios/compat/README.md:29,43`
- 当前实现状态：部分实现
- 相关路径：`aios/compat/audit-query/*`、`aios/shell/components/operator-audit/*`

# 4.7 hardware/

### Tier 1 实机 bring-up 签收
- 功能名称：Tier 1 实机启动、回滚、跨重启验证报告
- 文档描述：`aios/hardware/README.md:22,35-39`
- 当前实现状态：缺失
- 相关路径：`aios/hardware/*`、`scripts/evaluate-aios-hardware-boot-evidence.py`

### 正式支持矩阵的实证闭环
- 功能名称：把条件能力声明落实为真实平台证据
- 文档描述：`aios/hardware/README.md:28-31`
- 当前实现状态：部分实现
- 相关路径：`aios/hardware/profiles/*`、`docs/system-development/30-支持矩阵与已知限制.md`

---

## 5. CI/CD 与测试覆盖结论

### 已具备的优点

- 有 `cargo test --workspace`
- 有核心服务与 provider 的 build
- 有 provider / shell / compat / image / updated / deviced 多类 smoke
- 有 delivery bundle、image、recovery image、installer image 构建流程

### 主要不足

1. 大量验证仍是 smoke，难证明复杂真实场景稳定性
2. 缺少 Tier 1 实机自动化验证
3. shell compositor 未见明确纳入主 CI 构建测试矩阵
4. 文档已多次承认 integration tests 仍不足

---

## 6. 优先级建议

### 第一优先级
1. 补齐 `deviced` 正式 backend：portal / PipeWire / libinput / camera
2. 补齐 `updated` 与 `image` 的 Tier 1 实机安装 / 回滚 / 恢复证据
3. 将 shell/compositor 从 placeholder-only 推进到真实 embedding 与窗口管理

### 第二优先级
1. 接入真实 vendor GPU/NPU runtime
2. 将 browser / office / MCP compat 从 baseline bridge 推进到正式 worker / registration 治理闭环
3. 增加跨服务 runtime / policy / compat / shell observability correlation

### 第三优先级
1. 扩大 first-party provider fleet
2. 增加更强集成测试、失败注入测试、长稳测试
3. 收敛文档与实现成熟度标签，避免过度乐观表述

---

## 7. 最终判断

AIOS 当前最准确的定位是：

> **一个文档体系成熟、架构方向清晰、核心主链路已打通，但仍以原型/骨架实现为主的 AI OS 控制面与系统交付仓库。**

它已经具备：
- 可编译的核心服务
- 可运行的 provider / compat / shell 原型
- 可构建的 image / installer / recovery / QEMU 交付链
- 相对完善的 ADR、支持矩阵、发布标准和治理文档

但它仍然缺少：
- 正式设备 backend
- 正式 shell / compositor 桌面能力
- 正式 browser / office / MCP bridge 执行栈
- 真正的 vendor GPU/NPU 集成
- Tier 1 实机证据与发行级闭环

因此，**当前不应把 AIOS 定义为“已完成的系统产品”，更适合定义为“已进入系统原型后期、正在向 release-grade 收敛的工程仓库”。**

