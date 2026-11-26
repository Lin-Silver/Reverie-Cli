# Rust 3.0 市场 GUI/TUI 接入增量

本记录对应 `market_ui` 子任务，验证日期为 2026-11-23（报告使用 UTC，日期为 2026-11-24）。提交、推送和主任务文档由主代理统一处理。本增量完成市场来源和目录管理、页面导航及终端命令接入，不代表完整扩展生态或 Reverie CLI 3.0.0 已完成。

后续插件安装入口、Registry 多端点选择和完整插件管理增量见 [plugin-ui-notes.md](plugin-ui-notes.md)，使用另行核对的程序身份及实际运行证据；本记录的旧程序和验收范围保持历史归属。

## 实现范围

1. Electron/renderer 共用页面顺序与固定列表的归一化，过滤未知页面、去重，允许解除全部固定项，并通过现有桌面偏好接口持久化。
2. 更多页面菜单支持鼠标悬停、明确点击和键盘展开；悬停保留输入焦点，明确展开后建立菜单焦点；页面支持固定、解除固定和箭头排序。
3. 固定页面改变导航按钮的位置时，已打开的菜单重新计算锚点位置，不重建菜单或重置操作焦点；定向测试和实际 Electron 检查覆盖该修复。
4. 四个内置来源按需读取；手动来源支持 Git、本地目录、清单 URL 和 MCP Registry，接入现有 Rust 市场接口。
5. GUI 展示来源身份、SHA-256/提交、缓存、错误、分页及搜索，支持添加、刷新、停止、启用、禁用和移除；草稿、搜索、目录状态和进行中的刷新保存在 App 层，切换页面后接续。
6. 原生滚动终端接入 `/markets` 与 `/market`，支持来源列表、添加、目录/搜索、缓存分页、远端下一页、刷新、停止及启用/禁用/移除；下载在后台执行，Ctrl+C 和停止命令按市场 ID 取消。
7. `refreshMarket` 使用可取消后台超时策略，避免普通 IPC 的 60 秒超时阻断合法目录下载。

市场目录读取不执行插件安装入口，不授予插件信任，也不模拟 Connector/OAuth 成功。插件安装、注册和授权由其他实施子任务接入。

## 涉及文件

- 页面导航：`ReverieCli-ui/src/PageNavigation.tsx`、`page-navigation.css`、`PageNavigation.test.tsx`、`FloatingMenu.tsx`。
- 市场页面：`ReverieCli-ui/src/MarketsView.tsx`、`market-state.ts`、`markets.css`、`MarketsView.test.tsx`。
- 偏好与路由：`ReverieCli-ui/electron/navigation-preferences.ts`、两侧 `preferences.ts`、`src/preferences.test.ts`、`src/App.tsx`、`src/types.ts`、`src/desktop-commands.ts`、`src/i18n.tsx`。
- 后台超时：`ReverieCli-ui/electron/core-timeouts.ts`、`core-timeouts.test.ts`。
- 终端：`ReverieCli-rs/crates/cli/src/terminal/markets.rs`、`context.rs`、`mod.rs`。
- 真实验证：`scripts/verification/rust-markets-electron-smoke.mjs`、`rust-markets-electron-probe.cjs`、`rust-tui-smoke.mjs`。

`App.tsx` 等共享文件还包含其他实施子任务的工作。本子任务未创建分支/worktree，未提交或推送，未修改 Python、版本、CI 或发布流程，未删除缓存。

## 验证身份

- 实际 Rust 程序：`ReverieCli-rs/target/release/reverie.exe`。
- 版本/平台：`3.0.0-dev`、Windows x64、`sdk-bridge.v1`。
- 大小：36,200,448 字节。
- SHA-256：`d07759c69812eb67b3076db859dce16adb02706470538c9b1e4e8937b30f80b5`。
- 桌面暂存程序的摘要与大小一致；最终 Electron 报告另核对 `window.reverie.paths()` 返回的实际运行路径及文件摘要。
- 暂存记录标记 `source_dirty: true`，来源记录为 `881e3f14a1e4b79bc405cab7daa26fd32059aea0` 加未提交工作。该程序属于工作区构建，不属于正式发行候选。
- 本子任务未重复编译 Rust，使用主代理提供的程序。
- 最终 renderer/Electron 生产构建 ID：`44fb103c9f142e49`。实际 GUI 使用生产 renderer、preload、Electron 主进程及 Rust 程序，未重新打安装包。

