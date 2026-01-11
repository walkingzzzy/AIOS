# AIOS Protocol 核心概念

**版本**: 2.0.0  
**更新日期**: 2026-01-09  
**状态**: 战略规划阶段

---

## 概述

本文档定义 AIOS Protocol 的核心概念和术语，是理解协议的基础。

### 设计原则

AIOS Protocol 采用**开放设计**，核心原则包括：

| 原则 | 说明 |
|------|------|
| **语言无关** | 协议基于 JSON-RPC 2.0，任何语言均可实现 |
| **传输灵活** | 支持 stdio、HTTP、WebSocket、Unix Socket |
| **部署多样** | 本地、云端、Serverless、容器化均可 |
| **生态兼容** | 可桥接 MCP 服务器、A2A 代理 |
| **安全优先** | 5级权限模型 + 多级沙箱 + 用户确认 |

---

## 1. 适配器 (Adapter)

### 定义

**适配器**是连接 AIOS 协议与具体软件/系统的桥梁，封装了控制目标软件所需的逻辑。

```
AIOS Daemon ←→ 适配器 ←→ 目标软件/系统
```

### 适配器实现方式

AIOS 不限制适配器的实现语言和部署方式：

| 实现语言 | SDK | 适用场景 |
|---------|-----|---------|
| **Python** | `aios-sdk` | 快速开发、AI集成 |
| **TypeScript** | `@aios/sdk` | Web/Node.js生态 |
| **Go** | `aios-go` | 高性能服务 |
| **Rust** | `aios-sdk` (crate) | 系统级控制 |
| **Java/Kotlin** | `aios-jvm` | 企业应用 |

### 适配器类型

| 类型 | 标识 | 说明 | 示例 |
|------|------|------|------|
| **system** | `type: system` | 控制操作系统功能 | 电源、桌面设置、文件系统 |
| **application** | `type: application` | 控制桌面应用程序 | LibreOffice, GIMP |
| **browser** | `type: browser` | 控制网页浏览器 | Chrome, Firefox |
| **vision** | `type: vision` | **通用视觉控制** | **UI-TARS Adapter** |
| **professional** | `type: professional` | 控制专业软件 | Blender, FreeCAD |
| **custom** | `type: custom` | 自定义适配器 | 用户定义 |

### 适配器生命周期

```
┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
│  发现    │ ─→ │  注册    │ ─→ │  激活    │ ─→ │  调用    │
│ Discover │    │ Register │    │ Activate │    │ Invoke   │
└──────────┘    └──────────┘    └──────────┘    └──────────┘
      │               │               │               │
      ▼               ▼               ▼               ▼
  扫描工具        验证签名        初始化连接      执行能力
  读取描述        存入注册表      获取权限        返回结果
```

| 阶段 | 说明 |
|------|------|
| **发现** | 扫描 `.desktop` 文件、`tool.aios.yaml`、Adapter Card，发现可用适配器 |
| **注册** | 验证适配器签名（JWS），存入工具注册表 |
| **激活** | 初始化适配器，建立与目标软件的连接 |
| **调用** | 执行具体能力，返回结果 |

→ 详见 [发现机制规范](AIOS-Protocol-Discovery.md)

### 适配器部署方式

| 部署方式 | 传输协议 | 适用场景 |
|---------|---------|---------|
| **本地进程** | stdio | CLI工具、本地开发 |
| **本地服务** | Unix Socket / HTTP | 高性能本地通信 |
| **远程服务** | HTTP / WebSocket | 云端部署、远程访问 |
| **Serverless** | HTTP | Cloudflare Workers、AWS Lambda |
| **容器化** | HTTP | Docker、Kubernetes |

### 适配器层级

| 层级 | 名称 | 能力范围 | 来源 |
|------|------|---------|------|
| **L0** | 基础适配 | 启动/关闭 | 自动生成 |
| **L1** | CLI 适配 | 命令行参数控制 | 分析 `--help` |
| **L2** | API 适配 | 完整深度控制 | 第三方开发/官方 |

---

## 2. 能力 (Capability)

### 定义

**能力**是适配器对外暴露的具体控制功能，是 AIOS 调用的最小单元。

### 能力结构

