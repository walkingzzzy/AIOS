# office

此目录用于实现 Office / document compat provider。

## 目标

提供受治理的：

- `compat.document.open`
- `compat.document.export`
- `compat.office.export_pdf`
- 结构化导出与文件格式桥接

## 当前状态

- 已有 provider descriptor
- 已有 baseline runtime，可读取本地 text / markdown / HTML 文档
- 已有 text-only PDF export baseline
- 已有 `compat-office-document-v1` 结构化 worker/result contract
- 已有 success / error 两类结构化返回
- 已有 missing file / unsupported type 的结构化失败语义
- 已有可选 schema-aligned JSONL audit sink，用于本地 machine-readable evidence
- 已有可选 `execution_token` / `AIOS_COMPAT_POLICYD_SOCKET` centralized policy verify 通路，以及 `AIOS_COMPAT_OBSERVABILITY_LOG` shared audit sink 镜像
- 已有 persistent remote registry、`none` / `bearer` / `header` / `execution-token` remote auth mode、allowlist trust policy 与 target-bound remote metadata
- 已有 remote office bridge：可把 `open` / `export-pdf` 请求转发到已注册远端 worker，并把远端 PDF 回写到本地路径
- 已有 `register-control-plane`：可把已注册 remote worker descriptor 通过 `agentd provider.register` 提升为 `attested_remote` provider，并携带 `attestation` / `governance` 元数据参与 resolve 路径，且已由 smoke 直接验证
- 已有 compat runtime smoke 覆盖 manifest / health / registry resolution
- 已有 export target handle 签发 baseline
- 仍未有 `docx/xlsx/pptx` 原生解析、富布局保真转换与完整 Office automation worker

## 当前边界

当前 runtime 已同时提供 **local fallback baseline** 与 **registered remote bridge baseline**，适合：

- 打开 text / markdown / HTML 文档
- 提取元数据、标题与预览
- 将文本内容导出为轻量 PDF
- 把受 trust policy 约束的 `open` / `export-pdf` 请求转发到 remote office worker
- 把 remote office worker 注册进 control-plane provider registry 参与 `attested_remote` 解析

当前不提供：

- `docx/xlsx/pptx` 原生解析
- 富样式布局保真导出
- 真正的 Office 应用桥接或 GUI 自动化
- 宏、嵌入对象、复杂分页控制

## 下一步

1. 把 export target handle 与 remote bridge 继续推进到更正式的 document worker / conversion pipeline
2. 在现有 remote attestation / fleet governance baseline 之上继续补更细粒度 target-bound policy、registration 生命周期与 fleet control-plane 约束
3. 把 office result protocol 继续接进更持久的导出产物 / operator audit correlation UI
