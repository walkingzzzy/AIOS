# AIOS 系统开发方案

**创建日期**: 2026-03-23  
**基准版本**: 基于仓库截至 2026-03-23 的实际状态  
**适用范围**: 从当前基线推进至 Developer Preview → Product Preview → Stable Release 的全周期开发计划

---

## 一、项目定位与背景

AIOS 是一个 **AI 原生操作系统（Route B）** 系统工程项目，目标是构建一个以 AI 为认知内核、以 Linux 为执行根基的完整操作系统。

### 1.1 核心技术栈

| 层级 | 技术选型 |
|------|----------|
| 系统主语言 | Rust（edition 2021，rust-version 1.85） |
| 异步运行时 | Tokio |
| 存储 | SQLite（rusqlite bundled） |
| 服务管理 | systemd |
| 镜像构建 | mkosi（Fedora 42 x86-64） |
| 壳层渲染 | Smithay Wayland compositor + GTK4/libadwaita |
| 本地 IPC | Unix Domain Socket + JSON-RPC 2.0 |
| Shell/Compat 层 | Python |
| CI | GitHub Actions |

### 1.2 系统架构分层

```text
Hardware / Firmware
    ↓
Linux Kernel / Drivers / cgroup v2
    ↓
Boot / Image / Recovery / Update（mkosi + systemd-boot + systemd-sysupdate）
    ↓
System Manager（systemd）
    ↓
AIOS Core Services
  ├─ Control Plane: agentd / sessiond / policyd
  ├─ Runtime Plane: runtimed
  ├─ Device Plane: deviced
  └─ Trust Plane: updated / audit
    ↓
AIOS Shell / Wayland Compositor
    ↓
Compat Providers / Code Sandboxes
    ↓
User Workloads
```

### 1.3 五团队并行责任矩阵

| 团队 | 目录所有权 | 主要职责 |
|------|-----------|---------|
| **团队 A** | `image/`、`hardware/`、`delivery/`、`updated/` | 镜像、启动、安装、更新、回滚、恢复、硬件 bring-up |
| **团队 B** | `agentd/`、`sessiond/`、`policyd/`、`runtimed/`、共享 crate | 核心控制面、IPC/contract、安全治理 |
| **团队 C** | `shell/`、`aios-portal/` | 正式 shell、panel、chooser GUI、portal 交互 |
| **团队 D** | `deviced/`、`providers/`、`compat/`、`sdk/` | device、provider fleet、compat、sandbox 执行生态 |
| **团队 E** | `observability/`、`tests/`、`.github/workflows/`、发布文档 | 观测、验证、CI、证据归档、发布门槛治理 |

---

## 二、当前项目进度评估（截至 2026-03-23）

### 2.1 总体成熟度

| 主线 | 估算完成度 | 状态 | 核心判断 |
|------|-----------|------|---------|
| 镜像与启动链 | 98% | ✅ Near Complete | mkosi/QEMU/installer/recovery 均有证据；SELinux + audit 安全硬化已集成 |
| 更新/恢复 | 95% | ✅ Near Complete | sysupdate/rollback/recovery 有 smoke + delivery 验证 16/16；QEMU 全量 pass |
| Registry/Portal | 95% | ✅ Near Complete | 共享库、4 种 portal、chooser prototype 已齐备；模型生命周期管理器已落地 |
| 定义/规格/ADR | 92% | ✅ Near Complete | 文档 00-41 已冻结，ADR-0001~0010 已存档；SELinux policy 全覆盖 |
| Policy/Token/Audit | 92% | ✅ Near Complete | evaluator/approval/token/audit store/taint/capability catalog 完整；SELinux 6 服务全覆盖 |
| Runtime/Backend | 92% | ✅ Near Complete | wrapper 架构 + GPU 支持矩阵 + worker contract + local-cpu worker + 模型生命周期管理 |
| 仓库骨架 | 90% | ✅ Near Complete | Rust workspace 六服务 + 五 crate 可编译，CI 三 workflow 运行；sandbox policy 已集成 |
| Shell/Compositor | 90% | ✅ Near Complete | GTK4 desktop host + Smithay compositor + 10 panel + GTK4 renderer + damage tracking + multi-output |
| Compat/Sandbox | 90% | ✅ Near Complete | worker contracts + bubblewrap 3 隔离配置 + remote registry + control-plane + seccomp |
| 多模态/Device | 90% | ✅ Near Complete | formal native adapter contract + 4 runtime helpers + 媒体捕获协调模块 4 后端 + backend manager |
| 核心服务实现 | 88% | ✅ Near Complete | 六服务 RPC + smoke + observability.jsonl shared sink + SELinux + sandbox 全覆盖 |
| 硬件 Bring-up | 82% | In Progress | Tier1 报告已录入，QEMU baseline 全量 pass，evidence 工具链齐备，待实机签收 |

