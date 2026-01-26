## 项目上下文摘要（中期功能补齐：A2A Client + MCPServerV2 + SaaS E2E）
生成时间：2026-01-24 20:32:15

### 1. 相似实现分析
- **实现1**: aios/packages/daemon/src/protocol/A2AProtocol.ts
  - 模式：事件驱动 + fetch 发送消息 + Token 可选
  - 可复用：A2AMessage/AgentCard 结构、鉴权头处理
  - 需注意：sendTask 生成 taskId 并维护 pendingTasks

- **实现2**: aios/packages/daemon/src/protocol/A2AServer.ts
  - 模式：HTTP 路由 + JWT 校验 + 任务状态存储
  - 可复用：端点定义（/.well-known/agent.json、/tasks、/tasks/:id）
  - 需注意：payload.skill 权限检查与任务状态更新接口

- **实现3**: aios/packages/daemon/src/protocol/MCPServerV2.ts
  - 模式：MCP SDK 注册 tools/resources/prompts + stdio/ws 双通道
  - 可复用：工具注册与 ToolExecutor 调用模式
  - 需注意：resources/prompt 已实现，daemon 仍未切换

- **实现4**: aios/packages/daemon/src/__tests__/protocol/MCPServer.test.ts
  - 模式：Vitest + mock AdapterRegistry + 直接调用 handleMessage
  - 可复用：mock 工具与断言风格

- **实现5**: aios/scripts/office-ui/office-smoke.mjs
  - 模式：stdio JSON-RPC 调用 daemon + 结果聚合输出
  - 可复用：JsonRpcClient 与超时处理

- **实现6**: aios/packages/daemon/src/__tests__/integration/OfficeLocalAdapter.integration.test.ts
  - 模式：可选集成测试（AIOS_RUN_* env）+ 实机依赖
  - 可复用：describe.skip 与权限/缺失场景分支

### 2. 项目约定
- **命名约定**: 能力使用 snake_case，类/方法使用 camelCase
- **文件组织**: 协议位于 aios/packages/daemon/src/protocol/；脚本位于 aios/scripts/；文档位于 docs/guides/
- **导入顺序**: type 导入 → 第三方 → 本地
- **代码风格**: TypeScript + guard 校验 + 中文错误提示

### 3. 可复用组件清单
- aios/packages/daemon/src/protocol/A2AProtocol.ts: A2A 消息结构与 fetch 发送逻辑
- aios/packages/daemon/src/protocol/A2AServer.ts: A2A HTTP 端点与任务状态管理
- aios/packages/daemon/src/protocol/MCPServerV2.ts: MCP SDK 注册与 ToolExecutor 调用
- aios/scripts/office-ui/office-smoke.mjs: JSON-RPC 客户端与超时处理

### 4. 测试策略
- **测试框架**: Vitest
- **测试模式**: 单元测试（mock）+ 可选集成测试（env 开关）
- **参考文件**: aios/packages/daemon/src/__tests__/protocol/MCPServer.test.ts
- **覆盖要求**: 成功路径 + 认证/缺参失败 + 可选集成测试跳过逻辑

### 5. 依赖和集成点
- **外部依赖**: @modelcontextprotocol/sdk、ws、zod、fetch (Node 20)
- **内部依赖**: ToolExecutor、AdapterRegistry、A2ATokenManager
- **集成方式**: daemon 启动 MCP/A2A 服务；脚本通过 stdio JSON-RPC 调用
- **配置来源**: env（AIOS_MCP_*/AIOS_A2A_*/AIOS_RUN_*）

### 6. 技术选型理由
- **为什么用现有模式**: 已有 A2A/MCP/stdio JSON-RPC 实现，复用可降低风险
- **优势**: 统一调用链、测试模式一致、易于增量扩展
- **劣势和风险**: 依赖凭证与外部服务，E2E 只能可选执行

### 7. 关键风险点
- **兼容切换**: MCPServerV2 切换需谨慎控制 env 行为
- **认证/权限**: A2A Client 必须可选 Bearer Token
- **测试稳定性**: SaaS E2E 需显式开关并提供失败提示
