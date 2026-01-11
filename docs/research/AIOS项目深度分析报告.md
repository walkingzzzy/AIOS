# AIOS 项目深度分析报告

**分析日期**: 2026-01-08  
**项目版本**: AIOS Protocol v0.6.0  
**分析范围**: 架构设计、代码实现、最佳实践、可借鉴之处

---

## 一、项目概述

### 1.1 核心定位

AIOS Protocol 是一个**让 AI 通过自然语言控制操作系统和软件的开放标准协议**。

```
用户 (自然语言) → AI 引擎 (意图理解) → AIOS Protocol (执行控制) → 操作系统/软件
```

### 1.2 与竞品的差异化

| 方案 | 控制方式 | 速度 | 可靠性 | 安全性 |
|------|---------|------|--------|--------|
| Claude Computer Use | 截图+坐标点击 | 慢 | 低 | 依赖模型 |
| OpenAI Operator | GUI 交互 | 中 | 中 | 无标准 |
| MCP | API 调用 | 快 | 高 | **无权限模型** |
| **AIOS Protocol** | 标准化接口 + 视觉兜底 | 快 | 高 | **5级权限+沙箱** |

**AIOS 的独特价值**：
1. **用户导向** - 面向终端用户，而非开发者
2. **系统级控制** - 控制操作系统，而非仅调用工具
3. **安全优先** - 内置权限模型，MCP/A2A 无此功能
4. **渐进式视觉控制** - API 优先，视觉兜底

---

## 二、架构设计分析

### 2.1 三层控制架构 ⭐⭐⭐⭐⭐

这是 AIOS 最核心的架构设计：

```
┌─────────────────────────────────────────────────────────────────┐
│  第一层: 系统控制层 (D-Bus/API)                                  │
│  控制操作系统基础功能 - 最快、最可靠                              │
├─────────────────────────────────────────────────────────────────┤
│  第二层: 视觉控制层 (Vision)                                     │
│  基于 VLM 的通用控制 - 作为无 API 软件的兜底方案                   │
├─────────────────────────────────────────────────────────────────┤
│  第三层: 应用控制层 (API/MCP)                                    │
│  基于 API 的深度集成 - 浏览器、专业软件、MCP 工具                  │
└─────────────────────────────────────────────────────────────────┘
```

**设计理念**：
- **API 优先**：能用 API 就不用视觉，保证速度和可靠性
- **视觉兜底**：对于没有 API 的应用，使用视觉控制作为通用方案
- **渐进式实现**：Sprint 1-7 只分析不执行，Sprint 8+ 才自动执行

### 2.2 三层云端 AI 架构 ⭐⭐⭐⭐⭐

基于成本和延迟的智能路由设计：

| 层级 | 模型 | 价格 | 延迟目标 | 适用场景 | 占比 |
|------|------|------|---------|---------| -----|
| 🆓 Fast | gpt-4o-mini | $0.000 | <500ms | 简单指令 | 70% |
| 💰 Vision | gemini-2.5-flash | $0.001 | <3s | 截图分析 | 10% |
| 💎 Smart | claude-sonnet | $0.002 | <2s | 复杂推理 | 20% |

**预估月成本**: ~$15/月 (日均 1000 次调用)

### 2.3 5 级权限模型 ⭐⭐⭐⭐⭐

| 级别 | 名称 | 用户确认 | 自动授权 | 示例 |
|------|------|---------|---------|------|
| 0 | public | 无需 | ✅ | 读取时间 |
| 1 | low | 首次 | ✅ | 调整音量 |
| 2 | medium | 首次 | ⚠️ 可配置 | 打开浏览器 |
| 3 | high | 每次 | ❌ | 发送消息、窗口控制 |
| 4 | critical | 二次确认 | ❌ | 关机、删除文件 |

---

## 三、代码实现亮点

### 3.1 适配器协议设计

```swift
public protocol AIOSAdapter: AnyObject {
    var id: String { get }
    var name: String { get }
    var supportedActions: [String] { get }
    
    func getToolDefinition() -> ToolDefinition
    func execute(action: String, params: [String: Any]) async throws -> ToolCallResult
    
    // 诊断功能
    func diagnose() async -> [DiagnosticIssue]
    func requiredPermissions() -> [PermissionRequirement]
}
```

### 3.2 AI 路由器实现

```swift
public func route(input: String, hasScreenshot: Bool = false) -> RouteDecision? {
    let classification = classifier.classify(input, hasScreenshot: hasScreenshot)
    
    switch classification.complexity {
    case .simple:
        return RouteDecision(tier: .fast, engine: fastEngine, ...)
    case .vision:
        return RouteDecision(tier: .vision, engine: visionEngine, ...)
    case .complex:
        return RouteDecision(tier: .smart, engine: smartEngine, ...)
    }
}
```

### 3.3 工具定义 JSON Schema

