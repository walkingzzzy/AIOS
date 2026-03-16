# AIOS 团队5开发工作包：平台交付与兼容生态团队

## 1. 团队名称
平台交付与兼容生态团队

## 2. 主责范围

### 负责模块
- `aios/image/`
- `aios/services/updated`
- `aios/compat/`
- `aios/hardware/`
- 与交付、验证、实机 bring-up、兼容桥接直接相关的脚本、文档与 CI 资产

### 负责什么
1. image / installer / recovery / platform media 交付链
2. `updated` 的 sysupdate / rollback / boot verify / firmware hook / recovery backend
3. browser / office / mcp-bridge / code-sandbox 等 compat 正式 bridge 与治理闭环
4. Tier 1 hardware bring-up、support matrix、boot/rollback/recovery 证据
5. release gate 所需的 nightly、artifact validation、runbook 与签收材料

### 不负责什么
- 不负责 shell GUI 的具体实现
- 不负责 `agentd/sessiond/policyd` 控制面业务语义
- 不负责 `runtimed` 内部 backend 实现
- 不负责 `deviced` 原生 backend 实现

## 3. 当前需要完成的核心开发任务
1. 将 image/installer/recovery 从 QEMU 验证推进到 Tier 1 实机安装、首启、回滚、恢复证据闭环。
2. 将 `updated` 从 generic bridge 推进到 vendor-specific firmware hook、失败注入和 boot-success/rollback 实证。
3. 将 browser compat 从 baseline runtime 推进到正式 remote/browser bridge 能力。
4. 将 office compat 从文本导出或基础处理推进到正式 document worker / conversion pipeline。
5. 将 `mcp-bridge` 推进到 control-plane registration、attestation、rotation、revoke 治理闭环。
6. 将 compat shared audit/query/operator-facing 资产收敛为长期可用交付物。
7. 将硬件 bring-up kit、Tier 1 nomination、support matrix 与真实平台证据绑定。
8. 补齐 image/update/compat/hardware 的 CI、nightly、artifact validation、failure injection。

## 4. 输入与输出边界

### 主要输入依赖
- 团队2提供 platform runtime profile 与 runtime health/event 契约
- 团队1提供 provider registration / policy verify / token / audit/export 接口
- 团队4提供 recovery/update/operator-audit 展示接口需求
- 团队3提供设备与硬件状态模型供平台验证使用

### 主要输出产物
- 修改 `image/*`
- 修改 `services/updated/*`
- 修改 `compat/*`
- 修改 `hardware/*`
- 修改相关 `scripts/*` 与 CI 配置
- 产出 installer/recovery media、Tier 1 bring-up report、rollback evidence、compat bridge tests、release gate artifacts

## 5. 并行开发约束

### 可独立开发目录
- `image/`
- `services/updated`
- `compat/`
- `hardware/`

### 需要优先冻结的接口
- platform profile
- firmware hook contract
- compat worker / result contract
- provider registration fields
- hardware evidence schema

### 应避免的冲突点
- 团队2不应在 `image/` 中分叉 runtime profile 语义
- 团队4不应修改 `updated` 业务逻辑
- 团队1不应重复实现 compat registration 治理
- 团队3不应负责平台层证据汇总逻辑

## 6. 测试与验收

### 必要测试
- installer / recovery / rollback / boot-success 测试
- vendor firmware hook 与 failure injection 测试
- browser / office / mcp bridge 集成测试
- Tier 1 实机 bring-up 与跨重启验证
- nightly artifact validation 与 release gate 验证

### 验收标准
- 形成可审计的 Tier 1 实机安装、升级、回滚、恢复证据
- compat bridge 进入可联调、可验证状态，而非仅 baseline/skeleton
- `updated` 能覆盖更真实的平台与失败路径
- release gate 所需文档、脚本、报告和工件齐备

## 7. 优先级
**优先级：高**

### 原因
当前项目从“原型”走向“可交付系统”的最大阻塞集中在 image/update/hardware/compat bridge，这一组工作决定 release-grade 收敛程度。

### 阻塞项
- Tier 1 实机证据
- firmware hook contract 冻结
- compat registration / worker 契约冻结

### 可并行项
- installer UX 收敛
- audit/report/export 脚本化
- nightly / CI / artifact validation 加强

## 8. 阶段建议

### 第一阶段必须完成
- 冻结 platform profile、firmware hook、compat worker/result、hardware evidence schema
- 明确 Tier 1 bring-up 验收基线

### 第二阶段可并行推进
- image/update/recovery 主实现与实机验证
- compat bridge / document worker / registration 治理收敛
- CI/nightly/artifact validation 补齐

### 第三阶段收敛与验收
- release gate 联合验收
- 实机签收与支持矩阵同步
- runbook、checklist、文档更新

