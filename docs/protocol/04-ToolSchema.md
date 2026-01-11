# AIOS Protocol 工具描述规范

**版本**: 2.0.0  
**更新日期**: 2026-01-09  
**状态**: 战略规划阶段

---

## 概述

本文档定义 `tool.aios.yaml` 文件格式，这是 AIOS 适配器的核心描述文件。

> **注意**: `tool.aios.yaml` 是本地适配器的描述格式。对于远程适配器，请参考 [Adapter Card 规范](AIOS-Protocol-Discovery.md)。

---

## 1. 文件概述

### 文件名

```
tool.aios.yaml
```

### 文件位置

| 软件类型 | 位置 |
|---------|------|
| deb 包 | `/usr/share/aios/tools/<tool-id>.yaml` |
| Snap | `$SNAP/meta/aios/tool.aios.yaml` |
| Flatpak | `/app/share/aios/tool.aios.yaml` |
| 用户安装 | `~/.local/share/aios/tools/<tool-id>.yaml` |

---

## 2. 完整结构

```yaml
# AIOS 协议版本
aios_version: "0.3"

# 工具元数据
tool:
  id: "org.example.mytool"
  name: "我的工具"
  version: "1.0.0"
  author: "Example Inc."
  description: "工具的详细描述"
  license: "MIT"
  homepage: "https://example.org/mytool"
  
  # 工具类型
  type: "application"  # system | application | browser | professional | custom
  
  # 分类标签
  categories:
    - "Productivity"
    - "Office"
  
  # 图标
  icon: "mytool"  # 图标名称或路径

  # 系统提示词 (System Prompt) - 定义 Agent 的行为性格
  system_prompt: |
    你是一个专业的办公助手。在处理文档时，请优先使用 Markdown 格式。
    如果遇到不确定的操作，请先询问用户。
  
  # 支持的平台
  platforms:
    - os: "linux"
      distributions: ["ubuntu", "debian", "fedora"]
      min_version: "22.04"
    - os: "windows"
      min_version: "10"

# 能力声明
capabilities:
  - id: "system.example.action_name"
    name: "操作名称"
    description: "操作的详细描述"
    
    # 输入参数 (JSON Schema)
    input:
      type: object
      properties:
        param1:
          type: string
          description: "参数1描述"
        param2:
          type: integer
          minimum: 0
          maximum: 100
          default: 50
      required: ["param1"]
    
    # 输出格式 (JSON Schema)
    output:
      type: object
      properties:
        success:
          type: boolean
        message:
          type: string
        data:
          type: object
    
    # 所需权限
    permissions:
      - "aios.permission.category.resource.action"
    
    # AI 学习示例
    examples:
      - user_intent: "用户可能说的话"
        call:
          capability_id: "system.example.action_name"
          arguments:
            param1: "示例值"
    
    # 能力选项
    options:
      async: false           # 是否异步执行
      streaming: false       # 是否支持流式输出
      idempotent: true       # 是否幂等
      timeout_ms: 30000      # 默认超时

# 权限声明
permissions:
  - id: "aios.permission.category.resource.action"
    name: "权限显示名称"
    description: "向用户解释为什么需要此权限"
    risk_level: "low"  # public | low | medium | high | critical

# 依赖声明
dependencies:
  # 系统依赖
  system:
    - name: "gsettings"
      required: true
    - name: "dconf"
      required: false
  
  # 运行时依赖
  runtime:
    - name: "python3"
      version: ">=3.9"
  
  # 其他工具依赖
  tools:
    - id: "org.aios.system.dbus"
      version: ">=1.0"

# 适配器配置
adapter:
  # 适配器类型
  type: "dbus"  # dbus | cli | api | python | native | wasm
  
  # 类型特定配置
  config:
    # D-Bus 配置
    service: "org.freedesktop.portal.Desktop"
    interface: "org.freedesktop.portal.Settings"
    
    # CLI 配置
    # command: "/usr/bin/mytool"
    # args_template: "--action {action} --param {param}"
    
    # Python 配置
    # module: "mytool.adapter"
    # class: "MyToolAdapter"

# 可视化配置 (可选)
visualization:
  modes:
    - type: "overlay"
      supported: true
    - type: "step_panel"
      supported: true
  
  pre_action_notify:
    enabled: true
    delay_ms: 500
```

---

## 3. 字段详解

### 3.1 aios_version

AIOS 协议版本，必需字段。

```yaml
aios_version: "0.3"
```

