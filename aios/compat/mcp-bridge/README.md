# mcp-bridge

此目录用于实现 MCP / A2A / API bridge 类型的 compat provider。

## 目标

- 把外部互操作能力接入 provider registry
- 保持低信任 / 中低信任桥接语义
- 把 schema、来源、认证与超时纳入 policy / audit

## 当前状态

- 已有 provider descriptor
- 已有 baseline HTTP bridge runtime
- 已有 `compat-mcp-bridge-v1` 结构化 worker/result contract
- 已有显式 trust policy mode：`permissive` / `allowlist` / `deny`
- 已有结构化失败语义：invalid request / trust deny / timeout / remote unavailable / remote HTTP error
- 已有可选 schema-aligned JSONL audit sink，用于本地 machine-readable evidence
- 已有可选 `execution_token` / `AIOS_COMPAT_POLICYD_SOCKET` centralized policy verify 通路，以及 `AIOS_COMPAT_OBSERVABILITY_LOG` shared audit sink 镜像
- 已有 persistent remote registry：可保存 `provider_ref` / endpoint / capability / auth mode / target hash，并记录 heartbeat / revoke / control-plane provider id
- 已有 remote auth header strategy：`none` / `bearer` / `header` / `execution-token`
- 已有 remote attestation / fleet governance 元数据：可记录 issuer / digest / fleet / governance group / approval ref
- 已有 target-bound `execution_token` remote auth baseline，并把 remote registration 元数据写入 result protocol / audit
- 已有 `compat.mcp.call` / `compat.a2a.forward` 的本地 smoke 覆盖
- 已有 compat runtime smoke 覆盖 manifest / health / registry resolution
- 已有 attestation / fleet 级 remote auth 治理基线
- 已有正式 remote provider registration control-plane integration 基线

## 约束

- bridge 不是 core local IPC
- bridge 不获得授权豁免
- bridge 必须进入 registry、policy、audit
- 当前 baseline 只支持受限 HTTP/HTTPS JSON POST 桥接
- `AIOS_MCP_BRIDGE_TRUST_MODE=permissive` 仅用于过渡基线，默认视为 `degraded`

## 下一步

1. 把 bridge result protocol 继续接进更完整的 policy correlation / operator audit 视图
2. 把当前 control-plane registration 继续接入更完整的 provider routing / release gate evidence
3. 继续把 remote auth 从 baseline 推进到 rotation / revoke / nightly regression 闭环
