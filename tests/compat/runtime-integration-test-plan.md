# AIOS Compat Runtime Integration Test Plan

## 范围

本计划验证 compat provider descriptor、registry 接入与 runtime skeleton / executor 之间的最小集成闭环。

## 覆盖服务

- `agentd`
- browser compat runtime skeleton
- office compat runtime skeleton
- MCP bridge compat runtime skeleton
- code sandbox executor baseline

## 核心断言

### 1. compat provider 发现

- `agentd` 能通过 registry 发现 4 个 compat provider
- browser / office / mcp-bridge / code-sandbox descriptor 全部进入 discover 结果
- `provider.get_descriptor` 能返回每个 compat provider 的 descriptor

### 2. descriptor 与 runtime manifest 对齐

- runtime manifest 的 `provider_id` 与 descriptor 一致
- runtime manifest 的 `declared_capabilities` 与 descriptor 一致
- runtime `permissions` 输出与 descriptor 内的 `compat_permission_manifest` 一致
- registry 返回的 descriptor 保留 `compat_permission_manifest`
- health 输出带 `provider_id`
- `mcp-bridge` descriptor / manifest / health 对齐 `worker_contract` 与 `result_protocol_schema_ref`
- `browser` / `office` descriptor / manifest / health 也对齐 `worker_contract` 与 `result_protocol_schema_ref`
- `browser` / `office` / `mcp-bridge` 的 runtime manifest 统一声明 `audit-jsonl` implemented method
- 当提供 audit log 环境变量时，`browser` / `office` / `mcp-bridge` health 会返回 `audit_log_configured=true` 与 `audit_log_path`

### 3. capability resolution

- browser / office / bridge / code sandbox 的首个 capability 都能解析到对应 provider
- compat provider 通过 `kind=compat-provider` discover 可见

### 4. code sandbox baseline

- `compat.code.execute` 能执行最小 Python 脚本
- timeout 触发后返回 `exit_code=124`
- timeout payload 标记 `timed_out=true`
- payload 返回 `compat-sandbox-result` 结构化结果协议

## 运行入口

```bash
cargo build -p aios-agentd
scripts/test-compat-runtime-smoke.py --bin-dir aios/target/debug
```

## 后续扩展

1. 在 compat runtime smoke 之外，继续增加 browser / office / bridge 的跨 provider / policy / audit 联调用例
2. 在 Linux 环境补正式 sandbox engine 与真实 bridge worker 联调
3. 将 compat permission manifest 继续接入 policy / approval 与更细粒度的 remote trust filter
4. 将当前本地 JSONL audit sink 继续推进到集中式 audit / query / retention 消费链
