# 团队D-设备ProviderCompat执行计划书

## 1. 团队使命

团队 D 负责 AIOS 的受控执行生态，把“设备能力 + provider 执行 + compat 迁移 + sandbox 隔离”做成真正可运行、可验证、可审计的执行面。

本团队既负责 `deviced` 的原生能力建设，也负责 `providers/` 与 `compat/` 的执行链，但不负责核心策略规则本身，也不负责正式 shell 交互层实现。

---

## 2. 当前未完成部分

### 2.1 基于仓库事实保留的剩余缺口

根据 `docs/IMPLEMENTATION_PROGRESS.md`、`docs/system-development/19-实现映射与当前进度.md`、`aios/services/deviced/README.md`、`aios/providers/README.md`、`aios/compat/README.md`，团队 D 当前只保留下列未完成工作：

1. `deviced` 虽已有 probe、continuous capture、`backend-state.json`、`device.state.get`、`ui_tree_snapshot` 与 readiness matrix，但正式 portal / PipeWire / libinput / camera backend 仍未闭合
2. `device backend status`、indicator、`ui_tree` 的 shell 正式消费面仍需继续收敛，完整 AT-SPI live tree、跨桌面支持矩阵与长期稳定性证据仍未形成
3. `providers/` 虽已有多条 first-party runtime，且 `device.metadata.get` 已成为真实的 readiness 入口；关键 first-party provider 的 lifecycle trace / health observability 已补 shared sink，`system-files` provider audit 也已对齐统一 schema，但 shell / device / compat provider fleet 扩充、跨 provider 接入说明与更广 integration evidence 仍未封板
4. `compat/` 当前仍是 governed fallback / 桥接层：browser / office / MCP bridge / code-sandbox 虽已补 centralized `execution_token` + `policyd` verify、shared audit sink mirror、结构化 worker/result contract 与 schema-aligned audit envelope，且 code sandbox 已支持 `bubblewrap` 可用时优先启用 OS 级隔离，并已能通过 `audit-evidence-report` 导出 shared compat audit sink / centralized-policy 汇总；但仍缺真 bridge implementation、remote auth / registration 与 interactive / persistent audit query surface

---

## 3. 保留的未完成范围

### 3.1 唯一负责目录

- `aios/services/deviced/`
- `aios/providers/`
- `aios/compat/`
- `aios/sdk/`

### 3.2 当前仅保留的未完成能力

- `deviced` 正式 backend 化与 `ui_tree` 收敛
- provider fleet 扩充与 worker lifecycle / observability 收口
- compat 权限声明、bridge loader、正式 worker contract 收敛
- sandbox 正式隔离路线与结构化结果协议
- 团队 C / E 可消费的数据面、证据面与验收面稳定化

---

## 4. 未完成工作包

### WP1：`deviced` 正式 backend 化与 `ui_tree` 收敛

**剩余任务**

- 把 formal native adapter contract 从当前 native evidence / helper / state-bridge 路径继续推进到 release-grade portal / PipeWire backend
- 把 input 主路径从当前 formal native adapter/evidence 路径继续推进到正式 libinput backend，并补齐失败回收
- 把 camera 主路径从 state-file / stub / formal native adapter 路径继续推进到正式 camera backend
- 冻结 `device.state.get`、`backend-state.json`、readiness matrix 的统一字段
- 将 `ui_tree` 从 helper / snapshot 路径推进到完整 AT-SPI live tree、支持矩阵与长期 collector

**完成标志**

- 至少一个正式支持环境上，screen / audio / input / camera / `ui_tree` 都有真实 backend 主路径或明确 `unsupported` 说明
- `device.state.get`、`backend-state.json`、readiness 输出字段一致
- probe failure、backend unavailable、approval missing、continuous collector 中断都有结构化降级结果
- 团队 C 能稳定消费 backend status，团队 E 能稳定归档 capture / readiness evidence

### WP2：provider fleet 与 worker 生命周期稳定化

**剩余任务**

- 围绕 `device.metadata.get` 继续冻结 provider descriptor、health report、worker lifecycle 的统一口径，并把已落地的 shared observability/export 口径推广到更多 provider，避免 provider fleet 各自发明状态
- 补齐 provider 启动失败、健康抖动、禁用 / 恢复、自注册重放的回归验证
- 扩充 shell / device / compat 方向 provider，避免 provider fleet 长期停留在最小集合
- 输出 provider 接入说明，避免每个 worker 各自发明状态与日志格式

