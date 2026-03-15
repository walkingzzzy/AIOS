# AIOS Route B 快速开始

**更新日期**: 2026-03-10

---

> **系统开发口径修订（2026-03-08）**
> AIOS 统一定义为 **AI 原生操作系统 / 系统软件工程**。本文如提及桌面应用、Electron 客户端、应用适配器、App 安装等内容，除非明确标注为“原型期 / 兼容层 / 历史实现”，否则不再代表目标形态。
> 当前最高约束：**系统镜像、系统服务、系统壳层、设备/能力抽象、权限与更新恢复**。

## 1. 先建立正确认知

你现在拿到的不是一个“待启动的 Electron 原型”，而是一个**已具备系统工程基线、但远未完成发行闭环**的 AIOS 仓库。

当前最短入口不是 `pnpm dev`，而是：

- 运行本地 CI 对齐验证
- 构建 delivery bundle
- 检查镜像 / QEMU preflight

## 2. 30 分钟快速上手

1. 阅读 [项目架构](../AIOS-Project-Architecture.md)
2. 阅读 [实现进展](../IMPLEMENTATION_PROGRESS.md)
3. 安装 Python / Rust 基础依赖并补齐 `PyYAML`
4. 在仓库根目录执行本地 `validate`
5. 查看生成的 bundle / validation 产物

推荐命令：

```bash
python3 -m pip install --upgrade pip PyYAML
python3 scripts/run-aios-ci-local.py --stage validate
```

## 3. 这 30 分钟里你会得到什么

- 六个核心服务的编译与单测结果
- provider registry / shell / compat / delivery smoke 结果
- `out/aios-system-delivery/` 交付产物
- boot preflight 结果

如果宿主环境已经具备镜像与 QEMU 依赖，可继续：

```bash
bash scripts/build-aios-image.sh --preflight
python3 scripts/run-aios-ci-local.py --stage system-validation --dry-run
python3 scripts/run-aios-ci-local.py --stage full --dry-run --output-prefix out/validation/full-regression-report
```

## 4. 新贡献者的第一条纪律

在开始写代码前，先回答：

- 我在做系统主线，还是 compat layer？
- 这个能力属于 `system`、`service`、`shell`、`device` 还是 `compat`？
- 它会不会把 AIOS 拉回“应用开发”路径？

## 5. 下一步阅读建议

- 做系统服务：看 [开发规范](AIOS-Protocol-DevSpec.md)
- 做壳层：看 [系统开发指南](AIOS-System-DevGuide.md)
- 做 provider：看 [Provider 开发指南](../adapters/01-Development.md)
- 做镜像 / 安装 / 恢复：看 [安装指南](../INSTALL.md) 与 `aios/image/README.md`