**综合完成度**: P0-P5 任务 205/211 Done（97.2%），12 条主线平均估算完成度 **~92%**

### 2.2 已实质落地的部分

- 系统路线从 Electron/App 思维切换到 OS/Runtime 系统工程
- Rust Workspace 建立，六个核心服务 + 五个共享 crate 均可编译
- UDS + JSON-RPC 跨服务 IPC 已验证
- 四条 first-party Provider（system-files、device-metadata、runtime-local-inference、system-intent）
- local-cpu reference worker 已实现（支持 llama-cpp / transformers / echo 三种模式）
- 可启动镜像（mkosi + QEMU 验证启动链、firstboot、recovery、installer）
- GitHub Actions CI（validate + system-validation + nightly-container-delivery）
- 约 100+ 个 Python smoke 测试脚本 + E2E intent flow 集成测试
- sessiond SQLite 持久化（session、task、memory、portal）
- policyd 完整 policy 体系（token、approval、audit、taint、capability catalog）
- GTK4 desktop host + 统一 panel GTK4 renderer + panel integration bridge
- Device backend manager 统一管理 5 个后端（screen/audio/input/camera/ui_tree）
- Tier1 Bring-up 报告（Framework Laptop + NVIDIA Jetson）已入仓
- 五团队并行开发总计划根文档已建立
- Python 依赖管理 requirements.txt 已建立
- 170+ 个 Markdown 文档（路线图、ADR、发布标准、运维手册等）
- SELinux policy module + 文件上下文 (6 服务全覆盖)
- 系统级 sandbox policy（3 个 bubblewrap 隔离配置）
- 模型生命周期管理器（scan/register/validate/inventory）
- 媒体捕获协调模块（PipeWire/V4L2/libinput/Portal 4 后端）
- Smithay compositor damage tracking + multi-output state management
- QEMU baseline 全量 validation evidence（pass）
- mkosi.conf 安全硬化（SELinux + audit + bubblewrap + seccomp）

### 2.3 剩余缺口

| # | 缺口 | 严重程度 | 影响范围 |
|---|------|---------|---------|
| 1 | Tier1 实机硬件签收 | 🟡 中 | 报告已录入、QEMU 已 pass，但需真实硬件上的安装/恢复证据 |
| 2 | Release-grade 长期稳定性 | 🟡 中 | 需要长时间运行测试与性能调优 |

---

## 三、总体开发策略

### 3.1 核心原则

1. **先闭合主环再扩展**：`boot → service → shell → policy → execution → audit → recovery`
2. **先冻结 contract 再写实现**：schema / profile / ADR 优先于代码
3. **先打通跨服务闭环再做单点深化**：IPC > UI
4. **先保证本地基线再扩展条件能力**：CPU-only > GPU > NPU > Cloud
5. **若缺工具链则继续做静态校验、harness、fixture，而不是停工**

### 3.2 三阶段目标

| 阶段 | 目标发布 | 目标时间 | 核心交付 |
|------|---------|---------|---------|
| **阶段一** | Developer Preview | T+3 月 | 正式 Shell 可用 + Tier1 实机启动 + 真实推理执行 |
| **阶段二** | Product Preview | T+9 月 | 多模态闭环 + GPU 加速 + 完整 Provider 生态 + 安全硬化 |
| **阶段三** | Stable Release | T+18 月 | 全支持矩阵 + 长期维护基线 + 发行工程成熟 |

---

## 四、阶段一：Developer Preview（T+3 月）

**目标**：形成第一个可试用的系统镜像，系统开发者能够安装、启动、通过 AI Shell 提交意图并看到执行结果。

### 4.1 里程碑分解

#### M1.1 正式 Shell/Compositor 最小可用版（T+6 周）

**负责团队**: 团队 C（Shell）  
**优先级**: P0 — 阻塞所有用户交互

| 任务 ID | 任务描述 | 产物 | 验收标准 |
|---------|---------|------|---------|
| DP-SHL-001 | Smithay compositor 正式窗口管理 | `aios-shell-compositor` 可管理多窗口 | 可在 QEMU 或 Tier1 上创建/移动/关闭窗口 |
| DP-SHL-002 | GTK4/libadwaita launcher 正式 GUI | `launcher` GTK4 实现 | 可展示意图输入框、最近会话、suggested launches |
| DP-SHL-003 | 通知中心正式 GUI | `notification-center` GTK4 实现 | 可展示系统通知、审批请求、设备状态 |
| DP-SHL-004 | 任务面板正式 GUI | `task-surface` GTK4 实现 | 可展示当前任务列表、执行进度、provider route |
| DP-SHL-005 | 审批面板正式 GUI | `approval-panel` GTK4 实现 | 可展示待审批操作、approve/deny 交互 |
| DP-SHL-006 | 恢复面板正式 GUI | `recovery-surface` GTK4 实现 | 可展示恢复状态、诊断入口 |
| DP-SHL-007 | Compositor ↔ Panel 嵌入集成 | compositor slot 与 GTK panel 联动 | panel 可通过 slot 嵌入 compositor，focus/stacking 正常 |
| DP-SHL-008 | Portal Chooser 正式 GUI | `portal-chooser` GTK4 实现 | 文件选择/导出目标/屏幕共享三类 portal 可通过 GUI 交互 |
| DP-SHL-009 | Shell session 正式启动流程 | `shell_session.py` formal entrypoint 稳定 | compositor + GTK host + panel 可一键拉起 |
| DP-SHL-010 | Shell 集成测试 | 更新 shell smoke 套件 | 所有 shell smoke + acceptance tests 通过 |

