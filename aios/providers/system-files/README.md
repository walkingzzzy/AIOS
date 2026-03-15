# aios-system-files-provider

## 1. 角色

`aios-system-files-provider` 是 AIOS 第一批真实 first-party provider runtime。
它负责把 `provider.fs.open` 与 `system.file.bulk_delete` 从 descriptor fixture 变成可执行的本地 UDS worker。

核心职责：

- 通过 `sessiond` 解析 context-bound `portal.handle.lookup`
- 通过 `policyd` 校验 execution token
- 对 file / directory handle 执行受限本地文件读取
- 对审批后的 file / directory handle 执行受限删除
- 输出可审计的目标路径、`target_hash`、预览与删除影响范围

## 2. 不负责什么

- 不负责 chooser UI
- 不负责 provider registry 服务本身的生命周期管理；仅负责 provider-side 自注册与 health report
- 不负责审批决策本身
- 不负责广泛文件系统遍历或 wildcard 搜索
- 不绕过 portal handle 与 execution token

## 3. RPC 方法

- `system.health.get`
- `provider.fs.open`
- `system.file.bulk_delete`

### `provider.fs.open`

输入：

- `handle_id`
- `execution_token`
- `include_content`
- `max_bytes`
- `max_entries`

行为：

- 仅接受 `file_handle` / `directory_handle`
- 校验 token 的 `user_id` / `session_id` / `capability_id`
- 通过 `policy.token.verify` 绑定 `target_hash`
- 文件返回内容预览；目录返回子项列表

### `system.file.bulk_delete`

输入：

- `handle_id`
- `execution_token`
- `recursive`
- `dry_run`

行为：

- 仅接受已批准后签发的本地 execution token
- 阻止删除 `/`、用户 home 与系统关键根目录
- 阻止 symlink 删除
- dry-run 返回受影响路径列表
- 真删只对 portal handle 所指向的单个目标生效

## 4. 推荐技术路线

- 语言：Rust
- async runtime：Tokio
- IPC：UDS + JSON-RPC
- 依赖服务：`sessiond`、`policyd`
- 安全边界：portal handle + execution token + dangerous-path guard

## 5. 当前状态

- 仓库状态：`In Progress`
- 已有：真实 provider binary、config、RPC router、portal/token 校验、文件预览、recursive delete dry-run、schema-aligned provider audit sink、provider lifecycle observability 导出、provider → agentd registry health report 绑定、provider registry 自注册、后台 registry recovery sync、并发预算守卫、基于 token constraints 的目录删除约束、context-bound portal lookup、unit test skeleton、`scripts/test-provider-fs-smoke.py`、`scripts/test-provider-startup-edge-smoke.py`、`scripts/test-provider-registry-recovery-smoke.py` 与 `scripts/test-ipc-smoke.py` 的端到端集成验证
- 缺失：更多 chooser / export target 联调、跨 provider 的统一接入说明与更广覆盖的 registry/provider integration evidence

## 6. 目录结构

```text
providers/system-files/
├── Cargo.toml
├── README.md
├── service.yaml
├── src/
│   ├── main.rs
│   ├── config.rs
│   ├── clients.rs
│   ├── scope.rs
│   ├── ops.rs
│   └── rpc.rs
└── units/
    └── aios-system-files-provider.service
```

## 7. 运行示例

```bash
cargo build -p aios-system-files-provider
scripts/test-provider-fs-smoke.py --bin-dir aios/target/debug
```

## 8. 下一步

1. 把 provider runtime 接入 registry integration tests
2. 为 bulk delete 增加更细粒度 policy constraints
3. 输出 first-party provider 接入说明，冻结 lifecycle / health / observability 口径
4. 与 chooser surface 联调 directory / export target flow
