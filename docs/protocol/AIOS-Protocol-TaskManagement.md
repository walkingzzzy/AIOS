# AIOS Protocol 任务管理规范

> **系统开发口径修订（2026-03-08）**
> AIOS 统一定义为 **AI 原生操作系统 / 系统软件工程**。本文如提及桌面应用、Electron 客户端、应用适配器、App 安装等内容，除非明确标注为“原型期 / 兼容层 / 历史实现”，否则不再代表目标形态。
> 当前最高约束：**系统镜像、系统服务、系统壳层、设备/能力抽象、权限与更新恢复**。


**版本**: 2.0.0
**更新日期**: 2026-01-09
**状态**: 战略规划阶段

---

## 一、概述

本文档定义 AIOS Protocol 的任务管理机制，包括任务生命周期、状态机、异步执行和实时更新。

### 1.1 设计目标

| 目标 | 说明 |
|------|------|
| **完整性** | 支持从简单调用到复杂长任务的全场景 |
| **可观测** | 任务状态可查询、可订阅、可追踪 |
| **可控制** | 支持暂停、恢复、取消任务 |
| **可恢复** | 支持断线重连后恢复任务状态 |

### 1.2 与 MCP/A2A 的对比

| 特性 | MCP | A2A | AIOS |
|------|-----|------|------|
| 状态机 | 简单请求-响应 | 7 状态 | 8 状态（增加 paused, auth_required） |
| 传输 | JSON-RPC | HTTP + SSE | JSON-RPC + SSE |
| 产物 | Resources | Artifact | Artifact（兼容） |
| 权限 | 持续演进 | 基础认证 | 系统控制域5级权限 |
| 状态历史 | 无 | stateTransitionHistory | state_history |
| 推送通知 | 无 | webhooks | webhooks |

---

## 二、任务状态机

### 2.1 状态定义

```
                         ┌─────────────────────────────────────┐
                         │                                     │
                         ▼                                     │
┌─────────┐    ┌─────────────┐    ┌─────────────┐             │
│ pending │───>│   working   │───>│  completed  │             │
└────┬────┘    └──────┬──────┘    └─────────────┘             │
     │                │                                        │
     │                ├───────────────────────────────────────>│
     │                │                                        │
     │                ▼                                        │
     │         ┌─────────────┐                                 │
     │         │   paused    │─────────────────────────────────┤
     │         └──────┬──────┘                                 │
     │                │                                        │
     │                ▼                                        │
     │         ┌─────────────┐                                 │
     │         │input_required│────────────────────────────────┤
     │         └──────┬──────┘                                 │
     │                │                                        │
     │                ▼                                        │
     │         ┌─────────────┐                                 │
     └────────>│   failed    │                                 │
               └─────────────┘                                 │
                                                               │
                                                        ┌──────┴──────┐
                                                        │  canceled   │
                                                        └─────────────┘
```

### 2.2 状态说明

| 状态 | 说明 | 可转换到 | A2A对应 |
|------|------|---------|---------|
| `pending` | 任务已创建，等待执行 | working, failed, canceled | submitted |
| `working` | 任务正在执行 | completed, failed, paused, input_required, auth_required, canceled | working |
| `paused` | 任务已暂停 | working, canceled | - (AIOS独有) |
| `input_required` | 需要用户输入才能继续 | working, canceled | input-required |
| `auth_required` | 需要额外认证才能继续 | working, canceled | auth-required |
| `completed` | 任务成功完成 | - (终态) | completed |
| `failed` | 任务执行失败 | - (终态) | failed |
| `canceled` | 任务被取消 | - (终态) | canceled |

### 2.3 状态转换事件

| 转换 | 触发条件 |
|------|---------|
| pending → working | 调度器开始执行任务 |
| working → completed | 任务执行成功 |
| working → failed | 任务执行出错 |
| working → paused | 用户请求暂停 |
| working → input_required | 任务需要用户输入 |
| working → auth_required | 任务需要额外认证 |
| working → canceled | 用户请求取消 |
| paused → working | 用户请求恢复 |
| paused → canceled | 用户请求取消 |
| input_required → working | 用户提供输入 |
| input_required → canceled | 用户请求取消 |
| auth_required → working | 用户完成认证 |
| auth_required → canceled | 用户请求取消 |

