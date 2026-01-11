# AIOS Protocol 开发规范

**版本**: 2.0.0  
**更新日期**: 2026-01-09  
**状态**: 草案

---

## 一、开发者角色

### 角色分类

| 角色 | 职责 | 产出 |
|------|------|------|
| **协议开发者** | 维护 AIOS 核心协议 | 协议规范、SDK |
| **适配器开发者** | 为特定软件开发适配器 | tool.aios.yaml + 适配器代码 |
| **领域扩展者** | 提出领域标准化 | RFC 提案 |
| **集成开发者** | 将 AIOS 集成到自己的系统 | AIOS 客户端/服务端 |

---

## 二、适配器开发规范

### 2.1 项目结构

适配器项目应包含以下文件和目录：

| 文件/目录 | 必要性 | 说明 |
|----------|-------|------|
| `tool.aios.yaml` | 必须 | 工具描述文件 |
| `README.md` | 必须 | 文档 |
| `LICENSE` | 必须 | 许可证 |
| `CHANGELOG.md` | 推荐 | 变更日志 |
| `src/` | 必须 | 源代码目录 |
| `tests/` | 推荐 | 测试代码目录 |
| `examples/` | 推荐 | 使用示例目录 |
| `schemas/` | 可选 | 自定义 Schema |

### 2.2 工具描述文件规范

`tool.aios.yaml` 文件包含以下主要部分：

#### 工具元信息 (必须)

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | string | 工具 ID，反向域名格式 |
| `name` | string | 工具名称 |
| `version` | string | 语义化版本号 |
| `description` | string | 工具功能描述 |
| `author` | string | 作者名称 |
| `license` | string | 许可证类型 |
| `homepage` | string | 主页 URL |
| `repository` | string | 代码仓库 URL |
| `type` | string | 工具类型 (system/application/browser/integration) |
| `category` | array | 分类标签 |
| `platforms` | array | 支持的平台列表 |

#### 能力声明 (必须)

每个能力包含以下字段：

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | string | 能力 ID，推荐 `<namespace>.<category>.<action>`（action 部分为 snake_case），如 `system.audio.set_volume` |
| `name` | string | 能力名称 |
| `description` | string | 详细描述 |
| `version` | string | 能力版本 |
| `input` | object | 输入参数 JSON Schema |
| `output` | object | 输出格式 JSON Schema |
| `permissions` | array | 所需权限列表 |
| `examples` | array | AI 学习示例 |
| `constraints` | object | 执行约束 |

#### 依赖声明

| 字段 | 说明 |
|------|------|
| `protocol.aios` | AIOS 协议版本要求 |
| `system.commands` | 系统命令依赖 |

#### 权限声明

| 字段 | 说明 |
|------|------|
| `id` | 权限 ID |
| `reason` | 需要此权限的原因 |
| `scope` | 权限作用范围 |

#### 可视化支持 (可选)

| 字段 | 说明 |
|------|------|
| `modes` | 支持的可视化模式 |
| `progress_reporting` | 是否支持进度报告 |

### 2.3 适配器基类要求

所有适配器必须实现以下接口：

**必须实现**：

| 方法/属性 | 说明 |
|----------|------|
| `tool_id` | 返回工具 ID |
| `version` | 返回适配器版本 |
| `get_capabilities()` | 返回所有支持的能力 |
| `invoke(capability_id, arguments, context)` | 执行能力调用 |

**可选实现**：

| 方法 | 说明 |
|------|------|
| `initialize()` | 初始化适配器 |
| `shutdown()` | 关闭适配器 |
| `health_check()` | 健康检查 |
| `validate_params()` | 验证参数 |
| `report_progress()` | 报告进度 |
| `notify_user()` | 通知用户 |

---

## 三、协议消息规范

### 3.1 消息格式

AIOS 使用 JSON-RPC 2.0 协议，所有消息必须包含 `jsonrpc: "2.0"` 字段。

**请求消息**：

| 字段 | 必要性 | 说明 |
|------|-------|------|
| `jsonrpc` | 必须 | 固定为 "2.0" |
| `id` | 必须 | 请求 ID (string 或 number) |
| `method` | 必须 | 方法名 (namespace/action 格式) |
| `params` | 可选 | 参数对象 |

**成功响应**：

| 字段 | 必要性 | 说明 |
|------|-------|------|
| `jsonrpc` | 必须 | 固定为 "2.0" |
| `id` | 必须 | 对应请求的 ID |
| `result` | 必须 | 结果数据 |

**错误响应**：

| 字段 | 必要性 | 说明 |
|------|-------|------|
| `jsonrpc` | 必须 | 固定为 "2.0" |
| `id` | 必须 | 对应请求的 ID |
| `error.code` | 必须 | 错误码 |
| `error.message` | 必须 | 错误消息 |
| `error.data` | 可选 | 详细错误信息 |

**通知消息**（无 id 字段）：

