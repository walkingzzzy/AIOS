# 14 · Provider Registry 与 Portal 规范

**版本**: 1.0.0  
**更新日期**: 2026-03-08  
**状态**: P1/P2 核心规格

---

## 1. 目标

本文件定义 AIOS 中 provider 如何被声明、注册、发现、授权与调用。  
它补齐 `13-AI 控制流与应用调用规范` 中“谁负责最后一跳执行”的契约缺口。

Provider Registry 负责回答：

- 系统里有哪些 provider 可用
- 每个 provider 支持哪些 capability
- 它运行在什么信任边界中
- 调用它需要哪些权限、预算与前置条件

Portal 负责回答：

- 当 workload、compat、shell 或第三方对象需要系统能力时，如何通过统一 broker 申请能力
- 如何把“临时授权”与“持久权限”从 UI 语义变成系统语义

## 2. 基本原则

### 2.1 registry 不是权限系统

Registry 只负责：

- 描述 provider
- 发现 provider
- 路由到 provider
- 报告 provider 状态

真正的授权与裁决仍由 `policyd` 负责。

### 2.2 portal 不是快捷调用通道

Portal 是统一受控入口，而不是绕过 capability policy 的简化接口。

### 2.3 所有 provider 都必须有边界

每个 provider 必须显式声明：

- 运行位置
- 资源预算
- 权限需求
- 依赖的设备 / 网络 / 文件系统范围
- 是否允许远端桥接

## 3. Provider 分类

| 类型 | 说明 | 示例 |
|------|------|------|
| `system provider` | 核心系统能力提供者 | 文件、电源、通知、网络状态 |
| `device provider` | 设备与多模态能力提供者 | 摄像头、麦克风、屏幕采集 |
| `shell provider` | 壳层能力提供者 | window/focus/workspace |
| `runtime provider` | 推理与运行时能力提供者 | local inference / embedding / rerank |
| `compat provider` | 旧应用与外部系统桥接 | browser / office / SaaS bridge |
| `portal provider` | 统一用户授权与对象选择入口 | file chooser / open-uri / export target |
| `remote bridge provider` | 对外协议桥接 | MCP / A2A / OAuth/API bridge |

## 4. Provider Descriptor

每个 provider 必须提供结构化 descriptor，至少包含：

- `provider_id`
- `version`
- `kind`
- `display_name`
- `owner`
- `capabilities[]`
- `execution_location`：`local` / `sandbox` / `attested_remote`
- `sandbox_class`
- `required_permissions[]`
- `resource_budget`
- `supported_targets`
- `input_schema_refs`
- `output_schema_refs`
- `timeout_policy`
- `retry_policy`
- `healthcheck`
- `audit_tags`
- `taint_behavior`
- `degradation_policy`

### 4.1 capability 声明要求

每个 provider 暴露的 capability 至少还要说明：

- 是否只读
- 是否可恢复
- 是否需要审批
- 是否会产生外部副作用
- 是否会触发动态代码执行
- 是否依赖用户交互对象选择

## 5. Registry 模型

## 5.1 核心对象

Registry 至少维护三类对象：

- `provider_record`
- `capability_index`
- `provider_health_state`

### `provider_record`

用于描述 provider 的静态事实：

- 身份
- 版本
- 类型
- 可用 capability
- 依赖与边界

### `capability_index`

用于支持：

- capability → provider 候选集
- domain → provider 候选集
- execution location → provider 候选集

### `provider_health_state`

用于记录：

- 启动中 / 可用 / 降级 / 不可用
- 最近错误
- 熔断状态
- 资源压力状态

## 5.2 Registry 生命周期

### 注册

provider 启动后向 registry 注册自身 descriptor。

### 激活

registry 验证 descriptor 完整性、版本兼容性与签名 / 来源后，将 provider 标记为 `active`。

### 发现

`agentd`、`shell`、portal 或其他系统服务通过 registry 查询可用 provider。

### 失活

若 provider 健康检查失败、权限撤销或版本不兼容，则进入 `degraded` 或 `disabled`。

### 注销

provider 卸载、崩溃或被策略禁用时，registry 注销该实例。

## 6. Registry 接口建议

建议最少提供以下系统接口：

