# AIOS Route B 发布清单

**更新日期**: 2026-03-14

---

> **系统开发口径修订（2026-03-08）**
> AIOS 统一定义为 **AI 原生操作系统 / 系统软件工程**。本文如提及桌面应用、Electron 客户端、应用适配器、App 安装等内容，除非明确标注为“原型期 / 兼容层 / 历史实现”，否则不再代表目标形态。
> 当前最高约束：**系统镜像、系统服务、系统壳层、设备/能力抽象、权限与更新恢复**。

## 1. 系统级发布门槛

### 机器可读 gate

<!-- aios-release-gate-rules:start -->
```yaml
release_gate:
  use_matrix_blocking: true
  warn_on_non_blocking_failures: true
required_coverage_domains:
  - observability-governance
  - control-plane
  - runtime
  - provider
  - shell
  - device
  - compat
  - image-recovery-update
  - hardware-evidence
  - release-governance
required_health_component_kinds:
  - service
  - runtime
  - provider
  - shell
  - device
  - update
  - platform
  - hardware
hardware_evidence:
  required_by_default: true
```
<!-- aios-release-gate-rules:end -->

统一执行入口：

```bash
python3 scripts/check-release-gate.py
```

完整回归入口：

```bash
python3 scripts/run-aios-ci-local.py --stage full --output-prefix out/validation/full-regression-report
```

默认读取：

- `out/validation/system-delivery-validation-report.json`
- `out/validation/governance-evidence-index.json`
- `out/validation/cross-service-health-report.json`

默认输出：

- `out/validation/governance-evidence-index.json`
- `out/validation/governance-evidence-index.md`
- `out/validation/tier1-hardware-evidence-index.json`
- `out/validation/tier1-hardware-validation-report.md`
- `out/validation/release-gate-report.json`
- `out/validation/release-gate-report.md`
- `out/validation/full-regression-report.json`
- `out/validation/full-regression-report.md`

本清单与以下发布口径文档配套使用：

- `docs/system-development/33-开发者预览发布标准.md`
- `docs/system-development/34-产品预览发布标准.md`
- `docs/system-development/35-稳定版发布标准.md`
- `docs/system-development/36-第一轮安全审计报告.md`

当前 blocking gate 主要覆盖：

- 由 `tests/observability/validation-matrix.yaml` 标记为 `blocking: true` 的 governance 检查
- `tests/observability/high-risk-audit-coverage.yaml` 中 machine-readable 声明的高风险 capability 与 Team A `update.apply` / `update.rollback` / `recovery.bundle.export` 覆盖
- delivery / firstboot / installer 集成
- QEMU preflight / bring-up / recovery / installed-target cross reboot
- `updated` recovery surface / cross restart / firmware backend / platform profile
- control-plane / runtime / provider / shell / device 主路径的 machine-readable health/export 证据
- machine-readable validation report、governance evidence index、cross-service health report 与 operator-facing audit evidence report

当前 observability 补充证据：

- `python3 scripts/build-governance-evidence-index.py`
- `python3 scripts/test-high-risk-audit-coverage-smoke.py`
- `python3 scripts/build-observability-correlation-report.py ...`
- `python3 scripts/test-observability-correlation-smoke.py --bin-dir aios/target/debug`
- `python3 scripts/build-audit-evidence-report.py ...`
- `python3 scripts/test-audit-evidence-export-smoke.py --bin-dir aios/target/debug`
- `python3 scripts/test-cross-service-health-smoke.py --bin-dir aios/target/debug --delivery-manifest out/aios-system-delivery/manifest.json`

升级/恢复交付与实机取证流程统一见：

- `docs/system-development/27-升级与恢复交付Runbook.md`

### 启动与镜像
- [ ] 可生成可启动镜像
- [ ] 可在参考 VM 或硬件成功启动
- [ ] 有恢复模式或回滚入口
- [ ] 版本切换失败时可恢复

### 系统服务
- [ ] `aios-agentd` 可由系统服务管理器托管
- [ ] `aios-sessiond`、`aios-policyd` 有健康检查
- [ ] 关键服务异常可重启或隔离
- [ ] 有日志、追踪、审计链路

### 壳层与会话
- [ ] AI Shell 可进入会话
- [ ] workspace / launcher / notification / focus 基本可用
- [ ] 壳层崩溃不会导致不可恢复状态

### 安全与权限
- [ ] capability policy 已固化
- [ ] 高风险能力有审批和审计
- [ ] compat layer 权限与系统能力权限分离

### 更新与恢复
- [ ] 支持原子更新或等效机制
- [ ] 支持回滚
- [ ] 发布包包含恢复说明（见 `docs/system-development/27-升级与恢复交付Runbook.md`）

## 2. 兼容层发布说明

兼容层原型（如 Electron 控制台）可以发布，但不能替代系统主线发布判断。
换言之：

- 打包 Electron 应用 ≠ 发布 AIOS
- 发布 daemon 二进制 ≠ 发布 AIOS

## 3. 演示与对外交付物

对外演示优先级应为：

1. 可启动系统镜像
2. 系统服务图谱
3. AI Shell 演示
4. compat layer 演示

## 4. 当前仓库适用的最小清单

在系统镜像尚未落地前，只能做以下性质的发布：

- 原型兼容层演示版
- 协议验证版
- 开发者预研版

不应再对外包装为“AIOS 正式系统版本”。

## 5. 当前 gate 说明

- `validate` 阶段负责 schema smoke、workspace test 与核心 smoke
- `system-validation` 阶段负责系统镜像、QEMU、installer、updated 与 hardware evidence 验证
- `release gate` 先消费本文件中的 machine-readable rules，再读取 governance evidence index / cross-service health report 判定 blocking checks
- `validate` 阶段现也会跑 observability correlation smoke，验证 `sessiond` / `policyd` / `runtimed` 证据能 stitch 成统一报告
- `validate` 阶段现也会跑 audit evidence export smoke，验证 control-plane approval / token / runtime / observability / audit-store 证据，以及 `updated` apply / rollback / recovery retained evidence，能导出为 operator-facing report
- `validate` 阶段现会构建默认 `Tier 1 hardware evidence` baseline，生成 `out/validation/tier1-hardware-evidence-index.json` 供 release gate 默认消费
- `validate` 阶段现会额外产出 `ci-artifact-governance-report`，冻结 artifact 命名、上传目录、下载复用、失败保留与 retention 规则
- `validate` / `system-validation` 阶段现会产出 `cross-service-health-report`，用于卡口 control plane / device / update / shell provider / compat / delivery 证据是否断链
- `system-validation` 阶段现会先下载 `validate` artifact，再生成 `governance-evidence-index`，把 validation matrix、artifact governance、cross-service exporter、system delivery suite 与 release-governance 证据统一收口
- release gate 默认会优先使用 `out/validation/tier1-hardware-evidence-index.json`；如需覆盖默认路径，可执行：

```bash
python3 scripts/check-release-gate.py --hardware-evidence-index <path>
```

- 默认 baseline 只解决 machine-readable blocking gate，不替代真实 nominated machine 的 install / rollback / recovery sign-off
