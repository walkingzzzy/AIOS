# AIOS 协议开放化与完善方案

**版本**: 1.0.0  
**更新日期**: 2026-01-07  
**状态**: 深度研究提案  
**文档类型**: 💡 改进提案（已部分采纳）

> [!IMPORTANT]
> 本文档是 AIOS 协议开放化的改进提案。其中的多语言 SDK 设计、多传输支持等建议已被采纳到正式规范中。
> 正式的 AIOS 协议规范请参见 [protocol/](../protocol/) 目录。

> [!WARNING]
> **API 命名迁移说明**：本文档早期版本使用旧版 API 命名；为与最新战略/规范对齐，本文示例已更新为新命名，旧命名仅保留在对照表中：
> | 旧 API | 新 API |
> |--------|--------|
> | `aios/tool.invoke` | `aios/capability.invoke` |
> | `aios/tool.list` | `aios/capability.list` |
> | `aios/discovery.*` | `aios/registry.*` |

---

## 执行摘要

基于对MCP协议的深度网络搜索研究，本文档提出AIOS协议的开放化改进方案。核心理念：**AIOS不应限制技术方案，而应成为开放的、语言无关的AI控制协议**，同时保持其在权限、安全、系统控制方面的独特优势。

---

## 一、MCP协议技术实现深度分析

### 1.1 MCP的技术栈多样性

MCP协议的成功关键之一是**不限制技术方案**：

| 语言 | SDK | 成熟度 | 特点 |
|------|-----|--------|------|
| TypeScript | @modelcontextprotocol/sdk | ⭐⭐⭐⭐⭐ | 官方首选 |
| Python | mcp / FastMCP | ⭐⭐⭐⭐⭐ | 装饰器风格 |
| Go | mcp-go | ⭐⭐⭐⭐ | 高性能 |
| Java | mcp-java (Spring) | ⭐⭐⭐⭐ | 企业级 |
| Kotlin | mcp-kotlin | ⭐⭐⭐ | JVM生态 |
| C# | mcp-dotnet | ⭐⭐⭐ | .NET生态 |
| Rust | mcp-rust | ⭐⭐⭐ | 系统级 |
| Ruby/PHP | 社区SDK | ⭐⭐ | 新兴 |

### 1.2 MCP传输方式

MCP支持多种传输方式，适应不同场景：

```
┌─────────────────────────────────────────────────────────────────┐
│                    MCP 传输层架构                                │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  │
│  │     stdio       │  │ Streamable HTTP │  │   SSE (旧)      │  │
│  │   本地进程通信   │  │   远程HTTP通信   │  │  服务端推送     │  │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘  │
│         │                    │                    │             │
│         ▼                    ▼                    ▼             │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              JSON-RPC 2.0 消息层                         │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

| 传输方式 | 位置 | 连接数 | 延迟 | 适用场景 |
|---------|------|--------|------|---------|
| **stdio** | 本地 | 1:1 | 极低 | 本地工具、CLI集成 |
| **Streamable HTTP** | 远程 | 多:1 | 中等 | 云服务、远程API |
| **SSE** | 远程 | 多:1 | 中等 | 旧版兼容 |

### 1.3 MCP远程部署方案

MCP服务器可以部署在多种云平台，**无需本地安装**：

| 平台 | 特点 | 冷启动 | 成本模型 |
|------|------|--------|---------|
| **Cloudflare Workers** | 全球边缘、一键部署 | <50ms | 按请求计费 |
| **AWS Lambda** | 深度AWS集成 | 100-500ms | 按调用计费 |
| **Azure Container Apps** | 企业级、AD集成 | 中等 | 按资源计费 |
| **Google Cloud Run** | 自动扩缩容 | 中等 | 按请求计费 |
| **自托管Docker** | 完全控制 | 无 | 固定成本 |

### 1.4 MCP桥接工具

关键发现：**mcp-remote** 和 **mcp-proxy** 工具可以桥接本地和远程：

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   MCP Client    │◄───►│   mcp-proxy     │◄───►│  Remote MCP     │
│   (本地)        │     │   (桥接器)       │     │  Server         │
└─────────────────┘     └─────────────────┘     └─────────────────┘
        │                       │                       │
        │ stdio/JSON-RPC        │ HTTP/SSE              │
```

