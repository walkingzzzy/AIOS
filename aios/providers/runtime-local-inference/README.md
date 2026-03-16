# aios-runtime-local-inference-provider

`aios-runtime-local-inference-provider` 把 `runtime.local.inference` 从 descriptor 变成面向 provider registry 的真实 provider façade，并补齐 embedding / rerank 的正式 contract、metadata 与 observability 输出。

## 当前能力

- 通过 UDS + JSON-RPC 暴露 `runtime.infer.submit` / `runtime.embed.vectorize` / `runtime.rerank.score`
- 使用 `policyd` 校验 execution token，而不是直接信任上游请求
- `runtime.infer.submit` 将请求转发给 `runtimed`，并把 `backend_id` / `degraded` / `rejected` / `reason` 透传回来
- `runtime.embed.vectorize` 提供正式的确定性本地 embedding 路径，输出稳定向量维度、provider metadata 与 trace event
- `runtime.rerank.score` 提供正式的 lexical overlap 本地 rerank 路径，输出确定性排序结果、top_k 截断与 trace event
- provider 响应会补充 provider 状态、queue 饱和度与 runtime budget 快照
- 启动后向 `agentd` 自注册并汇报 provider health
- inference / embedding / rerank 结果会写入统一 provider observability sink，便于团队 4/5 直接消费

## 当前边界

- 不自己实现 `runtimed` inference backend
- embedding / rerank 当前仍是 reference backend，不是 vendor 神经网络模型或硬件加速实现
- 不伪造成功响应；`runtimed` 不可达时返回结构化拒绝结果
- 不替代 `runtimed` 的 budget / queue / fallback 策略

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
