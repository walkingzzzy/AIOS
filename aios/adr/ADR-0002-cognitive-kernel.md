# ADR-0002: Cognitive Kernel 不是 Linux 替代

- 状态：Accepted
- 日期：2026-03-08

决策：

- Linux Kernel 仍是执行根与安全根
- `agentd` / `runtimed` / `sessiond` / `policyd` / `deviced` 构成 AIOS 的认知控制平面
- `LLM-as-Kernel` 仅表示认知系统调用抽象，不表示替代 ring0 kernel
