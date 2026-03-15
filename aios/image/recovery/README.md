# recovery/

`recovery/` 保存 AIOS 恢复模式的最小入口资产。

当前内容：

- `profile.yaml`：恢复模式的路径与目标描述
- `aios-recovery.target`：独立恢复 target
- `aios-recovery-shell.service`：恢复摘要输出入口
- `aios-recovery-report.sh`：恢复上下文打印脚本
- `kernel-command-line.txt`：recovery image 的默认启动参数

当前边界：

- 已有 recovery image 构建脚本、QEMU bring-up 证据与 installer recovery manifest 集成
- 已有 `scripts/build-aios-platform-media.py`，可导出 standalone recovery media 与 flash script
- 仍缺真实平台上的 recovery boot entry 管理证据与硬件级 rollback 成功记录
