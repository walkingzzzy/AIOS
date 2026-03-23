# browser

此目录用于实现浏览器 compat provider。

## 目标

提供受治理的：

- `compat.browser.navigate`
- tab / window / export target 相关能力
- 浏览器桥接优先于 GUI automation

## 当前状态

- 已有 provider descriptor
- 已有 baseline runtime，可执行受限 HTML / text fetch
- 已有 `compat-browser-fetch-v1` 结构化 worker/result contract
- 已有 success / not-found / error 三类结构化返回
- 已有 invalid scheme / timeout / unavailable 的结构化失败语义
- 已有可选 schema-aligned JSONL audit sink，用于本地 machine-readable evidence
- 已有可选 `execution_token` / `AIOS_COMPAT_POLICYD_SOCKET` centralized policy verify 通路，以及 `AIOS_COMPAT_OBSERVABILITY_LOG` shared audit sink 镜像
- 已有 `navigate` / `extract` 命令与本地 smoke 覆盖
- 已有 persistent remote registry、`none` / `bearer` / `header` / `execution-token` remote auth mode、allowlist trust policy 与 target-bound remote metadata
- 已有 remote browser bridge：可把 `navigate` / `extract` 请求转发到已注册远端 worker，并返回结构化 bridge metadata
- 已有 `register-control-plane`：可把已注册 remote worker descriptor 通过 `agentd provider.register` 提升为 `attested_remote` provider，并携带 `attestation` / `governance` 元数据参与 resolve 路径，且已由 smoke 直接验证
- 已有 compat runtime smoke 覆盖 manifest / health / registry resolution
- 已有基于 session store 的本地 session/window/tab lifecycle，并可把 `navigate` / `extract` 状态回写到 tab 绑定
- 仍未有 JS-rendered DOM、登录态 / cookie jar、下载与自动化级浏览器执行栈

## 当前边界

当前 runtime 已同时提供 **governed fallback baseline** 与 **registered remote bridge baseline**，适合：

- `file://` / `http(s)://` 页面拉取
- 标题、纯文本预览、链接摘要
- 基于简单 selector（tag / `#id` / `.class`）的文本提取
- 把受 trust policy 约束的请求转发到 remote browser worker
- 把 remote browser worker 注册进 control-plane provider registry 参与 `attested_remote` 解析

当前不提供：

- 真实浏览器内核驱动的 session / cookie jar / 多页交互
- JS 执行后的 DOM
- 登录态继承、下载、screenshot 与 form automation

## 下一步

1. 把当前本地 session/window/tab model 继续推进到真正的 browser target adapter、cookie jar 与 automation-backed session
2. 在现有 remote attestation / fleet governance baseline 之上继续补更细粒度 target-bound policy、registration 生命周期与 fleet control-plane 约束
3. 把 browser bridge/result protocol 继续接进更持久的 operator audit query / correlation UI
