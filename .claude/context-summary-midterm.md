## 项目上下文摘要（中期功能对照与实现方案）
生成时间：2026-01-24 19:10:28

### 1. 相似实现分析
- **实现1**: dev/03-中期开发计划.md
  - 模式：按领域拆分功能 + 协议互操作目标
  - 可复用：功能清单、依赖与能力矩阵
  - 需注意：目标为 Phase 2（应用控制 + MCP/A2A）

- **实现2**: docs/IMPLEMENTATION_PROGRESS.md
  - 模式：按模块汇总完成度与测试覆盖
  - 可复用：已完成适配器与协议实现列表
  - 需注意：进度与实际代码可能存在口径偏差，需要代码核验

- **实现3**: dev/05-功能实现方案.md
  - 模式：端到端流程与技术选型说明
  - 可复用：技术栈与依赖选择、能力边界
  - 需注意：需对照真实代码确认落地情况

### 2. 项目约定
- **命名约定**: 能力使用 snake_case，类/方法使用 camelCase
- **文件组织**: 适配器位于 aios/packages/daemon/src/adapters/；协议位于 aios/packages/daemon/src/protocol/
- **导入顺序**: type 导入 → 第三方/共享模块 → 本地模块
- **代码风格**: TypeScript + guard 参数校验，中文错误提示

### 3. 可复用组件清单
- aios/packages/daemon/src/index.ts: JSON-RPC invoke/getAdapters/getAdapterStatus
- aios/packages/daemon/src/protocol/: MCP/A2A 协议实现
- aios/packages/daemon/src/adapters/: 第三方应用控制适配器

### 4. 测试策略
- **测试框架**: Vitest
- **测试模式**: 单元测试 + 少量集成测试
- **参考文件**: aios/packages/daemon/src/__tests__/adapters/*.test.ts
- **覆盖要求**: 正常流程 + 失败路径 + 权限/配置异常

### 5. 依赖和集成点
- **外部依赖**: Playwright、各 SaaS API、@modelcontextprotocol/sdk
- **内部依赖**: ToolExecutor、AdapterRegistry、PermissionManager
- **集成方式**: stdio JSON-RPC + 可选 WebSocket/MCP/A2A
- **配置来源**: 环境变量与 OAuth 配置

### 6. 技术选型理由
- **为什么用这个方案**: 复用现有适配器模式与协议组件，避免重复实现
- **优势**: 统一调用入口、跨平台一致性、可扩展协议互操作
- **劣势和风险**: OAuth/令牌依赖与外部 API 稳定性

### 7. 关键风险点
- **并发问题**: 多适配器并行调用需统一限流
- **边界条件**: OAuth 过期、无凭证、API 配额限制
- **安全考虑**: 外部调用需权限与域名白名单
