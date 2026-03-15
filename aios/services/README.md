# services/

`services/` 是 AIOS 的核心系统服务目录。  
这些服务共同构成 AIOS 的 **认知控制平面 + 执行治理平面**。

## 1. 目录目标

本目录承载的是长期运行的 system services：

- `agentd`
- `runtimed`
- `sessiond`
- `policyd`
- `deviced`
- `updated`

## 2. 当前状态

截至 2026-03-08，核心服务已经从“纯说明骨架”推进到**第一批源码骨架阶段**：

- 已建立 Rust workspace：`aios/Cargo.toml`
- 已建立共享 crate：`aios-core`、`aios-contracts`、`aios-rpc`
- `agentd` / `runtimed` / `sessiond` / `policyd` 已有 `src/`
- `updated` 已有最小 `src/` 与 `update.check` / `update.apply` / `update.health.get` / `update.rollback` / `recovery.bundle.export` skeleton
- 已有最小 UDS + JSON-RPC skeleton
- 已有基础 config / health / handler skeleton
- `deviced` 已有最小 `src/` 与多模态 RPC skeleton

## 3. 统一要求

每个服务子目录至少应长期包含：

- `README.md`：职责、边界、技术路线、当前状态、下一步
- `service.yaml`：服务元数据、技术基线、依赖、当前阶段、状态
- `units/*.service`：systemd unit
- `src/`：正式源码
- `tests/`：单测 / 集成测试

## 4. 服务总览

| 服务 | plane | 核心职责 | 当前状态 | 下一步 |
|------|-------|----------|----------|--------|
| `agentd` | control | 意图规划、capability 候选解析、任务重规划 | `In Progress` | 接入 `sessiond` / `policyd` / `runtimed` |
| `runtimed` | runtime | backend 抽象、queue、budget、fallback | `In Progress` | 扩展真实 GPU/NPU worker、跨服务 runtime event sink、更多 integration tests |
| `sessiond` | control | 会话、任务、记忆、恢复引用 | `In Progress` | 接 SQLite migration runner 与持久化 |
| `policyd` | trust | policy、approval、token、taint、audit | `In Progress` | 补 token verify、approval state machine |
| `deviced` | device | 多模态采集、归一化、设备状态 | `In Progress` | 深化 screen/audio/input capture adapters、状态恢复、normalize / retention |
| `updated` | trust | 更新、回滚、恢复、诊断包 | `In Progress` | 深化 `update.apply` / `update.rollback` 与真实 sysupdate / probe / rollback executor |

## 5. 统一技术基线

- 语言：Rust
- async runtime：Tokio
- 核心 RPC：Unix Domain Socket + JSON-RPC
- 桌面集成：D-Bus
- 配置：YAML / 环境变量覆盖
- 结构化事件：audit / trace / health events

## 6. 启动依赖原则

推荐顺序：

`updated -> sessiond -> policyd -> runtimed -> agentd -> deviced -> shell/provider/compat`

## 7. 当前最缺的东西

- 可编译验证的本地工具链与 CI
- `deviced` 的真实 capture adapters / visible indicators
- `updated` 的真实 sysupdate / rollback executor
- provider registry / portal runtime
- 服务间 integration tests
- boot 后自动拉起并通过 health check 的真实二进制
