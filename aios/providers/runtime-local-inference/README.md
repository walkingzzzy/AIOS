# aios-runtime-local-inference-provider

`aios-runtime-local-inference-provider` 把 `runtime.local.inference` 从 descriptor 变成面向 provider registry 的真实 provider façade，并补齐 embedding / rerank 的正式 contract、metadata 与 observability 输出。

## 当前能力

- 通过 UDS + JSON-RPC 暴露 `runtime.infer.submit` / `runtime.embed.vectorize` / `runtime.rerank.score`
- 使用 `policyd` 校验 execution token，而不是直接信任上游请求
- `runtime.infer.submit` 将请求转发给 `runtimed`，并把 `backend_id` / `degraded` / `rejected` / `reason` 透传回来
- 当 `/var/lib/aios/runtime/ai-readiness.json` 指示 `cloud-ready` / `hybrid-remote-only`，或本地 runtime 不可达但已配置远端 endpoint 时，`runtime.infer.submit` 会回退到 OpenAI-compatible `/v1/chat/completions`
- `runtime.embed.vectorize` 在 `remote-first` / `remote-only` 下可走 OpenAI-compatible `/v1/embeddings`，否则保留确定性本地 embedding 作为正式 fallback 路径
- `runtime.rerank.score` 在 `remote-first` / `remote-only` 下可走远端 embedding 相似度 rerank，失败时回退到本地 lexical overlap rerank
- provider 响应会补充 provider 状态、queue 饱和度与 runtime budget 快照
- 启动后向 `agentd` 自注册并汇报 provider health
- inference / embedding / rerank 结果会写入统一 provider observability sink，便于团队 4/5 直接消费

## 当前边界

- 不自己实现 `runtimed` inference backend
- 本地 embedding / rerank 仍保留 deterministic / lexical fallback，不等同于硬件加速或专用 vendor backend
- 不伪造成功响应；`runtimed` 不可达时返回结构化拒绝结果
- 不替代 `runtimed` 的 budget / queue / fallback 策略

## 远端配置

- provider unit 现会读取 `/etc/aios/runtime/platform.env`
- 支持的 env：
  - `AIOS_RUNTIMED_AI_ENDPOINT_BASE_URL` 或 `AIOS_RUNTIME_LOCAL_INFERENCE_PROVIDER_REMOTE_BASE_URL`
  - `AIOS_RUNTIMED_AI_ENDPOINT_MODEL` 或 `AIOS_RUNTIME_LOCAL_INFERENCE_PROVIDER_REMOTE_MODEL`
  - `AIOS_RUNTIMED_AI_ENDPOINT_EMBEDDING_MODEL` 或 `AIOS_RUNTIME_LOCAL_INFERENCE_PROVIDER_REMOTE_EMBEDDING_MODEL`
  - `AIOS_RUNTIMED_AI_ENDPOINT_RERANK_MODEL` 或 `AIOS_RUNTIME_LOCAL_INFERENCE_PROVIDER_REMOTE_RERANK_MODEL`
  - `AIOS_RUNTIMED_AI_ENDPOINT_API_KEY`、`OPENAI_API_KEY` 或 `AIOS_RUNTIME_LOCAL_INFERENCE_PROVIDER_REMOTE_API_KEY`
  - `AIOS_RUNTIMED_AI_ENABLED=0` 可禁用 provider 对外提供 AI 路径
  - `AIOS_RUNTIMED_AI_ROUTE_PREFERENCE=local-first|remote-first|remote-only` 可统一控制 infer / embedding / rerank 的本地/远端优先级
- 若 env 缺失，会继续尝试从 `/var/lib/aios/onboarding/ai-onboarding-report.json` 读取 endpoint base URL / model

## 运行示例

```bash
cargo build -p aios-runtime-local-inference-provider
python3 scripts/test-runtime-local-inference-provider-smoke.py --bin-dir aios/target/debug
python3 scripts/test-provider-registry-smoke.py --bin-dir aios/target/debug
```

## 主要验证

- `cargo test -p aios-runtime-local-inference-provider`
- `python3 scripts/test-runtime-local-inference-provider-smoke.py --bin-dir aios/target/debug`
- `python3 scripts/test-provider-registry-smoke.py --bin-dir aios/target/debug`
- [runtime-local-inference-provider-test-plan](../../../tests/ipc/runtime-local-inference-provider-test-plan.md)
