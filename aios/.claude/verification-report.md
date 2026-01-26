# 验证报告

## 验证摘要
- 目标：验证 OfficeLocalAdapter UI 扩展能力在目标平台的可用性。
- 结论：集成测试失败，需排查套件安装与权限问题；单元测试仍通过。

## 执行记录
- 命令：`AIOS_RUN_OFFICE_UI=1 AIOS_OFFICE_EXTENDED=1 pnpm --filter @aios/daemon test -- OfficeLocalAdapter`
- 结果：
  - OfficeLocalAdapter 单元测试通过（11 项）。
  - OfficeLocalAdapter 集成测试失败：完整 smoke 流程中的 word_create 返回失败。

## 初步判断
- 可能原因：
  - 本机未安装对应套件（默认 microsoft，Linux 默认 wps）。
  - UI 自动化权限未授权（macOS 辅助功能/屏幕录制）。
  - 前台焦点被占用导致 UI 操作失败。

## 建议下一步
- 明确套件：设置 `AIOS_OFFICE_SUITES=microsoft|wps`，并确保对应应用已安装。
- 授权：授予终端与 Office/WPS 辅助功能权限，关闭其他前台应用。
- 如需定位失败步骤，可运行 `scripts/office-ui/office-smoke.mjs` 输出逐步结果。
