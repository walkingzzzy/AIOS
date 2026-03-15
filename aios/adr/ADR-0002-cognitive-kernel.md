# ADR-0002: Cognitive Kernel 不是 Linux 替代

- 状态：Accepted
- 日期：2026-03-08

## 决策

- Linux Kernel 仍是执行根与安全根
- `agentd` / `runtimed` / `sessiond` / `policyd` / `deviced` 构成 AIOS 的认知控制平面
- `LLM-as-Kernel` 仅表示认知系统调用抽象，不表示替代 ring0 kernel
- AI 不是授权根，`policyd`、execution token、audit chain 才是正式治理闭环的一部分

## 结果

- 所有高风险动作必须走 `intent -> plan -> policy -> token -> execution -> audit -> recovery`
- shell、model runtime、legacy console 都不能成为授权根
