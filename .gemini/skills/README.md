# Antigravity Skills 索引

> 这是 Antigravity AI 助手的技能库，包含开发规范、工作流程和最佳实践。

## 🔍 快速查找

| 类别 | Skills |
|------|--------|
| **工作流程** | [workflow](workflow/SKILL.md), [progressive-context](progressive-context/SKILL.md) |
| **代码质量** | [code-standards](code-standards/SKILL.md), [quality-verification](quality-verification/SKILL.md) |
| **上下文检索** | [context-retrieval](context-retrieval/SKILL.md), [lazy-detection](lazy-detection/SKILL.md) |
| **测试** | [test-driven-development](test-driven-development/SKILL.md) |
| **开发实践** | [refactoring](refactoring/SKILL.md), [debugging](debugging/SKILL.md), [error-handling](error-handling/SKILL.md) |
| **工具** | [toolchain](toolchain/SKILL.md), [git-operations](git-operations/SKILL.md) |
| **文档** | [documentation](documentation/SKILL.md) |
| **框架** | [typescript](typescript/SKILL.md), [react](react/SKILL.md) |
| **安全** | [security](security/SKILL.md) |
| **集成** | [project-integration](project-integration/SKILL.md) |

---

## 📊 Skills 概览（17个）

### 核心 Skills
| Skill | 描述 |
|-------|------|
| [context-retrieval](context-retrieval/SKILL.md) | 编码前7步强制检索 |
| [workflow](workflow/SKILL.md) | 6步标准流程 + 迭代循环 |
| [code-standards](code-standards/SKILL.md) | 强制中文 + SOLID 原则 |
| [quality-verification](quality-verification/SKILL.md) | 评分体系(0-100) |

### 开发实践
| Skill | 描述 |
|-------|------|
| [test-driven-development](test-driven-development/SKILL.md) | Red-Green-Refactor |
| [debugging](debugging/SKILL.md) | 5W1H + 二分法定位 |
| [refactoring](refactoring/SKILL.md) | 代码异味识别 |
| [error-handling](error-handling/SKILL.md) | 熔断器 + 指数退避 |

### 框架 & 语言
| Skill | 描述 |
|-------|------|
| [typescript](typescript/SKILL.md) | 类型系统 + 严格模式 |
| [react](react/SKILL.md) | Hooks + 组件设计 |
| [security](security/SKILL.md) | 输入验证 + 漏洞防护 |

### 工具 & 集成
| Skill | 描述 |
|-------|------|
| [toolchain](toolchain/SKILL.md) | 工具选择决策树 |
| [git-operations](git-operations/SKILL.md) | Conventional Commits |
| [documentation](documentation/SKILL.md) | README/API 文档规范 |
| [project-integration](project-integration/SKILL.md) | 复用优先规则 |

### 高级
| Skill | 描述 |
|-------|------|
| [progressive-context](progressive-context/SKILL.md) | 渐进式上下文收集 |
| [lazy-detection](lazy-detection/SKILL.md) | 三级惩罚体系 |

---

## 🔄 Skills 关系图

```
context-retrieval ──→ progressive-context
         │                    │
         ↓                    ↓
    lazy-detection ←── workflow ──→ quality-verification
                           │
                           ↓
                    code-standards
                     ↙    ↓    ↘
            typescript  react  security
```

---

## 💡 使用说明

1. Skills 会在相关任务中**自动激活**
2. 每个 skill 底部有**相关 skills** 链接
3. 按任务类型查找对应 skill
