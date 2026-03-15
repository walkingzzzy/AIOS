# sdk/

`sdk/` 存放 AIOS 的共享 schema 与系统契约。  
它不是面向外部开发者市场化发布的 SDK，而是当前仓库内部和未来 provider / tooling 的契约源。

## 1. 负责什么

此目录用于：

- provider descriptor schema
- portal handle schema
- shared IDs / enums / object contracts
- 未来可抽出的 shared types 与 IDL

## 2. 当前状态

截至 2026-03-08：

- 已有：provider descriptor、portal handle schema
- 未有：共享类型库、版本迁移工具、schema 测试

当前判断：`Scaffold`

## 3. 约束

- 所有 schema 变更必须同步文档与服务实现
- provider / portal / token / audit 对象不得各自发明不兼容字段
- 未来如引入 IDL，必须先补 ADR
