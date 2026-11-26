# Rust 3.0 插件管理 GUI/TUI 接入增量

本记录对应 `market_ui` 子任务，日期为 2026-11-23（报告使用 UTC，日期为 2026-11-24）。插件管理源码已接入，修复后的统一程序通过生产 Electron 与 ConPTY 各六组本地流程。提交、推送及主任务文档由主代理统一处理。本记录不代表完整扩展生态或 Reverie CLI 3.0.0 产品已完成。

## 实现范围

1. GUI 提供从本地目录、归档文件/URL、Git 或市场条目准备候选，按具体候选审核并激活，分别管理信任、当前项目启用、Hooks、自动更新、更新候选、回退和移除。
2. 候选与当前版本详情显示来源身份、内容 SHA-256、固定内容/发布摘要依据、签名密钥、许可、组件、执行范围摘要及公开的权限、依赖、条款。缺少完整性依据的内容单独批准候选 SHA；已信任的执行范围变化单独批准新 profile。
3. 审核面板默认全部未确认；提交绑定具体候选、执行范围及 inspection revision。信任不隐式启用项目，Hooks 首次启用必须确认事件、入口及权限。
4. App 层 controller 保留安装草稿、候选选择、审核状态及后台请求；切换页面后继续。后台操作使用明确 operation ID 取消，管理流程不执行业务 Hooks、插件命令或 MCP 工具。
5. 市场条目追加“准备安装”入口；Registry 条目有多个远端时必须明确选择 URL，保留选择草稿，只准备该端点的未激活配置。
6. 滚动终端接入 `/plugins` 和 `/plugin`，提供准备、查看、审核、激活、信任、项目启用、Hooks、更新、回退、移除及停止；审核面板默认选择 Cancel，后台注册完成后才 spawn，Ctrl+C 与停止命令按 operation ID 取消。
7. 从 App 提取既有 `useDialogFocus`，插件审核与原有对话框共用焦点恢复、Tab 边界和 Escape 处理。Electron action 与后台超时接入同一 Rust 协议，生成类型仍由 Rust 程序产生。

## 涉及文件

- 插件界面：`ReverieCli-ui/src/PluginsView.tsx`、`plugin-state.ts`、`plugins.css`、`PluginsView.test.tsx`、`dialog-focus.ts`。
- 界面路由与协议：`ReverieCli-ui/src/App.tsx`、`types.ts`、`core-protocol.ts`、`i18n.tsx`。
- Electron actions 与超时：`ReverieCli-ui/electron/core-actions.ts`、`core-actions.test.ts`、`core-timeouts.ts`、`core-timeouts.test.ts`。
- 市场安装入口：`ReverieCli-ui/src/MarketsView.tsx`、`MarketsView.test.tsx`、`market-state.ts`、`markets.css`。
- 终端：`ReverieCli-rs/crates/cli/src/terminal/plugins.rs`、`mod.rs`、`context.rs`。
- 真实验证：`scripts/verification/rust-plugin-fixture.mjs`、`rust-plugins-tui-smoke.mjs`、`rust-plugins-electron-smoke.mjs`、`rust-plugins-electron-probe.cjs`。

共享文件包含其他实施子任务的工作。本子任务未创建分支/worktree，未提交或推送，未修改 Python、版本、CI、发布流程或清理缓存。只格式化自身改动的终端文件，Rust 编译与桌面内核暂存由主代理统一执行。

## 已取得的验证

| 命令 | 结果与范围 |
|---|---|
| `npm test -- src/PluginsView.test.tsx src/MarketsView.test.tsx electron/core-actions.test.ts electron/core-timeouts.test.ts` | 此前在同一增量执行，4 个文件、18 项通过；分别为 5、4、5、4 项。保留原市场的所有断言；未更改的市场/actions/超时 13 项未重复运行。 |
| `npm test -- src/PluginsView.test.tsx` | 当前版本详情回归用例先失败；修复后本文件 6 项通过，包含原有全部审批/草稿断言及新增的无候选当前版本展示。 |
| `npm run typecheck` | 当前版本详情修复后通过；1285 条翻译、82 个模板。 |
| `npm run build` | 最终生产 renderer/Electron 构建通过，2097 modules；build ID 为 `eb887a23802faa2c`。仅有现有大于 500 kB chunk 的 Vite 提示。 |
| 四份新增验证脚本的 `node --check` | 四份脚本通过语法检查；修改等待条件和截图位置后，两份受影响脚本再通过。 |
| `node scripts/verification/rust-plugins-electron-smoke.mjs ReverieCli-rs/target/release/reverie.exe` | 最终生产界面六组通过，包含实际激活后的当前版本详情断言；报告 `.runtime/rust-3.0/plugins-electron-smoke/case-HYoJBY/report.json`。 |
| `node scripts/verification/rust-plugins-tui-smoke.mjs ReverieCli-rs/target/release/reverie.exe` | 修复后的统一程序及真实 Windows ConPTY 六组通过，报告 `.runtime/rust-3.0/plugins-tui-smoke/case-wPVMVQ/report.json`。 |
| 本子任务文件的 `git diff --check` | 通过；只有既有 LF/CRLF 转换提示。 |

