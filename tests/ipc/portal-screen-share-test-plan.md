# AIOS Portal Screen Share Smoke Test Plan

## 范围

本计划验证 `agentd` / `sessiond` / `aios-portal` 之间的 screen share handle 最小闭环。

## 覆盖服务

- `agentd`
- `sessiond`
- `aios-portal`

## 核心断言

### 1. screen intent 解析

- `agent.intent.submit` 对 screen share 意图返回 `device.capture.screen.read`
- provider 解析到 `shell.screen-capture.portal`

### 2. screen share handle 签发

- `agentd` 能为 screen share 意图派生 portal target
- `portal_handle.kind` 为 `screen_share_handle`
- handle `target` 使用 `screen://...` 或 `window://...`
- handle scope 包含 `target` / `target_path` / `target_hash`

### 3. session 绑定

- `portal.handle.list` 能在同一 session 下列出 `screen_share_handle`
- file handle、export target handle 与 screen share handle 能同时存在

## 运行入口

```bash
cargo build -p aios-agentd -p aios-sessiond -p aios-policyd -p aios-runtimed
scripts/test-ipc-smoke.py --bin-dir aios/target/debug
```

## 后续扩展

1. 增加 chooser UI 对 screen/window 目标选择的交互验证
2. 增加真实 ScreenCast / PipeWire backend 对 `screen_share_handle` 的消费验证
3. 增加多显示器与 focused-window 精确目标选择用例
