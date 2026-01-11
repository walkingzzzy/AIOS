# AIOS Protocol 可扩展性框架

**版本**: 2.0.0  
**更新日期**: 2026-01-09  
**状态**: 战略规划阶段

---

## 设计哲学

> **我们不是开发具体功能，而是设计让别人能开发任何功能的协议标准**

### 核心原则

1. **协议优于实现** - 定义清晰的接口规范，而非具体实现
2. **向后兼容** - 新版本协议必须能处理旧版本数据
3. **向前容忍** - 旧版本处理新版本数据时忽略未知字段 (must-ignore)
4. **能力协商** - 双方声明支持的能力，按最小公共集工作
5. **自描述性** - 任何工具都能完整描述自己的能力

---

## 协议版本管理

### 语义化版本 (Semantic Versioning)

```
MAJOR.MINOR.PATCH
│      │      │
│      │      └─ 修复：向后兼容的错误修复
│      └─ 新增：向后兼容的功能新增（可选字段、新能力类型）
└─ 破坏：不兼容的协议变更
```

### 版本协商流程

```
┌─────────────┐                      ┌─────────────┐
│  AIOS Core  │                      │  Tool/Adapter│
└──────┬──────┘                      └──────┬──────┘
       │                                     │
       │  1. Hello (支持的协议版本列表)       │
       │────────────────────────────────────>│
       │                                     │
       │  2. Hello Response (选定的版本)     │
       │<────────────────────────────────────│
       │                                     │
       │  3. 按协商版本进行通信               │
       │<────────────────────────────────────>│
       │                                     │
```

---

## 能力协商系统 (Capability Negotiation)

> **借鉴 LSP (Language Server Protocol) 的成功设计**

### 能力声明格式

```yaml
# 每个工具/适配器必须在初始化时声明其能力
capabilities:
  # 标准能力 (协议定义)
  standard:
    - id: "aios.capability.invoke"   # 能力调用
      version: "1.0"
    - id: "aios.capability.discover" # 能力发现
      version: "1.0"
    - id: "aios.progress.report"    # 进度报告
      version: "1.0"
    - id: "aios.permission.request" # 权限请求
      version: "1.0"
      
  # 可选能力 (工具自行决定是否支持)
  optional:
    - id: "aios.visual.overlay"     # 可视化覆盖层
      version: "1.0"
      supported: true
    - id: "aios.visual.recording"   # 操作录制
      version: "1.0"
      supported: false
      
  # 扩展能力 (第三方定义，使用反向域名)
  extensions:
    - id: "com.blender.scripting"   # Blender 脚本能力
      version: "2.0"
    - id: "org.gimp.filters"        # GIMP 滤镜能力
      version: "1.0"
```

### 能力协商规则

| 规则 | 说明 |
|------|------|
| **最小公共集** | 双方只使用都支持的能力 |
| **优雅降级** | 缺少可选能力时提供替代方案 |
| **版本匹配** | 同一能力取双方支持的最高共同版本 |
| **未知忽略** | 未知的能力 ID 必须安全忽略 |

---

## 扩展点设计

### 协议扩展点

```
┌─────────────────────────────────────────────────────────────────┐
│                    AIOS Protocol 扩展架构                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │                    Layer 3: 应用扩展                       │  │
│  │  第三方开发者自定义能力、参数、返回值                        │  │
│  │  例: com.adobe.photoshop.layers                           │  │
│  └───────────────────────────────────────────────────────────┘  │
│                              ↑                                  │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │                    Layer 2: 领域扩展                       │  │
│  │  特定领域的标准能力集                                       │  │
│  │  例: aios.domain.cad, aios.domain.graphics                │  │
│  └───────────────────────────────────────────────────────────┘  │
│                              ↑                                  │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │                    Layer 1: 核心协议                       │  │
│  │  所有实现必须支持的基础能力                                  │  │
│  │  aios.capability.*, aios.permission.*, aios.lifecycle.*  │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 扩展命名规范

```
扩展ID格式: <namespace>.<domain>.<capability>

标准扩展:  aios.<domain>.<name>          # 官方定义
领域扩展:  aios.domain.<domain>.<name>   # 社区标准化
应用扩展:  <reverse.domain>.<app>.<name> # 第三方自定义