```yaml
capabilities:
  - id: "system.desktop.set_wallpaper"  # 全局能力 ID（RPC 调用时使用）
    name: "设置壁纸"                      # 显示名称
    description: "设置桌面壁纸"            # 功能描述

    input:                        # 输入参数 (JSON Schema)
      type: object
      properties:
        path: { type: string, description: "图片路径" }
        mode: { type: string, enum: ["fill", "fit", "tile"] }
      required: ["path"]

    output:                       # 输出格式 (JSON Schema)
      type: object
      properties:
        success: { type: boolean }
        message: { type: string }

    permissions:                  # 所需权限
      - "aios.permission.filesystem.read"
      - "aios.permission.desktop.wallpaper.write"

    examples:                     # AI 学习示例
      - user_intent: "把壁纸换成蓝色的"
        call:
          capability_id: "system.desktop.set_wallpaper"
          arguments: { path: "/backgrounds/blue.jpg" }
```

> **能力 ID 规范**：RPC 调用时使用全局能力 ID（如 `system.desktop.set_wallpaper`），而非局部 action 名称。

### 能力标识符规范

```
<namespace>.<category>.<action>
```

| 部分 | 说明 | 示例 |
|------|------|------|
| namespace | 顶层命名空间 | `system`, `app`, `professional` |
| category | 功能类别 | `desktop`, `browser`, `document` |
| action | 具体动作 | `set_wallpaper`, `open_url`, `create` |

**标准命名空间**：
| 命名空间 | 说明 | 示例 |
|---------|------|------|
| `system.*` | 操作系统功能 | `system.desktop.set_wallpaper` |
| `app.*` | 桌面应用控制 | `app.browser.open_url` |
| `professional.*` | 专业软件控制 | `professional.blender.create_mesh` |

**示例**：
- `system.desktop.set_wallpaper`
- `system.audio.set_volume`
- `app.browser.open_url`
- `app.office.document.create`
- `professional.blender.create_mesh`

> **扩展命名空间**：`vision.*` 等非标准命名空间可作为扩展使用，但不属于核心协议规范。

---

## 3. 意图 (Intent)

### 定义

**意图**是用户通过自然语言表达的需求，AI 引擎将其转换为具体的能力调用。

### 意图到能力的映射

```
用户输入: "帮我把屏幕调暗一点"
    ↓
AI 引擎: 意图识别
    ↓
意图: { action: "adjust_brightness", direction: "decrease" }
    ↓
能力调用: system.display.set_brightness(level: current - 10%)
```

### 多步骤意图

复杂意图可能需要调用多个能力：

```
用户: "用浏览器比较京东和淘宝上这款耳机的价格"
    ↓
AI 规划:
  1. app.browser.launch(app: "chrome")
  2. app.browser.open_url(url: "jd.com")
  3. app.browser.search(text: "耳机型号")
  4. app.browser.extract_content(selector: ".price")
  5. app.browser.open_url(url: "taobao.com")
  6. app.browser.search(text: "耳机型号")
  7. app.browser.extract_content(selector: ".price")
  8. AI 比较结果并返回
```

---

## 4. 权限 (Permission)

### 定义

**权限**控制 AI 可以执行哪些操作，是 AIOS 安全模型的核心。

### 五级权限体系

| 级别 | 标识 | 用户确认 | 示例 |
|------|------|---------|------|
| **0** | `public` | 无需 | 读取时间、系统信息 |
| **1** | `low` | 首次 | 读取设置、调整音量 |
| **2** | `medium` | 首次 | 打开浏览器、网络请求 |
| **3** | `high` | 每次 | 发送消息、写入文件 |
| **4** | `critical` | 二次确认 | 关机、删除文件、支付 |

### 权限命名规范

```
aios.permission.<category>.<resource>.<action>
```

**示例**：
- `aios.permission.filesystem.home.read`
- `aios.permission.network.internet.connect`
- `aios.permission.system.power.shutdown`

→ 详见 [权限模型](05-PermissionModel.md)

---

## 5. 能力令牌 (Capability Token)

### 定义

**能力令牌**是权限授予的凭证，具有细粒度、时效性、可撤销的特点。

### 令牌结构

| 字段 | 类型 | 说明 |
|------|------|------|
| `token_id` | string | 唯一标识符 |
| `tool_id` | string | 工具标识 |
| `permission_id` | string | 权限标识 |
| `scope` | string | 资源范围 |
| `issued_at` | timestamp | 签发时间 |
| `expires_at` | timestamp | 过期时间 |
| `revocable` | boolean | 是否可撤销 |

