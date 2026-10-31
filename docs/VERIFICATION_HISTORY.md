# 验证与审查历史

2026-10-31: 2.5.3 integrates Cloud RIU and Liquid Glass, fixes light-theme opaque accessibility materials, and shows user avatars without message names. The user authorized main publication. See [2.5.3 verification](verification/2026-10-31-v2.5.3/README.md) for current checks and remaining model/platform acceptance limits.


2026-10-30：本地 Liquid Glass 与云端 dev `894fe6e` 已整合，保留经典界面和 RIU 富格式路线。Windows 联合目录包与本轮回归证据见[本地整合记录](verification/2026-10-30-desktop-integration/README.md)。此记录不关闭历史模型质量及跨平台安装验收缺口。

2026-10-28 GitHub 接续更新：用户已明确授权将本轮全部仓库改动提交到新的 `dev` 分支；本轮授权覆盖此前禁止提交/推送的限制，不含版本升级或 Release。[接续说明](CONTINUE_RIU.md)与[可克隆 goal/关键证据](verification/2026-10-28-dev-handoff/README.md)已补齐。**最新源码还包含保留 v12 之后的 Linux 安装链接启动器修复；它的回归测试已有覆盖，但包含此修复的新安装包尚未验收，优先完成此项。** 此前 v12 通过记录仅对应原包；整体 RIU 仍未完成。实际提交 SHA 与远端推送结果以交付消息及 GitHub 分支为准。

2026-10-27 最新补充：当前源码 Linux x64 v12（build `fcce0356b0365178`）通过真实 FUSE 挂载 AppImage 富格式 **86/86**、P2 **24/24**；提取程序 P3/P4/隔离 **26/31/36** 全部通过。基线 P4 注册交互 P95 **332.864ms**、1,000 行输入至两帧 P95 **51.8ms**；之后同包60次合成循环 P4 **31/31**，注册/输入 P95 为 **286.16/47ms**，最大 **360.888/62.9ms**。长时稳定性仍未验收。当前源码 Qwen3.5-4B 应用内合成冒烟准确匹配指标、表格、徽标/来源/链接卡，深浅主题和1280/460px检查通过，浏览器错误0；正式模型质量样本0。Deb 元数据/核心载荷哈希通过；Bubblewrap rootless 隔离根以 Debian 13 当前依赖清单完成 v11 安装、v12 升级、卸载，未用 `--force-depends`，宿主包库和系统路径未变化；APT 只读模拟也通过。此测试不等于宿主系统安装或桌面启动。原始 package-validation exit1 仍保留；仓库验证脚本对核验过的 v12 预打包载荷在全新目录重试 deb/AppImage 后均 exit0。Windows/macOS 实机、物理辅助技术、长时稳定性未验收；两组上限后不启动第三正式模型组。报告见[静态富格式路由与当前包追验](verification/2026-10-27-static-rich-routing/README.md)、[包重建记录](verification/2026-10-27-static-rich-routing/package-rebuilds.json)和[本地 goal](../.runtime/riu-completion-20261021/goal.json)。

2026-10-26：最终 Linux x64 桌面包 `1a5c7b1a69284aaa`（2.5.0）完成参考图优先的富格式 UI 复核。Renderer **425/1**、类型检查通过；原生 P2/P3/富格式/P4/隔离 **24/26/61/31/36** 通过，复合参考布局原生复测 **86/86**，包括合成图片解码、徽标、来源胶囊、外链和深浅主题/宽窄屏布局。deb 实际安装、同版本升级、运行和卸载 **22/22**；AppImage 使用 `APPIMAGE_EXTRACT_AND_RUN=1` 完成原生富格式 **61/61**。构建版本未升级，未发布。[完整截图与报告](verification/2026-10-26-rich-answer-ui/README.md)。这些校准的模型质量样本数为0。模型质量门仍关闭，Windows/macOS、物理设备可访问性和 FUSE 挂载启动仍缺少实测，故整体 RIU 未完成。旧 `c059be45303a7a67` 报告作为历史证据保留。

同日另有四次本地模型探索性 UI 渲染回放，以及一次实际应用内 provider 请求：Qwen3.5-2B 在关闭思考后能够被原生 UI 渲染，但输出表格内容仍错误；LFM2.5-1.2B 未生成有效富格式。真实应用请求中，模型先调用文件工具，随后调用在约29k token 的长提示词处理阶段超时；已针对静态富格式直接输出加强提示词，契约测试 **57/57** 通过，未重新打包或模型复测。均未进入正式质量组，详见[模型与渲染证据](verification/2026-10-26-local-model-ui-smoke/README.md)。

2026-10-25：已按用户参考图实现**回答 UI/UX 与格式样式**：统计卡片、状态表格、图文推荐、来源与链接，支持深浅主题、窄容器、流式输出和会话重开。[格式说明](RICH_ANSWER_UI.md)与[实际原生截图和验证](verification/2026-10-25-rich-answer-ui/README.md)已记录。当前 Linux 包 **c9df6ba5417e0851**；Desktop **407/1**、Python **2314/24**、类型检查通过，最终包原生 P2/P3/隔离 **24/26/36** 通过。真实模型回答及两张远程图片实际显示成功，完整 27 工具和采样设置保留。旧正式矩阵依最新优先级停在 15 项，不宣称完成 36 项或整体模型质量验收。

2026-10-08 整理，2026-10-09–10 补充提交前验证，2026-10-16 补充 RIU P3 互操作，2026-10-17 补充 P4 展示与交付验收。集中保留历次审查、复现、测试、构建、性能采样及明确未验证范围。各章节的结果仅对应原日期、平台和工作树，不能累计为一次全量通过。结构化原始摘要继续保留在 `docs/verification/`；`.runtime/`、截图与安装包是本地材料，不要求随 Git 克隆分发。

## 目录与迁移索引

优先查看：

