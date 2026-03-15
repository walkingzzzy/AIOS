# 31 · Release Notes 模板

**版本**: 1.0.0  
**更新日期**: 2026-03-14  
**状态**: `P7-REL-008` frozen template

---

## 1. 目标

本文提供 AIOS 当前发布说明的统一模板，用于把支持边界、兼容关系、验证证据和已知限制写成可交付文档。

适用场景：

- repo preview
- developer preview
- platform media handoff
- hardware-validated preview

本文不负责定义支持边界本身。支持边界与兼容规则分别以以下文档为准：

- [30-支持矩阵与已知限制.md](30-支持矩阵与已知限制.md)
- [32-版本兼容矩阵.md](32-版本兼容矩阵.md)
- [27-升级与恢复交付Runbook.md](27-升级与恢复交付Runbook.md)
- [29-Operator-Troubleshooting-手册.md](29-Operator-Troubleshooting-手册.md)

## 2. 使用规则

1. 不得写出超出 [30-支持矩阵与已知限制.md](30-支持矩阵与已知限制.md) 的支持宣称。
2. 若没有真实硬件验证报告，发布级别必须写成 `repo-preview`、`developer-preview` 或 `platform-media-handoff`，不能写成稳定硬件发布。
3. Release Notes 必须显式给出本版引用的 validation report、release gate report 与 hardware evidence 路径。
4. 如涉及平台 profile、runtime profile、schema 版本或 artifact 路径，必须与 [32-版本兼容矩阵.md](32-版本兼容矩阵.md) 保持一致。
5. 若本版包含 update / rollback / recovery 改动，必须附带 runbook 与 operator 文档链接。

## 3. 建议发布级别

| 发布级别 | 适用条件 |
|----------|----------|
| `repo-preview` | 只有仓库级或 QEMU 级验证 |
| `developer-preview` | 有系统交付链、release gate 与 operator 文档，但仍无实机签收 |
| `platform-media-handoff` | 已导出 installer/recovery media 与 bring-up kit，等待目标机器验证 |
| `hardware-validated-preview` | 已附真实硬件验证报告与 evidence index |

## 4. Markdown 模板

```md
# AIOS Release Notes - <release-id>

- 发布日期: <YYYY-MM-DD>
- 发布级别: <repo-preview | developer-preview | platform-media-handoff | hardware-validated-preview>
- 发布状态: <draft | rc | shipped>
- 发布 owner: <team/person>

## 1. 本版结论

- 本版范围: <一句话说明>
- 支持口径: 见 `docs/system-development/30-支持矩阵与已知限制.md`
- 兼容矩阵: 见 `docs/system-development/32-版本兼容矩阵.md`
- 运行/恢复口径: 见 `docs/system-development/27-升级与恢复交付Runbook.md`

## 2. 包含的交付物

| Artifact | 路径 | 说明 |
|----------|------|------|
| system image | `<path>` | `<notes>` |
| installer image | `<path>` | `<notes>` |
| recovery image | `<path>` | `<notes>` |
| delivery bundle | `<path>` | `<notes>` |
| platform media manifest | `<path>` | `<notes>` |
| bring-up kit | `<path>` | `<notes>` |

## 3. 本版新增 / 变更

### Image / Installer / First-boot

- <change>

### Update / Rollback / Recovery

- <change>

### Shell / Operator Surface

- <change>

### Observability / Diagnostics

- <change>

## 4. 平台支持声明

| Platform | 当前状态 | 证据 | 备注 |
|----------|----------|------|------|
| `qemu-x86_64` | `<Repo/QEMU Validated>` | `<report/tests>` | `<notes>` |
| `generic-x86_64-uefi` | `<Platform Media Exportable / Hardware Validated>` | `<report/tests>` | `<notes>` |
| `nvidia-jetson-orin-agx` | `<Platform Media Exportable / Hardware Validated>` | `<report/tests>` | `<notes>` |

## 5. 兼容性与升级说明

- `updated` platform profile: `<profile path>`
- runtime profile: `<profile path>`
- route profile: `<profile path>`
- observability `schema_version`: `<version>`
- task metadata `schema_version`: `<version>`
- 若需要 operator 执行 update / rollback / recovery，请先阅读：
  - `docs/system-development/27-升级与恢复交付Runbook.md`
  - `docs/system-development/29-Operator-Troubleshooting-手册.md`

## 6. 验证与证据

| Check / Report | 路径或命令 | 结果 | 备注 |
|----------------|------------|------|------|
| system delivery validation | `<path or command>` | `<passed/failed>` | `<notes>` |
| release gate | `<path or command>` | `<passed/failed>` | `<notes>` |
| full regression | `<path or command>` | `<passed/failed>` | `<notes>` |
| platform media smoke | `<path or command>` | `<passed/failed>` | `<notes>` |
| hardware validation report | `<path>` | `<pending/passed/failed>` | `<notes>` |
| hardware evidence index | `<path>` | `<pending/passed/failed>` | `<notes>` |

## 7. 已知限制与不支持项

- <limitation>
- <limitation>

## 8. 回退与恢复说明

- rollback / recovery runbook: `docs/system-development/27-升级与恢复交付Runbook.md`
- diagnostic bundle guide: `docs/system-development/28-diagnostic-bundle-解读手册.md`
- operator troubleshooting guide: `docs/system-development/29-Operator-Troubleshooting-手册.md`

## 9. 发布阻塞项

- <blocker or "none">

## 10. 签收

- Sign-off owner: <name>
- Sign-off date: <YYYY-MM-DD>
- Evidence bundle / archive: <path>
```

## 5. 最低必填字段

- 发布日期
- 发布级别
- 当前支持声明
- 兼容性说明
- validation report / release gate / regression report 路径
- 若涉及 Tier 1 平台，必须给出 hardware validation report 或明确写 `pending`

## 6. 当前建议

在 Tier 1 实机验证尚未闭环前，团队 A 的发布说明应优先使用 `developer-preview` 或 `platform-media-handoff` 级别，并明确写出“支持矩阵已冻结，但硬件支持名单仍待验证”。

