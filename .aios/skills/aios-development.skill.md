---
name: AIOS Development
version: 1.0.0
description: AIOS 项目开发指南，包含架构理解、开发规范和常用命令
category: development
keywords: [aios, electron, mcp, daemon, 开发, 架构]
author: AIOS Team
enabled: true
priority: 10
---

# AIOS 项目开发指南

## 项目架构

AIOS 是一个基于 Electron 的智能操作系统项目，采用 monorepo 架构：

```
aios/
├── packages/
│   ├── daemon/         # MCP 服务守护进程
│   ├── shared/         # 共享类型和工具
│   └── client/         # Electron 客户端
```

## 常用命令

### 开发
```bash
# 启动开发服务
yarn dev

# 类型检查
yarn typecheck

# 构建项目
yarn build
```

### 测试
```bash
# 运行单元测试
yarn test

# 运行特定测试
yarn test -- --grep "SkillRegistry"
```

## 开发规范

### 1. 代码组织
- 服务类放在 `src/core/` 或 `src/services/`
- 类型定义使用独立的 `types.ts`
- 导出统一通过 `index.ts`

### 2. 命名约定
- 文件名：PascalCase 用于类，kebab-case 用于工具
- 类名：PascalCase
- 方法/变量：camelCase
- 常量：UPPER_SNAKE_CASE

### 3. 错误处理
```typescript
try {
    await operation();
} catch (error) {
    console.error('[ServiceName] Operation failed:', error);
    throw new AIOSError('OPERATION_FAILED', error);
}
```

## MCP 工具开发

添加新工具时：
1. 在 `src/tools/` 下创建工具文件
2. 实现 `Tool` 接口
3. 在对应的 `index.ts` 中注册
4. 添加单元测试

## 调试技巧

- 使用 `DEBUG=aios:*` 环境变量启用调试日志
- Electron DevTools: `Cmd/Ctrl + Shift + I`
- MCP 消息日志在 `logs/` 目录下
