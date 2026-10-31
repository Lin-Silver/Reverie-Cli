# 功能状态与已知缺口

2026-10-31: 2.5.3 integrates Cloud RIU and Liquid Glass, fixes light-theme opaque accessibility materials, and shows user avatars without message names. The user authorized main publication. See [2.5.3 verification](verification/2026-10-31-v2.5.3/README.md) for current checks and remaining model/platform acceptance limits.


2026-10-30：本地 Liquid Glass 与云端 dev `894fe6e` 已整合，保留经典界面和 RIU 富格式路线。Windows 联合目录包与本轮回归证据见[本地整合记录](verification/2026-10-30-desktop-integration/README.md)。此记录不关闭历史模型质量及跨平台安装验收缺口。

2026-10-28 GitHub 接续更新：用户已明确授权将本轮全部仓库改动提交到新的 `dev` 分支；本轮授权覆盖此前禁止提交/推送的限制，不含版本升级或 Release。[接续说明](CONTINUE_RIU.md)与[可克隆 goal/关键证据](verification/2026-10-28-dev-handoff/README.md)已补齐。**最新源码还包含保留 v12 之后的 Linux 安装链接启动器修复；它的回归测试已有覆盖，但包含此修复的新安装包尚未验收，优先完成此项。** 此前 v12 通过记录仅对应原包；整体 RIU 仍未完成。实际提交 SHA 与远端推送结果以交付消息及 GitHub 分支为准。

2026-10-27 最新状态：参考图中的统计卡片、总览表、图文推荐、徽标、来源与链接已在当前源码 Linux x64 包验证。v12 build `fcce0356b0365178` 的 AppImage 真实 FUSE 挂载下，富格式 **86/86**、P2 **24/24**；提取后的同包程序 P3 **26/26**、P4 **31/31**、隔离 **36/36**。P4 基线输入/注册交互 P95 为51.8/332.864ms；同包扩展60次压力循环31/31通过，注册交互/输入 P95 为286.16/47ms，最大360.888/62.9ms。压力仍属合成本地运行。当前 deb 在 rootless Bubblewrap 隔离根中，以宿主 Debian 13 的依赖清单完成 v11 安装、v12 升级与卸载，未用 `--force-depends`，且宿主机状态无变化；这不是宿主系统级安装或桌面启动验证。当前源码 Qwen3.5-4B 一次合成应用内请求精确呈现四项指标、两行表格和带徽标/来源/链接的推荐卡，深浅主题和1280/460px布局通过，浏览器错误0；正式模型质量样本仍为0。

Debian 13 只读 APT 依赖模拟通过，当前 t64 兼容包满足 v12 deb 必需依赖；Bubblewrap 隔离全生命周期测试也在依赖满足状态下安装、升级和卸载成功，未执行宿主系统级安装。仓库 `package-validation.mjs` 对已核验 v12 载荷在新临时输出目录重试 deb/AppImage 均退出0；最初两次退出1的日志保留，原因未确定。旧 v11 Pillow 缺件和 v12 首次 OOM 也保留。整体尚未达标：Windows/macOS 实机、物理输入与辅助技术、长时稳定性未验收；正式模型质量仍未接受，且不得启动第三组。详细结果见[实施清单](RIU_COMPLETION_PLAN.md)、[路线与包重建证据](verification/2026-10-27-static-rich-routing/README.md)、[结构化记录](verification/2026-10-27-static-rich-routing/package-rebuilds.json)。

完整 RIU 仍未验收达标。第2正式组按两组上限收尾：60个位置中59份完成评测、1份中断，原始自动31项合格、4项被人工否定，剩余27项不等于完整人工验收。模型质量、Windows/macOS实机、物理输入与辅助技术仍未验收；当前 Linux 构建成功不关闭这些缺口。见[实施清单](RIU_COMPLETION_PLAN.md)与[当前原生证据](verification/2026-10-26-rich-answer-ui/native-package-suites.json)。

上一阶段（2026-10-25）：已按用户参考图实现**回答 UI/UX 与格式样式**：统计卡片、状态表格、图文推荐、来源与链接，支持深浅主题、窄容器、流式输出和会话重开。[格式说明](RICH_ANSWER_UI.md)与[实际原生截图和验证](verification/2026-10-25-rich-answer-ui/README.md)已记录。当时 Linux 包 **c9df6ba5417e0851**；Desktop **407/1**、Python **2314/24**、类型检查通过，最终包原生 P2/P3/隔离 **24/26/36** 通过。真实模型回答及两张远程图片实际显示成功，完整 27 工具和采样设置保留。旧正式矩阵依最新优先级停在 15 项，不宣称完成 36 项或整体模型质量验收。

