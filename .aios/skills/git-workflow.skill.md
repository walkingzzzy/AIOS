---
name: Git Workflow
version: 1.0.0
description: Git 工作流程指南，包含分支管理、提交规范和常用操作
category: development
keywords: [git, 版本控制, 分支, commit, merge, rebase]
author: AIOS Team
enabled: true
priority: 7
---

# Git 工作流程指南

## 分支策略

采用 Git Flow 简化版：
- `main` - 生产分支，只接受 merge
- `develop` - 开发分支
- `feature/*` - 功能分支
- `fix/*` - 修复分支

## 提交规范

使用 Conventional Commits：

```
<type>(<scope>): <description>

[optional body]

[optional footer]
```

### Type 类型
- `feat`: 新功能
- `fix`: 修复 bug
- `docs`: 文档更新
- `style`: 代码格式（不影响功能）
- `refactor`: 重构
- `test`: 测试相关
- `chore`: 构建/工具链

### 示例
```
feat(skills): 添加技能注册表功能

- 实现 SkillRegistry 类
- 支持从 markdown 文件加载技能
- 添加关键词匹配算法

Closes #123
```

## 常用操作

### 创建功能分支
```bash
git checkout develop
git pull origin develop
git checkout -b feature/skill-system
```

### 合并请求前的准备
```bash
# 更新并 rebase
git fetch origin
git rebase origin/develop

# 如有冲突，解决后继续
git add .
git rebase --continue
```

### 紧急修复
```bash
git checkout main
git checkout -b fix/critical-bug
# 修复后合并到 main 和 develop
```

## 最佳实践

1. **小而频繁的提交** - 每个提交只做一件事
2. **描述性的提交信息** - 说明"为什么"而不仅是"做了什么"
3. **提交前检查** - 运行 `yarn typecheck` 和 `yarn test`
4. **保持历史整洁** - 使用 rebase 而非 merge 更新分支
