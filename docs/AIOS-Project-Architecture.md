# AIOS 系统架构文档

**版本**: 2.1.0
**更新日期**: 2026-03-08
**状态**: Route B / 系统架构基线

---

> **系统开发口径修订（2026-03-08）**
> AIOS 统一定义为 **AI 原生操作系统 / 系统软件工程**。本文如提及桌面应用、Electron 客户端、应用适配器、App 安装等内容，除非明确标注为“原型期 / 兼容层 / 历史实现”，否则不再代表目标形态。
> 当前最高约束：**系统镜像、系统服务、系统壳层、设备/能力抽象、权限与更新恢复**。

## 1. 架构结论

AIOS 的目标架构不是“App + daemon”。
AIOS 的目标架构是一个分层的 **系统软件栈**：

```
硬件 / 固件
    ↓
Linux Kernel / Driver Model
    ↓
Boot / Image / Recovery / Update
    ↓
PID1 / Service Manager (systemd)
    ↓
AIOS System Services
  - aios-agentd
  - aios-policyd
  - aios-sessiond
  - aios-deviced
  - aios-updated
    ↓
AIOS Shell / Compositor / Workspace Model
    ↓
Compat Providers / Professional Providers / External Bridges
    ↓
User Workloads
```

## 2. 目标分层

### 2.1 镜像与启动层
- 系统镜像构建
- 启动链、恢复分区、回滚
- 版本切换与原子更新

### 2.2 内核与设备层
- Linux 内核与驱动模型
- udev / device discovery
- 输入、显示、音频、网络等设备抽象

### 2.3 系统服务层
- `aios-agentd`：意图分析、任务编排、AI 路由
- `aios-policyd`：系统能力授权、审计与风控
- `aios-sessiond`：用户会话、上下文、任务生命周期
- `aios-deviced`：设备能力统一抽象
- `aios-updated`：系统升级、回滚、健康门控

### 2.4 壳层与会话层
- Wayland compositor / shell
- workspace / window / focus / notification / launcher
- AI 优先的人机入口

### 2.5 兼容层
- 旧应用控制
- 浏览器自动化
- 办公软件桥接
- MCP / A2A / SaaS 桥接

> 兼容层是过渡能力，不是 AIOS 的定义中心。

## 3. 当前仓库在目标架构中的位置

| 现有模块 | 新定位 | 说明 |
|---------|--------|------|
| `packages/client` | `legacy console` | 原型期调试控制台，不是未来系统壳层 |
| `packages/daemon` | `agentd prototype` | 可保留编排与路由逻辑，但需脱离 Electron 附庸身份 |
| `adapters/*` | `compat providers` | 过渡期桥接器，需要重构为系统服务接口或兼容提供者 |
| `MCP/A2A` | `external bridge` | 外部生态桥接能力 |

## 4. 设计红线

- 不再把 Electron 客户端当成 AIOS 本体
- 不再把“系统应用功能页”当成操作系统能力交付
- 不再用 App 术语主导协议命名、权限命名与发布标准
- 所有新接口必须回答：它属于 `system`、`service`、`shell`、`device` 还是 `compat`

## 5. Route B 的核心约束

### 5.1 system-first
系统镜像、系统服务与系统壳层优先于桌面控制台体验。

### 5.2 local-first
关键控制路径默认本地执行；远端 AI 只能参与策略与推理，不能替代系统控制边界。

### 5.3 capability-first
不按“页面按钮”建模，而按“系统能力”建模。

### 5.4 recoverable-by-design
所有高风险变更必须支持回滚、恢复或隔离。

## 6. 当前最重要的架构动作

1. 将 repo 重新划分为 `image/`、`services/`、`shell/`、`policy/`、`compat/`、`legacy/`
2. 把 `daemon` 中的编排逻辑抽取为未来 `aios-agentd`
3. 停止继续扩大 Electron 主界面的产品定义
4. 建立系统级权限模型，而不是停留在应用级 adapter permission
5. 为 AIOS 设计原子更新和恢复链路
