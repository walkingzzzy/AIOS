# AIOS 团队5 Backlog：平台交付与兼容生态团队

## 1. Backlog 目标
将 image/updated/compat/hardware 从当前以 QEMU、baseline bridge、部分脚本和文档规划为主的状态，推进到具备 Tier 1 实机证据、交付闭环和兼容生态正式执行栈的 release-grade 基线。

## 2. P0（第一优先级）

### P0-1 冻结 platform profile / firmware hook / hardware evidence schema
- 范围：`image/`、`services/updated`、`hardware/`
- 交付物：平台 profile、固件 hook 契约、硬件证据结构说明
- 验收标准：团队2/4/5联调时使用同一平台语义和证据格式
- 测试：schema tests、config validation tests
- 风险：平台语义不稳定会导致 runtime、shell、bring-up 验收不一致

### P0-2 冻结 compat worker/result 与 registration 契约
- 范围：`compat/`
- 交付物：browser/office/mcp bridge worker/result 字段、registration 字段说明
- 验收标准：团队1与团队5的治理边界清晰稳定
- 测试：contract compatibility tests
- 风险：兼容桥接与治理接口若不稳，会造成大量重复适配

### P0-3 明确 Tier 1 bring-up 验收基线
- 交付物：验收 checklist、证据模板、release gate 基线
- 验收标准：后续实机 bring-up 可按同一模板提交证据
- 测试：人工演练 + evidence pipeline 校验

## 3. P1（第二优先级）

### P1-1 推进 installer / recovery / rollback 到 Tier 1 实机闭环
- 交付物：安装、首启、恢复、回滚完整流程
- 验收标准：不仅 QEMU 可跑通，Tier 1 实机也可验证
- 测试：boot/recovery/rollback/in-place update tests

### P1-2 将 updated 推进到 vendor-specific firmware hook 与失败注入
- 交付物：更真实的平台 update backend
- 验收标准：可验证 boot-success、rollback、异常恢复路径
- 测试：failure injection tests、firmware hook tests

### P1-3 将 browser compat 推进到正式 bridge
- 交付物：remote/browser bridge 主路径
- 验收标准：不再仅停留在 baseline fetch/文本级能力
- 测试：browser bridge integration tests

### P1-4 将 office compat 推进到 document worker / conversion pipeline
- 交付物：正式文档处理路径
- 验收标准：docx/xlsx/pptx 处理不再仅限基础导出
- 测试：document conversion tests

### P1-5 将 mcp-bridge 推进到 attestation / rotation / revoke / registration 治理闭环
- 交付物：正式 remote provider 治理能力
- 验收标准：control-plane 可对接远端 provider 治理
- 测试：registration governance tests

## 4. P2（第三优先级）

### P2-1 收敛 compat shared audit/query/operator-facing 资产
- 交付物：可复用 audit/query/report 资产
- 验收标准：operator 可长期使用，而不是演示级脚本

### P2-2 加强 nightly / artifact validation / release gate
- 交付物：nightly 校验、工件验证脚本、release gate 集成
- 验收标准：交付链有稳定自动化入口

### P2-3 更新 runbook、release checklist、支持矩阵与实机报告
- 交付物：交付文档、签收材料、支持矩阵更新
- 验收标准：文档与实机证据一致

## 5. 里程碑建议

### M1：平台与治理契约冻结
完成 P0 项，明确平台、证据、compat 治理边界。

### M2：交付与兼容主路径落地
完成 P1-1 ~ P1-5，建立实机交付闭环与正式 compat bridge。

### M3：签收与发布收敛
完成 P2 项，形成 release gate、runbook、签收报告。

## 6. 关键依赖
- 需要团队2提供稳定 runtime profile 与 backend event
- 需要团队1提供 policy verify / token / registration / audit 接口
- 需要团队4提供 recovery/update/operator 展示契约
- 需要团队3提供设备与硬件状态证据输入

## 7. 完成定义（DoD）
1. Tier 1 安装、更新、恢复、回滚有真实证据
2. compat bridge 进入可联调、可验证正式状态
3. updated 覆盖更真实的平台失败路径
4. release gate、runbook、支持矩阵与工件验证齐备

