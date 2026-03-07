# ADR-0001: Linux-first + image-based

- 状态：Accepted
- 日期：2026-03-08

决策：

- AIOS v1 采用 Linux-first
- 采用 image-based 系统交付，而不是 app 包交付
- 采用 system-service-first，而不是 Electron-first

结果：

- 所有系统主线开发围绕 bootable image、systemd service、Wayland shell、policy、rollback 展开
