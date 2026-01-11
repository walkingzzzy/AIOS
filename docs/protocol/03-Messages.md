# AIOS Protocol 消息类型

**版本**: 2.0.0  
**更新日期**: 2026-01-09  
**状态**: 战略规划阶段

---

## 概述

本文档定义 AIOS Protocol 的所有消息类型，包括请求方法和响应格式。

---

## 1. 生命周期操作 (aios/*)

### aios/initialize

初始化协议连接，进行版本协商和能力协商。

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
      "platform": "linux"
    },
    "capabilities": {
      "streaming": true,
      "batch": true,
      "notifications": true
    },
    "extensions": {
      "supported": ["urn:aios:ext:priority:1.0"],
      "required": []
    }
  }
}
```

**响应**：
```json
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
      "limits": {
        "max_concurrent_tasks": 10
      }
    },
    "session": {
      "session_id": "sess-001",
      "expires_at": "2026-01-05T12:00:00Z"
    }
  }
}
```

→ 详见 [协议生命周期](AIOS-Protocol-Lifecycle.md)

---

### aios/initialized (通知)

客户端确认初始化完成。

```json
{
  "jsonrpc": "2.0",
  "method": "aios/initialized",
  "params": {}
}
```

---

### aios/shutdown

优雅关闭连接。

**请求**：
```json
{
  "jsonrpc": "2.0",
  "id": "shutdown-001",
  "method": "aios/shutdown",
  "params": {
    "reason": "client_exit",
    "timeout_ms": 5000
  }
}
```

**响应**：
```json
{
  "jsonrpc": "2.0",
  "id": "shutdown-001",
  "result": {
    "success": true,
    "pending_tasks_cancelled": 2
  }
}
```

---

### aios/ping (通知)

心跳检测。

```json
{
  "jsonrpc": "2.0",
  "method": "aios/ping",
  "params": {
    "timestamp": "2026-01-05T10:00:00.000Z"
  }
}
```

### aios/pong (通知)

心跳响应。

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

---

## 2. 能力操作 (aios/capability.*)

### aios/capability.list

列出所有可用能力。

**请求**：
```json
{
  "jsonrpc": "2.0",
  "id": "1",
  "method": "aios/capability.list",
  "params": {
    "namespace": "system",     // 可选: 过滤命名空间
    "category": "desktop"      // 可选: 过滤类别
  }
}
```

**响应**：
```json
{
  "jsonrpc": "2.0",
  "id": "1",
  "result": {
    "capabilities": [
      {
        "id": "system.desktop.set_wallpaper",
        "name": "设置壁纸",
        "namespace": "system",
        "version": "1.0.0",
        "permission_level": "low"
      },
      {
        "id": "system.desktop.get_wallpaper",
        "name": "获取壁纸",
        "namespace": "system",
        "version": "1.0.0",
        "permission_level": "public"
      }
    ]
  }
}
```

---

### aios/capability.info

获取能力详细信息。

**请求**：
```json
{
  "jsonrpc": "2.0",
  "id": "2",
  "method": "aios/capability.info",
  "params": {
    "capability_id": "system.desktop.set_wallpaper"
  }
}
```

**响应**：
```json
{
  "jsonrpc": "2.0",
  "id": "2",
  "result": {
    "id": "system.desktop.set_wallpaper",
    "name": "设置壁纸",
    "description": "设置桌面壁纸",
    "namespace": "system",
    "version": "1.0.0",
    "permission": {
      "level": "low",
      "scope": "system.desktop"
    },
    "input": {
      "type": "object",
      "properties": {
        "path": {"type": "string"},
        "mode": {"type": "string", "enum": ["fill", "fit", "stretch"]}
      },
      "required": ["path"]
    },
    "output": {
      "type": "object",
      "properties": {
        "success": {"type": "boolean"},
        "previous_path": {"type": "string"}
      }
    }
  }
}
```

---

### aios/capability.invoke

调用能力。

**请求**：
```json
{
  "jsonrpc": "2.0",
  "id": "3",
  "method": "aios/capability.invoke",
  "params": {
    "capability_id": "system.desktop.set_wallpaper",
    "arguments": {
      "path": "/home/user/wallpaper.jpg",
      "mode": "fill"
    },
    "context": {
      "session_id": "sess-001"
    },
    "options": {
      "timeout_ms": 30000,
      "stream": false
    }
  }
}
```

**响应 (成功)**：
```json
{
  "jsonrpc": "2.0",
  "id": "3",
  "result": {
    "success": true,
    "message": "壁纸已更换",
    "data": {
      "previous_path": "/usr/share/backgrounds/default.jpg",
      "current_path": "/home/user/wallpaper.jpg"
    },
    "execution_time_ms": 150
  }
}
```

**响应 (需要权限)**：
```json
{
  "jsonrpc": "2.0",
  "id": "3",
  "error": {
    "code": -32001,
    "message": "Permission denied",
    "data": {
      "permission_level": "low",
      "scope": "system.desktop",
      "request_id": "perm-req-001"
    }
  }
}
```

---

### aios/capability.status

查询异步任务状态。

**请求**：
```json
{
  "jsonrpc": "2.0",
  "id": "4",
  "method": "aios/capability.status",
  "params": {
    "task_id": "task-001"
  }
}
```

**响应**：
```json
{
  "jsonrpc": "2.0",
  "id": "4",
  "result": {
    "task_id": "task-001",
    "status": "running",
    "progress": 75,
    "message": "正在处理...",
    "started_at": "2026-01-05T10:00:00Z"
  }
}
```

---

### aios/capability.cancel

取消正在执行的任务。

**请求**：
```json
{
  "jsonrpc": "2.0",
  "id": "5",
  "method": "aios/capability.cancel",
  "params": {
    "task_id": "task-001"
  }
}
```

---

## 3. 权限操作 (aios/permission.*)

### aios/permission.request

请求权限。

**请求**：
```json
{
  "jsonrpc": "2.0",
  "id": "10",
  "method": "aios/permission.request",
  "params": {
    "capability_id": "app.browser.open_url",
    "permissions": [
      {
        "level": "low",
        "scope": "https://jd.com/*",
        "duration": "task",
        "reason": "访问京东网站比较商品价格"
      }
    ]
  }
}
```

**响应 (用户同意)**：
```json
{
  "jsonrpc": "2.0",
  "id": "10",
  "result": {
    "granted": true,
    "tokens": [
      {
        "token_id": "cap-token-001",
        "permission_id": "aios.permission.network.internet.connect",
        "scope": "https://jd.com/*",
        "expires_at": "2026-01-05T11:00:00Z"
      }
    ]
  }
}
```

**响应 (用户拒绝)**：
```json
{
  "jsonrpc": "2.0",
  "id": "10",
  "result": {
    "granted": false,
    "reason": "user_declined"
  }
}
```

---

### aios/permission.list

列出当前已授予的权限。

**请求**：
```json
{
  "jsonrpc": "2.0",
  "id": "11",
  "method": "aios/permission.list",
  "params": {
    "session_id": "sess-001"
  }
}
```

**响应**：
```json
{
  "jsonrpc": "2.0",
  "id": "11",
  "result": {
    "permissions": [
      {
        "token_id": "cap-token-001",
        "permission_id": "aios.permission.network.internet.connect",
        "tool_id": "org.aios.browser.chrome",
        "scope": "https://jd.com/*",
        "granted_at": "2026-01-05T10:00:00Z",
        "expires_at": "2026-01-05T11:00:00Z"
      }
    ]
  }
}
```

---

### aios/permission.revoke

撤销权限。

**请求**：
```json
{
  "jsonrpc": "2.0",
  "id": "12",
  "method": "aios/permission.revoke",
  "params": {
    "token_id": "cap-token-001"
  }
}
```

---

## 3. 会话操作 (aios/session.*)

### aios/session.create

创建新会话。

**请求**：
```json
{
  "jsonrpc": "2.0",
  "id": "20",
  "method": "aios/session.create",
  "params": {
    "user_id": "user-001",
    "metadata": {
      "client": "aios-cli",
      "version": "1.0.0"
    }
  }
}
```

**响应**：
```json
{
  "jsonrpc": "2.0",
  "id": "20",
  "result": {
    "session_id": "sess-001",
    "created_at": "2026-01-05T10:00:00Z",
    "expires_at": "2026-01-05T12:00:00Z"
  }
}
```

---

### aios/session.info

获取会话信息。

**请求**：
```json
{
  "jsonrpc": "2.0",
  "id": "21",
  "method": "aios/session.info",
  "params": {
    "session_id": "sess-001"
  }
}
```

---

### aios/session.close

关闭会话。

**请求**：
```json
{
  "jsonrpc": "2.0",
  "id": "22",
  "method": "aios/session.close",
  "params": {
    "session_id": "sess-001"
  }
}
```

---

## 4. 资源操作 (aios/resource.*)

### aios/resource.list

列出可用资源。

**请求**：
```json
{
  "jsonrpc": "2.0",
  "id": "30",
  "method": "aios/resource.list",
  "params": {
    "tool_id": "org.aios.system.filesystem"
  }
}
```

**响应**：
```json
{
  "jsonrpc": "2.0",
  "id": "30",
  "result": {
    "resources": [
      {
        "uri": "file:///home/user/Documents",
        "name": "Documents",
        "type": "directory",
        "mime_type": "inode/directory"
      }
    ]
  }
}
```

---

### aios/resource.read

读取资源内容。

**请求**：
```json
{
  "jsonrpc": "2.0",
  "id": "31",
  "method": "aios/resource.read",
  "params": {
    "uri": "file:///home/user/Documents/note.txt"
  }
}
```

**响应**：
```json
{
  "jsonrpc": "2.0",
  "id": "31",
  "result": {
    "uri": "file:///home/user/Documents/note.txt",
    "content": "文件内容...",
    "mime_type": "text/plain",
    "size": 1024
  }
}
```

---

## 5. 流式操作 (aios/stream.*)

### aios/stream.start (通知)

流开始。

```json
{
  "jsonrpc": "2.0",
  "method": "aios/stream.start",
  "params": {
    "stream_id": "stream-001",
    "task_id": "task-001",
    "estimated_chunks": 10
  }
}
```

### aios/stream.chunk (通知)

流数据块。

```json
{
  "jsonrpc": "2.0",
  "method": "aios/stream.chunk",
  "params": {
    "stream_id": "stream-001",
    "index": 0,
    "data": "部分结果..."
  }
}
```

### aios/stream.progress (通知)

流进度更新。

```json
{
  "jsonrpc": "2.0",
  "method": "aios/stream.progress",
  "params": {
    "stream_id": "stream-001",
    "progress": 50,
    "message": "正在处理..."
  }
}
```

### aios/stream.end (通知)

流结束。

```json
{
  "jsonrpc": "2.0",
  "method": "aios/stream.end",
  "params": {
    "stream_id": "stream-001",
    "result": {...}
  }
}
```

---

## 6. 批量操作 (aios/batch.*)

### aios/batch.execute

批量执行多个操作。

**请求**：
```json
{
  "jsonrpc": "2.0",
  "id": "40",
  "method": "aios/batch.execute",
  "params": {
    "mode": "sequential",
    "operations": [
      {
        "id": "op-1",
        "method": "aios/capability.invoke",
        "params": {
          "capability_id": "app.browser.launch"
        }
      },
      {
        "id": "op-2",
        "depends_on": ["op-1"],
        "method": "aios/capability.invoke",
        "params": {
          "capability_id": "app.browser.open_url",
          "arguments": {"url": "https://jd.com"}
        }
      }
    ],
    "options": {
      "stop_on_error": true
    }
  }
}
```

**响应**：
```json
{
  "jsonrpc": "2.0",
  "id": "40",
  "result": {
    "overall_status": "success",
    "results": [
      {"id": "op-1", "status": "success", "result": {...}},
      {"id": "op-2", "status": "success", "result": {...}}
    ]
  }
}
```

---

## 7. 任务操作 (aios/task.*)

### aios/task.create

创建异步任务。

**请求**：
```json
{
  "jsonrpc": "2.0",
  "id": "1",
  "method": "aios/task.create",
  "params": {
    "capability_id": "app.browser.search_and_compare",
    "arguments": {
      "query": "无线耳机",
      "sites": ["jd.com", "taobao.com"]
    },
    "options": {
      "async": true,
      "priority": "normal",
      "timeout_ms": 120000
    }
  }
}
```

**响应**：
```json
{
  "jsonrpc": "2.0",
  "id": "1",
  "result": {
    "task_id": "task-001",
    "status": "pending",
    "created_at": "2026-01-05T10:00:00Z"
  }
}
```

---

### aios/task.get

获取任务详情。

**请求**：
```json
{
  "jsonrpc": "2.0",
  "id": "2",
  "method": "aios/task.get",
  "params": {
    "task_id": "task-001",
    "include_history": true
  }
}
```

**响应**：
```json
{
  "jsonrpc": "2.0",
  "id": "2",
  "result": {
    "task_id": "task-001",
    "status": "working",
    "progress": {
      "percent": 45,
      "message": "正在搜索淘宝..."
    },
    "state_history": [
      {"state": "pending", "timestamp": "2026-01-05T10:00:00Z"},
      {"state": "working", "timestamp": "2026-01-05T10:00:01Z"}
    ]
  }
}
```

---

### aios/task.cancel

取消任务。

**请求**：
```json
{
  "jsonrpc": "2.0",
  "id": "3",
  "method": "aios/task.cancel",
  "params": {
    "task_id": "task-001",
    "reason": "user_request"
  }
}
```

---

### aios/task.pause / aios/task.resume

暂停/恢复任务。

```json
{
  "jsonrpc": "2.0",
  "id": "4",
  "method": "aios/task.pause",
  "params": { "task_id": "task-001" }
}
```

---

### aios/task.input

提供用户输入（当任务处于 `input_required` 状态）。

**请求**：
```json
{
  "jsonrpc": "2.0",
  "id": "5",
  "method": "aios/task.input",
  "params": {
    "task_id": "task-001",
    "input": {
      "selected_product": "product-123"
    }
  }
}
```

---

### aios/task.authenticate

提供认证信息（当任务处于 `auth_required` 状态）。

**请求**：
```json
{
  "jsonrpc": "2.0",
  "id": "6",
  "method": "aios/task.authenticate",
  "params": {
    "task_id": "task-001",
    "auth_response": {
      "type": "oauth2",
      "authorization_code": "..."
    }
  }
}
```

---

### aios/task.subscribe

订阅任务更新（SSE）。

**请求**：
```json
{
  "jsonrpc": "2.0",
  "id": "7",
  "method": "aios/task.subscribe",
  "params": {
    "task_id": "task-001",
    "events": ["status", "progress", "artifact"]
  }
}
```

**响应**：
```json
{
  "jsonrpc": "2.0",
  "id": "7",
  "result": {
    "subscription_id": "sub-001"
  }
}
```

---

### aios/task.resubscribe

断线重连后重新订阅。

**请求**：
```json
{
  "jsonrpc": "2.0",
  "id": "8",
  "method": "aios/task.resubscribe",
  "params": {
    "task_id": "task-001",
    "last_event_id": "evt-003"
  }
}
```

---

### aios/task.subscribe_webhook

注册 Webhook 推送通知。

**请求**：
```json
{
  "jsonrpc": "2.0",
  "id": "9",
  "method": "aios/task.subscribe_webhook",
  "params": {
    "task_id": "task-001",
    "webhook_url": "https://client.example.com/webhook",
    "events": ["completed", "failed"],
    "authentication": {
      "type": "bearer",
      "token": "secret"
    }
  }
}
```

→ 详见 [任务管理规范](AIOS-Protocol-TaskManagement.md)

---

## 8. 注册表操作 (aios/registry.*)

### aios/registry.search

搜索适配器。

**请求**：
```json
{
  "jsonrpc": "2.0",
  "id": "1",
  "method": "aios/registry.search",
  "params": {
    "query": "browser",
    "type": "application",
    "limit": 10
  }
}
```

**响应**：
```json
{
  "jsonrpc": "2.0",
  "id": "1",
  "result": {
    "adapters": [
      {
        "id": "org.aios.browser.chrome",
        "name": "Chrome 浏览器适配器",
        "version": "1.0.0",
        "status": "available"
      }
    ],
    "total": 1
  }
}
```

---

### aios/registry.info

获取适配器详情。

**请求**：
```json
{
  "jsonrpc": "2.0",
  "id": "2",
  "method": "aios/registry.info",
  "params": {
    "adapter_id": "org.aios.browser.chrome"
  }
}
```

---

### aios/registry.refresh

刷新适配器发现。

**请求**：
```json
{
  "jsonrpc": "2.0",
  "id": "3",
  "method": "aios/registry.refresh",
  "params": {
    "scope": "local"
  }
}
```

→ 详见 [发现机制规范](AIOS-Protocol-Discovery.md)

---

## 9. Artifact 操作 (aios/artifact.*)

### aios/artifact.get

获取任务产物。

**请求**：
```json
{
  "jsonrpc": "2.0",
  "id": "1",
  "method": "aios/artifact.get",
  "params": {
    "artifact_id": "art-001"
  }
}
```

**响应**：
```json
{
  "jsonrpc": "2.0",
  "id": "1",
  "result": {
    "artifact": {
      "id": "art-001",
      "name": "价格对比报告",
      "type": "report",
      "parts": [
        {"type": "text", "text": "## 价格对比结果..."},
        {"type": "data", "data": {"jd": 299, "taobao": 289}}
      ]
    }
  }
}
```

---

### aios/artifact.list

列出任务的所有产物。

**请求**：
```json
{
  "jsonrpc": "2.0",
  "id": "2",
  "method": "aios/artifact.list",
  "params": {
    "task_id": "task-001"
  }
}
```

→ 详见 [任务管理规范](AIOS-Protocol-TaskManagement.md)

---

## 10. 通知事件 (aios/notification.*)

### aios/notification.tool_available (通知)

新工具可用。

```json
{
  "jsonrpc": "2.0",
  "method": "aios/notification.tool_available",
  "params": {
    "tool_id": "com.example.newtool",
    "name": "新工具",
    "type": "application"
  }
}
```

### aios/notification.permission_expired (通知)

权限过期。

```json
{
  "jsonrpc": "2.0",
  "method": "aios/notification.permission_expired",
  "params": {
    "token_id": "cap-token-001",
    "permission_id": "aios.permission.network.internet.connect"
  }
}
```

### aios/notification.tools_changed (通知)

工具注册表变更。

```json
{
  "jsonrpc": "2.0",
  "method": "aios/notification.tools_changed",
  "params": {
    "added": [{"id": "org.aios.browser.chrome", "name": "Chrome"}],
    "removed": [],
    "updated": []
  }
}
```

---

## 方法速查表

### 生命周期方法

| 方法 | 类型 | 说明 |
|------|------|------|
| `aios/initialize` | 请求 | 初始化连接 |
| `aios/initialized` | 通知 | 确认初始化 |
| `aios/shutdown` | 请求 | 关闭连接 |
| `aios/ping` | 通知 | 心跳检测 |
| `aios/pong` | 通知 | 心跳响应 |

### 能力方法

| 方法 | 类型 | 说明 |
|------|------|------|
| `aios/capability.list` | 请求 | 列出能力 |
| `aios/capability.info` | 请求 | 能力详情 |
| `aios/capability.invoke` | 请求 | 调用能力 |
| `aios/capability.status` | 请求 | 查询状态 |
| `aios/capability.cancel` | 请求 | 取消执行 |

### 权限方法

| 方法 | 类型 | 说明 |
|------|------|------|
| `aios/permission.request` | 请求 | 请求权限 |
| `aios/permission.list` | 请求 | 列出权限 |
| `aios/permission.revoke` | 请求 | 撤销权限 |

### 会话方法

| 方法 | 类型 | 说明 |
|------|------|------|
| `aios/session.create` | 请求 | 创建会话 |
| `aios/session.info` | 请求 | 会话信息 |
| `aios/session.close` | 请求 | 关闭会话 |

### 资源方法

| 方法 | 类型 | 说明 |
|------|------|------|
| `aios/resource.list` | 请求 | 列出资源 |
| `aios/resource.read` | 请求 | 读取资源 |

### 任务方法

| 方法 | 类型 | 说明 |
|------|------|------|
| `aios/task.create` | 请求 | 创建任务 |
| `aios/task.get` | 请求 | 获取任务 |
| `aios/task.list` | 请求 | 列出任务 |
| `aios/task.cancel` | 请求 | 取消任务 |
| `aios/task.pause` | 请求 | 暂停任务 |
| `aios/task.resume` | 请求 | 恢复任务 |
| `aios/task.input` | 请求 | 提供输入 |
| `aios/task.authenticate` | 请求 | 提供认证 |
| `aios/task.subscribe` | 请求 | 订阅更新 |
| `aios/task.unsubscribe` | 请求 | 取消订阅 |
| `aios/task.resubscribe` | 请求 | 重新订阅 |
| `aios/task.subscribe_webhook` | 请求 | 注册Webhook |
| `aios/task.unsubscribe_webhook` | 请求 | 取消Webhook |

### 注册表方法

| 方法 | 类型 | 说明 |
|------|------|------|
| `aios/registry.search` | 请求 | 搜索适配器 |
| `aios/registry.info` | 请求 | 适配器详情 |
| `aios/registry.refresh` | 请求 | 刷新发现 |
| `aios/registry.subscribe` | 请求 | 订阅变更 |

### Artifact 方法

| 方法 | 类型 | 说明 |
|------|------|------|
| `aios/artifact.get` | 请求 | 获取产物 |
| `aios/artifact.list` | 请求 | 列出产物 |

### 其他方法

| 方法 | 类型 | 说明 |
|------|------|------|
| `aios/stream.*` | 通知 | 流式传输 |
| `aios/batch.execute` | 请求 | 批量执行 |
| `aios/notification.*` | 通知 | 事件通知 |

---

**文档版本**: 2.0.0  
**最后更新**: 2026-01-09  
**维护者**: AIOS Protocol Team
