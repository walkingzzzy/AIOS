# AIOS Protocol API 参考

> **系统开发口径修订（2026-03-08）**
> AIOS 统一定义为 **AI 原生操作系统 / 系统软件工程**。本文如提及桌面应用、Electron 客户端、应用适配器、App 安装等内容，除非明确标注为“原型期 / 兼容层 / 历史实现”，否则不再代表目标形态。
> 当前最高约束：**系统镜像、系统服务、系统壳层、设备/能力抽象、权限与更新恢复**。


**版本**: 2.0.0
**更新日期**: 2026-01-09
**状态**: 战略规划阶段

---

## 概述

本文档提供 AIOS Protocol 所有 API 方法的完整参考。

---

## 1. 能力方法 (aios/capability.*)

### aios/capability.list

列出所有可用能力。

| 属性 | 值 |
|------|---|
| 方法 | `aios/capability.list` |
| 权限 | 无需 |

**参数**：

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `namespace` | string | ❌ | 过滤命名空间前缀（如 system/service/shell/device/compat/professional/mcp 等） |
| `category` | string | ❌ | 过滤类别 |

**返回**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `capabilities` | array | 能力列表 |
| `capabilities[].id` | string | 能力 ID（如 `system.audio.set_volume`） |
| `capabilities[].name` | string | 能力名称 |
| `capabilities[].namespace` | string | 命名空间 |
| `capabilities[].version` | string | 版本号 |
| `capabilities[].permission_level` | string | 权限级别 |

---

### aios/capability.info

获取能力详细信息。

| 属性 | 值 |
|------|---|
| 方法 | `aios/capability.info` |
| 权限 | 无需 |

**参数**：

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `capability_id` | string | ✅ | 能力 ID |

**返回**：完整的能力描述对象

---

### aios/capability.invoke

调用能力。

| 属性 | 值 |
|------|---|
| 方法 | `aios/capability.invoke` |
| 权限 | 取决于能力 |

**参数**：

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `capability_id` | string | ✅ | 能力 ID |
| `arguments` | object | ❌ | 能力参数 |
| `context` | object | ❌ | 执行上下文 |
| `options.timeout_ms` | integer | ❌ | 超时时间 (默认 30000) |
| `options.stream` | boolean | ❌ | 是否流式返回 (默认 false) |
| `options.idempotency_key` | string | ❌ | 幂等键 |

**返回**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `success` | boolean | 是否成功 |
| `message` | string | 结果消息 |
| `data` | object | 返回数据 |
| `task_id` | string | 异步任务 ID (如果异步) |
| `execution_time_ms` | integer | 执行时间 |

**错误码**：

| 错误码 | 说明 |
|--------|------|
| -32001 | 权限被拒绝 |
| -32003 | 能力不存在 |
| -32004 | 适配器不可用 |
| -32005 | 执行超时 |
| -32108 | 验证失败 |

---

### aios/capability.status

查询异步任务状态。

**参数**：

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `task_id` | string | ✅ | 任务 ID |

**返回**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `task_id` | string | 任务 ID |
| `status` | string | pending/running/completed/failed |
| `progress` | integer | 进度百分比 (0-100) |
| `message` | string | 状态消息 |
| `result` | object | 结果 (completed 时) |
| `error` | object | 错误 (failed 时) |

---

### aios/capability.cancel

取消正在执行的任务。

**参数**：

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `task_id` | string | ✅ | 任务 ID |

**返回**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `success` | boolean | 是否成功取消 |

---

## 2. 权限方法 (aios/permission.*)

### aios/permission.request

请求权限。

**参数**：

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `capability_id` | string | ✅ | 能力 ID |
| `permissions` | array | ✅ | 权限请求列表 |
| `permissions[].level` | string | ✅ | 权限级别 (low/medium/high/critical) |
| `permissions[].scope` | string | ❌ | 范围限定 |
| `permissions[].duration` | string | ❌ | 有效期 (once/task/session/timed:N) |
| `permissions[].reason` | string | ❌ | 请求原因 |

**返回**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `granted` | boolean | 是否授予 |
| `tokens` | array | 令牌列表 (如果授予) |
| `reason` | string | 拒绝原因 (如果拒绝) |

---

### aios/permission.list

列出当前已授予的权限。

**参数**：

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `session_id` | string | ❌ | 会话 ID |
| `capability_id` | string | ❌ | 能力 ID |

**返回**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `permissions` | array | 权限令牌列表 |

---

### aios/permission.revoke

撤销权限。

**参数**：

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `token_id` | string | 二选一 | 令牌 ID |
| `capability_id` | string | 二选一 | 能力 ID (撤销该能力所有权限) |

**返回**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `success` | boolean | 是否成功 |
| `revoked_count` | integer | 撤销的令牌数量 |

---

