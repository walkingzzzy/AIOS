# AIOS 便捷AI工具调用机制设计方案

> **系统开发口径修订（2026-03-08）**
> AIOS 统一定义为 **AI 原生操作系统 / 系统软件工程**。本文如提及桌面应用、Electron 客户端、应用适配器、App 安装等内容，除非明确标注为“原型期 / 兼容层 / 历史实现”，否则不再代表目标形态。
> 当前最高约束：**系统镜像、系统服务、系统壳层、设备/能力抽象、权限与更新恢复**。


**版本**: 2.0.0
**更新日期**: 2026-01-09
**状态**: 提案
**文档类型**: 💡 改进提案（设计参考）

> [!NOTE]
> 本文档是便捷工具调用机制的设计提案，用于指导 AIOS 工具集成的实现。
> 正式的 AIOS 协议规范请参见 [protocol/](../protocol/) 目录。

> [!WARNING]
> **API 命名迁移说明**：本文档早期版本使用旧版 API 命名；为与最新战略/规范对齐，本文示例已更新为新命名，旧命名仅保留在对照表中：
> | 旧 API | 新 API |
> |--------|--------|
> | `aios/tool.invoke` | `aios/capability.invoke` |
> | `aios/tool.list` | `aios/capability.list` |
> | `aios/discovery.*` | `aios/registry.*` |

---

## 一、问题陈述

### 1.1 当前MCP工具调用的痛点

基于深度网络搜索研究，我们识别出以下核心痛点：

| 痛点 | 影响 | 严重程度 |
|------|------|---------|
| **运行时依赖** | 用户需安装npx/uvx，配置复杂 | 🔴 高 |
| **上下文膨胀** | 多服务器消耗大量token | 🔴 高 |
| **发现困难** | 无标准注册表，信任度低 | 🟡 中 |
| **安全缺失** | 无权限模型，无用户确认 | 🔴 高 |
| **调试困难** | stdio脆弱，错误信息不足 | 🟡 中 |

### 1.2 理想的AI工具调用体验

```
用户: "帮我把这个PDF转成Word文档"

AI: [自动发现] → [权限检查] → [执行转换] → [返回结果]

无需:
- 用户安装任何运行时
- 用户配置任何服务器
- 用户理解技术细节
```

---

## 二、AIOS便捷工具调用架构

### 2.1 整体架构

```
┌─────────────────────────────────────────────────────────────────┐
│                    用户自然语言请求                              │
│                 "帮我把音量调到50%"                              │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                      AI 理解层                                   │
│              (LLM 解析意图，选择工具)                             │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                    AIOS Daemon                                   │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐             │
│  │ 工具发现    │  │ 权限管理    │  │ 执行引擎    │             │
│  │ Discovery   │  │ Permission  │  │ Executor    │             │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘             │
│         │                │                │                     │
│  ┌──────┴────────────────┴────────────────┴──────┐             │
│  │              统一工具注册表                    │             │
│  │  ┌─────────┐ ┌─────────┐ ┌─────────┐         │             │
│  │  │ 原生    │ │ MCP     │ │ A2A     │         │             │
│  │  │ 适配器  │ │ 桥接    │ │ 桥接    │         │             │
│  │  └─────────┘ └─────────┘ └─────────┘         │             │
│  └───────────────────────────────────────────────┘             │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                    执行层                                        │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐             │
│  │ D-Bus       │  │ CLI         │  │ 沙箱        │             │
│  │ 系统服务    │  │ 命令行      │  │ WASM/容器   │             │
│  └─────────────┘  └─────────────┘  └─────────────┘             │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 核心设计原则

| 原则 | 说明 | 实现方式 |
|------|------|---------|
| **零配置** | 用户无需配置即可使用 | 自动发现已安装软件 |
| **渐进式** | 从简单到复杂逐步增强 | L0-L4适配级别 |
| **安全优先** | 默认安全，显式授权 | 5级权限模型 |
| **协议兼容** | 兼容MCP/A2A生态 | 桥接适配器 |
| **本地优先** | 优先使用本地能力 | 减少网络依赖 |

---

## 三、便捷工具发现机制

### 3.1 自动软件发现

AIOS Daemon自动发现系统中已安装的软件：

```
┌─────────────────────────────────────────────────────────────────┐
│                    软件发现流程                                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  1. 扫描 .desktop 文件                                          │
│     /usr/share/applications/                                    │
│     ~/.local/share/applications/                                │
│                                                                 │
│  2. 解析软件信息                                                 │
│     Name, Exec, Categories, MimeType                            │
│                                                                 │
│  3. 匹配适配器                                                   │
│     已安装软件 ←→ 可用适配器                                     │
│                                                                 │
│  4. 注册到工具表                                                 │
│     tool_id → adapter → capabilities                            │
│                                                                 │
│  5. 实时监控 (inotify)                                          │
│     软件安装/卸载 → 自动更新注册表                               │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 适配级别

