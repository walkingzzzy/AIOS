# AIOS 系统开发指南

**更新日期**: 2026-03-08

---

> **系统开发口径修订（2026-03-08）**
> AIOS 统一定义为 **AI 原生操作系统 / 系统软件工程**。本文如提及桌面应用、Electron 客户端、应用适配器、App 安装等内容，除非明确标注为“原型期 / 兼容层 / 历史实现”，否则不再代表目标形态。
> 当前最高约束：**系统镜像、系统服务、系统壳层、设备/能力抽象、权限与更新恢复**。

## 1. 推荐路线

AIOS 推荐采用 **Linux-first** 路线：

- Linux Kernel
- systemd
- Wayland compositor / shell
- Rust/Go 系统服务
- 本地优先 IPC 与 capability policy

## 2. 建议分层

### 镜像层
- 启动链
- 恢复模式
- 更新回滚

### 服务层
- `aios-agentd`
- `aios-sessiond`
- `aios-policyd`
- `aios-deviced`
- `aios-updated`

### 壳层
- AI launcher
- workspace / window / focus
- notification / task surface

### 兼容层
- browser providers
- office providers
- MCP / A2A bridges
- GUI automation fallback

## 3. 关键接口建议

| 能力域 | 建议命名 |
|--------|---------|
| 电源/文件/网络 | `system.*` |
| 任务/会话/策略 | `service.*` |
| workspace/window/focus | `shell.*` |
| 摄像头/音频/蓝牙/显示 | `device.*` |
| 浏览器/旧应用/办公 | `compat.*` |

## 4. 当前仓库如何过渡

- 保留 `daemon` 中可沉淀的编排逻辑
- 将现有 session / task / event 语义抽象为系统服务 API
- 将 Electron UI 降级为过渡期调试界面

## 5. 开发顺序建议

1. 明确 capability 与 policy 模型
2. 建立系统服务 skeleton
3. 建立镜像与启动链
4. 建立 AI Shell alpha
5. 最后再决定 compat layer 的承接方式

## 6. 非目标

- 不以“能控制多少桌面应用”衡量 AIOS 成熟度
- 不以 Electron 客户端体验作为系统完成度指标
- 不以 GUI 自动化作为核心控制范式
