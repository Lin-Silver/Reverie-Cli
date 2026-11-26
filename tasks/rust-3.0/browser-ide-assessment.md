# 浏览器与 IDE 接入评估

核实日期：2026-11-23。状态：只读评估与设计建议，浏览器宿主和完整 IDE 扩展宿主均未在本轮实现。

本地依据为 HEAD 881e3f14a1e4b79bc405cab7daa26fd32059aea0 及当时的工作树。并行集成仍会改变工作树；本文件的静态观察不能替代最终候选的运行证据。本评估不改变 Rust 3.0 的完整功能范围、四个内置市场、两个保留分支或发布策略。

## 1. 建议与收益判断

建议优先完成既有工作台、Rust Context Engine、可选 LSP 与 MCP/Skills 的共同链路，并采用现有 Electron 的 Chromium 提供桌面侧边浏览器。浏览器可以直接补足“观察网页—操作—回读结果”的产品链路，Rust 继续负责权限、任务归属、取消和记录。

按维护者“自行评估收益，提升不大则不要”的授权，本轮不引入完整 VS Code 扩展宿主。它能提供成熟的编辑、调试、测试及第三方扩展能力，但需要兼容 VS Code API、贡献点、激活事件、文档模型、扩展进程和界面生命周期。现有 AI 任务更直接需要语言诊断、符号/定义、工具、Skills 和浏览器回读；完整宿主的额外收益尚不足以证明能抵消新增进程、体积和持续维护成本。这是基于当前源码及接口的工程判断，没有将其写成已测出的效率提升。

Open VSX 可作为手动添加的候选来源评估。它不自动成为第五个内置市场，也不表示 Reverie 已具备通用 VSIX 运行能力。已有四个内置来源的迁移继续执行。

| 路线 | 主要收益 | 新增工作与限制 | 建议 |
|---|---|---|---|
| 既有工作台＋Rust Context Engine | 复用文件树、编辑、差异审查、证据检索和任务流程 | 仍需把当前库及界面连成已验证产品链路 | 作为 3.0 的基础路线 |
| 可选 LSP＋MCP/Skills | 语言服务、外部工具和工作流按需提供，无需完整编辑器宿主 | 需要服务器依赖、权限、版本与退出管理；协议兼容不能代替真实服务验证 | 优先整合已有能力 |
| 按需加载 Monaco 编辑视图 | 可补充编辑器功能和语言服务显示 | 要桥接文档版本、保存、诊断与取消；不能直接运行 VS Code 扩展 | 作为独立界面优化候选，未选定依赖 |
| Open VSX 包级适配 | 可发现语言服务或其他许可适用的组件 | 必须逐包核实入口、依赖、许可及能力；不能机械改名后运行全部 VSIX | 先评估明确组件，不承诺通用兼容 |
| 完整 Code-OSS/IDE 扩展宿主 | 更完整的 VS Code 扩展、调试、测试和编辑生态 | 增加 API、进程、界面与维护范围；市场接入另有许可边界 | 暂不建议整套接入 |
| Void 完整移植 | 可参考 AI 编辑与流式差异交互 | 已归档；主要是 TypeScript/VS Code 分支，许可分层，不能代替 Rust 内核 | 只参考必要设计或经审查的具体文件 |

这里的成本和收益均为技术推断。没有新增内存、安装体积、启动或用户效率的实测数字。复用 Electron 的 Chromium 可避免为桌面再打包另一套浏览器引擎，但页面、标签和宿主进程仍有资源成本。

## 2. 已验证的本地状态

