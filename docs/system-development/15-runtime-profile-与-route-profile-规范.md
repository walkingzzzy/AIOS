# 15 · Runtime Profile 与 Route Profile 规范

**版本**: 1.0.0  
**更新日期**: 2026-03-08  
**状态**: P1/P2 核心规格

---

## 1. 目标

本文件把 `13-AI 控制流与应用调用规范` 中的“AI 如何配置”落成正式配置对象。  
重点回答：

- 模型与推理后端如何配置
- 路由与 agent topology 如何配置
- 这些配置如何在系统、用户、会话、任务各层生效

## 2. 配置对象总览

AIOS v1 最少定义以下配置对象：

- `runtime-profile`
- `route-profile`
- `memory-profile`
- `policy-profile`
- `shell-profile`
- `provider-profile`

本文件重点冻结前两项，并定义它们与其余 profile 的关系。

## 3. `runtime-profile` 定义

`runtime-profile` 用来描述“系统如何运行模型与推理任务”。

### 3.1 核心字段

- `profile_id`
- `scope`：`system` / `organization` / `user` / `workspace` / `session` / `task`
- `default_backend`
- `allowed_backends[]`
- `local_model_pool[]`
- `remote_model_pool[]`
- `embedding_backend`
- `rerank_backend`
- `cpu_fallback`
- `memory_budget_mb`
- `kv_cache_budget_mb`
- `timeout_ms`
- `max_concurrency`
- `max_parallel_models`
- `offload_policy`
- `degradation_policy`
- `observability_level`

### 3.2 backend 类型

v1 推荐至少支持以下 backend 类型：

- `local-cpu`
- `local-gpu`
- `local-npu`
- `sandbox-runtime`
- `attested-remote`

### 3.3 `offload_policy`

用于定义什么情况下允许远端或受证明远端执行：

- `disabled`
- `manual-only`
- `allowed-low-sensitivity`
- `allowed-by-policy`

规则：

- 默认推荐 `disabled` 或 `manual-only`
- 不允许 profile 直接越过 `policyd` 打开受限远端执行

## 4. `route-profile` 定义

`route-profile` 用来描述“AIOS 如何为任务选择 topology、模型、provider 和执行路径”。

### 4.1 核心字段

- `profile_id`
- `default_topology`
- `allowed_topologies[]`
- `router_stack[]`
- `semantic_router_enabled`
- `llm_router_enabled`
- `cost_router_enabled`
- `provider_preference`
- `prefer_local`
- `prefer_structured_interface`
- `allow_gui_fallback`
- `iteration_cap`
- `tool_call_cap`
- `replan_cap`
- `escalation_threshold`
- `human_handoff_policy`

### 4.2 topology 约束

v1 推荐支持：

- `direct`
- `tool-calling`
- `supervisor`
- `plan-execute`

默认建议：

- 系统级短任务 → `tool-calling`
- 复杂长流程 → `plan-execute`
- 跨域协调任务 → `supervisor`
- 简单单步问答 → `direct`

### 4.3 `router_stack`

推荐路由栈：

1. rule router
2. semantic router
3. provider availability filter
4. policy constraints filter
5. cost / latency router
6. llm router

说明：

- 不应一开始就让大模型决定全部路由
- 结构化与低成本路由应优先于高成本自由推理路由

## 5. 作用域与优先级

配置作用域采用以下优先级：

```text
system
  < organization
  < hardware-profile
  < user
  < workspace
  < session
  < task
```

规则：

- 下层覆盖上层的“偏好”
- 下层不能覆盖上层的“禁止项”
- `policy-profile` 优先级始终高于 `runtime-profile` 与 `route-profile`

## 6. 安全与约束字段

### 6.1 `runtime-profile` 不得控制的内容

下列内容不可由 `runtime-profile` 单独决定：

- 自动批准高风险 capability
- 默认开启受证明远端执行
- 禁用 taint 检查
- 取消 code sandbox 限制

### 6.2 `route-profile` 不得控制的内容

下列内容不可由 `route-profile` 单独决定：

- 跳过 provider registry
- 跳过 portal 对象选择
- 在未授权条件下启用 GUI automation
- 把高风险任务降级为无审批执行

## 7. 预算模型

## 7.1 `runtime-profile` 最小预算字段

- `memory_budget_mb`
- `kv_cache_budget_mb`
- `cpu_time_budget_ms`
- `gpu_time_budget_ms`
- `max_tokens`
- `max_output_tokens`
- `max_parallel_calls`

## 7.2 `route-profile` 最小预算字段

- `iteration_cap`
- `tool_call_cap`
- `replan_cap`
- `max_route_depth`
- `max_handoffs`

## 8. 降级与回退

当资源不足、模型不可用或路由失败时，AIOS 至少应支持：

- `local-gpu -> local-cpu`
- `supervisor -> tool-calling`
- `tool-calling -> direct`
- `structured interface -> portal -> GUI fallback`
- `attested-remote -> local-safe-mode`

所有降级都必须：

- 可审计
- 可解释
- 不突破策略边界

## 9. 推荐配置示例

```yaml
runtime_profile:
  profile_id: default-local
  scope: system
  default_backend: local-gpu
  allowed_backends:
    - local-cpu
    - local-gpu
    - attested-remote
  local_model_pool:
    - qwen-local-14b
    - deepseek-local-7b
  remote_model_pool:
    - gpt-4.1
  embedding_backend: local-embedding
  rerank_backend: local-reranker
  cpu_fallback: true
  memory_budget_mb: 6144
  kv_cache_budget_mb: 2048
  timeout_ms: 30000
  max_concurrency: 4
  max_parallel_models: 2
  offload_policy: manual-only
  degradation_policy: fallback-local-cpu
  observability_level: standard

route_profile:
  profile_id: default-route
  default_topology: tool-calling
  allowed_topologies:
    - direct
    - tool-calling
    - supervisor
    - plan-execute
  router_stack:
    - rule
    - semantic
    - provider-filter
    - policy-filter
    - cost
    - llm
  semantic_router_enabled: true
  llm_router_enabled: true
  cost_router_enabled: true
  provider_preference: structured-first
  prefer_local: true
  prefer_structured_interface: true
  allow_gui_fallback: manual-only
  iteration_cap: 8
  tool_call_cap: 12
  replan_cap: 2
  escalation_threshold: high-risk-or-low-confidence
  human_handoff_policy: required-on-ambiguous-high-risk
```

## 10. 激活时机

### 启动时

加载：

- system `runtime-profile`
- hardware profile
- default `route-profile`

### 登录时

加载：

- user-level `route-profile`
- user-level `memory-profile`
- shell / provider profile

### 会话时

加载：

- workspace-specific route preference
- current session runtime overrides

### 任务时

允许有限覆盖：

- 指定模型池
- 指定超时
- 指定 topology 偏好
- 禁止扩大权限或绕开审批

## 11. 可观测性要求

以下配置生效点必须进入事件流：

- 哪个 runtime profile 被选中
- 哪个 route profile 被选中
- 是否发生 profile override
- 是否发生降级或回退
- 是否因预算不足拒绝执行
- 是否因策略冲突拒绝使用某 backend

## 12. v1 最低要求

- system / user / session 三层 profile 生效
- `runtime-profile` 与 `route-profile` 可独立加载
- profile override 可审计
- CPU fallback 存在
- GUI fallback 默认为关闭或手动
- 远端执行默认关闭或手动

## 13. 与现有文档的关系

- `13-AI 控制流与应用调用规范` 回答“配什么”
- 本文回答“配置对象长什么样、在哪一层生效、受什么约束”
- `10-能力、策略与审计规范` 仍然高于 profile 配置