**当前进展（2026-03-23 更新）**：
- ✅ Smithay compositor 已有 seat/input baseline、slot-based layout、panel snapshot bridge、modal reservation / stacking policy
- ✅ GTK4 desktop host 已实现（`shell_desktop_gtk.py`），支持自动刷新与面板切换
- ✅ 统一 GTK4 panel renderer（`shell_panel_gtk_renderer.py`）已创建，所有组件可共用
- ✅ Panel integration bridge（`shell_panel_clients_integration.py`）支持一键拉起任意组件的 GTK4 窗口
- ✅ 10 个 shell component panel 均已有 model 层
- 🟡 剩余：compositor panel embedding 从 snapshot bridge 升级到 xdg surface 嵌入；release-grade 稳定性打磨

#### M1.2 真实 Runtime Backend 执行（T+6 周）

**负责团队**: 团队 B（核心控制面）+ 团队 D（Provider）  
**优先级**: P0 — 阻塞 AI 推理能力

| 任务 ID | 任务描述 | 产物 | 验收标准 |
|---------|---------|------|---------|
| DP-RUN-001 | 接入真实 CPU 推理 backend | `runtimed` + llama.cpp / candle 集成 | 可在 local-cpu 上完成文本推理请求并返回结果 |
| DP-RUN-002 | runtime worker 进程管理 | 基于 `runtime-worker-v1` contract 的 worker 进程 | worker 可通过 stdio/unix socket 与 runtimed 通信 |
| DP-RUN-003 | 推理结果流式返回 | `agentd` → `runtimed` → worker → 结果流 | Shell 任务面板可实时显示推理输出 |
| DP-RUN-004 | Budget enforcement 最小闭环 | runtimed budget/timeout 实际生效 | 超预算请求被拒绝并返回明确错误 |
| DP-RUN-005 | runtime-local-inference-provider 真实执行 | provider 不再是 skeleton façade | `runtime.infer.submit` 可触发真实推理并返回结果 |

**当前进展（2026-03-23 更新）**：
- ✅ `runtime-worker-v1` request/response schema 已冻结
- ✅ `wrapper.rs` 已支持 stdio/unix 双传输
- ✅ `local_cpu_worker.py` reference worker 已实现（llama-cpp / transformers / echo 三模式），19 个 smoke test 通过
- ✅ GPU 支持矩阵（`gpu-backend-support-matrix.yaml`）已冻结
- ✅ Jetson vendor_accel_worker.py + TensorRT/DLA 集成已落地
- 🟡 剩余：接入真实 ML 模型文件（GGUF 等）进行推理验证；流式返回对接 Shell

#### M1.3 Tier1 实机 Bring-up（T+8 周）

**负责团队**: 团队 A（平台交付）  
**优先级**: P0 — 阻塞发布验证

| 任务 ID | 任务描述 | 产物 | 验收标准 |
|---------|---------|------|---------|
| DP-HW-001 | Framework Laptop 13 AMD 7040 安装与启动 | 实机 bring-up 报告 | kernel/systemd/core services 成功启动 |
| DP-HW-002 | Framework Laptop first-boot 验证 | firstboot 证据 | machine-id/random-seed 初始化成功 |
| DP-HW-003 | Jetson Orin AGX 安装与启动 | 实机 bring-up 报告 | kernel/systemd/core services 成功启动 |
| DP-HW-004 | 实机 recovery/rollback 验证 | 跨重启证据 | 可从 recovery 分区恢复、可执行 rollback |
| DP-HW-005 | 实机 Shell 启动验证 | compositor + GTK 截图证据 | Shell 可在实机显示器上正常渲染 |
| DP-HW-006 | Container-native 二进制产线收敛 | 消除 host-bin-dir fallback | 镜像构建完全在容器内可重复 |

**当前进展（2026-03-23 更新）**：
- ✅ 两台 Tier1 机器已在 `tier1-nominated-machines.yaml` 冻结
- ✅ bring-up 工具链（collect/evaluate/render）已完整
- ✅ `40-Framework-Laptop-13-AMD-7040-Bring-up报告.md` 已入仓
- ✅ `41-NVIDIA-Jetson-Orin-AGX-Bring-up报告.md` 已入仓
- ✅ `collect-aios-device-validation.py` 本地采集链已就绪
- 🟡 剩余：在实机上跑通并产出 pass 记录；容器产线收敛

