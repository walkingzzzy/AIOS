# aios-updated

## 1. 角色

`aios-updated` 是 AIOS 的更新、回滚与恢复管理服务。

核心职责：

- 更新与回滚
- 健康检查
- 恢复模式入口
- 自愈 runbook 协调
- 诊断包导出

## 2. 推荐技术路线

- 语言：Rust
- system integration：systemd update / boot / health tooling
- 通信：UDS + JSON-RPC
- 数据：deployment state、health state、recovery refs、boot control、recovery surface

## 3. 推荐目录结构

```text
updated/
├── src/
│   ├── main.rs
│   ├── config.rs
│   ├── rpc.rs
│   ├── deployment.rs
│   ├── health.rs
│   ├── rollback.rs
│   ├── diagnostics.rs
│   ├── boot.rs
│   ├── sysupdate.rs
│   ├── recovery_ui.rs
│   └── errors.rs
├── platforms/
├── tests/
├── service.yaml
└── units/
```

## 4. 当前状态

- 仓库状态：`In Progress`
- 已有：角色定义、unit、image/update 规范文档、`src/` 骨架、`update.check` / `update.apply` / `update.health.get` / `update.rollback` / `recovery.surface.get` / `recovery.bundle.export` RPC、deployment state 持久化、health probe 文件读取与命令刷新、启动阶段 health probe + recovery surface 自动同步、boot verify 后 deployment state 自动收敛（版本提升 / 版本恢复 / pending 清理 / recovery point 状态回写）、外部命令桥接、结构化 `systemd-sysupdate` backend 配置、`bootctl` / `firmwarectl` adapter split、boot slot / A-B 状态 JSON、rollback slot hint、recovery surface JSON + RPC、boot backend 适配（`state-file` / `bootctl` / `firmware`）、diagnostic bundle exporter，以及 `qemu-x86_64` / `generic-x86_64-uefi` / `nvidia-jetson-orin-agx` 平台 health probe 资产
- 已有：关键 update / recovery RPC 会镜像到共享 `observability.jsonl` sink，并复用 trace-event schema；`update.apply` / `update.rollback` 会带出 recovery-linked `update_id`
- 已新增平台 backend 落地：`platforms/qemu-x86_64` 与 `platforms/generic-x86_64-uefi` profile、`platform.env`、generic UEFI `systemd-sysupdate` bridge、generic UEFI `firmwarectl` bridge，以及 rootfs 集成
- 已新增实机证据采集接口：`aios-boot-evidence.service` 会在系统启动后导出 boot evidence，供 `scripts/evaluate-aios-hardware-boot-evidence.py` 做跨重启判定
- 已有最小验证：`cargo test -p aios-updated`、`cargo build -p aios-updated`、`cargo test --workspace`、`scripts/test-updated-smoke.py`、`scripts/test-updated-restart-smoke.py`、`scripts/test-updated-firmware-backend-smoke.py`、`scripts/test-updated-platform-profile-smoke.py`、`scripts/test-hardware-boot-evidence-smoke.py`、`scripts/test-system-delivery-validation.py`
- 当前缺口：真实 Tier 1 硬件 boot-success / rollback 证据、更多厂商特定 firmware hook 与失败注入验证

## 5. 下一步

1. 在目标平台把 generic UEFI bridge 替换成 vendor-specific hook 或接入现有 firmware 工具
2. 用 `aios-boot-evidence.service` + `scripts/evaluate-aios-hardware-boot-evidence.py` 采集真实跨重启证据
3. 把 recovery surface RPC / CLI fallback 推进到正式 shell surface
4. 在目标平台继续增加 vendor-specific failure injection 与 recovery 验证
