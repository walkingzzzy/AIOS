## 项目上下文摘要（Office 本地 UI 自动化 smoke 与集成测试）
生成时间：2026-01-24 18:57:51

### 1. 相似实现分析
- **实现1**: aios/packages/cli/src/index.ts
  - 模式：spawn daemon + JSON-RPC stdio 交互
  - 可复用：请求/响应缓冲处理、invoke 调用格式
  - 需注意：依赖已构建的 dist，超时处理 30s

- **实现2**: aios/packages/daemon/src/index.ts
  - 模式：JSONRPCHandler 注册 invoke/getAdapters/getAdapterStatus
  - 可复用：适配器调用入口、权限检查
  - 需注意：默认走 stdio 传输，可选 WebSocket

- **实现3**: aios/packages/daemon/src/__tests__/integration/daemon.test.ts
  - 模式：集成测试集中在 daemon 接入与 API 流程
  - 可复用：测试结构与运行方式
  - 需注意：当前集成测试无平台/环境依赖

### 2. 项目约定
- **命名约定**: 能力使用 snake_case，类/方法使用 camelCase
- **文件组织**: 测试放在 aios/packages/daemon/src/__tests__/，文档放在 docs/ 或 dev/
- **导入顺序**: type 导入 → 第三方/共享模块 → 本地模块
- **代码风格**: TypeScript + guard 参数校验，中文错误提示与说明

### 3. 可复用组件清单
- aios/packages/cli/src/index.ts: JSON-RPC stdio 客户端实现
- aios/packages/daemon/src/index.ts: invoke/getAdapterStatus 的 API 入口
- aios/packages/daemon/src/adapters/office/OfficeLocalAdapter.ts: Office UI 自动化能力实现

### 4. 测试策略
- **测试框架**: Vitest
- **测试模式**: 单元测试 + 集成测试
- **参考文件**: aios/packages/daemon/src/__tests__/integration/daemon.test.ts
- **覆盖要求**: 正常流程 + 失败路径（前台焦点/权限缺失/未安装）

### 5. 依赖和集成点
- **外部依赖**: Office/WPS 桌面应用、macOS 辅助功能授权、Linux xdotool + xclip/xsel
- **内部依赖**: JSON-RPC invoke 接口与 OfficeLocalAdapter
- **集成方式**: stdio JSON-RPC 或可选 WebSocket
- **配置来源**: 环境变量与运行手册

### 6. 技术选型理由
- **为什么用这个方案**: 复用现有 daemon stdio JSON-RPC 通道，避免新增依赖
- **优势**: 无需额外 SDK，可跨平台驱动 OfficeLocalAdapter
- **劣势和风险**: 需要真实桌面环境和前台焦点，自动化稳定性受环境影响

### 7. 关键风险点
- **并发问题**: UI 操作需串行，避免焦点冲突
- **边界条件**: 应用未安装、权限/辅助功能未开启
- **性能瓶颈**: UI 步骤耗时导致测试时间变长
- **安全考虑**: 文件路径需受控，避免对敏感路径操作