**完成标志**

- 关键 first-party provider 均能通过自注册进入 registry，并稳定暴露 descriptor / health
- provider 生命周期至少覆盖 start、ready、degraded、disabled、recovered 五类状态
- descriptor、health、worker runtime manifest 三者字段一致
- agentd / shell / validation harness 消费 provider 状态时不需要硬编码兼容分支
### WP3：compat 权限声明、bridge loader 与 sandbox 闭环

**剩余任务**

- 冻结 compat 权限声明格式，并实现统一 loader / validator / enforcement
- 把 browser / office / MCP bridge 已有的正式 worker/result contract、本地/共享 audit sink，以及 code sandbox 已补的结构化 denial / timeout / schema-aligned audit envelope，继续接进 remote registration / operator audit / trust 闭环
- 补齐 sandbox result return protocol，使 stdout / stderr / artifacts / audit_id / timed_out / degraded 状态结构化返回
- 明确 compat 与 core local control plane 的边界，避免 bridge 越权

**完成标志**

- compat permission manifest 有 schema、loader、validation、runtime enforcement 四件套
- browser / office / bridge / code sandbox 至少形成一条可运行主路径与一组失败 / 降级样本，并能稳定暴露 worker contract / result protocol
- sandbox 返回结构化结果，不再依赖脚本私有格式
- compat 相关能力都能通过 registry discover / resolve / audit 查询，不存在旁路执行

---

## 5. 未完成里程碑

### M1：设备 backend 口径冻结
- `deviced` 输出字段冻结
- readiness / support matrix 可机读
- 至少一条 native backend 主路径可稳定复验

### M2：provider 生命周期稳定
- 关键 first-party provider 自注册、health、disable / enable、recover 行为稳定
- `device-metadata` 成为正式设备 readiness 入口
- compat worker contract 不再停留在 README 级别

### M3：compat 与 sandbox 可验收
- compat 权限声明格式冻结
- browser / office / bridge / code sandbox 至少形成最小主路径
- sandbox 结果协议、audit 字段、失败样本完整

---

## 6. 当前验收口径（仅未完成部分）

- `deviced` 必须从 probe / helper / state-file 主导收敛到正式 backend 主路径
- provider lifecycle、descriptor、health、worker contract 必须形成统一口径
- compat 不得继续停留在 governed fallback 描述层，必须补齐 loader / enforcement / bridge contract
- 团队 C 与团队 E 必须能稳定消费团队 D 的 backend 状态、provider 健康与 sandbox 审计证据

---

## 7. 跨团队输入输出

### 7.1 依赖输入
- 团队 B：token verify、route resolve、approval、descriptor、execution location、audit correlation 契约
- 团队 C：chooser、indicator、backend-status、screen share / recovery / approval surface 的消费字段
- 团队 E：evidence schema、artifact 命名、审计归档、验收门槛、报告模板
- 团队 A：Tier 1 验证环境、硬件 bring-up 约束、设备 backend 在镜像中的落地条件

### 7.2 对外输出
- 给团队 A：设备 backend readiness、capture 能力支持矩阵、实机验证前置条件
- 给团队 C：backend-status、provider 状态、handle 关联对象、indicator 数据、`ui_tree_snapshot` 只读消费路径
- 给团队 E：backend-state、readiness、capture evidence、provider health 样本、sandbox audit、compat 执行记录

---

## 8. 不负责内容

- 不负责核心 `sessiond` / `policyd` / `runtimed` 业务规则实现
- 不负责正式 shell / chooser GUI / compositor 体验设计
- 不负责 image / update / recovery 执行链
- 不负责发布 gate 与 CI 编排主逻辑

---

## 9. 防冲突规则

1. 团队 D 不直接修改 `aios/shell/` 与核心控制面主逻辑，只通过稳定契约联调
2. provider / compat 所需 token / route / approval 变更必须先经过团队 B 契约冻结
3. 设备状态展示归团队 C，团队 D 只负责数据模型、执行后端与证据输出
4. sandbox / bridge / compat 的审计字段优先对齐团队 E 的观测模型
5. 若任务板状态与仓库现实不一致，团队 D 先更新任务状态，再宣称里程碑完成