| 日期 | 主题 | 证据边界 |
| --- | --- | --- |
| 2026-10-27 | [静态富格式回答路由追验](#riu-static-rich-routing-2026-10-27) | 当前源码 v12 Linux：FUSE 富格式86、P2 24、P3/P4/隔离26/31/36、Deb 依赖满足下隔离安装/升级/卸载与 Qwen 冒烟通过；Windows/macOS、物理辅助技术和正式模型质量仍开放 |
| 2026-10-26–27 | [本地小模型 UI 冒烟](verification/2026-10-26-local-model-ui-smoke/README.md) | 原始失败与后续路由修订分开；仅 v10 一次精确通过，不能推断整体模型可靠性 |
| 2026-10-21–22 | [RIU 作者契约与验证器继续实施](#riu-completion-2026-10-22) | 最新 Python 2214/24、Linux 3824bc06ee6c6e24；P4 两次超限与资源条件下的通过均保留，真实双模型矩阵待执行 |
| 2026-10-20–21 | [Cloud 原生续验](#riu-cloud-runtime-2026-10-20) | Linux 最终包与消费者通过；单模型生成 0/15、文本 3/3；免费接口与平台边界分别保留 |
| 2026-10-20 | [自动 UI、Harness 与 Cloud 暂停交接](#riu-cloud-handoff-2026-10-20) | 最新源码与旧包分开；Python 2098/2/1，Desktop 383/1；真实思考 CSS 对照；免费 source 续修与模型矩阵仍待完成 |
| 2026-10-18–20 | [RIU 请求去重、真实任务矩阵与便携包续验](#riu-quality-2026-10-20) | 保留脏工作树基线、完整请求与原生思考；源码回归、最终目录包、长路径真实解压分别验收；模型质量矩阵及失败归因单独记录 |
| 2026-10-17 | [RIU 提示词、真实模型与生成质量续验](#riu-prompt-quality-2026-10-17) | 模式/工具/运行时修复、原生思考人工复核、真实模型新写 HTML 与业务交互；成功、失败和静态提示分别记录 |
| 2026-10-17 | [RIU P4 展示与 Windows 交付验收](#riu-p4-delivery-2026-10-17) | P4 28/28、P2 24/24、P3 26/26、隔离 36/36；20/60 次渲染/输入采样；NSIS 载荷与便携实际运行。Python 全量 1 失败、真实模型 403/404/400/429、完整安装/卸载及其他平台保持未通过或未验证 |
| 2026-10-16 | [Intelligent UI P3 MCP Apps 互操作](#riu-p3-interop-2026-10-16) | Windows 最终目录包、原样官方 ext-apps 2.0.3 示例与失败/恶意 fixtures；26/26 互操作、36/36 隔离；离线 inline profile，实际 stdio / 核心协议 2025-06-18；完整 window.openai、Plugin Extensions、HTTP/SSE UI 与其他平台未验收 |
| 2026-10-15 | [Intelligent UI P2 交互与生命周期](#riu-p2-interactions-2026-10-15) | Windows 实际 packaged Electron + loopback 模型，24/24 交互与 34/34 隔离；审批归属、Stop、崩溃未知写状态不重放、私有状态与摘要、fork/rewind/delete；MCP 兼容与其他平台未验收 |
| 2026-10-11 | [Intelligent UI P1 流水线](#riu-p1-pipeline-2026-10-11) | render_view→受限存储→宿主→重启/fork/rewind/delete→TUI 全链路；两 fixture 的 Python e2e、渲染层重建、打包探针重跑 34/34；身份内核绑定、先持久化后显示、HTML 不重入模型请求；Linux/macOS 与实机模型驱动生成未验证，不宣称 HTML 零 token |
| 2026-10-11 | [Intelligent UI P0 隔离宿主](#riu-p0-isolation-2026-10-11) | Windows 打包 Electron 隔离探针 34/34、死循环与洪泛下宿主可用；仅 P0 可信宿主，Linux/macOS 未验证，P1 未实现 |
| 2026-10-10 | [桌面内存与独立 EXE](#desktop-memory-2026-10-10) | Windows 打包进程树采样、内核生命周期、界面及本地回归；模型目录不等于账户实测 |
| 2026-10-09–10 | [提交前验证](#publish-validation-2026-10-09) | 当前源码回归、Windows 构建和隔离应用检查；不替代远端 CI 或真实服务验收 |
| 2026-10-08 | [API 兼容](#reverie-cli-api-compatibility-2026-10-08) | 源码模型流程与编译后的上游失败分别记录 |
| 2026-10-07 | [Desktop UI](#reverie-cli-apple-ui-redesign-2026-10-07)、[启动与托盘](#reverie-cli-background-startup-repairs-2026-10-07) | Windows 打包与本地交互；不等于新增 provider/RATS 验收 |
| 2026-10-06 | [Workbench](#reverie-cli-workbench-repairs-2026-10-06) | 面板、文件编辑和本地请求耗时 |
| 2026-10-05 | [功能审查](#reverie-cli-feature-audit-2026-10-05)、[功能修复](#reverie-cli-feature-repairs-2026-10-05)、[请求修复](#reverie-cli-request-profile-repairs-2026-10-05) | 修复前后分开；MCP/平台附录仍保留未验证项 |
| 更早 | 下方完整原文件索引 | 原日期与原测量保留，不累计为当前的一次通过 |

<a id="riu-static-rich-routing-2026-10-27"></a>

## 2026-10-27 静态富格式回答路由追验

桌面静态回答路线收窄为内联生成：自包含的统计卡、总览表和推荐卡请求不携带无关工具、历史或记忆负载；其他请求仍使用原有工具路径。系统提示词要求每一组统计标签和值各输出为一个 metric item，保持请求顺序。新增 agent 与提示词契约专项 **99/99**，Python 完整套件 **2392 passed / 24 skipped / 14 warnings**（405.36秒）。

Qwen3.5-4B 一次 loopback provider 请求完成于 **120.364秒**，准确输出合成请求指定的 `计划中=7`、`开发中=5`、`已有成果=4`、`半归档=1`，两条三列项目行，和带正确徽标、来源及链接的编号卡。深浅主题与1280/460px布局 containment 检查4/4通过，浏览器错误0；窄图已人工查看。前序 v5/v8/v9 语义失败以及 v6/v7 环境中断均保留，v10 也只算探索性模型响应，正式样本0。模型/API、AppImage FUSE、Windows/macOS、真实设备与辅助技术验收没有改变。所有报告与截图见[独立证据目录](verification/2026-10-27-static-rich-routing/README.md)。

### 当前源码 Linux x64 v11 / v12 验收追踪

v11 的缺陷与失败原样保留：AppImage 参考布局富格式 **86/86**，但 P2 因冻结 Python 缺少 Pillow `_imaging` 未完成。源码 `ReverieCli-py/reverie.spec` 已明确收集 PIL 模块和动态库。v12 clean venv 构建的 kernel SHA-256 为 `d0d9f110bcd14e1bcb768933af3733f38177847bf9f0fb1ea3265923be63b5e9`，含 `_imaging` 且 `--kernel-info` 通过；UI build `fcce0356b0365178`，Vite 转换2071个模块。首次 v12 stage 曾发生 OOM，随后单独打包产出了当前候选 deb/AppImage；两次原始 builder exit1 日志仍保留。

原始候选 deb SHA-256 `48cbae5dd86f2c6535cb557354cb2b0ffdc2076dae1e2c6d0e020e4a7a7e3c29`，AppImage SHA-256 `6cf3d6468b28853cab7ccf90d2f7a368ef3918fc80e0895af473f8ce852bb1a6`。`dpkg-deb --info` 显示 `reverie 2.5.0 amd64`；包内 `ReverieUI`、`resources/app.asar` 和 Python sidecar 分别与 AppImage 提取内容哈希相同。然后在干净 tmpfs 目录用仓库原样 `package-validation.mjs` 和核验过的 v12 预打包载荷重跑 deb 与 AppImage，两个目标均以退出码0完成；新 duplicate package 只留在临时文件系统，哈希和日志记录在[结构化包重建记录](verification/2026-10-27-static-rich-routing/package-rebuilds.json)，没有覆盖原始候选或失败报告。

当前持久化 AppImage 以正常 FUSE 挂载启动（不是 extract-and-run）：富格式回答 **86/86**、P2 **24/24** 通过，覆盖图像源/实际加载与说明、徽标、来源胶囊、链接、真实表格数据、主题对比度及宽窄布局。容器原先缺 `libfuse.so.2`；从 Debian 官方快照下载并校验的 `libfuse2t64 2.9.9-9` 只解压到 `/tmp` 并通过 `LD_LIBRARY_PATH` 使用，没有系统安装。缺库时的首次失败单独保留。

从该 AppImage 提取的实际 `ReverieUI` 和同目录 sidecar 通过 P3 **26/26**、P4 **31/31**、隔离 **36/36**。P4 基线注册至可交互20次 P95 **332.864ms**；1,000行输入至两帧60次 P95/最大 **51.8/82.2ms**。另用同一 v12 构建运行60次合成创建/渲染循环，完整31项检查通过；该轮注册交互60次 P95/最大 **286.16/360.888ms**，输入至两帧 P95/最大 **47/62.9ms**，报告见[p4-stress-v12-60](../.runtime/riu-completion-20261021/package-v12-retry1-linux-20261027/p4-stress-v12-60-20261027/report.json)。仍不能据此宣称小时级稳定或真实模型性能。第一次 P4 的输入 P95 为101ms且在尝试启动纯文本 sidecar 时遇到 harness 路径假设，报告不覆盖；提取程序的完整重跑通过。隔离探针宿主在循环/洪泛期间均1ms响应、销毁4ms、销毁后17ms响应。

早期 rootless 最小 chroot 测试曾以 `--force-depends` 安装 v11、替换为 v12 并卸载；它仅验证包维护脚本和文件生命周期，原始日志保留。随后在独立 Bubblewrap user/mount namespace 根中，以当前 Debian 13 依赖清单、可写临时包根和只读宿主系统库/工具，未用 `--force-depends` 完整安装 v11、同版本升级至 v12并卸载成功。测试核对两个 kernel SHA-256、CLI/GUI 入口、`chrome-sandbox` 权限、包触发器及清理；宿主 dpkg 数据库和系统路径未改变。报告与成功日志见[完整依赖生命周期证据](../.runtime/riu-completion-20261021/package-v12-retry1-linux-20261027/deb-bwrap-isolated-lifecycle-20261027.json)。Debian 13 只读 APT 模拟也确认必需依赖由当前系统包（含 t64 提供项）满足。未在宿主系统安装软件，也未启动已安装桌面，因此宿主级安装与 GUI 启动仍未验收。

Qwen3.5-4B 当前源码应用内只完成一次合成展示请求，耗时 **118.47秒**：四个指标、两行三列表格和编号徽标/来源/链接推荐卡逐项匹配；深浅主题 × 1280/460px containment 4/4、浏览器错误0。窄屏截图已人工查看。这只新增一份探索性本地响应，不是正式模型质量样本；正式样本仍为0，按两组上限不开展第三组、不重评历史结果。

保留的其他失败包括：首轮 Xvfb 提前退出、P3/P4 harness 对 AppImage wrapper 目录布局的假设、FUSE 首次缺少兼容库、隔离 deb 首轮缺少 passwd/group 与 `/dev/null`、一次 tmpfs 满。每个失败有独立日志，最终重试没有覆盖失败原件。详细报告见[当前包结果](../.runtime/riu-completion-20261021/package-v12-retry1-linux-20261027/build-report.json)。整体 RIU 仍未完成：Windows x64、macOS arm64/x64 实机、物理 IME/屏幕阅读器/设备尺寸、长时稳定性和广泛模型质量均未闭环。

<a id="riu-completion-2026-10-22"></a>

## 2026-10-21–22 RIU 作者契约与验证器继续实施（执行中）

2026-10-23：Linux **3824bc06ee6c6e24** 对应完整 Python **2214/24/14 warnings**（168.19s）、六组 **244**、Desktop **387/1** 和类型/文档/diff 通过，源码前后哈希一致。14 个冻结模块、71 个 UI 文件及独立 CLI 10 个模块通过；CLI SHA-256 `20458438b6448396de9eedfa7f7985d77e485f378542ff6ae3172592087d9d37`。P2 **24**、P3 **26**、隔离 **36**。P4 首轮和同构建诊断轮输入 P95/最大 **107.7/165ms**、**101.3/161.2ms**，各 **30/31**；两份原报告和失败验收文件未改。只对闲置旧包文件缓存做不改磁盘内容的释放，实测内存占用下降约 1.764GB，随后相同源码、夹具、样本和门槛下 **31/31**，注册 P95/最大 **266.625/336.359ms**、输入 **68.9/96.9ms**；不能据此证明前两次原因或稳定达标。详见[本包结构化验收](verification/2026-10-21-riu-completion/native-build-3824bc06ee6c6e24.json)，包含三轮原始证据和资源条件。

同一份实际 native6 方案页面及会话在新包中通过六项摘要投影检查，原模型 HTML、原始历史及给模型的建议保持完整。实际查看了重开会话和 PiP 两张截图，用户摘要只显示原清单摘要。安全初始化示例、按钮与 SVG 配色指导、历史摘要回归合计改变五个源码/测试文件；终端与专用模式七份提示字节不变，十种模式工具与原有推理指导保留。GPT-OSS native6 全开发生成 **0/5**、文本 **1/1**；环境中断前用掉的两次反馈计入累计预算，续跑零剩余反馈。当前在执行同 397B/计算器构建前后观察，正式 **30+6** 仍需实际完成。

前一阶段 Linux 原生构建 **106bbd324fcf60f7** 对应 Python **2213 passed / 24 skipped / 14 warnings**（154.65s）、六组重点检查 **243 passed**、其中验证器 **114**，Desktop **383/1** 与类型检查重新通过，六个回归阶段均通过且源码哈希不变。14 个冻结模块、71 个 UI 文件、独立 CLI 10 个模块及信任清单核对通过；独立 CLI SHA-256 为 `9d961b3a8b8cf5f121e65338dbf3da020949b8dd5cb0526a91ba4677d7849a0e`。P2 **24/24**、P3 **26/26**、P4 **31/31**、隔离 **36/36**；注册上界 P95/最大 **630.160/648.881ms**，本地输入两帧 **50.6/69.5ms**，模型/编译/压缩未并行。详见[该包原生验收](verification/2026-10-21-riu-completion/native-build-106bbd324fcf60f7.json)；它不宣称真实模型质量门完成。

原冻结开发轮次十例生成中自动完整通过七例、文本二例通过；人工复核保留深色白卡片不可读及其他对比度问题。一例表单恢复为没有再次编辑入口的成功页，原键盘探针对隐藏字段的超时保留；两类原生探针时序错误与合法行内提示误判分别记录。新对比度探针也先复现柱顶文字背景误判，再用实际绘制位置修正；同一份模型图表在原生双主题中通过纠正后的只读复核，原 HTML 未改。后续先完整复查 GPT-OSS-120B，再冻结正式模型；旧报告不追改。

本轮继续使用 `350c5ba` 的既有脏工作树，版本保持 2.5.0，未提交、推送或发布。Desktop 自动选择回答形式及完整宿主示例前置，明确零值恢复、派生控件和约 400×400 首屏布局；工具作者提醒不阻断或改写模型 HTML。可选缓存提示被提供商明确拒绝后，仅在当前 agent 的来源、模型和凭据作用域内记住拒绝，保留全部 27 个工具、历史和原生思考。

前一轮原生构建对应的回归为 Python **2166 passed / 24 skipped / 14 warnings**（155.12s）、专项 **196 passed**，Desktop **383 passed / 1 skipped**，类型检查 **1041 translations / 82 templates**，文档和 diff 检查通过，回归前后源码哈希一致。Linux 构建 **651cf38f6afdbff1** 的 14 个冻结模块、manifest、71 个 UI 文件及独立 CLI 10 个模块核对通过；独立 CLI SHA-256 为 `39d58c3f7be6918da2eb9205aa16e8d60efc0975158ce3d9037c39b255677111`。P2 **24/24**、P3 **26/26**、P4 **31/31**、隔离 **36/36**；20 次注册到可交互 P95/最大 **231.621/317.555ms**，60 次输入 **42.8/46.4ms**。测量期间没有并行模型、编译或压缩任务。

外部验证器此前 **78 项**回归包含真实 Chromium 的正反例。表单 maxlength 后成功进入确认页、整卡选择和显式应用筛选、末尾 Tab 触发懒加载、价格排序箭头与 CSS 柱状图分别留有旧失败和新诊断；不追改原始报告。随后增加库存菜单、多个下拉框及月工作日/年假标签区分，新增反例原为 **4 失败 / 2 通过**，修正后专项 **84 passed**（26.13s），当时全量 **2172 passed / 24 skipped / 14 warnings**（154.26s），源码前后哈希一致。仅外部验证器和测试改变，产品源码未变，Desktop 与类型检查明确沿用上一轮通过记录。主要结果在 PiP 首屏之外、CSS 覆盖 hidden、零值被默认值替代等实际质量问题也保留，没有因注册成功而标为通过。此前漏传 DISPLAY 的全量 2058/60/24、提示词契约 181/1、P4 首轮超限和环境中断记录均保留。

官方 MiniCPM5-2B Space 的公开 Gradio/SSE API 与 OVHcloud 标准 Chat 匿名入口分别核对；前者不暴露 tools。OVHcloud 每 IP、每模型每分钟两次，当前开发实测遵守 Retry-After；Qwen3.5-9B、397B 及其他候选的原生工具预检不计为页面质量。完整两模型矩阵、相同模型任务的前后性能对照与人工多类型复核仍在执行，详情及原始目录见[实施记录](verification/2026-10-21-riu-completion/progress.md)和[免费来源核对](verification/2026-10-21-riu-completion/free-model-sources.md)。Windows/macOS、安装器生命周期、物理 IME 和屏幕阅读器仍缺本轮验收。

<a id="riu-cloud-runtime-2026-10-20"></a>

## 2026-10-20–21 Cloud 原生续验

实际工作区初始是干净的旧 `0bcbdda`，联网 fetch 后 fast-forward 到用户指定 `350c5baaed1b41f399ca09e01b912a4f81eaa80e` 才开始修改；没有 reset/clean 或覆盖用户工作。没有适用于根目录的 AGENTS.md。Linux x86_64 / Python 3.12.14 / Node 24.19.0 / Electron 41.2.1，约 30 GB 可用空间。原本缺少 Xvfb 和 PyInstaller，均在仓库内准备；没有 Windows 或模型密钥。旧 `.runtime/riu-*` 原始材料不在云端，使用已提交摘要并另建 `.runtime/riu-cloud-20261020`，不伪造旧日志。

粘贴失败可控复现：相同 CRLF 按键，修饰键关闭返回两行，持续按下使最后 Enter 变成换行并耗尽测试队列。这证明测试受真实 GetAsyncKeyState 影响的机制，但不证明旧 Windows 运行当时的物理键盘状态。测试隔离真实修饰键，保留显式 modified-Enter 用例；中文粘贴在 Linux 通过模拟输入模块执行，不能冒充 Windows 原生 IME 通过。

重试复现先红后绿：SDK/直接 HTTP 原来忽略 Retry-After；现保留秒数/HTTP 日期且不短于本地退避，沿原可取消等待，有界重试。普通 402 不重试；Pollinations 官方文档定义的 402 + Retry-After 允许等待免费时隙。匿名 Chat 原先被 SDK 空密钥检查拦截，现走已有无认证 HTTP 路径。这一步未改执行器；随后在原执行器中增加下述不完整参数拒绝。审批归属、会话锁、私有状态或 opaque-origin 沙箱保持原约束，没有新增思考/回答长度上限。

| 检查 | 结果与边界 |
| --- | --- |
| Linux Python 首轮 | 2021 passed / 24 skipped / 61 failed；60 项缺显示服务，1 项把包导入误当编码数据可加载，原日志保留 |
| 显示服务与验证前提修正后 | 2085/24；最终匿名路径修改后全量 2086 passed / 24 skipped / 14 warnings，125.58s |
| Desktop / 类型 | 383 passed / 1 skipped，74.83s；1041 translations / 82 templates |
| Linux CLI | 两次构建均保留，最终独立 CLI 与 7 个当前源码模块匹配，SHA256 `b39a04bee837ba5cbe8b56778d9478327d7650c49b68462f56df875df62b397e` |
| 最终 Linux 目录包 | `52ef2dbeb064d87d`；12 个冻结模块、manifest、71 个 UI 文件匹配，信任清单对应上述最终独立 CLI |
| 消费者 | P2 24/24；P3 26/26，SDK ext-apps2.0.3 / UI2026-01-26，官方组件未改写 |

P2 首次误在目录包生成完成前启动，FileNotFoundError 保留；P3 首次与前一 GUI 尾段重叠而触发单实例退出，保留后串行重跑通过。首轮 P4 31/31，但采样期间存在构建负载，保留为探索而不选作最终性能结论。打包包含 Windows-only hidden-import 和 Tk 库警告，没有据此声称那些功能在 Linux 可用。构建输出保留在仓库规定的 dist/build/release 路径，独立验证与临时材料在本轮目录。

OpenCode 官方现用 inference 路由，实时目录不含交接候选 Space Bunny。deepseek-v4.1-flash-free、big-pickle 在 zen 和 inference 两条路由，以 Reverie 自有身份匿名请求均返回 403 FreeTierError（仅允许 OpenCode 内使用）；没有伪装客户端、申请密钥或购买额度。切换官方明确允许匿名的 Pollinations Classic，目录为 openai-fast（GPT-OSS 20B），文本实际 200；官方每 IP 文本请求间隔至少 30s。gen.pollinations.ai 的更多模型目录不是免费可用证明。OpenRouter 官方要求 Bearer key，本环境未配置，不申请。

矩阵默认每条样本独立工作区/记忆/profile/进程，真实生成与普通文本分开。零断言注册仍为 registered_unvalidated。质量、请求规模、最终性能与失败分类在本轮结构化证据中继续记录；不把历史 SenseNova/NVIDIA 的不同来源延迟作为本轮前后改善。

环境重启后，继续保留旧矩阵：计算器/表格没有生成视图，旧验证器把缺视图归到浏览器超时；当前明确为 model_no_view。图表产生 23 项断言但多项业务/主题/恢复/版本失败，实际进程重启部分被环境重启中断，不算完整样本。文本对照已改用 session.roles 的磁盘角色归一化。根据模型原生思考补充“交互视图是回答的一部分、无需用户要求修改仓库”的指导，普通单次计算仍为文本。

重组图表原始 SSE 发现首个 create_file 参数字符串/对象未闭合，上游却结束为 tool_calls；旧 JSON-ish 扫描兜底把它写成 31 行半截文件。focused reproduction 先失败（确实写入），再修复解析失败标记沿历史归一化保留，由原执行器在工具发现与副作用前拒绝，返回正常工具错误供模型重提完整调用；上游可选的预审查流程保持不变。完整但转义欠佳的长内容回归保留，原生思考不删改。该阶段源码全量 **2089 passed / 24 skipped / 14 warnings，144.01s**，另有 156 项相关回归和拒绝归一化后不完整调用的 focused 断言。主模型 SDK/直接 HTTP 冷却等待不等于压缩器等所有辅助调用都已重构。

第二次矩阵在表单续轮出现真实 400：上游 messages 校验失败。逐字核对发现空 SSE 工具占位被执行成无函数名/无 ID 的调用，额外写入 tool_call_id 为空的结果；旧自动兼容兜底随后在 400/401/403/503 等错误下移除工具及其历史继续请求。先停止该受污染轮，保留 19 项已完成断言、400 原文、取消记录与所有模型原生数据，再修复：终结流时移除无身份占位，为缺失 ID 的有效调用一次绑定同一 ID；向 API 发送的副本排除旧空 ID 孤立结果，磁盘历史不改；删除自动剥离工具的 HTTP 错误兜底。4 个 HTTP 状态复现先失败，当前通过。原生思考不变，声明的 27 个工具/schema 不因错误被隐藏。见[协议失败原始归档](verification/2026-10-20-riu-cloud/protocol-failure-evidence.zip)。

最后协议修复的全量 Python 为 **2096 passed / 24 skipped，126.80s**；导出 JUnit 新增 45 条 record_property/xunit2 格式警告，另有 14 条原弃用警告，均保留。Desktop 再跑为 **383 passed / 1 skipped，90.75s**，typecheck 仍为 1041/82 通过。24 项 Linux 跳过原因逐项写入本轮证据。当前包 P2 24/24、P3 26/26 已再次通过；后续模型矩阵使用协议修复后的新目录，不拼接此前受污染轮的成功率。

最新 Linux 构建更新为 `342c18881b0108a4`，13 个模块、manifest、71 个 UI 文件匹配；最新独立 CLI 哈希为 `871c8efb2dedb3671ceb1cfcd77d083bded82936968d17b99919a74781de1e12`，同样经过源码核对。前文构建 `52ef2dbeb064d87d` 及其 P2/P3/P4 数字保留为相应阶段的证据，不能替代此后修复的新消费者验证。

此构建后续 P4 **31/31**、隔离 **36/36**。无并行构建/压缩/模型批量请求时，20 次注册到可交互 P50/P95/最大为 **177.089/266.904/290.902ms**；1,000 行本地输入 60 次到两帧 P50/P95/最大为 **37.6/68.4/122.1ms**，保留最大尖峰。隔离期间宿主 flood/loop ping 为 6/1ms，拆除为 3ms。它们是确定性消费者夹具测量，不能当真实模型生成速度或生成质量通过。OpenCode 最终生产链路成功取得 live catalog 并精确选择 raw ID，唯一生成请求得到 403 FreeTierError；不再自动剥离工具重发。

23:16 UTC 托管环境再次重启，协议修复后矩阵已完整结束 6 项；第 7 项写入 model_no_view 但尚未完成清理，单列中断，不纳入完整样本。续跑使用同一冻结包、同一验证器/任务与请求配置，在新目录补完余项，不覆盖原始 checkpoint。相同计算器任务的完整请求和 SSE 均出现相同 SHA256：profile/工作区独立不证明上游随机响应独立，重复响应会另行报告。客户端没有指定 temperature/top_p/seed 或输出长度，使用该服务默认值；多次上游 completion_tokens 恰为 1500 的不完整调用保留为截断证据，不能将其推断成客户端新增长度限制。

此版本矩阵最终完整 **15 生成 + 3 文本**：生成 15/15 model_no_view，文本 3/3 通过；41 个生成/续轮请求均 HTTP 200，报告 usage 合计 957853 token（含上游重复结果，不能推断实际计费或独立推理量）。4 个响应恰为 1500 completion token，7 组完全相同请求/SSE 各重复三次。单独诊断仅给保留的图表请求增加 max_tokens=16384，仍返回 1500 token、未闭合 create_file 参数；它不是 GUI 或质量样本，未据此改产品默认长度。

随后在原生包实际操作早期模型表单/图表，未修改 HTML：表单总价实时变化、键盘 Tab 和 PiP 布局可用，但真实报名点击不触发 submit；合成事件诊断能进入原处理代码，不算用户交互通过。确认现有 allow-scripts 沙箱禁原生表单/模态弹窗，保留既定权限并补全作者指导。图表点击“应用”后 2 倍=720、0 倍空态、负数反馈可用，但输入时不即时重算、明细行缺失、主题/状态恢复失败；实际进程重启后倍率 2 回到 1，零模型请求。三种展示模式在同一文档中切换，模型 HTML 哈希不变。窄窗重载后侧栏不可见造成一次检查定位等待，恢复窗口宽度后继续，未归因模型。此后的作者指导属于新的提示词版本，不能让前述矩阵替它通过。

补充表单作者契约后 focused 先红后绿（41 项通过），再全量 Python **2096/24/14 warnings，131.92s**、Desktop **383/1，59.97s**、类型 1041/82。新的 JUnit 导出采用兼容 record_property 的 xunit1，前一轮 xunit2 的 45 条格式警告及原始文件保留。第 6 轮 CLI/目录包构建为 **6328483677ede0e4**（23:39 UTC），13 个冻结模块、manifest、71 个 UI 文件匹配；独立 CLI **7b92340001cc325591d48eb1a3a8ae63116b31a8b329928df0e341340b53a6f9**，9 个模块及信任清单核对成功。没有修改 iframe allow-scripts、CSP、权限策略或模型思考。

该最终包串行 P2 **24/24**、P3 **26/26**、P4 **31/31**、隔离 **36/36**。P4 20 次注册到交互 P50/P95/最大 **189.869/305.666/314.394ms**；1,000 行输入 60 次到两帧 **38.4/70.8/90.4ms**。隔离 flood/loop ping **12/9ms**，拆除 **24ms**。这些数值与前一构建 342c 的性能分开保存，不能择优混报。此包再启动固定提示词下的 15 生成 + 3 文本独立矩阵，当前范围与最终结果见结构化报告。

矩阵中继续定位两类归因：没有注册修改版本，却在旧页面等待新增字段；图表输入只有相邻文字、没有 label/aria-label，却报普通定位超时。新增明确的版本注册失败与必需可访问控件失败断言，原始报告不改。表格还复现 OOPIF 搬移后的指针时序：立即点击 5 次有 4 次事件未到组件；等待父、子页面各两帧后 5/5 正常。只修验证器绘制同步，未修改模型 HTML、沙箱或业务行为。相关回归先红后绿。

环境在长时间间隔后无存活进程，最终矩阵原 checkpoint 保留 8 个完整样本，第 9 个图表中断单列；2026-10-21 继续新目录。原表单上游 SSE 明确包含 `upstream_error/usage_missing`，客户端保留数据并终止；它不是本地新增的 usage 校验。原表格点击时序错误另行重跑，已有可证实的业务/可访问性失败增加复核归因，不改写原异常或挑选更好的响应。

2026-10-21 再查官方端点，发现 `/inference/openai/v1/models` 实际 404，目录在 `/inference/v1/models`。先记录真实返回、focused 红例，再仅修官方 opencode.ai 域名的目录映射；保留新聊天路径、旧 zen 路径和自定义代理/query。录制器显式转发生产 source 解析出的独立目录 URL；测试后的 HTTP 请求/SSE 仍逐字节转发。source/录制器相关 **53 项通过**；本阶段产品全量 **Python 2102/24/14 warnings，147.01s**、Desktop **383/1，73.04s**、类型 **1041/82**。

第 7 轮构建 **f83a5d6f50971c66**：14 个模块（包括 opencode）、manifest、71 个 UI 文件匹配；独立 CLI **0c2fe03aac499d867123b80dc65fe00d8612fb5bc60f744ca8fe97f044ba0b07**，10 个模块及信任清单匹配。与 6328 的共同 13 个运行模块源码哈希一致，70/71 个 UI 文件字节一致，差异为构建信息。标准来源采样/任务/提示词源码未改，跨日日期和派生缓存键变化已记录；矩阵各构建保留来源区别。

此包再串行 P2 **24/24**、P3 **26/26**、P4 **31/31**、隔离 **36/36**。最终 P4 注册到交互 20 次 P50/P95/最大 **175.782/273.696/282.291ms**；输入到两帧 60 次 **34.6/44.1/50ms**。隔离 flood/loop ping **2/2ms**、拆除 **6ms**。OpenCode 新目录真实 200，生成请求以匿名 `Reverie-Cli/2.5.0`、`reverie-cli` 身份仅发送一次，真实 **403 FreeTierError**；目录修复不代表取得免费权限。Pollinations 今日目录仍只有 openai-fast，实际响应 GPT-OSS 20B；不申请密钥、不购买、不伪装客户端。

最终固定作者契约矩阵在 2026-10-21 13:15:48 UTC 完成 **15 生成 + 3 文本**：原始生成分类为 10 次 model_no_view、2 次 validator_or_product_error、3 次 service_unavailable；两项原始定位异常按保留的版本/DOM/业务失败复核为 semantic_failure，原报告不改。生成质量 **0/15**，文本 **3/3**。共 58 个请求均 HTTP 200，但其中 3 个服务错误 SSE 含 usage_missing；HTTP 200 不等于质量或协议成功。8 个响应恰为 1500 completion token，9 组请求/SSE 哈希重复。上游报告 usage 1323228 token，不能据此推断实际计费或独立推理量。18 个样本的临时配置清理均完成；原表格指针时序样本和图表环境中断另列，不混入完成数。旧、新构建的耗时分别汇总，跨日日期及缓存键差异使其不构成受控前后比较。

人工操作还补齐第三类早期模型产物——原 table-2：关键词和清除有效，空结果没有明确空态提示，深色下黑色文字不可读；PiP 关键控件可见。真实指针与双帧诊断均保留事件日志，没有用脚本设置 checkbox 状态冒充点击通过。表单、图表、表格的原 HTML 哈希均未改；它们是实际包上的人工复核，不替代最终矩阵质量。

按用户新线索检索官方 Hugging Face：MiniCPM-V 4.6 页面仍有 2026-05-17 “公开免费 API Key”公告，但当前 OpenBMB API 文档要求注册 Key，匿名 models 实际 401。另已通过官方 MiniCPM5-2B Space 公开 Gradio API 完成一次无 Key/Cookie/Token 的推理：POST 200、SSE 200、约 3.900s，保留完整原生响应。该接口没有暴露 tools/tool_choice，未计入第二个 RIU 工具闭环模型；ZeroGPU 共享配额亦不能当无限生产服务。LFM 官方 FAQ 和 Space 的远程/本地运行方式分别核对，见[免费接口核对及调用形式](verification/2026-10-20-riu-cloud/free-api-search.md)。

P3/P4 原始报告的 scope 沿用了历史 Windows 字符串；本轮实际运行环境、二进制路径、构建平台及 P4 hardware 都是 Linux。原报告保留，验证脚本后续 scope 改为平台中性，不借该字符串声称 Windows 通过。

最终 Python 全量包含最后一项独立目录转发回归，核心目录运行 **2103 passed / 24 skipped / 14 warnings，121.48s**。仓库根目录的文档命令首次收集时有两项 scripts 命名空间导入错误，原日志保留；pytest.ini 显式加入核心目录后，按同一根目录命令再次全量 **2103 passed / 24 skipped / 14 warnings，121.78s**。14 条均为既有 datetime.utcnow 弃用提示。Desktop 383/1 与类型检查后没有修改其源码，未重复制造新的通过数。

[结构化续验](verification/2026-10-20-riu-cloud.json)与[初期原始证据归档](verification/2026-10-20-riu-cloud/pre-matrix-evidence.zip)保存请求、SSE、会话、模型 HTML、截图、失败/回归日志及 SHA256 清单。最终矩阵保留独立目录及执行时验证器快照；所有后续材料见[最终原始证据](verification/2026-10-20-riu-cloud/final-evidence.zip)和[SHA256 清单](verification/2026-10-20-riu-cloud/final-manifest.json)。

Windows 新 CLI/GUI/便携包、安装器安装卸载、macOS、物理 IME/屏幕阅读器、远端 UI/OAuth 仍未验收；源码或 Linux 的成功不替代它们。本轮不修改版本、不发布、不提交推送。

<a id="riu-cloud-handoff-2026-10-20"></a>

### 2026-10-20 — 自动 UI、Harness 与 Cloud 暂停交接

用户因本机将关机要求暂停实现，将当前全部相关源码提交推送 GitHub，并编写 [Cloud Codex 完整续修提示词](CLOUD_CODEX_RIU_HANDOFF.md)。该请求新增了保存源码的 Git 授权，没有授权版本升级或 Release。此前“未提交/未推送”属于当时历史状态，保留原文；实际暂停提交以包含本文件和交接文件的 Git 记录为准。

最新源码改动包括：任务驱动的自动视图选择与业务初值/控件指导；Desktop 在实际检索时初始化 Context Engine；空 Harness 在诊断扫描前返回；以同一 cwd/命令最新结果判定未解决失败，同时保留历史失败；思考 Markdown 恢复正常块布局。实际 App 测试保留 fenced code 原始缩进，不过滤/隐藏/截短原生思考。源码 focused 85 passed；`npm test` **383 passed / 1 skipped，86.33s**；`npm run typecheck` 通过。完整 Python 命令仍为 `python -m pytest -q -c ReverieCli-py/pytest.ini ReverieCli-py/tests`，结果 **2098 passed / 2 skipped / 1 failed，449.56s**；`test_windows_prompt_editor_paste_preserves_single_newline` 出现 `IndexError: pop from an empty deque`，单独重跑1 passed / 0.18s。输入处理产品文件本轮未修改，尚未确定失败根因；原始全量失败不能用单测重跑覆盖。

同一份已保存 Nemotron 原生思考在真实旧包中仅切换宿主 CSS：21 个列表项，Markdown 高度 **2318.421875→1078.671875px**，DOM 文本完全相同。前后截图、文本哈希和测试日志见[结构化暂停记录](verification/2026-10-20-riu-continuation.json)。这是旧包 CSS 实验，不是最终消费者构建验收；第一版回放因测试进程未设置 loopback NO_PROXY 而连接失败，修正测试设置后通过。最新源码尚未重建独立 CLI、Desktop 核心、目录包或便携载体；下方 `2cfd719ac18e73a4` 是此前已验证构建，不包含这些修改。

本机 SenseNova `sensenova-6.8-flash-lite` 自然语言计算器基线，经旧包真实 executor 执行：录制正确的一次耗时约147557.2965ms、4个请求，首请求125555字节/system56137字符，原生schema65683字符/27工具；上游响应合计约139秒，不能把网络与提供商推理混同成本地 Harness。首轮碰到已有6144-token配置限制，空 create_file 参数经正常反馈恢复。另一次录制器误用 SenseNova base_url 字段而请求绕过录制器；保留该失败，不引用其完整API计时。两次均 generation-only，旧报告将0项语义检查误标为first_pass/repaired_success，正确归类是 **registered_unvalidated**；验证器已修复，原报告不改写。

旧 NVIDIA 矩阵在用户改模型时于样本间停止，计划36条（30生成+6文本）、完成10条，失败和清理记录保留；未完成自然语言修改、重启和跨模板质量验收。用户随后要求 Cloud 优先自行核对 OpenCode 匿名免费模型（如当时可用的 Space Bunny），遇API错误继续定位并修复各 source 客户端路径。官方目录并非匿名可用性证明；过去403不能预判未来，也不得通过伪装客户端绕过。Cloud 应以 live catalog 和真实生产请求建立新证据；本机 SenseNova/NVIDIA 凭据及 `.runtime/` 原始材料不会随 Git 上传。安装器生命周期、其他平台及广泛协议能力仍未验收。

<a id="riu-quality-2026-10-20"></a>

### 2026-10-18–20 — RIU 请求去重、真实任务矩阵与便携包续验

本轮基线是 `main` / `0bcbddadb55c24742dff35ff0b6045c0ea938034` 加当时全部未提交、未跟踪源码，不是单独 HEAD。保存了状态、原始 tracked patch、150 个源码文件快照及哈希；继续保留原有 RIU、模式与权限工作。版本仍为 **2.5.0**，没有提交、推送或发布。独立证据根目录为 `G:\Reverie\Reverie-Cli\.runtime\riu-quality-20261018-060708`，旧日期的失败记录没有被覆盖。

按实际初始化、复用、模式切换、固定 Skill、异步 MCP/插件刷新与每轮请求链路审查提示词。模式 manifest 保留用途、适用条件和调用约束，移除与同次原生 schema 重复的参数/示例手册；完整诊断和可运行 RIU 握手、主题、串行私有状态示例保留。修正默认 `rules.txt` 注释示例被当成有效规则，以及“不要读取文件”反而触发强制检索的问题。真正的代码分析/修改仍保留检索。原生思考的语义过滤、前缀缓冲及 CLI 猜测删段逻辑已移除；失败/中断时保存已收到的原生文本和空白，不执行半截工具参数。用户固定 Skill、实际工具能力、安全审批、私有元数据和沙箱边界均保留。

首个匹配 Nemotron 计算器请求的旧包/新包实测为 **137345 / 123317 字节**，system **70175 / 56742 字符**；两者原生 schemas 均 **65683 字符、27 个工具**。这只是同一隔离配置的首请求比较，不代表全部用户配置或后续增长的历史请求；不能据此解释历史 Step 5 的 512.83 秒。完整构成和计时边界见证据根目录 `request-construction-audit.md`；原始请求与 SSE 位于各次样本目录。原生思考仍可能复述说明或预演代码，不通过过滤、删除或新增长度上限制造改善。

源码与交付验证分开：

| 范围 | 原始结果 / 证据 |
| --- | --- |
| Python 产品回归 | `python-full-stable.log`：2081 passed / 2 skipped，545.98s；此前 2079/2/1 的 Gamer 旧 manifest 断言失败保留。后加验证器 focused tests 另记，不加到这次全量数字中 |
| Desktop 全量与类型 | 最后一次 `desktop-full-delivery.log`：382 passed / 1 skipped，86.20s；`typecheck-delivery.log` 通过。更早的真实 Git fixture 超时/清理争用及原生空白断言失败保留 |
| 最终核心与目录包 | 独立 CLI 先构建，再生成 Desktop 信任清单；`artifacts-final.json` 核对 16 个冻结模块、manifest 和 71 个编译 UI 文件。Desktop **2.5.0 / 2cfd719ac18e73a4**。独立启动 90s 超时与后续 300s 允许窗口内通过的 18 项检查分别保留 |
| 最终目录包 GUI | `p2-final` 24/24、`p3-final` 26/26、`p4-final` 31/31、`isolation-final.json` 36/36；固定 SDK ext-apps **2.0.3** / UI **2026-01-26**，原始官方组件不改写 |
| 本地渲染与输入 | P4 20 次本地渲染 P95 **345.467ms**、最大 **499.104ms**；60 次输入到两帧 P95 **68.8ms**、最大 **73.8ms**。比前次 244.925/411.419ms 更高，不宣称渲染加速；模型生成、落盘、宿主事件和本地帧初始化分别记录 |
| Windows 原生归档 | `archive-native/report.json` 真实文件系统检查 5/5；不代表模型或安装器验收 |
| 便携包 | 见下方真实缺件失败与修复后全新提取；`portable-long-path/report.json` 3/3 同实例切换，`final-delivery-long-path.json` 完整载荷 1084/1084、既有不可变载体 78/78 哈希匹配 |
| 安装器与其他平台 | NSIS 从已验证目录包生成；无可用干净 Windows VM/Sandbox，未在主机安装或卸载。PATH、快捷方式、卸载及 Linux/macOS 原生验证仍未完成 |

便携包最初冷启动有一次视图按钮选择超时，后续暖启动及另一全新目录分别 3/3，原超时原因仍未确定。随后完整字节检查发现 **19 个深路径内置 Skill 文件缺失**：GUI 通过不等于载荷完整。原 `final-delivery.json`、错误载体及解压目录保留。原生 NSIS fixture 先复现，再验证逐文件扩展长度路径提取；安装编译器 3.0.4.1 不支持 `ManifestLongPathAware`，没有擅自升级。启动器现在检查每次文件写入，全部成功才保存标记，脚本变化参与缓存身份。首次 `/oname` 引号编译错误保留；正确语法构建后的全新提取 **19414.1342ms** 包含解压、核心启动及恢复，不能当作模型或纯渲染耗时。

本轮最初 G 盘仅约 941MB 可用。自动审批拒绝递归删除已核对的 PyInstaller 缓存，返回 `blocked by policy`；未执行该删除。后来仅对 SHA-256 相同的不可变重复载体建立硬链接，保留用户配置、原失败证据、模型会话和 HTML；其他宿主活动带来的空间变化未归因于本轮清理。

真实任务固定于 `matrix-contract.json` 与[任务集](../scripts/verification/fixtures/riu-quality-tasks.json)，通过[生产 Desktop 验证器](../scripts/verification/riu_quality_benchmark.py)运行：两条已配置 NVIDIA 模型、五类生成任务各三次独立全新会话，文本对照另记。10 月 20 日预探测中 Laguna 先返回 503 worker 额度耗尽，85 秒后返回 200；生成阶段再次出现 HTTP 200 中的 SSE 500，均保留。模型错误、宿主错误和验证器错误分开归因；页面重载后事件订阅丢失及表格降序选择器已先复现后修正，旧失败不覆盖。矩阵结果、自然语言修改、版本/重启和人工视觉复核仍须按逐样本证据判断；注册成功、主题变色及漂亮截图均不关闭生成质量门。

<a id="riu-prompt-quality-2026-10-17"></a>

### 2026-10-17 — RIU 提示词、真实模型与生成质量续验

续修用户提供的 Opus 记录。此前将 Writer 失败归为“提示词预期冲突”不足以解释实际问题：主提示词、工具 manifest 和运行时附加块之间确实存在能力不一致。本轮按真实工具注册表分配工程/媒体/Context Engine/harness 指导，给 Atlas 实际注册任务账本，去掉 Writer 不可调用的文件/发现工具和动态 MCP/插件说明，保留用户固定 Skill。模式切换保存后刷新指导。原始模型 ID 与显示名称分开，媒体摘要区分开关、模型/凭据缺失及服务未验证；不由历史成功率或空 harness 推导智能水平。

发现并修正 Desktop 调用 `run_prompt_once` 时继承 CLI 单次规则的问题：Desktop 不再宣称没有后续对话，也不自动发送“Approved. Continue…”来跨过 Atlas 审阅阶段。真实工具执行、security_policy、permission_review、审批 owner 和会话锁未被替换。离线视图指导增加完整握手/主题/串行状态保存示例；`render_view` 对可执行 inline script 中明显的浏览器存储调用给出常量警告，让模型可继续修正，既不改写原 HTML，也不把静态提示当运行验证。

真实续轮还发现：注册 `artifacts/savings-comparator.html` 时多出的 `codebase-retrieval` 来自后端 `_context_engine_native_tool_choice`，原规则仅凭文件扩展名就强制检索，不能将该调用归因于模型自行偏离。改为同时要求仓库分析/修改意图；三种英中视图产物请求不再强制检索，真正的代码修改和解释请求仍保留强制检索。续轮的工具范围按当前用户轮断言，并单独保留历史违规，不从历史中删除原调用。

| UI 项 | 之前 | 之后 | 原因 |
| --- | --- | --- | --- |
| 位置按钮 | 22 px 高，激活位置仍以长提示为主 | 最少 32 px，激活按钮显示简短位置名称 | 更容易定位和操作 |
| 长摘要 | 全部展开挤压视图空间 | 默认三行，提供展开/收起；画中画更紧凑 | 保留全文与可访问控件，摘要操作不重载 iframe |
| 历史懒加载 | 未加载占位很短，加载相邻视图后把最新视图推离屏幕 | 占位预留默认或组件上报的高度，卸载后保留高度 | 在 100 视图会话中稳定滚动位置，继续只挂载可见实例 |

真实测试使用仓库内隔离配置和合成会话，仅复制选定来源的必要凭据。OpenCode `nemotron-3.5-lightning-free` 在旧、新官方路由均返回 **403 FreeTierError：免费层仅允许 OpenCode 内使用**；没有伪造客户端或绕过限制。随后测试已配置的 NVIDIA 开发接口，使用 `stepfun-ai/step-5-preview` 和 `openai/gpt-oss-20b`。它们的可用性、生成耗时与本地渲染性能分别记录，不把小型 HTTP 探针成功当完整 UI 通过。

保留的负面证据：第一轮 Step 5 身份问答的窄关键词检查曾给出通过，人工阅读仍发现明确引用系统提示词，因此另存否定结论并加严检测。后续 Step 5 不再明确引用系统提示词，但仍有“按规则”的措辞与过长能力罗列；GPT OSS 20B 的原生思考仍复述运行时说明。两次 GPT OSS 20B 生成均真实写文件并注册视图，但仍采用不支持的 localStorage；较长一轮还调用了请求范围外的 file_ops。测试脚本另有过宽标签选择器和未滚动到懒加载视图的问题，均与模型缺陷分开记录并修正。没有过滤或删改这些思考、替模型改写 HTML、隐藏失败或加入答案长度上限。

源码、冻结包、界面业务验证与人工质量结论分别列入本轮证据。协议范围仍是 ext-apps 2.0.3 / UI 2026-01-26 的离线 profile；一例成功不能证明所有模型都稳定，也不证明与 OpenAI 的完整智能 UI 对等。完整安装/卸载、Linux/macOS、原生 IME/屏幕阅读器、HTTP/SSE UI、OAuth 及完整 `window.openai` / Plugin Extensions 继续按原边界标为未验收或范围外。

最终目录包为 **2.5.0 / `a802526c1487ccb8`**，仍是当前未提交工作树，无版本提升或推送。[结构化证据](verification/2026-10-17-riu-prompt-quality.json)保留原始失败、当前结果、日志与交付文件 SHA-256。

| 验证层 | 最终结果 | 限定范围 |
| --- | --- | --- |
| Python 全量 | 2059 passed / 2 skipped | 两项符号链接能力检查因当前 Windows 环境跳过 |
| Desktop 全量与类型 | 380 passed / 1 skipped；typecheck PASS | 1041 个翻译、82 个模板；包含摘要、按钮和懒加载高度修复 |
| 包与源码 | 18 个冻结模块、71 个 UI 编译文件及 manifest 一致 | 独立 CLI 另做 20 项核对，Desktop 信任其当前 SHA-256 |
| 最终包 P2 / P3 / P4 | 24/24、26/26、31/31 | P2/P4 使用合成 loopback 模型；P3 使用未改写的官方 SDK 组件与恶意夹具 |
| 最终包隔离 | 36/36 | 包括阻断网络、父 DOM、Node/preload，洪泛与死循环期间宿主可响应 |
| Opus 归档裁剪续验 | 5/5 | 真实 Windows 文件系统，保留非归档文件及外部哨兵；未重写更广的路径键迁移，POSIX 未验收 |

真实生成的成功样本具有明确的续轮来源：Step 5 经源码 Desktop core 的真实 `create_file` 写入完整 HTML，约 **512.83 秒**；该源码轮最终带有中断标记，不能将引擎 success 标志当目标完成。之后在同一会话由打包程序真实续轮注册，修复强制检索后的该轮仅调用 `render_view`，约 **59.65 秒**。当时及最终 UI 构建均通过 **11/11** 业务/浏览器检查；最终 UI 复查没有新增模型请求。文件未由测试脚本编写或修补。两组本金与复利计算、年份及两项利率变化、三种位置保持同一文档、实时主题与私有状态恢复均实际操作验证。GPT OSS 20B 在最终包新发起的真实轮约 **55.60 秒**，经发现工具打开官方 MCP App，再点击宿主审批刷新时间，**2/2** 通过。

本地测量与上述生成时间分开：固定 7472 字节夹具，20 次可信 `view_ready` 发布时间到组件交互完成，P50 **186.338 ms**、P95 **244.925 ms**、最大 **411.419 ms**；1000 行数据的 60 次输入到两帧后，P50 **35.5 ms**、P95 **43.5 ms**、最大 **59.7 ms**。早期一组最大 **2556.658 ms** 的尾延迟保留；其解析完成到帧初始化间隔约 2504.5 ms，原因未确定，不能用成功重测抹去该尖峰。

三次早期 P4 失败分别记录：中文 stdout 编码错误、把含按钮/内边距的摘要总高误当三行正文上限，以及真实的历史懒加载布局跳动。前两项修正验证器；第三项修正产品占位高度及组件上报高度的保留，并增加“最新历史视图仍可见”的原生断言。最终 100 视图会话首次可见区挂载 2 个 iframe，长摘要正文为 57.56 px / 19.2 px 行高，展开不重载文档。

人工查看[真实模型页面](verification/2026-10-17-riu-prompt-generated.png)和[画中画](verification/2026-10-17-riu-prompt-generated-pip.png)：工作面板的结果层级与控件可读；画中画仍依靠内部滚动，参数控件在纵向排列的结果卡片下方，摘要仍夹带 HTML `output` 术语。功能通过不代表完整视觉验收，跨模板布局、文案与密度继续列为开放项。另附[真实宿主审批截图](verification/2026-10-17-riu-prompt-mcp-approval.png)与[长摘要回归截图](verification/2026-10-17-riu-prompt-summary.png)。

两个 Windows 交付载体均从最终目录包重建。便携包第一次解压时 **G 盘剩余空间为 0，退出码 2**，原失败报告保留；自动审批拒绝了组合式递归清理，随后仅删除本轮重复的单个 carrier 文件，并用同盘硬链接提供测试入口，未手动递归删除解压目录。启动器在缺少完成标记时按其原有流程重新解压，恢复验收 **3/3** 通过，三种展示位置保留同一文档，实际 Desktop build 为 `a802526c1487ccb8`。**17.15 秒**包含此次重新解压、core 启动与恢复视图，不作为冷盘或本地渲染指标。恢复后 G 盘约剩 **273 MB**；完整 NSIS 安装/卸载仍未进行。

新增可复用验证器 `scripts/verification/riu_prompt_real.py`，支持新会话、记录来源的真实续轮和无新增模型请求的已存产物复查；隔离输出目录必须放在仓库内。例：

```powershell
& ./ReverieCli-py/venv/Scripts/python.exe scripts/verification/riu_prompt_real.py --exe ReverieCli-ui/release/win-unpacked/ReverieUI.exe --sdk-root .runtime/riu-p3-sdk --source nvidia --model stepfun-ai/step-5-preview --cases identity generated --output .runtime/riu-prompt-next-real
```

这会使用当前已配置来源的真实服务，结果可能再次暴露原生思考复述、服务拒绝或沙箱 API 误用；验证器保留失败与原始事件，不承诺其他模型复现本样本质量。

<a id="riu-p4-delivery-2026-10-17"></a>

### 2026-10-17 — RIU P4 展示体验、性能与 Windows 交付验收

P4 代码与 Windows 本地功能验收已完成；**整体发布门仍未通过**：Python 全量有 1 项 Writer 提示词断言失败，真实外部模型到 MCP App 的链路未验证，完整安装/卸载及非 Windows 平台仍未验收。未改版本，未提交、未推送。当前基线为 `0bcbddadb55c24742dff35ff0b6045c0ea938034` 加既有 dirty tree；保留其他 Python/NVIDIA/RIU 工作，没有修改 Writer 提示词或其测试来追绿。[本轮结构化证据](verification/2026-10-17-riu-p4.json)记录每项命令、退出码、日志 SHA-256、实际计数、产物与限制；各次失败保留在 `.runtime/riu-p4/`，不与最终通过数累计。

复用 ConversationDisplay 的位置控件和 Workbench 的交互视图页签，只协商标准 `inline/fullscreen/pip`，`card/carousel` 是内容布局。按项目/会话/视图/revision 共用运行实例，固定 portal target 通过 Chromium `Element.moveBefore` 在连接中的容器间移动；位置与 live→历史交接不重建 iframe，保留 JS、表单和滚动。主题、语言、尺寸、CSS variables 动态更新，减少动效通过系统 CSS 与有名字空间的 Reverie 扩展提供。键盘、焦点返回、错误重试、1080×700 输入区及 Workbench 原页签恢复均有打包证据。Desktop 设置保存最多 200 条展示/展开偏好，浏览器存储仅作缓存；组件私有状态仍需主动保存，离屏销毁后不能恢复未保存的 JS 临时状态。

离屏历史仅挂载可见、聚焦、工具执行或 pinned 实例，关闭/卸载立即拒绝旧桥消息及迟到结果，释放执行租约、资源 token、监听器、观察器、计时器与动画。跨进程 iframe Escape 使用固定宿主键盘转发，只能返回 inline，不改第三方 HTML、不开 Node/preload，不触及原 executor/security_policy/permission_review/审批/会话锁。浏览器缓存清空后的展开恢复、live→历史交接、100 个离屏视图、聚焦后离屏再失焦与迟到资源释放均有定向测试。

最终目录包、NSIS 载荷与便携载荷的 UI 构建为 **`6198938667318762`**（UTC `2026-10-17T07:21:18.245Z`），Windows x64 / Electron **41.2.1** / UI 与核心 **2.5.0** / 核心接口 **1.0**。[包内一致性记录](verification/2026-10-17-riu-p4-artifacts.json)：**9 个冻结 Python 模块与当前源码代码对象一致，71 个编译 UI 文件与 ASAR 逐字节一致**。内置核心含提交后 `view_ready.committed_at`，不拿模型开始时间或写盘前 manifest 时间冒充渲染起点。

| 回归与交付检查 | 本轮实际结果 |
| --- | --- |
| Python 全量 | `PYTHONPATH=G:/Reverie/Reverie-Cli/ReverieCli-py`，项目 venv 的 `python -m pytest -q -c ReverieCli-py/pytest.ini ReverieCli-py/tests`：**2020 通过、2 跳过、1 失败，共 2023 项**，556.79 秒，退出码 1。失败：`test_reverie_prompt_upgrade.py::test_shared_coding_guardrails_are_injected_into_all_modes`（Writer，165 行）。当前提示词与“所有模式都含 Coding Guardrails”的测试预期冲突，涉及已有其他改动，未修改；不能声称全量绿 |
| Desktop 全量 | `npm test`：**379 通过、1 跳过，共 380 项**；51 文件通过/1 文件跳过，58.60 秒，退出码 0。RATS 实机集成未提供专用配对配置，继续跳过 |
| 定向检查 | Python RIU/MCP **91 通过、1 跳过**，13.39 秒；最终 Desktop 四个受影响文件 **35 通过**。不与全量相加；Windows 符号链接权限相关项跳过，不能借单测替代原生路径验证 |
| 类型与构建 | `npm run typecheck`：1038 translations/82 templates、两个 tsconfig 通过；`npm run build` 通过。`npm run dist:win` 在本轮完整生成过内核/NSIS/便携包；后续 UI 修复重建并实际测试最终目录包，最终再用 `npx electron-builder --win nsis --x64 --prepackaged release/win-unpacked` 与 `node scripts/build-portable.mjs` 从该包生成分发物，未重用旧安装器 |
| 文档与差异 | `python scripts/verification/check_docs.py`：**31 份文档、669 个本地链接、0 错误**；另报 85 个本地产物引用，不混算为链接门禁。`git diff --check` 通过 |
| P4 实际包 | [28/28](verification/2026-10-17-riu-p4-runtime.json)：同一实例三种位置、非法模式错误、iframe 与宿主键盘、亮暗主题、即时语言、减少动效、窄窗、空/1000 行/错误数据、刷新与实际进程重启、revision、缺文件重试、100 历史、撤销 token、关闭后正常聊天、私有边界及内置 CLI 摘要降级 |
| P2 / P3 实际包重跑 | [P2 24/24](verification/2026-10-17-riu-p4-p2.json)；[P3 26/26](verification/2026-10-17-riu-p4-p3.json)。原版 `@modelcontextprotocol/server-basic-vanillajs@2.0.3` 未修改，stdio / 核心协议 2025-06-18；app-only、隐藏结果 `_meta`、错误资源文本回退、审批允许/拒绝、消息建议与 teardown 均重跑 |
| 隔离 | [36/36](verification/2026-10-17-riu-p4-isolation.json)，`evaluation.passed=true`；洪泛中宿主 ping 0 ms，死循环中/销毁/销毁后本次各 1 ms。它们是单次探针，不是普遍性能承诺 |
| Windows 分发物 | `ReverieCli-ui/release/Reverie-Setup-2.5.0-x64.exe` 与 `dist/Reverie-Portable-2.5.0-x64.exe` 已生成。NSIS 安装选项页已读取，解出载荷与全新目录便携实际切换各 **3/3**；三套载荷 EXE/核心/ASAR 哈希一致。便携本次冷启动含解包、核心和恢复共 **25.41 秒**，原先约 225 秒端点超时的失败保留；这些启动耗时不算作渲染。结果/命令/哈希见结构化证据；完整安装/卸载未通过验收，保护检查发现已有 Reverie 开始菜单快捷方式，未覆盖它 |

按规格 5.1 的八组逐项核对，下面的“通过”仅覆盖实际运行的子集，不推导未测平台/扩展：

| 验收组 | 本次证据与边界 |
| --- | --- |
| 产物正确性 | 完整 Python 中的 views/render_view/bridge/e2e 与 MCP 资源负例，Desktop resolve/host tests，加打包缺文件→摘要→重试恢复。超限、JSON/编码/缺文件、穿越/UNC/哈希/跨会话等受测项通过；Windows symlink 权限跳过仍保留 |
| 事件与兼容 | pipeline、view-events、live-stream、core-protocol 与完整 Desktop 回归；伪造正文、重复/过期/取消、未知 schema 摘要降级受测项通过。没有借当前包宣称所有历史核心/Desktop 二进制组合均实机验证 |
| 用户流程 | P4 28 项、数据筛选/参数滑块、card/carousel 布局、新 revision、刷新/真实重启、缺文件恢复、关闭后继续聊天；原始 P1 SVG 图表/文本表格与复利模拟器另在最终包补跑 **5/5**，键盘滑块本地重算并跨三种位置保留。实际内置 `reverie.exe --prompt ... --report-file ...` 返回摘要，无 HTML |
| 安全隔离 | 36 项实际 Electron 探针：Node/preload/父 DOM/任意文件、导航/外链/下载/网络/相机、伪造身份、洪泛和同步死循环，执行权限不随位置变化扩大 |
| 交互授权 | P2 24 项和 P3 26 项：限制与 schema 拒绝、正确执行 worker 审批、忙碌、Stop、重复 ID、崩溃 unknown 不重放；timeout/断连/旧连接边界另由完整单测覆盖。未伪称已等待每一种审批的 330 秒超时实机过程 |
| 会话与隐私 | P2 重启/fork/rewind/delete、副作用计数与运行 journal；P3 私有 `_meta`/app-only 描述不入模型；P4 动态运行时私有标记不入全部请求，普通后续追问不附 HTML，完整模板不入请求。初始化/显式新版本时 FastContext 确实检索到原工作区 HTML 源码片段，属于真实 token 成本，不声称 HTML 零 token 或禁止用户显式读源文件 |
| MCP 互操作 | 原版官方组件与负例重跑：initialize/initialized、按序 tool-input/tool-result、回调、metadata/alias、app-only、未知方法错误、缺资源/错误 MIME/URI/网络 CSP/超大 HTML 文本回退。仅固定离线 stdio profile；HTTP/SSE UI、真实 2025-11-25 服务、OAuth、完整 window.openai/Plugin Extensions 未验证 |
| 可访问性与性能 | Tab/Enter/Escape 与焦点返回、系统减少动效、中文长标题/摘要、空/1000 行、亮暗对比度、1080×700、100 历史按需挂载及下表实测。额外用 Windows 原生输入实际切换 Workbench→pip→Escape，观察焦点环回到放大按钮。原生 IME、屏幕阅读器与全面 WCAG 认证未验证 |

性能主机为 Windows `10.0.26300`、AMD Ryzen 5 5600X（6 核/12 线程）、约 23.89 GiB RAM，Electron 41.2.1。fixture 的实际 HTML 字节数、hash 与原始样本见 runtime JSON，数据上限 1000 行；采样时没有并行构建/全量测试。采用 nearest-rank 分位数：

| 量测边界 | 样本 | P50 / P95 或原始耗时 |
| --- | --- | --- |
| 原子提交后 `view_ready.committed_at` → fixture 完成初始化/本地首轮 render 并进入 requestAnimationFrame（可交互标记） | 20 | **144.730 / 182.238 ms**，最大 183.869 ms；≤1 s 目标通过。HTML/模型生成与原子写盘分离记录，不算进此区间 |
| 1000 行本地 input dispatch → 两次 requestAnimationFrame | 60 | **24.6 / 28.1 ms**，最大 43.3 ms；≤100 ms 目标通过。不含 CDP 往返或模型等待，也不等于物理屏幕 photon 延迟 |
| 100 个视图/200 条消息历史切换 → 首个可交互视图 | 1 | **269.38 ms**；早期分页两次 **144.59、150.94 ms**；观测挂载数 **[2, 0, 0]**，最终 100 个视图行，没有全挂载。含核心 I/O，不调用模型；样本不足以称 P95 |

安装器 **441,330,470 字节**（SHA-256 `41dbe54391f03403d330a2f8bff4acd265758f98eabb35532c7f09ef1ed7b5a3`），便携包 **502,083,249 字节**（SHA-256 `8acff6b966e89d72a2aa336d8df1271fa258ca51bb358526141f81cea47e16f5`）。包内核对、载荷实际运行与截图见[结构化记录](verification/2026-10-17-riu-p4.json)及 [fullscreen](verification/2026-10-17-riu-p4-fullscreen.png)、[pip](verification/2026-10-17-riu-p4-pip.png)、[窄窗](verification/2026-10-17-riu-p4-narrow.png)、[历史](verification/2026-10-17-riu-p4-history.png)。安装器窗口的可访问性树确认停留安装选项页；原生截图受其他前台全屏窗口影响而不可用，没有按该截图发送坐标输入，也未点击安装。

主题 fixture 文字/背景对比度亮/暗分别 **14.71:1 / 16.31:1**。这是给定样例的测量，第三方组件仍需正确使用 host styles；不能由它推导任意外部 UI 都有合格对比度。

真实外部流程使用隔离配置与合成“读取当前时间”提示，复制已配置模型的必要凭据，仅发往其原端点，不修改用户当前配置，也不把凭据写入公开证据。实际尝试：OpenCode `nemotron-3.5-lightning-free` **403**（服务拒绝该客户端）；SenseNova `sensenova-6.7-flash-lite` **404 model is not found**；ModelScope `ZhipuAI/GLM-5` **400 no provider supported**；Mistral `devstral-latest` **429 rate limit**；Z.AI `GLM-4.6V-Flash` **429 overload/rate limit**。全部保持 **unverified**，本地 loopback/官方本地 stdio 的通过不能替代它。真实模型→生成 HTML 的实时流程也未验证。

验收过程中查出的实际产品问题已修复：位置移动重载 iframe、live→历史重复运行实例、语言更新重建 iframe、跨进程 Escape 无效、Workbench 窄窗遮挡/原页签未恢复、浏览器缓存丢失展示偏好，以及完整偏好广播用旧 inspectorOpen 覆盖新键盘操作。早期脚本失败也保留：并行 GUI 争用单实例、过早操作未选会话、关闭 iframe 后仍用 iframe 定位“展开”、将源码里的静态标记误作私有运行时数据。P2 旧夹具把 RPC ID 当跨重启操作 ID；本轮改用已有 `reverie/call-tool` 的显式 `callId` 后验证 unknown 不重放，标准 MCP 请求继续按实例命名空间隔离。没有改执行器、审批、核心安全边界来迁就测试。

复现命令在仓库根运行，Desktop build/test 在其子目录运行，所有 `--output` 使用新的仓库内目录，GUI 测试必须顺序执行：

```powershell
$env:PYTHONPATH='G:/Reverie/Reverie-Cli/ReverieCli-py'
& ./ReverieCli-py/venv/Scripts/python.exe -m pytest -q -c ReverieCli-py/pytest.ini ReverieCli-py/tests
python scripts/verification/riu_p4_electron.py --exe ReverieCli-ui/release/win-unpacked/ReverieUI.exe --output .runtime/riu-p4/new-p4-run --samples 20
python scripts/verification/riu_p2_electron.py --exe ReverieCli-ui/release/win-unpacked/ReverieUI.exe --output .runtime/riu-p4/new-p2-run
python scripts/verification/riu_p3_electron.py --exe ReverieCli-ui/release/win-unpacked/ReverieUI.exe --sdk-root .runtime/riu-p3-sdk --output .runtime/riu-p4/new-p3-run
python scripts/verification/riu_p3_artifacts.py --module tools.render_view --module agent.system_prompt --output .runtime/riu-p4/new-artifacts.json
python scripts/verification/check_docs.py
# ReverieCli-ui: npm test; npm run typecheck; npm run build; npm run dist:win
# Final carrier rebuild: npx electron-builder --win nsis --x64 --prepackaged release/win-unpacked
# Then: node scripts/build-portable.mjs
```

后续按顺序处理：由提示词改动所属工作确认 Writer guardrails 的正确契约并恢复全量绿；提供可用的已授权模型后重跑真实流程；在干净 Windows 用户/VM 完整安装、运行、卸载并检查 PATH/快捷方式；补原生 IME/屏幕阅读器与 Linux/macOS。MCP 断连后只保留快照，原连接回收后的回调拒绝且不自动重连/重放；联网 CSP、partial/tool-cancelled、全部内容模态与完整宿主扩展仍属单独验收范围。

<a id="riu-p3-interop-2026-10-16"></a>

### 2026-10-16 — Intelligent UI P3 MCP Apps 固定范围互操作

实施前重新读取规格引用的官方 [UI](https://developers.openai.com/plugins/build/chatgpt-ui)、[quickstart](https://developers.openai.com/plugins/build/app-quickstart)、[reference](https://developers.openai.com/plugins/reference) 全文，对照 ext-apps `2.0.3` / UI 协议 `2026-01-26`。测试的 manifest 与 lockfile 固定在 [fixture 目录](../scripts/verification/fixtures/mcp-apps/README.md)，实际安装的 MCP 包版本、integrity 和原始官方文件 SHA-256 均记录在 [结构化证据](verification/2026-10-16-riu-p3.json)。SDK 是契约与验证依赖；宿主直接实现声明范围内的标准 JSON-RPC，不修改组件或注入专有适配器。核心 transport 请求 `2025-06-18`，接受 `2025-06-18` / `2025-11-25` 并固定协商值；真实官方 stdio 服务本次协商的是 `2025-06-18`。

`mcp.py` 目录保留工具 UI metadata/visibility；资源层检查单个自包含 `ui://` HTML、标准 MIME、请求的 CSP/permissions 与宿主实际空授权，以服务器配置摘要、连接 nonce、URI、内容 hash 和策略构成缓存身份。结果格式化与动态工具只把公开 `content` / `structuredContent` 交给模型；私有结果 `_meta` 放在可服务目录之外，经宿主给组件。app-only 工具不进模型 schema、catalog/search/list，模型猜名执行也被拒绝。标准资源指针优先，`openai/outputTemplate` 仅为资源别名。

当前 profile 为 `offline-server-tools-v1`。支持标准 initialize/initialized、就绪后的 tool-input/tool-result、原服务器原连接的 `tools/call`、文本 `ui/message` 建议、text/JSON model-context、有限 inline 高度及标准销毁握手。标准组件无需 capability/sessionId/`riu/*` 字段；宿主绑定 source Window、实例租约、会话和 revision。回调继续通过原 coordinator、worker、executor、security_policy、permission_review、审批归属及会话锁；Writer 模式拒绝 MCP 回调，当前 app visibility/模式与最初 allowlist 取交集。组件自报 user-gesture 不启动模型，宿主按钮才发送正常追问。完整[支持 / 拒绝 / 未验证矩阵](INTELLIGENT_UI_SPEC.md#p3-固定兼容-profileoffline-server-tools-v1)保留每项边界。

最终验证为 Windows x64 / Electron `41.2.1` / UI 与核心 `2.5.0`，目录包构建 ID **`726514e3746dd726`**（UTC `2026-10-17T01:09:56.566Z`，纽约当地仍为 10 月 16 日）。`npm run pack` 重建 PyInstaller ui-onedir 内核，最后的 MCP 透明画布修复再运行 `npm run build` 与 `npx electron-builder --dir`。实际产物为 `ReverieCli-ui/release/win-unpacked/ReverieUI.exe`、内置 `reverie.exe` 和 `resources/app.asar`；[包内核对记录](verification/2026-10-16-riu-p3-artifacts.json)包含三者字节数与 SHA-256，验收时 7 个关键冻结 Python 模块与当前源码编译对象相同，69 个 UI 编译文件与 ASAR 内容逐字节一致。不能用源码检查或旧安装器替代此包的结果。

验收后的严格复核发现编译目录 `reverie-build.json` 于 UTC `01:16:51.706` 重新生成（ID `5c37394f6117ae10`）；因此后一次全文件比较为 false。单独核实 EXE/内核/ASAR 的 SHA-256 均未变化，7 个冻结模块与其余 68 个编译文件仍一致；差异只有构建标识的 id/builtAt。原始 69/69 记录对应验收时刻，后次差异另存于结构化证据 `post_acceptance_recheck`，未覆盖生成文件来消除差异。实际跑过互操作与隔离探针的包仍为 `726514e3746dd726`。

| 检查 | 本次实际结果 |
| --- | --- |
| Python 全量 | `python -m pytest tests -q -o faulthandler_timeout=120`：**2020 通过、2 跳过**，743.50 秒，退出码 0；慢测试打印过诊断线程栈，未中止测试；最终结果来自完整结束的运行 |
| Desktop 全量 | `npm test`：**370 通过、1 跳过**，51 文件通过 / 1 文件跳过，101.37 秒 |
| 定向回归 | Python MCP/回调 guard **59 通过**；最后的 lifecycle/画布定向测试 **14 通过**，不与全量数字相加 |
| 类型与构建 | `npm run typecheck`（1032 translations / 82 templates、两个 tsconfig）、renderer/Electron 构建、内核构建与目录打包通过 |
| 文档与差异 | 默认文档检查 31 份 / 655 个本地链接、fixture README 2 个本地链接均无错误；`git diff --check` 通过 |
| 原版标准示例与负例 | 最终包真实 GUI + loopback 模型 + 官方 stdio 服务，**26/26**，见[互操作原始报告](verification/2026-10-16-riu-p3-interop.json) |
| 打包隔离探针 | **36/36 检查条目通过**，包含 34 项必选门禁，`evaluation.passed=true`；见[隔离原始报告](verification/2026-10-16-riu-p3-isolation.json)。洪泛、死循环期间及销毁后的宿主 ping、销毁本次采样各 1 ms，不作普遍性能承诺 |

官方 `@modelcontextprotocol/server-basic-vanillajs@2.0.3` 的组件源码与发布 HTML 均未修改；实际存储的 HTML 与安装包逐字节相同，217,951 字节，SHA-256 `bd332aada2a5aff326101e9069840bf62fb6b9eaad413496e655b09d735a5e53`。真实 GUI 完成握手、按序输入/结果通知、工具回调审批允许与拒绝、消息建议和销毁 ack；[原样示例截图](verification/2026-10-16-riu-p3-official.png)。标准透明组件由宿主背景承载，本次实际文字对比度 16.40:1；未据此宣称全面可访问性认证。

独立失败/恶意 fixtures 验证 app-only 写操作经审批只执行一次，重复 ID 不重放；model-only 工具从 UI 调用在审批前被拒，未知方法给明确 JSON-RPC 错误。私有 `_meta` 只在组件可见，在全部 loopback 模型请求中均不存在；app-only 描述同样不存在。model-context 作为带来源的不可信 user 数据进入下一轮且不自动发起请求。缺资源、错误 MIME、URI 不符、请求网络 CSP、超大 HTML 五种 UI 失败，模型与用户仍取得服务器原文本结果；别名资源也实际显示。[边界截图](verification/2026-10-16-riu-p3-boundaries.png)与原始请求、审批日志、副作用和截图保存在 `.runtime/riu-p3/packaged-final-sequential/`，复现脚本为 `scripts/verification/riu_p3_electron.py`。

较早失败不计入通过：验证脚本曾误用 UI IPC hello，后来改为直连打包内核 SDK 而未增加 UI action；实际查出并修复了 MCP 历史未恢复视图、标准 MIME 被存储层拒绝，以及透明暗色组件落在白色 iframe 背景的缺陷；折叠活动导致的文本观测错误改为同时检查工具结果和用户可见文本。GUI 与探针并发会竞争 Electron 单实例互斥，最终验收分别顺序运行。旧包和旧源码的通过数未移作当前验收。

限制保持明确：空闲工作内核目前 30 秒后可被回收，旧 MCP 连接、重启或断连后的回调拒绝，须重新调用工具取得新绑定，不自动重连或重放。收起/组件主动销毁等待 ack 最多 500 ms，强制卸载/终止进程只能尽力通知，执行权限立即撤销。HTTP/SSE UI、实际核心协议 `2025-11-25` 服务、外部真实模型/服务、OAuth、Linux/macOS、安装器/便携版验收未验证；动态 hostContext、partial/tool-cancelled、展示模式与全部内容模态仍未实现。没有声明完整 `window.openai` 或 Plugin Extensions 兼容。本次未提交、未推送，保留其他已有工作树改动。

<a id="riu-p2-interactions-2026-10-15"></a>

### 2026-10-15 — Intelligent UI P2 交互控制、审批与状态恢复

在既有未提交的 P0/P1/P2 草稿上补齐 P2；未提交、未推送。交互方法与形状固定对照 ext-apps v1.2.0 / 协议 2026-01-26，仅承载本地离线生成视图。主进程把实例租约绑定到 project/session/view/revision，受限 iframe 通道验证 source、能力、握手、请求 ID、大小/速率/并发和超时。切换、卸载和重载撤销实例；迟到响应丢弃，重复请求不再次执行。第三方 MCP 回调因 P3 的 server/generation/app visibility 绑定尚未实现而拒绝，不声明 serverTools 或完整 MCP Apps 兼容。

工具回调复用普通 runPrompt 的 coordinator、worker pool、checkout/session 锁、RunJournal、ToolExecutor、security_policy、permission_review 和审批 worker 归属；删除草稿中 admin bridge 的独立回调通道。组件自报的 user-gesture 不作为授权证据，工具在原有 gate 中逐次等待宿主确认。ui/message 仅在宿主显示建议，用户点击“发送追问”才调用正常 runPrompt。私有 JSON 状态按内容 revision 保存并使用 baseRevision 冲突检查；状态、摘要、写前收据位于 HTML 可服务目录之外。模型只临时取得带 view/revision 来源、合计不超过 8 KiB 的不可信 user 摘要，不把其提升为 system 或持久历史。

写操作先持久化 unknown 收据再执行；成功、拒绝和 Stop 都消耗操作 ID。真实崩溃测试在 command_exec 已写入一行副作用之后强制终止整棵验证应用进程树，重新启动读取收据和私有筛选状态；再次点击同一操作收到 unknown 错误，没有第二行副作用。fork 复制可见版本与私有状态且重新绑定会话，不复制操作收据；rewind 隐藏后续引用，删除 fork 保留原会话。真实审批日志中的 run_id/session_id 与执行 worker 的持久运行记录/PID 对应。

最终验证包构建 ID 为 `6841218dffec623d`，包内 main/controller/build metadata 与编译输出逐字节核对；完整交互复现脚本为 `scripts/verification/riu_p2_electron.py`。当前验证结果：Python 全量 `python -m pytest tests -q` **1941 通过、2 跳过**（643.73 秒）；RIU focused **69 通过、1 跳过**；Desktop `npm test` **363 通过、1 跳过**（51 文件）。类型检查、i18n（1032 translations / 82 templates）、renderer/Electron 构建、PyInstaller ui-onedir 内核与独立目录打包通过。最后的权限/回调复核为 **81 通过**，最终交互 focused 为 **32 通过**。实际 packaged Electron 41.2.1 的 loopback fixture **24/24**，打包隔离探针 **34/34**（同步循环/洪泛中宿主 ping、销毁及销毁后 ping 本次各 1 ms）。这是一台 Windows 主机的样本，不作跨平台或普遍性能承诺。

初次生成时 FastContext 对工作区 HTML 源文件的检索片段确实进入过模型输入，此成本保留在 loopback 请求证据中，不宣称生成 HTML 零 token。后续追问实际只补充选中摘要，没有重新附带模板标记；私有状态标记在所有模型请求中均未出现。此处验证的是给定 fixture 的后续请求边界，不宣称任意用户查询都不会显式读取工作区 HTML。

原始模型请求、运行/审批 journal、截图、配置、crash 前后的副作用及全部尝试保存在仓库 `.runtime/riu-p2/`。较早的失败尝试未计入通过；包括修复前四项重放/陈旧状态回归、误删初始化字段后恢复、构建/打包重叠得到不完整 PIL 的验证包，以及脚本的过期 frame、异步等待和恢复收据显示检查。最终结果与文件哈希集中于 [P2 结构化证据](verification/2026-10-15-riu-p2.json)，隔离原始结果见 [打包探针](verification/2026-10-15-riu-p2-isolation.json)。

未完成项继续保持未完成：外部真实模型/服务、第三方不改代码 MCP 示例、完整 UI metadata/_meta 分流与 Apps 生命周期（P3）、动态主题/尺寸/展示模式和广泛可访问性/性能（P4）、Linux/macOS、安装器/便携发布流程。此次只生成验证包，未执行发布。

<a id="riu-p1-pipeline-2026-10-11"></a>

### 2026-10-11 — Intelligent UI P1 render_view 流水线与视图时间线

在已验证的 P0 可信宿主之上实现 `docs/INTELLIGENT_UI_SPEC.md` 的 P1：注册 `artifact_path` 的 `render_view` 工具、受限产物存储（`ViewStore`）、manifest schema、`view_ready` / `view_error` 事件、能力探测，以及视图时间线的 revision / fork / rewind / delete。先写能失败的 focused 测试，再实现最小宿主与受限通道；全过程不关闭 webSecurity、不放宽宿主 script-src、不把视图 HTML 注入主 DOM。

身份由内核绑定：会话 / 轮次 / 工具调用 id 从内核上下文读取，绝不取自模型参数；视图在产物落盘并提交到 `ViewStore` 之后才发出 `view_ready`（先持久化后显示）。模型文本里伪造的 handle 形字符串不会凭空生成视图行——渲染层只认由真实 `render_view` 工具结果铸出的行，再经 `ViewStore` 解引用。解析后的渲染层引用是白名单：只有注册器给出的不透明 `reverie-view:` url 与 policyId，绝不含文件系统路径。

证据按两条真实链路取得，不沿用历史数字：Python e2e 在两个强制 fixture（`parameter_simulator.html`、`data_chart.html`）上以真实 `RenderViewTool`、`ViewStore` 与桥接分发打通 工具→存储→宿主解引用→重启/fork/rewind/delete→TUI 降级；渲染层 pipeline 测试重建 行→行记录→解析引用。关键属性：工具结果与历史恢复后的模型请求都不含 HTML 字节或路径——fixture 的 `<script>` 标记在结果、事件、解析行、解析引用与恢复后的转录中均不出现。**不宣称 HTML 生成零 token**；此处只验证 HTML 不被重新加入模型请求。

测试与回归（当前测量，非历史累计，均在对应工作目录运行）：RIU focused Python **41 通过 / 1 跳过**（`tests/test_riu_views.py`、`test_riu_render_view.py`、`test_riu_bridge_views.py`、`test_riu_views_e2e.py`）；渲染层 pipeline **6 通过**（`src/view-pipeline.test.ts`）。桌面全量 `npm test` **342 通过 / 1 跳过**（48 文件）；`npm run typecheck`（i18n + 渲染层与 Electron 两个 tsconfig）通过。Python 全量 **1912 通过 / 2 跳过**；非游戏完成度门禁 `test_modules_do_not_silently_swallow_broad_exceptions` 通过——两处 RIU except（`render_view._emit`、agent 每轮 provenance 铸造）改走 `report_suppressed_exception` 后不再静默，记录到 logger `reverie.recovery`。另有 1 项非本任务失败 `test_rats_runtime.py::test_unreachable_supported_provider_fast_fails_and_remains_hidden`（全量 CPU 负载下 provider 快速失败预算 <1.0s 被 1.108s 超出），隔离重跑 2.29s 通过，判为与 RIU 无关的环境时序抖动，不追绿。

构建与打包：`npm run build`（tsc + vite + build-info）通过，构建 ID `03c991ccd69a9a3c`。`npm run dist:win`（PyInstaller 内核 + `electron-builder --win nsis --x64` + 便携版）产出 `release/win-unpacked/ReverieUI.exe`（223,114,752 字节）、内置 `reverie.exe`（14,116,343 字节）、NSIS 安装包 `Reverie-Setup-2.5.0-x64.exe`（441,172,175 字节，sha256 `99259a8b781fe331b17fb8362c73059a8bbba9bafe844d9b274d284920c1a8ff`）与便携版 `dist/Reverie-Portable-2.5.0-x64.exe`（501,867,890 字节，sha256 `beb9a93670237a7edcf99b7350c06555e742254fe1a1da5e4db79ebda57d2986`）。P1 代码已编入该打包程序；在真实包上重跑 P0 隔离探针 `--riu-isolation-probe` 得 **34/34 通过**（`evaluation.passed=true`，容器 sandboxed-iframe，失败 0），确认接入 P1 后视图宿主仍隔离且可响应。结构化结果见 [P1 流水线证据](verification/2026-10-11-riu-p1-pipeline.json)。

边界与范围：仅 Windows x64 实测，Linux/macOS **未验证**；**未验证**在运行中的打包 GUI 会话里由真实模型驱动的实时视图生成（真实模型写 HTML、用户看到渲染面板）——工具→存储→宿主→重启/fork/rewind/delete→TUI 链由上述 Python e2e 与渲染层重建证明，但未无头跑通一次实机模型会话；网络、原生 IME 与屏幕阅读器路径**未验证**。本次未提交、未推送，预先存在的未提交改动均保留。

<a id="riu-p0-isolation-2026-10-11"></a>

### 2026-10-11 — Intelligent UI P0 可信宿主隔离验证

按 `docs/INTELLIGENT_UI_SPEC.md` 的 P0 实施并验证生成式 UI 的可信宿主，暂不实现其余 RIU。承载方式为自定义特权协议 `reverie-view:`（standard+secure，不支持 fetch、不开 CORS、不绕过 CSP）配合 `allow-scripts` 的 sandbox iframe；该沙箱产生不透明来源（`window.origin` 序列化为 "null"），Chromium 站点隔离把视图帧放入独立进程。先写能失败的 focused 测试，再实现最小宿主与受限通道；全过程不关闭 webSecurity、不放宽宿主 script-src、不把视图 HTML 注入主 DOM。

容器选择依据实测：sandbox iframe 已满足 P0 的全部隔离与性能门禁，故本阶段不改用独立 WebContents。视图帧的权限请求一律拒绝，`reverie-view:` 的下载一律取消，帧内导航只允许绑定入口的首次提交。

平台与构建：Windows x64、Electron 41.2.1，构建 ID `5f3644816919bb5a`。探针在真实打包程序 `release/win-unpacked/ReverieUI.exe` 上以 `--riu-isolation-probe` 运行，加载仓库内离线 HTML fixture（benign/hostile/flood/loop），由视图帧内与可信主进程分别判定。结构化结果见 [隔离探针证据](verification/2026-10-11-riu-p0-isolation.json)。

隔离探针 **34/34 通过**（门禁集合，`evaluation.passed=true`）。覆盖：Node/preload/父 DOM/顶层窗口均不可达；不透明来源与 DOM 存储、cookie 被拒；路径穿越（原始 `..` 经 WHATWG 归一化后 404、百分号编码 `%2e%2e%2f` 被处理器拒为 400）、外来 token、脚本 MIME 不可映射、未绑定目录、下载、远程子资源、window.open、表单提交、fetch、WebSocket 均被阻断；视图帧权限请求授予数为 0；伪造桥来源、缺能力、过期实例、不支持方法、超大消息均被拒；洪泛被限速（accepted=64，rateLimited≈2938）。宿主剪贴板仍可用。

P0 核心主张在实机得到证明：在无限同步循环与消息洪泛下，宿主对主进程 ping 的最坏响应为 7ms（循环）与 3ms（洪泛，预算均 1500ms），循环期间聊天输入框仍可用；视图可被销毁、其进程确认退出，拆除耗时 32ms、拆除后 ping 2ms（预算 3000/1500ms）。

诚实说明：首轮探针为 30/34，4 项失败经核查均为断言把正确的安全行为判错，而非真实缺陷——不透明来源下 `document.cookie` 读取抛 SecurityError 即等于被拒；`session.fetch` 对原始 `..` 归一化得 404、对编码 `..` 得 400，两者都未泄露文件；WebSocket 构造函数不同步抛错但连接从不建立；`document.origin` 是已废弃别名、此处为 undefined，`window.origin==="null"` 才是不透明来源的权威信号。据此把断言改为验证真实属性后，重新在打包程序上运行得 34/34，未复制任何历史通过数。

桌面回归 **299 通过、1 跳过**；`npm run typecheck`（i18n、渲染层与 Electron 两个 tsconfig）通过；`npm run build` 与 `electron-builder --dir` 重新打包并签名通过，随后重建签名版 NSIS 安装包。未改动任何 Python 源码，故本轮未重跑 Python 全量（不沿用历史数字作为本次结果）。

边界与范围：仅 Windows 实测，Linux/macOS **未验证**；仅实现并验证 P0 可信宿主，`render_view`、持久产物、时间线、回调、私有状态等 P1+ 均未实现。探针与受限通道为验证路径，受 `--riu-isolation-probe` 开关控制，不进入普通应用流程。隔离产物保存在仓库内 `docs/verification/`。本次未提交、未推送。

<a id="desktop-memory-2026-10-10"></a>

### 2026-10-10 — 桌面启动内存、模型目录与独立 EXE

用户确认问题发生在 GUI 启动时。检查发现管理内核之外还会启动一个模型预热内核，两者均会自动索引；池中的聊天内核在空闲后没有释放时限。本次取消启动预热，把自动索引推迟到实际聊天或显式索引，并限定最多一个空闲工作内核保留 30 秒。活动聊天仍隔离，最多四个并发工作内核。

Windows x64、Electron 41.2.1，同一机器使用隔离配置和编译后的桌面程序，对可用输入框之后的进程树采样。仓库场景使用相同的本地测试模型配置、开启自动索引，测试地址为不可用的回环端口，不向外部模型服务发送请求：

| 场景 | 改动前工作集峰值 | 改动后工作集峰值 | 改动前私有内存峰值 | 改动后私有内存峰值 |
| --- | --- | --- | --- | --- |
| 空工作区、无模型 | 504.94 MiB | 458.12 MiB | 374.81 MiB | 357.01 MiB |
| 当前仓库、配置模型、自动索引 | 958.01 MiB | 522.17 MiB | 770.81 MiB | 429.84 MiB |

仓库场景工作集峰值下降 45.5%，私有内存峰值下降 44.2%；两个内核变为一个。工作集按进程相加，会重复计入共享页；私有内存是提交量，两者都不等于机器上唯一物理 RAM 页总数。这是启动后 30 秒的单次对比，不包含启动前几秒的瞬时峰值、长期运行、超大历史、真实模型服务和其他系统的内存保证；没有据此宣称所有内存问题已消除。空工作区改动后采样为 15 秒，不与仓库场景混成同一次测试。

另用本地 HTTP 模型替身实际完成两次桌面聊天：启动时一个内核，运行后两个，两次复用同一工作内核，空闲 35 秒后恢复一个。六项池测试检查释放、计时取消、活动运行、并发、容量和关闭竞争。GUI 通过 Playwright/CDP 检查 About 链接，以及深色 / 浅色、背景开关、活动 / 历史状态中思考区、标题与内容的透明背景。

独立 `reverie.exe` 仅复制一个文件到测试目录，即可完成版本查询、`--kernel-info` 和 SDK ready/shutdown；本地回环协议还验证了读取文件、创建同内容文件和执行命令三个实际工具调用。单 EXE 内含依赖并临时解包，不要求安装 Python 或复制外置 `reverie-runtime`。桌面内部包保持 `ui-onedir`，两者共用核心源码。结构化结果见 [内存与打包证据](verification/2026-10-10-desktop-memory.json)。

最终 CLI 为 328,898,686 字节；GUI 便携版为 486,568,195 字节，桌面构建 ID `a6754fa8bae70a4a`。便携版在独立目录首次解包后 19.45 秒出现可用输入框；SDK 会话显示、About 链接和八种透明背景组合通过。这是一次本地主机样本，不作为普遍启动时间承诺；未验收安装器流程。最终产物哈希保存在上述结构化记录中。

模型目录依据 2026-10-10 官方 Agnes 文档和 ModelScope 推理目录 / 模型卡更新；新配置采用当前默认模型，旧配置保留已选模型。Flash Max 使用嵌套 `chat_template_kwargs`，避免把旧预算参数用于新模型。新增 DeepSeek 条目使用宿主默认思考设置，未将本地参数测试称为真实账户验收。

完整桌面回归为 284 通过、1 跳过；类型检查与构建通过。最终 Python 全量为 **1872 通过、1 跳过**，耗时 422.03 秒。工作树中另有未完成的 Intelligent UI 文件，隔离检出只叠加本次改动进行桌面构建与检查。首轮 Python 全量在 G 盘耗尽后出现文件系统失败，没有计作通过；相关生成资源与失败测试数据保留并迁移到 C 盘。随后置于用户目录内的临时工作区触发祖先目录技能发现，导致 5 个技能断言失败（1867 通过、1 跳过）；迁到用户目录之外后相关 19 项及最终全量均通过，没有为本机环境修改产品技能发现逻辑。最终临时目录为 `C:/ReverieVerification-20261010/full-final`。

<a id="publish-validation-2026-10-09"></a>

### 2026-10-09–10 — 工作树整理与提交前验证

本次将已有代码和文档按五个主题整理为提交。代码基线为 `01727e5574ad3e62a90cd949177e0e4ca0377699`，文档随后单独提交；没有改变 2.5.0 版本号或实现 Intelligent UI。原有三笔本地提交继续保留，提交前完整文件备份及测试原始输出位于 `.runtime/publish-20261009/`。

| 检查 | 本次结果与解释 |
| --- | --- |
| Python 全量回归 | 项目虚拟环境、`ReverieCli-py` 目录下运行：**1864 passed / 1 failed / 1 skipped**。唯一失败是发布测试仍要求旧版单 EXE 文案；源码已改为 ZIP 加运行目录 |
| 失败修正与重测 | 更新该测试，检查 ZIP 同时打包 EXE 与 runtime，并检查下载链接。整个 `test_tooling_upgrades.py` 重测 **61 passed**；没有再次运行全量，也不将两次数字相加 |
| Desktop 回归 | **284 passed / 1 skipped**；真实外部 Engine RTP 集成未配置，保持跳过 |
| 类型与依赖 | `npm run typecheck`、`pip check`、`check_dependency_pins.py`、`setup.py check` 通过 |
| 源码 SDK | 隔离数据目录验证 JSONL ready/shutdown，正常退出 |
| 编译 CLI | `build.bat --reuse-venv --no-pause --test-exe` 通过；本地 HTTP fixture 经真实编译 SDK 执行读文件、创建副本、PowerShell 命令，工具结果和会话保存通过 |
| 打包 GUI | 构建 ID **3734a5c81d5e4e52**；首次隔离启动及重启、API 兼容开关保存/恢复、浅色/深色切换和正常退出通过；首次就绪 16.959 秒、重启 1.625 秒，仅为本次单次样本 |
| Windows 分发包 | NSIS 安装包 441,229,783 字节；便携版 501,967,569 字节。原构建在便携版阶段中断，10 月 10 日独立重跑 `node scripts/build-portable.mjs`，退出码 0；文件哈希见结构化记录 |
| Skills Git 一致性 | 22 个清单资源的 Git blob 和 Windows 检出字节均匹配哈希；限定在这批资源中保留 CRLF 与原始空白，避免 Unix CI 换行转换后校验失败 |
| 文档与 Skills 定向回归 | `test_documentation_links.py` 与 `test_design_skills.py` 合计 **4 passed**；25 份迁移正文及 762 行历史 Changelog 内容完整性复核通过，Markdown 文档保持 22 份 |

Python 跳过项是当前主机无法创建符号链接的资源逃逸测试。最初使用系统 Python 从仓库根目录运行时导入了另一个项目的同名 `reverie` 包；该次 90 个收集错误属于错误测试环境，以上结果来自正确虚拟环境的重新执行。没有修改其他项目或用户配置。

文档迁移完整性、链接统计、构建产物哈希及命令结果见 [结构化记录](verification/2026-10-09-publish-validation.json)。本地只连接 HTTP fixture，没有重新验证真实模型供应商、外部 Engine RTP、Linux/macOS 或长期运行。NSIS 安装流程与便携版首次解压不属于本次 GUI 检查；安装包生成成功不能代替安装/首次启动验收。GitHub Actions 的结果以推送后对应提交的运行状态为准。

### 2026-10-08 — 文档整合与 RIU 静态审查

本次只完成官方资料核实、当前源码阅读、开发规格与文档系统整理。没有实现或打包 RIU，没有重跑完整 Python/Desktop 产品回归，也没有把下方历史数字当成本次运行结果。

- `docs/` Markdown 从 44 份变为 22 份；25 份旧文档（含 Python 子项目的一份）完整迁入两份历史文件。各迁移正文的 SHA-256 校验通过，原内容备份保留在 `.runtime/docs-20261008/before/`。
- Changelog 原有 42 个版本段落合并为 40 个唯一、按版本倒序的入口；原有 762 个非标题内容行全部保留（仅规范迁移链接和明确纠正的日期），新增早期标签基线与历史未发布草案。
- 文档检查默认覆盖 Python/Desktop/Plugins 入口；修复原检查器强制依赖被忽略的本地 `API.md`、导致普通 Git 克隆缺文件的问题。
- `python -m pytest -q -c ReverieCli-py/pytest.ini ReverieCli-py/tests/test_documentation_links.py`：**3 passed**。覆盖无本地 API 文档、迁移锚点断裂和存在本地文档时的链接错误。
- 本地文件/标题链接检查与迁移完整性校验通过。最终检查计数、迁移路径、原内容哈希、版本证据范围见 [结构化整合记录](verification/2026-10-08-documentation-consolidation.json)。链接检查不证明外部服务、自然语言事实或产品运行正确。

### 完整原文件索引

- [Reverie 非流式 API 兼容与性能验证](#reverie-cli-api-compatibility-2026-10-08) — `docs/REVERIE_CLI_API_COMPATIBILITY_2026-10-08.md`
- [Reverie Desktop UI redesign — 2026-10-07](#reverie-cli-apple-ui-redesign-2026-10-07) — `docs/REVERIE_CLI_APPLE_UI_REDESIGN_2026-10-07.md`
- [背景、窗口托盘与终端启动修复（2026-10-07）](#reverie-cli-background-startup-repairs-2026-10-07) — `docs/REVERIE_CLI_BACKGROUND_STARTUP_REPAIRS_2026-10-07.md`
- [实时上下文与 GUI 修复验证](#reverie-cli-context-gui-validation-2026-10-02) — `docs/REVERIE_CLI_CONTEXT_GUI_VALIDATION_2026-10-02.md`
- [Reverie Desktop 深入验证与本地提交记录](#reverie-cli-deep-validation-2026-10-01) — `docs/REVERIE_CLI_DEEP_VALIDATION_2026-10-01.md`
- [Reverie CLI 功能与文档审查（2026-10-05）](#reverie-cli-feature-audit-2026-10-05) — `docs/REVERIE_CLI_FEATURE_AUDIT_2026-10-05.md`
- [Reverie CLI 功能复审附录：MCP 客户端边界（2026-10-05）](#reverie-cli-feature-audit-addendum-2026-10-05) — `docs/REVERIE_CLI_FEATURE_AUDIT_ADDENDUM_2026-10-05.md`
- [Reverie CLI 功能缺口修复与验证（2026-10-05）](#reverie-cli-feature-repairs-2026-10-05) — `docs/REVERIE_CLI_FEATURE_REPAIRS_2026-10-05.md`
- [Reverie Desktop S01–S21 实施与验收记录](#reverie-cli-implementation-report-2026-09-30) — `docs/REVERIE_CLI_IMPLEMENTATION_REPORT_2026-09-30.md`
- [JDW / Claude Messages 兼容性检查（2026-10-04）](#reverie-cli-jdw-compatibility-2026-10-04) — `docs/REVERIE_CLI_JDW_COMPATIBILITY_2026-10-04.md`
- [Reverie CLI 功能复审附录：跨平台身份与语言覆盖（2026-10-05）](#reverie-cli-platform-language-audit-2026-10-05) — `docs/REVERIE_CLI_PLATFORM_LANGUAGE_AUDIT_2026-10-05.md`
- [Reverie CLI 请求、个人资料与 MCP 修复验证（2026-10-05）](#reverie-cli-request-profile-repairs-2026-10-05) — `docs/REVERIE_CLI_REQUEST_PROFILE_REPAIRS_2026-10-05.md`
- [对话输出模式与交互优化](#reverie-cli-streaming-ux-validation-2026-10-03) — `docs/REVERIE_CLI_STREAMING_UX_VALIDATION_2026-10-03.md`
- [Tokens、上下文及输入区复审](#reverie-cli-token-context-review-2026-10-02) — `docs/REVERIE_CLI_TOKEN_CONTEXT_REVIEW_2026-10-02.md`
- [Tokens 用量统计：API 优先](#reverie-cli-token-usage-validation-2026-10-02) — `docs/REVERIE_CLI_TOKEN_USAGE_VALIDATION_2026-10-02.md`
- [Reverie UI 修复与实际验证（2026-10-04）](#reverie-cli-ui-repair-2026-10-04) — `docs/REVERIE_CLI_UI_REPAIR_2026-10-04.md`
- [工作面板、对话显示与请求启动修复](#reverie-cli-workbench-repairs-2026-10-06) — `docs/REVERIE_CLI_WORKBENCH_REPAIRS_2026-10-06.md`
- [Skills 系统检查记录](#skills-audit) — `docs/SKILLS_AUDIT.md`
- [Context Engine Retrieval Results](#context-engine-benchmark) — `docs/CONTEXT_ENGINE_BENCHMARK.md`
- [Chat performance and real Agnes task verification](#2026-09-27-chat-performance) — `docs/verification/2026-09-27-chat-performance.md`
- [Memory runtime review — 2026-09-26](#memory-runtime-review-2026-09-26) — `ReverieCli-py/docs/memory-runtime-review-2026-09-26.md`

---

<a id="reverie-cli-api-compatibility-2026-10-08"></a>

<a id="reverie-cli-api-compatibility-2026-10-08--reverie-非流式-api-兼容与性能验证"></a>

## Reverie 非流式 API 兼容与性能验证

> 原文件：`docs/REVERIE_CLI_API_COMPATIBILITY_2026-10-08.md`。以下为当时的记录；日期、测试数字、限制与旧实施提示词均保留，不代表本次重新验收。


完成日期：2026-10-08。测试和实现始于 2026-10-07。

新增「广泛 API 兼容」实验性开关，默认关闭。它位于 **设置 → 通用**，紧邻思考工具，内核分类同为 `Reasoning`。Chat 页面没有新增开关。CLI/TUI 同步使用此设置，也可通过 `/setting api-compatibility on|off` 切换。

<a id="reverie-cli-api-compatibility-2026-10-08--jdw-实际结果"></a>

### JDW 实际结果

凭据只从 `JUSTDOWORK_API_KEY` 读取；测试记录和报告不包含真实 Key。测试模型为 JDW 模型列表中实际公布的 `claude-opus-4-8`，地址为 `https://api.justwoker.icu/v1`。

| 调用方式 | 实际结果 |
| --- | --- |
| OpenAI Chat Completions，原生或文本工具请求 | Cloudflare HTTP 403 |
| Anthropic Messages，普通非流式文本 | HTTP 200，有文本 |
| Anthropic Messages，原生工具定义和强制工具选择 | 没有产生可执行的 Reverie 工具调用 |
| Anthropic Messages，新兼容模式，真实 ReverieAgent | 连续三轮成功读取文件、写入文件、执行命令并保存工具历史 |
| 编译后的 CLI，同一 JDW 模型 | 两次返回 HTTP 503 `model_not_found`，提示模型没有可用通道 |
| 编译结束后的短文本健康探测 | 仍返回相同 HTTP 503 |
| 编译后的 CLI，本地 HTTP 协议验证 | 四次非流式请求，三个真实工具完整执行，最终结果和历史均正确 |

三个真实模型成功样本分别耗时 **27.780、25.989、30.444 秒**，每轮三次 API 请求。每轮都实际读取随机内容的 `source.txt`，用 `str_replace_editor` 创建内容完全相同的 `copy.txt`，并通过 `command_exec` 运行 `Write-Output reverie-command-ok`。断言同时检查文件内容、实际命令标准输出、最终模型回答和已保存的工具消息。请求携带完整 Reverie 工作上下文和 28 个当前可见工具的参数定义。

后续编译版的真实调用受到当前 JDW 通道故障阻挡。因此，**真实模型的源码工具流程已验证；当前编译版对 JDW 的完整工具流程尚未验证成功**。本地 HTTP 验证证明编译产物能够完成协议和工具流程，并不能替代服务端恢复后的真实模型验证。503、403 和原生工具缺失是分别记录的故障。

<a id="reverie-cli-api-compatibility-2026-10-08--使用方法"></a>

### 使用方法

1. 在 **设置 → 模型与提供商** 编辑 JDW，将 **API 请求格式** 选择为 **Anthropic**；保留正确的 Base URL 和环境变量 Key。
2. 在 **设置 → 通用** 开启 **广泛 API 兼容（实验性）**。
3. 内核会使用 `stream: false`。即使全局流式响应已开启，兼容请求仍为非流式；工具开始、结果等界面事件照常显示。
4. 关闭开关即恢复原有调用路径。开关变化会重新初始化已运行的 Agent；设置会保存，并在重启后恢复。

该模式将工作区指令、完整工具参数和带角色的会话历史编码进普通用户文本。模型返回严格的 JSON 动作或最终回答，Reverie 使用现有工具执行器执行动作，并把真实结果发回模型。没有新增绕过权限的工具。无效、未知或不完整的动作不会执行；截断响应不会触发重复付费重试。

当前仅支持文本，图片和音频会在发送前明确拒绝。该开关无法修复 HTTP 403 或提供商无可用通道的 HTTP 503。Codex 和 WebGemini 登录型提供商沿用原有路径。

<a id="reverie-cli-api-compatibility-2026-10-08--性能变化"></a>

### 性能变化

- 对同一个已通过的首个请求，仅恢复完整工具主说明作为对照：请求从 **116,194 字节降到 102,864 字节，减少 11.47%**。所有工具参数定义保持相同；省去的是主说明里的重复示例和后续段落。
- 三组 30 次本地构造测量的中位数约 **6.25–6.58 毫秒**。这衡量本地编码开销，不能证明上游模型变快。
- SDK 和 Requests 路径复用连接；真实本地 HTTP 测试检查了连续工具往返使用同一 TCP 连接。系统 curl 仍通过独立进程执行。
- curl 使用标准输入传递 JSON，解决完整工作上下文超过 Windows 命令行长度上限的问题。实际大请求和取消连接回归均通过。
- CLI 继续使用 `reverie.exe` 加 `reverie-runtime` 的快速启动目录布局。压缩包只包含程序和运行目录，不包含用户配置。

新模式解决的是工具协议兼容性。失败的原生请求与成功的工具流程做的工作不同，不能把两者耗时直接当作加速比。网关报告的输入 token 数没有作为可靠计费量背书。

<a id="reverie-cli-api-compatibility-2026-10-08--编译与验证"></a>

### 编译与验证

- Python 聚焦回归：**233 通过**。涵盖七种 HTTP 传输配置、两种界面输出方式、真实文件工具、权限拒绝、历史、截断、无效 JSON、关闭兼容模式、Thinking Tool 和取消连接。
- 前端：**284 通过、1 跳过**；TypeScript 与 i18n 检查通过。
- CLI、内置桌面内核、Windows 安装包和便携版均实际编译。桌面 build ID：`b977c27ae895c3a9`。
- 编译桌面端和便携版各完成开启、退出、重启、恢复开启状态、再关闭；默认值、实验标记、分类和 Chat 无入口均经真实界面检查。四次最终退出均返回 0，无页面异常。
- CLI ZIP 实际解压后通过版本、内核信息、SDK bridge 启动与正常关闭验证。
- 测试使用项目内独立工作区、配置和进程。已有 CLI/已安装桌面端配置的 SHA-256 保持相同。没有安装覆盖用户的应用，没有 commit/push。

验证脚本最初使用了桌面未开放的 `listSettings` IPC，已改用现有 `getState`。一次附加调试器的退出得到 `0xc0000005`；该记录保留。最终先断开 CDP、让 inspector RPC 返回，再触发同一托盘菜单退出动作，四次均正常退出。没有为此修改产品代码，也没有把失败记录当作通过证据。

<a id="reverie-cli-api-compatibility-2026-10-08--产物与证据"></a>

### 产物与证据

- [完整结构化报告](verification/2026-10-08-api-compatibility.json)
- [Windows CLI ZIP](../dist/Reverie-CLI-windows-x64.zip)
- [Windows 便携版](../dist/Reverie-Portable-2.5.0-x64.exe)
- [Windows 安装包](../ReverieCli-ui/release/Reverie-Setup-2.5.0-x64.exe)
- [实际设置页截图](../result_images/api-compat-20261008/settings-light.png)

完整脱敏证据位于 `.runtime/api-compat-20261007/`：`final-compat-agent-{1,2,3}.json` 为成功的真实模型记录；`packaged-cli*-record.json` 区分编译版真实失败和本地协议通过；`post-build-health.json` 为最新服务端健康结果；`focused-final.xml` 和 `ui-tests.log` 为回归记录。`task-changes.patch` 只比较本任务开始时的源文件快照与最终实现，便于从已有未提交工作中识别此次改动。


---

<a id="reverie-cli-apple-ui-redesign-2026-10-07"></a>

<a id="reverie-cli-apple-ui-redesign-2026-10-07--reverie-desktop-ui-redesign--2026-10-07"></a>

## Reverie Desktop UI redesign — 2026-10-07

> 原文件：`docs/REVERIE_CLI_APPLE_UI_REDESIGN_2026-10-07.md`。以下为当时的记录；日期、测试数字、限制与旧实施提示词均保留，不代表本次重新验收。


The start page, desktop navigation and shared page materials have been redesigned using the user's Apple Design Skill. The welcome, real composer and four starter actions now form one composition. Light mode uses a bright canvas with a clear wallpaper detail; dark mode retains the workspace atmosphere. The original user accent, wallpaper, language and reading preferences remain available.

<a id="reverie-cli-apple-ui-redesign-2026-10-07--implementation"></a>

### Implementation

- `ReverieCli-ui/src/StartPage.tsx`: workspace identity, restrained welcome artwork and concise starter actions. Each action inserts the existing complete prompt and focuses the composer.
- `ReverieCli-ui/src/App.tsx`: grouped navigation, workspace breadcrumb, a two-line model selector and new start-page composition. The composer retains its DOM identity when the first turn replaces the welcome.
- `ReverieCli-ui/src/desktop.css`: shared materials, typography, spacing and responsive layouts across conversations, libraries, preferences and the workspace panel. Selected and shadowed Skills keep their distinct state cues. System reduced-motion, reduced-transparency and increased-contrast preferences receive specific adaptations.
- `ReverieCli-ui/electron/main.ts`: the native title bar overlay follows the new 58 px header. The overlay stays transparent, so caption button backgrounds match the title bar, including when the workspace panel is open.
- Focused tests cover all four starter prompts, English localization, composer focus and DOM identity across the first turn.

The earlier continuous-background, close-to-tray and fast CLI distribution repairs are retained. Their original evidence is recorded in `REVERIE_CLI_BACKGROUND_STARTUP_REPAIRS_2026-10-07.md`.

<a id="reverie-cli-apple-ui-redesign-2026-10-07--verification"></a>

### Verification

- `npm run typecheck`: passed, including translation key checks and both Electron and renderer TypeScript checks.
- `npm test`: **283 passed, 1 skipped**, across 41 passing test files. The skipped external RATS integration requires `RATS_ENGINE`.
- Windows CLI kernel, renderer, Electron application, NSIS installer and portable launcher were compiled and packaged. Final binary identity, checksums and runtime records are stored in `docs/verification/2026-10-07-apple-ui-redesign.json`.
- Actual Electron and portable runtime checks use an isolated project/profile under `.runtime/apple-redesign-20261007/`. Screenshots cover light/dark welcome and conversations, English, clean and wallpaper backgrounds, attachments with a long draft, preferences, tools, SubAgents, RATS/RTP, Skills, plugins, recovery and file preview.
- Native screenshots verify the caption background against the title bar. Tests also exercise minimize, maximize, tray restore, close-to-tray with a live terminal, cancelling explicit quit, and accepting explicit quit.
- The rendering stress checks include 960 × 700 and 900 × 500 test windows with a temporarily lowered test-only minimum. The product's existing native minimum remains 1080 × 700.

The main-process inspector controls only the test-owned process. File-picker and quit-dialog responses are supplied for deterministic testing; attachment import/validation, persistence, native window operations, tray callbacks, PTY state and the packaged bridge run normally. Conversation messages are local fixtures. This UI work does not establish new live-provider or external RATS integration results.

Reviewable screenshots are copied to `result_images/apple-redesign-20261007/`. Sources remain uncommitted, with the pre-existing worktree preserved.


---

<a id="reverie-cli-background-startup-repairs-2026-10-07"></a>

<a id="reverie-cli-background-startup-repairs-2026-10-07--背景窗口托盘与终端启动修复2026-10-07"></a>

## 背景、窗口托盘与终端启动修复（2026-10-07）

> 原文件：`docs/REVERIE_CLI_BACKGROUND_STARTUP_REPAIRS_2026-10-07.md`。以下为当时的记录；日期、测试数字、限制与旧实施提示词均保留，不代表本次重新验收。


消息区和输入区现在共用连续的背景遮罩，移除了消息区额外叠加的背景色。浅色主题取消固定的图片透明度和重复白色遮罩，保留用户设置的透明度、亮度与清晰的壁纸纹理。输入框仍保持可读的独立表面。

原生窗口按钮使用透明背景，随标题栏显示相同的颜色。关闭窗口默认隐藏到托盘，后台任务和用户终端继续运行；点击托盘或“显示 Reverie”恢复原窗口。“退出 Reverie”才退出，保留原有的后台任务结束确认。

Windows 终端默认使用 `reverie.exe` 与同目录的 `reverie-runtime/`，避免每次启动展开单文件 EXE。用户已确认优先快速启动并允许附带运行目录。发布流程增加 `Reverie-CLI-windows-x64.zip`，保留 `REVERIE_PYINSTALLER_MODE=onefile` 的显式构建方式。Unix 构建方式保持原样。

启动分析还发现：CLI 工具元数据加载会提前导入 Pyglet 的窗口、OpenGL 和媒体后端。现在在引擎实际使用输入、音频时加载这些后端，移除了渲染模块未使用的提前导入。

<a id="reverie-cli-background-startup-repairs-2026-10-07--验证"></a>

### 验证

测试环境为本机 Windows x64，所有验证使用仓库内的隔离配置与项目，没有替换正在使用的安装目录或用户配置。

- Python 启动与引擎相关回归：162 passed。
- 桌面完整 Vitest：280 passed / 1 skipped。跳过项要求外部 `REVERIE_RATS_ENGINE_BIN`。初轮 Git 远程分支测试在并行构建期间超时；单项复测和构建结束后的完整复测均通过，没有修改该测试。
- `npm run typecheck`、CLI PyInstaller 构建、`npm run dist:win` 均通过，桌面 build ID 为 `1acc55d4895fd101`。
- 实际原生引擎运行：键鼠事件、480×300 到 640×360 的窗口缩放、OpenGL 像素绘制和关闭，5 帧完成，无 native rendering error。
- 最终打包 GUI 与便携 EXE：深浅主题、任务栏展开、原生最小化/最大化/关闭消息、真实 Tray 实例恢复、关闭后真实 ConPTY 终端保活、显式退出与进程清理通过。退出确认的两个响应在测试中注入，原生确认对话框按钮未手动点击。
- 终端 ZIP：1766 项文件 CRC 检查、解压后的 `--version`、`--kernel-info` 与 SDK bridge ready/shutdown 合同通过；解压后的交互终端也能正常 `/exit`。

原生窗口截图中，浅色标题栏与三个窗口按钮的背景采样均为 RGB(224,225,226)；深色采样最大通道差为 1。消息区与输入区交界处的平均 RGB 差分别为深色 0.33、浅色 0.16（每通道 0–255），截图中的横向色差条已消除。

<a id="reverie-cli-background-startup-repairs-2026-10-07--启动计时"></a>

### 启动计时

通过真实 Windows ConPTY，从创建进程计时到可输入的 Reverie 提示符；每项三次，均通过 `/exit` 正常退出。配置隔离，不包含模型联网请求。

| 运行方式 | 三次提示符就绪时间（秒） |
| --- | --- |
| 修复前的单文件终端基线 | 15.87 / 24.01 / 20.06 |
| 同一验证项目内、独立运行的旧单文件控制 | 13.36 / 8.17 / 7.77 |
| 最终 `dist/reverie.exe` 与运行目录 | 2.32 / 4.26 / 2.99 |
| 最终终端 ZIP 解压后的 EXE | 2.70 / 2.13 / 2.54 |
| 最终桌面包内的终端内核 | 2.99 / 2.75 / 1.83 |

旧单文件控制与最后三项复测使用同一项目，期间没有并行构建或 GUI 验证，控制记录为 `control-startup.json`。早期并行验证中，新目录版有一次 8.22 秒首次加载，旧单文件控制有一次 90 秒超时；原始记录保留在 `final-startup.json`，没有计入上述独立复测。早期 `after-startup.json` 的 `onefile` 标记沿用了旧脚本名称，实际已是新目录版，以 `settled-startup.json` 的正式命名和计时为准。

便携 GUI 仍需首次展开一次完整应用：单独首次运行观测为 48.30 秒，缓存运行观测为 9.28 秒，各一次；此前一次首次运行超过了 60 秒测试等待时间。快速终端 ZIP 使用已经展开的运行目录。这些计时是本机观测，不代表其他机器、配置或模型联网流程的启动上界。

<a id="reverie-cli-background-startup-repairs-2026-10-07--产物与证据"></a>

### 产物与证据

- `dist/Reverie-CLI-windows-x64.zip`：快速终端包，329881804 bytes。解压后保持 EXE 和运行目录相邻。
- `ReverieCli-ui/release/Reverie-Setup-2.5.0-x64.exe`：桌面安装包，441220447 bytes。
- `dist/Reverie-Portable-2.5.0-x64.exe`：便携桌面包，501953611 bytes。

原始日志、计时 JSON、原生窗口截图和测试脚本保存在 `.runtime/background-startup-20261007/`。代表截图为 `final-dark-native.png`、`final-light-native.png` 和 `final-light-task-expanded.png`；机器可读记录见 `docs/verification/2026-10-07-background-startup.json`。

本次没有 commit/push；原有未提交工作保留，Unix 构建脚本与任务开始时的副本逐字节一致。


---

<a id="reverie-cli-context-gui-validation-2026-10-02"></a>

<a id="reverie-cli-context-gui-validation-2026-10-02--实时上下文与-gui-修复验证"></a>

## 实时上下文与 GUI 修复验证

> 原文件：`docs/REVERIE_CLI_CONTEXT_GUI_VALIDATION_2026-10-02.md`。以下为当时的记录；日期、测试数字、限制与旧实施提示词均保留，不代表本次重新验收。


后续用户修订已移除“本条上下文”汇总入口和弹层；本文件弹层及 41 项数字为历史阶段证据。原计数复用、负面改动复审、运行时选择器及错误区尺寸修正的最终证据见 [复审记录](#reverie-cli-token-context-review-2026-10-02)。

<a id="reverie-cli-context-gui-validation-2026-10-02--范围与实现"></a>

### 范围与实现

按 2026-10-02 用户修订移除会话上移/下移、手动排序及“最近与手动顺序 / 运行中 / 需处理”下拉框。保留置顶、搜索、重命名、归档、逐行状态及原有最近顺序；不删除历史排序偏好或独立草稿。

上下文统计以 250ms 节流刷新草稿、就绪附件、流式输出与工具事件。生成中读取该会话的真实执行 worker，读取不替换运行历史、不消耗暂停/补充的 safe point；未完成的助手输出追加到只读统计快照。统计快照不覆盖代理用于自动压缩的缓存。

API 返回 usage 时发布带工作区/会话身份的 `context.usage` 事件，作为该次请求和响应的测量基准。后续未发送草稿和新增内容采用原有本地分词器计算增量，界面区分“API 返回用量”“API 用量 + 本地估算”和本地估算。草稿清空时回到测量基准。模型变化清除基准；历史缩短/压缩导致基准失配时回退本地。基准不跨应用重启持久化；重启后在下一次 API 测量前显示本地估算。

自定义模型目录、设置卡片与运行时容量统一读取保存的模型配置，修复目录 200K 而实际配置/运行时 512K 的来源不一致。容量一致性是附带修复，实时刷新是本次重点。

输入上下文弹层改为 body portal，在整个输入框上方定位；支持窄窗口、滚动/缩放重定位、点击外部关闭、Escape 和关闭按钮返回入口焦点，并避开中文输入法 composing Escape。长错误只在消息错误卡展示，限制高度、内部滚动并支持复制完整内容；内核错误不再当作助手文本流发送，兼容已有错误流的界面也过滤重复诊断。失败后输入框可编辑，停止“正在处理”状态。自定义 Provider 的图片入口与其 vision 能力配置保持一致。

<a id="reverie-cli-context-gui-validation-2026-10-02--检查与编译"></a>

### 检查与编译

- Python 六组相关回归 375 passed；批量执行/错误事件回归 23 passed；媒体输入回归 3 passed。
- UI 全套 205 passed、1 skipped（未配置真实 Reverie Engine 的 RATS 集成测试）；最后错误事件修复另行复测交互测试 74 passed。类型检查和国际化检查通过（918 translations、82 templates）。
- 最终 PyInstaller 内核、TypeScript/Vite 前端、electron-builder Windows 目录包实际编译成功。应用路径：`ReverieCli-ui/release/context-live-final-20261002/win-unpacked/ReverieUI.exe`。
- 默认发布目录解除占用后，备份并同步 `reverie.exe`、运行库、trusted-kernels manifest 和 `resources/app.asar` 到 `ReverieCli-ui/release/win-unpacked/`。两处内核 SHA-256 相同（`1FC097F0C1EB3CB5744ADB87967F353EED65B0CBF1E99FD10193C512F974F472`）。默认目录未发现 `.reverie` 数据文件，0 文件哈希检查不能作为原用户全部数据的完整性证明；同步仅针对上述打包文件，不处理其他应用数据根目录。
- 构建日志：`.runtime/context-ui-20261002/build-kernel-accepted.log`、`build-renderer-accepted.log`、`package-accepted.log`。旧的外部 `dist/reverie.exe` 探测失败，本轮显式选择本次编译的 `.kernel/reverie/reverie.exe`；未改写旧外部内核或被锁定的默认发布目录。
- 最终验收采用独立应用数据和项目内 Git fixture，不改写用户的原有会话/草稿。所有最终临时目录、日志、截图和测试产物都在项目 `.runtime/context-ui-20261002/` 内。

<a id="reverie-cli-context-gui-validation-2026-10-02--实际界面流程"></a>

### 实际界面流程

1. **草稿、流式输出与 API 校准。** 输入长中文草稿无需发送即可看到环更新；实际 HTTP SSE 输出期间占用连续从 7% → 10% → 13% → 16% → 19%。最终 API usage（401 输入、23 输出、424 总量）到达后显示 424；新增草稿显示混合来源，清空草稿恢复基准。这里刻意让服务返回值不同于本地估算，检验 API 优先级。截图：`after-07-live-draft.png`、`after-08-live-stream.png`、`after-06-recovered.png`、`after-09-api-live-draft.png`。
2. **图片与上下文弹层。** 实际 Windows 剪贴板图片粘贴为工作区 PNG，预览实际图片，Escape 返回附件入口；HTTP 请求中包含该图片的 data URI。深/浅主题分别以 1500×960 和 760×650 验证弹层完整显示、位于输入框上方、边界在窗口内、键盘返回焦点。截图：`after-05-image-preview.png`、`after-popup-{dark,light}-{1500,760}.png`。原界面裁切证据：`before-01-context-popup.png`。
3. **失败、重试与恢复。** 实际 HTTP 400 返回超过 2000 字符的中英文诊断；错误标题、复制、内部滚动可用，不再在输入框或助手文本中重复。复制到真实系统剪贴板并读回完整文本；深浅主题和窄窗口检查横向溢出。随后发起真实重试，正常返回后错误卡清除。原问题：`before-02-error.png`；修复截图：`after-error-{dark,light}-{1500,760}.png`。
4. **本机基础路径。** 从打包版 bridge 读取真实中文文件，通过 Git snapshot 验证 fixture 分支/HEAD，通过原生 PTY 写入中文文件并读回输出。生成中的实时统计与停止操作一起验证。仅对隔离 fixture 做操作，本项目不执行 commit/push。

完整断言和 API 事件记录见 `.runtime/context-ui-20261002/accepted-runtime-evidence.json`，日志见 `runtime-accepted.log`；入口脚本为 `verify.py` 和 `runtime_driver.py`。实际界面截图均来自 Windows 打包程序的 Electron 页面，未用开发网页截图替代。

最终打包版 41/41 项断言通过，包括生成中停止、真实文件/剪贴板/Git/PTY/bridge。停止 SSE 时本机验证服务记录了 Windows 10053 连接中止，这是取消实际请求的结果；应用已恢复可编辑状态，相关停止断言通过。Python 后续批量/媒体复测 26 passed；最终交互复测 74 passed，`git diff --check` 通过。原生 IME、外部视觉理解及真实 Engine RATS 项仍保留在下方未验收列表。

同步后的默认 `release/win-unpacked/ReverieUI.exe` 重新启动并完成相同的 41/41 项验收，证据为 `default-runtime-evidence.json`、`runtime-default.log`。最终 `after-*` 截图已由默认包这次运行重新生成。默认包与独立验收包均通过，无需用户切换到特殊测试入口。

<a id="reverie-cli-context-gui-validation-2026-10-02--仍缺证据"></a>

### 仍缺证据

- HTTP 验收为实际本机服务与打包内核的真实传输，不能代替外部 JDW 服务账单对账或模型视觉理解质量验证。
- 工具结果在执行 worker 中完整计数、只读统计不改运行历史由聚焦回归验证；本轮尚未用外部模型多轮工具任务证明整条实时工具链。
- 中文内容输入与 composing 键盘事件有自动化验证；原生中文输入法候选框交互、不同 DPI/屏幕读屏器尚未实机证明。
- 初次流式断言在 worker 启动阶段过早采样，未等第一条响应；调整为收到首条 SSE 输出后再测，保留失败日志。实际打包检查还发现了自定义图片入口与错误文本重复的问题，均补充修复后重新编译验证，不把初次检查当作最终通过。

代码实现、上述 UI/UX 路径和验证证据分别列出，不据此宣称所有 S01–S21 的外部模型、授权或原生交互验收全部完成。保留原先 Tokens 统计改动及无关 `result_images/`，本轮未提交或推送。

同步记录见 `default-package-update.json`，被替换文件备份在 `default-package-backup/`。运行库第一次复制产生了 `release/win-unpacked/reverie-runtime/reverie-runtime/` 重复目录；删除被自动审批以 `blocked by policy` 拒绝。重复目录保留，随后按相对文件路径将 797 个运行库文件同步到正确目录。未绕过拒绝或删除其他文件。


---

<a id="reverie-cli-deep-validation-2026-10-01"></a>

<a id="reverie-cli-deep-validation-2026-10-01--reverie-desktop-深入验证与本地提交记录"></a>

## Reverie Desktop 深入验证与本地提交记录

> 原文件：`docs/REVERIE_CLI_DEEP_VALIDATION_2026-10-01.md`。以下为当时的记录；日期、测试数字、限制与旧实施提示词均保留，不代表本次重新验收。


本轮延续 S01–S21，重点验证图片提交、UI/UX、动效、真实文件/剪贴板、Git、终端及打包内核 bridge。T01–T05、X01–X08、Local/Cloud 继续排除。用户追加“验证后提交”后，本轮准备并执行范围明确的本地 Git 提交，没有推送授权。完整 21 项的代码实现、UI/UX、通过证据和未完成验收矩阵仍见 [阶段实施记录](#reverie-cli-implementation-report-2026-09-30)。

<a id="reverie-cli-deep-validation-2026-10-01--本轮修复"></a>

### 本轮修复

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

<a id="reverie-cli-deep-validation-2026-10-01--实际构建与测试"></a>

### 实际构建与测试

- 内核真实 PyInstaller 编译及 Electron 打包：[deep-kernel-final-pack.log](../.runtime/implementation-20260930/deep-kernel-final-pack.log)。最终 UI 经 TypeScript/Vite 编译再目录打包：[deep-layout-delivery-pack.log](../.runtime/implementation-20260930/deep-layout-delivery-pack.log)。程序：[ReverieUI.exe](../ReverieCli-ui/release/win-unpacked/ReverieUI.exe)。验证对象为 Windows x64 目录包，不将此结果称为安装器安装验证。
- Typecheck/i18n 通过，918 个翻译、77 个模板。完整 UI 测试 **200 passed、1 skipped**：[deep-ui-final-tests.log](../.runtime/implementation-20260930/deep-ui-final-tests.log)。测试临时目录位于本项目内，磁盘集成测试使用单 worker、120 秒测试上限和 30 秒清理上限。
- 相关 Python 测试 **179 passed**：[deep-python-final.log](../.runtime/implementation-20260930/deep-python-final.log)，包括桌面 bridge、输入/控制、工具权限、命令取消、模型 transport 与代理。
- 最终包重跑照片/UI **24/24**、本机照片协议 **8/8**、R2 Git/预览 **20/20**、R3 原生终端/bridge **14/14**、R4 双目录/恢复 **17/17**；共 83 条断言。R2 使用全新项目内仓库和 bare remote 重跑 Git 闭环，结果见同名证据。本轮新增 18 张照片/UI 关键截图，并更新原有 R2/R3/R4 截图。
- 中途验证曾失败：旧测试配置重复模型名导致选择旧端点；纯图协议包含自动文件说明，最初断言错误地要求只有图片；项目内 TEMP 暴露父 Git 发现和 5/30 秒超时及 Windows 清理锁。改用全新独立测试目录、按图片顺序/字节校验、隔离非仓库夹具的 Git 边界、顺序执行和清理重试后重新验证。构建也曾因自己的验收进程占用 DLL 失败，关闭该进程后重打包。失败尝试不作为成功证据。
- jsdom 的 canvas 提示没有被当作 PDF/终端渲染证明；运行截图、原生进程、像素和磁盘结果提供对应证据。
- R2 重跑的旧 harness 曾等待 PDF iframe 而超时；当前实现已使用 PDF canvas。修正检查实际 canvas 后，20 项完整通过，PDF 第 2 页像素验证仍由 R3 提供。

<a id="reverie-cli-deep-validation-2026-10-01--界面验收路径"></a>

### 界面验收路径

验收使用实际目录包和独立 `PORTABLE_EXECUTABLE_DIR`，通过现有 Python Playwright API/CDP 操作自己的 Electron 页面。最终测试、打包和实机验收的文件、Git 仓库、HTTP 端点、日志、截图和备份均留在 `.runtime/implementation-20260930`；没有替换用户原配置。早期一次 UI 单元测试继承了系统 TEMP，测试具有自动清理，随后改为项目内 TEMP 并完整重跑。

1. **导入与预览：已修复。** 真实 PNG/JPEG 拖放显示尺寸、顺序和版本，原生剪贴板图片导入；预览读取原图、焦点循环和关闭恢复可用。[附件](../.runtime/implementation-20260930/deep-screenshots/02-photos-imported.png)、[预览](../.runtime/implementation-20260930/deep-screenshots/03-photo-preview.png)。
2. **发送与历史：协议通过，真实视觉理解待验。** 实际内核把纯图片和混合图片发送到本机 HTTP 记录端点，图片字节哈希和次序匹配源文件；完成记录有独立内核 PID，重新打开后可预览图片。[发送等待](../.runtime/implementation-20260930/deep-screenshots/13-pure-photo-running.png)、[混合消息](../.runtime/implementation-20260930/deep-screenshots/11-mixed-photo-contract.png)、[历史图片预览](../.runtime/implementation-20260930/deep-screenshots/12-sent-photo-preview.png)。
3. **失败与恢复：已修复。** 原配置无活动模型时失败可见，图文草稿保留；真实图片删除后禁止发送，重试按钮可见；文件恢复后重试恢复资格。[发送失败](../.runtime/implementation-20260930/deep-screenshots/05-send-failure-preserved.png)、[文件丢失](../.runtime/implementation-20260930/deep-screenshots/06-missing-photo.png)、[恢复](../.runtime/implementation-20260930/deep-screenshots/07-retry-recovered.png)。
4. **布局与动效：已修复。** 深浅主题、800/1024/1440×700 输入区完整，输入器不产生额外横向滚动；正常布局 transition 有界，系统 reduced motion 禁用布局动效。截图在预览动效结束后保存。[深色窄窗口](../.runtime/implementation-20260930/deep-screenshots/08-photos-dark-800.png)、[浅色窄窗口](../.runtime/implementation-20260930/deep-screenshots/08-photos-light-800.png)。
5. **Git、终端、bridge 与独立目录：本地路径通过，服务项待验。** 真实 hunk 暂存/提交及项目内 bare remote 推送证据在 R2；原生 PTY、中文文件、Ctrl+C、复制/日志入未发送草稿、exit 7、PDF 第 2 页、日志导出在 R3；双工作目录的 PTY/内核 PID、FIFO 等待取消和脏目录归档恢复在 R4。证据：[R2](../.runtime/implementation-20260930/r2-runtime-evidence.json)、[R3](../.runtime/implementation-20260930/r3-runtime-evidence.json)、[R4](../.runtime/implementation-20260930/r4-runtime-evidence.json)。主项目没有执行测试用 push。

照片/UI 证据：[deep-ui-runtime-evidence.json](../.runtime/implementation-20260930/deep-ui-runtime-evidence.json)、[photo-contract-runtime-evidence.json](../.runtime/implementation-20260930/photo-contract-runtime-evidence.json)。本机端点只记录协议并返回固定 `CONTRACT_ONLY_NO_VISUAL_INFERENCE` 文本；没有视觉推理、实际服务认证或模型工具调用。已通过协议传输不能替代真实模型验收。

<a id="reverie-cli-deep-validation-2026-10-01--仍缺证据"></a>

### 仍缺证据

- 有凭据的真实视觉服务理解/输出、长任务 Steer/暂停/Stop、只读模型审查、双目录模型写入与并行审批。
- 真实认证插件、连接及授权 RATS 服务；托管 Git 远端凭据。
- Windows 原生中文候选窗与组合输入后 Enter；复杂终端 TUI。
- OS 通知点击回跳和关闭系统通知场景。此前实际最小化后台通知 `shown` 的结果保留在 [通知证据](../.runtime/implementation-20260930/notification-runtime-evidence.json)。

<a id="reverie-cli-deep-validation-2026-10-01--保留与提交范围"></a>

### 保留与提交范围

提交只纳入 S01–S21 相关内核、桌面代码、测试和产品/验收文档。原有无关 `ReverieCli-py/tests/test_rats_engine_task_e2e.py` 和 `result_images/` 不纳入；临时验证数据与 release 产物不纳入。每次打包前备份原 `.reverie`，结束后恢复；原 54 个文件哈希全部一致，无关 RATS e2e 文件与基线一致。提交前核对基线、范围及 `git diff --cached --check`；没有 commit hooks/自动推送的成功假设。见 [保留与包哈希证据](../.runtime/implementation-20260930/deep-preservation-evidence.json)。


---

<a id="reverie-cli-feature-audit-2026-10-05"></a>

<a id="reverie-cli-feature-audit-2026-10-05--reverie-cli-功能与文档审查2026-10-05"></a>

## Reverie CLI 功能与文档审查（2026-10-05）

> 原文件：`docs/REVERIE_CLI_FEATURE_AUDIT_2026-10-05.md`。以下为当时的记录；日期、测试数字、限制与旧实施提示词均保留，不代表本次重新验收。


> 本报告保留**修复前**的审查与复现。随后用户要求修复发现的问题；当前实现与验证请看 [修复报告](#reverie-cli-feature-repairs-2026-10-05) 和 [功能状态](FEATURE_STATUS.md)。本文的失败结果和源码描述是历史基线，不代表修复后的行为。

<a id="reverie-cli-feature-audit-2026-10-05--结论与范围"></a>

### 结论与范围

当前代码已有较完整的本地编码工作流，但不能把 S01–S21 的代码接入或单轮打包测试解释为全部功能完成。本次登记 **24 项缺口 / 限制 / 证据问题**，其中 G22 的文档整理在本次完成；其余状态在 [功能矩阵](FEATURE_STATUS.md)，后续工作与验收条件只维护于 [ROADMAP](ROADMAP.md)。

审查对象是 `G:\Reverie\Reverie-Cli` 的**本地工作区**，起始 HEAD 为 `127c39769217d87dd7647a3c6b296e2629d8f9ff`，版本 2.5.0，已有大量未提交实现。本次没有把 HEAD、远端发布和工作区混成一个版本，没有修改用户凭据 / 会话 / 配置，没有 commit、push 或远端发布。

检查覆盖 CLI/help/批处理、Desktop/SDK dispatch、草稿/附件/会话/Skills、执行器/审批/目标/终端/通知、Git/worktrees/审查/预览、提供商/MCP/插件/RATS、Context Engine/Memory/Tokens、Atlas/Writer/媒体/桌面控制、Engine/Gamer，以及打包和 CI。TODO / NotImplementedError 检索只作线索；抽象基类、明确排除功能和可选依赖没有直接算成未完成产品。

本次是审查与文档更新，未修复下面登记的软件缺口。Windows 编译、现有包 bridge 冒烟、回归与隔离复现是新证据；10 月 4 日菜单 / 主题 / 重启及 JDW 网络采样是注明日期的历史证据，今天没有重做 GUI 截图或远端模型请求。

<a id="reverie-cli-feature-audit-2026-10-05--已确认的核心缺口"></a>

### 已确认的核心缺口

| ID | 触发与当前结果 | 源码 / 证据 | 判定 |
| --- | --- | --- | --- |
| G01 | Desktop 的 `/permission mode strict`、`/mode writer` 等参数化命令走普通 agent 输入；`/review file` 仅打开面板，不设置文件 | [App.tsx](../ReverieCli-ui/src/App.tsx)，`COMMAND_VIEWS`、`sendPrompt`、`chooseCommand`；[sdk_bridge.py](../ReverieCli-py/reverie/sdk_bridge.py) `_dispatch_prompt` 调用 `run_prompt_once` | 派发缺失；命令目录存在不能代表 GUI 执行 |
| G02 | 保存 `apple-design` 后读取原会话仍有 pin；分叉与 rotate 的新会话都没有 `pinned_skills` | [SessionManager](../ReverieCli-py/reverie/session/manager.py) `fork_current_session` / `rotate_session`；真实磁盘隔离复现 | 元数据继承缺失 |
| G03 | CLI 改 pin 只刷新 prompt；`restore_pinned_skills` 的运行时调用在 SDK bridge，不在独立 CLI 会话恢复流程 | [commands.py](../ReverieCli-py/reverie/cli/commands.py) `_after_pinned_skills_changed`；[interface.py](../ReverieCli-py/reverie/cli/interface.py)；[bridge](../ReverieCli-py/reverie/sdk_bridge.py) `_sync_skill_pins` | CLI/Desktop 持久语义不一致；未用真实用户会话复测 |
| G04 | 同一 Git 仓库的根目录与 `src` 分别提交 writable acquire，两个 entry 都立即 running | [execution-coordinator.ts](../ReverieCli-ui/electron/execution-coordinator.ts) 使用 `realpath(projectRoot).toLowerCase()` 作为 checkout；实际编译模块 + 隔离 Git 目录 | 同 checkout 的不同项目路径可绕过排队；未实际并发改文件 |
| G05 | 空闲时保存目标仅写 Electron goal 文件；下一轮 payload 没有读取目标；运行中的修改才 Steer 发送 | [SessionWorkbench.tsx](../ReverieCli-ui/src/SessionWorkbench.tsx) `savePlan`；[App.tsx](../ReverieCli-ui/src/App.tsx) `runPromptText`；[main.ts](../ReverieCli-ui/electron/main.ts) goal 操作 | 显示/保存与模型执行未闭环 |
| G06 | 本地 HTTP 服务返回 200，正文 `{"choices":[],"usage":{"completion_tokens":1}}`，chat probe 仍报告 online/answered | [custom_providers.py](../ReverieCli-py/reverie/custom_providers.py) `probe_custom_provider_chat`；本次真实 HTTP 复现 | 探测假阳性；不是远端服务测试 |
| G07 | pin 被提升为 mandatory system block，但没有逐轮检验 inspect 分块已读完后再允许执行 | [skills_manager.py](../ReverieCli-py/reverie/skills_manager.py) `describe_pinned_for_prompt`；[agent.py](../ReverieCli-py/reverie/agent/agent.py) | 提示已生效，实际遵循仍依赖模型；标签不是证明 |

隔离复现摘要：

```json
{
  "session_pins": {
    "original": ["apple-design"],
    "restored_original": ["apple-design"],
    "fork": null,
    "rotation": null
  },
  "coordinator": {
    "same_git_checkout": true,
    "project_roots": ["checkout-fixture", "checkout-fixture/src"],
    "writable_running": 2
  },
  "chat_probe": {
    "http": 200,
    "choices": [],
    "reported_status": "online"
  }
}
```

这些复现在仓库 `.runtime/feature-audit-20261005` 下创建独立数据，不写用户工作文件。协调器检查只取得/释放队列许可，没有启动模型或写任务；HTTP 服务只绑定 loopback，已关闭。

<a id="reverie-cli-feature-audit-2026-10-05--性能体验与长期状态"></a>

### 性能、体验与长期状态

| ID | 观察 | 判断边界 |
| --- | --- | --- |
| G08 | `gitPatch` 获得整份 patch 后才切 2000 行；`versions` 读取完整 working/staged binary diff；`readPreview` 整文件读、哈希，图片/PDF 转 base64 | 当前分页是显示分页。源码确认存在规模上限，不把 10 月 4 日普通仓库的 0.56–0.90 秒快照推广到大仓库 |
| G09 | `search_sessions` 逐会话读 JSON 并扫描消息，结果 limit 不限制无命中扫描 | 历史打开已有索引/分页优化，全文搜索仍是另一个未优化路径；本次未给出稳定耗时结论 |
| G10 | PTY 与 run 事件持续追加文件；终端恢复整份读取；SessionWorkbench 使用 2.5 秒 interval，owner 防护只检查 root | 日志容量/长时间恢复边界不足。切换同项目会话的异步竞态需要专门复现，不能说已发生跨会话写入 |
| G11 | review JSON 解析失败仍保留原文，但 findings 为 `[]`；字段过滤不验证 path/line 是否属于实际 diff | 不能把“没有结构化发现”当作“没有问题”；只读工具白名单与审查结果质量是两件事 |
| G13 / G14 | 输入已有 isComposing / key 229；候选已支持键盘；通知已有 owner/去重/应用内回跳 | 原生 IME、命令面板完整键盘/屏幕阅读器、OS 点击/禁用及并行通知尚缺完整实机证据 |
| G17 / G18 | Vite 主 chunk 约 1.12 MB，构建发出 500 kB 警告；便携版首次解压；版本号持续为 2.5.0；CI 包含多平台构建 | 构建警告不是 UI 卡顿证明。当前应分别衡量首次解压、核心启动、renderer 和长任务；本次只验证 Windows |

`file_ops` 只读检查点优化、EISDIR 和候选顶层显示已在 [10 月 4 日报告](#reverie-cli-ui-repair-2026-10-04)验证；不能因这些修复而认为所有 Git/日志/历史路径都已没有性能问题。

<a id="reverie-cli-feature-audit-2026-10-05--服务专用模式与引擎"></a>

### 服务、专用模式与引擎

- **G12 提供商**：catalog probe 与非流式最小 Hi probe 不验证工具、SSE、图像、思考签名或计费。自定义模型元数据缺工具能力时还会默认 `tool_calling=true`，这是兼容假设，不是测得的能力。10 月 4 日 JDW 三次采样记录仍保留，今天没有重测，也不能声称 Claude Desktop 两种模式已恢复。
- **G15 集成**：MCP 实现有 stdio、streamable HTTP 和 SSE；插件/RATS 有实际启用/信任/权限/工具路径。RATS 官方 registry 仅内置 Engine，但现在已有用户显式 custom provider 定义，不应继续把“provider-neutral cleanup”写成完全未做。真实认证服务、本次 Engine E2E 和其他产品提供者仍缺证据。
- **G16 检索**：Context Engine/Memory 有广泛回归；公开文档中的 23 个 SWE-bench 样例及冻结 7 个样例是历史小样本，不等于 300 个完整基准。本地 token/图像估算也不能覆盖网关隐藏提示和服务侧编码。
- **Atlas/Writer**：文档流程、章节事务、字数/重复/连续性门禁存在并有回归。历史 Writer 五章实测有价值，但不是“任意十万字作品质量与完成”证明；无需因此再添加一个空的专用 UI。
- **浏览器/桌面控制/媒体**：后端工具与可选运行时已有实现，依赖模型、SDK、设备与许可。Desktop 的隔离静态 HTML 预览不能冒充嵌入交互浏览器；不能把模型可用的浏览器工具误列为全产品缺失。
- **G19–G21 内置 Engine/Gamer**：CLI 的 Python 运行时源码和能力报告仍是 Alpha，ModernGL 用 standalone context/framebuffer，缺桌面事件窗口；基础纹理不是完整 PBR。Live2D 明确 `native_renderer_implemented=false`；音频区分 installed/unverified/operational。切片、程序化资产和受限迁移存在，AAA/3A 和 3D 开放世界仍不支持。外部 Engine 编辑器与 RATS 服务是另一表面，没有在本次重新验收，不能把这里的窗口缺口套到它上面。

<a id="reverie-cli-feature-audit-2026-10-05--新验证与失败"></a>

### 新验证与失败

| 检查 | 本次结果 | 范围 |
| --- | --- | --- |
| 完整 Desktop Vitest | **235 passed / 1 skipped**，31 个文件通过、1 个跳过 | 使用 `--testTimeout 30000`；真实 Engine 未配置的 E2E 跳过 |
| Python 首批相关 22 个测试文件 | **513 passed / 1 skipped** | SDK/执行控制/Skill/权限/提供商/Writer/Engine 等路径；不是全量 |
| 完整 Python `ReverieCli-py/tests` | **1740 passed / 2 failed / 1 skipped** | 285.16 秒；两个失败单独复测仍失败，不能报告全量通过 |
| TypeScript / i18n | 通过，948 个翻译、82 个模板 | 当前源码，Electron 与 renderer 类型 |
| `npm run build` | Electron / renderer 实际编译通过 | 保留 chunk 警告；没有重打安装包/便携包，软件实现未在本次改动 |
| 已有编译 CLI `--help` | 通过 | 核对真实支持的参数，发现并修正 README 的无效参数 |
| 已有编译 CLI SDK bridge | ready + shutdown，exit 0 | `smoke_sdk_bridge.py --executable dist/reverie.exe`，不是模型工具验收 |
| Session / coordinator / provider 隔离复现 | 三组结果与上面摘要一致 | 真实磁盘、编译协调器、实际本地 HTTP；未调用付费远端 |

**G23 的两项失败：**

1. `test_chat_loading_performance.py::test_transcript_revision_changes_when_the_saved_history_changes`：测试构造的 `SimpleNamespace` 缺 `project_data_dir`，新的 `_sync_skill_pins` 在进入 revision 断言前抛 `AttributeError`。这是旧 fixture 未跟上接口，不证明真实 CLIInterface 会话版本坏了；revision 回归目前没有得到通过证据。
2. `test_tooling_upgrades.py::test_skill_lookup_lists_and_inspects_discovered_skills`：新增 14 个内置包后，测试共发现 18 项，但默认 list 只输出 8 项；测试仍要求用户 `openai-docs` 出现在第一页。报告里另有 10 项 omitted。这不证明该包无法 inspect，但反映测试覆盖/目录假设需要维护。

本次保留失败，没有为了获得绿色结果修改实现、放松断言或跳过它们。新旧测试数有重叠，不相加。完整日志及 probe 脚本在本地 `.runtime/feature-audit-20261005`；公开复核摘要在 [结构化证据](verification/2026-10-05-feature-audit.json)，无需依赖未发布日志理解结果。

<a id="reverie-cli-feature-audit-2026-10-05--文档系统更新"></a>

### 文档系统更新

| 原问题 | 本次处理 |
| --- | --- |
| 主入口只突出终端/Engine，近六天报告未集中 | 新增功能矩阵、桌面/Skills 使用指南，索引集中当前指南和历史报告 |
| README 使用不存在的 `--provider`、`--resume`、`--workspace`、`--verbose` 等 | 按实际编译程序 `--help` 改成 `--source`、位置路径和真实参数；会话选择使用 TUI |
| 把核心配置写成 `%APPDATA%` / 工作区单一路径 | 对齐核心 app-root、工作区 Electron 数据与 renderer storage，说明备份边界 |
| Skill 仍写成仅内存 pin / 三种资源通配符 | 说明 Desktop metadata/draft 持久化和其他场景缺口；对齐递归资源打包及 14 个设计包 |
| 旧侧栏/轨迹规格可误导后续再实现已移除控件 | 给历史规格/交接加状态说明，当前指南明确用户删除项 |
| RATS 文档仍只描述旧 Engine coupling / schema 2 | 对齐 custom provider、provider-neutral 路径、settings schema 4；保留官方仅一个 provider 的事实 |
| 报告依赖忽略的 `.runtime` / 二进制材料 | 离线检查单独列本地材料；新公开状态和摘要不依赖这些文件 |
| 维护规则只覆盖 Engine 计划，没有自动文档检查 | 统一产品 ROADMAP、当前状态与证据来源；增加标准库链接/锚点检查及 CI job |

本地文档检查基线为 **34 份文档、197 个相对链接、0 个缺失文件/锚点、66 个本地产物引用**。问题主要是语义过时和入口缺失，而非当时的相对文件链接断裂。检查不抓取外部网页、不验证所有自然语言承诺，也不把本地截图存在当成 Git 发布成功。

更新后检查 **39 份文档、356 个相对链接，0 个缺失文件/锚点**，仍单列 66 个本地产物引用。最终范围增加四份当前 Markdown 文档和桌面 README。隔离用例验证中文/编码路径、重复标题、显式 ID、引用链接和代码围栏；缺失文件、无效锚点、越出仓库的链接能被检测，CLI 分别返回 0 / 1。CI YAML 已解析，检查命令在本地通过；没有执行远端 CI。

HEAD 与开工基线一致，暂存区为空；Git 状态比较未发现文档、文档检查器和对应 CI 之外的新状态变化。原有软件改动保持未提交；本次没有采集它们的开工逐文件哈希，不把状态比较写成逐字节保全证明。

T01–T05、X01–X08 和用户主动删除的 UI 继续保持原取舍。未来实现应按路线图闭环现有价值，不能把本报告的能力对照当作增加 Local/Cloud 或其他未授权产品的指令。


---

<a id="reverie-cli-feature-audit-addendum-2026-10-05"></a>

<a id="reverie-cli-feature-audit-addendum-2026-10-05--reverie-cli-功能复审附录mcp-客户端边界2026-10-05"></a>

## Reverie CLI 功能复审附录：MCP 客户端边界（2026-10-05）

> 原文件：`docs/REVERIE_CLI_FEATURE_AUDIT_ADDENDUM_2026-10-05.md`。以下为当时的记录；日期、测试数字、限制与旧实施提示词均保留，不代表本次重新验收。


> 本附录是 10 月 5 日修复报告之后的一轮定向源码复审，补充原功能审计未登记的 MCP 客户端边界。范围是当前本地工作区中的 MCP 实现与相应指南；不是远端服务验收，也没有修改 MCP 运行时代码。

后续状态：G25 分页已修复，G27 类型化媒体结果部分修复；本附录保留修复前源码结论，当前实现与验证见 [请求 / 个人资料修复报告](#reverie-cli-request-profile-repairs-2026-10-05)和[功能状态](FEATURE_STATUS.md)。

<a id="reverie-cli-feature-audit-addendum-2026-10-05--核对范围"></a>

### 核对范围

`ReverieCli-py/reverie/mcp.py` 将协议版本固定为 `2025-06-18`。本轮逐项核对该客户端的 initialize、目录发现、工具调用、资源读取、配置字段、工具结果序列化和 agent 消息接收路径，并对照同版本的 [MCP Tools](https://modelcontextprotocol.io/specification/2025-06-18/server/tools)、[Resources](https://modelcontextprotocol.io/specification/2025-06-18/server/resources)、[Prompts](https://modelcontextprotocol.io/specification/2025-06-18/server/prompts)、[Roots](https://modelcontextprotocol.io/specification/2025-06-18/client/roots)、[Sampling](https://modelcontextprotocol.io/specification/2025-06-18/client/sampling)、[Elicitation](https://modelcontextprotocol.io/specification/2025-06-18/client/elicitation) 和 [HTTP Authorization](https://modelcontextprotocol.io/specification/2025-06-18/basic/authorization) 页面。

传输类型已有 stdio、Streamable HTTP 和 legacy HTTP+SSE 路径。本附录不把未实现的 MCP **可选**客户端能力说成所有 MCP 调用都坏了；已发现的动态工具和资源列表 / 读取路径仍存在。HTTP Authorization 在协议中也是可选的；当前缺口是没有托管 OAuth，而非禁止用户通过静态 header 接入。

<a id="reverie-cli-feature-audit-addendum-2026-10-05--新增缺口"></a>

### 新增缺口

| ID | 当前行为 | 源码证据 | 用户影响 / 判定 |
| --- | --- | --- | --- |
| G24 | initialize 发送空的 client `capabilities`；发现流程会列出 tools、resources、prompts，但没有 `prompts/get`；没有 resource templates、resource subscriptions 或 roots / sampling / elicitation 的客户端处理器。 | `mcp.py`：`BaseMCPClient.initialize`、`discover`、`call_tool`、`read_resource`；`MCPRuntime` 的动态目录只从 `tools/list` 构建。全仓 MCP 路径未发现 `prompts/get` 等处理。 | 状态页可能显示服务器列出了多少 prompt，但用户和模型不能选择 / 渲染模板。需要这些可选客户端能力的服务器无法使用其相应流程；常规工具调用仍可用。 |
| G25 | `tools/list`、`resources/list`、`prompts/list` 各请求一次，参数为空，未读取返回的 `nextCursor`。 | `mcp.py`：`BaseMCPClient.discover` 的三处 list 请求；MCP 官方 Tools / Resources / Prompts 协议页说明相应 list 操作支持分页。 | 服务端分多页返回目录时，后续页内容不会进入当前工具或资源目录。源码确认，尚未用多页 fixture 做动态复现。 |
| G26 | HTTP 请求可以发送配置中的静态 `headers`；没有 OAuth 资源元数据 / 授权服务器发现、PKCE、401 挑战处理或令牌刷新路径。 | `mcp.py`：`normalize_mcp_server_config` 仅规范化 `headers`；`HttpMCPClient._request_headers` 复制静态 header；请求错误路径不进入授权流程。 | 需要交互 OAuth 的远端 MCP 服务不能走内置授权生命周期。协议将 HTTP Authorization 设为可选；本项目目前也没有声明实现它。静态令牌应按秘密数据保护，不能提交到仓库。 |
| G27 | MCP 工具结果格式化读取文本与 resource URI；没有可读文本 / structured content 时会把整个结果 JSON 化。原始 `content` 仅保存在元数据中。agent 的模型消息只读取 `message_content` / `relay_content`，否则使用字符串 `output`。 | `mcp.py`：`format_mcp_call_result`、`MCPRuntime.call_tool`；`tools/mcp_dynamic.py` 将 `output` 作为普通文本返回；`agent.py`：`_tool_result_content`。 | MCP image / audio 内容没有作为类型化多模态消息传给模型；没有文本的二进制结果可能退化为包含 base64 的 JSON 文本。源码确认，未用真实媒体 MCP 服务验收。 |

<a id="reverie-cli-feature-audit-addendum-2026-10-05--文档同步"></a>

### 文档同步

- [功能状态](FEATURE_STATUS.md) 增加 G24–G27，并将 MCP 矩阵标为“部分客户端实现”。
- [路线图](ROADMAP.md) 为客户端能力边界、列表分页、远端授权和多模态结果分别登记闭环条件。它们是待评估的功能工作，不构成对所有可选协议能力的自动实施授权。
- [配置指南](CONFIGURATION.md#mcp-server-connections) 新增 `.reverie/mcp.json` 配置位置、传输和字段说明，列明当前实现边界。
- [CLI 命令指南](CLI_COMMANDS.md) 删除“prompt guidance 已对模型可用”的不准确信息；目前 `prompts/list` 只有发现和计数用途。
- 根目录 README 说明 Chromium 是 Python 核心提供的 agent 工具，Electron Desktop 没有交互式浏览器标签面板；这和历史规格中暂缓 X03 一致。

<a id="reverie-cli-feature-audit-addendum-2026-10-05--验证边界"></a>

### 验证边界

本轮证据为当前源码路径审阅及与 `2025-06-18` 官方协议文档的逐项对照。没有启动真实 MCP 服务、授权服务器或多模态 fixture；没有重新运行 MCP 集成测试，也没有改写之前的全量测试数字。仓库内 MCP 专项测试文件是 `ReverieCli-py/tests/test_mcp_background_discovery.py`，它不能覆盖上述 prompt、分页、OAuth 或多模态流程。文档链接检查结果记录在本次变更结束时更新的 [结构化摘要](verification/2026-10-05-mcp-scope-audit.json)。


---

<a id="reverie-cli-feature-repairs-2026-10-05"></a>

<a id="reverie-cli-feature-repairs-2026-10-05--reverie-cli-功能缺口修复与验证2026-10-05"></a>

## Reverie CLI 功能缺口修复与验证（2026-10-05）

> 原文件：`docs/REVERIE_CLI_FEATURE_REPAIRS_2026-10-05.md`。以下为当时的记录；日期、测试数字、限制与旧实施提示词均保留，不代表本次重新验收。


后续请求取消、开关延迟、裁剪头像、对话布局和 MCP 修复见 [请求 / 个人资料报告](#reverie-cli-request-profile-repairs-2026-10-05)；本文保留首轮验证统计。

本轮按用户“修复发现的问题”的要求，修复 [审查报告](#reverie-cli-feature-audit-2026-10-05) 中已确认的软件缺陷，更新 [当前功能状态](FEATURE_STATUS.md)、使用指南和 [剩余路线图](ROADMAP.md)。修复前报告保留为历史基线。

审查对象仍是 `G:\Reverie\Reverie-Cli` 的本地工作区，版本 2.5.0；未 commit、push 或发布远端。起始及结束 HEAD 均为 `127c39769217d87dd7647a3c6b296e2629d8f9ff`。既有未提交工作保留，628 个既有内置 Skill 文件没有改变。Codex 已安装的 Apple Design 等设计 Skills 与 Reverie 内置的 14 个 Emil Kowalski 包沿用上一轮安装，未替换上游正文或许可。

<a id="reverie-cli-feature-repairs-2026-10-05--修复后的行为"></a>

### 修复后的行为

| 缺口 | 改动及结果 |
| --- | --- |
| G01 | 参数化 `/mode`、`/permission mode`、`/provider` 和 `/review` 明确派发；审查保留文件、范围和基准。其余终端命令标为“终端参考”，发送时报错并保留草稿，不误发给模型。 |
| G02 / G03 | pin 变更立即保存；CLI / Desktop 启动、加载与切换恢复。相同任务的分叉、自动轮换复制独立 pin 列表；普通新会话清空。 |
| G04 | 以真实 Git checkout / 非 Git 重叠目录协调写入，根目录、子目录和路径别名不能绕过锁；独立托管 worktree 保留并行能力。 |
| G05 | 所属执行器取得运行权时读取保存目标，传入本轮系统消息与运行记录；排队任务读取最新保存值，普通目标不进入只读审查。临时系统指导不沉入压缩历史。 |
| G06 | Chat / Responses / Messages 文本探测要求非空有效文本；HTTP 200、空 choices 或只有用量不能算“在线 / 已回答”。 |
| G07 | 每轮完整读取固定 `SKILL.md` 主正文，附加到系统请求，记录名称、SHA256、字符数和完整状态；失效、空正文或总量超过 128000 字符时阻止执行。 |
| G08 | 文本与 Git diff 流式处理，限制每页 2000 行 / 2 MiB、单行 256 KiB、hunk 元数据 10000 项；媒体预览限制 20 MiB。工作区版本用路径 / 对象及流式内容哈希计算，避免为状态扫描缓存整份巨型 diff。 |
| G09 | 工作区 SQLite 派生索引与增量更新替代每次读取全部会话 JSON；批量事务与紧凑 trigram 索引减少构建开销，字面量复核避免候选误匹配。旧派生缓存按版本重建。 |
| G10 | 日志保留当前及上一份各 8 MiB，恢复最多 1 MiB，UTF-8 / JSONL 边界处理；PTY 磁盘队列有背压，运行事件突发丢失有明确标记。Workbench、目标、独立目录的异步响应校验项目 / 会话归属，轮询等待上次完成。 |
| G11 | 合法空数组与格式错误分开；发现需有效字段、优先级和捕获 diff 内的真实文件 / 行。保存原文，不把无效输出解释为“没有问题”。实机另发现只读审查被编码完成规则续跑，现改用独立审查规则并禁止这类自动续跑。 |
| G13 | 命令面板补齐上下键、Enter、选中项滚动及 ARIA；组合输入期间不选择。目标栏切换会话立即清除旧目标，无步骤时隐藏“0/0 验证通过”。 |
| G17 | 构建输出生成可辨识 ID；关于页显示构建 ID、时间和实际 GUI / 内核路径。当前最终 GUI 为 `3446a494732d4efb`，构建于 `2026-10-05T09:30:56.029Z`。 |
| G19 | 内置 Engine 增加 Pyglet 原生窗口、事件循环与 ModernGL 呈现；接通当前帧输入、实际窗口尺寸、关闭及异常资源释放。初始化失败明确报告，headless 路径保持可用。 |
| G22 / G23 | 当前指南、状态表、路线图、文档入口和变更日志同步；两个过期回归 fixture / 查询假设已修正，保留原有语义断言。 |

每轮加载完整 Skill 主正文保证宿主已提供指令，不保证模型按语义执行每一步，也不自动执行 references / scripts。工具与模式的限制继续生效。

<a id="reverie-cli-feature-repairs-2026-10-05--最终验证"></a>

### 最终验证

| 检查 | 结果和范围 |
| --- | --- |
| 全量 Python | **1761 passed / 1 skipped**，314.64 秒；条件跳过为未配置真实 Engine 的 RTP 任务生命周期。 |
| 全量 Desktop | **254 passed / 1 skipped**，串行 worker、每测试 15 秒超时；真实 Git 根 / 子目录 / 别名 / worktree、审查解析和延迟响应均保留验证。条件跳过同为真实 Engine 服务集成。 |
| 类型 / 翻译 | `npm run typecheck` 通过；957 个翻译键、82 个模板。 |
| CLI 编译 | `build.bat --reuse-venv --skip-plugins --test-exe --no-pause` 成功，新的 `dist/reverie.exe` 启动检查通过；插件源码未改动，沿用既有插件产物。 |
| Windows 桌面编译 | `npm run dist:win` 生成安装包、便携包和 `win-unpacked` GUI；运行证据使用真实编译后的 Electron GUI / Python 内核。 |
| 隔离 GUI 链路 | 真实 `@` 文件选择、`/skill apple-design`、左下角模式菜单、命令面板键盘选择、参数派发、终端参考拦截、目录项、目标保存、审查错误展示、fork / 新会话 pin 语义。 |
| 实际网络请求 | 隔离本地 HTTP 服务捕获请求：Apple Design 主正文每轮存在；目标保存前不存在、保存后存在，fork 无所属目标，审查不携带普通目标。服务仅返回协议 fixture，不用于证明远端模型质量。 |
| 独立 CLI | 真 Windows PTY 启动编译后的 `reverie.exe`，恢复会话及 `apple-design`，执行 `/skill status`；发送普通提示后实际 HTTP 请求含 Skill 主正文，正常保存退出。 |
| 真实 PTY 日志 | 一次输出约 12 MiB；上一份 8388424 字节、当前份 4455369 字节，均在上限内；恢复 1048576 字节、保留 `PTY-END`、截断状态为真，退出码 0。GUI 重启后两份终端记录均恢复为 exited / 0。 |
| GUI 重启 / 改包 | 原会话 ID、中文草稿、dark 主题、固定 Skill 和保存目标均恢复；新构建 ID / 实际路径正确，空步骤没有“0/0 验证通过”。重启使用隔离的 `win-unpacked` GUI。 |
| Engine 原生窗口 | Windows 实际呈现 5 帧、D 按下 / 松开、鼠标位置及当前帧增量、480×300 到 640×360 缩放、WM_CLOSE 干净结束；呈现后的 framebuffer 图片检查通过。使用占位纹理和明确放大的样例 sprite，不代表生产美术或完整游戏控制。 |

实机审查验证暴露并修复了普通编码任务自动续跑规则的误用；最终编译包中只读审查不要求文件修改 / 测试，也不进入 Atlas / Writer 的文档完成续跑。无效 review JSON 仍显示格式错误和原文，模型质量与格式契约分别判定。

<a id="reverie-cli-feature-repairs-2026-10-05--重复性能对照"></a>

### 重复性能对照

Windows 本机、相同隔离数据，各路径三次采样；原实现保留为控制路径。下表是观察范围，不是所有机器和仓库的延迟保证。

| 场景 | 修复前 | 修复后 |
| --- | --- | --- |
| 32550000 字节、350001 行文本与 700006 行 diff 的进程峰值 RSS | 629080 KiB（约 614 MiB） | 81996 KiB（约 80 MiB） |
| Git snapshot | 801–1286 ms | 424–596 ms |
| diff 页 | 932–975 ms | 551–581 ms |
| 文本预览页 | 47–64 ms | 58–69 ms；没有宣称这条路径提速 |
| 1000 会话、49516034 字节历史的热搜索 | 189–203 ms，每次读取 1000 份 JSON | 4.3–4.8 ms，未变化正文读取为 0 |
| 搜索管理器重启后复用索引 | 每次重新扫描正文 | 4.5–11 ms，未变化正文读取为 0 |

索引首次创建 / 旧缓存迁移的本次样本为 **4368.83 ms**，仍读取 1000 份正文；这是单次构建样本，不是重复磁盘冷启动范围。为精确哈希和总行数，每个文本 / diff 页仍扫描完整数据流；随机磁盘分页和取消未闭环。短查询、没有 trigram 的 SQLite 和文件时间戳对账仍有扫描成本。分页正文哈希与旧路径相同。

<a id="reverie-cli-feature-repairs-2026-10-05--产物和证据"></a>

### 产物和证据

可审阅的 [机器记录](verification/2026-10-05-feature-repairs.json) 随文档保存。下面是本地构建产物与验证材料，**被 Git 忽略，不随仓库克隆发布**：

- [Windows 安装包](../ReverieCli-ui/release/Reverie-Setup-2.5.0-x64.exe)、[便携包](../dist/Reverie-Portable-2.5.0-x64.exe)、[编译 GUI](../ReverieCli-ui/release/win-unpacked/ReverieUI.exe)、[CLI](../dist/reverie.exe)。
- [重启后的 GUI](../.runtime/feature-repairs-20261005/09-after-restart.png)、[只读审查格式错误](../.runtime/feature-repairs-20261005/10-review-final.png)、[模式菜单](../.runtime/feature-repairs-20261005/06-mode-menu.png)、[Engine 呈现](../.runtime/feature-repairs-20261005/native-engine-window.png)。
- [Python 最终回归](../.runtime/feature-repairs-20261005/python-final-2.log)、[Desktop 最终回归](../.runtime/feature-repairs-20261005/ui-final-2.json)、[PTY / 权限记录](../.runtime/feature-repairs-20261005/packaged-permission-pty.json)、[出站请求摘要](../.runtime/feature-repairs-20261005/provider-capture.jsonl)。
- [大 diff 对照](../.runtime/feature-repairs-20261005/workbench-performance.json)、[历史搜索对照](../.runtime/feature-repairs-20261005/search-performance.json)、[源文件保留检查](../.runtime/feature-repairs-20261005/baseline-comparison.json)。

<a id="reverie-cli-feature-repairs-2026-10-05--剩余边界"></a>

### 剩余边界

G12 逐来源 / 模型的 SSE、工具、思考签名、视觉及 Claude Desktop 两种模式未重新验收；10 月 4 日 JDW 远端异常只作为注明日期的历史采样。G14 通知点击 / 系统禁用组合、G15 真实授权集成、G16 完整检索质量基准、G18 Linux / macOS 与长时间运行、G20 高级渲染 / 音频 / Cubism、G21 生产游戏深度继续留在路线图。原生中文 IME 候选窗及屏幕阅读器仍未实机验收。

**便携版首次启动被自动审批拒绝**：工具只返回 `blocked by policy`，未说明具体原因；本轮没有通过另一机制重试同一个启动动作。便携包构建成功，但首次解压 / 启动尚未验证；使用不涉及 NSIS 解压清理的编译 GUI 完成上述运行检查。关于页可用于识别误开的旧安装版本，生成新便携包不会自动更新旧快捷方式。


---

<a id="reverie-cli-implementation-report-2026-09-30"></a>

<a id="reverie-cli-implementation-report-2026-09-30--reverie-desktop-s01s21-实施与验收记录"></a>

## Reverie Desktop S01–S21 实施与验收记录

> 原文件：`docs/REVERIE_CLI_IMPLEMENTATION_REPORT_2026-09-30.md`。以下为当时的记录；日期、测试数字、限制与旧实施提示词均保留，不代表本次重新验收。


**历史验收记录，状态说明更新于 2026-10-05。** 下表描述当时交付和证据，当前能力以 [功能状态](FEATURE_STATUS.md)为准。S06 的会话手动排序/状态过滤以及 Message context 汇总、重复轨迹栏已按后来用户要求移除；原有测试通过也不解除新审查确认的会话 pin 继承、目标输入和 checkout 协调缺口。见 [本次审查](#reverie-cli-feature-audit-2026-10-05)。

本次直接更新 `G:\Reverie\Reverie-Cli`，按 R1 → R4 实施默认 S01–S21。T01–T05、X01–X08、Local/Cloud 未纳入。9 月 30 日阶段遵照最初要求没有 commit/push；10 月 1 日用户追加“验证后提交”，授权深入验证后本地提交，未要求推送。新增修复、最终测试和截图见 [深入验证记录](#reverie-cli-deep-validation-2026-10-01)。验收使用的临时 Git 仓库、bare remote、私有恢复引用均位于项目内部。

**代码和界面已经接入全部 21 项，阶段验收仍有明确缺证据项。** “已实现”表示功能路径存在；“打包验证”只表示下面实际走过的场景。缺模型、连接授权或原生输入法证据的项目保持验收未完成，不能把单元测试当成真实服务成功。

<a id="reverie-cli-implementation-report-2026-09-30--1-保留与运行位置"></a>

### 1. 保留与运行位置

- 开始时读取 ROADMAP、新增清单、差距分析，检查源码和 Git 状态，遵守用户提供的项目 guardrails。
- 原有未提交文件保存于 `.runtime/implementation-20260930/baseline/files`，Git 基线保存于 `baseline/status.txt` 和 `baseline/head.txt`。原有 RATS e2e 修改和 `result_images` 保留。
- 每次打包前备份已有 `release/win-unpacked/.reverie`，打包后恢复；测试使用独立 `PORTABLE_EXECUTABLE_DIR`，不会把测试配置写入原有打包数据目录。
- 9 月 30 日保留核对：原打包数据的 54 个文件哈希全部一致；无关 RATS e2e 文件与开工备份一致；提交前 HEAD 为 `67b9b28950cc20ebf4184dc235a4698ed178c5d0`。见 [保留证据](../.runtime/implementation-20260930/preservation-evidence.json)。10 月 1 日提交前再次核对，结果见深入验证记录。
- 验收目录 `.runtime/implementation-20260930/` 加入本地 Git `info/exclude`。临时文件、测试仓库、日志、截图、导出和备份都留在本项目内。
- 输出程序：[ReverieUI.exe](../ReverieCli-ui/release/win-unpacked/ReverieUI.exe)。本次验证 Windows x64 的实际编译内核和 Electron 包。

<a id="reverie-cli-implementation-report-2026-09-30--2-逐项状态"></a>

### 2. 逐项状态

| ID | 代码实现 | UI/UX 接入 | 已通过的验证 | 仍缺证据 / 验收边界 |
| --- | --- | --- | --- | --- |
| S01 | 输入区、状态、工作面板、阅读跟随控制；按项目/会话保留阅读位置 | 复用品牌、主题和原导航，回到最新；窄窗口输入区及面板适配 | R1 中英文/深浅截图；R2 输入器高度；R4 800/1024/1500 面板 | Windows 原生中文候选窗尚未实测 |
| S02 | v2 文本与有序附件草稿，兼容 v1；异步结果归属和失效校验 | 切换恢复、导入取消/失败可见；恢复后缺失或变更副本禁发 | 草稿持久化、真实文件、恢复校验测试；后台队列切会话回归 | 真实模型长任务切换缺证据 |
| S03 | 原生截图剪贴板、真实拖放/选文件，工作区引用与外部复制，限额、哈希、顺序 | 文件/缩略图卡、重排、删除、重试、固定副本、预览和纯附件发送入口 | R1 原生 CF_DIB→PNG、中文文件/外部文件真实导入；混合内容次序测试 | 纯图/混合输入的真实模型理解缺活动模型 |
| S04 | `@` 防抖检索、文件/符号行引用、最近引用；模型视觉能力未知时明确展示 | 上下键/Enter/Escape；路径与行；“本条上下文”汇总按 2026-10-02 用户修订移除 | 检索交互与模型能力拒绝测试，实际文件版本读取 | 真实符号检索大项目和视觉服务结果仍需补验收 |
| S05 | 持久队列、编辑/排序/删除、会话后台调度；安全点 Steer、协作 Stop/暂停、独立强停 | Queue/Steer 选择与快捷键、接收/等待/停止状态；重启队列暂停 | 队列不重启内核、后台不串草稿；RunControl、安全点、实际命令取消测试；R4 真实等待取消 | 真实模型持续调用中的 Steer/Stop/暂停及失败恢复仍缺模型 |
| S06 | 项目/会话置顶、手动顺序、状态/未读、运行归属；删除后台运行记录前拦截 | 原侧栏分组、排序按钮、状态过滤与入口 | 组织/偏好和切换交互测试，打包多目录会话截图 | 长时间后台模型事件通知需补真实任务 |
| S07 | 工作区/暂存区/提交/merge-base 分支/AI 轮次范围；全量元数据与懒加载分页 | 文件状态过滤、完整路径、并排/统一、换行/空白、真实行号 | 真实 Git 大 diff 分页、删除/二进制/未跟踪/重命名/冲突测试；打包真实两 hunk 浏览 | 极大型仓库的耗时范围未做性能结论 |
| S08 | 文件/区块暂存、取消暂存、版本检查、确认撤销；未跟踪删除独立确认 | 文件/区块入口、风险确认、失败保留状态、索引变化要求刷新 | 真实 Git 部分暂存/取消/撤销、旧索引保留、stale/index.lock 拒绝；打包 UI 部分暂存 | 特殊编码与复杂重命名区块可能由 Git 拒绝，错误可见，无强制覆盖 |
| S09 | 整个暂存区提交；显式远端/分支/SHA 普通推送和远端 ref 核对 | 提交内容清单、说明保留、推送计划确认、成功 SHA/失败输出 | 真实 hook 失败保留索引；打包 UI 部分提交、bare remote 普通推送 SHA 一致 | 真实托管远端凭据未使用；PR/CI 属排除的 T01 |
| S10 | 分支 upstream/tracking/最后提交/worktree 元数据；脏状态/占用/运行与终端预检 | 原分支弹层扩展元数据、实时刷新；占用目录可打开并创建会话；失败提示保留现场 | 原分支测试、真实 worktree 与 SDK 切目录；Git 运行期保护 | 已占用分支拒绝在当前目录直接切换 |
| S11 | 内核强制只允许审计的内置读取/检索；模型审查结果版本绑定、定位与反馈 | `/review`、明确范围/指定文件、发现状态、加入草稿、不自动执行修复 | 真实文件读允许、写入/命令拒绝；原文件不变；行反馈/协议测试 | 真实模型产生结构化发现、完整只读审查结果未验证 |
| S12 | 安全路径/行链接、分页文本/Markdown/图像、本地 PDF canvas、隔离静态 HTML | 源码/渲染、搜索/行定位、图片尺寸/缩放、前后产物、来源哈希/时间、阅读位置 | 打包真实 Markdown/图片/PDF/HTML；PDF 第 2 页实际像素；脚本/网络剥离 | Office/区域批注/内置交互浏览器不在默认范围 |
| S13 | node-pty 真 PTY、会话/根目录归属、多终端、resize、日志序号避免重建丢流；历史终端保守恢复 | xterm 搜索/复制/粘贴/Ctrl+C、PID/目录/退出码、选中日志入草稿、结束确认 | 打包原生 PTY 中文文件、Ctrl+C、持久日志、错误会话拒绝；双目录真实进程同时运行 | 原生中文 IME 候选窗与复杂 TUI 尚未实测 |
| S14 | 项目动作保存命令/相对目录/ENV 名称；真实 PTY 运行、初始化必须显式确认 | 动作编辑/取消/删除、运行确认、失败日志与重新运行入口 | 打包动作正确 cwd、实际 exit 7、配置初始化不会自动执行 | 真实项目开发服务的长期占用/退出需项目具体命令补测 |
| S15 | 精确审批 owner；命令/cwd/参数/已知路径、一次/会话作用域；重复解决与停止审批拦截 | 范围卡、个性化拒绝、提交防重复、未知网络明确标注 | 审批 typed bridge 回归；后端拒绝非法/重复操作的原测试 | 模型触发的两个并行真实审批缺活动模型；软件权限不代表 OS 沙箱 |
| S16 | 每轮身份/输入/模型/分支/PID/事件/结果/前后快照；异常不自动重放；脱敏导出 | 运行记录、时间线、返回所属会话、差异范围与保守恢复提示 | 真实独立内核失败记录、项目内 Markdown 导出；截断 JSONL/重启恢复/秘密脱敏测试 | 外部工具部分副作用只能标为待核对；没有宣称自动恢复所有动作 |
| S17 | 用户目标、条件、步骤状态/来源、验证命令与修订；pause/continue 到安全边界 | 输入区目标摘要、编辑/重排/撤下、用户确认验证、暂停/继续说明 | 打包目标实际磁盘持久化；RunControl 线程边界暂停/恢复测试 | 真实长模型任务与后台命令边界暂停尚未验收 |
| S18 | 按 run+kind 去重的完成/失败/审批记录，持久化、静音、实际 OS 状态记录；修正最小化窗口仍报焦点时跳过通知 | 全局未读提示、通知列表/过滤/已读、项目+会话回跳 | 打包真实失败产生应用内记录与会话身份；实际 HWND 最小化后 Windows 通知返回 `shown` | 系统通知点击回跳、OS 禁用设置下的场景及模型审批通知仍缺实测 |
| S19 | 受管本地 detached worktree；显式改动复制/删除；可恢复归档、原始字节/忽略文件/祖先保留；拒绝嵌套/不安全路径 | 创建/基础 ref/复制清单/确认、打开绑定会话、归档范围/忽略选择、恢复原路径、失败保留输入 | 单测真实 Git 的未推送祖先、CRLF 字节、stale/嵌套拒绝；打包两个目录创建、脏归档/恢复、主目录索引不变 | 外部独立进程仍可能改文件：版本变化即拒绝；复杂 submodule 场景只提供拒绝策略 |
| S20 | 每轮独立实际 SDK 内核、最多 4；同 checkout 写入 FIFO；独立目录并行；事件/审批/停止路由 | 后台执行器/PID/等待原因/所属会话入口与取消；切会话继续运行 | 打包两个真实核心 PID 与目录归属不同；同目录等待和无工具取消；4 槽单测；双 PTY 各写自己目录 | 两个模型同时工具写入/独立审批/单独 Stop 的完整模型验收未完成 |
| S21 | 使用实际 listTools/listSkills/listPlugins/RATS cached 数据，作用域/固定/遮蔽/启用/信任/权限交集 | 生效能力页；原技能/插件/RATS 页面保留，真实 enable/disable 入口；授权未报告即未知 | 打包实际内核工具目录、技能/插件/RATS 状态读取 | 没有真实认证插件或连接服务；不把“安装/启用/连接配置”标为已授权 |

<a id="reverie-cli-implementation-report-2026-09-30--3-构建与验证产物"></a>

### 3. 构建与验证产物

阶段均实际编译 Python 内核、TypeScript 主进程和 Vite renderer，执行 Electron 目录打包，并启动输出 `ReverieUI.exe`，不是开发服务器。

| 阶段 | 编译/打包日志 | 实际运行证据 | 关键截图 |
| --- | --- | --- | --- |
| R1 | [r1-pack.log](../.runtime/implementation-20260930/r1-pack.log) | [r1-runtime-evidence.json](../.runtime/implementation-20260930/r1-runtime-evidence.json) | 截图目录的 `r1-*`，含中英文、深浅主题、四种界面 |
| R2 | [r2-pack.log](../.runtime/implementation-20260930/r2-pack.log) | [r2-runtime-evidence.json](../.runtime/implementation-20260930/r2-runtime-evidence.json) | `r2-*`，含 Git 推送、预览与窄窗口输入 |
| R3 | [r3-pack.log](../.runtime/implementation-20260930/r3-pack.log) | [r3-runtime-evidence.json](../.runtime/implementation-20260930/r3-runtime-evidence.json) | [真实 PTY](../.runtime/implementation-20260930/screenshots/r3-real-pty.png)、[失败动作](../.runtime/implementation-20260930/screenshots/r3-action-failure.png)、[PDF 第二页](../.runtime/implementation-20260930/screenshots/r3-pdf-page2.png) |
| R4 | [r4-pack.log](../.runtime/implementation-20260930/r4-pack.log) | [r4-runtime-evidence.json](../.runtime/implementation-20260930/r4-runtime-evidence.json) | [目录](../.runtime/implementation-20260930/screenshots/r4-worktrees.png)、[归档范围](../.runtime/implementation-20260930/screenshots/r4-archive-scope.png)、[窄窗口](../.runtime/implementation-20260930/screenshots/r4-worktrees-dark-800.png) |
| 最终修订 | [内核与全包](../.runtime/implementation-20260930/final-pack.log)、[最终 UI 重编译与目录打包](../.runtime/implementation-20260930/delivery-pack.log)、[最小化通知修订包](../.runtime/implementation-20260930/notification-fix-pack.log) | UI 修订版重跑 R3/R4；最后的通知修订单独实际启动验证，以对应 JSON 为准 | 最终重跑覆盖同名截图；共保存 44 张界面截图 |

- 最终 `npm run typecheck` 通过，包括 917 个中英文翻译、77 个模板校验。完整 UI 测试 **190 passed、1 skipped**，见 [final-ui-tests.log](../.runtime/implementation-20260930/final-ui-tests.log)；新增大 diff 行号、二进制/删除/重命名/冲突、worktree 字节恢复、执行器协调、后台队列归属、日志恢复和脱敏测试。
- 分阶段打包运行断言：R1 25 项、R2 19 项、R3 14 项、R4 17 项均通过。这些断言覆盖所列真实本地路径，不能替代下节缺模型或授权的验收。
- 最后单独补测原生后台通知：实际 Reverie HWND 最小化前后均为 true，真实失败运行对应的通知返回 `shown`。见 [notification-runtime-evidence.json](../.runtime/implementation-20260930/notification-runtime-evidence.json)。没有把此前 `not requested` 的尝试当成通过证据。
- 相关 Python 测试 **119 passed**：[r4-python-tests.log](../.runtime/implementation-20260930/r4-python-tests.log)。覆盖桌面 bridge、真实文件读取/写入拒绝、输入次序、控制点、命令执行、batch prompt 与权限。
- 本机原先 node-pty 源码重建报 `MSB8040`（缺 Spectre 库）。本次使用依赖包携带的 Windows N-API 二进制，保留 ASAR unpack 路径并关闭重复 native rebuild；实际包内 PTY 已运行。没有安装或改动系统 Visual Studio。
- jsdom 缺 canvas 的提示不作为 PDF/终端渲染通过证据；PDF/PTY 成功以真实 Electron 截图、文件、像素和进程结果为准。

<a id="reverie-cli-implementation-report-2026-09-30--4-明确未完成的验收"></a>

### 4. 明确未完成的验收

1. 保留的独立打包配置没有活动模型。真实请求得到 `No active model is configured.`（此前显式空选择也得到 `Unknown or ambiguous model for Manual Model`）。10 月 1 日仅在独立测试配置中使用本机 HTTP 协议记录端点，验证实际内核图片传输、顺序、哈希和落盘，不进行视觉推理。因此纯图片理解、长任务 Steer/暂停/Stop、模型只读发现、两 worktree 同时模型写入与审批隔离的完整服务验收仍未完成。
2. 没有真实认证插件、托管远端凭据或活跃授权 RATS 服务参与本次验证。页面显示实际内核可调用工具、安装/信任状态及未知授权；账户与服务操作成功尚未证明。
3. IME `isComposing` 和 229 防误发已实现；中文路径、内容与真实 PTY 已验证。原生中文输入法候选窗、组合输入后 Enter 的完整人工实机验收仍缺证据。
4. Windows 最小化后台通知已获得真实 `shown` 事件，应用内列表独立保留。系统通知点击回跳与 OS 禁用通知设置的实机场景未测试；审批通知仍需真实模型触发。`requested` 本身不视为送达通过。

<a id="reverie-cli-implementation-report-2026-09-30--5-使用入口"></a>

### 5. 使用入口

输入器：剪贴板图片、附件按钮/拖放、`@`、上下文详情、运行中的 Queue/Steer/Stop。队列重启后暂停，需显式继续。

“工作面板”：Git → 范围、文件/区块、提交、普通推送；文件预览 → 路径/行、图像/PDF/静态 HTML；只读审查 → 明确范围或指定文件；运行与终端 → 独立工作目录、用户终端、项目动作、运行记录、目标、通知、生效能力。

独立工作目录的初始化不会自动执行。打开目录后在项目动作中检查命令并确认运行。归档前检查所有忽略文件；默认保留。恢复后的 HEAD 分离，原提交祖先和本地恢复引用保留。归档不使用强制 dirty 删除；进行中的任务和终端必须先结束。

退出有运行中的后台任务/终端时给出目录、会话和 PID 影响说明。普通停止优先合作取消；强制停止需要核对部分副作用。未知状态不会自动重放文件写入或命令。


---

<a id="reverie-cli-jdw-compatibility-2026-10-04"></a>

<a id="reverie-cli-jdw-compatibility-2026-10-04--jdw--claude-messages-兼容性检查2026-10-04"></a>

## JDW / Claude Messages 兼容性检查（2026-10-04）

> 原文件：`docs/REVERIE_CLI_JDW_COMPATIBILITY_2026-10-04.md`。以下为当时的记录；日期、测试数字、限制与旧实施提示词均保留，不代表本次重新验收。


本报告对应附加的 justwoker 异常报告。原报告属于待核实的输入；以下把实际测得的行为与推测分开。用户确认 Claude Desktop 的普通聊天和 Code 模式都遇到了问题。

<a id="reverie-cli-jdw-compatibility-2026-10-04--当前结论"></a>

### 当前结论

Reverie 已补齐非流式 Anthropic Messages 的思考块保存、工具结果即时落盘、终止原因处理及空响应报错。真实 Anthropic SDK、本地 HTTP 服务、真实 `file_ops` 和 SessionManager 的完整工具往返测试通过。

JDW 这条线路目前仍有网关问题。修改 Reverie 请求格式不能恢复被上游丢弃的文本或工具定义，也不能让 Claude Desktop 自动接受不完整的 SSE。当前可用的非流式文本请求不等于完整的编程客户端兼容。

<a id="reverie-cli-jdw-compatibility-2026-10-04--对-jdw-的三次实际请求"></a>

### 对 JDW 的三次实际请求

使用本机既有 JDW 凭据，探测 `claude-opus-4-8` 的 Anthropic Messages 接口；每次限制 192 个输出 token。没有改动用户凭据或提供商配置，日志不含密钥。

| 请求 | HTTP / 耗时 | 实际内容 | 结论 |
| --- | --- | --- | --- |
| 非流式短文本 | 200 / 5.23 秒 | `text`，准确返回指定短文本，`end_turn` | 此次文本请求成功 |
| 非流式，强制自定义 `reverie_probe_echo` | 200 / 5.51 秒 | `thinking` + `text`，没有 `tool_use`，`end_turn` | 此次客户端工具选择未被遵守 |
| 流式短文本 | 200 / 3.07 秒 | 只有 `message_start`、`message_delta`、`message_stop`；文本增量为 0 | 此次 SSE 没有交付文本 |

三次响应申报约 10,378–10,390 个 `cache_creation_input_tokens`。这远大于这个小探测的预期，需服务商解释输入变换和计费口径；响应本身不能证明它具体注入了 Kiro 提示，也不能证明最终账单如何计算。未复测报告里的 OpenAI 403，因此不把它列为本次验证结果。

原始结构化证据：[`provider-live-probe.json`](../.runtime/ui-design-20261004/provider-live-probe.json)。结果仅代表这三次请求，不推广为所有模型、所有分组或所有工具都失败。

<a id="reverie-cli-jdw-compatibility-2026-10-04--reverie-里的使用方式与代码变化"></a>

### Reverie 里的使用方式与代码变化

JDW 的 Claude 模型应使用 **Anthropic Messages** 格式，并选择网关实际提供的模型 ID。当前 `dist/.reverie/config.json` 中 JDW 的格式为 `openai-chat`，选中模型 ID 与这次测试的 Claude ID 不一致；本任务没有擅自重写该配置。请在模型与提供商设置中确认格式和模型，输入栏的波形按钮可切换到非流式。

请求遵守原生 Messages 契约：`stream: false`、工具 `name/description/input_schema`、assistant 的 `tool_use` 与 user 的 `tool_result` 使用同一个 ID。端点归一化沿用原来的实现，避免重复 `/v1`；没有添加把任意工具参数改成服务商内部名称的适配。

此次实现与验证包括：

- 非流式 `thinking` / `redacted_thinking` 原生块和签名保存在历史中，下一次 Anthropic 请求原样回传；切换其他提供商时不发送该专用字段。
- 收到工具调用与结果时立即保存，而不是等待整个轮次结束。重启后已保存的结果可恢复，缺失结果标记为可能中断。
- 工具执行仍按真实 `tool_use` 内容判断；即使某网关把 `stop_reason` 错写为 `end_turn`，有效工具调用仍能执行。这个已有行为现在有完整 HTTP 回归覆盖。
- 使用实际 `stop_reason` 识别完成和 `max_tokens` 截断；截断续写有上限。
- 自定义提供商宣称有输出 token 却没有文本或客户端工具时，明确报错，不在这个路径自动重复请求。

测试文件：[`test_anthropic_non_streaming_contract.py`](../ReverieCli-py/tests/test_anthropic_non_streaming_contract.py)，4 项通过。覆盖实际 SDK HTTP 序列化、中文路径文件读取、工具 ID 配对、签名回传、历史落盘、正常结束、截断续写、空响应只请求一次。另有 158 项相关回归和最后 48 项 agent / Skill / 只读工具检查通过；这些是有重叠的测试集，不能相加为独立用例总数。

<a id="reverie-cli-jdw-compatibility-2026-10-04--claude-desktop普通聊天与-code"></a>

### Claude Desktop：普通聊天与 Code

使用 Desktop 自己的第三方推理配置。按官方说明，在 **Help → Troubleshooting → Enable Developer Mode** 启用后重启，再进入 **Developer → Configure Third-Party Inference**；只设置 `ANTHROPIC_BASE_URL` 或 Claude Code 的 `settings.json` 并不能配置 Desktop 的网关路由。参考 [Desktop 连接说明](https://code.claude.com/docs/en/llm-gateway-connect#desktop-app)。

在该窗口选择 Gateway，填入服务商提供的网关根地址、模型和 API key，并匹配认证方式。本次 JDW 的实际请求使用 `x-api-key`；不要在 Desktop 中误选默认 Bearer。若走自行搭建的修复代理，则填代理地址和代理自身要求的认证方式。官方配置字段是 `inferenceProvider`、`inferenceGatewayBaseUrl`、`inferenceGatewayApiKey`、`inferenceGatewayAuthScheme`。参考 [Desktop Gateway 配置](https://claude.com/docs/third-party/claude-desktop/gateway)。

这只能纠正配置。Desktop 网关要求 Messages 的流式与工具调用都工作，因此当前 JDW 线路仍需服务商修复，或切换到已验证的原生 Messages 线路。没有在正在使用的 Claude Desktop 中替换配置或进行端到端会话测试，本报告不声称已修好该应用。

<a id="reverie-cli-jdw-compatibility-2026-10-04--服务商必须修复什么"></a>

### 服务商必须修复什么

1. 原样保留客户端的 system、messages、tools、tool_choice、工具参数名与调用 ID。不能把客户端工具换成服务端自带的工具，也不能把内部 agent 的轨迹冒充客户端工具结果。客户端工具契约见 [官方 tool use 文档](https://platform.claude.com/docs/claude/docs/tool-use)。
2. SSE 必须交付内容块、增量、块结束，再交付终止原因与用量；流式文本不能只发送消息开始和结束。保持思考签名、相关请求字段/头与错误正文；长等待期间及时发送 keep-alive。参考 [官方网关协议要求](https://code.claude.com/docs/en/llm-gateway-protocol)。
3. 明确公布线路是否改变提示、工具、模型能力和用量，解释本次小请求里的大量缓存创建 token。若此分组只是包裹服务端 agent 的线路，提供独立的原生 Messages 入口。

如果只有上游非流式接口能可靠工作，可在自己控制的代理中采用临时转换：接收客户端 `stream: true`，向上游发送 `stream: false`，等待期间发送 ping，再把校验过的原生内容块转换为完整 SSE。保留 `tool_use` 的 JSON 输入、思考签名、用量和真实结束原因；空内容应报错，不能伪造成功或自动重发计费请求。这是缓冲式兼容方案，会延后可见内容，**无法恢复本来就被上游丢弃的工具**。因此仍需一个遵守客户端工具契约的上游；本任务没有部署此代理。


---

<a id="reverie-cli-platform-language-audit-2026-10-05"></a>

<a id="reverie-cli-platform-language-audit-2026-10-05--reverie-cli-功能复审附录跨平台身份与语言覆盖2026-10-05"></a>

## Reverie CLI 功能复审附录：跨平台身份与语言覆盖（2026-10-05）

> 原文件：`docs/REVERIE_CLI_PLATFORM_LANGUAGE_AUDIT_2026-10-05.md`。以下为当时的记录；日期、测试数字、限制与旧实施提示词均保留，不代表本次重新验收。


> 本附录是 10 月 5 日修复报告与 [MCP 客户端边界附录](#reverie-cli-feature-audit-addendum-2026-10-05) 之后的第三轮定向源码复审。范围是 RATS 提供者身份校验的平台条件、回归测试的平台门禁、Context Engine 的多语言解析依赖和 LSP 覆盖面。**没有修改任何运行时代码**；本轮只登记缺口并同步文档。

起始及结束 HEAD 均为 `127c39769217d87dd7647a3c6b296e2629d8f9ff`，工作区保留既有未提交改动，版本 2.5.0。

<a id="reverie-cli-platform-language-audit-2026-10-05--核对范围"></a>

### 核对范围

| 对象 | 核对内容 |
| --- | --- |
| [rats.py](../ReverieCli-py/reverie/rats.py) | `_reverie_engine_executable`、`_reverie_engine_process`、`_windows_product_names`、`_windows_process_matches_executable`、`_product_name_validator` 的平台分支 |
| [tests/](../ReverieCli-py/tests) | `os.name != "nt"` / `platform.system() != "Windows"` 的 `skipif` 门禁与函数体内平台分支 |
| [treesitter_parser.py](../ReverieCli-py/reverie/context_engine/parsers/treesitter_parser.py) | `SUPPORTED_LANGUAGES`、`can_parse`、`_get_parser`、`_walk_tree`、`_parse_with_regex` 的语言分支一致性 |
| [setup.py](../ReverieCli-py/setup.py)、[requirements.txt](../ReverieCli-py/requirements.txt)、[reverie.spec](../ReverieCli-py/reverie.spec)、[build.bat](../ReverieCli-py/build.bat) | tree-sitter 依赖在安装、打包与构建脚本中的实际传递路径 |
| [lsp_manager.py](../ReverieCli-py/reverie/context_engine/lsp_manager.py) | `SERVER_DEFINITIONS` 与本仓已有解析器语言的对照 |

<a id="reverie-cli-platform-language-audit-2026-10-05--新增缺口"></a>

### 新增缺口

| ID | 当前行为 | 源码证据 | 用户影响 / 判定 |
| --- | --- | --- | --- |
| G28 | RATS 提供者身份校验在非 Windows 上**失败开放**。可执行文件身份降级为 `executable.is_file()`；活动进程校验降级为 `os.kill(pid, 0)` 存活探测，且 `PermissionError` 返回 `True`。 | `rats.py`：`_reverie_engine_executable` 在 `os.name != "nt"` 时直接返回 `is_file()`；`_reverie_engine_process` 的非 Windows 分支只做存活探测；`_product_name_validator` 的 docstring 明确这是刻意降级（"Off Windows there is no equivalent resource to read, so this degrades to the existence check rather than refusing every executable"）。 | 在 Linux / macOS 上，描述符所指路径只要存在就通过身份校验，任何同用户进程持有该 PID 即视为该提供者。描述符 schema、注册表成员、端点格式、`hello` 一致性、请求 ID 与响应哈希检查仍然生效，所以这不是"任意本地服务都能接入"；但 Windows 上由 PE `ProductName` 与 `QueryFullProcessImageNameW` 提供的那层身份保证在其他平台不存在。源码确认，未在非 Windows 主机复现。 |
| G29 | 回归套件有 11 处 Windows-only `skipif` 门禁，另有 3 处函数体内平台分支；非 Windows CI 静默跳过这些断言。 | `tests/test_rats_runtime.py` 6 处（RATS 身份、进程映像校验、真实 Engine E2E）、`tests/test_runtime_plugins.py` 3 处（Blender 便携包部署）、`tests/test_tooling_upgrades.py` 1 处（`taskkill` 进程终止）、`tests/test_config_repair.py` 1 处（Windows 盘符路径规范化）；函数体内分支见 `test_rats_engine_task_e2e.py:53`、`test_tooling_upgrades.py:649`、`test_workspace_guard.py:383`。 | 文档中的"1761 通过 / 1 跳过"是 Windows 主机的数字；在其他平台同一套件的跳过数更高，而跳过项正好覆盖 G28 所在的身份校验路径。这不是失败，但不能当成跨平台验收。 |
| G30 | tree-sitter 是可选 extra。`install_requires` 不含它，`.[build]` 不含它，`reverie.spec` 的 `hiddenimports` 没有任何 `tree_sitter*` 条目，`build.bat` 只安装 `-e ".[build]"`。缺失时 `_init_tree_sitter` 吞掉 `ImportError` 并静默切到正则回退。 | `setup.py`：`extras_require["treesitter"]` 有 12 个固定版本包，`install_requires` 与 `extras_require["build"]` 都没有；`reverie.spec:9-16` 的 `hiddenimports`；`build.bat:137`；`treesitter_parser.py:108-121` 的 `except ImportError` 分支。 | JavaScript / TypeScript / C / C++ / C# / Rust / Go / Java / HTML / CSS 的符号与依赖抽取精度取决于安装方式，且降级没有任何用户可见提示。`dist/reverie.exe` 的实际语法树覆盖由构建机 venv 状态决定（`--reuse-venv` 下曾装过 extra 的 venv 会被打进去），spec 没有把它固定下来。Python / Lua / GDScript / 配置 / 文档 / 脚本走本仓原生解析器，不受影响。 |
| G31 | `zig` 是死配置：`SUPPORTED_LANGUAGES` 登记 `.zig` 且 `can_parse` 认领它，但 `_get_parser` 没有 `zig` 分支，`extras_require["treesitter"]` 没有 `tree-sitter-zig`，`_parse_with_regex` 也没有 `zig` 分支。模块 docstring 仍把 Zig 列为受支持语言。 | `treesitter_parser.py`：`SUPPORTED_LANGUAGES['zig']`；`_get_parser` 的语言 `if/elif` 链落到 `else: return None`（该链还保留一个 `python` 分支，而 `.py` 由原生 `python_parser.py` 处理）；`_walk_tree` 调用的 `_extract_zig` 已定义但不可达；`_regex_parse_zig` 不存在。 | `.zig` 文件被解析器认领后产出 0 符号、0 依赖、**0 错误**——与"解析成功但文件里没有符号"无法区分。模块文档对 Zig 的支持声明不成立。 |
| G32 | LSP 桥只定义 6 个服务器（pyright-langserver、pylsp、typescript-language-server、gopls、rust-analyzer、clangd）。 | `lsp_manager.py:35-42` 的 `SERVER_DEFINITIONS`。 | Java、C#、Lua、GDScript 即使本机装了语言服务器也不会被发现，而这些语言在本仓已有解析器或语法树分支。LSP 本身是可选增强，缺少定义不影响基础检索。 |

<a id="reverie-cli-platform-language-audit-2026-10-05--运行时复现"></a>

### 运行时复现

在隔离临时目录上实例化 `TreeSitterParser`（本机未安装 `treesitter` extra）：

| 观察项 | 结果 |
| --- | --- |
| `_tree_sitter_available` | `False`（`import tree_sitter` 抛 `ModuleNotFoundError`，被静默吞掉） |
| `SUPPORTED_LANGUAGES` 键 | `c`、`cpp`、`csharp`、`css`、`go`、`html`、`java`、`javascript`、`rust`、`typescript`、`zig` |
| `.zig` | `can_parse` = `True`，`_get_parser('zig')` = `None`，解析结果 0 符号 / 0 依赖 / 0 错误 |
| `.ts`（一个导出函数 + 一个导出类） | 正则回退抽出 2 个符号，0 错误 |
| 方法存在性 | `_extract_zig` 已定义（不可达），`_regex_parse_zig` 不存在 |

由此可知：本机 **1761 通过 / 1 跳过** 的全量 Python 回归是在 `tree_sitter` 完全缺失的环境下跑完的，只覆盖了正则回退路径。全仓没有任何测试文件引用 `tree_sitter` / `TreeSitterParser` / `treesitter`；唯一引用是 [check_dependency_pins.py](../ReverieCli-py/scripts/check_dependency_pins.py)，它只核对 `setup.py` 的 treesitter 组与 `requirements.txt` 的固定版本是否一致，不验证任何解析行为。

<a id="reverie-cli-platform-language-audit-2026-10-05--本轮没有发现的问题"></a>

### 本轮没有发现的问题

这些是明确的否定结论，不是未检查项：

- Python 核心与 Desktop 源码中没有 `TODO` / `FIXME` / `HACK` 标记的未完成实现。
- `NotImplementedError` 只出现在合法的抽象基类上（解析器 / 提供者基类），没有被当成"待实现"占位符。
- Desktop 渲染层没有发现"即将推出"式的惰性入口；`@` / `/` 候选、模式菜单、命令面板的空状态文案都对应真实空数据，不是功能占位。

<a id="reverie-cli-platform-language-audit-2026-10-05--文档同步"></a>

### 文档同步

- [功能状态](FEATURE_STATUS.md) 增加 G28–G32，并在 Context Engine、RATS 与发布 / 平台三行注明对应边界。
- [路线图](ROADMAP.md) 为跨平台提供者身份、平台测试门禁、语法树依赖传递、`zig` 死配置和 LSP 覆盖面分别登记闭环条件。登记缺口不等于授权实施所有可选扩展。
- [RATS / RTP](RATS_RTP.md) 的信任边界一节明确写出非 Windows 的降级行为，不再只说"Windows 上额外要求 ProductName"。
- [开发指南](DEVELOPMENT.md) 说明 tree-sitter 是可选 extra、哪些语言在缺失时退回正则、以及打包不固定该依赖。
- 机器可读结论见 [结构化摘要](verification/2026-10-05-platform-language-audit.json)。

<a id="reverie-cli-platform-language-audit-2026-10-05--验证边界"></a>

### 验证边界

本轮证据是源码路径审阅加一次本机 Windows 解析器探测。没有在 Linux / macOS 主机上复现 G28 / G29，没有安装 `treesitter` extra 对照语法树与正则回退的抽取差异，没有重新打包 `dist/reverie.exe` 去确认其内是否含有语法树绑定，也没有重跑或改写既有的全量测试数字。G28 是源码确认的信任边界降级，不是已观察到的被冒充事件。


---

<a id="reverie-cli-request-profile-repairs-2026-10-05"></a>

<a id="reverie-cli-request-profile-repairs-2026-10-05--reverie-cli-请求个人资料与-mcp-修复验证2026-10-05"></a>

## Reverie CLI 请求、个人资料与 MCP 修复验证（2026-10-05）

> 原文件：`docs/REVERIE_CLI_REQUEST_PROFILE_REPAIRS_2026-10-05.md`。以下为当时的记录；日期、测试数字、限制与旧实施提示词均保留，不代表本次重新验收。


本轮依据用户要求继续修复此前统计的问题，并处理 Stop 等待、流式切换、用户名称 / 裁剪头像、对话左右布局和请求启动开销。工作区为 `G:\Reverie\Reverie-Cli`，版本 2.5.0；没有 commit / push，原有未提交工作保留。此前 [功能审计](#reverie-cli-feature-audit-2026-10-05)、[首轮修复](#reverie-cli-feature-repairs-2026-10-05)和 [MCP 复审](#reverie-cli-feature-audit-addendum-2026-10-05)保留历史结论；当前状态以 [FEATURE_STATUS](FEATURE_STATUS.md) 为准。

<a id="reverie-cli-request-profile-repairs-2026-10-05--等待原因与修复"></a>

### 等待原因与修复

| 原因 | 本轮处理 | 已验证的边界 |
| --- | --- | --- |
| Stop 只设置协作标志，同步网络调用要返回才能到安全点 | 用同一个异步 I/O 循环提供同步 SDK / requests 适配，取消等待并关闭所属上游 socket；curl 注册进程终止回调 | 等待响应头、读取响应体、流停滞、重试等待均可取消；工具执行仍有自己的安全边界 |
| 流式开关保存后刷新插件、模型目录和工作区 | 保留真实校验 / 保存，去掉这项设置的无关刷新；界面先反馈、保存失败回滚 | 草稿保留；配置保存期间避免下一轮使用旧模式；其他设置仍按各自语义刷新 |
| 每轮重新启动独立内核 | 最多四个内核，空闲时复用；同 checkout 写锁、审批归属与运行记录仍保留 | 并行任务不共用正在执行的内核；失败内核回收；异步回收与退出竞争有回归 |
| SDK 与外层重试叠加 | OpenAI / Anthropic SDK 内置重试设为 0，外层统一处理请求开始前的可重试错误；等待可以中断 | 不重放已开始输出的流；连接复用不改变鉴权和请求内容 |
| SDK 收到 SSE 结束标记后没有读完 HTTP 最后帧 | 清理最多 50 ms / 64 KiB 的尾部后释放响应，健康连接进入共享池 | Content-Length 与 chunked 均有连续三次请求的连接复用验证；停滞尾部有时间上限；取消跳过清理等待 |
| 压缩 / Codex 交接 / 刷新请求绕过取消传输 | 改为同一可取消 POST 路径，压缩重试可中断，停止不会进入压缩异常回退 | 三类请求等待响应头时均有真实 socket 取消验证 |

共享池按代理 / TLS 配置隔离：最多 32 个连接、16 个空闲连接、120 秒空闲保留。短生命周期 SDK 客户端不拥有进程级池。system curl 仍是每次请求的独立进程。网络后端使用 [HTTPcore 的公开异步接口](https://www.encode.io/httpcore/network-backends/)。

<a id="reverie-cli-request-profile-repairs-2026-10-05--用户名称头像和左右布局"></a>

### 用户名称、头像和左右布局

入口是 **设置 → 对话显示**。名称沿用现有偏好存储；新增上传、拖动、缩放、水平 / 垂直键盘滑块、取消、保存和移除头像。输入支持不超过 20 MB 的 PNG / JPEG / WebP / GIF，保存的是选中的 **256 × 256 PNG**，偏好载荷上限 512 KiB。

历史消息和当前轮使用相同头像组件；用户名称 / 头像及气泡在右侧，模型回答在左侧。测试用 600 × 300 红蓝两色图片，实际上传并选择红色半边；输出尺寸及中心像素 `(227, 38, 54)` 与选区一致，取消不会覆盖，刷新和退出重开后名称、头像、历史均保留。

打包实测发现 renderer CSP 缺少 `img-src blob:`，会拦截上传图片的临时预览地址。此问题已经修复并补上回归；仅 jsdom 的 Image / canvas mock 无法验证这一点。

<a id="reverie-cli-request-profile-repairs-2026-10-05--mcp-已修复范围"></a>

### MCP 已修复范围

- **G25 已修复**：工具、资源、提示目录跟随 `nextCursor`，重复 / 非法游标明确失败，发现时间预算仍生效；不再静默保留第一屏目录。
- **G27 部分修复**：保留文本、structuredContent、资源元数据和工具错误；支持的图片 / WAV / MP3 音频转为类型化 relay。OpenAI Chat 接收对应图片 / 音频，Anthropic 与 Responses 转换支持的图片，对不支持的音频给出明确说明。超过 12 MiB 编码、无效 base64、未知媒体类型不给模型堆入原始 JSON。用户专属文本 / 图像 / 音频块不进入模型消息。
- 嵌入二进制资源、真实媒体服务器与逐模型视觉 / 音频兼容仍有限；G24 的提示获取 / 模板 / 订阅 / 可选客户端能力，以及 G26 的托管 OAuth，仍未闭环。

协议对照为同版本的 [MCP Tools](https://modelcontextprotocol.io/specification/2025-06-18/server/tools)、[Resources](https://modelcontextprotocol.io/specification/2025-06-18/server/resources)和 [Prompts](https://modelcontextprotocol.io/specification/2025-06-18/server/prompts)。离线转换通过不代表每个远端服务或模型已经验收。

<a id="reverie-cli-request-profile-repairs-2026-10-05--测试与构建"></a>

### 测试与构建

| 检查 | 本轮结果 |
| --- | --- |
| Python 最终全量回归 | **1826 通过 / 1 跳过**，370.26 秒 |
| 网络取消 / 连接复用 / 提前关闭 / 重试 / 预请求 | **59 通过**；45 次取消 = 5 种传输 × 3 阶段 × 3 次重复 |
| 桌面默认全量回归 | **264 通过 / 1 跳过**，类型与 971 条翻译 / 82 个模板检查通过 |
| 外部 Engine RATS 独立回归 | **11 通过** |
| Windows CLI、内置 kernel、桌面安装包 / 便携包 | 重新构建成功；独立 CLI 与内置 kernel 的 `--kernel-info`、SDK ready / shutdown 协议均通过 |
| 新打包 Electron 实际流程 | 裁剪 / 取消 / 保存 / 重开、开关、连续模型请求、socket 取消、下一轮恢复、同内核 / 同连接复用均通过，无 renderer page error |

初次 Python 全量是 1812 通过、3 失败、1 跳过：新连接池退出异常未记录、Skill fixture 受真实用户目录影响，以及实际 Engine 调用超时（当时构建也在运行）。前两项已经修正；Engine 单独运行通过。网络矩阵也曾在首次 curl 模块导入时超过连接等待门限，测试已把模块加载与网络连接阶段分开。旧失败记录保留，最终全量结果单独记录，1826 项通过、1 项跳过；退出重开测试后验证应用及其内核已清理。

新界面构建 ID 为 **`cac49bb794e88eaa`**，构建时间 **2026-10-05T14:50:50.057Z**。已实测的启动文件为 `ReverieCli-ui/release/win-unpacked/ReverieUI.exe`，内核为同目录 `reverie.exe`；安装包 / 便携包构建成功不代表首次安装或 NSIS 解压流程已重新验收。

<a id="reverie-cli-request-profile-repairs-2026-10-05--实际时间测量"></a>

### 实际时间测量

本地 HTTP fixture 是真实 socket、真实 SDK 与新打包应用，模型只返回固定短文本。它能验证客户端生命周期和启动开销，不能证明远端模型速度。

| 测量 | 样本 / 结果 | 方法与限制 |
| --- | --- | --- |
| 开关界面反馈 | 6 次，**0.8–1.3 ms** | renderer `MutationObserver` 和 `performance.now()`，实际按钮事件与 DOM 属性 |
| 开关持久化结束 | 6 次，**67.9–89.6 ms** | 同一 renderer 计时，包括真实 IPC / Python 配置保存 |
| 点击 Stop 到服务端断开 | 6 次，**16.68–22.09 ms** | 等响应头 / 停滞流各三次；含 Playwright 点击开销，服务端检测 EOF / reset |
| Stop 到界面结束运行 | 6 次，**236.98–350.06 ms** | 包含持久记录和界面回收；已进入工具动作不在这个 HTTP 测试范围 |
| 新内核第一轮点击到 HTTP 请求 | **3987.89 ms** | 包括新会话、内核启动、Git 快照和上下文准备 |
| 同内核后续五轮点击到 HTTP 请求 | **697.08 / 846.93 / 1242.32 / 4475.76 / 1548.30 ms** | 中位数 1242.32 ms，有 4475.76 ms 长尾；全流程仍有准备开销，不声称每次请求都在一秒内 |
| 连接 / 内核复用 | 两轮同 PID **49740**、同服务端连接 **106**；停止后五轮同连接 **480** | 取消会丢弃被停止的连接；后续请求恢复新的健康连接并复用 |

<a id="reverie-cli-request-profile-repairs-2026-10-05--当前真实线路的限制"></a>

#### 当前真实线路的限制

另外使用当前配置的 OpenCode `nemotron-3.5-lightning-free` 发送合成短提示，输出上限 64 token，不发送仓库内容。正确完整端点的新传输与原 requests 对照均返回 **HTTP 403**；服务消息明确指出免费层只允许在 OpenCode 内使用。没有取得有效模型输出，因此这条线路的远端首 token 时间仍未验收。

该模型及 `/zen/v1/chat/completions` 端点仍列在 [OpenCode 官方目录](https://opencode.ai/docs/en/zen/) 中；目录存在不等于当前调用已经获准。最初探测脚本直接使用了 API 基址而得到 404，这个探测错误已纠正，**不作为产品缺陷或线路故障证据**。

<a id="reverie-cli-request-profile-repairs-2026-10-05--可复核材料和未完成范围"></a>

### 可复核材料和未完成范围

结构化摘要见 [验证记录](verification/2026-10-05-request-profile-repairs.json)。本地 `.runtime` 材料是被忽略的验证产物，不随 Git 文档发布；摘要保留了结果与范围，不依赖截图才能理解结论。

本地材料包括 `.runtime/network-cancellation.xml`、`.runtime/full-repairs-python-final.xml`、`.runtime/rats-isolated-repairs.xml`，以及 `ReverieCli-ui/.runtime/profile-smoke-20261005-105544/` 下的 `packaged-results.json`、裁剪 / 对话 / 重启截图、fixture socket 记录。真实线路的脱敏记录在 `.runtime/live-model-latency/`。

G12 的逐线路工具 / 思考 / 视觉矩阵、原生 IME / 屏幕阅读器、其他系统、真实认证 MCP / 插件、首次便携解压、长期任务和引擎生产深度仍按 [功能状态](FEATURE_STATUS.md)与 [路线图](ROADMAP.md)保留；本轮不把这些未验收项标成完成。


---

<a id="reverie-cli-streaming-ux-validation-2026-10-03"></a>

<a id="reverie-cli-streaming-ux-validation-2026-10-03--对话输出模式与交互优化"></a>

## 对话输出模式与交互优化

> 原文件：`docs/REVERIE_CLI_STREAMING_UX_VALIDATION_2026-10-03.md`。以下为当时的记录；日期、测试数字、限制与旧实施提示词均保留，不代表本次重新验收。


用户选择的方向是“克制顺滑”：及时反馈、稳定阅读、轻微过渡。保留 Reverie 的品牌与原有能力；本轮不进行项目 commit/push。

<a id="reverie-cli-streaming-ux-validation-2026-10-03--实现"></a>

### 实现

- 输入区右下角增加一个“流式 / 非流式”按钮，复用原有 `stream_responses` 配置和设置页，不创建第二套配置。加载配置时禁用；保存中用 `aria-disabled` 和处理器拦截重复操作并保留焦点；保存失败显示错误并保留原值、草稿和附件。实际 Electron 验证发现原生 `disabled` 在保存中会丢失键盘焦点，已修复。支持键盘 Space/Enter，发送输入保留原有中文组合态判断。
- 删除桌面 `runPrompt` / `resumePrompt` 的 `stream: true` 硬编码；发送、恢复与排队任务由实际内核配置决定输出方式。运行中切换用于下一次任务，当前任务继续使用启动时复制的配置。SenseNova 写作模式的既有强制流式规则在按钮上明确说明并禁用切换。
- Codex/WebGemini 原有非流式路径仍通过供应商流聚合正文。修复思考与协议事件混入正文的问题，沿用原思考历史字段和工具事件通道；输出方式不等于每一种供应商网络协议都能关闭 SSE。
- 消息入场、工具组与任务列表展开采用 140–160ms、2px 的轻微过渡；切换按钮有主题一致的状态、悬停、按下和焦点反馈。减少动态效果偏好沿用全局限制。
- 流式正文通过 `StreamingMarkdown` 延后非紧急更新，纯 `memo(Markdown)` 在旧字符串时跳过重解析。实测仅延后更新仍有密集 Markdown 长帧，进一步将正文刷新合并为 100ms 节奏；完成、失败或停止时立即显示完整结果。保留原 Markdown 格式和 40ms 事件合批，Tokens 仍沿原事件更新。切换会话会重新创建正文组件，避免暂时显示另一会话的旧文本。一次同步 Markdown 解析仍不能中断，性能边界见实测记录。
- 同时观察消息容器和真实内容尺寸，工具原位完成、图片载入、输入区增高时仅按用户的末尾跟随意图调整。向上阅读保持位置，原位工具结果也提示“回到最新”。按钮位于消息区底部，不使用固定的输入区高度假设。
- 最后完整流程复现展开诊断、向上阅读后发送新问题仍停在旧位置；明确发送新问题或点击“继续任务”现在恢复末尾跟随。只输入草稿、阅读期间排队或补充当前任务不会重置阅读位置。对应回归先失败再通过，最终真实文件工具输出及展开结果都保持末尾跟随。
- 会话阅读位置同时保存已加载的历史起点，切走再回来恢复同一批消息，保留原分页前插的高度差补偿。
- 实际 160 条历史会话验收发现会话切换时旧滚动监听写错会话位置；监听的清理和恢复调整到布局阶段。原加载提示还产生 14px 的位置变化，改为不占内容高度的浮层。
- 正常用户停止显示中性“已停止”，结束后清除“正在停止”和强制停止计时；真实失败保留原诊断。主动停止不发布误导性的运行失败通知。
- 实际运行还发现非流式请求等待期间收到 Stop，返回正文后仍按成功结束的问题。在发布完整正文前检查原有停止状态；供应商已完成的请求用量、历史与工具操作仍保留，未修改供应商传输协议。
- 失败或停止的活动消息与保存历史使用同一个开始边界，避免刷新历史后把本轮消息再显示一次。边界由原有 `run.started` 事件补充传递，支持后台任务与恢复路径。
- 内容区较窄时首页卡片使用单列，避免侧栏展开后标题和说明被挤成极窄的两列；空会话从首页顶部开始，不使用消息末尾跟随而截掉标题。思考按钮中文标签保持单行。
- 为原工作面板按钮预留会话操作空间，限制其计数宽度，修复遮挡重命名、分叉、回退和删除按钮的问题；验收几何检查同时覆盖顶部和底部控件。
- 加强几何验收后复现 480px 对话网格被隐式最小宽度撑到约 548px、外层裁剪掩盖溢出的问题。网格改为明确的 `minmax(0,1fr)` 列，检查同时覆盖真实网格边界。
- 实际焦点/尺寸切换还复现整页向左移动 14px：隐藏面板的位移动效产生外壳的可滚动溢出。外壳改用 `overflow: clip`，保留原有面板过渡和内部滚动；验证明确尝试设置外壳横向滚动，最终位置仍为 0。诊断：`default-focus-diagnostic-runtime-evidence.json`。
- 内容区小于等于 520px 时，排队/补充选择占上一行，模式、用量、停止与发送在下一行成组，附件入口对齐到底部，避免发送键单独换行。最终几何验收额外检查模式、停止与发送的垂直对齐。
- 真实 JDW 验收返回 Cloudflare HTML 拦截页面。此类失败现在显示简短说明，原始错误默认折叠，仍可用键盘展开和完整复制；不把拦截页面当作模型回复。
- 最后图片截图复核区分了两种现象：无背景时的模糊截图截在 140ms 入场过渡中；开启品牌星空背景后，输入区的 `backdrop-filter` 确实把固定预览弹窗限制到输入区并裁掉下半部分。附件预览现在沿用 `createPortal` 放到 `document.body`，逃离玻璃输入区的定位与裁剪，同时沿用根级主题变量、原动画、焦点与原图加载路径。遮罩也覆盖顶部模型控件，关闭和文件预览入口复用 Reverie 已有按钮样式。截图等待原图加载和动画实际结束，不把过渡中间帧当作最终界面。

交互参考：[Cline ChatView 源码](https://github.com/cline/cline/blob/main/apps/vscode/webview-ui/src/components/chat/ChatView.tsx) 将输入、消息与滚动管理分开；本轮沿用 Reverie 的结构落实明确的跟随意图和输入反馈。

<a id="reverie-cli-streaming-ux-validation-2026-10-03--验证状态"></a>

### 验证状态

代码与 UI 入口已实现；以下分别记录测试、真实打包运行和外部服务证据。

- 新增原生供应商聚合回归先红：8 failed；修复后包括实际 SSE/增量解析路径的相关四套 Python 测试 88 passed。证据：`.runtime/stream-toggle-20261003/aggregation-{red,verified}.log`。
- UI 最终全套 222 passed、1 skipped；跳过项为未配置真实 Engine 的测试。最新日志：`ui-preview-final.log`。首次沙箱文件/Git 回归的 EPERM 与 loopback 权限错误保留，在本项目 fixture 内重跑通过。后续并发运行中 5 项 Git 测试超过 5s；未修改产品代码，受控 `--maxWorkers=1 --testTimeout=30000` 重跑通过。增加了持续增量/结束全文、HTML 错误折叠与完整复制回归；相关 UI 两套 92 passed，日志：`ui-cadence-html.log`。新增发送/排队阅读位置回归先失败，修复后通过：`ui-new-prompt-follow-red.log`、`ui-new-prompt-follow-verified.log`。玻璃输入区图片预览新增回归先失败，修复后附件四项通过：`ui-preview-portal-red.log`、`ui-preview-portal-verified.log`。
- 非流式停止新增回归先红：1 failed、1 passed；修复后五套相关 Python 测试 136 passed，包含实际 agent、控制、bridge、聚合和批处理路径。日志：`nonstream-stop-red-focused.log`、`python-verified.log`。
- 预览按钮最后仅复用已有样式类；随后附件四项测试再次通过，日志：`ui-preview-delivery.log`。
- 国际化与 TypeScript 检查通过：928 translations、82 templates；日志：`typecheck-delivery-final.log`。
- PyInstaller 内核、TypeScript/Vite 前端和 Windows 目录包实际编译完成。独立包：`ReverieCli-ui/release/stream-ux-20261003/win-unpacked/ReverieUI.exe`；最终日志：`build-kernel-verified.log`、`build-delivery-final.log`、`package-delivery-final.log`。原有 Vite 大包警告仍保留；本轮没有重新生成 NSIS 安装器或便携 ZIP。
- 真实打包基线已复现主动停止仍显示“正在停止”并出现红色失败卡。截图：`baseline-stopped.png`。此前独立包 102 项运行检查通过，日志：`runtime-final-verified.log`；最新默认包复核在下方记录。
- 160 条真实历史会话加载、切换和双草稿验收 6 项通过。分页前插可见锚点变化小于 1px，切换前后滚动位置均为 12089px；日志：`runtime-history-complete.log`，截图：`history-complete-restored-anchor.png`。
- 真实排队任务验收 3 项通过，请求顺序为 `stream=true`、`stream=false`，第三轮中文草稿保留；日志：`runtime-queue-complete.log`。初次脚本错误地要求已完成任务执行 resume，bridge 正确拒绝；保留该失败记录，恢复功能由中断任务的实际 UI 流程验收。
- JDW 使用项目已有凭据，在隔离配置里请求原模型列表的 `claude-opus-4-8`。原配置选中的 `gpt-5.6-luna` 不在该列表，首次被明确拒绝；原配置未改动。第二次真实非流式请求约 15.2s 后返回 Cloudflare 拦截 HTML，无模型回复、无 API 用量；流式真实成功项未继续尝试。证据：`real-jdw-verified-runtime-evidence.json`、`real-jdw-verified-buffered.png`，隔离配置中的凭据已脱敏。
- 默认包最终完整运行验收 154 项通过，页面未捕获运行错误；日志：`runtime-default-delivery-final.log`，结构化记录：`default-delivery-final-runtime-evidence.json`。覆盖两种真实 HTTP 输出模式、运行中切换、停止、真实中断任务的 UI 恢复、失败/HTML 诊断、减少动态效果、深浅主题与 1500/760/480 渲染视口、阅读位置、真实文件工具、系统剪贴板图片、中文路径 bridge、Git、PTY 和重启持久化。实际剪贴板图片已进入非流式 HTTP 请求；这不等于已验证外部模型的视觉理解。
- 英文打包界面 15 项检查通过，覆盖深浅主题的 760/480 视口边界、不重叠、模式/停止/发送同排和 HTML 诊断的原生键盘展开。日志：`runtime-english-final.log`，结构化记录：`default-english-final-runtime-evidence.json`。
- 两种输出模式的真实打包用量验收 10 项通过：fixture 返回输入 401、输出 23、总量 424；两轮落账为输入 802、输出 46、总量 848。上下文使用 API 基准，新中文草稿只增加原计数器的本地增量，界面明确显示 API 来源，模型上限保持 128000。证据：`default-token-modes-runtime-evidence.json`、`runtime-token-modes-final.log`；这是实际 HTTP/bridge/持久化验证，数值来自合成服务，不是外部供应商账单。
- 默认包最终布局修复后的历史恢复 6 项、排队 3 项和原生最小窗口 3 项均通过。证据：`default-history-final-runtime-evidence.json`、`default-queue-final-runtime-evidence.json`、`default-native-window-runtime-evidence.json`。原生 Win32 窗口调整为 1080×700，实际渲染内容为 1064×692；760/480 使用打包应用的 CDP 渲染视口验证，原生最小尺寸未变更。
- 图片预览最终默认包 63 项通过：品牌背景开关、深浅主题和 1500/760/480 视口下，遮罩覆盖完整应用，原图及稳定弹窗不被裁剪，原生 Tab/Shift+Tab/Esc 和点击遮罩均可用并恢复入口焦点。实际原生剪贴板图片写入项目并加载原图。证据：`default-photo-preview-delivery-runtime-evidence.json`、`runtime-photo-preview-delivery.log`；修复前实际裁剪截图保留为 `default-modal-background-before-settled.png`。

验证应用数据、截图、测试 Git 仓库与运行日志位于本项目内，后续构建明确设置项目内 TEMP/TMP、npm 与 Electron 缓存。只关闭验证脚本自己启动的进程，保留用户会话、草稿、无关未提交改动与 `result_images/`。

<a id="reverie-cli-streaming-ux-validation-2026-10-03--默认包与关键截图"></a>

### 默认包与关键截图

默认入口已更新为 `ReverieCli-ui/release/win-unpacked/ReverieUI.exe`，复制并逐文件校验 801 个文件。更新前文件保存在 `.runtime/stream-ux-20261003/default-package-backup/`，原有无关数据和重复运行时目录保留。完整校验清单：`default-package-update.json`；同步日志：`sync-delivery-final.log`。

| 文件 | 最终 SHA-256 |
| --- | --- |
| `ReverieUI.exe` | `3C79F1A1C71B5E9E16AB0DFF2AE9ABA9CE52AB4093C0DE4A12BF7A85E99D871D` |
| `reverie.exe` | `AA53522DCF7F27139D957EAE032D03465E43F55B1870320572ED8C17BA27536F` |
| `resources/app.asar` | `CAE97F48999361EB43091A14CBFAAF6FA4A4408145ED5BB9EF9B6D15997BA04F` |

以下关键截图已逐张复核，来自实际默认包；全部截图和日志位于 `.runtime/stream-ux-20261003/`。

- [中文浅色窄视口运行中](../.runtime/stream-ux-20261003/default-delivery-final-running-light-480.png)：排队/补充占上一行，模式、停止和发送成组。
- [英文深色窄视口运行中](../.runtime/stream-ux-20261003/default-english-final-running-dark-480.png)：较长英文标签保持边界内。
- [浅色 HTML 失败](../.runtime/stream-ux-20261003/default-delivery-final-html-failure-light-760.png)：摘要、可展开原诊断、复制和继续任务均可访问。
- [默认包原生最小窗口](../.runtime/stream-ux-20261003/default-native-window-native-minimum-window.png)：首页和输入区完整可用。
- [星空背景图片预览](../.runtime/stream-ux-20261003/default-photo-preview-delivery-aurora-archive-dark-1500.png)：真实剪贴板导入、原图加载、背景模糊与弹窗完整边界。
- [浅色窄视口图片预览](../.runtime/stream-ux-20261003/default-photo-preview-delivery-none-light-480.png)：原图和全部操作保持可访问。
- [停止结束](../.runtime/stream-ux-20261003/default-delivery-final-stopped.png)：中性结束状态，无残留强制停止操作。

本轮未暂存、提交或推送项目改动。最终项目 HEAD 为 `127c39769217d87dd7647a3c6b296e2629d8f9ff`；工作区保留既有未提交改动，最终 Git 状态和检查记录见 `git-status-final.log`、`git-diff-check-final.log`。

<a id="reverie-cli-streaming-ux-validation-2026-10-03--性能实测"></a>

### 性能实测

使用真实 Windows 目录包，在 760×650 渲染视口下分别输出约 5 万字符的普通文本、完整代码块和密集标题/列表/GFM 表格；每种负载重复 3 次。供应商 fixture 每 50ms 发送约 600 字符，同时通过 CDP 输入下一轮草稿。基线、仅延后渲染、最终 100ms 正文合批各保留 9 个样本，测量期间不并行运行构建、测试或另一验证应用。

| 指标，3 次范围 | 旧包基线 | 仅延后渲染 | 100ms 合批候选包 |
| --- | --- | --- | --- |
| 密集 Markdown 帧间隔 P95 | 36.4–78.7ms | 24.3–48.5ms | 23.0–29.6ms |
| 密集 Markdown 超过 50ms 的帧数 | 25–30 | 23–26 | 13–17 |
| 密集 Markdown 键盘命令往返 P95 | 47.5–97.7ms | 29.7–45.5ms | 35.8–41.7ms |
| 密集 Markdown 最大帧间隔 | 169.6–387.9ms | 187.8–393.9ms | 192.0–377.8ms |
| 普通文本/代码帧间隔 P95 | — | — | 8.1–8.2ms，超过 50ms 的帧数均为 0 |

100ms 策略 9 个样本的结束标记、完整代码与独立草稿均通过；密集 Markdown 的标题与表格行数检查均通过。输入事件延迟最大值为 0.2–0.8ms，这不同于操作系统物理键盘或原生输入法延迟。结果表明长帧减少，但极长密集 Markdown 的同步解析和完成渲染仍有长帧；没有宣称完全无卡顿。普通负载的帧间隔还受显示刷新节奏影响，不能把单个样本当作稳定的速度倍数。

随后完成网格与外壳裁剪修复的默认包再次执行 3 次独立密集 Markdown：P95 22.6–29.7ms，超过 50ms 的帧数 13–18，最大帧间隔 143.7–184.1ms；结束正文、表格格式与草稿均通过。记录：`default-final-dense-runtime-evidence.json`。这组没有前置的 6 轮普通文本/代码历史，不能直接把最大值降低归因于代码优化；最终窄布局调整仅影响小于等于 520px 的内容区。

原始记录：`baseline-workload-valid-runtime-evidence.json`、`after-workload-verified-runtime-evidence.json`、`after-workload-cadence-final-runtime-evidence.json`；最终负载截图为 `after-workload-cadence-final-{text,code,markdown}.png`。

<a id="reverie-cli-streaming-ux-validation-2026-10-03--证据边界"></a>

### 证据边界

外部真实 Codex/WebGemini、JDW 成功回复及 API 用量、真实视觉理解、原生中文输入法候选框与真实 Engine RATS 尚无本轮独立通过证据。JDW 的实际阻碍是供应商 Cloudflare 拦截，并非未找到凭据。合成的本地 HTTP/SSE 验证可确认打包应用、bridge、配置、请求与 UI 路径，不能代替供应商账单或真实账号兼容性验证。


---

<a id="reverie-cli-token-context-review-2026-10-02"></a>

<a id="reverie-cli-token-context-review-2026-10-02--tokens上下文及输入区复审"></a>

## Tokens、上下文及输入区复审

> 原文件：`docs/REVERIE_CLI_TOKEN_CONTEXT_REVIEW_2026-10-02.md`。以下为当时的记录；日期、测试数字、限制与旧实施提示词均保留，不代表本次重新验收。


<a id="reverie-cli-token-context-review-2026-10-02--本地计数沿用原有实现"></a>

### 本地计数沿用原有实现

原来就有本地 Tokens 计数，本次不应新建分词算法。本轮将工作区统计的 `_get_encoding`、`_count_value_tokens`、`count_text_tokens`、`count_message_tokens`、`count_messages_tokens`，以及代理的 `_count_request_tokens` 与 Git HEAD 做 AST 比较，6 项均未改变。证据：`.runtime/context-review-20261002/original-counters.json`；复查脚本：`audit_counters.py`。

有效 API 字段优先，缺失字段才调用这些原有方法。打包包含原有 tiktoken 编码插件；tiktoken 不可用时仍采用原来的启发式估算。未发送草稿、尚未收到 API 用量的流式内容需要预估，也复用同一套计数方法。这里的本地预估不能被称为供应商的精确用量。

累计消耗统计按每次模型调用累加；上下文环依据当前请求及最近 API 测量更新，不把工作区累计消耗当成当前上下文长度。API 只报告部分字段时，界面必须区分已报告值和本地补足值。

<a id="reverie-cli-token-context-review-2026-10-02--此前改动清单"></a>

### 此前改动清单

下表覆盖当前未提交的 Tokens、上下文和 GUI 改动，不把原有 S01–S21 能力当成本轮新增。

| 范围 | 当前改动 |
| --- | --- |
| 用量传输 | Chat Completions 请求最终流式 usage；SDK/直接 HTTP/Responses 接收用量快照；明确拒绝用量选项的网关移除该选项重试；快照覆盖，不重复相加 |
| 用量账本 | 按缺失字段复用旧计数；保留 API 独立总数；兼容旧统计文件；记录空响应/重试的模型调用；CLI 展示 API 优先策略 |
| 实时上下文 | 草稿、就绪附件、流式内容及工具事件触发 250ms 节流读取；读取内核会话或真实执行 worker 的请求历史；API 测量校准后本地计新增长 |
| 上下文容量 | 自定义模型目录与运行时采用同一份已保存容量；模型切换清除旧测量基准 |
| 错误及图片 | 自定义 Provider 按实际 vision 配置允许图片输入；失败详情集中到可滚动、可复制的消息错误卡；清除错误文本重复和错误“运行中”状态 |
| 用户要求删除 | 会话上移/下移、手动排序及侧栏状态过滤已移除；最新修订继续移除“本条上下文”汇总入口、弹层及专用样式/翻译 |
| 运行时输入区 | 原生 Queue/Steer 下拉改为主题一致的两项切换按钮；保留排队、补充、停止及待发送草稿；支持箭头键、Home/End，组合态不切换 |
| 打包 | 恢复旧分词器编码插件；实际编译内核、前端并生成 Windows 目录包；默认包同步情况和运行证据在下方记录 |

附件卡片、技能条和实时上下文环继续使用原有入口。没有新增 Local/Cloud，也没有另造文件索引、模型配置或分词器。

<a id="reverie-cli-token-context-review-2026-10-02--确认的负面改动及修正"></a>

### 确认的负面改动及修正

| 问题 | 影响 | 修正及证据 |
| --- | --- | --- |
| 前端把分页历史和工具展示预览当作统计历史 | 会漏掉内核当前请求中的历史/工具内容，并在流式渲染时额外重建长数据 | 撤掉前端重建；内核读取自身完整会话，再按原有请求构建规则处理；5 项失败的回归检查中包含此问题 |
| SDK 调用省略 `liveRead` 时可能替换执行 worker 历史 | 统计读取有机会影响正在执行的任务 | 以实际 run control 判断运行状态；统计构建为只读，不消费 steer/pause safe point；True/False 两种调用均验证 |
| 只按本地长度判断 API 测量是否仍有效 | 替换历史后加大草稿可错误套用旧 API 数据 | 对非 system 请求消息建立内容指纹，前缀变化即拒绝旧基准；保留缩短/压缩失配检查 |
| 部分 API 用量被标为纯 API，独立 total 可能被输入/输出和覆盖 | 统计来源不真实，API 总数可能失真 | 区分 `api_tokens` 与本地补足/增长；保留独立总数；回归及真实 HTTP 部分用量场景验证 |
| 上下文报告异常可提前中断后续用量账本记录 | GUI 的辅助统计异常影响核心计费/内存事件记录 | 报告及回调异常独立捕获；故意抛错后账本仍更新 |
| 旧统计请求失败可能清除更新后的 API 事件 | 新数据短暂消失或回退 | 成功和异常分支都检查同一修订号，过期结果不覆盖当前显示 |
| “本条上下文”汇总重复展示已有入口且产生重叠 | 增加不必要操作和界面噪声 | 按用户要求删除整块功能，不保留本轮为它增加的 portal/尺寸监听 |
| Queue/Steer 使用未主题化的原生下拉 | 系统菜单、焦点框与应用主题和输入区布局脱节 | 改成两项紧凑切换，保留行为；键盘操作和草稿保留回归通过 |
| 缩窄窗口后错误卡仍处于旧滚动位置，详情高度只按窗口计算 | 错误卡详情被消息区边界截断；原“元素可见”检查不足 | 实机复现：760×650 时错误卡 bottom≈524，而消息区 bottom≈326；跟踪消息区尺寸，仅在跟随末尾时重定位；详情高度按实际消息区限制，保留用户向上阅读位置 |

复现与修复不能混为一谈：`.runtime/context-review-20261002/red-tests.log` 保留修复前 **5 failed、1 passed**；后续 Python 相关八组回归 **405 passed**。旧弹层尺寸变化后的重叠在 `popup-before.json/png` 中有实机证据，该弹层已按最新要求删除。错误区原始尺寸和截图保留在 `error-layout-before.json`、`error-layout-before-{1500,760}.png`。

<a id="reverie-cli-token-context-review-2026-10-02--验证与证据"></a>

### 验证与证据

- 本地计数 AST 对比：6/6 原有函数一致。
- Python 八组相关回归：405 passed，包括统计、API 用量、桌面 bridge、Provider、完成/重试、传输、批量提示及媒体输入。
- 最新删除/输入行为/尺寸监听聚焦回归：3 passed；最终 UI 全套 **207 passed、1 skipped**，跳过项为未配置真实 Engine 的 RATS 集成检查。日志：`behavior-tests-final.log`、`ui-tests-revised.log`。
- TypeScript 与国际化检查通过：914 translations、82 templates（已删除汇总弹层专用翻译）。
- 复审内核 PyInstaller、最终 TypeScript/Vite 前端及 Windows 目录包实际编译成功；日志：`build-kernel.log`、`build-renderer-final.log`、`package-final.log`。独立包：`ReverieCli-ui/release/context-review-final-20261002/win-unpacked/ReverieUI.exe`。
- 删除汇总入口之前的复审包通过了完整/部分 API、真实工具及文件/剪贴板/Git/PTY/bridge 共 52 项检查；这是历史中间结果。最终版本必须重新验证删除入口、主题化运行控件和错误区尺寸变化，不能沿用这 52 项宣布完成。
- 最终独立包实际启动完成 **62/62** 项检查；备份并同步默认包后，`ReverieCli-ui/release/win-unpacked/ReverieUI.exe` 再次实际启动完成相同 **62/62** 项。证据：`revised-runtime-evidence.json`、`default-runtime-evidence.json`；日志：`runtime-revised.log`、`runtime-default.log`。
- 验证覆盖深/浅主题，1500×960、760×650、480×650：无汇总入口残留；运行时两项切换的箭头键及草稿保留；停止/发送入口可用且无横向溢出；完整错误卡位于消息区边界内。失败详情复制到真实系统剪贴板并读回；图片从剪贴板写入实际 PNG、预览并进入 HTTP 请求的图片 data URI；重试后错误清除。
- 实际 SSE 生成中上下文从 10% → 13% → 16% → 19% 更新；最终使用服务返回的 424 tokens，未发送草稿显示混合来源，清空恢复该基准。实际部分用量响应仅提供输入 401，只有 401 标为 API，其余由旧计数方法估算。替换历史的失配基准被拒绝。
- 实际文件工具读取预算内 **19,014 字符**，HTTP 后续请求包含末尾标记，执行 worker 的上下文统计计入 **3,010 tool tokens**。另验证真实中文文件的 bridge 预览、Git fixture 分支/HEAD、原生 PTY 写入/读取中文文件，生成中停止保持可编辑。最初验证文件超过旧工具输出预算导致截断的失败记录保留，未修改原有工具预算去迎合测试。
- 默认包另行实测动效：两项切换背景/颜色过渡为 **0.15s**；开启减少动态效果偏好后为 **0.00001s**。证据：`motion-evidence.json`、`motion-check.log`。原生输入法候选框仍不在该证据覆盖范围内。
- 默认包按相对文件路径备份并同步 **801 文件**，全部 SHA-256 与独立包一致，含 `ReverieUI.exe`、`reverie.exe`、trusted-kernels manifest、`resources/app.asar` 和 797 个运行库文件。记录：`default-package-update.json`、`default-package-sync.log`；旧文件备份：`default-package-backup/`。内核 SHA-256：`0720939EDCA44622FD91083A5830006BEFC39A842FE85C5954466BC844165BDA`。
- `git diff --check` 通过，最终变更列表保留在 `git-status-final.txt`；本轮未 stage/commit/push。

完整日志、回归脚本、运行证据及截图均保留在 `.runtime/context-review-20261002/`，不使用 Desktop 或系统临时目录存放验证产物。打包验收使用本项目内的独立应用数据及 Git fixture，不替换用户真实会话或草稿。

最终界面截图由默认包实机运行生成：`after-composer-{dark,light}-{1500,760,480}.png`、`after-running-{dark,light}-{1500,760,480}.png`、`after-error-{dark,light}-{1500,760,480}.png`，以及 `after-05-image-preview.png`、`after-08-live-stream.png`、`after-11-partial-api.png`、`after-12-real-tool-context.png`。截图不是开发网页或界面设计稿。关闭实际 SSE 请求时验证服务记录的 Windows 10053 为取消连接的结果，停止后的 UI/bridge 检查已通过。

<a id="reverie-cli-token-context-review-2026-10-02--仍存在的代价和证据限制"></a>

### 仍存在的代价和证据限制

- 实时读取会增加本地计数和 bridge 通信，当前有节流和订阅内单请求控制；长会话不同机器的 CPU/延迟范围尚未完整测量，不能宣称零性能代价。
- 不支持流式用量选项的旧网关可能多一次兼容性 HTTP 请求；只在明确选项拒绝时移除选项。无用量服务仍依赖原有本地计数。
- API 基准指纹校验普通请求历史；供应商隐藏提示、图片内部编码及服务侧变换无法由客户端精确计算。原生输入法候选框、外部 JDW 账单/视觉理解、真实 Engine RATS 均缺独立实机证据。
- 先前默认包运行库复制曾生成重复目录 `ReverieCli-ui/release/win-unpacked/reverie-runtime/reverie-runtime/`，约 352 MiB。删除被自动审批拒绝，原因仅返回 `blocked by policy`；该目录保留，未绕过拒绝。最终同步按文件相对路径执行，避免再产生嵌套目录。
- 初次 Git 全套测试遇到临时 fixture 清理 EBUSY。仅在验证进程设置 `maintenance.auto=false`、`gc.auto=0` 后三项 Git 测试通过；未改变产品 Git 实现或用户 Git 配置。失败日志保留。

原 Tokens 及 GUI 验收记录见 [Tokens 统计](#reverie-cli-token-usage-validation-2026-10-02)、[上下文与 GUI](#reverie-cli-context-gui-validation-2026-10-02)。保留原有无关未提交工作与 `result_images/`，不进行本项目 commit/push。


---

<a id="reverie-cli-token-usage-validation-2026-10-02"></a>

<a id="reverie-cli-token-usage-validation-2026-10-02--tokens-用量统计api-优先"></a>

## Tokens 用量统计：API 优先

> 原文件：`docs/REVERIE_CLI_TOKEN_USAGE_VALIDATION_2026-10-02.md`。以下为当时的记录；日期、测试数字、限制与旧实施提示词均保留，不代表本次重新验收。


原本地计数方法的 AST 一致性、引入的负面改动及修正、最新用户删除项和运行时输入区验收见 [后续复审记录](#reverie-cli-token-context-review-2026-10-02)。本文件中的测试数字与锁定目录情况属于初次统计验收阶段。

<a id="reverie-cli-token-usage-validation-2026-10-02--行为"></a>

### 行为

- 默认优先使用 API 返回的 `prompt_tokens` / `completion_tokens` 或 `input_tokens` / `output_tokens`，以及 `total_tokens`。有效的 `0` 也是 API 数据，不会触发本地估算。
- API 给出总数和一侧计数时，另一侧通过总数推导；仅给出总数时保留该总数，本地仅估算输入/输出分配。没有有效数据的字段才使用原有默认分词器（tiktoken `cl100k_base`，不可用时沿用原有启发式估算）。
- Chat Completions 流式请求默认发送 `stream_options.include_usage=true`，接收 `choices=[]` 的最终用量块。SDK、直接 HTTP、Responses 共用流式用量归集，累计快照覆盖而不相加，每次完成的模型响应计一次。空响应和内部重试响应也计入消耗，不把客户端生成的未完成提示计为模型输出。
- 明确拒绝 `stream_options` / `include_usage` 的旧网关可重试一次并仅移除该选项，保留工具字段；用量缺失时使用本地计数。其他错误沿用原有错误/重试处理。
- Anthropic 输入用量包含普通输入、缓存写入、缓存读取；OpenAI 嵌套的缓存/推理详情已经计入输入/输出总数，不重复添加。
- 打包配置显式包含 tiktoken 动态编码插件，恢复打包版本地回退的默认 `cl100k_base` 编码。
- 模型、会话、来源及工作区保留 API 的总数。旧统计文件无独立总数字段时，从历史输入+输出恢复，历史记录不追溯重算。
- `/status`、`/total` 明示 API 优先策略。上下文环实时跟踪草稿、附件和流式输出；收到 API 用量后以该次测量为基准，新增内容用本地分词器估算并标明来源。没有 API 基准时全部本地预估；自动压缩门限继续按实际请求的本地估算执行。上下文占用与累计消耗用途不同。

协议依据：[OpenAI 流式用量说明](https://help.openai.com/en/articles/10478918-reviewing-api-usage-and-costs)、[Anthropic 缓存用量说明](https://platform.claude.com/docs/zh-CN/build-with-claude/prompt-caching)。

<a id="reverie-cli-token-usage-validation-2026-10-02--验证"></a>

### 验证

- Python 相关回归：242 passed，覆盖统计、流式/非流式代理、传输兼容、上下文压缩、自动接力、上下文预算和 CLI 展示。
- UI 类型检查、国际化键检查通过（918 translations，77 templates）。
- PyInstaller 内核编译、TypeScript/Vite 生产编译通过；electron-builder 在项目内独立目录打包成功。默认 `release/win-unpacked/ReverieUI.exe` 被系统锁定（EBUSY），未能覆盖该输出，使用 `ReverieCli-ui/release/token-usage-20261002/win-unpacked/ReverieUI.exe` 完成验收。
- 打包版 50 项断言通过：8 组真实本地 HTTP 请求（API 用量、零值、部分用量、无用量回退、拒绝用量选项、直接 request、Responses、Anthropic 缓存）；9 次 HTTP 请求包含 1 次兼容性重试，8 次模型用量记录，未重复相加流式快照。
- 模型、会话、工作区落盘值一致；8 次执行的数据在桌面及 CLI 关闭后仍完整。默认本地回退实际为打包内核的 `tiktoken cl100k_base`，未继续降级启发式估算。
- 实际打包 CLI 的 `/status`、`/total` 读取同一持久化统计，显示 API 优先策略和工作区总数，展示命令未增加模型用量调用。原生 Windows stdout 采用 CP1252，保留原始字节并按实际编码转存 UTF-8 验证文本。
- 8 张打包桌面截图保存在 `.runtime/token-usage-20261002/*-packaged.png`。最终协议与 CLI 断言合并保存在 `packaged-runtime.json`；早期验收脚本的计数器/入口/输出解码问题保留独立记录，修正后继续验证。
- 原打包目录的 216 个既有数据文件 SHA-256 全部保持一致。自动审批拒绝删除本轮产生的重复备份目录（仅返回 blocked by policy），这些目录保留在项目内。

验证日志与运行脚本保留在项目 `.runtime/token-usage-20261002/`；内核及前端编译日志在 `.runtime/implementation-20260930/token-20261002-complete-pack.log`，最终独立包日志在 `.runtime/token-usage-20261002/package-final.log`。未对本任务执行 commit/push，保留原有无关 `result_images/`。

<a id="reverie-cli-token-usage-validation-2026-10-02--尚缺证据"></a>

### 尚缺证据

上下文实时刷新、输入弹层与错误显示的后续修复和打包版验收见 [实时上下文与 GUI 验证记录](#reverie-cli-context-gui-validation-2026-10-02)。本文件上方测试数字属于初始 Tokens 统计验收，后续结果在该记录中单列。

本轮协议验收使用实际本地 HTTP 服务提供用量数据，验证真实打包内核的传输及持久化路径；不等同于外部收费供应商的账单对账。供应商账单与其返回的 usage 是否一致仍需外部服务凭据及账单证据。


---

<a id="reverie-cli-ui-repair-2026-10-04"></a>

<a id="reverie-cli-ui-repair-2026-10-04--reverie-ui-修复与实际验证2026-10-04"></a>

## Reverie UI 修复与实际验证（2026-10-04）

> 原文件：`docs/REVERIE_CLI_UI_REPAIR_2026-10-04.md`。以下为当时的记录；日期、测试数字、限制与旧实施提示词均保留，不代表本次重新验收。


已按用户要求先为 Codex 安装并学习设计 Skill，再修改 Reverie。此次工作保留原有未提交改动，没有在主仓库 commit、push 或发布到 GitHub。

<a id="reverie-cli-ui-repair-2026-10-04--设计-skill"></a>

### 设计 Skill

[emilkowalski/skills](https://github.com/emilkowalski/skills) 的 14 个 Skill 已安装到 `C:\Users\Raiden\.codex\skills`，并将全部 22 个 Skill / 支持文件内置到 Reverie。来源固定于 `e8a175de22ae1e49370fc144c1f3bb9aeedf988d`，保留 MIT 许可与文件哈希清单。实际桌面包发现 17 个内置 Skill（本次新增 14 个，原有 3 个）。

主要采用 Apple Design、Emil Design Engineering 的规则：清楚的文字层级、安静的表面、即时按压反馈、明确焦点、按需展开、菜单贴近触发点；高频键盘菜单不加开合动画。用 break-ui 对长文件名、中文、emoji、超长描述、空列表、单项、千项、窄屏和大字体进行实际压力检查，修复了 320px / 200% 字体下菜单底部快捷键溢出。

清单与安装证据：[`emilkowalski-source.json`](../ReverieCli-py/reverie/builtin_skills/emilkowalski-source.json)、[`codex-skills-installed.json`](../.runtime/ui-design-20261004/codex-skills-installed.json)。

<a id="reverie-cli-ui-repair-2026-10-04--修复内容"></a>

### 修复内容

| Before | After | Why |
| --- | --- | --- |
| `@` 的文件结果被输入区裁剪 | 原生 popover 顶层菜单，上拉、滚动、键盘选择、指针选择；真实中文文件已选成附件 | 结果必须能看见和操作 |
| `/` 没有输入内候选列表 | 指令列表和 `/skill` 必须使用的 Skill 选择 | 发现功能不应依赖猜测 |
| Skill 固定仅存在内存 | 草稿 / 会话落盘；首次创建转移、新会话清空、切回恢复、重启恢复 | 固定选择应随会话保留 |
| 模式选择占据顶栏 | 移到输入栏左下角，向上展开 | 工作模式贴近输入操作 |
| 项目、主题、思考和 Git 菜单被其他 UI 遮住 | body portal + 原生顶层 popover，窗口边缘限位，焦点和 Escape 关闭 | 菜单应在遮挡层之上 |
| 思考被大卡片包住 | 紧凑脑图标摘要，悬停 / 焦点高亮，点击展开缩进正文 | 与用户给出的三态参考一致 |
| 浅色主题 + 壁纸重新给思考加白色卡片 | 去掉旧主题规则对思考区域的背景覆盖 | 各主题都使用同一种摘要结构 |
| 重复的执行轨迹工具栏、空运行条、说明文字和 Streaming 大按钮 | 去掉重复展示；技术轨迹在消息内展开，显示选项在设置页 | 把空间留给对话 |
| Skills 页面大片计数卡、路径和描述占满屏幕 | 行式列表、简洁计数、细节按需展开 | 搜索和固定成为主要操作 |
| Workbench 把嵌套仓库当文件读，抛出 EISDIR | 正确识别目录，解释如何作为项目打开 | 目录不是普通文件 |
| Workbench 关闭时也频繁扫描，文件切换丢请求 | 按需打开；轮询完成后才计划下一次；差异请求独立并拒绝过期结果 | 避免无意义的扫描和过期内容 |
| 窄窗口里 Workbench 压住对话 | 可用宽度不足时切换为整块面板，返回按钮回到对话 | 当前操作应有足够空间 |
| 只读列目录也前后扫描 Git 工作区 | 内置文件工具的 read / list / exists / info 和编辑器 view 跳过写入检查点 | 列文件不应付出写入快照成本 |
| 重启后工具结果不完整或旧调用继续转圈 | 工具开始和结果即时保存；未保存结果的历史调用标记可能中断 | 恢复记录不应假装仍在执行 |

`/` 的页面指令在界面内处理；其余 CLI 指令仍沿用输入 / agent 路径。这不是把所有 CLI 交互指令改造成 GUI 执行器。思考记录没有保存可靠时长时只显示“已思考”，没有编造 “5s”。

<a id="reverie-cli-ui-repair-2026-10-04--workbench-是什么"></a>

### Workbench 是什么

它是围绕工作区改动的辅助面板：查看 Git 文件和区块差异、暂存 / 撤销改动、预览文件和产物、发起只读审查、查看任务运行与终端。需要检查 AI 修改了什么、看文件或操作终端时才打开；普通对话不需要展开它。

本次去掉面板里重复的工作区路径 / 会话标识、常驻技术版本串和冗余控制，把差异显示选项折叠。保留已有的实际工作功能，没有再添加工作台概念页或新模块。

<a id="reverie-cli-ui-repair-2026-10-04--性能实测"></a>

### 性能实测

- 真实 `G:\Reverie\Reverie-Cli` 上，内置 `file_ops` 列目录为首次 **806.7ms**，后四次 **24.09–29.62ms**。这是本地工具耗时，不包含模型响应或网关等待。
- 同一真实项目的 Workbench 快照为 **898.7 / 688.3 / 557.9ms**，78 个文件条目，没有误扫 `.runtime/` 验证目录。
- 独立 Git 验证项目含普通文件修改和嵌套仓库；面板正确显示 `README.md +1` 与目录项，目录不再出现 EISDIR。

证据：[`file-list-latency.json`](../.runtime/ui-design-20261004/file-list-latency.json)、[`workbench-real-repo-latency.json`](../.runtime/ui-design-20261004/workbench-real-repo-latency.json)、[`workbench-fixture-evidence.json`](../.runtime/ui-design-20261004/workbench-fixture-evidence.json)。没有旧版本的配对耗时，因此不声称某个固定倍数的提升。

<a id="reverie-cli-ui-repair-2026-10-04--验证范围"></a>

### 验证范围

- 最后完整 UI 回归：**235 passed / 1 skipped**。跳过项需要真实 Reverie Engine，当前未配置。日志：[`delivery-full-ui-tests.log`](../.runtime/ui-design-20261004/delivery-full-ui-tests.log)。
- 完整 UI 检查之前曾出现两个 5 秒测试超时（Git 操作、RATS 设置交互），单独复测通过；最后完整运行使用 30 秒单项超时，通过所有可运行项目。
- TypeScript、Electron 编译与 948 个翻译 / 82 个模板检查通过；renderer、GUI Python 内核、CLI 单文件内核、NSIS 安装版、便携版均实际生成。
- Python 相关回归 158 项通过；修正本地测试服务的代理环境后，真实 Anthropic SDK / HTTP 工具契约 4 项通过；最后 agent / Skill / 只读工具检查 48 项通过。各测试集有重叠，不能相加。
- 实际 Electron 包操作验证：文件候选、中文文件选择、指令菜单、Skill 固定、模式位置、底部项目菜单、Workbench 文件 / 目录、会话切换和重启恢复。
- 底部项目菜单每个按钮都在窗口内，且 `elementFromPoint` 命中菜单按钮；文件 / Skill 菜单使用顶层 popover，与输入栏间距 8px。
- 实际 SessionManager 保存的隔离会话：推理摘要默认折叠；工具结果重启后仍在；缺失结果的历史工具没有运行转圈。验证内容存放在 `.runtime/ui-design-20261004/audit-home`，没有改动用户真实会话。
- 真实浏览器压力检查：320×720、200% 字体、1000 项的 End 导航、空 / 单项、浅色与深色。原生中文 IME 和真实认证的第三方模型审查没有在本次人工验证中覆盖。

<a id="reverie-cli-ui-repair-2026-10-04--交付与启动"></a>

### 交付与启动

- 便携版：[`dist/Reverie-Portable-2.5.0-x64.exe`](../dist/Reverie-Portable-2.5.0-x64.exe)
- 安装版：[`Reverie-Setup-2.5.0-x64.exe`](../ReverieCli-ui/release/Reverie-Setup-2.5.0-x64.exe)
- CLI 核心：[`dist/reverie.exe`](../dist/reverie.exe)
- 解包桌面：[`ReverieUI.exe`](../ReverieCli-ui/release/win-unpacked/ReverieUI.exe)

实际启动日志确认当前桌面启动优先选用包内 `app-runtime/reverie.exe`，不是外置的单文件核心。内置与外置均已更新，并同步外置核心信任哈希。之前“优先外置核心”的判断已按源码和日志更正。

最终便携版实际启动后的路径、前端资源、17 个 Skill 和固定状态见 [`portable-runtime-final-evidence.json`](../.runtime/ui-design-20261004/portable-runtime-final-evidence.json)。实际解压运行的 `app.asar` 与交付包 SHA256 一致，证据见 [`portable-hash-evidence.json`](../.runtime/ui-design-20261004/portable-hash-evidence.json)；全部产物的大小和哈希见 [`delivery-artifacts.json`](../.runtime/ui-design-20261004/delivery-artifacts.json)。

便携版首次启动仍需要解压完整运行时；日志里的桌面初始化时间不含解压，不能把它当作整个首次启动耗时。如果使用以前安装的快捷方式，需要安装本次生成的安装版；本任务没有覆盖系统里的另一个安装目录。

截图与运行证据集中在 [`.runtime/ui-design-20261004`](../.runtime/ui-design-20261004)：`16/17/18-final-reasoning-*` 对应折叠 / 高亮 / 展开；`19-final-file-menu`、`20-final-slash-menu`、`21-final-mode-menu`；底部菜单与 Workbench 在 `11/12/13-*`；Skills 页面在 `14-final-skills`。最终包浅色壁纸为 `23-light-wallpaper-final`，900px 窄屏 Workbench 和其上方菜单为 `24-narrow-workbench-menu`，深色壁纸为 `25-final-dark-wallpaper`。这两种主题的思考区域背景都实测为透明，固定 Skill 与历史结果保留，历史工具转圈为 0。

最终工作区状态保存在 [`final-git-status.txt`](../.runtime/ui-design-20261004/final-git-status.txt)，`git diff --check` 通过。验证用临时应用与浏览器压力服务器已关闭，保留了验证材料。

JDW 和 Claude Desktop 的额外任务、真实网关缺陷与修复边界见 [兼容性报告](#reverie-cli-jdw-compatibility-2026-10-04)。


---

<a id="reverie-cli-workbench-repairs-2026-10-06"></a>

<a id="reverie-cli-workbench-repairs-2026-10-06--工作面板对话显示与请求启动修复"></a>

## 工作面板、对话显示与请求启动修复

> 原文件：`docs/REVERIE_CLI_WORKBENCH_REPAIRS_2026-10-06.md`。以下为当时的记录；日期、测试数字、限制与旧实施提示词均保留，不代表本次重新验收。


核对日期：**2026-10-06**。范围：Windows 桌面端 2.5.0 当前工作区，承接 [请求与个人资料修复](#reverie-cli-request-profile-repairs-2026-10-05)。保留原有未提交改动；没有 commit / push。结构化证据见 [验证记录](verification/2026-10-06-workbench-repairs.json)。

<a id="reverie-cli-workbench-repairs-2026-10-06--本轮修复"></a>

### 本轮修复

| 用户遇到的问题 | 实现 | 验证 |
| --- | --- | --- |
| Workbench 与右侧栏同时占宽，内容被挤压 | 合并为一个右侧工作面板；拖动、方向键、Home / End、双击复位；保存首选宽度，随窗口临时收窄 | 打包应用实拖；1920、1600、1101、900、600 像素窗口；宽窗口主区至少 420 像素，窄窗口使用可关闭的覆盖面板 |
| Git 分类只有字母，含义不清 | 显示“已修改、已新增、已删除、已重命名、已复制、未跟踪、冲突”，保留字母辅助识别 | 核对下拉选项、文件状态与真实 Git diff；文件标题换行，操作按钮可见 |
| 文件预览只能手输路径，不能编辑 | 按需加载目录树；点击文件预览 / 编辑；Ctrl+S 保存，外部编辑冲突保护，切换文件时保存 / 放弃 / 取消 | 实际磁盘保存中文，逐字节检查 UTF-8 BOM 和 CRLF；外部修改后保存被拒绝，草稿仍在 |
| 对话显示只能去设置调整 | 标题栏眼睛按钮：全部内容、思考与回复、仅模型回复；独立开关思考、调用、结果、实时活动 | 使用真实内核的文件列表工具和本地 HTTP 模型响应；验证隐藏与恢复、页面刷新、程序重启 |
| 面板缺少过渡 | 开合使用 200 ms 透明度 / 位移过渡，目录箭头和菜单有短动画；遵循减少动态效果偏好 | 实际 DOM / 截图核对；减少动态效果时无面板位移；拖宽时不播放布局补间 |
| 首次及连续请求启动慢 | 空闲内核预备、SDK 懒加载提前完成；初始化与 Git 快照并行；相同 tree / HEAD 的快照复用提交对象；保留连接池与内核复用 | 实际打包内核、真实 Git、HTTP socket 和请求阶段计时，见下表 |
| 刷新后管理内核返回旧的空会话 | 当前会话对象单独记录磁盘版本，目录扫描版本不再冒充对象版本 | 外部写入回归测试；打包 worker 写入多轮回复后刷新 / 重启均显示完整历史 |

另外修复附件校验的旧响应覆盖新导入状态，以及切换到“文件”标签后残留 Git 加载指示。文件编辑增加同文件重复点击、保存期间继续输入和会话切换后的草稿保护；截图复核修正了显示菜单开关受通用按钮高度样式影响的问题。

<a id="reverie-cli-workbench-repairs-2026-10-06--使用方式与边界"></a>

### 使用方式与边界

- 顶栏打开工作面板，左边缘调整宽度。默认 620 像素，首选范围 380–1100；实际可用宽度受窗口和左侧栏限制。原右侧的 AI 改动、上下文、活动已与 Git、文件、审查、运行合并。
- 文件树每个目录最多显示 2000 项并提示截断；`.git` 隐藏，指向工作区之外的符号链接不可打开。当前提供基础文本编辑，不包含 VS Code 的扩展、补全或调试器。
- 编辑限不超过 2 MiB 的 UTF-8 文本；保留 BOM / LF / CRLF。二进制、其他编码、混合换行文件使用只读预览或系统编辑器。每次保存检查磁盘哈希并串行处理同文件保存，临时文件完成后再替换。
- 未保存草稿在本次应用运行中保留，切换标签 / 折叠面板不会丢失；退出前应保存。模型任务运行期间禁止保存。版本复查能拦截已观察到的外部修改，不声称与任意外部写入程序实现跨进程原子锁。
- 新配置默认显示全部内容，思考正文默认展开；已有用户的自定义显示偏好保留。“仅模型回复”仍保留用户消息，只隐藏技术记录，不删除历史或改变模型上下文。
- 空闲预备不发起模型 HTTP 请求。每轮 Git 快照仍重新扫描文件和父提交；只有内容与父提交都相同才复用已有对象，各轮恢复引用仍独立。真实用户 Git 暂存区不被改写。

完整入口见 [桌面指南](DESKTOP_GUIDE.md)。

<a id="reverie-cli-workbench-repairs-2026-10-06--编译与回归"></a>

### 编译与回归

| 检查 | 结果 |
| --- | --- |
| 全量 Python | **1829 通过，1 跳过**，369.84 秒 |
| 全量 Desktop | **277 通过，1 跳过**，80.69 秒 |
| 最后文件 / 工作面板 / 池 / 快照定向回归 | **22 通过** |
| TypeScript 与翻译键 | 通过；1009 条翻译、82 个模板 |
| Windows 打包 | Python 桌面内核、Electron、renderer、NSIS 安装包和便携包生成成功；最终构建 **1735f0c36cfe26ba** |
| 打包应用实测 | 文件树 / 编辑 / 冲突、缩放布局、显示筛选、真实工具结果、Stop、模式切换、刷新 / 重启均通过；监测期间无 renderer 页面异常 |
| 文档链接与差异检查 | 44 份文档、462 个本地链接，0 错误；`git diff --check` 通过 |

实测启动的是 `ReverieCli-ui/release/win-unpacked/ReverieUI.exe` 及其新内核。可交付文件为 `ReverieCli-ui/release/Reverie-Setup-2.5.0-x64.exe` 和 `dist/Reverie-Portable-2.5.0-x64.exe`。本轮没有重新执行 NSIS 安装或便携包首次解压，也没有重建根目录 `dist/reverie.exe` 独立 CLI；不能把桌面验证扩大为这些路径均已验收。

<a id="reverie-cli-workbench-repairs-2026-10-06--请求耗时与取消"></a>

### 请求耗时与取消

本地使用独立工作区、真实 Git 和本地 HTTP 服务，模型仅返回合成短文本；不使用用户会话或仓库内容。5 次请求通过真实 IPC 发起，随后另测输入框发送。计时到服务端收到请求，包含内核 / Git / 上下文准备，不只是 TCP 建连。旧版对照是前一修复包的同类 fixture。

请求、开关和取消的计时采集于构建 `b6474095dbd94e96`。之后仅修正显示菜单开关的 CSS 高度，重新生成构建 `1735f0c36cfe26ba` 并复核窄窗口、文件 / Git 展示及对话 / 工具显示；请求代码和 Python 内核未再改变。

| 项目 | 旧包对照 | 本轮包 |
| --- | --- | --- |
| 首轮到达 HTTP 服务 | 3857.44 ms | 2548.93 ms |
| 后续四轮 | 668.13 / 875.07 / 2509.97 / 1164.21 ms | 595.62 / 621.98 / 581.10 / 594.00 ms |
| 后续四轮中位数 | 1019.64 ms | 594.81 ms |
| 连接 / 内核复用 | 原修复已有复用 | 五轮同 HTTP 连接、同内核 PID |
| Stop 到服务端断开 | 见前一报告 | 等响应头与停滞流各三次，**14.85–28.80 ms** |
| Stop 到界面结束 | 见前一报告 | 六次，**232.35–346.02 ms**；之后正常发送成功 |
| 流式开关界面反馈 | 见前一报告 | 六次，**0.9–2.4 ms** |
| 流式开关保存完成 | 见前一报告 | 六次，**60.3–121.8 ms** |

这是当前机器的小工作区样本，包含调度、Git 进程和自动化开销；旧包与新包并非随机交替测试。不能由此保证大型仓库、不同线路或冷启动每次一秒内完成，也不能把本地启动改进视为远端模型提速。Stop 的这组数字只覆盖模型 HTTP 等待，已经进入的工具动作仍按安全边界停止。

<a id="reverie-cli-workbench-repairs-2026-10-06--真实-nvidia-线路"></a>

#### 真实 NVIDIA 线路

使用配置中的 NVIDIA 凭据，只发送合成短提示，不记录密钥，不修改用户配置；请求体中的模型 ID 单独核对。

- 截图模型 `google/diffusiongemma-26b-a4b-it`：3 次 HTTP 200；响应头 **661.02–1270.37 ms**，首个 SSE 数据 **967.98–1479.76 ms**。只有一次含正文，正文首片段约 **1093.99 ms**；另外两次为空。
- 再以 256 token 上限发送一次短提示，仍只收到空首块、`finish_reason=stop` 和结束记录，服务端报告 1 个输出 token。这是上游实际返回的空正文，不能标成可用回答，也没有证据可将其归因于前端等待。
- 配置目录中的 `stepfun-ai/step-3.7-flash` 当次返回 **HTTP 410**，813.64 ms。保持错误可见，没有通过重复重试掩盖。
- 最初另一轮脚本被静态模型目录归一化为 `meta/muse-glimmer-30b`，该结果仅作为该模型的探测记录，**没有计入截图模型的样本**。

因此，本地可避免的启动与等待已经修复并测量；这两条模型路径仍存在上游可用性问题。全线路工具 / 思考 / 视觉矩阵、其他操作系统、原生 IME、长期任务等仍按 [功能状态](FEATURE_STATUS.md)保留验收边界。

<a id="reverie-cli-workbench-repairs-2026-10-06--可复核材料"></a>

### 可复核材料

本地 `.runtime` 文件为被忽略的验证产物；公开摘要不依赖它们存在。

- `.runtime/workbench-python-full.log`、`workbench-ui-final.log`、`workbench-focused-final.log`、`workbench-typecheck-final.log`：测试与类型检查。
- `.runtime/workbench-package-final.log`、`workbench-ui-repackage.log`：内核 / 桌面打包，以及最后 CSS 修正后的重新打包。
- `ReverieCli-ui/.runtime/workbench-smoke-20261006-091148/`：实际磁盘 fixture、`workbench-results.json`、服务端 socket 记录和明 / 暗主题、窄窗口、文件编辑、显示菜单截图。
- `ReverieCli-ui/.runtime/workbench-smoke-20261005-220454/baseline-latency.json`：旧包对照。
- `.runtime/nvidia-exact-model-latency-2026-10-06/`、`nvidia-exact-model-detail-2026-10-06/`、`nvidia-model-latency-2026-10-06/`：脱敏真实线路记录。

复跑测试：`npm --prefix ReverieCli-ui run typecheck`、`npm --prefix ReverieCli-ui test -- --maxWorkers=2 --testTimeout=15000`、`ReverieCli-py/venv/Scripts/python.exe -m pytest ReverieCli-py/tests -q`。文档链接使用 `python scripts/verification/check_docs.py` 离线检查；它不验证远端 URL。


---

<a id="skills-audit"></a>

<a id="skills-audit--skills-系统检查记录"></a>

## Skills 系统检查记录

> 原文件：`docs/SKILLS_AUDIT.md`。以下为当时的记录；日期、测试数字、限制与旧实施提示词均保留，不代表本次重新验收。


**历史快照，状态说明更新于 2026-10-05。** 下文保留 9 月的数量、路径和验证结果；当前内置包已新增 14 个设计 Skill，固定项的 Desktop 持久化、CLI/分叉缺口和资源打包方式见 [Skills 指南](SKILLS.md)及 [功能状态](FEATURE_STATUS.md)。本文不是当前全量测试通过的证明。

检查日期：2026-09-08 至 2026-09-09。环境：Windows、项目 venv 中的 Python 3.10.11。
检查基线为 `main` 的 `be90cab`，远端 `origin/main` 也已核对为同一提交。
本记录对应经用户审阅批准的改动；验证结果基于提交前的工作区源码。

<a id="skills-audit--已完成的修复"></a>

### 已完成的修复

| 问题 | 修复与验证 |
| --- | --- |
| UTF-8 BOM 导致 `SKILL.md` 元数据未解析 | 统一使用 `utf-8-sig` 读取，验证名称、描述、正文和显式调用。 |
| 中文关键词搜不到描述或正文 | 增加原文短语匹配，覆盖中文描述、正文以及无匹配查询。 |
| 非法资源路径直接抛异常 | 资源路径解析纳入错误处理；继续限制在技能包内，并保留二进制、编码及 2 MiB 上限检查。 |
| 内置技能的嵌套参考资料被 Git 忽略 | 为 reverse-skill 的嵌套 references 添加精确例外，227 份参考文件恢复为可提交内容。另有一份上游 reports 文件仍按上游规则忽略。 |
| photo-to-3d 引用了常规模式不可用的工具 | 将缺失参考图时的询问改为实际可用的 `userInput(question, reason)`。 |
| 内嵌浏览器 DevTools 本机请求误走代理 | 仅对本机 CDP HTTP 请求关闭环境代理；实测启动、输入、点击、页面读取、截图、控制台和关闭会话成功。 |
| Windows 内核信息 arch 为空 | 当 `platform.machine()` 为空时使用 Python 构建平台信息，覆盖 x64、arm64、ia32。 |
| Engine 端到端测试的独立探测误走代理 | 测试探测使用与运行时一致的直连方式；真实 Engine 任务生命周期测试通过。 |
| 递归打包收入 reports 和缓存 | setup.py 和 PyInstaller 数据收集排除 reports、Python/pytest/mypy/ruff 缓存，保留磁盘上的原文件。 |
| 桌面文件改动状态归并错误 | 根据操作前后文件是否存在归并状态；覆盖空文件新增/删除、删除后重建、恢复原内容，以及创建后删除。 |
| 跨模式提示要求调用不可用工具 | 保留 Skills 浏览及固定；Writer 和 Computer Controller 在模型提示、CLI 与桌面显示执行限制和切换方式。工具切换模式后立即刷新 Skills 模式。 |
| 打包目录本身位于 reports 下时遗漏全部 Skills | 排除规则只检查技能树内的相对路径，覆盖 reports/checkout 构建位置。 |
| 差异行数与实际预览不一致 | 内容以 ++/-- 开头仍正确计数；按最终可见预览统计截断行数，保留文件末尾无换行标记。 |
| 切换会话后保留旧的文件预览错误 | 切换会话时同时清除错误和改动；验证迟到请求不会污染新会话。 |
| 截图回退后仍宣称 full_page | 成功回退为视口截图时返回 full_page=false，覆盖两种截图结果。 |
| 错误弹窗太小、停留太短 | 右下角错误弹窗最多 520px 宽、至少 15px 字号，停留 12 秒，支持手动关闭、长文本换行与选择复制；适配窄窗口。 |

将原先放在 `test_desktop_changes.py` 中的两项 Skills 测试移入
`test_skill_resources.py`，桌面状态测试与 Skills 资源测试各自维护。
新增的打包和本机代理验证分别位于 `test_skill_packaging.py`、
`test_browser_controler_proxy.py`。

<a id="skills-audit--验证证据"></a>

### 验证证据

| 检查 | 结果 |
| --- | --- |
| 修复前 Python 全量测试 | 1537 通过、2 失败；失败分别为 arch 为空、Engine 独立 HTTP 探测被代理干扰。 |
| 最终 Python 全量测试 | 1575 通过、1 跳过，359.70 秒；使用项目 venv，正常 pytest 配置。 |
| 最终桌面端 Vitest | 131 通过、1 跳过，34.27 秒；使用默认测试进程配置，无启动超时。 |
| 桌面真实 Engine 集成 | 显式指定复制到 dist 审计目录中的 Engine 后，默认跳过的 1 项测试通过，15.62 秒；验证 SDK bridge 的发现、连接、动态工具、停用及正常关闭。 |
| 桌面端类型和 i18n 检查 | 通过。 |
| Electron 主进程及渲染器生产构建 | 通过；存在既有的 JS chunk 超过 500 kB 提示。 |
| reverse-skill 路由 | 175/175 基准用例通过，使用实际 PowerShell 路由脚本。 |
| reverse-skill 文档分块读取 | 44 份路由目标及 2 份核心文档，合计 266 块，46/46 完整重组与原文件一致。 |
| Wheel 资源清单及解包导入 | 当前 Python 源码的 604 个应发布内置资源全部存在且逐文件内容一致；报告与缓存为 0；4 个内置 Skills 均能发现，46 份文档完整读取、中文搜索及 Writer 固定/切换提示通过。 |
| 源码发布包 sdist | 同样包含全部 604 个内置资源，内容逐文件一致，无报告或缓存。 |
| PyInstaller 数据收集 | 执行 spec 中实际的收集函数及 Skills 调用，确认参考资料保留、报告缓存排除。未重新构建完整 exe。 |
| 浏览器真实交互 | 独立 Chromium 页面中的输入与点击改变了标题，DOM 与截图均观察到预期文本，会话已关闭。 |
| 错误弹窗布局 | 使用实际项目 CSS 的独立 Chromium 布局检查：1280px 与 360px 窗口、深浅两种主题均无横向溢出，字号 15px，宽度分别为 520px 和 324px。交互及计时另由 App 回归测试覆盖。 |

Python 跳过项为符号链接越界验证：本机不允许创建符号链接。
桌面全量测试的跳过项为需要显式指定 Engine 可执行文件的集成测试，已单独启用并通过。
绝对路径、普通目录穿越、非法路径、编码、二进制和大小限制均已验证。
浏览器全页截图在本次最小化窗口测试中回退为视口截图，工具已返回回退说明；
本次证据不证明长页面全页截图能力。

本地日志和测试产物放在仓库 `dist/skills-audit/` 以及
`dist/skills-audit-python-current.log`、`dist/skills-audit-ui-current.log`、
`dist/skills-audit-ui-build.log`，不纳入源码提交。
Wheel 构建依赖仅临时安装到 `dist/skills-audit/build-tools/`。
审阅源码的 wheel 和清单位于 `dist/skills-audit/wheel-reviewed/`。
最终候选源码清单及逐文件 SHA-256 位于 `dist/skills-audit/review-inventory.json`，
共 625 个文件（包含新导入的上游资源）。本项目代码及适配层的暂存差异空白检查通过；
新导入的 upstream 原文保留上游尾随空格和末尾空行（包括 Markdown 硬换行），
全范围 `git diff --cached --check` 会报告这些格式问题，不对上游资料批量重排。

<a id="skills-audit--内置-skills-的可用范围"></a>

### 内置 Skills 的可用范围

| Skill | 已确认范围 | 未覆盖范围 |
| --- | --- | --- |
| browser-controler | 发现、调用说明、真实独立浏览器交互、页面和视口截图证据。 | 任意外部站点、真实登录/上传流程、长页面全页截图。 |
| photo-to-3d | 元数据、完整工作流正文、全部参考资料、工具名称以及浏览器检查基础链路。 | 未用用户照片完整执行八阶段建模，未证明模型生成质量。 |
| reverie-engine | Gamer 模式发现与模式门控；全量测试中的游戏循环、资源与真实 Engine 任务生命周期。 | 未重新发布独立 Engine 或 CLI exe；不将单元测试等同于任意游戏交付。 |
| reverse-skill | 作为一个顶层包发现；175 个路由用例、44 个路由文档、核心资源和发布完整性。 | 外部逆向工具/MCP 未安装或启动；未逐个执行所有安全分析场景。 |

`reverse-skill/UPSTREAM.md` 已记录 5 份导入时被杀毒软件阻止的参考文档缺失。
依赖这些文件的流程不能宣称完整可用；本次没有尝试补取或绕过该限制。

跨模式策略已完成：保留通用 Skills 的发现、浏览和固定。
Writer 显式提示先切换再检查技能，Computer Controller 提示执行依赖工作区工具的流程前切换；
使用 `switch_mode` 或 `/mode reverie`，固定状态会保留。
Reverie、Atlas、Gamer 保留原工具能力；reverie-engine 仍遵守既有 Gamer 模式门控。

<a id="skills-audit--最终提交范围"></a>

### 最终提交范围

包括 Skills 系统与内置资源、模式说明、浏览器及内核修复、打包规则、桌面文件改动预览、
已有桌面侧栏和 Thinking Tool 显示改动，以及本次新增的错误弹窗调整与回归测试。
保留 reverse-skill 的上游归属、许可证和缺失文档说明。
不包含 dist 下的构建产物、测试日志、缓存和临时依赖。

用户已授权自主修复检查中发现的问题，并于审阅后明确批准提交。
提交及推送目标为当前仓库的 `main`，不创建 PR。


---

<a id="context-engine-benchmark"></a>

<a id="context-engine-benchmark--context-engine-retrieval-results"></a>

## Context Engine Retrieval Results

> 原文件：`docs/CONTEXT_ENGINE_BENCHMARK.md`。以下为当时的记录；日期、测试数字、限制与旧实施提示词均保留，不代表本次重新验收。


On 2026-07-18, the Context Engine was evaluated locally as a file-localization system using real SWE-bench Lite issue statements and patch files. The benchmark environment, dataset, repository snapshots, caches, and raw results are intentionally not versioned.

| Evaluation | Instances | Recall@5 | Recall@10 | MRR@10 | Query p50 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Broader cross-repository validation | 23 | 0.522 | 0.609 | 0.351 | 245 ms |
| Frozen unseen subset, original `main` | 7 | 0.429 | 0.429 | 0.226 | 598 ms |
| Frozen unseen subset, optimized | 7 | 0.714 | 0.857 | 0.354 | 245 ms |

The seven unseen cases were held back until the retrieval changes were frozen, so they test generalization rather than case-specific rules. The sample is still small: these figures are a development result, not a universal-performance claim, and full release qualification requires all 300 instances plus broader cross-language tasks.

<a id="context-engine-benchmark--2026-07-21--corpus-absent-query-expansion-filtering"></a>

### 2026-07-21 — Corpus-absent query-expansion filtering

Failure analysis of a 284-instance partial run (Recall@1 0.472, Recall@5 0.736, Recall@10 0.803, MRR@10 0.584, nDCG@10 0.637) showed the dominant miss pattern was query-term fabrication rather than a retrieval-channel gap. Two query-expansion heuristics were synthesising terms that name nothing in the codebase, and because a zero-body term receives the rare-term IDF bonus, those fabrications rose to the top of the weighted term list and displaced the real query signal:

* **Joined prose compounds** — every adjacent word pair was concatenated (`"undefined expression"` → `undefinedexpression`, `"feature request"` → `featurerequest`). The heuristic exists to recover split names such as `"auto detector"` → `autodetector`, but most pairs are noise.
* **Reproduction-snippet dotted fragments** — local-variable method calls lifted from issue repros (`r.limit`, `e.subs`, `publication.objects`) were weighted as stable identifiers.

The fix filters both against the corpus: a compound is kept only when it has non-zero content document frequency or is a substring of a real symbol/file name, and a dotted fragment is dropped when its content document frequency is zero (its already-emitted attribute suffix is retained). A query term that resolves to nothing in the index is noise by definition, so this is a general information-retrieval correction, not benchmark tuning. It adds no runtime dependency, reuses the existing FTS content-frequency lookup, and leaves indexing cost unchanged.

Held-out profiles (indices rebuilt per instance), before → after the filter:

| Profile | Instances | Recall@1 | Recall@5 | Recall@10 | MRR@10 | nDCG@10 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Holdout | 12 | 0.67 → 0.67 | 0.92 → 1.00 | 0.92 → 1.00 | 0.75 → 0.79 | 0.79 → 0.85 |
| Blind | 9 | 0.56 → 0.67 | 0.67 → 0.89 | 0.89 → 1.00 | 0.62 → 0.77 | 0.68 → 0.83 |
| Generalization | 10 | 0.40 → 0.50 | 0.50 → 0.60 | 0.60 → 0.60 | 0.47 → 0.52 | 0.50 → 0.54 |

Every profile improved or held with no regression. A separate, pre-existing robustness item remains open: a file that is the top hit in the strongest lexical channel can still jitter in and out of the top ten across parallel index builds, because parallel parsing does not fix symbol ordering and the fusion tie-break depends on it. That is a ranking-stability question rather than a term-quality one and is deferred.

<a id="context-engine-benchmark--2026-07-22--deterministic-parallel-indexing-resolves-the-deferred-stability-item"></a>

### 2026-07-22 — Deterministic parallel indexing (resolves the deferred stability item)

Investigating the ranking jitter noted above revealed that it was the visible symptom of a deeper, more serious defect: **parallel indexing was not deterministic and, worse, not correct**. Building the same tree three times with `max_workers=8` produced different symbol counts each run (e.g. 1108 / 1109 / 1110), whole modules' symbols appearing and disappearing between runs, while the indexer still reported every file parsed with zero failures. A serial (`max_workers=1`) build was already stable.

Two independent causes were found and fixed:

* **Shared stateful parsers (data corruption).** A single set of parser instances was shared across every worker thread. Parsers keep per-parse state on the instance (`PythonParser` stores the current file's content, line list, and module name; `TreeSitterParser` holds a live parse cache), so two threads parsing different files at once clobbered each other — dropping and misattributing symbols. Each worker thread now builds and reuses its own parser pipeline via a thread-local, so at most `max_workers` pipelines exist and no instance is ever touched by two threads. This restores correctness: a parallel build now extracts *exactly* the same symbols as a serial build.

* **Insertion-order-dependent index state (ordering jitter).** Symbols and dependency edges were merged in thread-completion order, so `SymbolTable._symbols` and the dependency adjacency lists carried a nondeterministic order into lookups. Read paths that pick the first match (`find_by_name`/`find_by_pattern`/`find_by_prefix`/`get_by_kind`) and the serialized cache therefore varied run to run — and the first `find_by_name` result is the ranking *anchor*, the heaviest fusion channel. The index state is now canonicalized by qualified name when it is committed (`SymbolTable.replace_with`, `DependencyGraph.replace_with`), and the lookup methods sort before truncating, so both the ordering and the truncated membership are stable.

After both fixes, five consecutive 8-worker builds of the Context Engine package produced an identical symbol list (1112 symbols), an identical dependency graph, and output byte-identical to the serial build. The retrieval and ranking logic was not touched; this is purely an indexing-layer correctness and determinism fix. Regression tests assert (a) insertion-order independence of the symbol table and dependency graph and (b) that a parallel `full_index` matches a serial one and repeats exactly across runs.

With this in place the ranking-stability item deferred on 2026-07-21 is resolved at its source: the top lexical-channel hit no longer jitters, because the index it is derived from is now reproducible.

<a id="context-engine-benchmark--2026-08-10--indexquery-analysis-symmetry-for-compound-identifiers"></a>

### 2026-08-10 — Index/query analysis symmetry for compound identifiers

Studying [`alibaba/zvec`](https://github.com/alibaba/zvec), whose full-text stack models analysis as an explicit *pipeline* (tokenizer → token filters, run identically at index and query time), surfaced a structural asymmetry in this engine: the two sides did not agree on what a token was.

SQLite FTS5's `porter unicode61` splits on underscores but stores `ModelAdmin` as the single opaque token `modeladmin`. The retriever's query tokenizer, however, *does* split camel case. The consequence was silent and total: a query for `model`, `admin`, `user`, or `name` returned **zero** hits against a file defining `ModelAdmin.getUserName`. One Django worktree contains 6,369 distinct camelCase identifiers across 80,382 occurrences — and Django is snake_case-dominant, so camel-heavy ecosystems (JavaScript/TypeScript, Java, Go) lose substantially more.

The fix supplies the missing token-filter half of the pipeline (`context_engine/text_analysis.py`) and indexes its output in a dedicated `subwords` column on both `content_search` and `chunk_search`. Three design choices matter:

* **A separate column rather than appending to `body`.** Inlining the expansion would inflate the primary field's term frequencies and document lengths, corrupting BM25 for the original spellings. A distinct column is independently weighted (`bm25(content_search, 1.0, 0.35)`; `bm25(chunk_search, 5.5, 3.0, 1.8, 1.0, 0.6)`) so an exact match on the full identifier always outranks a sub-token match.
* **One entry per distinct sub-token per document, not per occurrence.** The goal is to make a term *reachable*; frequency signal stays with the text as written. Index growth measured on Django: **1.4%**. Per-occurrence emission would have roughly doubled it.
* **No snake_case expansion.** `unicode61` already splits underscores, so expanding it would double the vocabulary for no recall gain.

A `PRAGMA user_version` schema guard discards caches written before the new column, which would otherwise be appended to with mismatched column arity.

**The instructive part of this change was a regression it initially caused.** `content_document_frequencies()` issued its `MATCH` unscoped, so the new column immediately began contributing to document frequency: every `*Admin` symbol donated an `admin` posting, making precisely the discriminative terms look common and stripping them of the rare-term IDF bonus. This re-created, through a new door, the exact defect corrected on 2026-07-20. Holdout fell to Recall@1 0.583 / nDCG 0.804. Scoping the frequency query to `body` restored and slightly exceeded the baseline. The general rule, now covered by a regression test: **an expansion column may broaden reachability, but must never enter term statistics.**

Held-out profiles (indices rebuilt per instance), baseline → final:

| Profile | Instances | Recall@1 | Recall@5 | Recall@10 | MRR@10 | nDCG@10 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Holdout | 12 | 0.67 → 0.67 | 1.00 → 1.00 | 1.00 → 1.00 | 0.781 → 0.794 | 0.835 → 0.846 |
| Generalization | 10 | 0.50 → 0.50 | 0.60 → 0.60 | 0.60 → 0.60 | 0.520 → 0.520 | 0.539 → 0.539 |
| Blind | 9 | 0.56 → 0.56 | 1.00 → 1.00 | 1.00 → 1.00 | 0.731 → 0.713 | 0.799 → 0.785 |

Holdout improves; generalization is unchanged to the last digit; blind loses one instance from rank 2 to rank 3 (the ΔMRR of 1/54 is exactly (1/2 − 1/3)/9). The honest reading of a ±1-instance movement on a 9-instance profile is noise, not signal — these sets are too small for a single rank shift to carry meaning. The change is justified by the mechanism it corrects, which is a genuine recall hole on camel-cased code that these Python-dominated profiles are poorly positioned to measure.

**One candidate change was tested and rejected.** Replacing the counter in `_score_file_content_for_task` with textbook BM25 saturation and length normalization produced *bit-identical* results across all 35 tuning instances (`quick` n=12, `validation` n=23 — every metric equal to the last digit). That function is not a retrieval channel: it re-scores the top-32 candidates already selected by the FTS channels, so it can reorder a shortlist but never change its membership. It was reverted rather than kept as unmeasurable complexity. One real defect found inside it was kept: the scoring loop terminated once it had collected four *reasons*, silently abandoning every remaining query term.

<a id="context-engine-benchmark--the-schema-guard-was-itself-a-bug"></a>

#### The schema guard was itself a bug

The `PRAGMA user_version` guard above was written to drop and rebuild an incompatible index. Checking where it actually fires showed that this was backwards. `_begin_content_index_rebuild` unlinks its target and builds into a fresh temporary file, so `user_version` is always 0 there and the drop branch never runs. The only caller that can reach it is `_begin_content_index_update` — the *incremental* path, which opens the existing database and then rewrites **only the files it was handed**. Dropping the tables there discards every unchanged file's postings and re-inserts a handful, while `incremental_index` still reports success.

A three-file reproduction reduced the content index to the single changed file. The condition needed to hit this is ordinary: upgrade the build, edit one file, and let the watcher fire before any full re-index. Search then silently misses most of the repository, with no error and a valid-looking cache on disk.

The guard now distinguishes the two callers. A rebuild may discard, an in-place update raises `OutdatedContentIndexError` and leaves the old database untouched and readable; `incremental_index`'s existing handler catches it and skips content indexing for that pass, because both write helpers are already no-ops when the connection is `None`. `CacheManager.CACHE_VERSION` moves to `1.11.0` in the same change, which is what forces the full rebuild that legitimately replaces the layout — the two counters have to move together, since nothing re-indexes while the JSON cache still validates.

The prior regression test asserted the drop-and-recreate behaviour, so it encoded the bug as expected output. It passed only because its fixture held one file, making the loss invisible. It is replaced by a multi-file test that fails against the old behaviour on the reachability assertion, plus a test pinning the `CACHE_VERSION` rejection. Holdout is unchanged at Recall@1 0.667 / MRR 0.794 / nDCG 0.846 — bit-identical to the pre-fix run, as expected for a fix on a path the benchmark's rebuilt-per-instance indices never take.

The general lesson is the same one the DF regression taught, in a different register: a guard is only correct relative to the caller that reaches it, so it is worth checking which callers actually can. Here the branch that looked like the safety mechanism was unreachable from the safe caller and destructive from the unsafe one.


---

<a id="2026-09-27-chat-performance"></a>

<a id="2026-09-27-chat-performance--chat-performance-and-real-agnes-task-verification"></a>

## Chat performance and real Agnes task verification

> 原文件：`docs/verification/2026-09-27-chat-performance.md`。以下为当时的记录；日期、测试数字、限制与旧实施提示词均保留，不代表本次重新验收。


Date: 2026-09-27. Windows, Electron 41.2.1, Reverie 2.5.0.

<a id="2026-09-27-chat-performance--conversation-loading"></a>

### Conversation loading

The baseline renderer uses `App.tsx` from `21c6fb472e53495b641f62e0848068bc92e2426d`.
Both renderer builds use the same surrounding assets and compiled Python kernel,
an isolated profile and a visible 1480×940 Electron window. The saved conversation
contains 1200 records; half contain Markdown paragraphs and a table. Each timing
includes the UI click, settled session state and two animation frames. This is one
local comparison, rather than a statistical claim about all machines or providers.

| Measurement | Baseline | Optimized |
| --- | ---: | ---: |
| First open of long conversation | 1422 ms | 178 ms |
| Return to cached long conversation | 2216 ms | 119 ms |
| Return to short conversation | 117 ms | 59 ms |
| Composer update | 57 ms | 16 ms |
| Longest observed main-thread task | 1183 ms | 90 ms |
| Initially mounted history records | 1200 | 60 |
| Scroll shift when prepending 60 records | not measured | 0 px |

Raw data: [baseline](verification/chat-performance/before-final.json),
[optimized](verification/chat-performance/after-final.json).

The later timeline/task-bar build was measured again with the same 1200-record
fixture and its newly compiled kernel. Across four local runs, first open ranged
from 287 to 861 ms and cached return from 185 to 777 ms; every run mounted 60
records and preserved a 0-pixel scroll anchor. One five-update typing probe had
a 38 ms median (33–108 ms). The run's longest main-thread task was 685 ms.
The old renderer on that same newly compiled kernel also showed large timing
swings (including a 2606 ms short-session switch), so these later single-machine
measurements do not establish a stable change in responsiveness from the new
timeline. Raw data: [final UI run 1](verification/chat-performance/optimized-ux-final.json),
[run 2](verification/chat-performance/optimized-ux-repeat.json),
[run 3](verification/chat-performance/optimized-ux-third.json),
[run 4 with typing samples](verification/chat-performance/final-ux.json), and
[old renderer control](verification/chat-performance/optimized-old-samples.json).

The implementation renders recent history first and preserves the scroll anchor
when loading earlier records. Stable history/live Markdown is memoized. Unchanged
transcripts retain their cached objects through file revisions. Context statistics
are debounced, deduplicated, cancelled on navigation and read without activating
old sessions or rewriting memory. Repeated selection and pending-load/stream races
have regression coverage. Streaming follows the bottom only while the reader is
already there.

<a id="2026-09-27-chat-performance--reproduce-the-local-loading-benchmark"></a>

#### Reproduce the local loading benchmark

Install the desktop dependencies and Python development environment; install
Playwright in that Python environment for the measurement driver. Build the
renderer/main process and directory kernel:

```powershell
cd ReverieCli-ui
npm ci
npm run build
npm run build:kernel
cd ..
$env:PERF_KERNEL = (Resolve-Path ReverieCli-ui\.kernel\reverie\reverie.exe).Path
& ReverieCli-py\venv\Scripts\python.exe scripts\verification\chat-performance\measure.py optimized
```

Outputs and isolated state are under `.audit/chat-perf/`. `PERF_RENDERER_ROOT`
can select a separately built baseline renderer. Run with no packaging process
competing for CPU/disk. The benchmark does not call an external model or use the
user's account configuration.

<a id="2026-09-27-chat-performance--conversation-timeline-and-task-continuation"></a>

### Conversation timeline and task continuation

The desktop now renders assistant progress text and tool groups in transcript
order. Each group is collapsed by default and each tool row can be opened to
read its arguments and result. History preserves the same sequence after a
session reload. The composer task bar uses TaskManager's structured checklist:
its header shows the current item, and its expanded view shows the full list.

The desktop records the active prompt and saves stable history boundaries during
the turn. After an interrupted run, Continue task issues `resumePrompt` against
the existing session, without adding a user message or touching an unsent draft.
If a hard stop left a tool call without a recorded result, the agent records that
its outcome is unknown instead of repeating a possible side effect automatically.
One provider response may contain several tool calls; they are all handled before
the next model request. Execution remains serial so writes and commands retain
their original order.

The real Agnes website exercise below predates these interface controls. The
timeline, task bar, resume protocol and two-call response have separate renderer,
bridge and agent regression tests; the final packaged runtime smoke is reported
in the build section.

<a id="2026-09-27-chat-performance--real-agnes-task"></a>

### Real Agnes task

The model built a Python standard-library/SQLite task-board website, using the
real Agnes API through the compiled desktop package. The generated application,
prompts and verification artifacts are retained locally under
`.audit/agnes-task/local-example/`; the sample application is excluded from the
GitHub submission at the user's request.

The initial generated tests failed (one failure and 14 errors out of 25).
Diagnostic feedback was supplied to Agnes, which repaired its application and
fixture. Application source was not manually patched. Final verification results
were rerun independently: 29 application tests and 7 HTTP contract tests passed,
including restart persistence and 25 concurrent POSTs. Chromium CRUD, keyboard
submission, counts, hostile-title text rendering and the 390-pixel layout passed.
The 200-request localhost GET probe measured p50 1.29 ms and p95 1.57 ms.

An additional local Agnes 3.0 Flash run exercised interruption and
`resumePrompt` against the frozen kernel. The process was stopped immediately
after its first recorded tool result, then resumed with no new user message.
The resumed session retained exactly one user message and generated
`slugify.py`, `test_slugify.py`, and `README.md`. Some Agnes API requests timed
out and required another `resumePrompt`; the final response succeeded and the
stored task state became `completed`, still with one user message. Independent
verification of the final Python files passed 7 unit tests and `compileall`.
Its workspace, profile, and diagnostic output remain local under
`.audit/agnes-resume/`.

<a id="2026-09-27-chat-performance--runtime-issues-found-by-the-task"></a>

### Runtime issues found by the task

The initial packaged run stalled in shadow Git initialization before writing a
file. A later run wrote the application but stalled while starting Python tests.
The repaired subprocess launch uses closed stdin and `CREATE_NO_WINDOW` on
Windows. Shadow Git now has deadlines
(15 seconds for initialization, 60 seconds for other operations). Pure task progress
updates skip workspace checkpoints. Real file mutations retain their checkpoints.

The command tool previously passed `&&` literally to the executable rather than
running a shell chain. It now rejects shell operators with a request to execute
commands separately, while retaining quoted operator text as data and existing
PowerShell cmdlet pipelines. The tool's description explains this before model
execution.

A successful repair/test run was followed by an automatic generic edge-case
verification turn, extending the run by about 200 seconds and ending in
preparatory prose. That unconditional extra turn was removed. Missing actual
edits or successful verification still trigger continuation. Explicit requirements
remain part of the batch instructions and are independently checked here.

The exact cause of the inherited-console startup wait was not isolated to a
specific Windows API. The launch change is verified by the subsequent packaged
provider run, rather than an assertion that a particular DLL caused the stall.

<a id="2026-09-27-chat-performance--build-and-regression-gates"></a>

### Build and regression gates

- The staged renderer/main source passed TypeScript and translation checks.
- Full UI suite: 160 passed, 1 skipped across renderer and Electron. The final
  preference-default change passed its 10 focused tests.
- Python desktop bridge, agent continuation, token accounting, loading,
  workspace guard, command execution, permissions and batch prompt tests:
  193 passed.
- The actual Python directory kernel and desktop production renderer/main process
  were compiled. The packaged ASAR renderer's source map matched staged `App.tsx`.
  A packaged Electron smoke exercised the chronology, collapsible tool details,
  full task list, Continue button and unsent-draft preservation.
- Windows installer and portable executables were built locally; build outputs and
  provider credentials are excluded from the Git commit.


---

<a id="memory-runtime-review-2026-09-26"></a>

<a id="memory-runtime-review-2026-09-26--memory-runtime-review--2026-09-26"></a>

## Memory runtime review — 2026-09-26

> 原文件：`ReverieCli-py/docs/memory-runtime-review-2026-09-26.md`。以下为当时的记录；日期、测试数字、限制与旧实施提示词均保留，不代表本次重新验收。


本次范围为记忆管理的 remember/list/get/correct/delete/consolidate/conflicts/status、recall/answer、上下文组装、工具执行、模型请求及 Windows 交付。GUI 原生交互及其他产品功能未纳入这轮验收。

<a id="memory-runtime-review-2026-09-26--已修复的逻辑与性能问题"></a>

### 已修复的逻辑与性能问题

- 记忆操作和只读工具不再触发全工作区 Git 检查点；检查点失败后会恢复 active tool 上下文，并记录失败结果。工具计时包含前置检查点。
- 最近事件从 JSONL 尾部按块读取，找到足够结果即停止；保留原有顺序与筛选语义，支持跨块 UTF-8、长记录、无末尾换行和损坏行。
- 新增记忆直接检查已提交记录与全文索引，不再执行全库排名或增加其他记忆的访问计数。
- 检索只更新访问元数据，不重建全文索引。缓存有界的不可变文本特征，避免多样性排名中的重复分词；时间、置信度、访问次数仍按当前记录计算。
- 无搜索词的列表在数据库中应用范围、类型、会话及数量限制。
- 会话记忆记录所属会话，并在去重、冲突检测与检索中隔离；相同正文不会覆盖其他会话的记录。
- 已被替换或已删除的记录不能通过 correct 或 remember 复活、分叉并破坏历史；只合并仍有效的重复记忆。
- HTTP 和 OpenAI Chat 请求遵守配置的重试次数与退避；关闭 Chat SDK 的叠加重试，非兼容性 4xx 不再重发相同请求。Responses SDK 保留独立的配置重试。
- 一次模型请求复用同一份上下文，随后转换本地图片，避免重复组装；Responses 请求也复用已组装消息。
- 修复运行时的强制工具路由：明确调用记忆工具或修改/删除指定记忆 ID 时，不因正文包含“项目”“测试”等词而强制查代码。修改记忆模块的源代码仍先调用 Context Engine。
- 提示词及实际工具 schema 要求模型自行组织简洁、独立的记忆正文。Memory OS 负责结构化存储；应用没有硬编码用户的记忆正文。

<a id="memory-runtime-review-2026-09-26--本地基准"></a>

### 本地基准

同一台机器、真实 SQLite/FTS5、2,000 条记忆、50,000 条 JSONL 事件；每项重复五次取中位数。重复检索包含缓存收益。这些数字不是远程模型端到端延迟，构建并行时会有波动。

| 操作 | 修改前 | 修改后参考值 |
| --- | ---: | ---: |
| 最近 20 条事件 | 361.4 ms | 0.258 ms |
| 筛选最近 20 条事件 | 474.8 ms | 0.703 ms |
| 检索 8 条记忆 | 393.5 ms | 110.023 ms |
| 新增记忆 | 464.4 ms | 95.296 ms |
| 列出最近 20 条记忆 | 50.8 ms | 1.940 ms |

参考测量文件：`build/memory-review-benchmark-final.json`。最终运行也会在各自 JSON 报告内记录基准。

<a id="memory-runtime-review-2026-09-26--可重复的真实循环"></a>

### 可重复的真实循环

```powershell
cd G:\Reverie\Reverie-Cli\ReverieCli-py
.\venv\Scripts\python.exe scripts\smoke_memory_runtime.py --config ..\dist\.reverie\config.json --executable ..\ReverieCli-ui\release\win-unpacked\reverie.exe --cycles 1 --report ..\build\memory-smoke.json
```

省略 `--executable` 测源码；改为 `..\dist\reverie.exe` 测独立 CLI；省略 `--config` 只跑本地基准。`--cycles 2` 在同一临时项目重复循环，轮间暂停 60 秒。

循环为：新增中文简洁回答偏好 → 检索 → 修改为中文详细回答偏好 → 再检索 → 删除。直接检查实际数据库、版本、模型生成正文、工具结果和检索输出。没有模拟模型、伪造工具成功或写入用户真实项目记忆。

凭据从指定配置或 `AGNES_API_KEY` 读取，仅通过内存/环境传递；临时配置不含密钥。报告记录实际耗时和源运行中的模型等待时间。

连续请求曾真实触发 Agnes 免费用户的 429 限流，包括“工具已成功、最终模型确认被限流”的情况。因此脚本默认步骤间隔 15 秒；`--step-delay 0` 可以进行无间隔压力测试。间隔单独报告，排除在单步耗时之外，应用运行时没有这个人工间隔。成功的有间隔循环不能证明免费 API 可无限连续请求。

<a id="memory-runtime-review-2026-09-26--验证与交付证据"></a>

### 验证与交付证据

- Python 相关回归：403 项通过。
- 桌面 Vitest：151 项通过，1 项跳过；UI 编译通过。
- Windows CLI、桌面内核、安装包和便携版按最终源代码重新编译；内核 `--kernel-info` 与 SDK bridge ready/shutdown 协议检查成功。
- 最终源码及交付内核循环的逐步结果保存在 `build/memory-review-source-final.json` 和 `build/memory-review-release-final.json`；更早的源码、目录内核、独立 CLI 循环也保留在 `build/memory-review-*.json`。
- 原 CLI 和便携版备份：`build/memory-review-backups/`。未修改用户的凭据、实际项目记忆或模型选择。

GUI 原生交互没有单独验收；真实测试覆盖与桌面共用的后端执行链。模型有时仍会自主追加记忆 get 调用，外部响应时间和免费限流仍有波动。旧记录如果没有会话 ID，无法可靠猜测所属会话；此修复保留这些旧记录，未迁移或重写用户历史。

最终源码单步耗时：新增 15.307s、检索 7.503s、修改 10.245s、再次检索 18.252s、删除 8.142s；相应记忆工具 9–18ms。交付包内核：28.498s、9.279s、13.570s、12.011s、10.008s；工具 7–17ms。每轮额外的 4 次 15 秒测试间隔共 60 秒，已单独记录，未计入这些单步耗时。两轮最终报告均为成功，工具调用均属于 memory_manager/memory_retrieval。

交付文件的 SHA256 和大小已核对，记录于 `build/memory-review-artifacts.json`：实际 CLI 与暂存 CLI 一致，交付包内核与编译内核一致。
