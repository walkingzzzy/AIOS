# AIOS Protocol 协议互操作性规范

> **系统开发口径修订（2026-03-08）**
> AIOS 统一定义为 **AI 原生操作系统 / 系统软件工程**。本文如提及桌面应用、Electron 客户端、应用适配器、App 安装等内容，除非明确标注为“原型期 / 兼容层 / 历史实现”，否则不再代表目标形态。
> 当前最高约束：**系统镜像、系统服务、系统壳层、设备/能力抽象、权限与更新恢复**。


**版本**: 2.0.0
**更新日期**: 2026-01-09
**状态**: 战略规划阶段

---

## 一、概述

AIOS Protocol 是 AI 系统控制的开放标准，与 MCP/A2A 形成互补关系，共同构成 AI 能力边界。

> **核心定位**：AIOS 做系统控制，MCP 做工具调用，两者互补而非竞争。

### 1.1 协议层级关系

```
┌─────────────────────────────────────────────────────────────────┐
│                     AI 协议生态                                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  MCP (Anthropic)          A2A (Google)         AIOS            │
│  AI ↔ 工具/数据           AI ↔ AI              AI ↔ 操作系统    │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  │
│  │  数据库、API    │  │  Agent 协作     │  │  系统控制       │  │
│  │  文件系统       │  │  任务委托       │  │  兼容层能力     │  │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘  │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 1.2 AIOS 与 MCP/A2A 的关系

| 协议 | 定位 | 范围 | 关系 |
|------|------|------|------|
| **MCP** | AI 调用工具的协议 | API、数据库、文件 | 互补 |
| **A2A** | AI 之间协作的协议 | Agent 间通信 | 互补 |
| **AIOS** | AI 控制系统的协议 | 操作系统、系统服务、兼容层 | 核心 |

**关键区别**：
- **MCP** 解决：AI 如何调用工具（API、数据库、文件）
- **A2A** 解决：AI 如何与其他 AI 协作
- **AIOS** 解决：AI 如何控制操作系统、系统服务与兼容层能力（MCP 不涉及的领域）

### 1.3 AIOS 桥接 MCP/A2A 时的策略叠加

> **注意**：AIOS 与 MCP/A2A 是互补关系。AIOS 专注系统控制域，MCP 专注工具调用域。桥接时可叠加本地策略。

| 能力 | 说明 |
|------|------|
| 策略叠加 | 桥接 MCP/A2A 时可叠加本地用户确认、审计、最小权限策略 |
| 统一调用 | 自动检测协议，无缝切换 |
| 审计追踪 | 跨协议操作统一日志 |
| 用户确认 | 敏感操作需要用户同意 |
| 沙箱隔离 | 外部工具在沙箱中执行 |

### 1.4 MCP生态集成能力

基于深度研究，AIOS支持以下MCP集成方式：

| 集成方式 | 说明 | 适用场景 |
|---------|------|---------|
| **stdio桥接** | 调用本地MCP服务器 | 本地工具 |
| **HTTP桥接** | 调用远程MCP服务器 | 云服务 |
| **mcp-remote代理** | 本地↔远程透明转换 | 混合部署 |
| **OpenAPI转换** | 现有API自动变成工具 | API集成 |

#### AIOS 作为 MCP 服务端 (规划中)

> [!TIP]
> 参考 Make Agent 的双向 MCP 集成模式，AIOS 可作为 MCP 服务端暴露自身能力

```
外部 AI Agent (Claude/Cursor/GPT)
         ↓
    MCP 协议调用
         ↓
   AIOS MCP Server
         ↓
   AIOS 适配器生态 → 操作系统控制
