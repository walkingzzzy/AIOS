# AIOS 团队2 Backlog：运行时与推理后端团队

## 1. Backlog 目标
将 runtime 从当前具备 scheduler/budget/queue 基础能力但仍存在 placeholder worker、vendor backend 缺失、embedding/rerank skeleton 的状态，推进到正式可依赖的本地推理后端层。

## 2. P0（第一优先级）

### P0-1 冻结 runtime schema 与 worker contract
- 范围：`services/runtimed`、`runtime/`
- 交付物：request/response schema、worker lifecycle 字段、错误码说明
- 验收标准：团队1/4/5 基于同一契约联调，不再频繁改协议
- 测试：schema snapshot tests、worker compatibility tests
- 风险：协议不稳会放大上下游返工

### P0-2 收敛 route-profile / runtime-profile 结构
- 交付物：统一 profile 结构与说明
- 验收标准：平台注入与 runtime 消费使用同一套 profile 语义
- 测试：profile parsing tests、config compatibility tests
- 风险：若 profile 重复定义，会导致 image/runtime 行为不一致

### P0-3 完成 backend health / event 字段定义
- 交付物：health 状态、event 字段、observability 输出规范
- 验收标准：shell/operator/platform 可稳定消费 runtime 状态
- 测试：event schema tests、health transition tests

## 3. P1（第二优先级）

### P1-1 将 local-gpu / local-npu 从 baseline 推进到正式 vendor backend
- 交付物：至少一条可验证 GPU/NPU 接入路径
- 验收标准：不再依赖纯 placeholder worker 来表示可用后端
- 测试：backend integration tests、hardware-backed smoke

### P1-2 完成 worker readiness / restart / timeout / fallback
- 交付物：worker 生命周期管理实现
- 验收标准：backend 异常时可恢复或回退，行为可预期
- 测试：failure injection tests、restart tests、timeout tests

### P1-3 补齐 budget / queue / backpressure 正式行为
- 交付物：预算控制和队列治理逻辑
- 验收标准：高并发或资源受限时行为稳定
- 测试：budget tests、queue pressure tests

### P1-4 将 embedding / rerank 从 skeleton 升级为正式能力
- 范围：`providers/runtime-local-inference`
- 交付物：正式 embedding/rerank backend
- 验收标准：不再出现 `provider-skeleton` 作为主要路径
- 测试：embedding/rerank integration tests

## 4. P2（第三优先级）

### P2-1 建立跨服务 runtime observability sink
- 交付物：事件聚合输出、消费方说明
- 验收标准：团队4/5可直接读取 runtime 事件
- 测试：event propagation tests

### P2-2 完善文档、运行说明与调试指引
- 交付物：README、运行说明、故障处理文档
- 验收标准：新成员可根据文档完成联调

### P2-3 扩展 backend test matrix
- 交付物：更多 failure injection、平台差异、兼容性测试
- 验收标准：release gate 可引用 runtime 测试结果

## 5. 里程碑建议

### M1：契约冻结
完成 P0 项，形成稳定 runtime 协议与 profile 结构。

### M2：后端正式化
完成 P1-1 ~ P1-4，runtime 进入可验证正式联调状态。

### M3：观测与收敛
完成 P2 项，完善事件、文档与测试矩阵。

## 6. 关键依赖
- 需要团队5提供 platform/hardware profile 约束
- 需要团队1稳定控制面对 runtime 的调用方式
- 需要团队4明确 runtime 状态展示需求

## 7. 完成定义（DoD）
1. worker contract 稳定并可回归验证
2. 至少一条 GPU/NPU/backend 正式路径可验证
3. embedding/rerank 不再停留在 skeleton
4. runtime 可输出统一 health/event 给上下游消费

