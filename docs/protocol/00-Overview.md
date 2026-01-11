# AIOS Protocol 协议总览

**版本**: 2.0.0  
**更新日期**: 2026-01-09  
**状态**: 战略规划阶段

---

## 什么是 AIOS Protocol

**AIOS Protocol** 是 AI 系统控制的开放标准 —— 定义 AI 如何描述、调用和安全执行系统控制能力。

> **核心设计原则**：标准化「接口」，而非「实现」—— 与 MCP 互补，专注系统控制领域。

```
用户 → "帮我把壁纸换成蓝色的"
       ↓
AI 引擎 → 理解意图: 更换壁纸
       ↓
AIOS Protocol → 调用能力: system.desktop.set_wallpaper
       ↓
操作系统 → 壁纸已更换 ✓
```

### 核心价值

| 特性 | 说明 |
|------|------|
| **系统控制** | 专注操作系统、桌面应用、专业软件控制（MCP 不涉及的领域） |
| **标准化接口** | 使用原生 API 而非截图点击，快速可靠 |
| **安全可控** | 5 级权限模型，敏感操作需要用户确认 |
| **开放协议** | 语言无关，支持多种 SDK 和部署方式 |
| **可扩展** | 开发者可为任何软件创建适配器 |

### 与 MCP 的关系

| 维度 | MCP | AIOS |
|------|-----|------|
| **领域** | 工具调用（API、数据库、文件） | 系统控制（操作系统、桌面应用） |
| **关系** | 互补 | 互补 |
| **权限模型** | 无标准（正在添加） | 5 级内置 |

---

## 开放协议设计

### 多语言SDK支持

AIOS协议是**语言无关**的，基于JSON-RPC 2.0，支持多种编程语言：

| 语言 | SDK | 状态 | 适用场景 |
|------|-----|------|---------|
| **Python** | aios-sdk | 开发中 | 快速开发、AI集成 |
| **TypeScript** | @aios/sdk | 计划中 | Web、Node.js |
| **Go** | aios-go | 计划中 | 高性能服务 |
| **Rust** | aios-rs | 核心实现 | 系统级适配器 |

### 多传输方式

| 传输方式 | 位置 | 适用场景 |
|---------|------|---------|
| **stdio** | 本地 | CLI工具、MCP兼容 |
| **Unix Socket** | 本地 | 高性能本地通信 |
| **HTTP/SSE** | 远程 | 云服务、远程访问 |
| **WebSocket** | 远程 | 双向实时通信 |

### 多部署方式

| 部署方式 | 说明 |
|---------|------|
| **本地进程** | 传统方式，AIOS Daemon管理 |
| **Docker容器** | 隔离部署，便于分发 |
| **Serverless** | Cloudflare Workers、AWS Lambda |
| **远程服务** | 任何HTTP端点 |

→ 详见 [传输层规范](02-Transport.md) 和 [协议开放化方案](../research/AIOS-Protocol-Enhancement-Proposal.md)

---

## 核心概念速览

### 适配器 (Adapter)

连接 AIOS 与具体软件的桥梁，定义 AI 如何控制该软件。

```yaml
# 示例: Chrome 浏览器适配器
tool:
  id: "org.aios.browser.chrome"
  name: "Chrome 浏览器"
  type: "browser"
```

### 能力 (Capability)

适配器对外暴露的具体控制功能。

```yaml
capabilities:
  - id: "app.browser.open_url"
    name: "打开网址"
    input:
      properties:
        url: { type: string }
```

### 权限 (Permission)

控制 AI 可以执行哪些操作，分为 5 个级别：

| 级别 | 确认方式 | 示例 |
|------|---------|------|
| public | 无需 | 读取时间 |
| low | 首次 | 调整音量 |
| medium | 首次 | 打开浏览器 |
| high | 每次 | 发送消息 |
| critical | 二次确认 | 删除文件 |

→ 详见 [核心概念](01-CoreConcepts.md) 和 [权限模型](05-PermissionModel.md)

---

## 三层控制架构

```
┌─────────────────────────────────────────────────────────────────┐
│  第一层: 系统控制                                                │
│  控制操作系统基础功能 (壁纸、音量、电源、文件)                      │
│  技术: D-Bus, gsettings, systemd                                │
├─────────────────────────────────────────────────────────────────┤
│  第二层: 视觉控制 (Vision)                                       │
│  基于视觉识别的通用控制，作为无 API 软件的兜底方案                   │
│  技术: VLM (UI-TARS), 仿生输入 (贝塞尔曲线+随机延迟)               │
├─────────────────────────────────────────────────────────────────┤
│  第三层: 应用控制 (API/MCP)                                      │
│  基于 API 的深度集成 (浏览器、专业软件、MCP 工具)                   │
│  技术: DevTools Protocol, UNO API, Python API, MCP              │
├─────────────────────────────────────────────────────────────────┤
│  混合计算: 双栈运行模式                                          │
│  Standard Mode (端侧<500ms) + Pro Mode (云端<2s)                │
└─────────────────────────────────────────────────────────────────┘
```

### 用户场景示例

| 层级 | 用户说 | AI 执行 |
|------|-------|---------|
| 系统 | "10分钟后关机" | systemd 定时关机 |
| 通用 | "比较京东淘宝耳机价格" | 打开浏览器，搜索比较 |
| 专业 | "用 Blender 创建低多边形小狗" | 调用 bpy API 建模 |

