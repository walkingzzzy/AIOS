## 项目上下文摘要（本地 Office UI 自动化适配器）
生成时间：2026-01-24 18:08:28

### 1. 相似实现分析
- **实现1**: aios/packages/daemon/src/adapters/system/DesktopAdapter.ts
  - 模式：参数校验 + 平台分支 + osascript/xdotool/PowerShell 执行
  - 可复用：跨平台脚本调用、错误提示中文化、能力参数定义风格
  - 需注意：Windows 下使用 PowerShell SendKeys，Linux 使用 xdotool

- **实现2**: aios/packages/daemon/src/adapters/apps/WindowAdapter.ts
  - 模式：键盘快捷键驱动窗口管理，checkAvailability 校验工具可用性
  - 可复用：runPlatformCommand 与平台级快捷键策略
  - 需注意：macOS 依赖辅助功能授权，Linux 依赖 xdotool

- **实现3**: aios/packages/daemon/src/adapters/apps/AppsAdapter.ts
  - 模式：应用启动/关闭与应用扫描，使用 open/ps-list
  - 可复用：打开应用/URL 的启动方式
  - 需注意：以名称启动应用、跨平台兼容

- **实现4**: aios/packages/daemon/src/adapters/clipboard/ClipboardAdapter.ts
  - 模式：跨平台剪贴板读写，使用 pbcopy/pbpaste、PowerShell、xclip/xsel
  - 可复用：剪贴板读写命令与错误处理逻辑
  - 需注意：Linux 需 xclip/xsel

### 2. 项目约定
- **命名约定**: 能力使用 snake_case，类/方法使用 camelCase
- **文件组织**: 适配器位于 aios/packages/daemon/src/adapters/<domain>/，测试位于 aios/packages/daemon/src/__tests__/adapters/
- **导入顺序**: type 导入 → 第三方/共享模块 → 本地模块
- **代码风格**: TypeScript，错误信息中文，switch 分发，参数校验 guard

### 3. 可复用组件清单
- aios/packages/shared/src/utils/command.ts: runPlatformCommand/runCommand/spawnBackground
- aios/packages/daemon/src/adapters/system/DesktopAdapter.ts: 平台脚本执行方式
- aios/packages/daemon/src/adapters/clipboard/ClipboardAdapter.ts: 剪贴板读写命令

### 4. 测试策略
- **测试框架**: Vitest
- **测试模式**: 单元测试 + mock 外部命令
- **参考文件**: aios/packages/daemon/src/__tests__/adapters/DesktopAdapter.test.ts
- **覆盖要求**: 参数校验 + 平台命令调用 + 失败路径

### 5. 依赖和集成点
- **外部依赖**: osascript (macOS), PowerShell (Windows), xdotool/xclip/xsel (Linux)
- **内部依赖**: BaseAdapter, runPlatformCommand, App/Window/Clipboard 控制模式
- **集成方式**: ToolExecutor 通过 adapter.capabilities 暴露工具
- **配置来源**: 平台可用性检测与默认应用名称

### 6. 技术选型理由
- **为什么用这个方案**: 现有系统适配器已使用平台脚本，可复用到本地 UI 自动化
- **优势**: 无需新增依赖，跨平台可用
- **劣势和风险**: UI 自动化对前台焦点/快捷键敏感，稳定性受环境影响

### 7. 关键风险点
- **并发问题**: UI 自动化需串行执行，避免焦点冲突
- **边界条件**: 应用未安装、权限不足、快捷键冲突
- **性能瓶颈**: 多步骤 UI 操作延迟较大
- **安全考虑**: 需要对路径/输入做校验，避免命令注入