| 版本 | 说明 |
|------|------|
| `"0.2"` | 初始版本 |
| `"0.3"` | 当前版本，添加高级特性 |

---

### 3.2 tool (工具元数据)

#### id (必需)

工具唯一标识符，使用反向域名格式。

```yaml
tool:
  id: "org.aios.browser.chrome"
```

**格式**: `<domain>.<category>.<name>`

**示例**:
- `org.aios.system.power` - 系统电源控制
- `org.mozilla.firefox` - Firefox 浏览器
- `com.blender.aios` - Blender 适配器

#### type (必需)

工具类型，影响 AIOS 如何处理此工具。

| 类型 | 说明 | 典型沙箱 |
|------|------|---------|
| `system` | 系统功能 | L0 或 L1 |
| `application` | 桌面应用 | L1 或 L2 |
| `browser` | 浏览器 | L2 |
| `professional` | 专业软件 | L1 或 L2 |
| `custom` | 自定义 | L2 |

#### platforms (可选)

声明支持的平台。

```yaml
platforms:
  - os: "linux"
    distributions: ["ubuntu", "debian"]
    min_version: "22.04"
    desktop_environments: ["gnome", "kde"]
  - os: "windows"
    min_version: "10"
  - os: "macos"
    min_version: "12.0"
```

---

### 3.3 capabilities (能力)

能力是工具对外暴露的具体功能。

#### input (输入参数)

使用 JSON Schema 定义输入参数。

```yaml
input:
  type: object
  properties:
    path:
      type: string
      description: "文件路径"
      pattern: "^/.*"
    mode:
      type: string
      enum: ["fill", "fit", "stretch", "tile", "center"]
      default: "fill"
    opacity:
      type: number
      minimum: 0
      maximum: 1
      default: 1.0
  required: ["path"]
```

**支持的类型**:
- `string` - 字符串
- `number` / `integer` - 数值
- `boolean` - 布尔值
- `array` - 数组
- `object` - 对象

**常用验证**:
- `enum` - 枚举值
- `pattern` - 正则表达式
- `minimum` / `maximum` - 数值范围
- `minLength` / `maxLength` - 字符串长度
- `default` - 默认值

#### output (输出格式)

定义能力的输出格式。

```yaml
output:
  type: object
  properties:
    success:
      type: boolean
    message:
      type: string
    data:
      type: object
      properties:
        previous_value:
          type: string
        current_value:
          type: string
```

#### permissions (所需权限)

声明此能力需要的权限。

```yaml
permissions:
  - "aios.permission.filesystem.home.read"
  - "aios.permission.desktop.wallpaper.write"
```

#### examples (AI 学习示例)

帮助 AI 理解如何使用此能力。

```yaml
examples:
  - user_intent: "帮我换个蓝色的壁纸"
    call:
      capability_id: "system.desktop.set_wallpaper"
      arguments:
        path: "/usr/share/backgrounds/blue.jpg"
        mode: "fill"
  
  - user_intent: "把这张图片设为桌面背景"
    call:
      capability_id: "system.desktop.set_wallpaper"
      arguments:
        path: "${context.mentioned_file}"
```

**上下文变量**:
- `${context.mentioned_file}` - 用户提到的文件
- `${context.current_directory}` - 当前目录
- `${context.selection}` - 当前选中内容

---

### 3.4 permissions (权限声明)

声明工具使用的权限及其原因。

```yaml
permissions:
  - id: "aios.permission.filesystem.home.read"
    name: "读取主目录"
    description: "读取您的主目录中的文件以查找壁纸图片"
    risk_level: "low"
  
  - id: "aios.permission.desktop.wallpaper.write"
    name: "修改壁纸"
    description: "更改您的桌面壁纸设置"
    risk_level: "low"
```

**risk_level 值**:

| 级别 | 说明 |
|------|------|
| `public` | 无风险 |
| `low` | 低风险，首次确认 |
| `medium` | 中风险，首次确认 |
| `high` | 高风险，每次确认 |
| `critical` | 危险，二次确认 |

---

### 3.5 dependencies (依赖)

声明工具的依赖项。

```yaml
dependencies:
  system:
    - name: "gsettings"
      required: true
      check_command: "which gsettings"
    - name: "python3"
      required: true
      version: ">=3.9"
  
  runtime:
    - name: "gi"
      package: "python3-gi"
  
  tools:
    - id: "org.aios.system.dbus"
      version: ">=1.0"
```

---

### 3.6 adapter (适配器配置)

定义如何执行能力。

