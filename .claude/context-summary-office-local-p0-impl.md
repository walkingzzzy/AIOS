## 项目上下文摘要（本地 Office P0 能力实现）
生成时间：2026-01-25 13:20:45

### 1. 相似实现分析
- **实现1**: aios/packages/daemon/src/adapters/office/OfficeLocalAdapter.ts:96-760
  - 模式：能力列表 + invoke 分发 + 平台分支（Windows COM / macOS-Linux UI）
  - 可复用：路径安全校验、UI 自动化流程、Clipboard 读写、Excel/Word/PPT 基础流程
  - 需注意：UI 自动化强依赖焦点与权限；path 安全检查必须保持一致

- **实现2**: aios/packages/daemon/src/adapters/system/FileAdapter.ts:20-200
  - 模式：guardPath 校验 + fs 操作 + capability 分发
  - 可复用：路径安全模型与文件操作风格、错误码
  - 需注意：路径白名单与敏感路径策略一致性

- **实现3**: aios/packages/daemon/src/adapters/productivity/Microsoft365Adapter.ts:1-200
  - 模式：能力列表与分支处理、参数校验与错误返回
  - 可复用：能力定义与参数约定风格
  - 需注意：保持 capability 命名一致

### 2. 项目约定
- **命名约定**: capability 使用 snake_case，适配器 id 使用 com.aios.adapter.*
- **文件组织**: adapter 按领域目录归类（office/system/productivity）
- **导入顺序**: Node 内置 -> 外部包 -> 本地模块
- **代码风格**: TypeScript + 中文注释，错误码使用大写下划线

### 3. 可复用组件清单
- aios/packages/daemon/src/adapters/office/OfficeLocalAdapter.ts: 路径安全、UI 自动化、剪贴板工具
- aios/packages/daemon/src/adapters/system/FileAdapter.ts: 文件操作与路径 guard 模式
- aios/packages/daemon/src/adapters/BaseAdapter.ts: success/failure 返回结构

### 4. 测试策略
- **测试框架**: Vitest
- **测试模式**: 单元测试 + 集成测试（需真实桌面环境）
- **参考文件**:
  - aios/packages/daemon/src/__tests__/adapters/OfficeLocalAdapter.test.ts
  - aios/packages/daemon/src/__tests__/integration/OfficeLocalAdapter.integration.test.ts
- **覆盖要求**: 正常流程 + 安全路径拒绝 + 平台分支

### 5. 依赖和集成点
- **外部依赖**: Node.js fs/os/path/child_process
- **内部依赖**: BaseAdapter、@aios/shared（getPlatform、spawnBackground）
- **集成方式**: 通过 adapterRegistry 注册能力，daemon invoke 路由调用
- **配置来源**: 环境变量与运行平台能力

### 6. 技术选型理由
- **为什么用本地方案**: 离线可用、可控性高、避免云端依赖
- **优势**: 适配既有 OfficeLocalAdapter 框架，易于扩展
- **劣势和风险**: UI 自动化易受焦点影响，macOS 需辅助功能权限

### 7. 关键风险点
- **并发问题**: UI 自动化需要串行执行，继续复用 operationQueue
- **边界条件**: 路径安全、文件不存在、权限缺失
- **性能瓶颈**: 大文件操作需避免频繁打开 UI
- **安全考虑**: 继续复用路径白名单与敏感模式拦截

### 8. 工具与检索限制说明
- desktop-commander/context7/github.search_code 不可用，已使用 rg + 本地阅读 + web fetch 替代，并记录在操作日志。
