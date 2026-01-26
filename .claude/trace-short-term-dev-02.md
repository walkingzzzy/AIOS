# 短期开发计划逐条勾稽清单（仅依据 dev/02-短期开发计划.md）
时间：2026-01-24 22:34:50

## 依据文档
- `dev/02-短期开发计划.md`

## 勾稽说明
- 状态：✅ 完成 / ⚠️ 部分完成 / ❌ 未完成
- 证据：对应实现的代码或配置路径

---

## 1. 阶段一核心目标（1.1）
- ✅ 系统设置控制（音量/亮度/壁纸/外观）
  - 证据：`aios/packages/daemon/src/adapters/system/AudioAdapter.ts`、`aios/packages/daemon/src/adapters/system/DisplayAdapter.ts`、`aios/packages/daemon/src/adapters/system/DesktopAdapter.ts`
- ✅ 文件管理
  - 证据：`aios/packages/daemon/src/adapters/system/FileAdapter.ts`
- ✅ 进程控制/应用启动关闭/监控
  - 证据：`aios/packages/daemon/src/adapters/apps/AppsAdapter.ts`
- ✅ 电源管理
  - 证据：`aios/packages/daemon/src/adapters/system/PowerAdapter.ts`
- ⚠️ 窗口管理
  - 证据：`aios/packages/daemon/src/adapters/apps/WindowAdapter.ts`（实现存在，但技术方案与计划不同）
- ✅ AI 交互（自然语言、多轮）
  - 证据：`aios/packages/daemon/src/ai/AIRouter.ts`、`aios/packages/daemon/src/core/TaskOrchestrator.ts`、`aios/packages/client/src/renderer/src/views/ChatView.tsx`

## 2. 技术栈（1.2）
- ⚠️ Node.js 20+ 约束
  - 证据：未见显式 engines 配置（需补充）
- ✅ TypeScript 5.x
  - 证据：`aios/packages/daemon/package.json`、`aios/packages/client/package.json`
- ✅ stdio / WebSocket IPC
  - 证据：`aios/packages/daemon/src/core/transports/StdioTransport.ts`、`aios/packages/daemon/src/core/transports/WebSocketTransport.ts`
- ✅ Electron 客户端
  - 证据：`aios/packages/client/package.json`、`aios/packages/client/src/main/index.ts`
- ✅ 三层云端 AI
  - 证据：`aios/packages/daemon/src/ai/AIRouter.ts`、`aios/packages/daemon/src/index.ts`

## 3. 跨平台依赖（1.3）
- ✅ loudness / brightness / wallpaper / open / ps-list / systeminformation / playwright
  - 证据：`aios/packages/daemon/package.json`
- ❌ @nut-tree/nut-js
  - 证据：依赖缺失且实现未使用

## 4. 系统 API 映射（2.2）
- ✅ 音频控制（get/set/mute）
  - 证据：`aios/packages/daemon/src/adapters/system/AudioAdapter.ts`
- ✅ 显示控制（亮度）
  - 证据：`aios/packages/daemon/src/adapters/system/DisplayAdapter.ts`
- ✅ 桌面设置（壁纸/外观）
  - 证据：`aios/packages/daemon/src/adapters/system/DesktopAdapter.ts`
- ✅ 电源管理（锁屏/休眠/关机/重启）
  - 证据：`aios/packages/daemon/src/adapters/system/PowerAdapter.ts`
- ✅ 应用管理（打开/进程/关闭）
  - 证据：`aios/packages/daemon/src/adapters/apps/AppsAdapter.ts`
- ⚠️ 窗口管理（计划为 nut.js）
  - 证据：`aios/packages/daemon/src/adapters/apps/WindowAdapter.ts`
- ✅ 系统信息
  - 证据：`aios/packages/daemon/src/adapters/system/SystemInfoAdapter.ts`

## 5. Sprint 1：项目骨架 + AI 引擎（3.2）
- ✅ 项目初始化（TS + pnpm workspace）
  - 证据：`aios/pnpm-workspace.yaml`、`aios/tsconfig.json`
- ✅ AI 引擎接口
  - 证据：`aios/packages/daemon/src/ai/AIEngine.ts`
- ✅ 意图分类器
  - 证据：`aios/packages/daemon/src/ai/IntentClassifier.ts`
- ✅ 三层路由器
  - 证据：`aios/packages/daemon/src/ai/AIRouter.ts`
