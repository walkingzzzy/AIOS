# ADR-0004: 完整系统采用基线能力 + 条件能力声明模型

- 状态：Accepted
- 日期：2026-03-08

## 背景

AIOS 的目标是完整系统，而不是简化版 demo。  
但完整系统不等于每台机器、每个图形栈、每个 provider 都必须默认暴露全部扩展能力。

## 决策

- AIOS 采用 `baseline capability` + `declared optional capability` 的能力声明模型
- 基线能力必须长期稳定成立：bootable image、core services、native shell、policy / audit、rollback / recovery、`local-cpu`
- 条件能力按支持矩阵声明：`ui_tree`、`local-gpu`、`local-npu`、高级多模态、trusted offload、多显示器 / 高刷 / 触控增强
- 条件能力必须由 `hardware profile`、shell stack、provider support、policy state 共同决定是否激活

## 结果

- AIOS 保留完整系统目标，不再用“全平台无条件具备全部能力”定义完整性
- 对外支持声明必须以支持矩阵为准
- 未声明支持的条件能力不得被当作基线缺陷
