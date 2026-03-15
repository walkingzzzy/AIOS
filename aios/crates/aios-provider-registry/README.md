# aios-provider-registry

`aios-provider-registry` 是 AIOS 当前 Phase 3 的 provider registry shared library。

## 角色

它负责：

- 加载 provider descriptor
- 建立 capability → provider 候选集
- 解析 capability 对应的 provider
- 维护 provider health report / health query / disable / enable 状态
- 为 `agentd` / `policyd` / 后续 shell flow 提供统一解析入口

它当前**不是独立 daemon**；服务级生命周期 RPC 由 `agentd` 代为暴露。

## 当前实现范围

已实现：

- `provider.register`
- `provider.unregister`
- `provider.discover`
- `provider.resolve_capability`
- `provider.get_descriptor`
- `provider.health.get`
- `provider.health.report`
- `provider.disable`
- `provider.enable`
- JSON / YAML descriptor loader
- static descriptor dirs + dynamic state dir 合并加载
- `agentd` RPC 接线与 registry smoke harness

未实现：

- 独立 `registryd`
- descriptor 签名校验
- registry-owned provider worker 生命周期管理

## 存储模型

默认由调用方传入 `state_dir`，目录下当前使用：

- `descriptors/`：动态注册的 provider descriptor
- `health/`：health / disabled 状态

静态 descriptor 通过 `descriptor_dirs` 扫描。

## 当前接入点

- `aios/services/agentd/src/main.rs`
- `aios/services/agentd/src/providers.rs`
- `aios/services/agentd/src/rpc.rs`
- `scripts/test-provider-registry-smoke.py`

## 相关契约

- `aios/crates/aios-contracts/src/lib.rs`
- `aios/sdk/schemas/provider-descriptor.schema.json`
- `docs/system-development/14-provider-registry-与-portal-规范.md`
