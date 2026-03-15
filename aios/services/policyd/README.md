# aios-policyd

## 1. 角色

`aios-policyd` 是 AIOS 的治理中枢。

核心职责：

- capability policy
- 风险评估
- taint 处理
- 审批链
- execution token 签发
- 审计事件生成

## 2. 授权原则

`policyd` 是高风险操作的正式裁决者之一。  
以下对象都不是授权根：

- shell
- runtime backend
- compat bridge
- legacy console
- 远端模型输出

## 3. 推荐技术路线

- 语言：Rust
- policy evaluator
- token signer / verifier
- 本地状态存储：SQLite 或受限状态目录
- 通信：UDS + JSON-RPC

## 4. 推荐目录结构

```text
policyd/
├── src/
│   ├── main.rs
│   ├── config.rs
│   ├── rpc.rs
│   ├── evaluator.rs
│   ├── token.rs
│   ├── approval.rs
│   ├── taint.rs
│   ├── audit.rs
│   └── errors.rs
├── rules/
├── keys/
├── tests/
├── service.yaml
└── units/
```

## 5. 当前状态

- 仓库状态：`In Progress`
- 已有：default policy、execution token schema、`src/` 骨架、evaluator / token issue / token verify / audit store / audit query、approval store、`approval.create` / `get` / `list` / `resolve` RPC、`policy.evaluate` 自动生成 `approval_ref`、审批 TTL/超时、批准后撤销、token issuance 与 approval_ref 绑定校验、approval create/resolve 审计事件、capability version metadata（`version` / `supersedes` / `migration_note`）、`system.contract.get` manifest、结构化 RPC error code（含 `invalid_approval_status` / `approval_invalid_transition`）、token key storage hardening（symlink 拒绝、0600/0700 权限收紧、原子写入、health fingerprint），以及 capability catalog、prompt injection baseline 与上游 `taint_summary` propagation
- 已有：audit log 会按 audit-event schema 字段镜像到共享 `observability.jsonl` sink，并保留 `approval_id` / `artifact_path`；`audit.jsonl` 现支持 retained segment rotation、pruning、`audit-index.json` 索引与跨段查询，health 也会暴露 audit index / archive / retention 概览
- 已有：crate 内联单测覆盖 evaluator / approval store / audit / token 关键路径，并新增 RPC 级 high-risk approval matrix，覆盖 `pending` / `approved` / `revoked` / `timed-out`、prompt guard、approval context mismatch、approval `target_hash` / `constraints` mismatch、taint propagation、token gating，以及 high-risk token single-use consume / reuse 拒绝；`scripts/test-policyd-audit-store-smoke.py`、`scripts/test-team-b-control-plane-smoke.py`、`scripts/test-provider-fs-smoke.py`、`scripts/test-screen-capture-provider-smoke.py` 与 `scripts/test-portal-capture-chain-smoke.py` 也已复验 audit store、scoped approval、taint propagation 与高风险 token 消费路径
- 已有：`approval-panel` / `shellctl` / `shell_desktop.py` 与 `scripts/test-shell-session-policy-registry-flow-smoke.py` 已形成正式 shell approval surface baseline
- 已有：approval record 已显式持久化 `target_hash` / `constraints` scope，`policy.token.issue` 会拒绝 scope 漂移并写入 `approval-scope-mismatch` 审计；`scripts/build-audit-evidence-report.py` 现会统一导出 approval scope、target-bound/constraint-bound 统计、`release-signoff` 治理视图与 mismatch 证据，并可自动发现已落盘的 real-machine `hardware-validation-evidence.json`
- 缺失：更广 hardware / real-machine sign-off 现场证据收敛，以及更多高保真现场 evidence export 扩面

## 6. 下一步

1. 扩展 hardware / update 主线 evidence query 与导出面
2. 继续补更多现场 machine-readable 审计字段与 retained artifact 规范
3. 把跨服务 audit correlation 持续收口到统一 operator / recovery 证据视图
