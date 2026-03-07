# AIOS Protocol 权限模型

> **系统开发口径修订（2026-03-08）**
> AIOS 统一定义为 **AI 原生操作系统 / 系统软件工程**。本文如提及桌面应用、Electron 客户端、应用适配器、App 安装等内容，除非明确标注为“原型期 / 兼容层 / 历史实现”，否则不再代表目标形态。
> 当前最高约束：**系统镜像、系统服务、系统壳层、设备/能力抽象、权限与更新恢复**。


**版本**: 2.0.0
**更新日期**: 2026-01-09
**状态**: 战略规划阶段

---

## 概述

本文档定义 AIOS Protocol 的权限模型，包括权限体系、能力令牌、授权流程。

> **相关文档**:
> - [任务管理规范](AIOS-Protocol-TaskManagement.md) - `auth_required` 状态处理
> - [协议互操作性](AIOS-Protocol-Interoperability.md) - 跨协议权限增强

---

## 1. 设计原则

| 原则 | 说明 |
|------|------|
| **最小权限** | 工具只能请求完成任务所需的最小权限 |
| **默认拒绝** | 未明确授权的操作一律拒绝 |
| **用户知情** | 用户必须明确知道并同意权限授予 |
| **可撤销** | 用户可以随时撤销已授予的权限 |
| **可审计** | 所有权限使用必须可追溯 |
| **时效限制** | 权限应有明确的有效期 |

---

## 2. 五级权限体系

### 权限级别定义

| 级别 | 标识 | 用户确认 | 自动授权 | 审计 | 示例 |
|------|------|---------|---------|------|------|
| **0** | `public` | 无需 | ✅ 允许 | 可选 | 读取时间、系统信息 |
| **1** | `low` | 首次 | ✅ 允许 | 建议 | 读取设置、调整音量 |
| **2** | `medium` | 首次 | ⚠️ 可配置 | 必须 | 打开浏览器、网络请求 |
| **3** | `high` | 每次 | ❌ 禁止 | 必须+详细 | 发送消息、写入文件 |
| **4** | `critical` | 二次确认 | ❌ 禁止 | 必须+实时 | 关机、删除文件 |

### 确认方式说明

| 确认类型 | 说明 |
|---------|------|
| **无需** | 系统自动授权，无需用户干预 |
| **首次** | 首次使用时确认，后续自动授权 |
| **每次** | 每次使用都需要确认 |
| **二次确认** | 需要用户通过两个独立动作确认 |

---

## 3. 权限命名空间

### 命名格式

```
aios.permission.<category>.<resource>.<action>
```

### 标准权限类别

#### filesystem (文件系统)

| 权限 | 级别 | 说明 |
|------|------|------|
| `aios.permission.filesystem.home.read` | low | 读取主目录 |
| `aios.permission.filesystem.home.write` | high | 写入主目录 |
| `aios.permission.filesystem.home.delete` | critical | 删除主目录文件 |
| `aios.permission.filesystem.system.read` | medium | 读取系统目录 |
| `aios.permission.filesystem.system.write` | critical | 写入系统目录 |

#### system (系统)

| 权限 | 级别 | 说明 |
|------|------|------|
| `aios.permission.system.info.read` | public | 读取系统信息 |
| `aios.permission.system.settings.read` | low | 读取系统设置 |
| `aios.permission.system.settings.write` | high | 修改系统设置 |
| `aios.permission.system.power.lock` | low | 锁定屏幕 |
| `aios.permission.system.power.suspend` | high | 休眠 |
| `aios.permission.system.power.shutdown` | critical | 关机 |
| `aios.permission.system.power.reboot` | critical | 重启 |

#### network (网络)

| 权限 | 级别 | 说明 |
|------|------|------|
| `aios.permission.network.local.connect` | low | 连接本地网络 |
| `aios.permission.network.internet.connect` | medium | 连接互联网 |
| `aios.permission.network.internet.listen` | high | 监听网络端口 |

#### compat（兼容层）

| 权限 | 级别 | 说明 |
|------|------|------|
| `aios.permission.compat.launch` | medium | 启动应用 |
| `aios.permission.compat.control` | high | 控制应用 |
| `aios.permission.compat.data.read` | high | 读取应用数据 |
| `aios.permission.compat.data.write` | critical | 修改应用数据 |

#### desktop (桌面)

