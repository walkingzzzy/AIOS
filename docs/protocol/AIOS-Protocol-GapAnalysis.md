# AIOS Protocol 协议差距分析报告

**版本**: 2.0.0  
**更新日期**: 2026-01-09  
**状态**: 深度分析报告（开放化更新）

---

## 一、概述

本报告基于对 **MCP (Model Context Protocol, 2025-06-18版)** 和 **A2A (Agent-to-Agent Protocol, DRAFT v1.0)** 两大标准协议的**深度分析**，对比 AIOS Protocol 现有设计，识别出需要补充和完善的领域。

### 1.1 协议版本信息

| 协议 | 版本 | 发布日期 | 主要特性 |
|------|------|---------|---------|
| MCP | 2025-06-18 | 2025-06-18 | Streamable HTTP, OAuth 2.1, Elicitation |
| A2A | DRAFT v1.0 | 2025 | Agent Card签名, 多协议绑定, Extensions |
| AIOS | 0.3.0 | 2026-01-05 | 5级权限, 软件发现, 适配器生态 |

### 1.2 协议对比总览

| 特性 | MCP (2025-06-18) | A2A (DRAFT v1.0) | AIOS (当前) | 差距评估 |
|------|------------------|------------------|-------------|----------|
| **发现机制** | 配置文件 + 能力协商 | Agent Card + /.well-known + JWS签名 | .desktop + tool.aios.yaml | 🔴 需要标准化端点和签名 |
| **传输协议** | JSON-RPC 2.0 + Streamable HTTP | HTTP + JSON-RPC + gRPC + SSE | JSON-RPC 2.0 + Unix Socket | 🟡 需要HTTP传输支持 |
| **生命周期** | initialize → initialized → shutdown | 无状态 + Agent Card | session (部分) | 🔴 需要完善握手流程 |
| **版本协商** | 协议版本协商 | A2A-Version头 | ❌ 缺失 | 🔴 需要添加 |
| **任务管理** | 简单请求-响应 | 完整状态机 (7状态) | 部分实现 | 🟡 已有草案，需完善 |
| **多模态** | Resources + 内容类型 | Part/Artifact | 基础支持 | 🟡 需要规范化 |
| **权限模型** | ❌ 无 | 基础认证 (OAuth2/OIDC/mTLS) | ✅ 5级权限 | 🟢 AIOS优势 |
| **认证授权** | OAuth 2.1 + PKCE | OAuth2/OIDC/API Key/mTLS | 会话令牌 | 🟡 需要OAuth集成 |
| **扩展机制** | 实验性功能 | Extensions URI | x-前缀 | 🟡 需要规范化 |
| **SDK** | Python/TS/Java/Go/C#/Kotlin | Python/Go/JS/Java | Python (设计中) | 🔴 需要多语言SDK |
| **开发工具** | Inspector | - | - | 🔴 需要调试工具 |

---

## 二、MCP协议深度分析 (2025-06-18版)

### 2.1 MCP核心架构

```
┌─────────────────────────────────────────────────────────────────┐
│                    MCP 协议架构 (2025-06-18)                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────┐         ┌─────────────┐                       │
│  │   Client    │ ←────→  │   Server    │                       │
│  │  (AI Host)  │         │  (Tool)     │                       │
│  └─────────────┘         └─────────────┘                       │
│        │                       │                               │
│        │  Capabilities:        │  Features:                    │
│        │  • roots              │  • prompts                    │
│        │  • sampling           │  • resources                  │
│        │  • elicitation        │  • tools                      │
│        │                       │  • logging                    │
│        │                       │  • completions                │
│                                                                 │
│  Transport: stdio | Streamable HTTP (替代HTTP+SSE)              │
│  Authorization: OAuth 2.1 + PKCE + RFC8414 + RFC7591           │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 MCP生命周期详解

**初始化序列**:
```
Client                              Server
  │                                    │
  │──── initialize ───────────────────>│
  │     {protocolVersion, capabilities,│
  │      clientInfo}                   │
  │                                    │
  │<─── initialize result ─────────────│
  │     {protocolVersion, capabilities,│
  │      serverInfo, instructions}     │
  │                                    │
  │──── initialized (notification) ───>│
  │                                    │
  │         [Ready for operations]     │
  │                                    │
  │──── shutdown ─────────────────────>│ (或 ping/pong 心跳)
  │                                    │
