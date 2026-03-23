# 40 · Framework Laptop 13 AMD 7040 Bring-up 报告

**状态**: `Recorded / Real-machine Sign-off Pending`  
**更新日期**: 2026-03-23  
**关联任务**: `P5-HW-003`

---

## 1. 目的

本文件用于固定 `framework-laptop-13-amd-7040` 这台正式 Tier 1 x86_64 机器的 bring-up 报告入口。

这里记录的是：

1. 当前仓库已经为这台正式机器生成了独立的 bring-up 报告产物
2. 这些产物已经进入默认 validation 产物链和 smoke 校验
3. 当前报告仍明确区分“已记录报告”与“真实机器签收已完成”

---

## 2. 绑定关系

- 机器 ID：`framework-laptop-13-amd-7040`
- machine profile：`aios/hardware/profiles/framework-laptop-13-amd-7040.yaml`
- canonical platform combo：`generic-x86_64-uefi`
- updated platform profile：`/usr/share/aios/updated/platforms/generic-x86_64-uefi/profile.yaml`
- runtime profile：`/etc/aios/runtime/default-runtime-profile.yaml`

这台机器继续作为：

- 主 x86_64 installer / firstboot / rollback / recovery bring-up 目标
- Developer Preview 阶段最优先的正式机器报告对象

---

## 3. 已入库产物

### 3.1 生成与校验入口

- `scripts/build-default-hardware-evidence-index.py`
- `scripts/test-tier1-machine-bringup-reports-smoke.py`

### 3.2 默认产物路径

- `out/validation/tier1-machine-bringup/framework-laptop-13-amd-7040/hardware-validation-report.md`
- `out/validation/tier1-machine-bringup/framework-laptop-13-amd-7040/hardware-validation-evidence.json`
- `out/validation/tier1-machine-bringup/framework-laptop-13-amd-7040/hardware-boot-evidence-report.json`
- `out/validation/tier1-machine-bringup/framework-laptop-13-amd-7040/support-matrix.md`
- `out/validation/tier1-machine-bringup/framework-laptop-13-amd-7040/known-limitations.md`
- `out/validation/tier1-machine-bringup/framework-laptop-13-amd-7040/device-metadata.json`
- `out/validation/tier1-machine-bringup-summary.json`

---

## 4. 当前结论

截至 2026-03-23，这台正式机器的 bring-up 报告已经有了明确仓库产物与 machine-readable 证据索引，因此 `P5-HW-003` 的“记录第一台 Tier 1 bring-up 报告”交付物已经成立。

> **补充**（2026-03-23）：`local-cpu` reference worker smoke test 已在本机 profile 对应的 x86_64 runtime 基线上通过验证，确认 `local-cpu` 作为全局推理 fallback 在此平台可用。

但这份报告的当前口径仍是：

- `validation_status = pending`
- `baseline_kind = nominated-machine-profile-baseline`
- `real_machine_signoff_status = pending-separate-evidence`

也就是说：

- 可以宣称“Framework Laptop 13 AMD 7040 的正式 bring-up 报告入口已入库”
- 不能宣称“这台机器已经完成 install / rollback / recovery 的真实硬件签收”

---

## 5. 尚待补齐的现场证据

后续若要把这台机器推进到 `Hardware Validated`，至少还需要补齐：

- 安装介质启动与 guided installer 结果
- firstboot 成功证据
- update / rollback 跨重启证据
- recovery 介质启动与恢复证据
- 现场照片、串口或日志采集件

这些证据应继续挂到本文件对应的 report / evidence index 路径，而不是另起新的机器口径。
