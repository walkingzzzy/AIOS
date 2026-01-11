# AIOS 适配器开发指南

**版本**: 2.0.0  
**更新日期**: 2026-01-09  
**状态**: 战略规划阶段

---

## 概述

本文档指导开发者如何为软件创建 AIOS 适配器。AIOS 协议采用**开放设计**，不限制技术方案，支持多种编程语言、传输方式和部署模式。

### 核心理念

- **语言无关**：Python、TypeScript、Go、Rust 等均可
- **传输灵活**：stdio、HTTP、WebSocket、Unix Socket
- **部署多样**：本地、云端、Serverless、容器化

---

## 1. 开发准备

### 环境要求

选择您熟悉的技术栈：

| 语言 | 版本要求 | SDK |
|------|---------|-----|
| Python | 3.9+ | `aios-sdk` |
| TypeScript/Node.js | 18+ | `@aios/sdk` |
| Go | 1.21+ | `github.com/aios-protocol/aios-go` |
| Rust | 1.70+ | `aios-sdk` (crate) |

### 安装 SDK

```bash
# Python SDK
pip install aios-sdk

# TypeScript/Node.js SDK
npm install @aios/sdk

# Go SDK
go get github.com/aios-protocol/aios-go

# Rust SDK
cargo add aios-sdk
```

---

## 2. 创建适配器步骤

### 步骤概览

1. 创建 `tool.aios.yaml` 描述文件
2. 实现适配器代码
3. 本地测试
4. 打包发布

---

## 3. 创建 tool.aios.yaml

### 最小示例

```yaml
aios_version: "0.3"

tool:
  id: "com.example.mytool"
  name: "我的工具"
  version: "1.0.0"
  type: "application"

capabilities:
  - id: "com.example.mytool.hello"
    name: "打招呼"
    description: "返回问候语"
    input:
      type: object
      properties:
        name:
          type: string
          description: "姓名"
      required: ["name"]
    output:
      type: object
      properties:
        message:
          type: string
    permissions: []

adapter:
  type: "python"
  config:
    module: "mytool_adapter"
    class: "MyToolAdapter"
```

### 完整示例

参见 [工具描述规范](../protocol/04-ToolSchema.md)

---

## 4. 实现适配器

### Python 适配器（推荐：装饰器风格）

```python
# mytool_adapter.py
from aios import AIOSAdapter, capability

@AIOSAdapter(
    id="com.example.mytool",
    name="我的工具",
    version="1.0.0"
)
class MyToolAdapter:
    """我的工具适配器"""
    
    @capability(
        id="com.example.mytool.hello",
        name="打招呼",
        risk_level="public",
        description="返回问候语"
    )
    async def do_hello(self, name: str) -> dict:
        """
        打招呼能力
        
        Args:
            name: 姓名
            
        Returns:
            包含问候语的字典
        """
        return {
            "success": True,
            "message": f"你好，{name}！"
        }
    
    async def on_activate(self):
        """适配器激活时调用"""
        pass
    
    async def on_deactivate(self):
        """适配器停用时调用"""
        pass

# 启动适配器（支持多种传输方式）
if __name__ == "__main__":
    adapter = MyToolAdapter()
    adapter.run(transport="stdio")  # 或 "http", "unix_socket", "websocket"
```

### TypeScript 适配器

```typescript
// mytool-adapter.ts
import { AIOSAdapter, capability } from '@aios/sdk';

const adapter = new AIOSAdapter({
  id: 'com.example.mytool',
  name: '我的工具',
  version: '1.0.0'
});

adapter.addCapability({
  id: 'com.example.mytool.hello',
  name: '打招呼',
  riskLevel: 'public',
  description: '返回问候语',
  inputSchema: {
    type: 'object',
    properties: {
      name: { type: 'string', description: '姓名' }
    },
    required: ['name']
  },
  handler: async ({ name }) => {
    return {
      success: true,
      message: `你好，${name}！`
    };
  }
});

// 启动适配器
adapter.run({ transport: 'http', port: 8080 });
```