```

**关键特性**:
- `protocolVersion`: 版本协商，服务端选择支持的最高版本
- `capabilities`: 双向能力声明
- `instructions`: 服务端可提供使用说明给LLM

### 2.3 MCP能力协商机制

**客户端能力 (Client Capabilities)**:
| 能力 | 说明 | AIOS对应 |
|------|------|---------|
| `roots` | 提供文件系统根目录 | ❌ 缺失 |
| `sampling` | 允许服务端请求LLM补全 | ❌ 缺失 |
| `elicitation` | 允许服务端请求用户输入 | 🟡 部分 (权限确认) |

**服务端能力 (Server Capabilities)**:
| 能力 | 说明 | AIOS对应 |
|------|------|---------|
| `prompts` | 提供提示模板 | ✅ tool.system_prompt |
| `resources` | 提供可读资源 | ✅ aios/resource.* |
| `tools` | 提供可调用工具 | ✅ aios/capability.* |
| `logging` | 日志级别控制 | 🟡 审计日志 |
| `completions` | 参数自动补全 | ❌ 缺失 |

### 2.4 MCP传输层演进

**Streamable HTTP (新增，替代HTTP+SSE)**:
```
POST /mcp HTTP/1.1
Content-Type: application/json
Mcp-Session-Id: session-123

{"jsonrpc":"2.0","id":1,"method":"tools/call",...}

---
HTTP/1.1 200 OK
Content-Type: text/event-stream
Mcp-Session-Id: session-123

event: message
data: {"jsonrpc":"2.0","id":1,"result":{...}}
```

**会话管理**:
- `Mcp-Session-Id` 头用于会话标识
- 支持会话恢复和状态保持
- DELETE请求用于终止会话

### 2.5 MCP OAuth 2.1 授权

**授权流程**:
```
1. 客户端发现授权服务器 (RFC8414 /.well-known/oauth-authorization-server)
2. 动态客户端注册 (RFC7591, 可选)
3. Authorization Code + PKCE 流程
4. Token绑定到audience (防止token滥用)
5. TLS必需 (远程连接)
```

**AIOS差距**: 当前仅有会话令牌，缺少标准OAuth集成

---

## 三、A2A协议深度分析 (DRAFT v1.0)

### 3.1 A2A核心架构

```
┌─────────────────────────────────────────────────────────────────┐
│                    A2A 协议架构 (DRAFT v1.0)                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    Agent Card                            │   │
│  │  /.well-known/agent-card.json (可选JWS签名)              │   │
│  │  • name, description, version                           │   │
│  │  • url, protocolVersion                                 │   │
│  │  • capabilities (streaming, pushNotifications)          │   │
│  │  • skills[] (id, name, description, examples)           │   │
│  │  • authentication (schemes, credentials)                │   │
│  │  • extensions[]                                         │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  Protocol Bindings:                                            │
│  • JSON-RPC 2.0 over HTTP                                      │
│  • gRPC (可选)                                                  │
│  • HTTP+JSON/REST (可选)                                        │
│                                                                 │
│  Streaming: SSE with TaskStatusUpdateEvent, TaskArtifactUpdate │
│  Push Notifications: Webhooks with authentication              │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 A2A Agent Card规范

```json
{
  "name": "Research Agent",
  "description": "专业研究助手",
  "url": "https://agent.example.com",
  "version": "1.0.0",
  "protocolVersion": "1.0",
  
  "capabilities": {
    "streaming": true,
    "pushNotifications": true,
    "stateTransitionHistory": true
  },
  
  "skills": [
    {
      "id": "web_research",
      "name": "网络研究",
      "description": "搜索和分析网络信息",
      "examples": ["研究AI发展趋势", "查找竞品分析"]
    }
  ],
  
  "authentication": {
    "schemes": ["oauth2", "apiKey"],
    "credentials": "..."
  },
  
  "extensions": [
    "urn:example:custom-extension:1.0"
  ],
  
  "signature": {
    "algorithm": "RS256",
    "keyId": "key-001",
    "value": "..."
  }
}
```

