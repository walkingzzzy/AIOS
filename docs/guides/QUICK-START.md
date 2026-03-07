# AIOS Route B 快速开始

**更新日期**: 2026-03-08

---

> **系统开发口径修订（2026-03-08）**
> AIOS 统一定义为 **AI 原生操作系统 / 系统软件工程**。本文如提及桌面应用、Electron 客户端、应用适配器、App 安装等内容，除非明确标注为“原型期 / 兼容层 / 历史实现”，否则不再代表目标形态。
> 当前最高约束：**系统镜像、系统服务、系统壳层、设备/能力抽象、权限与更新恢复**。

## 1. 先建立正确认知

你现在拿到的是一个 **系统开发路线中的过渡仓库**。
它包含可运行的兼容层原型，但 AIOS 的目标是操作系统，不是 Electron 应用。

## 2. 30 分钟快速上手

1. 阅读 [项目架构](../AIOS-Project-Architecture.md)
2. 阅读 [协议总览](../protocol/00-Overview.md)
3. 阅读 [实现进展](../IMPLEMENTATION_PROGRESS.md)
4. 运行当前兼容层原型，理解哪些能力已经存在

## 3. 运行当前兼容层原型

```bash
git clone https://github.com/aios-protocol/aios.git
cd aios
pnpm install
pnpm build
pnpm dev
```

这一步的目的只是：

- 理解现有编排逻辑
- 理解 compat provider 的形态
- 评估哪些能力可上移为系统服务

## 4. 新贡献者的第一条纪律

在开始写代码前，先回答：

- 我在做系统主线，还是 compat layer？
- 这个能力属于 `system`、`service`、`shell`、`device` 还是 `compat`？
- 它会不会把 AIOS 拉回“应用开发”路径？

## 5. 下一步阅读建议

- 做系统服务：看 [开发规范](AIOS-Protocol-DevSpec.md)
- 做壳层：看 [系统开发指南](AIOS-System-DevGuide.md)
- 做 provider：看 [Provider 开发指南](../adapters/01-Development.md)
