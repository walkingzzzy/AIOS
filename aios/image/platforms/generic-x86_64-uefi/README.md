# generic-x86_64-uefi/

该平台目录定义了仓库内的“真实平台安装盘/回滚介质”导出参数：

- installer 采用单介质模式，把系统镜像作为 payload 内嵌到 installer media
- installer 在写盘后会把 target overlay 注入目标系统，切换 `updated` 到 generic UEFI backend profile
- installer profile 现携带 vendor id、partition strategy 与 firmware hook 配置
- recovery media 单独导出，用作回滚/诊断介质

- `scripts/build-aios-platform-media.py` 还会在输出目录生成 `bringup/` 套件，包含 Tier 1 profile 模板、install/rollback checklist、hardware validation report template、boot evidence 资产、SSH 拉取脚本与 evaluator wrapper
