# AIOS 适配器概述

**版本**: 2.0.0  
**更新日期**: 2026-01-09  
**状态**: 战略规划阶段

---

## 概述

**适配器**是连接 AIOS Protocol 与具体软件/系统的桥梁，封装了控制目标软件所需的逻辑。

---

## 1. 什么是适配器

```
┌──────────┐    ┌──────────────┐    ┌──────────────┐
│ AIOS     │ ←→ │   适配器     │ ←→ │  目标软件    │
│ Daemon   │    │ (Adapter)    │    │  /系统       │
└──────────┘    └──────────────┘    └──────────────┘
```

适配器负责：
- 将 AIOS 协议调用转换为目标软件的 API 调用
- 处理目标软件的响应并转换为 AIOS 格式
- 管理与目标软件的连接生命周期

---

## 2. 适配器类型

| 类型 | 标识 | 说明 | 示例 |
|------|------|------|------|
| **系统** | `system` | 操作系统功能 | 电源、桌面设置、文件系统 |
| **应用** | `application` | 桌面应用程序 | LibreOffice, GIMP |
| **浏览器** | `browser` | 网页浏览器 | Chrome, Firefox |
| **视觉** | `vision` | 通用视觉控制 | UI-TARS Adapter |
| **专业** | `professional` | 专业软件 | Blender, FreeCAD |
| **自定义** | `custom` | 用户定义 | 第三方工具 |

---

## 3. 适配器层级

根据能力深度，适配器分为三个层级：

| 层级 | 名称 | 能力范围 | 来源 |
|------|------|---------|------|
| **L0** | 基础适配 | 启动/关闭 | 自动生成 |
| **L1** | CLI 适配 | 命令行参数 | 分析 `--help` |
| **L2** | API 适配 | 完整深度控制 | 开发者创建 |

### L0: 基础适配

从 `.desktop` 文件自动生成，功能有限。

```yaml
# 自动生成的 L0 适配器
tool:
  id: "org.mozilla.firefox"
  name: "Firefox"
  type: "browser"

capabilities:
  - id: "app.browser.launch"
    name: "启动 Firefox"
  - id: "app.browser.close"
    name: "关闭 Firefox"
```

### L1: CLI 适配

扩展 L0，分析命令行帮助信息生成。

```yaml
# L1 适配器，支持 CLI 参数
capabilities:
  - id: "app.browser.open_url"
    name: "打开网址"
    input:
      properties:
        url: { type: string }
    
adapter:
  type: "cli"
  config:
    command: "/usr/bin/firefox"
    args_template: "{url}"
```

### L2: API 适配

完整的 API 集成，需要开发者创建。

```yaml
# L2 适配器，完整 API 集成
tool:
  id: "org.aios.browser.chrome"
  name: "Chrome 浏览器"
  type: "browser"

capabilities:
  - id: "app.browser.open_url"
  - id: "app.browser.navigate"
  - id: "app.browser.extract_content"
  - id: "app.browser.fill_form"
  - id: "app.browser.click_element"
  - id: "app.browser.screenshot"
  # ... 完整能力

adapter:
  type: "api"
  config:
    protocol: "devtools"
    port: 9222
```

---

## 4. 软件发现机制

AIOS 支持自动发现已安装的软件并生成基础适配器。

### 发现流程

```
软件安装 → 检测 .desktop 文件 → 解析元数据 → 生成 L0 适配器
                                     ↓
                            查询适配器市场
                                     ↓
                            获取 L1/L2 适配器
```

### 发现方式

| 方式 | 说明 | 监控目标 |
|------|------|---------|
| **inotify** | 文件系统监控 | `/usr/share/applications/` |
| **APT/dpkg** | 包管理器钩子 | 软件安装事件 |
| **AppStream** | 元数据解析 | 应用元数据 |
| **tool.aios.yaml** | 直接检测 | AIOS 工具描述文件 |

### 监控路径

| 路径 | 说明 |
|------|------|
| `/usr/share/applications/` | 系统应用 |
| `~/.local/share/applications/` | 用户应用 |
| `/var/lib/flatpak/exports/share/applications/` | Flatpak |
| `/var/lib/snapd/desktop/applications/` | Snap |

---

## 5. 控制方式优先级

适配器可使用多种方式控制目标软件，按优先级排序：

| 优先级 | 方式 | 说明 | 适用场景 |
|--------|------|------|---------  |
| **P1** | 原生 API / MCP | 软件提供的编程接口 | 浏览器、办公软件 |
| **P2** | AT-SPI | Linux 无障碍 API | GUI 应用 |
| **P3** | **视觉控制 (Vision)** | **截图 + 视觉模型分析** | **无 API 的应用 (通用兜底)** |
| **P4** | GUI 自动化 | 传统脚本/坐标点击 | 最后手段 |

