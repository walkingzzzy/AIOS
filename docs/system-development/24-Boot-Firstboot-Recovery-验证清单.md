# Boot / First-boot / Recovery 验证清单

日期：2026-03-10
范围：把 AIOS 当前已落地的 image、firstboot、recovery image、installer integration、firmware backend 与 updated cross-restart 能力收敛成一份可重复执行的系统级验证清单。

## 目标

- 验证 delivery bundle 的 rootfs hygiene 不会把 `machine-id` / `random-seed` 作为出厂持久状态打包进镜像
- 验证 firstboot 离线执行仍满足初始化与幂等性要求
- 验证 installer 会把 install identity、boot backend 与 recovery manifest 写入目标 sysroot
- 验证 `aios-qemu-x86_64.raw` 可在 QEMU 中成功启动，并输出 `AIOS_FIRSTBOOT_REPORT`
- 验证 `aios-qemu-x86_64-recovery.raw` 可在 QEMU 中进入 recovery target，并输出 `AIOS recovery mode`
- 验证 `updated` 的 recovery surface、diagnostic bundle export、staged boot slot、`bootctl` / `firmware` backend 与跨重启收敛路径

## 推荐执行入口

统一入口：

```bash
python3 scripts/test-system-delivery-validation.py
```

默认会生成：

- `out/validation/system-delivery-validation-report.json`
- `out/validation/system-delivery-validation-report.md`
- `out/validation/system-delivery-validation-evidence-index.json`
- `out/validation/release-gate-report.json`
- `out/validation/release-gate-report.md`

## 子检查项

| 检查项 | 命令 | 目的 | 主要证据 |
|--------|------|------|----------|
| delivery rootfs hygiene | `python3 scripts/test-image-delivery-smoke.py --bundle-dir out/aios-system-delivery` | 验证 bundle 的 unit、descriptor、task 与 machine-id hygiene | `out/aios-system-delivery/manifest.json` |
| firstboot offline hygiene | `python3 scripts/test-firstboot-hygiene-smoke.py --bundle-dir out/aios-system-delivery` | 验证 firstboot 初始化与幂等性 | firstboot report stdout |
| installer integration | `python3 scripts/test-installer-smoke.py` | 验证 installer sysroot staging、install identity 与 recovery manifest 集成 | installer summary + firstboot report |
| QEMU preflight | `python3 scripts/test-boot-qemu-smoke.py` | 验证 mkosi / image / QEMU 依赖与镜像存在性 | preflight JSON |
| QEMU bring-up + firstboot | `python3 scripts/test-boot-qemu-bringup.py --timeout 180 --expect-firstboot` | 验证 raw image 真正启动并执行 `aios-firstboot.service` | `out/boot-qemu-bringup.log` |
| QEMU recovery bring-up | `python3 scripts/test-boot-qemu-recovery.py --timeout 180` | 验证 recovery image 真正进入 `aios-recovery.target` | `out/boot-qemu-recovery.log` |
| updated recovery surface | `python3 scripts/test-updated-smoke.py` | 验证 `update.apply`、`recovery.surface.get`、`recovery.bundle.export` 与 `update.rollback` | smoke stdout + temp state |
| updated cross-restart | `python3 scripts/test-updated-restart-smoke.py` | 验证 staged boot slot、重启后收敛与 rollback | smoke stdout + temp state |
| updated firmware backend | `python3 scripts/test-updated-firmware-backend-smoke.py` | 验证 firmware backend A/B 切槽、mark-good 与 rollback 跨重启路径 | smoke stdout + temp state |

## 当前已验证结论

截至 2026-03-10：

- `delivery rootfs hygiene` 通过
- `firstboot offline hygiene` 通过
- `installer integration` 通过
- `QEMU preflight` 通过
- `QEMU bring-up + firstboot` 通过
- `QEMU recovery bring-up` 通过
- `updated recovery surface` 通过
- `updated cross-restart` 通过
- `updated firmware backend` 通过
- 汇总报告已写入 `out/validation/system-delivery-validation-report.{json,md}`
- evidence index 已写入 `out/validation/system-delivery-validation-evidence-index.json`
- release gate 已写入 `out/validation/release-gate-report.{json,md}`

## 当前仍未覆盖的部分

这份清单与 suite 仍然没有覆盖以下发行级能力：

- 真实安装介质分区、引导与回滚路径
- 真实平台 firmwarectl / bootloader / `systemd-sysupdate` backend
- 真实硬件或整机虚拟机级跨重启 update 成功/失败证据
- Tier 1 实机 bring-up 与 installer/recovery 记录

## 结论

当前 AIOS 已具备“本地可重复执行的 boot / firstboot / recovery / installer / updated validation suite”，并且 recovery image、installer integration 与 firmware backend 已经有仓库级证据。但它仍不是完整发行版，后续应优先把这份 suite 接入更强的镜像流水线，并补真实安装介质与硬件级重启验证。