#### D-Bus 适配器

```yaml
adapter:
  type: "dbus"
  config:
    service: "org.gnome.desktop.background"
    interface: "org.freedesktop.DBus.Properties"
    bus: "session"  # session | system
```

#### CLI 适配器

```yaml
adapter:
  type: "cli"
  config:
    command: "/usr/bin/gsettings"
    args_template: "set {schema} {key} {value}"
    env:
      DISPLAY: ":0"
```

#### Python 适配器

```yaml
adapter:
  type: "python"
  config:
    module: "aios_desktop.wallpaper"
    class: "WallpaperAdapter"
    method_prefix: "do_"
```

#### WASM 适配器

```yaml
adapter:
  type: "wasm"
  config:
    module: "mytool.wasm"
    permissions:
      filesystem:
        - path: "/home/user/Pictures"
          access: "read"
      network:
        - host: "example.com"
          ports: [443]
```

---

## 5. 多语言适配器实现

AIOS协议是语言无关的，适配器可以用任何语言实现。以下是各语言的实现示例：

### 5.1 Python 适配器 (推荐)

```python
from aios import AIOSAdapter, capability

@AIOSAdapter(
    id="org.example.mytool",
    name="我的工具",
    version="1.0.0"
)
class MyToolAdapter:
    
    @capability(
        id="do_something",
        name="执行操作",
        risk_level="medium",
        description="执行某个操作"
    )
    async def do_something(self, param1: str, param2: int = 50) -> dict:
        """执行操作的具体实现"""
        result = await self._internal_logic(param1, param2)
        return {"success": True, "data": result}
    
    async def _internal_logic(self, param1, param2):
        # 实际业务逻辑
        return f"处理了 {param1}，参数为 {param2}"

# 启动适配器
if __name__ == "__main__":
    adapter = MyToolAdapter()
    # 支持多种传输方式
    adapter.run(transport="http", port=8080)  # 或 stdio, unix_socket
```

### 5.2 TypeScript 适配器

```typescript
import { AIOSAdapter, capability } from '@aios/sdk';

const adapter = new AIOSAdapter({
  id: 'org.example.mytool',
  name: '我的工具',
  version: '1.0.0'
});

adapter.addCapability({
  id: 'do_something',
  name: '执行操作',
  riskLevel: 'medium',
  description: '执行某个操作',
  input: {
    type: 'object',
    properties: {
      param1: { type: 'string', description: '参数1' },
      param2: { type: 'integer', default: 50 }
    },
    required: ['param1']
  },
  handler: async (params) => {
    const result = await internalLogic(params.param1, params.param2);
    return { success: true, data: result };
  }
});

// 启动适配器
adapter.run({ transport: 'http', port: 8080 });
```

### 5.3 Go 适配器

```go
package main

import (
    "context"
    "github.com/aios-protocol/aios-go"
)

func main() {
    adapter := aios.NewAdapter(aios.Config{
        ID:      "org.example.mytool",
        Name:    "我的工具",
        Version: "1.0.0",
    })

    adapter.AddCapability(aios.Capability{
        ID:          "org.example.mytool.do_something",
        Name:        "执行操作",
        RiskLevel:   aios.RiskMedium,
        Description: "执行某个操作",
        Handler: func(ctx context.Context, params map[string]any) (any, error) {
            param1 := params["param1"].(string)
            param2 := int(params["param2"].(float64))
            result := internalLogic(param1, param2)
            return map[string]any{"success": true, "data": result}, nil
        },
    })

    adapter.Run(aios.TransportHTTP, ":8080")
}
```

### 5.4 Rust 适配器 (系统级)

```rust
use aios_sdk::{Adapter, Capability, RiskLevel};
use serde_json::{json, Value};

#[tokio::main]
async fn main() {
    let mut adapter = Adapter::new(
        "org.example.mytool",
        "我的工具",
        "1.0.0",
    );

    adapter.add_capability(Capability {
        id: "org.example.mytool.do_something".to_string(),
        name: "执行操作".to_string(),
        risk_level: RiskLevel::Medium,
        handler: Box::new(|params: Value| {
            let param1 = params["param1"].as_str().unwrap();
            let param2 = params["param2"].as_i64().unwrap_or(50);
            Ok(json!({
                "success": true,
                "data": format!("处理了 {}，参数为 {}", param1, param2)
            }))
        }),
    });

    adapter.run_http("0.0.0.0:8080").await;
}
```

### 5.5 从OpenAPI自动生成

