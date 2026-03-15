# ADR-0008: Sandbox engine 采用 bubblewrap 风格隔离 + language runtime adapter 的组合路线

- 状态：Accepted
- 日期：2026-03-09

## 背景

AIOS 需要 compat code sandbox，但此前只有 README，没有正式 sandbox engine ADR，导致动态代码执行、browser compat、office compat 与 bridge runtime 都缺统一隔离模型。

## 决策

- sandbox engine 的系统级方向采用 `bubblewrap` 风格的最小文件系统 / 最小网络 / 资源限额隔离
- 语言执行层通过 runtime adapter 接入，例如 Python、WASI、browser automation worker
- 开发阶段允许使用本地最小 executor skeleton 验证结果回传协议、CPU / memory / timeout 限额与审计字段
- 所有 compat runtime 都必须进入 provider registry、policy、audit，不能因“沙箱内执行”获得豁免

## 结果

- compat / sandbox 轨道拥有正式路线
- `code-sandbox` 可以先以本地 executor skeleton 起步，再替换为真实 sandbox engine
- browser / office / bridge runtime 的隔离边界更一致
