# AIOS Route B 实施进展

**更新日期**: 2026-03-14

---

> **系统开发口径修订（2026-03-08）**
> AIOS 统一定义为 **AI 原生操作系统 / 系统软件工程**。本文如提及桌面应用、Electron 客户端、应用适配器、App 安装等内容，除非明确标注为“原型期 / 兼容层 / 历史实现”，否则不再代表目标形态。
> 当前最高约束：**系统镜像、系统服务、系统壳层、设备/能力抽象、权限与更新恢复**。

## 1. 现状结论

当前仓库**已经不是纯兼容层原型**，而是一个正在推进中的 AIOS 系统工程基线：

- `aios/` Rust workspace 已包含六个核心服务与共享 crate
- `provider registry / portal / runtime / shell / compat` 已有 smoke 与单测基线
- `image / delivery / installer / recovery / QEMU` 已有构建脚本与验证入口

但它**仍不足以宣称“AIOS 已完成”**：正式 shell/compositor、真实 runtime backend、实机安装恢复与 release-grade 更新闭环仍未完成。

## 2. 已形成的系统基线

| 能力域 | 状态 | 说明 |
|--------|------|------|
| 核心服务与本地 IPC | ✅ | 六个核心服务已可编译、可测试，并通过本地 smoke |
| Provider / Portal / Runtime 基线 | ✅ | registry、portal handle、provider 解析、`runtime-local-inference-provider` façade 与 runtimed backend smoke 已打通；关键 first-party provider 现已补共享 lifecycle observability，`system-files-provider` audit 也已对齐统一 schema，四条 first-party provider 也已统一补齐 startup-edge 与 registry-recovery lifecycle smoke |
| System delivery bundle | ✅ | 可构建 `out/aios-system-delivery/`，并通过 delivery / firstboot hygiene smoke；`out/validation/` 现已产出 validation report、governance evidence index、cross-service correlation report、audit evidence report、cross-service health report、CI artifact governance report、high-risk audit coverage report、image build strategy report 与 release gate report，`tests/observability/validation-matrix.yaml` 也已固化 owner / command / artifact / failure symptom / triage 之外的 `workflow_jobs` / `coverage_domains` / `status_source` 元数据，`tests/observability/ci-artifact-governance.yaml` 还能校验 workflow 的 artifact 命名 / 下载复用 / retention 规则，而 `tests/observability/high-risk-audit-coverage.yaml` + `scripts/test-high-risk-audit-coverage-smoke.py` 现会卡住新增 `risk_tier=high` capability 与 Team A `update.apply` / `update.rollback` / `recovery.bundle.export` 的审计覆盖漂移；本轮还补齐了 delivery bundle 对 `release-shell-profile.yaml` 与 `aios/shell/compositor/` source/config 资产的镜像内同步，`scripts/test-image-delivery-smoke.py` 现会固定校验 `rootfs/` 与 `mkosi.extra/` 两侧 shell/compositor 资产一致性；`scripts/build-audit-evidence-report.py` 与 `scripts/test-audit-evidence-export-smoke.py` 继续把 `sessiond` / `policyd` / `runtimed` 的 approval / token / runtime / observability / audit-store 证据收口为 operator-facing report；`docs/RELEASE_CHECKLIST.md` 的 machine-readable rules 已直接驱动 release gate，cross-service health exporter 也已覆盖 `hardware` 组件与 evidence-index 输入，`sessiond` / `policyd` / `runtimed` / `updated` / `deviced` 也已可共享 `observability.jsonl` sink |
| 可启动镜像 / recovery / installer 基线 | 🟡 | 已有构建脚本、QEMU preflight、system validation 报告，以及 installer vendor/hardware 元数据、平台分区策略与 firmware hook 基线，但离发行级闭环仍有距离 |
| Compat / legacy 迁移资产 | 🟡 | browser / office / MCP / code sandbox / shell prototype 可用，且 browser / office / `mcp-bridge` 已分别补 `compat-browser-fetch-v1`、`compat-office-document-v1`、`compat-mcp-bridge-v1` 结构化 worker/result contract、失败样本与 schema-aligned 本地 JSONL audit envelope；`code-sandbox` 也已补显式 worker contract、policy-deny/timeout/error 结构化结果与 schema-aligned JSONL audit envelope；本轮进一步把 browser / office / `mcp-bridge` / `code-sandbox` 接进可选 centralized `execution_token` + `policyd` verify 通路与共享 `AIOS_COMPAT_OBSERVABILITY_LOG` sink，`code-sandbox` 也会在 `bubblewrap` 可用时优先启用 OS 级隔离；`mcp-bridge` 已补 persistent remote registry、`bearer` / `header` / `execution-token` remote auth strategy 与 target-bound token baseline；browser / office 现也已补 persistent remote registry、同组 remote auth/trust policy、remote bridge 执行，以及带 `attestation` / `governance` 元数据的 `register-control-plane -> agentd provider.register -> attested_remote resolve` 基线，并由各自 smoke 直接验证；`compat.audit.query.local` 也已补 saved query / query history / scriptable interactive audit query surface，`notification-center` 开始汇总 compat remote/policy/runtime 相关 operator audit 摘要，新增的 `operator-audit` panel 则已能持久展示跨服务 recent records / issue / task correlation；`audit-evidence-report` 现还会对 compat 输出 shared sink / centralized-policy / token-verified / per-provider timeout/deny 汇总，但整体仍是过渡层 |

