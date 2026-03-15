# ADR-0006: Shell stack 采用 Smithay compositor + GTK4 panels 的分层路线

- 状态：Accepted
- 日期：2026-03-09

## 背景

AIOS 已有 `shellctl.py`、panel skeleton 和多条 shell smoke harness，但仍缺正式 shell stack 冻结，导致 chooser、approval UI、recovery UI 与 `ui_tree` 相关实现没有统一落点。

## 决策

- compositor 层优先采用 `Smithay` 路线
- 早期控制面 panel / settings / approval / recovery 视图优先采用 `GTK4/libadwaita`
- `shellctl.py` 与现有 Python prototypes 继续作为过渡期聚合层与 smoke harness 入口
- shell 与 core services 之间继续优先使用本地 IPC / D-Bus / portal，而不是引入 bridge 协议替代本地控制面
- `ui_tree`、screen share、approval chooser 属于条件能力，不在 shell stack ADR 中被无条件承诺

## 结果

- shell 轨道有了正式技术方向
- 现有 prototype、future GTK panel、future Smithay compositor 之间的分工清晰
- chooser / approval / recovery surface 可以在不等待完整 compositor 完成的前提下继续推进