这意味着：
- 本地客户端可以访问远程服务器
- 远程客户端可以访问本地服务器
- 传输协议可以自动转换

### 1.5 OpenAPI自动转换

MCP生态已有成熟的OpenAPI到MCP转换工具：

| 工具 | 语言 | 特点 |
|------|------|------|
| **openapi-mcp** | Rust | 高性能、CLI工具 |
| **FastMCP OpenAPI** | Python | 自动生成MCP服务器 |
| **openapi-to-mcpserver** | Go | Higress集成 |
| **Stainless** | 商业 | 企业级自动生成 |
| **Speakeasy** | 商业 | SDK+MCP生成 |

**关键洞察**：现有API可以**零代码**转换为MCP工具！

---

## 二、MCP当前痛点分析

### 2.1 运行时依赖问题

**问题**：用户需要安装npx/uvx，配置复杂

```json
// 典型MCP配置 - 需要用户理解命令行
{
  "mcpServers": {
    "filesystem": {
      "command": "uvx",
      "args": ["mcp-server-filesystem", "--root", "/home/user"]
    }
  }
}
```

**影响**：
- 非技术用户难以使用
- 环境配置容易出错
- 版本冲突问题

### 2.2 注册表碎片化

当前MCP服务器分散在多个注册表：

| 注册表 | 服务器数 | 特点 |
|--------|---------|------|
| mcp.so | 17,000+ | 社区驱动 |
| Smithery | 4,900+ | CLI工具好 |
| Glama | 3,000+ | 托管支持 |
| MCPServers.org | 3,500+ | 表单提交 |
| Docker Hub | 增长中 | 容器化 |

**问题**：
- 发现困难
- 信任度低
- 质量参差不齐

### 2.3 上下文窗口膨胀

**问题**：每个MCP服务器的工具定义消耗LLM上下文

**Anthropic官方解决方案**（2025年发布）：
- 动态工具发现：只加载需要的工具
- 文件系统探索：Agent自己发现工具
- Token节省：从150,000降到2,000（98.7%节省）

### 2.4 安全认证不足

**问题**：OAuth 2.1规范2025年6月才添加

**当前状态**：
- 本地服务器无认证
- 远程认证实现不一致
- 企业级部署困难

### 2.5 开发者体验问题

**社区反馈的痛点**：
- 文档不完善
- 调试困难（stdio脆弱）
- 错误处理不标准
- 工具版本管理缺失

---

## 三、AIOS协议开放化设计

### 3.1 核心理念转变

**从**：限制技术方案的封闭系统
**到**：开放的、语言无关的AI控制协议

```
┌─────────────────────────────────────────────────────────────────┐
│                    AIOS 开放协议架构                             │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              协议规范层 (语言无关)                        │   │
│  │              JSON-RPC 2.0 + AIOS扩展                     │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              │                                  │
│  ┌───────────┬───────────┬───────────┬───────────┬──────────┐  │
│  │ Python    │ TypeScript│ Go        │ Rust      │ 其他     │  │
│  │ SDK       │ SDK       │ SDK       │ SDK       │ SDK      │  │
│  └───────────┴───────────┴───────────┴───────────┴──────────┘  │
│                              │                                  │
│  ┌───────────┬───────────┬───────────┬───────────┬──────────┐  │
│  │ stdio     │ Unix Sock │ HTTP      │ WebSocket │ gRPC     │  │
│  │ 本地      │ 本地高性能│ 远程      │ 双向实时  │ 高性能   │  │
│  └───────────┴───────────┴───────────┴───────────┴──────────┘  │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 协议层设计

AIOS协议基于JSON-RPC 2.0，与MCP兼容，但增加AIOS特有扩展：

```json
// AIOS请求格式
{
  "jsonrpc": "2.0",
  "id": "req-001",
  "method": "aios/capability.invoke",
  "params": {
    "capability_id": "app.browser.open_url",
    "arguments": { "url": "https://example.com" },
    
    // AIOS扩展字段
    "aios": {
      "preferred_adapter_id": "org.aios.browser.chrome",
      "permission_token": "tok_xxx",      // 权限令牌
      "user_confirmed": true,              // 用户已确认
      "sandbox_level": "L2",               // 沙箱级别
      "audit_context": { "session": "..." } // 审计上下文
    }
  }
}
```

### 3.3 多语言SDK设计

#### Python SDK (FastMCP风格)

```python
from aios import AIOSAdapter, capability

