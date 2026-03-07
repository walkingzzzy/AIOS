# AIOS Protocol 发现机制规范

> **系统开发口径修订（2026-03-08）**
> AIOS 统一定义为 **AI 原生操作系统 / 系统软件工程**。本文如提及桌面应用、Electron 客户端、应用适配器、App 安装等内容，除非明确标注为“原型期 / 兼容层 / 历史实现”，否则不再代表目标形态。
> 当前最高约束：**系统镜像、系统服务、系统壳层、设备/能力抽象、权限与更新恢复**。


**版本**: 2.0.0
**更新日期**: 2026-01-09
**状态**: 战略规划阶段

---

## 一、概述

本文档定义 AIOS Protocol 的适配器发现和注册机制，包括 Adapter Card 规范、发现端点和能力协商。

### 1.1 设计目标

| 目标 | 说明 |
|------|------|
| **标准化** | 提供标准化的发现端点，对齐 A2A Agent Card |
| **安全性** | 支持签名验证，确保适配器身份可信 |
| **灵活性** | 支持本地发现和远程发现 |
| **兼容性** | 与现有 .desktop 和 tool.aios.yaml 机制兼容 |

### 1.2 与 MCP/A2A 对比

| 特性 | MCP | A2A | AIOS |
|------|-----|-----|------|
| 发现端点 | 配置文件 | /.well-known/agent-card.json | /.well-known/aios-adapter.json |
| 能力声明 | initialize 握手 | Agent Card | Adapter Card + initialize |
| 身份验证 | - | JWS 签名 | JWS 签名 |
| 本地发现 | - | - | .desktop + inotify |

---

## 二、Adapter Card 规范

### 2.1 端点位置

| 场景 | 端点 |
|------|------|
| HTTP 远程适配器 | `/.well-known/aios-adapter.json` |
| 本地适配器 | `/aios/adapter.json` 或 `tool.aios.yaml` |

### 2.2 Adapter Card 结构

```json
{
  "adapter": {
    "id": "org.aios.browser.chrome",
    "name": "Chrome 浏览器适配器",
    "description": "通过 Chrome DevTools Protocol 控制 Chrome 浏览器",
    "version": "1.0.0",
    "protocol_version": "0.3.0",
    "author": "AIOS Team",
    "homepage": "https://aios.example.com/adapters/chrome",
    "license": "MIT"
  },

  "capabilities": {
    "streaming": true,
    "batch_operations": true,
    "async_tasks": true,
    "push_notifications": false,
    "state_transition_history": true
  },

  "skills": [
    {
      "id": "compat.browser.open_url",
      "name": "打开网址",
      "description": "在浏览器中打开指定的 URL",
      "permission_level": "medium",
      "examples": [
        "打开京东首页",
        "访问 https://example.com"
      ],
      "input_schema": {
        "type": "object",
        "properties": {
          "url": {"type": "string", "format": "uri"}
        },
        "required": ["url"]
      }
    },
    {
      "id": "compat.browser.search",
      "name": "搜索",
      "description": "在搜索引擎中搜索关键词",
      "permission_level": "medium",
      "examples": [
        "搜索无线耳机",
        "查找 Python 教程"
      ]
    },
    {
      "id": "compat.browser.extract_content",
      "name": "提取页面内容",
      "description": "提取当前页面的文本内容",
      "permission_level": "low"
    }
  ],

  "authentication": {
    "required": false,
    "schemes": []
  },

  "endpoints": {
    "rpc": "unix:///run/user/1000/aios/chrome.sock",
    "http": "http://localhost:9527/adapters/chrome",
    "health": "/health",
    "metrics": "/metrics"
  },

  "requirements": {
    "software": {
      "name": "Google Chrome",
      "min_version": "100.0",
      "detection": {
        "desktop_file": "google-chrome.desktop",
        "executable": "/usr/bin/google-chrome",
        "dbus_service": null
      }
    },
    "dependencies": [
      {"name": "chrome-devtools-protocol", "version": ">=1.0"}
    ]
  },

  "extensions": [
    "urn:aios:ext:priority:1.0"
  ],

  "signature": {
    "algorithm": "RS256",
    "key_id": "aios-adapter-key-001",
    "value": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9..."
  }
}
```

### 2.3 字段说明

