# Ubuntu AI 操作系统技术研究报告

**版本**: 0.6.0  
**更新日期**: 2026-01-07  
**目标平台**: Ubuntu Linux (GNOME Desktop)  
**文档类型**: 📖 技术研究（平台支持参考）

> [!NOTE]
> 本文档研究了 Ubuntu 系统的 AI 集成技术，用于指导 AIOS 在 Ubuntu 上的实现。
> 正式的 AIOS 协议规范请参见 [protocol/](../protocol/) 目录。

---

## 一、Ubuntu 系统控制 API 研究

### 1.1 D-Bus 通信机制

D-Bus 是 Linux 桌面的核心进程间通信 (IPC) 系统，所有系统服务都通过它暴露 API。

| 总线类型 | 用途 | 示例服务 |
|---------|------|---------|
| **System Bus** | 系统级服务 | systemd, NetworkManager, UPower |
| **Session Bus** | 用户会话服务 | GNOME Shell, dconf, 应用程序 |

**关键工具**:
- `dbus-send` - 命令行发送 D-Bus 消息
- `busctl` - systemd 的 D-Bus 工具
- `gdbus` - GLib 的 D-Bus 工具
- `qdbus` - Qt 的 D-Bus 工具

### 1.2 设置管理 (gsettings/dconf)

```
┌─────────────────────────────────────────┐
│            GSettings API                │  ← 高级接口
├─────────────────────────────────────────┤
│              dconf                      │  ← 后端存储
├─────────────────────────────────────────┤
│          D-Bus Session Bus              │  ← 通信层
└─────────────────────────────────────────┘
```

**常用设置路径**:
- 壁纸: `org.gnome.desktop.background picture-uri`
- 主题: `org.gnome.desktop.interface gtk-theme`
- 语言: `org.gnome.system.locale region`

### 1.3 systemd 电源管理 API

通过 `org.freedesktop.login1` D-Bus 接口:

| 操作 | D-Bus 方法 |
|------|-----------|
| 关机 | `PowerOff(interactive)` |
| 重启 | `Reboot(interactive)` |
| 休眠 | `Suspend(interactive)` |
| 锁屏 | `LockSession(id)` |

### 1.4 NetworkManager API

- **D-Bus 服务**: `org.freedesktop.NetworkManager`
- **Python 库**: `python-networkmanager`, `libnm` (GObject introspection)
- **命令行**: `nmcli`

**功能**: WiFi 扫描、连接、断开、VPN 管理等

### 1.5 音频控制 (PulseAudio/PipeWire)

- **PulseAudio**: `pactl`, D-Bus 接口
- **PipeWire**: 取代 PulseAudio 的新一代音频系统
- **Python**: `pulsectl` 库

---

## 二、GUI 自动化技术

### 2.1 Xorg vs Wayland 对比

| 特性 | Xorg | Wayland |
|------|------|---------|
| **自动化工具** | xdotool, xte, PyAutoGUI | 需要 compositor 支持 |
| **屏幕截图** | 随意获取 | 需要 XDG Portal 权限 |
| **安全性** | 低（应用可互相监控） | 高（隔离沙箱） |
| **AI 自动化难度** | ⭐ 简单 | ⭐⭐⭐⭐ 复杂 |

> ⚠️ **重要**: Ubuntu 24.04 默认使用 Wayland，传统 xdotool 不可用！

### 2.2 GNOME 无障碍接口 (AT-SPI)

| 工具 | 说明 |
|------|------|
| **pyatspi2** | AT-SPI 的 Python 绑定 |
| **dogtail** | 高级自动化框架 |
| **gnome-ponytail-daemon** | Wayland 下 dogtail 的辅助工具 |

**适用场景**: 
- 识别 GUI 控件（按钮、文本框、菜单）
- 模拟用户操作
- 自动化测试

### 2.3 XDG Desktop Portal

面向沙箱应用的标准化接口:

- `org.freedesktop.portal.FileChooser` - 文件选择
- `org.freedesktop.portal.Screenshot` - 屏幕截图
- `org.freedesktop.portal.Notification` - 通知
- `org.freedesktop.portal.Settings` - 系统设置

> ✅ **推荐**: AIOS 应该通过 XDG Portal 获取权限，而非绕过安全机制

---

## 三、软件生态元数据

### 3.1 软件包格式对比

| 格式 | 元数据文件 | 能力声明 | 发现机制 |
|------|-----------|---------|---------|
| **Snap** | `snapcraft.yaml`, `snap/manifest.yaml` | interfaces | Snap Store API |
| **Flatpak** | `manifest.json/.yaml` | finish-args | Flathub API |
| **AppImage** | `.appstream.xml`, `.desktop` | 内嵌 | AppImageHub |

### 3.2 AppStream 标准

跨发行版的软件元数据格式，被 GNOME Software、KDE Discover 支持。

**关键信息**:
- 应用 ID、名称、描述
- 截图、图标
- 分类、关键词
- 支持的 MIME 类型

---

## 四、AI Agent 协议现状

### 4.1 主流协议对比

