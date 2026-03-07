# AIOS Protocol 核心概念

**版本**: 2.1.0
**更新日期**: 2026-03-08
**状态**: Route B / 系统协议基线

---

> **系统开发口径修订（2026-03-08）**
> AIOS 统一定义为 **AI 原生操作系统 / 系统软件工程**。本文如提及桌面应用、Electron 客户端、应用适配器、App 安装等内容，除非明确标注为“原型期 / 兼容层 / 历史实现”，否则不再代表目标形态。
> 当前最高约束：**系统镜像、系统服务、系统壳层、设备/能力抽象、权限与更新恢复**。

## 1. Provider

Provider 是 AIOS 中承接 capability 的执行单元。
它可以是系统服务、壳层组件、设备抽象，或兼容层桥接器。

### Provider 类型

| 类型 | 说明 |
|------|------|
| `system` | 操作系统基础能力 |
| `service` | 第一方系统服务 |
| `shell` | 壳层 / workspace / window / focus |
| `device` | 硬件与传感器 |
| `compat` | 旧应用、浏览器、外部桥接 |
| `vision` | 视觉兜底 |
| `professional` | 专业域能力 |

## 2. Capability

Capability 是协议暴露的最小执行单元。
它必须可以：

- 被授权
- 被审计
- 被观测
- 被撤销或恢复

### 命名规范

```
<domain>.<subsystem>.<action>
```

| 域 | 示例 |
|----|------|
| `system` | `system.power.shutdown` |
| `service` | `service.session.restore` |
| `shell` | `shell.workspace.focus` |
| `device` | `device.audio.set_volume` |
| `compat` | `compat.browser.open_url` |

> 旧 `app.*` 命名空间在 Route B 中统一视为 `compat.*` 的历史别名。

## 3. Policy

Policy 定义 capability 的授权、审批、审计与撤销规则。
Policy 永远独立于 UI 和控制台存在。

## 4. Session

Session 是用户、任务、上下文和 capability token 的运行边界。
它是系统级对象，而不是某个前端页面状态。

## 5. Task

Task 是由 AIOS 执行的意图单元。
Task 可以跨多个 provider 执行，但必须在同一个 policy / audit 约束下流转。

## 6. Compat Layer

Compat layer 用于连接旧应用、浏览器和外部软件。
它的职责是：

- 提供过渡能力
- 降低迁移成本
- 为协议提供现实世界桥接

它的限制是：

- 不定义 AIOS 核心架构
- 不重写系统核心权限边界
- 不凌驾于原生系统能力之上

## 7. 壳层

壳层是 AIOS 的系统人机入口，包括：

- launcher
- workspace
- window focus
- notifications
- task surfaces

壳层不是“一个 GUI 客户端”，而是 AIOS 运行环境的一部分。
