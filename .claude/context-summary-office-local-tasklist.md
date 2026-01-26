# 上下文摘要：Office 本地优先能力任务清单

## 任务范围
- 以本地 Office（Microsoft Office/WPS 桌面版）为主，输出 P0-P2 能力补齐任务列表。

## 现有实现概览
- 本地 Office 适配器：`aios/packages/daemon/src/adapters/office/OfficeLocalAdapter.ts`
  - 已有：Word 创建/读取、Excel 创建/读写范围/新增工作表、PPT 创建/读取幻灯片、文件列表/删除
- 现有云端：Microsoft365/Outlook/Google Workspace 适配器（作为参考，不作为主路径）

## 约束
- 本次仅输出任务列表，不改代码，不跑测试。
- 输出需简体中文。