| 协议 | 来源 | 用途 | 通信方式 |
|------|------|------|---------|
| **MCP** | Anthropic | AI → 工具 | JSON-RPC 2.0 |
| **A2A** | Google (Linux Foundation) | Agent → Agent | JSON-RPC, SSE |
| **ACP** | IBM (Linux Foundation) | Agent → Agent | 标准化消息 |
| **Function Calling** | OpenAI | LLM → 函数 | JSON Schema |

### 4.2 Agent 发现机制

| 方式 | 说明 |
|------|------|
| **Well-known URI** | `/.well-known/agent-card.json` |
| **Catalog Registry** | 中央注册服务 |
| **DNS-based** | SRV/TXT 记录 |
| **MCP 动态发现** | 订阅注册/注销事件 |

### 4.3 Agent Card (A2A)

```json
{
  "name": "壁纸管理器",
  "description": "管理桌面壁纸",
  "url": "https://example.com/agent",
  "capabilities": ["set_wallpaper", "list_wallpapers"],
  "authentication_required": false
}
```

---

## 五、开源 AI 桌面助手项目

| 项目 | 特点 | Ubuntu 支持 |
|------|------|------------|
| **Mycroft AI** | 开源语音助手，模块化 | ✅ |
| **Newelle AI** | GNOME 深度集成，终端命令 | ✅ |
| **Rhasspy** | 完全离线，隐私优先 | ✅ |
| **PyGPT** | 跨平台，支持多种 LLM | ✅ |
| **Dragonfire** | Mozilla DeepSpeech 语音识别 | ✅ |

**启示**: 这些项目验证了 AI + Ubuntu 桌面集成的可行性

---

## 六、关键技术选型建议

### 系统控制层

| 功能 | 推荐技术 |
|------|---------|
| 设置管理 | gsettings (通过 subprocess 或 D-Bus) |
| 电源管理 | systemd-logind D-Bus API |
| 网络管理 | NetworkManager D-Bus 或 python-networkmanager |
| 音频控制 | pulsectl 或 pactl |
| 文件操作 | 原生 Python 或 XDG Portal |

### GUI 自动化层

| 场景 | 推荐技术 |
|------|---------|
| Xorg 环境 | PyAutoGUI, xdotool |
| Wayland 环境 | dogtail + AT-SPI, XDG Portal |
| 跨环境 | ScreenEnv (Docker 容器方案) |

### AI 协议层

| 需求 | 推荐方案 |
|------|---------|
| 工具发现 | 参考 MCP 的 Resource/Tool 机制 |
| Agent 通信 | 参考 A2A 的 Agent Card + JSON-RPC |
| 能力声明 | 参考 JSON Schema + OpenAPI |

---

## 八、2025-2026 年技术更新

### 8.1 Wayland 成为默认

Ubuntu 24.04+ 默认使用 Wayland，对 AI 自动化的影响：

| 影响 | 说明 | 解决方案 |
|------|------|---------|
| xdotool 不可用 | 传统 X11 工具失效 | 使用 AT-SPI |
| 屏幕截图受限 | 需要用户授权 | 使用 XDG Portal |
| 窗口管理受限 | 无法直接操作窗口 | 使用 D-Bus 接口 |

### 8.2 AT-SPI 在 Wayland 下的状态

| 特性 | 支持状态 |
|------|---------|
| 控件识别 | ✅ 完全支持 |
| 点击操作 | ✅ 支持 |
| 文本输入 | ✅ 支持 |
| 键盘模拟 | ⚠️ 部分支持 |
| 鼠标移动 | ⚠️ 需要 compositor 支持 |

### 8.3 推荐的 Python 库

| 用途 | 库 | 说明 |
|------|---|------|
| D-Bus | pydbus | 简洁的 D-Bus 绑定 |
| AT-SPI | pyatspi2, dogtail | GUI 自动化 |
| 音频 | pulsectl | PulseAudio 控制 |
| 网络 | python-networkmanager | NetworkManager 绑定 |
| 系统信息 | psutil | 跨平台系统信息 |

---

## 九、AIOS 协议设计启示

基于以上研究，AIOS 协议应该:

| 建议 | 说明 |
|------|------|
| 基于 D-Bus 构建 | 与 Ubuntu 系统无缝集成 |
| 使用 JSON Schema | 兼容 MCP/OpenAPI/Function Calling |
| 借鉴 AppStream | 软件元数据格式 |
| 实现 Agent Card | 工具自描述能力 |
| 通过 XDG Portal | 获取权限（尤其是 Wayland） |
| 支持多种发现机制 | Well-known URI + Registry + MCP |
| AT-SPI 优先 | GUI 自动化首选方案 |

---

## 参考资料

| 资源 | 链接 |
|------|------|
| GNOME Developer Documentation | https://developer.gnome.org/ |
| freedesktop.org Specifications | https://www.freedesktop.org/wiki/Specifications/ |
| Model Context Protocol | https://modelcontextprotocol.io/ |
| A2A Protocol | https://google.github.io/A2A/ |
| NetworkManager D-Bus API | https://networkmanager.dev/ |
| XDG Desktop Portal | https://flatpak.github.io/xdg-desktop-portal/ |
| AT-SPI Documentation | https://wiki.linuxfoundation.org/accessibility/atk/at-spi/start |
| dogtail | https://gitlab.com/dogtail/dogtail |

---

**文档版本**: 0.3.0  
**最后更新**: 2026-01-02  
**维护者**: AIOS Protocol Team
