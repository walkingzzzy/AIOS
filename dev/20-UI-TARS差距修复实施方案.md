# UI-TARS 差距修复实施方案

**版本**: 1.0.0
**更新日期**: 2026-01-25
**文档类型**: 🛠️ 专项实施方案
**状态**: 现行
**适用范围**: UI-TARS 差距修复实施细节
**维护人**: zy

---

## 一、实施细节（由开发周期文档迁移）

## 二、阶段详细计划

### Phase 1: 流式响应全链路接入 (W1-W2)

- **目标**: 让引擎层流式能力进入 TaskOrchestrator 并通过 IPC 送达前端。
- **关键工作**: `aios/packages/daemon/src/core/TaskOrchestrator.ts` 增加流式处理入口；`aios/packages/daemon/src/index.ts` 增加 `daemon:smartChatStream` 与事件广播；前端订阅校验 `aios/packages/client/src/preload/index.ts` 与 `aios/packages/client/src/renderer/src/hooks/useStreamingChat.ts`。
- **交付物**: 端到端流式链路、取消流式能力、错误与回收路径。
- **验收标准**: 连续输出 chunk；完成事件包含 `executionTime/tier/model`；取消后不再输出内容。

### Phase 2: LLM 生命周期钩子 (W3)

- **目标**: 补齐 LLM 请求/响应/流式分片 Hook。
- **关键工作**: `aios/packages/daemon/src/core/hooks/types.ts` 新增事件类型；`aios/packages/daemon/src/core/hooks/HookManager.ts` 增加触发方法；`aios/packages/daemon/src/core/TaskOrchestrator.ts` 在 LLM 调用前后触发。
- **交付物**: Hook 事件结构、触发时机、基础日志与指标采集。
- **验收标准**: 每次 LLM 调用都有请求/响应记录；流式分片可被 Hook 捕获。

### Phase 3: 统一事件流系统 (W4)

- **目标**: 形成统一事件流模型，供 UI/调试/回放使用。
- **关键工作**: 新增 `aios/packages/daemon/src/core/events/EventStream.ts`；在 TaskOrchestrator 关键节点发事件；Hook 与事件流对齐。
- **交付物**: 事件定义、订阅 API、事件过滤与回放接口。
- **验收标准**: Task/Tool/LLM/Progress 事件可统一订阅；事件数量可控并支持裁剪。

### Phase 4: MCP SDK 迁移评估 (W5-W6，可选)

- **目标**: 评估迁移 `@modelcontextprotocol/sdk` 的收益与风险。
- **关键工作**: 对比 `aios/packages/daemon/src/protocol/MCPClient.ts` 与 UI-TARS MCP 客户端；输出迁移影响清单与兼容性策略。
- **交付物**: 迁移方案、分阶段路径、回滚策略。
- **验收标准**: 形成可实施的迁移决策结论（实施或延后）。

---

---

## 版本变更记录

- 2026-01-25：补充状态/适用范围/维护人元信息，整理文档层级与索引结构。
