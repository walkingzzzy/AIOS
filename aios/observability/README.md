# observability/

`observability/` 承载 AIOS 的 audit、trace、health、recovery 与 validation/release-gate 契约。

## 1. 负责什么

此目录存放：

- audit event schema
- trace event schema
- diagnostic bundle schema
- recovery evidence model
- health event schema
- validation report / evidence index / release gate / cross-service health report schema
- cross-service correlation report schema
- shared correlation field mapping (`FIELD_MAPPING.md`)
- schema samples 与 schema smoke 入口
- schema loader / runtime validation / versioning baseline

## 2. 当前状态

截至 2026-03-14：

- 已有：audit / trace / diagnostic / health / recovery schema
- 已有：validation report、evidence index、release gate schema
- 已有：cross-service health report builder / smoke / machine-readable artifact
- 已有：cross-service correlation report builder 与 smoke
- 已有：`audit-evidence-report.schema.json`、`scripts/build-audit-evidence-report.py` 与 `scripts/test-audit-evidence-export-smoke.py`，可把 `sessiond` / `policyd` / `runtimed` 的 approval / token / runtime / observability / audit-store 证据，以及 shell / provider / compat / device / updated / hardware / release-signoff retained evidence，统一导出为 operator-facing report；其中 `release-signoff` 域会自动 stitching `system-delivery-validation`、governance evidence、release gate 与已落盘的 real-machine `hardware-validation-evidence.json`
- 已有：`scripts/build-governance-evidence-index.py`，会从 `tests/observability/validation-matrix.yaml` 汇总治理证据并产出 `out/validation/governance-evidence-index.{json,md}`
- 已有：validation matrix 的 `workflow_jobs` / `coverage_domains` / `status_source` 元数据约束，可把 workflow 对齐、覆盖域和机器可读状态来源一起纳入 smoke
- 已有：`tests/observability/ci-artifact-governance.yaml` 与 `scripts/test-ci-artifact-governance-smoke.py`，可对 CI artifact 的命名、下载复用、失败保留与 retention 规则做 machine-readable 校验
- 已有：`docs/RELEASE_CHECKLIST.md` 中的 machine-readable release rules，`scripts/check-release-gate.py` 会直接消费这些规则并结合 governance evidence index / cross-service health report 做 blocking 判定
- 已有：`scripts/test-observability-schema-smoke.py`
- 已有：`aios-core::schema` 的 observability schema loader / compiled validator / version tests
- 已有：`runtimed` observability sink 的 trace schema runtime validation
- 已有：`sessiond`、`runtimed`、`policyd`、`updated` 与 `deviced` 可共享 `observability.jsonl` sink，会话/任务 trace、runtime trace、policy audit、update/recovery trace 以及 device state / capture trace 会镜像进入该 sink
- 已有：`scripts/build-observability-correlation-report.py`
- 已有：`scripts/build-cross-service-health-report.py`
- 已有：跨团队共享的 observability 字段映射表（`FIELD_MAPPING.md`）
- 已有：`scripts/test-cross-service-health-smoke.py` 会显式校验 `aios-deviced` 与 `aios-updated` 写入共享 sink，确保 cross-service health/exporter 与统一 trace sink 一起回归
- 已有：cross-service health exporter 可消费 `evidence-index` 类型来源，并把 `hardware` 组件纳入统一 health report 覆盖
- 未有：更多服务统一 observability event sink

当前判断：`Schema + governance evidence index + health exporter + artifact governance + multi-domain audit evidence export + default hardware gate baseline + release-signoff stitching landed`

## 3. 原则

- 高风险 capability 必须有 audit event
- 降级 / 回退 / 拒绝必须可追踪
- update / recovery / provider / runtime 事件必须可串联

## 4. 下一步

1. 把更多服务接到统一 observability sink，而不只是 control-plane 与 device/update 主链
2. 在新增 sink / exporter 时遵循 `FIELD_MAPPING.md`，继续收敛 audit / trace / health / recovery / validation 引用字段
3. 在默认 blocking gate 已切到 `out/validation/tier1-hardware-evidence-index.json` 之后，继续补真实 nominated machine sign-off，而不是停留在 synthetic baseline
4. 接 `updated` 的 diagnostic bundle exporter，进一步丰富治理索引与 release gate 输入
5. 继续把 audit evidence report 从当前的 control-plane + shell / provider / compat / device / updated / hardware / release-signoff 覆盖，推进到更多真实 nominated machine sign-off 与现场取证
6. 将其余服务逐步切到共享 schema loader，而不是各自内联校验
