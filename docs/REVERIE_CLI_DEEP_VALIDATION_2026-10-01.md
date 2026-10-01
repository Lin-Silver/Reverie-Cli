# Reverie Desktop 深入验证与本地提交记录

本轮延续 S01–S21，重点验证图片提交、UI/UX、动效、真实文件/剪贴板、Git、终端及打包内核 bridge。T01–T05、X01–X08、Local/Cloud 继续排除。用户追加“验证后提交”后，本轮准备并执行范围明确的本地 Git 提交，没有推送授权。完整 21 项的代码实现、UI/UX、通过证据和未完成验收矩阵仍见 [阶段实施记录](REVERIE_CLI_IMPLEMENTATION_REPORT_2026-09-30.md)。

## 本轮修复

| 问题 | 代码实现与 UI/UX | 验证方式 |
| --- | --- | --- |
| 图片预览只放大缩略图，弹层焦点泄漏 | 按真实文件读取原始分辨率；显示加载/读取失败及版本；固定副本改变时要求重新导入；Tab/Shift+Tab 留在弹层，Escape 关闭并回到入口，组合输入不误关 | 组件回归与实际 2048×1536 PNG、键盘焦点、截图 |
| 丢失文件错误挤出重试/删除按钮 | 错误文本限高可滚动，操作区保留可见位置，低窗口附件区适配 | 删除真实 PNG 后重启、检查按钮边界、重建文件后重试 |
| 跨项目排队图片可能发往当前项目 | 请求使用队列所属 `runRoot` | 切项目后队列仍发往原目录，并保留另一个项目草稿的回归 |
| 空历史中的新对话忽略未发送图文 | 只有无文本、无附件的空对话才复用；有草稿时创建新会话 | 新建/返回原会话，文字和照片独立恢复 |
| 手动模型图片能力因 ID 不一致显示未知 | 用选中目录项 ID 查能力，不用实际请求模型名匹配索引 ID | 已知支持/不支持两个回归场景与实际测试目录模型 |
| 本机模型端点误走 Windows 自动代理 | 未显式配置代理的 loopback 使用直接 HTTP 客户端；显式代理继续生效 | 两条真实 HTTP 测试；实际编译内核发送图片到本机记录端点 |
| 发送成功后只有文件说明，图片没有预览入口 | 历史消息按内容顺序显示图片入口；纯图片历史不丢弃；发送等待期间保留附件身份 | 纯图片、混合两图和中间文本、重新打开会话、实际工作面板预览；三个相关回归 |
| 窄窗口输入器出现横向滚动条 | 收紧输入器装饰层边界；保留附件列表自身横向滚动 | 深浅主题 800/1024/1440 窗口，页面和输入器容器分别核对宽度 |

## 实际构建与测试

- 内核真实 PyInstaller 编译及 Electron 打包：[deep-kernel-final-pack.log](../.runtime/implementation-20260930/deep-kernel-final-pack.log)。最终 UI 经 TypeScript/Vite 编译再目录打包：[deep-layout-delivery-pack.log](../.runtime/implementation-20260930/deep-layout-delivery-pack.log)。程序：[ReverieUI.exe](../ReverieCli-ui/release/win-unpacked/ReverieUI.exe)。验证对象为 Windows x64 目录包，不将此结果称为安装器安装验证。
- Typecheck/i18n 通过，918 个翻译、77 个模板。完整 UI 测试 **200 passed、1 skipped**：[deep-ui-final-tests.log](../.runtime/implementation-20260930/deep-ui-final-tests.log)。测试临时目录位于本项目内，磁盘集成测试使用单 worker、120 秒测试上限和 30 秒清理上限。
- 相关 Python 测试 **179 passed**：[deep-python-final.log](../.runtime/implementation-20260930/deep-python-final.log)，包括桌面 bridge、输入/控制、工具权限、命令取消、模型 transport 与代理。
- 最终包重跑照片/UI **24/24**、本机照片协议 **8/8**、R2 Git/预览 **20/20**、R3 原生终端/bridge **14/14**、R4 双目录/恢复 **17/17**；共 83 条断言。R2 使用全新项目内仓库和 bare remote 重跑 Git 闭环，结果见同名证据。本轮新增 18 张照片/UI 关键截图，并更新原有 R2/R3/R4 截图。
- 中途验证曾失败：旧测试配置重复模型名导致选择旧端点；纯图协议包含自动文件说明，最初断言错误地要求只有图片；项目内 TEMP 暴露父 Git 发现和 5/30 秒超时及 Windows 清理锁。改用全新独立测试目录、按图片顺序/字节校验、隔离非仓库夹具的 Git 边界、顺序执行和清理重试后重新验证。构建也曾因自己的验收进程占用 DLL 失败，关闭该进程后重打包。失败尝试不作为成功证据。
- jsdom 的 canvas 提示没有被当作 PDF/终端渲染证明；运行截图、原生进程、像素和磁盘结果提供对应证据。
- R2 重跑的旧 harness 曾等待 PDF iframe 而超时；当前实现已使用 PDF canvas。修正检查实际 canvas 后，20 项完整通过，PDF 第 2 页像素验证仍由 R3 提供。

