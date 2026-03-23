# Shell Acceptance

This document defines the repeatable acceptance path for Team C shell and portal work.

## Surface Roles

- `launcher`: shell entry, session resume, task creation
- `task-surface`: workspace task state and plan tracking
- `approval-panel`: approval-first modal surface
- `portal-chooser`: user-selected object and handle confirmation surface
- `notification-center`: cross-surface feed and routing hub
- `recovery-surface`: update and rollback visibility
- `capture-indicators`: visible capture and approval attention strip
- `device-backend-status`: backend readiness and ui-tree diagnostics

## Expected Interaction Semantics

- Modal priority: `approval-panel` > `portal-chooser` > `recovery-surface`
- Cross-surface routing:
  - `notification-center review-approvals` routes to `approval-panel`
  - `notification-center open-recovery` routes to `recovery-surface`
  - `notification-center inspect-device-health` routes to `device-backend-status`
  - `capture-indicators review-approvals` routes to `approval-panel`
  - `launcher create-session` and `launcher resume-session` route to `task-surface`
  - `launcher focus-window` and `launcher restore-window` route to `task-surface`
  - `task-surface restore-window` keeps focus on `task-surface`
  - `approval-panel approve` returns to `task-surface`
  - `portal-chooser confirm-selection` returns to `task-surface`

## Acceptance Flow

1. Start from a formal shell session plan:
   - `python3 aios/shell/runtime/shell_session.py plan --json --profile aios/shell/profiles/formal-shell-profile.yaml`
2. Capture a full shell snapshot or export bundle:
   - `python3 aios/shell/runtime/shell_session.py export --json --profile aios/shell/profiles/formal-shell-profile.yaml --output-prefix ./.tmp/aios-shell-acceptance`
3. Validate chooser-only behavior:
   - `python3 scripts/test-shell-chooser-smoke.py`
   - This path should cover `file_handle`, `directory_handle`, `export_target_handle`, and `screen_share_handle`
4. Validate standalone portal flow artifacts:
   - `python3 scripts/test-portal-flow-smoke.py`
5. Validate desktop host integration:
   - `python3 scripts/test-shell-desktop-smoke.py`
6. Validate formal session bootstrap:
   - `python3 scripts/test-shell-session-smoke.py`
7. Validate end-to-end shell acceptance path:
   - `python3 scripts/test-shell-acceptance-smoke.py`
8. Validate repeated stability path:
   - `python3 scripts/test-shell-stability-smoke.py`
9. Validate compositor acceptance path:
   - `python3 scripts/test-shell-compositor-acceptance-smoke.py`
10. Validate release-profile / non-nested DRM contract path:
   - `python3 scripts/test-shell-release-profile-smoke.py`
   - `python3 aios/shell/runtime/shell_session.py probe --json --profile aios/shell/profiles/release-shell-profile.yaml`
11. Validate Unix-RPC-backed live/provider harnesses when the platform supports them:
   - `python3 scripts/test-shell-live-smoke.py`
   - `python3 scripts/test-shell-provider-smoke.py`
   - `python3 scripts/test-shell-control-clients-live-smoke.py`
   - `python3 scripts/test-shell-session-policy-registry-flow-smoke.py`
   - On non-Unix/Windows developer machines these harnesses intentionally print `skip` and return 0, because the underlying Rust service binaries only expose Unix RPC transports today.

## Validation Boundary

- Nested / Windows / sandboxed runs validate the structured contract for `session_plan`, `panel_host_bridge`, `panel_action_events`, compositor output topology, workspace lifecycle, and minimized-window restore behavior.
- True DRM/KMS closure still requires Linux hardware with libseat/DRM access; the release-profile probe should be used to collect `drm_*`, `output_count`, `renderable_output_count`, and `release_grade_output_status` evidence on that class of machine.
- Shell session / acceptance / stability / compositor acceptance harnesses now default `AIOS_SHELL_SESSION_TEMP_ROOT` to the repository `.tmp/` directory so restricted developer environments can still export stable evidence bundles.

## Evidence Artifacts

The shell acceptance path should produce:

- snapshot JSON
- human-readable snapshot text
- chooser/action state transitions in fixture or panel action results
- chooser standalone snapshot/export artifacts
- chooser standalone export manifest artifact
- chooser recent-event history for confirm / cancel / retry / approval-review paths
- panel action routing results for approval, chooser, recovery, and backend status
- desktop host route evidence for both GTK and Tk fallback helpers
- shell acceptance / stability / compositor acceptance manifest JSON for Team E artifact collection
- compositor JSON summary fields for `active_modal_surface_id`, `primary_attention_surface_id`, and `last_panel_action_target_component`
- compositor output topology fields for `output_count`, `renderable_output_count`, `non_renderable_output_count`, and `release_grade_output_status`
- workspace/window lifecycle fields for `active_workspace_id`, `managed_window_count`, `minimized_window_count`, and `workspace_window_counts`
- compositor acceptance artifacts sourced from exported shell session snapshots, with stable modal/attention evidence across repeated runs

When running with a compositor-backed formal session, the exported snapshot should include:

- `session_plan.entrypoint = formal`
- `session_plan.session_backend = compositor`
- resolved `panel_host_bridge` metadata and panel surface summary
- stable `AIOS_SHELL_SESSION_*` environment contract for compositor, standalone, and fallback host launches

