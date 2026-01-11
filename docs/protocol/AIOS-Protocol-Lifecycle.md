# AIOS Protocol 协议生命周期规范

**版本**: 2.0.0  
**更新日期**: 2026-01-09  
**状态**: 战略规划阶段

---

## 一、概述

本文档定义 AIOS Protocol 的连接生命周期，包括初始化、版本协商、能力协商、心跳保活和优雅关闭。

### 1.1 设计原则

| 原则 | 说明 |
|------|------|
| **兼容性** | 与 MCP 协议的生命周期模型保持兼容 |
| **可靠性** | 支持断线检测和自动重连 |
| **可扩展** | 支持能力协商和版本演进 |
| **安全性** | 初始化阶段完成认证和授权 |

### 1.2 与MCP/A2A对比

| 特性 | MCP | A2A | AIOS |
|------|-----|-----|------|
| 初始化握手 | initialize/initialized | 无状态 | initialize/initialized |
| 版本协商 | protocolVersion | A2A-Version头 | protocol_version + 头 |
| 能力协商 | capabilities | Agent Card | capabilities |
| 会话管理 | Mcp-Session-Id | contextId | session_id + 头 |
| 心跳机制 | ping/pong | - | ping/pong |

---

## 二、连接生命周期

### 2.1 状态机

```
┌─────────────┐
│ Disconnected│
└──────┬──────┘
       │ connect()
       ▼
┌─────────────┐
│ Connecting  │
└──────┬──────┘
       │ connected
       ▼
┌─────────────┐     initialize
│  Connected  │ ─────────────────┐
└──────┬──────┘                  │
       │                         ▼
       │                  ┌─────────────┐
       │                  │ Initializing│
       │                  └──────┬──────┘
       │                         │ initialized
       │                         ▼
       │                  ┌─────────────┐
       │                  │    Ready    │◄──────┐
       │                  └──────┬──────┘       │
       │                         │              │
       │              ┌──────────┼──────────┐   │
       │              │          │          │   │
       │              ▼          ▼          ▼   │
       │         [正常通信]  [心跳检测]  [重连] ─┘
       │              │
       │              │ shutdown
       │              ▼
       │         ┌─────────────┐
       │         │  Closing    │
       │         └──────┬──────┘
       │                │ closed
       └────────────────┼────────────────────────┐
                        ▼                        │
                 ┌─────────────┐                 │
                 │   Closed    │ ◄───────────────┘
                 └─────────────┘
```

### 2.2 状态说明

| 状态 | 说明 |
|------|------|
| `Disconnected` | 未连接状态 |
| `Connecting` | 正在建立传输层连接 |
| `Connected` | 传输层已连接，等待初始化 |
| `Initializing` | 正在进行协议初始化 |
| `Ready` | 初始化完成，可以正常通信 |
| `Closing` | 正在关闭连接 |
| `Closed` | 连接已关闭 |

---

## 三、初始化流程

### 3.1 初始化序列

```
Client                              Server
  │                                    │
  │──────── [传输层连接] ──────────────>│
  │                                    │
  │──────── aios/initialize ──────────>│
  │                                    │
  │<─────── initialize result ─────────│
  │                                    │
  │──────── aios/initialized ─────────>│
  │                                    │
  │           [Ready 状态]             │
  │                                    │
```

### 3.2 aios/initialize 请求

客户端发送初始化请求，声明自身能力和版本信息。

**请求**：
```json
{
  "jsonrpc": "2.0",
  "id": "init-001",
  "method": "aios/initialize",
  "params": {
    "protocol_version": "0.3.0",
    "supported_versions": ["0.3.0", "0.2.0"],
    "client_info": {
      "name": "aios-client",
      "version": "1.0.0",
      "platform": "linux",
      "arch": "x86_64"
    },
    "capabilities": {
      "streaming": true,
      "batch": true,
      "notifications": true,
      "multimodal": {
        "supported_types": ["text", "image", "file", "data"]
      }
    },
    "content_negotiation": {
      "supported_types": ["text/plain", "text/markdown", "application/json", "image/png"],
      "max_inline_size": 1048576,
      "prefer_uri": true
    },
    "extensions": {
      "supported": ["urn:aios:ext:priority:1.0"],
      "required": []
    },
    "authentication": {
      "type": "session",
      "credentials": {
        "user_id": "user-001"
      }
    }
  }
}
```

**参数说明**：

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `protocol_version` | string | ✅ | 客户端首选的协议版本 |
| `supported_versions` | array | ❌ | 客户端支持的所有版本 (降序) |
| `client_info` | object | ✅ | 客户端信息 |
| `client_info.name` | string | ✅ | 客户端名称 |
| `client_info.version` | string | ✅ | 客户端版本 |
| `client_info.platform` | string | ❌ | 运行平台 |
| `client_info.arch` | string | ❌ | CPU 架构 |
| `capabilities` | object | ❌ | 客户端能力声明 |
| `content_negotiation` | object | ❌ | 内容协商配置 |
| `extensions` | object | ❌ | 扩展支持声明 |
| `authentication` | object | ❌ | 认证信息 |

