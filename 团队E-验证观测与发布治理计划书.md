# 团队E-验证观测与发布治理计划书

## 1. 团队使命

团队 E 负责把 AIOS 当前“已有 schema、workflow、validation report、evidence index 与 release gate baseline”的状态，推进到“证据结构统一、验证入口稳定、发布门槛可自动执行”的工程状态。

本团队不是功能实现团队，而是五个团队共享的质量与证据中枢：统一观测模型、回归矩阵、CI gate、artifact 归档、发布阻塞规则与项目汇报口径。

---

## 2. 当前未完成部分

### 2.1 基于仓库事实保留的剩余缺口

根据 `docs/IMPLEMENTATION_PROGRESS.md`、`aios/observability/README.md`、`.github/workflows/aios-ci.yml`、`tests/observability/validation-matrix.yaml`、`docs/RELEASE_CHECKLIST.md` 与 `out/validation/` 现有产物，团队 E 当前只保留下列未完成工作：

1. `aios/observability/` 已具备 schema baseline、共享字段映射、`aios-core::schema` loader / compiled validator / version tests、部分运行时 validation 与 shared sink，但这些能力还没有扩展成覆盖更多服务与证据对象的统一工程化入口
2. 统一 observability sink、cross-service health / correlation / evidence exporter 虽已有基线；control-plane、shell、provider、compat、device、updated 与默认 hardware baseline 的 operator-facing audit evidence export 已补齐，但真实 nominated machine sign-off 与更高保真现场证据还未完全通过同一稳定入口归档
3. CI 虽已有 `validate`、`system-validation`、`nightly-container-delivery` 三层 job，以及 validation report、evidence index、release gate report、validation matrix 等真实产物，但 artifact 命名、失败分流、跨 job 对比与 retention 策略仍未完全统一
4. `tests/observability/validation-matrix.yaml` 已固化 owner / command / artifact / failure symptom / triage 映射，但仍需继续覆盖更多能力域，并把 local gate、CI gate、nightly gate 的边界收敛为统一治理口径
5. `docs/RELEASE_CHECKLIST.md` 与 release-gate report 已形成 machine-readable baseline，但发布门槛仍未完全自动阻塞化，项目层汇报字段也还没有完全统一

---

## 3. 保留的未完成范围

### 3.1 唯一负责目录
- `aios/observability/`
- `tests/`
- `.github/workflows/`
- `docs/IMPLEMENTATION_PROGRESS.md`
- `docs/RELEASE_CHECKLIST.md`
- 发布 / 验证相关根文档与报告模板

### 3.2 当前仅保留的未完成能力
- 共享 schema loader / runtime validation / 版本迁移在更多服务与 evidence 对象上的收口
- 统一 observability sink 与 cross-service exporter 向更多真实现场证据与 nominated machine sign-off 侧继续扩展
- 回归矩阵、owner、artifact、triage 对应表在更多能力域上的固化
- CI gate、artifact 命名、失败分流与 retention 策略统一
- release checklist 自动阻塞化与五团队统一验收口径收敛

---

## 4. 未完成工作包

### WP1：观测 schema 平台扩展收口
**剩余任务**
- 在现有 schema baseline、loader、compiled validator、version tests 基础上，继续把 shared schema loader / runtime validation 扩展到更多服务与 evidence 对象
- 定义 schema migration strategy，明确版本升级、兼容与废弃路径
- 冻结 audit、trace、health、recovery、validation、release-gate、correlation 的统一关联键
- 继续维护 schema 与各团队证据对象之间的字段映射表，避免不同模块继续漂移

**完成标志**
- schema 不再只是 observability 域局部可用，而能作为跨团队统一入口持续消费
- 团队 A/B/C/D 产出的关键 evidence 都能通过统一 schema 路径校验
- `validation report`、`evidence index`、`release-gate report`、`cross-service correlation report` 的关联字段一致
- schema 版本变更具备兼容检查与升级说明，不再依赖人工口头约定

### WP2：统一事件汇聚与 exporter 收口
**剩余任务**
- 在现有共享 `observability.jsonl` sink 基础上，把更多服务接入统一 sink，而不只停留在 control-plane 与 device / update 主链
- 在已覆盖 control-plane、shell、provider、compat、device、updated 与默认 hardware baseline 的 audit evidence export 基础上，继续把真实实机 sign-off、bring-up 与现场证据并入统一入口，并与 cross-service health / correlation exporter 统一收口
- 收敛 evidence index 生成链路，避免各团队分别输出无法关联的 artifact
- 补齐 exporter 缺失、字段不完整、事件延迟或缺失时的降级与告警样本

**完成标志**
- 团队 A/B/C/D 的关键 evidence 能通过统一 sink / exporter 路径被稳定归档
- health event、recovery evidence、validation report、artifact index 之间能稳定交叉引用
- 跨服务 correlation 报告不再依赖人工补字段
- 团队 E 能对“事件缺失 / 证据断链 / exporter 异常”输出结构化失败结果