@AIOSAdapter(
    id="org.mycompany.myapp",
    name="我的应用适配器",
    version="1.0.0"
)
class MyAppAdapter:
    
    @capability(
        id="do_something",
        name="执行操作",
        risk_level="medium",
        description="执行某个操作"
    )
    async def do_something(self, param1: str, param2: int) -> dict:
        """执行操作的具体实现"""
        result = await self._internal_logic(param1, param2)
        return {"success": True, "data": result}

# 启动适配器
if __name__ == "__main__":
    adapter = MyAppAdapter()
    adapter.run(transport="http", port=8080)  # 或 stdio, unix_socket
```

#### TypeScript SDK

```typescript
import { AIOSAdapter, capability } from '@aios/sdk';

const adapter = new AIOSAdapter({
  id: 'org.mycompany.myapp',
  name: '我的应用适配器',
  version: '1.0.0'
});

adapter.addCapability({
  id: 'do_something',
  name: '执行操作',
  riskLevel: 'medium',
  handler: async (params) => {
    const result = await internalLogic(params);
    return { success: true, data: result };
  }
});

// 启动适配器
adapter.run({ transport: 'http', port: 8080 });
```

#### Go SDK

```go
package main

import (
    "github.com/aios-protocol/aios-go"
)

func main() {
    adapter := aios.NewAdapter(aios.Config{
        ID:      "org.mycompany.myapp",
        Name:    "我的应用适配器",
        Version: "1.0.0",
    })

    adapter.AddCapability(aios.Capability{
        ID:        "do_something",
        Name:      "执行操作",
        RiskLevel: aios.RiskMedium,
        Handler: func(ctx context.Context, params map[string]any) (any, error) {
            // 实现逻辑
            return map[string]any{"success": true}, nil
        },
    })

    adapter.Run(aios.TransportHTTP, ":8080")
}
```

### 3.4 多传输支持

| 传输方式 | 配置示例 | 适用场景 |
|---------|---------|---------|
| stdio | `adapter.run(transport="stdio")` | 本地开发、CLI集成 |
| Unix Socket | `adapter.run(transport="unix", path="/tmp/aios.sock")` | 本地高性能 |
| HTTP | `adapter.run(transport="http", port=8080)` | 远程访问 |
| WebSocket | `adapter.run(transport="ws", port=8080)` | 双向实时 |

### 3.5 远程部署支持

#### Cloudflare Workers部署

```typescript
// worker.ts
import { AIOSAdapter } from '@aios/sdk-cloudflare';

export default {
  async fetch(request: Request, env: Env) {
    const adapter = new AIOSAdapter({
      id: 'org.mycompany.cloud-tool',
      // ... 配置
    });
    return adapter.handleRequest(request);
  }
};
```

#### Docker部署

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY . .
RUN pip install aios-sdk
EXPOSE 8080
CMD ["python", "-m", "aios", "run", "--transport", "http", "--port", "8080"]
```

#### Serverless配置

```yaml
# serverless.yml
service: my-aios-adapter
provider:
  name: aws
  runtime: python3.11
functions:
  adapter:
    handler: handler.main
    events:
      - http:
          path: /aios
          method: ANY
```

---

## 四、工具集成简化方案

### 4.1 OpenAPI自动转换

AIOS应支持从OpenAPI规范自动生成适配器：

```bash
# 从OpenAPI生成AIOS适配器
aios-cli generate --from openapi --spec ./api.yaml --output ./adapter

# 生成的结构
adapter/
├── tool.aios.yaml      # AIOS适配器配置
├── adapter.py          # Python实现
├── capabilities/       # 能力定义
│   ├── get_users.py
│   └── create_order.py
└── README.md
```

