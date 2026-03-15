# Observability Field Mapping

`FIELD_MAPPING.md` 冻结团队 A/B/C/D 与团队 E 共用的 observability 关联字段，避免 schema、exporter、report builder 和发布文档继续各自定义引用口径。

## 1. 关联字段定义

| Field | 含义 | 典型来源 | 使用规则 |
|-------|------|----------|----------|
| `session_id` | 用户会话主键 | `sessiond`、shell session、control plane report | 仅在会话相关证据中填写；跨服务 correlation 的顶层主关联键 |
| `task_id` | 任务 / intent 执行主键 | `sessiond`、`policyd`、`runtimed` | 与 `session_id` 成对使用；无任务上下文时不要伪造 |
| `provider_id` | provider / compat / runtime backend 标识 | provider registry、shell/provider health、compat runtime | 仅对 provider-backed 证据填写 |
| `approval_id` | 审批记录标识 | `policyd` audit / approval 流 | 仅对需要审批链路的审计与追踪事件填写 |
| `update_id` | 更新批次 / 交付批次标识 | `updated`、delivery / recovery exporter | update / recovery / diagnostic 主关联键之一 |
| `boot_id` | 启动实例标识 | boot / recovery / updated exporter | 与 `update_id`、`image_id` 联合定位单次 bring-up |
| `image_id` | 镜像 / 交付 bundle 标识 | delivery manifest `bundle_name`、image / recovery exporter | 交付、QEMU、installer、recovery、hardware evidence 必须优先带上 |
| `artifact_path` | 主 machine-readable artifact 或采集入口路径 | report builder、probe/exporter、manifest / socket / log path | 指向最能复盘该记录的路径；不要同时写多个主路径 |

补充规则：

- control plane 侧统一优先使用 `session_id + task_id`
- delivery / update / recovery 侧统一优先使用 `update_id + boot_id + image_id`
- `provider_id`、`approval_id` 只在语义真实存在时写入，缺失时保持空缺，不做占位
- `artifact_path` 应指向主证据入口；附加证据仍通过 `evidence_paths`、`artifacts[*].path`、`diagnostic_bundles`、`recovery_points` 等数组补充

## 2. Schema / Report 映射

状态说明：

- `required`: 该对象直接要求该字段
- `optional`: 该对象直接接受该字段，但不是必填
- `derived`: 该对象通过嵌套事件、路径集合或聚合结果间接携带
- `n/a`: 当前对象不承载该字段

| Artifact | `session_id` | `task_id` | `provider_id` | `approval_id` | `update_id` | `boot_id` | `image_id` | `artifact_path` | Notes |
|----------|--------------|-----------|---------------|---------------|-------------|-----------|------------|-----------------|-------|
| `audit-event` | required | required | optional | optional | optional | optional | optional | optional | control plane 审计主记录；`audit_id` 是单条记录主键 |
| `trace-event` | optional | optional | optional | optional | optional | optional | optional | optional | runtime / service trace；`event_id` 是单条记录主键 |
| `health-event` | optional | optional | optional | optional | optional | optional | optional | optional | health exporter 统一事件格式；`service_id` 必填 |
| `recovery-evidence` | optional | optional | optional | optional | optional | optional | optional | optional | update / rollback / recovery 主证据；`recovery_id` 是主键 |
| `diagnostic-bundle` | n/a | n/a | n/a | n/a | optional | optional | optional | optional | 当前聚焦 update / boot / image 维度；`bundle_id` 是主键 |
| `validation-report` | n/a | n/a | n/a | n/a | n/a | n/a | n/a | derived | 通过 `json_report`、`markdown_report`、`checks[*].evidence_paths` 关联原始证据 |
| `evidence-index` | n/a | n/a | n/a | n/a | n/a | n/a | n/a | derived | 通过 `report_paths`、`artifacts.*`、`checks[*].evidence_paths` 汇总证据路径 |
| `release-gate-report` | n/a | n/a | n/a | n/a | n/a | n/a | n/a | derived | 通过 `validation_report`、`evidence_index`、`health_report`、`release_checklist` 等路径指向上游产物 |
| `cross-service-correlation-report` | required | required | derived | derived | derived | derived | derived | derived | 顶层用 `session.session_id`、`tasks[*].task_id` 聚合，其余字段保留在嵌入的 audit / runtime / observability records 中 |
| `cross-service-health-report` | derived | derived | derived | derived | derived | derived | derived | derived | `events[*]` 必须是可单独通过 `health-event` schema 的事件，`checks[*].artifact_paths` 与 `summary.artifact_paths` 汇总其路径 |

## 3. 跨团队证据对象映射

| Team | 上游证据 | 规范化对象 | 最低关联键 | 下游消费方 |
|------|----------|------------|------------|------------|
| Team A / Platform | delivery manifest、QEMU boot log、installer / recovery log、updated diagnostic、hardware boot evidence | `health-event`、`diagnostic-bundle`、`recovery-evidence`、`validation-report` / `evidence-index` | `image_id`、`boot_id`、`update_id`、`artifact_path` | `cross-service-health-report`、`release-gate-report`、发布清单 |
| Team B / Control Plane | policy audit、approval 决策、runtime trace、session / task state | `audit-event`、`trace-event`、`cross-service-correlation-report` | `session_id`、`task_id`；按需补 `approval_id`、`provider_id`、`artifact_path` | correlation report、observability sink、治理报告 |
| Team C / Shell | shell session、panel / chooser / notification 证据、shell provider health | `health-event`、`trace-event`、`validation-report` | `session_id`、`artifact_path`；provider-backed 场景补 `provider_id`；任务态场景补 `task_id` | `cross-service-health-report`、validation report、release gate |
| Team D / Device & Compat | `backend-state.json`、readiness matrix、capture / `ui_tree`、compat provider health / worker evidence | `health-event`、`trace-event`、`validation-report` | provider-backed 场景补 `provider_id`，否则至少提供 `artifact_path`；动作级证据补 `session_id` / `task_id` | `cross-service-health-report`、validation report、release gate |
| Team E / Governance | validation matrix、validation report、evidence index、release gate、cross-service reports | machine-readable report / index | `check_id` + `artifact_path`，并继承上游关联键 | CI gate、发布清单、项目层汇报 |

## 4. 变更规则

修改上述任一共享字段时，必须同步更新：

1. `aios/observability/schemas/*.json`
2. `aios/observability/samples/*.json`
3. `aios/crates/aios-core/src/schema.rs` 中的 loader / validator / version tests
4. 相关 exporter / sink / report builder
5. `tests/observability/validation-matrix.yaml`
6. 本文件与 `aios/observability/SCHEMA_VERSIONING.md`

如果某个新对象暂时无法直接承载这些字段，至少要保证它能通过上游 `artifact_path` 或嵌套记录稳定回溯到已有关联键，而不是另起一套命名。
