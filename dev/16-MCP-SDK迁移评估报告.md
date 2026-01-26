# Phase 4: MCP SDK 迁移评估报告

**评估日期**: 2026-01-17
**评估人**: AIOS 开发团队
**评估版本**: @modelcontextprotocol/sdk v1.x
**状态**: 评估
**适用范围**: MCP SDK 迁移评估结论
**维护人**: zy


---

## 一、现状分析

### 当前实现

| 模块 | 代码量 | 功能覆盖 |
|:---|:---:|:---|
| [MCPClient.ts](file:///Users/mac/Desktop/AIOS/aios/packages/daemon/src/protocol/MCPClient.ts) | 110 LOC | stdio/websocket 客户端、工具列表/调用 |
| [MCPServer.ts](file:///Users/mac/Desktop/AIOS/aios/packages/daemon/src/protocol/MCPServer.ts) | 193 LOC | stdio/websocket 服务端、工具暴露、认证 |

**已实现功能**:
- ✅ JSON-RPC 2.0 协议
- ✅ stdio 和 WebSocket 传输
- ✅ 工具列表与调用 (`tools/list`, `tools/call`)
- ✅ 基础认证 (Bearer Token)

**未实现功能**:
- ❌ Resources 资源暴露
- ❌ Prompts 提示模板
- ❌ Sampling LLM 采样
- ❌ SSE 传输
- ❌ Elicitation 表单/OAuth 输入
- ❌ Tasks 长运行任务
- ❌ 能力协商

---

## 二、官方 SDK 功能对比

| 功能 | 当前实现 | 官方 SDK | 评估 |
|:---|:---:|:---:|:---|
| Tools 工具调用 | ✅ | ✅ | 对等 |
| Resources 资源 | ❌ | ✅ | SDK 优势 |
| Prompts 提示模板 | ❌ | ✅ | SDK 优势 |
| stdio 传输 | ✅ | ✅ | 对等 |
| WebSocket 传输 | ✅ | ✅ | 对等 |
| SSE 传输 | ❌ | ✅ | SDK 优势 |
| Streamable HTTP | ❌ | ✅ | SDK 优势 |
| OAuth 认证 | 部分 | ✅ | SDK 优势 |
| Zod 类型验证 | ❌ | ✅ | SDK 优势 |
| MCP Inspector 调试 | ❌ | ✅ | SDK 优势 |

---

## 三、收益分析

### 3.1 迁移收益

| 收益项 | 影响等级 | 说明 |
|:---|:---:|:---|
| **协议合规性** | 高 | 官方实现保证 100% 协议兼容 |
| **功能扩展性** | 高 | 无需自研 Resources/Prompts/Sampling |
| **类型安全** | 中 | Zod 验证确保输入输出类型正确 |
| **维护成本** | 中 | 官方更新，无需跟踪协议变更 |
| **调试便利** | 中 | MCP Inspector 可视化调试 |

### 3.2 迁移风险

| 风险项 | 影响等级 | 说明 |
|:---|:---:|:---|
| **API 变更** | 中 | SDK v2 预计 Q1 2026 稳定，需跟踪变化 |
| **依赖增加** | 低 | 新增 `zod` peerDependency |
| **集成改动** | 中 | AdapterRegistry 注册逻辑需调整 |
| **测试回归** | 低 | 现有 MCP 测试需重写 |

---

## 四、迁移方案

### 4.1 推荐路径：渐进式迁移

1. **阶段 1 (Week 1)**: 新建 `MCPClientV2.ts` 使用官方 SDK，保留旧实现
2. **阶段 2 (Week 2)**: `MCPServer` 迁移至官方 SDK，添加 Resources 支持
3. **阶段 3 (Week 3)**: 移除旧实现，统一使用 SDK

### 4.2 关键集成点

```typescript
// 使用官方 SDK 创建服务端
import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';

const server = new McpServer({
    name: 'aios-mcp-server',
    version: '1.0.0',
});

// 注册工具
server.tool('adapter_capability', schema, async (args) => {
    return await adapterRegistry.invoke(adapterId, capabilityId, args);
});
```

### 4.3 回滚策略

- 保留 `MCPClient.ts` 和 `MCPServer.ts` 作为 fallback
- 通过环境变量 `AIOS_MCP_SDK=0` 禁用新实现

---

## 五、实施状态

### ✅ Phase 1 已完成 (2026-01-17)

已创建基于官方 SDK 的新实现：

| 文件 | 代码量 | 功能 |
|:---|:---:|:---|
| [MCPClientV2.ts](file:///Users/mac/Desktop/AIOS/aios/packages/daemon/src/protocol/MCPClientV2.ts) | 232 LOC | stdio/websocket、Tools/Resources/Prompts 客户端 |
| [MCPServerV2.ts](file:///Users/mac/Desktop/AIOS/aios/packages/daemon/src/protocol/MCPServerV2.ts) | 437 LOC | stdio/websocket、Tools/Resources/Prompts 服务端 |

**新增能力**：
- ✅ Resources 资源读取
- ✅ Prompts 提示模板
- ✅ Zod 类型验证
- ✅ 向后兼容（旧实现保留）

### 后续行动

| 时间节点 | 行动 |
|:---|:---|
| 当前 | Phase 1 完成，新旧实现共存 |
| 按需 | 迁移现有代码使用 V2 版本 |
| 按需 | 移除旧版 MCPClient/MCPServer |

---

## 六、附录

### 参考资源

- [MCP 官方 SDK GitHub](https://github.com/modelcontextprotocol/typescript-sdk)
- [MCP 协议规范](https://modelcontextprotocol.io)
- [MCP Inspector 调试工具](https://github.com/modelcontextprotocol/inspector)

---

## 版本变更记录

- 2026-01-25：补充状态/适用范围/维护人元信息，整理文档层级与索引结构。
