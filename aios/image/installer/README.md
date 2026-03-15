# installer/

`installer/` 保存 AIOS 安装介质的最小入口资产。

当前内容：

- `profile.yaml`：安装介质的设备约定与工作模式描述
- `aios-installer.target`：独立 installer target
- `aios-installer.service`：guided installer -> actual install runner 的执行入口
- `aios-installer-guided.sh`：安装前摘要、最小交互确认与 session/report 输出
- `aios-installer-run.sh`：把 bootable system image 写入目标磁盘并重置 firstboot 元数据
- installer 运行期状态与 report 写入 `/run/aios-installer/`，避免安装介质因上一次执行留下持久 completed 标记而变成单次可用
- `aios-installer.env`：默认的 source / target / recovery 设备映射
- `ui/`：guided UX 资产与说明
- `kernel-command-line.txt`：installer image 的默认启动参数
- `aios-installer-run.sh` 已支持 `AIOS_INSTALLER_SOURCE_IMAGE_FILE` 与 `AIOS_INSTALLER_TARGET_OVERLAY_DIR`，可从 installer media 内嵌 payload 写盘，并在目标系统落下平台 overlay

当前边界：

- 已提供 image-based installer media，可在 QEMU 中把 bootable system image 写入目标磁盘并产出安装报告
- 已提供 guided installer 摘要层，可显示 platform / disk / vendor / hardware / hook 状态，并支持 dry-run/interactive 模式
- 已提供安装后目标盘的 firstboot reset、install manifest、recovery manifest 和 VM 级跨重启验证
- 已提供 `scripts/build-aios-platform-media.py`，可导出 single-media installer payload、target overlay 与 flash script
- 仍缺真正图形化 installer 与真实硬件上的介质发现自动化
