# image/

此目录负责：

- QEMU / VM 开发镜像
- 安装介质
- 启动链
- 恢复模式
- 更新与回滚

## 当前状态

截至 2026-03-11，本目录已经推进到**可构建、可启动、并已有 firstboot / recovery / installer-media / cross-reboot 证据，以及仓库级平台介质导出、vendor/hardware 安装元数据、平台分区策略与 firmware hook 接口的 image 基线**：

- 已建立 `mkosi` 主配置：`aios/image/mkosi.conf`
- 已建立 `boot/` 目录与基础 loader / kernel command line 资产
- 已建立 `systemd-repart` 分区配置：`aios/image/repart.d/`
- 已建立 `systemd-sysupdate` transfer 资产：`aios/image/sysupdate.d/`
- 已建立 image overlay：`aios/image/mkosi.extra/`
- 已建立 `firstboot/`、`recovery/`、`installer/` 与 `platforms/` 目录，并补上最小 systemd unit / script / profile 资产
- 已建立 system delivery bundle 组装脚本：`scripts/build-aios-delivery.py`
- 已建立镜像构建脚本：`scripts/build-aios-image.sh`
- 已建立平台介质导出脚本：`scripts/build-aios-platform-media.py`
- 已建立 QEMU 启动脚本：`scripts/boot-qemu.sh`
- 已建立 overlay 同步脚本：`scripts/sync-aios-image-overlay.sh`
- 已建立 image/QEMU preflight smoke：`scripts/test-boot-qemu-smoke.py`
- 已建立 QEMU bring-up smoke：`scripts/test-boot-qemu-bringup.py`
- 已建立 first-boot hygiene smoke：`scripts/test-firstboot-hygiene-smoke.py`
- 已建立 recovery image 构建脚本：`scripts/build-aios-recovery-image.sh`
- 已建立 recovery QEMU bring-up smoke：`scripts/test-boot-qemu-recovery.py`
- 已建立 installer integration 脚本：`scripts/install-aios-system.py`
- 已建立 installer smoke：`scripts/test-installer-smoke.py`
- 已建立 guided installer wrapper：`aios/image/installer/aios-installer-guided.sh`，并补上 `scripts/test-installer-ux-smoke.py`
- 已建立 installer image 构建与 QEMU 安装介质验证：`scripts/build-aios-installer-image.sh`、`scripts/test-boot-qemu-installer.py`、`scripts/test-qemu-cross-reboot.py`
- 已建立平台介质导出 smoke：`scripts/test-platform-media-smoke.py`
- 平台介质导出现在会同时生成 `bringup/` 套件，包含 Tier 1 profile 模板、boot evidence 资产、主机侧 pull/evaluate helper 与实机执行 README
- installer / firstboot / platform media 已支持 `vendor_id`、`hardware_profile_id`、平台级 `partition_strategy`、`runtimed` 的 platform env/runtime profile 注入，以及 pre/post install firmware hook 元数据，并已纳入 smoke / QEMU system-delivery validation
- 已新增 `nvidia-jetson-orin-agx` platform profile、installer hooks、`updated` nvbootctrl adapter 与 `scripts/test-vendor-firmware-hook-smoke.py`
- 已新增 `docker/aios-delivery.Dockerfile` 与 `scripts/build-aios-delivery-container.sh`，用于容器内原生 `linux/x86_64` delivery bundle 构建
- 已在本地产出 `aios/image/mkosi.output/aios-qemu-x86_64.raw`、`aios/image/recovery.output/aios-qemu-x86_64-recovery.raw` 与 `aios/image/installer.output/aios-qemu-x86_64-installer.raw`，并通过串口日志验证 firstboot、recovery target、installer media -> target disk -> second boot 闭环；最新证据记录在 `out/boot-qemu-bringup.log`、`out/boot-qemu-recovery.log`、`out/boot-qemu-installer.log`、`out/boot-qemu-installed-cross-reboot.log` 与 `out/validation/system-delivery-validation-report.{json,md}`
- delivery bundle 会显式产出空的 `/etc/machine-id`、`/var/lib/dbus/machine-id -> /etc/machine-id`，并保证 `random-seed` 不会随镜像落盘

## 当前技术路线

