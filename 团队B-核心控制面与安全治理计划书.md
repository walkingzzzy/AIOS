# 团队B-核心控制面与安全治理计划书

**更新日期**: 2026-03-13

## 1. 团队使命

团队 B 负责 AIOS 的核心控制面与安全治理闭环，覆盖：

- `agentd`
- `sessiond`
- `policyd`
- `runtimed`
- 本地 IPC / schema / contract / shared core

团队目标不是继续堆 skeleton，而是把当前已经存在的最小可运行闭环推进到“接口稳定、失败可恢复、行为可审计、测试可持续”的系统中枢。

---

## 2. 当前未完成部分

### 2.1 基于仓库事实保留的剩余缺口

根据 `docs/IMPLEMENTATION_PROGRESS.md`、`docs/system-development/19-实现映射与当前进度.md`、`docs/system-development/20-核心服务详细设计.md`，团队 B 当前只保留下列未完成工作：

1. 核心契约虽已形成，但版本冻结、兼容性规则、变更准入机制仍未正式收口
2. `aios-rpc` 与跨服务 shared error code 仍未真正统一，config / schema validation loader 也未完全工程化
3. `sessiond` 的 task event 查询面、semantic memory surface、恢复证据链仍未完全成型
4. `policyd` 的 high-risk approval 仍缺批准、拒绝、超时、撤销 / 过期的完整治理闭环
5. `runtimed` 的 observability export、统一证据归档、budget enforcement 与 backend freeze 口径仍需继续收敛
6. 团队 B 现有单测与 smoke 仍偏分散，尚未收敛成团队 A / C / D / E 可持续消费的 control-plane harness

---

## 3. 保留的未完成范围

### 3.1 唯一负责目录

- `aios/services/agentd/`
- `aios/services/sessiond/`
- `aios/services/policyd/`
- `aios/services/runtimed/`
- `aios/crates/aios-core/`
- `aios/crates/aios-contracts/`
- `aios/crates/aios-rpc/`
- `aios/policy/`

### 3.2 当前仅保留的未完成能力

- 核心 RPC / schema / shared error model 冻结
- `agentd + sessiond` 的恢复、query、memory 证据收敛
- `policyd` 审批状态机与 audit query 闭环
- `runtimed` 的 route / budget / observability / backend contract 收敛
- 面向下游团队与团队 E 的持续化 control-plane harness

---

## 4. 未完成工作包

### WP1：核心契约与共享基线冻结

**剩余任务**

- 输出核心 contract 版本清单与兼容性规则
- 收敛 shared error code、schema / config validation loader 与变更记录机制
- 明确 health、route、token、approval、taint 等跨团队关键字段

**完成标志**

- 团队 A / C / D / E 使用的核心字段在当前里程碑内不发生无说明破坏性变更
- 新增跨服务 RPC 必须附带 schema 或结构定义
- `aios-contracts` 与 `aios-rpc` 拥有最小兼容性测试

### WP2：`agentd + sessiond` 执行链路收敛

**剩余任务**

- 补齐 task event query、semantic memory surface、恢复路径断言
- 强化 plan、task、memory、portal handle、recovery ref 的失败恢复证据
- 把当前联调从人工 smoke 收敛成可持续验证入口

**完成标志**

- `agentd -> sessiond -> policyd -> runtimed` 主执行链路可重复验证
- session / task / recovery 关键对象在服务重启后仍能恢复或给出明确失败状态
- task event 与 recovery 证据可以被查询，而不是只能看日志

### WP3：`policyd` 安全治理闭环

**剩余任务**

- 补齐 high-risk approval 完整状态机
- 收敛 audit query、持久化与恢复证据关联
- 固定 taint、risk、approval、token 之间的可追溯关系

**完成标志**

- 至少覆盖批准、拒绝、超时、撤销 / 过期四类审批路径
- token issue / verify 与 approval 状态保持一致，不允许绕过审批发放高风险 token
- audit 查询结果可定位到审批决策、token、能力风险与恢复证据

