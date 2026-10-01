# Reverie CLI / Desktop 与 Codex 的功能及体验差距审计

功能审计日期：2026-09-29；产品取舍与 UI/UX 规划更新：2026-09-30。对象是本仓库当前的 Reverie Python CLI、Electron 桌面端及 SDK bridge；参照物主要是 Codex 所在的 ChatGPT 桌面端，必要时注明 Codex CLI、IDE、Remote 或 ChatGPT Work 独有的能力。此文是**产品能力与可见工作流**的对比，不把“模型可以通过命令自己完成”算成“桌面端有同等原生操作”。

**实施入口：**[Reverie 新增及完善功能清单](REVERIE_CLI_FEATURE_ADDITIONS_2026-09-30.md)给出最终取舍、21 个默认实施项、逐项 UI/UX 规格和验收条件；[新会话实施提示词](REVERIE_CLI_IMPLEMENTATION_PROMPT_2026-09-30.md)可直接复制。本文保留 47 项差距作为证据，**差距清单不等于全部要实现的任务**。计划总入口仍是 [ROADMAP](ROADMAP.md)。

## 1. 判定方法与边界

- 对照了桌面端 `src/App.tsx`、`src/FileChanges.tsx`、`electron/main.ts`、`electron/preload.ts`、`electron/core-actions.ts`，Python `sdk_bridge.py`、`desktop_changes.py`、`context_engine/git_integration.py`、`agent/tool_manifest.json`，以及项目 README 和安全文档。本文用“已有”“部分”“未见原生入口”“待实机验证”四种结论；“未见”只针对本次源码和桌面 UI 审计，不断言所有可选插件或任意模型绝对做不到。
- Codex 侧以文末官方资料为准。不同 Codex 表面能力不同：桌面端、CLI、IDE、Remote、ChatGPT Work 和云环境不会被混成一个产品承诺；账号、套餐、系统、插件和管理员策略也可能影响可用性。
- 本次没有用有权限的真实 GitHub 账号、多个远程主机或真实模型密钥逐一试所有端到端服务。因此诸如远程 PR 发布、所有模型的图像理解质量、跨设备通知的可靠性，均不宣称已实测。
- “差距”按实际用户路径拆分。表中 P0/P1/P2 是 2026-09-29 对照 Codex 完整能力时的差距评级，不是最终实施顺序。2026-09-30 的产品决定以新增清单的 R1–R4 和 S01–S21 为准；尤其 OS 沙箱、远程同步、托管云、定时任务不会因出现在本表而自动进入默认范围。
- 2026-09-30 重新检查了输入器、发送/硬中断路径、附件状态、文本草稿、Git IPC、变更面板和 bridge 契约，并核对官方输入、审查和 worktree 文档。本轮只更新产品文档；没有新增软件功能、重新打包或开展新一轮实机视觉审计。下文“本次已完成”与验证记录均指 2026-09-29 的实现，不是把规划写成已完成。

## 2. 本次已完成的用户请求

| 请求 | 本次实现 | 行为边界 |
| --- | --- | --- |
| 自定义用户消息名称 | 设置 → 对话显示可输入并保存名称；历史消息与正在生成的用户消息都会按新名称显示；空值恢复“你”；最多 32 个字符。 | 仅改变本机 UI 表示，不改会话协议里的 `role=user`，也不修改既有消息文本。 |
| Git 分支栏 | 打开 Git 仓库时，主区域底部显示当前分支和未提交文件数量；点开后可搜索本地和远端独有分支、切换已有分支、创建并切换新分支。非 Git 项目不显示；忙碌会话期间禁用切换。 | 使用本机 Git 和当前工作区。Git 可能拒绝有冲突的切换；弹出错误而不强制丢弃改动。不含截图中的 Local/Cloud 模式。远端列表来自本地已获取的 refs，不会自动 `fetch`。 |
| 输入栏文件拖放 | 将本地文件拖到输入框，显示目标覆盖层；一次最多 20 个，复制到项目的 `.reverie/attachments`，出现可移除的附件芯片并把 `@` 引用加入草稿。模型仍在回复时添加的附件属于下一条草稿，不会被上一轮完成事件清掉。 | 本次实现的是**磁盘文件拖放**；剪贴板截图粘贴、目录递归拖放、原位引用和图片缩略图仍是下文差距。 |
| UI/UX | 输入框的拖放状态和快捷提示更清楚，消息名称层级与空白态字重调整，Git 分支弹层采用与 Codex 截图相近的底部位置、分组、搜索和创建入口。 | 这是一轮可验证的交互与视觉改进，不代表整套 Codex 导航和审查界面已复刻。 |

