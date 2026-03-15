# aios-runtime-local-inference-provider

`aios-runtime-local-inference-provider` 把 `runtime.local.inference` 从 descriptor 变成面向 provider registry 的真实 façade。

## 当前能力

- 通过 UDS + JSON-RPC 暴露 `runtime.infer.submit` / `runtime.embed.vectorize` / `runtime.rerank.score`
- 使用 `policyd` 校验 execution token，而不是直接信任上游请求
- `runtime.infer.submit` 将请求转发给 `runtimed`，并把 `backend_id` / `degraded` / `rejected` / `reason` 透传回来
- `runtime.embed.vectorize` 提供 deterministic embedding skeleton，输出稳定向量维度与 provider metadata
- `runtime.rerank.score` 提供 lexical rerank skeleton，输出排序结果与 provider metadata
- 在 provider 响应里补充 provider 状态、queue 饱和度与 runtime budget 快照
- 启动后向 `agentd` 自注册并汇报 provider health

## 当前边界

- 不自己实现推理 backend
- embedding / rerank 仍是 skeleton，不是正式模型推理 backend
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