| 级别 | 名称 | 控制方式 | 能力 | 示例 |
|------|------|---------|------|------|
| **L0** | 基础 | 启动/关闭 | 仅启动应用 | 任意应用 |
| **L1** | 命令行 | CLI参数 | 带参数启动 | ffmpeg, git |
| **L2** | 通用协议 | D-Bus/AT-SPI | 基础UI控制 | GTK/Qt应用 |
| **L3** | 专用协议 | CDP/UNO等 | 深度控制 | Chrome, LibreOffice |
| **L4** | 原生API | Python API | 完全控制 | Blender, GIMP |

### 3.3 智能工具推荐

```python
# AI 请求工具时，使用 aios/registry.search 获取候选
# 推荐逻辑（排序、打分、理由）属于实现层能力，可作为附加字段返回
{
  "method": "aios/registry.search",
  "params": {
    "query": "编辑 PDF 文件",
    "context": {
      "file_type": "application/pdf",
      "operation": "edit"
    },
    "limit": 10
  }
}

# 响应
{
  "result": {
    "adapters": [
      {
        "id": "org.aios.office.libreoffice",
        "score": 0.95,
        "reason": "LibreOffice Draw 支持 PDF 编辑",
        "capability_ids": ["compat.office.open_pdf", "compat.office.edit_pdf", "compat.office.export_pdf"]
      },
      {
        "id": "mcp.pdf_tools",
        "score": 0.80,
        "reason": "MCP PDF 工具服务器",
        "capability_ids": ["mcp.pdf_tools.merge", "mcp.pdf_tools.split", "mcp.pdf_tools.convert"]
      }
    ],
    "total": 2
  }
}
```

---

## 四、简化的工具调用流程

### 4.1 单步调用

```json
// 传统MCP方式 - 需要多步
// 1. 配置服务器
// 2. 启动服务器
// 3. 初始化连接
// 4. 调用工具

// AIOS方式 - 单步调用
{
  "method": "aios/capability.invoke",
  "params": {
    "capability_id": "system.audio.set_volume",
    "arguments": {
      "level": 50
    }
  }
}
```

### 4.2 自然语言调用

```json
// 高级模式：直接使用自然语言
{
  "method": "aios/natural.execute",
  "params": {
    "request": "把音量调到50%",
    "context": {
      "user_id": "user-001",
      "session_id": "sess-001"
    }
  }
}

// AIOS自动：
// 1. 解析意图 → 调整音量
// 2. 选择能力 → system.audio.set_volume
// 4. 检查权限 → low（首次确认）
// 5. 执行操作 → 调用PulseAudio
// 6. 返回结果 → "音量已调整到50%"
```

### 4.3 批量操作

```json
// 批量执行多个操作
{
  "method": "aios/batch.execute",
  "params": {
    "operations": [
      {
        "tool_id": "org.aios.system.display",
        "capability_id": "system.display.set_brightness",
        "arguments": { "level": 70 }
      },
      {
        "tool_id": "org.aios.system.audio",
        "capability_id": "system.audio.set_volume",
        "arguments": { "level": 50 }
      },
      {
        "tool_id": "org.aios.system.power",
        "capability_id": "system.power.set_power_mode",
        "arguments": { "mode": "balanced" }
      }
    ],
    "options": {
      "atomic": false,  // 非原子操作，部分失败继续
      "parallel": true  // 并行执行
    }
  }
}
```

---

## 五、智能权限管理

### 5.1 权限预授权

```json
// 用户可以预先授权常用操作
{
  "method": "aios/permission.preset",
  "params": {
    "presets": [
      {
        "name": "日常办公",
        "grants": [
          "system.audio.*",
          "system.display.*",
          "compat.browser.open_url"
        ],
        "duration": "session"  // 会话期间有效
      },
      {
        "name": "开发模式",
        "grants": [
          "system.files.read_file",
          "system.files.write_file",
          "professional.development.vscode.*"
        ],
        "duration": "permanent"  // 永久有效
      }
    ]
  }
}
```

### 5.2 上下文感知权限

```json
// 根据上下文自动调整权限要求
{
  "context_rules": [
    {
      "condition": {
        "time": "09:00-18:00",
        "location": "office_network"
      },
      "auto_allow": ["medium"],
      "require_confirm": ["high", "critical"]
    },
    {
      "condition": {
        "time": "18:00-09:00",
        "location": "any"
      },
      "auto_allow": ["low"],
      "require_confirm": ["medium", "high", "critical"]
    }
  ]
}
```