#### M1.4 核心服务联调收敛（T+8 周）

**负责团队**: 团队 B（核心控制面）  
**优先级**: P1

| 任务 ID | 任务描述 | 产物 | 验收标准 |
|---------|---------|------|---------|
| DP-SVC-001 | agentd → runtimed 真实推理闭环 | 集成测试 | 提交意图 → 规划 → 路由 → 推理 → 返回结果 |
| DP-SVC-002 | sessiond 编译验证与 CI 固化 | cargo test 通过 + CI green | 所有 sessiond 单测通过 |
| DP-SVC-003 | policyd 跨服务 evidence query | 统一导出面 | 可查询跨服务审计事件并关联 session/task |
| DP-SVC-004 | 六服务 systemd 联动验证 | 实机 systemd 启动证据 | 六服务同时拉起、IPC 互通、health 互报 |
| DP-SVC-005 | semantic memory 最小实现 | sessiond 嵌入索引接口 | 可存储和检索知识向量 |
| DP-SVC-006 | task event query API | sessiond RPC | 可按 session/task 查询完整事件链 |

#### M1.5 CI/CD 与发布工程（T+10 周）

**负责团队**: 团队 E（验证与发布）  
**优先级**: P1

| 任务 ID | 任务描述 | 产物 | 验收标准 |
|---------|---------|------|---------|
| DP-CI-001 | Image-level CI 自动构建 | CI workflow | 每次 push 自动构建 bootable image |
| DP-CI-002 | 集成测试自动化 | CI 集成测试 step | registry/provider/image 联调自动运行 |
| DP-CI-003 | Release gate 自动检查 | release gate report | machine-readable gate 在 CI 中自动执行 |
| DP-CI-004 | Release notes 生成 | DP release notes | 按模板生成含已知限制的 release notes |
| DP-CI-005 | Python 依赖管理 | `requirements.txt` 或 `pyproject.toml` | 所有 Python 脚本依赖固定版本 |

#### M1.6 端到端用户流验证（T+12 周）

**负责团队**: 全团队  
**优先级**: P0 — 发布 gate

| 任务 ID | 任务描述 | 产物 | 验收标准 |
|---------|---------|------|---------|
| DP-E2E-001 | 意图提交到结果显示全流程 | E2E 测试 | 用户在 launcher 输入意图 → agentd 规划 → runtimed 推理 → task-surface 展示结果 |
| DP-E2E-002 | 文件操作审批全流程 | E2E 测试 | 请求文件操作 → policyd 评估 → approval-panel 审批 → provider 执行 → 审计记录 |
| DP-E2E-003 | 恢复流程全验证 | E2E 测试 | 模拟系统异常 → recovery-surface 展示 → 诊断包导出 → rollback 成功 |
| DP-E2E-004 | 首次安装全流程 | E2E 测试 | 从安装介质启动 → installer → first-boot → Shell 出现 |

### 4.2 Developer Preview 退出条件

根据 `33-开发者预览发布标准.md`，必须满足：

- [x] 六个核心服务可编译、单测通过
- [x] `test-ipc-smoke.py` 通过
- [x] 高风险 capability 有 approval + audit + execution token 闭环
- [x] launcher / notification / task-surface / approval / recovery 至少有正式 GUI 或可工作 prototype
- [x] shell smoke tests 全部通过
- [x] provider registry resolution 可用，四条 first-party provider 有 smoke 证据
- [x] delivery bundle 可生成
- [ ] QEMU 与至少一台 Tier1 实机 bring-up 通过（QEMU ✅，Tier1 实机待签收）
- [x] 已附带支持矩阵、已知限制、版本兼容矩阵、validation report
- [x] release notes 与 upgrade/recovery runbook 已发布

---

## 五、阶段二：Product Preview（T+9 月）

**目标**：形成功能较完整的系统镜像，覆盖多模态感知、GPU 加速推理、完整 Provider 生态与深度安全治理。

### 5.1 里程碑分解

#### M2.1 多模态 Device Backend 真实闭环（T+4-6 月）

**负责团队**: 团队 D

| 任务 ID | 任务描述 | 产物 | 验收标准 |
|---------|---------|------|---------|
| PP-DEV-001 | Screen Portal 真实 backend | PipeWire ScreenCast 集成 | 可通过 portal 请求屏幕流并获取帧数据 |
| PP-DEV-002 | Audio PipeWire 真实 backend | PipeWire 音频采集 | 可采集系统音频并输出结构化数据 |
| PP-DEV-003 | Input libinput 真实 backend | libinput 事件流 | 可采集键盘/鼠标/触控事件 |
| PP-DEV-004 | Camera V4L2 真实 backend | v4l2 视频流 | 可采集摄像头帧数据 |
| PP-DEV-005 | AT-SPI ui_tree 完整实现 | 结构化 UI 树 | 可获取当前桌面应用的完整 accessibility tree |
| PP-DEV-006 | 多模态事件聚合 | deviced 融合引擎 | 可将屏幕+音频+输入统一为结构化上下文 |
| PP-DEV-007 | Continuous capture 发行级 | 持续采集管理器 | 长时间运行稳定，资源占用可控 |

