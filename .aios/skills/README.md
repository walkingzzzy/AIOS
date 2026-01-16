# AIOS Skills 系统 - 开发准则

本目录包含项目级的技能（Skills）定义，用于增强 AI 助手的能力。

## 目录结构

```
.aios/skills/
├── README.md                            # 本文档
│
├── ## 核心开发准则 Skills ##
├── context-retrieval.skill.md          # 强制上下文检索（编码前7步检索）
├── quality-verification.skill.md       # 质量验证机制（评分体系）
├── code-standards.skill.md             # 代码质量标准（SOLID/DRY等）
├── workflow.skill.md                   # 标准工作流程（6步骤+5阶段）
├── toolchain.skill.md                  # 工具链集成（决策树）
├── project-integration.skill.md        # 项目集成规则（复用优先）
├── lazy-detection.skill.md             # 懒惰检测防护（三级惩罚）
├── progressive-context.skill.md        # 渐进式上下文收集
│
├── ## 通用开发 Skills ##
├── code-review.skill.md                # 代码审查技能
├── typescript-best-practices.skill.md  # TypeScript 最佳实践
├── aios-development.skill.md           # AIOS 项目开发指南
├── git-workflow.skill.md               # Git 工作流程
└── debugging.skill.md                  # 调试指南
```

## 开发准则 Skills 概览

| Skill 文件 | 描述 | 优先级 |
|------------|------|--------|
| `context-retrieval` | **编码前必须执行**的7步强制检索清单和充分性验证 | 10 |
| `quality-verification` | 强制验证机制、评分体系（0-100分）和审查规范 | 10 |
| `workflow` | 标准工作流6步骤和研究-计划-实施5阶段模式 | 10 |
| `code-standards` | 强制中文、SOLID/DRY原则、实现标准 | 9 |
| `toolchain` | 工具选择决策树（desktop-commander/context7/github） | 9 |
| `project-integration` | 标准化+生态复用优先、代码库学习规则 | 9 |
| `lazy-detection` | 编码前/中/后检测和三级惩罚体系 | 8 |
| `progressive-context` | 渐进式收集流程和充分性检查 | 8 |

## 技能执行流程

```
1. 需求理解 → context-retrieval（7步检索）
2. 上下文收集 → progressive-context（渐进式收集）
3. 规划与执行 → workflow（工作流程）
4. 编码标准 → code-standards + lazy-detection
5. 工具使用 → toolchain（决策树）
6. 项目集成 → project-integration
7. 质量验证 → quality-verification（评分决策）
```

## 技能文件格式

每个技能文件使用 Markdown 格式，包含 YAML frontmatter：

```markdown
---
name: 技能名称
version: 1.0.0
description: 技能描述
category: development
keywords: [关键词1, 关键词2]
author: 作者
enabled: true
priority: 10
---

# 技能内容
...
```

## 关键强制规则摘要

### 语言规范
- ⚠️ **绝对强制使用简体中文**（代码标识符除外）

### 编码前必须
1. 完成7步强制检索
2. 通过充分性验证（7项检查）
3. 生成上下文摘要文件

### 质量决策
- ≥90分 → 通过
- 80-89分 → 需讨论
- <80分 → 退回

## 技能目录

### 用户级技能
`~/.aios/skills/` - 全局共享，所有项目可用

### 项目级技能
`.aios/skills/` - 本项目专用
