# 中国生态适配器落地任务清单

## 目标
- 按调研文档落地 CN 生态适配器与关键能力。
- 输出可调用的适配器能力 + 测试 + 验证报告。

## 任务列表
1. 新增 `adapters/cn` 目录与统一导出入口。
2. 实现 QQNT CDP 适配器（连接、列页、执行脚本、发送文本、读取消息）。
3. 实现 WPS AirScript 适配器（提交脚本、查询执行状态）。
4. 实现 飞书 适配器（发送卡片、创建文档）。
5. 实现 剪映草稿适配器（列项目、读取草稿、写入草稿）。
6. 可选：实现 微信 OCR 适配器（截图+OCR）。
7. 更新适配器注册与导出。
8. 补充单元测试覆盖新适配器能力。
9. 运行本地测试并输出验证报告。
10. 更新操作日志与编码后声明。

## 交付物
- 代码：`aios/packages/daemon/src/adapters/cn/*`
- 导出/注册：`aios/packages/daemon/src/adapters/index.ts`，`aios/packages/daemon/src/index.ts`
- 测试：`aios/packages/daemon/src/__tests__/adapters/*`
- 日志/报告：`.claude/operations-log.md`，`.claude/verification-report.md`
