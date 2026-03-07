# AIOS Protocol 总览

**版本**: 2.1.0
**更新日期**: 2026-03-08
**状态**: Route B / 系统协议基线

---

> **系统开发口径修订（2026-03-08）**
> AIOS 统一定义为 **AI 原生操作系统 / 系统软件工程**。本文如提及桌面应用、Electron 客户端、应用适配器、App 安装等内容，除非明确标注为“原型期 / 兼容层 / 历史实现”，否则不再代表目标形态。
> 当前最高约束：**系统镜像、系统服务、系统壳层、设备/能力抽象、权限与更新恢复**。

## 1. 协议定义

AIOS Protocol 是 AIOS 操作系统内部与外部组件交换 **系统能力、任务状态、风险策略与兼容层桥接能力** 的统一协议。

## 2. 协议目标

- 让 AI 可以以受控方式调用系统能力
- 让系统服务、壳层和兼容层共享统一任务语义
- 让权限、审计、回滚和恢复成为协议一部分

## 3. 不再追求的目标

- 不再把协议定义成“桌面应用控制标准”
- 不再以 App 自动化为协议中心
- 不再让兼容层能力反向决定协议核心语义

## 4. 能力域

| 域 | 含义 |
|----|------|
| `system.*` | 核心操作系统能力 |
| `service.*` | 第一方系统服务能力 |
| `shell.*` | 会话、工作区、窗口、焦点、通知 |
| `device.*` | 硬件、传感器、I/O |
| `compat.*` | 浏览器、旧应用、办公软件、外部控制桥接 |
| `professional.*` | 专业域软件或工作流 |

## 5. 分层视角

```
AI Shell / UX Surface
    ↓
AIOS Protocol
    ↓
system / service / shell / device / compat providers
    ↓
kernel / drivers / system manager / hardware
```

## 6. 示例

```yaml
capabilities:
  - id: "system.power.shutdown"
  - id: "service.session.create"
  - id: "shell.workspace.focus"
  - id: "device.audio.set_volume"
  - id: "compat.browser.open_url"
```

## 7. 兼容层说明

`compat.*` 是旧世界桥接域，不是 AIOS 的定义中心。
未来若 AIOS 有原生 shell 和原生服务，同类能力优先进入 `system.*` / `service.*` / `shell.*`。