### Go 适配器

```go
// mytool_adapter.go
package main

import (
    "context"
    "github.com/aios-protocol/aios-go"
)

func main() {
    adapter := aios.NewAdapter(aios.Config{
        ID:      "com.example.mytool",
        Name:    "我的工具",
        Version: "1.0.0",
    })

    adapter.AddCapability(aios.Capability{
        ID:          "com.example.mytool.hello",
        Name:        "打招呼",
        RiskLevel:   aios.RiskPublic,
        Description: "返回问候语",
        Handler: func(ctx context.Context, params map[string]any) (any, error) {
            name := params["name"].(string)
            return map[string]any{
                "success": true,
                "message": "你好，" + name + "！",
            }, nil
        },
    })

    // 启动适配器
    adapter.Run(aios.TransportHTTP, ":8080")
}
```

### Rust 适配器

```rust
// src/main.rs
use aios_sdk::{Adapter, Capability, RiskLevel, Transport};
use serde_json::{json, Value};

#[tokio::main]
async fn main() {
    let mut adapter = Adapter::new(
        "com.example.mytool",
        "我的工具",
        "1.0.0"
    );

    adapter.add_capability(Capability {
        id: "com.example.mytool.hello".to_string(),
        name: "打招呼".to_string(),
        risk_level: RiskLevel::Public,
        description: "返回问候语".to_string(),
        handler: Box::new(|params| {
            let name = params["name"].as_str().unwrap_or("世界");
            Ok(json!({
                "success": true,
                "message": format!("你好，{}！", name)
            }))
        }),
    });

    // 启动适配器
    adapter.run(Transport::Http { port: 8080 }).await;
}
```

### Python 适配器（传统类风格）

```python
# mytool_adapter.py
from aios_sdk import BaseAdapter, capability

class MyToolAdapter(BaseAdapter):
    """我的工具适配器（传统风格）"""
    
    def __init__(self):
        super().__init__()
        # 初始化代码
    
    @capability("com.example.mytool.hello")
    async def do_hello(self, name: str) -> dict:
        return {
            "success": True,
            "message": f"你好，{name}！"
        }
    
    async def on_activate(self):
        """适配器激活时调用"""
        pass
    
    async def on_deactivate(self):
        """适配器停用时调用"""
        pass
```

### D-Bus 适配器

```python
from aios_sdk import BaseAdapter, capability
from gi.repository import Gio

class DesktopAdapter(BaseAdapter):
    """桌面设置适配器"""
    
    def __init__(self):
        super().__init__()
        self.settings = Gio.Settings.new("org.gnome.desktop.background")
    
    @capability("system.desktop.set_wallpaper")
    async def do_set_wallpaper(self, path: str, mode: str = "zoom") -> dict:
        """设置壁纸"""
        previous = self.settings.get_string("picture-uri")
        
        # 设置新壁纸
        uri = f"file://{path}"
        self.settings.set_string("picture-uri", uri)
        self.settings.set_string("picture-uri-dark", uri)
        self.settings.set_string("picture-options", mode)
        
        return {
            "success": True,
            "message": "壁纸已更换",
            "data": {
                "previous_path": previous,
                "current_path": path
            }
        }
    
    @capability("system.desktop.get_wallpaper")
    async def do_get_wallpaper(self) -> dict:
        """获取当前壁纸"""
        uri = self.settings.get_string("picture-uri")
        mode = self.settings.get_string("picture-options")
        
        # 移除 file:// 前缀
        path = uri.replace("file://", "")
        
        return {
            "path": path,
            "mode": mode
        }
```

### CLI 适配器

```python
from aios_sdk import BaseAdapter, capability
import subprocess

class CLIToolAdapter(BaseAdapter):
    """CLI 工具适配器"""
    
    @capability("com.example.mytool.run_command")
    async def do_run_command(self, args: list) -> dict:
        """执行命令"""
        result = subprocess.run(
            ["/usr/bin/mytool"] + args,
            capture_output=True,
            text=True
        )
        
        return {
            "success": result.returncode == 0,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode
        }
```