---

## 三、任务操作

### 3.1 创建任务

**方法**: `aios/task.create`

**请求**：
```json
{
  "jsonrpc": "2.0",
  "id": "1",
  "method": "aios/task.create",
  "params": {
    "capability_id": "compat.browser.search_and_compare",
    "arguments": {
      "query": "无线耳机",
      "sites": ["jd.com", "taobao.com"]
    },
    "options": {
      "async": true,
      "priority": "normal",
      "timeout_ms": 120000,
      "retry": {
        "max_attempts": 3,
        "delay_ms": 1000
      }
    },
    "metadata": {
      "user_request": "比较京东和淘宝的耳机价格",
      "tags": ["shopping", "comparison"]
    }
  }
}
```

**参数说明**：

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `capability_id` | string | ✅ | 能力标识 |
| `arguments` | object | ❌ | 能力参数 |
| `options.async` | boolean | ❌ | 是否异步执行（默认 false） |
| `options.priority` | string | ❌ | 优先级：low/normal/high |
| `options.timeout_ms` | integer | ❌ | 超时时间 |
| `options.retry` | object | ❌ | 重试配置 |
| `metadata` | object | ❌ | 任务元数据 |

**响应**：
```json
{
  "jsonrpc": "2.0",
  "id": "1",
  "result": {
    "task_id": "task-001",
    "status": "pending",
    "created_at": "2026-01-05T10:00:00Z",
    "estimated_duration_ms": 30000
  }
}
```

### 3.2 查询任务状态

**方法**: `aios/task.get`

**请求**：
```json
{
  "jsonrpc": "2.0",
  "id": "2",
  "method": "aios/task.get",
  "params": {
    "task_id": "task-001"
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
    "capability_id": "compat.browser.search_and_compare",
    "status": "working",
    "progress": {
      "percent": 45,
      "message": "正在搜索淘宝...",
      "current_step": 2,
      "total_steps": 4
    },
    "created_at": "2026-01-05T10:00:00Z",
    "started_at": "2026-01-05T10:00:01Z",
    "artifacts": []
  }
}
```

### 3.3 列出任务

**方法**: `aios/task.list`

**请求**：
```json
{
  "jsonrpc": "2.0",
  "id": "3",
  "method": "aios/task.list",
  "params": {
    "filter": {
      "status": ["pending", "working"],
      "capability_id": "compat.browser.*"
    },
    "pagination": {
      "limit": 10,
      "offset": 0
    },
    "sort": {
      "field": "created_at",
      "order": "desc"
    }
  }
}
```

**响应**：
```json
{
  "jsonrpc": "2.0",
  "id": "3",
  "result": {
    "tasks": [
      {
        "task_id": "task-001",
        "status": "working",
        "progress": {"percent": 45},
        "created_at": "2026-01-05T10:00:00Z"
      }
    ],
    "total": 1,
    "has_more": false
  }
}
```

### 3.4 取消任务

**方法**: `aios/task.cancel`

**请求**：
```json
{
  "jsonrpc": "2.0",
  "id": "4",
  "method": "aios/task.cancel",
  "params": {
    "task_id": "task-001",
    "reason": "user_request"
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
    "status": "canceled",
    "canceled_at": "2026-01-05T10:01:00Z"
  }
}
```

### 3.5 暂停任务

**方法**: `aios/task.pause`

**请求**：
```json
{
  "jsonrpc": "2.0",
  "id": "5",
  "method": "aios/task.pause",
  "params": {
    "task_id": "task-001"
  }
}
```

### 3.6 恢复任务

**方法**: `aios/task.resume`

**请求**：
```json
{
  "jsonrpc": "2.0",
  "id": "6",
  "method": "aios/task.resume",
  "params": {
    "task_id": "task-001"
  }
}
```

### 3.7 提供输入

当任务处于 `input_required` 状态时，提供所需输入。

**方法**: `aios/task.input`

**请求**：
```json
{
  "jsonrpc": "2.0",
  "id": "7",
  "method": "aios/task.input",
  "params": {
    "task_id": "task-001",
    "input": {
      "selected_product": "product-123",
      "confirm_purchase": true
    }
  }
}
```

