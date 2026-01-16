# AIOS Protocol 快速入门指南

## 系统要求

### 支持的操作系统
- **Windows**: Windows 10 21H2+ / Windows 11
- **macOS**: macOS 13 (Ventura) 及以上
- **Linux**: Ubuntu 22.04+ / Fedora 38+

### 运行环境
- Node.js 20+
- pnpm 8+

## 安装

### 1. 克隆项目

```bash
git clone https://github.com/aios-protocol/aios.git
cd aios
```

### 2. 安装依赖

```bash
pnpm install
```

### 3. 构建项目

```bash
pnpm build
```

## 配置 AI 模型

AIOS 使用三层 AI 架构，需要配置 API Key：

### 方式一：环境变量

```bash
# Fast 层 (简单指令)
export AIOS_FAST_PROVIDER=openai
export AIOS_FAST_MODEL=gpt-4o-mini
export OPENAI_API_KEY=sk-xxx

# Vision 层 (视觉分析)
export AIOS_VISION_PROVIDER=google
export AIOS_VISION_MODEL=gemini-2.0-flash
export GOOGLE_API_KEY=xxx

# Smart 层 (复杂推理)
export AIOS_SMART_PROVIDER=anthropic
export AIOS_SMART_MODEL=claude-sonnet-4-20250514
export ANTHROPIC_API_KEY=xxx
```

### 方式二：客户端设置

启动客户端后，在设置界面配置 AI 模型。

## 启动

### 启动 Daemon

```bash
cd aios/packages/daemon
pnpm start
```

### 启动客户端

```bash
cd aios/packages/client
pnpm dev
```

## 基本使用

### 自然语言命令示例

| 说法 | 功能 |
|------|------|
| "音量调到 50" | 设置系统音量 |
| "屏幕亮一点" | 增加屏幕亮度 |
| "打开 Chrome" | 启动 Chrome 浏览器 |
| "锁屏" | 锁定屏幕 |
| "截个图" | 截取屏幕 |
| "复制这段文字" | 操作剪贴板 |

### 工具箱

在客户端的"工具"页面，可以：
- 查看所有可用适配器
- 测试各项功能
- 查看执行历史

## macOS 权限配置

首次使用需要授予以下权限：

1. **辅助功能权限**
   - 系统偏好设置 → 安全性与隐私 → 隐私 → 辅助功能
   - 添加 AIOS 应用

2. **屏幕录制权限**（截图功能需要）
   - 系统偏好设置 → 安全性与隐私 → 隐私 → 屏幕录制
   - 添加 AIOS 应用

## 常见问题

### Q: 音量/亮度控制不工作？

**macOS**: 确保已授予辅助功能权限。

**Linux**: 安装必要的系统工具：
```bash
# Ubuntu/Debian
sudo apt install pactl xrandr

# Fedora
sudo dnf install pulseaudio-utils xrandr
```

### Q: 截图功能不工作？

**macOS**: 需要屏幕录制权限。

**Linux**: 安装截图工具：
```bash
# Ubuntu/Debian
sudo apt install gnome-screenshot
# 或
sudo apt install scrot
```

### Q: AI 响应很慢？

检查网络连接和 API Key 配置。可以在设置界面测试连接。

## 下一步

- 查看 [适配器开发指南](../adapters/01-Development.md)
- 了解 [三层 AI 架构](../../dev/06-三层AI协调设计方案.md)
- 阅读 [API 文档](../api/)
