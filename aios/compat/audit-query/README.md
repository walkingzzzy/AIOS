# compat audit-query

此目录提供 compat shared audit sink 的查询与 saved-query 运行时。

## 当前状态

- 已有 provider descriptor 与 `compat-audit-query-v1` 结果协议
- 已有本地 JSONL 查询、saved query 持久化、query history 与 scriptable interactive surface
- 已有 provider-specific audit log，可记录 query/save/run/list 操作
- 未有跨服务统一 correlation UI

## 目标

- 给 operator 一个可重复执行、可保存、可导出的 compat audit query 面
- 用 compat provider 形式把这条能力纳入 provider fleet，而不是停留在零散脚本