实现入口：[App.tsx](../ReverieCli-ui/src/App.tsx)、[styles.css](../ReverieCli-ui/src/styles.css)、[git-workspace.ts](../ReverieCli-ui/electron/git-workspace.ts)、[main.ts](../ReverieCli-ui/electron/main.ts)、[preload.ts](../ReverieCli-ui/electron/preload.ts)、[preferences.ts](../ReverieCli-ui/src/preferences.ts)。

## 3. 现有能力，避免把“部分已有”误写成缺失

Reverie 已有项目分组、会话新建/重命名/归档/分叉/回退/删除/全文搜索、草稿恢复、模型及提供商选择、思考等级、实时工具活动、批准面板、Context Engine 文件和符号 `@` 推荐、任意文件选择器、图片/视频输入路径、图片生成模型、MCP/本地插件/技能、SubAgents、RATS/RTP、工作区索引、回滚检查点、深浅主题及背景。Python 侧也有 Git 历史、blame、提交详情和未提交状态检索。证据见 [桌面 README](../ReverieCli-ui/README.md)、[工具清单](../ReverieCli-py/reverie/agent/tool_manifest.json)、[Git 检索](../ReverieCli-py/reverie/context_engine/git_integration.py) 和 [安全边界](SECURITY_PERMISSIONS.md)。

因此，下文的 Git 审查、终端、工作树等项目多数是**缺少用户可直接操作的完整界面或隔离模型**，不是说 AI 无法通过已有工具读取 Git 或执行某个命令。对媒体输入也要区分“提供商和核心可以识别图片”与“桌面输入器对图片提供完整的拖放、粘贴、缩略图和发送前检查”。

## 4. 逐项差距

### A. 输入栏、附件与消息控制

