# aios-agentd

## 1. 角色

`aios-agentd` 是 AIOS 的规划与编排入口，负责把用户意图转成受治理的任务计划。

核心职责：

- 意图分析
- 任务规划 / 重规划
- topology 选择
- capability 候选解析
- 调用 registry 解析 provider
- 失败后生成恢复计划或低风险替代路径

## 2. 不负责什么

`agentd` 不负责：

- 最终授权
- execution token 签发
- 持久化最终会话状态
- 直接执行高风险 capability
- 直接持有长期主记忆写权限

这些分别属于 `policyd`、`sessiond`、provider 或 `runtimed`。

## 3. 推荐技术路线

- 语言：Rust
- async runtime：Tokio
- 通信：UDS + JSON-RPC
- 关键模块：planner、resolver、topology、route client、recovery planner

## 4. 推荐目录结构

```text
agentd/
├── src/
│   ├── main.rs
│   ├── config.rs
│   ├── rpc.rs
│   ├── planner.rs
│   ├── resolver.rs
│   ├── topology.rs
│   ├── recovery.rs
│   └── errors.rs
├── tests/
├── service.yaml
└── units/
```

## 5. 关键输入 / 输出

**输入**

- `intent`
- `multimodal_context`
- `session_context_refs`
- provider candidates
- route constraints

**输出**

- `task_plan`
- `candidate_capabilities`
- `route_request`
- `recovery_plan`
- `working_memory_writeback`

## 6. 当前状态

- 仓库状态：`In Progress`
- 已有：`README.md`、`service.yaml`、`units/aios-agentd.service`、`src/` 骨架、planner / resolver / topology / RPC skeleton、`sessiond/policyd/runtimed` 联调、provider registry 接入与 lifecycle RPC、browser / office / code-sandbox compat 意图识别、portal file / export target / screen share handle flow、task state sync、working / episodic memory write-back、basis-task-aware replan、模块级单测、registry 与 IPC smoke harness，以及 `agentd -> system-files-provider` 实际调用闭环验证
- 缺失：formal chooser / approval GUI surface、recovery 深化、多步执行流与更多 provider worker 联调

## 7. 下一步

1. 扩展多步任务规划
2. 深化 recovery / fallback state reuse
3. 接 formal shell chooser / approval GUI surface
4. 接更多 provider worker / runtime contracts