| 权限 | 级别 | 说明 |
|------|------|------|
| `aios.permission.desktop.wallpaper.read` | public | 读取壁纸设置 |
| `aios.permission.desktop.wallpaper.write` | low | 修改壁纸 |
| `aios.permission.desktop.theme.read` | public | 读取主题 |
| `aios.permission.desktop.theme.write` | low | 修改主题 |

#### gui / vision (界面与视觉)

| 权限 | 级别 | 说明 |
|------|------|------|
| `aios.permission.gui.read` | low | 读取界面元素结构 (Accessibility Tree) |
| `aios.permission.gui.control` | medium | 控制界面元素 (Accessibility Action) |
| `aios.permission.vision.analyze` | high | **截屏并分析 (Screen Capture)** |
| `aios.permission.gui.input.simulate` | high | 模拟输入 (Raw Input) |
| `aios.permission.gui.input.humanlike` | medium | **模拟仿生输入 (Human-like Input)** |

#### audio (音频)

| 权限 | 级别 | 说明 |
|------|------|------|
| `aios.permission.audio.volume.read` | public | 读取音量 |
| `aios.permission.audio.volume.write` | low | 调整音量 |
| `aios.permission.audio.record` | high | 录音 |

---

## 4. 能力令牌 (Capability Token)

### 令牌结构

```json
{
  "token_id": "cap-token-abc123",
  "tool_id": "org.aios.browser.chrome",
  "permission_id": "aios.permission.network.internet.connect",
  "scope": "https://jd.com/*",
  "issued_at": "2026-01-05T10:00:00Z",
  "expires_at": "2026-01-05T11:00:00Z",
  "issued_by": "user-001",
  "revocable": true,
  "signature": "..."
}
```

### 字段说明

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `token_id` | string | ✅ | 唯一标识符 |
| `tool_id` | string | ✅ | 工具标识 |
| `permission_id` | string | ✅ | 权限标识 |
| `scope` | string | ❌ | 资源范围限定 |
| `issued_at` | timestamp | ✅ | 签发时间 |
| `expires_at` | timestamp | ❌ | 过期时间 |
| `issued_by` | string | ✅ | 授权者 |
| `revocable` | boolean | ✅ | 是否可撤销 |
| `signature` | string | ✅ | 数字签名 |

### 范围限定 (Scope)

限定权限的适用范围：

| 类型 | 范围表达式 | 说明 |
|------|-----------|------|
| 文件 | `/home/user/Documents/*` | 仅限 Documents 目录 |
| 文件 | `/home/user/*.jpg` | 仅限主目录下的 jpg 文件 |
| 网络 | `https://jd.com/*` | 仅限 jd.com 域名 |
| 网络 | `https://*.example.com/*` | 仅限 example.com 子域名 |
| 应用 | `org.mozilla.firefox` | 仅限特定应用 |

### 时效类型

| 类型 | 语法 | 说明 |
|------|------|------|
| 单次 | `once` | 使用一次后失效 |
| 任务 | `task` | 当前任务完成后失效 |
| 会话 | `session` | 当前会话结束后失效 |
| 定时 | `timed:3600` | 3600 秒后失效 |
| 永久 | `persistent` | 永久有效（需明确同意） |

---

## 5. 权限请求流程

### 标准流程

```
┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
│ 工具请求 │ ─→ │ 权限检查 │ ─→ │ 用户确认 │ ─→ │ 令牌签发 │
└──────────┘    └──────────┘    └──────────┘    └──────────┘
      │               │               │               │
      │               │               │               ▼
      │               │               │         ┌──────────┐
      │               │               └───────→ │ 执行操作 │
      │               │                         └──────────┘
      │               ▼
      │         ┌──────────┐
      └───────→ │ 已有权限 │ ─→ 直接执行
                └──────────┘
```

### 流程步骤

1. **工具请求权限**
```json
{
  "method": "aios/permission.request",
  "params": {
    "capability_id": "compat.browser.open_url",
    "permissions": [{
      "level": "low",
      "scope": "https://jd.com/*",
      "duration": "task",
      "reason": "访问京东网站比较商品价格"
    }]
  }
}
```

2. **系统检查现有权限**
   - 检查是否有匹配的有效令牌
   - 验证范围是否覆盖

3. **用户确认** (如需)
   - 显示权限请求对话框
   - 说明请求原因和范围

