# tasks/

`tasks/` 保存 AIOS 的 machine-readable 任务元数据。

当前文件：

- `master-task-list.yaml`：从 `docs/system-development/21-完整任务清单.md` 导出的完整任务清单
- `execution-board.yaml`：从 `docs/system-development/22-执行任务看板.md` 导出的当前执行队列与阻塞

同步命令：

```bash
python3 scripts/sync-aios-task-metadata.py
```

校验命令：

```bash
python3 scripts/sync-aios-task-metadata.py --check
```

约束：

- `docs/system-development/21-完整任务清单.md` 仍是任务定义来源
- `docs/system-development/22-执行任务看板.md` 仍是执行节奏来源
- `tasks/` 用于交付、CI、报表与后续自动化，不应手工漂移
