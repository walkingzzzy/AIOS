## 项目上下文摘要（本地 Office 全覆盖能力与测试补齐）
生成时间：2025-09-02 00:00:00

### 1. 相似实现分析
- **实现1**: /Users/mac/Desktop/AIOS/aios/packages/daemon/src/adapters/office/OfficeLocalAdapter.ts
  - 模式：BaseAdapter + capabilities 列表 + invoke 分发，按平台区分 Windows COM 与 UI 自动化。
  - 可复用：`normalizeFilePath`、`ensureFileExists`、`validateRange`、`validateValues`、`runUiSequence`、`saveAsUi`、`goToRangeUi`。
  - 需注意：路径白名单与敏感路径校验必须先执行；UI 自动化依赖快捷键与前台焦点。

- **实现2**: /Users/mac/Desktop/AIOS/aios/packages/daemon/src/adapters/productivity/Microsoft365Adapter.ts
  - 模式：能力清单 + invoke 分发 + API 调用封装；测试用例以模拟 fetch 覆盖能力列表与错误分支。
  - 可复用：能力命名规范、测试结构（能力列表校验 + 正常/异常流程）。
  - 需注意：命名保持与 OfficeLocalAdapter 一致，避免能力 ID 漂移。

- **实现3**: /Users/mac/Desktop/AIOS/aios/packages/daemon/src/adapters/cn/WpsAirScriptAdapter.ts
  - 模式：能力清单 + 参数校验 + success/failure 统一返回。
  - 可复用：参数必填校验与错误码模式。
  - 需注意：错误码与消息必须中文，且与 BaseAdapter 的 failure 约定一致。

### 2. 项目约定
- **命名约定**: 能力 ID 使用英文小写下划线（如 word_create），类名使用 PascalCase。
- **文件组织**: 适配器位于 packages/daemon/src/adapters 下，测试位于 packages/daemon/src/__tests__。
- **导入顺序**: 先内置模块，再第三方，再本地模块。
- **代码风格**: TypeScript，2/4 空格缩进保持现状；所有注释与说明为简体中文。

### 3. 可复用组件清单
- `/Users/mac/Desktop/AIOS/aios/packages/daemon/src/adapters/office/OfficeLocalAdapter.ts`: UI 自动化流程与路径校验工具。
- `/Users/mac/Desktop/AIOS/aios/packages/daemon/src/adapters/BaseAdapter.ts`: success/failure 统一封装。
- `/Users/mac/Desktop/AIOS/aios/packages/daemon/src/__tests__/adapters/Microsoft365Adapter.test.ts`: 能力列表与 invoke 测试结构模板。

### 4. 测试策略
- **测试框架**: Vitest。
- **测试模式**: 单元测试 + 集成测试（可通过环境变量控制执行）+ scripts/office-ui/office-smoke.mjs smoke。
- **参考文件**: /Users/mac/Desktop/AIOS/aios/packages/daemon/src/__tests__/adapters/OfficeLocalAdapter.test.ts，/Users/mac/Desktop/AIOS/aios/packages/daemon/src/__tests__/integration/OfficeLocalAdapter.integration.test.ts。
- **覆盖要求**: 能力列表完整性、Windows 分支使用 PowerShell、UI 分支基本调用、错误路径与权限校验。

### 5. 依赖和集成点
- **外部依赖**: PowerShell/COM（Windows）、AppleScript/xdotool/xclip（macOS/Linux）、LibreOffice/soffice（PDF 导出）。
- **内部依赖**: BaseAdapter、spawnBackground（@aios/shared）。
- **集成方式**: invoke 路由调用，本地文件路径校验，UI 自动化调用。
- **配置来源**: 环境变量 AIOS_RUN_OFFICE_UI、AIOS_OFFICE_SUITES、AIOS_OFFICE_TIMEOUT_MS 等。

### 6. 技术选型理由
- **为什么用这个方案**: 保持与现有 OfficeLocalAdapter 模式一致，实现跨平台与多套件支持。
- **优势**: 最小引入新依赖，复用现有 UI 自动化与 Windows COM 方案。
- **劣势和风险**: UI 快捷键与套件差异导致不稳定，Linux 依赖 WPS 安装与桌面权限。

### 7. 关键风险点
- **并发问题**: UI 自动化操作需串行执行，依赖前台窗口。
- **边界条件**: 文档不存在、路径不合法、range 格式错误、图片不存在。
- **性能瓶颈**: UI 自动化步骤较慢；大范围表格读写可能耗时。
- **安全考虑**: 路径白名单与敏感路径限制必须保持严格。

### 工具与资料检索异常记录
- context7 与 github.search_code 在当前环境不可用，已改用本地 rg/sed 检索与现有实现比对。
- desktop-commander 工具不可用，已用 shell_command 替代，并在 operations-log 记录。
