# AIOS 团队4开发工作包：Shell 与交互界面团队

## 1. 团队名称
Shell 与交互界面团队

## 2. 主责范围

### 负责模块
- `aios/shell/` 全目录
- `shell/components/*`
- `shell/runtime/*`
- `shell/compositor/*`
- 与 shell acceptance、GUI smoke、交互模型直接相关的文档与测试资产

### 负责什么
1. GTK host、panel clients、panel bridge、shell session
2. Smithay compositor 从 baseline 到正式 panel embedding / stacking / focus / policy
3. launcher、task、approval、portal chooser、recovery、operator audit、device status 等交互面
4. shell acceptance、stability、nested compositor 测试与 CI 接入

### 不负责什么
- 不负责控制面审批与任务编排业务语义
- 不负责 `deviced` 原生 backend
- 不负责 runtime backend
- 不负责 image/update/hardware bring-up
- 不负责 compat bridge 业务实现

## 3. 当前需要完成的核心开发任务
1. 将 compositor 中的 `placeholder-only` surface 推进到真实 panel embedding。
2. 完成完整 shell role / xdg toplevel policy / stacking / focus / modal routing。
3. 将 task-surface、approval-panel、recovery-surface、portal-chooser 从 skeleton UI 推到正式交互流程。
4. 收敛 GTK host、compositor host、fallback host 的切换逻辑与 session 入口。
5. 接通 operator-audit、device-backend-status、notification-center 的长期可用界面。
6. 为 shell/compositor 增加 acceptance、interactive、stability、nested backend 测试。
7. 将 shell/compositor 纳入更明确的 CI 验证矩阵。
8. 同步更新 shell README、交互说明、测试说明。

## 4. 输入与输出边界

### 主要输入依赖
- 团队1提供 task/approval/portal/audit 的稳定只读接口
- 团队3提供 backend-state、device status、indicator 输入模型
- 团队5提供 recovery/update/operator-facing surface contract

### 主要输出产物
- 修改 `shell/components/*`
- 修改 `shell/runtime/*`
- 修改 `shell/compositor/*`
- 新增 acceptance tests、GUI smoke、embedding tests、stability tests
- 输出稳定的 panel action event / snapshot / view model 文档

## 5. 并行开发约束

### 可独立开发目录
- `shell/`

### 需要优先冻结的接口
- panel snapshot 模型
- panel action event schema
- task / approval / device / recovery 的只读 view model
- compositor 与 panel host 的嵌入契约

### 应避免的冲突点
- 团队1不应在 shell 内写业务逻辑
- 团队3不应在 shell/components 中实现 backend adapter
- 团队5只能定义 recovery surface contract，不能接管 shell host 实现

## 6. 测试与验收

### 必要测试
- compositor embedding 测试
- task / approval / recovery / portal chooser 交互测试
- shell acceptance 与 stability 测试
- nested compositor / panel host CI 验证

### 验收标准
- compositor 不再依赖 placeholder-only 作为主路径
- panel 与交互面可消费稳定只读数据模型
- recovery / approval / task / operator audit 具备正式 GUI 流程
- shell 有独立可复用的 acceptance/CI 资产

## 7. 优先级
**优先级：中高**

### 原因
shell 是用户直接可见层，但它依赖团队1、团队3、团队5先冻结输入模型，因此适合在接口稳定后快速并行推进。

### 阻塞项
- task / approval / device / recovery 视图模型冻结
- compositor/panel embedding 契约冻结

### 可并行项
- GUI 组件完善
- acceptance / stability / CI 补齐
- host 切换与 session 收敛

## 8. 阶段建议

### 第一阶段必须完成
- 冻结 shell 输入模型与 panel/compositor 边界
- 明确各交互面的主流程

### 第二阶段可并行推进
- compositor embedding 与窗口策略实现
- approval/task/recovery/operator-audit/device-status GUI 正式化
- acceptance/CI 建立

### 第三阶段收敛与验收
- 与控制面、设备、平台交付联调
- 用户流程回归
- 文档与测试资产同步

