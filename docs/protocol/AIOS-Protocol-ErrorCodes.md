# AIOS Protocol 错误码规范

> **系统开发口径修订（2026-03-08）**
> AIOS 统一定义为 **AI 原生操作系统 / 系统软件工程**。本文如提及桌面应用、Electron 客户端、应用适配器、App 安装等内容，除非明确标注为“原型期 / 兼容层 / 历史实现”，否则不再代表目标形态。
> 当前最高约束：**系统镜像、系统服务、系统壳层、设备/能力抽象、权限与更新恢复**。


**版本**: 2.0.0
**更新日期**: 2026-01-09
**状态**: 战略规划阶段

---

## 一、错误码设计原则

### 设计目标

1. **唯一性** - 每个错误都有唯一标识
2. **可分类** - 错误码按类别组织
3. **可扩展** - 第三方可定义自己的错误码
4. **国际化** - 支持多语言错误消息
5. **可调试** - 包含足够的上下文信息

---

## 二、错误码结构

### 2.1 错误码格式

```
错误码范围:
  -32768 ~ -32600  : JSON-RPC 标准保留
  -32001 ~ -32099  : AIOS 协议错误
  -32100 ~ -32199  : AIOS 业务错误
  -32200 ~ -20001  : 领域扩展保留
  -20000 ~ -1      : 第三方应用保留
  1 ~ ∞            : 应用自定义 (正数)
```

### 2.2 错误对象结构

```json
{
  "jsonrpc": "2.0",
  "id": "req-001",
  "error": {
    "code": -32001,
    "message": "Permission denied",
    "data": {
      "error_id": "AIOS-PERM-001",
      "details": "Missing required permission: filesystem.home.read",
      "permission_required": "aios.permission.filesystem.home.read",
      "suggestion": "Request permission using aios/permission.request",
      "docs_url": "https://aios-protocol.org/errors/AIOS-PERM-001",
      "timestamp": "2026-01-01T21:30:00Z",
      "trace_id": "trace-xxx"
    }
  }
}
```

---

## 三、JSON-RPC 标准错误码

| 错误码 | 错误ID | 名称 | 说明 |
|-------|--------|------|------|
| -32700 | JSONRPC-PARSE | Parse error | JSON 解析失败 |
| -32600 | JSONRPC-INVALID-REQ | Invalid Request | 请求格式无效 |
| -32601 | JSONRPC-METHOD-NOT-FOUND | Method not found | 方法不存在 |
| -32602 | JSONRPC-INVALID-PARAMS | Invalid params | 参数无效 |
| -32603 | JSONRPC-INTERNAL | Internal error | 内部错误 |

---

## 四、AIOS 协议错误码 (-32001 ~ -32099)

| 错误码 | 错误ID | 名称 | 说明 |
|-------|--------|------|------|
| -32001 | AIOS-PERM-DENIED | Permission denied | 权限被拒绝 |
| -32002 | AIOS-USER-CANCELLED | User cancelled | 用户取消确认 |
| -32003 | AIOS-CAP-NOT-FOUND | Capability not found | 能力不存在 |
| -32004 | AIOS-ADAPTER-UNAVAIL | Adapter not available | 适配器不可用 |
| -32005 | AIOS-TIMEOUT | Timeout | 执行超时 |
| -32006 | AIOS-RATE-LIMITED | Rate limited | 频率限制 |
| -32007 | AIOS-RESOURCE-BUSY | Resource busy | 资源被占用 |
| -32008 | AIOS-PLATFORM-UNSUPPORTED | Platform not supported | 平台不支持 |
| -32009 | AIOS-VERSION-MISMATCH | Version mismatch | 版本不兼容 |
| -32010 | AIOS-SANDBOX-VIOLATION | Sandbox violation | 沙盒违规 |

---

## 五、AIOS 业务错误码 (-32100 ~ -32199)