- `provider.register`
- `provider.unregister`
- `provider.discover`
- `provider.resolve_capability`
- `provider.get_descriptor`
- `provider.health.get`
- `provider.disable`
- `provider.enable`

说明：

- `provider.discover` 只返回候选
- `provider.resolve_capability` 只负责解析，不自动授权
- 真正调用前仍需 `policyd` 签发 execution token

## 7. Portal 模型

Portal 是受控对象选择与受限资源授予层。  
其作用类似“系统代理式 chooser + broker”。

## 7.1 Portal 负责的场景

- 用户选择文件 / 目录 / 导出位置
- 用户选择要共享的屏幕 / 窗口
- 用户选择联系人、邮箱、浏览器 tab 等对象
- 用户确认外发目标、下载目标、导出目标

## 7.2 Portal 的基本规则

- Portal 只能授予**明确、最小、可审计**的对象访问权
- Portal 授予的是对象句柄或受限 token，而不是广泛文件系统权限
- Portal 返回的对象引用必须带过期时间与来源说明

## 7.3 Portal 输出对象

Portal 可以返回：

- `file_handle`
- `directory_handle`
- `window_handle`
- `screen_share_handle`
- `export_target_handle`
- `contact_ref`
- `remote_account_ref`

这些句柄必须：

- 可审计
- 可撤销
- 可过期
- 与用户 / 会话绑定

## 8. 标准调用链

### 8.1 Registry 解析链

```text
intent
  ↓
agentd
  ↓
resolve capability
  ↓
provider registry
  ↓
provider candidates
  ↓
policyd
  ↓
selected provider + execution token
```

### 8.2 Portal 授权链

```text
task needs user-selected object
  ↓
portal.request
  ↓
user selects object
  ↓
portal returns scoped handle
  ↓
policyd binds handle to task/session
  ↓
provider consumes handle
```

## 9. MCP / A2A 与 Registry 的关系

外部协议桥接 provider 也必须进入 registry，而不是绕过 registry 单独存在。

Registry 至少要记录：

- 对端来源
- 协议类型：`mcp` / `a2a` / `api`
- 认证方式
- schema 版本
- 信任级别
- 超时策略
- 可调用 capability 映射

规则：

- 外部对端默认低信任
- schema 校验失败的 provider 不得激活
- `mcp.*` / `a2a.*` 只表示桥接来源，不代表授权豁免

## 10. 路由与选择规则

当多个 provider 同时支持同一 capability 时，推荐按以下顺序选择：

1. `system provider`
2. `runtime/device/shell provider`
3. `local compat provider`
4. `sandbox compat provider`
5. `attested remote bridge provider`
6. `GUI automation fallback`

附加过滤条件：

- execution location 是否符合策略
- 数据分类是否允许
- 预算是否足够
- provider 健康状态是否正常
- 是否需要用户通过 portal 选择对象

## 11. 错误模型

Registry / Portal 至少应统一以下错误类：

- `PROVIDER_NOT_FOUND`
- `CAPABILITY_UNRESOLVED`
- `PROVIDER_INCOMPATIBLE`
- `PROVIDER_DISABLED`
- `PORTAL_CANCELLED`
- `PORTAL_HANDLE_EXPIRED`
- `PORTAL_SCOPE_VIOLATION`
- `REMOTE_SCHEMA_INVALID`
- `REMOTE_TRUST_INSUFFICIENT`
- `EXECUTION_LOCATION_DENIED`

## 12. 审计要求

下列动作必须进入审计链：

- provider 注册 / 注销
- provider 被禁用 / 启用
- capability 被解析到哪个 provider
- portal 请求了什么对象
- portal 最终授予了哪个句柄
- 远端桥接是否被选中
- 降级到 GUI fallback 的原因

## 13. v1 最低要求

- 有本地 provider registry
- system / shell / device / compat provider 全部进入 registry
- 至少有文件、导出目标、屏幕共享三类 portal
- provider health state 可查询
- capability 到 provider 的解析链可审计
- 外部 MCP / A2A provider 进入低信任路径

## 14. 与现有文档的关系

- `13-AI 控制流与应用调用规范` 负责说明“怎么调用”
- 本文负责说明“调用谁、怎么发现、怎么把对象授权给它”
- `10-能力、策略与审计规范` 仍负责最终授权与执行 token