### 令牌示例

```json
{
  "token_id": "cap-token-abc123",
  "tool_id": "org.aios.browser.chrome",
  "permission_id": "aios.permission.network.internet.connect",
  "scope": "https://jd.com/*",
  "issued_at": "2026-01-05T10:00:00Z",
  "expires_at": "2026-01-05T11:00:00Z",
  "revocable": true
}
```

### 令牌时效类型

| 类型 | 说明 |
|------|------|
| `once` | 单次使用后失效 |
| `task` | 当前任务完成后失效 |
| `session` | 当前会话结束后失效 |
| `timed:N` | N 秒后失效 |
| `persistent` | 永久有效（需明确同意） |

---

## 6. 会话 (Session)

### 定义

**会话**是用户与 AIOS 交互的上下文环境，管理权限状态、任务历史等。

### 会话属性

| 属性 | 说明 |
|------|------|
| `session_id` | 唯一会话标识 |
| `user_id` | 用户标识 |
| `created_at` | 创建时间 |
| `expires_at` | 过期时间 |
| `granted_permissions` | 已授予的权限列表 |
| `active_tokens` | 活跃的能力令牌 |

### 会话生命周期

```
创建 → 活跃 → 空闲 → 过期/关闭
```

---

## 7. 上下文 (Context)

### 定义

**上下文**是执行能力时传递的环境信息。

### 上下文层级

| 层级 | 生命周期 | 内容 |
|------|---------|------|
| **全局** | 永久 | 用户偏好、全局配置 |
| **会话** | 会话期间 | 会话状态、权限令牌 |
| **任务** | 任务期间 | 任务参数、中间结果 |
| **调用** | 单次调用 | 调用参数、临时数据 |

### 上下文传递

```json
{
  "context": {
    "session_id": "sess-001",
    "user_id": "user-001",
    "task_id": "task-001",
    "mentioned_file": "/home/user/image.jpg",
    "locale": "zh-CN",
    "timezone": "Asia/Shanghai"
  }
}
```

---

## 8. 工具注册表 (Tool Registry)

### 定义

**工具注册表**是 AIOS 维护的所有可用工具（适配器+能力）的目录。

### 注册表结构

```
┌─────────────────────────────────────────────────────────────────┐
│                    统一工具注册表                                │
├─────────────────────────────────────────────────────────────────┤
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  │
│  │ AIOS 原生工具   │  │ MCP 服务器      │  │ A2A 代理        │  │
│  │                 │  │                 │  │                 │  │
│  │ • system.power  │  │ • mcp.filesystem│  │ • a2a.research  │  │
│  │ • system.audio  │  │ • mcp.github    │  │ • a2a.coding    │  │
│  │ • browser.chrome│  │ • mcp.database  │  │ • a2a.design    │  │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

### 工具发现机制

| 机制 | 说明 | 监控目标 |
|------|------|---------|
| **inotify** | 文件系统监控 | `.desktop` 文件目录 |
| **APT/dpkg** | 包管理器钩子 | 软件安装事件 |
| **AppStream** | 元数据解析 | 应用元数据 |
| **tool.aios.yaml** | 直接检测 | AIOS 工具描述文件 |
| **Adapter Card** | HTTP 发现 | `/.well-known/aios-adapter.json` |
| **MCP 桥接** | 协议转换 | 现有 MCP 服务器 |
| **OpenAPI 转换** | 自动生成 | REST API 规范 |

→ 详见 [发现机制规范](AIOS-Protocol-Discovery.md)

---

## 9. 传输层 (Transport)

### 定义

**传输层**定义了 AIOS 组件之间的通信方式，支持多种协议以适应不同场景。

### 支持的传输方式

| 传输方式 | 协议 | 特点 | 适用场景 |
|---------|------|------|---------|
| **stdio** | 标准输入输出 | 简单、低延迟 | 本地CLI、进程间通信 |
| **Unix Socket** | Unix Domain Socket | 高性能、本地 | 本地高性能通信 |
| **HTTP** | HTTP/1.1, HTTP/2 | 通用、跨网络 | 远程访问、云部署 |
| **WebSocket** | WS/WSS | 双向、实时 | 流式响应、实时通知 |

> **注意**：gRPC 等其他传输方式可作为非标准实现选项，但不属于协议官方规范。

### 传输层架构

```
┌─────────────────────────────────────────────────────────────────┐
│                    AIOS 传输层架构                               │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              JSON-RPC 2.0 消息层                         │   │
│  │         (统一的请求/响应/通知格式)                        │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              │                                  │
│  ┌───────────┬───────────┬───────────┬───────────┐             │
│  │  stdio    │ Unix Sock │   HTTP    │ WebSocket │             │
│  │  本地     │ 本地高性能│   远程    │  双向实时 │             │
│  └───────────┴───────────┴───────────┴───────────┘             │
│                                                                 │
│  注：其他传输方式（如 gRPC）可作为非标准实现选项                  │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

