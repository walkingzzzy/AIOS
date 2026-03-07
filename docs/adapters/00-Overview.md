# AIOS Provider 概述

**更新日期**: 2026-03-08

---

> **系统开发口径修订（2026-03-08）**
> AIOS 统一定义为 **AI 原生操作系统 / 系统软件工程**。本文如提及桌面应用、Electron 客户端、应用适配器、App 安装等内容，除非明确标注为“原型期 / 兼容层 / 历史实现”，否则不再代表目标形态。
> 当前最高约束：**系统镜像、系统服务、系统壳层、设备/能力抽象、权限与更新恢复**。

## 1. Provider 的新定义

在 Route B 中，AIOS 不再以“应用适配器”为中心，而以 **provider** 为中心。
Provider 是把协议能力映射到系统栈不同层级的实现单元。

## 2. Provider 类型

| 类型 | 说明 | 典型场景 |
|------|------|---------|
| `system` | 核心操作系统能力 | 电源、文件、网络、进程 |
| `service` | 第一方系统服务 | session、policy、task、notification |
| `shell` | 壳层与会话能力 | workspace、window、focus、launcher |
| `device` | 设备与传感器 | 摄像头、音频、蓝牙、显示器 |
| `compat` | 兼容层能力 | 浏览器、旧应用、办公软件、SaaS |
| `vision` | 视觉兜底 | 无原生能力时的视觉控制 |
| `professional` | 专业域能力 | CAD、DCC、EDA 等 |

## 3. 发现来源

Route B 推荐的发现来源：

- system service manifests
- D-Bus / IPC service names
- device manifests / udev metadata
- shell component manifests
- compat provider manifests

> 扫描 `.desktop` 文件只属于 compat layer 的历史策略，不再代表 AIOS 的核心发现机制。

## 4. 命名空间建议

- `system.*`
- `service.*`
- `shell.*`
- `device.*`
- `compat.*`
- `professional.*`

## 5. 当前仓库的兼容策略

当前 `adapters/*` 目录中的大量实现仍然有效，但其角色应重新理解为：

- 能直接对应系统服务的，未来应上移为 `system` 或 `service`
- 控制旧应用/浏览器的，归入 `compat`
- 依赖视觉与 GUI 自动化的，归入 `vision` 或 `compat`

## 6. 设计原则

- 先建模系统能力，再考虑旧应用桥接
- 先定义 capability 与 policy，再决定具体实现语言
- 能系统化就不要界面自动化，能结构化就不要视觉兜底
