## 项目上下文摘要（E2E Mock 模式）
生成时间：2026-01-25 00:03:46

### 1. 相似实现分析
- **实现1**: aios/scripts/integration/saas-smoke.mjs
  - 模式：脚本内置 JsonRpcClient + env 开关，逐场景执行并记录结果
  - 可复用：record/runScenario/JsonRpcClient 结构
  - 需注意：缺少环境变量时直接失败，适配器状态需先检查
- **实现2**: aios/scripts/office-ui/office-smoke.mjs
  - 模式：daemon 入口校验 + 环境变量开关 + 统一日志函数
  - 可复用：daemonEntry 校验、跳过不支持套件的逻辑
  - 需注意：保持真实调用路径不被 mock 破坏
- **实现3**: aios/packages/daemon/src/__tests__/integration/OfficeLocalAdapter.integration.test.ts
  - 模式：JsonRpcClient + 环境变量控制用例执行
  - 可复用：按环境变量跳过真实场景
  - 需注意：用例描述与提示信息为中文

### 2. 项目约定
- **命名约定**: camelCase 变量/函数名，常量用全大写环境变量
- **文件组织**: 脚本集中在 `aios/scripts/*`
- **导入顺序**: Node 内置模块优先
- **代码风格**: 使用 const/let，日志输出中文

### 3. 可复用组件清单
- `aios/scripts/integration/saas-smoke.mjs`: JsonRpcClient、runScenario、record
- `aios/scripts/office-ui/office-smoke.mjs`: daemon 入口校验与日志格式
- `aios/packages/daemon/src/__tests__/integration/OfficeLocalAdapter.integration.test.ts`: 环境变量控制执行

### 4. 测试策略
- **测试框架**: Vitest + Playwright（E2E）
- **测试模式**: 集成与 E2E 通过环境变量开关跳过
- **参考文件**: aios/packages/client/src/__tests__/e2e/app.e2e.test.ts
- **覆盖要求**: 正常流程、权限/缺失场景

### 5. 依赖和集成点
- **外部依赖**: Node.js 内置模块（child_process、fs/promises、path）
- **内部依赖**: daemon 入口 `packages/daemon/dist/index.js`
- **集成方式**: JSON-RPC 通过 stdin/stdout 通道调用
- **配置来源**: 环境变量（AIOS_E2E_* / 凭证）

### 6. 技术选型理由
- **为什么用脚本层 mock**: 不影响适配器实现，方便无凭证环境验证流程
- **优势**: 无需真实凭证，可验证脚本结构与结果汇总
- **劣势和风险**: 可能掩盖真实适配器问题，需要文档明确仅作占位

### 7. 关键风险点
- **行为偏差**: mock 模式误导为真实通过
- **边界条件**: 未启用任何 AIOS_E2E_* 时仍应提示
- **稳定性**: mock 应避免影响非 mock 路径

### 8. 额外说明
- GitHub 搜索：因认证失败未获取结果，已记录在日志中。
- 文档查询：使用 context7 查询 Node.js child_process spawn 与 fs/promises access 用法。