```json
{
  "id": "aios.system.audio",
  "actions": [
    {
      "name": "set_volume",
      "permissionLevel": "low",
      "parameters": [
        { "name": "volume", "type": "integer", "minimum": 0, "maximum": 100 }
      ]
    }
  ]
}
```

---

## 四、值得借鉴的设计理念

### 4.1 渐进式实现策略

| Sprint | 视觉能力 | 兜底行为 |
|--------|---------|---------|
| Sprint 1-7 | 截图 + 分析 (只读) | 提示用户手动操作 |
| Sprint 8+ | 截图 + 分析 + 点击 | 自动执行视觉控制 |

### 4.2 仿生操作算法

| 参数 | 算法 | 说明 |
|------|------|------|
| 轨迹生成 | 贝塞尔曲线 | 模拟人类手指自然摆动 |
| 压力值 | 随机化 | 0.3-0.9 范围 |
| 操作延迟 | 固定+抖动 | 1000-5000ms |

### 4.3 技术可行性验证

项目在开发前进行了深度技术验证，记录验证来源和风险等级。

---

## 五、对开发计划的建议

### 5.1 架构设计建议

1. **采用三层控制架构** - API 优先，视觉兜底
2. **实现智能 AI 路由** - 70% 简单指令使用免费模型
3. **建立权限模型** - 5 级权限，与系统 TCC 映射

### 5.2 代码组织建议

```
project/
├── daemon/Sources/
│   ├── Core/AI/           # AI 引擎和路由
│   ├── Core/Adapter/      # 适配器协议
│   ├── Adapters/System/   # 系统适配器
│   └── Security/          # 安全模块
├── tools/                 # 工具定义 JSON
└── docs/                  # 文档
```

### 5.3 技术选型建议

| 组件 | 推荐技术 | 理由 |
|------|---------|------|
| 核心运行时 | Swift + Rust | Swift 原生 API，Rust 性能 |
| 进程通信 | XPC Services | macOS 原生，沙盒隔离 |
| AI 引擎 | 三层云端 API | 成本可控 |
| 通信协议 | JSON-RPC 2.0 | 与 MCP 兼容 |

---

## 六、总结

### 核心优势

1. **三层控制架构** - API 优先，视觉兜底
2. **三层云端 AI** - 智能路由，成本可控
3. **5 级权限模型** - 安全优先
4. **渐进式实现** - 降低风险

### 可直接复用的设计

1. 适配器协议 - 清晰接口，支持诊断
2. AI 路由器 - 基于复杂度的智能路由
3. TCC 权限管理 - 与系统权限映射
4. 工具定义格式 - JSON Schema 验证

### 需要注意的风险

1. Private API 使用 - 亮度控制需要私有 API
2. AppleScript 废弃风险 - Apple 转向 Shortcuts
3. WiFi SSID 隐私限制 - macOS 15.3+ 需要位置权限

---

**报告版本**: 1.0.0  
**分析日期**: 2026-01-08


---

## 附录 A：关键代码模式参考

### A.1 适配器基类模式

```swift
open class BaseAdapter: AIOSAdapter {
    public let id: String
    public let name: String
    
    open func execute(action: String, params: [String: Any]) async throws -> ToolCallResult {
        throw AdapterError.actionNotSupported(action)
    }
    
    open func diagnose() async -> [DiagnosticIssue] {
        var issues: [DiagnosticIssue] = []
        
        // 检查权限
        for permission in requiredPermissions() {
            if !permission.isSatisfied {
                issues.append(DiagnosticIssue(
                    type: .permissionDenied,
                    message: "缺少\(permission.name)权限",
                    suggestion: permission.grantInstructions
                ))
            }
        }
        
        return issues
    }
}
```

### A.2 TCC 权限检查模式

```swift
public final class TCCManager {
    public var hasAccessibilityPermission: Bool {
        AXIsProcessTrusted()
    }
    
    public func requestAccessibilityPermission() {
        let options = [kAXTrustedCheckOptionPrompt.takeUnretainedValue(): true] as CFDictionary
        AXIsProcessTrustedWithOptions(options)
    }
    
    public func openPrivacySettings(for service: PrivacyService) {
        let urlString = "x-apple.systempreferences:com.apple.preference.security?Privacy_\(service.rawValue)"
        if let url = URL(string: urlString) {
            NSWorkspace.shared.open(url)
        }
    }
}
```

### A.3 渐进式控制路由

```swift
func execute(action: Action) async throws -> Result {
    // 1. 尝试 API 控制
    if let result = try? await apiAdapter.execute(action) {
        return result
    }
    
    // 2. 视觉控制兜底
    if visionAdapter.canAutoExecute {
        return try await visionAdapter.execute(action)  // Sprint 8+
    } else {
        // Sprint 1-7: 只分析不点击，提示用户
        let analysis = try await visionAdapter.analyze(action)
        return .degraded(
            message: "该应用暂不支持自动控制",
            hint: analysis.suggestedAction
        )
    }
}
```

