# ADR-0007: Update stack 采用 systemd-sysupdate + boot control adapter 的双层模型

- 状态：Accepted
- 日期：2026-03-09

## 背景

`updated` 已经实现 deployment state、health probe、rollback skeleton 与 restart smoke，但 update stack 还没有正式 ADR，导致 image、boot、recovery、slot 管理之间缺少稳定边界。

## 决策

- 更新编排层优先使用 `systemd-sysupdate`
- 启动槽位控制采用独立 boot control adapter 抽象
- 开发环境允许 `state-file` 与 `bootctl` adapter 作为过渡后端
- 真正的 firmware / bootloader slot switch 需要在后续平台 bring-up 中补平台适配器
- recovery surface、diagnostics bundle、rollback evidence 都由 `updated` 统一汇总

## 结果

- `updated` 与 image / boot 之间的边界更明确
- 本地 smoke、QEMU bring-up、硬件平台适配可以共用一套 update state model
- boot control 后端可从开发适配器平滑替换为真实平台适配器
