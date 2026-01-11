# AIOS Protocol 依赖管理规范

**版本**: 2.0.0  
**更新日期**: 2026-01-09  
**状态**: 战略规划阶段

---

## 一、依赖类型

### 1.1 依赖分类

```yaml
dependency_types:
  # 协议依赖 - AIOS 协议版本要求
  protocol:
    description: "要求特定的 AIOS 协议版本"
    
  # 工具依赖 - 依赖其他 AIOS 工具
  tool:
    description: "依赖其他 AIOS 工具提供的能力"
    
  # 系统依赖 - 依赖系统组件
  system:
    description: "依赖操作系统组件或命令"
    
  # 运行时依赖 - 依赖运行时环境
  runtime:
    description: "依赖特定的运行时环境"
```

---

## 二、依赖声明格式

### 2.1 工具描述中的依赖

```yaml
# tool.aios.yaml
tool:
  id: "com.example.advanced-tool"
  name: "Advanced Tool"
  version: "2.0.0"

dependencies:
  # 协议版本要求
  protocol:
    aios: ">=0.2.0 <1.0.0"
    
  # 工具依赖
  tools:
    - id: "com.example.base-tool"
      version: ">=1.0.0"
      optional: false
      capabilities_required:
        - "basic.operation"
        
    - id: "org.community.helper"
      version: ">=2.0.0 <3.0.0"
      optional: true
      reason: "启用高级功能需要此工具"
      
  # 系统依赖
  system:
    commands:
      - name: "gsettings"
        required: true
        check: "gsettings --version"
        
      - name: "ffmpeg"
        required: false
        version: ">=4.0.0"
        check: "ffmpeg -version"
        
    services:
      - name: "org.freedesktop.NetworkManager"
        type: "dbus"
        required: true
        
    libraries:
      - name: "libgtk-4"
        version: ">=4.0.0"
        required: true
        
  # 运行时依赖
  runtime:
    python:
      version: ">=3.10"
      packages:
        - name: "requests"
          version: ">=2.28.0"
        - name: "pydbus"
          version: ">=0.6.0"
```

---

## 三、版本约束语法

### 3.1 版本规范 (Semantic Versioning)

```
MAJOR.MINOR.PATCH[-PRERELEASE][+BUILD]

示例:
1.0.0
2.1.0-alpha.1
3.0.0-beta.2+build.123
```

### 3.2 版本约束表达式

| 表达式 | 含义 | 示例匹配 |
|--------|------|---------|
| `1.2.3` | 精确版本 | 1.2.3 |
| `>=1.2.0` | 大于等于 | 1.2.0, 1.3.0, 2.0.0 |
| `<2.0.0` | 小于 | 1.0.0, 1.9.9 |
| `>=1.0.0 <2.0.0` | 范围 | 1.0.0 ~ 1.9.9 |
| `^1.2.0` | 兼容 (同 major) | 1.2.0 ~ 1.x.x |
| `~1.2.0` | 近似 (同 minor) | 1.2.0 ~ 1.2.x |
| `*` | 任意版本 | 所有版本 |
| `1.x` | 通配符 | 1.0.0 ~ 1.9.9 |

### 3.3 预发布版本处理

```yaml
version_rules:
  - rule: "预发布版本仅在明确指定时匹配"
    example: ">=1.0.0-alpha 只匹配 1.0.0-alpha.x"
    
  - rule: "正式版本不匹配预发布版本"
    example: ">=1.0.0 不匹配 1.0.0-beta"
```

---

## 四、依赖解析

### 4.1 解析流程