AIOS支持从OpenAPI规范自动生成适配器：

```bash
# 从OpenAPI生成Python适配器
aios-cli generate --from openapi --spec ./api.yaml --lang python --output ./adapter

# 从OpenAPI生成TypeScript适配器
aios-cli generate --from openapi --spec ./api.yaml --lang typescript --output ./adapter
```

**自动映射规则**：

| OpenAPI | AIOS | 风险级别 |
|---------|------|---------|
| GET endpoint | 只读能力 | low |
| POST endpoint | 写入能力 | medium |
| PUT endpoint | 更新能力 | medium |
| DELETE endpoint | 删除能力 | high |
| operationId | capability_id | - |
| summary | capability name | - |

---

## 4. 完整示例

### 系统壁纸适配器

```yaml
aios_version: "0.3"

tool:
  id: "org.aios.system.desktop.wallpaper"
  name: "壁纸管理器"
  version: "1.0.0"
  author: "AIOS Team"
  description: "管理 GNOME 桌面壁纸"
  type: "system"
  categories: ["System", "Desktop"]
  
  platforms:
    - os: "linux"
      distributions: ["ubuntu", "debian"]
      desktop_environments: ["gnome"]

capabilities:
  - id: "system.desktop.set_wallpaper"
    name: "设置壁纸"
    description: "将指定图片设置为桌面壁纸"
    
    input:
      type: object
      properties:
        path:
          type: string
          description: "壁纸图片的完整路径"
        mode:
          type: string
          enum: ["wallpaper", "centered", "scaled", "stretched", "zoom", "spanned"]
          default: "zoom"
          description: "壁纸显示模式"
      required: ["path"]
    
    output:
      type: object
      properties:
        success:
          type: boolean
        message:
          type: string
        data:
          type: object
          properties:
            previous_path:
              type: string
            current_path:
              type: string
    
    permissions:
      - "aios.permission.filesystem.read"
      - "aios.permission.desktop.wallpaper.write"
    
    examples:
      - user_intent: "帮我把壁纸换成蓝色的"
        call:
          capability_id: "system.desktop.set_wallpaper"
          arguments:
            path: "/usr/share/backgrounds/blue.jpg"
      
      - user_intent: "把这张图片设为桌面背景"
        call:
          capability_id: "system.desktop.set_wallpaper"
          arguments:
            path: "${context.mentioned_file}"
  
  - id: "system.desktop.get_wallpaper"
    name: "获取当前壁纸"
    description: "获取当前桌面壁纸的路径"
    
    input: {}
    
    output:
      type: object
      properties:
        path:
          type: string
        mode:
          type: string
    
    permissions:
      - "aios.permission.desktop.wallpaper.read"

permissions:
  - id: "aios.permission.filesystem.read"
    name: "文件读取"
    description: "读取壁纸图片文件"
    risk_level: "low"
  
  - id: "aios.permission.desktop.wallpaper.read"
    name: "读取壁纸设置"
    description: "读取当前壁纸设置"
    risk_level: "public"
  
  - id: "aios.permission.desktop.wallpaper.write"
    name: "修改壁纸"
    description: "更改桌面壁纸"
    risk_level: "low"

dependencies:
  system:
    - name: "gsettings"
      required: true
    - name: "dconf"
      required: false

adapter:
  type: "dbus"
  config:
    service: "org.gnome.desktop.background"
    bus: "session"
```

---

## 6. 与 Adapter Card 的关系

`tool.aios.yaml` 主要用于本地适配器描述，而 [Adapter Card](AIOS-Protocol-Discovery.md) 用于远程适配器发现。两者可以相互转换：

| tool.aios.yaml | Adapter Card |
|----------------|--------------|
| `tool.id` | `adapter.id` |
| `tool.name` | `adapter.name` |
| `tool.version` | `adapter.version` |
| `capabilities[]` | `skills[]` |
| `permissions[]` | 映射到 `skills[].permission_level` |

当同一适配器同时存在多种描述时，优先级为：
1. Adapter Card JSON (最高)
2. tool.aios.yaml
3. .desktop 文件 + 自动推断 (最低)

---

## 7. 验证

使用 JSON Schema 验证 `tool.aios.yaml` 文件：

```bash
aios-cli validate tool.aios.yaml
```

JSON Schema 文件位置：`/usr/share/aios/schemas/tool.aios.schema.json`

---

**文档版本**: 2.0.0
**最后更新**: 2026-01-09
**维护者**: AIOS Protocol Team
