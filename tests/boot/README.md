# Boot Smoke

此目录保存 AIOS image / boot / firstboot / recovery 相关的最小验证说明。

当前内容：

- `test-plan.md`
- `scripts/test-image-delivery-smoke.py`
- `scripts/test-boot-qemu-smoke.py`

当前范围：

- 校验 delivery bundle 中是否包含 boot / firstboot / recovery / compat 基础资产
- 校验 image 构建前的静态前置条件
- 校验 `mkosi` / `qemu-system-x86_64` preflight 状态并稳定暴露 bring-up 阻塞

当前未覆盖：

- 真实 `mkosi` boot artifact 启动
- QEMU bring-up
- recovery target 实机切换
