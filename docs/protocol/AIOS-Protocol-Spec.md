# AIOS Protocol 正式规范

**版本**: 2.1.0
**更新日期**: 2026-03-08
**状态**: Route B / 草案

---

> **系统开发口径修订（2026-03-08）**
> AIOS 统一定义为 **AI 原生操作系统 / 系统软件工程**。本文如提及桌面应用、Electron 客户端、应用适配器、App 安装等内容，除非明确标注为“原型期 / 兼容层 / 历史实现”，否则不再代表目标形态。
> 当前最高约束：**系统镜像、系统服务、系统壳层、设备/能力抽象、权限与更新恢复**。

## 1. 规范范围

本规范定义 AIOS 内部与外部组件之间用于交换 capability、task、policy、audit、approval 和 compat bridge 的协议。

## 2. 体系边界

```
shell / AI entry
    ↓
AIOS protocol runtime
    ↓
system / service / shell / device / compat providers
    ↓
kernel / service manager / hardware
```

## 3. 核心约束

1. 协议必须服务于系统软件，而非单一桌面应用
2. 所有高风险 capability 都必须可授权、可审计、可恢复
3. compat layer 只能作为桥接域，不能成为协议中心
4. session 与 task 语义必须独立于任意前端实现

## 4. 域模型

- `system.*`
- `service.*`
- `shell.*`
- `device.*`
- `compat.*`
- `professional.*`

## 5. 历史别名策略

- 旧文档中的 `app.*` 一律视为 `compat.*`
- 旧文档中的 `type: application` 一律视为 `type: compat`
- 若旧语义与系统主线冲突，以 Route B 定义为准

## 6. 规范优先级

若出现以下冲突，优先级按从高到低排序：

1. 系统安全与恢复约束
2. capability policy
3. 协议正式规范
4. compat layer 便捷性
5. 调试控制台实现细节

## 7. 当前仓库的解释规则

- Electron 客户端：仅为历史原型或过渡控制台
- Node daemon：仅为 `agentd` 的原型前身
- 现有 adapters：默认解释为 compat providers，除非后续上移到系统主线
