# AIOS

AIOS 是按 Route B 重建的 **AI-native 系统工程仓库**。  
它不是桌面应用仓库，也不是单一 daemon 仓库，而是一个面向 **bootable image + core services + native shell + governed runtime** 的系统软件仓库。

## 1. 当前定位

当前仓库承担四类职责：

1. **系统目录骨架**：把 image、services、runtime、shell、policy、compat、hardware、sdk、observability、legacy 正式拆层
2. **契约冻结**：通过 schema、profile、ADR、spec 文档冻结长期关键边界
3. **实现入口**：为后续 Rust workspace、systemd services、QEMU bring-up 提供落点
4. **迁移中枢**：把旧 client / daemon / cli 的可复用逻辑迁移到新系统结构

## 2. 当前真实状态（截至 2026-03-09）

- **定义层**：已基本成型
- **规格层**：已较完整
- **ADR 层**：第一轮已建立
- **目录骨架**：已完成
- **真正实现层**：已形成第一批可编译服务、provider/runtime、image build 与 QEMU bring-up 基线，但距离发行级 first-boot / recovery / update 闭环仍有明显距离

准确说法：

> AIOS 已完成系统路线重构与仓库骨架搭建，并已建立本地可编译的 core services / registry / portal / provider / update / shell prototype 交付链；现在已经能产出 bootable image，并在 QEMU 串口中验证到 kernel、systemd 与 `aios-deviced` 启动，但 first-boot / recovery / A/B update 仍未形成发行级闭环。

## 3. 当前成熟度判断

| 领域 | 状态 | 说明 |
|------|------|------|
| `docs/system-development` | `In Progress` | 已从规格扩展到实现与执行层 |
| `aios/adr` | `In Progress` | 已有 `ADR-0001`~`ADR-0008`，shell / update / sandbox 路线已冻结 |
| `aios/image` | `In Progress` | 已有 `mkosi` / repart / sysupdate / overlay / QEMU 脚本、boot / firstboot / recovery 资产与 system delivery bundle 流水线，并已产出 bootable image 与 QEMU bring-up 证据；缺 first-boot / recovery / update 发行级闭环 |
| `aios/services` | `In Progress` | 六个核心服务均已有 `src/`、可编译二进制与本地 smoke / unit test 证据，`agentd` 已接 provider registry 并暴露 lifecycle RPC |
| `aios/runtime` | `In Progress` | 已有 profile / schema，`runtimed` 已补 scheduler / queue / budget / timeout skeleton |
| `aios/policy` | `In Progress` | 有 policy / token schema，`policyd` 已补 evaluator / approval / token / audit writer/query，并完成 token key storage hardening、capability catalog 与 prompt-injection baseline |
| `aios/shell` | `In Progress` | 已有 `shellctl.py`、7 个 shell component CLI prototype + panel skeleton、shell provider runtime、Tk desktop host，以及 live / panel smoke harness |
| `aios/compat` | `In Progress` | 已有 compat provider descriptors、runtime skeleton、browser / office / mcp baseline provider、可选 centralized `execution_token` + `policyd` verify、共享 `AIOS_COMPAT_OBSERVABILITY_LOG` sink，以及 `bubblewrap` 优先的 code sandbox OS 级隔离路径；缺正式 bridge / remote auth / provider registration / operator-facing 持久审计查询 |
| `aios/hardware` | `In Progress` | 有 Tier 0 / Tier 1 profile，QEMU x86_64 已有 bring-up 记录；缺 Tier 1 实机 bring-up |
| `aios/observability` | `In Progress` | 已有 audit / trace / diagnostic / health / recovery schema，以及 validation report / evidence index / release gate / cross-service correlation schema、schema smoke 与 correlation report builder |

## 4. 目录总览

- `image/`：镜像、启动链、first-boot、更新、回滚、恢复
- `services/`：核心 system services 与 unit 元数据
- `runtime/`：推理后端、队列、预算、route / runtime profiles
- `shell/`：AI Shell / compositor / launcher / workspace / approval surfaces
- `policy/`：capability、审批、execution token、taint、policy profiles
- `compat/`：browser / office / MCP / A2A / code sandbox / legacy bridge
- `hardware/`：Tier 0 / Tier 1 profiles、bring-up、支持矩阵
- `sdk/`：provider descriptor、portal handle、共享 schema
- `observability/`：audit、trace、health、diagnostic、recovery、validation / release-gate schema
- `legacy/`：旧控制台与迁移说明

## 5. 当前仓库缺什么

当前最缺的不是“更多介绍”，而是下面这些真正可执行产物：

- CI 级可重复构建与 image-level 验证
- service binary 打包进 image
- first-boot / machine identity / random-seed 的发行级收敛
- recovery / rollback / A/B update 的镜像级验证证据
- formal portal chooser GUI / real screen cast flow
- 真实 provider runtime / bridge worker
- shell / compositor 正式 GUI
- `deviced` 的真实 capture adapters / visible indicators
- `updated` 的真实 sysupdate / rollback executor

## 6. 立即主线

当前主线不应继续发散，而应集中到以下顺序：

1. 把已打通的 image / QEMU bring-up 基线推进到 first-boot / recovery / update 闭环
2. 继续收敛 `sessiond` / `policyd` / `runtimed` / `agentd` 的系统级联调
3. 把 shell desktop host、chooser/provider 与 device/backend 状态推进到更正式的 GUI 形态
4. 把 provider/runtime / compat / sandbox 从 skeleton 推到更真实的 worker/backends
5. 最后进入 Tier 1 硬件 bring-up、A/B update 与 release validation

## 7. 与 `docs/system-development` 的关系

`aios/` 目录是 `docs/system-development` 的实现落点。  
推荐配套阅读：

- `docs/system-development/17-技术选型与框架矩阵.md`
- `docs/system-development/18-开发主计划与任务状态.md`
- `docs/system-development/19-实现映射与当前进度.md`
- `docs/system-development/20-核心服务详细设计.md`

## 8. 仓库维护规则

- 任何新模块都必须说明自己属于 `system`、`runtime`、`shell`、`device`、`compat` 中哪一层
- 任何高影响决策必须先补 ADR
- 任何条件能力都必须说明其 `hardware profile / shell stack / provider support / policy state`
- 不允许再以 legacy UI 的功能页数量衡量 AIOS 主线进度
