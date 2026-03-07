# ADR-0003: Provider Registry 与 Portal 为统一执行入口

- 状态：Accepted
- 日期：2026-03-08

决策：

- 所有 system/runtime/device/compat provider 必须进入 registry
- 所有对象选择与受限授权通过 portal 返回 scoped handle
- registry 负责发现与解析，`policyd` 负责最终授权