### 浏览器适配器 (DevTools Protocol)

```python
from aios_sdk import BaseAdapter, capability
import aiohttp

class ChromeAdapter(BaseAdapter):
    """Chrome 浏览器适配器"""
    
    def __init__(self):
        super().__init__()
        self.ws = None
        self.msg_id = 0
    
    async def on_activate(self):
        """连接到 Chrome DevTools"""
        async with aiohttp.ClientSession() as session:
            async with session.get("http://localhost:9222/json") as resp:
                tabs = await resp.json()
                self.ws_url = tabs[0]["webSocketDebuggerUrl"]
    
    async def send_command(self, method: str, params: dict = None):
        """发送 DevTools 命令"""
        self.msg_id += 1
        message = {
            "id": self.msg_id,
            "method": method,
            "params": params or {}
        }
        # 发送 WebSocket 消息
        # ...
    
    @capability("app.browser.open_url")
    async def do_open_url(self, url: str) -> dict:
        """打开网址"""
        await self.send_command("Page.navigate", {"url": url})
        return {"success": True, "message": f"已打开 {url}"}
    
    @capability("app.browser.screenshot")
    async def do_screenshot(self, path: str) -> dict:
        """截图"""
        result = await self.send_command("Page.captureScreenshot")
        # 保存图片...
        return {"success": True, "path": path}
```

---

## 5. 处理权限

### 声明权限

在 `tool.aios.yaml` 中声明：

```yaml
capabilities:
  - id: "system.files.write_file"
    permissions:
      - "aios.permission.filesystem.home.write"

permissions:
  - id: "aios.permission.filesystem.home.write"
    name: "写入主目录"
    description: "将结果保存到您的主目录"
    risk_level: "high"
```

### 检查权限

```python
from aios_sdk import BaseAdapter, capability, require_permission

class FileAdapter(BaseAdapter):
    
    @capability("system.files.write_file")
    @require_permission("aios.permission.filesystem.home.write")
    async def do_write_file(self, path: str, content: str) -> dict:
        """写入文件（需要权限）"""
        with open(path, "w") as f:
            f.write(content)
        return {"success": True}
```

---

## 6. 错误处理

### 标准错误

```python
from aios_sdk import BaseAdapter, capability, AIOSError

class MyAdapter(BaseAdapter):
    
    @capability("system.example.risky_action")
    async def do_risky_action(self) -> dict:
        try:
            # 执行操作
            result = await self.do_something()
            return {"success": True, "data": result}
        
        except FileNotFoundError as e:
            raise AIOSError(
                code=-32102,
                message="File not found",
                data={"path": str(e)}
            )
        
        except PermissionError as e:
            raise AIOSError(
                code=-32001,
                message="Permission denied",
                data={"reason": str(e)}
            )
        
        except Exception as e:
            raise AIOSError(
                code=-32603,
                message="Internal error",
                data={"error": str(e)}
            )
```

---

## 7. 流式响应

```python
from aios_sdk import BaseAdapter, capability, StreamResponse

class LongTaskAdapter(BaseAdapter):
    
    @capability("system.example.process_files")
    async def do_process_files(self, files: list) -> StreamResponse:
        """处理多个文件，支持流式响应"""
        
        async def generate():
            total = len(files)
            
            # 发送开始
            yield {"type": "start", "total": total}
            
            for i, file in enumerate(files):
                # 处理文件
                result = await self.process_file(file)
                
                # 发送进度
                yield {
                    "type": "progress",
                    "current": i + 1,
                    "total": total,
                    "file": file
                }
                
                # 发送结果块
                yield {
                    "type": "chunk",
                    "data": result
                }
            
            # 发送结束
            yield {"type": "end", "success": True}
        
        return StreamResponse(generate())
```

---

## 8. 传输方式与部署

### 8.1 传输方式选择

AIOS 支持多种传输方式，适应不同场景：

