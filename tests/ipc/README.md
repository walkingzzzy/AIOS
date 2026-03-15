# IPC Smoke Harness

此目录用于 AIOS 本地多服务联调的最小 smoke 测试说明。

## 当前内容

- `scripts/test-ipc-smoke.py`
- `scripts/test-provider-registry-smoke.py`
- `scripts/test-portal-file-handle-smoke.py`
- `tests/ipc/test-plan.md`
- `tests/ipc/portal-file-handle-test-plan.md`
- `tests/ipc/provider-registry-test-plan.md`
- `tests/ipc/provider-fs-test-plan.md`
- `tests/ipc/portal-export-target-test-plan.md`
- `tests/ipc/portal-screen-share-test-plan.md`

## 目标

在单机环境中验证以下最小闭环：

1. 启动 `sessiond`
2. 启动 `policyd`
3. 启动 `runtimed`
4. 启动 `agentd`
5. 调用 `agent.intent.submit`
6. 校验返回中的：
   - session/task 已创建
   - plan 已生成
   - policy 已返回
   - route 已返回
   - provider resolution 已返回
7. 调用 `task.list` 校验 primary task 已落到 `sessiond`
8. 调用 `task.state.update` 校验任务状态机可用
9. 复用同一 session 发送 file intent
10. 复用同一 session 发送 export intent
11. 复用同一 session 发送 screen share intent
12. 校验 file/export/screen `portal_handle` 已生成
13. 调用 `portal.handle.list` 校验 handle 已绑定到 `sessiond`
14. 调用 `memory.read` 校验 `agentd` 计划摘要已回写到 `sessiond`
15. 调用 `memory.episodic.list` 校验任务历史已写入 episodic memory
16. 调用 `agent.task.replan` 校验 replan 会复用 session 历史并返回 basis task
17. 调用 `memory.procedural.put` / `memory.procedural.list` 校验 procedural versioning skeleton
18. 调用 `policy.evaluate` / `approval.get` / `approval.list` / `approval.resolve` 校验最小审批链
19. 调用 `policy.token.issue` / `policy.token.verify` 校验审批后 token 才可签发
20. 调用 `provider.fs.open` / `system.file.bulk_delete` 校验 filesystem provider runtime

## 运行前提

需要先有已编译的二进制，例如：

```bash
cargo build -p aios-agentd -p aios-sessiond -p aios-policyd -p aios-runtimed
```

## 运行示例

```bash
scripts/test-ipc-smoke.py --bin-dir aios/target/debug
```

如需验证 `system-files-provider`：

```bash
scripts/test-provider-fs-smoke.py --bin-dir aios/target/debug
```

如需只验证 provider registry 与 builtin runtime capability resolve：

```bash
scripts/test-provider-registry-smoke.py --bin-dir aios/target/debug
```

如需覆盖自定义文件路径 portal 流：

```bash
scripts/test-ipc-smoke.py --bin-dir aios/target/debug --file-intent 'Open /tmp/report.txt'
```

也可以分别指定路径：

```bash
scripts/test-ipc-smoke.py \
  --agentd aios/target/debug/agentd \
  --sessiond aios/target/debug/sessiond \
  --policyd aios/target/debug/policyd \
  --runtimed aios/target/debug/runtimed
```

## 当前限制

- 当前 runner 依赖本地已编译的 Rust 二进制
- control-plane smoke 与 filesystem provider smoke 已有入口，`scripts/test-portal-file-handle-smoke.py` 也已覆盖 chooser prototype 的 live 读取链，但仍不覆盖正式 shell GUI / compositor
- 当前不做性能、并发和恢复链验证
