# AIOS Protocol 传输层规范

**版本**: 2.0.0  
**更新日期**: 2026-01-09  
**状态**: 战略规划阶段

---

## 概述

AIOS Protocol 基于 **JSON-RPC 2.0** 协议进行通信，支持多种传输方式，适应本地和远程部署场景。

### 传输方式总览

| 传输方式 | 位置 | 连接数 | 延迟 | 适用场景 |
|---------|------|--------|------|---------|
| **stdio** | 本地 | 1:1 | 极低 | CLI工具、MCP兼容 |
| **Unix Socket** | 本地 | 多:1 | 极低 | 高性能本地通信 |
| **TCP Socket** | 本地/远程 | 多:1 | 低 | 跨进程通信 |
| **HTTP/SSE** | 远程 | 多:1 | 中等 | 云服务、远程API |
| **WebSocket** | 远程 | 多:1 | 低 | 双向实时通信 |

### 部署方式

| 部署方式 | 传输 | 说明 |
|---------|------|------|
| **本地Daemon** | Unix Socket | 默认方式，AIOS Daemon管理 |
| **Docker容器** | HTTP/TCP | 容器化部署 |
| **Cloudflare Workers** | HTTP/SSE | Serverless边缘部署 |
| **AWS Lambda** | HTTP | Serverless云部署 |
| **远程服务** | HTTP/WS | 任何HTTP端点 |

---

## 1. 协议基础

### JSON-RPC 2.0

