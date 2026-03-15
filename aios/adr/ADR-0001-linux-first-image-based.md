# ADR-0001: Linux-first + image-based

- 状态：Accepted
- 日期：2026-03-08

## 决策

- AIOS v1 采用 Linux-first
- 采用 image-based 系统交付，而不是 app 包交付
- 采用 system-service-first，而不是 Electron-first

## 结果

- 所有系统主线开发围绕 bootable image、systemd service、native shell、policy、rollback、recovery 展开
- `local-cpu` 为完整系统的最低运行时基线
- 完整系统目标不再等同于“所有扩展能力在同一时间、同一硬件默认成立”