**自动映射规则**：

| OpenAPI | AIOS |
|---------|------|
| GET endpoint | 只读能力 (risk: low) |
| POST endpoint | 写入能力 (risk: medium) |
| DELETE endpoint | 删除能力 (risk: high) |
| operationId | capability_id |
| summary | capability name |
| description | capability description |

### 4.2 MCP服务器桥接

AIOS可以直接调用任何MCP服务器：

```yaml
# aios-config.yaml
bridges:
  mcp:
    servers:
      - id: mcp.filesystem
        command: uvx
        args: ["mcp-server-filesystem", "--root", "/home/user"]
        permission_mapping:
          read_file: low
          write_file: high
          delete_file: critical
          
      - id: mcp.github
        url: "https://mcp.github.example.com"
        auth:
          type: bearer
          token: "${GITHUB_TOKEN}"
```

### 4.3 CLI工具自动包装

```yaml
# 将CLI工具包装为AIOS能力
cli_wrappers:
  - id: org.aios.tools.ffmpeg
    name: FFmpeg视频处理
    command: ffmpeg
    capabilities:
      - id: convert_video
        name: 转换视频格式
        risk_level: medium
        args_template: "-i {input} -c:v {codec} {output}"
        parameters:
          input: { type: string, description: "输入文件路径" }
          codec: { type: string, enum: ["h264", "h265", "vp9"] }
          output: { type: string, description: "输出文件路径" }
```

### 4.4 D-Bus服务自动发现

```python
# AIOS自动发现D-Bus服务并生成能力
from aios.discovery import DBusDiscovery

discovery = DBusDiscovery()
services = discovery.scan()

# 自动生成的能力
# org.freedesktop.NetworkManager.Enable -> aios.network.enable
# org.bluez.Adapter1.StartDiscovery -> aios.bluetooth.start_discovery
```

---

## 五、AIOS独特价值保留

### 5.1 5级权限模型

这是AIOS相对于MCP的核心优势，必须保留：

```
┌─────────────────────────────────────────────────────────────────┐
│                    AIOS 5级权限模型                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Level 0: public    │ 无需确认 │ 读取时间、版本信息              │
│  Level 1: low       │ 首次确认 │ 读取文件、查询数据              │
│  Level 2: medium    │ 可配置   │ 修改设置、网络请求              │
│  Level 3: high      │ 每次确认 │ 删除文件、安装软件              │
│  Level 4: critical  │ 二次确认 │ 系统关机、格式化磁盘            │
│                                                                 │
│  MCP/A2A 均无此能力！                                           │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 5.2 系统级控制能力

AIOS独有的系统控制能力：

| 控制层 | 技术 | MCP支持 | AIOS支持 |
|--------|------|---------|---------|
| 系统设置 | D-Bus/gsettings | ❌ | ✅ |
| 电源管理 | UPower | ❌ | ✅ |
| 网络控制 | NetworkManager | ❌ | ✅ |
| 蓝牙控制 | BlueZ | ❌ | ✅ |
| 音频控制 | PulseAudio/PipeWire | ❌ | ✅ |
| 显示控制 | Mutter/KWin | ❌ | ✅ |

### 5.3 多级沙箱隔离

```
┌─────────────────────────────────────────────────────────────────┐
│                    AIOS 沙箱架构                                 │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  L0: 无隔离      │ 直接执行     │ 信任的系统适配器              │
│  L1: 进程隔离    │ 独立进程     │ 一般适配器                    │
│  L2: WASM隔离    │ Wasmtime     │ 外部工具、MCP桥接             │
│  L3: 容器隔离    │ Docker/Podman│ 不信任的工具                  │
│  L4: VM隔离      │ Firecracker  │ 高风险操作                    │
│                                                                 │
│  MCP/A2A 均无沙箱支持！                                         │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 5.4 用户确认机制

