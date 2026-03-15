# delivery/

`delivery/` 描述 AIOS 当前的系统级交付方式。

当前交付物仍不是完整发行版；它本身是一个可复用的 **system delivery bundle**，并作为镜像 staging 来源被 `scripts/test-system-delivery-validation.py` 间接验证到 boot / recovery / installer-media QEMU 闭环，用于：

- 汇总当前可编译的 core services / provider binaries
- 汇总 systemd units、默认 profile、descriptor、schema 与 shell prototype 资源
- 汇总 boot / firstboot / recovery / compat runtime skeleton 资产
- 汇总 updated platform profile、generic UEFI backend bridge 与 hardware boot evidence 资产
- 生成 `mkosi.extra` overlay
- 为后续 `mkosi` 镜像构建提供单一 staging 来源

构建命令：

```bash
python3 scripts/build-aios-delivery.py --build-missing
```

默认输出：

- `out/aios-system-delivery/rootfs/`
- `out/aios-system-delivery/manifest.json`
- `out/aios-system-delivery/image/`
- `out/aios-system-delivery.tar.gz`

与镜像构建的关系：

- `scripts/sync-aios-image-overlay.sh` 会调用 delivery builder，把 `rootfs/` 同步到 `aios/image/mkosi.extra/`
- `scripts/build-aios-image.sh` 会先刷新 overlay，再调用 `mkosi`

当前边界：

- 已覆盖服务二进制、units、profiles、provider descriptors、schema、tasks、shell prototype、boot / firstboot / recovery、compat runtime skeleton、updated platform profile 与硬件证据采集资产
- `rootfs/` 与 `mkosi.extra/` 现已同步携带 `default/formal/release` 三档 shell profile，以及 `aios/shell/compositor/` 的 source/config 资产，并由 `scripts/test-image-delivery-smoke.py` 固定校验
- 仍未等同于最终已签名发行物或真实硬件成功证明
