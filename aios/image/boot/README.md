# boot/

`boot/` 保存 AIOS 镜像启动链的显式配置资产。

当前内容：

- `loader/loader.conf`：systemd-boot 基础行为配置
- `kernel-command-line.txt`：AIOS 默认内核命令行基线

当前边界：

- 这些资产已经进入仓库与 delivery bundle
- 它们还没有替代 `mkosi` 的最终 boot artifact 生成逻辑
- 本地已经通过 boot smoke 与 QEMU bring-up 取得第一份启动证据，但 boot asset、first-boot、recovery 与 update 之间仍未形成发行级闭环
