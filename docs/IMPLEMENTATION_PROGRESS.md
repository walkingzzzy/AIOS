# AIOS Route B 实施进展

**更新日期**: 2026-03-23

---

> **系统开发口径修订（2026-03-08）**
> AIOS 统一定义为 **AI 原生操作系统 / 系统软件工程**。本文如提及桌面应用、Electron 客户端、应用适配器、App 安装等内容，除非明确标注为"原型期 / 兼容层 / 历史实现"，否则不再代表目标形态。
> 当前最高约束：**系统镜像、系统服务、系统壳层、设备/能力抽象、权限与更新恢复**。

## 1. 现状结论

当前仓库**已经不是纯兼容层原型**，而是一个正在推进中的 AIOS 系统工程基线：

- P0–P5 任务整体进展 **195 / 211 Done**，剩余集中在 release-grade shell polish、实机 sign-off 与真实 ML inference 集成
- `aios/` Rust workspace 已包含六个核心服务与共享 crate
- `provider registry / portal / runtime / shell / compat` 已有 smoke 与单测基线
- `image / delivery / installer / recovery / QEMU` 已有构建脚本与验证入口
- 开发文档已达 **41 篇**（含 doc 40–41 Tier 1 bring-up 报告），覆盖系统全链路

但它**仍不足以宣称"AIOS 已完成"**：release-grade shell/compositor 打磨、真实 runtime backend ML 推理、实机安装恢复与 release-grade 更新闭环仍未完成。

## 2. 已形成的系统基线

| 能力域 | 状态 | 说明 |
|--------|------|------|
| 核心服务与本地 IPC | ✅ | 六个核心服务已可编译、可测试，并通过本地 smoke |
| Provider / Portal / Runtime 基线 | ✅ | registry、portal handle、provider 解析、`runtime-local-inference-provider` façade 与 runtimed backend smoke 已打通；first-party provider 已统一补齐 lifecycle observability、startup-edge 与 registry-recovery smoke |
| System delivery bundle | ✅ | 可构建 `out/aios-system-delivery/`，并通过 delivery / firstboot hygiene smoke；validation report、governance evidence index、cross-service correlation/health report、CI artifact governance report、release gate report 等均已产出；`sessiond` / `policyd` / `runtimed` / `updated` / `deviced` 已可共享 `observability.jsonl` sink |
| 可启动镜像 / recovery / installer 基线 | ✅ | 已有构建脚本、QEMU preflight、system validation 报告，installer vendor/hardware 元数据、平台分区策略与 firmware hook 基线均已就位；delivery bundle 对 shell/compositor 资产的镜像内同步已验证，镜像构建与 firstboot 链路可端到端跑通 |
| Compat / legacy 迁移资产 | ✅ | browser / office / MCP / code sandbox / shell prototype 可用，已接入 centralized `execution_token` + `policyd` verify 通路与共享 observability sink；`mcp-bridge` 已补 persistent remote registry 与 remote auth strategy；browser / office 已补 persistent remote registry、remote auth/trust policy 与 `register-control-plane -> agentd provider.register -> attested_remote resolve` 基线；`compat.audit.query.local` 已补 saved query / query history / scriptable interactive audit query surface；整体仍定位为过渡层，但功能闭环与审计覆盖已基本达标 |

## 3. 仍未完成的 OS 主线

| OS 工作项 | 状态 | 说明 |
|-----------|------|------|
| 正式 AI Shell / compositor | 🟡 | GTK4 desktop host 已存在，Smithay compositor 已支持全量 formal shell role（launcher / task / approval / portal chooser / notification / recovery / capture indicators / device backend status）与 modal reservation / stacking policy；本轮新增 **surface damage tracking** 与 **multi-output state management**，GTK4 renderer 也已对齐；`formal-shell-profile.yaml` 与 `entrypoint=formal` / `host_runtime=gtk4-libadwaita` profile 语义已落地。Linux 实机上的长期稳定性与 release-grade polish 仍在推进 |
| 真实 runtime backend 执行 | 🟡 | scheduler / fallback / budget 基线已有，`runtime-worker-v1` request/response schema 与 reference local-cpu worker 已落地；GPU backend 支持矩阵已冻结（`local-cpu` 全局基线、Jetson `local-gpu` 首选路径）；Jetson managed worker 路径已收敛到仓库内置 `vendor_accel_worker.py`；本轮新增 **model_manager.py 模型生命周期管理器**（scan / register / validate / inventory），worker 集成 profile 已全部建模。**仍需真实 ML 模型推理集成与实机 release-grade sign-off** |
| 原生设备适配器 | 🟡 | formal native backend adapter contract 已落地（screen / audio / input / camera / `ui_tree` 区分 `*-native` 与 `*-probe`），continuous native capture manager 与四条 runtime helper 资产已就位；本轮新增 **media_capture.py 媒体捕获协调模块**（screen / audio / camera / ui_tree 四个后端，统一 session 管理）。真实 portal/PipeWire/libinput/camera 的 release-grade media pipeline 仍未齐备 |
| update / rollback / recovery 发行闭环 | 🟡 | 已有 smoke、交付验证基线、runbook、operator 手册、支持矩阵与版本兼容矩阵；本轮新增 **SELinux policy module**（aios-services.te/fc，覆盖 6 个服务）与**系统级 bubblewrap sandbox profiles**，mkosi.conf 已完成安全硬化（6 个安全包 + SELinux 内核参数）；剩余缺口集中在 release-grade first-boot / recovery / update 的实机证据收敛 |
| 实机硬件 bring-up | 🟡 | 整体进度 **82%**。Tier 1 bring-up 报告（doc 40–41）已入仓，覆盖 `framework-laptop-13-amd-7040` 与 `nvidia-jetson-orin-agx` 两台正式 Tier 1 机器；bring-up kit 已支持一键 collect/evaluate/render wrapper 与 `collect-aios-device-validation.py` 本地采集链；本轮 **QEMU baseline validation evidence 已全量 validated-pass**，Tier 1 nominated machines 状态已推进，evidence toolchain 已完善。仍缺 Tier 1 实机成功 sign-off 记录 |

## 4. 当前代码在 Route B 中的保留价值

### 保留
- Intent / task orchestration
- task lifecycle / streaming model
- session persistence
- compat provider 的经验与接口
- MCP/A2A bridge

### 降级
- 历史 Electron / client 叙事
- "应用适配器"叙事
- 面向 App 安装与打包的发布流程

## 5. 下一阶段目标

1. **Release-grade shell polish**：将 GTK4 desktop host + Smithay compositor 推进到实机长稳、多窗口策略完备的发行级壳层
2. **真实 ML inference 集成**：把 `local-cpu` reference worker 替换为真实模型加载 / 推理执行，验证 Jetson TensorRT/DLA 端到端链路
3. **Tier 1 实机 sign-off**：完成 Framework Laptop 与 Jetson Orin AGX 的真实安装、firstboot、recovery 与 update 验收
4. **系统稳定化**：收敛剩余 16 项未完成任务，把 compat / legacy 资产继续收缩为迁移桥接层

## 6. 进展汇报方式变更

此后所有进展文档统一按下列结构汇报：

- 镜像与启动
- 系统服务
- 壳层与会话
- 权限与审计
- 更新与恢复
- compat layer

不再以"客户端 UI 功能点数量"作为主进展指标。
