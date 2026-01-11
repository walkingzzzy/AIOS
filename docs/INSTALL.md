# AIOS Protocol macOS 安装指南

本文档介绍如何在 macOS 上安装和配置 AIOS Protocol 的**参考实现**。

> **协议 vs 参考实现**：AIOS Protocol 是开放标准协议（见 [protocol/](protocol/) 目录），本文档描述的是 macOS 平台的参考实现。任何人都可以基于协议规范开发自己的实现。

## 系统要求

| 项目 | 要求 |
|------|------|
| **操作系统** | macOS 13.0 (Ventura) 或更高版本 |
| **处理器** | Apple Silicon (M1/M2/M3) 或 Intel |
| **内存** | 4GB RAM（建议 8GB+） |
| **存储** | 100MB 可用空间 |

## 安装步骤

### 方式一：DMG 安装（推荐）

1. **下载 DMG 文件**
   - 从 [Releases](https://github.com/aios-protocol/aios-macos/releases) 页面下载最新版本的 `AIOS-x.x.x.dmg`

2. **打开 DMG 文件**
   - 双击下载的 DMG 文件
   - 将 AIOS 拖拽到 Applications 文件夹

3. **首次启动**
   - 打开 Applications 文件夹
   - 右键点击 AIOS，选择"打开"
   - 在安全提示中点击"打开"（首次运行需要）

4. **配置权限**
   - 按照首次运行向导完成权限配置
   - 详见下方 [权限配置](#权限配置) 部分

### 方式二：从源码构建

#### 前置要求

- Xcode 15.0+ 或 Xcode Command Line Tools
- Swift 5.9+

#### 构建步骤

```bash
# 克隆仓库
git clone https://github.com/aios-protocol/aios-macos.git
cd aios-macos

# 构建 Debug 版本
./scripts/build.sh debug

# 或构建 Release 版本
./scripts/build.sh release

# 运行 CLI
cd daemon && swift run aios-cli

# 运行 Daemon
cd daemon && swift run aios-daemon
```

## 权限配置

AIOS 需要以下系统权限才能完整工作：

### 必需权限

| 权限 | 用途 | 如何授予 |
|------|------|---------|
| **辅助功能** | 窗口控制、UI 自动化 | 系统设置 → 隐私与安全性 → 辅助功能 → 添加 AIOS |
| **自动化** | 控制其他应用程序 | 首次使用时系统会自动弹窗请求 |

### 可选权限

| 权限 | 用途 | 如何授予 |
|------|------|---------|
| **屏幕录制** | 截图、屏幕共享 | 系统设置 → 隐私与安全性 → 屏幕录制 |
| **位置服务** | 获取 WiFi 网络名称 (SSID) | 系统设置 → 隐私与安全性 → 位置服务 |
| **麦克风** | 语音输入（未来功能） | 系统设置 → 隐私与安全性 → 麦克风 |

### 权限配置向导

首次启动 AIOS 时，会自动显示权限配置向导，引导您完成必要的权限设置。

> ⚠️ **注意**：如果跳过某些权限，相关功能可能无法使用。您可以随时在系统设置中添加权限。

## AI 引擎配置

AIOS 支持多种 AI 引擎，您可以根据需要选择配置：

### Claude API（推荐）

1. 访问 [Anthropic Console](https://console.anthropic.com/) 获取 API Key
2. 设置环境变量：

```bash
export ANTHROPIC_API_KEY="your-api-key-here"
```

或在 AIOS 设置界面中配置。

### Ollama（本地运行）

1. 安装 Ollama：

```bash
brew install ollama
```

2. 启动 Ollama 服务：

```bash
ollama serve
```

3. 下载模型（推荐 llama3.2 或 qwen2.5）：

```bash
ollama pull llama3.2
```

4. 在 AIOS 设置中选择 Ollama 引擎

### OpenAI 兼容 API

支持任何 OpenAI 兼容的 API 服务（如 DeepSeek、智谱等）：

1. 在设置中选择"OpenAI Compatible"
2. 配置 API Base URL 和 API Key
3. 选择模型名称

## 开机自启动

### 启用开机自启动

1. 打开 AIOS
2. 进入 设置 → 通用
3. 勾选"开机时自动启动"

### 手动配置 LaunchAgent

```bash
# 复制 LaunchAgent 配置
cp /Applications/AIOS.app/Contents/Resources/LaunchAgents/com.aios.daemon.plist \
   ~/Library/LaunchAgents/

# 加载服务
launchctl load ~/Library/LaunchAgents/com.aios.daemon.plist

# 启动服务
launchctl start com.aios.daemon
```

### 停止和卸载

```bash
# 停止服务
launchctl stop com.aios.daemon

# 卸载服务
launchctl unload ~/Library/LaunchAgents/com.aios.daemon.plist
```

## 卸载

### 完全卸载

1. 退出 AIOS 应用
2. 停止后台服务：

```bash
launchctl stop com.aios.daemon
launchctl unload ~/Library/LaunchAgents/com.aios.daemon.plist
```

3. 删除应用：

```bash
rm -rf /Applications/AIOS.app
```

4. 删除配置文件（可选）：

```bash
rm -rf ~/Library/Application\ Support/AIOS
rm -rf ~/Library/Preferences/com.aios.*
rm ~/Library/LaunchAgents/com.aios.*.plist
```

5. 移除权限（可选）：
   - 系统设置 → 隐私与安全性 → 各权限类别 → 移除 AIOS

## 故障排除

### 应用无法打开

**症状**：双击应用后无响应或提示"无法打开"

**解决方案**：
1. 右键点击应用，选择"打开"
2. 如仍无法打开，检查系统设置 → 隐私与安全性 → 安全性 → 点击"仍要打开"

### 功能不工作

**症状**：语音命令无响应、窗口控制失败等

**解决方案**：
1. 检查对应权限是否已授予
2. 打开 AIOS 设置，查看权限状态
3. 如权限显示"受限"，按照提示重新授权

### AI 无法响应

**症状**：发送消息后无 AI 回复

**解决方案**：
1. 检查网络连接
2. 验证 API Key 是否正确
3. 如使用 Ollama，确认服务已启动：`ollama serve`
4. 查看日志：`/tmp/aios-daemon.log`

### 查看日志

```bash
# 查看 Daemon 日志
tail -f /tmp/aios-daemon.log

# 查看错误日志
tail -f /tmp/aios-daemon.error.log
```

## 获取帮助

- **文档**：[docs/](https://github.com/aios-protocol/aios-macos/tree/main/docs)
- **问题反馈**：[GitHub Issues](https://github.com/aios-protocol/aios-macos/issues)
- **讨论区**：[GitHub Discussions](https://github.com/aios-protocol/aios-macos/discussions)

---

**版本**: 2.0.0-alpha  
**更新日期**: 2026-01-09
