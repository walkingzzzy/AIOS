# shell/components

此目录用于放置 AIOS 壳层中的具体交互组件。

## 规划中的组件

- launcher
- workspace manager
- notification center
- operator audit
- portal chooser
- task surface
- approval panel
- recovery surface
- capture indicators
- device backend status
- settings / diagnostics panel

## 当前状态

- 已有 `launcher/` CLI prototype + `client.py`，并补上 `panel.py` formal panel entrypoint；当前 launcher panel 已支持只读 recent session discovery、suggested launches 与 recent session row actions
- 已有 `notification-center/` CLI prototype + `client.py`（已接 recovery surface file/RPC、indicators、通过 `agent.approval.list` 聚合 approvals、backend health、panel action feed 与 cross-service operator audit summary 汇总），并补上 `panel.py` formal panel entrypoint；当前已支持 `inspect-operator-audit` action 与 operator audit source/issue/task 汇总
- 已有 `operator-audit/` CLI prototype + `client.py`，并补上 `panel.py` formal panel entrypoint；当前可持久显示 `policyd` / `runtimed` / remote bridge / compat shared sink 的 recent records、issue feed、task correlation 与 artifact paths
- 已有 `portal-chooser/` CLI prototype + `client.py`（可读 `agent.portal.handle.list` 或 fixture），并补上 `panel.py` formal panel entrypoint 与 `standalone.py` 独立 chooser host；当前已支持 chooser request metadata、requested kind ranking、handle row selection、confirm/cancel/retry 状态流、approval-aware route、recent event history、`resource unavailable` / `retry_after` 异常提示，以及 export/screen handle 细节展示与 manifest 产物
- 已有 `task-surface/` CLI prototype + `client.py`，并补上 `panel.py` formal panel entrypoint；当前已支持 `agent.task.list` / `agent.task.get` / `agent.task.events.list` / `agent.task.plan.get` / `agent.task.state.update` live 状态、focus task 详情、最近 task lifecycle events，以及主 capability 的 provider route / candidate view
- 已有 `approval-panel/` CLI prototype + `client.py`，并补上 `panel.py` formal panel entrypoint；当前已支持 live `agent.approval.list` / `agent.approval.get` / `agent.approval.create` / `agent.approval.resolve` 与 approval-first route 返回
- 已有 `recovery-surface/` CLI prototype + `client.py`（可读 surface file，缺失时回退 `recovery.surface.get`），并补上 `panel.py` formal panel entrypoint；当前已支持 recovery surface file/RPC fallback、surface-file action fallback 与 update / rollback / bundle action dispatch
- 已有 `capture-indicators/` CLI prototype + `client.py`，并补上 `panel.py` formal panel entrypoint
- 已有 `device-backend-status/` CLI prototype + `client.py`（可显示 backend readiness + adapter path，并支持 attention 过滤），并补上 `panel.py` formal panel entrypoint
- 已有 `shellctl.py` 统一聚合入口与 `panel` 子命令，以及 `scripts/test-shell-panels-smoke.py`、`scripts/test-shellctl-smoke.py`、`scripts/test-shell-live-smoke.py`、`scripts/test-shell-clients-smoke.py`、`scripts/test-shell-control-clients-live-smoke.py`、`scripts/test-shell-session-policy-registry-flow-smoke.py`，覆盖 shell 原型 / client / formal panel 对 live 与 fixture 状态消费
- compositor 级 UI framework 已按 `ADR-0006` 冻结为 Smithay compositor + GTK4/libadwaita panels 路线；Tk host 保留为兼容 fallback

## 下一步

1. 先定义组件边界
2. 明确哪些组件与 compositor 同进程，哪些是独立 shell clients
3. 继续把现有 task / approval / recovery formal panel 从 JSON/text model 推到正式 shell UI，并保持 `shellctl.py` 作为统一聚合层


