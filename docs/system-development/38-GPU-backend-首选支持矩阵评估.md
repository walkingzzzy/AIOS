# GPU backend 首选支持矩阵评估

**状态**: `Baseline Delivered / Release-Grade Hardware Pending`  
**更新日期**: 2026-03-14  
**关联任务**: `P5-GPU-001`、`P5-GPU-002`、`P5-GPU-003`、`P5-GPU-004`

---

## 1. 目的

本文件用于冻结 AIOS 当前 `GPU backend` 的首选支持矩阵、平台优先级判断、降级规则与验证证据。

当前结论不是宣称“GPU 路线已经 release-grade 完成”，而是确认：

1. `local-cpu` 仍是全平台默认运行时下限
2. `local-gpu` 已形成可声明的条件能力与优先平台判断
3. `nvidia-jetson-orin-agx` 已拥有仓库级最完整的 GPU 路线资产
4. GPU 路线的 machine-readable 结论已经落入 `aios/runtime/gpu-backend-support-matrix.yaml`

---

## 2. 当前首选后端判断

### 2.1 全局默认结论

- `local-cpu` 是唯一可以跨平台默认宣称的运行时基线
- `local-gpu` 只能按 `hardware profile` 单独声明
- 任何 GPU 路线都必须保留 `cpu_fallback=true`

### 2.2 为什么当前不能把 `local-gpu` 设为全平台默认

- 仓库已经有 `local-gpu` backend skeleton、wrapper 路径、budget accounting 与 GPU -> CPU fallback
- 但仓库仍未接入 release-grade 的真实 vendor GPU runtime
- `generic-x86_64-uefi` 目前没有像 Jetson 那样的专属 runtime profile 与 managed worker bridge 资产
- 因此当前最稳妥的全局默认仍应是 `local-cpu`

### 2.3 当前优先平台判断

截至 2026-03-14，AIOS 当前最强的仓库级 GPU 路线是：

1. `nvidia-jetson-orin-agx`
2. 其余平台继续保持 `local-cpu` 默认

原因：

- Jetson 已有独立 runtime profile
- Jetson 已有 `launch-managed-worker.sh` bridge
- Jetson 已有 managed worker 成功 smoke 与失败降级 smoke
- Jetson 平台资产已被 platform media / image delivery 路径打包验证

---

## 3. 已落地实现基线

### 3.1 Runtime 基线

- `aios/services/runtimed/src/backend/gpu.rs`
  已定义 `local-gpu` backend，可根据显式 wrapper 或设备节点状态给出 readiness
- `aios/services/runtimed/src/scheduler.rs`
  已接入 GPU 预算计数与降级路径
- `aios/runtime/profiles/default-runtime-profile.yaml`
  继续把 `local-cpu` 设为默认，同时保留 `local-gpu` 作为可声明后端

### 3.2 Jetson 平台基线

- `aios/runtime/platforms/nvidia-jetson-orin-agx/default-runtime-profile.yaml`
  已把 `default_backend` 设为 `local-gpu`
- `aios/runtime/platforms/nvidia-jetson-orin-agx/bin/launch-managed-worker.sh`
  已作为 `local-gpu` / `local-npu` 的统一 bridge
- `AIOS_JETSON_ALLOW_REFERENCE_WORKER=1`
  可在 bring-up 阶段启用 reference worker，用于先验证 managed worker contract 与路由

### 3.3 Machine-readable 资产

- `aios/runtime/gpu-backend-support-matrix.yaml`
  冻结当前后端分层、平台偏好、支持状态与证据脚本
- `scripts/test-gpu-backend-support-matrix-smoke.py`
  校验文档、matrix、默认 profile、Jetson profile 与证据路径是否一致

---

## 4. 首选支持矩阵

| 硬件 / 平台 | runtime profile | 当前首选 backend | 当前支持状态 | 当前可对外口径 |
|------|------|------|------|------|
| `qemu-x86_64` | `aios/runtime/profiles/default-runtime-profile.yaml` | `local-cpu` | `repo-qemu-validated` | 仅能证明 wrapper / fallback 语义，不代表真实 GPU 支持 |
| `generic-x86_64-uefi` | `aios/runtime/profiles/default-runtime-profile.yaml` | `local-cpu` | `platform-media-exportable` | 可交付平台介质，但不能宣称 GPU 支持已成立 |
| `nvidia-jetson-orin-agx` | `aios/runtime/platforms/nvidia-jetson-orin-agx/default-runtime-profile.yaml` | `local-gpu` | `bringup-kit-validated` | 可宣称已冻结 Jetson GPU bring-up 路线；不能宣称 release-grade Jetson GPU 支持 |