| 项目 | 当前证据 | 证据边界 |
|---|---|---|
| Electron | [package.json](../../ReverieCli-ui/package.json) 声明 41.2.1；本地 node_modules/electron/package.json 也为 41.2.1 | 未运行浏览器宿主，未核实最终发行包内 Chromium 的实际版本 |
| 主窗口隔离 | [main.ts](../../ReverieCli-ui/electron/main.ts) 设置 contextIsolation=true、nodeIntegration=false、sandbox=true；HTTP(S) 新窗口和主窗口外部导航交给系统浏览器 | 这些设置保护既有主窗口，不证明新增浏览器标签已受同样管理 |
| 文件与工作台 | [FileBrowser.tsx](../../ReverieCli-ui/src/FileBrowser.tsx) 有文件浏览、草稿和 textarea 编辑；[Workbench.tsx](../../ReverieCli-ui/src/Workbench.tsx) 有 Git/差异审查 | 未发现 Monaco 或通用 VS Code extension host |
| Rust Context Engine | [core/src/lib.rs](../../ReverieCli-rs/crates/core/src/lib.rs) 共享 Rust ContextEngine；[host/catalog.rs](../../ReverieCli-rs/crates/core/src/host/catalog.rs) 暴露有内容身份和片段上限的检索工具 | 本轮是源码观察，不重用其他版本的测试作为当前证明 |
| 可选 LSP 库 | [lsp.rs](../../ReverieCli-rs/crates/core/src/lsp.rs) 与 [runtime.rs](../../ReverieCli-rs/crates/core/src/lsp/runtime.rs) 有项目绑定及只读查询；目录中的库正在统一集成 | 当前工具说明仍标 LSP 迁移中；不能称完整 GUI/TUI 产品链路已验收 |
| 浏览器执行器 | 本次检索未找到现成 WebContentsView、BrowserView 或 CDP debugger 浏览器适配器 | 未找到不等于对所有隐藏或外部依赖作绝对不存在断言；最小缺证是实际入口与运行结果 |
| RIU/MCP Apps | 现有独立视图宿主及交互代码存在 | 受隔离交互视图与通用浏览器的来源、导航和权限不同，不能直接当作完整浏览器 |

## 3. 官方来源、技术栈与许可

### VS Code 与 Visual Studio Marketplace

微软的 [Extension Host 文档][vscode-host] 区分本地/远程 Node.js 宿主与浏览器 WebWorker 宿主，分别使用 main/browser 入口；[扩展清单][vscode-manifest] 还包含 engines.vscode、contributes、activationEvents、extensionKind 和扩展依赖。这说明安装 VSIX、运行 LSP 与兼容整个 VS Code 扩展 API 是不同层级。

微软 [FAQ][vscode-faq] 明确：Visual Studio Marketplace 仅供 Visual Studio 产品家族使用，包含 Code-OSS 分支在内的其他产品不获准接入。其 [2025 年 9 月版 ToU][vscode-terms] 第 2 节 b 项也限制 Marketplace Offerings 在所列产品家族之外安装、导入或使用。

因此，公开可访问的 gallery URL 不能作为 Reverie 获准接入的依据。不能借用 Void 的 gallery 配置、伪装产品身份或绕过该限制。独立取得的源码、发行包和其他市场分别按其来源及许可核实；不能只看到某仓库开源便推断该 Marketplace 包可用。

### Open VSX

官方项目已从 eclipse/openvsx 移到 [eclipse-openvsx/openvsx][openvsx-repo]。本轮核实提交为 5e055e1410e5f438e892e87e8da38ceaf3c19c9c，[服务端项目许可证][openvsx-license] 为 EPL-2.0。

官方 [Registry API 文档入口][openvsx-api] 指向公开 Swagger 文档，并将未公开在该文档中的 user/admin API 视为内部接口。候选适配器应采用公开 API，不能依赖内部登录或管理接口。

[官方 FAQ][openvsx-faq] 要求扩展声明许可，但不要求所有扩展开源，也明确发行许可可以不同于源码许可。[网站条款源文件][openvsx-terms-source] 的第三方内容条款要求使用者遵守具体内容的许可；平台提供内容不会额外授予其知识产权许可。该源文件固定在 edee1bad4d8628e5e57455bc56721bd3220b11d9，文件 blob 为 2819fea14adf3eb6bbfc8297cd4377df24a4ebf6。

所以，Registry 的 EPL-2.0 不覆盖其中全部扩展。复制 Registry 源码、使用服务 API、安装扩展和再分发扩展要分别审查；本轮没有复制它的代码或下载安装测试包。官网 terms-of-use 页的直接抓取未得到正文，已核对官方仓库对应源文件；正式接入前仍须确认线上条款与该文件一致。

