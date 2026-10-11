# 验证与审查历史

2026-10-08 整理，2026-10-09–10 补充提交前验证。集中保留历次审查、复现、测试、构建、性能采样及明确未验证范围。各章节的结果仅对应原日期、平台和工作树，不能累计为一次全量通过。结构化原始摘要继续保留在 `docs/verification/`；`.runtime/`、截图与安装包是本地材料，不要求随 Git 克隆分发。

## 目录与迁移索引

优先查看：

| 日期 | 主题 | 证据边界 |
| --- | --- | --- |
| 2026-10-10 | [桌面内存与独立 EXE](#desktop-memory-2026-10-10) | Windows 打包进程树采样、内核生命周期、界面及本地回归；模型目录不等于账户实测 |
| 2026-10-09–10 | [提交前验证](#publish-validation-2026-10-09) | 当前源码回归、Windows 构建和隔离应用检查；不替代远端 CI 或真实服务验收 |
| 2026-10-08 | [API 兼容](#reverie-cli-api-compatibility-2026-10-08) | 源码模型流程与编译后的上游失败分别记录 |
| 2026-10-07 | [Desktop UI](#reverie-cli-apple-ui-redesign-2026-10-07)、[启动与托盘](#reverie-cli-background-startup-repairs-2026-10-07) | Windows 打包与本地交互；不等于新增 provider/RATS 验收 |
| 2026-10-06 | [Workbench](#reverie-cli-workbench-repairs-2026-10-06) | 面板、文件编辑和本地请求耗时 |
| 2026-10-05 | [功能审查](#reverie-cli-feature-audit-2026-10-05)、[功能修复](#reverie-cli-feature-repairs-2026-10-05)、[请求修复](#reverie-cli-request-profile-repairs-2026-10-05) | 修复前后分开；MCP/平台附录仍保留未验证项 |
| 更早 | 下方完整原文件索引 | 原日期与原测量保留，不累计为当前的一次通过 |

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

当前代码已有较完整的本地编码工作流，但不能把 S01–S21 的代码接入或单轮打包测试解释为全部功能完成。本次登记 **23 项缺口 / 限制 / 证据问题**，其中 G22 的文档整理在本次完成；其余状态在 [功能矩阵](FEATURE_STATUS.md)，后续工作与验收条件只维护于 [ROADMAP](ROADMAP.md)。

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
