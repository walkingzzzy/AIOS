# Tier 1 正式机器冻结清单

**状态**: `Baseline Delivered / Hardware Evidence Pending`  
**更新日期**: 2026-03-14  
**关联任务**: `P5-HW-001`、`P5-HW-003`、`P5-HW-004`

---

## 1. 目的

本文件用于冻结 AIOS 当前 `Tier 1` 正式机器清单。

它解决的不是“哪些平台理论上可以支持”，而是：

1. 当前仓库到底把哪几台机器视为正式 bring-up 目标
2. 每台正式机器绑定哪条 platform media / runtime / hardware profile 组合
3. 后续 `P5-HW-003` / `P5-HW-004` 应该优先在哪些机器上补实机证据

machine-readable 对应资产为：

- `aios/hardware/tier1-nominated-machines.yaml`

---

## 2. 当前冻结结论

截至 2026-03-14，AIOS 当前冻结两台正式 Tier 1 机器：

1. `framework-laptop-13-amd-7040`
2. `nvidia-jetson-orin-agx`

其中：

- 前者是当前主 x86_64 开发者机器
- 后者是当前主加速/异构算力开发机器

这份清单的意义是“正式 nomination / freeze”，不是“已经 hardware validated”。

---

## 3. 正式机器清单

| 机器 ID | 角色 | 绑定平台组合 | 运行时定位 | 当前状态 |
|------|------|------|------|------|
| `framework-laptop-13-amd-7040` | 主 x86_64 Tier 1 机器 | `generic-x86_64-uefi` | `local-cpu` 默认，保留 `local-gpu` 可选 | `nominated-formal-tier1` |
| `nvidia-jetson-orin-agx` | 主 accelerator Tier 1 机器 | `nvidia-jetson-orin-agx` | `local-gpu` 首选，保留 `local-cpu` fallback | `bringup-kit-only` |

---

## 4. 绑定关系

### 4.1 `framework-laptop-13-amd-7040`

- 机器 profile:
  `aios/hardware/profiles/framework-laptop-13-amd-7040.yaml`
- canonical platform combo:
  `generic-x86_64-uefi`
- updated platform profile:
  `/usr/share/aios/updated/platforms/generic-x86_64-uefi/profile.yaml`
- runtime profile:
  `/etc/aios/runtime/default-runtime-profile.yaml`

选择原因：

- 满足 Tier 1 对 Wi-Fi、蓝牙、音频、摄像头与 UEFI 的要求
- 维持集显优先、CPU fallback 优先的 x86_64 bring-up 路线
- 能作为 installer / firstboot / rollback / recovery 的主验证对象

### 4.2 `nvidia-jetson-orin-agx`

- 机器 profile:
  `aios/hardware/profiles/nvidia-jetson-orin-agx.yaml`
- canonical platform combo:
  `nvidia-jetson-orin-agx`
- updated platform profile:
  `/usr/share/aios/updated/platforms/nvidia-jetson-orin-agx/profile.yaml`
- runtime profile:
  `/usr/share/aios/runtime/platforms/nvidia-jetson-orin-agx/default-runtime-profile.yaml`

选择原因：

- 当前仓库里 GPU / managed worker 路线最完整
- 已有 platform media、worker bridge、Jetson runtime profile 与失败降级 smoke
- 是当前最合适的 accelerator-oriented bring-up 目标

---

## 5. 与平台支持矩阵的关系

这里冻结的是“正式机器”，不是“平台组合”本身。

因此：

- `generic-x86_64-uefi` 仍是平台交付组合
- `framework-laptop-13-amd-7040` 是绑定到该组合上的正式机器
- `nvidia-jetson-orin-agx` 同时是平台组合与正式机器

这也是为什么不能再把所有 x86_64 bring-up 都写成“某个 generic 参考机器”。

---

## 6. 后续任务如何使用

### 6.1 `P5-HW-003`

第一台实机 bring-up 报告应优先使用：

- `framework-laptop-13-amd-7040`

原因：

- 它覆盖主 x86_64 交付链
- 它直接决定 installer / firstboot / rollback / recovery 的主线是否成立

### 6.2 `P5-HW-004`

第二台实机 bring-up 报告应优先使用：

- `nvidia-jetson-orin-agx`

原因：

- 它覆盖 accelerator / local-gpu / managed worker 平台路径
- 能把 GPU 条件能力与硬件 bring-up 报告接起来

---

## 7. 当前声明边界

### 7.1 可以宣称的内容

- AIOS 已指定正式 Tier 1 机器清单
- 后续硬件验证不再停留在抽象“generic x86_64”口径
- `P5-HW-003` / `P5-HW-004` 已有明确优先目标

### 7.2 不能宣称的内容

- 不能宣称这两台机器已经完成 hardware validation
- 不能宣称 `framework-laptop-13-amd-7040` 已有 install / rollback / recovery 成功证据
- 不能宣称 `nvidia-jetson-orin-agx` 已有 release-grade Jetson bring-up 证据

---

## 8. 当前结论

截至 2026-03-14，`P5-HW-001` 的完成依据已经成立：

- 已有正式冻结清单
- 已有 machine-readable nomination asset
- 已有 x86_64 正式机器 profile
- 已明确后续两份 bring-up 报告的优先对象

因此 `P5-HW-001` 可以进入 `Done`。