**关键特性**:
- JWS签名 (RFC 7515) 用于验证Agent身份
- Extensions机制支持协议扩展
- Skills提供语义化能力描述

### 3.3 A2A任务状态机

```
                         ┌─────────────────────────────────────┐
                         │                                     │
                         ▼                                     │
┌─────────┐    ┌─────────────┐    ┌─────────────┐             │
│submitted│───>│   working   │───>│  completed  │             │
└────┬────┘    └──────┬──────┘    └─────────────┘             │
     │                │                                        │
     │                ├───> input-required ────────────────────┤
     │                │                                        │
     │                ├───> auth-required ─────────────────────┤
     │                │                                        │
     │                ├───> failed ────────────────────────────┤
     │                │                                        │
     └────────────────┴───> canceled ──────────────────────────┘
                      │
                      └───> rejected (新增)
```

**状态说明**:
| 状态 | 说明 | AIOS对应 |
|------|------|---------|
| `submitted` | 任务已提交 | pending |
| `working` | 任务执行中 | working |
| `input-required` | 需要用户输入 | input_required |
| `auth-required` | 需要认证 | ❌ 缺失 |
| `completed` | 任务完成 | completed |
| `failed` | 任务失败 | failed |
| `canceled` | 任务取消 | canceled |
| `rejected` | 任务被拒绝 | ❌ 缺失 |

### 3.4 A2A Part类型 (v1.0更新)

```json
{
  "parts": [
    {"type": "text", "text": "分析结果如下："},
    {
      "type": "file",
      "file": {
        "name": "report.pdf",
        "mimeType": "application/pdf",
        "bytes": "base64...",
        "uri": "https://..."
      }
    },
    {
      "type": "data",
      "data": {"chart": {...}}
    }
  ]
}
```

**注意**: v1.0移除了`kind`字段，改用`type`

### 3.5 A2A服务参数

**HTTP头**:
| 头 | 说明 | AIOS对应 |
|---|------|---------|
| `A2A-Version` | 协议版本 | ❌ 缺失 |
| `A2A-Extensions` | 启用的扩展 | ❌ 缺失 |
| `A2A-Request-Id` | 请求追踪ID | ❌ 缺失 |

### 3.6 A2A扩展机制

```json
{
  "extensions": [
    "urn:ietf:params:a2a:ext:priority:1.0",
    "urn:example:custom:1.0"
  ]
}
```

**扩展URI格式**: `urn:<namespace>:<extension-name>:<version>`

---

## 四、高优先级差距详解

### 4.1 发现和注册机制

#### 差距分析

| 特性 | MCP | A2A | AIOS现状 | 差距 |
|------|-----|-----|---------|------|
| 发现端点 | 配置文件 | /.well-known/agent-card.json | ❌ 无 | 🔴 高 |
| 能力协商 | initialize握手 | Agent Card | 部分 | 🟡 中 |
| 身份验证 | - | JWS签名 | ❌ 无 | 🔴 高 |
| 动态发现 | ❌ | ✅ | .desktop监控 | 🟡 中 |

#### 建议补充

**1. 定义 AIOS Adapter Card 规范**