**当前进展（2026-03-23 更新）**：
- ✅ 4 条 runtime helper（screen_portal_live / pipewire_audio_live / libinput_input_live / camera_v4l_live）已就位
- ✅ `BackendManager` 统一管理器已创建，支持 5 个后端的 probe/readiness/state
- ✅ Continuous capture manager 已实现（含 continuous-captures.json 输出）
- ✅ Formal native adapter contract 已统一（adapter_contract=formal-native-backend）
- 🟡 剩余：在 Linux 实机上调通真实 PipeWire/libinput/V4L2 管线

#### M2.2 GPU 加速推理（T+4-6 月）

**负责团队**: 团队 B + 团队 A（Jetson）

| 任务 ID | 任务描述 | 产物 | 验收标准 |
|---------|---------|------|---------|
| PP-GPU-001 | Jetson TensorRT 真实 worker | vendor_accel_worker.py 实机验证 | 在 Jetson Orin 上使用 TensorRT 完成推理 |
| PP-GPU-002 | x86 GPU backend（CUDA/ROCm） | runtimed GPU worker | 在 x86 独显上完成推理并验证性能提升 |
| PP-GPU-003 | GPU → CPU 自动 fallback 验证 | fallback smoke | GPU 不可用时自动切换到 CPU 并完成推理 |
| PP-GPU-004 | KV cache 内存预算管理 | runtimed memory budget | KV cache 超水位时自动驱逐或拒绝新请求 |
| PP-GPU-005 | 连续批处理实现 | runtimed continuous batching | 多请求自动 batching，吞吐量提升可量化 |

#### M2.3 Provider 生态扩展（T+5-7 月）

**负责团队**: 团队 D

| 任务 ID | 任务描述 | 产物 | 验收标准 |
|---------|---------|------|---------|
| PP-PVD-001 | Browser 真实 bridge worker | Chromium CDP 集成 | 可通过 provider 执行真实网页浏览和数据提取 |
| PP-PVD-002 | Office 真实 document worker | LibreOffice UNO 集成 | 可通过 provider 打开/编辑/导出文档 |
| PP-PVD-003 | MCP bridge 真实 remote 执行 | MCP 协议集成 | 可连接外部 MCP server 并执行工具调用 |
| PP-PVD-004 | Code sandbox bubblewrap 实机验证 | bubblewrap 隔离执行 | 代码在 OS 级 sandbox 中执行，可验证资源限制 |
| PP-PVD-005 | Provider attestation 基线 | remote provider 信任验证 | remote provider 注册时需通过 attestation 检查 |
| PP-PVD-006 | 更多 system provider | 网络/蓝牙/电源 等 | 至少新增 3 个 system-level provider |

#### M2.4 安全治理深化（T+6-8 月）

**负责团队**: 团队 B

| 任务 ID | 任务描述 | 产物 | 验收标准 |
|---------|---------|------|---------|
| PP-SEC-001 | 跨服务审计事件关联与导出 | 统一 audit exporter | 可按 session/task 导出完整审计链 |
| PP-SEC-002 | Policy engine 规则热加载 | policyd 动态规则 | 修改 policy profile 无需重启即可生效 |
| PP-SEC-003 | Fine-grained capability constraints | target-bound token | token 可绑定具体资源路径和操作约束 |
| PP-SEC-004 | Audit GUI 持久化面板 | operator-audit panel 正式版 | 可持久展示审计记录、支持筛选和详情查看 |
| PP-SEC-005 | Prompt injection 防御增强 | taint detection pipeline | 多层 taint 检测覆盖更多攻击向量 |

#### M2.5 更新/恢复发行级闭环（T+7-9 月）

**负责团队**: 团队 A

| 任务 ID | 任务描述 | 产物 | 验收标准 |
|---------|---------|------|---------|
| PP-UPD-001 | A/B update 实机验证 | 两台 Tier1 更新证据 | 可从 v1 更新到 v2 并验证功能正常 |
| PP-UPD-002 | Rollback 实机验证 | rollback 证据 | 更新失败时可回滚到上一版本 |
| PP-UPD-003 | Recovery 实机验证 | recovery 证据 | 系统损坏时可从 recovery 分区恢复 |
| PP-UPD-004 | 签名发行物 | 签名的镜像/更新包 | 所有发行物经过数字签名 |
| PP-UPD-005 | Vendor-specific firmware hook | 平台 firmware 适配 | Framework/Jetson 各有正式 firmware backend |

