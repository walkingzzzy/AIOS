# code-sandbox

此目录用于实现 AIOS 的动态代码受限执行环境。

## 目标

承载：

- 小型转换脚本
- 受限数据处理逻辑
- 不能直接放进 core services 的短生命周期代码执行

## 当前状态

- 已有 provider descriptor
- 已有 bounded local sandbox runtime
- 已有 CPU / memory / timeout 限额
- 已有默认禁用网络 / 子进程、临时工作目录、input/output 目录约定
- 已有显式 `worker_contract` / `result_protocol_schema_ref`
- 已有结构化 `compat-sandbox-executor-v1` result protocol，覆盖 success / timeout / policy-deny / runtime-error
- 已有 schema-aligned JSONL audit envelope，与 compat runtime smoke 覆盖 manifest / health / execute / timeout / deny
- 已有可选 `execution_token` / `AIOS_COMPAT_POLICYD_SOCKET` centralized policy verify 通路，以及 `AIOS_COMPAT_OBSERVABILITY_LOG` shared audit sink 镜像
- 已有 `bubblewrap` 可用时优先启用的 OS 级 sandbox engine，并保留 bounded-local fallback

## 约束

- 动态代码不是越权理由
- 必须有 CPU / memory / timeout 限额
- 必须默认最小文件系统与最小网络
- 必须进入 audit 链

## 下一步

1. 继续收紧 `bubblewrap` mount / network / tmpfs 策略与失败回退证据
2. 评估 `bubblewrap` 与 WASI 的分工
3. 把 provider wrapper / registry discover / operator audit correlation 继续做完整
