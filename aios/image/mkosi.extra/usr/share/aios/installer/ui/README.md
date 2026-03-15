# installer/ui/

该目录承载 installer 的 guided UX 资产。

当前实现是 `aios-installer-guided.sh`：

- 在真正写盘前输出面向操作员的安装摘要
- 显示目标磁盘、平台 ID、平台 profile、vendor/hardware 元数据与 hook 状态
- 支持 `AIOS_INSTALLER_GUIDED_MODE=interactive` 的最小交互确认
- 支持 `AIOS_INSTALLER_GUIDED_DRY_RUN=1`，便于在 smoke 中验证 guided 流程而不触发写盘
