# 27 · 升级与恢复交付 Runbook

**版本**: 1.0.0  
**更新日期**: 2026-03-13  
**状态**: `P7-REL-007` frozen runbook

---

## 1. 目标

本文把 AIOS 当前已经落地的 delivery、installer、recovery、`updated`、release gate 与硬件 bring-up 能力收敛成一份**可执行的升级/恢复交付 runbook**。

它回答四个问题：

1. 发布前需要跑哪些仓库级 gate
2. 如何导出 installer / recovery 介质与 bring-up kit
3. 目标机器上如何做 install、first-boot、update、rollback、recovery 取证
4. 最终要把哪些 artifact 交给团队 E 或项目交付方

本文不替代：

- [09-镜像、安装、更新与恢复规范](09-镜像-安装-更新-恢复规范.md)：系统规格与约束
- [24-Boot / Firstboot / Recovery 验证清单](24-Boot-Firstboot-Recovery-验证清单.md)：当前仓库级验证项
- [29-Operator Troubleshooting 手册](29-Operator-Troubleshooting-手册.md)：现场故障排查动作
- `bringup/` handoff kit：具体平台的实机执行包

## 2. 交付完成定义

一次 upgrade / recovery 交付只有在以下条件同时成立时才算完成：

- 仓库级 `system-delivery-validation` 通过，并产出 machine-readable report
- `release gate` 已基于 validation report 与 evidence index 计算完成
- `full regression suite` 已产出 JSON/Markdown 汇总报告
- 平台 installer / recovery / system image 已导出，并生成 `platform-media-manifest.json`
- 目标机器已完成 install、first-boot、至少两次不同 `boot_id` 的 boot evidence 采集
- update 成功路径或失败后 rollback / recovery 路径至少一条有连续证据
- 最终硬件验证报告和 evidence index 可以被团队 E 直接消费

## 3. 关键产物地图

| 产物 | 默认路径 | 用途 |
|------|----------|------|
| delivery bundle | `out/aios-system-delivery/` | systemd unit、service metadata、image overlay 与 rootfs hygiene 基线 |
| system delivery validation report | `out/validation/system-delivery-validation-report.{json,md}` | 仓库级 installer / recovery / QEMU / updated 汇总验证 |
| system delivery evidence index | `out/validation/system-delivery-validation-evidence-index.json` | 团队 E release gate 的证据输入 |
| release gate report | `out/validation/release-gate-report.{json,md}` | blocking / warning checks 的最终判定 |
| full regression report | `out/validation/full-regression-report.{json,md}` | `validate + system-validation` 全量回归汇总 |
| platform media manifest | `out/platform-media/<platform>/platform-media-manifest.json` | installer / recovery / system image、overlay、bring-up kit 的单一清单 |
| hardware validation report | `out/platform-media/<platform>/bringup/reports/hardware-validation-report.md` | 实机 install / rollback / evidence 总结 |
| hardware evidence index | `out/platform-media/<platform>/bringup/reports/hardware-validation-evidence.json` | 实机证据索引；可作为默认 `out/validation/tier1-hardware-evidence-index.json` 之外的补充签收输入 |

`aios-updated` 默认状态面也必须可读：

| 状态面 | 默认路径 | 说明 |
|--------|----------|------|
| UDS socket | `/run/aios/updated/updated.sock` | `updated` JSON-RPC 入口 |
| deployment state | `/var/lib/aios/updated/deployment-state.json` | 当前版本、pending action、active recovery |
| health probe | `/var/lib/aios/updated/health-probe.json` | probe summary、checked_at、notes |
| recovery surface | `/var/lib/aios/updated/recovery-surface.json` | shell / operator 可消费的恢复面模型 |
| boot state | `/var/lib/aios/updated/boot-control.json` | current / last-good / staged slot |
| recovery points | `/var/lib/aios/updated/recovery/` | `update.apply` / `update.rollback` 的恢复记录 |
| diagnostic bundles | `/var/lib/aios/updated/diagnostics/` | `recovery.bundle.export` 输出目录 |

