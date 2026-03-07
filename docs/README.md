# AIOS 系统开发文档中心

**版本**: 2.1.0 | **状态**: Route B / 系统开发路线 | **更新**: 2026-03-08

---

> **系统开发口径修订（2026-03-08）**
> AIOS 统一定义为 **AI 原生操作系统 / 系统软件工程**。本文如提及桌面应用、Electron 客户端、应用适配器、App 安装等内容，除非明确标注为“原型期 / 兼容层 / 历史实现”，否则不再代表目标形态。
> 当前最高约束：**系统镜像、系统服务、系统壳层、设备/能力抽象、权限与更新恢复**。

## 定位

AIOS 不再被定义为“运行在现有操作系统上的 AI 系统应用”。
自 2026-03-08 起，AIOS 文档、协议、架构和发布口径统一切换到 **系统开发**：

- AIOS 的目标是构建 **AI 原生操作系统 / 系统软件栈**
- 当前仓库中的 `packages/client` 与 `packages/daemon` 仅视为 **原型期兼容层**
- 所有协议设计均以 **系统镜像、系统服务、系统壳层、能力权限模型、更新与恢复** 为最高优先级

## 文档地图



### 系统开发专项

| 文档 | 用途 |
|------|------|
| [系统开发方案](system-development/README.md) | Route B 的全新系统开发总方案与系统规格索引 |
| [AIOS 定义与分级](system-development/00-AIOS-定义与分级.md) | 冻结 AIOS 的工程定义、最小交付物与成熟度等级 |
| [信任边界与威胁模型](system-development/07-信任边界与威胁模型.md) | 明确 AIOS 的安全边界、审批边界与高风险场景 |
| [用户、会话与进程模型](system-development/08-用户-会话-进程模型.md) | 明确主体、会话、任务、进程与资源治理模型 |
| [镜像、安装、更新与恢复规范](system-development/09-镜像-安装-更新-恢复规范.md) | 明确 AIOS 必须是可启动、可回滚、可恢复的系统 |
| [能力、策略与审计规范](system-development/10-能力-策略-审计规范.md) | 明确 capability、风险分级、审批链与审计链 |
| [应用、兼容层与沙箱模型](system-development/11-应用-兼容层-沙箱模型.md) | 明确 compat、第三方 workload 与沙箱边界 |
| [硬件目标与 Bring-up 矩阵](system-development/12-硬件目标与Bring-up矩阵.md) | 明确支持平台、硬件优先级与 bring-up 路线 |
| [AI 控制流与应用调用规范](system-development/13-AI控制流与应用调用规范.md) | 明确 AI 如何操作系统、如何调用应用与如何配置 AI |
| [Provider Registry 与 Portal 规范](system-development/14-provider-registry-与-portal-规范.md) | 明确 provider 如何注册、被发现，以及 portal 如何授予受限对象访问 |
| [Runtime Profile 与 Route Profile 规范](system-development/15-runtime-profile-与-route-profile-规范.md) | 明确 AI 的模型、路由、预算、降级与 profile 分层生效规则 |
| [多模态采集与设备能力规范](system-development/16-多模态采集与设备能力规范.md) | 明确屏幕、音频、输入、摄像头与环境状态如何进入系统感知层 |

### 战略与架构

| 文档 | 用途 |
|------|------|
| [项目架构](AIOS-Project-Architecture.md) | AIOS 的目标分层、服务边界、兼容层定位 |
| [发布路线](AIOS-Protocol-Release-Plan.md) | Route B 的阶段目标与里程碑 |
| [项目介绍](AIOS-Protocol-项目介绍.md) | 对外阐述 AIOS 的系统定位 |
| [构思文档](AIOS-Protocol-构思.md) | 为什么 AIOS 必须走系统开发 |
| [实现进展](IMPLEMENTATION_PROGRESS.md) | 当前仓库与目标 OS 的真实差距 |

### 协议规范

| 文档 | 用途 |
|------|------|
| [协议总览](protocol/00-Overview.md) | AIOS Protocol 的系统级范围与边界 |
| [核心概念](protocol/01-CoreConcepts.md) | provider、capability、policy、compat layer 等定义 |
| [正式规范](protocol/AIOS-Protocol-Spec.md) | 系统开发语境下的正式规范 |
| [传输层](protocol/02-Transport.md) | 本地优先的协议传输设计 |
| [消息类型](protocol/03-Messages.md) | 请求、事件、任务、审批消息 |
| [工具描述规范](protocol/04-ToolSchema.md) | provider / component 描述文件 |
| [权限模型](protocol/05-PermissionModel.md) | 系统能力、兼容层能力和风险分级 |

### 组件开发

| 文档 | 用途 |
|------|------|
| [适配器概述](adapters/00-Overview.md) | system provider / compat provider 的角色划分 |
| [组件开发](adapters/01-Development.md) | 如何开发系统服务、壳层组件、兼容提供者 |
| [开发规范](guides/AIOS-Protocol-DevSpec.md) | Route B 的仓库分层与开发约束 |
| [系统开发指南](guides/AIOS-System-DevGuide.md) | Linux-first AIOS 的实现建议 |
| [最佳实践](guides/AIOS-Developer-BestPractices.md) | 系统组件开发的质量、安全、观测规范 |
| [快速开始](guides/QUICK-START.md) | 新开发者进入 Route B 的最短路径 |

### 接口与研究

| 文档 | 用途 |
|------|------|
| [API 参考](api/Reference.md) | JSON-RPC 方法与命名空间迁移说明 |
| [研究报告目录](research/) | 外部方案研究；均以系统开发视角重新解读 |

## 阅读路径

### 我在做路线切换
1. [项目架构](AIOS-Project-Architecture.md)
2. [发布路线](AIOS-Protocol-Release-Plan.md)
3. [实现进展](IMPLEMENTATION_PROGRESS.md)

### 我在做系统服务
1. [协议总览](protocol/00-Overview.md)
2. [核心概念](protocol/01-CoreConcepts.md)
3. [组件开发](adapters/01-Development.md)
4. [开发规范](guides/AIOS-Protocol-DevSpec.md)

### 我在做 AI Shell / compositor
1. [项目架构](AIOS-Project-Architecture.md)
2. [系统开发指南](guides/AIOS-System-DevGuide.md)
3. [权限模型](protocol/05-PermissionModel.md)

### 我在做兼容层 / 过渡期原型
1. [实现进展](IMPLEMENTATION_PROGRESS.md)
2. [快速开始](guides/QUICK-START.md)
3. [API 参考](api/Reference.md)

## 统一用语

- `system.*`：核心操作系统能力
- `service.*`：第一方系统服务能力
- `shell.*`：会话、工作区、窗口与桌面壳层能力
- `device.*`：设备、传感器和硬件抽象能力
- `compat.*`：兼容层能力，用于桥接旧应用/浏览器/外部软件
- `professional.*`：专业域能力
- `mcp.*` / `a2a.*`：桥接或对外交互能力

## 当前共识

AIOS 不是“一个更强的桌面应用”。
AIOS 的目标是：**把 AI 变成操作系统的第一公民，而不是把 AI 塞进现有 App 外壳里。**
