# AIOS Runtime Local Inference Provider Test Plan

## 范围

本计划验证 `runtime.local.inference` provider 的正式最小闭环：

- provider registry 自注册
- `runtime.infer.submit`
- `runtime.embed.vectorize`
- `runtime.rerank.score`
- provider observability sink
- 与 `policyd` / `agentd` / `runtimed` 的最小集成

## 覆盖服务

- `policyd`
- `agentd`
- `runtimed`
- `aios-runtime-local-inference-provider`

## 核心断言

### 1. provider 自注册与健康状态

- `runtime.local.inference` 会向 registry 自注册
- `provider.health.get` 能看到 `available` 状态
- health notes 会暴露 `embedding_backend` 与 `rerank_backend`

### 2. inference façade

- `runtime.infer.submit` 会先校验 execution token
- provider 会把请求转发给 `runtimed`
- 响应保留 `backend_id`、`route_state`、`runtime_service_id`
- provider 会附带 runtime budget / queue 元数据
- provider 会写出 `provider.runtime.infer.result` trace

### 3. embedding 正式路径

- `runtime.embed.vectorize` 接受多输入文本
- 响应返回稳定的向量维度与 embedding records
- 响应 notes 标记 `provider_operation=embedding`
- `route_state` 固定为 `provider-local-embedding`
- `provider_id` 与 `embedding_backend` 对齐 descriptor / config
- provider 会写出 `provider.runtime.embed.result` trace

### 4. rerank 正式路径

- `runtime.rerank.score` 按 lexical overlap 返回排序结果
- `top_k` 会截断结果数
- 响应 notes 标记 `provider_operation=rerank`
- `route_state` 固定为 `provider-local-rerank`
- `provider_id` 与 `rerank_backend` 对齐 descriptor / config
- provider 会写出 `provider.runtime.rerank.result` trace

### 5. 失败与退化语义

- session / task 与 execution token 不匹配时请求被拒绝
- provider 并发预算耗尽时返回结构化 budget exhaustion 错误
- `runtimed` 不可用时 `runtime.infer.submit` 返回 `runtime-unavailable`
- provider health 会在 runtime outage 时降级

## 运行入口

```bash
cargo build -p aios-policyd -p aios-agentd -p aios-runtimed -p aios-runtime-local-inference-provider
python3 scripts/test-runtime-local-inference-provider-smoke.py --bin-dir aios/target/debug
```

## 后续扩展

1. 将 embedding / rerank 从 reference backend 继续推进到 vendor / hardware adapter
2. 把 provider 并发预算与 `runtimed` queue budget 做更细粒度联动
3. 扩展更完整的 request/response 审计与回放验证