### 5.2 Product Preview 退出条件

根据 `34-产品预览发布标准.md`：

- [ ] 所有 Developer Preview 条件已满足
- [ ] Shell/compositor 达到正式可用级别
- [ ] 至少两类多模态（屏幕+音频或屏幕+输入）在 Tier1 硬件上稳定
- [ ] 至少一条 GPU 加速路径验证通过
- [ ] A/B update + rollback 在 Tier1 实机验证通过
- [ ] Provider 生态覆盖 system/shell/device/compat 四大类
- [ ] 安全审计覆盖所有高风险路径
- [ ] 两台 Tier1 完整 bring-up 报告

---

## 六、阶段三：Stable Release（T+18 月）

**目标**：形成可长期维护的稳定发行版，具备完整支持矩阵、安全基线与运维体系。

### 6.1 关键工作项

#### M3.1 条件能力闭环（T+10-14 月）

| 任务 ID | 任务描述 | 产物 |
|---------|---------|------|
| SR-CAP-001 | ui_tree 在正式图形栈上稳定 | AT-SPI 跨桌面验证报告 |
| SR-CAP-002 | local-npu 在 Jetson DLA 上验证 | NPU profile + worker |
| SR-CAP-003 | Trusted cloud offload beta | attestation + fallback + audit |
| SR-CAP-004 | 多显示器支持 | compositor 多输出 |
| SR-CAP-005 | 高刷新率支持 | compositor 帧率适配 |
| SR-CAP-006 | 触控增强 | 手势识别 + 触控优化 |

#### M3.2 产品化硬化（T+14-18 月）

| 任务 ID | 任务描述 | 产物 |
|---------|---------|------|
| SR-REL-001 | 支持矩阵最终冻结 | 全平台验证结果 |
| SR-REL-002 | 长期安全更新策略 | 安全响应 SOP |
| SR-REL-003 | 自愈 runbook 完整覆盖 | 自动化修复脚本 |
| SR-REL-004 | 性能基线冻结 | benchmark 结果与退化检测 |
| SR-REL-005 | API 稳定性保证 | breaking change policy |
| SR-REL-006 | 第三方 provider SDK 发布 | SDK 文档 + 样例 |
| SR-REL-007 | 安装程序 UX 优化 | GUI installer |
| SR-REL-008 | 完整国际化 | i18n 基础设施 |

### 6.2 Stable Release 退出条件

- [ ] 所有 Product Preview 条件已满足
- [ ] 支持矩阵覆盖至少两个正式平台
- [ ] 安全审计无 Critical/High 未修复项
- [ ] 升级/恢复在所有 Tier1 平台验证通过
- [ ] API 稳定性声明发布
- [ ] 运维 runbook 覆盖所有常见故障场景
- [ ] 发布工程自动化（CI/CD/签名/分发）

---

## 七、关键路径与风险管理

### 7.1 关键路径

```text
Shell GUI（M1.1）──────┐
                       ├──→ 端到端用户流（M1.6）──→ Developer Preview
Runtime Backend（M1.2）─┤
                       │
Tier1 Bring-up（M1.3）─┘
```

**关键路径上的三项（Shell GUI、Runtime Backend、Tier1 Bring-up）必须并行推进、同步收敛。**

### 7.2 风险登记

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|---------|
| Smithay compositor 在 Tier1 硬件上不稳定 | 中 | 高 | 保留 wlroots fallback 方案；优先在 QEMU 中稳定 |
| llama.cpp/candle 集成困难 | 低 | 高 | 选择社区成熟度最高的方案；保留 subprocess wrapper |
| Tier1 硬件驱动不兼容 | 中 | 中 | 优先使用 Fedora 42 内核默认驱动；准备补丁策略 |
| GTK4 在 Smithay compositor 上渲染异常 | 中 | 高 | 保留 nested Wayland 方案；先在 weston 上验证 |
| 团队资源不足导致并行推进受阻 | 高 | 高 | 严格按优先级排序；跨团队共享阻塞信息 |
| PipeWire/libinput 版本兼容问题 | 低 | 中 | 锁定 Fedora 42 版本；提前建立 CI 回归 |

### 7.3 阻塞清单与处理策略

| 当前阻塞 | 影响 | 处理策略 |
|----------|------|---------|
| Shell 正式 GUI 几乎为零 | 用户无法交互 | 阶段一 P0 任务，团队 C 全力投入 |
| Tier1 实机零记录 | 无法证明可行性 | 阶段一 P0 任务，团队 A 优先安排硬件 |
| 真实推理 worker 缺失 | AI 能力空壳 | 阶段一 P0 任务，团队 B 接入 llama.cpp |
| image 构建有 host-bin-dir fallback | 不可重复构建 | 阶段一内收敛 container-native 产线 |
| Python 依赖散落 | 构建不可靠 | 阶段一内补 requirements.txt |

---

## 八、开发节奏与协作机制

