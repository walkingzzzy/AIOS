# 41 · NVIDIA Jetson Orin AGX Bring-up 报告

**状态**: `Recorded / Real-machine Sign-off Pending`  
**更新日期**: 2026-03-23  
**关联任务**: `P5-HW-004`

---

## 1. 目的

本文件用于固定 `nvidia-jetson-orin-agx` 这台正式 Tier 1 accelerator 机器的 bring-up 报告入口。

与 `40-Framework-Laptop-13-AMD-7040-Bring-up报告.md` 不同，这里承载的是：

- ARM64 + vendor firmware hook 路线
- `local-gpu` / managed worker 平台路径
- Jetson 平台的 installer / update / rollback / recovery 后续签收入口

---

## 2. 绑定关系

- 机器 ID：`nvidia-jetson-orin-agx`
- machine profile：`aios/hardware/profiles/nvidia-jetson-orin-agx.yaml`
- canonical platform combo：`nvidia-jetson-orin-agx`
- updated platform profile：`/usr/share/aios/updated/platforms/nvidia-jetson-orin-agx/profile.yaml`
- runtime profile：`/usr/share/aios/runtime/platforms/nvidia-jetson-orin-agx/default-runtime-profile.yaml`

这台机器继续作为：

- Jetson / ARM64 bring-up 主目标
- `local-gpu` 条件能力与 managed worker 路线的正式硬件报告对象

---

## 3. 已入库产物

### 3.1 生成与校验入口

- `scripts/build-default-hardware-evidence-index.py`
- `scripts/test-tier1-machine-bringup-reports-smoke.py`

### 3.2 默认产物路径

- `out/validation/tier1-machine-bringup/nvidia-jetson-orin-agx/hardware-validation-report.md`
- `out/validation/tier1-machine-bringup/nvidia-jetson-orin-agx/hardware-validation-evidence.json`
- `out/validation/tier1-machine-bringup/nvidia-jetson-orin-agx/hardware-boot-evidence-report.json`
- `out/validation/tier1-machine-bringup/nvidia-jetson-orin-agx/support-matrix.md`
- `out/validation/tier1-machine-bringup/nvidia-jetson-orin-agx/known-limitations.md`
- `out/validation/tier1-machine-bringup/nvidia-jetson-orin-agx/device-metadata.json`
- `out/validation/tier1-machine-bringup-summary.json`

---

## 4. 当前结论

截至 2026-03-23，这台正式 Jetson 机器已经有独立的 bring-up 报告和 evidence index，因此 `P5-HW-004` 的“记录第二台 Tier 1 bring-up 报告”交付物已经成立。

> **补充**（2026-03-23）：`vendor_accel_worker.py` 验证已通过，确认 Jetson 平台的 vendor accelerator worker 基线可在 `local-gpu` runtime profile 下正常启动与响应。

但当前结论仍然是：

- `validation_status = pending`
- `baseline_kind = nominated-machine-profile-baseline`
- `real_machine_signoff_status = pending-separate-evidence`

这意味着：

- 可以宣称“Jetson Orin AGX 的正式 bring-up 报告入口已固定”
- 不能宣称“Jetson Orin AGX 已形成 release-grade 硬件支持”

---

## 5. 尚待补齐的现场证据

后续若要把这台机器推进到 `Hardware Validated`，至少还需要补齐：

- 实机安装与 second boot 证据
- vendor firmware hook 的现场执行证据
- update / rollback 跨重启证据
- recovery 介质恢复证据
- `local-gpu` / vendor runtime 的实机 sign-off 件

在 Jetson 路线上，只有当这些证据进入对应 evidence index 后，`local-gpu` 路径才可以从 repo-level baseline 提升为 real-machine validated 结论。
