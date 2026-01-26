# 上下文摘要：Office 场景能力盘点与代码对齐

## 任务范围
- 深度联网检索 Office 办公场景常见能力（Word/Excel/PowerPoint/Outlook/OneDrive/协作等）。
- 对比 AIOS 项目现有适配器能力，识别缺口。

## 已发现的本地实现
- 本地 Office 适配器：`aios/packages/daemon/src/adapters/office/OfficeLocalAdapter.ts`
  - 能力：Word/Excel/PPT 的创建、读取/写入 Excel 范围、添加工作表、PPT 读取幻灯片、列出/删除文件
  - 平台：Windows COM、macOS/WPS UI 自动化、Linux WPS + xdotool

## SaaS/云端实现
- Microsoft 365 适配器：`aios/packages/daemon/src/adapters/productivity/Microsoft365Adapter.ts`
  - 能力：Word/Excel/PPT 创建与读取、Excel 范围读写、添加工作表、OneDrive 文件列表/删除
- Google Workspace 适配器：`aios/packages/daemon/src/adapters/productivity/GoogleDocsAdapter.ts`
  - 能力：Docs 创建/读取/追加文本、Sheets 创建/读写
- Outlook 适配器：`aios/packages/daemon/src/adapters/productivity/OutlookAdapter.ts`
  - 能力：发送邮件、列表、详情、回复、删除

## 风险与注意事项
- 工具优先级要求使用 desktop-commander 与 firecrawl/context7，但当前不可用，需要记录并改用 shell 与 fetch。
- 对比需以能力清单为主，避免超出 Office 场景范围。