## 4. 发布前仓库级收敛

### 4.1 构建与系统级验证

先在仓库根目录执行：

```bash
python3 scripts/build-aios-delivery.py --build-missing
python3 scripts/test-system-delivery-validation.py
python3 scripts/check-release-gate.py
python3 scripts/run-aios-ci-local.py --stage full --output-prefix out/validation/full-regression-report
```

最低要求：

- `system-delivery-validation-report.json` 的 `overall_status` 为 `passed`
- `release-gate-report.json` 的 `gate_status` 为 `passed`
- `full-regression-report.json` 已生成，且 report schema 校验通过

如果准备把实机证据一并作为 blocking gate，改用：

```bash
python3 scripts/check-release-gate.py \
  --hardware-evidence-index out/platform-media/<platform>/bringup/reports/hardware-validation-evidence.json \
  --require-hardware-evidence
```

### 4.2 当前仓库级验证覆盖面

当前 runbook 默认依赖以下已经存在的 suite：

- `scripts/test-system-delivery-validation.py`
- `scripts/test-updated-smoke.py`
- `scripts/test-updated-restart-smoke.py`
- `scripts/test-updated-firmware-backend-smoke.py`
- `scripts/test-platform-media-smoke.py`
- `scripts/test-hardware-boot-evidence-smoke.py`

它们分别覆盖 delivery bundle、QEMU boot / recovery、installer cross reboot、`updated` staged update / rollback、platform media export、boot evidence evaluator 基线。

## 5. 导出平台介质与 bring-up kit

以 `generic-x86_64-uefi` 为例：

```bash
python3 scripts/build-aios-platform-media.py \
  --platform generic-x86_64-uefi \
  --output-dir out/platform-media/generic-x86_64-uefi
```

如果希望导出时一并重建 platform overlay 生效后的 installer / recovery image，可增加：

```bash
--build-platform-images
```

执行完成后至少检查以下文件存在：

- `out/platform-media/generic-x86_64-uefi/platform-media-manifest.json`
- `out/platform-media/generic-x86_64-uefi/installer-media/write-installer-media.sh`
- `out/platform-media/generic-x86_64-uefi/recovery-media/write-recovery-media.sh`
- `out/platform-media/generic-x86_64-uefi/bringup/README.md`
- `out/platform-media/generic-x86_64-uefi/bringup/checklists/install-rollback-checklist.md`
- `out/platform-media/generic-x86_64-uefi/bringup/profiles/generic-x86_64-uefi-tier1.yaml`
- `out/platform-media/generic-x86_64-uefi/bringup/profiles/generic-x86_64-uefi.yaml`
- `out/platform-media/generic-x86_64-uefi/bringup/support/support-matrix.md`
- `out/platform-media/generic-x86_64-uefi/bringup/support/known-limitations.md`

`bringup/` 目录是实机 handoff 包。它已经包含：

- Tier 1 profile 模板
- canonical hardware profile 副本
- install / rollback checklist
- support matrix 与 known limitations
- 硬件验证报告模板
- boot evidence 采集补丁资产
- pull / evaluate / render / collect-and-render 包装脚本

## 6. 目标机器 install 与 first-boot

### 6.1 介质写入

使用导出目录中的脚本写入 installer 与 recovery 介质：

```bash
./out/platform-media/generic-x86_64-uefi/installer-media/write-installer-media.sh /dev/<installer-usb>
./out/platform-media/generic-x86_64-uefi/recovery-media/write-recovery-media.sh /dev/<recovery-usb>
```

### 6.2 安装时必须确认

按 `bringup/checklists/install-rollback-checklist.md` 逐项打勾，至少确认：

- 目标机器与 `bringup/profiles/<platform>-tier1.yaml` 匹配
- 已阅读 `bringup/support/support-matrix.md` 与 `bringup/support/known-limitations.md`
- Guided installer summary 中的目标磁盘、平台 profile、分区策略正确
- installer report 与 vendor firmware hook report 已归档
- 安装完成后首次启动成功