| ID / 优先级 | Codex 参照及 Reverie 现状 | 具体差距与建议验收 |
| --- | --- | --- |
| A01 / P0 | Codex 桌面端可把图像加入对话；Web/CLI/IDE 也各有粘贴、拖放或图像参数路径 [C4]。Reverie 此次增加磁盘文件拖放，已有回形针。 | **剪贴板截图 `Ctrl+V`** 未在桌面输入栏处理：`Composer` 有 `onDrop`，没有 `onPaste`。应支持粘贴 PNG/JPEG、显示待发送预览、删除和多张顺序；检查只含图像而无文字的发送是否可用。当前复制文件路径不等于实现截图粘贴。 |
| A02 / P0 | Codex 有直接附加图像的输入路径 [C4]；Reverie 附件芯片仅有文件图标、名称和大小。 | 对照视觉附件任务所需的发送前检查，图片拖入后应显示缩略图、宽高/格式、可放大预览和移除；视频应至少显示类型、时长或首帧，让用户能发现拿错图或顺序错。 |
| A03 / P1 | Codex 可用 `@` 引用工作区文件 [C3]；Reverie 用 Context Engine 推荐 `@` 文件/符号，附件被复制并插入 `@` 路径。 | 对常规仓库文件缺少明确的“原位引用还是复制附件”选择；复制会制造另一份快照，原文件再修改时容易与引用版本不一致。建议仓库内文件优先原位引用，仓库外文件复制并标明来源和副本位置。 |
| A04 / P1 | Codex 的输入与文件工作流可针对多种文件提供上下文 [C3][C4]。Reverie 拖放上限 20 个，`Promise.all` 全部复制。 | 超过上限、文件过大、网络盘断开或其中一个文件失败时没有逐文件进度、失败清单和可重试动作；部分已复制文件可能残留。应有总量/单文件限制、批次结果、取消和部分成功的清理策略。 |
| A05 / P1 | Codex 在不同表面支持图像/文件附加 [C4]。Reverie 拖放仅通过 `File` 实际磁盘路径处理。 | 文件夹拖入没有递归列表、忽略规则、总文件数和确认预览；从网页或剪贴板拖来的无磁盘路径对象会被过滤。应分别给出“暂不支持”的明确反馈，并在未来设计目录导入。 |
| A06 / P1 | Codex 桌面端运行中可选择 **Steer** 当前运行或 **Queue** 下一轮，队列可编辑、重排、立即发送、删除 [C3]。Reverie 运行中按 Enter 会硬中断内核并发送新提示。 | 缺少两种行为的显式选择；硬中断会丢失未持久化的部分输出。应把“补充当前任务”“排队下一轮”“停止并改问”区分，并在提交前说明影响；队列显示在输入框上方，支持编辑/取消。 |
| A07 / P1 | Codex 可以在长运行任务中接收后续约束 [C3][C5]。Reverie 只有停/继续和上述硬中断路径。 | 模型正等待工具、审批或长命令时，用户不能把补充信息无损并入正在运行的上下文。需要后端 turn 级消息队列或安全中断点，不应只改按钮文案。 |
| A08 / P2 | Codex 支持输入器中明确的文件引用与命令提示 [C3]。Reverie `@` 弹层可选，回形针与 `/skill`、`/compact` 也有入口。 | `@` 搜索结果目前偏推荐排序，缺少最近文件/完整路径/文件类型可见过滤；文件名相同的结果难快速区分。建议键盘上下选择、路径高亮和“只看当前目录”等轻量筛选。 |
| A09 / P2 | Codex 输入器通常可把附件和消息作为一个可审阅单元 [C4]。Reverie 附件芯片与 `@` 文本是两个同步状态。 | 用户手动删除 `@` 文本后芯片仍可能存在，直接粘贴同一路径也不会生成芯片；移除芯片只替换首次出现的引用。应让附件成为结构化草稿，序列化发送时统一生成引用，避免状态不同步。 |
| A10 / P2 | Codex 的输入/长任务表面能明确提示任务运行状态 [C3][C5]。Reverie 有实时活动和任务条。 | 输入框没有“待发送文件正在复制”“当前消息将中断任务”等持续状态，错误只以短暂 toast 反馈。应提供可见的传输状态、失败操作和稳定错误摘要。 |

### B. Git、代码审查与发布