| 传输方式 | 适用场景 | 性能 | 配置复杂度 |
|---------|---------|------|-----------|
| **stdio** | 本地开发、CLI集成 | 极高 | 低 |
| **Unix Socket** | 本地高性能通信 | 极高 | 低 |
| **HTTP** | 远程访问、云部署 | 中等 | 中 |
| **WebSocket** | 双向实时通信 | 高 | 中 |

### 8.2 本地部署

```python
# stdio 模式（本地CLI集成）
adapter.run(transport="stdio")

# Unix Socket 模式（本地高性能）
adapter.run(transport="unix", path="/tmp/mytool.sock")

# HTTP 模式（本地网络访问）
adapter.run(transport="http", host="127.0.0.1", port=8080)
```

### 8.3 远程部署

#### Docker 部署

```dockerfile
# Dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY . .
RUN pip install aios-sdk
EXPOSE 8080
CMD ["python", "adapter.py", "--transport", "http", "--port", "8080"]
```

```bash
# 构建和运行
docker build -t my-aios-adapter .
docker run -p 8080:8080 my-aios-adapter
```

#### Cloudflare Workers 部署

```typescript
// worker.ts
import { AIOSAdapter } from '@aios/sdk-cloudflare';

export default {
  async fetch(request: Request, env: Env) {
    const adapter = new AIOSAdapter({
      id: 'com.example.cloud-tool',
      name: '云端工具',
      version: '1.0.0'
    });
    
    adapter.addCapability({
      id: 'process',
      name: '处理数据',
      riskLevel: 'low',
      handler: async (params) => {
        return { success: true, data: params };
      }
    });
    
    return adapter.handleRequest(request);
  }
};
```

#### AWS Lambda 部署

```python
# lambda_handler.py
from aios import AIOSAdapter, capability

adapter = AIOSAdapter(
    id="com.example.lambda-tool",
    name="Lambda工具",
    version="1.0.0"
)

@adapter.capability(id="process", risk_level="low")
async def process(data: dict) -> dict:
    return {"success": True, "processed": data}

def handler(event, context):
    return adapter.handle_lambda(event, context)
```

### 8.4 适配器配置文件

远程适配器可通过配置文件注册：

```yaml
# ~/.config/aios/adapters.yaml
adapters:
  # 本地适配器
  - id: com.example.local-tool
    transport: stdio
    command: python
    args: ["/path/to/adapter.py"]
    
  # 远程HTTP适配器
  - id: com.example.remote-tool
    transport: http
    url: "https://my-adapter.example.com/aios"
    auth:
      type: bearer
      token: "${ADAPTER_TOKEN}"
      
  # Docker适配器
  - id: com.example.docker-tool
    transport: http
    docker:
      image: "my-adapter:latest"
      port: 8080
```

---

## 9. OpenAPI 自动转换

### 9.1 从 OpenAPI 生成适配器

如果您已有 REST API，可以自动生成 AIOS 适配器：

```bash
# 从 OpenAPI 规范生成适配器
aios-cli generate --from openapi --spec ./api.yaml --output ./adapter

# 生成的目录结构
adapter/
├── tool.aios.yaml      # AIOS 配置
├── adapter.py          # Python 实现
├── capabilities/       # 能力定义
└── README.md
```

### 9.2 自动映射规则

| OpenAPI | AIOS |
|---------|------|
| GET endpoint | 只读能力 (risk: low) |
| POST endpoint | 写入能力 (risk: medium) |
| PUT endpoint | 更新能力 (risk: medium) |
| DELETE endpoint | 删除能力 (risk: high) |
| operationId | capability_id |
| summary | capability name |
| description | capability description |

### 9.3 示例：转换 Petstore API

```bash
# 下载 OpenAPI 规范
curl -o petstore.yaml https://petstore.swagger.io/v2/swagger.yaml

# 生成 AIOS 适配器
aios-cli generate --from openapi --spec petstore.yaml --output petstore-adapter

# 启动适配器
cd petstore-adapter
python adapter.py --transport http --port 8080
```

