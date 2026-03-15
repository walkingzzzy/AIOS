# capabilities/

此目录存放 `policyd` 使用的 capability catalog 与风险元数据。

当前已提供：

- `default-capability-catalog.yaml`

当前范围：

- capability 风险等级
- 默认审批 lane
- taint tags
- prompt-injection-sensitive 标记

当前未覆盖：

- 更细的 provider-level capability 分层
- capability 版本化与迁移元数据

当前命名空间：

- `system.*`
- `runtime.*`
- `service.*`
- `shell.*`
- `device.*`
- `compat.*`
