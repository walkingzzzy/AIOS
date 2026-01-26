## 项目上下文摘要（短期开发落地补齐）
生成时间：2026-01-24 22:52:30

### 1. 相似实现分析
- **实现1**: `aios/packages/daemon/src/adapters/apps/WindowAdapter.ts`
  - 模式：适配器继承 BaseAdapter，能力列表 + invoke 分发
  - 可复用：能力定义结构、invoke 错误处理
  - 需注意：当前使用 runPlatformCommand，计划要求 nut-js

- **实现2**: `aios/packages/daemon/src/adapters/system/DesktopAdapter.ts`
  - 模式：动态导入依赖 + 参数校验 + 平台命令封装
  - 可复用：参数校验与错误返回风格
  - 需注意：适配器初始化/可用性检测流程

- **实现3**: `aios/packages/client/src/renderer/src/views/ToolsView.tsx`
  - 模式：卡片网格 + 能力按钮 + 动态参数表单 + 快速测试
  - 可复用：参数解析、快速测试、adapter 状态展示
  - 需注意：E2E 测试依赖 `.tools-view` 与 `.adapter-card` 类名

- **实现4**: `aios/packages/client/src/renderer/src/components/ConfirmationDialog.tsx`
  - 模式：覆盖层 + 弹窗结构，阻止冒泡关闭
  - 可复用：弹窗交互与样式组织方式

### 2. 项目约定
- **命名约定**: 适配器能力使用 snake_case，UI 组件使用 PascalCase
- **文件组织**: daemon 逻辑在 `aios/packages/daemon/src`，client 在 `aios/packages/client/src`
- **导入顺序**: 外部依赖 → 本地模块 → 样式
- **代码风格**: TypeScript + 明确类型 + 中文注释/提示

### 3. 可复用组件清单
- `aios/packages/daemon/src/adapters/BaseAdapter.ts`: 适配器基类与返回结构
- `aios/packages/daemon/src/core/JSONRPCHandler.ts`: JSON-RPC 方法注册与处理
- `aios/packages/client/src/renderer/src/utils/api.ts`: 统一 RPC 调用
- `aios/packages/client/src/renderer/src/components/ConfirmationDialog.tsx`: 弹窗交互样式

### 4. 测试策略
- **测试框架**: Vitest
- **测试模式**: daemon 单元测试 + client E2E（Playwright）
- **参考文件**: `aios/packages/daemon/src/__tests__/adapters/WindowAdapter.test.ts`、`aios/packages/client/src/__tests__/e2e/app.e2e.test.ts`
- **覆盖要求**: 适配器能力调用 + UI 视图渲染类名保持

### 5. 依赖和集成点
- **外部依赖**: `@nut-tree/nut-js`（计划引入）、`playwright`（已存在）
- **内部依赖**: AdapterRegistry、JSONRPCHandler、client api
- **集成方式**: daemon 方法注册 → client api 调用 → UI 展示
- **配置来源**: `aios/packages/client/package.json` build 配置

### 6. 技术选型理由
- **为什么用这个方案**: 窗口管理统一采用 nut-js；工具面板组件化复用既有 ToolsView 逻辑
- **优势**: 与计划一致、跨平台统一、减少方案分歧
- **劣势和风险**: nut-js 依赖原生能力，平台权限与可用性需要验证

### 7. 关键风险点
- **并发问题**: 适配器状态检查可能耗时，需避免 UI 阻塞
- **边界条件**: 权限不足或 GUI 不可用导致能力失败
- **性能瓶颈**: 大量适配器状态检查可能拉长加载时间
- **安全考虑**: 高危能力仍需权限检查与确认流程

### 工具可用性说明
- desktop-commander/context7/github.search_code 不可用，已改用本地 rg/sed/cat 检索并记录替代方案。
