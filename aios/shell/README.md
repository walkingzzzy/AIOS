# shell/

`shell/` 是 AIOS 的原生系统壳层目录。  
它不等于普通桌面应用，也不等于 legacy 控制台，而是 AIOS 的系统交互入口。

## 1. 负责什么

职责包括：

- AI launcher
- workspace / focus / notification
- task surface / approval UI
- session restore surface
- 多模态交互入口
- 与 portal / provider / policy 的受控交互

## 2. 当前状态

截至 2026-03-14：

- 已有：README、`profiles/`、`components/` 目录、`shellctl.py` 统一壳层聚合入口、launcher / notification center / task surface / approval panel / recovery surface / capture indicators / device backend status / operator audit / portal chooser 的 CLI prototype + client/panel skeleton，以及 `shell_control_provider.py` / `screen_capture_portal_provider.py` / `shell_desktop.py` runtime 与 `shell.control.local` / `shell.screen-capture.portal` provider descriptor；当前又补上了 `runtime/shell_snapshot.py` 共享 snapshot/model 层、`runtime/shell_profile.py` profile 解释层、`runtime/shell_session.py` 正式 session bootstrap、`runtime/shell_desktop_gtk.py` GTK4/libadwaita host、`runtime/shell_panel_bridge_service.py` 常驻 socket bridge，以及 `runtime/shell_panel_clients_gtk.py` 独立 GTK panel clients；`shell/compositor/` 下真实引入 Smithay、已注册最小 `xdg-shell` global、已接上 `wl_shm` 路径，并补上 seat/input capability baseline、nested input event routing baseline（keyboard/pointer/touch 事件已经路由到 Smithay seat/focus handle），panel slot/layout + hit-testing/stacking baseline（按 `app_id/title` 把 toplevel 映射到 launcher / task-surface / approval-panel / notification-center / operator-audit 等已知 slot，以对应 layout origin 渲染，并按 slot layer/z-order 进行焦点选择），以及优先基于 `panel_bridge_socket` 的 panel host bridge（bridge 不可用时回退到 `panel_snapshot_command` / `panel_snapshot_path` 和 `panel_action_command`）；compositor 现在也会给 slot 暴露 reservation / pointer / focus policy，并对 panel-host-only slot 记录 activation telemetry，还可通过 bridge 或 command bridge 把 slot activation 落到真实 shell panel action；本轮又补了结构化 `panel_action_events` telemetry 与可选 `panel_action_log_path` JSONL artifact，让 compositor -> shell panel bridge 不再只有一条 summary 字符串，而 `notification-center` / `shellctl` / `shell_control_provider` 也已能直接消费这条事件流，且 `shell.control.local` 现已把这条 log 正式暴露为只读 `shell.panel-events.list` provider capability；`task-surface` 现在会在 live 模型里同时消费 `task.get` / `task.events.list` / `task.plan.get`，展示 focus task 详情、最近 lifecycle events，以及主 capability 的 provider route / candidate view；`approval-panel` 则继续消费 `policyd approval.list`，二者现已通过 `scripts/test-shell-session-policy-registry-flow-smoke.py` 形成 live `sessiond` / `policyd` / registry UI flow；`device-backend-status` 现在也会同时消费 `device.state.get` 与 `backend-state.json` 里的只读 `ui_tree_snapshot`，`shellctl status` / panel model / live smoke 已覆盖这条链路；新增的 `operator-audit` panel 会持久汇总 `policyd` / `runtimed` / compat shared sink / remote audit 的 issue、recent records、task correlation 与 artifact path，`shell.control.local` / `shellctl control` 也已补 `shell.operator-audit.open` 正式控制面入口；`shellctl control` 现在也能基于 profile 中的 `policyd_socket` / `shell_control_provider_socket` 自动 issue token 并调用 `shell.notification.open` / `shell.window.focus` / `shell.panel-events.list`；`shell_session.py serve --session-backend compositor` 现在也会在 session plan 中显式暴露 `panel_host_bridge`，并在 nested/直接 compositor 启动时自动注入 live panel bridge socket、snapshot command、panel action command 与可选 action log path；GTK formal 路径默认也会优先启动独立 panel clients，而不是单窗口 host；同时 compositor 在 active modal slot 存在时会把焦点/命中重定向回 modal，避免 Linux nested 会话下 workspace/client 意外夺回焦点；在 Linux 环境优先尝试 nested `winit + GLES` renderer/backend 的 compositor baseline；Tk host 仍保留为 fallback；并已有 `scripts/test-shell-panels-smoke.py` / `scripts/test-shellctl-smoke.py` / `scripts/test-shell-live-smoke.py` / `scripts/test-shell-clients-smoke.py` / `scripts/test-shell-control-clients-live-smoke.py` / `scripts/test-shell-chooser-smoke.py` / `scripts/test-shell-provider-smoke.py` / `scripts/test-screen-capture-provider-smoke.py` / `scripts/test-shell-desktop-smoke.py` / `scripts/test-shell-compositor-smoke.py` / `scripts/test-shell-session-policy-registry-flow-smoke.py` harness
- 已冻结：`ADR-0006`，明确采用 Smithay compositor + GTK4/libadwaita panels 的分层路线
- 已补：launcher panel 现在会通过只读 `session.list` + `session.evidence.get` 自发现最近会话，暴露 suggested launches / recent session row actions，并避免 panel 渲染路径通过 `session.resume` 产生副作用
- 已补：跨 surface action route 语义，`notification-center` / `capture-indicators` / `launcher` / `approval-panel` / `portal-chooser` 的关键动作现在会显式返回 `target_component`，GTK host 与 Tk fallback host 都会据此切换到目标 surface；同时新增 `scripts/test-shell-acceptance-smoke.py`、`scripts/test-shell-stability-smoke.py` 与 [ACCEPTANCE.md](./ACCEPTANCE.md) 作为正式验收路径；compositor session summary 现在也会显式暴露 `active_modal_surface_id` / `primary_attention_surface_id` / `last_panel_action_target_component`；`portal-chooser` 也新增了 `standalone.py` 独立 chooser host，可直接展示 request / approval / export / screen handle 细节，并在 export 时输出固定 manifest artifact
- 已补：`screen_capture_portal_provider.py` 现在会消费 `screen_share_handle.scope` 中的 `window_ref` / `display_ref` / `continuous` / `portal_session_ref` / `target_hash` 等元数据，并把 scope-aware `capture_request` 摘要暴露给 smoke / evidence 路径
- 已补：shell snapshot summary 现在会额外暴露 `modal_surface_count` / `attention_surface_count` / `blocked_surface_count` / `focus_policy_counts` / `interaction_mode_counts` / `attention_components` / `blocked_components` / `top_stack_surface`，并新增 `scripts/test-shell-compositor-acceptance-smoke.py` 把 exported shell session artifact 接到 compositor acceptance 路径
- 未有：完整窗口管理、真实 panel 嵌入、以及更完整的 shell role/xdg toplevel policy 组合；当前 renderer/backend 仍是 nested baseline，不是 DRM/KMS 级别完整桌面栈

