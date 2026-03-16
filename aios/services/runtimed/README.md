# aios-runtimed

## 1. 角色

`aios-runtimed` 是 AIOS 的运行时与推理调度服务。  
它不是某个单一模型框架的别名，而是统一管理本地 / 条件后端、预算、队列、降级与拒绝策略的系统服务。

核心职责：

- 本地模型后端包装
- CPU / GPU / NPU 预算与队列
- runtime profile / route profile 生效
- local / sandbox / attested remote 路由
- 资源不足时安全降级
- fallback 与拒绝策略

## 2. 不负责什么

- 不负责最终审批
- 不负责长期会话持久化
- 不负责直接决定 trusted offload 的授权
- 不把高风险 route 视为天然合法

## 3. 推荐技术路线

- 语言：Rust
- async runtime：Tokio
- 结构：scheduler + backend plugin
- 通信：UDS + JSON-RPC
- 可观测性：budget / route / degrade events

## 4. backend 策略

- `local-cpu`：基线后端，必须长期可用
- `local-gpu`：主要加速后端，按支持矩阵启用
- `local-npu`：条件后端，仅在声明支持的 hardware profile 上启用
- `attested-remote`：条件执行位置，需 policy / audit / attestation 完整

## 5. 推荐目录结构

```text
runtimed/
├── src/
│   ├── main.rs
│   ├── config.rs
│   ├── rpc.rs
│   ├── scheduler.rs
│   ├── queue.rs
│   ├── budget.rs
│   ├── backend/
│   │   ├── mod.rs
│   │   ├── cpu.rs
│   │   ├── gpu.rs
│   │   ├── npu.rs
│   │   └── remote.rs
│   └── errors.rs
├── tests/
├── service.yaml
└── units/
```

## 6. 当前实现状态

- 仓库状态：`In Progress`
- 已落地 backend：
  - `local-cpu`：内建 worker，可在无额外依赖时稳定执行
  - `attested-remote`：真实 HTTP request/response 或 wrapper 路径，要求 `execution_token`，并绑定到当前配置的 remote target hash
  - `local-gpu`：支持 shell wrapper 或 `unix://` 本地 worker，readiness / capability / fallback 已落地，不会在不可用时伪装成功；`runtimed` 现在也可按 runtime profile / hardware profile / env 自主管理 managed unix worker
  - `local-npu`：支持 shell wrapper 或 `unix://` 本地 worker；未配置或设备缺失时明确 capability-gated，并支持与 `local-gpu` 同类的 managed unix worker 生命周期与 hardware-profile 命令选择
- 已落地事件面：
  - `runtime.backend.health`
  - `runtime.infer.submit`
  - `runtime.infer.admitted`
  - `runtime.infer.started`
  - `runtime.infer.completed`
  - `runtime.infer.rejected`
  - `runtime.infer.failed`
  - `runtime.infer.timeout`
  - `runtime.infer.fallback`
  - `runtime.infer.degraded`
  - `runtime.events.get` 支持 `session_id` / `task_id` / `kind` / `limit` / `reverse`
  - 事件会落盘到 JSONL，查询优先走完整持久化日志；即使超过内存 ring 容量、服务重启后也仍可查询历史事件
  - `runtime.backend.health` 与 `runtime.infer.*` payload 现已统一为稳定字段，便于 shell / operator / platform 直接消费
  - managed worker 生命周期变化（包括自动重启、restart-exhausted 与 shutdown）会触发 `runtime.backend.health` 重新发射，保证 health / events / observability 一致
  - runtime trace 与 attested-remote audit 会镜像到统一 `observability.jsonl` sink，便于团队 4/5 与恢复链路消费
  - `observability.jsonl` sink 会通过 `aios-core::schema` 按 trace schema 做 runtime validation，并把 `backend_id` / `route_state` / `health_state` 等关键字段镜像到顶层输出
  - `system.contract.get` manifest 与结构化 RPC error code 已接入 shared governance 基线
- 已落地 enforcement：
  - queue saturation reject
  - memory / kv / parallel budget reject
  - timeout reject / fallback
  - attested-remote token 校验与审计