| 错误码 | 错误ID | 名称 | 说明 |
|-------|--------|------|------|
| -32100 | AIOS-COMPAT-NOT-RUNNING | Compat provider not running | 应用未运行 |
| -32101 | AIOS-COMPAT-NOT-INSTALLED | Compat provider not installed | 应用未安装 |
| -32102 | AIOS-FILE-NOT-FOUND | File not found | 文件不存在 |
| -32103 | AIOS-INVALID-FILE-TYPE | Invalid file type | 文件类型错误 |
| -32104 | AIOS-SESSION-EXPIRED | Session expired | 会话已过期 |
| -32105 | AIOS-SESSION-NOT-FOUND | Session not found | 会话不存在 |
| -32106 | AIOS-TASK-NOT-FOUND | Task not found | 任务不存在 |
| -32107 | AIOS-TASK-CANCELLED | Task cancelled | 任务已取消 |
| -32108 | AIOS-VALIDATION-FAILED | Validation failed | 验证失败 |
| -32109 | AIOS-DEPENDENCY-MISSING | Dependency missing | 依赖缺失 |

---

## 六、兼容性映射（旧错误码 → 新错误码）

> [!NOTE]
> 以下映射表用于从旧 `-31xxx` 错误码迁移到新 `-320xx` 体系。

| 旧错误码 | 新错误码 | 说明 |
|---------|---------|------|
| -31100 | -32001 | Permission denied |
| -31101 | -32001 | Permission not requested → Permission denied |
| -31102 | -32001 | Permission expired → Permission denied |
| -31103 | -32001 | Permission revoked → Permission denied |
| -31200 | -32003 | Tool not found → Capability not found |
| -31201 | -32004 | Tool not available → Adapter not available |
| -31202 | -32003 | Capability not found |
| -31204 | -32005 | Tool timeout → Timeout |
| -31205 | -32005 | Tool timeout → Timeout |
| -31300 | -32102 | Resource not found → File not found |
| -31301 | -32007 | Resource busy |
| -31500 | -32104 | Session not found → Session expired |
| -31700 | -32009 | Protocol version not supported → Version mismatch |

---

## 七、错误处理指南

### 7.1 错误分类与重试策略

| 错误码范围 | 类别 | 是否可重试 | 建议策略 |
|-----------|------|-----------|---------|
| -32001 ~ -32002 | 权限错误 | 是 | 请求权限后重试 |
| -32003 ~ -32004 | 能力错误 | 否 | 检查能力ID或适配器 |
| -32005 ~ -32007 | 资源错误 | 是 | 等待后重试 |
| -32008 ~ -32010 | 环境错误 | 否 | 检查配置 |
| -32100 ~ -32109 | 业务错误 | 视情况 | 根据具体错误处理 |

### 7.2 错误响应最佳实践

```yaml
best_practices:
  - rule: "始终返回有意义的 error_id"
  - rule: "包含足够的上下文信息"
  - rule: "提供解决建议 (suggestion)"
  - rule: "敏感信息不要放在错误中"
  - rule: "提供文档链接 (docs_url)"
  - rule: "包含追踪 ID (trace_id)"
```

---

## 八、第三方错误码规范

### 8.1 注册自定义错误码

```yaml
# 在适配器描述文件中声明
errors:
  namespace: "com.example.mytool"
  codes:
    - code: -20001
      id: "MYTOOL-001"
      name: "Custom error"
      description: "自定义错误说明"
      retryable: false

    - code: -20002
      id: "MYTOOL-002"
      name: "Another error"
      description: "另一个错误"
      retryable: true
      retry_delay_ms: 1000
```

### 8.2 命名规范

```
错误ID格式: <NAMESPACE>-<CATEGORY>-<NUMBER>

示例:
AIOS-PERM-001      # 协议权限错误
BLENDER-MESH-001   # Blender 网格错误
GIMP-LAYER-001     # GIMP 图层错误
```

---

## 九、国际化支持

### 9.1 多语言消息

```json
{
  "error": {
    "code": -32001,
    "message": "Permission denied",
    "data": {
      "error_id": "AIOS-PERM-DENIED",
      "messages": {
        "en": "Permission denied: {permission}",
        "zh-CN": "权限被拒绝: {permission}",
        "ja": "権限が拒否されました: {permission}"
      },
      "permission": "filesystem.home.read"
    }
  }
}
```

### 9.2 消息模板

```yaml
error_templates:
  AIOS-PERM-DENIED:
    en: "Permission denied: {permission_id}. Reason: {reason}"
    zh-CN: "权限被拒绝: {permission_id}。原因: {reason}"

  AIOS-TIMEOUT:
    en: "Execution timeout after {timeout_ms}ms"
    zh-CN: "执行超时，已等待 {timeout_ms} 毫秒"
```

---

**文档版本**: 2.0.0
**最后更新**: 2026-01-09
**维护者**: AIOS Protocol Team
