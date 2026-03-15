# Observability Schema Versioning

## Current Version

当前 observability 版本基线为：

`2026-03-13`

适用对象：

- `audit-event`
- `trace-event`
- `diagnostic-bundle`
- `health-event`
- `recovery-evidence`

## 当前策略

1. schema 文件本身与 sample payload 分离维护
2. 版本字段通过 payload 内的 `schema_version` 表达
3. 对于已版本化的 observability payload：
   - 新写入记录应始终带当前版本
   - runtime validator 允许缺失 `schema_version` 的旧记录继续被读取
   - 一旦带了 `schema_version`，就必须属于当前支持集合
4. `validation-report`、`evidence-index`、`release-gate-report`、`cross-service-correlation-report`、`cross-service-health-report` 当前依赖文件级 schema 约束，暂不引入 payload 内版本字段

## 关联字段冻结

当前跨团队共享的 observability 关联字段冻结为：

- `session_id`
- `task_id`
- `provider_id`
- `approval_id`
- `update_id`
- `boot_id`
- `image_id`
- `artifact_path`

字段语义与各 schema / report 的落点以 `FIELD_MAPPING.md` 为准。变更这些字段时，不仅要修改 schema，还必须同步更新 exporter、report builder、validation matrix 与映射文档。

## 兼容与迁移

版本迁移遵循“先兼容、后切换、最后淘汰”：

1. 增字段：
   - 优先新增可选字段
   - 先更新 schema / sample / loader / report consumer
   - 再推动各服务 exporter 开始写入
2. 字段改名或语义收紧：
   - 保留旧字段至少一个迁移窗口
   - loader / validator 明确接受旧字段的过渡策略
   - correlation / report builder 在迁移期同时消费新旧字段
3. 删除字段：
   - 先在文档中标记 deprecated
   - 至少经过一个稳定版本窗口后再删除
   - 删除前必须补 version tests 和迁移说明

## 版本测试要求

每次 observability schema 变更至少同步更新：

- `aios/observability/schemas/*.json`
- `aios/observability/samples/*.json`
- `aios/crates/aios-core/src/schema.rs` 中的 loader / validator / version tests
- 相关 exporter / sink / report builder
- `aios/observability/FIELD_MAPPING.md`（如果涉及共享关联字段）

## 运行时校验边界

- `aios-core::schema` 负责 schema 解析、路径发现、编译和 payload 校验
- `runtimed` 当前已将统一 observability sink 接到 trace schema 的 runtime validation
- `scripts/build-cross-service-health-report.py` 当前会对导出的每个 `health-event` 与最终 health report 进行 schema 校验
- 其他服务在接入统一 sink 时应复用同一 loader，而不是各自手写版本检查