### 3.3 initialize 响应

服务端返回协商结果和会话信息。

**成功响应**：
```json
{
  "jsonrpc": "2.0",
  "id": "init-001",
  "result": {
    "protocol_version": "0.3.0",
    "server_info": {
      "name": "aios-daemon",
      "version": "1.0.0",
      "platform": "linux",
      "instructions": "AIOS守护进程，支持系统控制和软件适配。使用aios/capability.list查看可用能力。"
    },
    "capabilities": {
      "streaming": true,
      "batch": true,
      "notifications": true,
      "multimodal": {
        "supported_types": ["text", "image", "file", "data"]
      },
      "limits": {
        "max_concurrent_tasks": 10,
        "max_batch_size": 100,
        "max_message_size": 10485760
      }
    },
    "extensions": {
      "enabled": ["urn:aios:ext:priority:1.0"]
    },
    "session": {
      "session_id": "sess-001",
      "created_at": "2026-01-05T10:00:00Z",
      "expires_at": "2026-01-05T12:00:00Z"
    }
  }
}
```

**版本不兼容响应**：
```json
{
  "jsonrpc": "2.0",
  "id": "init-001",
  "error": {
    "code": -32009,
    "message": "Version mismatch",
    "data": {
      "requested_version": "0.4.0",
      "supported_versions": ["0.3.0", "0.2.0", "0.2.1"],
      "latest_version": "0.3.0"
    }
  }
}
```

**扩展不支持响应**：
```json
{
  "jsonrpc": "2.0",
  "id": "init-001",
  "error": {
    "code": -32009,
    "message": "Required extension not supported",
    "data": {
      "required_extension": "urn:example:custom:1.0",
      "supported_extensions": ["urn:aios:ext:priority:1.0"]
    }
  }
}
```

### 3.4 aios/initialized 通知

客户端确认初始化完成，进入 Ready 状态。

```json
{
  "jsonrpc": "2.0",
  "method": "aios/initialized",
  "params": {}
}
```

---

## 四、能力协商

### 4.1 标准能力

| 能力 | 说明 | 默认值 |
|------|------|--------|
| `streaming` | 支持流式传输 | false |
| `batch` | 支持批量操作 | false |
| `notifications` | 支持通知消息 | true |
| `multimodal` | 支持多模态内容 | false |
| `task_management` | 支持异步任务管理 | false |
| `resource_subscription` | 支持资源订阅 | false |

### 4.2 协商规则

1. **最小公共集**：协商结果为双方都支持的能力
2. **版本兼容**：服务端选择双方都支持的最高版本
3. **限制取小**：数值限制取双方的较小值

### 4.3 动态能力更新

运行时可以通过 `aios/capabilities.update` 更新能力：

```json
{
  "jsonrpc": "2.0",
  "id": "cap-001",
  "method": "aios/capabilities.update",
  "params": {
    "capabilities": {
      "streaming": false
    }
  }
}
```

---

## 五、心跳机制

### 5.1 心跳配置

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `heartbeat_interval_ms` | 30000 | 心跳间隔（毫秒） |
| `heartbeat_timeout_ms` | 10000 | 心跳超时（毫秒） |
| `max_missed_heartbeats` | 3 | 最大丢失心跳数 |

### 5.2 心跳消息

**Ping（客户端 → 服务端）**：
```json
{
  "jsonrpc": "2.0",
  "method": "aios/ping",
  "params": {
    "timestamp": "2026-01-05T10:00:00.000Z"
  }
}
```

**Pong（服务端 → 客户端）**：
```json
{
  "jsonrpc": "2.0",
  "method": "aios/pong",
  "params": {
    "timestamp": "2026-01-05T10:00:00.000Z",
    "server_time": "2026-01-05T10:00:00.050Z"
  }
}
```

### 5.3 断线检测

```
连续 3 次心跳无响应
       │
       ▼
触发断线事件
       │
       ├──> 通知应用层
       │
       └──> 尝试重连（如果配置了自动重连）
```

---

## 六、重连机制

### 6.1 重连策略

| 策略 | 说明 |
|------|------|
| `none` | 不自动重连 |
| `immediate` | 立即重连 |
| `exponential_backoff` | 指数退避重连 |

### 6.2 指数退避参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `initial_delay_ms` | 1000 | 初始延迟 |
| `max_delay_ms` | 30000 | 最大延迟 |
| `multiplier` | 2 | 延迟倍数 |
| `max_attempts` | 10 | 最大尝试次数 |

### 6.3 重连流程

```
断线检测
   │
   ▼
等待 initial_delay_ms
   │
   ▼
尝试重连 ──────────────────┐
   │                       │
   ├── 成功 ──> 重新初始化  │
   │                       │
   └── 失败 ──> 延迟 *= multiplier
                   │
                   ▼
              延迟 > max_delay_ms ?
                   │
           ┌──────┴──────┐
           │ 是          │ 否
           ▼             ▼
    延迟 = max_delay_ms  继续
                   │
                   ▼
              尝试次数 < max_attempts ?
                   │
           ┌──────┴──────┐
           │ 是          │ 否
           ▼             ▼
        重试连接      放弃重连
```