| ID / 优先级 | Codex 参照及 Reverie 现状 | 具体差距与建议验收 |
| --- | --- | --- |
| B01 / P0 | Codex 审查面板可看未提交、暂存、提交、分支和最近一轮差异 [C1]。Reverie 的 `FileChanges` 只显示**当前运行中由文件编辑工具记录**的会话改动。 | 缺少完整仓库视图：手改文件、外部工具改动、暂存区、新文件、删除和 Git 外文件都应有一致入口；需要清楚标注比较基准，并与“本轮 AI 变更”并列。 |
| B02 / P0 | Codex 可对整个 diff、单文件、单 hunk 暂存/取消暂存/撤销 [C1]。Reverie 审查面板只读。 | 需要先做可审阅的工作区 diff，再提供对应粒度动作和撤销确认；必须处理同一文件既有 staged 又有 unstaged 片段、二进制文件和冲突。 |
| B03 / P0 | Codex 审查面板支持提交并推送 PR 分支 [C1]。Reverie 有 Git 检索及被审计的命令执行，但无桌面 Git 发布流程。 | 缺少差异检查、选择暂存文件、编辑提交说明、提交、推送、远端/目标分支校验及失败恢复。AI 可以调用命令不构成用户可核对的出版流程。 |
| B04 / P1 | Codex 支持在 PR 上看上下文、评论与文件差异，并让代理修复选定评论 [C1]。Reverie 未见 GitHub/GitLab PR 面板或评论模型。 | 需要 PR 关联、鉴权、评论定位、审查状态、选中评论形成任务、提交后回看 diff；首次版本至少只读 PR + 本地改动映射。GitHub/GitLab 可按连接能力分别提供。 |
| B05 / P1 | Codex 有逐行/逐文件审查反馈路径 [C1]。Reverie 差异用 `<pre>` 展示，无行号、内联评论或定位到代理。 | 应支持新旧行号、折叠上下文、选中行创建反馈、回跳文件路径、评论状态；注释须绑定文件和版本，避免代码变化后指向错误行。 |
| B06 / P1 | Codex 可选 branch/commit 作为比较基准 [C1]。Reverie 此次只显示和切换分支。 | 分支弹层缺少 ahead/behind、upstream、最后提交、远端新旧状态；不能在不切换工作树的情况下比较分支。先做只读元数据和比较，再考虑合并/变基。 |
| B07 / P1 | Codex 可以在 Git worktree 中并行运行对话，之后在 Local/worktree 间 handoff [C2]。Reverie 目前是单个活动工作区加项目会话。 | 分支切换仍共享当前 checkout，多个会话不能在不同分支同时安全改代码。需要独立 worktree 生命周期、会话绑定、状态同步、恢复与清理。用户明确不要求本次实现 Local/Cloud 切换，所以这里只作差距记录。 |
| B08 / P1 | Codex Git 工作流可以选起始分支并隔离未完成改动 [C2]。Reverie 本次的 `git switch` 遇到冲突直接呈现 Git 错误。 | 应在切换前展示将受影响的未提交文件、可否切换和建议处理；严禁静默 stash/reset。对已打开的编辑器/会话应提示工作树内容已变化并刷新索引。 |
| B09 / P1 | Codex 与 GitHub 等连接配合，PR/分支可形成可审阅成果 [C1][C9]。Reverie 没有原生 PR 创建/更新及 CI 状态汇总。 | 建议在推送后展示 PR 标题/正文草案、目标分支、检查状态、审查反馈和打开链接；身份与权限依赖连接，不能只用模型生成 URL 代替。 |
| B10 / P2 | Codex 审查页针对 Git 状态组织差异 [C1]。Reverie 的会话差异是截断文本，二进制/大文件只给“不可用”。 | 需要大 diff 分页、文件树、搜索、文件类型预览、二进制摘要、重命名/移动识别、空白字符和换行差异选项；至少让用户知道被截断的文件和原始文件可打开位置。 |
| B11 / P2 | Codex 的 Git 视图能在操作后持续反映工作树状态 [C1]。Reverie 本次状态在项目切换、聚焦或打开弹层时刷新。 | 外部终端改分支/新提交时若窗口持续聚焦不会立刻刷新；需文件系统或轻量轮询监听 `.git` 与工作树并防抖，切换时保留搜索/焦点。 |
| B12 / P1 | Codex `/review` 有未提交改动、基准分支、指定提交等审查范围，并把发现定位到差异 [C1]。Reverie 首页“审查变更”只是填入自然语言提示。 | 缺少确定的 diff 基准、专用审查运行类型、只读约束、发现优先级与位置存储。应让用户在开始前选审查范围，审查结果可逐条打开对应行，并能与普通聊天继续讨论。 |
| B13 / P2 | Codex 本地项目可包含多个 Git 仓库，审查页提供仓库选择器 [C1]。Reverie 的工作区 Git 栏只针对当前项目目录归属的一个仓库。 | monorepo 中嵌套仓库、子模块或多目录项目无法在统一审查页切换；先检测仓库边界，再以只读列表明确每个仓库的根与状态，避免把父库分支误标给子库。 |

### C. 并行工作、环境、终端和自动化

