# AIOS Protocol 文档中心

**版本**: 2.0.0 | **状态**: 战略规划阶段 | **更新**: 2026-01-09

---

## 🚀 快速开始

**AIOS Protocol** 是 AI 系统控制的开放标准 —— 定义 AI 如何描述、调用和安全执行系统控制能力。

> **核心设计原则**：标准化「接口」，而非「实现」—— 与 MCP 互补，专注系统控制领域。

```
用户: "帮我把壁纸换成蓝色的"
  ↓
AI 引擎 (理解意图) → AIOS Protocol (系统控制) → 操作系统 (更换壁纸)
```

**5 分钟了解 AIOS**：阅读 [协议总览](protocol/00-Overview.md)

---

## 📚 文档目录

### 协议规范

| 文档 | 说明 |
|------|------|
| [协议总览](protocol/00-Overview.md) | 什么是 AIOS Protocol，核心价值和快速示例 |
| [核心概念](protocol/01-CoreConcepts.md) | 适配器、能力、意图、权限等核心定义 |
| [传输层规范](protocol/02-Transport.md) | JSON-RPC 2.0 消息格式和连接方式 |
| [消息类型](protocol/03-Messages.md) | 完整的请求/响应消息定义 |
| [工具描述规范](protocol/04-ToolSchema.md) | tool.aios.yaml 文件格式规范 |
| [权限模型](protocol/05-PermissionModel.md) | 五级权限体系和能力令牌 |
| [协议生命周期](protocol/AIOS-Protocol-Lifecycle.md) | 初始化、版本协商、心跳、重连、关闭流程 |
| [任务管理](protocol/AIOS-Protocol-TaskManagement.md) | 任务状态机、异步执行、Artifact、Webhooks |
| [发现机制](protocol/AIOS-Protocol-Discovery.md) | Adapter Card、发现端点、签名验证 |
| [安全模型](protocol/AIOS-Protocol-Security.md) | 安全设计和 OWASP 合规 |
| [协议互操作](protocol/AIOS-Protocol-Interoperability.md) | MCP/A2A 集成 |
| [高级特性](protocol/AIOS-Protocol-AdvancedFeatures.md) | 批量操作、流式响应等 |
| [错误码](protocol/AIOS-Protocol-ErrorCodes.md) | 标准错误码定义 |
| [扩展性](protocol/AIOS-Protocol-Extensibility.md) | 协议扩展机制 |
| [差距分析](protocol/AIOS-Protocol-GapAnalysis.md) | 与 MCP/A2A 深度对比分析 |

### 适配器

| 文档 | 说明 |
|------|------|
| [适配器概述](adapters/00-Overview.md) | 适配器系统和软件发现机制 |
| [适配器开发](adapters/01-Development.md) | 如何开发 AIOS 适配器 |

### API 参考

| 文档 | 说明 |
|------|------|
| [API 参考](api/Reference.md) | 完整的 API 方法定义 |

### 开发指南

| 文档 | 说明 |
|------|------|
| [开发规范](guides/AIOS-Protocol-DevSpec.md) | 开发规范和代码风格 |
| [系统开发指南](guides/AIOS-System-DevGuide.md) | 系统控制层开发 |
| [最佳实践](guides/AIOS-Developer-BestPractices.md) | 开发最佳实践 |

### 研究报告

| 文档 | 说明 |
|------|------|
| [技术可行性报告](research/AIOS-TechFeasibility-Report.md) | 技术验证和市场分析 |
| [MCP协议分析](research/MCP-Protocol-Analysis-Report.md) | MCP技术实现与工具集成机制深度分析 |
| [协议开放化方案](research/AIOS-Protocol-Enhancement-Proposal.md) | AIOS协议开放化与完善方案 |
| [工具集成方案](research/AIOS-Tool-Integration-Proposal.md) | 便捷AI工具调用机制设计 |
| [竞品分析 (Doubao/Make)](../AIOS-Competitor-Analysis-Doubao-Make.md) | 豆包手机与 Make Agent 深度分析与对比 |

---

## 🗺️ 阅读路径

### 我是新手
1. [协议总览](protocol/00-Overview.md)
2. [核心概念](protocol/01-CoreConcepts.md)
3. [工具描述规范](protocol/04-ToolSchema.md)

### 我要开发适配器
1. [协议总览](protocol/00-Overview.md) - 了解开放协议设计
2. [适配器概述](adapters/00-Overview.md)
3. [适配器开发](adapters/01-Development.md)
4. [工具描述规范](protocol/04-ToolSchema.md) - 包含多语言SDK示例
5. [最佳实践](guides/AIOS-Developer-BestPractices.md)

### 我要实现协议
1. [协议总览](protocol/00-Overview.md)
2. [传输层规范](protocol/02-Transport.md) - 包含远程部署和桥接
3. [消息类型](protocol/03-Messages.md)
4. [API 参考](api/Reference.md)
5. [权限模型](protocol/05-PermissionModel.md)
6. [协议开放化方案](research/AIOS-Protocol-Enhancement-Proposal.md)

### 我关注安全
1. [安全模型](protocol/AIOS-Protocol-Security.md)
2. [权限模型](protocol/05-PermissionModel.md)
3. [高级特性 - AI Guardrails](protocol/AIOS-Protocol-AdvancedFeatures.md)

---

## 🔗 外部资源

| 资源 | 链接 |
|------|------|
| MCP 协议 | https://modelcontextprotocol.io/ |
| A2A 协议 | https://google.github.io/A2A/ |
| OWASP Agentic Top 10 | https://genai.owasp.org/ |
| FastMCP (Python) | https://gofastmcp.com/ |
| MCP TypeScript SDK | https://github.com/modelcontextprotocol/typescript-sdk |
| Cloudflare Workers MCP | https://developers.cloudflare.com/agents/ |

---

## 📋 最新更新 (2026-01-09)

### v2.0.0 战略更新

#### 核心定位明确
- **AIOS = AI 系统控制协议**（不是 MCP 安全层）
- **与 MCP 互补**：MCP 做工具调用，AIOS 做系统控制
- **设计原则**：标准化「接口」而非「实现」

#### 协议规范统一
- 能力命名空间：`system.*` / `app.*` / `professional.*`
- 调用方法：`aios/capability.invoke`
- 权限模型：5 级（public/low/medium/high/critical）
- 错误码：-32001 ~ -32199

#### SDK 接口规范
- Python SDK：`pip install aios-sdk`
- TypeScript SDK：`@aios/sdk`
- 适配器开发接口标准化

---

**维护者**: AIOS Protocol Team
