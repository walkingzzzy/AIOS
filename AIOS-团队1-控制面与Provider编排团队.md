# AIOS 团队1开发工作包：控制面与 Provider 编排团队

## 1. 团队名称
控制面与 Provider 编排团队

## 2. 主责范围

### 负责模块
- `aios/services/agentd`
- `aios/services/sessiond`
- `aios/services/policyd`
- `aios/providers/system-intent`
- `aios/providers/system-files`
- 与上述模块直接相关的 `docs/system-development/*`、接口说明、测试资产

### 负责什么
1. `agentd` 的 planner / resolver / provider route / portal handle / recovery flow 主链路
2. `sessiond` 的 task state、memory、handle persistence、SQLite migration runner
3. `policyd` 的 approval、token issue/verify、audit writer/query、target-bound constraints
4. `system-intent` 与 `system-files` provider 的正式控制面接入
5. 控制面对 shell / compat / device 暴露的只读查询接口

### 不负责什么
- 不负责 `runtimed` 的 GPU/NPU backend 与 worker 生命周期
- 不负责 `deviced` 的原生采集 backend
- 不负责 `shell/` 的 GUI 和 compositor 实现
- 不负责 `image/`、`updated`、`hardware/` 的交付与实机验证
- 不负责 `compat/` 内 browser/office/mcp bridge 的执行栈实现

## 3. 当前需要完成的核心开发任务
1. 将 `agentd` 从 skeleton 编排链推进到正式多步任务执行流。
2. 完成 planner / replan / recovery flow / portal-bound task lifecycle 的收敛。
3. 完成 `sessiond` 的 SQLite migration runner 与 memory 持久化闭环。
4. 完成 task、working memory、episodic/procedural memory 的一致性持久化。
5. 深化 `policyd` 的 approval state machine、token 约束、evidence query/export。
6. 建立统一的 provider registry + portal + control-plane 调用路径，避免各处重复接 provider。
7. 将 `system-intent`、`system-files` 从基础 provider 接入推进到正式可依赖能力。
8. 补齐 `agentd -> sessiond -> policyd -> provider` 的 integration tests。
9. 为 shell 提供稳定的 task/approval/portal/audit 只读查询模型。
10. 为 compat / operator 场景提供可消费的 evidence/export/query 接口。

## 4. 输入与输出边界

### 主要输入依赖
- 团队2提供稳定的 runtime RPC、worker result 和 route/profile 契约
- 团队3提供稳定的 device state / capture metadata / backend-state 模型
- 团队4提出 shell 侧所需的 task/approval/query 只读视图需求
- 团队5提出 compat registration / audit/export / token verify 的消费需求

### 主要输出产物
- 修改 `services/agentd/src/*`
- 修改 `services/sessiond/src/*` 与 `migrations/*`
- 修改 `services/policyd/src/*`
- 修改 `providers/system-intent/*`、`providers/system-files/*`
- 新增 integration tests、migration tests、audit/export tests
- 更新 README、接口文档、必要 ADR 或 schema 文档

## 5. 并行开发约束

### 可独立开发目录
- `services/agentd`
- `services/sessiond`
- `services/policyd`
- `providers/system-intent`
- `providers/system-files`

### 需要优先冻结的接口
- `task.*` RPC
- `approval.*` RPC
- `portal.handle.*` 数据模型
- `audit/query/export` 接口
- provider capability descriptor
- token / constraint schema

### 应避免的冲突点
- 团队4不得在 shell 中复制 approval 业务逻辑
- 团队5不得在 compat 内重新实现 registration 审批语义
- 团队2不得在 runtime 层定义控制面自己的 provider route 逻辑

## 6. 测试与验收

### 必要测试
- `agentd/sessiond/policyd/provider` 集成测试
- SQLite migration 测试
- approval/token/query/export 回归测试
- portal handle 生命周期测试

### 验收标准
- 多步任务可以稳定走通 planner -> approval -> provider execution -> persistence
- 审批与 token 约束能被 shell/compat 正确消费
- evidence query/export 可被 operator 流程调用
- 不再依赖大量 skeleton-only 控制面联调路径

## 7. 优先级
**优先级：高**

### 原因
控制面是 shell、compat、provider、device、runtime 联调的上游协调层；如果接口不稳定，其它团队会频繁返工。

### 阻塞项
- task / approval / portal / audit 只读接口冻结
- provider registry 与 capability 模型冻结

### 可并行项
- memory persistence 收敛
- `system-intent` / `system-files` 正式化
- audit/export 测试与文档补齐

## 8. 阶段建议

### 第一阶段必须完成
- 冻结 task/approval/portal/audit 接口
- 收敛 provider registry 与 control-plane 路由

### 第二阶段可并行推进
- 深化 memory persistence、migration runner、recovery flow
- 完成 control-plane integration tests

### 第三阶段收敛与验收
- 跨团队联调
- 回归测试
- README / docs / ADR 同步

