# firstboot/

`firstboot/` 提供 AIOS 第一次启动的初始化入口。

当前职责：

- 初始化 AIOS 状态目录和本地系统元数据
- 确保镜像内的 `machine-id` hygiene 在 first-boot 阶段正确收敛
- 维持 `/var/lib/dbus/machine-id -> /etc/machine-id` 的一致性
- 在 first-boot 阶段生成本机 `random-seed`，避免把种子随镜像落盘
- 把 install identity、boot backend 与 recovery manifest 信息收敛到统一 firstboot report

当前形态：

- `aios-firstboot.service`
- `aios-firstboot.sh`
- `aios-firstboot.env`

当前验证：

- delivery bundle 会显式产出空的 `/etc/machine-id`
- delivery bundle 会显式移除 `/var/lib/systemd/random-seed`
- delivery bundle 会显式建立 `/var/lib/dbus/machine-id -> /etc/machine-id`
- `scripts/test-firstboot-hygiene-smoke.py` 会离线执行 firstboot 脚本，验证 machine-id 初始化、random-seed 生成、report 写入与幂等性
- `scripts/test-installer-smoke.py` 会验证 installer 写入的 install identity / recovery manifest 能被 firstboot report 正确收敛

当前边界：

- 已有 service + script 落点、QEMU firstboot 证据与 installer integration
- 仍缺真实安装介质分区/引导流程与硬件级 first-boot 证据回收