### Monaco

本轮核实 [Monaco README][monaco-readme] 与 [MIT LICENSE][monaco-license]，固定提交 a310cd1f26fa78568172faa19d252c0c11b90256。README 对“已写好的 VS Code 扩展能否直接在浏览器 Monaco 中运行”回答 No，并区分独立语言服务接入。

Monaco 是候选编辑库，不是通用 VS Code extension host。若后续选用，需要保留 MIT 版权与许可声明，并单独验证编辑、保存、语言服务、CJK/输入法与界面资源成本。本轮未安装或集成 Monaco。

### Void

官方 [README][void-readme] 已声明 deprecated、停止接受贡献，并明确 Void 是 VS Code fork；GitHub 仓库元数据为 archived=true。本轮固定来源为 b3166e7ef2aefbdfeb139445fdf248a561b85d4d。

官方语言统计中 TypeScript 为 69,634,891 字节，Rust 为 500,641 字节，TypeScript 约占总量 95.22%。[package.json][void-package] 与 [代码指南][void-guide] 展示 Node/Gulp、Electron、React 和 VS Code Workbench 扩展流程。存在少量 Rust 文件不能把整个 Void 称为 Rust 项目。语言统计是仓库字节分布，不能直接推算运行内存或包体积。

[LICENSE.txt][void-license] 为 Apache-2.0；[LICENSE-VS-Code.txt][void-vscode-license] 明确原 VS Code 部分为 MIT，Void 新增和修改为 Apache-2.0。package/product 中仍有 MIT 字段，不能覆盖实际许可证分层。[product.json][void-product] 配置了 Microsoft gallery URL，但配置本身不证明获准访问或使用。

参考流式差异、上下文呈现和 Provider 管理时，记录设计来源。复制具体文件时，核对该文件来源、版权、适用许可、修改标识及对应第三方声明；品牌、图标和素材另查许可。本轮只读取 [ThirdPartyNotices.txt][void-notices] 开头，没有完成全部依赖与素材许可审查。

### Electron 与 Chromium

已按本项目版本读取 Electron v41.2.1 的 [WebContentsView][electron-view]、[Debugger][electron-debugger]、[Session][electron-session]、[安全指南][electron-security]、[Chrome Extension Support][electron-extensions] 与 [LICENSE][electron-license]。

Electron 自身采用 MIT；当前安装目录还包含 LICENSES.chromium.html。发行包必须保留实际版本的 Chromium 和第三方许可材料，不能用 Electron 的 MIT 声明替代整个二进制的许可集合。

官方文档支持由主进程管理 WebContentsView，并通过 debugger 使用 CDP。它也明确只兼容部分 Chrome Extensions API，任意 Chrome 商店扩展兼容不是 Electron 的目标；只支持加载未打包扩展等限制也存在。因此，“Chrome in Reverie”应理解为 Chromium 内置浏览器设计，不能宣称具备完整 Chrome、商店扩展、账号同步或其他未验证能力。

## 4. 侧边浏览器的最小设计契约

以下均为待实施设计，不是当前可调用 API。优先在既有 BrowserWindow 中增加受管 WebContentsView，避免为了嵌入浏览器重建整个桌面框架。可信桌面界面提交请求，Rust 权限链决定执行范围，Electron 主进程的受限适配器控制网页；远端页面没有应用 preload、核心 IPC 或凭据接口。

| 能力 | 最小契约 |
|---|---|
| 能力与宿主状态 | 明确宿主是否存在、实际版本、支持的动作与会话；缺宿主返回具体状态 |
| 列出、打开与切换标签 | 绑定项目、任务、会话、profile、tab 和导航修订；桌面侧边可见，可由用户直接操作 |
| 观察 | 返回 URL、标题、可见元素或受限页面内容、frame/元素身份、内容修订及截图坐标元数据；页面内容按外部数据处理 |
| 点击、输入、滚动与按键 | 用已观察到的目标与修订执行有限动作；旧目标、跨标签和变化后的截图必须重新观察 |
| 前进、后退、刷新与导航 | 跟踪重定向、弹窗和新标签的归属；处理允许的协议与目标，不把网页提议当作用户授权 |
| 下载与上传 | 进入既有文件/工具权限链，绑定目标路径、实际文件、下载状态和取消；不将网页路径直接交给宿主执行 |
| 关闭、崩溃与取消 | 释放 debugger、WebContents、监听器及任务引用；区分未执行、已执行和交付不确定，后者不自动重放 |

