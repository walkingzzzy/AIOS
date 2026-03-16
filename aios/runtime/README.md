# runtime/

`runtime/` 是 AIOS 的推理后端、调度、预算与 route/profile 契约目录。  
它不是某个单一模型框架的源码目录，而是 `aios-runtimed` 的实现基础层。

## 1. 负责什么

此目录长期应承载：

- model wrapper
- queue / budget / timeout / backpressure 策略
- local / sandbox / attested-remote route policy
- `runtime-profile` / `route-profile` schema 与默认值
- backend plugin interface

## 2. 当前状态

截至 2026-03-16：

- 已有：`profiles/`、`platforms/`、`schemas/`、README、provider descriptors，以及 `runtimed` 侧已经落地的 scheduler / budget / queue / fallback / event surface
- 已有：`backend_worker_contract`、`managed_worker_commands`、`hardware_profile_managed_worker_commands`、`runtime-worker-v1` request/response schema，`local-gpu` / `local-npu` 可通过 `stdio` wrapper 或 `unix://` worker 执行
- 已有：`runtimed` 自主管理 `local-gpu` / `local-npu` managed unix worker 生命周期，在 runtime dir 下等待 socket ready 后把 worker socket 注入实际 backend command，并在 health notes 中暴露 contract / worker count / worker status/source/detail
- 已有：平台可通过 `/etc/aios/runtime/platform.env` 注入 `AIOS_RUNTIMED_HARDWARE_PROFILE_ID` 与 `AIOS_RUNTIMED_RUNTIME_PROFILE`；仓库现已提供 `platforms/nvidia-jetson-orin-agx/default-runtime-profile.yaml` 作为 Jetson runtime 基线，并通过 `bin/launch-managed-worker.sh` bridge 把 `local-gpu` / `local-npu` 转接到显式 `AIOS_JETSON_LOCAL_GPU_WORKER_COMMAND` / `AIOS_JETSON_LOCAL_NPU_WORKER_COMMAND` 或内置 `vendor_accel_worker.py`
- 已有：Jetson builtin vendor helper 会用 `AIOS_JETSON_TRTEXEC_BIN`、`AIOS_JETSON_VENDOR_ENGINE_ROOT` / `AIOS_JETSON_VENDOR_*_ENGINE_PATH`、`AIOS_JETSON_VENDOR_*_EXTRA_ARGS` 和 `AIOS_JETSON_VENDOR_EVIDENCE_DIR` 驱动 TensorRT / DLA，并把 machine-readable evidence 落到 runtimed state dir；`scripts/test-runtimed-jetson-platform-vendor-helper-smoke.py` 已覆盖这条正式 helper 路径
- 已有：Jetson bring-up 可临时打开 `AIOS_JETSON_ALLOW_REFERENCE_WORKER=1`（并配合 `AIOS_JETSON_REFERENCE_WORKER_PYTHON` / `AIOS_JETSON_REFERENCE_WORKER_PATH`）使用仓库内 reference worker 验证 managed worker 路径；`scripts/test-runtimed-jetson-platform-vendor-worker-smoke.py` 继续覆盖显式 vendor command bridge 成功路径
- 已有：未配置 vendor bridge / helper runtime 时会显式报 `launch-failed` 并回退到 `local-cpu`
- 已有：`runtime.queue.get` / `runtime.budget.get` / `runtime.events.get`、memory / kv / model 并行预算启发式准入、queue saturation telemetry、remote audit、GPU/NPU 不可用时的 CPU fallback，以及 managed worker / contract / backend / events / budget smoke
- 未有：实机 release-grade GPU sign-off、实机 release-grade NPU sign-off、跨服务 runtime 事件汇聚 sink

当前判断：`Partial Impl`

## 3. 技术基线

- 主控语言：Rust
- 与 `aios-runtimed` 配合使用
- 结构化契约：JSON Schema
- 配置对象：YAML / TOML

## 4. 当前最重要的目录目标

- `profiles/`：默认 profile 与示例 profile
- `platforms/`：平台专属 runtime profile 资产，供 image / installer / recovery 链路注入
- `schemas/`：profile schema、validation schema
- `backends/`：后续的 CPU / GPU / NPU / remote plugin interface
- `queue/`：后续的调度、预算、拒绝策略实现

## 5. 下一步

1. 在现有 managed worker / contract 基础上接入真实 vendor GPU runtime
2. 在现有 managed worker / contract 基础上接入真实 vendor NPU runtime
3. 导出更正式的 runtime observability / cross-service event sink
4. 增加更真实的 backend / fallback / image-device 级联验证
