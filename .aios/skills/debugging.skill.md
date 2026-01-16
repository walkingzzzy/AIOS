---
name: Debugging Guide
version: 1.0.0
description: 系统化调试指南，提供问题诊断和解决的方法论
category: development
keywords: [调试, debug, 错误排查, 问题定位, troubleshooting]
author: AIOS Team
enabled: true
priority: 9
---

# 系统化调试指南

## 调试方法论

### 1. 问题定义（5W1H）
- **What**: 具体问题是什么？
- **When**: 什么时候发生？
- **Where**: 在哪里发生？
- **Who**: 影响谁？
- **Why**: 可能的原因？
- **How**: 如何复现？

### 2. 信息收集
- 错误消息和堆栈跟踪
- 日志文件内容
- 环境信息（Node 版本、OS 等）
- 最近的代码变更

### 3. 假设验证
```
1. 形成假设
2. 设计验证实验
3. 执行并观察结果
4. 确认或排除假设
5. 重复直到找到根因
```

## 调试工具

### Node.js / TypeScript
```bash
# 启用调试模式
node --inspect dist/index.js

# 使用 Chrome DevTools
chrome://inspect
```

### Electron
```javascript
// 在 main 进程
mainWindow.webContents.openDevTools();

// 在 renderer 进程
console.log() / debugger;
```

### 日志分析
```bash
# 实时查看日志
tail -f logs/app.log

# 过滤错误
grep -i "error" logs/app.log

# 时间范围过滤
awk '/2024-01-14 10:00/,/2024-01-14 11:00/' logs/app.log
```

## 常见问题模式

### 类型错误
- 检查 `undefined` 和 `null`
- 验证 API 响应结构
- 确认异步操作完成

### 性能问题
- 使用 profiler 定位热点
- 检查内存泄露
- 分析网络请求

### 并发问题
- 检查竞态条件
- 验证锁和同步机制
- 使用时序分析

## 调试清单

- [ ] 能否稳定复现？
- [ ] 是否检查了错误日志？
- [ ] 是否简化了复现步骤？
- [ ] 是否排除了环境因素？
- [ ] 是否检查了最近的变更？
