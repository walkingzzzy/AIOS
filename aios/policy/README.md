# policy/

`policy/` 是 AIOS 的 capability、审批、execution token、taint 与审计治理目录。

## 1. 负责什么

此目录长期应承载：

- capability profile
- policy profile
- execution token schema
- taint / approval / deny-list 规则
- 审计规则与恢复语义引用

## 2. 当前状态

截至 2026-03-13：

- 已有：`profiles/`、`schemas/`、`capabilities/default-capability-catalog.yaml`，以及 `policyd` 侧 evaluator / approval / token / audit writer / audit query / prompt guard baseline；capability catalog 现也支持 `version` / `supersedes` / `migration_note`
- 未有：更完整的跨服务 policy test matrix、正式 shell approval surface

当前判断：`Partial Impl`，但仍缺 governance 深化与跨服务闭环。

## 3. 技术基线

- 主实现服务：`aios-policyd`
- 主语言：Rust
- 结构化契约：JSON Schema
- 运行时输出：approval decision / execution token / audit event

## 4. 当前优先事项

1. 深化 approval 规则与消费模型
2. 增加跨服务 policy / prompt guard 测试矩阵
3. 继续收敛 capability versioning / migration 元数据的治理流程
4. 接入 shell approval surface
