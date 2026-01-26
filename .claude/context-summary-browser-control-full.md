## 项目上下文摘要（浏览器控制全面实现）
生成时间：2026-01-24 17:38:30

### 1. 相似实现分析
- **实现1**: aios/packages/daemon/src/adapters/browser/BrowserAdapter.ts
  - 模式：BaseAdapter + capabilities 列表 + invoke 分发 + success/failure 统一返回
  - 可复用：NetworkGuard.checkUrl、懒加载浏览器实例、错误信息中文化
  - 需注意：当前仅支持 open_url/search/导航/截图/标题，缺少 DOM 交互与多页管理

- **实现2**: aios/packages/daemon/src/adapters/system/DesktopAdapter.ts
  - 模式：参数校验函数 + switch 分发 + 平台分支处理
  - 可复用：ensureNumber/输入校验方式、能力参数定义风格
  - 需注意：所有错误提示为中文，permissionLevel 设置与风险等级一致

- **实现3**: aios/packages/daemon/src/adapters/system/FileAdapter.ts
  - 模式：安全检查封装 + guardPath 复用 + 失败即时返回
  - 可复用：安全检查与参数校验的 guard 结构、失败码统一
  - 需注意：涉及安全域白名单与阻断逻辑，和 NetworkGuard 类似思路

### 2. 项目约定
- **命名约定**: 适配器能力使用 snake_case（如 open_url、get_current_url）；类/方法使用 camelCase
- **文件组织**: 适配器位于 aios/packages/daemon/src/adapters/<domain>/；测试位于 aios/packages/daemon/src/__tests__/adapters/
- **导入顺序**: 先 type 导入，再第三方/共享模块，再本地模块
- **代码风格**: TypeScript；错误信息与注释全部中文；switch 分发；返回 success/failure 结构

### 3. 可复用组件清单
- aios/packages/daemon/src/adapters/BaseAdapter.ts: success/failure 返回与统一接口
- aios/packages/daemon/src/core/security/NetworkGuard.ts: URL 白名单与阻断
- aios/packages/daemon/src/core/ToolExecutor.ts: capabilities -> tool 映射与权限校验

### 4. 测试策略
- **测试框架**: Vitest
- **测试模式**: 单元测试 + mock 外部依赖
- **参考文件**: aios/packages/daemon/src/__tests__/adapters/BrowserAdapter.test.ts
- **覆盖要求**: 正常流程 + 参数校验失败 + 安全阻断 + 异常处理

### 5. 依赖和集成点
- **外部依赖**: Playwright（浏览器控制）
- **内部依赖**: NetworkGuard、BaseAdapter、ToolExecutor 权限链路
- **集成方式**: ToolExecutor 调用 adapter.invoke；capability 定义驱动工具暴露
- **配置来源**: NetworkGuard 内置白名单；headless 参数由调用方传入

### 6. 技术选型理由
- **为什么用这个方案**: 现有 BrowserAdapter 已基于 Playwright，扩展成本低，能覆盖 DOM 操作、截图与提取需求
- **优势**: 跨平台、能力丰富、与现有 Adapter 架构一致
- **劣势和风险**: 需要处理多页/多上下文管理与安全白名单限制

### 7. 关键风险点
- **并发问题**: 多次调用共享单一 page 可能造成状态污染
- **边界条件**: selector 不存在、超时、导航中断
- **性能瓶颈**: 过度截图或大 DOM 提取导致内存消耗
- **安全考虑**: NetworkGuard 默认白名单不含电商域名，需要明确授权策略