```

**优势**: 使任何支持 MCP 的 AI 都能调用 AIOS 的系统控制能力

→ 详见 [MCP协议分析报告](../research/MCP-Protocol-Analysis-Report.md)

### 1.4 相关文档

| 文档 | 说明 |
|------|------|
| [发现机制规范](AIOS-Protocol-Discovery.md) | Adapter Card、发现端点 |
| [任务管理规范](AIOS-Protocol-TaskManagement.md) | 任务状态机、Artifact |
| [协议生命周期](AIOS-Protocol-Lifecycle.md) | 初始化、版本协商 |

---

## 二、MCP 协议集成

### 2.1 MCP 协议概述

> **Model Context Protocol** - Anthropic 开发的开放标准
> 用于 AI 代理与外部工具/资源的标准化交互

**核心概念**:
| 概念 | 说明 |
|------|------|
| Tools | 可执行的函数 |
| Resources | 可读取的数据资源 |
| Prompts | 可复用的提示模板 |

**通信协议**: JSON-RPC 2.0 (与 AIOS 相同)

**传输方式**:
| 方式 | 说明 | 适用场景 |
|------|------|---------|
| stdio | 标准输入输出 | 本地服务器 |
| Streamable HTTP | HTTP + SSE | 远程服务器 |

### 2.2 AIOS-MCP 概念映射

| MCP 概念 | AIOS 概念 | 说明 |
|---------|----------|------|
| MCP Server | AIOS Tool (Adapter) | 1:1 映射 |
| MCP Tool | AIOS Capability | 功能等价 |
| MCP Resource | AIOS Capability (read) | 作为只读能力 |
| MCP Prompt | AIOS Example | 作为使用示例 |
| - | AIOS Permission | MCP 无权限模型 |

### 2.3 MCP 方法映射

| AIOS 方法 | MCP 方法 |
|----------|---------|
| `aios/initialize` | `initialize` |
| `aios/capability.list` | `tools/list` |
| `aios/capability.invoke` | `tools/call` |
| `aios/resource.list` | `resources/list` |
| `aios/resource.read` | `resources/read` |

### 2.4 MCP 桥接架构

```
┌─────────────────────────────────────────────────────────────────┐
│                      AIOS MCP Bridge                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  │
│  │ 协议转换器      │  │ 权限增强器      │  │ 连接管理器      │  │
│  │ AIOS ↔ MCP     │  │ 添加权限检查    │  │ 服务器生命周期  │  │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘  │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    MCP 服务器池                          │   │
│  │  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐     │   │
│  │  │filesystem│  │ github  │  │ database│  │ custom  │     │   │
│  │  └─────────┘  └─────────┘  └─────────┘  └─────────┘     │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 2.5 MCP 桥接时的策略叠加

> **注意**：MCP 在认证授权方面持续演进（如 OAuth 2.1）。AIOS 桥接 MCP 时可叠加本地策略：

| MCP 工具类型 | AIOS 权限映射 | 风险级别 |
|-------------|--------------|---------|
| filesystem | aios.permission.filesystem.external | medium-high |
| database | aios.permission.data.database | high |
| network | aios.permission.network.internet | medium |
| shell | aios.permission.system.execute | critical |

---

## 三、A2A 协议集成

### 3.1 A2A 协议概述

> **Agent-to-Agent Protocol** - Google 开发的开放标准
> 用于 AI 代理之间的通信与协作

**核心概念**:
| 概念 | 说明 |
|------|------|
| AgentCard | 代理身份和能力声明 |
| Task | 任务单元 (有状态生命周期) |
| Artifact | 任务输出产物 |
| Message/Part | 消息内容单元 |

**通信协议**: HTTP REST + Server-Sent Events (SSE)

### 3.2 AIOS-A2A 概念映射

| A2A 概念 | AIOS 概念 | 说明 |
|---------|----------|------|
| AgentCard | Adapter Card | 能力声明（见[发现机制](AIOS-Protocol-Discovery.md)） |
| A2A Agent | AIOS Tool (remote) | 远程工具 |
| Task | AIOS Task | 有状态任务（见[任务管理](AIOS-Protocol-TaskManagement.md)） |
| Artifact | AIOS Artifact | 输出产物 |
| Skill | AIOS Capability | 能力 |

### 3.3 A2A 任务状态映射

| A2A 状态 | AIOS 状态 | 说明 |
|---------|----------|------|
| submitted | pending | 已提交 |
| working | working | 执行中 |
| input-required | input_required | 需要输入 |
| auth-required | auth_required | 需要认证 |
| completed | completed | 已完成 |
| failed | failed | 失败 |
| canceled | canceled | 已取消 |
| - | paused | 已暂停（AIOS独有） |

> **注意**: AIOS 增加了 `auth_required` 状态用于处理需要额外认证的场景，以及 `paused` 状态用于任务暂停。详见[任务管理规范](AIOS-Protocol-TaskManagement.md)。

### 3.4 A2A 桥接架构

```
┌─────────────────────────────────────────────────────────────────┐
│                      AIOS A2A Bridge                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  │
│  │ AgentCard 解析  │  │ 任务管理器      │  │ SSE 订阅器      │  │
│  │ 能力发现        │  │ 状态追踪        │  │ 实时更新        │  │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘  │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    远程 Agent 注册表                     │   │
│  │  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐     │   │
│  │  │research │  │ coding  │  │ design  │  │ custom  │     │   │
│  │  │ agent   │  │ agent   │  │ agent   │  │ agent   │     │   │
│  │  └─────────┘  └─────────┘  └─────────┘  └─────────┘     │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 3.5 A2A 权限增强

| A2A 操作 | AIOS 权限 | 风险级别 |
|---------|----------|---------|
| 与远程代理通信 | aios.permission.network.a2a | medium |
| 共享数据到远程 | aios.permission.data.share | high |
| 接受远程任务 | aios.permission.task.accept | high |
| 执行远程代码 | aios.permission.system.execute | critical |

---

## 四、统一调用接口

### 4.1 协议自动检测

AIOS 支持自动检测工具使用的协议：

| 检测方式 | 规则 |
|---------|------|
| 前缀检测 | `aios.*` → AIOS, `mcp.*` → MCP, `a2a.*` → A2A |
| URL Scheme | `stdio://` → MCP, `http(s)://` → A2A |
| 发现端点 | `/.well-known/agent.json` → A2A, `/.well-known/aios-adapter.json` → AIOS |

