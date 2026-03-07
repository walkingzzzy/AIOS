# AIOS

AIOS 是按 Route B 重建的 **AI-native 系统工程骨架**。

当前仓库目标：

- 以 `image/`、`services/`、`runtime/`、`shell/`、`policy/`、`compat/`、`hardware/` 为系统主线
- 以 schema、profile、ADR 先冻结关键执行契约
- 将旧 `client/daemon/cli` 降级到 `legacy/`

目录总览：

- `image/`：镜像、启动链、恢复、更新
- `services/`：系统服务骨架
- `runtime/`：推理后端、路由、预算、profile
- `shell/`：AI Shell / compositor / UX 入口
- `policy/`：capability、审批、token、策略 profile
- `compat/`：浏览器、办公、MCP/A2A、代码沙箱桥接
- `hardware/`：硬件 profile 与 bring-up 资料
- `observability/`：audit、trace、诊断对象 schema
- `sdk/`：provider / portal / profile 共享 schema
- `legacy/`：仅保留迁移说明与过渡期占位

当前状态：

- 这是结构重构后的最小系统工程骨架
- 还没有完整实现 Linux 镜像、systemd 服务逻辑和 Wayland shell
- 下一阶段应优先实现 `runtimed`、`policyd`、provider registry 与 QEMU 开发镜像