---

## 10. MCP 服务器桥接

### 10.1 调用现有 MCP 服务器

AIOS 可以桥接任何 MCP 服务器，无需修改：

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

### 10.2 桥接时的策略叠加

> **注意**：MCP 在认证授权方面持续演进。AIOS 桥接 MCP 服务器时可叠加本地策略：

```yaml
permission_mapping:
  # MCP工具名 -> AIOS权限级别
  read_file: low
  write_file: high
  delete_file: critical
  list_directory: low
  create_directory: medium
```

---

## 11. 本地测试

### 使用 CLI 测试

```bash
# 验证 tool.aios.yaml
aios-cli validate tool.aios.yaml

# 启动测试适配器（多种传输方式）
aios-cli adapter start ./mytool_adapter.py --transport stdio
aios-cli adapter start ./mytool_adapter.py --transport http --port 8080

# 调用能力
aios-cli invoke com.example.mytool.hello --arguments '{"name":"世界"}'

# 查看日志
aios-cli logs

# 测试远程适配器
aios-cli invoke --url http://localhost:8080 com.example.mytool.hello --arguments '{"name":"世界"}'
```

### 使用 Python 测试

```python
import asyncio
from mytool_adapter import MyToolAdapter

async def test():
    adapter = MyToolAdapter()
    await adapter.on_activate()
    
    result = await adapter.do_hello(name="世界")
    print(result)
    
    await adapter.on_deactivate()

asyncio.run(test())
```

---

## 12. 打包发布

### 目录结构

```
mytool-adapter/
├── tool.aios.yaml
├── adapter.py          # 或 adapter.ts, main.go, src/main.rs
├── requirements.txt    # 或 package.json, go.mod, Cargo.toml
├── Dockerfile          # 可选：容器化部署
├── README.md
└── tests/
    └── test_adapter.py
```

### 打包

```bash
aios-cli package ./mytool-adapter
```

### 发布到市场

```bash
aios-cli publish ./mytool-adapter.aios
```

---

## 13. 最佳实践

### 安全

- ✅ 只请求必要的权限
- ✅ 验证所有输入参数
- ✅ 不在日志中输出敏感信息
- ✅ 使用安全的错误处理

### 性能

- ✅ 使用异步 I/O
- ✅ 缓存重复查询
- ✅ 实现超时控制
- ✅ 避免阻塞操作

### 兼容性

- ✅ 检测目标软件是否存在
- ✅ 处理版本差异
- ✅ 提供降级方案
- ✅ 清晰的错误消息
- ✅ 支持多种传输方式

### 文档

- ✅ 完整的能力描述
- ✅ 丰富的 AI 示例
- ✅ 清晰的权限说明
- ✅ 更新日志
- ✅ 部署指南

---

## 14. 示例项目

| 项目 | 说明 | 语言 | 链接 |
|------|------|------|------|
| aios-adapter-template | 适配器模板 | Python | GitHub |
| aios-adapter-template-ts | TypeScript模板 | TypeScript | GitHub |
| aios-adapter-template-go | Go模板 | Go | GitHub |
| aios-adapter-chrome | Chrome 适配器 | Python | GitHub |
| aios-adapter-blender | Blender 适配器 | Python | GitHub |
| aios-openapi-example | OpenAPI转换示例 | Python | GitHub |

---

## 15. 语言选择指南

| 场景 | 推荐语言 | 理由 |
|------|---------|------|
| 快速原型 | Python | 开发速度快，AI生态丰富 |
| 前端集成 | TypeScript | 与Web技术栈一致 |
| 高性能需求 | Go/Rust | 编译型语言，性能优异 |
| 系统级控制 | Rust | 内存安全，系统编程 |
| 企业应用 | Java/Kotlin | JVM生态，企业级支持 |

---

**文档版本**: 2.0.0  
**最后更新**: 2026-01-09  
**维护者**: AIOS Protocol Team
