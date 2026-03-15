# aios-sessiond

## 1. 角色

`aios-sessiond` 是 AIOS 的会话、任务与记忆治理服务。

核心职责：

- 用户会话
- 任务生命周期
- working / episodic / semantic / procedural memory 绑定
- portal handle / recovery ref 绑定
- 会话恢复与任务恢复

## 2. 推荐技术路线

- 语言：Rust
- 存储：SQLite（WAL）+ 文件对象引用
- 通信：UDS + JSON-RPC
- 关键模块：session、task、memory、recovery、handle binding

## 3. 推荐目录结构

```text
sessiond/
├── src/
│   ├── main.rs
│   ├── config.rs
│   ├── rpc.rs
│   ├── db.rs
│   ├── session.rs
│   ├── task.rs
│   ├── memory.rs
│   ├── recovery.rs
│   └── errors.rs
├── migrations/
├── tests/
├── service.yaml
└── units/
```

## 4. 当前数据对象

- `sessions`
- `tasks`
- `task_events`
- `task_plans`
- `memory_working_refs`
- `memory_episodic_entries`
- `portal_handles`
- `recovery_refs`

## 5. 当前状态

- 仓库状态：`In Progress`
- 已有：职责说明、service metadata、unit、`src/` 骨架、migration SQL、SQLite runtime、session/task RPC、`task.list` / `task.state.update` / `task.events.list`、`task_events` 生命周期记录与查询、`task.plan` store、`memory.read` / `memory.write`、`memory.episodic.append` / `list`、`memory.semantic.put` / `list`、`memory.procedural.put` / `list`、`session.evidence.get` 聚合证据视图、`system.contract.get` manifest、结构化 RPC error code、portal handle binding、portal RPC，以及 `portal.handle.lookup` / `revoke` 的 `session_id` / `user_id` 绑定校验
- 已有：session / task 生命周期关键变更会镜像到共享 `observability.jsonl` sink，并复用 trace-event schema
- 已有：crate 单测现覆盖 portal context-bound lookup / revoke 与 SQLite 外键绑定
- 缺失：更多跨服务联调证据

## 6. 下一步

1. 增加 `sessiond` 单测与集成测试
2. 与 `agentd` / `policyd` / `runtimed` 的联调 smoke 继续收敛
3. 继续收敛证据字段以服务恢复/审计消费面
