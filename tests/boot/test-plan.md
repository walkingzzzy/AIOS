# AIOS Boot Smoke Test Plan

## 目标

在进入真实 QEMU bring-up 前，先验证 image / boot / firstboot / recovery 资产已经进入 delivery bundle。

## 当前步骤

1. `python3 scripts/build-aios-delivery.py --no-archive`
2. `python3 scripts/test-image-delivery-smoke.py --bundle-dir out/aios-system-delivery`
3. `python3 scripts/test-boot-qemu-smoke.py` 暴露 image/QEMU preflight 状态
4. `scripts/build-aios-image.sh` 在本地有 `mkosi` 时刷新 overlay 并尝试构建 image
5. `scripts/boot-qemu.sh` 在本地有 QEMU 时验证镜像可启动

## 通过条件

- bundle manifest 存在
- rootfs 中存在核心服务二进制
- rootfs 中存在 `aios-firstboot.service`
- rootfs 中存在 recovery target / service
- rootfs 中存在 compat runtime skeleton 与 provider descriptors

## 后续扩展

- first-boot 成功标记与 bring-up report
- recovery mode isolate 验证
- boot slot / update / rollback 联调
- `mkosi` / QEMU 主机依赖自动安装与 CI bring-up