```yaml
# /.well-known/aios-adapter.json 或 /aios/adapter.json
adapter:
  id: "org.aios.browser.chrome"
  name: "Chrome 浏览器适配器"
  version: "1.0.0"
  protocol_version: "0.3.0"
  
  # 能力声明 (对齐MCP/A2A)
  capabilities:
    streaming: true
    batch_operations: true
    async_tasks: true
    push_notifications: false
    
  # 技能/能力列表 (对齐A2A skills)
  skills:
    - id: "app.browser.open_url"
      name: "打开网址"
      description: "在浏览器中打开指定URL"
      permission_level: "medium"
      examples:
        - "打开京东首页"
        - "访问 https://example.com"
    - id: "app.browser.extract_content"
      name: "提取页面内容"
      permission_level: "low"
      
  # 认证要求 (对齐A2A authentication)
  authentication:
    required: false
    schemes: []
    
  # 端点信息
  endpoints:
    rpc: "unix:///run/user/1000/aios/chrome.sock"
    http: "http://localhost:9527/adapters/chrome"
    health: "/health"
    
  # 签名 (对齐A2A JWS)
  signature:
    algorithm: "RS256"
    key_id: "aios-adapter-key-001"
    value: "..."
```

**2. 添加版本协商 (对齐MCP)**

```json
// 请求
{
  "jsonrpc": "2.0",
  "id": "init-001",
  "method": "aios/initialize",
  "params": {
    "protocol_version": "0.3.0",
    "supported_versions": ["0.3.0", "0.2.0"],
    "client_info": {
      "name": "aios-client",
      "version": "1.0.0"
    },
    "capabilities": {
      "streaming": true,
      "batch": true,
      "notifications": true
    }
  }
}

// 响应
{
  "jsonrpc": "2.0",
  "id": "init-001",
  "result": {
    "protocol_version": "0.3.0",
    "server_info": {
      "name": "aios-daemon",
      "version": "1.0.0",
      "instructions": "AIOS守护进程，支持系统控制和软件适配"
    },
    "capabilities": {
      "streaming": true,
      "batch": true,
      "max_concurrent_tasks": 10
    },
    "session_id": "sess-001"
  }
}
```

**3. 添加服务参数头 (对齐A2A)**

| HTTP头 | 说明 |
|--------|------|
| `AIOS-Version` | 协议版本 |
| `AIOS-Session-Id` | 会话标识 (对齐MCP Mcp-Session-Id) |
| `AIOS-Request-Id` | 请求追踪ID |
| `AIOS-Extensions` | 启用的扩展 |

---

### 4.2 协议生命周期完善

#### 差距分析

| 特性 | MCP | A2A | AIOS现状 | 差距 |
|------|-----|-----|---------|------|
| 初始化握手 | initialize/initialized | 无状态 | 部分 | 🟡 中 |
| 版本协商 | ✅ | A2A-Version头 | ❌ | 🔴 高 |
| 心跳机制 | ping/pong | - | 设计中 | 🟡 中 |
| 优雅关闭 | shutdown | - | 设计中 | 🟡 中 |
| 会话恢复 | Mcp-Session-Id | contextId | ❌ | 🔴 高 |

#### 建议补充

已在 `AIOS-Protocol-Lifecycle.md` 中定义，需要补充:

**1. 会话恢复机制 (对齐MCP)**

```json
// 重连时携带之前的session_id
{
  "method": "aios/initialize",
  "params": {
    "session_recovery": {
      "previous_session_id": "sess-001",
      "last_message_id": "msg-100"
    }
  }
}
```

**2. 能力变更通知 (对齐MCP)**

```json
// 服务端能力变更时通知客户端
{
  "jsonrpc": "2.0",
  "method": "aios/notification.capabilities_changed",
  "params": {
    "added": ["new_capability"],
    "removed": ["old_capability"]
  }
}
```

---

### 4.3 任务管理完善

#### 差距分析

| 特性 | MCP | A2A | AIOS现状 | 差距 |
|------|-----|-----|---------|------|
| 状态机 | 简单 | 7状态 | 7状态 | 🟢 已有 |
| auth_required状态 | - | ✅ | ❌ | 🔴 高 |
| rejected状态 | - | ✅ | ❌ | 🟡 中 |
| 任务历史 | - | stateTransitionHistory | ❌ | 🟡 中 |
| 推送通知 | - | webhooks | ❌ | 🟡 中 |

#### 建议补充

**1. 添加 auth_required 状态**

