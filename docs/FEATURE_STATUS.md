# 功能状态与已知缺口

状态汇总更新：**2026-10-10，版本 2.5.0**。逐项功能审查基线为 2026-10-05–06，后续检查按日期注明范围。本文描述当前实现；开发优先级和闭环条件统一维护在 [ROADMAP](ROADMAP.md)。[审查报告](VERIFICATION_HISTORY.md#reverie-cli-feature-audit-2026-10-05)保留修复前复现，[首轮修复报告](VERIFICATION_HISTORY.md#reverie-cli-feature-repairs-2026-10-05)、[请求 / 个人资料修复报告](VERIFICATION_HISTORY.md#reverie-cli-request-profile-repairs-2026-10-05)与[工作面板修复报告](VERIFICATION_HISTORY.md#reverie-cli-workbench-repairs-2026-10-06)记录后续改动和验证。G24–G27 来自 [MCP 客户端边界附录](VERIFICATION_HISTORY.md#reverie-cli-feature-audit-addendum-2026-10-05)，G28–G32 来自 [跨平台身份与语言覆盖附录](VERIFICATION_HISTORY.md#reverie-cli-platform-language-audit-2026-10-05)。

## 如何读状态

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

**G33 — Intelligent UI / MCP Apps 宿主：P1，提案、未实现。** 缺产物注册、隔离渲染、时间线视图、受控回调、私有状态与标准 Apps 生命周期；已有的资源读取和结构化 MCP 结果不等于 UI 宿主。验收和下一步提示词在 [技术规格](INTELLIGENT_UI_SPEC.md)，实施顺序在 [Roadmap](ROADMAP.md#intelligent-ui)。G24 仍保留不属于 UI 的 MCP 功能边界。

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
| G16 | P2 | 检索性能与质量基准覆盖不足 | 缺少验收；历史 SWE-bench 23 项 / 冻结 7 项不是完整 300 项或跨语言结论 |
| G17 | P2 | 同版本改包和启动路径识别 | 已加入构建 ID、时间与实际启动路径；本轮便携版首次启动被自动审批拦截，未验证首次解压；已编译 GUI 验证见修复报告 |
| G18 | P2 | 当前 Linux / macOS GUI、长运行与原生设备验证不足 | 缺少验收；CI 配置存在，本次在 Windows 核对，未重验其他平台 |
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