当前判断：`In Progress`

## 3. 技术方向

- compositor：ADR 已冻结为 Smithay 路线，当前仓库已补 Linux 目标下真实使用 `smithay` 的最小 compositor baseline，已接 `wayland_frontend + xdg-shell + wl_shm`、seat/input capability baseline、nested input event routing baseline、基于 slot 的 panel/workspace layout + hit-testing/stacking baseline，以及通过 `panel_snapshot_path` 或 `panel_snapshot_command` 消费 shell snapshot 的 panel host bridge，并优先尝试 nested `backend_winit + renderer_gl`；非 Linux 目标保留 stub fallback 以保证开发机 smoke 可跑
- 控制面 UI：当前已有 Tk fallback host 和 GTK4/libadwaita host；两者现在都可渲染现有 panel model，并支持 surface 选择、panel action、row action 与 `target_component` 路由切换；依赖缺失时会清晰报错
- 与系统集成：D-Bus、portal、核心本地 IPC

## 4. 子目录目标

- `components/`：launcher、workspace manager、notification、portal chooser、task / approval / recovery surfaces
- `profiles/`：shell profile 与 feature flags
- `shellctl.py`：统一 profile 解析、跨组件状态汇总、panel skeleton 与透传调用入口
- `runtime/`：shell control provider runtime、shared snapshot/profile/session bootstrap 与 host glue
- `compositor/`：Smithay compositor baseline crate

