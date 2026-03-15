# 团队C-Shell与Portal交互计划书

## 1. 团队使命

团队 C 负责把 AIOS 壳层从“已有可运行 baseline”收敛为“正式可交付交互层”，让用户通过 shell、panel、chooser 和 portal 流稳定完成系统交互。

本团队只负责壳层、surface、chooser 与 portal 用户流，不负责核心策略规则本身，也不负责更新执行后端和设备采集后端本体。

---

## 2. 当前未完成部分

### 2.1 基于仓库事实的剩余缺口

根据 `docs/IMPLEMENTATION_PROGRESS.md`、`aios/shell/README.md`、`aios/shell/components/README.md`、`aios/shell/ACCEPTANCE.md`，团队 C 当前只保留下列未完成工作：

1. shell / compositor 虽已有 Smithay nested baseline、panel host bridge、formal shell role、acceptance smoke，但仍未达到 release-grade，当前仍不是 DRM/KMS 级完整桌面栈
2. panel host 真嵌入、compositor / host 进程边界、stacking / focus / modal 策略仍需继续收敛，现阶段仍带明显 baseline 性质
3. `portal-chooser` 虽已有 standalone host、panel skeleton、metadata / retry / unavailable 路径与 smoke，但 file / directory / export target / screen share 的最终统一体验与复杂异常路径仍未完全封板
4. approval / recovery / notification / task / capture / backend-status 等 surface 虽已接入正式 role 与 action route，但长时间运行稳定性、真实 Linux 环境行为一致性仍未完成
5. shell acceptance / compositor acceptance artifact 已存在，但 session restore、approval-first modal、backend status、real screen cast 主路径仍需沉淀成长期可回归资产

---

## 3. 保留的未完成范围

### 3.1 唯一负责目录
- `aios/shell/`
- `aios/crates/aios-portal/`
- shell 相关 smoke / acceptance / panel / desktop host 脚本

### 3.2 当前仅保留的未完成能力
- release-grade compositor 与正式窗口级 GUI 壳层收敛
- chooser GUI 的最终用户流、异常路径与 artifact 稳定化
- panel 真嵌入、stacking / focus / modal / action route 策略收敛
- shell 对 session / policy / recovery / device backend status / screen capture 主路径的正式验收
- Linux 实机环境、长时运行与复杂交互稳定性

---

## 4. 未完成工作包

### WP1：compositor / host / panel 真嵌入收敛
**剩余任务**
- 在现有 Smithay nested baseline 上继续补 panel 真嵌入、真实 shell role / xdg toplevel policy 组合与更细窗口策略
- 继续收敛 GTK host、nested compositor、fallback host 三者之间的行为一致性
- 把 panel-host-only slot、modal redirect、focus policy、panel action route 从“可运行”提升到“稳定可维护”

**完成标志**
- compositor 与 host 进程边界稳定
- launcher / task / approval / notification / recovery / chooser / capture / backend-status 八类 surface 在统一布局语义下运行
- Linux 环境下正式 shell 路径不再依赖 demo 级 fallback 完成关键用户流

### WP2：chooser 与 portal 用户流封板
**剩余任务**
- 补齐 file / directory / export target / screen share handle 的最终 chooser 体验
- 补齐批准、取消、失败、重试、超时、resource unavailable 等复杂异常路径
- 打通 chooser 后真实受控媒体链路，并与 `deviced` 正式 backend 主路径对齐

**完成标志**
- formal chooser GUI 覆盖四类 handle 的正常与异常路径
- handle 元数据、失败原因与重试提示可被用户稳定理解
- portal flow smoke、chooser smoke、screen capture 主路径验收可重复执行

### WP3：正式 shell 验收路径与稳定性收口
**剩余任务**
- 继续打通 session restore、approval-first modal、recovery surface、device backend status 的正式壳层验收链路
- 增加长时间运行、复杂窗口策略、跨 surface action route 的稳定性验证
- 把现有 shell acceptance / compositor acceptance 输出收敛成团队 E 可长期消费的固定 artifact

**完成标志**
- shell 在恢复、失败、modal 抢占、backend 状态变化等场景下不丢关键状态
- 形成可重复执行的 shell acceptance / compositor acceptance / stability 验收路径
- 团队 E 可稳定消费 panel snapshot、panel action event、chooser/export artifact、shell acceptance artifact

---

## 5. 未完成里程碑

### M1：compositor / host 边界冻结
- panel 真嵌入路线明确
- stacking / focus / modal 规则冻结
- GTK host / nested compositor / fallback host 行为差异收敛

### M2：chooser 与 screen cast 用户流可验收
- 四类 handle 统一交互体验可运行
- 异常路径可重复验证
- chooser 后真实受控媒体链路打通

### M3：shell 验收闭环成立
- session restore、approval-first modal、backend status 展示打通
- shell acceptance artifact 固定输出
- Linux 环境下正式 shell 路径达到可演示、可回归水平

---

## 6. 当前验收口径（仅未完成部分）

- 不能再把团队 C 的工作描述为“空白 shell”，当前剩余任务是把已有 baseline 收敛到 release-grade
- chooser GUI 必须覆盖 file / directory / export target / screen share 的正常与异常路径
- approval、recovery、notification、task、capture、backend-status 等 surface 的优先级和行为必须在复杂交互下保持一致
- shell 关键事件、快照与 acceptance artifact 必须能被团队 E 持续收集为 machine-readable 证据

---

## 7. 跨团队输入输出

### 7.1 依赖输入
- 团队 B：session、policy、approval、registry、shell control 稳定接口
- 团队 A：recovery surface JSON / RPC、更新恢复状态字段
- 团队 D：device backend status、portal handle 关联对象、screen capture / provider 状态
- 团队 E：事件 / 快照 schema、验收门槛、报告模板

### 7.2 对外输出
- 给团队 E：UI smoke artifact、panel snapshot、panel action event、chooser/export artifact、acceptance 证据
- 给团队 B：对接口可用性的反馈与必要字段需求
- 给团队 D：chooser / indicator / backend-status 展示接入需求

---

## 8. 不负责内容

- 不负责核心 policy / token / route 规则实现
- 不负责 image / update / firmware / recovery 执行后端
- 不负责 provider worker 本体实现
- 不负责 `deviced` 原生采集 backend

---

## 9. 防冲突规则

1. 团队 C 不直接改核心服务业务规则，只消费团队 B 提供的稳定接口
2. chooser 所需 handle / schema 变更，必须通过团队 B / D 的契约评审进入
3. 与 recovery / update 的对接只限 UI surface，不侵入团队 A 的执行后端
4. shell 事件、快照、artifact 格式优先对齐团队 E 的观测模型