---

## 四、任务订阅（实时更新）

### 4.1 订阅任务

**方法**: `aios/task.subscribe`

**请求**：
```json
{
  "jsonrpc": "2.0",
  "id": "8",
  "method": "aios/task.subscribe",
  "params": {
    "task_id": "task-001",
    "events": ["status", "progress", "artifact", "log"]
  }
}
```

**响应**：
```json
{
  "jsonrpc": "2.0",
  "id": "8",
  "result": {
    "subscription_id": "sub-001",
    "task_id": "task-001"
  }
}
```

### 4.2 SSE 事件流

订阅后，服务端通过 SSE 推送事件：

```
event: task.status
id: evt-001
data: {"task_id": "task-001", "status": "working", "timestamp": "2026-01-05T10:00:01Z"}

event: task.progress
id: evt-002
data: {"task_id": "task-001", "progress": {"percent": 25, "message": "正在搜索京东..."}}

event: task.progress
id: evt-003
data: {"task_id": "task-001", "progress": {"percent": 50, "message": "正在搜索淘宝..."}}

event: task.artifact
id: evt-004
data: {"task_id": "task-001", "artifact": {"id": "art-001", "name": "京东搜索结果", "type": "data"}}

event: task.input_required
id: evt-005
data: {"task_id": "task-001", "prompt": "找到多个商品，请选择要比较的商品", "options": [...]}

event: task.status
id: evt-006
data: {"task_id": "task-001", "status": "completed", "timestamp": "2026-01-05T10:01:00Z"}

event: task.result
id: evt-007
data: {"task_id": "task-001", "result": {...}, "artifacts": [...]}
```

### 4.3 事件类型

| 事件 | 说明 |
|------|------|
| `task.status` | 任务状态变更 |
| `task.progress` | 进度更新 |
| `task.artifact` | 产生新的 Artifact |
| `task.input_required` | 需要用户输入 |
| `task.log` | 任务日志 |
| `task.result` | 任务完成结果 |
| `task.error` | 任务错误 |

### 4.4 取消订阅

**方法**: `aios/task.unsubscribe`

**请求**：
```json
{
  "jsonrpc": "2.0",
  "id": "9",
  "method": "aios/task.unsubscribe",
  "params": {
    "subscription_id": "sub-001"
  }
}
```

### 4.5 重新订阅（断线恢复）

**方法**: `aios/task.resubscribe`

**请求**：
```json
{
  "jsonrpc": "2.0",
  "id": "10",
  "method": "aios/task.resubscribe",
  "params": {
    "task_id": "task-001",
    "last_event_id": "evt-003"
  }
}
```

**响应**：
```json
{
  "jsonrpc": "2.0",
  "id": "10",
  "result": {
    "subscription_id": "sub-002",
    "missed_events": [
      {"id": "evt-004", "event": "task.artifact", "data": {...}},
      {"id": "evt-005", "event": "task.input_required", "data": {...}}
    ]
  }
}
```

---

## 五、Artifact（任务产物）

### 5.1 Artifact 结构

```json
{
  "artifact": {
    "id": "art-001",
    "name": "价格对比报告",
    "type": "report",
    "mime_type": "application/json",
    "created_at": "2026-01-05T10:01:00Z",
    "parts": [
      {
        "type": "text",
        "text": "## 价格对比结果\n\n京东价格: ¥299\n淘宝价格: ¥289"
      },
      {
        "type": "data",
        "data": {
          "jd": {"price": 299, "url": "https://jd.com/..."},
          "taobao": {"price": 289, "url": "https://taobao.com/..."}
        }
      },
      {
        "type": "image",
        "image": {
          "uri": "file:///tmp/comparison_chart.png",
          "mime_type": "image/png"
        }
      }
    ],
    "metadata": {
      "source_task": "task-001",
      "version": 1
    }
  }
}
```

### 5.2 Part 类型

| 类型 | 说明 | 字段 |
|------|------|------|
| `text` | 文本内容 | `text` |
| `data` | 结构化数据 | `data` (JSON object) |
| `file` | 文件引用 | `file.uri`, `file.mime_type`, `file.size` |
| `image` | 图片 | `image.uri`, `image.mime_type` |
| `audio` | 音频 | `audio.uri`, `audio.duration_ms` |
| `video` | 视频 | `video.uri`, `video.duration_ms` |