### 4.1 当前规则

- 若没有平台专属 GPU runtime 资产，默认首选仍是 `local-cpu`
- 若平台 profile 显式声明 `local-gpu` 且有 managed worker / wrapper 证据，才允许把 `local-gpu` 写成该平台首选
- 若 GPU worker 启动失败，必须回退到 `local-cpu`

---

## 5. 验证证据

### 5.1 通用 GPU wrapper / fallback 证据

- `scripts/test-runtimed-backend-smoke.py`
  验证 `unix://` GPU worker wrapper、`runtime.infer.submit`、backend availability 与 budget 计数
- `scripts/test-runtime-local-inference-provider-smoke.py`
  验证 provider façade 能保持 `preferred_backend=local-gpu` 语义并返回 runtimed wrapper 结果

### 5.2 Hardware-profile managed worker 证据

- `scripts/test-runtimed-hardware-profile-managed-worker-smoke.py`
  验证 `hardware_profile_managed_worker_commands` 可把 `local-gpu` / `local-npu` 激活为 `configured-unix-worker`

### 5.3 Jetson 平台成功路径证据

- `scripts/test-runtimed-jetson-platform-worker-smoke.py`
  验证 Jetson runtime profile、worker bridge、reference worker 与 `local-gpu` / `local-npu` 路由成立
- `scripts/test-image-delivery-smoke.py`
  验证 delivery bundle 已打包 Jetson runtime profile 与 managed worker bridge 资产
- `scripts/test-platform-media-smoke.py`
  验证 platform media / installer overlay 已携带 Jetson runtime profile、worker bridge 与 support docs

### 5.4 Jetson 平台失败降级证据

- `scripts/test-runtimed-jetson-platform-worker-failure-smoke.py`
  验证未配置 vendor bridge 时，`runtimed` 会显式报 `managed_worker.local-gpu=launch-failed`，并降级到 `local-cpu`

---

## 6. 当前声明边界

### 6.1 可以宣称的内容

- AIOS 已完成 `local-gpu` 条件能力的首选支持矩阵评估
- AIOS 已明确 `local-cpu` 是当前全平台默认运行时基线
- AIOS 已明确 `nvidia-jetson-orin-agx` 是当前仓库内 GPU 路线最完整的平台目标
- AIOS 已具备 GPU 成功路径与失败降级路径的最小 smoke 证据

### 6.2 不能宣称的内容

- 不能宣称所有 Tier 1 平台都已支持 `local-gpu`
- 不能宣称 Jetson 已完成 release-grade GPU 支持
- 不能把 QEMU / wrapper smoke 当作真实 vendor GPU 性能或稳定性证明
- 不能移除 `CPU fallback` 再继续宣称 GPU 路线可安全交付

---

## 7. 对任务状态的结论

按当前任务口径，`P5-GPU-001` 的目标是“评估 GPU backend 首选支持矩阵”，而不是“完成真实 vendor GPU runtime”。

截至 2026-03-14，该任务的完成依据已经成立：

- 已有 runtime / platform 仓库产物
- 已有 machine-readable matrix
- 已有成功路径与失败降级证据
- 已有正式评估文档与支持声明口径

因此 `P5-GPU-001` 可以进入 `Done`。

但后续仍有明确剩余项：

- 真实 vendor GPU runtime integration
- Tier 1 实机 GPU bring-up 证据
- release-grade 稳定性与性能报告
- `P5-HW-001` 之后的正式机器收敛与实机报告

---

## 8. 当前结论

截至 2026-03-14，AIOS 对 GPU backend 的最准确表述应为：

> `local-cpu` 仍是 AIOS 当前唯一的全平台默认运行时基线；`local-gpu` 已形成条件能力、支持矩阵与失败降级闭环，其中 `nvidia-jetson-orin-agx` 是当前仓库内首选的 GPU 平台路径，但真实 vendor runtime 与实机 release-grade 证据仍待后续硬件任务收口。