状态汇总更新：**2026-10-24，版本 2.5.0**。逐项功能审查基线为 2026-10-05–06，后续检查按日期注明范围。本文描述当前实现；开发优先级和闭环条件统一维护在 [ROADMAP](ROADMAP.md)。[审查报告](VERIFICATION_HISTORY.md#reverie-cli-feature-audit-2026-10-05)保留修复前复现，[首轮修复报告](VERIFICATION_HISTORY.md#reverie-cli-feature-repairs-2026-10-05)、[请求 / 个人资料修复报告](VERIFICATION_HISTORY.md#reverie-cli-request-profile-repairs-2026-10-05)与[工作面板修复报告](VERIFICATION_HISTORY.md#reverie-cli-workbench-repairs-2026-10-06)记录后续改动和验证。G24–G27 来自 [MCP 客户端边界附录](VERIFICATION_HISTORY.md#reverie-cli-feature-audit-addendum-2026-10-05)，G28–G32 来自 [跨平台身份与语言覆盖附录](VERIFICATION_HISTORY.md#reverie-cli-platform-language-audit-2026-10-05)。

## 如何读状态

2026-10-23 继续实施中：Python 全量 **2214/24**、验证器 **114**、六组重点检查 **244**，Desktop **387/1**、类型、文档和 diff 检查通过，源码前后哈希一致。Linux 新包 **3824bc06ee6c6e24** 的 14 个冻结模块、71 个 UI 文件、独立 CLI 10 个模块及信任清单通过核对；P2 **24/24**、P3 **26/26**、隔离 **36/36**。安全接线示例区分恢复/纯重算与初始化后的用户保存，并补充按钮及 SVG 标签配色；重开会话的摘要不再混入模型作者建议，原工具输出、建议、历史和模型 HTML 保持不变。

P4 首轮及同构建诊断轮均为 **30/31**，输入 P95/最大分别 **107.7/165ms**、**101.3/161.2ms**。测得闲置旧包文件缓存后释放约 1.764GB，未删除文件或改动源码、夹具、60 个样本与 100ms 门槛；该条件下第三轮 **31/31**，注册上界 P95/最大 **266.625/336.359ms**，本地输入至两帧 **68.9/96.9ms**。三轮及资源条件完整保留，不能据此断言前两次原因或稳定达标；本地测量不代表模型生成或物理显示延迟。

GPT-OSS-120B 的 native6 开发轮次生成 **0/5**、文本 **1/1**，实际五份页面 74 条记录及 22 张代表截图已复核。旧强模型开发与人工失败亦保留；当前进行相同 397B/计算器前后构建观察，随后按冻结两个 Qwen 模型完整执行正式 **30+6**。见[本包原生验收](verification/2026-10-21-riu-completion/native-build-3824bc06ee6c6e24.json)和[本轮记录](verification/2026-10-21-riu-completion/progress.md)。

2026-10-20 Cloud 续验基线为 `350c5ba`。匿名 Chat 复用无认证 HTTP 路径，避免 SDK 在请求前要求密钥；主模型请求的 SDK/直接 HTTP 重试入口遵守 Retry-After 秒数或日期，服务显式提供冷却时间的 402 按限流有界等待，普通 402 仍失败，Stop 可取消。Linux 最新源码与验证器全量 **2103 passed / 24 skipped**，Desktop **383 passed / 1 skipped**，类型检查通过；原 Windows 2098/2/1 失败仍保留。已构建 Linux CLI/目录包 `f83a5d6f50971c66` 并核对源码，P2 24/24、P3 26/26、P4 31/31、隔离 36/36 是实际消费者证据，不能代替 Windows 新包或真实模型质量。见 [Cloud 续验](VERIFICATION_HISTORY.md#riu-cloud-runtime-2026-10-20)。

2026-10-21 固定任务矩阵完成 15 生成 + 3 文本：生成 10 次 model_no_view、2 次复核语义失败、3 次上游 usage_missing 错误，质量通过 0/15；文本 3/3。真实模型质量门保持未通过，原始异常、环境中断与一次验证器时序重跑分别保留。按用户线索找到 MiniCPM-V 4.6 的公开免费 Key 公告，但当前官方标准 API 要求注册 Key；另已匿名实测官方 MiniCPM5-2B Space 的 Gradio/SSE API，未暴露 tools，不能当第二个工具闭环来源。见[免费接口核对](verification/2026-10-20-riu-cloud/free-api-search.md)。

2026-10-20 暂停交接：用户因关机要求将当前源码保存到 GitHub 并交由 Cloud 续修。[交接提示词](CLOUD_CODEX_RIU_HANDOFF.md)和[结构化记录](verification/2026-10-20-riu-continuation.json)说明最新状态。自动选择交互视图的指导、Desktop 按需初始化检索、空 Harness 快速返回、失败命令重跑成功后的门禁修复及思考区 Markdown 空白排版已改源码，**尚未重建最终包**。最新 Desktop 383/1、类型检查通过；Python 全量 2098/2/1，Windows 粘贴输入测试单独重跑通过但根因未闭环。此前 `2cfd719ac18e73a4` 的通过不能覆盖这些后续修改。云端按用户最新要求优先验证合法 OpenCode 匿名免费来源，并修复实际发现的 source 客户端问题；模型生成与视觉质量门继续保留。

2026-10-09–10 提交前复核：完成当前工作树的 Python / Desktop 回归、依赖检查、Windows CLI 构建、本地 HTTP 工具流程及打包 GUI 设置持久化检查；修正了旧发布断言和 Skills 文件在 Git 换行转换后的哈希不一致。具体通过、失败后重测、跳过和打包范围见 [本次验证记录](VERIFICATION_HISTORY.md#publish-validation-2026-10-09)。版本号未变，Intelligent UI 仍为待开发提案，外部服务与跨平台缺口没有因本次提交而关闭。

2026-10-08 补充：本次仅对 Intelligent UI 相关源码做定向静态审查，并整理文档；没有重跑全部产品验收。已有 Markdown、`ui.event`、MCP 工具/资源和 Workbench，但没有生成式交互视图宿主、MCP Apps 桥及相应持久化链路。见 [Intelligent UI 规格](INTELLIGENT_UI_SPEC.md) 与 G33。此前各日期的验证已集中到 [验证历史](VERIFICATION_HISTORY.md)。

2026-10-10 补充：GUI 启动时取消额外预热内核及管理内核自动索引；工作内核按需启动，最多一个空闲内核保留 30 秒。Windows CLI 默认恢复独立单 EXE；桌面包内部仍保留自己的运行文件。更新 Agnes / ModelScope 文本目录、About GitHub 链接和透明思考背景；内存采样、独立 EXE、界面和回归检查见 [本次验证](VERIFICATION_HISTORY.md#desktop-memory-2026-10-10)。并行开发的未提交 Intelligent UI 文件不计入本次验收。

| 状态 | 含义 |
| --- | --- |
| 已实现并有验证 | 对应路径存在，且有注明范围的测试或运行证据；不代表所有模型、系统和数据规模都通过 |
| 已实现但有限 | 可使用，但存在明确功能、规模、协议或设备边界 |
| 缺少验收 | 实现存在，仍缺真实模型、授权服务、原生输入或长期运行等证据 |
| 已确认缺口 | 源码路径或隔离复现确认当前行为达不到要求 |
| 外部阻塞 | 上游响应、凭据或设备条件限制；客户端测试通过不能解除该限制 |
| 排除 / 条件扩展 | 产品未选择进入默认范围，不能算成实现遗漏 |

本页不使用总体完成百分比。2026-09-30 的 S01–S21 是实施范围，不是 21 项全部验收通过的声明；截至本次核对，仍有下面这些缺口。

本页的 Engine / Gamer 运行时指 CLI 内置的 Python `reverie.engine` / `reverie_engine` 工具。RATS 的 `reverie.engine` provider ID 指外部 Engine 应用服务；其编辑器窗口不属于 G19 的内置运行时缺口，外部产品本身没有在本次重新验收。

## 能力矩阵

| 功能域 | 当前可用能力 | 状态与实际边界 | 指南 / 主要实现 |
| --- | --- | --- | --- |
| CLI / 批处理 | 交互命令、单次提示、文件 / stdin 输入、结构化报告、临时模式 / 来源 / 模型选择 | 已实现并有验证；终端命令与 Desktop 输入命令不是同一执行器 | [命令](CLI_COMMANDS.md)、[入口](../ReverieCli-py/reverie/__main__.py) |
| Desktop 输入 | 独立文本 / 附件草稿、剪贴板图片、拖放、`@`、`/` 候选、模式选择、流式开关 | 已实现并有验证；支持的参数命令明确派发，其余标为终端参考并阻止误发聊天 | [桌面指南](DESKTOP_GUIDE.md)、[输入](../ReverieCli-ui/src/App.tsx) |
| 执行控制 | Queue、Steer、Stop、暂停、强停和后台会话 | 模型连接 / 响应头 / 流读取及重试等待可直接取消；工具动作仍在安全点停止；真实长任务组合验收仍有限 | [桌面指南](DESKTOP_GUIDE.md)、[RunControl](../ReverieCli-py/reverie/desktop_control.py) |
| 对话个人资料 | 用户名称、图片上传、拖动 / 缩放 / 键盘裁剪、移除头像；用户右侧 / 模型左侧 | 已实现并有打包应用验证；保存 256 × 256 PNG 裁剪结果，刷新后保留 | [桌面指南](DESKTOP_GUIDE.md#用户名称和头像)、[裁剪](../ReverieCli-ui/src/AvatarEditor.tsx) |
| 请求启动与输出模式 | 即时流式开关、内核空闲预备与复用、共享连接池、初始化与快照并行、相同快照对象复用 | 本地真实 HTTP、打包应用及 NVIDIA 线路有分阶段测量；服务端等待和空内容响应不能计为客户端已解决 | [最新请求验证](VERIFICATION_HISTORY.md#reverie-cli-workbench-repairs-2026-10-06)、[传输](../ReverieCli-py/reverie/provider_transport.py) |
| 会话 / 恢复 | 索引、分页历史、归档、分叉、回退、继续、工具结果即时保存 | 已实现并有验证；分叉 / 轮换继承独立 pin 列表，普通新会话清空 | [SessionManager](../ReverieCli-py/reverie/session/manager.py)、[最近修复](VERIFICATION_HISTORY.md#reverie-cli-ui-repair-2026-10-04) |
| 历史搜索 | 搜索当前工作区会话名称、正文、思考和工具名 | 已实现并有规模验证；SQLite 缓存、变化会话增量更新；首次建索引及短查询有明确开销 | [搜索实现](../ReverieCli-py/reverie/session/search.py) |
| Git / 独立目录 | diff、区块暂存 / 撤销、整个暂存区提交、普通推送、分支、worktree 归档 / 恢复 | 已实现并有真实 Git 证据；不含 PR / CI 集成、重写历史和完整 submodule 管理 | [工作面板](DESKTOP_GUIDE.md)、[Git](../ReverieCli-ui/electron/workbench.ts)、[独立目录](../ReverieCli-ui/electron/isolated-workspaces.ts) |
| 工作面板 / 文件 | 单一可伸缩右侧栏，合并 Git、文件树、审查、运行、AI 改动、上下文和活动；UTF-8 文件编辑 | 有打包应用验证；编辑限 2 MiB，保留 BOM / 换行，拒绝覆盖外部修改；其他编码和二进制只读。大文件预览每页仍扫描数据流（G08） | [指南](DESKTOP_GUIDE.md)、[FileBrowser](../ReverieCli-ui/src/FileBrowser.tsx) |
| 对话内容显示 | 标题栏直接选择全部、思考与回复、仅回复，或自定义显示开关 | 默认全部；只改变显示，偏好与设置同步并持久保存。会话缓存独立跟踪已加载的磁盘版本 | [验证报告](VERIFICATION_HISTORY.md#reverie-cli-workbench-repairs-2026-10-06) |
| 只读模型审查 | 明确 diff 范围、读取工具白名单、保存模型输出、发现反馈 | 已实现并有解析 / UI 回归；格式错误独立展示，定位必须属于捕获 diff；真实模型审查质量未验收 | [审查](../ReverieCli-ui/src/Workbench.tsx)、[工具执行](../ReverieCli-py/reverie/agent/tool_executor.py) |
| 用户终端 / 动作 | 真 PTY、会话归属、日志、取消、显式项目动作 | 已实现；8 MiB × 2 轮换、1 MiB 恢复、有限磁盘队列与明确丢失标记 | [终端](../ReverieCli-ui/electron/session-workspace.ts) |
| 目标与计划 | 条件、步骤、手动状态、修订、验证命令和磁盘保存 | 已实现；所属执行器开始时加载目标，运行中更新仍使用 Steer；验证状态为手动报告 | [计划 UI](../ReverieCli-ui/src/SessionWorkbench.tsx) |
| 会话并行 | 最多 4 个独立内核、同 checkout 写入排队、独立目录并行 | 已实现并有真实 Git 验证；父 / 子目录和别名共享锁，嵌套托管 worktree 可独立并行 | [协调器](../ReverieCli-ui/electron/execution-coordinator.ts) |
| Skills | 渐进发现、遮蔽提示、最多 4 个固定项、CLI / Desktop 恢复、14 个设计 Skill | 已实现；每轮完整读取主正文并记录哈希，缺失时阻止执行；模型工作流遵循仍需检查 | [Skills](SKILLS.md)、[管理器](../ReverieCli-py/reverie/skills_manager.py) |
| 提供商 | 内置来源、自定义 Chat / Responses / Messages、缓存提示、思考、工具与用量处理 | 已实现；文本探测需有效文本，目录 / SSE / 工具 / 思考 / 视觉是不同验收（G12） | [配置](CONFIGURATION.md)、[提供商实现](../ReverieCli-py/reverie/custom_providers.py) |
| JDW Claude 线路 | 原生非流式客户端契约已补齐 | 外部阻塞；10 月 4 日采样出现空 SSE 和忽略强制工具；10 月 5 日未重测远端 | [兼容性记录](VERIFICATION_HISTORY.md#reverie-cli-jdw-compatibility-2026-10-04) |
| 当前 OpenCode 免费线路 | 目录、端点与客户端请求路径存在 | 外部拒绝；10 月 5 日当前 Nemotron 免费线路新旧传输均返回 403，服务提示免费层仅限 OpenCode 内调用；未取得首 token 性能证据 | [现场记录](VERIFICATION_HISTORY.md#reverie-cli-request-profile-repairs-2026-10-05--当前真实线路的限制) |
| Context Engine / Memory | 代码 / 符号 / 依赖 / LSP / Git 检索、压缩、项目记忆、handoff | 已实现并有验证；大型、多语言和完整检索基准仍有限（G16）。多语言语法树是可选 extra，缺失时静默退回正则（G30）；`.zig` 被认领但两条路径都没有实现（G31）；LSP 只定义 6 个服务器（G32） | [项目记忆](CONTEXT_ENGINE_MEMORY.md)、[基准](VERIFICATION_HISTORY.md#context-engine-benchmark) |
| Tokens / 上下文 | API 用量校准、缓存分类、草稿及附件估算、会话 / 工作区累计 | 已实现但有限；供应商隐藏提示、媒体编码和计费不是本地可精确求出的量 | [计数说明](VERIFICATION_HISTORY.md#reverie-cli-token-usage-validation-2026-10-02)、[复审](VERIFICATION_HISTORY.md#reverie-cli-token-context-review-2026-10-02) |
| 审批 / 工作区保护 | Default / Auto Check / Strict、能力上限、owner、读取审查白名单 | 已实现并有回归；软件政策不是 OS 沙箱，用户 PTY 使用当前用户权限 | [权限](SECURITY_PERMISSIONS.md)、[工作区保护](../ReverieCli-py/reverie/workspace_guard.py) |
| SubAgents | 明确范围、同步 / 后台运行、协作取消、选择性记忆、日志 | 已实现并有回归；独立代理不继承完整主会话，禁止嵌套委派 | [SubAgents](SUBAGENTS.md) |
| 插件 / MCP / RATS | 插件启用 / 信任、MCP stdio / Streamable HTTP / legacy SSE、动态工具和资源读取、RATS 官方 / 自定义提供者 | MCP 当前是部分客户端实现（G24–G27）；真实授权服务仍缺当前验收（G15）；RATS 官方内置提供者仍只有 Engine，自定义登记不代表已授权 / 可调用；RATS 可执行体与进程身份校验在非 Windows 上降级为存在性检查（G28） | [MCP 配置与边界](CONFIGURATION.md#mcp-server-connections)、[RATS](RATS_RTP.md) |
| 通知 | 持久应用内记录、去重、静音、返回所属会话、OS 通知 | 已实现；系统点击回跳、系统禁用、双审批通知仍缺完整实机证据（G14） | [通知实现](../ReverieCli-ui/electron/main.ts) |
| Atlas / Writer | 文档驱动交付；原生小说项目、章节门禁、连续性和事务提交 | 已实现并有回归；规则与字数检查不证明作品质量，历史实测五章不等于任意长篇完成 | [Writer](writer_mode.md)、[Atlas](../ReverieCli-py/reverie/atlas.py) |
| 浏览器 / 桌面控制 / 媒体 | Chromium 工具、Windows 桌面控制、图片 / 视频生成与附件路径 | 已实现但依赖运行时、模型与权限；不等于 Desktop 有内嵌交互浏览器；真实视觉理解并未逐来源验收 | [桌面控制](COMPUTER_CONTROLLER.md)、[媒体](../ReverieCli-py/reverie/media_capabilities.py) |
| 内置 Engine / Gamer | headless 游戏循环、原生窗口 / 离屏渲染、存档、程序化资产、垂直切片与证据门禁 | Alpha；Windows 窗口、输入、缩放、关闭已验证，完整 PBR / Cubism / 生产深度仍缺（G20 / G21） | [引擎指南](engine/reverie_engine_user_guide.md) |
| 发布 / 平台 | Windows 核心、安装包、便携版；Linux / macOS CI 构建配置 | 已实现；关于页显示构建 ID、时间、启动路径；其他平台及长运行验收仍有限（G18）；回归套件有 11 处 Windows-only 门禁，其他平台的跳过数更高（G29） | [开发](DEVELOPMENT.md)、[发布工作流](../.github/workflows/build-core-release.yml) |

## 缺口登记

**G33 — Intelligent UI / MCP Apps：P0–P4 宿主已实现；真实模型生成质量仍按模型和样本限定。** 标准 `inline/fullscreen/pip` 复用同一 iframe，支持动态主题/语言/尺寸、键盘与焦点、窄窗、私有状态、分页历史与资源回收；长摘要可展开，展示按钮增大。后续确认 Writer 失败涉及实际提示词/工具不一致，已修正模式、MCP/插件注入、Atlas 账本、原始模型 ID、媒体前置条件、空 harness 和 Desktop 自动批准等路径。生成视图说明提供可用的宿主集成示例；工具对明显的不支持 API 给出静态提示。原始失败和当前源码/包/真实模型结果见 [提示词与生成质量续验](VERIFICATION_HISTORY.md#riu-prompt-quality-2026-10-17)；早期性能与交付范围保留在 [P4 记录](VERIFICATION_HISTORY.md#riu-p4-delivery-2026-10-17)。关键词检查或 `render_view` 注册成功不等于模型质量通过，不宣称 OpenAI 功能/效果对等。P3 仍为 ext-apps 2.0.3/UI 2026-01-26 离线 profile，原执行/审批/会话锁继续生效；Linux 原生 Xvfb 已有本轮包与消费者证据；macOS、原生 IME/屏幕阅读器、HTTP/SSE UI、完整 window.openai 与 Plugin Extensions 未验证或另属范围，G24/G26 保留。

2026-10-18–20 续修：按完整生产请求去重工具参数说明，保留全部原生 schema、用户固定 Skill、安全约束和可运行示例；忽略默认规则注释，修正显式视图工具范围被否定文件指令误触发检索。移除原生思考的内容过滤及 CLI 猜测删段，保存失败/中断的原始文本。画中画增加高度、短摘要可展开，内容仍须自行组织结果与关键控件。最终 Windows Desktop **2.5.0 / 2cfd719ac18e73a4** 通过 P2/P3/P4 与隔离回归；便携启动器修复深路径漏件，真实新解压 1084 个文件全部匹配。安装/卸载、其他平台及跨模板生成质量仍有独立门禁，见[本轮续验](VERIFICATION_HISTORY.md#riu-quality-2026-10-20)。提示词缩短或宿主通过不代表模型生成稳定。

P1 优先影响执行正确性或核心闭环；P2 影响规模、体验或验证完整度。“源码确认”与“实机 / 隔离复现”分开，未经复现的风险不写成已发生的数据错误。

| ID | 优先级 | 缺口 | 判定与证据 |
| --- | --- | --- | --- |
| G01 | P1 | Desktop 指令误发、review 参数丢失 | 已修复；明确 GUI 派发、终端参考拦截、参数与键盘交互回归 |
| G02 | P1 | 分叉 / 自动轮换不继承固定 Skill | 已修复；真实 SessionManager 磁盘及副本独立性验证 |
| G03 | P1 | CLI pin 保存 / 恢复不完整 | 已修复；启动、切换、即时持久化、普通新会话隔离 |
| G04 | P1 | 同 checkout 父 / 子目录绕过写锁 | 已修复；真实 Git 根、子目录、别名、独立托管 worktree 回归 |
| G05 | P1 | 保存目标没有传入下一轮 | 已修复；执行器绑定目标、系统消息 / 压缩隔离及陈旧响应回归 |
| G06 | P1 | 空 HTTP 200 被标为在线 | 已修复；真实本地 HTTP 返回空 choices 现在报告 error，三种格式文本校验 |
| G07 | P2 | 固定 Skill 没有本轮完整读取保证 | 主正文加载已修复；每轮完整正文、哈希 / 字符记录和缺失阻断；模型遵循仍有限 |
| G08 | P2 | 大文件 / diff 的内存和读取成本 | 内存与 IPC 负载已修复并测量；精确哈希 / 总行数仍需全流扫描，取消和随机磁盘分页仍有限 |
| G09 | P2 | 历史搜索重复逐个读取 JSON | 已修复；1000 个会话测量、热搜索 / 重启零正文读取；首次建索引与短查询仍有限 |
| G10 | P2 | 日志容量、恢复和异步归属 | 已修复；轮换、有限恢复 / 队列、截断标记、非重叠轮询和会话过期请求回归 |
| G11 | P2 | 审查解析 / 路径 / 行定位混淆 | 已修复；无效 JSON 与合法空数组区分，实际 diff 定位验证、保存原文、UI 错误验证 |
| G12 | P1 | 逐模型 SSE / 工具 / 思考 / 图像兼容矩阵未完成 | 缺少验收 / 外部阻塞；本地 SDK 契约通过与远端网关表现需分别判断 |
| G13 | P2 | 原生中文 IME 与屏幕阅读器验收不足 | 命令面板键盘选择与组合输入保护已补齐；原生候选窗 / 屏幕阅读器仍缺实机验收 |
| G14 | P2 | OS 通知点击、禁用和并行审批通知缺证据 | 缺少验收；应用内记录和历史 Windows shown 证据不能覆盖这些组合 |
| G15 | P2 | 认证插件 / MCP / RATS 的真实授权生命周期缺当前证据 | 外部 Engine RATS 集成单独运行 11 项通过；其他真实认证插件 / MCP 生命周期仍缺验收，静态注册不是授权成功 |
| G16 | P2 | 检索性能与质量基准覆盖不足 | 缺少验收；历史 SWE-bench 24 项 / 冻结 7 项不是完整 300 项或跨语言结论 |
| G17 | P2 | 同版本改包和启动路径识别 | 已加入构建 ID、时间与实际启动路径；本轮便携版首次启动被自动审批拦截，未验证首次解压；已编译 GUI 验证见修复报告 |
| G18 | P2 | macOS GUI、长运行与原生设备验证不足 | 2026-10-20–21 Linux Xvfb 原生 CLI/GUI 与当前包消费者已验证；macOS、实机设备及长运行仍缺验收，不能用 CI 配置替代 |
| G19 | P1 | 内置 Engine 原生窗口 / 输入呈现 | 已实现并有真实 Windows 帧、按键 / 鼠标、缩放与关闭验证；其他平台未验收 |
| G20 | P2 | 完整渲染材质、设备音频与原生 Live2D 尚未闭环 | 功能缺失 / 缺少验收；基础纹理可用，Cubism manifest / bridge 不代表角色已渲染 |
| G21 | P2 | Gamer 生产深度和迁移覆盖有限 | 已实现但有限；切片和程序化候选可用，不支持通用 AAA / 3D 开放世界交付 |
| G22 | P1 | 文档入口、用法和证据发布方式落后 | 已修正文档入口、错误用法、浏览器 UI 边界和 MCP 支持说明，并增加离线链接检查；历史本地材料仍不随 Git 发布 |
| G23 | P1 | 全量 Python 回归门禁未通过 | 首轮 1761 通过 / 1 跳过；后续补齐隔离和传输测试。2026-10-06 全量 1829 通过 / 1 跳过，详见 [最新验证](VERIFICATION_HISTORY.md#reverie-cli-workbench-repairs-2026-10-06) |
| G24 | P2 | MCP 客户端协议功能面不完整 | 源码只执行 `tools/call`、`resources/read`，发现时只列 `tools/list`、`resources/list`、`prompts/list`；提示模板没有 `prompts/get` 入口，也没有 resource template / subscription、roots / sampling / elicitation 请求处理（这些是当前协议的可选客户端能力）。动态工具和资源路径仍可用；精确范围见 [复审附录](VERIFICATION_HISTORY.md#reverie-cli-feature-audit-addendum-2026-10-05) |
| G25 | P2 | MCP 工具 / 资源 / 提示目录分页未跟随 | 已修复；三种目录跟随 `nextCursor`，重复 / 非法游标明确失败，保留发现时间预算；多页 fixture 与缓存回归通过 |
| G26 | P2 | 远程 MCP 没有托管 OAuth 生命周期 | HTTP 传输支持手工静态 `headers`；未实现受保护资源发现、OAuth / PKCE、401 授权挑战或令牌刷新。OAuth 在 MCP HTTP 传输中是可选能力，当前未实现不等同于所有连接都失效 |
| G27 | P2 | MCP 工具多模态结果没有原生传给模型 | 部分修复；支持的图片与 WAV / MP3 音频转为类型化内容，保留文本 / structuredContent / 资源元数据和错误状态；OpenAI Chat 图片 / 音频、Anthropic 图片、Responses 图片各有转换，后两者不支持的音频明确提示。媒体大小 / 类型有边界，嵌入二进制资源与真实媒体服务器 / 逐模型验收仍有限 |
| G28 | P1 | RATS 提供者身份校验在非 Windows 上失败开放 | 源码确认；`rats.py` 的 `_reverie_engine_executable` 在非 Windows 返回 `is_file()`，`_reverie_engine_process` 降级为 `os.kill(pid, 0)` 且 `PermissionError` 返回真。描述符 schema、注册表、端点、`hello`、请求 ID 与响应哈希检查仍生效；PE `ProductName` / PID 映像那层保证只存在于 Windows。未在非 Windows 主机复现 |
| G29 | P2 | 平台测试门禁使跨平台断言静默跳过 | 源码确认；11 处 Windows-only `skipif` 覆盖 RATS 身份 / 进程映像、Blender 便携部署、`taskkill` 终止和 Windows 路径规范化，另有 3 处函数体内平台分支。"1761 通过 / 1 跳过"是 Windows 数字，不能当成跨平台验收 |
| G30 | P2 | 多语言语法树依赖不随安装与打包传递 | 源码确认；tree-sitter 只在 `extras_require["treesitter"]`，不在 `install_requires`、不在 `.[build]`、不在 `reverie.spec` 的 `hiddenimports`，`build.bat` 只装 `-e ".[build]"`。缺失时 `ImportError` 被吞掉并静默退回正则，10 种语言的抽取精度取决于安装方式；全仓没有任何测试引用 tree-sitter |
| G31 | P2 | `zig` 是死配置且 docstring 声明不成立 | 已确认缺口；`.zig` 被 `can_parse` 认领，但 `_get_parser` 与 `_parse_with_regex` 都没有 `zig` 分支，extra 里也没有 `tree-sitter-zig`。本机复现产出 0 符号 / 0 依赖 / 0 错误，与"文件里没有符号"无法区分；`_extract_zig` 已定义但不可达 |
| G32 | P2 | LSP 服务器定义覆盖面不足 | 源码确认；`SERVER_DEFINITIONS` 只有 python ×2、typescript、go、rust、cpp。Java / C# / Lua / GDScript 即使本机装了语言服务器也不会被发现，而这些语言本仓已有解析器或语法树分支。LSP 是可选增强，不影响基础检索 |

修复软件缺口不等于解除 G12 / G14–G16 / G18 / G20 / G21 的外部服务、设备、平台或产品深度边界。MCP G25 已修复，G27 部分修复，G24 / G26 仍保留明确范围边界。G28–G32 是第三轮定向源码复审新登记的项，本轮只登记和同步文档，没有改动运行时代码。修复前复现见 [审查报告](VERIFICATION_HISTORY.md#reverie-cli-feature-audit-2026-10-05)，后续软件修复验证见 [请求修复报告](VERIFICATION_HISTORY.md#reverie-cli-request-profile-repairs-2026-10-05)，MCP 二次源码审查见 [复审附录](VERIFICATION_HISTORY.md#reverie-cli-feature-audit-addendum-2026-10-05)，跨平台身份与语言覆盖见 [第三轮附录](VERIFICATION_HISTORY.md#reverie-cli-platform-language-audit-2026-10-05)，后续验收见 [路线图](ROADMAP.md)。

## 已做与主动排除

`@` / `/` 候选顶层显示、左下角模式选择、紧凑思考三态、目录 EISDIR、只读工具检查点开销、Desktop pin 恢复及历史工具结果恢复已有 [10 月 4 日证据](VERIFICATION_HISTORY.md#reverie-cli-ui-repair-2026-10-04)。本次发现的分叉、CLI、checkout 别名等是不同场景。

不恢复用户已移除的会话手动排序、状态过滤、Message context 汇总或重复轨迹栏。不增加 Local/Cloud、托管云、同步账号、定时任务、无限自主目标或完整 Git GUI。PR / 多仓库审查 / 区域批注 / Office 预览 / OS 沙箱仍是 S01–S21 规格中的条件扩展，须重新明确范围后才实施。