```json
// 任务需要额外认证
{
  "task_id": "task-001",
  "status": "auth_required",
  "auth_request": {
    "type": "oauth2",
    "authorization_url": "https://auth.example.com/authorize",
    "scopes": ["read", "write"],
    "reason": "访问受保护资源需要用户授权"
  }
}
```

**2. 添加状态转换历史**

```json
{
  "task_id": "task-001",
  "status": "completed",
  "state_history": [
    {"state": "pending", "timestamp": "2026-01-05T10:00:00Z"},
    {"state": "working", "timestamp": "2026-01-05T10:00:01Z"},
    {"state": "input_required", "timestamp": "2026-01-05T10:00:30Z", "reason": "需要选择商品"},
    {"state": "working", "timestamp": "2026-01-05T10:01:00Z"},
    {"state": "completed", "timestamp": "2026-01-05T10:02:00Z"}
  ]
}
```

**3. 添加推送通知支持 (对齐A2A webhooks)**

```json
// 注册webhook
{
  "method": "aios/task.subscribe_webhook",
  "params": {
    "task_id": "task-001",
    "webhook_url": "https://client.example.com/aios/webhook",
    "events": ["status", "artifact"],
    "authentication": {
      "type": "bearer",
      "token": "..."
    }
  }
}
```

---

### 4.4 多模态和Artifact支持

#### 差距分析

| 特性 | MCP | A2A | AIOS现状 | 差距 |
|------|-----|-----|---------|------|
| Part类型定义 | 内容类型 | text/file/data | 基础 | 🟡 中 |
| Artifact概念 | Resources | ✅ | 设计中 | 🟡 中 |
| 流式Artifact | ✅ | lastChunk | ❌ | 🔴 高 |
| 内容协商 | ✅ | mimeType | ❌ | 🟡 中 |

#### 建议补充

已在 `AIOS-Protocol-TaskManagement.md` 中有基础定义，需要补充:

**1. 流式Artifact支持 (对齐A2A)**

```json
// 流式Artifact事件
{
  "event": "task.artifact_chunk",
  "data": {
    "task_id": "task-001",
    "artifact": {
      "id": "art-001",
      "name": "分析报告",
      "index": 0,
      "parts": [
        {"type": "text", "text": "第一部分内容..."}
      ],
      "last_chunk": false,
      "append": true
    }
  }
}
```

**2. 内容协商机制**

```json
// 客户端声明支持的内容类型
{
  "method": "aios/initialize",
  "params": {
    "content_negotiation": {
      "supported_types": [
        "text/plain",
        "text/markdown",
        "application/json",
        "image/png",
        "image/jpeg",
        "audio/wav"
      ],
      "max_inline_size": 1048576,
      "prefer_uri": true
    }
  }
}
```

---

## 五、中优先级差距详解

### 5.1 认证授权框架

#### 差距分析

| 特性 | MCP | A2A | AIOS现状 | 差距 |
|------|-----|-----|---------|------|
| OAuth 2.0/2.1 | ✅ OAuth 2.1 + PKCE | ✅ OAuth2 | 会话令牌 | 🔴 高 |
| OIDC | - | ✅ | ❌ | 🟡 中 |
| API Key | - | ✅ | ❌ | 🟡 中 |
| mTLS | - | ✅ | ❌ | 🟡 中 |
| 动态客户端注册 | RFC7591 | - | ❌ | 🟡 中 |
| Token Audience | ✅ | - | ❌ | 🟡 中 |

#### 建议补充

**1. OAuth 2.0/OIDC 集成规范**

```yaml
# 认证配置
authentication:
  schemes:
    - type: "oauth2"
      flows:
        authorization_code:
          authorization_url: "https://auth.example.com/authorize"
          token_url: "https://auth.example.com/token"
          scopes:
            "aios.read": "读取权限"
            "aios.write": "写入权限"
            "aios.admin": "管理权限"
      pkce_required: true  # 对齐MCP OAuth 2.1
      
    - type: "oidc"
      issuer: "https://auth.example.com"
      
    - type: "api_key"
      header: "X-AIOS-API-Key"
      
    - type: "bearer"
      header: "Authorization"
      
    - type: "mtls"
      client_cert_required: true
```