| ID / 优先级 | Codex 参照及 Reverie 现状 | 具体差距与建议验收 |
| --- | --- | --- |
| C01 / P0 | Codex 每个对话有独立上下文，可并行工作，Git 项目可用 worktree 避免互相覆盖 [C2][C5]。Reverie Electron 复用**单个**长期 Python bridge，运行时不支持多个会话并行执行。 | 项目内切换会话不等于并行代理任务。应建立每会话执行队列/子进程或等价隔离，标明 busy/等待原因；写同一 checkout 的冲突应阻止或明确管理。 |
| C02 / P1 | Codex 有 `/goal`，进度行支持暂停、继续、修改、清除；`/plan` 可先界定目标 [C5]。Reverie 有工具级 `task_boundary` 和任务条。 | 没有持久、用户可编辑的目标对象、完成条件、预算/剩余时间状态、暂停恢复语义和计划审阅流程。把任务条当作目标模式会混淆；应先定义协议与生命周期。 |
| C03 / P1 | Codex 桌面端每个对话有按项目/worktree 定位的集成终端，代理可读取其输出 [C6]。Reverie 有 AI 的 `execute_command` 工具，但没有用户终端面板。 | 用户无法在聊天旁直接跑测试、看持续服务日志、复制失败输出并交给 AI。需要 PTY、退出码、会话生命周期、复制/搜索、项目目录绑定和清楚的执行主体。 |
| C04 / P1 | Codex local environment 可设初始化脚本和常用 action，action 从 UI 启动于终端 [C7]。Reverie 有项目路径和模式设置。 | 新项目的依赖安装、环境变量、测试/开发服务器按钮没有统一声明及状态；应有每项目配置、手动触发、输出/失败可见性和不自动覆盖用户环境的规则。 |
| C05 / P1 | ChatGPT 桌面端可建立定时任务；Git 项目可选本地或专用 worktree，任务可回到同一聊天 [C8]。Reverie 未见调度器、任务列表或定时运行入口。 | 缺少创建/编辑/暂停/删除、下一次时间、时区、运行历史、失败重试、通知与安全审批。首次版本可只做本机单项目定时任务，不应声称跨设备在线执行。 |
| C06 / P1 | Codex Remote 可从移动端启动、引导、批准和回看连接电脑上的工作 [C2][C10]。Reverie 是本机 CLI/桌面。 | 缺少设备配对、远程状态同步、断线续接、移动端审批/审查和主机离线提示。属于跨设备产品工程，不宜混入本次分支 UI。 |
| C07 / P2 | Codex 可以在主聊天旁使用 side chat 询问状态而不打断长期目标 [C5]。Reverie 可创建/分叉会话，但一个 bridge 当前只能跑一条主工作流。 | 需要只读旁路问答或独立进程、共享可控上下文和明显的写入权限，避免“问进度”意外打断正在运行的任务。 |
| C08 / P2 | Codex/ChatGPT 的定时任务和长任务有持续通知/待审批状态 [C5][C8]。Reverie 有操作系统错误提示和应用内 toast。 | 缺少统一通知中心：完成、失败、需审批、长任务无进展，支持静音、按项目过滤与回跳具体会话；任务完成后窗口在后台应可直接定位结果。 |

### D. 文件、产物与审阅体验

| ID / 优先级 | Codex 参照及 Reverie 现状 | 具体差距与建议验收 |
| --- | --- | --- |
| D01 / P1 | ChatGPT 桌面端能并排预览文档、幻灯片、表格、PDF、HTML，并在支持的预览上标注 [C11]；Codex CLI 本身不提供此类视觉预览。Reverie 只有 Markdown 回答和改动文本。 | 生成文件没有“打开/预览”面板、源文件与渲染切换、批注和逐版本对照。建议先支持文本/图片/PDF/HTML，再分格式扩展；安全地隔离 HTML 预览。 |
| D02 / P1 | Codex 审查流程围绕文件和行定位 [C1]。Reverie 回答中的 Markdown 链接都交给 `openExternal`，本地文件路径没有项目内打开路径。 | 本地 `path:line` 点击后应定位到只读代码预览/系统编辑器并保留行号；网页链接仍交外部浏览器；需要防止模型生成的任意路径无意泄露到外部协议。 |
| D03 / P1 | Codex 可通过截图和预览反馈视觉问题 [C4][C11]。Reverie 有浏览器自动化和媒体工具，但桌面主界面没有统一的截图回看/比较入口。 | 建议在聊天产物卡片中展示本轮截图、尺寸、来源、前后切换、放大查看与复制路径；代理生成的图与用户附件在视觉上区分。 |
| D04 / P2 | ChatGPT 桌面端支持在部分预览上标注具体区域 [C11]。Reverie 只能通过自然语言重新描述。 | 图片矩形/箭头、PDF 页码、代码行和幻灯片页等结构化定位可以减少误解；最小版本保存位置 + 附注并附入下一条提示。 |
| D05 / P2 | Codex 审查页可跨文件定位和筛选变更 [C1]。Reverie 的 `FileChanges` 平铺每个文件的详情块。 | 大量文件时缺少文件树、过滤、改动总览和“只看本轮/全部工作树”切换；几百文件时滚动与渲染成本高。 |

