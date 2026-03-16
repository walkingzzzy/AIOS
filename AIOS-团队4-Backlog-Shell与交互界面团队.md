# AIOS 团队4 Backlog：Shell 与交互界面团队

## 1. Backlog 目标
将 shell/compositor 从当前 placeholder-heavy、panel skeleton、多 host 并存但流程未完全收敛的状态，推进到正式可交互的 AI Shell 界面层。

## 2. P0（第一优先级）

### P0-1 冻结 shell 输入 view model
- 范围：`shell/components/*`、`shell/runtime/*`
- 交付物：task/approval/device/recovery/operator-audit 的只读 view model
- 验收标准：团队1/3/5 提供的数据模型稳定，shell 不再反复改字段
- 测试：view model schema tests
- 风险：输入不稳会导致 UI 返工频繁

### P0-2 冻结 panel action event / snapshot 契约
- 交付物：panel 输入输出事件规范
- 验收标准：panel host 与业务方交互清晰，不再混杂业务逻辑
- 测试：panel event compatibility tests

### P0-3 明确 compositor 与 panel embedding 边界
- 交付物：embedding contract、surface 生命周期说明
- 验收标准：placeholder-only 不再作为默认主路径
- 测试：embedding smoke tests

## 3. P1（第二优先级）

### P1-1 将 compositor 的 placeholder-only surface 推进到真实 embedding
- 交付物：panel 嵌入与窗口展示主路径
- 验收标准：launcher/task/approval/recovery 等界面可作为正式 surface 工作
- 测试：compositor embedding tests

### P1-2 完成 shell role / xdg toplevel policy / stacking / focus
- 交付物：窗口策略实现
- 验收标准：窗口管理不再主要依赖 placeholder 流程
- 测试：focus/stacking tests

### P1-3 正式化 task / approval / portal chooser / recovery GUI
- 交付物：完整用户交互流程
- 验收标准：关键用户流程可闭环演示
- 测试：interactive flow tests

### P1-4 收敛 GTK host / compositor host / fallback host 切换逻辑
- 交付物：统一 session 入口与 host 选择逻辑
- 验收标准：不同 host 模式行为清晰一致
- 测试：host switching tests

## 4. P2（第三优先级）

### P2-1 接通 operator-audit / device-backend-status / notification-center 正式界面
- 交付物：长期可用的操作面板
- 验收标准：不再只是 JSON/text 占位展示
- 测试：operator GUI tests

### P2-2 建立 shell acceptance / stability / nested compositor CI
- 交付物：验收测试矩阵与 CI 项
- 验收标准：shell 有稳定独立的测试入口
- 测试：acceptance tests、stability tests

### P2-3 更新 README、交互说明、运行说明
- 交付物：文档与示例
- 验收标准：文档可指导联调与演示

## 5. 里程碑建议

### M1：模型与契约冻结
完成 P0 项，形成 shell 稳定输入输出边界。

### M2：主交互流程落地
完成 P1-1 ~ P1-4，形成正式 GUI 主路径。

### M3：收敛与验收
完成 P2 项，进入 acceptance、stability、CI 收敛阶段。

## 6. 关键依赖
- 需要团队1提供稳定 task/approval/audit/portal 数据模型
- 需要团队3提供 backend-state/device status 输入
- 需要团队5提供 recovery/update/operator-facing 展示契约

## 7. 完成定义（DoD）
1. compositor 不再以 placeholder-only 作为主要路径
2. 关键面板具备正式 GUI 与交互流程
3. shell 具有独立 acceptance/stability/CI 资产
4. 文档、交互模型与实现状态一致

