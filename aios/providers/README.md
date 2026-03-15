# providers/

`providers/` 承载 AIOS 的 first-party provider runtimes。

## 当前原则

- provider 负责最后一跳执行，不负责授权决策
- 所有 provider 都必须消费 portal handle 或 execution token，而不是直接拿广泛权限
- provider 描述符进入 registry，provider worker 保持独立可替换

## 当前状态

- `system-files/`：`In Progress`，已是首个真实 provider runtime
- `device-metadata/`：`In Progress`，已提供 `device.metadata.get` 的真实 worker
- `system-intent/`：`In Progress`，已提供 `system.intent.execute` 的本地控制面规划 worker
- `runtime-local-inference/`：`In Progress`，已提供 `runtime.infer.submit` / `runtime.embed.vectorize` / `runtime.rerank.score` 的 provider-facing façade 与 smoke harness
- 上述四条 first-party provider 现已共享 lifecycle trace / health observability 基线，`system-files` provider audit 也已对齐统一 audit schema；目前四条 first-party provider 已统一补齐 startup-edge 与 registry-recovery lifecycle smoke
- `shell/` 与 `compat/` 侧也已各自落地 `shell.control.local`、`shell.screen-capture.portal`、browser / office / `mcp-bridge` / code-sandbox runtime 与 descriptor；其中 browser / office remote worker 现还可通过 `register-control-plane` 提升为 `attested_remote` provider
- provider fleet 仍远未完成：正式 device worker、更多 bridge provider、以及更广集成证据仍在推进中；browser / office compat remote provider 的 attestation / fleet governance baseline 已有，但离 fleet/control-plane 级完整治理仍有距离

## 技术基线

- 语言：Rust
- IPC：UDS + JSON-RPC
- 编排：descriptor + registry resolve + `policyd` token verify + portal handle binding
- 验证：provider smoke harness + 后续 registry/provider integration tests
