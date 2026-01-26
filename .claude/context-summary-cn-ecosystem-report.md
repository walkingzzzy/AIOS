## 项目上下文摘要（中国用户电脑使用习惯与生态报告对齐）
生成时间：2026-01-24 22:52:54

### 1. 相似实现分析
- **实现1**: /Users/mac/Desktop/AIOS/aios/packages/daemon/src/adapters/BaseAdapter.ts
  - 模式：适配器基类 + capability 列表声明
  - 可复用：success/failure + 平台判断
  - 需注意：ESM 导入使用 .js 扩展
- **实现2**: /Users/mac/Desktop/AIOS/aios/packages/daemon/src/adapters/browser/BrowserAdapter.ts
  - 模式：Playwright 驱动浏览器能力集合
  - 可复用：浏览器上下文管理与能力注册方式
  - 需注意：当前未覆盖 CDP 连接
- **实现3**: /Users/mac/Desktop/AIOS/aios/packages/daemon/src/adapters/office/OfficeLocalAdapter.ts
  - 模式：本地 Office/WPS UI 自动化 + OS 分支
  - 可复用：路径白名单/黑名单策略、UI 操作队列
  - 需注意：WPS 仅 UI 自动化，无 AirScript 接入

### 2. 项目约定
- **命名约定**：适配器类以 Adapter 结尾，能力以动词_名词命名
- **文件组织**：/packages/daemon/src/adapters 按领域拆分
- **导入顺序**：先类型/内部，再第三方（ESM .js 扩展）
- **代码风格**：TypeScript + readonly 字段 + 显式参数校验

### 3. 可复用组件清单
- /Users/mac/Desktop/AIOS/aios/packages/daemon/src/adapters/BaseAdapter.ts
- /Users/mac/Desktop/AIOS/aios/packages/daemon/src/adapters/screenshot/ScreenshotAdapter.ts
- /Users/mac/Desktop/AIOS/aios/packages/shared/src/types/adapter.ts

### 4. 测试策略
- **测试框架**：Vitest
- **测试模式**：单元/集成并存，适配器测试覆盖能力列表
- **参考文件**：/Users/mac/Desktop/AIOS/aios/packages/daemon/src/__tests__/adapters/BrowserAdapter.test.ts
- **覆盖要求**：能力可用性 + 参数校验 + 异常分支

### 5. 依赖和集成点
- **外部依赖**：playwright、node-notifier、systeminformation
- **内部依赖**：@aios/shared 适配器类型
- **集成方式**：适配器注册 + MCP/任务编排调用
- **配置来源**：packages/daemon/package.json

### 6. 技术选型理由
- **为什么用这个方案**：已有 Browser/Office/Screenshot 适配器可扩展 CN 生态
- **优势**：跨平台/模块化 + 可复用适配器能力注册
- **劣势和风险**：QQ/微信等本土应用暂无适配器，OCR/Hook 风险需规避

### 7. 关键风险点
- **并发问题**：UI 自动化需串行化队列
- **边界条件**：WPS/QQ 版本差异导致 UI/协议变化
- **性能瓶颈**：视觉识别依赖外部模型或 OCR
- **安全考虑**：Hook 类方案合规风险高，应避免

### 检索说明
- GitHub search_code 调用因 API 速率限制失败，已改用 search_repositories 与网页检索。
