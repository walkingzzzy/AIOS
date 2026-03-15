# ADR

此目录存放 AIOS Route B 的 Architecture Decision Records。

## 规则

以下事项必须先补 ADR，再进入主线实现：

- 新系统服务边界
- 新 capability 域
- 新 profile / route 策略
- 新 provider / portal / bridge 方式
- 新镜像、恢复、更新策略
- 新 shell stack / compositor 路线
- 新 sandbox engine / code execution 路线
- 新 memory backend / audit storage 路线
- 新的本地 IPC / bridge 边界调整
- 条件能力支持矩阵的正式引入或对外承诺

## 当前已冻结 ADR

- `ADR-0001`：Linux-first + image-based + system-service-first
- `ADR-0002`：Cognitive Kernel 不是 Linux 替代
- `ADR-0003`：Provider Registry 与 Portal 为统一执行入口
- `ADR-0004`：完整系统采用基线能力 + 条件能力声明模型
- `ADR-0005`：核心控制面本地 IPC 优先，MCP / A2A 属于 bridge / interop 层
- `ADR-0006`：Shell stack 采用 Smithay compositor + GTK4 panels 分层路线
- `ADR-0007`：Update stack 采用 systemd-sysupdate + boot control adapter 模型
- `ADR-0008`：Sandbox engine 采用 bubblewrap 风格隔离 + runtime adapter 路线
- `ADR-0009`：控制面记忆后端采用 SQLite 主存储 + 分层视图模型
- `ADR-0010`：核心控制面 RPC wire contract 采用共享 manifest + 结构化错误模型

## 约束

- ADR 一旦接受，相关 `docs/system-development` 文档必须同步
- 若某项能力只在特定硬件 / 图形栈 / provider / policy 组合下成立，必须同步更新支持矩阵
- 未经 ADR 冻结，不得把实验能力直接写成稳定默认能力