### 视觉控制层特性

> [!TIP]
> 视觉控制采用仿生操作算法，避免被应用风控识别

| 特性 | 实现 |
|------|------|
| **轨迹生成** | 贝塞尔曲线模拟人类手指摆动 |
| **压力随机化** | 0.3-0.9 范围内随机 |
| **操作延迟** | 1000-5000ms 强制延迟 |
| **动态路由** | API→AT-SPI→Vision 智能降级 |

### 控制方式示例

| 软件 | 推荐方式 | API |
|------|---------|-----|
| Chrome | 原生 API | DevTools Protocol |
| Firefox | 原生 API | Remote Protocol |
| LibreOffice | 原生 API | UNO API |
| Blender | 原生 API | bpy (Python) |
| GIMP | 原生 API | Python-Fu |
| VLC | D-Bus | MPRIS |
| 微信 | AT-SPI/GUI | 无官方 API |

---

## 6. 核心适配器列表

### 系统适配器

| 适配器 ID | 名称 | 能力 |
|----------|------|------|
| `org.aios.system.power` | 电源管理 | 关机、重启、休眠、锁屏 |
| `org.aios.system.desktop` | 桌面管理 | 壁纸、主题、显示器 |
| `org.aios.system.audio` | 音频管理 | 音量、静音、输出设备 |
| `org.aios.system.network` | 网络管理 | WiFi、VPN、连接状态 |
| `org.aios.system.filesystem` | 文件系统 | 文件操作 |
| `org.aios.system.notification` | 通知 | 发送通知 |

### 浏览器适配器

| 适配器 ID | 名称 | 控制方式 |
|----------|------|---------|
| `org.aios.browser.chrome` | Chrome | DevTools Protocol |
| `org.aios.browser.firefox` | Firefox | Remote Protocol |
| `org.aios.browser.edge` | Edge | DevTools Protocol |

### 办公软件适配器

| 适配器 ID | 名称 | 控制方式 |
|----------|------|---------|
| `org.aios.office.libreoffice` | LibreOffice | UNO API |
| `org.aios.office.writer` | LibreOffice Writer | UNO API |
| `org.aios.office.calc` | LibreOffice Calc | UNO API |

### 专业软件适配器

| 适配器 ID | 名称 | 控制方式 |
|----------|------|---------|
| `org.aios.professional.blender` | Blender | bpy Python API |
| `org.aios.professional.gimp` | GIMP | Python-Fu |
| `org.aios.professional.freecad` | FreeCAD | Python API |
| `org.aios.professional.inkscape` | Inkscape | inkex |

---

## 7. 适配器配置类型

### D-Bus 适配器

```yaml
adapter:
  type: "dbus"
  config:
    service: "org.gnome.desktop.background"
    interface: "org.freedesktop.DBus.Properties"
    bus: "session"
```

### CLI 适配器

```yaml
adapter:
  type: "cli"
  config:
    command: "/usr/bin/gsettings"
    args_template: "set {schema} {key} {value}"
```

### Python 适配器

```yaml
adapter:
  type: "python"
  config:
    module: "aios_blender.adapter"
    class: "BlenderAdapter"
```

### API 适配器

```yaml
adapter:
  type: "api"
  config:
    protocol: "devtools"
    url: "http://localhost:9222"
```

### WASM 适配器

```yaml
adapter:
  type: "wasm"
  config:
    module: "mytool.wasm"
    sandbox_level: "L2"
```

---

## 8. 沙箱隔离

| 层级 | 名称 | 技术 | 适用场景 |
|------|------|------|---------|
| **L0** | 无隔离 | 直接执行 | 受信任系统工具 |
| **L1** | 进程隔离 | 独立进程 | 一般工具 |
| **L2** | WASM 沙箱 | Wasmtime | 第三方工具 |
| **L3** | 容器隔离 | Docker + gVisor | 不可信工具 |
| **L4** | VM 隔离 | Firecracker | 高风险操作 |

### 默认沙箱级别

| 工具来源 | 默认沙箱 |
|---------|---------|
| 系统内置 | L0 |
| 官方验证 | L1 |
| 社区提交 | L2 |
| 未验证 | L3 |

---

## 下一步

- [适配器开发指南](01-Development.md) - 如何开发适配器
- [工具描述规范](../protocol/04-ToolSchema.md) - tool.aios.yaml 格式

---

**文档版本**: 2.0.0  
**最后更新**: 2026-01-09  
**维护者**: AIOS Protocol Team
