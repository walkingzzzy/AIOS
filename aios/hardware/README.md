# hardware/

`hardware/` 用于承载 AIOS 的支持平台、bring-up 与条件能力声明。

## 1. 负责什么

此目录存放：

- Tier 0 / Tier 1 profile
- bring-up checklist
- 实机跨重启证据采集资产
- 设备能力 profile
- 支持矩阵与条件能力声明

## 2. 当前状态

截至 2026-03-14：

- 已有：`qemu-x86_64.yaml`、`tier1-template.yaml`、`generic-x86_64-uefi.yaml`、`nvidia-jetson-orin-agx.yaml`、`framework-laptop-13-amd-7040.yaml` 与 `tier1-nominated-machines.yaml`
- 已有：`evidence/aios-boot-evidence.service`、`evidence/aios-boot-evidence.sh`、`scripts/evaluate-aios-hardware-boot-evidence.py`、`scripts/render-aios-hardware-validation-report.py`、`scripts/test-hardware-boot-evidence-smoke.py`、`scripts/test-hardware-validation-report-smoke.py`，以及 `scripts/build-aios-platform-media.py` 生成的 `bringup/` handoff kit
- bring-up kit 现已包含：canonical hardware profile 副本、Tier 1 profile、formal nominated machine profile 副本、support matrix、known limitations、实机执行 README、install/rollback checklist、hardware validation report template、evidence index template、pull/evaluate/render helper scripts，以及一键 `collect-and-render-hardware-validation.sh` wrapper
- 未有：Tier 1 实机 bring-up 记录、真实平台成功 boot / rollback 报告

当前判断：`Bring-up tooling + Tier 1 nomination landed; hardware proof pending`

## 3. 原则

- Tier 0 `QEMU x86_64` 是默认基线
- Tier 1 是正式开发硬件
- `ui_tree`、`local-gpu`、`local-npu`、trusted offload 必须按支持矩阵声明
- 实机跨重启证明必须来自 `boot_id` 不同的真实采样记录，不能以仓库内 smoke 代替

## 4. 下一步

1. 用 `scripts/build-aios-platform-media.py` 导出的 `out/platform-media/<platform>/bringup/` 套件准备实机 bring-up 资产
2. 在目标机器启用 `aios-boot-evidence.service`，采集至少两次不同 `boot_id` 的 evidence
3. 优先使用 bring-up kit 里的 `collect-and-render-hardware-validation.sh`，或分别调用 evaluator / renderer 生成 bring-up 报告与 evidence index
4. 为 Tier 1 正式机器建立独立 profile，并随 bring-up kit 冻结 support matrix / known limitations
5. 优先按 `framework-laptop-13-amd-7040` 与 `nvidia-jetson-orin-agx` 两台正式机器补齐 bring-up 报告