- 已冻结 scheduler / backend 边界：
  - `runtime.backend.list` 输出稳定 backend health 字段：`backend_id` / `availability` / `activation` / `health_state` / `reason` / `fallback_backend` / `worker_contract` / `worker_state` / `command_source` / `socket_path`
  - `runtime.backend.health` 与 `runtime.infer.*` payload 使用同一套稳定字段，并把关键字段镜像到 observability 顶层
  - `RuntimeBackend` trait 稳定为 `backend_id` / `readiness` / `descriptor` / `execute` 四元接口
  - `aios/services/runtimed/src/backend/mod.rs` 内联单测覆盖 descriptor、readiness 与 wrapper / inlined execution 路径
- 已有 smoke：
  - `scripts/test-runtimed-backend-smoke.py`
  - `scripts/test-runtimed-worker-contract-smoke.py`
  - `scripts/test-runtimed-managed-worker-smoke.py`
  - `scripts/test-runtimed-managed-worker-restart-smoke.py`
  - `scripts/test-runtimed-managed-worker-restart-exhausted-smoke.py`
  - `scripts/test-runtimed-hardware-profile-managed-worker-smoke.py`
  - `scripts/test-runtimed-jetson-platform-worker-smoke.py`
  - `scripts/test-runtimed-jetson-platform-vendor-helper-smoke.py`
  - `scripts/test-runtimed-jetson-platform-vendor-worker-smoke.py`
  - `scripts/test-runtimed-jetson-platform-worker-failure-smoke.py`
  - `scripts/test-runtimed-budget-smoke.py`
  - `scripts/test-runtimed-events-smoke.py`
- 仍未完成：
  - 实机 release-grade GPU sign-off
  - 实机 release-grade NPU sign-off

## 7. 关键环境变量

- `AIOS_RUNTIMED_LOCAL_CPU_COMMAND`
- `AIOS_RUNTIMED_LOCAL_GPU_COMMAND`
- `AIOS_RUNTIMED_LOCAL_NPU_COMMAND`
- `AIOS_RUNTIMED_LOCAL_GPU_WORKER_COMMAND`
- `AIOS_RUNTIMED_LOCAL_NPU_WORKER_COMMAND`
- `AIOS_RUNTIMED_HARDWARE_PROFILE_ID`
- `AIOS_RUNTIMED_MANAGED_WORKER_RESTART_BACKOFF_MS`
- `AIOS_RUNTIMED_MANAGED_WORKER_RESTART_LIMIT`
- `AIOS_RUNTIMED_BACKEND_HEALTH_POLL_MS`
- `AIOS_RUNTIMED_ATTESTED_REMOTE_COMMAND`
- `AIOS_RUNTIMED_POLICYD_SOCKET`
- `AIOS_RUNTIMED_REMOTE_AUDIT_LOG`
- `AIOS_RUNTIMED_OBSERVABILITY_LOG`
- `AIOS_RUNTIMED_RUNTIME_PROFILE`
- `AIOS_RUNTIMED_ROUTE_PROFILE`
- `AIOS_JETSON_LOCAL_GPU_WORKER_COMMAND`
- `AIOS_JETSON_LOCAL_NPU_WORKER_COMMAND`
- `AIOS_JETSON_VENDOR_WORKER_PYTHON`
- `AIOS_JETSON_VENDOR_WORKER_PATH`
- `AIOS_JETSON_VENDOR_EVIDENCE_DIR`
- `AIOS_JETSON_VENDOR_ENGINE_ROOT`
- `AIOS_JETSON_TRTEXEC_BIN`
- `AIOS_JETSON_VENDOR_GPU_PROVIDER`
- `AIOS_JETSON_VENDOR_GPU_PROVIDER_ID`
- `AIOS_JETSON_VENDOR_GPU_ENGINE_PATH`
- `AIOS_JETSON_VENDOR_GPU_EXTRA_ARGS`
- `AIOS_JETSON_VENDOR_NPU_PROVIDER`
- `AIOS_JETSON_VENDOR_NPU_PROVIDER_ID`
- `AIOS_JETSON_VENDOR_NPU_ENGINE_PATH`
- `AIOS_JETSON_VENDOR_NPU_EXTRA_ARGS`
- `AIOS_JETSON_VENDOR_NPU_DLA_CORE`
- `AIOS_JETSON_ALLOW_REFERENCE_WORKER`
- `AIOS_JETSON_REFERENCE_WORKER_PYTHON`
- `AIOS_JETSON_REFERENCE_WORKER_PATH`