### WP3：回归矩阵与验证入口治理
**剩余任务**
- 在现有 `validation-matrix.yaml` 基础上，继续覆盖 shell、provider、compat、hardware、release governance 等关键能力域
- 区分提交 gate、系统 gate、夜间 gate，避免重复执行与责任不清
- 收敛 local gate 与 CI gate 的最小必跑集合，明确 blocker 与 nightly-only 边界
- 给五个团队补齐失败排障说明与 artifact 查找路径

**完成标志**
- control plane、shell、provider、device、compat、image / recovery / update、hardware evidence 七类能力域都有明确回归入口
- 每个关键验证入口都能对应 owner、command、artifact、triage 路径
- `tests/`、workflow、validation report 三者之间的映射稳定
- 新增或变更验证入口时能同步进入统一矩阵，而不是散落在脚本和文档里

### WP4：CI gate、artifact 治理与发布阻塞收口
**剩余任务**
- 统一 `.github/workflows/aios-ci.yml` 中各 job 的 artifact 命名、上传目录、失败分流与 retention 规则
- 收敛 system validation、release gate、hardware validation、observability schema validation 的报告形状
- 把 `docs/RELEASE_CHECKLIST.md` 从人工 checklist 进一步推进到自动阻塞依据
- 定义 release blocker 规则，覆盖 boot / image、installer / recovery、shell / provider / device / runtime 主路径、observability evidence 缺失等关键失败场景
- 将 `docs/IMPLEMENTATION_PROGRESS.md`、validation report、evidence index、release gate report 的项目层汇报字段统一

**完成标志**
- CI 三层 gate 的 artifact 输出结构一致，成功与失败场景都能稳定保留足够证据
- release checklist 能消费 machine-readable gate 结果并对不满足条件的发布形成明确阻塞
- 项目层周报 / 阶段汇报 / 发布验收使用同一套 evidence 字段与质量结论
- artifact 命名、保留周期、失败分流策略固定，排障不再依赖人工逐次解释

---

## 5. 未完成里程碑

### M1：schema 平台可扩展可执行
- shared loader、runtime validation、version tests、migration strategy 形成闭环
- 关键 evidence 对象字段冻结并可统一校验
- 跨团队字段映射表可持续维护

### M2：事件汇聚与回归矩阵稳定
- 统一 event sink / health exporter 可持续输出
- evidence index 与 correlation / health 报告形成稳定链路
- 回归矩阵覆盖关键能力域并可用于日常 triage

### M3：CI 与 artifact 治理收口
- validate / system-validation / nightly 三层 gate 输出结构统一
- artifact 命名、失败分流、retention 规则固定
- validation report 与 release-gate report 形状一致且可追溯到原始入口

### M4：发布阻塞正式生效
- release checklist 能自动消费 gate 结果并形成 blocker
- 五团队阶段汇报统一使用同一证据口径
- 项目层发布决策可直接依赖 machine-readable report 与 evidence index

---

## 6. 当前验收口径（仅未完成部分）

- 团队 E 不能再重复建设新的验证体系，必须在已有 schema、workflow、matrix、report baseline 上做收口
- 不能再把 observability 写成“只有几个 schema 文件”；当前剩余工作是把已有基线扩展为跨团队统一入口
- 团队 A/B/C/D 的关键 evidence 必须能通过统一 sink / exporter / index 归档与关联
- CI 与 release checklist 必须能对关键失败场景产生明确阻塞，而不只是输出说明文档
- 回归矩阵必须能把命令、owner、artifact、failure symptom、triage 路径稳定关联起来

---

## 7. 跨团队输入输出

### 7.1 依赖输入
- 团队 A：image / firstboot / installer / recovery / update 证据，QEMU 与实机 bring-up 日志，hardware validation 产物
- 团队 B：audit / trace / approval / token / route 契约，核心服务 integration 与 observability 输出
- 团队 C：shell session、chooser、panel、notification、approval UI artifact 与 shell smoke / snapshot 证据
- 团队 D：`backend-state.json`、readiness matrix、capture / `ui_tree` / provider health / compat / sandbox 执行证据

### 7.2 对外输出
- 给所有团队：schema、字段约定、回归矩阵、gate 规则、artifact 命名规范、验收模板
- 给项目层：validation report、evidence index、release blocker 列表、里程碑质量状态、风险清单

---

## 8. 不负责内容

- 不承担 `agentd`、`sessiond`、`policyd`、`runtimed`、`deviced`、`updated` 的主功能实现
- 不替代团队 C 或团队 D 编写正式 shell / provider / device / compat 主逻辑
- 不独立负责 Tier 1 实机 bring-up 执行，只负责证据模型、验证口径和发布阻塞治理
- 不在未协商的情况下长期接管其他团队目录

---

## 9. 防冲突规则

1. 团队 E 优先通过 schema、test plan、workflow、报告模板影响其他团队，而不是直接侵入功能实现
2. 需要修改验证脚本或 workflow 时，优先保持“只加证据采集 / gate / 报告，不改业务语义”
3. 所有 artifact、report、index 优先 machine-readable，避免手工汇报口径漂移
4. 发布门槛、阻塞项、评分卡调整必须经过五团队同步评审
5. 团队 E 发现功能缺陷时，应优先提交 blocker、回归用例或最小修复建议，而不是越权接管模块开发
