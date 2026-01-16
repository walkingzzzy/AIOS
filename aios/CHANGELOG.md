# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- ScreenshotAdapter: 跨平台截图功能
  - `capture_screen`: 截取全屏
  - `capture_window`: 截取当前窗口
  - `capture_region`: 截取指定区域（交互式）
  - `get_screenshot_dir`: 获取截图保存目录
- ClipboardAdapter: 跨平台剪贴板操作
  - `read_text`: 读取剪贴板文本
  - `write_text`: 写入文本到剪贴板
  - `clear`: 清空剪贴板
  - `has_text`: 检查剪贴板是否有文本
- PermissionManager: 统一权限管理
  - 5 级权限模型 (public/low/medium/high/critical)
  - 跨平台权限检查和请求
  - 权限缓存机制
- 单元测试覆盖
  - AudioAdapter 测试
  - PowerAdapter 测试
  - ScreenshotAdapter 测试
  - ClipboardAdapter 测试
  - PermissionManager 测试
  - IntentClassifier 测试

### Changed
- invoke 方法现在会进行权限检查
- ToolsView 更新以显示所有 18 个适配器
- 添加更多快速测试预设

## [0.1.0] - 2026-01-11

### Added
- 初始版本发布
- AIOS Daemon (Node.js 守护进程)
- Electron 客户端应用
- 三层 AI 协调架构 (Fast/Vision/Smart)
- 16 个系统适配器:
  - AudioAdapter: 音量控制
  - DisplayAdapter: 亮度控制
  - DesktopAdapter: 壁纸、外观模式
  - PowerAdapter: 电源管理
  - AppsAdapter: 应用管理
  - SystemInfoAdapter: 系统信息
  - FileAdapter: 文件操作
  - WindowAdapter: 窗口管理
  - BrowserAdapter: 浏览器控制
  - SpeechAdapter: 语音合成
  - NotificationAdapter: 系统通知
  - TimerAdapter: 定时器
  - CalculatorAdapter: 计算器
  - CalendarAdapter: 日历
  - WeatherAdapter: 天气查询
  - TranslateAdapter: 翻译
- JSON-RPC 2.0 通信协议
- stdio 和 WebSocket 传输支持
- 动态 AI 模型配置
- 意图分类器
- 任务编排器

### Technical
- TypeScript + Node.js 20+
- pnpm workspace monorepo
- Electron 29
- React 18
- Vitest 测试框架