**2. 速率限制规范 (新增)**

```json
// 响应头
{
  "X-RateLimit-Limit": "1000",
  "X-RateLimit-Remaining": "999",
  "X-RateLimit-Reset": "1704456000",
  "X-RateLimit-Policy": "1000;w=3600"
}

// 超限错误
{
  "error": {
    "code": -32006,
    "message": "Rate limited",
    "data": {
      "retry_after_ms": 60000,
      "limit": 1000,
      "window_seconds": 3600
    }
  }
}
```

**3. Token Audience绑定 (对齐MCP)**

```json
// Token必须绑定到特定audience
{
  "access_token": "...",
  "token_type": "Bearer",
  "expires_in": 3600,
  "scope": "aios.read aios.write",
  "audience": "https://aios.example.com"
}
```

---

### 5.2 扩展机制规范化

#### 差距分析

| 特性 | MCP | A2A | AIOS现状 | 差距 |
|------|-----|-----|---------|------|
| 扩展声明 | 实验性功能 | Extensions URI | x-前缀 | 🟡 中 |
| 扩展协商 | - | A2A-Extensions头 | ❌ | 🟡 中 |
| 扩展版本 | - | URI版本 | ❌ | 🟡 中 |

#### 建议补充

**1. AIOS扩展机制规范**

```json
// 扩展声明 (对齐A2A)
{
  "extensions": [
    "urn:aios:ext:priority:1.0",
    "urn:aios:ext:batch-v2:1.0",
    "urn:example:custom:1.0"
  ]
}

// 扩展协商
{
  "method": "aios/initialize",
  "params": {
    "extensions": {
      "supported": [
        "urn:aios:ext:priority:1.0",
        "urn:aios:ext:streaming-v2:1.0"
      ],
      "required": [
        "urn:aios:ext:priority:1.0"
      ]
    }
  }
}
```

**2. 标准扩展列表**

| 扩展URI | 说明 |
|---------|------|
| `urn:aios:ext:priority:1.0` | 任务优先级扩展 |
| `urn:aios:ext:batch-v2:1.0` | 增强批量操作 |
| `urn:aios:ext:streaming-v2:1.0` | 增强流式传输 |
| `urn:aios:ext:audit:1.0` | 审计日志扩展 |

---

### 5.3 SDK和开发者工具规范

#### 差距分析

| 特性 | MCP | A2A | AIOS现状 | 差距 |
|------|-----|-----|---------|------|
| Python SDK | ✅ | ✅ | 设计中 | 🟡 中 |
| TypeScript SDK | ✅ | ✅ | ❌ | 🔴 高 |
| Go SDK | ✅ | ✅ | ❌ | 🟡 中 |
| Java SDK | ✅ | ✅ | ❌ | 🟡 中 |
| Rust SDK | - | - | 核心 | 🟢 优势 |
| Inspector工具 | ✅ | - | ❌ | 🔴 高 |
| CLI工具 | - | - | 设计中 | 🟡 中 |

#### 建议补充

**1. SDK接口规范**

```python
# Python SDK 示例接口
class AIOSClient:
    # 生命周期
    async def connect(self, endpoint: str) -> None
    async def initialize(self, capabilities: dict) -> Session
    async def shutdown(self) -> None
    
    # 工具操作
    async def list_tools(self, filter: ToolFilter = None) -> List[Tool]
    async def get_tool(self, tool_id: str) -> Tool
    async def invoke(self, tool_id: str, capability: str, arguments: dict) -> Result
    
    # 任务管理
    async def create_task(self, ...) -> Task
    async def get_task(self, task_id: str) -> Task
    async def cancel_task(self, task_id: str) -> None
    async def subscribe_task(self, task_id: str) -> AsyncIterator[TaskEvent]
    
    # 权限管理
    async def request_permission(self, permissions: List[Permission]) -> PermissionGrant
    async def list_permissions(self) -> List[PermissionGrant]
    async def revoke_permission(self, token_id: str) -> None
    
    # 资源操作
    async def list_resources(self, tool_id: str) -> List[Resource]
    async def read_resource(self, uri: str) -> ResourceContent
```