## 3. 仍未完成的 OS 主线

| OS 工作项 | 状态 | 说明 |
|-----------|------|------|
| 正式 AI Shell / compositor | 🟡 | 已把 `aios/shell/runtime/shell_session.py` 从 prototype session bootstrap 收敛为 formal entrypoint：新增 `formal-shell-profile.yaml`、`entrypoint=formal` / `host_runtime=gtk4-libadwaita` profile 语义、GTK host command / nested fallback 计划渲染、host env 导出与 live snapshot/export 路径；`shell_snapshot.py` 现会输出 `active_modal_surface` / `primary_attention_surface` / `stack_order`、surface `shell_role` / `focus_policy` / `interaction_mode` / `blocked_by` / `stack_rank` 等正式壳层调度信息，GTK host / desktop runtime 也按 stack order 呈现；Smithay compositor 现已把 panel-host-only slot 的 modal reservation / stacking policy / topmost 选择收敛到 approval-first 语义，并通过 `panel_snapshot_path` / `panel_snapshot_command`、`panel_action_command`、`panel_action_events` / `panel_action_log_path` 与 launcher / approval / notification 等 panel 联动；本轮又把默认 compositor placeholder surface 扩到 launcher / task / approval / portal chooser / notification / recovery / capture indicators / device backend status 全量 formal shell role，补上 nested compositor 已起而 GTK host 启动失败时的 standalone fallback 路径，并在 compositor input routing 中加入 active-modal focus redirect，避免 modal slot 存在时下层 workspace/client 重新抢焦点；本地已验证 `scripts/test-shell-session-smoke.py`、`scripts/test-shell-panels-smoke.py`、`scripts/test-shell-desktop-smoke.py`、`scripts/test-shell-live-smoke.py`、`scripts/test-shell-compositor-smoke.py` 与 `cargo test -p aios-shell-compositor` 里的相关 unit test。Linux 实机上的长期稳定性与更多复杂窗口策略仍未到 release-grade |
| 真实 runtime backend 执行 | 🟡 | 已有 scheduler / fallback / budget 基线，并把 runtime profile 扩展到 `backend_worker_contract` + `backend_commands` + `managed_worker_commands`，`runtimed` health 现会暴露有效 worker contract / wrapper 计数与 managed worker 状态；同时已落地 `runtime-worker-v1` request/response schema 与 reference GPU/NPU worker（支持 `stdio` / `unix://` 两种本地 contract），并进一步把 `unix://` worker 执行路径收紧为必须返回匹配的 `worker_contract` / `backend_id`，避免错误 socket 或错误 worker 被误判为可用；`runtime-local-inference-provider` 也已补齐 `runtime.infer.submit` / `runtime.embed.vectorize` / `runtime.rerank.score` façade、自注册 health sync 与 dedicated smoke。本轮还新增 `docs/system-development/38-GPU-backend-首选支持矩阵评估.md`、`aios/runtime/gpu-backend-support-matrix.yaml` 与 `scripts/test-gpu-backend-support-matrix-smoke.py`，正式冻结 `local-cpu` 全局基线、Jetson `local-gpu` 首选路径与 CPU fallback 边界。仍需强调：这还是 reference worker contract，不是接上真实 vendor GPU/NPU 推理栈后的 release-grade backend |
| 原生设备适配器 | 🟡 | capture / policy / retention 流程已存在，并已把 command-adapter 改为受显式 probe gate 约束、补上 `ui_tree native-ready` adapter 与 `AIOS_DEVICED_UI_TREE_LIVE_COMMAND` 驱动的 AT-SPI live collector helper；本轮又把 builtin/native live 证据路径正式抬升为 formal native backend adapter contract，screen / audio / input / camera / `ui_tree` 现会区分 `*-native` 与 `*-probe` 两类 adapter id，并统一暴露 `adapter_contract=formal-native-backend` 元数据；同时只读 `ui_tree_snapshot` 已正式接入 `device.state.get` 与 `backend-state.json`，并进一步新增结构化 `ui_tree_support_matrix`，把 current-session / AT-SPI live / state-bridge / screen+OCR fallback 这些支持路径统一暴露给 `device.state.get`、`backend-state.json` 与 shell `device-backend-status` panel；与此同时新增 continuous native capture manager：`continuous=true` 的 screen/audio/input/camera 请求在 native execution path 下会启动后台 collector、周期刷新 `continuous-captures.json`，并把 `continuous_collectors` 同步暴露给 `device.state.get` 与 `backend-state.json`；仓库也已正式补齐 `screen_portal_live.py`、`pipewire_audio_live.py`、`libinput_input_live.py`、`camera_v4l_live.py` 四条 runtime helper 资产与 `AIOS_DEVICED_HELPER_PYTHON` / `/usr/bin/python3` 默认 helper 发现逻辑，这组 helper 现在还会统一输出 `request_binding` / `session_contract` / `transport` / `evidence` / `media_pipeline` 结构化 contract，并由 `scripts/test-deviced-runtime-helpers-smoke.py` 复验；现在 `deviced` 也会把 `device.state.reported`、`device.capture.requested`、`device.capture.rejected`、`device.capture.stopped` / `device.capture.stop.missed` 写入共享 `observability.jsonl` sink，并在 `scripts/test-deviced-policy-approval-smoke.py` 中验证 `approval_id` 关联、在 `scripts/test-cross-service-health-smoke.py` 中验证 cross-service shared sink 覆盖；已通过 `scripts/test-deviced-native-backend-smoke.py`、`scripts/test-deviced-readiness-matrix-smoke.py`、`scripts/test-deviced-smoke.py`、`scripts/test-deviced-continuous-native-smoke.py`、`scripts/test-deviced-runtime-helpers-smoke.py`、`scripts/test-deviced-policy-approval-smoke.py`、`scripts/test-cross-service-health-smoke.py` 与 `cargo test -p aios-deviced` 验证。真实 portal/PipeWire/libinput/camera 的 release-grade media pipeline 与完整 AT-SPI live tree 仍未齐备，但正式 native adapter contract 已不再只是 `*-probe` 命名 |
| update / rollback / recovery 发行闭环 | 🟡 | 已有 smoke、交付验证基线、runbook、operator 手册、支持矩阵/已知限制、Release Notes 模板与版本兼容矩阵；剩余缺口集中在 release-grade first-boot / recovery / update 的实机证据收敛 |
| 实机硬件 bring-up | 🟡 | 已有 QEMU 证据、boot evidence 采集/评估、Tier 1 profile-aware 报告与 evidence index 渲染工具链，bring-up kit 也已支持一键 collect/evaluate/render wrapper；本轮还冻结了 `framework-laptop-13-amd-7040` 与 `nvidia-jetson-orin-agx` 两台正式 Tier 1 机器，并把 nominated machine profile 接入 bring-up kit 导出链；但仍缺 Tier 1 实机成功记录 |

## 4. 当前代码在 Route B 中的保留价值

### 保留
- Intent / task orchestration
- task lifecycle / streaming model
- session persistence
- compat provider 的经验与接口
- MCP/A2A bridge

### 降级
- 历史 Electron / client 叙事
- “应用适配器”叙事
- 面向 App 安装与打包的发布流程

## 5. 下一阶段目标

1. 继续收敛 `agentd` / `sessiond` / `policyd` / `runtimed` / `deviced` / `updated` 的真实执行链路
2. 把镜像、installer、recovery、first-boot 与 update 验证继续推进到 release-grade 闭环
3. 用正式 shell/compositor 替换当前 prototype 壳层
4. 把 compat / legacy 资产继续收缩为迁移与桥接层

## 6. 进展汇报方式变更

此后所有进展文档统一按下列结构汇报：

- 镜像与启动
- 系统服务
- 壳层与会话
- 权限与审计
- 更新与恢复
- compat layer

不再以“客户端 UI 功能点数量”作为主进展指标。
