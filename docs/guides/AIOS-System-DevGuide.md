# AIOS 系统应用开发指南（Linux 参考实现）

**版本**: 2.0.0  
**更新日期**: 2026-01-09  
**适用平台**: Linux (Ubuntu/GNOME)

> **注意**：本文档为 Linux 平台参考实现指南。Phase 1 重点平台为 macOS，Linux 支持属于 Phase 2 计划。macOS 开发指南请参见 [aios-macos](../../aios-macos/) 项目。

---

## 一、Ubuntu 系统集成概述

### 1.1 开放协议说明

AIOS 协议采用开放设计，本指南中的系统集成方法可以使用任何支持的编程语言实现：

| 语言 | SDK | 适用场景 |
|------|-----|---------|
| Python | `aios-sdk` | 快速开发、脚本化 |
| Rust | `aios-sdk` (crate) | 系统级控制、高性能 |
| Go | `aios-go` | 高性能服务 |
| TypeScript | `@aios/sdk` | Node.js 环境 |

### 1.2 系统层级架构

AIOS 运行时通过系统适配器层与 Ubuntu 系统服务交互。适配器层包含四种主要适配器：

| 适配器类型 | 职责 | 目标服务 |
|-----------|------|---------|
| D-Bus 适配器 | 系统服务通信 | systemd, NetworkManager, GNOME Settings |
| CLI 适配器 | 命令行工具调用 | pactl, gsettings, nmcli |
| 文件系统适配器 | 文件操作 | 本地文件系统 |
| XDG 适配器 | 沙箱应用接口 | XDG Desktop Portal |

### 1.2 可用的系统接口

