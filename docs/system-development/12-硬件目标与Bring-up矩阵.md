# 12 · 硬件目标与 Bring-up 矩阵

**版本**: 1.1.1  
**更新日期**: 2026-03-08  
**状态**: P1/P2 必备规格

---

## 1. 目标

如果没有硬件目标，AIOS 会持续停留在抽象架构阶段。  
本文件定义 v1 必须支持的硬件范围与 bring-up 顺序，并把异构算力纳入验证范围。

## 2. 平台分级

### Tier 0 · 开发基线

- `x86_64` QEMU / KVM / UTM 虚拟机
- UEFI 启动
- VirtIO 磁盘 / 网卡 / 显示
- CPU-only runtime fallback

这是所有系统功能开发的默认基线，不允许跳过。

### Tier 1 · 开发者硬件

- Intel / AMD x86_64 UEFI 笔记本或台式机
- 集显优先，可选独显
- 常见 Wi-Fi / 蓝牙 / 音频 / 摄像头设备
- 若存在 NPU，则作为增强项验证

当前冻结的正式 Tier 1 机器见 [39-Tier1-正式机器冻结清单.md](39-Tier1-正式机器冻结清单.md)：

- `framework-laptop-13-amd-7040`
- `nvidia-jetson-orin-agx`

### Tier 2 · 扩展平台

- ARM64 开发板或迷你主机
- 独立 NPU / AI PC 场景
- 多显示器、高刷、触控等增强场景

Tier 2 不得阻塞 v1 发布。

## 3. v1 推荐硬件策略

- 先做 `QEMU x86_64`
- 再收敛到 2-3 台固定开发者硬件
- 先证明 CPU-only fallback 可用
- 再做 GPU / NPU 的受控加速接入
- 最后再扩展 ARM64 与异构硬件

禁止一开始就追求“全平台通吃”。

## 3.1 完整系统与条件能力声明

AIOS 的完整系统目标覆盖 GPU / NPU、多模态、复杂图形栈与可信云等能力域；  
但这些能力不应被写成“所有支持机器、所有图形栈、所有软件默认同时具备”的前提。

建议将能力声明分为三类：

- **Baseline Mandatory**：启动链、核心 services、AI Shell、`local-cpu` runtime、更新 / 回滚 / 恢复、policy / audit
- **Declared Optional**：`ui_tree`、`local-gpu`、`local-npu`、高级多模态、trusted offload、多显示器 / 高刷 / 触控增强
- **Experimental**：Tier 2 平台、前沿加速器、尚未长期维护的外设或图形栈能力

规则：

- 任何 Optional / Experimental 能力都必须挂在 `hardware profile` 与支持矩阵下声明
- 未声明支持的能力不能被视为“系统缺陷”，只能视为“当前 profile 不覆盖”
- 但一旦对外宣称支持，就必须满足策略、审计、降级和恢复要求

## 4. bring-up 阶段

### Stage 1 · Boot Bring-up

- 固件进入 bootloader
- kernel / initrd 正常加载
- 能到达 `systemd` multi-user 或等价目标

### Stage 2 · Storage / Logging Bring-up

- 分区识别
- 日志可写
- `var`、`home`、`model-cache`、恢复入口可用

### Stage 3 · Runtime Bring-up

- `runtimed` 可启动
- CPU-only 推理包装器可工作
- queue / budget / timeout 有安全默认值

### Stage 4 · Graphics / Input Bring-up

- Wayland compositor 可启动
- 键盘、鼠标、触摸板输入正常
- 分辨率与基础窗口栈稳定

### Stage 5 · GPU / NPU Bring-up

- GPU / NPU 可枚举
- 设备能力与 driver 状态可见
- runtime 能做安全降级与 fallback
- 显存 / 共享内存预算可观测
- 任何 `local-npu` 支持都必须与具体 `hardware profile` 绑定，而不是抽象为全平台默认能力

### Stage 6 · Audio / Camera / Multimodal Bring-up

- 麦克风、扬声器、蓝牙、摄像头可枚举
- 屏幕 / 音频 / 输入至少两类管线可进入 AIOS 感知层
- 敏感设备权限控制生效
- `ui_tree` 若存在，必须声明其来源（compositor、可访问性树、portal 或 provider），否则默认走 `screen_frame + OCR`

### Stage 7 · Network / Trusted Offload Bring-up

- 有线 / VirtIO 网络可用
- 时间同步可用
- 可信云卸载路径可显式开启 / 关闭
- attestation 失败时有可验证的拒绝行为
- trusted offload 只在声明支持的硬件 / 策略组合中进入可用态

### Stage 8 · Reliability Bring-up

- 睡眠唤醒
- 更新回滚
- 恢复模式
- 崩溃日志与诊断包导出

## 5. 硬件验证矩阵

| 能力项 | Tier 0 | Tier 1 | Tier 2 |
|--------|--------|--------|--------|
| UEFI 启动 | 必须 | 必须 | 建议 |
| 核心 services 启动 | 必须 | 必须 | 建议 |
| CPU-only runtime | 必须 | 必须 | 建议 |
| AI Shell | 必须 | 必须 | 建议 |
| GPU / NPU 枚举 | 可选 | 建议 | 必须 |
| 更新回滚 | 必须 | 必须 | 建议 |
| Wi-Fi / 蓝牙 | 可选 | 必须 | 建议 |
| 摄像头 / 麦克风 | 可选 | 必须 | 建议 |
| trusted offload toggle | 可选 | 建议 | 建议 |
| 睡眠唤醒 | 可选 | 必须 | 建议 |

## 6. 设备抽象优先级

优先级从高到低：

1. 显示与输入
2. 存储与日志
3. 运行时 CPU fallback
4. 网络
5. 音频
6. 摄像头
7. GPU / NPU 加速
8. 蓝牙与专用加速器

原因：v1 首先要证明 AIOS 是一个可启动、可交互、可恢复、可降级的系统。

## 7. 退出条件

### 开发者预览前

必须至少满足：

- Tier 0 全通过
- Tier 1 至少 2 台硬件通过基本图形与更新回滚验证
- 核心 services、runtime、shell、policy、recovery 在固定硬件上稳定
- runtime 在无 GPU / NPU 时也能安全降级运行
- 所有 Optional 能力都有“支持 / 不支持 / 实验中”的明确标注

### 产品预览前

必须至少满足：

- Tier 1 有稳定支持清单
- 已知不支持硬件有明确说明
- 升级与恢复策略在支持硬件上通过
- 若宣称支持 NPU / GPU，则需有资源预算与降级策略文档
- 若宣称支持 `ui_tree` 或 trusted offload，则需有对应支持栈、限制说明与审计语义文档

## 8. 与当前仓库的关系

当前 `aios/packages/*` 代码主要只能复用到：

- `agentd` 的任务编排原型
- `sessiond` 的任务 / 会话语义原型
- compat provider 的桥接经验
- runtime 接口层的早期包装逻辑

它们不能替代：

- 启动链 bring-up
- 异构硬件验证
- Wayland shell bring-up
- runtime budget / memory budget 验证
- 更新 / 恢复验证

## 9. 结论

AIOS 的系统开发不应从“再做几个功能页”开始，而应从“在哪些机器上能稳定启动、进入 shell、执行最小任务、在资源受限时安全降级，并且可回滚恢复”开始。
