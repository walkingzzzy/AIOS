# ADR-0010: 核心控制面 RPC wire contract 采用共享 manifest + 结构化错误模型

- 状态：Accepted
- 日期：2026-03-13

## 背景

AIOS 的核心控制面已经形成 `agentd`、`sessiond`、`policyd`、`runtimed` 的 Unix socket + JSON-RPC 协作模型。

但在本次冻结前仍存在两个问题：

- 契约版本与冻结边界主要停留在文档口径，没有统一可查询 manifest。
- 错误返回主要依赖 message 字符串，不利于跨服务恢复、测试与证据归档。

## 决策

- 核心控制面服务提供 `system.contract.get`，返回共享 contract manifest。
- manifest 至少包含：
  - `contract_version`
  - `compatibility_epoch`
  - frozen method list
  - frozen schema list
- 核心控制面服务的 RPC 错误统一携带结构化 `error_code`。
- 标准 JSON-RPC 错误码继续保留；控制面域错误使用共享 `-3200x` 段。

## 结果

- 团队 A / C / D / E 可以通过运行中服务直接确认契约版本，而不只依赖文档同步。
- smoke / integration harness 可以断言 machine-readable `error_code`，而不是模糊匹配 message。
- 后续引入兼容性检查、回归门禁与证据归档时，有了可持续演进的正式入口。