**2. CLI工具规范**

```bash
# aios-cli 命令设计
aios-cli init                    # 初始化配置
aios-cli connect [endpoint]      # 连接到AIOS Daemon

# 工具管理
aios-cli tools list              # 列出工具
aios-cli tools info <tool_id>    # 工具详情
aios-cli tools invoke <tool> <cap> [args]  # 调用能力

# 任务管理
aios-cli task create <tool> <cap> [args]   # 创建任务
aios-cli task status <task_id>   # 任务状态
aios-cli task cancel <task_id>   # 取消任务
aios-cli task logs <task_id>     # 任务日志

# 适配器开发
aios-cli adapter init            # 初始化适配器项目
aios-cli adapter validate        # 验证tool.aios.yaml
aios-cli adapter test            # 测试适配器
aios-cli adapter package         # 打包适配器
aios-cli adapter publish         # 发布适配器

# 调试
aios-cli debug inspect           # 启动Inspector
aios-cli debug messages          # 查看消息流
aios-cli debug permissions       # 查看权限状态
```

**3. Inspector工具规范 (对齐MCP Inspector)**

| 功能 | 说明 |
|------|------|
| 连接管理 | 连接到 AIOS Daemon |
| 工具浏览 | 浏览所有可用工具和能力 |
| 交互式调用 | 手动调用能力并查看结果 |
| 消息监控 | 实时查看 JSON-RPC 消息 |
| 权限管理 | 查看和管理权限 |
| 任务追踪 | 追踪任务执行状态 |
| 性能分析 | 调用耗时、资源使用 |

---

## 六、AIOS独特优势

### 6.1 五级权限模型

**MCP和A2A都缺少标准化的权限模型**，这是AIOS的核心优势：

| 级别 | AIOS | MCP | A2A |
|------|------|-----|-----|
| public (无需确认) | ✅ | ❌ | ❌ |
| low (首次确认) | ✅ | ❌ | ❌ |
| medium (可配置) | ✅ | ❌ | ❌ |
| high (每次确认) | ✅ | ❌ | ❌ |
| critical (二次确认) | ✅ | ❌ | ❌ |

### 6.2 软件自动发现

AIOS独有的软件发现机制：

| 特性 | AIOS | MCP | A2A |
|------|------|-----|-----|
| .desktop文件扫描 | ✅ | ❌ | ❌ |
| inotify实时监控 | ✅ | ❌ | ❌ |
| 自动适配器匹配 | ✅ | ❌ | ❌ |
| 渐进式适配 (L0-L4) | ✅ | ❌ | ❌ |

### 6.3 系统级控制

AIOS专注于系统级控制，这是MCP/A2A不涉及的领域：

| 控制层 | AIOS | MCP | A2A |
|--------|------|-----|-----|
| 系统控制 (D-Bus/gsettings) | ✅ | ❌ | ❌ |
| 通用软件控制 (CDP/UNO) | ✅ | 部分 | ❌ |
| 专业软件控制 (bpy/Python-Fu) | ✅ | ❌ | ❌ |

### 6.4 安全沙箱

多级沙箱隔离是AIOS的安全优势：

| 沙箱级别 | 技术 | MCP | A2A |
|---------|------|-----|-----|
| L0 无隔离 | 直接执行 | - | - |
| L1 进程隔离 | 独立进程 | ❌ | ❌ |
| L2 容器隔离 | Wasmtime | ❌ | ❌ |
| L3 VM隔离 | Firecracker | ❌ | ❌ |

---

## 七、需要新增的文档

基于以上深度分析，建议新增以下协议文档：

