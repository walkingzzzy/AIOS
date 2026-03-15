# 00 · AIOS 定义与分级

**版本**: 1.1.0  
**更新日期**: 2026-03-08  
**状态**: Route B / 定义冻结草案

---

## 1. 定义冻结

AIOS 在 Route B 中的唯一推荐定义为：

> **一个基于 Linux 的 AI-native 操作系统发行版 / 系统平台**。  
> 它以可启动系统镜像、第一方系统服务、原生系统壳层、AI 运行时内核、受治理的 capability、可审计的任务执行链、可回滚的系统更新为核心交付物。

## 2. 双内核概念澄清

研究文档中的 `LLM-as-Kernel` 应被吸收为**架构抽象**，而不是字面意义上的“用大模型替换 Linux 内核”。

AIOS 应明确采用双层内核理解：

### 2.1 真实内核

- Linux Kernel
- Drivers / HMM / cgroup v2 / namespace / scheduler
- 启动链、内存管理、设备管理、文件系统、进程隔离

### 2.2 认知内核

- 由 `agentd`、`runtimed`、`sessiond`、`policyd`、`deviced` 等共同构成
- 负责意图分解、模型路由、上下文治理、记忆协调、能力决策与恢复反馈
- 运行在 Linux 之上，但在 AIOS 中承担“系统认知控制平面”的角色

结论：

- Linux Kernel 决定 **系统能否安全运行**
- Cognitive Kernel 决定 **系统如何理解意图并智能执行**

## 3. AIOS 的工程边界

### 3.1 第一阶段必须覆盖的内容

AIOS v1 必须至少覆盖以下系统对象：

1. **Bootable image**：可启动、可安装、可恢复的系统镜像
2. **Core services**：`agentd`、`runtimed`、`sessiond`、`policyd`、`deviced`、`updated`
3. **Native shell**：AI launcher、workspace、window/focus、notification、task surface
4. **Runtime substrate**：CPU / GPU / NPU 调度、模型包装器、KV cache / batch / memory budget
5. **Memory system**：工作记忆、情景记忆、语义记忆、程序记忆的系统级区分与治理
6. **Capability governance**：能力命名、权限分级、审批链、审计链
7. **Sandboxed workloads**：compat、第三方 workload、代码执行环境的受限运行模型
8. **Update / rollback / recovery**：系统升级、健康检查、失败回滚、恢复入口、自愈 runbook
9. **Developer surface**：provider SDK、schema、日志、QEMU 开发镜像、调试工具

### 3.2 第一阶段明确不做的内容

以下内容不作为 v1 成功标准：

- 自研 Linux 内核调度器
- 自研 GPU / Wi-Fi / 蓝牙 / NPU 驱动
- 自研通用文件系统
- 自研完整桌面应用生态商店
- 覆盖所有桌面软件或办公软件的自动化适配
- 将 GUI 自动化作为系统主控制范式
- 将远端云推理默认视为本地等价信任域

### 3.3 完整系统中的基线能力与条件能力

AIOS 的“完整系统”指的是**能力域完整**，不是“每台支持机器都必须暴露全部扩展能力”。

必须长期稳定成立的**基线能力**包括：

- bootable image / install / rollback / recovery
- `agentd` / `runtimed` / `sessiond` / `policyd` / `deviced` / `updated`
- 原生 AI Shell 与系统级审批 / 审计 / 恢复入口
- `local-cpu` 为底线的 runtime substrate
- provider registry / portal / compat sandbox 的受治理闭环

按支持矩阵显式声明的**条件能力**包括：

- `ui_tree` 或等价结构化图形来源
- `local-gpu` / `local-npu` 等加速后端
- 可信云卸载与 attestation 链
- 高级多模态采集、复杂图形栈特性、多显示器 / 高刷 / 触控增强

规则：

- 条件能力必须由 `hardware profile`、`route/runtime profile`、`provider descriptor` 与 `policy` 共同声明
- 条件能力不能被产品文案暗示为“全平台默认可用”
- 某项条件能力未在当前平台声明支持，不应阻塞 AIOS 作为完整系统的其余基线闭环成立