### E. 项目组织、扩展与协作

| ID / 优先级 | Codex 参照及 Reverie 现状 | 具体差距与建议验收 |
| --- | --- | --- |
| E01 / P1 | Codex/ChatGPT 桌面端的项目可组织聊天及相关项目上下文 [C12]。Reverie 已有最近项目与嵌套会话。 | 缺少项目级置顶、手动排序、分组/自定义栏和跨项目优先级视图；活跃、需输入、未读状态没有统一排序。先从侧栏可见性、筛选和保存顺序做起。 |
| E02 / P1 | Codex 支持连接 GitHub/GitLab 等服务以形成 PR 与协作流程 [C9]。Reverie 的插件/MCP 能扩展工具，但没有同一套桌面连接状态/授权展示。 | 安装插件和授权账号应分开呈现，明确作用域、过期、可用工具、失败原因与撤销；“模型知道仓库 URL”不等于连接已授权。 |
| E03 / P2 | Codex 端存在可复用的技能、环境 action、插件等发现路径 [C7][C13]。Reverie 有技能和插件目录页。 | 缺少按项目生效范围、依赖/连接状态、版本变更提示和“此会话可调用哪些工具”的简洁汇总；RATS 另有权限机制，建议让用户能看到叠加后最终可用范围。 |
| E04 / P2 | Codex Remote/多端可在不同设备继续同一任务 [C10]。Reverie 会话和桌面偏好主要存于本机。 | 缺少设备间一致的会话身份、可审查同步冲突和加密/授权模型。数据同步设计必须先明确本地隐私边界，不宜简单上传 `.reverie`。 |
| E05 / P1 | ChatGPT 桌面端有内置浏览器侧栏/标签，可打开链接并在聊天旁查看页面 [C15]。Reverie Python 核心有嵌入式 Chromium 浏览器控制工具，但 Electron 聊天界面没有浏览器标签面板。 | 用户无法在应用内直接查看代理正在检查的页面、切换标签、把当前页面作为上下文、对页面截图给出可定位反馈。应把浏览器视图与代理会话绑定，并保留外部浏览器打开选项。 |
| E06 / P2 | Codex 云环境可按分支/提交创建容器并运行 setup script [C16]。Reverie 以本地 Python 核心为主。 | 无托管云运行、可复现环境镜像和远程构建资源。用户本次明确排除 Local/Cloud 切换；此项仅供后续战略评估，不列为本次 UI 验收。 |

### F. 权限、可恢复性与可观测性

| ID / 优先级 | Codex 参照及 Reverie 现状 | 具体差距与建议验收 |
| --- | --- | --- |
| F01 / P0 | Codex 区分 sandbox 权限和需批准动作 [C14]。Reverie 有软件能力级别、Default/Auto Check/Strict 审批及 shadow-Git 恢复，但文档明确指出它不是操作系统沙箱。 | 在 `developer` 或更高权限运行的子进程仍以当前用户访问网络/文件；路径检查不能约束任意第三方可执行文件。若以 Codex 安全边界为目标，需 OS 级文件/进程/网络隔离和实际逃逸测试，不能只改权限 UI。 |
| F02 / P1 | Codex 的权限提示与沙箱范围相联系 [C14]。Reverie 已有审批面板和风险审查。 | 审批卡片应并列显示将执行的命令、工作目录、预计可写路径、网络访问及批准作用域；现有静态工具级授权对命令实际副作用的解释需要更细。后端需要给出可核验的能力说明。 |
| F03 / P1 | Codex 长任务可持续运行、暂停并恢复目标 [C5]。Reverie 的硬中断会重启内核，未持久化输出丢失，虽然历史会话和草稿可恢复。 | 需要可恢复任务事件日志、幂等检查点、外部命令进度与已完成步骤清单；“继续提示”应标明从哪个持久化点恢复，以及哪些工具可能已执行。 |
| F04 / P2 | Codex 的 Review/terminal/goal 形成运行、结果、差异可追溯链 [C1][C5][C6]。Reverie 的活动、恢复、改动分别在不同面板。 | 每轮应可关联提示、工具事件、审批决策、变更文件、测试命令/退出码和最终回复；导出审计摘要以便复现。当前数据可能部分存在，但缺少统一用户路径。 |
| F05 / P2 | Codex 可基于项目/worktree 明确上下文归属 [C2]。Reverie 的单 bridge 在项目切换时替换 workspace 服务。 | 正在索引、附件复制或异步 Git 状态刷新时应有跨项目结果隔离；本次 Git 查询用了序号保护，但其他异步操作仍需专项审计，避免旧项目结果显示在新项目。 |

