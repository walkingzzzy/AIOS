# aios-system-intent-provider

`aios-system-intent-provider` 把 `system.intent.execute` 从 descriptor 变成真实的本地控制面 provider。

## 当前能力

- 通过 UDS + JSON-RPC 暴露 `system.intent.execute`
- 使用 `policyd` 校验 execution token，而不是接受裸 intent
- 使用 `sessiond` 读取 task / task plan，把 intent 转成结构化本地动作建议
- 启动后向 `agentd` 自注册并上报 provider health

## 当前边界

- 第一阶段只输出结构化控制动作建议，不直接执行危险系统变更
- 不替代 `agentd` 的 planner，只消费其已有 task plan 并在缺失时做最小启发式回退
- 不绕过 execution token

## 运行示例

```bash
cargo build -p aios-system-intent-provider
python3 scripts/test-system-intent-provider-smoke.py --bin-dir aios/target/debug
```
