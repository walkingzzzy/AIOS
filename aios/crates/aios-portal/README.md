# aios-portal

`aios-portal` 是 AIOS 当前 Phase 3 的 portal handle shared library。

## 角色

它负责：

- 发放受控对象句柄
- 查找句柄
- 撤销句柄
- 列出句柄
- 在 state dir 中维护句柄生命周期

当前实现重点仍是**句柄层**，但仓库内已补 `portal-chooser` shell surface prototype，并已把 chooser request metadata、requested kind ranking、confirm/cancel/retry 状态流接到 shell panel、GTK host 与 standalone chooser host；chooser 现在也会显示 export/screen handle 细节，并支持 approval-aware route。

## 当前实现范围

已实现：

- 通用 handle issue / lookup / revoke / list
- `file_handle` / `directory_handle` / `window_handle` / `screen_share_handle` / `export_target_handle` / `contact_ref` / `remote_account_ref` kind 校验
- file / directory handle 的真实 filesystem target 校验、非 symlink 约束与 scope 元数据富化（`display_name` / `target_kind` / `availability` / `target_parent` / `target_hash`）
- expiry 到期失效
- revocation state 持久化
- lookup / revoke 的 `session_id` / `user_id` 绑定校验
- `sessiond` handle binding
- `agentd` file / export target / screen share handle flow
- `portal-chooser` standalone chooser host
- chooser request audit tag / approval ref 展示
- export target / screen share handle detail summary
- scope-aware `screen_capture_portal_provider` request bridge
- `scripts/test-portal-file-handle-smoke.py` / `scripts/test-provider-fs-smoke.py` / `scripts/test-ipc-smoke.py` 已覆盖 file/directory handle 的签发、绑定、消费与撤销路径

未实现：

- native desktop portal / PipeWire worker 深度集成
- 与真实 approval/audit service 的更深度联调

## 存储模型

默认由调用方传入 `state_dir`，目录下当前使用：

- `handles/`：portal handle JSON records

## 相关契约

- `aios/crates/aios-contracts/src/lib.rs`
- `aios/sdk/schemas/portal-handle.schema.json`
- `docs/system-development/14-provider-registry-与-portal-规范.md`
