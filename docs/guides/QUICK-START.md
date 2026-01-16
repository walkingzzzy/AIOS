# AIOS 快速入门指南

欢迎使用 AIOS（AI Operating System）！本指南将帮助你在 5 分钟内快速上手。

## 📋 目录

- [系统要求](#系统要求)
- [快速安装](#快速安装)
- [基本使用](#基本使用)
- [高级功能](#高级功能)
- [常见问题](#常见问题)

---

## 系统要求

### 支持的操作系统
- **Windows**: Windows 10 21H2+ / Windows 11
- **macOS**: macOS 13 (Ventura) 及以上
- **Linux**: Ubuntu 22.04+ / Fedora 38+

### 运行环境
- **Node.js**: 18.0.0 或更高（推荐 20+）
- **pnpm**: 8.0.0 或更高
- **内存**: 4GB RAM（推荐 8GB）
- **磁盘**: 500MB 可用空间
- **网络**: 互联网连接（用于 AI API 调用）

---

## 快速安装

### 1. 克隆项目

```bash
git clone https://github.com/aios-protocol/aios.git
cd aios
```

### 2. 安装依赖

```bash
# 安装 pnpm（如果还没有）
npm install -g pnpm

# 安装项目依赖
pnpm install
```

### 3. 构建项目

```bash
pnpm build
```

### 4. 配置环境变量

创建 `.env` 文件：

```bash
cp .env.example .env
```

编辑 `.env` 文件，添加你的 API 密钥：

```env
# AI 提供商配置（至少配置一个）
ANTHROPIC_API_KEY=your_anthropic_api_key
OPENAI_API_KEY=your_openai_api_key
GOOGLE_API_KEY=your_google_api_key

# 功能开关
AIOS_ENABLE_CACHE=true
AIOS_ENABLE_CONFIRMATION=true
```

---

## 基本使用

### 启动 AIOS

#### 方式 1: 使用客户端（推荐）

```bash
# 终端 1: 启动 Daemon
cd aios/packages/daemon
pnpm start

# 终端 2: 启动客户端
cd aios/packages/client
pnpm dev
```

然后在浏览器中打开 `http://localhost:5173`

#### 方式 2: 使用 CLI

```bash
cd aios/packages/cli
pnpm start --interactive
```

### 常用命令示例

#### 系统控制
| 命令 | 功能 |
|------|------|
| "音量调到 50" | 设置系统音量 |
| "调高音量" | 增加音量 |
| "静音" | 静音系统 |
| "屏幕亮一点" | 增加屏幕亮度 |
| "亮度设置为 80" | 设置亮度 |
| "锁屏" | 锁定屏幕 |
| "深色模式" | 切换到深色模式 |

#### 应用管理
| 命令 | 功能 |
|------|------|
| "打开 Chrome" | 启动 Chrome 浏览器 |
| "关闭 Safari" | 关闭 Safari |
| "启动计算器" | 打开计算器应用 |

#### 文件操作
| 命令 | 功能 |
|------|------|
| "读取文件 /path/to/file.txt" | 读取文件内容 |
| "列出目录 /path/to/dir" | 列出目录内容 |
| "截个图" | 截取屏幕 |

#### 实用工具
| 命令 | 功能 |
|------|------|
| "计算 (2 + 3) * 4" | 数学计算 |
| "翻译成英文：你好世界" | 文本翻译 |
| "设置 5 分钟定时器" | 设置定时器 |
| "提醒我：开会时间到了" | 发送通知 |
| "复制这段文字" | 操作剪贴板 |

#### 系统信息
| 命令 | 功能 |
|------|------|
| "获取系统信息" | 查看系统信息 |
| "查看 CPU 使用率" | 查看 CPU 状态 |
| "查看内存使用情况" | 查看内存状态 |

---

## 高级功能

### 1. 视觉任务

AIOS 可以分析屏幕内容：

```
屏幕上有什么
分析当前界面
识别这个按钮
```

### 2. 复杂任务

AIOS 会自动分解复杂任务并显示任务板：

```
分析系统性能并生成报告
首先获取 CPU 使用率，然后获取内存使用率，最后生成总结
```

### 3. 代码生成

AIOS 可以生成代码并在 Artifact 中渲染：

```
写一个 Python 函数计算斐波那契数列
创建一个 HTML 页面展示个人简历
写一个 React 组件显示待办事项
```

### 4. 语音输入

点击输入框旁边的麦克风图标使用语音输入：

1. 点击麦克风图标 🎤
2. 说出你的指令
3. 系统自动识别并执行

### 5. 高危操作确认

对于高危操作，AIOS 会要求确认：

```
删除所有临时文件
关机
重启系统
```

系统会显示：
- 风险等级（中等/高/严重）
- 操作详情
- 自动超时拒绝（30秒）

### 6. 工具箱

在客户端的"工具"页面，可以：
- 查看所有 31 个可用适配器
- 测试各项功能
- 查看执行历史
- 快速测试预设命令

---

## 配置 AI 模型

### 在客户端设置

1. 点击左侧导航栏的"设置"
2. 配置三层 AI 模型：

#### Fast 层（快速响应）
- **推荐**: Claude 3 Haiku
- **备选**: GPT-3.5-turbo, Gemini 1.5 Flash

#### Vision 层（视觉理解）
- **推荐**: Claude 3 Sonnet
- **备选**: GPT-4 Vision, Gemini 1.5 Pro

#### Smart 层（复杂推理）
- **推荐**: Claude 3 Opus
- **备选**: GPT-4, Gemini 2.0 Flash

### 使用环境变量

```bash
# Fast 层
export AIOS_FAST_PROVIDER=anthropic
export AIOS_FAST_MODEL=claude-3-haiku-20240307

# Vision 层
export AIOS_VISION_PROVIDER=anthropic
export AIOS_VISION_MODEL=claude-3-sonnet-20240229

# Smart 层
export AIOS_SMART_PROVIDER=anthropic
export AIOS_SMART_MODEL=claude-3-opus-20240229
```

---

## 性能优化

### 启用缓存

```env
# 启用缓存以提高性能和降低成本
AIOS_CACHE_ENABLED=true
AIOS_CACHE_SIZE=100
AIOS_CACHE_TTL=3600000  # 1小时
```

**效果**:
- 意图分析性能提升 5-10x
- AI 调用成本节省 30-40%
- 相同查询响应时间从 2-3s 降低到 <100ms

### 调整并发设置

```env
# O-W 模式并行数（1-5）
AIOS_OW_WORKERS=3
```

---
---

## 常见问题

### Q: 如何获取 API 密钥？

**Anthropic (Claude)**:
1. 访问 https://console.anthropic.com
2. 注册账号并登录
3. 在 API Keys 页面创建密钥

**OpenAI (GPT)**:
1. 访问 https://platform.openai.com
2. 注册账号并登录
3. 在 API Keys 页面创建密钥

**Google (Gemini)**:
1. 访问 https://makersuite.google.com
2. 注册账号并登录
3. 获取 API 密钥

### Q: 音量/亮度控制不工作？

**macOS**:
1. 打开"系统偏好设置" → "安全性与隐私" → "隐私" → "辅助功能"
2. 添加 AIOS 应用并授予权限

**Linux**: 安装必要的系统工具：
```bash
# Ubuntu/Debian
sudo apt install pactl xrandr

# Fedora
sudo dnf install pulseaudio-utils xrandr
```

**Windows**:
- 确保以管理员权限运行 AIOS

### Q: 截图功能不工作？

**macOS**:
1. 打开"系统偏好设置" → "安全性与隐私" → "隐私" → "屏幕录制"
2. 添加 AIOS 应用并授予权限

**Linux**: 安装截图工具：
```bash
# Ubuntu/Debian
sudo apt install gnome-screenshot
# 或
sudo apt install scrot
```

### Q: AI 响应很慢？

可能的原因和解决方案：

1. **网络问题**: 检查网络连接
2. **API 限流**: 等待一段时间后重试
3. **缓存未启用**:
   ```env
   AIOS_CACHE_ENABLED=true
   ```
4. **模型选择**: 使用更快的模型（如 Haiku）

### Q: 如何查看日志？

```bash
# Daemon 日志
cd aios/packages/daemon
pnpm start --log-level debug

# 客户端日志
# 打开浏览器开发者工具 (F12)
# 查看 Console 标签
```

### Q: 如何重置配置？

```bash
# 删除配置文件
rm .env
rm aios.db

# 重新配置
cp .env.example .env
# 编辑 .env 文件添加 API 密钥
```

### Q: 支持哪些语言？

AIOS 目前支持：
- 中文（简体）
- 英文

更多语言支持正在开发中。

### Q: 如何更新 AIOS？

```bash
# 拉取最新代码
git pull origin main

# 安装新依赖
pnpm install

# 重新构建
pnpm build

# 重启服务
pnpm start
```

### Q: 为什么某些功能需要确认？

AIOS 使用 5 级权限模型保护系统安全：

- **Public**: 无需权限（计算器、翻译）
- **Low**: 低风险（通知、语音）
- **Medium**: 中等风险（应用管理、网络）
- **High**: 高风险（文件操作、浏览器）
- **Critical**: 严重风险（电源管理、系统关机）

高风险和严重风险操作会触发确认对话框。

---

## 权限配置

### macOS 权限

首次使用需要授予以下权限：

1. **辅助功能权限**（必需）
   - 系统偏好设置 → 安全性与隐私 → 隐私 → 辅助功能
   - 添加 AIOS 应用

2. **屏幕录制权限**（截图功能需要）
   - 系统偏好设置 → 安全性与隐私 → 隐私 → 屏幕录制
   - 添加 AIOS 应用

3. **麦克风权限**（语音输入需要）
   - 系统偏好设置 → 安全性与隐私 → 隐私 → 麦克风
   - 添加浏览器应用

### Linux 权限

```bash
# 音频控制
sudo usermod -aG audio $USER

# 亮度控制
sudo usermod -aG video $USER

# 重新登录以应用权限
```

### Windows 权限

- 以管理员权限运行 AIOS
- 允许防火墙访问（如果提示）

---

## 故障排除

### 问题: 无法连接到 Daemon

**解决方案**:
1. 确保 Daemon 正在运行
2. 检查端口是否被占用：
   ```bash
   lsof -i :3000
   ```
3. 更改端口：
   ```env
   AIOS_PORT=3001
   ```

### 问题: 模块未找到错误

**解决方案**:
```bash
# 清理并重新安装
rm -rf node_modules
rm pnpm-lock.yaml
pnpm install
pnpm build
```

### 问题: 构建失败

**解决方案**:
```bash
# 检查 Node.js 版本
node --version  # 应该 >= 18.0.0

# 检查 pnpm 版本
pnpm --version  # 应该 >= 8.0.0

# 清理缓存
pnpm store prune
pnpm install
```

### 问题: API 调用失败

**解决方案**:
1. 检查 API 密钥是否正确
2. 检查网络连接
3. 查看 API 配额是否用完
4. 在设置页面测试连接

---

## 下一步

### 学习更多

- 📖 [完整文档](../README.md)
- 🏗️ [架构设计](../../dev/06-三层AI协调设计方案.md)
- 🔧 [适配器开发](../adapters/01-Development.md)
- 📡 [API 文档](../api/Reference.md)
- 🎯 [实现进度](../IMPLEMENTATION_PROGRESS.md)

### 参与贡献

- 🐛 [报告 Bug](https://github.com/aios-protocol/aios/issues)
- 💡 [提出建议](https://github.com/aios-protocol/aios/discussions)
- 🤝 [贡献代码](../../CONTRIBUTING.md)

### 获取帮助

- **GitHub Issues**: https://github.com/aios-protocol/aios/issues
- **Discussions**: https://github.com/aios-protocol/aios/discussions
- **Email**: support@aios.dev

---

## 性能基准

### 响应时间

| 操作类型 | 平均响应时间 | 缓存命中时 |
|---------|-------------|-----------|
| 简单命令 | ~100ms | <10ms |
| 视觉任务 | ~2s | <100ms |
| 复杂任务 | ~5s | <500ms |

### 资源使用

| 资源 | 空闲时 | 运行时 | 峰值 |
|------|--------|--------|------|
| 内存 | ~200MB | ~500MB | ~2GB |
| CPU | <1% | 20-50% | 80-100% |

---

## 安全建议

### 1. 保护 API 密钥

```bash
# 不要提交 .env 文件到 Git
echo ".env" >> .gitignore

# 使用环境变量
export ANTHROPIC_API_KEY=your_key
```

### 2. 限制权限

在设置中禁用不需要的高危权限：
- 文件删除
- 系统关机
- 网络访问

### 3. 启用确认

```env
# 启用高危操作确认
AIOS_ENABLE_CONFIRMATION=true
```

### 4. 定期更新

```bash
# 定期检查更新
git pull origin main
pnpm install
pnpm build
```

### 5. 审查日志

定期检查 `aios.db` 中的操作日志，确保没有异常活动。

---

**祝你使用愉快！** 🎉

如有问题，请随时在 [GitHub Issues](https://github.com/aios-protocol/aios/issues) 中提问。
