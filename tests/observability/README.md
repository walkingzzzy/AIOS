# Observability Validation

此目录保存 AIOS observability / validation / release gate 的最小测试说明。

当前内容：

- `test-plan.md`
- `scripts/test-observability-schema-smoke.py`
- `scripts/test-validation-matrix-smoke.py`
- `scripts/build-observability-correlation-report.py`
- `scripts/test-observability-correlation-smoke.py`
- `scripts/build-cross-service-health-report.py`
- `scripts/test-cross-service-health-smoke.py`
- `scripts/test-policyd-audit-store-smoke.py`
- `scripts/check-release-gate.py`
- `validation-matrix.yaml`

当前范围：

- 校验 `aios/observability/schemas/*.json` 的 JSON Schema 合法性
- 校验 observability sample payload 与 schema 对齐
- 校验 validation matrix 对 `owner / command / artifact / triage` 的映射是 machine-readable 且与 system validation report 对齐
- 校验 `system-delivery-validation-report`、`system-delivery-validation-evidence-index`、`full-regression-report`、`release-gate-report` 的 machine-readable 形状
- 校验 `sessiond` / `policyd` / `runtimed` 的证据可 stitch 成 cross-service correlation report
- 校验 control plane / device / update / shell provider / compat provider / delivery manifest 可收敛成统一 cross-service health report
- 校验 `policyd` audit store 的 retained segment rotation / pruning / query 行为
- 校验发布 gate 会对 blocking checks 返回正确退出码