- ⚠️ GPT-4o-mini 适配器（实现方式不同）
  - 证据：`aios/packages/daemon/src/ai/engines/OpenAICompatibleEngine.ts`（未见 GPTMiniAdapter.ts）
- ✅ Claude 适配器
  - 证据：`aios/packages/daemon/src/ai/engines/AnthropicEngine.ts`
- ✅ 命令行客户端
  - 证据：`aios/packages/cli/src/index.ts`

## 6. Sprint 2：Daemon + IPC（3.3）
- ✅ JSON-RPC 解析
  - 证据：`aios/packages/daemon/src/core/JSONRPCHandler.ts`
- ✅ stdio 通信
  - 证据：`aios/packages/daemon/src/core/transports/StdioTransport.ts`
- ✅ WebSocket 通信
  - 证据：`aios/packages/daemon/src/core/transports/WebSocketTransport.ts`
- ⚠️ 消息路由
  - 证据：`aios/packages/daemon/src/core/TaskOrchestrator.ts`（无 Router.ts，需确认设计对应关系）
- ✅ 适配器接口
  - 证据：`aios/packages/daemon/src/adapters/BaseAdapter.ts`、`aios/packages/shared/src/types/adapter.ts`
- ❌ 健康检查
  - 证据：未见 HealthCheck.ts 或相关实现

## 7. Sprint 3：基础系统控制（3.4）
- ✅ AudioAdapter / DisplayAdapter / DesktopAdapter
  - 证据：`aios/packages/daemon/src/adapters/system/*.ts`

## 8. Sprint 4：应用管理 + 电源控制（3.5）
- ✅ AppsAdapter / PowerAdapter
  - 证据：`aios/packages/daemon/src/adapters/apps/AppsAdapter.ts`、`aios/packages/daemon/src/adapters/system/PowerAdapter.ts`

## 9. Sprint 5：文件管理 + 系统信息（3.6）
- ✅ FileAdapter / SystemInfoAdapter
  - 证据：`aios/packages/daemon/src/adapters/system/FileAdapter.ts`、`aios/packages/daemon/src/adapters/system/SystemInfoAdapter.ts`

## 10. Sprint 6：窗口管理 + 浏览器控制（3.7）
- ⚠️ WindowAdapter（方案偏离）
  - 证据：`aios/packages/daemon/src/adapters/apps/WindowAdapter.ts`
- ✅ BrowserAdapter（Playwright）
  - 证据：`aios/packages/daemon/src/adapters/browser/BrowserAdapter.ts`

## 11. Sprint 7：Electron 客户端（3.8）
- ✅ 主界面（对话）
  - 证据：`aios/packages/client/src/renderer/src/views/ChatView.tsx`
- ✅ 系统托盘
  - 证据：`aios/packages/client/src/main/index.ts`
- ✅ 快速启动器
  - 证据：`aios/packages/client/src/main/index.ts`、`aios/packages/client/src/renderer/src/views/ChatView.tsx`
- ✅ 设置界面（AI 配置）
  - 证据：`aios/packages/client/src/renderer/src/views/SettingsView.tsx`
- ❌ 工具卡片面板
  - 证据：未发现 ToolCardsPanel/ToolCard/ToolTestDialog 相关实现

## 12. Sprint 8：高级功能 + 测试（3.9）
- ✅ ScreenshotAdapter / ClipboardAdapter
  - 证据：`aios/packages/daemon/src/adapters/screenshot/ScreenshotAdapter.ts`、`aios/packages/daemon/src/adapters/clipboard/ClipboardAdapter.ts`
- ⚠️ 单元测试/集成测试
  - 证据：存在部分适配器单测 `aios/packages/daemon/src/__tests__/adapters/*.test.ts`，端到端覆盖仍需补充

## 13. Sprint 9：发布准备（3.10）
- ✅ Electron 打包
  - 证据：`aios/packages/client/package.json`（electron-builder 配置）
- ❌ 代码签名
  - 证据：未见签名配置或证书说明
- ⚠️ 用户文档
  - 证据：`docs/INSTALL.md`、`docs/guides/QUICK-START.md` 存在，但未对照验收要求逐条确认
- ✅ 发布说明
  - 证据：`CHANGELOG.md`

## 14. 功能清单（Phase 1）与验收标准（7.1）
- ✅ 音量控制/亮度控制/应用管理/窗口管理/文件操作
  - 证据：对应适配器实现见上述条目

