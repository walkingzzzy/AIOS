# AIOS 项目优化方案

> 基于 OpenCoWork 项目和 Anthropic Cowork 深度研究

**创建日期**: 2026-01-13  
**更新日期**: 2026-01-13  
**文档版本**: 3.0.0

---

## 目录

1. [参考项目分析](#1-参考项目分析)
2. [AIOS 现状分析](#2-aios-现状分析)
3. [核心借鉴价值](#3-核心借鉴价值)
4. [优化方案](#4-优化方案)
5. [实施计划](#5-实施计划)
6. [技术选型验证](#6-技术选型验证)
7. [风险评估](#7-风险评估)
8. [实现状态审计](#8-实现状态审计) ⭐ 新增
9. [遗漏功能补充](#9-遗漏功能补充) ⭐ 新增

---

## 1. 参考项目分析

### 1.1 OpenCoWork 项目

OpenCoWork 是一个云端 AI Agent 执行平台，灵感来自 Anthropic Cowork。

**核心架构**：
- Frontend (Next.js) → Executor Manager (APScheduler) → Executor (Claude Agent)
- Backend (FastAPI) 负责会话管理、回调处理、持久化
- PostgreSQL 数据存储

**核心设计模式**：

| 模式 | 描述 | 关键实现 |
|------|------|---------|
| **Hook 系统** | 4 个生命周期方法：on_setup / on_agent_response / on_teardown / on_error | 内置 CallbackHook、WorkspaceHook、TodoHook |
| **任务调度** | APScheduler 实现任务队列和并发控制 | 容器池复用，状态同步 |
| **回调机制** | 实时进度追踪，增量状态更新 (state_patch) | 进度 = 已完成 Todo / 总数 × 100 |
| **工作区追踪** | Git 状态监控，文件变更收集 | 支持 diff 展示和回滚 |

### 1.2 Anthropic Cowork

Anthropic Cowork 代表了 AI Agent 从"对话助手"向"自主执行智能体"的转变。

**核心架构**：
- 混合边缘云架构：Apple VZ Framework 本地虚拟化 + 云端 Claude 推理
- 安全沙箱：VirtioFS 文件挂载 + VirtioSocket 网络隔离

**核心技术创新**：

| 技术组件 | 实现方案 | 关键价值 |
|---------|---------|---------|
| **显式状态管理** | PLAN.md 任务计划文件 | 克服 LLM 无状态缺陷，支持长周期任务 |
| **项目记忆** | CLAUDE.md 项目知识库 | 跨会话知识持久化 |
| **技能系统** | SKILL.md + 渐进式披露 | 动态能力加载，节省 97% Token |
| **多智能体编排** | Orchestrator-Worker 模式 | 并行执行 + 上下文隔离 |
| **ReAct 循环** | 感知→规划→决策→执行→观察→反思 | 结构化推理，支持自我修正 |
| **纵深防御** | 提示词防护 + 沙箱 + 白名单 + 人机回环 | 安全执行环境 |

### 1.3 两个项目对比

| 维度 | OpenCoWork | Anthropic Cowork |
|------|------------|------------------|
| **定位** | 开源云端执行平台 | 商业桌面产品 |
| **执行环境** | Docker 容器 | macOS 本地虚拟机 |
| **AI 引擎** | Claude Agent SDK | Claude 3.5 Sonnet/Opus |
| **核心亮点** | Hook 系统、任务调度、回调机制 | 状态管理、技能系统、安全防御 |
| **适用场景** | 云端任务执行 | 本地知识工作 |

---

## 2. AIOS 现状分析

### 2.1 当前架构

```
Client (Electron) ──JSON-RPC──▶ AIOS Daemon (Node.js)
                                    │
                    ┌───────────────┼───────────────┐
                    ▼               ▼               ▼
              TaskOrchestrator  AdapterRegistry  MCP/A2A Server
              (三层 AI 协调)     (26+ 适配器)     (协议互操作)
```

### 2.2 现有优势

| 优势 | 描述 |
|------|------|
| ✅ **三层 AI 协调** | Fast (gpt-4o-mini) / Vision (gemini-2.5-flash) / Smart (claude-sonnet) 分层处理 |
| ✅ **多模型支持** | OpenAI / Claude / Gemini，成本优化 |
| ✅ **26+ 适配器** | 系统控制能力：音量、亮度、文件、进程、网络等 |
| ✅ **协议支持** | MCP + A2A 双协议互操作 |
| ✅ **跨平台** | macOS / Windows / Linux |
| ✅ **轻量实现** | 直接使用 REST API，无厚重 SDK |

### 2.3 待改进点

| 问题 | 描述 | 优先级 |
|------|------|--------|
| ❌ 缺少任务队列 | 无并发任务管理 | P0 |
| ❌ 缺少进度追踪 | 长任务无实时反馈 | P0 |
| ❌ 缺少 Hook 系统 | 扩展性受限 | P0 |
| ❌ 缺少状态管理 | 复杂任务易迷失方向 | P0 |
| ❌ 缺少会话持久化 | 重启后丢失状态 | P1 |
| ❌ 缺少技能系统 | 能力描述占用大量 Token | P1 |
| ❌ 缺少容错机制 | 任务失败无重试 | P2 |

---

## 3. 核心借鉴价值

### 3.1 从 OpenCoWork 借鉴

| 特性 | 借鉴方式 | 优先级 | 价值 |
|------|---------|--------|------|
| **Hook 生命周期** | 为 TaskOrchestrator 添加 Hook 支持 | P0 | 插件化扩展 |
| **Todo 进度追踪** | 让 AI 输出任务分解，计算进度 | P0 | 实时反馈 |
| **增量状态更新** | 回调只发送变更部分 (state_patch) | P1 | 减少传输 |
| **Git 状态追踪** | WorkspaceHook 监控文件变更 | P1 | 透明可控 |
| **回调机制** | Electron IPC 实时推送 | P0 | 用户体验 |
| **会话持久化** | SQLite 存储任务历史 | P1 | 断点续传 |

### 3.2 从 Anthropic Cowork 借鉴

| 特性 | 借鉴方式 | 优先级 | 价值 |
|------|---------|--------|------|
| **PLAN.md 状态管理** | 任务计划文件，读-写-执行循环 | P0 | 解决长任务迷失问题 |
| **ReAct 认知循环** | 增加"反思与修正"环节 | P0 | 提升推理质量 |
| **Skills 技能系统** | 渐进式披露，按需加载能力 | P1 | 节省 97% Token |
| **AIOS.md 项目记忆** | 跨会话知识持久化 | P1 | 减少重复说明 |
| **O-W 多智能体模式** | Smart Layer 增强，并行执行 | P2 | 复杂任务效率 |
| **安全增强** | 提示词防护 + 操作审计 | P2 | 防御注入攻击 |

### 3.3 不需要借鉴的部分

| 特性 | 不借鉴原因 |
|------|-----------|
| Apple VZ 虚拟化 | AIOS 是跨平台桌面应用，不需要 macOS 专属虚拟化 |
| VirtioFS 文件挂载 | AIOS 直接访问本地文件系统，无需隔离 |
| 容器池 | AIOS 是本地执行，不需要容器管理 |
| VirtioSocket 网络 | AIOS 使用标准 IPC，不需要虚拟化网络 |

### 3.4 AIOS 独有优势（保持）

| 优势 | 说明 |
|------|------|
| **三层 AI 协调** | Fast/Vision/Smart 分层，成本优化，OpenCoWork/Cowork 均无此能力 |
| **多模型支持** | OpenAI/Claude/Gemini 灵活切换 |
| **26+ 本地适配器** | 系统控制能力远超两个参考项目 |
| **MCP + A2A** | 协议互操作，生态扩展 |
| **跨平台** | Win/Mac/Linux 全覆盖 |

---

## 4. 优化方案

### 4.1 Phase 1: Hook 系统 (P0)

**目标**：任务执行生命周期管理 + 插件化扩展

**核心设计**：
- `BaseHook` 抽象类：onTaskStart / onProgress / onToolCall / onToolResult / onTaskComplete / onTaskError
- `HookManager` 管理器：注册、执行、错误隔离
- 内置 Hook：LoggingHook、ProgressHook、CallbackHook、MetricsHook、PersistenceHook

**文件结构**：
```
src/core/hooks/
├── BaseHook.ts
├── HookManager.ts
├── LoggingHook.ts
├── ProgressHook.ts
├── CallbackHook.ts
└── index.ts
```

### 4.2 Phase 2: 任务队列 (P0)

**目标**：任务排队、并发控制、优先级调度

**核心设计**：
- 使用 `p-queue` 库实现（并发控制、优先级、超时、事件）
- `Task` 接口：id / type / priority / status / prompt / progress / result
- `TaskScheduler` 调度器：submit / cancel / getStatus / getQueue

**技术选型**：p-queue v8+ (ESM-only, 2278+ dependents)

### 4.3 Phase 3: 会话持久化 (P1)

**目标**：任务历史查询、会话恢复、统计分析

**核心设计**：
- 使用 `better-sqlite3` 存储（6.8k stars, 173k+ 使用）
- 数据模型：SessionRecord / TaskRecord / MessageRecord / ToolExecutionRecord
- Repository 模式：SessionRepository / TaskRepository / MessageRepository

### 4.4 Phase 4: 进度 API (P1)

**目标**：实时进度推送、任务状态查询

**核心设计**：
- JSON-RPC 方法：task.submit / task.cancel / task.getStatus / task.getQueue / task.getHistory
- Electron IPC 推送：task:progress / task:complete / task:error
- 使用 IPC 替代 WebSocket（更轻量、更安全）

### 4.5 Phase 5: 容错重试 (P2)

**目标**：自动重试、断点续传

**核心设计**：
- `RetryPolicy`：maxRetries / initialDelay / backoffMultiplier / retryableErrors
- `CheckpointManager`：save / load / resume
- 默认策略：3 次重试，指数退避

### 4.6 Phase 6: PLAN.md + ReAct 循环 (P0) [Cowork 借鉴]

**目标**：解决长任务迷失问题，提升推理质量

**核心设计**：
- `TaskPlan` 接口：taskId / goal / todos / currentStep / knownIssues / completedSteps
- `PlanManager`：getOrCreatePlan / decomposeTasks / completeStep / getPlanSummary
- ReAct 循环：感知 → 规划 → 决策 → 执行 → 观察 → 反思
- 反思输出：success / reason / nextAction (continue/retry/revise_plan/escalate)

**关键机制**：
- 复杂任务强制进入"规划模式"
- 每步操作前读取 PLAN，操作后更新
- 上下文压缩：可丢弃历史对话，仅保留 PLAN 热启动

### 4.7 Phase 7: Skills 系统 + AIOS.md (P1) [Cowork 借鉴]

**目标**：节省 Token，跨会话知识持久化

**Skills 系统设计**：
- 三层加载：Metadata (~100 tokens) → Instructions (~2-5K tokens) → Resources (按需)
- `SkillMeta`：name / description / category / keywords
- `SkillRegistry`：discoverSkills / getSkillSummaries / loadSkill / matchSkills
- 技能目录：~/.aios/skills/ 和 .aios/skills/

**AIOS.md 设计**：
- 存储位置：项目根目录 .aios/AIOS.md
- 内容：用户偏好、项目规范、常用任务、自定义指令
- 每次会话启动时自动注入

### 4.8 Phase 8: O-W 模式 + 安全增强 (P2) [Cowork 借鉴]

**Orchestrator-Worker 模式**：
- 编排者：浅而宽上下文，任务分解和协调
- 工作者：深而窄上下文，专注具体子任务
- 作为 Smart Layer 的增强，而非替代三层架构

**安全增强**：
- `PromptGuard`：wrapUntrustedData / detectInjection
- `AuditLogger`：logOperation / getAuditTrail
- 高风险操作需用户确认

---

## 5. 实施计划

### 5.1 时间线

```
Phase 1: Hook 系统 ─────────────────────────▶ 1 周
Phase 2: 任务队列 ─────────────────────────▶ 1 周
Phase 3: 会话持久化 ────────────────────────▶ 1 周
Phase 4: 进度 API ──────────────────────────▶ 0.5 周
Phase 5: 容错重试 ──────────────────────────▶ 1 周
Phase 6: PLAN.md + ReAct ───────────────────▶ 1 周 [Cowork]
Phase 7: Skills + AIOS.md ──────────────────▶ 1.5 周 [Cowork]
Phase 8: O-W 模式 + 安全 ───────────────────▶ 2 周 [Cowork]

总计: 约 9 周（可并行部分工作，实际约 7 周）
```

### 5.2 依赖关系

```
Phase 1 (Hook) ──┬──▶ Phase 2 (队列) ──┬──▶ Phase 4 (API)
                 │                     └──▶ Phase 5 (容错)
                 │
                 └──▶ Phase 3 (持久化) ──▶ Phase 7 (Skills)
                 │
                 └──▶ Phase 6 (PLAN.md) ──▶ Phase 8 (O-W)
```

### 5.3 文件结构

```
aios/packages/daemon/src/core/
├── hooks/
│   ├── BaseHook.ts
│   ├── HookManager.ts
│   └── [内置 Hook]
├── scheduler/
│   ├── Task.ts
│   ├── TaskScheduler.ts
│   ├── RetryPolicy.ts
│   └── Checkpoint.ts
├── storage/
│   ├── models.ts
│   └── [Repository]
├── planning/
│   ├── TaskPlan.ts
│   ├── PlanManager.ts
│   └── ReActOrchestrator.ts
├── skills/
│   ├── Skill.ts
│   ├── SkillRegistry.ts
│   └── ProjectMemory.ts
└── security/
    ├── PromptGuard.ts
    └── AuditLogger.ts
```

---

## 6. 技术选型验证

### 6.1 验证结论

| 组件 | 选型 | 验证状态 | 说明 |
|------|------|---------|------|
| 任务队列 | p-queue v8+ | ✅ 推荐 | 并发控制、优先级、超时、事件支持 |
| 数据库 | better-sqlite3 v11+ | ✅ 推荐 | 6.8k stars, 同步 API, WAL 模式 |
| 进程通信 | Electron IPC | ✅ 推荐 | 内置 API, 更轻量安全 |
| Skills 格式 | SKILL.md (YAML + Markdown) | ✅ 推荐 | Anthropic 官方规范，主流平台已采用 |

### 6.2 依赖清单

| 依赖 | 版本 | 用途 |
|------|------|------|
| p-queue | ^8.x | 任务队列（ESM-only） |
| better-sqlite3 | ^11.x | 数据持久化 |
| Electron IPC | 内置 | 进程通信 |

### 6.3 注意事项

> [!WARNING]
> **p-queue v8+ 是 ESM-only**
> 需要确保项目支持 ESM 或使用动态导入。

---

## 7. 风险评估

### 7.1 技术风险

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| Hook 性能开销 | 低 | 异步执行，可配置禁用 |
| 任务队列内存 | 低 | p-queue 成熟稳定，SQLite 持久化兜底 |
| 并发问题 | 中 | 单进程应用，同步 API 避免竞态 |
| Skills 元数据维护 | 中 | 需要保持描述准确，否则影响加载决策 |

### 7.2 兼容性风险

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| API 变更 | 中 | 保持向后兼容，版本化 API |
| 存储格式变更 | 中 | 迁移脚本 |
| 与现有架构兼容 | 中 | 渐进式集成 |

### 7.3 实施建议

> [!IMPORTANT]
> **优先实施 Phase 1、2、6**
> Hook 系统、任务队列、PLAN.md 是最核心的改进，能够显著提升复杂任务成功率。

> [!TIP]
> **渐进式实施**
> 每个 Phase 完成后进行充分测试，确保稳定性。Skills 系统可以与现有适配器模式共存，逐步迁移。

> [!NOTE]
> **保持 AIOS 独有优势**
> 三层 AI 协调、26+ 适配器、MCP+A2A 是 AIOS 的核心竞争力，借鉴是为了增强而非替代。

---

## 附录 A: 参考项目对比

| 方面 | AIOS | OpenCoWork | Anthropic Cowork |
|------|------|------------|------------------|
| **语言** | TypeScript | Python | Swift + Python |
| **运行时** | Node.js (本地) | Docker (云端) | macOS VM (本地) |
| **AI 引擎** | 多模型 | Claude 专用 | Claude 专用 |
| **协议** | MCP + A2A | 自定义 | 自定义 |
| **适配器** | 26+ 本地控制 | 代码执行为主 | 文件操作为主 |
| **部署** | 桌面应用 | 微服务架构 | 桌面应用 |

## 附录 B: 参考链接

- [OpenCoWork GitHub](https://github.com/open-cowork/open-cowork)
- [Anthropic Agent Skills 文档](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview)
- [Claude Agent SDK 工程博客](https://www.anthropic.com/engineering/building-agents-with-the-claude-agent-sdk)
- [awesome-agent-skills](https://github.com/skillmatic-ai/awesome-agent-skills)

## 附录 D: 报告准确性验证说明

> 关于 a-cowork.md 和 a-cowork技术方案.md 与 open-cowork 代码的对照

### D.1 对象差异说明

两份报告（a-cowork.md、a-cowork技术方案.md）聚焦的是 **Anthropic Cowork（桌面/边缘虚拟化产品）**，而 open-cowork 是 **云端/微服务执行平台**。因此按 open-cowork 代码核对时，大量结论呈现"未落地/实现路径不同"，属于对象差异而非报告错误。

### D.2 实现路线差异对照

| 报告主张 | open-cowork 实际实现 | 结论 |
|---------|---------------------|------|
| Apple VZ 微虚拟机沙箱 | Docker 容器 (`container_pool.py` line 22) | 实现路线完全不同 |
| VirtioFS 结构化挂载 | Docker volume bind (`container_pool.py` line 85) | 目标相似，机制不同 |
| VirtioSocket 网络气隙 | 未实现网络隔离，使用 host 网络 | open-cowork 安全控制缺失 |
| Orchestrator-Worker 多智能体 | 单 ClaudeSDKClient (`engine.py` line 38) | 并非多智能体协作 |
| PLAN.md 显式状态管理 | 无 PLAN.md 管理逻辑 | 报告主张未在 open-cowork 落地 |
| SKILL.md 技能系统 | 仅 schema 预留，未实现加载链路 | 接口占位，未实现 |
| 人机回环/重要操作确认 | 启用 bypassPermissions (`engine.py` line 34) | 与报告理念相反 |

### D.3 open-cowork 特有能力（报告未覆盖）

以下为 open-cowork 实际实现但报告基本不覆盖的"云端平台工程化"能力：

| 能力 | 代码位置 | 借鉴价值 |
|------|---------|---------|
| 工作区归档清理与磁盘统计 | `workspace_manager.py` (line 130) | 高 |
| 工具执行与用量落库 | `callback_service.py` (line 40, 134) | 高 |
| 请求链路追踪 | `request_context.py` (line 17) | 中 |
| 统一错误码体系 | `error_codes.py` (line 4) | 中 |
| Git 平台 API 集成 | `github.py` (line 35) | 中 |

---

## 8. 实现状态审计

> 基于 2026-01-13 代码库检索和 open-cowork 源码逐项核对

### 8.1 Phase 1-8 实现状态总览

| Phase | 功能 | 状态 | 代码位置 | 说明 |
|-------|------|------|----------|------|
| **Phase 1** | Hook 系统 | ✅ 完成 | `src/core/hooks/` | BaseHook、HookManager、LoggingHook、ProgressHook、CallbackHook、MetricsHook 均已实现 |
| **Phase 2** | 任务队列 | ✅ 完成 | `src/core/scheduler/` | TaskScheduler 基于 p-queue 实现，支持优先级、并发控制、超时、重试 |
| **Phase 3** | 会话持久化 | ✅ 完成 | `src/core/storage/` | SessionRepository、TaskRepository、MessageRepository 使用 better-sqlite3 |
| **Phase 4** | 进度 API | ⚠️ 部分完成 | - | 核心模块就绪，但 **JSON-RPC 方法未注册**，IPC 推送未集成 |
| **Phase 5** | 容错重试 | ✅ 完成 | `src/core/resilience/` | RetryPolicy（指数退避+抖动）、CheckpointManager（断点续传） |
| **Phase 6** | PLAN.md + ReAct | ⚠️ 部分完成 | `src/core/planning/` | PlanManager、ReActOrchestrator 已实现，但 **AI 调用是占位实现** |
| **Phase 7** | Skills 系统 | ✅ 完成 | `src/core/skills/` | SkillRegistry、ProjectMemoryManager 已实现 |
| **Phase 8** | O-W 模式 + 安全 | ⚠️ 部分完成 | `src/core/orchestration/` | WorkerPool、TaskDecomposer、PromptGuard、AuditLogger 已实现，但 **未集成到主流程** |

### 8.2 需要纠偏的实现细节

| 问题 | 当前状态 | 参考实现 | 建议修正 |
|------|---------|---------|---------|
| **state_patch 定义不清** | CallbackHook 发送完整事件数据，非增量 patch，且未持久化 | open-cowork: `callback.py` (line 27) | 明确定义 patch vs full state，并落库/落文件 |
| **Todo 进度机制未装配** | ProgressHook 存在但依赖外部调用 `onProgress()`，无自动 todo 解析 | open-cowork: `todo.py` (line 13) | 实现 TodoHook 解析 AI 输出的任务分解 |
| **并发隔离不足** | TaskScheduler 用 p-queue 控制并发，但未考虑端口/目录隔离 | open-cowork: `container_pool.py` (line 89) | 本地进程/沙箱实例需要端口/目录隔离 |
| **ReAct AI 集成** | `decompose()`、`decide()`、`reflect()` 是占位实现 | - | 接入 Smart Layer AI 引擎 |
| **O-W 未集成主流程** | WorkerPool 独立存在，未在 `TaskOrchestrator.executeComplex()` 中使用 | - | 作为 Smart Layer 增强集成 |
| **用户确认机制缺失** | PromptGuard 检测到高风险但无确认流程 | - | 实现 Electron 前端交互 |

### 8.3 模块导出与测试覆盖

| 模块 | 导出状态 | 测试文件 |
|------|---------|---------|
| hooks | ✅ `src/core/index.ts` | `__tests__/hooks.test.ts` |
| scheduler | ✅ `src/core/index.ts` | `__tests__/scheduler.test.ts` |
| storage | ✅ `src/core/index.ts` | `__tests__/storage.test.ts` |
| resilience | ✅ `src/core/index.ts` | `__tests__/resilience.test.ts` |
| planning | ✅ `src/core/index.ts` | - |
| skills | ✅ `src/core/index.ts` | `__tests__/skills.test.ts` |
| orchestration | ✅ `src/core/index.ts` | `__tests__/orchestration.test.ts` |

---

## 9. 遗漏功能补充

> 基于 open-cowork 源码核对，以下功能在原方案中未覆盖但具有重要价值

### 9.1 Phase 9: 工具执行审计增强 (P0) ⭐ 新增

**目标**：完整的工具调用追踪，支持可回放与审计

**问题背景**：
- 当前 `ToolExecutionRecord` 类型已定义，`AuditLogger.logToolCall()` 已实现
- 但**缺少 tool_use_id 去重和乱序合并逻辑**
- 参考：open-cowork `callback_service.py` (line 65)、`tool_execution.py` (line 25)

**核心设计**：
```typescript
interface ToolTrace {
    toolUseId: string;        // 唯一标识，用于去重
    sessionId: string;
    taskId: string;
    adapterId: string;
    capabilityId: string;
    input: Record<string, unknown>;
    output?: unknown;
    error?: string;
    status: 'pending' | 'completed' | 'failed';
    startedAt: number;
    completedAt?: number;
    duration?: number;
}
```

**关键实现**：
- `ToolTraceHook`：捕获每次 Adapter 调用
- 去重策略：按 `(session_id, tool_use_id)` 唯一约束
- 乱序合并：ToolUse 先占位，ToolResult 回填
- `ToolTraceRepository`：持久化到 SQLite

**文件结构**：
```
src/core/audit/
├── ToolTrace.ts
├── ToolTraceHook.ts
├── ToolTraceRepository.ts
└── index.ts
```

### 9.2 Phase 10: 用量/成本核算 (P0) ⭐ 新增

**目标**：支撑"成本优化"从口号变成可度量

**问题背景**：
- AIOS 强调多模型成本优化，但**完全缺失成本记账/归因机制**
- 参考：open-cowork `usage_service.py` (line 16)、`callback_service.py` (line 134)

**核心设计**：
```typescript
interface UsageRecord {
    id: string;
    sessionId: string;
    taskId: string;
    model: string;
    tier: 'fast' | 'vision' | 'smart';
    tokenInput: number;
    tokenOutput: number;
    cost: number;           // 美元
    duration: number;       // 毫秒
    createdAt: number;
}

interface UsageStats {
    totalTokens: number;
    totalCost: number;
    avgDuration: number;
    byModel: Map<string, { tokens: number; cost: number }>;
    byTier: Map<string, { tokens: number; cost: number }>;
}
```

**关键实现**：
- `UsageHook`：从 AI 响应中提取 usage 信息
- `UsageRepository`：按 task/session 聚合存储
- `UsageService`：统计分析接口
- 进度 API 同步返回 tokens/cost/duration

**JSON-RPC 方法**：
- `usage.getBySession(sessionId)` → UsageStats
- `usage.getByTask(taskId)` → UsageRecord[]
- `usage.getTotal(startTime?, endTime?)` → UsageStats

**文件结构**：
```
src/core/usage/
├── types.ts
├── UsageHook.ts
├── UsageRepository.ts
├── UsageService.ts
└── index.ts
```

### 9.3 Phase 11: 工作区生命周期治理 (P1) ⭐ 新增

**目标**：解决长期运行带来的存储膨胀与复盘需求

**问题背景**：
- 原方案只覆盖"Git 状态追踪"，未覆盖"工作区留存/归档/清理"
- 参考：open-cowork `workspace_manager.py` (line 40-241)、`cleanup_service.py` (line 26)

**核心设计**：
```typescript
interface WorkspaceConfig {
    rootDir: string;           // ~/.aios/workspaces
    activeDir: string;         // /active
    archiveDir: string;        // /archive
    tempDir: string;           // /temp
    maxActiveAge: number;      // 7 天
    maxArchiveSize: number;    // 10 GB
}

interface WorkspaceMeta {
    sessionId: string;
    taskId: string;
    userId?: string;
    mode: 'ephemeral' | 'persistent';
    createdAt: number;
    lastAccessedAt: number;
    sizeBytes: number;
    gitStatus?: GitStatus;
}
```

**关键实现**：
- `WorkspaceManager`：active/archive/temp 目录结构
- `meta.json`：每个工作区的元信息
- 归档：tar.gz 导出 + 可下载
- 清理：定时任务 + 磁盘统计 + 自动清理策略

**JSON-RPC 方法**：
- `workspace.create(sessionId, mode)` → WorkspaceMeta
- `workspace.archive(sessionId)` → archivePath
- `workspace.list(filter?)` → WorkspaceMeta[]
- `workspace.stats()` → { total, active, archived, diskUsage }
- `workspace.delete(sessionId)` → boolean
- `workspace.cleanup(policy)` → { deleted: number, freedBytes: number }

**文件结构**：
```
src/core/workspace/
├── types.ts
├── WorkspaceManager.ts
├── WorkspaceRepository.ts
├── CleanupService.ts
└── index.ts
```

### 9.4 Phase 12: 链路追踪 (P1) ⭐ 新增

**目标**：显著降低排障与追责成本

**问题背景**：
- 当前无跨 Electron/Daemon/任务的 traceId 传播
- 参考：open-cowork `request_context.py` (line 17)、`logging.py` (line 8)

**核心设计**：
```typescript
interface TraceContext {
    traceId: string;      // 全局唯一，贯穿整个请求链路
    requestId: string;    // 单次请求 ID
    spanId: string;       // 当前操作 ID
    parentSpanId?: string;
}

// 上下文传播
class TraceContextManager {
    static create(): TraceContext;
    static fromHeaders(headers: Record<string, string>): TraceContext;
    static toHeaders(ctx: TraceContext): Record<string, string>;
    static current(): TraceContext | null;
    static run<T>(ctx: TraceContext, fn: () => T): T;
}
```

**关键实现**：
- IPC/JSON-RPC 层生成 traceId 并向下透传
- 日志注入：所有日志自动携带 traceId
- 持久化：审计记录关联 traceId
- Hook 执行时自动继承上下文

**日志格式**：
```
[2026-01-13T10:30:00.000Z] [INFO] [trace:abc123] [span:def456] Task started: task_001
```

**文件结构**：
```
src/core/trace/
├── TraceContext.ts
├── TraceContextManager.ts
├── TraceLogger.ts
└── index.ts
```

### 9.5 Phase 13: 回调通道鉴权 (P0 安全项) ⭐ 新增

**目标**：防止回调伪造，不重复 open-cowork 的"字段存在但未使用"问题

**问题背景**：
- 当前 `CallbackHook` 无鉴权机制
- open-cowork 有 callback_token 字段但未实际校验：`callback.py` (line 14)

**核心设计**：
```typescript
interface CallbackAuth {
    method: 'hmac' | 'token';
    secret?: string;          // HMAC 密钥
    token?: string;           // 短期 token
    expiresAt?: number;       // token 过期时间
}

interface SignedCallback {
    payload: CallbackEvent;
    signature: string;        // HMAC-SHA256(payload, secret)
    timestamp: number;
}
```

**关键实现**：
- `CallbackAuthManager`：签名生成与验证
- HMAC 签名：`HMAC-SHA256(JSON.stringify(payload) + timestamp, secret)`
- 时间窗口：拒绝超过 5 分钟的回调
- 鉴权失败纳入审计日志

**文件结构**：
```
src/core/security/
├── CallbackAuth.ts
├── CallbackAuthManager.ts
└── index.ts  // 合并到现有 security 模块
```

### 9.6 Phase 14: 统一错误码体系 (P1) ⭐ 新增

**目标**：提升可观测与可恢复性

**问题背景**：
- JSON-RPC 有基础错误处理，但无业务错误码枚举
- 参考：open-cowork `error_codes.py` (line 4)、`response.py` (line 10)

**核心设计**：
```typescript
enum ErrorCode {
    // 任务相关 (-32100 ~ -32199)
    TASK_NOT_FOUND = -32100,
    TASK_ALREADY_RUNNING = -32101,
    TASK_CANCELLED = -32102,
    TASK_TIMEOUT = -32103,
    
    // 会话相关 (-32200 ~ -32299)
    SESSION_NOT_FOUND = -32200,
    SESSION_EXPIRED = -32201,
    
    // 工作区相关 (-32300 ~ -32399)
    WORKSPACE_NOT_FOUND = -32300,
    WORKSPACE_LOCKED = -32301,
    WORKSPACE_DISK_FULL = -32302,
    
    // 适配器相关 (-32400 ~ -32499)
    ADAPTER_NOT_FOUND = -32400,
    CAPABILITY_NOT_FOUND = -32401,
    PERMISSION_DENIED = -32402,
    
    // AI 相关 (-32500 ~ -32599)
    AI_RATE_LIMIT = -32500,
    AI_CONTEXT_OVERFLOW = -32501,
    AI_INVALID_RESPONSE = -32502,
}

interface AppError {
    code: ErrorCode;
    message: string;
    details?: Record<string, unknown>;
    recoverable: boolean;
    retryAfter?: number;  // 秒
}
```

**文件结构**：
```
src/core/errors/
├── ErrorCode.ts
├── AppError.ts
├── ErrorHandler.ts
└── index.ts
```

### 9.7 Phase 15: Git 平台闭环 (P2 可选) ⭐ 新增

**目标**：把结果输出到协作平台（提 Issue/PR）

**问题背景**：
- 原方案只覆盖 Git 状态追踪，未提及平台集成
- 参考：open-cowork `github.py` (line 35-277)、`gitlab.py` (line 36)

**核心设计**：
```typescript
interface GitPlatformClient {
    // Issue 操作
    createIssue(repo: string, title: string, body: string): Promise<Issue>;
    updateIssue(repo: string, issueId: number, updates: Partial<Issue>): Promise<Issue>;
    
    // PR 操作
    createPullRequest(repo: string, pr: PullRequestCreate): Promise<PullRequest>;
    mergePullRequest(repo: string, prId: number): Promise<void>;
    
    // 通用
    getRepository(repo: string): Promise<Repository>;
}

// 平台实现
class GitHubClient implements GitPlatformClient { ... }
class GitLabClient implements GitPlatformClient { ... }
```

**使用场景**：
- 任务完成后自动生成变更摘要
- 创建分支 → 提交 → 发 PR
- 任务失败时自动创建 Issue

**文件结构**：
```
src/adapters/git-platform/
├── types.ts
├── GitPlatformClient.ts
├── GitHubClient.ts
├── GitLabClient.ts
└── index.ts
```

---

## 10. 更新后的实施计划

### 10.1 调整后的优先级

| 优先级 | Phase | 功能 | 状态 | 理由 |
|-------|-------|------|------|------|
| **P0** | 1 | Hook 系统 | ✅ 完成 | 基础设施 |
| **P0** | 2 | 任务队列 | ✅ 完成 | 基础设施 |
| **P0** | 6 | PLAN.md + ReAct | ⚠️ 需完善 | 核心能力，AI 集成待完成 |
| **P0** | 9 | 工具执行审计增强 | ❌ 新增 | 可调试性与安全审计质量 |
| **P0** | 10 | 用量/成本核算 | ❌ 新增 | 多模型架构核心价值点 |
| **P0** | 13 | 回调通道鉴权 | ❌ 新增 | 安全基线 |
| **P1** | 3 | 会话持久化 | ✅ 完成 | 数据基础 |
| **P1** | 4 | 进度 API | ⚠️ 需完善 | JSON-RPC 注册待完成 |
| **P1** | 7 | Skills 系统 | ✅ 完成 | Token 优化 |
| **P1** | 11 | 工作区生命周期 | ❌ 新增 | 长期运行必需 |
| **P1** | 12 | 链路追踪 | ❌ 新增 | 排障效率 |
| **P1** | 14 | 统一错误码 | ❌ 新增 | 可观测性 |
| **P2** | 5 | 容错重试 | ✅ 完成 | 稳定性增强 |
| **P2** | 8 | O-W 模式 + 安全 | ⚠️ 需完善 | 主流程集成待完成 |
| **P2** | 15 | Git 平台闭环 | ❌ 新增 | 产品增益 |

### 10.2 更新后的时间线

```
已完成 ─────────────────────────────────────────────────────
Phase 1: Hook 系统 ✅
Phase 2: 任务队列 ✅
Phase 3: 会话持久化 ✅
Phase 5: 容错重试 ✅
Phase 7: Skills 系统 ✅

需完善 ─────────────────────────────────────────────────────
Phase 4: 进度 API (JSON-RPC 注册) ──────────▶ 0.5 周
Phase 6: PLAN.md + ReAct (AI 集成) ─────────▶ 1 周
Phase 8: O-W 模式 (主流程集成) ─────────────▶ 1 周

新增 P0 ────────────────────────────────────────────────────
Phase 9: 工具执行审计增强 ──────────────────▶ 1 周
Phase 10: 用量/成本核算 ────────────────────▶ 1 周
Phase 13: 回调通道鉴权 ─────────────────────▶ 0.5 周

新增 P1 ────────────────────────────────────────────────────
Phase 11: 工作区生命周期 ───────────────────▶ 1.5 周
Phase 12: 链路追踪 ─────────────────────────▶ 1 周
Phase 14: 统一错误码 ───────────────────────▶ 0.5 周

新增 P2 ────────────────────────────────────────────────────
Phase 15: Git 平台闭环 ─────────────────────▶ 2 周 (可选)

总计新增工作量: 约 10 周（可并行，实际约 6-7 周）
```

### 10.3 更新后的依赖关系

```
已完成模块
    │
    ├──▶ Phase 4 (进度 API 完善)
    │
    ├──▶ Phase 6 (ReAct AI 集成) ──▶ Phase 8 (O-W 主流程集成)
    │
    ├──▶ Phase 9 (工具审计) ──┬──▶ Phase 10 (用量核算)
    │                        │
    │                        └──▶ Phase 12 (链路追踪)
    │
    ├──▶ Phase 11 (工作区) ──▶ Phase 15 (Git 平台)
    │
    ├──▶ Phase 13 (回调鉴权)
    │
    └──▶ Phase 14 (错误码)
```

### 10.4 更新后的文件结构

```
aios/packages/daemon/src/core/
├── hooks/                    # ✅ 已完成
│   ├── BaseHook.ts
│   ├── HookManager.ts
│   ├── LoggingHook.ts
│   ├── ProgressHook.ts
│   ├── CallbackHook.ts
│   ├── MetricsHook.ts
│   └── index.ts
├── scheduler/                # ✅ 已完成
│   ├── Task.ts
│   ├── TaskScheduler.ts
│   └── index.ts
├── storage/                  # ✅ 已完成
│   ├── types.ts
│   ├── SessionRepository.ts
│   ├── TaskRepository.ts
│   ├── MessageRepository.ts
│   ├── SessionManager.ts
│   └── index.ts
├── resilience/               # ✅ 已完成
│   ├── RetryPolicy.ts
│   ├── CheckpointManager.ts
│   └── index.ts
├── planning/                 # ⚠️ 需完善 AI 集成
│   ├── types.ts
│   ├── PlanManager.ts
│   ├── ReActOrchestrator.ts
│   └── index.ts
├── skills/                   # ✅ 已完成
│   ├── types.ts
│   ├── SkillRegistry.ts
│   ├── ProjectMemoryManager.ts
│   └── index.ts
├── orchestration/            # ⚠️ 需完善主流程集成
│   ├── types.ts
│   ├── WorkerPool.ts
│   ├── TaskDecomposer.ts
│   ├── PromptGuard.ts
│   ├── AuditLogger.ts
│   └── index.ts
├── audit/                    # ❌ 新增
│   ├── ToolTrace.ts
│   ├── ToolTraceHook.ts
│   ├── ToolTraceRepository.ts
│   └── index.ts
├── usage/                    # ❌ 新增
│   ├── types.ts
│   ├── UsageHook.ts
│   ├── UsageRepository.ts
│   ├── UsageService.ts
│   └── index.ts
├── workspace/                # ❌ 新增
│   ├── types.ts
│   ├── WorkspaceManager.ts
│   ├── WorkspaceRepository.ts
│   ├── CleanupService.ts
│   └── index.ts
├── trace/                    # ❌ 新增
│   ├── TraceContext.ts
│   ├── TraceContextManager.ts
│   ├── TraceLogger.ts
│   └── index.ts
├── security/                 # ⚠️ 需扩展
│   ├── PromptGuard.ts        # 已有
│   ├── AuditLogger.ts        # 已有
│   ├── CallbackAuth.ts       # ❌ 新增
│   └── index.ts
└── errors/                   # ❌ 新增
    ├── ErrorCode.ts
    ├── AppError.ts
    ├── ErrorHandler.ts
    └── index.ts
```

---

## 附录 C: OpenCoWork 源码核对清单

> 以下为基于 open-cowork 源码逐项核对的关键实现参考

### C.1 已借鉴并实现

| 功能 | open-cowork 位置 | AIOS 实现 |
|------|-----------------|-----------|
| Hook 生命周期 | `executor/hooks/base.py` (line 14) | `src/core/hooks/BaseHook.ts` |
| 回调机制 | `executor/hooks/callback.py` (line 27) | `src/core/hooks/CallbackHook.ts` |
| 会话持久化 | `backend/repositories/session_repository.py` | `src/core/storage/SessionRepository.ts` |
| 任务调度 | `executor_manager/scheduler/task_service.py` | `src/core/scheduler/TaskScheduler.ts` |

### C.2 已借鉴但需完善

| 功能 | open-cowork 位置 | AIOS 差距 |
|------|-----------------|-----------|
| Todo 进度 | `executor/hooks/todo.py` (line 13) | TodoHook 未装配到执行链路 |
| state_patch | `executor/hooks/callback.py` (line 72) | 发送完整状态而非增量，未持久化 |

### C.3 未借鉴但应补充

| 功能 | open-cowork 位置 | 建议 Phase |
|------|-----------------|-----------|
| 工具执行去重/乱序合并 | `backend/services/callback_service.py` (line 65) | Phase 9 |
| 用量/成本核算 | `backend/services/usage_service.py` (line 16) | Phase 10 |
| 工作区归档/清理 | `executor_manager/workspace/workspace_manager.py` (line 130) | Phase 11 |
| 链路追踪 | `backend/core/observability/request_context.py` (line 17) | Phase 12 |
| 统一错误码 | `backend/core/error_codes.py` (line 4) | Phase 14 |
| Git 平台集成 | `executor/tools/git/github.py` (line 35) | Phase 15 |

---

*本方案基于 OpenCoWork 项目和 Anthropic Cowork 的架构设计，结合 AIOS 的实际需求制定。*

**文档版本**: 3.0.0  
**最后更新**: 2026-01-13  
**可行性验证**: ✅ 已完成  
**实现状态审计**: ✅ 已完成 (2026-01-13)
