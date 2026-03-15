# shell/components

此目录用于放置 AIOS 壳层中的具体交互组件。

## 规划中的组件

- launcher
- workspace manager
- notification center
- portal chooser
- task surface
- approval panel
- recovery surface
- capture indicators
- device backend status
- settings / diagnostics panel

## 当前状态

- 已有 `launcher/` CLI prototype + `client.py`，并补上 `panel.py` formal panel skeleton；当前 launcher panel 已支持只读 recent session discovery、suggested launches 与 recent session row actions
- 已有 `notification-center/` CLI prototype + `client.py`（已接 recovery surface file/RPC、indicators、approvals、backend health 汇总），并补上 `panel.py` formal panel skeleton
- 已有 `portal-chooser/` CLI prototype + `client.py`（可读 `sessiond portal.handle.list` 或 fixture），并补上 `panel.py` formal panel skeleton 与 `standalone.py` 独立 chooser host；当前已支持 chooser request metadata、requested kind ranking、handle row selection、confirm/cancel/retry 状态流、approval-aware route、recent event history、`resource unavailable` / `retry_after` 异常提示，以及 export/screen handle 细节展示与 manifest 产物
- 已有 `task-surface/` CLI prototype + `client.py`，并补上 `panel.py` formal panel skeleton；当前已支持 `task.list` / `task.get` / `task.events.list` / `task.plan.get` live 状态、focus task 详情、最近 task lifecycle events，以及主 capability 的 provider route / candidate view
- 已有 `approval-panel/` CLI prototype + `client.py`，并补上 `panel.py` formal panel skeleton；当前已支持 live `approval.list` / `approval.resolve` 与 approval-first route 返回
- 已有 `recovery-surface/` CLI prototype + `client.py`（可读 surface file，缺失时回退 `recovery.surface.get`），并补上 `panel.py` formal panel skeleton；当前已支持 recovery surface file/RPC fallback 与 update / rollback / bundle action dispatch
- 已有 `capture-indicators/` CLI prototype + `client.py`，并补上 `panel.py` formal panel skeleton
- 已有 `device-backend-status/` CLI prototype + `client.py`（可显示 backend readiness + adapter path，并支持 attention 过滤），并补上 `panel.py` formal panel skeleton
- 已有 `shellctl.py` 统一聚合入口与 `panel` 子命令，以及 `scripts/test-shell-panels-smoke.py`、`scripts/test-shellctl-smoke.py`、`scripts/test-shell-live-smoke.py`、`scripts/test-shell-clients-smoke.py`、`scripts/test-shell-control-clients-live-smoke.py`、`scripts/test-shell-session-policy-registry-flow-smoke.py`，覆盖 shell 原型 / client / panel skeleton 对 live 与 fixture 状态消费
- compositor 级 UI framework 已按 `ADR-0006` 冻结为 Smithay compositor + GTK4/libadwaita panels 路线；Tk host 保留为兼容 fallback

## 下一步

1. 先定义组件边界
2. 明确哪些组件与 compositor 同进程，哪些是独立 shell clients
3. 继续把现有 task / approval / recovery panel skeleton 从 JSON/text model 推到正式 shell UI，并保持 `shellctl.py` 作为统一聚合层
