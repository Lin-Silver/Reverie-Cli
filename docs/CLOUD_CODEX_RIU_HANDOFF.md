# Cloud Codex 续修提示词（2026-10-20 暂停点）

请直接继续 Reverie-Cli 的 RIU、Harness、请求性能、思考区排版和各模型 source 的修复，落实代码、测试、真实运行与文档。不要只交分析或计划，也不要拆成需要用户逐次确认的阶段。用户因本地电脑关机要求暂停，并明确授权将当前全部源码工作保存到 GitHub；本文件随该暂停提交交付。版本保持 2.5.0，不发布、不新增付费服务、不购买额度或申请密钥。

## 基线、必读材料与环境

仓库是 https://github.com/Lin-Silver/Reverie-Cli ，本机原路径 `G:\Reverie\Reverie-Cli`，Windows / PowerShell。原始 HEAD 为 `0bcbddadb55c24742dff35ff0b6045c0ea938034`，但它原本不含大量 RIU 续修。本次暂停提交将这些已有未提交/未跟踪源码一起保存。**以包含本文件的提交及其后继为实际基线，不能退回旧 HEAD。** 开始先检查 AGENTS.md、git status、分支、提交、平台、磁盘和依赖，保留已有改动，不 reset/clean/覆盖恢复，不擅自换到只含旧 HEAD 的 checkout。

先实际阅读：`docs/INTELLIGENT_UI_SPEC.md`、`docs/FEATURE_STATUS.md`、`docs/ROADMAP.md`、`docs/VERIFICATION_HISTORY.md`、`docs/DESKTOP_GUIDE.md`、`docs/changelog.md`、`docs/verification/2026-10-17-riu-prompt-quality.json`、`docs/verification/2026-10-20-riu-continuation.json` 及本文件引用的新日志。验证历史中 `riu-prompt-quality-2026-10-17`、`riu-quality-2026-10-20` 和最新暂停条目要分别阅读；不能把早期失败当当前结论，也不能用后来的成功抹掉原失败。

Cloud 可能没有 Windows、真实凭据、本机 SDK、打包程序或 `.runtime/` 原始证据。逐项检查并说明缺什么；源码已提交不代表本机产物也上传了。缺某项就继续其他可执行工作，准确保留受阻验收；不能伪造旧日志、用 mock/手写 HTML 填真实样本，或将 Linux 测试冒充 Windows 原生通过。所有新临时文件、模型会话、日志、截图和配置留在当前仓库内的新独立输出目录；不使用 Desktop，不覆盖旧证据。

## 用户最新方向：云端使用 OpenCode 免费来源

**云端优先使用 OpenCode 免费网关中实际可用的匿名免费模型，例如 Space Bunny。** 本机之前按用户指示将真实测试默认设为 SenseNova `sensenova-6.8-flash-lite`；这是本机阶段配置，不要求 Cloud 索取或复制本机 SenseNova/NVIDIA 密钥。Cloud 应扩展现有真实验证器对 `opencode` 的支持，在隔离配置里选择免费来源，不修改用户原始默认来源、凭据或安全设置。

