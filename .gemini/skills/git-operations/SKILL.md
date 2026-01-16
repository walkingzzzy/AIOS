---
name: git-operations
description: Git 工作流规范，包含提交信息格式、分支策略、PR 最佳实践和版本管理
---

# Git 操作规范

## 提交信息格式

### Conventional Commits
```
<type>(<scope>): <description>

[body]

[footer]
```

### Type 类型

| Type | 描述 |
|------|------|
| feat | 新功能 |
| fix | 修复 bug |
| docs | 文档更新 |
| style | 代码格式（不影响功能） |
| refactor | 重构（不新增功能或修复bug） |
| test | 测试相关 |
| chore | 构建/工具链 |
| perf | 性能优化 |

### 示例
```
feat(用户模块): 添加用户注册功能

- 实现邮箱验证
- 添加密码强度检查
- 创建用户表结构

Closes #123
```

---

## 分支策略

### Git Flow 简化版
```
main       ← 生产分支，只接受 merge
  ↑
develop    ← 开发分支
  ↑
feature/*  ← 功能分支
fix/*      ← 修复分支
```

### 分支命名
```
feature/用户认证
fix/登录失败处理
docs/更新README
refactor/优化查询性能
```

---

## PR/MR 最佳实践

### 创建 PR 前
```
✅ 本地测试通过
✅ 代码自审完成
✅ 与目标分支同步
✅ 提交历史整洁
```

### PR 描述模板
```markdown
## 变更类型
- [ ] 新功能
- [ ] Bug 修复
- [ ] 重构
- [ ] 文档

## 变更描述
[简述变更内容]

## 测试方式
[如何测试这些变更]

## 相关 Issue
Closes #xxx
```

### PR 大小
- ✅ 单一职责，小而专注
- ✅ 理想：<300 行变更
- ❌ 避免：>500 行的超大 PR

---

## 常用操作

### 同步分支
```bash
git fetch origin
git rebase origin/develop
```

### 合并提交
```bash
git rebase -i HEAD~3  # 合并最近3个提交
```

### 撤销操作
```bash
git reset --soft HEAD~1  # 撤销提交，保留更改
git checkout -- <file>   # 撤销文件修改
```

---

## 禁止行为

- ❌ 在 main/develop 直接提交
- ❌ 强制推送到共享分支
- ❌ 提交敏感信息（密钥、密码）
- ❌ 提交大型二进制文件
- ❌ 使用模糊的提交信息
