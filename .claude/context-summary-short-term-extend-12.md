## 项目上下文摘要（短期扩展方案核对-12）
生成时间：2026-01-24 23:52:37

### 1. 相似实现分析
- **实现1**: aios/packages/daemon/src/adapters/apps/WindowAdapter.ts
  - 模式：继承 BaseAdapter，定义 capabilities 数组，invoke 分发
  - 可复用：runPlatformCommand 跨平台命令封装
  - 需注意：平台依赖（macOS/Windows/Linux）
- **实现2**: aios/packages/daemon/src/adapters/calendar/CalendarAdapter.ts
  - 模式：本地内存事件存储，不依赖外部 API
  - 可复用：BaseAdapter 的 success/failure 返回格式
  - 需注意：与文档宣称的 Google Calendar API 不一致
- **实现3**: aios/packages/client/src/renderer/src/views/SettingsView.tsx
  - 模式：React Hooks + api 工具请求模型列表
  - 可复用：api.fetchModels / api.testAIConnection
  - 需注意：动态模型配置属于 UI 功能验证点

### 2. 项目约定
- **命名约定**：TypeScript/React 使用 PascalCase 组件与类名，适配器 ID 为 com.aios.adapter.*
- **文件组织**：后端适配器位于 aios/packages/daemon/src/adapters/*，前端视图位于 aios/packages/client/src/renderer/src/views
- **代码风格**：ESM import，BaseAdapter 统一 success/failure 返回

### 3. 可复用组件清单
- `aios/packages/daemon/src/adapters/BaseAdapter.ts`: 适配器基类与结果封装
- `aios/packages/daemon/src/index.ts`: 适配器注册入口
- `aios/packages/client/src/renderer/src/components/voice/VoiceInput.tsx`: STT 语音输入组件
- `aios/packages/client/src/renderer/src/components/widgets/*`: 天气/翻译/计算器小部件

### 4. 测试策略
- **测试框架**：Vitest（daemon），前端包含 e2e 测试文件
- **参考文件**：aios/packages/daemon/src/__tests__/adapters/*.test.ts
- **覆盖要求**：适配器基础能力、API/协议、集成用例

### 5. 依赖和集成点
- **外部依赖**：say/node-notifier/node-schedule/mathjs/brightness/loudness/wallpaper/playwright
- **内部依赖**：BaseAdapter、adapterRegistry（aios/packages/daemon/src/index.ts）
- **集成方式**：daemon 注册适配器 → MCP/Task API 调用 → 前端 ToolsView 测试

### 6. 技术选型理由
- **为什么用这个方案**：统一适配器接口，跨平台命令和 API 调用复用
- **优势**：能力清单可枚举，便于 ToolsView 测试与权限控制
- **劣势和风险**：依赖第三方 API/系统命令，平台差异与文档偏差风险

### 7. 关键风险点
- **文档偏差**：Calendar/Translate API 与依赖声明不匹配
- **平台依赖**：窗口管理、电源控制等功能依赖系统命令权限
- **验证缺口**：未运行测试，仅做静态对比

### 8. 工具限制说明
- desktop-commander/context7/github.search_code 不可用，已改用 rg + 直接读取文件进行检索与取证。
