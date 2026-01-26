## 项目上下文摘要（浏览器控制全面实现）
生成时间：2026-01-24 17:27:31

### 1. 相似实现分析
- **实现1**: aios/packages/daemon/src/adapters/browser/BrowserAdapter.ts
  - 模式：适配器能力定义 + Playwright 懒加载实例 + NetworkGuard 白名单
  - 可复用：capabilities 结构、invoke 分发、ensureBrowser 管理
  - 需注意：仅支持 open_url/search/截图/标题等基础能力

- **实现2**: aios/packages/daemon/src/adapters/screenshot/ScreenshotAdapter.ts
  - 模式：参数校验 + 平台差异处理 + 输出路径管理
  - 可复用：参数验证、错误封装、路径处理
  - 需注意：跨平台命令执行与权限判断

- **实现3**: aios/packages/daemon/src/adapters/system/FileAdapter.ts
  - 模式：输入校验 + 安全限制 + 统一错误返回
  - 可复用：参数 guard、异常转换为 AdapterResult
  - 需注意：安全白名单/黑名单的判定逻辑

### 2. 项目约定
- **命名约定**: Adapter 类以 Adapter 结尾，capability id 使用 snake_case
- **文件组织**: aios/packages/daemon/src/adapters/<domain>/，统一通过 adapters/index.ts 导出
- **导入顺序**: 先类型，再内部模块，再外部依赖
- **代码风格**: TypeScript + ESM，注释为简体中文

### 3. 可复用组件清单
- `aios/packages/daemon/src/adapters/browser/BrowserAdapter.ts`: 浏览器实例管理与基础能力
- `aios/packages/daemon/src/core/ToolExecutor.ts`: 工具名映射与适配器执行封装
- `aios/packages/daemon/src/core/TaskOrchestrator.ts`: AI → 工具调用 → 回填结果的核心链路
- `aios/packages/daemon/src/core/security/NetworkGuard.ts`: 域名白名单与拦截策略

### 4. 测试策略
- **测试框架**: Vitest
- **测试模式**: 适配器单元测试 + 集成测试
- **参考文件**: aios/packages/daemon/src/__tests__/adapters/BrowserAdapter.test.ts
- **覆盖要求**: 新增能力需补全单测（正常流程 + 参数校验 + 拦截场景）

### 5. 依赖和集成点
- **外部依赖**: Playwright（浏览器控制）
- **内部依赖**: AdapterRegistry / ToolExecutor / TaskOrchestrator
- **集成方式**: ToolExecutor 提供工具定义，LLM 调用后路由到 BrowserAdapter
- **配置来源**: NetworkGuard 白名单默认配置

### 6. 技术选型理由
- **为什么用这个方案**: 统一适配器能力模型与工具执行链路，便于扩展
- **优势**: LLM 可调用工具完成复杂流程；浏览器能力独立可维护
- **劣势和风险**: 当前能力缺失 DOM 操作/解析；NetworkGuard 限制第三方域名

### 7. 关键风险点
- **并发问题**: 现有 BrowserAdapter 仅单实例/单页面
- **边界条件**: 选择器找不到、页面加载失败、跨域受限
- **性能瓶颈**: 频繁启停浏览器或大量页面操作
- **安全考虑**: 域名白名单、潜在敏感页面操作

### 上下文充分性检查
- 能列出至少 3 个相似实现路径：是
- 理解实现模式：是
- 可复用组件明确：是
- 命名约定与风格明确：是
- 测试方式明确：是
- 未重复造轮子的证明：已检查 BrowserAdapter/ScreenshotAdapter/FileAdapter 模式
- 依赖与集成点清楚：是

### 备注
- desktop-commander、github.search_code、context7 不可用，已使用本地检索替代并记录在 operations-log。