### 4.2 协议路由规则

| 协议 | 路由条件 |
|------|---------|
| AIOS | tool_id 以 `aios.` 开头，或本地注册的原生工具 |
| MCP | tool_id 以 `mcp.` 开头，或配置的 MCP 服务器 |
| A2A | tool_id 以 `a2a.` 开头，或 HTTP(S) URL |

### 4.3 统一工具注册表

```
┌─────────────────────────────────────────────────────────────────┐
│                    统一工具注册表                                │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  │
│  │ AIOS 原生工具   │  │ MCP 服务器      │  │ A2A 代理        │  │
│  │                 │  │                 │  │                 │  │
│  │ • system.power  │  │ • mcp.filesystem│  │ • a2a.research  │  │
│  │ • system.audio  │  │ • mcp.github    │  │ • a2a.coding    │  │
│  │ • browser.chrome│  │ • mcp.database  │  │ • a2a.design    │  │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘  │
│                                                                 │
│  统一查询接口: aios/registry.search → 返回所有协议的能力         │
│  统一调用接口: aios/capability.invoke → 自动路由到正确协议       │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

> **注意**: 工具发现和注册详见[发现机制规范](AIOS-Protocol-Discovery.md)。

---

## 五、跨协议安全

### 5.1 安全风险

| 风险 | 说明 | 缓解措施 |
|------|------|---------|
| 外部工具风险 | 桥接的外部工具可能执行敏感操作 | AIOS 层叠加策略检查 |
| A2A 远程信任 | 远程代理可能不可信 | OAuth + 白名单 + 沙箱 |
| 数据泄露 | 敏感数据可能被发送到外部 | 审计日志 + 数据过滤 |
| 中间人攻击 | 通信可能被拦截 | TLS + 签名验证 |

### 5.2 外部工具默认策略

| 策略 | 值 |
|------|---|
| 默认信任级别 | untrusted |
| 默认沙箱级别 | L2 (WASM) |
| 需要用户确认 | 是 |
| 最大权限级别 | medium |

### 5.3 跨协议审计

所有跨协议调用都记录到统一审计日志：

| 字段 | 说明 |
|------|------|
| protocol | 使用的协议 (aios/mcp/a2a) |
| source_tool | 发起调用的工具 |
| target_tool | 被调用的工具 |
| permission_used | 使用的权限 |
| data_transferred | 传输的数据摘要 |
| result | 调用结果 |

---

## 六、配置规范

### 6.1 MCP 服务器配置

| 字段 | 类型 | 说明 |
|------|------|------|
| name | string | 服务器名称 |
| id | string | 工具 ID |
| transport | enum | stdio / streamable-http |
| command | string | 启动命令 (stdio) |
| args | array | 命令参数 |
| url | string | 服务器 URL (http) |
| auto_register | boolean | 自动注册工具 |

### 6.2 A2A 代理配置

| 字段 | 类型 | 说明 |
|------|------|------|
| name | string | 代理名称 |
| id | string | 工具 ID |
| url | string | 代理 URL |
| auto_discover | boolean | 自动发现能力 |
| trust_level | enum | 信任级别 |
| skills_filter | array | 允许的技能列表 |

### 6.3 权限策略配置

| 字段 | 类型 | 说明 |
|------|------|------|
| default_risk | enum | 默认风险级别 |
| require_approval | boolean | 需要用户批准 |
| max_permissions | array | 最大允许权限 |
| category_mapping | object | 类别到权限的映射 |

---

## 七、发展路线

### 已完成
- [x] 设计 MCP 桥接架构
- [x] 设计 A2A 桥接架构
- [x] 定义统一调用接口
- [x] 规划权限增强策略
- [x] 定义 Adapter Card 规范（对齐 A2A Agent Card）
- [x] 定义任务状态机（增加 auth_required、paused 状态）
- [x] 定义发现端点和注册表 API

### 即将进行
- [ ] 实现 MCP 桥接适配器
- [ ] 实现 A2A 桥接适配器
- [ ] 添加协议自动检测
- [ ] 创建测试用例
- [ ] 编写集成指南

---

## 八、参考资料

| 资源 | 链接 |
|------|------|
| MCP 协议规范 | https://modelcontextprotocol.io/ |
| A2A 协议规范 | https://google.github.io/A2A/ |
| AIOS 核心协议 | ./00-Overview.md |
| AIOS 发现机制 | ./AIOS-Protocol-Discovery.md |
| AIOS 任务管理 | ./AIOS-Protocol-TaskManagement.md |
| AIOS 生命周期 | ./AIOS-Protocol-Lifecycle.md |

---

**文档版本**: 2.0.0
**最后更新**: 2026-01-09
**维护者**: AIOS Protocol Team