## 5. UI/UX 具体改进路线

2026-09-30 的取舍把“本地编码闭环”与配套界面作为默认工作，把平台工程和专业编辑能力放入条件清单。具体规格见[新增及完善功能清单](REVERIE_CLI_FEATURE_ADDITIONS_2026-09-30.md)；这里仅保留顺序，避免出现两套互相冲突的计划。

| 阶段 | 功能结果 | 必须同时交付的 UI/UX |
| --- | --- | --- |
| R1：输入与执行控制 | 结构化附件、截图粘贴、独立草稿、Queue/Steer/Stop、异步结果隔离、审批范围说明。 | 统一的聊天外壳、可预览附件、持久错误、队列与状态反馈、键盘/中文输入法支持、侧栏状态、深浅主题和窄窗口适配。 |
| R2：单仓库审查与提交 | 完整 Git diff、文件与 hunk 操作、提交/普通推送、分支预检、只读代码审查、本地产物预览。 | 清楚的比较基准、文件树与行号、审查意见回跳、明确的提交/推送目标、并排预览与打开文件入口。 |
| R3：验证与长任务反馈 | 终端、项目 action、运行记录与保守恢复、轻量计划/目标、通知、技能与连接状态。 | 按会话绑定的终端、可回传日志、任务卡片、待处理通知、实际生效能力视图。 |
| R4：本地并行隔离 | 本地 worktree 生命周期、每会话执行器、同一 checkout 写入互斥。 | “独立工作目录”入口、明确的分支/路径/运行归属、创建与归档进度、跨会话审批和结果定位。 |

PR/CI 协作、多仓库、区域批注、Office/高级媒体预览与 OS 沙箱列为条件扩展。定时任务、side chat、内置交互浏览器、移动/远程同步、托管云和 Local/Cloud 切换不进入默认实施范围。OS 沙箱仍是真实能力差距，界面要如实显示现有边界；不把软件权限提示写成 OS 隔离。完整 47 项的保留、合并、简化和暂缓决定可在新增清单的逐项映射表追溯。

## 6. 本次验证及仍未取得的证据

- TypeScript 类型检查、国际化键检查、桌面 Vitest 全套和实际 Windows unpacked 打包均通过；Git 分支模块用真实临时 Git 仓库验证 local/remote、切换、新建及未提交计数。
- 额外的流式运行回归测试覆盖“前一轮尚未结束时拖入下一轮文件”的草稿保留行为。
- 打包后的 `ReverieUI.exe` 已启动，Electron 页面通过 `file://.../app.asar/dist/index.html` 加载，Python bridge 初始化，当前工作区和分支栏可见，页面没有告警。首次运行发现远端 `HEAD` 符号引用被错误显示成 `origin`；已修正、补单测、重新打包并再次启动确认弹层只显示真正的分支。
- 在隔离临时 Git 项目中，打包版输入框接收真实磁盘文件拖放后显示芯片和 `@` 引用，复制出的文件内容与原件相同。通过打包版界面创建并切换 `ui-smoke-branch`，再切回 `main`，外部 `git branch --show-current` 与 UI 一致。昵称偏好经打包版 bridge 保存并重载后，设置表单显示保存值。
- 运行测试使用的 `.runtime/smoke-repo` 和少量 CDP 检查脚本均在现有 `.gitignore` 排除的 `.runtime` 目录内。自动审批策略拒绝清理这些测试文件，只返回 `blocked by policy`，因此此处如实保留其位置。
- 未用真实云端 PR、远程移动设备或受保护模型密钥验证；不把源码存在、单测通过或打包成功写成这些能力的真实服务验证。