| 接口 | 用途 | 技术 | 文档链接 |
|------|------|------|---------|
| **D-Bus** | 系统服务通信 | Session/System Bus | [D-Bus Tutorial](https://dbus.freedesktop.org/doc/dbus-tutorial.html) |
| **gsettings/dconf** | 桌面设置 | D-Bus + 配置库 | [GNOME dconf](https://wiki.gnome.org/Projects/dconf) |
| **systemd** | 服务和电源管理 | D-Bus API | [systemd D-Bus API](https://www.freedesktop.org/wiki/Software/systemd/dbus/) |
| **NetworkManager** | 网络管理 | D-Bus API | [NM D-Bus API](https://networkmanager.dev/docs/api/latest/) |
| **PulseAudio/PipeWire** | 音频控制 | D-Bus + pactl | [PipeWire Wiki](https://gitlab.freedesktop.org/pipewire/pipewire/-/wikis/home) |
| **XDG Desktop Portal** | 沙箱应用接口 | D-Bus | [Portal Docs](https://flatpak.github.io/xdg-desktop-portal/) |
| **AT-SPI** | 无障碍/GUI 自动化 | D-Bus | [AT-SPI Wiki](https://wiki.linuxfoundation.org/accessibility/atk/at-spi/start) |

---

## 二、D-Bus 适配器开发

### 2.1 D-Bus 基础概念

D-Bus 是 Linux 桌面的核心进程间通信 (IPC) 系统，所有系统服务都通过它暴露 API。

| 总线类型 | 用途 | 示例服务 |
|---------|------|---------|
| **System Bus** | 系统级服务 | systemd, NetworkManager, UPower |
| **Session Bus** | 用户会话服务 | GNOME Shell, dconf, 应用程序 |

### 2.2 关键调试工具

| 工具 | 用途 | 说明 |
|------|------|------|
| `dbus-send` | 命令行发送 D-Bus 消息 | 基础工具 |
| `busctl` | systemd 的 D-Bus 工具 | 推荐使用 |
| `gdbus` | GLib 的 D-Bus 工具 | GNOME 环境 |
| `d-feet` | 图形化 D-Bus 浏览器 | 可视化调试 |

### 2.3 常用 D-Bus 服务

#### Session Bus 服务

| 服务 | 对象路径 | 用途 |
|------|---------|------|
| `org.gnome.SettingsDaemon.Color` | `/org/gnome/SettingsDaemon/Color` | 显示器色彩管理 |
| `org.gnome.Shell` | `/org/gnome/Shell` | 桌面 Shell 控制 |
| `org.freedesktop.Notifications` | `/org/freedesktop/Notifications` | 桌面通知 |
| `org.freedesktop.portal.Desktop` | `/org/freedesktop/portal/desktop` | XDG 桌面门户 |
| `org.gnome.ScreenSaver` | `/org/gnome/ScreenSaver` | 屏幕保护/锁屏 |
| `org.mpris.MediaPlayer2.*` | `/org/mpris/MediaPlayer2` | 媒体播放器控制 |

#### System Bus 服务

| 服务 | 对象路径 | 用途 |
|------|---------|------|
| `org.freedesktop.login1` | `/org/freedesktop/login1` | 会话和电源管理 |
| `org.freedesktop.NetworkManager` | `/org/freedesktop/NetworkManager` | 网络管理 |
| `org.freedesktop.UPower` | `/org/freedesktop/UPower` | 电源状态 |
| `org.freedesktop.hostname1` | `/org/freedesktop/hostname1` | 主机名管理 |
| `org.freedesktop.timedate1` | `/org/freedesktop/timedate1` | 时间日期管理 |

### 2.4 D-Bus 适配器设计原则

适配器应遵循以下设计原则：

1. **延迟初始化**：D-Bus 连接应在首次使用时建立，而非构造时
2. **能力声明**：每个适配器必须声明其提供的能力列表
3. **权限检查**：调用前必须验证所需权限
4. **健康检查**：提供连接状态检测机制
5. **错误处理**：统一的错误码和错误消息格式

---

## 三、系统控制能力

### 3.1 电源管理

电源管理通过 `org.freedesktop.login1` D-Bus 服务实现。

| 能力 | 权限级别 | 确认要求 | D-Bus 方法 |
|------|---------|---------|-----------|
| 关机 | critical | 二次确认 | `PowerOff(interactive)` |
| 重启 | critical | 二次确认 | `Reboot(interactive)` |
| 休眠 | medium | 首次确认 | `Suspend(interactive)` |
| 锁屏 | low | 首次确认 | `org.gnome.ScreenSaver.Lock()` |
| 定时关机 | critical | 二次确认 | `shutdown +N` CLI |

### 3.2 网络管理

网络管理通过 NetworkManager D-Bus API 实现。

| 能力 | 权限级别 | D-Bus 接口 |
|------|---------|-----------|
| 获取网络状态 | public | `State`, `Connectivity` 属性 |
| 列出 WiFi 网络 | low | `GetAccessPoints()` |
| 开关 WiFi | medium | `WirelessEnabled` 属性 |
| 飞行模式 | medium | `WirelessEnabled` + `WwanEnabled` |
| 连接网络 | medium | `ActivateConnection()` |

**NetworkManager 状态码**：

| 状态码 | 含义 |
|-------|------|
| 0 | unknown |
| 10 | asleep |
| 20 | disconnected |
| 30 | disconnecting |
| 40 | connecting |
| 50 | connected_local |
| 60 | connected_site |
| 70 | connected_global |

### 3.3 桌面设置 (gsettings/dconf)

桌面设置通过 GSettings API 管理，底层使用 dconf 存储。

**常用设置路径**：

| Schema | Key | 说明 |
|--------|-----|------|
| `org.gnome.desktop.background` | `picture-uri` | 壁纸路径 |
| `org.gnome.desktop.background` | `picture-options` | 壁纸模式 (zoom/scaled/stretched) |
| `org.gnome.desktop.interface` | `gtk-theme` | GTK 主题 |
| `org.gnome.desktop.interface` | `color-scheme` | 颜色方案 (prefer-dark/prefer-light) |
| `org.gnome.desktop.interface` | `font-name` | 界面字体 |
| `org.gnome.desktop.interface` | `text-scaling-factor` | 文字缩放 |
| `org.gnome.desktop.sound` | `event-sounds` | 事件声音 |
| `org.gnome.desktop.screensaver` | `lock-enabled` | 锁屏启用 |
| `org.gnome.desktop.session` | `idle-delay` | 空闲延迟 |

### 3.4 音频控制

音频控制支持 PulseAudio 和 PipeWire（Ubuntu 22.04+ 默认）。

| 能力 | 工具 | 说明 |
|------|------|------|
| 获取音量 | `pactl get-sink-volume` | 返回百分比 |
| 设置音量 | `pactl set-sink-volume` | 0-150% |
| 静音切换 | `pactl set-sink-mute toggle` | 开关静音 |
| 列出设备 | `pactl list sinks short` | 输出设备列表 |
| 切换设备 | `pactl set-default-sink` | 更改默认输出 |

---

## 四、XDG Desktop Portal 集成

### 4.1 为什么使用 Portal

Portal 是 Flatpak/Snap 沙箱应用访问系统资源的标准方式，也是 Wayland 环境下的推荐方案。

| 场景 | 传统方式 | Portal 方式 |
|------|---------|------------|
| 文件选择 | 直接访问文件系统 | 用户通过对话框选择 |
| 屏幕截图 | 需要额外权限 | 用户确认后授权 |
| 通知 | 直接发送 | 统一通知系统 |
| 打开 URI | 直接调用 | 系统默认应用 |

> ⚠️ **重要**: Ubuntu 24.04+ 默认使用 Wayland，传统 xdotool 不可用！必须使用 Portal。

### 4.2 Portal 服务列表

| Portal | D-Bus 接口 | 用途 |
|--------|-----------|------|
| FileChooser | `org.freedesktop.portal.FileChooser` | 文件选择对话框 |
| Screenshot | `org.freedesktop.portal.Screenshot` | 屏幕截图 |
| Notification | `org.freedesktop.portal.Notification` | 发送通知 |
| OpenURI | `org.freedesktop.portal.OpenURI` | 打开 URI/文件 |
| Settings | `org.freedesktop.portal.Settings` | 读取系统设置 |
| Background | `org.freedesktop.portal.Background` | 后台运行请求 |
| Camera | `org.freedesktop.portal.Camera` | 摄像头访问 |
| ScreenCast | `org.freedesktop.portal.ScreenCast` | 屏幕录制 |

### 4.3 Portal 调用流程

1. 获取 Portal 接口对象
2. 生成唯一的 handle_token
3. 调用 Portal 方法（异步）
4. 等待用户确认（Portal 会弹出系统对话框）
5. 通过 Response 信号获取结果

---

## 五、GUI 自动化 (AT-SPI)

### 5.1 AT-SPI 概述

AT-SPI (Assistive Technology Service Provider Interface) 是 Linux 桌面的无障碍 API，允许程序访问和控制 GUI 应用程序。

**架构层次**：

| 层级 | 组件 | 说明 |
|------|------|------|
| 高级封装 | dogtail, ldtp | 友好的 Python API |
| 底层 API | pyatspi2 | 直接访问 AT-SPI |
| D-Bus 层 | org.a11y.atspi.Registry | AT-SPI 注册表服务 |
| 应用层 | GTK/Qt 应用程序 | 提供无障碍信息 |

### 5.2 AT-SPI vs 传统方案

| 方案 | X11 支持 | Wayland 支持 | 可靠性 | 速度 |
|------|---------|-------------|--------|------|
| **xdotool** | ✅ | ❌ | 中 | 快 |
| **xte** | ✅ | ❌ | 中 | 快 |
| **AT-SPI** | ✅ | ✅ | 高 | 中 |
| **截图+OCR** | ✅ | ✅ | 低 | 慢 |

> ⚠️ **重要**: Ubuntu 24.04+ 默认使用 Wayland，xdotool 不可用！AT-SPI 是唯一可靠的 GUI 自动化方案。

### 5.3 启用 AT-SPI

AT-SPI 需要在系统设置中启用无障碍功能：

```bash
# 检查 AT-SPI 是否启用
gsettings get org.gnome.desktop.interface toolkit-accessibility

# 启用 AT-SPI
gsettings set org.gnome.desktop.interface toolkit-accessibility true
```

启用后需要重启应用程序才能生效。

### 5.4 AT-SPI 核心概念

**控件树结构**：
- Desktop（桌面）→ Application（应用）→ Window（窗口）→ Widget（控件）
- 每个控件有 Role（角色）、Name（名称）、State（状态）等属性

**常用操作**：
- 遍历控件树
- 按名称/角色查找控件
- 执行动作（点击、输入等）
- 读取控件属性和状态

### 5.5 AT-SPI 角色类型参考

| 角色 (Role) | 说明 | 常见控件 |
|------------|------|---------|
| `application` | 应用程序 | 顶级应用 |
| `frame` | 窗口框架 | 主窗口 |
| `dialog` | 对话框 | 弹出对话框 |
| `push button` | 按钮 | 普通按钮 |
| `toggle button` | 切换按钮 | 开关按钮 |
| `check box` | 复选框 | 多选框 |
| `radio button` | 单选按钮 | 单选框 |
| `text` | 文本框 | 输入框 |
| `password text` | 密码框 | 密码输入 |
| `combo box` | 下拉框 | 选择框 |
| `menu` | 菜单 | 菜单栏 |
| `menu item` | 菜单项 | 菜单选项 |
| `list` | 列表 | 列表视图 |
| `list item` | 列表项 | 列表条目 |
| `tree` | 树形视图 | 文件树 |
| `table` | 表格 | 数据表 |
| `scroll bar` | 滚动条 | 滚动控件 |
| `slider` | 滑块 | 音量条等 |
| `progress bar` | 进度条 | 加载进度 |
| `label` | 标签 | 文本标签 |
| `tool bar` | 工具栏 | 工具按钮区 |
| `status bar` | 状态栏 | 底部状态 |
| `tab` | 标签页 | 选项卡 |

### 5.6 Python 库选择

| 库 | 特点 | 适用场景 |
|---|------|---------|
| **pyatspi2** | 底层 API，完整控制 | 需要精细控制 |
| **dogtail** | 高级封装，易用 | 快速开发 |
| **ldtp** | 测试框架风格 | 自动化测试 |

---

## 六、安全模型

### 6.1 五级权限模型

| 级别 | 名称 | 用户确认 | 自动授权 | 示例 |
|------|------|---------|---------|------|
| 0 | public | 无需 | ✅ | 读取时间、读取设置 |
| 1 | low | 首次 | ✅ | 调整音量、锁屏 |
| 2 | medium | 首次 | ⚠️ 可配置 | 打开浏览器、网络请求 |
| 3 | high | 每次 | ❌ | 发送消息、写入文件 |
| 4 | critical | 二次确认 | ❌ | 关机、删除文件 |

### 6.2 预定义权限列表

**系统控制权限**：

| 权限 ID | 名称 | 级别 |
|--------|------|------|
| `aios.permission.system.power.shutdown` | 关机 | critical |
| `aios.permission.system.power.reboot` | 重启 | critical |
| `aios.permission.system.power.suspend` | 休眠 | medium |
| `aios.permission.system.power.lock` | 锁屏 | low |

**设置权限**：

| 权限 ID | 名称 | 级别 |
|--------|------|------|
| `aios.permission.system.settings.read` | 读取设置 | public |
| `aios.permission.system.settings.write` | 修改设置 | low |

**网络权限**：

| 权限 ID | 名称 | 级别 |
|--------|------|------|
| `aios.permission.network.status` | 网络状态 | public |
| `aios.permission.network.control` | 网络控制 | medium |

**文件系统权限**：

| 权限 ID | 名称 | 级别 |
|--------|------|------|
| `aios.permission.filesystem.read` | 读取文件 | medium |
| `aios.permission.filesystem.write` | 写入文件 | high |
| `aios.permission.filesystem.delete` | 删除文件 | critical |

**GUI 自动化权限**：

| 权限 ID | 名称 | 级别 |
|--------|------|------|
| `aios.permission.gui.read` | 读取界面 | low |
| `aios.permission.gui.control` | 控制界面 | medium |

### 6.3 能力令牌 (Capability Token)

能力令牌是权限授予的凭证，包含以下字段：

| 字段 | 类型 | 说明 |
|------|------|------|
| token_id | string | 唯一标识符 |
| tool_id | string | 工具标识 |
| permission_id | string | 权限标识 |
| scope | string | 作用范围（可选） |
| issued_at | timestamp | 签发时间 |
| expires_at | timestamp | 过期时间 |
| revocable | boolean | 是否可撤销 |

### 6.4 输入验证

**必须检测的危险模式**：

| 类型 | 检测内容 |
|------|---------|
| 命令注入 | `; & | \` $ ( ) { }` 等特殊字符 |
| 路径遍历 | `..` 和 `../` 模式 |
| 敏感目录 | `/etc`, `/root`, `/var`, `/usr`, `/bin`, `/sbin` |
| 提示注入 | "ignore previous instructions", "system:" 等模式 |

**路径验证规则**：
- 禁止包含 `..`
- 只允许访问用户目录 (`/home/`)
- 禁止访问系统敏感目录

### 6.5 审计日志

所有操作必须记录审计日志，包含以下信息：

| 字段 | 说明 |
|------|------|
| timestamp | 操作时间 (ISO 8601) |
| event_type | 事件类型 |
| tool_id | 工具标识 |
| capability_id | 能力标识 |
| user_id | 用户标识 |
| session_id | 会话标识 |
| request_params | 请求参数（敏感信息脱敏） |
| result_success | 是否成功 |
| error_code | 错误码（如有） |
| permission_level | 权限级别 |
| confirmation_required | 是否需要确认 |
| confirmation_given | 是否已确认 |
| execution_time_ms | 执行时间 |
| checksum | 校验和（防篡改） |

**敏感参数脱敏**：
- password, token, secret, key, credential 等字段应替换为 `[REDACTED]`

---

## 七、调试与测试

### 7.1 D-Bus 调试命令

| 命令 | 用途 |
|------|------|
| `busctl --user list` | 列出所有 Session Bus 服务 |
| `busctl list` | 列出所有 System Bus 服务 |
| `busctl --user tree <service>` | 查看服务的对象树 |
| `busctl --user introspect <service> <path>` | 查看接口详情 |
| `dbus-monitor --session` | 监控 D-Bus 消息 |
| `d-feet` | 图形化 D-Bus 浏览器 |

### 7.2 AT-SPI 调试命令

| 命令 | 用途 |
|------|------|
| `gsettings get org.gnome.desktop.interface toolkit-accessibility` | 检查 AT-SPI 状态 |
| `accerciser` | 图形化 AT-SPI 浏览器 |
| `sniff` | dogtail 命令行工具 |

### 7.3 测试策略

**单元测试**：
- Mock D-Bus 连接和服务对象
- 测试权限检查逻辑
- 测试输入验证
- 测试错误处理

**集成测试**：
- 验证 D-Bus 连接可用性
- 验证 gsettings 读写
- 验证通知发送
- 验证 AT-SPI 可用性

---

## 八、常见问题

### 8.1 D-Bus 相关

**Q: 无法连接到 D-Bus**

检查步骤：
1. 检查 D-Bus 服务状态：`systemctl --user status dbus`
2. 检查环境变量：`echo $DBUS_SESSION_BUS_ADDRESS`
3. 如果为空，启动 D-Bus：`eval $(dbus-launch --sh-syntax)`

**Q: 权限被拒绝**

检查步骤：
1. 检查 polkit 策略：`pkaction --verbose --action-id <action>`
2. 检查用户组：`groups`
3. 添加必要的组：`sudo usermod -aG sudo,adm $USER`

**Q: 服务不存在**

检查步骤：
1. 列出可用服务：`busctl --user list | grep -i <service>`
2. 检查服务是否安装：`dpkg -l | grep <package>`

### 8.2 AT-SPI 相关

**Q: AT-SPI 不工作**

解决方案：
1. 启用无障碍功能：`gsettings set org.gnome.desktop.interface toolkit-accessibility true`
2. 重启应用程序或注销重新登录
3. 检查 AT-SPI 注册表：`busctl --user list | grep atspi`

**Q: 找不到控件**

解决方案：
1. 使用 accerciser 图形工具查看控件树
2. 检查控件是否可见（showing 属性）
3. 尝试不同的查找策略（按名称、按角色）

**Q: Wayland 下 xdotool 不工作**

解决方案：
1. 检查会话类型：`echo $XDG_SESSION_TYPE`
2. 如果是 wayland，使用 AT-SPI 或 XDG Portal
3. xdotool 只在 X11 下工作

### 8.3 音频相关

**Q: pactl 命令失败**

检查步骤：
1. 检查音频服务状态：`systemctl --user status pipewire pipewire-pulse`
2. 重启音频服务：`systemctl --user restart pipewire pipewire-pulse`
3. 检查默认设备：`pactl info | grep "Default Sink"`

---

## 九、开发检查清单

### 9.1 适配器开发

- [ ] 选择正确的系统接口（D-Bus / gsettings / AT-SPI / Portal）
- [ ] 实现适配器基类的所有必要方法
- [ ] 定义清晰的能力和权限
- [ ] 实现延迟初始化
- [ ] 实现健康检查

### 9.2 安全实现

- [ ] 实现输入验证
- [ ] 实现权限检查
- [ ] 添加审计日志
- [ ] 敏感信息脱敏
- [ ] 错误信息不泄露敏感信息

### 9.3 兼容性

- [ ] 处理 Wayland 兼容性
- [ ] 处理 PipeWire/PulseAudio 兼容性
- [ ] 处理不同 GNOME 版本差异

### 9.4 测试

- [ ] 编写单元测试
- [ ] 编写集成测试
- [ ] 测试错误处理路径
- [ ] 测试权限拒绝场景

---

## 十、最佳实践

1. **优先使用 D-Bus API** - 比 CLI 更可靠、更快、更易于错误处理
2. **使用 XDG Portal** - Wayland 兼容，内置用户确认机制
3. **AT-SPI 作为 GUI 自动化首选** - 跨 X11/Wayland，比截图+OCR 更可靠
4. **实现完整的权限检查** - 安全第一，所有操作前验证权限
5. **记录所有操作** - 审计日志对于调试和安全审计至关重要
6. **优雅处理错误** - 返回有意义的错误信息，不泄露敏感信息
7. **延迟初始化** - 避免启动时建立不必要的连接
8. **资源清理** - 确保 D-Bus 连接和其他资源正确释放
9. **使用仿生输入 (Bionic Input)** - 当需要模拟鼠标/触控输入时:
   - 使用贝塞尔曲线模拟平滑移动，而非瞬移。
   - 随机化点击位置、按压时长、触控面积。
   - 在操作间添加人为的随机延迟 (100ms-500ms)。
   - **目的**: 避免被应用程序的反自动化/风控机制识别。

---

## 十一、相关资源

| 资源 | 链接 |
|------|------|
| D-Bus 规范 | https://dbus.freedesktop.org/doc/dbus-specification.html |
| GNOME 开发文档 | https://developer.gnome.org/ |
| AT-SPI 文档 | https://wiki.linuxfoundation.org/accessibility/atk/at-spi/start |
| XDG Portal 文档 | https://flatpak.github.io/xdg-desktop-portal/ |
| pyatspi2 文档 | https://lazka.github.io/pgi-docs/Atspi-2.0/ |
| dogtail 文档 | https://gitlab.com/dogtail/dogtail |
| pydbus 文档 | https://github.com/LEW21/pydbus |
| NetworkManager D-Bus API | https://networkmanager.dev/docs/api/latest/ |
| PipeWire Wiki | https://gitlab.freedesktop.org/pipewire/pipewire/-/wikis/home |
| AIOS 适配器开发指南 | [../adapters/01-Development.md](../adapters/01-Development.md) |
| AIOS 协议开放化方案 | [../research/AIOS-Protocol-Enhancement-Proposal.md](../research/AIOS-Protocol-Enhancement-Proposal.md) |

---

**文档版本**: 2.0.0  
**最后更新**: 2026-01-09  
**维护者**: AIOS Protocol Team