## 界面验收路径

验收使用实际目录包和独立 `PORTABLE_EXECUTABLE_DIR`，通过现有 Python Playwright API/CDP 操作自己的 Electron 页面。最终测试、打包和实机验收的文件、Git 仓库、HTTP 端点、日志、截图和备份均留在 `.runtime/implementation-20260930`；没有替换用户原配置。早期一次 UI 单元测试继承了系统 TEMP，测试具有自动清理，随后改为项目内 TEMP 并完整重跑。

1. **导入与预览：已修复。** 真实 PNG/JPEG 拖放显示尺寸、顺序和版本，原生剪贴板图片导入；预览读取原图、焦点循环和关闭恢复可用。[附件](../.runtime/implementation-20260930/deep-screenshots/02-photos-imported.png)、[预览](../.runtime/implementation-20260930/deep-screenshots/03-photo-preview.png)。
2. **发送与历史：协议通过，真实视觉理解待验。** 实际内核把纯图片和混合图片发送到本机 HTTP 记录端点，图片字节哈希和次序匹配源文件；完成记录有独立内核 PID，重新打开后可预览图片。[发送等待](../.runtime/implementation-20260930/deep-screenshots/13-pure-photo-running.png)、[混合消息](../.runtime/implementation-20260930/deep-screenshots/11-mixed-photo-contract.png)、[历史图片预览](../.runtime/implementation-20260930/deep-screenshots/12-sent-photo-preview.png)。
3. **失败与恢复：已修复。** 原配置无活动模型时失败可见，图文草稿保留；真实图片删除后禁止发送，重试按钮可见；文件恢复后重试恢复资格。[发送失败](../.runtime/implementation-20260930/deep-screenshots/05-send-failure-preserved.png)、[文件丢失](../.runtime/implementation-20260930/deep-screenshots/06-missing-photo.png)、[恢复](../.runtime/implementation-20260930/deep-screenshots/07-retry-recovered.png)。
4. **布局与动效：已修复。** 深浅主题、800/1024/1440×700 输入区完整，输入器不产生额外横向滚动；正常布局 transition 有界，系统 reduced motion 禁用布局动效。截图在预览动效结束后保存。[深色窄窗口](../.runtime/implementation-20260930/deep-screenshots/08-photos-dark-800.png)、[浅色窄窗口](../.runtime/implementation-20260930/deep-screenshots/08-photos-light-800.png)。
5. **Git、终端、bridge 与独立目录：本地路径通过，服务项待验。** 真实 hunk 暂存/提交及项目内 bare remote 推送证据在 R2；原生 PTY、中文文件、Ctrl+C、复制/日志入未发送草稿、exit 7、PDF 第 2 页、日志导出在 R3；双工作目录的 PTY/内核 PID、FIFO 等待取消和脏目录归档恢复在 R4。证据：[R2](../.runtime/implementation-20260930/r2-runtime-evidence.json)、[R3](../.runtime/implementation-20260930/r3-runtime-evidence.json)、[R4](../.runtime/implementation-20260930/r4-runtime-evidence.json)。主项目没有执行测试用 push。

照片/UI 证据：[deep-ui-runtime-evidence.json](../.runtime/implementation-20260930/deep-ui-runtime-evidence.json)、[photo-contract-runtime-evidence.json](../.runtime/implementation-20260930/photo-contract-runtime-evidence.json)。本机端点只记录协议并返回固定 `CONTRACT_ONLY_NO_VISUAL_INFERENCE` 文本；没有视觉推理、实际服务认证或模型工具调用。已通过协议传输不能替代真实模型验收。

## 仍缺证据

- 有凭据的真实视觉服务理解/输出、长任务 Steer/暂停/Stop、只读模型审查、双目录模型写入与并行审批。
- 真实认证插件、连接及授权 RATS 服务；托管 Git 远端凭据。
- Windows 原生中文候选窗与组合输入后 Enter；复杂终端 TUI。
- OS 通知点击回跳和关闭系统通知场景。此前实际最小化后台通知 `shown` 的结果保留在 [通知证据](../.runtime/implementation-20260930/notification-runtime-evidence.json)。

## 保留与提交范围

提交只纳入 S01–S21 相关内核、桌面代码、测试和产品/验收文档。原有无关 `ReverieCli-py/tests/test_rats_engine_task_e2e.py` 和 `result_images/` 不纳入；临时验证数据与 release 产物不纳入。每次打包前备份原 `.reverie`，结束后恢复；原 54 个文件哈希全部一致，无关 RATS e2e 文件与基线一致。提交前核对基线、范围及 `git diff --cached --check`；没有 commit hooks/自动推送的成功假设。见 [保留与包哈希证据](../.runtime/implementation-20260930/deep-preservation-evidence.json)。
