# 05 · 优先级 Backlog

## 1. 说明

本 Backlog 服务于 **完整 AIOS 系统**，不是 MVP 范围裁剪。  
它的作用是把完整目标按依赖关系拆成优先级，而不是把所有终局能力同时塞进最近阶段。

原则：

- 优先交付系统主闭环：`boot -> service -> shell -> policy -> execution -> audit -> recovery`
- 优先冻结长期影响架构的决策，再推进具体实现
- 条件能力必须进入主计划，但排在基线闭环之后
- 协议桥接、GUI fallback、远端执行都不能反客为主定义系统内核

## 2. P0 · 架构冻结与长期决策

- 冻结 AIOS 为 `Linux-first + image-based + system-service-first + runtime-first`
- 明确 `LLM-as-Kernel` 在 AIOS 中是认知控制平面抽象，而非 Linux 替代
- 冻结 `baseline capability` 与 `declared optional capability` 表达方式
- 建立 `image/`、`services/`、`runtime/`、`shell/`、`policy/`、`compat/`、`hardware/`、`legacy/` 目录框架
- 将旧 `client` / `daemon` / `cli` 明确标记为 `legacy`
- 冻结 `agentd` / `runtimed` / `sessiond` / `policyd` / `deviced` / `updated` 服务边界
- 冻结 capability 命名空间与迁移策略，特别是 `runtime.*`、`device.*`、`compat.*`
- 冻结工作记忆 / 情景记忆 / 语义记忆 / 程序记忆模型
- 冻结 prompt injection / taint / execution token / code sandbox 基础模型
- 冻结 Tier 0 / Tier 1 硬件目标与支持矩阵表达方式
- 补齐关键 ADR：shell stack、update stack、sandbox engine、memory backend、core local IPC 与 bridge 边界

## 3. P1 · 系统 bring-up 基线

- 完成 `QEMU x86_64` 开发镜像原型
- 建立镜像构建链、first-boot、基础分区与状态目录初始化
- 跑通 `systemd` 启动、日志与恢复入口
- 完成 `runtimed` 的最小推理包装器与 `local-cpu` fallback
- 拉起核心 system units skeleton
- 验证最小 rootfs、版本元数据与 machine identity 初始化
- 建立更新前置条件：部署对象、健康检查对象、诊断包对象

## 4. P2 · 核心控制面与运行时闭环

- 抽取 `agentd` 的最小编排能力
- 抽取 `sessiond` 的最小持久化、会话与记忆能力
- 抽取 `policyd` 的审批、裁决与审计骨架
- 抽取 `runtimed` 的路由、预算、降级与拒绝策略骨架
- 建立本地 IPC / system bus / Unix socket 主链路
- 建立 execution token、policy decision 与最小 audit event 闭环
- 建立 provider descriptor / portal handle / profile schema 的验证与加载链
- 建立 provider registry、provider health 与 capability resolution 最小闭环

## 5. P3 · 壳层、provider 与用户交互闭环

- AI launcher alpha
- workspace / focus / notification / task surface
- 最小人工审批界面与恢复入口
- 第一方 system / shell / device provider 最小集合
- portal（至少文件、导出目标、屏幕共享三类）
- working / episodic / semantic / procedural memory 的最小落地
- compat provider 的独立进程边界与最小权限声明
- route profile / runtime profile / policy profile 的系统级加载与覆盖链

## 6. P4 · 安全、更新、恢复与运维基线

- capability token 正式化
- compat 权限分区
- code sandbox alpha
- prompt injection / taint 防御链
- 更新、健康检查、回滚与恢复模式闭环
- 审计事件、trace 事件、诊断包格式冻结
- shell / provider / compat / sandbox 统一进入 audit / recovery 视图
- 自愈 runbook 与失败退出条件固化

## 7. P5 · 条件能力主线

- 屏幕 / 音频 / 输入多模态主线闭环
- 至少一条 `local-gpu` 路线稳定成立，并保持 `local-cpu` 可回退
- `ui_tree` 在至少一个正式支持的图形栈 / 应用栈上稳定成立
- `local-npu` 在声明支持的 `hardware profile` 上成立
- trusted cloud offload 在 attestation、可禁用、可审计前提下进入 beta
- Tier 1 支持矩阵与限制说明形成正式文档
- 条件能力的降级、审计、恢复与对外支持声明同步固化

## 8. P6 · 产品化与长期稳定化

- 开发者预览、产品预览、稳定版标准分层冻结
- 支持矩阵、已知限制、升级与恢复策略文档冻结
- 发布工程、版本兼容矩阵与运维基线长期化
- 安全审计、发布审计与支持策略进入长期维护模式

## 9. 挂起项

以下事项可以做，但不应抢占主线：

- 继续美化 legacy UI
- 继续新增“系统应用功能页”并以此汇报主线进展
- 在 runtime / policy / recovery 基线未完成前追求“全平台硬件支持”
- 把 MCP / A2A 当成核心本地控制面 IPC 替代
- 在未冻结支持矩阵前对外承诺通用 `ui_tree`、NPU 或 trusted offload 能力
