# AIOS 团队3 Backlog：设备与多模态团队

## 1. Backlog 目标
将 deviced 从当前 adapter skeleton、缺正式 portal/PipeWire/libinput/camera backend 的状态，推进到可被 shell、policy、hardware 验收共同依赖的正式设备与多模态层。

## 2. P0（第一优先级）

### P0-1 冻结 capture RPC 与 backend-state schema
- 范围：`services/deviced`
- 交付物：`device.capture.*`、`device.state.get`、backend-state 字段定义
- 验收标准：团队1/4/5 可以基于稳定模型联调
- 测试：schema tests、RPC compatibility tests
- 风险：字段频繁变化会导致 shell 与平台验证返工

### P0-2 明确 screen/audio/input/camera 主 backend 路线
- 交付物：后端选型与路径说明
- 验收标准：每种模态有唯一主实现方向，不再并行试错
- 测试：backend bring-up smoke tests
- 风险：模态路径不清会造成重复开发

### P0-3 冻结 support matrix 字段与能力描述
- 交付物：machine-readable support matrix 字段说明
- 验收标准：`device-metadata`、hardware、shell 共用同一能力描述模型
- 测试：matrix consistency tests

## 3. P1（第二优先级）

### P1-1 落地 portal / PipeWire / libinput / camera backend
- 交付物：正式原生 backend
- 验收标准：主要模态可通过正式 backend 获取状态或数据
- 测试：native backend integration tests

### P1-2 收敛 retention / indicator / backend-state 状态恢复语义
- 交付物：状态恢复与长期运行逻辑
- 验收标准：重启或异常后状态可恢复、可查询
- 测试：state recovery tests、long-run tests

### P1-3 完成 `ui_tree` 正式支持路径
- 交付物：ui_tree backend 与文档
- 验收标准：shell 能稳定消费 UI 树或相关可视状态
- 测试：ui_tree tests

### P1-4 打通 `device-metadata` 与 hardware/runtime/profile
- 交付物：动态能力映射
- 验收标准：provider 反映真实 backend 能力，而不是静态描述
- 测试：provider mapping tests

## 4. P2（第三优先级）

### P2-1 补齐 failure injection 与 readiness 测试
- 交付物：失败路径与 readiness 测试资产
- 验收标准：backend 异常、权限不足、设备缺失等场景可验证

### P2-2 更新支持矩阵与限制文档
- 交付物：README、支持矩阵、已知限制说明
- 验收标准：文档与实现状态一致

### P2-3 建立设备验收报告模板
- 交付物：与团队5联动的设备能力验收模板
- 验收标准：实机 bring-up 可复用同一设备能力报告

## 5. 里程碑建议

### M1：接口与矩阵冻结
完成 P0 项，形成稳定设备状态与能力描述模型。

### M2：原生 backend 落地
完成 P1-1 ~ P1-4，设备层进入正式联调阶段。

### M3：测试与签收
完成 P2 项，支撑实机验证与长期运行收敛。

## 6. 关键依赖
- 需要团队1提供 approval metadata/约束字段
- 需要团队4明确 indicator / device-status 视图需求
- 需要团队5提供硬件 bring-up 与实机验证要求

## 7. 完成定义（DoD）
1. 主要模态有正式 backend，而非仅 skeleton
2. shell 可消费稳定 backend-state
3. `device-metadata` 能反映真实设备能力
4. 支持矩阵、测试、文档与实现状态一致

