# Office 本地 UI 自动化测试手册

> **系统开发口径修订（2026-03-08）**
> AIOS 统一定义为 **AI 原生操作系统 / 系统软件工程**。本文如提及桌面应用、Electron 客户端、应用适配器、App 安装等内容，除非明确标注为“原型期 / 兼容层 / 历史实现”，否则不再代表目标形态。
> 当前最高约束：**系统镜像、系统服务、系统壳层、设备/能力抽象、权限与更新恢复**。


本文档用于在真实桌面环境中验证 OfficeLocalAdapter 的 UI 自动化能力，包括 smoke 测试、集成测试与故障注入流程。

## 适用范围

- Microsoft Office 桌面版（Windows/macOS）
- WPS Office 桌面版（Windows/macOS/Linux）
- AIOS 本地 Office UI 自动化适配器

## 前置条件

### 通用要求

- 已安装 Node.js 18+ 与 pnpm
- 已执行 `pnpm install`
- 已构建 daemon：`pnpm --filter @aios/daemon build`

### Windows

- 安装 Microsoft Office 或 WPS Office（桌面版）
- 若使用 WPS，确保可通过桌面图标启动 WPS Office

### macOS

- 安装 Microsoft Office 或 WPS Office（桌面版）
- 打开 **系统设置 → 隐私与安全性 → 辅助功能**
  - 勾选运行测试的终端应用（Terminal/iTerm）以及 Node 进程

### Linux

- 安装 WPS Office（桌面版）
- 安装依赖工具：`xdotool` 与 `xclip` 或 `xsel`
- 确保 `wps/et/wpp` 命令可用

## Smoke 测试（推荐先执行）

### 1) 执行命令

```bash
cd aios
node scripts/office-ui/office-smoke.mjs
```

### 2) 常用参数

| 环境变量 | 说明 | 示例 |
| --- | --- | --- |
| `AIOS_OFFICE_SUITES` | 指定套件列表 | `microsoft,wps` |
| `AIOS_OFFICE_KEEP_FILES` | 保留临时文件 | `1` |
| `AIOS_OFFICE_TIMEOUT_MS` | 单次请求超时 | `60000` |
| `AIOS_DAEMON_ENTRY` | 自定义 daemon 入口 | `/path/to/dist/index.js` |
| `AIOS_OFFICE_ALLOW_UNSUPPORTED` | Linux 强制跑 microsoft | `1` |

### 3) 通过标准

- 所有能力调用返回成功
- Excel 读写流程完整
- PPT 幻灯片列表可读
- 列表与删除成功（或按需保留文件）

## 集成测试（可选，需真实桌面环境）

集成测试默认关闭，仅在显式设置环境变量后执行。

### 1) 执行命令

```bash
cd aios/packages/daemon
AIOS_RUN_OFFICE_UI=1 pnpm test -- --runTestsByPath src/__tests__/integration/OfficeLocalAdapter.integration.test.ts
```

### 2) 常用参数

| 环境变量 | 说明 | 示例 |
| --- | --- | --- |
| `AIOS_RUN_OFFICE_UI` | 启用集成测试 | `1` |
| `AIOS_OFFICE_SUITES` | 指定套件列表 | `microsoft,wps` |
| `AIOS_OFFICE_TEST_TIMEOUT` | 单测超时 | `120000` |

## 故障注入流程（前台焦点 / 权限缺失 / 应用未安装）

### 1) 权限缺失

- **macOS**：在“辅助功能”中取消终端权限
- 执行：

```bash
cd aios/packages/daemon
AIOS_RUN_OFFICE_UI=1 AIOS_EXPECT_PERMISSION_DENIED=1 pnpm test -- --runTestsByPath src/__tests__/integration/OfficeLocalAdapter.integration.test.ts
```

- 期望：`word_create` 被拒绝，返回 Permission denied

### 2) 应用未安装

- 卸载/关闭目标套件（如只保留 WPS 或只保留 Office）
- 执行：

```bash
cd aios/packages/daemon
AIOS_RUN_OFFICE_UI=1 AIOS_EXPECT_APP_MISSING=1 AIOS_EXPECT_MISSING_SUITE=wps pnpm test -- --runTestsByPath src/__tests__/integration/OfficeLocalAdapter.integration.test.ts
```

- 期望：`word_create` 调用失败

### 3) 前台焦点

- 运行测试时将焦点切换到其他窗口（如浏览器）
- 执行：

```bash
cd aios/packages/daemon
AIOS_RUN_OFFICE_UI=1 AIOS_EXPECT_FOCUS_FAIL=1 pnpm test -- --runTestsByPath src/__tests__/integration/OfficeLocalAdapter.integration.test.ts
```

- 期望：`word_get_content` 失败（若仍成功，说明当前环境焦点影响不明显）

## 注意事项

- UI 自动化强依赖前台焦点与系统权限，测试期间请避免操作键盘鼠标。
- Linux 仅支持 WPS，Microsoft Office 无法运行。
- macOS 权限变更后需重新启动终端或 daemon。
- PPT 读取在 macOS/Linux 通过解压 pptx 读取 slide XML，需确保文件已保存。

## 输出与清理

- smoke 脚本默认清理临时目录，若需保留请设置 `AIOS_OFFICE_KEEP_FILES=1`。
- 集成测试使用 `/tmp` 临时目录，测试结束自动清理。
