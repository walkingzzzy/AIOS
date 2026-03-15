# aios-deviced

## 1. 角色

`aios-deviced` 是 AIOS 的设备与多模态 broker。

核心职责：

- 屏幕、音频、输入、摄像头等设备能力
- 多模态采集归一化与标注
- device capability 事件流
- taint / retention / visible indicator / approval 协同

## 2. 条件能力提醒

`deviced` 涉及多项条件能力：

- `ui_tree`
- 高级屏幕共享
- 输入采集 / 输入注入边界
- 摄像头连续采集

这些能力必须按支持矩阵、portal、policy 与 shell stack 联合声明，不能默认视为全平台可用。

## 3. 推荐技术路线

- 语言：Rust
- 通信：UDS + JSON-RPC + D-Bus / portal integration
- 采集适配层：screen / audio / input / camera adapters
- 对象模型：`screen_frame`、`ui_tree_snapshot`、`audio_chunk`、`input_event_batch`

## 4. 推荐目录结构

```text
deviced/
├── src/
│   ├── main.rs
│   ├── config.rs
│   ├── rpc.rs
│   ├── capture/
│   │   ├── mod.rs
│   │   ├── screen.rs
│   │   ├── audio.rs
│   │   ├── input.rs
│   │   └── camera.rs
│   ├── adapters.rs
│   ├── approval.rs
│   ├── indicator.rs
│   ├── normalize.rs
│   ├── probe.rs
│   ├── taint.rs
│   ├── retention.rs
│   └── errors.rs
├── runtime/
│   └── ui_tree_atspi_snapshot.py
├── tests/
├── service.yaml
└── units/
```

## 5. 当前状态

- 仓库状态：`In Progress`
- 已有：角色定义、unit、`src/` 骨架、`device.capture.request` / `device.capture.stop` / `device.state.get` / `device.object.normalize` / `device.retention.apply` RPC、screen/audio/input/camera baseline、外部 capture adapter 命令桥、native state-bridge preview（portal / PipeWire / libinput / camera / AT-SPI state paths）与 native stub/session-bus fallback、按 modality 的 live probe command 通路（screen/audio/input/camera/ui_tree）、`ui_tree_snapshot` 附加、capture 状态落盘、visible indicator 状态落盘、backend readiness 矩阵、插件化 capture adapter plan、`device.state.get`/`backend-state.json` 双路径暴露、approval allowlist / mode、对 `policyd approval.list` 已批准记录的真实审批联动、retention / taint / approval 元数据联动、capture 重启恢复与 interrupted reconciliation、shell `device-backend-status` / `notification-center` live 消费路径，以及通过 `AIOS_DEVICED_UI_TREE_LIVE_COMMAND` 接入的 builtin AT-SPI live collector helper（`runtime/ui_tree_atspi_snapshot.py`）；本轮还把 native-live 路径进一步区分为 formal native backend adapter 与 explicit probe-command adapter：builtin/native 证据路径现会暴露 `screen.portal-native` / `audio.pipewire-native` / `input.libinput-native` / `camera.v4l-native` / `ui_tree.atspi-native` 这组 adapter id，以及统一的 `adapter_contract=formal-native-backend` 元数据，而显式 probe command 仍保留 `*-probe` 身份；与此同时 screen / audio / input / camera 也已新增 `AIOS_DEVICED_*_LIVE_COMMAND` 通路，可把 per-modality live helper 的 payload 直接并入 `native-live` preview 与 health/readiness 证据；同时仓库已正式补齐 `runtime/screen_portal_live.py`、`runtime/pipewire_audio_live.py`、`runtime/libinput_input_live.py`、`runtime/camera_v4l_live.py` 四条 helper 资产，并在 `config.rs` 中提供 `AIOS_DEVICED_HELPER_PYTHON` / `/usr/bin/python3` 默认 helper 发现逻辑，作为 release-grade backend 之前的 shipped runtime helper baseline；这组 helper 现在也会统一输出 `request_binding` / `session_contract` / `transport` / `evidence` / `media_pipeline` 结构化 contract，并在 live capture 路径中回绑真实 session/task/window/source context；同时也补上了 continuous native capture manager，`continuous=true` 的 screen/audio/input/camera 请求在 native execution path 下会维护后台 collector，并把 `continuous_collectors` / `continuous-captures.json` 暴露给 `device.state.get` 与 `backend-state.json`；`ui_tree` 方面也新增 dedicated `ui-tree-support-matrix.json` artifact，并把 `desktop_environment` / `session_type` / `adapter_id` / `execution_path` / `stability` / `limitations` / `evidence` 字段统一暴露到 `device.state.get`、health notes 与 backend snapshot；同时 `AIOS_DEVICED_OBSERVABILITY_LOG` 现已把 `device.state.reported`、`device.capture.requested`、`device.capture.rejected`、`device.capture.stopped` / `device.capture.stop.missed` 统一镜像到共享 `observability.jsonl` sink，并在通过 `policyd` 审批时补齐 `approval_id` 关联字段
- 已有最小验证：`cargo test -p aios-deviced`、`cargo build -p aios-deviced`、`cargo test --workspace`、`scripts/test-deviced-smoke.py`、`scripts/test-deviced-native-backend-smoke.py`、`scripts/test-deviced-readiness-matrix-smoke.py`、`scripts/test-deviced-continuous-native-smoke.py`、`scripts/test-deviced-runtime-helpers-smoke.py`、`scripts/test-deviced-ui-tree-collector-smoke.py`、`scripts/test-deviced-policy-approval-smoke.py`、`scripts/test-cross-service-health-smoke.py`、`scripts/test-shell-prototypes.py`、`scripts/test-shell-live-smoke.py`、`scripts/test-device-metadata-provider-smoke.py`，覆盖 formal native backend adapter id、screen probe live path、screen + audio capture、continuous native capture collector、runtime helper 默认发现、native stub preview、indicator state、approval metadata、`policyd` 审批联动、共享 observability sink 的 device trace / approval correlation、retention linkage、backend readiness 状态、backend snapshot JSON、dedicated `ui_tree` support matrix artifact、builtin AT-SPI live collector 与 shell live fallback
- 缺失：真实 portal / PipeWire / libinput / camera backend、跨桌面环境 fully-qualified `ui_tree` 支持矩阵与长期稳定性证据、visible indicator / backend status 正式 shell surface

## 6. 下一步

1. 继续把 formal native adapter contract 从当前 evidence / helper / state-bridge 路径推进到 release-grade portal / PipeWire / libinput / camera backend
2. 接 portal / ScreenCast / PipeWire / input backend 与真实状态回传
3. 把 `runtime/ui_tree_atspi_snapshot.py` 从 helper/fixture 路径继续推进到正式支持栈上的长期运行 collector 与支持矩阵
4. 把 visible indicators / backend status 从 JSON state / CLI prototype 推到正式 shell surface
5. 继续把 `policyd` 审批联动从批准校验扩展到更细粒度的 taint / retention / shell 呈现