### 6.4 会话恢复

重连成功后，可以尝试恢复之前的会话：

```json
{
  "jsonrpc": "2.0",
  "id": "init-002",
  "method": "aios/initialize",
  "params": {
    "protocol_version": "0.3.0",
    "client_info": {...},
    "session_recovery": {
      "previous_session_id": "sess-001",
      "last_message_id": "msg-100"
    }
  }
}
```

**恢复成功响应**：
```json
{
  "result": {
    "session": {
      "session_id": "sess-001",
      "recovered": true,
      "missed_messages": [...]
    }
  }
}
```

**恢复失败响应**：
```json
{
  "result": {
    "session": {
      "session_id": "sess-002",
      "recovered": false,
      "reason": "session_expired"
    }
  }
}
```

---

## 七、优雅关闭

### 7.1 关闭流程

```
Client                              Server
  │                                    │
  │──────── aios/shutdown ────────────>│
  │                                    │
  │         [等待任务完成]              │
  │                                    │
  │<─────── shutdown result ───────────│
  │                                    │
  │         [关闭传输层连接]            │
  │                                    │
```

### 7.2 aios/shutdown 请求

```json
{
  "jsonrpc": "2.0",
  "id": "shutdown-001",
  "method": "aios/shutdown",
  "params": {
    "reason": "client_exit",
    "timeout_ms": 5000,
    "force": false
  }
}
```

**参数说明**：

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `reason` | string | ❌ | 关闭原因 |
| `timeout_ms` | integer | ❌ | 等待任务完成的超时时间 |
| `force` | boolean | ❌ | 是否强制关闭（不等待任务） |

### 7.3 关闭原因

| 原因 | 说明 |
|------|------|
| `client_exit` | 客户端正常退出 |
| `user_request` | 用户请求关闭 |
| `error` | 发生错误 |
| `timeout` | 超时 |
| `server_shutdown` | 服务端关闭 |

### 7.4 shutdown 响应

```json
{
  "jsonrpc": "2.0",
  "id": "shutdown-001",
  "result": {
    "success": true,
    "pending_tasks_cancelled": 2,
    "session_duration_ms": 3600000
  }
}
```

---

## 八、错误处理

### 8.1 生命周期相关错误码

| 错误码 | 消息 | 说明 |
|--------|------|------|
| `-32009` | Version mismatch | 协议版本不支持 |
| `-32009` | Already initialized | 重复初始化 |
| `-32009` | Not initialized | 未初始化就调用方法 |
| `-32104` | Session expired | 会话过期 |
| `-32104` | Session recovery failed | 会话恢复失败 |
| `-32005` | Heartbeat timeout | 心跳超时 |
| `-32005` | Connection lost | 连接丢失 |

### 8.2 错误恢复策略

| 错误 | 恢复策略 |
|------|---------|
| 版本不支持 | 降级到支持的版本或提示升级 |
| 会话过期 | 重新初始化，创建新会话 |
| 心跳超时 | 触发重连机制 |
| 连接丢失 | 触发重连机制 |

---

## 九、实现要求

### 9.1 必须实现

- `aios/initialize` 请求和响应
- `aios/initialized` 通知
- `aios/shutdown` 请求和响应
- 基本的版本协商

### 9.2 应该实现

- 心跳机制（`aios/ping`、`aios/pong`）
- 自动重连
- 会话恢复

### 9.3 可选实现

- 动态能力更新
- 高级重连策略

---

## 十、示例代码

### 10.1 Python 客户端示例

```python
import asyncio
import json

class AIOSClient:
    def __init__(self, transport):
        self.transport = transport
        self.state = "disconnected"
        self.session_id = None
        
    async def connect(self):
        self.state = "connecting"
        await self.transport.connect()
        self.state = "connected"
        
    async def initialize(self, capabilities=None):
        self.state = "initializing"
        
        request = {
            "jsonrpc": "2.0",
            "id": "init-001",
            "method": "aios/initialize",
            "params": {
                "protocol_version": "0.3.0",
                "client_info": {
                    "name": "aios-python-client",
                    "version": "1.0.0"
                },
                "capabilities": capabilities or {}
            }
        }
        
        response = await self.transport.send(request)
        
        if "error" in response:
            raise InitializationError(response["error"])
            
        self.session_id = response["result"]["session"]["session_id"]
        
        # 发送 initialized 通知
        await self.transport.send({
            "jsonrpc": "2.0",
            "method": "aios/initialized",
            "params": {}
        })
        
        self.state = "ready"
        return response["result"]
        
    async def shutdown(self, reason="client_exit"):
        self.state = "closing"
        
        request = {
            "jsonrpc": "2.0",
            "id": "shutdown-001",
            "method": "aios/shutdown",
            "params": {"reason": reason}
        }
        
        response = await self.transport.send(request)
        await self.transport.close()
        
        self.state = "closed"
        return response.get("result")
```

---

**文档版本**: 2.0.0  
**最后更新**: 2026-01-09  
**维护者**: AIOS Protocol Team
