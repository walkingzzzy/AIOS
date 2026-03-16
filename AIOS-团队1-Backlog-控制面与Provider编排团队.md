# AIOS 团队1 Backlog：控制面与 Provider 编排团队

## 1. Backlog 目标
将控制面从当前可联调但仍偏 skeleton/partial impl 的状态，推进到可稳定支撑 shell、compat、device、runtime 联调的正式编排层。

## 2. P0（第一优先级）

### P0-1 冻结 task / approval / portal / audit 查询接口
- 范围：`services/agentd`、`services/sessiond`、`services/policyd`
- 交付物：接口文档、schema、响应字段说明
- 验收标准：团队4/5可以基于同一只读模型联调，不再反复改字段
- 测试：RPC compatibility tests、schema snapshot tests
- 风险：接口晚冻结会导致 shell/compat 反复返工

### P0-2 收敛 provider registry 与 control-plane 调用路径
- 范围：`services/agentd`、`providers/system-intent`、`providers/system-files`
- 交付物：统一 provider registry、capability descriptor、调用链文档
- 验收标准：同一 provider 不存在多套接入路径
- 测试：provider registry integration tests
- 风险：若 registry 不统一，后续 provider 扩展会重复开发

### P0-3 完成 approval state machine 与 token/constraint 基线
- 范围：`services/policyd`
- 交付物：approval 状态机、token verify 约束、target-bound schema
- 验收标准：shell/compat/operator 均能使用同一审批和约束语义
- 测试：approval flow tests、token verify tests
- 风险：权限边界不稳会影响所有上层功能

## 3. P1（第二优先级）

### P1-1 完成 sessiond 的 SQLite migration runner
- 交付物：migration runner、版本管理、回归说明
- 验收标准：新旧状态可迁移，测试环境可重建数据库
- 测试：migration tests、persistence recovery tests

### P1-2 收敛 task / working / episodic / procedural memory 持久化
- 交付物：memory persistence 实现、字段一致性说明
- 验收标准：任务恢复、历史查询和 memory 读取行为一致
- 测试：session persistence tests、recovery tests

### P1-3 打通 agentd 多步任务执行流与 recovery flow
- 交付物：planner/replan/recovery 正式流程
- 验收标准：任务能稳定走通 planner -> approval -> provider -> persistence
- 测试：multi-step integration tests

## 4. P2（第三优先级）

### P2-1 增强 evidence query/export 能力
- 交付物：导出接口、operator 场景查询说明
- 验收标准：团队5可直接消费 audit/export 结果
- 测试：query/export tests

### P2-2 完善 system-intent / system-files 正式化能力
- 交付物：更完整的 provider 行为、约束、文档
- 验收标准：从 baseline provider 提升到稳定 first-party provider
- 测试：provider behavior tests

### P2-3 文档与 ADR 同步
- 交付物：README、接口说明、必要 ADR 更新
- 验收标准：文档状态与实现一致
- 测试：人工审查 + 示例联调验证

## 5. 里程碑建议

### M1：接口冻结
完成 P0-1 ~ P0-3，形成稳定控制面输入输出模型。

### M2：主流程落地
完成 P1-1 ~ P1-3，控制面进入正式联调阶段。

### M3：扩展与验收
完成 P2 项，补齐 operator/export/provider 收敛与文档。

## 6. 关键依赖
- 依赖团队2提供稳定 runtime 契约
- 依赖团队3提供稳定 device 状态模型
- 需要尽早响应团队4/5 的只读接口消费需求

## 7. 完成定义（DoD）
1. shell/compat 可直接消费稳定接口
2. 控制面不再依赖大量 skeleton-only 路径
3. migration、approval、provider registry 有回归测试
4. 文档与代码实现状态一致