| 字段 | 必要性 | 说明 |
|------|-------|------|
| `jsonrpc` | 必须 | 固定为 "2.0" |
| `method` | 必须 | 方法名 |
| `params` | 可选 | 参数对象 |

---

## 四、标准方法列表

### 4.1 生命周期方法

| 方法 | 说明 | 方向 |
|------|------|------|
| `aios/initialize` | 初始化连接 | Client → Server |
| `aios/initialized` | 初始化完成通知 | Server → Client |
| `aios/shutdown` | 关闭连接 | Client → Server |

### 4.2 能力方法

| 方法 | 说明 | 方向 |
|------|------|------|
| `aios/capability.list` | 列出可用能力 | Client → Server |
| `aios/capability.info` | 获取能力信息 | Client → Server |
| `aios/capability.invoke` | 调用能力 | Client → Server |
| `aios/capability.cancel` | 取消执行 | Client → Server |

### 4.3 权限方法

| 方法 | 说明 | 方向 |
|------|------|------|
| `aios/permission.request` | 请求权限 | Server → Client |
| `aios/permission.grant` | 授予权限 | Client → Server |
| `aios/permission.revoke` | 撤销权限 | Client → Server |
| `aios/permission.list` | 列出权限 | Client → Server |

### 4.4 进度方法

| 方法 | 说明 | 方向 |
|------|------|------|
| `aios/progress.report` | 报告进度 | Server → Client |
| `aios/progress.cancel` | 取消进度 | Client → Server |

---

## 五、传输协议

### 5.1 支持的传输方式

| 传输 | 适用场景 | 实现要求 |
|------|---------|---------|
| **stdio** | 进程内通信 | 必须支持 |
| **Unix Socket** | 本地进程间 | 推荐支持 |
| **HTTP** | 远程调用 | 可选支持 |
| **WebSocket** | 实时双向 | 可选支持 |

### 5.2 消息分帧 (stdio)

使用 HTTP 风格的头部分帧：
- `Content-Length: <length>\r\n\r\n<JSON-RPC message>`

### 5.3 HTTP 映射

| JSON-RPC | HTTP |
|---------|------|
| 请求 | POST /jsonrpc |
| 成功响应 | 200 OK |
| 解析错误 | 400 Bad Request |
| 方法未找到 | 200 OK (错误在 body) |
| 认证失败 | 401 Unauthorized |

---

## 六、测试规范

### 6.1 必须通过的测试

| 测试名称 | 说明 |
|---------|------|
| schema_validation | tool.aios.yaml 符合 JSON Schema |
| capability_invoke | 所有能力都可正常调用 |
| error_handling | 错误返回格式正确 |
| permission_request | 权限请求格式正确 |
| unknown_fields | 能正确忽略未知字段 |

### 6.2 测试工具命令

| 命令 | 用途 |
|------|------|
| `aios-cli validate tool.aios.yaml` | 验证工具描述文件 |
| `aios-cli test --compatibility <adapter>` | 运行兼容性测试 |
| `aios-cli invoke <capability_id> --arguments '{...}'` | 模拟调用 |

---

## 七、发布规范

### 7.1 发布清单

| 检查项 | 说明 |
|-------|------|
| tool.aios.yaml 通过验证 | 使用 aios-cli validate |
| 所有测试通过 | 单元测试 + 集成测试 |
| 版本号遵循语义化版本 | MAJOR.MINOR.PATCH |
| CHANGELOG.md 已更新 | 记录变更内容 |
| README.md 包含安装说明 | 用户指南 |
| LICENSE 文件存在 | 明确许可证 |
| 无安全漏洞 | 安全审计 |

### 7.2 版本发布流程

1. 更新版本号 (tool.aios.yaml, package.json 等)
2. 更新 CHANGELOG.md
3. 运行完整测试套件
4. 创建 Git tag
5. 发布到注册表
6. 通知依赖者 (如有破坏性变更)

---

## 八、命名规范

| 类型 | 格式 | 示例 |
|------|------|------|
| 工具 ID | 反向域名 | `com.example.mytool` |
| 能力 ID | 分层命名 | `system.audio.set_volume` |
| 权限 ID | 点分层级 | `aios.permission.filesystem.read` |
| 错误 ID | 大写连字符 | `AIOS-TOOL-001` |

---

## 九、文档规范

### 9.1 必须包含的文档

| 文档内容 | 说明 |
|---------|------|
| 每个能力的 description | 清晰描述功能 |
| 每个参数的说明 | 类型、范围、默认值 |
| 使用示例 | AI 学习用 |
| 权限用途说明 | 为什么需要此权限 |
| 版本变更记录 | CHANGELOG |

### 9.2 文档质量要求

- 使用清晰简洁的语言
- 避免歧义表述
- 提供足够的上下文
- 保持文档与代码同步

---

**文档版本**: 2.0.0  
**最后更新**: 2026-01-09  
**维护者**: AIOS Protocol Team