→ 详见 [传输规范](02-Transport.md)

---

## 10. 任务 (Task)

### 定义

**任务**是异步执行的工作单元，具有完整的生命周期和状态管理。

### 任务状态

| 状态 | 说明 |
|------|------|
| `pending` | 任务已创建，等待执行 |
| `working` | 任务正在执行 |
| `paused` | 任务已暂停 |
| `input_required` | 需要用户输入 |
| `auth_required` | 需要额外认证 |
| `completed` | 任务成功完成 |
| `failed` | 任务执行失败 |
| `canceled` | 任务被取消 |

→ 详见 [任务管理规范](AIOS-Protocol-TaskManagement.md)

---

## 11. Artifact（任务产物）

### 定义

**Artifact** 是任务执行产生的输出产物，可以包含多种类型的内容。

### Part 类型

| 类型 | 说明 |
|------|------|
| `text` | 文本内容 |
| `data` | 结构化数据 |
| `file` | 文件引用 |
| `image` | 图片 |
| `audio` | 音频 |
| `video` | 视频 |

→ 详见 [任务管理规范](AIOS-Protocol-TaskManagement.md)

---

## 12. 生态集成

### MCP 桥接

AIOS 与 MCP 是**互补关系**。桥接 MCP 服务器时，可叠加本地用户确认、审计和最小权限策略：

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   AIOS Client   │◄───►│   MCP Bridge    │◄───►│  MCP Server     │
│ (策略叠加/审计) │     │   (协议转换)     │     │  (工具实现)     │
└─────────────────┘     └─────────────────┘     └─────────────────┘
```

> **注意**：MCP 在认证授权方面持续演进（如 OAuth 2.1）。AIOS 的权限模型专注于系统控制域，桥接时提供额外的本地策略控制。

### A2A 桥接

AIOS 可以与 A2A 代理协作，实现跨系统任务：

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   AIOS Client   │◄───►│   A2A Bridge    │◄───►│  A2A Agent      │
│   (本地控制)    │     │   (任务委托)     │     │  (远程协作)     │
└─────────────────┘     └─────────────────┘     └─────────────────┘
```

→ 详见 [互操作性规范](AIOS-Protocol-Interoperability.md)

---

## 术语表

| 术语 | 英文 | 定义 |
|------|------|------|
| 适配器 | Adapter | 连接 AIOS 与目标软件的桥梁 |
| 能力 | Capability | 适配器暴露的具体控制功能 |
| 意图 | Intent | 用户自然语言表达的需求 |
| 权限 | Permission | 控制 AI 可执行操作的机制 |
| 能力令牌 | Capability Token | 权限授予的细粒度凭证 |
| 会话 | Session | 用户与 AIOS 交互的上下文环境 |
| 上下文 | Context | 执行能力时的环境信息 |
| 工具注册表 | Tool Registry | 可用工具的目录 |
| 任务 | Task | 异步执行的工作单元 |
| 产物 | Artifact | 任务执行产生的输出 |
| 适配器卡片 | Adapter Card | 适配器的能力声明文档 |
| 传输层 | Transport | 组件间通信方式 |
| MCP 桥接 | MCP Bridge | 调用 MCP 服务器的适配层 |
| A2A 桥接 | A2A Bridge | 与 A2A 代理协作的适配层 |

---

**文档版本**: 2.0.0  
**最后更新**: 2026-01-09  
**维护者**: AIOS Protocol Team