## 3. 会话方法 (aios/session.*)

### aios/session.create

创建新会话。

**参数**：

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `user_id` | string | ❌ | 用户 ID |
| `metadata` | object | ❌ | 会话元数据 |
| `timeout_ms` | integer | ❌ | 会话超时 |

**返回**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `session_id` | string | 会话 ID |
| `created_at` | string | 创建时间 |
| `expires_at` | string | 过期时间 |

---

### aios/session.info

获取会话信息。

**参数**：

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `session_id` | string | ✅ | 会话 ID |

**返回**：会话详细信息

---

### aios/session.close

关闭会话。

**参数**：

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `session_id` | string | ✅ | 会话 ID |

---

## 4. 资源方法 (aios/resource.*)

### aios/resource.list

列出可用资源。

**参数**：

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `capability_id` | string | ❌ | 能力 ID |
| `uri` | string | ❌ | 资源 URI 前缀 |

**返回**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `resources` | array | 资源列表 |
| `resources[].uri` | string | 资源 URI |
| `resources[].name` | string | 资源名称 |
| `resources[].type` | string | 资源类型 |
| `resources[].mime_type` | string | MIME 类型 |

---

### aios/resource.read

读取资源内容。

**参数**：

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `uri` | string | ✅ | 资源 URI |

**返回**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `uri` | string | 资源 URI |
| `content` | string | 资源内容 |
| `mime_type` | string | MIME 类型 |
| `size` | integer | 大小 (字节) |

---

## 5. 批量方法 (aios/batch.*)

### aios/batch.execute

批量执行多个操作。

**参数**：

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `mode` | string | ❌ | 执行模式 (parallel/sequential/dag)，默认 sequential |
| `operations` | array | ✅ | 操作列表 |
| `operations[].id` | string | ✅ | 操作 ID |
| `operations[].method` | string | ✅ | 方法名 |
| `operations[].params` | object | ❌ | 方法参数 |
| `operations[].depends_on` | array | ❌ | 依赖的操作 ID |
| `options.stop_on_error` | boolean | ❌ | 遇错停止，默认 true |
| `options.timeout_ms` | integer | ❌ | 总超时时间 |

**返回**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `overall_status` | string | 整体状态 |
| `results` | array | 各操作结果 |
| `results[].id` | string | 操作 ID |
| `results[].status` | string | success/failed/skipped |
| `results[].result` | object | 操作结果 |
| `results[].error` | object | 错误信息 |

---

## 6. 流式方法 (aios/stream.*)

### 通知消息

流式消息通过通知方式发送，无需响应。

#### aios/stream.start

```json
{
  "method": "aios/stream.start",
  "params": {
    "stream_id": "string",
    "task_id": "string",
    "estimated_chunks": 10
  }
}
```

#### aios/stream.chunk

```json
{
  "method": "aios/stream.chunk",
  "params": {
    "stream_id": "string",
    "index": 0,
    "data": "any"
  }
}
```

#### aios/stream.progress

```json
{
  "method": "aios/stream.progress",
  "params": {
    "stream_id": "string",
    "progress": 50,
    "message": "string"
  }
}
```

#### aios/stream.end

```json
{
  "method": "aios/stream.end",
  "params": {
    "stream_id": "string",
    "result": "any"
  }
}
```

### 控制请求

#### aios/stream.pause

暂停流式传输。

#### aios/stream.resume

恢复流式传输。

#### aios/stream.cancel

取消流式传输。

---

## 7. 错误码速查

| 错误码 | 消息 | 说明 |
|--------|------|------|
| -32700 | Parse error | JSON 解析错误 |
| -32600 | Invalid Request | 无效请求 |
| -32601 | Method not found | 方法不存在 |
| -32602 | Invalid params | 无效参数 |
| -32603 | Internal error | 内部错误 |
| -32001 | Permission denied | 权限被拒绝 |
| -32002 | User cancelled | 用户取消确认 |
| -32003 | Capability not found | 能力不存在 |
| -32004 | Adapter not available | 适配器不可用 |
| -32005 | Timeout | 执行超时 |
| -32006 | Rate limited | 频率限制 |
| -32007 | Resource busy | 资源忙 |
| -32008 | Platform not supported | 平台不支持 |
| -32009 | Version mismatch | 版本不兼容 |
| -32010 | Sandbox violation | 沙盒违规 |
| -32100 | Compat provider not running | 应用未运行 |
| -32102 | File not found | 文件不存在 |
| -32104 | Session expired | 会话过期 |
| -32106 | Task not found | 任务不存在 |
| -32108 | Validation failed | 验证失败 |

→ 详见 [错误码规范](../protocol/AIOS-Protocol-ErrorCodes.md)

---

**文档版本**: 2.0.0
**最后更新**: 2026-01-09
**维护者**: AIOS Protocol Team