最终实际程序为 `ReverieCli-rs/target/release/reverie.exe`，`3.0.0-dev`、Windows x64、`sdk-bridge.v1`，大小 46,531,072 字节，SHA-256 为 `3c65127d354a6b0d5c02f3c96108974b96b41c3f3bbb57e14beda9020b74a7eb`。Electron 报告同时核对了 `window.reverie.paths()` 的实际内核路径及摘要，ConPTY 脚本复核程序在整个运行期间未被替换。两份最终报告使用同一 Rust 程序；最终桌面 build ID 为 `eb887a23802faa2c`。最后的 GUI 修复没有改变 Rust 程序，不重复已经通过的 ConPTY。该身份属于未提交工作区构建，不能作为正式发行包证据。

首轮生产 Electron 报告 `.runtime/rust-3.0/plugins-electron-smoke/case-RCTiJ5/report.json` 与 ConPTY 失败 `.runtime/rust-3.0/plugins-tui-smoke/case-JgBe8i/failure.json` 保留，其程序为 46,530,048 字节、SHA-256 `b7d8d9af7e66092d7094ef6862300fd0cc4b42fd75053d64a0070c21d3b13f44`，不计作修复后的通过证据。

`case-NFOLKS` 的生产 Electron 报告使用修复后 Rust 程序及旧界面 build `92e4575c801d5b6f`，保留其历史通过范围。新增的当前版本详情断言在 `.runtime/rust-3.0/plugins-electron-smoke/case-z9KP6t` 实际失败；最终界面修复后使用 `case-HYoJBY` 通过，不将旧报告当作新界面的证据。

Electron 使用生产 renderer、preload、主进程及 Rust 程序，采用独立应用配置、Git 项目、本地 MIT 插件和回环 HTTP 目录。覆盖候选默认不激活/不信任、激活后仍可查看当前版本身份与组件、独立信任、Hooks 明确确认、项目启用、自动更新退出、准备更新、内容/profile 审批、回退、切页保留草稿/后台下载与取消、Registry 多端点选择、移除及正常退出。HTTP 请求只有 `/version`、`/hold.zip`、`/registry`，没有 `/mcp-one` 或 `/mcp-two`；管理没有产生业务 Hook 标记，公开 metadata 和界面没有测试凭据值。Renderer 错误列表为空；日志中的 `Extension download cancelled.` 是主动取消负例。

ConPTY 覆盖候选默认不激活、不信任，Enter 选择默认 Cancel 保持不激活，明确激活后按同一 SHA 信任，项目启用、Hooks 明确确认及关闭、自动更新退出、准备更新、改变 profile 后审核激活、回退、下载期间继续列插件、停止命令和 Ctrl+C 分别关闭真实 HTTP 请求、移除以及 CLI/bridge 正常退出。检查了公开输出没有测试凭据值，管理未产生业务 Hook 标记。

已读取最终 `case-HYoJBY` 的 `plugin-current-version.png`、`plugin-hooks-review.png`、`plugin-confirmations.png`、`plugin-remaining-candidate.png`，检查了当前版本身份与组件、Hook 事件/入口/权限、默认未勾选确认项、禁用的提交按钮、剩余未激活 Registry 配置及滚动区域。实际详情消失的失败截图与修复后的当前版本截图均已检查；此前候选和 profile 截图保持历史归属。本轮未改变 Windows 缩放。

## 实际发现与修复

1. ConPTY 首轮证明激活后的 `/plugins trust` 返回 `The requested version is not an inspected candidate.`。`PluginStore` 从 `record.candidates` 排除当前版本，将其置于 `inspection.active`；TUI 只查候选列表。已补齐按同一 SHA-256 查找 `inspection.active`，保留具体版本、profile 和 revision 审批；重新构建后的实际 ConPTY 通过激活后信任和启用 Hooks，生产 Electron 同时复验通过。
2. 验证脚本原先仅凭停止按钮消失或输入提示存在来判断操作结束，可能提前发送下一条命令。Electron 改为等待 pending status 消失；ConPTY 等待本次完整的 `Plugin state updated:` 或下载取消回执，再确认正常 viewport。该修改只影响探针，不减少原有产品断言。
3. 激活且没有其他候选时，GUI 原先只显示安装目录，已取得的 `inspection.active` 未展示。实际 Electron 和新增定向用例均证明当前版本 SHA、许可和组件消失；无候选分支改为复用已有当前版本详情组件。修复后定向 6 项、类型/生产构建及含新增断言的实际 Electron 六组通过。

## 尚未验证或不在本增量中

1. 四个公开市场的完整实际安装、固定 Git、离线归档、可信发布摘要和发布者数字签名更新未由本 GUI/TUI 增量验收。
2. Connector 的真实 OAuth、刷新、恢复、撤销和真实 MCP 服务调用未由本增量验收。
3. 插件命令、Skills、子代理、Hooks、LSP 和配置的完整业务执行及自动更新调度未由管理界面探针验收。
4. 更新篡改、危险路径、并发、进程中断、重启恢复、Windows 文件占用及业务数据回退未由本界面探针验收。
5. 真实键盘/输入法、屏幕阅读器、系统缩放 DPI 和物理多屏尚未验证。
6. Linux/macOS、正式安装包/便携包及签名未由本增量验收。
7. 空闲内存、安装体积、冷启动、长期稳定性及整个 Reverie CLI 3.0.0 产品尚未由本增量验收。
