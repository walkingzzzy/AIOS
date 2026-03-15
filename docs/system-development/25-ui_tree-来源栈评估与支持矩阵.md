# `ui_tree` 来源栈评估与支持矩阵

**状态**: `Baseline Delivered / Overall In Progress`  
**更新日期**: 2026-03-14  
**关联任务**: `P6-UIX-001`、`P6-UIX-002`、`P6-UIX-003`、`P6-UIX-004`

---

## 1. 目的

本文件用于冻结 AIOS 当前 `ui_tree` 能力的来源栈判断、AT-SPI adapter spike、支持矩阵，以及 `ui_tree_snapshot` object model 的接入边界。

当前结论不是宣称“`ui_tree` 已完成”，而是确认：

1. `deviced` 已具备可运行的 `ui_tree` 路由选择与对象模型
2. AT-SPI live collector 与 state-bridge 路线都已有仓库实现
3. shell 与 `device.state.get` 已可消费统一的 `ui_tree_snapshot`
4. 支持矩阵已经 machine-readable，而不是只存在于说明文档中

---

## 2. 当前来源栈评估

### 2.1 当前主路线

AIOS 当前把 `ui_tree` 视为条件能力，优先按以下顺序解析：

1. `native-live`
   入口：`AIOS_DEVICED_UI_TREE_LIVE_COMMAND`
   实现：`aios/services/deviced/runtime/ui_tree_atspi_snapshot.py`
   适用：当前 session 可直接通过 AT-SPI live collector 拉取结构化树

2. `native-state-bridge`
   入口：`AIOS_DEVICED_UI_TREE_STATE_PATH`
   实现：`deviced` 从 state file 暴露 `ui_tree_snapshot`
   适用：已有外部 collector 或桥接层写入快照，`deviced` 只负责状态消费与统一输出

3. `native-ready`
   入口：仅存在 AT-SPI bus 或 session 条件，但还没有 live tree 数据
   适用：支持矩阵上宣告“当前环境可进入正式 collector 路线”，但当前尚未产出完整快照

4. `screen-frame+ocr`
   入口：support matrix 中的 fallback row
   适用：`ui_tree` 不可用时仍保留 screen frame + OCR 的最后一级回退路径

### 2.2 为什么选择 AT-SPI 为当前 spike 主体

- 它是 Linux-first 图形栈里最现实的可访问性树来源
- 它能提供窗口/控件/焦点/状态等结构化对象，而不是只返回像素
- 它适合先用 Python collector 快速验证 object model，再逐步替换成长运行 collector
- 现有 shell 与 `deviced` 已经围绕它建立了 `native-live`、`native-ready`、`native-state-bridge` 三段式状态

### 2.3 当前不直接承诺的内容

- 不承诺所有桌面环境都已形成同等稳定度的 live tree
- 不承诺 Wayland/X11/嵌套 compositor 全部具备同一条 collector 主路径
- 不承诺 `ui_tree` 可替代 portal / approval / visible indicator 边界

---

## 3. 已落地的 adapter spike

### 3.1 核心实现

- `aios/services/deviced/runtime/ui_tree_atspi_snapshot.py`
  提供 fixture / live collector 双模式，输出标准化 `ui_tree_snapshot`
- `aios/services/deviced/src/adapters.rs`
  负责 `ui_tree` adapter 选择、state snapshot 装配、screen payload 附加
- `aios/services/deviced/src/backend.rs`
  负责 `ui_tree_support_matrix` 生成与 `device.state.get` / `backend-state.json` 汇总

### 3.2 已验证的 adapter / route

| route | adapter_id | execution_path | 说明 |
|------|------|------|------|
| AT-SPI live collector | `ui_tree.atspi-probe` | `native-live` | 通过 live command 收集结构化树 |
| AT-SPI state bridge | `ui_tree.atspi-state-file` | `native-state-bridge` | 消费状态文件中的树快照 |
| AT-SPI ready-only | `ui_tree.atspi-ready` | `native-ready` | 有 bus / session 条件但无 live tree 数据 |

### 3.3 对应验证

- `scripts/test-deviced-ui-tree-collector-smoke.py`
- `scripts/test-deviced-smoke.py`
- `scripts/test-deviced-readiness-matrix-smoke.py`
- `scripts/test-deviced-probe-failure-smoke.py`
- `scripts/test-shell-live-smoke.py`

---

## 4. 支持矩阵

`deviced` 当前输出的 `ui_tree_support_matrix` 至少包含以下 machine-readable 行：

