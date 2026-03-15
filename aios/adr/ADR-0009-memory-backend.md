# ADR-0009: 控制面记忆后端采用 SQLite 主存储 + 分层视图模型

- 状态：Accepted
- 日期：2026-03-13

## 背景

AIOS 的控制面已经在 `sessiond` 中沉淀 working、episodic、semantic、procedural memory，以及 task / recovery / portal handle 关联关系。

此前仓库里虽然已有 migration 与部分实现，但“记忆后端路线”还没有被正式冻结，导致下游容易把：

- working memory
- episodic history
- semantic indexes
- procedural rules

混成一个模糊概念，而不是明确的分层对象。

## 决策

- `sessiond` 采用 SQLite 作为控制面记忆主存储。
- working / episodic / semantic / procedural memory 保持独立表与独立 RPC surface，不做单表混存。
- session 级证据视图可以聚合这些对象，但不改变底层分层边界。
- 若未来引入向量索引、外部检索或对象存储，只能作为扩展层，不能替代当前控制面基线。

## 结果

- 记忆模型从“实现细节”升级为正式架构约束。
- 团队 C / E 可以围绕稳定对象编排 UI 与证据消费面。
- 后续扩展向量检索或离线归档时，不会反向破坏控制面最小恢复能力。
