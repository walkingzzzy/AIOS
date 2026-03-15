# AIOS Portal File/Directory Handle Smoke Test Plan

## 范围

本计划验证 `sessiond` / `aios-portal` / shell chooser prototype 的 file handle 与 directory handle 最小闭环。

## 覆盖服务

- `sessiond`
- `aios-portal`
- `shell portal-chooser prototype`

## 核心断言

### 1. 句柄签发

- `portal.handle.issue` 能签发 `file_handle`
- `portal.handle.issue` 能签发 `directory_handle`
- 句柄 scope 包含 `display_name`、`target_kind`、`target_hash`、`canonical_target`

### 2. 类型与路径校验

- 缺失文件不能被签发成 `file_handle`
- 文件不能被签发成 `directory_handle`
- file/directory handle 只接受真实存在且类型匹配的目标

### 3. 会话与用户绑定

- 同一 `session_id` / `user_id` 能成功 `portal.handle.lookup`
- 跨 session 的 lookup 返回隐藏结果
- 跨 session 的 revoke 返回隐藏结果
- 正确上下文 revoke 会写入 `revoked_at`

### 4. Shell 读取链

- `portal-chooser` prototype 能直接从 live `sessiond` 读取 handles
- live summary 包含 `file_handle` 与 `directory_handle`
- live summary 中两个 handle 都是 selectable

## 运行入口

```bash
cargo build -p aios-sessiond
python3 scripts/test-portal-file-handle-smoke.py --bin-dir aios/target/debug
```
