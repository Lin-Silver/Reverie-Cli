# Rust Context 使用量、压缩与恢复的 GUI/TUI 接入

记录日期：2026-11-23。本记录针对共享工作树中的增量接入；不代表整个 3.0.0 已验收。源码和统一构建由主代理管理，本子代理没有运行 Cargo、生产打包、提交或推送。

GUI 复用 Inspector 的压缩按钮、`/compact [focus]` 与 TaskBar 的继续任务按钮。压缩登记项目、会话与运行 ID，可通过现有停止按钮取消；保留未发送草稿、切换后的会话和已加载的历史页。无变更回执用普通信息呈现。正在压缩时发送会提示等待，并保留输入。

`saved_native_context_estimate` 与 `native_next_request_estimate` 均明确标为本地估算，后者显示下一次请求的估算范围；本地分词精确不等于 Provider 的完整请求计量。空闲时读取保存上下文，活动运行使用有归属的 `context.usage` 事件，不把草稿或流式片段伪称为已保存输入。

Electron 的手动压缩使用独立操作登记，复用实际 Rust bridge，不写普通运行日志或新增用户消息。停止严格匹配项目、会话、助手命名空间与运行 ID；失效压缩不能取消随后启动的 prompt。压缩事件保留原生身份并补充 AiO 命名空间。压缩采用现有无传输期限、可显式取消的请求约定。

TUI 增加 `/compact [focus]`、`/resume`、`/context usage` 和对应帮助。恢复调用 `begin_resume`/`complete_prompt`，不重新保存用户文本；压缩调用独立异步入口。运行期间可编辑草稿，明确提交的后续请求排队，停止遵循既有清空队列语义。上下文事件和回执检查项目、会话与运行归属，取消与退出沿用内核控制和任务等待。

本轮主要挂载点为 `ReverieCli-ui/src/App.tsx`、`src/core-protocol.ts`、`electron/main.ts` 和 `ReverieCli-rs/crates/cli/src/terminal/{mod,context}.rs`；原 Connector、Markets、Plugins 接入保留。Rust 协议与 generated 类型未由本子代理修改；`CoreContextUsage` 及压缩回执字段在前端契约中兼容扩展。

基础验证：

- `npm test -- src/App.interaction.test.tsx -t 'context|compact|resum|stopp'`：18 passed，110 skipped；没有运行整个 App 测试集。
- `npm test -- electron/main-compaction-controls.test.ts electron/core-timeouts.test.ts`：12 passed。
- renderer 与 Electron 的 `tsc --noEmit`：均通过。
- `npm run check:i18n`：通过，1291 translations / 85 templates。
- 两终端文件 `rustfmt --edition 2024 --emit stdout`：只读解析通过，没有整体重排终端源码。
- 本轮相关路径 `git diff --check`：通过。
- 删除失效压缩的运行 ID 守卫后，针对误取消后续 prompt 的测试按预期失败；守卫已恢复，并重新通过宿主测试。

终端运行身份已补充 UNIX 时间纳秒，格式为 `terminal-{kind}-{PID}-{nanos}-{seq}`，避免持久 `task_runs.id` 遇到 PID 重用时只依赖进程内序号。实际方法的两项独立定向断言已通过；统一 Cargo 和真实终端运行结果由主代理另行记录。

未验证事项：

1. 本轮 TUI 新代码的统一 Cargo 编译、Clippy 与新增归属单元测试尚未由本子代理执行。
2. 新编译程序在真实 ConPTY 中的压缩、恢复、取消、CJK focus、草稿与退出行为尚未实测。
3. 真实 Electron 窗口与 Rust 程序之间的压缩进度、停止、跨会话回执和恢复按钮链路尚未实测。
4. 真实模型的摘要质量、长上下文保真、超限恢复与 Provider 计量差异尚未在该 GUI/TUI 增量中验收。
5. 压缩期间宿主崩溃、强制终止、重启恢复、多个窗口并发和持久运行身份的跨重启行为尚未实测。
6. Windows、Linux、macOS arm64/x64 的发行程序及桌面实包尚未针对该增量重新验收。
7. 100%、125%、150%、200% 的真实 DPI 与浏览器交互未在本轮接入中验证。
8. 性能、内存、长时间稳定性与正式 Recall/nDCG 基准没有由上述定向交互测试替代。
9. Chrome in Reverie 侧边浏览器没有在本轮实现；profile、独立 CLI 宿主及相关路线仍见 `browser-ide-assessment.md` 的待明确事项。