### 6.3 首启后必须确认

登录目标系统后，至少核对以下内容：

- `/etc/aios/updated/platform.env` 指向期望的平台 profile
- `/etc/aios/runtime/platform.env` 与目标 hardware profile 一致
- `/var/lib/aios/hardware-evidence/boots/` 已开始写入 boot evidence

如果目标系统尚未集成 boot evidence service，可对挂载后的 sysroot 补装：

```bash
./out/platform-media/generic-x86_64-uefi/bringup/scripts/install-boot-evidence-assets.sh /path/to/mounted-sysroot
```

## 7. `updated` 运行面与关键 RPC

`aios-updated` 的关键入口来自 `uds-jsonrpc`。当前冻结的核心方法如下：

| 方法 | 用途 | 关键返回字段 |
|------|------|--------------|
| `system.health.get` | 查看服务是否 ready，以及当前状态文件/平台 profile 路径 | `status`、`notes` |
| `update.check` | 拉取可用 update artifact 并计算 `ready-to-stage` | `status`、`artifacts`、`next_version` |
| `update.apply` | 记录 recovery point、切换 staged slot、接受更新 | `status`、`deployment_status`、`recovery_ref` |
| `update.health.get` | 刷新 health probe，并把 post-boot 状态收敛到 deployment/boot state | `overall_status`、`rollback_ready`、`recovery_points`、`diagnostic_bundles` |
| `recovery.surface.get` | 生成 shell / operator 可消费的恢复面 | `current_slot`、`last_good_slot`、`staged_slot`、`available_actions` |
| `recovery.bundle.export` | 导出诊断包 | `bundle_id`、`bundle_path` |
| `update.rollback` | 基于 recovery point 或最近 recovery 记录回退 | `status`、`rollback_target` |

如需手动调试，可用任意支持 UNIX socket 的 JSON-RPC 客户端调用 `/run/aios/updated/updated.sock`。最小示例：

```bash
python3 - <<'PY'
import json
import socket

socket_path = "/run/aios/updated/updated.sock"
payload = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "recovery.surface.get",
    "params": {},
}
with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
    client.connect(socket_path)
    client.sendall(json.dumps(payload).encode("utf-8") + b"\n")
    data = b""
    while not data.endswith(b"\n"):
        data += client.recv(65536)
print(json.dumps(json.loads(data.decode("utf-8"))["result"], indent=2, ensure_ascii=False))
PY
```

## 8. 标准升级流程

### 8.1 升级前基线

升级前先保存以下证据：

- `system.health.get`
- `update.health.get`
- `recovery.surface.get`
- 当前 `deployment-state.json`
- 当前 `boot-control.json`

目标状态应满足：

- `system.health.get.status` 为 `ready` 或至少不是 `blocked`
- `recovery.surface.get.available_actions` 含 `check-updates`
- 当前 last-good slot 与 current slot 一致

### 8.2 检查并执行更新

顺序如下：

1. 调 `update.check`
2. 期望 `status` 为 `ready-to-stage` 或 `up-to-date`
3. 调 `update.apply`
4. 记录返回的 `recovery_ref`
5. 重启到 staged slot

成功 stage 后至少应看到：

- 新 recovery point 写入 `/var/lib/aios/updated/recovery/`
- `boot-control.json` 出现 `staged_slot`
- `recovery-surface.json` 已同步更新

### 8.3 重启后收敛

重启完成后立即执行：

1. `system.health.get`
2. `update.health.get`
3. `recovery.surface.get`

成功判定：

- `update.health.get.overall_status` 为 `ready`
- `boot-control.json` 中 `current_slot == last_good_slot`
- `boot-control.json` 中 `staged_slot` 已清空
- `deployment-state.json.status` 收敛到 `up-to-date`
- 新版本已写入 `deployment-state.json.current_version`