### WP4：`runtimed` 路由、预算与证据收敛

**剩余任务**

- 冻结 backend trait / worker contract 正式口径
- 补 route resolve、fallback、timeout、budget reject 的跨服务证据
- 收敛 runtime event、remote audit 与团队 E 所需 evidence 输出

**完成标志**

- `runtime.route.resolve`、`runtime.infer.submit`、`runtime.events.get` 在正常与失败路径都有回归验证
- local CPU / GPU / NPU 与 attested-remote 的降级行为可复现、可解释、可查询
- 后端未就绪时必须显式暴露健康状态，不能伪装成功

### WP5：集成 harness 与 machine-readable 证据持续化

**剩余任务**

- 把团队 B 现有单测与 smoke 收敛成至少一套 control-plane 级联调 harness
- 固定失败注入、审批链、恢复链的 evidence 输出格式
- 让团队 E 可直接归档，不再依赖人工整理

**完成标志**

- 团队 B 的关键服务可在本地一键跑完基础回归
- 证据输出可被团队 E 归档
- 集成 harness 从“一次性脚本”升级为“持续维护资产”

---

## 5. 未完成里程碑

### M1：契约冻结与边界拉齐
- 输出核心 RPC / schema / contract 冻结清单
- 明确 shared error code、health、route、token、approval、taint 结构
- 冻结 `runtimed` backend trait / worker contract

### M2：服务工程化收敛
- `agentd / sessiond / policyd / runtimed` 关键成功路径可持续回归
- config loader / schema validation loader 收敛
- recovery hooks、failure handling、关键 tracing 字段统一

### M3：安全治理可验收
- high-risk approval policy 正式可运行
- audit query、审批关联与恢复证据链正式可运行
- token / approval / taint / audit / recovery evidence 能串成证据链

### M4：跨团队联调封板
- 团队 A / C / D 不再因核心控制面接口频繁返工
- 团队 E 将团队 B 的 smoke / evidence 接入持续验证
- 高影响接口变更转入“先评审、后实现”的治理节奏

---

## 6. 当前验收口径（仅未完成部分）

- 核心契约必须冻结并具备最小兼容性治理，不能继续靠口头同步
- `sessiond`、`policyd`、`runtimed` 的失败路径、query 路径与证据链必须成立
- 审批、token、taint、audit 必须形成完整治理闭环
- 团队 E 必须能持续消费团队 B 输出的 machine-readable 证据

---

## 7. 跨团队输入输出

### 7.1 依赖输入
- 团队 A：`updated` 所需 health、recovery hooks、deployment state 字段要求
- 团队 C：session / policy / approval / registry 用户流需要的接口与状态语义
- 团队 D：provider / device / compat 侧 token、route、descriptor、capability 需求
- 团队 E：证据格式、审计字段、测试门槛与归档约束

### 7.2 对外输出
- 给团队 A：health、policy、recovery hooks、deployment state 契约
- 给团队 C：session、policy、approval、portal handle、registry 稳定接口
- 给团队 D：token verify、route resolve、provider descriptor / capability 契约
- 给团队 E：trace、audit、smoke、contract 证据输出

---

## 8. 不负责内容

- 不负责 shell GUI、chooser GUI、approval panel 的界面实现
- 不负责 image、installer、firmware、recovery 介质本体
- 不负责 `deviced` 原生采集 backend
- 不负责 compat / browser / office worker 本体实现

---

## 9. 防冲突规则

1. 核心接口变更必须先改 schema / contract，再进入实现
2. 不直接修改团队 C 的 shell 组件与团队 D 的 provider 业务实现
3. 审计与证据字段优先与团队 E 对齐，不私自扩 machine-readable 字段
4. 所有跨服务新增 RPC 必须保持向后兼容，或显式提供版本标记
5. 高影响变更优先补 ADR、契约说明或字段对照，再安排联调
