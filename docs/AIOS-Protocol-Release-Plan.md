# AIOS Protocol 协议发布计划

**版本**: 2.0.0  
**更新日期**: 2026-01-09  
**状态**: 规划阶段

---

## 概述

本文档描述了如何将 AIOS Protocol 作为开放标准协议发布，参考 [MCP (Model Context Protocol)](https://modelcontextprotocol.io) 的成功发布模式。

---

## 一、发布模式参考

### MCP 发布模式分析

| 组成部分 | MCP 做法 | 效果 |
|---------|---------|------|
| **协议规范网站** | modelcontextprotocol.io（Mintlify 构建） | 专业、易读 |
| **GitHub 组织** | github.com/modelcontextprotocol | 开源透明 |
| **多语言 SDK** | TypeScript、Python、Kotlin、Swift | 跨平台支持 |
| **JSON Schema** | 机器可读的规范定义 | 工具生成 |
| **官方背书** | Anthropic 博客公告 | 权威认可 |
| **社区生态** | MCP Servers 目录、Discord | 开发者参与 |

### AIOS 应采用的路径

```
┌─────────────────────────────────────────────────────────────────┐
│                   AIOS Protocol 发布架构                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   ┌─────────────────┐    ┌─────────────────┐    ┌────────────┐ │
│   │  协议规范网站    │    │  GitHub 组织     │    │  SDK 分发  │ │
│   │  aios-protocol  │    │  /aios-protocol  │    │  npm/PyPI  │ │
│   │      .io        │    │                  │    │  crates.io │ │
│   └────────┬────────┘    └────────┬─────────┘    └─────┬──────┘ │
│            │                      │                    │        │
│            └──────────────────────┼────────────────────┘        │
│                                   ▼                             │
│                        ┌─────────────────────┐                  │
│                        │   开发者社区         │                  │
│                        │   Discord/论坛      │                  │
│                        └─────────────────────┘                  │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 二、发布路线图

### 第一阶段：基础设施（Week 1-2）

| 任务 | 说明 | 优先级 | 状态 |
|------|------|--------|------|
| 注册域名 | `aios-protocol.io` 或 `aiosprotocol.org` | P0 | ⏳ |
| 创建 GitHub 组织 | `github.com/aios-protocol` | P0 | ⏳ |
| 选择文档框架 | Mintlify / Docusaurus / VitePress | P0 | ⏳ |
| 设计品牌标识 | Logo、配色方案 | P1 | ⏳ |

#### 推荐文档框架

| 框架 | 优势 | 适用场景 |
|------|------|---------|
| **Mintlify** | MCP 使用、美观、AI 友好 | 首选推荐 |
| **Docusaurus** | Meta 开源、功能丰富 | 大型文档 |
| **VitePress** | Vue 生态、轻量快速 | 简洁文档 |

### 第二阶段：规范整理（Week 3-4）

#### 网站结构规划

```
aios-protocol.io/
├── /                       # 首页（协议介绍）
├── /specification          # 协议规范
│   ├── /overview           # 协议总览
│   ├── /core-concepts      # 核心概念
│   ├── /transport          # 传输层规范
│   ├── /messages           # 消息类型
│   ├── /tools              # 工具定义规范
│   ├── /permissions        # 权限模型
│   ├── /lifecycle          # 协议生命周期
│   ├── /errors             # 错误码
│   └── /security           # 安全模型
├── /sdk                    # SDK 文档
│   ├── /python             # Python SDK
│   ├── /typescript         # TypeScript SDK
│   ├── /swift              # Swift SDK
│   └── /rust               # Rust SDK
├── /adapters               # 适配器开发
│   ├── /overview           # 适配器概述
│   ├── /development        # 开发指南
│   └── /examples           # 示例适配器
├── /interoperability       # 协议互操作
│   ├── /mcp                # MCP 集成
│   └── /a2a                # A2A 集成
├── /blog                   # 发布公告
└── /community              # 社区资源
```

#### 文档迁移映射

| 当前文件 | 目标位置 | 转换任务 |
|---------|---------|---------|
| `docs/protocol/00-Overview.md` | `/specification/overview` | 翻译为英文 |
| `docs/protocol/01-CoreConcepts.md` | `/specification/core-concepts` | 翻译为英文 |
| `docs/protocol/02-Transport.md` | `/specification/transport` | 翻译为英文 |
| `docs/protocol/03-Messages.md` | `/specification/messages` | 翻译为英文 |
| `docs/protocol/04-ToolSchema.md` | `/specification/tools` | 翻译为英文 |
| `docs/protocol/05-PermissionModel.md` | `/specification/permissions` | 翻译为英文 |
| `docs/protocol/AIOS-Protocol-Lifecycle.md` | `/specification/lifecycle` | 翻译为英文 |
| `docs/protocol/AIOS-Protocol-ErrorCodes.md` | `/specification/errors` | 翻译为英文 |
| `docs/protocol/AIOS-Protocol-Security.md` | `/specification/security` | 翻译为英文 |
| `docs/protocol/AIOS-Protocol-Interoperability.md` | `/interoperability` | 翻译为英文 |

### 第三阶段：技术规范（Week 5-6）

#### 需要创建的技术文件

| 文件 | 说明 | 格式 |
|------|------|------|
| `aios-protocol.schema.json` | 协议 JSON Schema | JSON |
| `tool.aios.schema.json` | 工具定义 Schema | JSON |
| `openapi.yaml` | HTTP API OpenAPI 规范 | YAML |
| `messages.schema.json` | 消息格式 Schema | JSON |

#### JSON Schema 示例

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://aios-protocol.io/schemas/tool.aios.schema.json",
  "title": "AIOS Tool Definition",
  "description": "Schema for AIOS Protocol tool definition files",
  "type": "object",
  "properties": {
    "tool": {
      "type": "object",
      "properties": {
        "id": { "type": "string", "pattern": "^[a-z]+\\.[a-z]+\\.[a-z_]+$" },
        "name": { "type": "string" },
        "version": { "type": "string", "pattern": "^\\d+\\.\\d+\\.\\d+$" },
        "type": { "enum": ["system", "application", "service", "plugin"] }
      },
      "required": ["id", "name", "version", "type"]
    },
    "capabilities": {
      "type": "array",
      "items": { "$ref": "#/$defs/capability" }
    }
  },
  "$defs": {
    "capability": {
      "type": "object",
      "properties": {
        "id": { "type": "string" },
        "name": { "type": "string" },
        "permission_level": { "enum": ["public", "low", "medium", "high", "critical"] }
      }
    }
  }
}
```

### 第四阶段：SDK 发布（Week 7-10）

#### SDK 发布计划

| SDK | 包名 | 发布渠道 | 状态 |
|-----|------|---------|------|
| Python | `aios-sdk` | PyPI | ⏳ 计划中 |
| TypeScript | `@aios/sdk` | npm | ⏳ 计划中 |
| Swift | `AIOSProtocol` | Swift Package Manager | 🔄 开发中 |
| Rust | `aios-rs` | crates.io | ⏳ 计划中 |
| Go | `aios-go` | Go Modules | ⏳ 计划中 |

#### GitHub 仓库结构

```
github.com/aios-protocol/
├── specification           # 协议规范（核心仓库）
│   ├── docs/               # 规范文档
│   ├── schemas/            # JSON Schema
│   └── examples/           # 示例
├── python-sdk              # Python SDK
├── typescript-sdk          # TypeScript SDK
├── swift-sdk               # Swift SDK（从 aios-macos 分离）
├── rust-sdk                # Rust SDK
├── adapters                # 官方适配器集合
│   ├── system/             # 系统控制适配器
│   ├── browser/            # 浏览器适配器
│   └── office/             # 办公软件适配器
└── website                 # 官网源码
```

### 第五阶段：生态建设（Week 11+）

| 任务 | 说明 | 优先级 |
|------|------|--------|
| **适配器市场** | 类似 MCP Servers 目录 | P1 |
| **示例项目** | 参考实现 + 教程 | P1 |
| **社区渠道** | Discord 服务器 / GitHub Discussions | P1 |
| **认证计划** | "AIOS Compatible" 徽章 | P2 |
| **贡献指南** | CONTRIBUTING.md | P1 |
| **合作伙伴** | AI 公司、OS 厂商合作 | P2 |

---

## 三、国际化策略

### 语言优先级

| 语言 | 优先级 | 说明 |
|------|--------|------|
| **英文** | P0 | 国际标准语言，必须 |
| **中文** | P0 | 原始开发语言，保留 |
| **日文** | P2 | 日本开发者市场 |
| **韩文** | P2 | 韩国开发者市场 |

### 文档结构

```
docs/
├── en/                     # 英文（主要）
│   ├── specification/
│   └── sdk/
├── zh/                     # 中文
│   ├── specification/
│   └── sdk/
└── ja/                     # 日文
```

---

## 四、与 IETF RFC 的对比

| 路径 | 适用场景 | 时间周期 | 权威性 | 灵活性 |
|------|---------|---------|--------|--------|
| **GitHub + 网站** | 快速迭代、实用协议 | 1-3 个月 | 行业认可 | 高 |
| **IETF RFC** | 互联网基础协议 | 1-3 年 | 国际标准 | 低 |

### 建议策略

1. **短期**（2026 Q1-Q2）：GitHub + 独立网站发布
2. **中期**（2026 Q3-Q4）：积累用户和实现案例
3. **长期**（2027+）：考虑提交 IETF 或其他标准化组织

---

## 五、发布清单

### 发布前检查

- [ ] 域名已注册并配置
- [ ] GitHub 组织已创建
- [ ] 协议规范英文版完成
- [ ] JSON Schema 文件完成
- [ ] 至少一个 SDK 可用
- [ ] 文档网站已部署
- [ ] 示例适配器可运行
- [ ] 贡献指南已编写
- [ ] LICENSE 文件已添加（推荐 Apache 2.0 或 MIT）

### 发布公告渠道

| 渠道 | 优先级 | 说明 |
|------|--------|------|
| **官方博客** | P0 | 发布公告主页 |
| **GitHub Releases** | P0 | 版本发布说明 |
| **Hacker News** | P1 | 开发者社区 |
| **Reddit (r/programming)** | P1 | 开发者社区 |
| **Twitter/X** | P1 | 社交媒体 |
| **知乎/掘金** | P1 | 中文开发者社区 |
| **AI 相关媒体** | P2 | 行业影响力 |

---

## 六、竞争分析与定位

### 协议生态对比

| 协议 | 发布者 | 定位 | AIOS 差异化 |
|------|--------|------|-------------|
| **MCP** | Anthropic | AI 调用外部工具 | AIOS 有权限模型 |
| **A2A** | Google | Agent 间通信 | AIOS 面向系统控制 |
| **OpenAI Plugins** | OpenAI | ChatGPT 插件 | AIOS 更底层 |

### AIOS 独特价值主张

1. **系统级控制**：控制操作系统，而非仅调用 API
2. **安全优先**：5 级权限模型 + 能力令牌
3. **国产自主**：中国团队开发的开放协议
4. **MCP/A2A 兼容**：可调用现有 MCP 服务器

---

## 七、时间线总览

```
2026 Q1                    2026 Q2                    2026 Q3
│                          │                          │
├─ Week 1-2: 基础设施      ├─ Week 13-16: 社区建设    ├─ 标准化讨论
├─ Week 3-4: 规范整理      ├─ Week 17-20: 适配器市场  ├─ IETF 探索
├─ Week 5-6: 技术规范      ├─ Week 21-24: 合作伙伴    │
├─ Week 7-10: SDK 发布     │                          │
└─ Week 11-12: 公开发布 🎉  │                          │
```

---

## 八、资源需求

| 资源 | 说明 | 预算估算 |
|------|------|---------|
| **域名** | aios-protocol.io 或类似 | $50/年 |
| **文档托管** | Mintlify Pro 或自建 | $0-150/月 |
| **设计** | Logo、品牌设计 | $200-1000（一次性）|
| **翻译** | 英文翻译 | $500-2000 |
| **服务器** | API 示例、Schema 托管 | $10-50/月 |

---

## 九、成功指标

| 指标 | 目标（6个月内） | 目标（12个月内） |
|------|----------------|-----------------|
| GitHub Stars | 500+ | 2000+ |
| SDK 下载量 | 1000+ | 10000+ |
| 第三方适配器 | 10+ | 50+ |
| 社区成员 | 100+ | 500+ |
| 企业采用 | 2+ | 10+ |

---

## 参考资料

| 资源 | 链接 |
|------|------|
| MCP 官网 | https://modelcontextprotocol.io |
| MCP GitHub | https://github.com/modelcontextprotocol |
| A2A 官网 | https://google.github.io/A2A |
| Mintlify | https://mintlify.com |
| Docusaurus | https://docusaurus.io |
| JSON Schema | https://json-schema.org |
| IETF RFC 指南 | https://www.ietf.org/standards/rfcs/ |

---

**文档版本**: 2.0.0  
**最后更新**: 2026-01-09  
**维护者**: AIOS Protocol Team