重新查询当时的官方文档和 live models 目录，核对模型 raw ID、免费资格、端点、协议、是否确实匿名可调用、工具/思考能力和速率限制。2026-10-20 阅读的 [Zen 官方资料](https://docs.opencode.ai/docs/zen/)列出了候选 `space-bunny-free` 和 chat/completions，但目录/免费政策/新旧 API 路由会变化，不能硬编码旧目录当可用性证明。也检查最新官方文档与实际返回；不要因名称带 Free 就假定无需认证或当前可用。

**API 中途出错要自行定位、修复、优化各 source 的客户端问题，继续其他可用线路，不要遇到一次错误就结束任务。** 沿来源配置→模型选择/raw ID→URL/headers/proxy→Chat/Responses/Messages→流式/non-streaming→原生思考/工具参数→executor→Desktop/history 全链路定位。针对具体失败先加 focused reproduction，再最小修复；覆盖错误体、SSE 中途错误、空响应、截断、超时、取消、连接复用、重试、Retry-After 和模式能力声明。保留其他 source 的兼容回归；有凭据才做其真实远端验证，没有凭据仍能完成本地协议测试和修复，不声称所有来源已实测。

历史 OpenCode 免费接口确实返回过 403 FreeTierError，只允许其客户端调用；那是当时服务结论，不等于 Cloud 今天必然失败。用 Reverie 的真实身份重新检查。不得伪装 OpenCode User-Agent/客户端、绕过权限或额度限制。官方 OpenCode 客户端可以单独作辅助对照，但不能代替 Reverie 生产链路测试。持续的 401/403/429/服务停用按真实错误归因，遵守退避，不无限重试或购买服务；自动切换到另一条合法可用的免费路线。只有一个模型可用时完成该模型全部组合，并明确第二模型阻塞。

## 已完成、必须保留的修复

- 模式指导按真实工具注册表构建；Writer 不再收到不可调用的工程/MCP/插件说明，Atlas 实际注册账本；raw ID 与显示名分离；媒体开关、模型/凭据、已配置能力与已验证服务分开陈述；模式切换刷新指导。
- 移除重复 manifest 参数/示例注入，保留用途、适用条件、调用限制和全部 native schemas；默认 rules.txt 注释不再作为规则；真正代码分析仍检索，离线 HTML 注册不再被文件扩展名或否定文件语句强制插入检索。
- Desktop 不继承 CLI“没有后续对话”的规则，不自动发送“Approved. Continue…”冒充批准。原生思考过滤/猜测删段逻辑已移除；流失败/取消保存已收到的完整思考和空白，不执行半截工具参数。不能为看起来干净再过滤、隐藏或截短思考。
- RIU 提供可运行的标准初始化、主题和串行宿主私有状态示例。render_view 的浏览器存储静态提醒只是作者反馈，不是安全校验器。更大位置按钮、可展开摘要、保留高度的懒加载占位、约 400px PiP 的高度改善和原有 iframe 状态保存均保留。
- 最新未打包改动：按任务自动选择适合的交互视图，不等待用户刻意说 HTML/页面；普通问答正常文本；强调初始化业务结果、控件联动、空/错误状态、结果/关键控件优先和用户语言摘要。
- 最新未打包改动：Desktop 在实际检索时再初始化 Context Engine；空 Harness 无账本/审计时提前返回；Harness 用“同一 cwd + 同一命令的最后结果”判断未解决失败，保留累计原始失败数，其他命令/目录不能清掉失败。
- 最新未打包改动：`.reasoning-content .markdown { white-space: normal; }` 修复继承 pre-wrap 导致 Markdown 列表间距巨大。实际 App 测试保留 fenced code 缩进；真实旧包同一原生思考仅改变宿主 CSS，高度 2318.421875→1078.671875px、21 项列表、DOM 文本哈希不变。不是删思考，也不是新包已验收。不能盲改未参与当前构建的 `_legacy_*` prompt；其探索修改已撤回。
- Windows 便携启动器修复深路径遗漏 19 个 Skill 文件；按文件扩展路径提取、任何写失败退出2、成功后才写完成标记；启动器自身字节进入缓存身份。保持这项修复和原失败记录。

## 暂停时的真实验证状态

最新源码 focused：85 passed。Desktop 全量：383 passed / 1 skipped，86.33s。类型检查通过（1041 translations / 82 templates）。**最新 Python 全量：2098 passed / 2 skipped / 1 failed，449.56s**；失败 `test_input_handler.py::test_windows_prompt_editor_paste_preserves_single_newline`，`IndexError: pop from an empty deque`。单独重跑 1 passed / 0.18s；尚未确定根因，不可把全量改记通过。输入处理产品文件本轮没有修改；排查时序/隔离问题并保留失败。原始日志副本见 `docs/verification/2026-10-20-riu-continuation/`。

此前通过的 Windows 包是 **2.5.0 / 2cfd719ac18e73a4**，不是包含上述最新修改的新构建：Python 2081/2、Desktop 382/1、P2 24/24、P3 26/26、P4 31/31、隔离36/36、Windows归档5/5、便携恢复3/3、1084/1084解压文件哈希匹配。P4本地渲染20次P95 345.467ms、最大499.104ms；输入60次P95 68.8ms/最大73.8ms。更早244.925/411.419ms和2556.658ms尖峰均属其他构建/边界；不能择优混报。最新改动尚未重建独立CLI、Desktop内核/目录包、安装器和便携包。安装/卸载、PATH/快捷方式、Linux/macOS验收未完成。

本机 SenseNova 真生产包自然语言计算器基线 `before-sensenova-recorded`：4个请求、约147557.2965ms一轮，首个原生输出24777.3ms、首工具72890.3ms、view_ready134649ms；首请求125555字节，system56137字符，schemas65683字符/27工具。上游响应合计约139秒；提供商推理和网络无法仅凭客户端进一步拆开。首请求命中已有6144 token配置上限，产生空 create_file 参数，后经正常反馈恢复，原始失败保留。没有新增回答/思考长度上限。此前另一次 SenseNova 基线 recorder 配错 base_url/api_url，真实请求绕过录制器，其计时不能当完整 API 证据。

**两次 SenseNova 基线都用了 generation-only，旧报告将0项语义断言的注册错误标成 first_pass/repaired_success。原报告保留，正确解读为 registered_unvalidated；验证器已补测试修复。** 二者不能算质量通过。旧 NVIDIA 矩阵因用户改模型在样本间停止：计划36、完成10；Nemotron存在业务/主题/状态/可访问性缺陷及验证器错误，Laguna出现503 worker额度错误。没有完整30生成样本，不能标矩阵完成。本机直接200探针只说明当时可用，不证明GUI/工具稳定。

## 要继续完成的工作与验收

1. 审查实际完整请求构成与全部刷新路径：system、模式、harness、Context Engine、固定 Skill、插件/MCP、manifest、native schemas。根据真实数据精简重复，不截断尾部、不藏工具、不删用户指令/安全约束/可运行示例，不另造复杂框架。思考围绕任务、事实、交互和验证，原生不遵循也如实保留计入质量。
2. 复现并修复 source 错误、未完成的 Harness 问题、UI 排版及自动选用视图质量。保持最小完整改动，不无关重构或全文件格式化。模型目录、历史成功率或开关不等于能力已验收。
3. 复用并扩展 `scripts/verification/riu_quality_benchmark.py`、`riu_prompt_real.py`、`riu_p2_electron.py`、`riu_p3_electron.py`、`riu_p4_electron.py`、`riu_p4_windows.py`、`riu_p3_artifacts.py`。自然任务 fixture 是 `scripts/verification/fixtures/riu-natural-tasks.json` **2026-10-20.2**；旧显式UI任务集保留为历史对照。每模型×calculator/table/chart/form/comparison各3次独立全新会话，至少30生成任务，普通文本对照另记。优先两个真实可用免费模型；固定任务、采样与提示词版本后全部保留。不能把同一profile中带工作区记忆的后续会话叫完全独立。
4. 每类验证业务初值/变化、可操作控件、必要空/错误状态、键盘、自然语言修改、版本追踪、同一实例inline/fullscreen/pip、主题、保存和实际进程重启恢复。断言语义，不强制单个HTML模板/固定措辞。验证器选择器、编码、懒加载、重载事件丢失与异步错误先定位修复，保留原失败再新目录重跑；不能由脚本改模型HTML后算成功。只允许模型经正常 create_file/render_view/executor修复。首次成功、正常修复成功、超时、违规、服务不可用和验证器错误分开统计。
5. 人工实际查看并操作多类真实页面：inline、工作面板、约400px PiP、窄窗、深浅主题、长中文/长标题、空/错误和键盘。关键结果/控件容易发现；摘要用用户语言。不能只磨储蓄比较器、只看截图/主题切换，不能隐藏必要内容/审批改变业务换漂亮效果。
6. 相同任务/模型/配置前后对照完整请求字节、system/schema规模、首原生/可见输出、首有效工具、模型轮完成、工具/本地渲染、重试错误和所有延迟异常。录制器字节转发生产请求，原始SSE/HTML哈希保留；测量时不并行编译/压缩/批量请求。不能把提示词长度直接解释为513秒生成原因。
7. 产品代码变更后完成 focused + 全量Python/Desktop + typecheck/docs/diff + 构建 + 消费者协议/GUI。Cloud缺Windows时仍做可运行原生平台/浏览器/协议/真实模型工作，明确无法做的Windows最终包；源码/直接HTTP/替代平台成功不能替代消费者验收。先修全量Python粘贴测试的时序疑点。

## 不可破坏的边界

继续复用 executor、security_policy、permission_review、审批 worker ownership 和会话锁。组件按钮、消息、权限声明、user-gesture不能冒充批准；追问经宿主人类明确操作。不能绕过执行器直调MCP。私有_meta不入模型，app-only不暴露模型；资源身份、实例隔离、撤销、unknown写不重放、跨会话拒绝保留。页面继续opaque-origin沙箱及宿主私有状态通道，不放开localStorage/sessionStorage、任意文件/网络迁就模型。

展示模式仅inline/fullscreen/pip，card/carousel是内容布局。MCP Apps profile固定ext-apps2.0.3 / UI2026-01-26。涉及兼容变更重新读官方规格，不造riu/*协议，不宣称完整window.openai/Plugin Extensions或OpenAI功能对等/超越。HTTP/SSE UI、OAuth、远程UI等没有证据不能完成。

## 构建、命令与文档交付

Windows命令须先核对路径参数：`PYTHONPATH=<repo>/ReverieCli-py`；`python -m pytest -q -c ReverieCli-py/pytest.ini ReverieCli-py/tests`；`python scripts/verification/check_docs.py`；`git diff --check`；在ReverieCli-ui运行`npm test`、`npm run typecheck`、`npm run build`、`npm run pack`。Python核心变化必须先按仓库脚本重建独立CLI，再Desktop内核与信任清单，核对冻结代码、manifest、编译UI、实际build ID。不要将旧CLI哈希写入新清单或放宽信任校验。

SDK按 `scripts/verification/fixtures/mcp-apps/package.json` 和lock准备在仓库内，保留官方组件原始字节。GUI验证顺序执行避免单实例/焦点争用；`--exe`为最终win-unpacked/ReverieUI.exe，`--sdk-root`为核对的SDK，`--output`为新目录。安装器/便携从最终验证目录包生成，实际便携解压、启动、恢复交互和SHA256另验。安装/卸载只在干净Windows VM/沙盒，不在主机覆盖/卸载现用软件。其他平台只有真实原生测试才通过。

大构建/解压前重新核对磁盘，争取≥5GB；本机14:30UTC约24GB仅是旧观察。清理仅可再生缓存，保留用户文件/失败会话/HTML。Windows递归删除/移动先独立确认解析绝对路径在明确可再生项目目录内，用PowerShell LiteralPath，不跨shell拼命令，不绕过自动审批拒绝。

持续更新FEATURE_STATUS当前能力/限制、ROADMAP质量门、INTELLIGENT_UI_SPEC实际契约、VERIFICATION_HISTORY本轮命令构建失败/成功证据、changelog具体变更和必要DESKTOP_GUIDE。结构化报告追溯来源/raw ID、提示词版本、任务/尝试、初次/修复成功率、业务交互断言、原生/工具/本地计时、截图/HTML哈希及归因。最终分别说明源码、打包、模型、人工视觉、安装器/平台范围和Git交付事实；留下准确阻塞，不以“建议以后继续/要不要下一步”替代可执行工作。

本机原始证据（通常被忽略，Cloud不保证存在）：`.runtime/riu-prompt-update-20261017-093759`、`.runtime/riu-quality-20261018-060708`、`.runtime/riu-experience-20261020-100708`、`.runtime/riu-p3-sdk`。不要重建伪装旧记录；缺失时用已提交摘要与当前源码建立新的有明确日期和范围的验证。