CDP 是受信任适配器的实现手段，模型只获得有限浏览器能力。不能直接暴露任意 debugger.sendCommand、任意页面脚本或应用主窗口控制。DevTools 打开可能导致 debugger detach，必须把断连作为生命周期事件处理。

会话应使用明确的 Session partition，避开应用默认会话与 Connector 凭据存储。浏览器网页登录、扩展安装信任和 MCP OAuth 授权分别记录；网页登录不能自动授予 Connector 权限，网页也不能访问系统 vault。临时与持久 profile 的默认策略尚未决定，不能自行选择或承诺与外部 Chrome 登录态共享。

截图需保留视口、捕获区域、裁剪、返回尺寸、缩放和导航修订，区分 CSS/DIP、物理像素与返回图像坐标。实际 100%、125%、150%、200% 单屏 DPI 验证仍属于 Rust 候选验收，模拟坐标计算不代替实际命中。

WebContentsView 不能只从界面移除。Electron 的 [BaseWindow 生命周期说明][electron-window] 明确要求关闭其 WebContents，否则可能泄漏资源；在现有 BrowserWindow 集成中也应明确每个受管标签的释放归属并验证退出。

独立终端没有 Electron 进程时，还需要交付按需启动的浏览器宿主。可选 Electron 浏览器组件是候选方式，可复用桌面渲染能力而不让 Rust 内核/终端强制依赖 GUI；组件打包、启动、退出与四平台支持尚待确认。capability=false 只能描述当前缺失，不能代替原有终端浏览器功能的迁移。

## 5. 需要明确的实施决策

1. 完整通用 IDE/VSIX 宿主本轮不引入；依维护者授权由实施者评估后选择既有 AI 工作台、可选语言服务和浏览器路线。
2. 浏览器默认使用临时 profile，还是允许用户选择的持久 profile；共享登录态的范围需明确。
3. 独立 CLI 的浏览器宿主是否采用按需安装的 Electron 组件；明确组件缺失时的安装与启动流程。
4. Monaco 是否需要进入本轮界面优化，还是先保留现有编辑器并补足语言服务显示。
5. Open VSX 是否作为手动来源进入后续适配，及首批具体允许的扩展/语言服务包；四个内置市场保持既有决策。

以上只影响新增接入的实现方式。本轮 Rust 核心、模式、现有扩展与 GUI 集成可以继续，不等待这些候选路线的完整实测。

## 6. 未实现或未验证清单

1. 桌面侧边浏览器的 Host、协议、Electron 适配器和 GUI/TUI 操作链路尚未实现及运行验证。
2. 实际网页打开、导航、元素观察、点击、输入、滚动、弹窗与结果回读尚未验证。
3. 四档真实单屏 DPI、裁剪/缩小截图坐标、窗口移动及旧截图失效尚未用该浏览器实现验证。
4. 临时/持久 profile、真实网页登录、会话隔离、退出和删除数据策略尚未确定及验证。
5. 浏览器请求通过当前 StrictIds 与 HardDenialPolicy::Block 权限策略的完整链路尚未验证。
6. 网页越权 IPC、危险导航、跨任务目标、过期句柄和凭据隔离尚未验证。
7. CDP 被 DevTools 分离、页面崩溃、Stop、宿主退出、重启及不确定操作不重放尚未验证。
8. 下载/上传的真实路径权限、覆盖保护、取消及失败清理尚未验证。
9. 独立 CLI 无桌面进程时的可选浏览器宿主打包、启动、连接和退出尚未交付。
10. Windows x64、Linux x64、macOS arm64/x64 的浏览器实包与原生运行尚未验证。
11. 浏览器或 Monaco 接入后的空闲内存、安装体积、冷启动及多标签资源成本尚未测量。
12. Open VSX 公开 API 的实际检索、下载、离线包、修订与完整性校验尚未完成；线上条款与已核实源文件的一致性仍需确认。
13. 具体 VSIX 包的许可、入口、平台、依赖、权限和已支持组件映射尚未核实，通用 VS Code 扩展兼容未实现。
14. Void 或其他参考实现的实际复用文件、完整第三方许可与素材清单尚未冻结，不能宣称完整移植已获许可。
15. 调试或测试协议对 Reverie 的实际效率收益尚未测量，完整 IDE 宿主的收益结论仍为建议。

