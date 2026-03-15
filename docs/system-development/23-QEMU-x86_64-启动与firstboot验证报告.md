# QEMU x86_64 启动与 firstboot 验证报告

日期：2026-03-09
目标：验证 `aios/image/mkosi.output/aios-qemu-x86_64.raw` 可启动，并确认 first-boot 链路已在 QEMU guest 内实际执行。

## 执行命令

```bash
python3 scripts/build-aios-delivery.py --no-archive --sync-overlay aios/image/mkosi.extra
python3 scripts/test-image-delivery-smoke.py --bundle-dir out/aios-system-delivery
python3 scripts/test-firstboot-hygiene-smoke.py --bundle-dir out/aios-system-delivery
bash scripts/build-aios-image.sh
python3 scripts/test-boot-qemu-bringup.py --timeout 180 --expect-firstboot
```

## 结果摘要

- `scripts/test-image-delivery-smoke.py` 通过，交付 bundle 仍显式产出空的 `/etc/machine-id`、`/var/lib/dbus/machine-id -> /etc/machine-id`，且不携带持久化 `random-seed`
- `scripts/test-firstboot-hygiene-smoke.py` 通过，离线 firstboot 仍验证 machine-id 初始化、report 写入与幂等性
- `bash scripts/build-aios-image.sh` 成功产出 `aios/image/mkosi.output/aios-qemu-x86_64.raw`
- `scripts/test-boot-qemu-bringup.py --expect-firstboot` 返回 `0`
- 串口日志文件：`out/boot-qemu-bringup.log`

## 关键证据

QEMU bring-up 成功匹配到以下信号：

- kernel 启动
- `systemd` 进入 system mode
- 至少一个 AIOS service 启动（本次为 `aios-deviced.service`）
- `aios-firstboot.service` 实际执行并输出：

```text
AIOS_FIRSTBOOT_REPORT profile_id=qemu-x86_64-dev channel=dev machine_id_state=preserved machine_id_generated=false random_seed_present=true report=/var/lib/aios/firstboot/report.json
```

补充解释：

- 交付 bundle 的离线 smoke 已证明镜像出厂态为“空 `/etc/machine-id` + 无持久化 `random-seed`”
- QEMU guest 中 firstboot report 显示 `machine_id_state=preserved` 且 `random_seed_present=true`，说明在 AIOS 自定义 firstboot service 执行前，systemd 首启流程已经为本次启动生成并持久化了 machine identity / random seed
- 因此，`machine-id / random-seed` 的镜像 hygiene 与真实首启行为已经同时具备证据，不再只是 preflight

## 结论

`QEMU x86_64` 启动链已经具备以下已验证能力：

- bootable raw image 可成功启动到 userspace
- `aios-firstboot.service` 在 guest 内实际执行
- machine identity / random-seed 不随镜像预置落盘，并会在真实首启中收敛到有效状态

## 仍未完成的部分

- recovery image / rollback / A-B boot slot 仍未完成发行级验证
- update / firmware backend 仍未完成实机或虚拟化重启验证
- 该报告证明的是 image bring-up 与 firstboot 闭环，不等价于所有 AIOS service 长稳态通过
