# AIOS 团队3开发工作包：设备与多模态团队

## 1. 团队名称
设备与多模态团队

## 2. 主责范围

### 负责模块
- `aios/services/deviced`
- `aios/providers/device-metadata`
- `services/deviced/runtime/*`
- 与 device capture、support matrix、backend-state 直接相关的文档与测试资产

### 负责什么
1. `deviced` 的 screen / audio / input / camera / ui_tree 正式 backend
2. capture request、retention、normalize、indicator、backend-state 状态链
3. `device-metadata` provider 与 hardware/profile/support matrix 的映射
4. 对 shell 输出稳定的 backend-state / ui-tree / capability 只读模型
5. device 原生 backend、失败路径、长期运行语义的测试与文档

### 不负责什么
- 不负责 shell 中 device-backend-status 的界面实现
- 不负责 runtime 的 GPU/NPU backend
- 不负责 image/update/recovery/bring-up
- 不负责 compat bridge
- 不负责 approval 业务语义本身

## 3. 当前需要完成的核心开发任务
1. 将 `deviced` 从 adapter skeleton 推进到正式 portal / PipeWire / libinput / camera backend。
2. 收敛 `device.capture.*`、`device.state.get`、`device.object.normalize` 的稳定行为。
3. 完成 continuous capture、retention、indicator、backend-state 的状态恢复语义。
4. 完成 `ui_tree` 正式支持路线，并形成 machine-readable support matrix。
5. 将 `device-metadata` provider 与 hardware profile、runtime/backend state 打通。
6. 建立 shell 可直接消费的 backend-state 输出，而不是让 shell 自行推断设备状态。
7. 增加 device integration tests、readiness tests、failure injection tests。
8. 更新支持矩阵、限制说明、backend 能力文档。

## 4. 输入与输出边界

### 主要输入依赖
- 团队1提供 approval metadata / policy 约束字段
- 团队4提供 indicator/backend-status 的展示视图需求
- 团队5提供 hardware profile 与实机验证需求

### 主要输出产物
- 修改 `services/deviced/src/*`
- 修改 `providers/device-metadata/*`
- 新增原生 backend helper、integration tests、readiness/failure tests
- 输出 backend-state schema、support matrix 字段、设备能力文档

## 5. 并行开发约束

### 可独立开发目录
- `services/deviced`
- `providers/device-metadata`

### 需要优先冻结的接口
- `device.capture.*` RPC
- `device.state.get` 响应结构
- backend-state schema
- support matrix 字段
- approval metadata 字段

### 应避免的冲突点
- 团队4不得在 shell 内生成设备 readiness 逻辑
- 团队5不得复制设备证据采集格式
- 团队1不得在控制面重新封装设备 backend 状态语义

## 6. 测试与验收

### 必要测试
- screen/audio/input/camera/backend 集成测试
- capture/retention/state 恢复测试
- `ui_tree` / support matrix 一致性测试
- failure injection 与长时间运行测试

### 验收标准
- 至少形成可验证的原生 backend 路径
- shell 可以消费稳定的设备状态模型
- `device-metadata` 能反映真实后端能力而非静态描述
- 文档中的支持矩阵与实现状态一致

## 7. 优先级
**优先级：高**

### 原因
正式 device backend 是 shell、agent、policy、hardware 验收共同依赖的基础能力，当前也是仓库最明显的缺口之一。

### 阻塞项
- native backend contract 冻结
- backend-state schema 冻结

### 可并行项
- `device-metadata` provider 收敛
- 支持矩阵与文档更新
- readiness / failure / long-run 测试补齐

## 8. 阶段建议

### 第一阶段必须完成
- 冻结 capture RPC、backend-state schema、support matrix 字段
- 明确各模态 backend 主路径

### 第二阶段可并行推进
- 原生 backend 落地
- indicator / retention / backend-state 收敛
- 设备 provider 与 profile 打通

### 第三阶段收敛与验收
- 与 shell / policy / hardware 联调
- 实机与长稳测试
- 文档与支持矩阵同步