| environment_id | readiness | available 语义 | 说明 |
|------|------|------|------|
| `current-session` | 当前会话推导值 | 表示当前会话的实际 `ui_tree` 能力状态 | 聚合 session type、adapter、probe、snapshot |
| `atspi-live` | `native-live` / `native-ready` / `missing-atspi-bus` | 表示 AT-SPI live collector 路线是否可走 | 由 bus 与 probe 共同决定 |
| `state-bridge` | `native-state-bridge` / `missing-state-file` | 表示状态桥接路线是否可走 | 由 state file 是否存在决定 |
| `screen-ocr-fallback` | `screen-frame+ocr` | 恒为可用 fallback | 表示没有结构化树时的最后回退路径 |

矩阵当前会同时落到三条消费路径：

- `device.state.get` 顶层 `ui_tree_support_matrix`
- `backend-state.json` 快照
- dedicated `ui-tree-support-matrix.json` artifact，并通过 `system.health.get` / `device.state.get` notes 暴露路径

### 4.1 当前会话判断输入

`current-session` 行至少吸收以下条件：

- `XDG_CURRENT_DESKTOP` / `DESKTOP_SESSION`
- `XDG_SESSION_TYPE`
- `DBUS_SESSION_BUS_ADDRESS`
- `AT_SPI_BUS_ADDRESS`
- 当前 backend status
- 当前 adapter 选择结果
- 当前 `ui_tree_snapshot`

### 4.2 当前支持结论

- 如果存在 live collector 输出，则当前会话可进入 `native-live`
- 如果仅存在 AT-SPI bus，则当前会话可进入 `native-ready`
- 如果仅存在 state file，则当前会话可进入 `native-state-bridge`
- 若以上都不成立，仍必须保留 `screen-frame+ocr` fallback

---

## 5. `ui_tree_snapshot` object model

### 5.1 顶层字段

当前标准对象至少包含：

- `snapshot_id`
- `generated_at`
- `source`
- `backend`
- `collector`
- `application_count`
- `desktop_count`
- `node_count`
- `focus_node`
- `focus_name`
- `focus_role`
- `applications`

### 5.2 节点字段

节点最小结构为：

- `node_id`
- `name`
- `role`
- `states`
- `child_count`
- `children`
- `description`（可选）
- `truncated`（可选）

### 5.3 `deviced` 注入的附加字段

当 `ui_tree_snapshot` 进入 `device.state.get`、screen preview 或 shell panel 时，当前实现还会保留：

- `adapter_id`
- `adapter_execution_path`
- `capture_mode`
- `backend_ready`
- `adapter.backend`

### 5.4 当前接入位置

- `device.state.get`
- `backend-state.json`
- screen capture preview object
- shell `device-backend-status` panel
- `shellctl status`

---

## 6. 与 shell 的集成结论

当前 shell 侧并不是“知道 `ui_tree` 的存在”，而是已经消费结构化对象：

- `aios/shell/components/device-backend-status/panel.py`
  直接读取 `ui_tree_snapshot` 与 `ui_tree_support_matrix`
- `scripts/test-shell-live-smoke.py`
  已覆盖 `deviced -> shell` 的 live `ui_tree` 消费链
- `scripts/test-shell-panels-smoke.py`
  已覆盖 panel model 对 `ui_tree` 元数据的消费

因此 `P6-UIX-004` 的当前验收口径可以定义为：

- `ui_tree_snapshot` 已进入 `deviced` object model
- `ui_tree_snapshot` 已进入 shell backend status / `shellctl` 消费路径
- shell 不需要额外私有转换层来理解 `ui_tree`

---

## 7. 验证入口

### 7.1 单测

- `cargo test -p aios-deviced`

### 7.2 Smoke

- `python3 scripts/test-deviced-ui-tree-collector-smoke.py`
- `python3 scripts/test-deviced-smoke.py --bin-dir aios/target/debug`
- `python3 scripts/test-deviced-readiness-matrix-smoke.py --bin-dir aios/target/debug`
- `python3 scripts/test-deviced-probe-failure-smoke.py --bin-dir aios/target/debug`
- `python3 scripts/test-shell-live-smoke.py --bin-dir aios/target/debug`

---

## 8. 当前结论

截至 2026-03-14，`ui_tree` 相关工作已经具备明确的实现基线：

- 来源栈已评估
- AT-SPI adapter spike 已实现
- 支持矩阵已 machine-readable
- `ui_tree_snapshot` object model 已接入 `deviced` 与 shell 消费路径

按当前任务口径，这意味着 `P6-UIX-001`、`P6-UIX-002`、`P6-UIX-003`、`P6-UIX-004` 的**基线交付**都已具备：其中 `P6-UIX-003` 的完成依据，是 `deviced` 已能稳定输出 machine-readable support matrix、dedicated matrix artifact、统一字段与对应 smoke 证据。

但这还不能推出 `ui_tree` 主线已完成。当前仍缺：

- 完整 AT-SPI live tree 长期运行能力
- fully-qualified 跨桌面环境支持矩阵与长期稳定性证据
- 与正式 shell surface 的 release-grade 收敛