AIOS 采用 [JSON-RPC 2.0](https://www.jsonrpc.org/specification) 作为消息格式标准，与 MCP 协议兼容。

### 消息编码

| 属性 | 值 |
|------|---|
| 编码 | UTF-8 |
| 格式 | JSON |

### 消息分帧

不同传输方式使用不同的分帧机制：

| 传输方式 | 分帧方式 | 说明 |
|---------|---------|------|
| **stdio** | Content-Length 头 | 对齐 MCP/LSP 规范 |
| **Unix Socket** | 换行符 `\n` | 简单高效 |
| **HTTP** | HTTP body | 标准 HTTP 语义 |
| **WebSocket** | WebSocket frame | 标准 WS 语义 |

**stdio 分帧格式**（对齐 MCP/LSP）：
```
Content-Length: <length>\r\n\r\n<JSON-RPC message>
```

---

## 2. 连接方式

### 2.1 Unix Domain Socket (推荐)

本地进程间通信的首选方式。

| 属性 | 值 |
|------|---|
| 默认路径 | `/run/user/$UID/aios/aios.sock` |
| 权限 | `0600` (仅用户可访问) |

**连接示例 (Python)**:

```python
import socket
import json

sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
sock.connect('/run/user/1000/aios/aios.sock')

request = {
    "jsonrpc": "2.0",
    "id": "1",
    "method": "aios/capability.list",
    "params": {}
}
sock.send(json.dumps(request).encode() + b'\n')
```

### 2.2 TCP Socket

用于远程或跨进程通信。

| 属性 | 值 |
|------|---|
| 默认端口 | `9527` |
| 绑定地址 | `127.0.0.1` (默认仅本地) |

### 2.3 stdio

用于与子进程通信，常用于 MCP 兼容模式。

| 属性 | 值 |
|------|---|
| 输入 | stdin |
| 输出 | stdout |
| 分帧 | Content-Length 头（对齐 MCP/LSP） |

**分帧格式**：
```
Content-Length: <length>\r\n\r\n<JSON-RPC message>
```

### 2.4 HTTP/Streamable HTTP

用于远程访问和 Web 集成，对齐 MCP Streamable HTTP。

| 属性 | 值 |
|------|---|
| 端点 | `POST /aios/rpc` |
| Content-Type | `application/json` |
| 响应类型 | `application/json` 或 `text/event-stream` (SSE) |

**请求示例**：
```http
POST /aios/rpc HTTP/1.1
Host: localhost:9527
Content-Type: application/json
AIOS-Version: 0.3.0
AIOS-Session-Id: sess-001

{"jsonrpc":"2.0","id":"1","method":"aios/capability.list","params":{}}
```

**SSE 响应示例**：
```http
HTTP/1.1 200 OK
Content-Type: text/event-stream
AIOS-Session-Id: sess-001

event: message
data: {"jsonrpc":"2.0","id":"1","result":{...}}
```

### 2.5 WebSocket

用于双向实时通信，适合需要服务端主动推送的场景。

| 属性 | 值 |
|------|---|
| 端点 | `ws://localhost:9527/aios/ws` |
| 协议 | WebSocket + JSON-RPC 2.0 |

### 2.6 服务参数头

| HTTP 头 | 说明 | 示例 |
|---------|------|------|
| `AIOS-Version` | 协议版本 | `0.3.0` |
| `AIOS-Session-Id` | 会话标识 | `sess-001` |
| `AIOS-Request-Id` | 请求追踪 ID | `req-001` |
| `AIOS-Extensions` | 启用的扩展 | `urn:aios:ext:priority:1.0` |

---

## 2.7 远程部署支持

### Cloudflare Workers 部署

```typescript
// worker.ts - AIOS适配器部署到Cloudflare Workers
import { AIOSAdapter } from '@aios/sdk-cloudflare';

const adapter = new AIOSAdapter({
  id: 'org.mycompany.cloud-tool',
  name: '云端工具',
  version: '1.0.0'
});

adapter.addCapability({
  id: 'hello',
  name: '问候',
  riskLevel: 'public',
  handler: async ({ name }) => ({ message: `Hello, ${name}!` })
});

export default {
  async fetch(request: Request) {
    return adapter.handleRequest(request);
  }
};
```

### Docker 部署

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY . .
RUN pip install aios-sdk
EXPOSE 8080
CMD ["python", "-m", "aios", "run", "--transport", "http", "--port", "8080"]
```

### 远程适配器配置

```yaml
# aios-config.yaml
remote_adapters:
  - id: org.example.remote-tool
    url: "https://my-adapter.example.com/aios"
    transport: http
    auth:
      type: bearer
      token: "${REMOTE_TOKEN}"
```

---

## 2.8 桥接机制

### 本地↔远程桥接

AIOS支持通过代理桥接本地和远程适配器：

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   AIOS Client   │◄───►│   aios-proxy    │◄───►│  Remote AIOS    │
│   (本地)        │     │   (桥接器)       │     │  Adapter        │
└─────────────────┘     └─────────────────┘     └─────────────────┘
        │                       │                       │
        │ Unix Socket           │ HTTP/SSE              │
```

**使用方式**：
```bash
# 将远程适配器桥接到本地
aios-cli proxy --remote "https://my-adapter.example.com" --local "/tmp/aios-proxy.sock"
```

### MCP服务器桥接

AIOS可以桥接任何MCP服务器：

```yaml
# aios-config.yaml
mcp_bridges:
  - id: mcp.filesystem
    command: uvx
    args: ["mcp-server-filesystem", "--root", "/home/user"]
    transport: stdio
    permission_mapping:
      read_file: low
      write_file: high
      delete_file: critical
      
  - id: mcp.github
    url: "https://mcp.github.example.com"
    transport: http
    auth:
      type: bearer
      token: "${GITHUB_TOKEN}"
```

---

## 3. 消息格式

### 3.1 请求 (Request)

```json
{
  "jsonrpc": "2.0",
  "id": "req-001",
  "method": "aios/capability.invoke",
  "params": {
    "capability_id": "system.desktop.set_wallpaper",
    "arguments": {
      "path": "/home/user/wallpaper.jpg"
    },
    "context": {
      "session_id": "sess-001"
    }
  }
}
```

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `jsonrpc` | string | ✅ | 必须为 `"2.0"` |
| `id` | string\|number | ✅ | 请求标识符 |
| `method` | string | ✅ | 方法名 |
| `params` | object | ❌ | 方法参数 |

### 3.2 成功响应 (Success Response)

```json
{
  "jsonrpc": "2.0",
  "id": "req-001",
  "result": {
    "success": true,
    "message": "壁纸已更换",
    "data": {
      "previous_path": "/usr/share/backgrounds/default.jpg",
      "current_path": "/home/user/wallpaper.jpg"
    }
  }
}
```

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `jsonrpc` | string | ✅ | 必须为 `"2.0"` |
| `id` | string\|number | ✅ | 对应请求的 ID |
| `result` | any | ✅ | 执行结果 |

### 3.3 错误响应 (Error Response)

```json
{
  "jsonrpc": "2.0",
  "id": "req-001",
  "error": {
    "code": -32001,
    "message": "Permission denied",
    "data": {
      "permission": "aios.permission.filesystem.write",
      "reason": "User declined permission request"
    }
  }
}
```

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `error.code` | integer | ✅ | 错误码 |
| `error.message` | string | ✅ | 错误消息 |
| `error.data` | any | ❌ | 详细错误信息 |

### 3.4 通知 (Notification)

通知是没有 `id` 的请求，不期望响应。

```json
{
  "jsonrpc": "2.0",
  "method": "aios/notification.progress",
  "params": {
    "task_id": "task-001",
    "progress": 50,
    "message": "正在处理..."
  }
}
```

### 3.5 批量请求 (Batch Request)

发送多个请求作为数组：

```json
[
  {"jsonrpc": "2.0", "id": "1", "method": "aios/capability.list", "params": {}},
  {"jsonrpc": "2.0", "id": "2", "method": "aios/session.info", "params": {}}
]
```

响应也是数组（顺序可能不同）：

```json
[
  {"jsonrpc": "2.0", "id": "2", "result": {"session_id": "sess-001"}},
  {"jsonrpc": "2.0", "id": "1", "result": {"capabilities": [...]}}
]
```

---

## 4. 方法命名空间

### 命名规范

```
aios/<namespace>.<action>
```

### 标准命名空间

| 命名空间 | 说明 | 示例方法 |
|---------|------|---------|
| `aios/initialize` | 初始化 | `initialize`, `initialized`, `shutdown` |
| `aios/capability` | 能力操作 | `list`, `invoke`, `status` |
| `aios/task` | 任务管理 | `create`, `get`, `cancel`, `subscribe` |
| `aios/permission` | 权限管理 | `request`, `grant`, `revoke` |
| `aios/session` | 会话管理 | `create`, `close`, `info` |
| `aios/resource` | 资源操作 | `list`, `read`, `subscribe` |
| `aios/artifact` | 产物操作 | `get`, `list` |
| `aios/registry` | 发现注册 | `search`, `info`, `refresh` |
| `aios/notification` | 通知事件 | `progress`, `tools_changed` |
| `aios/stream` | 流式操作 | `start`, `chunk`, `end` |
| `aios/batch` | 批量操作 | `execute` |

→ 详见 [消息类型](03-Messages.md)、[任务管理](AIOS-Protocol-TaskManagement.md) 和 [API 参考](../api/Reference.md)

---

## 5. 错误码

### 标准 JSON-RPC 错误码

| 错误码 | 消息 | 说明 |
|--------|------|------|
| `-32700` | Parse error | JSON 解析错误 |
| `-32600` | Invalid Request | 无效请求 |
| `-32601` | Method not found | 方法不存在 |
| `-32602` | Invalid params | 无效参数 |
| `-32603` | Internal error | 内部错误 |

### AIOS 协议错误码

| 错误码 | 消息 | 说明 |
|--------|------|------|
| `-32001` | Permission denied | 权限被拒绝 |
| `-32002` | User cancelled | 用户取消确认 |
| `-32003` | Capability not found | 能力不存在 |
| `-32004` | Adapter not available | 适配器不可用 |
| `-32005` | Timeout | 执行超时 |
| `-32006` | Rate limited | 频率限制 |
| `-32007` | Resource busy | 资源忙 |
| `-32008` | Platform not supported | 平台不支持 |
| `-32009` | Version mismatch | 版本不兼容 |
| `-32010` | Sandbox violation | 沙箱违规 |
| `-32100` | App not running | 应用未运行 |
| `-32102` | File not found | 文件不存在 |
| `-32104` | Session expired | 会话过期 |
| `-32106` | Task not found | 任务不存在 |
| `-32108` | Validation failed | 验证失败 |

→ 详见 [错误码规范](AIOS-Protocol-ErrorCodes.md) 和 [任务管理](AIOS-Protocol-TaskManagement.md)

---

## 6. 流式传输

### 6.1 Server-Sent Events (SSE)

用于服务端向客户端推送数据，适用于 HTTP 传输。

**事件格式**：

```
event: stream.chunk
data: {"task_id": "task-001", "chunk": "部分结果..."}

event: stream.progress
data: {"task_id": "task-001", "progress": 75}

event: stream.end
data: {"task_id": "task-001", "result": {...}}
```

### 6.2 JSON-RPC 通知流

通过持续发送通知消息实现流式传输。

```json
{"jsonrpc": "2.0", "method": "aios/stream.start", "params": {"stream_id": "s1"}}
{"jsonrpc": "2.0", "method": "aios/stream.chunk", "params": {"stream_id": "s1", "data": "..."}}
{"jsonrpc": "2.0", "method": "aios/stream.chunk", "params": {"stream_id": "s1", "data": "..."}}
{"jsonrpc": "2.0", "method": "aios/stream.end", "params": {"stream_id": "s1"}}
```

### 6.3 流控制

| 方法 | 说明 |
|------|------|
| `aios/stream.pause` | 暂停流 |
| `aios/stream.resume` | 恢复流 |
| `aios/stream.cancel` | 取消流 |

---

## 7. 安全传输

### TLS 要求

| 场景 | TLS 要求 |
|------|---------|
| Unix Socket | 不需要 (本地) |
| TCP 本地 | 可选 |
| TCP 远程 | **必需** |
| HTTP | **HTTPS 必需** |

### 认证

| 方式 | 说明 | 适用场景 |
|------|------|---------|
| 会话令牌 | 请求中包含 `session_id` | 本地应用 |
| API 密钥 | Header: `X-AIOS-API-Key` | 外部应用 |
| OAuth 2.0 | Bearer Token | 远程访问 |

---

## 8. 超时与重试

### 默认超时

| 操作类型 | 默认超时 |
|---------|---------|
| 能力调用 | 30 秒 |
| 权限请求 | 60 秒 (等待用户确认) |
| 流式操作 | 5 分钟 |

### 重试策略

| 错误类型 | 可重试 | 建议策略 |
|---------|--------|---------|
| 网络错误 | ✅ | 指数退避 |
| 超时 | ✅ | 指数退避 |
| 资源忙 | ✅ | 固定延迟 |
| 权限拒绝 | ❌ | 不重试 |
| 参数错误 | ❌ | 不重试 |

→ 详见 [高级特性 - 重试策略](AIOS-Protocol-AdvancedFeatures.md)

---

## 9. 实现要求

### 必须实现

- JSON-RPC 2.0 请求/响应
- 至少一种传输方式 (推荐 Unix Socket)
- 错误响应格式
- 超时处理

### 应该实现

- 批量请求支持
- 通知消息
- 流式传输
- TLS 加密 (远程)

### 可选实现

- HTTP/SSE 传输
- WebSocket 传输
- 压缩

---

**文档版本**: 2.0.0  
**最后更新**: 2026-01-09  
**维护者**: AIOS Protocol Team