### 5.3 获取 Artifact

**方法**: `aios/artifact.get`

**请求**：
```json
{
  "jsonrpc": "2.0",
  "id": "11",
  "method": "aios/artifact.get",
  "params": {
    "artifact_id": "art-001"
  }
}
```

### 5.4 列出任务的 Artifacts

**方法**: `aios/artifact.list`

**请求**：
```json
{
  "jsonrpc": "2.0",
  "id": "12",
  "method": "aios/artifact.list",
  "params": {
    "task_id": "task-001"
  }
}
```

---

## 六、任务优先级和调度

### 6.1 优先级级别

| 级别 | 说明 | 使用场景 |
|------|------|---------|
| `low` | 低优先级 | 后台任务、批量处理 |
| `normal` | 普通优先级 | 默认 |
| `high` | 高优先级 | 用户交互任务 |
| `urgent` | 紧急 | 系统关键任务 |

### 6.2 调度策略

| 策略 | 说明 |
|------|------|
| 优先级队列 | 高优先级任务优先执行 |
| 公平调度 | 同优先级任务按创建时间排序 |
| 资源限制 | 限制并发任务数 |
| 超时控制 | 超时任务自动失败 |

### 6.3 并发控制

```json
// 在 initialize 响应中返回
{
  "capabilities": {
    "limits": {
      "max_concurrent_tasks": 10,
      "max_tasks_per_tool": 3,
      "max_queue_size": 100
    }
  }
}
```

---

## 七、错误处理

### 7.1 任务相关错误码

| 错误码 | 消息 | 说明 |
|--------|------|------|
| `-32106` | Task not found | 任务不存在 |
| `-32107` | Task already completed | 任务已完成，无法操作 |
| `-32107` | Task already canceled | 任务已取消 |
| `-32005` | Task timeout | 任务超时 |
| `-32006` | Task queue full | 任务队列已满 |
| `-32108` | Invalid task state | 无效的状态转换 |
| `-32002` | Input required | 需要用户输入 |
| `-32108` | Invalid input | 用户输入无效 |

### 7.2 任务失败信息

```json
{
  "task_id": "task-001",
  "status": "failed",
  "error": {
    "code": -32005,
    "message": "Timeout",
    "data": {
      "capability_id": "compat.browser.search_and_compare",
      "timeout_ms": 30000,
      "elapsed_ms": 30500
    }
  },
  "failed_at": "2026-01-05T10:00:30Z"
}
```

---

## 八、任务历史和审计

### 8.1 查询任务历史

**方法**: `aios/task.history`

**请求**：
```json
{
  "jsonrpc": "2.0",
  "id": "13",
  "method": "aios/task.history",
  "params": {
    "filter": {
      "start_time": "2026-01-05T00:00:00Z",
      "end_time": "2026-01-05T23:59:59Z",
      "status": ["completed", "failed"]
    },
    "pagination": {
      "limit": 50,
      "offset": 0
    }
  }
}
```

### 8.2 任务审计日志

每个任务的关键事件都会记录到审计日志：

| 事件 | 记录内容 |
|------|---------|
| 创建 | 任务参数、创建者、时间 |
| 状态变更 | 旧状态、新状态、原因 |
| 权限请求 | 请求的权限、用户响应 |
| 完成/失败 | 结果摘要、耗时 |

---

## 九、auth_required 状态处理

### 9.1 认证请求事件

当任务需要额外认证时，发送 `task.auth_required` 事件：

```json
{
  "event": "task.auth_required",
  "data": {
    "task_id": "task-001",
    "status": "auth_required",
    "auth_request": {
      "type": "oauth2",
      "provider": "google",
      "authorization_url": "https://accounts.google.com/o/oauth2/v2/auth",
      "scopes": ["https://www.googleapis.com/auth/drive.readonly"],
      "reason": "访问Google Drive需要用户授权",
      "timeout_ms": 300000
    }
  }
}
```

### 9.2 提供认证

**方法**: `aios/task.authenticate`

