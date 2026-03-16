# AIOS 团队2开发工作包：运行时与推理后端团队

## 1. 团队名称
运行时与推理后端团队

## 2. 主责范围

### 负责模块
- `aios/services/runtimed`
- `aios/runtime/`
- `aios/providers/runtime-local-inference`
- 与 runtime schema、profile、worker contract 直接相关的文档与测试资产

### 负责什么
1. `runtimed` 的 scheduler / queue / budget / backpressure / fallback / backend lifecycle
2. `runtime/` 下 route-profile、runtime-profile、backend contract、event surface
3. `runtime-local-inference` 的 embedding / rerank / infer 正式能力
4. GPU / NPU / managed worker / unix worker 的正式接入
5. runtime observability sink 与 backend health/event 规范

### 不负责什么
- 不负责 `agentd` 的任务编排与审批业务
- 不负责 `shell/` GUI
- 不负责 `deviced` 原生 backend
- 不负责 `image/updated/hardware` 的交付闭环
- 不负责 `compat/` 的 browser/office/mcp bridge 实现

## 3. 当前需要完成的核心开发任务
1. 将 `local-gpu`、`local-npu` 从 baseline / placeholder worker 推进到真实 vendor runtime 接入。
2. 完成 worker readiness、health、restart、timeout、fallback 的正式实现。
3. 补齐 budget enforcement、queue backpressure、route fallback 的稳定行为。
4. 将 `runtime-local-inference` 中的 embedding/rerank 从 `provider-skeleton` 升级为正式后端。
5. 收敛 `runtime-profile` 与 `route-profile`，避免平台侧和 runtime 侧重复维护配置语义。
6. 建立跨服务 runtime observability sink，向 shell/operator/platform 输出统一事件。
7. 增加 backend integration tests、failure injection tests、budget/fallback tests。
8. 补齐 worker contract 文档、schema 与兼容性约束。

## 4. 输入与输出边界

### 主要输入依赖
- 团队1提供稳定的 runtime 调用契约与 provider 消费模式
- 团队5提供 platform profile、hardware profile 与平台注入约束
- 团队4提出 shell/operator 对 runtime health/event 的展示需求

### 主要输出产物
- 修改 `services/runtimed/src/*`
- 修改 `runtime/*`
- 修改 `providers/runtime-local-inference/*`
- 新增 worker contract tests、backend tests、failure injection tests
- 输出稳定的 runtime schema、health/event 字段、profile 文档

## 5. 并行开发约束

### 可独立开发目录
- `services/runtimed`
- `runtime/`
- `providers/runtime-local-inference`

### 需要优先冻结的接口
- `runtime-*.schema.json`
- worker request / response contract
- backend health / event 字段
- route-profile / runtime-profile 结构

### 应避免的冲突点
- 团队5只能消费 runtime profile，不能在 `runtimed/src` 中实现 vendor backend
- 团队1不得在控制面复制 route/budget/fallback 逻辑
- 团队4不得在 shell 内自行推断 backend 生命周期语义

## 6. 测试与验收

### 必要测试
- worker contract 测试
- backend readiness / restart / timeout / fallback 测试
- budget / queue / backpressure 测试
- embedding / rerank / infer 集成测试
- failure injection 与 observability 事件测试

### 验收标准
- 至少形成可验证的 GPU/NPU/backend 正式接入路径
- runtime profile 与平台 profile 的边界清晰稳定
- embedding / rerank 不再停留在 skeleton 状态
- shell / operator / platform 可消费统一 runtime 事件

## 7. 优先级
**优先级：高**

### 原因
runtime backend 是 AI 能力落地的基础层，也是本地推理、预算控制和硬件能力调度的核心阻塞项。

### 阻塞项
- worker contract 冻结
- runtime/profile/schema 冻结

### 可并行项
- embedding/rerank 正式化
- observability sink
- backend failure injection 与测试矩阵补齐

## 8. 阶段建议

### 第一阶段必须完成
- 冻结 runtime schema、worker contract、profile 结构
- 收敛 backend health/event 字段

### 第二阶段可并行推进
- GPU/NPU/managed worker 正式实现
- embedding/rerank backend 完整化
- observability sink 建立

### 第三阶段收敛与验收
- 与团队1/4/5联调
- 加入统一 release gate
- 更新 runtime README、设计文档与测试说明

