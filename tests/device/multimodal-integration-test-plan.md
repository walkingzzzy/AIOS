# AIOS Device / Multimodal Integration Test Plan

## 目标

本计划用于覆盖团队 D 在 `deviced` 与 `device-metadata` 上的多模态集成闭环，对应：

- `P3-PVD-003`
- `P5-DEV-003`
- `P5-DEV-004`
- `P5-DEV-005`
- `P5-DEV-006`
- `P5-DEV-007`
- `P5-DEV-008`

## 覆盖范围

- `deviced`
- `device-metadata-provider`
- `agentd` provider resolution（仅用于 device metadata provider 集成）
- shell 对 `backend-state.json` / `device.state.get` 的只读消费路径

## 核心断言

### 1. 设备基线采集

- screen / audio / input / camera 至少有一条 baseline capture 或 readiness 路径
- capture 结果保留 `adapter_id`、`adapter_execution_path`、`source_backend`
- backend snapshot 与实时 `device.state.get` 保持一致

### 2. normalize / taint / retention

- `device.object.normalize` 会按 modality 生成标准 object kind
- audio / camera 等敏感模态会进入更严格 retention class
- normalize 结果保留 taint / source backend / 时间戳信息

### 3. visible indicators 与 approval

- 活动 capture 会写入 indicator state
- stop / restart reconciliation 会清理或收敛 indicator state
- approval required 模态会反映到 capture / indicator 元数据

### 4. continuous collectors

- `continuous=true` 的 screen / audio / input / camera 会产生 collector 状态
- `continuous-captures.json` 与 `device.state.get` 对 collector 状态输出一致

### 5. `ui_tree` 集成

- `ui_tree_snapshot` 能进入 `device.state.get`
- `ui_tree_support_matrix` 能进入 `backend-state.json`
- shell `device-backend-status` / `shellctl status` 能消费 `ui_tree` 元数据

### 6. device metadata provider

- provider 能通过 registry discover / resolve 被找到
- `device.metadata.get` 能返回 screen / audio / input / camera 的统一 readiness 视图
- `device.metadata.get` 能返回 top-level `summary` readiness 摘要与 `ui_tree_support_matrix`
- `deviced` 短时掉线后，provider health 会先降为 `unavailable`，恢复后重新回到 `available`
- provider stop 后健康状态与 capability 暴露会正确收敛

## 运行入口

### Rust 单测

```bash
cargo test -p aios-deviced
```

### 集成 / smoke

```bash
python3 scripts/test-deviced-smoke.py --bin-dir aios/target/debug
python3 scripts/test-deviced-readiness-matrix-smoke.py --bin-dir aios/target/debug
python3 scripts/test-deviced-policy-approval-smoke.py --bin-dir aios/target/debug
python3 scripts/test-deviced-continuous-native-smoke.py --bin-dir aios/target/debug
python3 scripts/test-deviced-probe-failure-smoke.py --bin-dir aios/target/debug
python3 scripts/test-deviced-ui-tree-collector-smoke.py
python3 scripts/test-shell-live-smoke.py --bin-dir aios/target/debug
python3 scripts/test-device-metadata-provider-smoke.py --bin-dir aios/target/debug
```

## 证据产物

- `captures.json`
- `indicator-state.json`
- `backend-state.json`
- `continuous-captures.json`
- `ui_tree` fixture / state snapshot
- provider health / descriptor / resolve 结果

## 当前结论

截至 2026-03-14，上述脚本已经覆盖团队 D 当前已落地的多模态基线实现；按当前任务口径，`P3-PVD-003` 与 `P5-DEV-003` ~ `P5-DEV-008` 的仓库交付物与 smoke 已齐备，但这不等于 device 主线已经完成。

当前仍缺：

- 真实 portal / PipeWire / libinput / camera release-grade backend
- 正式 shell indicator / backend status surface
- fully-qualified `ui_tree` 支持矩阵与长期稳定性证据
