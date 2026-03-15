# ADR-0005: 核心控制面本地 IPC 优先，MCP / A2A 属于 bridge / interop 层

- 状态：Accepted
- 日期：2026-03-08

## 背景

AIOS 需要协议化互操作，但不能把桥接协议反过来当成核心系统内部通信的唯一基础。

## 决策

- `agentd`、`runtimed`、`sessiond`、`policyd`、`deviced`、`updated` 之间优先使用本地 IPC / system bus / Unix socket 等系统内通道
- MCP / A2A / API bridge 用于 interop、compat、remote bridge 与外部协作
- bridge provider 必须进入 registry、进入 policy、进入 audit，但不替代核心控制面本地协作机制

## 结果

- AIOS 核心控制面与 bridge 层边界更清晰
- 外部协议桥接不会反向定义系统主语义
- 远端与桥接能力仍保留正式位置，但被限制在受治理的边界内