#### adapter (必需)

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `id` | string | ✅ | 适配器唯一标识符 (反向域名格式) |
| `name` | string | ✅ | 适配器显示名称 |
| `description` | string | ❌ | 适配器描述 |
| `version` | string | ✅ | 适配器版本 (SemVer) |
| `protocol_version` | string | ✅ | 支持的 AIOS 协议版本 |
| `author` | string | ❌ | 作者/组织 |
| `homepage` | string | ❌ | 主页 URL |
| `license` | string | ❌ | 许可证 |

#### capabilities (必需)

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `streaming` | boolean | false | 支持流式传输 |
| `batch_operations` | boolean | false | 支持批量操作 |
| `async_tasks` | boolean | false | 支持异步任务 |
| `push_notifications` | boolean | false | 支持推送通知 |
| `state_transition_history` | boolean | false | 支持状态历史 |

#### skills (必需)

技能列表，对应适配器提供的能力：

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `id` | string | ✅ | 技能标识符 |
| `name` | string | ✅ | 技能显示名称 |
| `description` | string | ❌ | 技能描述 |
| `permission_level` | string | ✅ | 权限级别 (public/low/medium/high/critical) |
| `examples` | array | ❌ | 使用示例 (供 AI 学习) |
| `input_schema` | object | ❌ | 输入参数 JSON Schema |
| `output_schema` | object | ❌ | 输出格式 JSON Schema |

#### authentication (可选)

| 字段 | 类型 | 说明 |
|------|------|------|
| `required` | boolean | 是否需要认证 |
| `schemes` | array | 支持的认证方式 (oauth2/api_key/bearer/mtls) |

#### endpoints (必需)

| 字段 | 类型 | 说明 |
|------|------|------|
| `rpc` | string | JSON-RPC 端点 (unix socket 或 TCP) |
| `http` | string | HTTP 端点 (可选) |
| `health` | string | 健康检查端点 |
| `metrics` | string | 指标端点 (可选) |

#### signature (可选但推荐)

JWS 签名，用于验证 Adapter Card 的真实性：

| 字段 | 类型 | 说明 |
|------|------|------|
| `algorithm` | string | 签名算法 (RS256/ES256) |
| `key_id` | string | 密钥标识符 |
| `value` | string | 签名值 (Base64) |

---

## 三、发现流程

### 3.1 本地发现流程

```
┌─────────────────────────────────────────────────────────────────┐
│                      本地适配器发现流程                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  1. 启动时全量扫描                                               │
│     ├── /usr/share/applications/*.desktop                      │
│     ├── ~/.local/share/applications/*.desktop                  │
│     ├── /usr/share/aios/adapters/*.yaml                        │
│     └── ~/.local/share/aios/adapters/*.yaml                    │
│                                                                 │
│  2. 建立 inotify 监控                                           │
│     └── 监控上述目录的 CREATE/DELETE/MODIFY 事件                 │
│                                                                 │
│  3. 解析适配器描述                                               │
│     ├── .desktop 文件 → 提取应用元数据                          │
│     └── tool.aios.yaml → 完整适配器描述                         │
│                                                                 │
│  4. 匹配预定义适配器库                                           │
│     └── 根据应用 ID 匹配已知适配器                               │
│                                                                 │
│  5. 验证适配器签名 (如有)                                        │
│                                                                 │
│  6. 注册到工具注册表                                             │
│                                                                 │
│  7. 通知 AI 引擎新工具可用                                       │
│     └── aios/notification.tools_changed                        │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 远程发现流程

```
┌─────────────────────────────────────────────────────────────────┐
│                      远程适配器发现流程                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  1. 获取 Adapter Card                                           │
│     GET https://adapter.example.com/.well-known/aios-adapter.json
│                                                                 │
│  2. 验证签名                                                    │
│     ├── 获取公钥 (从 key_id 或 JWKS 端点)                       │
│     └── 验证 JWS 签名                                           │
│                                                                 │
│  3. 验证协议版本兼容性                                           │
│                                                                 │
│  4. 注册到工具注册表                                             │
│                                                                 │
│  5. 建立连接 (按需)                                              │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 3.3 发现 API

#### 搜索适配器

**方法**: `aios/registry.search`

