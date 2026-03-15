# ADR-0003: Provider Registry 与 Portal 为统一执行入口

- 状态：Accepted
- 日期：2026-03-08

## 决策

- 所有 system / runtime / device / shell / compat provider 必须进入 registry
- 所有对象选择与受限授权通过 portal 返回 scoped handle
- registry 负责发现与解析，`policyd` 负责最终授权
- 外部 MCP / A2A / API bridge 也必须进入 registry，但默认属于低信任或中低信任桥接层

## 结果

- provider 发现与对象授权不再散落在各自实现里
- GUI fallback 只能作为最后一级降级路径
- 外部 bridge 进入统一审计与策略链，但不获得控制面豁免