- 镜像构建：`mkosi`
- 启动方式：UEFI + `systemd-boot`
- 分区：`systemd-repart`
- 更新：`systemd-sysupdate`
- 平台介质导出：embedded installer payload + target overlay + standalone recovery media + hardware bring-up kit
- 运行目标：`QEMU x86_64` 开发机型与 generic x86_64 UEFI 平台

## 已落地的目录

- `mkosi.conf`：镜像主配置
- `boot/`：loader 配置与默认 kernel command line
- `firstboot/`：首次启动初始化 unit / script / env
- `recovery/`：恢复 target / service / profile
- `installer/`：installer target / env / runtime / embedded payload 支持
- `platforms/`：平台介质导出配置与实机 bring-up kit 模板
- `repart.d/`：ESP / root / var 分区布局
- `sysupdate.d/`：后续增量更新入口资产
- `mkosi.extra/etc/aios/`：默认 policy / runtime profile 注入
- `mkosi.extra/usr/share/aios/runtime/platforms/`：平台专属 runtime profile 资产
- `mkosi.extra/usr/lib/systemd/system/`：核心 unit 注入
- `mkosi.extra/usr/lib/tmpfiles.d/aios.conf`：状态目录初始化
- `scripts/build-aios-delivery.py`：组装服务二进制、unit、descriptor、schema、tasks、platform profile 与硬件证据资产到统一 bundle/rootfs

## 当前缺口

- 已有 QEMU 闭环和仓库级平台安装盘 / 回滚介质导出流程，但仍缺真实 Tier 1 硬件上的成功安装 / 回滚记录
- installer 已具备 guided UX、平台级分区策略、vendor/hardware 元数据与 hook 接口，但仍缺真正图形化 installer 与实机媒体发现
- update / rollback 已有 generic x86_64 UEFI backend，以及 `nvidia-jetson-orin-agx` 的 nvbootctrl adapter；仍缺实机验证与更多平台覆盖
- 当前 image 构建已补上 container-native delivery bundle 脚本与 nightly 入口，并在 Linux/x86_64 + `docker buildx` 可用时默认优先走 container-native strategy；若 docker 暂不可用但已有 `out/aios-delivery-container-target/debug`，则会优先复用缓存的 container-native 二进制目录；但完整镜像产线仍需继续减少 `host-bin-dir` 最终回退

## 当前开发命令

- 构建镜像：`scripts/build-aios-image.sh`
- 构建 system delivery bundle：`scripts/build-aios-delivery.py --build-missing`
- 同步 overlay：`scripts/sync-aios-image-overlay.sh`
- 构建平台安装盘 / 回滚介质：`scripts/build-aios-platform-media.py --platform generic-x86_64-uefi`
- 启动 QEMU：`scripts/boot-qemu.sh`
- 运行 preflight：`scripts/test-boot-qemu-smoke.py`
- 运行 bring-up smoke：`scripts/test-boot-qemu-bringup.py --timeout 180`
- 构建 recovery image：`scripts/build-aios-recovery-image.sh`
- 安装 bundle 到 sysroot：`scripts/install-aios-system.py --sysroot /path/to/sysroot`
- 运行 first-boot hygiene smoke：`scripts/test-firstboot-hygiene-smoke.py --bundle-dir out/aios-system-delivery`
- 运行 installer smoke：`scripts/test-installer-smoke.py`
- 运行 recovery bring-up：`scripts/test-boot-qemu-recovery.py --timeout 180`
- 运行镜像策略 smoke：`scripts/test-image-build-strategy-smoke.py`（输出 `out/validation/image-build-strategy-report.{json,md}`）
- 运行系统级交付验证套件：`scripts/test-system-delivery-validation.py`

## 下一步

1. 把导出的 installer / recovery media 真正烧录到目标平台并采集硬件级证据
2. 把 generic UEFI backend 的 firmware hook 接口接到目标平台正式 firmware 工具
3. 继续收敛容器内原生 `linux/x86_64` 服务二进制产线，把 `host-bin-dir` 压缩到仅在无 docker/buildx 且无缓存容器二进制时才使用
4. 把系统级交付验证套件继续接进 CI / nightly 镜像验证，保留 bring-up 与 recovery 证据