### 5.3 权限令牌

```json
// 创建临时权限令牌
{
  "method": "aios/token.create",
  "params": {
    "capability_id": "system.files.write_file",
    "scope": "/home/user/documents/*",
    "duration": 3600,  // 1小时
    "max_uses": 10     // 最多使用10次
  }
}

// 响应
{
  "token": {
    "id": "tok_abc123",
    "expires_at": "2026-01-06T11:00:00Z",
    "remaining_uses": 10
  }
}
```

---

## 六、MCP兼容层设计

### 6.1 透明桥接

```
┌─────────────────────────────────────────────────────────────────┐
│                    AIOS MCP 透明桥接                             │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  AIOS Client                                                    │
│       │                                                         │
│       │ aios/capability.invoke                                  │
│       │ capability_id: "mcp.filesystem.write_file"              │
│       ▼                                                         │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                   MCP Bridge                             │   │
│  │                                                          │   │
│  │  1. 检测 mcp.* 前缀                                      │   │
│  │  2. 查找对应 MCP 服务器配置                              │   │
│  │  3. 自动启动服务器（如未运行）                           │   │
│  │  4. 转换 AIOS → MCP 消息格式                            │   │
│  │  5. 添加权限检查                                         │   │
│  │  6. 执行调用                                             │   │
│  │  7. 转换 MCP → AIOS 响应格式                            │   │
│  │                                                          │   │
│  └─────────────────────────────────────────────────────────┘   │
│       │                                                         │
│       │ tools/call                                              │
│       ▼                                                         │
│  MCP Server (filesystem)                                        │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 6.2 MCP服务器自动管理

```yaml
# AIOS自动管理MCP服务器生命周期
mcp_servers:
  filesystem:
    command: "uvx"
    args: ["mcp-server-filesystem", "--root", "/home/user"]
    auto_start: true      # 首次调用时自动启动
    auto_stop: true       # 空闲时自动停止
    idle_timeout: 300     # 5分钟无调用则停止
    restart_on_failure: true
    max_restarts: 3

  github:
    command: "uvx"
    args: ["mcp-server-github"]
    env:
      GITHUB_TOKEN: "${GITHUB_TOKEN}"
    auto_start: false     # 需要显式启动
```

### 6.3 权限增强

```json
// MCP工具调用时自动添加权限检查
{
  "method": "aios/capability.invoke",
  "params": {
    "capability_id": "mcp.filesystem.write_file",
    "arguments": {
      "path": "/etc/hosts",
      "content": "..."
    }
  }
}

// AIOS自动检测：
// 1. 目标路径 /etc/hosts 是系统文件
// 2. 风险级别提升为 critical
// 3. 需要二次确认
// 4. 返回确认请求给用户
```

---

## 七、开发者体验优化

### 7.1 适配器开发简化

```yaml
# tool.aios.yaml - 简化的适配器定义
adapter:
  id: org.aios.myapp
  name: 我的应用适配器
  version: 1.0.0

# 自动生成能力定义
auto_discover:
  dbus: true          # 自动发现D-Bus接口
  cli: true           # 自动发现CLI命令

# 手动定义的能力
capabilities:
  - id: org.aios.myapp.do_something
    name: 执行操作
    risk_level: medium
    handler:
      type: dbus
      service: org.myapp.Service
      method: DoSomething
```

### 7.2 调试工具

```bash
# AIOS CLI 调试命令
aios-cli debug inspect              # 启动Inspector UI
aios-cli debug messages             # 实时查看消息流
aios-cli debug permissions          # 查看权限状态
aios-cli debug tools                # 列出所有工具
aios-cli debug invoke <capability_id> --arguments '{...}'  # 手动调用测试
```

### 7.3 SDK示例

```python
# Python SDK - 简洁的API
from aios import AIOSClient

async with AIOSClient() as client:
    # 简单调用
    result = await client.invoke(
        capability_id="system.audio.set_volume",
        arguments={"level": 50}
    )

    # 自然语言调用
    result = await client.natural("把音量调到50%")

    # 批量调用
    results = await client.batch([
        {"capability_id": "system.audio.set_volume", "arguments": {"level": 50}},
        {"capability_id": "system.display.set_brightness", "arguments": {"level": 70}},
    ])

    # 订阅事件
    async for event in client.subscribe("system.power.*"):
        print(f"电源事件: {event}")