4. **签发令牌**
```json
{
  "result": {
    "granted": true,
    "tokens": [{
      "token_id": "cap-token-001",
      "permission_id": "aios.permission.network.internet.connect",
      "scope": "https://jd.com/*",
      "expires_at": "2026-01-05T11:00:00Z"
    }]
  }
}
```

---

## 6. 用户确认机制

### UI 要求

| 级别 | UI 要求 |
|------|---------|
| `low` | 简单确认框 |
| `medium` | 确认框 + 范围说明 |
| `high` | 详细说明 + 明确确认按钮 |
| `critical` | 详细说明 + 二次确认 + 倒计时 |

### 确认对话框示例

```
┌─────────────────────────────────────────────────────────┐
│  🔐 权限请求                                            │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  Chrome 浏览器 请求以下权限:                              │
│                                                         │
│  📌 访问网络                                            │
│     范围: https://jd.com/*                              │
│     有效期: 当前任务                                     │
│                                                         │
│  原因: 访问京东网站比较商品价格                           │
│                                                         │
│  ┌─────────────┐    ┌─────────────┐                     │
│  │   拒绝      │    │   允许      │                     │
│  └─────────────┘    └─────────────┘                     │
│                                                         │
│  □ 记住此选择                                           │
└─────────────────────────────────────────────────────────┘
```

---

## 7. 权限撤销

### 撤销方式

| 方式 | 说明 |
|------|------|
| **手动撤销** | 用户主动撤销 |
| **超时撤销** | 令牌过期自动撤销 |
| **任务结束** | 任务完成时撤销 task 类型令牌 |
| **会话结束** | 会话关闭时撤销 session 类型令牌 |
| **强制撤销** | 检测到安全威胁时强制撤销 |

### 撤销 API

```json
{
  "method": "aios/permission.revoke",
  "params": {
    "token_id": "cap-token-001"
  }
}
```

### 批量撤销

```json
{
  "method": "aios/permission.revoke",
  "params": {
    "capability_id": "compat.browser.open_url"  // 撤销该能力所有权限
  }
}
```

---

## 8. 权限审计

### 审计事件

| 事件 | 说明 |
|------|------|
| `permission.requested` | 权限请求 |
| `permission.granted` | 权限授予 |
| `permission.denied` | 权限拒绝 |
| `permission.used` | 权限使用 |
| `permission.expired` | 权限过期 |
| `permission.revoked` | 权限撤销 |

### 审计日志格式

```json
{
  "timestamp": "2026-01-05T10:00:00Z",
  "event": "permission.granted",
  "session_id": "sess-001",
  "user_id": "user-001",
  "capability_id": "compat.browser.open_url",
  "tool_id": "org.aios.browser.chrome",
  "permission_id": "aios.permission.network.internet.connect",
  "scope": "https://jd.com/*",
  "token_id": "cap-token-001",
  "duration": "task"
}
```

---

## 9. 权限策略配置

### 用户级策略

```yaml
# ~/.config/aios/permission-policy.yaml
auto_grant:
  - "aios.permission.desktop.wallpaper.*"
  - "aios.permission.audio.volume.*"

always_deny:
  - "aios.permission.filesystem.system.*"

require_confirmation:
  level: "medium"  # 此级别及以上需要确认

default_duration: "session"
```

### 系统级策略

```yaml
# /etc/aios/permission-policy.yaml
max_permission_level: "high"  # 禁止授予 critical 权限
require_audit: true
session_timeout: 3600
```

---

## 10. 任务认证 (auth_required)

当任务需要额外认证时（如 OAuth 授权），任务会进入 `auth_required` 状态。

### 认证类型

| 类型 | 说明 |
|------|------|
| `oauth2` | OAuth 2.0 授权码流程 |
| `api_key` | API 密钥 |
| `password` | 用户名密码 |
| `certificate` | 客户端证书 |

### 认证流程

1. 任务执行时发现需要额外认证
2. 任务状态变为 `auth_required`
3. 发送 `task.auth_required` 事件
4. 用户完成认证
5. 调用 `aios/task.authenticate` 提供认证信息
6. 任务恢复执行

→ 详见 [任务管理规范](AIOS-Protocol-TaskManagement.md)

---

**文档版本**: 2.0.0
**最后更新**: 2026-01-09
**维护者**: AIOS Protocol Team
