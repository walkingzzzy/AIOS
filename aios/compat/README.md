# compat/

`compat/` 是 AIOS 的兼容与桥接层。  
它是正式能力域，但不是系统本体，也不是权限豁免层。

## 1. 负责什么

兼容层用于：

- 浏览器桥接
- Office 桥接
- MCP / A2A / API bridge
- 代码沙箱
- GUI automation fallback

## 2. 基本约束

- compat 不是 AIOS 本体
- compat 默认受限运行
- compat 所有能力必须进入 provider registry 与 policy 审批链
- bridge 协议不能替代 core local control plane
- GUI automation 只能作为最后一级 fallback

## 3. 当前状态

截至 2026-03-14：

- 已有：子目录与 README、browser / office / `mcp-bridge` / `code-sandbox` / `audit-query` provider descriptors 与 runtime；browser / office / `mcp-bridge` 已分别补 `compat-browser-fetch-v1`、`compat-office-document-v1`、`compat-mcp-bridge-v1` 结构化 worker/result contract、失败语义与 schema-aligned 本地 JSONL audit envelope，`code-sandbox` 现也已补显式 `worker_contract`、结构化 `compat-sandbox-executor-v1` result protocol、policy-deny/timeout/error 语义与 schema-aligned JSONL audit envelope；本轮进一步把 browser / office / `mcp-bridge` / `code-sandbox` 接进可选 centralized `execution_token` + `policyd` verify 通路与共享 `AIOS_COMPAT_OBSERVABILITY_LOG` sink，并把 session / task / approval / taint 上下文统一写入 result protocol 与 audit 记录；`code-sandbox` 也会在 `bubblewrap` 可用时优先启用 OS 级隔离；`mcp-bridge` 现已补 persistent remote registry、remote auth header strategy 与 target-bound `execution_token` baseline；browser / office 现也已补 remote attestation / fleet governance metadata、control-plane `attested_remote` registration baseline；`compat.audit.query.local` 也已补 saved query / query history / scriptable interactive query surface，并已纳入 compat runtime integration smoke；与此同时 `scripts/build-audit-evidence-report.py` / `scripts/test-audit-evidence-export-smoke.py` 已开始把 shared compat audit sink、centralized-policy 命中数、token-verified 记录与 per-provider timeout/deny 汇总到 operator-facing evidence export，而 shell `operator-audit` panel 也已开始持久显示 compat cross-service audit 关联信息
- 未有：browser / office 真桥接实现、fleet/control-plane 级 remote attestation 与 registration 治理闭环、以及更强的 interactive audit correlation/query workflow

当前判断：`In Progress`

## 4. 子目录说明

- `browser/`：浏览器 provider
- `office/`：Office / document provider
- `mcp-bridge/`：MCP / A2A / API 互操作桥接
- `code-sandbox/`：动态代码受限执行环境
- `audit-query/`：compat shared audit sink 查询与 saved-query runtime

## 5. 下一步

1. 继续把 `compat.audit.query.local` 接进更广的 cross-service correlation / operator UI
2. 把 browser / office skeleton 升级为更真实的 bridge / document worker
3. 继续把 remote auth / registration 从当前 attestation / fleet governance baseline 推进到更正式的 fleet/control-plane 治理闭环