[vscode-host]: https://code.visualstudio.com/api/advanced-topics/extension-host
[vscode-manifest]: https://code.visualstudio.com/api/references/extension-manifest
[vscode-faq]: https://code.visualstudio.com/docs/supporting/faq#extensions
[vscode-terms]: https://cdn.vsassets.io/v/M264_20251020.18/_content/Microsoft-Visual-Studio-Marketplace-Terms-of-Use.pdf
[openvsx-repo]: https://github.com/eclipse-openvsx/openvsx/tree/5e055e1410e5f438e892e87e8da38ceaf3c19c9c
[openvsx-license]: https://github.com/eclipse-openvsx/openvsx/blob/5e055e1410e5f438e892e87e8da38ceaf3c19c9c/LICENSE
[openvsx-api]: https://github.com/eclipse-openvsx/openvsx/wiki/Registry-API
[openvsx-faq]: https://www.eclipse.org/legal/open-vsx-registry-faq/
[openvsx-terms-source]: https://github.com/EclipseFdn/open-vsx.org/blob/edee1bad4d8628e5e57455bc56721bd3220b11d9/website/static/documents/terms-of-use.md
[monaco-readme]: https://github.com/microsoft/monaco-editor/blob/a310cd1f26fa78568172faa19d252c0c11b90256/README.md
[monaco-license]: https://github.com/microsoft/monaco-editor/blob/a310cd1f26fa78568172faa19d252c0c11b90256/LICENSE.txt
[void-readme]: https://github.com/voideditor/void/blob/b3166e7ef2aefbdfeb139445fdf248a561b85d4d/README.md
[void-package]: https://github.com/voideditor/void/blob/b3166e7ef2aefbdfeb139445fdf248a561b85d4d/package.json
[void-guide]: https://github.com/voideditor/void/blob/b3166e7ef2aefbdfeb139445fdf248a561b85d4d/VOID_CODEBASE_GUIDE.md
[void-license]: https://github.com/voideditor/void/blob/b3166e7ef2aefbdfeb139445fdf248a561b85d4d/LICENSE.txt
[void-vscode-license]: https://github.com/voideditor/void/blob/b3166e7ef2aefbdfeb139445fdf248a561b85d4d/LICENSE-VS-Code.txt
[void-product]: https://github.com/voideditor/void/blob/b3166e7ef2aefbdfeb139445fdf248a561b85d4d/product.json
[void-notices]: https://github.com/voideditor/void/blob/b3166e7ef2aefbdfeb139445fdf248a561b85d4d/ThirdPartyNotices.txt
[electron-view]: https://github.com/electron/electron/blob/v41.2.1/docs/api/web-contents-view.md
[electron-debugger]: https://github.com/electron/electron/blob/v41.2.1/docs/api/debugger.md
[electron-session]: https://github.com/electron/electron/blob/v41.2.1/docs/api/session.md
[electron-security]: https://github.com/electron/electron/blob/v41.2.1/docs/tutorial/security.md
[electron-extensions]: https://github.com/electron/electron/blob/v41.2.1/docs/api/extensions.md
[electron-license]: https://github.com/electron/electron/blob/v41.2.1/LICENSE
[electron-window]: https://github.com/electron/electron/blob/v41.2.1/docs/api/base-window.md
