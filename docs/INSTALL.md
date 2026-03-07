# AIOS 系统开发环境安装指南

**更新日期**: 2026-03-08

---

> **系统开发口径修订（2026-03-08）**
> AIOS 统一定义为 **AI 原生操作系统 / 系统软件工程**。本文如提及桌面应用、Electron 客户端、应用适配器、App 安装等内容，除非明确标注为“原型期 / 兼容层 / 历史实现”，否则不再代表目标形态。
> 当前最高约束：**系统镜像、系统服务、系统壳层、设备/能力抽象、权限与更新恢复**。

## 1. 重要说明

当前仓库**尚不能生成可启动的 AIOS 系统镜像**。
因此本安装文档分为两部分：

1. **运行现有兼容层原型**（用于验证编排与接口）
2. **准备 Route B 系统开发环境**（用于后续镜像、服务、壳层开发）

## 2. 运行现有兼容层原型

### 前置条件
- Node.js 20+
- pnpm 8+

### 步骤
```bash
git clone https://github.com/aios-protocol/aios.git
cd aios
pnpm install
pnpm build
pnpm dev
```

### 说明
- 这一步运行的是 **原型期兼容层**
- 它可以验证 AI 编排、任务流、兼容控制与桥接能力
- 它不是 AIOS 的最终安装形态

## 3. Route B 系统开发环境

### 推荐宿主环境
- Linux 主机，或
- Linux 虚拟机（QEMU / UTM / VMware / VirtualBox）

### 推荐工具链
- Rust stable
- cargo / rustfmt / clippy
- QEMU
- systemd 开发工具
- Wayland / wlroots / smithay 相关依赖
- 镜像构建工具（如 mkosi）

### 推荐目录职责
- `image/`：镜像与启动链
- `services/`：系统服务
- `shell/`：壳层与 compositor
- `policy/`：权限、审计、恢复
- `compat/`：兼容层
- `legacy/`：原型控制台

## 4. 当前不再推荐的理解方式

以下理解方式已废弃：

- “把 AIOS 安装到 Applications / Program Files 就完成了安装”
- “打一个 DMG / EXE 就代表 AIOS 发布”
- “Electron 客户端就是 AIOS”

## 5. 现阶段团队协作建议

- 想验证 AI 功能与协议：运行兼容层原型
- 想推进操作系统主线：优先准备 Linux-first 开发环境
- 所有新文档与新模块，必须显式说明自己属于系统主线还是 compat layer
