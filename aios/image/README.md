# image/

此目录负责：

- QEMU / VM 开发镜像
- 安装介质
- 启动链
- 恢复模式
- 更新与回滚

首要目标：

- 先构建 `x86_64 QEMU` 开发镜像
- 先跑通 systemd + 核心 service skeleton
- 先验证恢复入口与日志