| 文档 | 优先级 | 状态 | 说明 |
|------|--------|------|------|
| `AIOS-Protocol-Discovery.md` | 🔴 高 | 待创建 | Adapter Card和发现机制规范 |
| `AIOS-Protocol-Lifecycle.md` | 🔴 高 | ✅ 已创建 | 协议生命周期规范 |
| `AIOS-Protocol-TaskManagement.md` | 🔴 高 | ✅ 已创建 | 任务管理规范 |
| `AIOS-Protocol-Multimodal.md` | 🟡 中 | 待创建 | 多模态和Artifact规范 |
| `AIOS-Protocol-Authentication.md` | 🟡 中 | 待创建 | OAuth 2.0/OIDC认证规范 |
| `AIOS-SDK-Specification.md` | 🟡 中 | 待创建 | SDK接口规范 |
| `AIOS-CLI-Specification.md` | 🟡 中 | 待创建 | CLI工具规范 |
| `AIOS-Protocol-Extensions.md` | 🟡 中 | 待创建 | 扩展机制规范 |
| `AIOS-Protocol-Versioning.md` | 🟢 低 | 待创建 | 版本管理规范 |

---

## 八、实施路线图

### 8.1 短期 (1-2周) - 高优先级

| 任务 | 说明 | 依赖 |
|------|------|------|
| 完善版本协商 | 在initialize中添加版本协商 | - |
| 添加AIOS-Version头 | HTTP传输支持 | - |
| 添加auth_required状态 | 任务状态机完善 | - |
| 创建Adapter Card规范 | 发现机制标准化 | - |
| 添加会话恢复机制 | 断线重连支持 | - |

### 8.2 中期 (1个月) - 中优先级

| 任务 | 说明 | 依赖 |
|------|------|------|
| 实现流式Artifact | 对齐A2A lastChunk | 短期任务 |
| OAuth 2.0集成 | 认证授权框架 | - |
| 扩展机制规范化 | Extensions URI | - |
| Python SDK开发 | 参考MCP SDK | 短期任务 |
| CLI工具开发 | aios-cli | Python SDK |

### 8.3 长期 (2-3个月) - 完善阶段

| 任务 | 说明 | 依赖 |
|------|------|------|
| TypeScript SDK | 前端/Node.js支持 | 中期任务 |
| Go SDK | 高性能场景 | 中期任务 |
| Inspector工具 | 调试和开发工具 | SDK |
| 适配器市场 | 适配器分发平台 | CLI工具 |
| 性能优化 | 基准测试和优化 | 全部 |

---

## 九、差距优先级矩阵

```
                    影响程度
                    高        中        低
              ┌─────────┬─────────┬─────────┐
        高    │ 版本协商 │ OAuth   │ 扩展机制│
              │ 发现机制 │ 流式Art │         │
    紧        │ auth状态 │         │         │
    迫  ├─────┼─────────┼─────────┼─────────┤
    程  中    │ 会话恢复 │ SDK     │ 版本管理│
    度        │ 服务参数 │ CLI     │         │
              │         │ Inspector│        │
        ├─────┼─────────┼─────────┼─────────┤
        低    │         │ 多语言SDK│ 市场   │
              │         │         │         │
              └─────────┴─────────┴─────────┘
```

---

## 十、参考资料

| 资源 | 链接 | 版本 |
|------|------|------|
| MCP 规范 | https://modelcontextprotocol.io/specification | 2025-06-18 |
| MCP TypeScript SDK | https://github.com/modelcontextprotocol/typescript-sdk | latest |
| MCP Python SDK | https://github.com/modelcontextprotocol/python-sdk | latest |
| A2A 规范 | https://google.github.io/A2A/specification | DRAFT v1.0 |
| A2A Python SDK | https://github.com/google/A2A/tree/main/samples/python | latest |
| OAuth 2.1 | RFC 9728 (draft) | - |
| JSON-RPC 2.0 | https://www.jsonrpc.org/specification | 2.0 |

---

**文档版本**: 2.0.0
**最后更新**: 2026-01-09
**维护者**: AIOS Protocol Team