## 5. 下一步

1. 把 `runtime/shell_session.py` 作为正式 session 入口，继续收敛 host/backend 切换
2. 在 GTK host 已接通的 action 回调之上继续补更多 shell flow、panel 嵌入与状态联动
3. 在现有 Smithay nested renderer baseline 上继续补真实 shell role、完整 panel host 嵌入、交互式 stacking 调度与更细的窗口策略

## 6. 当前入口

- 兼容 desktop 入口：`python3 aios/shell/runtime/shell_desktop.py snapshot --json`
- 正式 session 入口：`python3 aios/shell/runtime/shell_session.py plan --json`
- GTK host 入口：`python3 aios/shell/runtime/shell_session.py serve --desktop-host gtk`
- GTK panel clients 入口：`python3 aios/shell/runtime/shell_panel_clients_gtk.py snapshot --json`
- compositor baseline 入口：`cargo run --manifest-path aios/shell/compositor/Cargo.toml -- --config aios/shell/compositor/default-compositor.conf --once`
- shell acceptance smoke：`python3 scripts/test-shell-acceptance-smoke.py`
- shell stability smoke：`python3 scripts/test-shell-stability-smoke.py`
- shell compositor acceptance smoke：`python3 scripts/test-shell-compositor-acceptance-smoke.py`
- standalone chooser host：`python3 aios/shell/components/portal-chooser/standalone.py snapshot --json`
- standalone chooser export：`python3 aios/shell/components/portal-chooser/standalone.py export --output-prefix /tmp/aios-portal-chooser --json`
- shellctl chooser host：`python3 aios/shell/shellctl.py --profile aios/shell/profiles/default-shell-profile.yaml chooser snapshot --json`
- portal flow doc：see [PORTAL_FLOW.md](./PORTAL_FLOW.md)
- shell control provider 调用：`python3 aios/shell/shellctl.py control panel-events --session-id session-1 --task-id task-1 --component approval-panel --json`
- shell snapshot bridge：可在 compositor config 或 `AIOS_SHELL_COMPOSITOR_PANEL_BRIDGE_SOCKET` 中优先提供常驻 panel bridge socket；bridge 不可用时，也可用 `AIOS_SHELL_COMPOSITOR_PANEL_SNAPSHOT_PATH` 提供 `shell_snapshot.py` 导出的 JSON 路径，或用 `panel_snapshot_command` / `AIOS_SHELL_COMPOSITOR_PANEL_SNAPSHOT_COMMAND` 直接拉取 live shell snapshot；`panel_snapshot_refresh_ticks` 用于控制刷新节流；`panel_action_command` / `AIOS_SHELL_COMPOSITOR_PANEL_ACTION_COMMAND` 仍可作为 panel action fallback；`panel_action_log_path` / `AIOS_SHELL_COMPOSITOR_PANEL_ACTION_LOG_PATH` 可选输出结构化 panel action JSONL artifact，同时 session summary 会暴露最近 `panel_action_events`，而 `notification-center` / `shellctl` / shell provider 也可消费这条 log；shell provider 现还提供 `shell.panel-events.list`，可在 provider/token 边界内查询最近 panel activation / dispatch 事件；`shell_session.py plan --json` 会显式暴露 `panel_host_bridge` 与默认 panel clients 启动命令，而 `serve --session-backend compositor` 会自动把 bridge 注入 compositor 与 GTK panel clients 启动环境

## 7. prerequisites

- Tk fallback：标准库 `tkinter`
- GTK host：`PyGObject` + GTK4 + libadwaita typelibs
- compositor baseline：Rust toolchain；Linux 目标会编译真实 Smithay path，并优先尝试 nested `winit + GLES` backend；无显示环境下会保留 frontend-only fallback 以避免 smoke 直接失败；当前 crate 为 standalone manifest，不改 `aios/Cargo.toml`