默认镜像 / 安装链路可通过 `/etc/aios/runtime/platform.env` 向 systemd unit 注入 `AIOS_RUNTIMED_HARDWARE_PROFILE_ID` 与 `AIOS_RUNTIMED_RUNTIME_PROFILE`，把平台介质里的 `hardware_profile_id` 和平台专属 runtime profile 自动传给 `runtimed`。`nvidia-jetson-orin-agx` 平台额外提供 `launch-managed-worker.sh` bridge：若设置 `AIOS_JETSON_LOCAL_GPU_WORKER_COMMAND` / `AIOS_JETSON_LOCAL_NPU_WORKER_COMMAND`，bridge 会走显式 vendor command；否则默认落到仓库内置的 `vendor_accel_worker.py`，通过 `AIOS_JETSON_TRTEXEC_BIN`、`AIOS_JETSON_VENDOR_ENGINE_ROOT` / `AIOS_JETSON_VENDOR_*_ENGINE_PATH`、`AIOS_JETSON_VENDOR_*_EXTRA_ARGS` 和 `AIOS_JETSON_VENDOR_EVIDENCE_DIR` 驱动 TensorRT / DLA 执行与证据落盘。bring-up 阶段也可临时使用 `AIOS_JETSON_ALLOW_REFERENCE_WORKER=1` 走 reference worker；vendor helper 缺少 runtime binary 或 engine 时 health notes 会记成 `launch-failed`，调度则安全回退到 `local-cpu`。

## 8. 验证

建议至少执行：

```bash
cargo test --workspace --offline
cargo build -p aios-runtimed -p aios-policyd --offline
python3 scripts/test-runtimed-backend-smoke.py --bin-dir aios/target/debug
python3 scripts/test-runtimed-worker-contract-smoke.py --bin-dir aios/target/debug
python3 scripts/test-runtimed-managed-worker-smoke.py --bin-dir aios/target/debug
python3 scripts/test-runtimed-managed-worker-restart-smoke.py --bin-dir aios/target/debug
python3 scripts/test-runtimed-managed-worker-restart-exhausted-smoke.py --bin-dir aios/target/debug
python3 scripts/test-runtimed-hardware-profile-managed-worker-smoke.py --bin-dir aios/target/debug
python3 scripts/test-runtimed-jetson-platform-worker-smoke.py --bin-dir aios/target/debug
python3 scripts/test-runtimed-jetson-platform-vendor-helper-smoke.py --bin-dir aios/target/debug
python3 scripts/test-runtimed-jetson-platform-vendor-worker-smoke.py --bin-dir aios/target/debug
python3 scripts/test-runtimed-jetson-platform-worker-failure-smoke.py --bin-dir aios/target/debug
python3 scripts/test-runtimed-budget-smoke.py --bin-dir aios/target/debug
python3 scripts/test-runtimed-events-smoke.py --bin-dir aios/target/debug
```

在 Windows / 不支持 POSIX Unix Domain Socket 的 Python 环境中，上述 runtimed smoke 会快速提示 `This smoke harness requires Python socket.AF_UNIX support`；`scripts/run-aios-ci-local.py` 也会把这类步骤标记为 `skipped`，避免把平台限制误记成 runtime 回归。

## 9. 下一步

1. 在现有 managed worker lifecycle 基础上接入 vendor GPU runtime
2. 在现有 managed worker / contract 基础上接入 vendor NPU runtime
3. 扩展 runtime observability exporter 与更多消费方联调
4. 扩展跨服务联调和 image / device 级联验证