```json
// 敏感操作需要用户确认
{
  "method": "aios/permission.request",
  "params": {
    "capability_id": "system.files.delete_file",
    "permissions": [
      {
        "level": "critical",
        "scope": "/home/user/important.doc",
        "duration": "session",
        "reason": "AI请求删除此文件"
      }
    ]
  }
}

// 用户响应
{
  "result": {
    "granted": true,
    "tokens": [
      {
        "token_id": "cap-token-xxx",
        "permission_id": "aios.permission.filesystem.home.delete",
        "scope": "/home/user/important.doc",
        "expires_at": "2026-01-05T12:00:00Z"
      }
    ]
  }
}
```

---

## 六、与MCP生态的关系

### 6.1 定位：MCP之上的控制层

```
┌─────────────────────────────────────────────────────────────────┐
│                     用户自然语言请求                             │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                    AIOS Protocol Layer                          │
│                   (AI控制层 - 权限/安全/审计)                    │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  │
│  │  原生系统控制    │  │  MCP 桥接       │  │  A2A 桥接       │  │
│  │  (D-Bus/CLI)    │  │  (外部工具)     │  │  (远程Agent)    │  │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘  │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 6.2 AIOS为MCP添加的能力

| 能力 | MCP原生 | AIOS增强 |
|------|---------|---------|
| 权限控制 | ❌ | ✅ 5级权限 |
| 用户确认 | ❌ | ✅ 敏感操作确认 |
| 沙箱隔离 | ❌ | ✅ 多级沙箱 |
| 审计日志 | 基础 | ✅ 完整追踪 |
| 统一入口 | ❌ | ✅ 单一API |

### 6.3 兼容性策略

1. **协议兼容**：AIOS使用JSON-RPC 2.0，与MCP消息格式兼容
2. **工具兼容**：任何MCP服务器可通过桥接在AIOS中使用
3. **SDK兼容**：AIOS SDK可以导出为MCP服务器
4. **渐进迁移**：现有MCP工具可逐步迁移到AIOS

---

## 七、实施路线图

### Phase 1: 协议开放化 (2周)

| 任务 | 优先级 | 说明 |
|------|--------|------|
| 协议规范文档 | P0 | 语言无关的JSON-RPC规范 |
| 多传输支持 | P0 | stdio、HTTP、Unix Socket |
| Python SDK | P0 | 首个官方SDK |

### Phase 2: 生态集成 (4周)

| 任务 | 优先级 | 说明 |
|------|--------|------|
| TypeScript SDK | P1 | 前端/Node.js支持 |
| MCP桥接器 | P1 | 调用任何MCP服务器 |
| OpenAPI转换 | P1 | 现有API一键转换 |

### Phase 3: 远程部署 (4周)

| 任务 | 优先级 | 说明 |
|------|--------|------|
| Cloudflare Workers | P1 | Serverless部署 |
| Docker镜像 | P1 | 容器化部署 |
| 远程代理 | P2 | aios-proxy工具 |

### Phase 4: 开发者工具 (4周)

| 任务 | 优先级 | 说明 |
|------|--------|------|
| CLI工具 | P1 | aios-cli |
| Inspector | P2 | 调试UI |
| 适配器市场 | P2 | 发现和分发 |

---

## 八、总结

### 8.1 核心改进

| 改进点 | 当前状态 | 目标状态 |
|--------|---------|---------|
| 技术栈 | 仅Rust | 多语言SDK |
| 传输方式 | Unix Socket | stdio/HTTP/WS |
| 部署方式 | 本地 | 本地+远程+Serverless |
| 工具集成 | 手动开发 | OpenAPI自动转换 |
| MCP兼容 | 无 | 完全兼容 |

### 8.2 保留的独特优势

| 优势 | 说明 |
|------|------|
| 5级权限 | MCP/A2A均无 |
| 系统控制 | D-Bus/CLI集成 |
| 多级沙箱 | WASM/容器/VM |
| 用户确认 | 人在回路 |
| 审计追踪 | 完整日志 |

### 8.3 预期效果

| 指标 | 当前 | 目标 |
|------|------|------|
| 支持语言 | 1 (Rust) | 5+ |
| 部署方式 | 1 (本地) | 4+ |
| 工具集成时间 | 数天 | 数分钟 |
| MCP兼容性 | 0% | 100% |

---

**文档版本**: 1.0.0  
**最后更新**: 2026-01-07  
**维护者**: AIOS Protocol Team