## 7. 来源

### Codex / ChatGPT 官方资料

- [C1] [Code review](https://learn.chatgpt.com/docs/code-review)：审查基准、PR 上下文、stage/unstage/revert、提交与推送。
- [C2] [Worktrees](https://learn.chatgpt.com/docs/environments/git-worktrees)：平行任务、独立 checkout、起始分支及 handoff。
- [C3] [Prompting](https://learn.chatgpt.com/docs/prompting)：`@` 文件、运行中 Steer/Queue 和可编辑队列。
- [C4] [Image inputs](https://learn.chatgpt.com/docs/image-inputs)：各表面的图片附加、粘贴、拖入方式；具体交互随桌面、Web、CLI、IDE 不同。
- [C5] [Long-running work](https://learn.chatgpt.com/docs/long-running-work)：Goal/Plan、暂停恢复、并行和 side chat。
- [C6] [Integrated terminal](https://learn.chatgpt.com/docs/integrated-terminal)：每聊天的终端与 agent 可读取输出。
- [C7] [Local environments](https://learn.chatgpt.com/docs/environments/local-environment)：项目设置脚本和 action。
- [C8] [Scheduled tasks](https://learn.chatgpt.com/docs/automations)：定时/持续任务、历史、工作树执行和通知条件。
- [C9] [GitHub](https://learn.chatgpt.com/docs/third-party/github) 与 [GitLab](https://learn.chatgpt.com/docs/third-party/gitlab)：连接范围依功能、账号和管理员策略而异。
- [C10] [Codex Remote engineering overview](https://developers.openai.com/blog/mastering-codex-remote-for-engineering)：移动端遥控本机代理、审查与审批。
- [C11] [Work with files](https://learn.chatgpt.com/docs/artifacts-viewer)：桌面端预览文档、表格、PDF、HTML 与标注；不是 Codex CLI 功能。
- [C12] [Projects and chats](https://learn.chatgpt.com/docs/projects)：项目与聊天组织。
- [C13] [Build skills](https://learn.chatgpt.com/docs/build-skills)：可复用技能的范围与发现。
- [C14] [Sandbox and permissions](https://learn.chatgpt.com/docs/permissions) 与 [Agent approvals and security](https://learn.chatgpt.com/docs/agent-approvals-security)：沙箱与批准是两个边界。
- [C15] [Browser](https://learn.chatgpt.com/docs/browser)：桌面内置浏览器入口及标签使用。
- [C16] [Cloud environments](https://learn.chatgpt.com/docs/environments/cloud-environment)：云端 checkout、容器和 setup script。

### 本仓库的主要证据

- [桌面 UI 与输入栏](../ReverieCli-ui/src/App.tsx)，[会话文件改动视图](../ReverieCli-ui/src/FileChanges.tsx)，[桌面 bridge 动作契约](../ReverieCli-ui/electron/core-actions.ts)。
- [Electron 入口](../ReverieCli-ui/electron/main.ts)、[preload](../ReverieCli-ui/electron/preload.ts)、[Python SDK bridge](../ReverieCli-py/reverie/sdk_bridge.py)。
- [会话差异来源](../ReverieCli-py/reverie/desktop_changes.py)、[Git 上下文检索](../ReverieCli-py/reverie/context_engine/git_integration.py)、[可用工具定义](../ReverieCli-py/reverie/agent/tool_manifest.json)、[安全权限说明](SECURITY_PERMISSIONS.md)。
## 2026-09-30 实施记录入口

本文保留 2026-09-29 审计基线。S01–S21 的后续实现已经接入 R1–R4，当前源码行为与独立验收状态以 [2026-09-30 实施与验收报告](REVERIE_CLI_IMPLEMENTATION_REPORT_2026-09-30.md) 为准。原审计中的“缺失”描述不是当前工作树的逐项完成结论。真实模型、连接授权与原生中文候选窗仍有未完成证据；T01–T05、X01–X08 与 Local/Cloud 没有扩展进本次实现。
