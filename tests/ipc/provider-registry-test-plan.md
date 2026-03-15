# AIOS Provider Registry Smoke Test Plan

## 范围

本计划验证 `agentd` 暴露的 provider registry 服务级闭环。

## 覆盖服务

- `agentd`

## 核心断言

### 1. registry RPC 可用

- `agentd` 能创建自己的 UDS socket
- `system.health.get` 返回 `ready`
- `provider.register` / `provider.unregister` / `provider.discover`
- `provider.resolve_capability` / `provider.get_descriptor`
- `provider.health.get` / `provider.health.report` / `provider.disable` / `provider.enable`

### 2. builtin descriptor 发现

- registry 能扫描 system / runtime / shell / compat descriptor 目录
- 至少发现 `system.intent.local`、`system.files.local`
- 至少发现 `runtime.local.inference`
- 至少发现 `shell.screen-capture.portal`
- 至少发现 browser / office / mcp-bridge / code-sandbox 四类 compat provider

### 3. capability resolution

- `system.intent.execute` 解析到 `system.intent.local`
- `provider.fs.open` 解析到 `system.files.local`
- `runtime.infer.submit` 解析到 `runtime.local.inference`
- `runtime.embed.vectorize` 解析到 `runtime.local.inference`
- `runtime.rerank.score` 解析到 `runtime.local.inference`
- `device.capture.screen.read` 解析到 `shell.screen-capture.portal`
- compat 各能力能解析到对应 provider

### 4. health report / disable / enable 生命周期

- `provider.health.report` 能把 builtin provider 标记为 `unavailable` / `available`
- `require_healthy=true` 时，`unavailable` provider 不再被 resolve 选中
- `provider.disable` 会把目标 provider 标记为 disabled
- disabled provider 不再出现在默认 discover / resolve 结果中
- `include_disabled=true` 时能看到 disabled provider
- `provider.enable` 后 provider 恢复可解析状态

### 5. dynamic register / unregister

- `provider.register` 能写入 dynamic descriptor 与 health state
- dynamic provider 能被 discover / resolve / get_descriptor 读取
- `provider.unregister` 后 descriptor 与 health state 文件被移除
- unregister 后 capability 不再可解析

## 运行入口

```bash
cargo build -p aios-agentd
scripts/test-provider-registry-smoke.py --bin-dir aios/target/debug
```

## 后续扩展

1. 增加多 provider 同 capability 的排序与降级用例
2. 增加损坏 descriptor / health 文件的恢复用例
3. 增加 provider worker runtime 与 registry 生命周期联动验证