---

## 协议特性

### 安全优先

- **5 级权限模型**：从 public 到 critical
- **能力令牌**：细粒度、有时效、可撤销
- **多层沙箱**：WASM → 容器 → VM
- **AI Guardrails**：输入验证、输出过滤、行为监控

### 协议生命周期

AIOS 定义了完整的连接生命周期：

```
Client                              Server
  │                                    │
  │──── aios/initialize ──────────────>│  (版本协商、能力声明)
  │<─── initialize result ─────────────│
  │──── aios/initialized ─────────────>│
  │                                    │
  │         [Ready - 正常通信]          │
  │                                    │
  │──── aios/shutdown ────────────────>│
```

→ 详见 [协议生命周期](AIOS-Protocol-Lifecycle.md)

### 任务管理

支持完整的任务状态机（8 状态）：

| 状态 | 说明 |
|------|------|
| pending | 等待执行 |
| working | 执行中 |
| paused | 已暂停 |
| input_required | 需要用户输入 |
| auth_required | 需要额外认证 |
| completed | 已完成 |
| failed | 失败 |
| canceled | 已取消 |

→ 详见 [任务管理](AIOS-Protocol-TaskManagement.md)

### 发现机制

支持标准化的适配器发现：

- **Adapter Card**: `/.well-known/aios-adapter.json`
- **本地发现**: .desktop 文件 + inotify 监控
- **签名验证**: JWS (RFC 7515) 签名

→ 详见 [发现机制](AIOS-Protocol-Discovery.md)

### MCP/A2A 兼容

AIOS 与 MCP/A2A 是**互补关系**：

```
┌─────────────────────────────────────────────────────────────────┐
│                    AIOS Protocol (系统控制)                      │
├─────────────────────────────────────────────────────────────────┤
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  │
│  │  原生系统控制    │  │  MCP 桥接       │  │  A2A 桥接       │  │
│  │  (D-Bus/CLI)    │  │  (工具调用)     │  │  (远程协作)     │  │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

**桥接时的策略叠加**：
- 桥接 MCP 工具时，可叠加本地用户确认、审计、最小权限策略
- 统一调用接口，自动检测协议类型
- 跨协议操作的统一审计追踪

> **注意**：MCP 在认证授权方面持续演进（如 OAuth 2.1），其目标是工具调用域。AIOS 的权限模型专注于系统控制域。

**MCP桥接能力**：
- 调用任何MCP服务器（本地stdio或远程HTTP）
- 桥接时可叠加本地策略和沙箱隔离
- 支持mcp-remote/mcp-proxy桥接工具
- OpenAPI规范可自动转换为AIOS工具

→ 详见 [协议互操作](AIOS-Protocol-Interoperability.md) 和 [MCP分析报告](../research/MCP-Protocol-Analysis-Report.md)

---

## 快速示例

### 请求：调用能力

```json
{
  "jsonrpc": "2.0",
  "id": "req-001",
  "method": "aios/capability.invoke",
  "params": {
    "capability_id": "system.desktop.set_wallpaper",
    "arguments": {
      "path": "/home/user/blue.jpg",
      "mode": "fill"
    }
  }
}
```

### 响应：执行成功

```json
{
  "jsonrpc": "2.0",
  "id": "req-001",
  "result": {
    "success": true,
    "message": "壁纸已更换",
    "data": {
      "previous_path": "/usr/share/backgrounds/default.jpg",
      "current_path": "/home/user/blue.jpg"
    }
  }
}
```

→ 详见 [传输层规范](02-Transport.md) 和 [消息类型](03-Messages.md)

---

## 与现有方案对比

| 方案 | 控制方式 | 速度 | 可靠性 | 安全性 |
|------|---------|------|--------|--------|
| Claude Computer Use | 截图+坐标点击 | 慢 | 低 | 依赖模型 |
| MCP | API 调用 | 快 | 高 | 无权限模型 |
| A2A | Agent 间通信 | 中 | 高 | 无标准 |
| **AIOS Protocol** | 标准化接口 | 快 | 高 | 5级权限+沙箱 |

### AIOS 的独特价值

1. **用户导向**：面向终端用户，而非开发者
2. **系统级控制**：控制操作系统，而非仅调用工具
3. **安全优先**：内置权限模型，MCP/A2A 无此功能
4. **软件自动发现**：自动识别已安装软件

---

## 下一步

| 目标 | 推荐文档 |
|------|---------|
| 理解核心概念 | [核心概念](01-CoreConcepts.md) |
| 了解消息格式 | [传输层规范](02-Transport.md) |
| 了解生命周期 | [协议生命周期](AIOS-Protocol-Lifecycle.md) |
| 了解任务管理 | [任务管理](AIOS-Protocol-TaskManagement.md) |
| 了解发现机制 | [发现机制](AIOS-Protocol-Discovery.md) |
| 开发适配器 | [适配器开发](../adapters/01-Development.md) |
| 了解安全设计 | [安全模型](AIOS-Protocol-Security.md) |
| 协议差距分析 | [差距分析](AIOS-Protocol-GapAnalysis.md) |

---

**文档版本**: 2.0.0  
**最后更新**: 2026-01-09  
**维护者**: AIOS Protocol Team