示例:
- aios.tool.invoke           # 核心协议
- aios.domain.cad.modeling   # CAD 领域标准
- com.blender.mesh.create    # Blender 专用
- io.inkscape.path.boolean   # Inkscape 专用
```

---

## 工具描述规范 (Tool Description Schema)

### JSON Schema 定义

```json
{
  "$schema": "https://aios-protocol.org/schemas/tool/v1",
  "$id": "https://aios-protocol.org/schemas/tool/v1/tool.schema.json",
  
  "type": "object",
  "required": ["aios_version", "tool", "capabilities"],
  
  "properties": {
    "aios_version": {
      "type": "string",
      "pattern": "^\\d+\\.\\d+$",
      "description": "协议版本 (MAJOR.MINOR)"
    },
    
    "tool": {
      "type": "object",
      "required": ["id", "name", "version"],
      "properties": {
        "id": {
          "type": "string",
          "pattern": "^[a-z][a-z0-9]*\\.([a-z][a-z0-9]*\\.)*[a-z][a-z0-9]*$",
          "description": "反向域名格式的唯一标识符"
        },
        "name": { "type": "string" },
        "version": { "type": "string" },
        "description": { "type": "string" },
        "author": { "type": "string" },
        "license": { "type": "string" },
        "homepage": { "type": "string", "format": "uri" },
        "repository": { "type": "string", "format": "uri" }
      },
      "additionalProperties": true
    },
    
    "capabilities": {
      "type": "array",
      "items": { "$ref": "#/$defs/capability" }
    },
    
    "permissions": {
      "type": "array",
      "items": { "$ref": "#/$defs/permission" }
    }
  },
  
  "$defs": {
    "capability": {
      "type": "object",
      "required": ["id", "name"],
      "properties": {
        "id": { "type": "string" },
        "name": { "type": "string" },
        "description": { "type": "string" },
        "input": { "$ref": "https://json-schema.org/draft/2020-12/schema" },
        "output": { "$ref": "https://json-schema.org/draft/2020-12/schema" },
        "examples": { "type": "array" },
        "permissions": { "type": "array", "items": { "type": "string" } }
      },
      "additionalProperties": true
    },
    
    "permission": {
      "type": "object",
      "required": ["id", "risk_level"],
      "properties": {
        "id": { "type": "string" },
        "name": { "type": "string" },
        "description": { "type": "string" },
        "risk_level": {
          "type": "string",
          "enum": ["public", "low", "medium", "high", "critical"]
        }
      },
      "additionalProperties": true
    }
  },
  
  "additionalProperties": true
}
```

### additionalProperties: true 的重要性

> **这是协议可扩展性的关键设计**

任何第三方开发者都可以在标准字段之外添加自定义字段，协议实现必须：
- ✅ 安全忽略未知字段 (must-ignore processing)
- ✅ 传递未知字段到下游
- ❌ 不能因未知字段报错

---

## 通信协议扩展

### 消息格式扩展

```json
{
  "jsonrpc": "2.0",
  "id": "uuid-xxx",
  "method": "aios/capability.invoke",
  "params": {
    "capability_id": "com.example.tool.do_something",
    "arguments": { ... },
    
    // 标准扩展点
    "context": { ... },
    "options": { ... },
    
    // 任意第三方扩展 (must-ignore)
    "x-custom-field": { ... }
  }
}
```

### 方法命名空间

```
标准方法:
  aios/capability.list      # 列出能力
  aios/capability.invoke    # 调用能力
  aios/capability.cancel    # 取消调用
  aios/permission.request   # 请求权限
  aios/progress.report      # 进度报告

第三方方法:
  <namespace>/method.name
  例: com.blender/scene.render
```

---

## 第三方开发者指南

### 创建新工具的步骤

```
1. 定义工具描述文件 (tool.aios.yaml / tool.aios.json)
   │
   ├─ 遵循 Tool Description Schema
   ├─ 使用反向域名作为 tool.id
   └─ 声明所有能力和权限

2. 实现适配器
   │
   ├─ 实现核心协议能力 (aios.capability.invoke)
   ├─ 可选实现可视化能力
   └─ 可添加自实义扩展能力

3. 测试兼容性
   │
   ├─ 使用 AIOS 协议验证工具
   └─ 确保 must-ignore 正确处理

4. 发布
   │
   ├─ 随软件包分发 tool.aios.yaml
   ├─ 可发布到适配器市场
   └─ 可提交标准化申请 (成为领域扩展)
```

### 扩展工具能力

开发者可以在标准能力基础上添加扩展：

```yaml
capabilities:
  # 标准能力 (AIOS 核心理解)
  - id: "aios.capability.invoke"
    ...
    
  # 自定义能力 (仅兼容的客户端理解)
  - id: "com.mycompany.mytool.advanced_feature"
    name: "高级功能"
    description: "我的专有能力"
    
    # 自定义输入/输出
    input:
      type: object
      properties:
        my_param: { type: string }
        
    # 自定义扩展字段
    x-requires-license: true
    x-min-version: "2.0"
```

---

## 领域标准化流程

### 从应用扩展到领域标准

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  应用扩展    │ --> │  提案审核    │ --> │  领域标准    │
│              │     │              │     │              │
│ com.blender. │     │ RFC 流程     │     │ aios.domain. │
│ mesh.create  │     │ 社区讨论     │     │ cad.modeling │
└──────────────┘     └──────────────┘     └──────────────┘
```

### 标准化提案模板

```markdown
# RFC: aios.domain.cad

## 摘要
为 CAD 软件定义通用能力集

## 动机
多个 CAD 软件有相似能力，标准化后可互操作

## 能力定义
- aios.domain.cad.modeling.create_primitive
- aios.domain.cad.modeling.boolean_operation
- aios.domain.cad.export.to_format

## 兼容性
列出已有哪些软件可以支持

## 参考实现
示例代码
```

---

## 互操作性保证

### 必须遵守的规则

| 规则 | 说明 | 违反后果 |
|------|------|---------|
| **R1** | 忽略未知字段 | 无法与新版本工具互操作 |
| **R2** | 能力协商 | 无法确定可用功能 |
| **R3** | 版本声明 | 无法判断兼容性 |
| **R4** | 错误格式 | 错误处理不一致 |
| **R5** | 权限声明 | 安全审计不可行 |

### 兼容性测试套件

协议将提供官方测试套件，验证：
- JSON Schema 验证通过
- 未知字段正确忽略
- 能力协商正常工作
- 错误响应格式正确
- 版本协商成功

---

## 路线图

### 已完成
- [x] 设计核心扩展架构
- [x] 定义能力协商系统
- [x] 创建 Tool Description Schema
- [x] 建立扩展命名规范

### 即将进行
- [ ] 发布 JSON Schema 到公开仓库
- [ ] 创建协议验证工具 (`aios-cli validate`)
- [ ] 编写开发者详细文档
- [ ] 建立 RFC 提案流程
- [ ] 创建示例适配器模板

### 相关文档

- [核心协议](AIOS-Protocol-Spec.md)
- [开发规范](../guides/AIOS-Protocol-DevSpec.md)
- [最佳实践](../guides/AIOS-Developer-BestPractices.md)