### 8.1 迭代周期

| 周期 | 频率 | 输出物 |
|------|------|--------|
| 每日 Stand-up | 每工作日 | 当日阻塞 + 进展 |
| Sprint 迭代 | 2 周 | Sprint review + demo |
| 里程碑检查 | 每月 | 里程碑报告 + 阻塞升级 |
| 发布决策 | 按阶段 | Release gate check + go/no-go |

### 8.2 每周状态同步

按 `26-每周状态同步模板.md` 格式输出：

- 本周完成项（附仓库证据链接）
- 当前阻塞项（附影响范围和升级计划）
- 新增 ADR 需求
- 下周目标

### 8.3 完成定义（Definition of Done）

一个任务从 `In Progress` 进入 `Done` 前必须满足：

1. **有仓库产物**：代码/配置/schema 已合并到主分支
2. **有验证证据**：至少有一条 smoke test 或单测覆盖
3. **有文档同步**：相关文档已更新（README/设计文档/API 文档）
4. **有回退说明**：高影响变更必须有 rollback 策略
5. **无 P0 Lint 告警**：代码通过 clippy/mypy 检查

### 8.4 代码审查规则

- 所有代码变更必须经过至少一人 review
- 涉及跨服务 contract 变更必须两人 review
- ADR 变更必须全团队 review
- 安全相关变更必须团队 B review

---

## 九、技术债务与改进计划

### 9.1 当前技术债务

| 债务项 | 严重程度 | 计划解决时间 |
|--------|---------|-------------|
| mkosi.extra 与源树大量文件重复 | 中 | 阶段一 M1.5 |
| Python 脚本无依赖管理 | 中 | 阶段一 M1.5 |
| 源码中缺少 TODO/FIXME 标记 | 低 | 持续改进 |
| compositor 独立 workspace 未纳入主 workspace | 低 | 阶段一 M1.1 |
| smoke 测试基于脚本而非测试框架 | 中 | 阶段二 |
| 缺乏性能基线和回归检测 | 中 | 阶段二 |

### 9.2 架构改进计划

| 改进项 | 目标 | 阶段 |
|--------|------|------|
| Rust workspace 统一（含 compositor） | 减少构建复杂度 | 阶段一 |
| smoke 测试迁移到 pytest 框架 | 提高测试可维护性 | 阶段二 |
| 引入性能 benchmark CI | 防止性能退化 | 阶段二 |
| Schema 版本管理与迁移 | 保证前向兼容 | 阶段二 |
| 引入 OCI 容器交付流水线 | 标准化分发 | 阶段二 |

---

## 十、资源需求评估

### 10.1 人力需求

| 团队 | 当前估算人力 | 阶段一增强建议 | 关键技能需求 |
|------|------------|--------------|-------------|
| 团队 A（平台） | 1-2 人 | 建议 2 人 | Linux 系统、mkosi、systemd、硬件调试 |
| 团队 B（控制面） | 2-3 人 | 建议 3 人 | Rust、分布式系统、LLM 推理引擎 |
| 团队 C（Shell） | 1-2 人 | **建议 3 人** | Wayland/Smithay、GTK4、UI/UX 设计 |
| 团队 D（Provider） | 1-2 人 | 建议 2 人 | Python、浏览器自动化、设备驱动 |
| 团队 E（验证） | 1 人 | 建议 2 人 | CI/CD、测试工程、发布工程 |

**最关键的人力缺口在团队 C（Shell）**，因为 Shell 正式 GUI 几乎从零开始，且位于关键路径上。

### 10.2 硬件需求

| 设备 | 用途 | 数量 | 优先级 |
|------|------|------|--------|
| Framework Laptop 13 AMD 7040 | Tier1 x86 验证 | 1 台 | P0 |
| NVIDIA Jetson Orin AGX | Tier1 ARM+GPU 验证 | 1 台 | P0 |
| x86 台式机（独显） | GPU 推理开发 | 1 台 | P1 |
| 通用 x86 服务器 | CI runner | 1 台 | P1 |

### 10.3 基础设施需求

| 需求 | 描述 | 优先级 |
|------|------|--------|
| GitHub Actions 扩容 | image build 耗时长，需要更多并行 runner | P1 |
| 私有 registry | 存放构建产物和容器镜像 | P2 |
| 内部 CDN/Mirror | 加速依赖下载 | P2 |

---

## 十一、质量保障策略

### 11.1 测试金字塔

```text
              ┌───────────┐
              │   E2E     │  ← 端到端用户流（阶段一末尾）
              │  Tests    │
            ┌─┴───────────┴─┐
            │  Integration  │  ← 跨服务联调（阶段一中期）
            │    Tests      │
          ┌─┴───────────────┴─┐
          │   Smoke Tests     │  ← 当前 97 个 Python 脚本（持续扩展）
          │                   │
        ┌─┴───────────────────┴─┐
        │     Unit Tests        │  ← Rust 内联单测（60+ 文件）
        │                       │
      ┌─┴───────────────────────┴─┐
      │    Static Analysis        │  ← cargo clippy + py_compile（CI 已有）
      └───────────────────────────┘
```

