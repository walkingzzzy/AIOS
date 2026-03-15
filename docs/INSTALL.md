# AIOS 系统开发环境安装指南

**更新日期**: 2026-03-10

---

> **系统开发口径修订（2026-03-08）**
> AIOS 统一定义为 **AI 原生操作系统 / 系统软件工程**。本文如提及桌面应用、Electron 客户端、应用适配器、App 安装等内容，除非明确标注为“原型期 / 兼容层 / 历史实现”，否则不再代表目标形态。
> 当前最高约束：**系统镜像、系统服务、系统壳层、设备/能力抽象、权限与更新恢复**。

## 1. 重要说明

当前仓库**已经具备 AIOS 系统工程基线**，包括：

- 本地 CI 对齐入口：`scripts/run-aios-ci-local.py`
- full regression suite 报告入口：`scripts/run-aios-ci-local.py --stage full --output-prefix out/validation/full-regression-report`
- system delivery bundle 构建：`scripts/build-aios-delivery.py`
- 系统镜像 / recovery / installer 构建入口：`scripts/build-aios-image.sh`、`scripts/build-aios-recovery-image.sh`、`scripts/build-aios-installer-image.sh`
- QEMU / 交付验证聚合：`scripts/test-system-delivery-validation.py`

但它**仍不是发行级完成态**：正式 shell/compositor、真实硬件验证、release-grade update/recovery 闭环仍未完成。

## 2. 推荐开发环境

### 必需工具
- Python 3.12（与 CI 保持一致，至少应使用能运行当前脚本的解释器）
- `PyYAML`
- Rust stable（当前最小工具链按 1.85.0 对齐）
- `cargo`
- `bash`

### 镜像 / 系统验证附加工具
- `qemu-system-x86_64`
- `qemu-img`
- `ovmf` / 对应 UEFI firmware
- `mkosi`，或可用的 `docker + git`（`scripts/build-aios-image.sh` 支持容器化回退）

### 推荐宿主环境
- Linux-first
- macOS / 其他宿主可先运行本地 `validate`、bundle 构建和 preflight；完整 image-level 验证需要镜像与 QEMU 依赖齐备

## 3. 最短可用验证路径

在**仓库根目录**执行：

```bash
python3 -m pip install --upgrade pip PyYAML
python3 scripts/run-aios-ci-local.py --stage validate
```

这条路径会按 CI 顺序执行：

- task metadata 校验
- Python 语法检查
- Rust workspace 单测
- provider / shell / compat / delivery smoke
- boot preflight

## 4. 镜像与系统级验证路径

建议先做 preflight，再执行重型步骤：

```bash
bash scripts/build-aios-image.sh --preflight
python3 scripts/run-aios-ci-local.py --stage system-validation --dry-run
python3 scripts/run-aios-ci-local.py --stage full --dry-run --output-prefix out/validation/full-regression-report
```

宿主环境满足条件后，再执行：

```bash
bash scripts/build-aios-image.sh
bash scripts/build-aios-recovery-image.sh
bash scripts/build-aios-installer-image.sh
python3 scripts/test-system-delivery-validation.py
python3 scripts/run-aios-ci-local.py --stage full --output-prefix out/validation/full-regression-report
```

## 5. 当前不再推荐的理解方式

以下理解方式已废弃：

- “把 AIOS 安装到 Applications / Program Files 就完成了安装”
- “打一个 DMG / EXE 就代表 AIOS 发布”
- “Electron 客户端就是 AIOS”

## 6. 现阶段团队协作建议

- 想验证仓库当前是否健康：优先运行 `scripts/run-aios-ci-local.py --stage validate`
- 想推进镜像 / 安装 / 恢复主线：优先准备 Linux-first + QEMU 环境
- `compat/` 与 `legacy/` 仅作为迁移与桥接资产，不应再充当主入口说明
- 所有新文档与新模块，必须显式说明自己属于系统主线还是 compat layer
