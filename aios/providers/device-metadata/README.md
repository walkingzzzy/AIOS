# aios-device-metadata-provider

`aios-device-metadata-provider` 把 `device.metadata.get` 从静态 descriptor 变成真实的 first-party provider worker。

## 当前能力

- 通过 UDS + JSON-RPC 暴露 `device.metadata.get`
- 启动后向 `agentd` 自注册并上报 provider health
- 运行时向 `deviced` 调用 `device.state.get`
- 将 capability / backend / adapter 三层状态汇总成统一 metadata 响应
- 在 metadata 响应里补 `summary` readiness 摘要与 `ui_tree_support_matrix`
- 在 `deviced` 掉线 / 恢复时通过后台 health sync 向 registry 反映 `unavailable -> available` 收敛

## 当前边界

- 只提供只读 metadata，不执行 capture
- 仍依赖 `deviced` 的 backend snapshot，而不是直接接 PipeWire / libinput / camera driver
- 尚未接入 `agentd` 的正式 intent 执行闭环
- 设备 readiness 的 release-grade 完成度仍受 `deviced` 原生 backend 与 `ui_tree` 支持矩阵成熟度限制

## 联调约定

- `device.metadata.get` 直接透传 `deviced` 的 `backend_summary`，不在 provider 内重复推导 backend 整体状态
- metadata `notes` 会稳定暴露 `backend_overall_status`、`backend_available_status_count`、`backend_attention_count`
- provider `system.health.get` 会稳定暴露 `device_backend_overall_status`、`device_backend_available_status_count`、`device_backend_attention_count`
- `ui_tree_support_matrix` 与 `backend_summary.ui_tree_capture_mode` 共同作为 shell / hardware / provider 的统一 UI 树能力描述