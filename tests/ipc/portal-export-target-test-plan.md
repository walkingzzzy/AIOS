# AIOS Portal Export Target Smoke Test Plan

## 范围

本计划验证 `agentd` / `sessiond` / `aios-portal` 之间的 export target handle 最小闭环。

## 覆盖服务

- `agentd`
- `sessiond`
- `aios-portal`

## 核心断言

### 1. export intent 解析

- `agent.intent.submit` 对导出意图返回 `compat.office.export_pdf`
- provider 解析到 `compat.office.document.local`

### 2. export target handle 签发

- `agentd` 能从 intent 中提取输出路径
- `portal_handle.kind` 为 `export_target_handle`
- handle scope 包含 `target` / `target_path` / `target_hash`

### 3. session 绑定

- `portal.handle.list` 能在同一 session 下列出 export target handle
- file handle 与 export target handle 能同时存在

## 运行入口

```bash
cargo build -p aios-agentd -p aios-sessiond -p aios-policyd -p aios-runtimed
scripts/test-ipc-smoke.py --bin-dir aios/target/debug
```

## 后续扩展

1. 增加 chooser / export target UI 交互验证
2. 增加 provider worker 对 export target handle 的实际消费验证
3. 增加目录导出与文件覆盖策略用例
