# 05 · 优先级 Backlog

## P0 · 立即开始

- 冻结 AIOS 为 `Linux-first + image-based + system-service-first + runtime-first`
- 明确 `LLM-as-Kernel` 在 AIOS 中是“认知控制平面抽象”而非 Linux 替代
- 建立 `image/`、`services/`、`runtime/`、`shell/`、`policy/`、`compat/`、`hardware/`、`legacy/` 目录框架
- 将 `packages/client`、`packages/daemon`、`packages/cli` 明确标记为 `legacy`
- 设计 `agentd/runtimed/sessiond/policyd/deviced/updated` 的服务边界
- 定义新的 capability 命名空间与迁移策略，新增 `runtime.*`
- 冻结工作记忆 / 情景记忆 / 语义记忆 / 程序记忆模型
- 冻结 prompt injection / taint / code sandbox 的基础模型
- 冻结 Tier 0 / Tier 1 硬件目标

## P1 · 系统骨架

- 完成开发镜像原型
- 建立 service manager 启动方式
- 完成 `runtimed` 的最小推理包装器与 CPU-only fallback
- 抽取 `agentd` 的最小编排能力
- 抽取 `sessiond` 的最小持久化与记忆能力
- 抽取 `policyd` 的审批与审计骨架
- 建立本地 IPC、provider registry、MCP discovery skeleton

## P2 · 运行时与壳层

- AI launcher alpha
- workspace / focus 模型
- 通知中心与 task surface
- queue / budget / timeout / backpressure 机制
- KV cache / memory budget accounting
- 屏幕 / 音频 / 输入的多模态采集管线
- 规则路由 / 语义路由 / LLM 路由 / 成本路由最小实现

## P3 · 安全、恢复与可信扩展

- capability token
- compat 权限分区
- code sandbox alpha
- prompt injection / taint 防御链
- 更新与回滚
- 恢复模式与自愈 runbook
- trusted cloud offload 原型与 attestation 边界
- MCP / A2A 的系统级桥接重构

## 挂起项

以下事项可以做，但不应抢占主线：

- 继续美化 Electron UI
- 继续新增“系统应用功能页”
- 继续以兼容层功能数量做里程碑汇报
- 在 runtime 与 policy 基线未完成前追求“全平台硬件支持”