```

---

## 八、性能优化

### 8.1 连接池

```
┌─────────────────────────────────────────────────────────────────┐
│                    连接池管理                                    │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                   Connection Pool                        │   │
│  │                                                          │   │
│  │  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐    │   │
│  │  │ D-Bus   │  │ Unix    │  │ MCP     │  │ HTTP    │    │   │
│  │  │ 连接    │  │ Socket  │  │ stdio   │  │ 连接    │    │   │
│  │  │ (复用)  │  │ (复用)  │  │ (管理)  │  │ (复用)  │    │   │
│  │  └─────────┘  └─────────┘  └─────────┘  └─────────┘    │   │
│  │                                                          │   │
│  │  策略:                                                   │   │
│  │  - 最大连接数: 100                                       │   │
│  │  - 空闲超时: 5分钟                                       │   │
│  │  - 健康检查: 30秒                                        │   │
│  │                                                          │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 8.2 缓存策略

```json
// 工具描述缓存
{
  "cache": {
    "tool_descriptions": {
      "ttl": 3600,           // 1小时
      "invalidate_on": ["tool_update", "adapter_reload"]
    },
    "permission_grants": {
      "ttl": 300,            // 5分钟
      "invalidate_on": ["grant_change", "revoke"]
    },
    "discovery_results": {
      "ttl": 60,             // 1分钟
      "invalidate_on": ["app_install", "app_uninstall"]
    }
  }
}
```

### 8.3 懒加载

```json
// 工具描述分层加载
{
  "tool_id": "org.aios.browser.chrome",
  "summary": "Chrome浏览器控制",           // 始终加载 (~50 tokens)
  "capabilities_count": 15,

  // 按需加载
  "capabilities": "lazy",                   // 调用时才加载
  "examples": "lazy",                       // 调用时才加载
  "schema": "lazy"                          // 调用时才加载
}
```

---

## 九、实施路线图

### 9.1 Phase 1: 基础框架 (2周)

| 任务 | 说明 | 优先级 |
|------|------|--------|
| 统一工具注册表 | 管理所有工具来源 | P0 |
| 简化调用接口 | 单步调用API | P0 |
| 权限检查集成 | 调用前权限验证 | P0 |

### 9.2 Phase 2: MCP集成 (2周)

| 任务 | 说明 | 优先级 |
|------|------|--------|
| MCP Client实现 | 连接MCP服务器 | P0 |
| 协议转换层 | AIOS ↔ MCP | P0 |
| 服务器生命周期 | 自动启停管理 | P1 |

### 9.3 Phase 3: 智能增强 (2周)

| 任务 | 说明 | 优先级 |
|------|------|--------|
| 工具推荐 | 基于意图推荐工具 | P1 |
| 自然语言接口 | 直接自然语言调用 | P1 |
| 上下文权限 | 基于上下文的权限 | P2 |

### 9.4 Phase 4: 开发者工具 (2周)

| 任务 | 说明 | 优先级 |
|------|------|--------|
| CLI工具 | aios-cli | P1 |
| Inspector | 调试UI | P1 |
| SDK完善 | Python/TS SDK | P1 |

---

## 十、总结

### 10.1 AIOS便捷工具调用的核心优势

| 优势 | 说明 |
|------|------|
| **零配置** | 自动发现，无需用户配置 |
| **单步调用** | 简化的API，减少样板代码 |
| **安全内置** | 权限检查自动集成 |
| **协议兼容** | 透明支持MCP/A2A |
| **智能推荐** | 基于意图的工具推荐 |
| **性能优化** | 连接池、缓存、懒加载 |

### 10.2 与MCP的关系

AIOS 与 MCP 是**互补集成**的关系，各有侧重：

| 协议 | 侧重点 | 核心能力 |
|------|--------|---------|
| **MCP** | AI 调用外部工具 | 工具定义、资源访问、提示模板 |
| **AIOS** | AI 系统控制 | 权限模型、安全沙箱、系统级能力 |

AIOS 通过桥接层与 MCP 互补集成：
1. **权限增强**: 为 MCP 工具添加 5 级权限控制
2. **生命周期管理**: 自动管理 MCP 服务器启停
3. **系统级扩展**: 提供 MCP 不涉及的系统控制能力
4. **统一入口**: 原生适配器与 MCP 工具统一调用接口

### 10.3 预期效果

| 指标 | 当前(MCP) | 目标(AIOS) |
|------|----------|-----------|
| 配置复杂度 | 高 | 低 |
| 首次使用时间 | 30分钟+ | 5分钟 |
| Token消耗 | 高 | 低(懒加载) |
| 安全性 | 低 | 高 |
| 开发者体验 | 中 | 高 |

---

**文档版本**: 2.0.0
**最后更新**: 2026-01-09
**维护者**: AIOS Protocol Team
