## 项目上下文摘要（短期扩展方案补齐与对齐）
生成时间：2026-01-25 00:07:17

### 1. 相似实现分析
- **实现1**: aios/packages/daemon/src/adapters/productivity/GmailAdapter.ts
  - 模式：BaseAdapter + OAuthManager + fetch 调用 Google API
  - 可复用：OAuthManager、Google provider 配置、Bearer token 头
  - 需注意：依赖 OAuthProviders.scopes 定义

- **实现2**: aios/packages/daemon/src/adapters/productivity/GoogleDocsAdapter.ts
  - 模式：BaseAdapter + OAuthManager + 直接 REST API
  - 可复用：token 获取与错误处理模式
  - 需注意：API URL、请求体与返回结构封装

- **实现3**: aios/packages/daemon/src/adapters/weather/WeatherAdapter.ts
  - 模式：API Key 驱动的外部服务调用
  - 可复用：环境变量读取 + set_api_key 能力
  - 需注意：API Key 缺失时失败分支

- **实现4**: aios/packages/daemon/src/adapters/speech/SpeechAdapter.ts
  - 模式：TTS 能力封装（say）+ invoke 分发
  - 可复用：capabilities 声明与参数校验模式

### 2. 项目约定
- **命名约定**：适配器 ID 为 com.aios.adapter.*，能力 ID 为 snake_case
- **文件组织**：适配器位于 aios/packages/daemon/src/adapters/*，测试位于 aios/packages/daemon/src/__tests__/adapters
- **代码风格**：ESM import，BaseAdapter success/failure 统一返回

### 3. 可复用组件清单
- `aios/packages/daemon/src/auth/OAuthManager.ts`: OAuth token 管理
- `aios/packages/daemon/src/auth/OAuthProviders.ts`: Google OAuth scopes 配置
- `aios/packages/daemon/src/index.ts`: adapterRegistry 注册入口
- `aios/packages/daemon/src/adapters/BaseAdapter.ts`: 适配器基类

### 4. 测试策略
- **测试框架**：Vitest（daemon）
- **参考文件**：
  - aios/packages/daemon/src/__tests__/adapters/CalendarAdapter.test.ts
  - aios/packages/daemon/src/__tests__/adapters/TranslateAdapter.test.ts
  - aios/packages/daemon/src/__tests__/adapters/SpeechAdapter.test.ts
- **覆盖要求**：正常调用、缺参、错误路径、API Key 缺失

### 5. 依赖和集成点
- **外部依赖**：say/node-notifier/node-schedule/mathjs 等；Google API 通过 OAuth/REST 访问
- **内部依赖**：OAuthManager + OAuthProviders
- **集成方式**：adapterRegistry 注册 → MCP/Task API 调用 → ToolsView 测试

### 6. 技术选型理由
- **为什么用现有模式**：与 Gmail/GoogleWorkspace 保持一致，复用 OAuth 管理能力
- **优势**：减少额外 SDK 引入，统一授权与错误处理路径
- **风险**：需要补齐 Google OAuth scopes 与 API Key 配置说明

### 7. 关键风险点
- **权限范围**：Google OAuth scopes 不含 Calendar/Speech，需要更新配置
- **文档偏差**：依赖清单与实际实现不一致，需要更新文档
- **验证风险**：涉及外部 API，测试需要 mock fetch/Token

### 8. 工具限制说明
- desktop-commander/context7/github.search_code 不可用，已改用 rg + 直接读取文件进行检索与取证。
