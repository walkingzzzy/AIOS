# AIOS Provider 开发指南

**更新日期**: 2026-03-08

---

> **系统开发口径修订（2026-03-08）**
> AIOS 统一定义为 **AI 原生操作系统 / 系统软件工程**。本文如提及桌面应用、Electron 客户端、应用适配器、App 安装等内容，除非明确标注为“原型期 / 兼容层 / 历史实现”，否则不再代表目标形态。
> 当前最高约束：**系统镜像、系统服务、系统壳层、设备/能力抽象、权限与更新恢复**。

## 1. 开发目标

Provider 开发的目标不再是“给某个 App 补一个插件”，而是为 AIOS 提供 **可治理、可授权、可恢复** 的系统能力实现。

## 2. 何时开发哪类 Provider

| 需求 | 优先类型 |
|------|---------|
| 操作系统基础能力 | `system` |
| 会话 / 调度 / 策略 | `service` |
| 桌面壳层 | `shell` |
| 设备控制 | `device` |
| 旧应用桥接 | `compat` |
| 无结构化接口的软件 | `vision` |

## 3. 描述文件示例

```yaml
aios_version: "0.4"

provider:
  id: "org.aios.session.manager"
  name: "AIOS Session Manager"
  version: "0.1.0"
  type: "service"

capabilities:
  - id: "service.session.create"
    name: "创建会话"
    description: "创建新的 AIOS 用户会话"
  - id: "service.session.restore"
    name: "恢复会话"
    description: "恢复先前的用户会话"
```

## 4. 开发要求

- 必须声明 capability
- 必须声明风险等级和权限域
- 必须提供失败模式与恢复建议
- 必须能够被观测（日志、trace、health）

## 5. Compat Provider 的特殊约束

Compat provider 允许桥接旧应用，但必须：

- 明确标注为 `compat`
- 不得反向主导 AIOS 的架构定义
- 权限策略必须与系统核心能力隔离
- 优先寻找结构化接口，视觉自动化只能作为兜底

## 6. 推荐语言

| 场景 | 推荐语言 |
|------|---------|
| 核心系统服务 | Rust / Go |
| 壳层与图形 | Rust |
| 原型验证 | TypeScript / Python |
| 兼容层脚本 | Python / TypeScript |

## 7. 验收标准

一个 Provider 被认为可合入，至少满足：

- 接口定义完整
- 权限说明完整
- 失败模式可解释
- 可被自动化测试
- 在文档中明确归属哪一层