---

## 附录 B：项目文件结构

```
aios-macos/
├── daemon/
│   ├── Package.swift                    # Swift Package 定义
│   └── Sources/
│       ├── Core/
│       │   ├── AI/
│       │   │   ├── AIRouter.swift       # 三层 AI 路由器
│       │   │   └── IntentClassifier.swift
│       │   ├── Adapter/
│       │   │   └── AdapterProtocol.swift # 适配器协议
│       │   ├── Protocol/                # JSON-RPC 协议
│       │   └── Router/                  # 请求路由
│       ├── Adapters/
│       │   ├── System/
│       │   │   ├── AudioAdapter.swift   # 音频控制
│       │   │   ├── DisplayAdapter.swift # 显示控制
│       │   │   └── PowerAdapter.swift   # 电源管理
│       │   ├── Apps/                    # 应用控制
│       │   ├── Network/                 # 网络控制
│       │   └── Window/                  # 窗口管理
│       └── Security/
│           ├── TCCManager.swift         # TCC 权限管理
│           └── PermissionGuard.swift    # 权限守卫
├── client/                              # SwiftUI 客户端
└── tools/                               # 工具定义 JSON
    ├── audio.json
    ├── window.json
    ├── vision.json
    └── ...
```

---

## 附录 C：Sprint 开发计划参考

| Sprint | 周期 | 目标 | 交付物 |
|--------|------|------|--------|
| Sprint 1 | Week 1-2 | 项目骨架 + 三层云端 AI + 视觉基础 | 基础框架、AI 路由、截图分析 |
| Sprint 2 | Week 3-4 | AIOS Daemon + XPC 服务 | 核心守护进程 |
| Sprint 3 | Week 5-6 | 基础系统控制适配器 | 音量、亮度、壁纸等 |
| Sprint 4 | Week 7-8 | TCC 权限系统 | 权限检查、引导流程 |
| Sprint 5 | Week 9-10 | 文件管理 + 进程控制 | Finder 集成、应用管理 |
| Sprint 6 | Week 11-12 | 窗口管理 + 网络控制 | Accessibility、WiFi/蓝牙 |
| Sprint 7 | Week 13-16 | SwiftUI 客户端 | GUI 界面 |
| Sprint 8 | Week 17-20 | 高级功能 + 云端视觉控制 | Gemini Vision、截图 |
| Sprint 9 | Week 21-24 | Alpha 发布准备 | 签名、公证、文档 |

---

## 附录 D：工具定义完整示例

```json
{
  "$schema": "https://aios-protocol.org/schemas/tool/v1",
  "id": "aios.system.audio",
  "name": "audio",
  "displayName": "音频控制",
  "description": "控制系统音量、静音和音频设备",
  "version": "1.0.0",
  "platform": "macos",
  "actions": [
    {
      "name": "get_volume",
      "description": "获取当前系统音量",
      "permissionLevel": "public",
      "parameters": [],
      "returns": {
        "type": "object",
        "properties": {
          "volume": { "type": "integer", "description": "音量值 (0-100)" }
        }
      }
    },
    {
      "name": "set_volume",
      "description": "设置系统音量",
      "permissionLevel": "low",
      "parameters": [
        {
          "name": "volume",
          "type": "integer",
          "description": "音量值 (0-100)",
          "required": true,
          "minimum": 0,
          "maximum": 100
        }
      ]
    }
  ],
  "examples": [
    {
      "description": "设置音量为 75%",
      "request": { "action": "set_volume", "params": { "volume": 75 } },
      "response": { "volume": 75 }
    }
  ]
}
```

---

## 附录 E：多语言 SDK 示例

### Python SDK

```python
from aios import AIOSAdapter, capability

@AIOSAdapter(id="org.example.mytool", name="我的工具", version="1.0.0")
class MyToolAdapter:
    
    @capability(id="do_something", name="执行操作", risk_level="medium")
    async def do_something(self, param1: str, param2: int = 50) -> dict:
        result = await self._internal_logic(param1, param2)
        return {"success": True, "data": result}

# 启动适配器
if __name__ == "__main__":
    adapter = MyToolAdapter()
    adapter.run(transport="http", port=8080)
```

### TypeScript SDK

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
  handler: async (params) => {
    const result = await internalLogic(params.param1, params.param2);
    return { success: true, data: result };
  }
});

adapter.run({ transport: 'http', port: 8080 });
```

### Go SDK

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
        ID:        "do_something",
        Name:      "执行操作",
        RiskLevel: aios.RiskMedium,
        Handler: func(ctx context.Context, params map[string]any) (any, error) {
            return map[string]any{"success": true}, nil
        },
    })

    adapter.Run(aios.TransportHTTP, ":8080")
}
```