## 已通过验证

| 命令 | 结果与范围 |
|---|---|
| `npm test -- src/PageNavigation.test.tsx src/MarketsView.test.tsx src/preferences.test.ts electron/core-timeouts.test.ts` | 在 `ReverieCli-ui` 执行，4 个文件、18 项通过，包含锚点位置修复、页面偏好、切页接续、缓存/搜索和后台超时。 |
| `npm run typecheck` | 通过；翻译检查为 1215 条翻译、82 个模板。 |
| `npm run build` | 生产 renderer 与 Electron 构建通过；保留现有大于 500 kB chunk 的 Vite 警告。 |
| `node scripts/verification/rust-markets-electron-smoke.mjs` | 最终 6 组实际 GUI 检查通过，报告 `.runtime/rust-3.0/markets-electron-smoke/case-HoLslz/report.json`。 |
| `node scripts/verification/rust-tui-smoke.mjs` | 原生程序与 Windows ConPTY 检查 12 项通过，报告 `.runtime/rust-3.0/tui-smoke/case-CGUXOd/report.json`。 |
| `git diff --check -- <本子任务已管理文件>` | 通过；仅有仓库既有 LF/CRLF 转换提示。 |

Electron 检查使用独立应用配置、项目和本地/回环 HTTP 市场，覆盖四个按需来源、原生 SHA-256、分页/搜索、草稿切页、损坏清单保留已有缓存、挂起下载跨切页后停止、启用/禁用/移除，以及 renderer 重载后的导航和来源恢复。报告的 renderer 错误列表为空；日志中的坏 JSON 与主动取消错误来自明确的负例。

终端检查覆盖 35 条本地目录的真实缓存与分页、`/market` 搜索别名、下载中继续列出来源、停止命令与 Ctrl+C 释放实际 HTTP 请求，以及无额外模型调用。原有 Skills、粘贴、CJK/Emoji、询问、权限、命令流、Context Engine、尺寸变化、取消、JSON 入口和正常退出断言保持并通过。

已读取最终实际截图：`case-HoLslz/page-navigation.png`、`market-catalog.png`、`market-sources.png`。检查了菜单可见状态、市场列表、搜索结果、长路径、按钮布局和滚动区域；未更改 Windows 缩放。

早期探针的分页和启用/禁用等待错误已修正；其失败目录保留。新增真实锚点位置检查在 `.runtime/rust-3.0/markets-electron-smoke/case-AdYzRg` 证明了固定页面后错位，修复后最终报告通过该检查。

## 尚未验证或不在本增量中

1. 四个公开市场的实时下载、来源变化及完整插件安装/更新/注册流程尚未作为本增量验收。
2. Connector 的真实服务 OAuth、刷新、恢复和撤销尚未作为本增量验收。
3. Hooks、LSP、子代理、插件命令及配置的完整组件管理尚未在本市场页面实现或验收。
4. MCP Registry 真实远端分页、Git 来源刷新与离线包尚未在本 GUI/PTY 探针中实际运行。
5. 物理键盘、输入法、辅助技术、四档真实 DPI 和物理多屏尚未验证。
6. Linux/macOS、正式安装/便携包、签名与完整 GUI/TUI 验收尚未验证。
7. 桌面空闲内存、安装体积、冷启动和长期稳定性门槛尚未通过本增量验证。
8. 本记录不覆盖 Reverie CLI 3.0.0 的全模式、完整本地语义推理、Gamer、Live2D 或完整产品交付。