```
┌─────────────────────────────────────────────────────────────────┐
│                     依赖解析流程                                 │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  1. 读取工具的 dependencies 声明                                 │
│     ↓                                                           │
│  2. 构建依赖图                                                   │
│     ↓                                                           │
│  3. 检测循环依赖                                                 │
│     ↓                                                           │
│  4. 拓扑排序确定加载顺序                                         │
│     ↓                                                           │
│  5. 版本解析 (找到满足所有约束的版本)                            │
│     ↓                                                           │
│  6. 检查系统依赖是否满足                                         │
│     ↓                                                           │
│  7. 按顺序加载工具                                               │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 4.2 冲突解析策略

| 冲突类型 | 解决策略 |
|---------|---------|
| **版本冲突** | 尝试找到都满足的版本 |
| **无解版本** | 报错，显示冲突详情 |
| **循环依赖** | 报错，显示依赖环路 |
| **可选依赖缺失** | 警告，继续执行 |

### 4.3 冲突报告格式

```json
{
  "error": {
    "code": -32109,
    "message": "Dependency missing",
    "data": {
      "error_id": "AIOS-DEP-001",
      "conflicts": [
        {
          "package": "com.example.helper",
          "required_by": [
            { "capability": "com.example.tool-a", "version_req": ">=2.0.0" },
            { "capability": "com.example.tool-b", "version_req": "<2.0.0" }
          ],
          "resolution": "No version satisfies all constraints"
        }
      ]
    }
  }
}
```

---

## 五、依赖检查 API

### 5.1 检查依赖是否满足

```json
{
  "jsonrpc": "2.0",
  "id": "dep-check-001",
  "method": "aios/dependency.check",
  "params": {
    "tool_id": "com.example.mytool"
  }
}
```

### 5.2 检查响应

```json
{
  "jsonrpc": "2.0",
  "id": "dep-check-001",
  "result": {
    "satisfied": false,
    "dependencies": {
      "protocol": {
        "aios": { "required": ">=0.2.0", "installed": "0.2.1", "satisfied": true }
      },
      "tools": [
        { "id": "com.example.base-tool", "required": ">=1.0.0", "installed": "1.2.0", "satisfied": true },
        { "id": "org.community.helper", "required": ">=2.0.0", "installed": null, "satisfied": false, "optional": true }
      ],
      "system": {
        "commands": [
          { "name": "gsettings", "required": true, "found": true, "path": "/usr/bin/gsettings" },
          { "name": "ffmpeg", "required": false, "found": true, "version": "5.1.0" }
        ]
      }
    },
    "missing": [
      { "type": "tool", "id": "org.community.helper", "optional": true }
    ]
  }
}
```

---

## 六、依赖安装

### 6.1 安装请求

```json
{
  "jsonrpc": "2.0",
  "method": "aios/dependency.install",
  "params": {
    "tool_id": "com.example.mytool",
    "install_optional": false,
    "dry_run": false
  }
}
```

### 6.2 安装进度报告

```json
{
  "jsonrpc": "2.0",
  "method": "aios/progress.report",
  "params": {
    "operation": "dependency.install",
    "current": 2,
    "total": 5,
    "status": "installing",
    "current_item": "com.example.base-tool@1.2.0"
  }
}
```

---

## 七、锁文件 (Lock File)

### 7.1 锁文件格式

```yaml
# aios.lock.yaml
lockfile_version: 1
generated_at: "2026-01-01T21:30:00Z"

tools:
  - id: "com.example.mytool"
    version: "2.0.0"
    checksum: "sha256:abc123..."
    
  - id: "com.example.base-tool"
    version: "1.2.0"
    checksum: "sha256:def456..."
    resolved_by: "com.example.mytool"

system:
  - name: "gsettings"
    version: "3.38.0"
    path: "/usr/bin/gsettings"
```

### 7.2 锁文件用途

| 用途 | 说明 |
|------|------|
| **可重复构建** | 确保每次使用相同版本 |
| **快速启动** | 跳过版本解析过程 |
| **安全审计** | 追踪依赖变更 |

---

## 八、最佳实践

### 8.1 依赖声明建议

```yaml
best_practices:
  - rule: "使用范围约束而非精确版本"
    good: ">=1.0.0 <2.0.0"
    bad: "1.2.3"
    
  - rule: "标记可选依赖"
    example: "optional: true + reason 说明"
    
  - rule: "检查系统依赖"
    example: "使用 check 命令验证"
    
  - rule: "文档化依赖用途"
    example: "说明为什么需要此依赖"
```

### 8.2 版本发布建议

```yaml
release_guidelines:
  - rule: "MAJOR 变更前通知依赖者"
  - rule: "保持 MINOR 变更向后兼容"
  - rule: "PATCH 仅用于修复"
  - rule: "使用预发布版本测试"
```