**请求**：
```json
{
  "jsonrpc": "2.0",
  "id": "auth-001",
  "method": "aios/task.authenticate",
  "params": {
    "task_id": "task-001",
    "auth_response": {
      "type": "oauth2",
      "authorization_code": "...",
      "state": "..."
    }
  }
}
```

### 9.3 认证类型

| 类型 | 说明 |
|------|------|
| `oauth2` | OAuth 2.0 授权码流程 |
| `api_key` | API密钥 |
| `password` | 用户名密码 |
| `certificate` | 客户端证书 |

---

## 十、状态转换历史

### 10.1 获取状态历史

**方法**: `aios/task.get` (包含 `include_history` 参数)

**请求**：
```json
{
  "jsonrpc": "2.0",
  "id": "14",
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
  "id": "14",
  "result": {
    "task_id": "task-001",
    "status": "completed",
    "state_history": [
      {
        "state": "pending",
        "timestamp": "2026-01-05T10:00:00Z"
      },
      {
        "state": "working",
        "timestamp": "2026-01-05T10:00:01Z"
      },
      {
        "state": "input_required",
        "timestamp": "2026-01-05T10:00:30Z",
        "reason": "需要选择商品",
        "metadata": {
          "prompt": "找到多个商品，请选择要比较的商品",
          "options_count": 5
        }
      },
      {
        "state": "working",
        "timestamp": "2026-01-05T10:01:00Z",
        "reason": "用户提供了输入"
      },
      {
        "state": "completed",
        "timestamp": "2026-01-05T10:02:00Z"
      }
    ],
    "result": {...}
  }
}
```

---

## 十一、推送通知 (Webhooks)

### 11.1 注册Webhook

**方法**: `aios/task.subscribe_webhook`

**请求**：
```json
{
  "jsonrpc": "2.0",
  "id": "15",
  "method": "aios/task.subscribe_webhook",
  "params": {
    "task_id": "task-001",
    "webhook_url": "https://client.example.com/aios/webhook",
    "events": ["status", "artifact", "completed", "failed"],
    "authentication": {
      "type": "bearer",
      "token": "webhook-secret-token"
    },
    "retry_policy": {
      "max_retries": 3,
      "retry_delay_ms": 1000
    }
  }
}
```

### 11.2 Webhook请求格式

```http
POST /aios/webhook HTTP/1.1
Host: client.example.com
Content-Type: application/json
Authorization: Bearer webhook-secret-token
X-AIOS-Event: task.status
X-AIOS-Delivery-Id: delivery-001
X-AIOS-Signature: sha256=...

{
  "event": "task.status",
  "task_id": "task-001",
  "timestamp": "2026-01-05T10:01:00Z",
  "data": {
    "status": "completed",
    "result": {...}
  }
}
```

### 11.3 取消Webhook

**方法**: `aios/task.unsubscribe_webhook`

**请求**：
```json
{
  "jsonrpc": "2.0",
  "id": "16",
  "method": "aios/task.unsubscribe_webhook",
  "params": {
    "task_id": "task-001",
    "webhook_url": "https://client.example.com/aios/webhook"
  }
}
```

---

## 十二、方法速查表

| 方法 | 说明 |
|------|------|
| `aios/task.create` | 创建任务 |
| `aios/task.get` | 获取任务详情 |
| `aios/task.list` | 列出任务 |
| `aios/task.cancel` | 取消任务 |
| `aios/task.pause` | 暂停任务 |
| `aios/task.resume` | 恢复任务 |
| `aios/task.input` | 提供用户输入 |
| `aios/task.authenticate` | 提供认证信息 |
| `aios/task.subscribe` | 订阅任务更新 (SSE) |
| `aios/task.unsubscribe` | 取消订阅 |
| `aios/task.resubscribe` | 重新订阅 |
| `aios/task.subscribe_webhook` | 注册Webhook |
| `aios/task.unsubscribe_webhook` | 取消Webhook |
| `aios/task.history` | 查询历史 |
| `aios/artifact.get` | 获取 Artifact |
| `aios/artifact.list` | 列出 Artifacts |

---

**文档版本**: 2.0.0
**最后更新**: 2026-01-09
**维护者**: AIOS Protocol Team