## 9. 失败分支与恢复流程

### 9.1 系统仍可启动，但更新异常

先导出诊断包：

1. 调 `recovery.bundle.export`
2. 记录返回的 `bundle_id` 与 `bundle_path`
3. 归档 `/var/lib/aios/updated/diagnostics/` 下新增 bundle

然后检查 `recovery.surface.get`：

- 若 `rollback_ready == true` 且 `available_actions` 含 `rollback`，优先走 `update.rollback`
- 若 `overall_status == blocked`，必须先保留诊断包，再决定是否继续回退
- diagnostic bundle 的字段解释与阅读顺序见 [`28-diagnostic-bundle-解读手册.md`](28-diagnostic-bundle-解读手册.md)

执行 rollback 后：

1. 记录 `rollback_target`
2. 重启到 last-good slot
3. 再次执行 `update.health.get`
4. 确认 `deployment-state.json.current_version` 已恢复到旧版本
5. 确认 recovery point 状态已变为 `rolled-back`

### 9.2 正常系统无法恢复，需要 recovery media

若更新后目标机器无法进入正常系统：

1. 使用导出的 recovery media 启动
2. 保留 recovery 启动画面、串口日志或照片证据
3. 导出日志、`updated` 状态文件与可用 diagnostic bundle
4. 如系统盘可挂载，额外归档：
   - `/var/lib/aios/updated/deployment-state.json`
   - `/var/lib/aios/updated/boot-control.json`
   - `/var/lib/aios/updated/recovery-surface.json`
   - `/var/lib/aios/updated/recovery/`
   - `/var/lib/aios/updated/diagnostics/`
5. 回到 bring-up checklist，把 rollback trigger、recovery log、post-rollback boot 结果补齐

## 10. 实机 boot evidence 与最终报告

目标机器至少要产生两个不同 `boot_id` 的 boot evidence record。推荐直接使用 `bringup/` 包装脚本：

```bash
AIOS_BRINGUP_PULL_HOST=root@<target-host> \
./out/platform-media/generic-x86_64-uefi/bringup/scripts/collect-and-render-hardware-validation.sh \
  ./out/hardware-boots \
  --expect-slot-transition a:b \
  --expect-last-good-slot b \
  -- \
  --machine-vendor <vendor> \
  --machine-model <model> \
  --operator <name>
```

这一步会串联：

1. `pull-boot-evidence.sh`
2. `evaluate-boot-evidence.sh`
3. `render-hardware-validation.sh`

最终至少要归档：

- evaluator JSON
- evaluator Markdown
- `hardware-validation-report.md`
- `hardware-validation-evidence.json`
- installer / recovery log
- 现场照片或串口记录

## 11. 最终交付包

团队 A 向团队 E 或项目交付方输出时，最少包含：

- `out/validation/system-delivery-validation-report.json`
- `out/validation/system-delivery-validation-evidence-index.json`
- `out/validation/release-gate-report.json`
- `out/validation/full-regression-report.json`
- `out/platform-media/<platform>/platform-media-manifest.json`
- `out/platform-media/<platform>/bringup/reports/hardware-validation-report.md`
- `out/platform-media/<platform>/bringup/reports/hardware-validation-evidence.json`
- installer / recovery / update / rollback 现场日志
- `recovery.bundle.export` 产生的诊断包路径与 bundle id

## 12. 当前边界

截至 2026-03-13，本 runbook 已冻结仓库级与 handoff 级流程，但仍需注意：

- 没有实机 `hardware-validation-report.md` 时，平台只能算 repo/QEMU validated，不能算 hardware validated
- vendor-specific firmware hook 与失败注入仍按平台 profile 逐步补齐，不能假设所有机器共享同一套 firmware 行为
- `recovery.surface.get` 已冻结为 shell / operator 可消费的 JSON 模型；diagnostic bundle 字段解释见 [`28-diagnostic-bundle-解读手册.md`](28-diagnostic-bundle-解读手册.md)