## 4. AIOS 与相关概念的区别

| 概念 | 是否等于 AIOS | 正确关系 |
|------|---------------|----------|
| Electron Client | 否 | 仅可作为 `legacy console` |
| Node Daemon | 否 | 仅可沉淀部分编排原型逻辑 |
| Linux Kernel | 否，但为 AIOS 基线 | 是系统安全与资源控制的根基 |
| Cognitive Kernel | 否，但属于 AIOS 核心 | 是 AIOS 的认知控制平面 |
| AI Runtime | 否，但属于 AIOS 核心 | 是模型执行、调度、记忆与路由引擎 |
| AI Shell | 否，但属于 AIOS 核心 | 是系统壳层，不是普通应用 |
| Protocol / SDK | 否 | 是接口层，不是系统本体 |
| Compat Layer | 否 | 是桥接层，属于次级能力 |
| 发行版镜像 | 是 | 是 AIOS 的最小交付形态之一 |

## 5. AIOS 的最小可交付物

在工程上，只有同时满足以下条件，才可以称为“AIOS 开发者预览版”：

- 能生成并启动 `QEMU` / `VM` 系统镜像
- 有 AIOS 自己的 system services 与 unit 编排
- 有 `runtimed` 负责本地模型或推理包装器调度
- 有原生 AI Shell，而不是依赖 Electron 充当系统界面
- 有 capability policy、最小审批链和审计链
- 有多模态输入的最小系统管线
- 有系统更新、失败回滚与恢复模式
- 有 compat / code sandbox 的受限边界

## 6. 版本分级

### L0 · 原型期

- 仅有用户态 client / daemon / adapters
- 无系统镜像
- 无系统服务边界
- 无原生 shell
- 无 runtime substrate

### L1 · 系统骨架期

- 可启动开发镜像
- 有 `agentd` / `runtimed` / `sessiond` / `policyd` skeleton
- 有 systemd unit 编排、日志与恢复入口
- 仍未形成完整 shell、多模态和更新体系

### L2 · 开发者预览

- 可在目标 VM 启动并进入 AI Shell
- capability policy 生效
- runtime queue / budget 生效
- 最小 compat sandbox 生效
- 可执行更新、失败回滚与恢复

### L3 · 产品预览

- 有稳定硬件目标
- 有安装流程与用户数据升级策略
- 有开发者 SDK 与 provider 生命周期规范
- 有本地 / 可信云卸载边界说明

### L4 · 稳定版

- 关键硬件矩阵通过
- 更新、回滚、恢复链路稳定
- 安全基线与审计基线达标
- 兼容层与系统本体边界长期稳定
- 条件能力按支持矩阵长期稳定声明，而不是以“所有机器全量具备”作为稳定版定义

## 7. 项目成功标准

AIOS 的成功不以“控制了多少第三方应用”衡量，而以以下问题是否成立衡量：

- AI 是否已经成为系统一级入口
- 异构算力是否被抽象为统一可治理资源
- 模型、记忆、工具调用是否都受策略与审计约束
- 高风险任务是否必经审批、审计和恢复边界
- shell 是否是系统壳层而非应用壳
- 系统是否可启动、可更新、可回滚、可恢复
- compat 是否被严格限制在桥接层而非核心定义层

## 8. Route B 的强约束

从本文件生效后，以下事项视为冻结共识：

1. AIOS v1 走 **Linux-first** 路线
2. AIOS v1 走 **image-based system** 路线
3. AIOS v1 走 **system-service-first** 路线
4. AIOS v1 必须建设独立的 **runtime substrate**
5. AIOS v1 的 AI 能力必须服从 **policy-first** 治理
6. 当前 `packages/client`、`packages/daemon`、`packages/cli` 一律视作 `legacy`

## 9. 推荐参考

- systemd Building Images Safely: `https://systemd.io/BUILDING_IMAGES/`
- Linux cgroup v2: `https://docs.kernel.org/admin-guide/cgroup-v2.html`
- Wayland Protocol Model: `https://wayland.freedesktop.org/docs/html/ch04.html`
- vLLM: `https://github.com/vllm-project/vllm`