### 11.2 CI/CD 流水线增强计划

| 阶段 | 新增 CI Step | 触发条件 |
|------|------------|---------|
| 阶段一 | Image 构建 + QEMU boot 验证 | 每次 push 到 main |
| 阶段一 | 集成测试（registry+provider+IPC） | 每次 push 到 main |
| 阶段二 | 性能 benchmark 回归 | 每周定时 |
| 阶段二 | Tier1 硬件自动测试 | 每次 release tag |
| 阶段三 | 安全扫描（cargo-audit + bandit） | 每次 push |

### 11.3 Release Gate 规则

每次发布前必须通过 `docs/RELEASE_CHECKLIST.md` 定义的 machine-readable gate，包括：

- cargo build/test 全绿
- smoke suite 全绿
- delivery validation 全绿
- release gate report 无 blocking failure
- 已知限制已声明

---

## 十二、附录

### A. 任务 ID 编码规则

| 前缀 | 含义 |
|------|------|
| DP- | Developer Preview 阶段任务 |
| PP- | Product Preview 阶段任务 |
| SR- | Stable Release 阶段任务 |
| SHL | Shell 相关 |
| RUN | Runtime 相关 |
| HW | 硬件相关 |
| SVC | 核心服务相关 |
| CI | CI/CD 相关 |
| E2E | 端到端测试相关 |
| DEV | Device 相关 |
| GPU | GPU 相关 |
| PVD | Provider 相关 |
| SEC | 安全相关 |
| UPD | 更新/恢复相关 |
| CAP | 条件能力相关 |
| REL | 发布相关 |

### B. 与现有文档体系的映射关系

| 本方案章节 | 对应系统文档 |
|-----------|------------|
| 项目定位 | `01-总体定位与边界.md`、`02-目标架构.md` |
| 当前进度 | `19-实现映射与当前进度.md`、`IMPLEMENTATION_PROGRESS.md` |
| 阶段目标 | `04-阶段路线图.md`、`05-优先级-Backlog.md` |
| 任务分解 | `21-完整任务清单.md`、`22-执行任务看板.md` |
| 退出条件 | `06-首批验收标准.md`、`33/34/35-发布标准.md` |
| 团队职责 | `18-开发主计划与任务状态.md` |
| 风险管理 | `37-阶段运行手册与阻塞清单索引.md` |

### C. 关键文档索引

| 文档 | 路径 |
|------|------|
| 系统定义 | `docs/system-development/00-AIOS-定义与分级.md` |
| 目标架构 | `docs/system-development/02-目标架构.md` |
| 技术选型 | `docs/system-development/17-技术选型与框架矩阵.md` |
| 核心服务设计 | `docs/system-development/20-核心服务详细设计.md` |
| ADR 列表 | `aios/adr/README.md` |
| 发布检查清单 | `docs/RELEASE_CHECKLIST.md` |
| 实施进展 | `docs/IMPLEMENTATION_PROGRESS.md` |
| 支持矩阵 | `docs/system-development/30-支持矩阵与已知限制.md` |

### D. 术语表

| 术语 | 定义 |
|------|------|
| Route B | AIOS 的系统工程路线，区别于原先的桌面应用路线 |
| Tier 0 | QEMU 虚拟机验证目标 |
| Tier 1 | 正式支持的实机硬件目标 |
| Provider | AIOS 能力抽象的执行单元 |
| Portal | 受控的资源访问句柄（文件/屏幕/导出目标） |
| Capability | AIOS 系统中可管控的能力声明 |
| Execution Token | policyd 签发的一次性执行凭证 |
| Compat Layer | 旧应用/协议的兼容桥接层 |
| Smoke Test | 最小可行性验证测试 |
| Bring-up | 在新硬件/环境上首次成功运行 |

### E. 本轮更新记录（2026-03-23）

| 变更项 | 说明 |
|--------|------|
| 基准日期 | 2026-03-23（持续更新） |
| 综合完成度 | P0-P5 任务 205/211 Done（97.2%），12 条主线平均完成度 ~92% |
| 新增产物 | SELinux policy module（6 服务全覆盖）、bubblewrap 3 隔离配置、模型生命周期管理器、媒体捕获协调模块（4 后端）、Smithay damage tracking + multi-output、QEMU baseline 全量 pass、mkosi.conf 安全硬化 |
| 退出条件 | Developer Preview 10 项退出条件中 9 项已满足，仅 Tier1 实机签收待完成 |
| 缺口收敛 | 核心缺口从 5 项缩减为 2 项，所有🔴已消除，仅剩 2 个🟡 |

---

> **本文档随项目推进持续更新。任何重大变更需经团队 review 后修订。**
