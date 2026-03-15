# AIOS Observability / Release Gate Test Plan

## 目标

验证团队 E 的 observability schema、cross-service health / correlation、operator-facing audit evidence export、validation report、evidence index、validation matrix、full regression report 与 release gate 已形成最小闭环。

## 当前步骤

1. `python3 scripts/test-observability-schema-smoke.py`
2. `python3 scripts/test-validation-matrix-smoke.py`
3. `python3 scripts/test-high-risk-audit-coverage-smoke.py`
4. `python3 scripts/test-ci-artifact-governance-smoke.py`
5. `python3 scripts/test-policyd-audit-store-smoke.py --bin-dir aios/target/debug`
6. `python3 scripts/test-observability-correlation-smoke.py --bin-dir aios/target/debug`
7. `python3 scripts/test-audit-evidence-export-smoke.py --bin-dir aios/target/debug`
8. `python3 scripts/test-cross-service-health-smoke.py --bin-dir aios/target/debug --delivery-manifest out/aios-system-delivery/manifest.json`
9. `python3 scripts/test-full-regression-suite-smoke.py`
10. `python3 scripts/test-system-delivery-validation.py`
11. `python3 scripts/check-release-gate.py`

## 通过条件

- `aios/observability/schemas/*.json` 都能通过 schema 自校验
- `aios/observability/samples/*.json` 都能通过对应 schema 校验
- `system-delivery-validation-report.json` 符合 validation report schema
- `system-delivery-validation-evidence-index.json` 符合 evidence index schema
- `validation-matrix.yaml` 能稳定映射 `owner / command / artifact / failure symptom / triage`，并覆盖当前 system-validation checks
- `high-risk-audit-coverage-report.json` 能稳定卡住新增 `risk_tier=high` capability 与 Team A `update.apply` / `update.rollback` / `recovery.bundle.export` 的审计覆盖漂移
- `ci-artifact-governance-report.json` 能稳定校验 workflow 中的 artifact 命名、保留期、下载复用与失败保留策略
- `policyd` audit store 能稳定产出 `audit.jsonl` / `audit-index.json` / archived segments，并支持 retention window 内的 query
- `full-regression-report.json` 符合 full regression report schema
- `release-gate-report.json` 符合 release gate schema
- `cross-service-correlation-report.json` 符合 correlation schema，并同时含有 audit / runtime / session 关联证据
- `audit-evidence-report.json` 符合 audit evidence report schema，并同时含有 control-plane + shell / provider / compat / device / updated / hardware / release-signoff 的 approval / token / runtime / observability / audit-store / recovery / release-gate 证据
- `cross-service-health-report.json` 与 `cross-service-health-events.jsonl` 可稳定覆盖 control plane / device / update / shell provider / compat provider / delivery 主线
- `tier1-hardware-evidence-index.json` 默认落到 `out/validation/`，并能被 `scripts/check-release-gate.py` 作为默认 blocking gate 输入消费
- blocking checks 全通过时，`scripts/check-release-gate.py` 返回 0

## 当前未覆盖

- 跨服务真实 audit / trace event sink
- nominated machine 的真实 install / rollback / recovery sign-off 仍需继续补现场 evidence，但 `audit-evidence-report` 已可自动吸收落盘后的 `hardware-validation-evidence.json`
