# AIOS Provider Filesystem Smoke Test Plan

## 范围

本计划验证 `aios-system-files-provider` 的最小执行闭环。

## 覆盖服务

- `sessiond`
- `policyd`
- `system-files-provider`

## 核心断言

### 1. 服务启动

- 三个服务都能创建自己的 UDS socket
- `system.health.get` 返回 `ready`

### 2. Portal handle 绑定

- `portal.handle.issue` 能签发 `file_handle`
- `portal.handle.issue` 能签发 `directory_handle`
- `portal.handle.lookup` 对错误 `session_id` / `user_id` 返回空结果
- handle scope 中包含 `target_hash`
- file / directory handle 只接受真实存在且非 symlink 的目标

### 3. `provider.fs.open`

- 文件 handle 能返回 `content_preview`
- 文件结果保留 `target_hash`
- 目录 handle 能返回 `entries[]`
- provider 拒绝无效 token / revocation / 过期 handle
- provider 并发预算耗尽时返回明确拒绝

### 4. `system.file.bulk_delete`

- `policy.evaluate` 对该 capability 返回 `approval_ref`
- `approval.resolve` 批准后才能 `policy.token.issue`
- 目录删除缺少 `allow_directory_delete` / `allow_recursive` 约束时会被拒绝
- `max_affected_paths` 过小时目录删除会被拒绝
- `dry_run=true` 返回 `would-delete`
- recursive 删除能覆盖嵌套路径
- 真删后目标路径消失

## 运行入口

```bash
cargo build -p aios-sessiond -p aios-policyd -p aios-system-files-provider
scripts/test-provider-fs-smoke.py --bin-dir aios/target/debug
```

## 后续扩展

1. 与 `provider-registry-test-plan.md` 共同维护 descriptor discovery / lifecycle 覆盖
2. 增加 dangerous-path / symlink / expired-handle 负向用例
3. 增加 policy constraints 对 delete 范围的约束验证
4. 增加 provider registry self-registration 验证
