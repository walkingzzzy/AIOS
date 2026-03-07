# SaaS 适配器 E2E 测试指南

> **系统开发口径修订（2026-03-08）**
> AIOS 统一定义为 **AI 原生操作系统 / 系统软件工程**。本文如提及桌面应用、Electron 客户端、应用适配器、App 安装等内容，除非明确标注为“原型期 / 兼容层 / 历史实现”，否则不再代表目标形态。
> 当前最高约束：**系统镜像、系统服务、系统壳层、设备/能力抽象、权限与更新恢复**。


本文档提供 Spotify/Slack/Gmail/Notion 适配器的可选 E2E 测试脚本与环境配置说明。

## 前置条件
- 真实模式需构建 daemon：`pnpm --filter @aios/daemon build`
- 按需准备 OAuth 或 Token 凭证
- 使用真实环境执行（测试会调用真实 API）
- 无 SaaS 环境时可启用 mock 模式跳过真实调用

## 脚本入口
```bash
node scripts/integration/saas-smoke.mjs
```

## 启用开关
- `AIOS_E2E_MOCK=1`（mock 模式，仅验证脚本流程）
- `AIOS_E2E_SPOTIFY=1`
- `AIOS_E2E_SLACK=1`
- `AIOS_E2E_GMAIL=1`
- `AIOS_E2E_NOTION=1`
- `AIOS_E2E_FEISHU=1`
- `AIOS_E2E_WPS=1`

## Mock 模式说明
- 启用 `AIOS_E2E_MOCK=1` 后将跳过真实 API 调用与凭证校验
- 若未设置任何 `AIOS_E2E_*` 场景开关，将默认执行全部场景（仅 mock）
- mock 模式下不会校验 daemon 构建产物
- 建议与具体场景开关组合使用，便于定位流程问题

## 重要环境变量
### Spotify
- `SPOTIFY_CLIENT_ID`
- `SPOTIFY_CLIENT_SECRET`
- `AIOS_SPOTIFY_QUERY`（可选，默认 AIOS）
- 需完成 OAuth 授权并在本地存储生成 token

### Slack
- `SLACK_BOT_TOKEN`
- `AIOS_SLACK_SEND=1`（可选，启用发送消息）
- `AIOS_SLACK_CHANNEL`（发送消息时必填）
- `AIOS_SLACK_TEXT`（可选）

### Gmail
- `GOOGLE_CLIENT_ID`
- `GOOGLE_CLIENT_SECRET`
- `AIOS_GMAIL_SEND=1`（可选，启用发送邮件）
- `AIOS_GMAIL_TO`（发送邮件时必填）
- `AIOS_GMAIL_SUBJECT` / `AIOS_GMAIL_BODY`（可选）
- `AIOS_GMAIL_MAX`（列表数量，默认 5）
- 需完成 OAuth 授权并在本地存储生成 token

### Notion
- `NOTION_TOKEN`
- `AIOS_NOTION_QUERY`（可选，默认 AIOS）

### 飞书
- `FEISHU_APP_ID`
- `FEISHU_APP_SECRET`
- `FEISHU_TENANT_ACCESS_TOKEN`（或 `LARK_TENANT_ACCESS_TOKEN`）
- `AIOS_FEISHU_TITLE`（可选，默认 AIOS E2E 文档）
- `AIOS_FEISHU_FOLDER_TOKEN`（可选）

### WPS AirScript
- `AIOS_WPS_FILE_ID`
- `WPS_ACCESS_TOKEN`（或 `KDOCS_ACCESS_TOKEN`）

## 运行示例
```bash
AIOS_E2E_SLACK=1 SLACK_BOT_TOKEN=xxx node scripts/integration/saas-smoke.mjs
```

```bash
AIOS_E2E_MOCK=1 AIOS_E2E_SPOTIFY=1 AIOS_E2E_FEISHU=1 node scripts/integration/saas-smoke.mjs
```

```bash
AIOS_E2E_FEISHU=1 FEISHU_APP_ID=xxx FEISHU_APP_SECRET=xxx FEISHU_TENANT_ACCESS_TOKEN=xxx node scripts/integration/saas-smoke.mjs
```

```bash
AIOS_E2E_WPS=1 AIOS_WPS_FILE_ID=xxx WPS_ACCESS_TOKEN=xxx node scripts/integration/saas-smoke.mjs
```

## 结果判定
- 任意用例失败会返回非 0 退出码
- 日志会输出每个用例的 OK/FAIL 与错误原因

## 常见问题
- 若适配器显示不可用，请确认已配置 OAuth/Token 并完成授权流程
- Slack/Gmail 的发送类动作可能触发权限校验或提示，请确保权限已授予