**请求**：
```json
{
  "jsonrpc": "2.0",
  "id": "1",
  "method": "aios/registry.search",
  "params": {
    "query": "browser",
    "type": "compat",
    "capabilities": ["streaming"],
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
        "skills_count": 15,
        "status": "available"
      },
      {
        "id": "org.aios.browser.firefox",
        "name": "Firefox 浏览器适配器",
        "version": "1.0.0",
        "skills_count": 12,
        "status": "available"
      }
    ],
    "total": 2
  }
}
```

#### 获取适配器详情

**方法**: `aios/registry.info`

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

**响应**：
```json
{
  "jsonrpc": "2.0",
  "id": "2",
  "result": {
    "adapter": {...},
    "capabilities": {...},
    "skills": [...],
    "status": {
      "available": true,
      "software_installed": true,
      "software_running": false
    }
  }
}
```

#### 刷新发现

**方法**: `aios/registry.refresh`

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

---

## 四、签名验证

### 4.1 签名格式

Adapter Card 签名使用 JWS (JSON Web Signature, RFC 7515) 格式：

```
Header.Payload.Signature
```

### 4.2 签名生成

```python
import json
import base64
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding

def sign_adapter_card(adapter_card: dict, private_key) -> str:
    # 移除现有签名
    card_copy = {k: v for k, v in adapter_card.items() if k != 'signature'}

    # 规范化 JSON
    payload = json.dumps(card_copy, sort_keys=True, separators=(',', ':'))

    # 签名
    signature = private_key.sign(
        payload.encode(),
        padding.PKCS1v15(),
        hashes.SHA256()
    )

    return base64.urlsafe_b64encode(signature).decode()
```

### 4.3 签名验证

```python
def verify_adapter_card(adapter_card: dict, public_key) -> bool:
    signature = adapter_card.get('signature', {})
    if not signature:
        return False

    # 移除签名字段
    card_copy = {k: v for k, v in adapter_card.items() if k != 'signature'}

    # 规范化 JSON
    payload = json.dumps(card_copy, sort_keys=True, separators=(',', ':'))

    # 验证
    try:
        public_key.verify(
            base64.urlsafe_b64decode(signature['value']),
            payload.encode(),
            padding.PKCS1v15(),
            hashes.SHA256()
        )
        return True
    except:
        return False
```

### 4.4 公钥分发

| 方式 | 说明 |
|------|------|
| JWKS 端点 | `/.well-known/jwks.json` |
| 内置信任 | AIOS 内置的受信任公钥 |
| 手动导入 | 用户手动导入公钥 |

---

## 五、工具变更通知

### 5.1 通知事件

当工具注册表发生变化时，发送通知：

```json
{
  "jsonrpc": "2.0",
  "method": "aios/notification.tools_changed",
  "params": {
    "added": [
      {
        "id": "org.aios.browser.chrome",
        "name": "Chrome 浏览器适配器"
      }
    ],
    "removed": [],
    "updated": []
  }
}
```

### 5.2 订阅工具变更

**方法**: `aios/registry.subscribe`

**请求**：
```json
{
  "jsonrpc": "2.0",
  "id": "4",
  "method": "aios/registry.subscribe",
  "params": {
    "events": ["added", "removed", "updated"]
  }
}
```

---

## 六、与 tool.aios.yaml 的关系

### 6.1 格式转换

`tool.aios.yaml` 可以转换为 Adapter Card JSON 格式：

| tool.aios.yaml | Adapter Card |
|----------------|--------------|
| `tool.id` | `adapter.id` |
| `tool.name` | `adapter.name` |
| `tool.version` | `adapter.version` |
| `capabilities[]` | `skills[]` |
| `permissions[]` | 映射到 `skills[].permission_level` |

### 6.2 优先级

当同一适配器同时存在多种描述时：

1. Adapter Card JSON (最高优先级)
2. tool.aios.yaml
3. .desktop 文件 + 自动推断 (最低优先级)

---

## 七、方法速查表

| 方法 | 说明 |
|------|------|
| `aios/registry.search` | 搜索适配器 |
| `aios/registry.info` | 获取适配器详情 |
| `aios/registry.refresh` | 刷新发现 |
| `aios/registry.subscribe` | 订阅工具变更 |
| `aios/registry.unsubscribe` | 取消订阅 |

---

**文档版本**: 2.0.0
**最后更新**: 2026-01-09
**维护者**: AIOS Protocol Team
