# AIOS IPC Smoke Test Plan

## 范围

本计划验证 AIOS 当前已经落地的 control-plane 最小闭环。

## 覆盖服务

- `sessiond`
- `policyd`
- `runtimed`
- `agentd`

## 核心断言

### 1. 服务启动

- 每个服务都能创建自己的 UDS socket
- `system.health.get` 返回 `ready`

### 2. `agent.intent.submit`

输入：

- `user_id`
- `intent`

断言：

- 返回 `session.session_id`
- 返回 `task.task_id`
- 返回 `plan.candidate_capabilities`
- 返回 `policy.decision`
- 返回 `route.selected_backend`
- 返回 `provider_resolution`

### 3. `sessiond` task lifecycle

断言：

- `task.list` 能返回当前 session 下任务
- `task.state.update` 能完成 `planned -> approved` 或 `approved -> executing`
- 带 `state` filter 的 `task.list` 能查到更新后的任务
- `task_events` 生命周期记录在 `sessiond` 落地

### 4. Registry 接线

断言：

- `agentd` 返回 `provider_resolution.selected` 或明确的无匹配原因
- provider candidate 来自 descriptor fixtures 或 provider self-registration，而不是硬编码 response
- 即使移除静态 `system-files.local.json`，`system-files-provider` 仍能通过自注册恢复 `provider.fs.open` 解析

### 5. Portal handle flow

断言：

- 含显式文件路径的 intent 返回 `portal_handle`
- 含显式导出路径的 intent 返回 `export_target_handle`
- 含 screen share 意图的 intent 返回 `screen_share_handle`
- `sessiond` 的 `portal.handle.list` 能查到同 session 下的 handle
- 返回的 handle 带 `target_hash` 与 expiry

### 6. Working memory write-back

断言：

- `agentd` 把 plan summary 写入 `sessiond`
- `memory.read` 能读到 primary task 与 file task 的摘要
- memory payload 包含 `task_id`、`summary`、`route_preference`、`candidate_capabilities`

### 7. Episodic memory

断言：

- `agentd` 在 submit / plan / replan 后追加 episodic history
- `memory.episodic.list` 能读到 primary task 与 file task 的 history entry
- episodic metadata 包含 `task_id`、`intent`、`candidate_capabilities`、`task_state`

### 8. Replan path

断言：

- `agent.task.replan` 会复用已有 `session_id`
- 返回值带 `basis_task_id` 与 `session_task_count`
- 新建任务状态为 `planned`，而不是直接覆盖 basis task
- basis task 若可转移，则被标记为 `replanned`

### 9. Procedural memory

断言：

- `memory.procedural.put` 可写入 versioned rule record
- `memory.procedural.list` 可按 `rule_name` 与 `session_id` 过滤
- procedural record 保留 `version_id`、`rule_name`、`payload`、`created_at`

### 10. Approval state machine

断言：

- `policy.evaluate` 对 `system.file.bulk_delete` 返回 `needs-approval`
- 返回值带 `approval_ref`
- `approval.get` 可读取 pending 记录
- `approval.list` 可按 `session_id` / `status` 过滤
- `approval.resolve` 可把 pending 更新为 `approved`
- `policy.token.issue` 只有在 `approval_ref` 已批准时才成功
- `policy.token.verify` 能验证审批后 token

### 11. Runtime preview

对于包含 `runtime.infer.submit` 的 intent：

- 若 policy 允许且 provider 可用，则返回 `runtime_preview`
- 若 provider 不可用，则返回可解释的 `provider_resolution.reason`
- 若 policy 不是 `allowed`，则不应触发 preview execute

## 后续扩展

下一轮应继续补：

1. recovery / replan path validation
2. shell approval / chooser flow validation
3. compiled multi-service evidence capture
4. provider worker runtime 与 registry 生命周期联动验证（当前 registry smoke 见 `provider-registry-test-plan.md`）
