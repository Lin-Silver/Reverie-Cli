# Reverie Desktop S01–S21 实施与验收记录

本次直接更新 `G:\Reverie\Reverie-Cli`，按 R1 → R4 实施默认 S01–S21。T01–T05、X01–X08、Local/Cloud 未纳入。9 月 30 日阶段遵照最初要求没有 commit/push；10 月 1 日用户追加“验证后提交”，授权深入验证后本地提交，未要求推送。新增修复、最终测试和截图见 [深入验证记录](REVERIE_CLI_DEEP_VALIDATION_2026-10-01.md)。验收使用的临时 Git 仓库、bare remote、私有恢复引用均位于项目内部。

**代码和界面已经接入全部 21 项，阶段验收仍有明确缺证据项。** “已实现”表示功能路径存在；“打包验证”只表示下面实际走过的场景。缺模型、连接授权或原生输入法证据的项目保持验收未完成，不能把单元测试当成真实服务成功。

## 1. 保留与运行位置

- 开始时读取 ROADMAP、新增清单、差距分析，检查源码和 Git 状态，遵守用户提供的项目 guardrails。
- 原有未提交文件保存于 `.runtime/implementation-20260930/baseline/files`，Git 基线保存于 `baseline/status.txt` 和 `baseline/head.txt`。原有 RATS e2e 修改和 `result_images` 保留。
- 每次打包前备份已有 `release/win-unpacked/.reverie`，打包后恢复；测试使用独立 `PORTABLE_EXECUTABLE_DIR`，不会把测试配置写入原有打包数据目录。
- 9 月 30 日保留核对：原打包数据的 54 个文件哈希全部一致；无关 RATS e2e 文件与开工备份一致；提交前 HEAD 为 `67b9b28950cc20ebf4184dc235a4698ed178c5d0`。见 [保留证据](../.runtime/implementation-20260930/preservation-evidence.json)。10 月 1 日提交前再次核对，结果见深入验证记录。
- 验收目录 `.runtime/implementation-20260930/` 加入本地 Git `info/exclude`。临时文件、测试仓库、日志、截图、导出和备份都留在本项目内。
- 输出程序：[ReverieUI.exe](../ReverieCli-ui/release/win-unpacked/ReverieUI.exe)。本次验证 Windows x64 的实际编译内核和 Electron 包。

## 2. 逐项状态

| ID | 代码实现 | UI/UX 接入 | 已通过的验证 | 仍缺证据 / 验收边界 |
| --- | --- | --- | --- | --- |
| S01 | 输入区、状态、工作面板、阅读跟随控制；按项目/会话保留阅读位置 | 复用品牌、主题和原导航，回到最新；窄窗口输入区及面板适配 | R1 中英文/深浅截图；R2 输入器高度；R4 800/1024/1500 面板 | Windows 原生中文候选窗尚未实测 |
| S02 | v2 文本与有序附件草稿，兼容 v1；异步结果归属和失效校验 | 切换恢复、导入取消/失败可见；恢复后缺失或变更副本禁发 | 草稿持久化、真实文件、恢复校验测试；后台队列切会话回归 | 真实模型长任务切换缺证据 |
| S03 | 原生截图剪贴板、真实拖放/选文件，工作区引用与外部复制，限额、哈希、顺序 | 文件/缩略图卡、重排、删除、重试、固定副本、预览和纯附件发送入口 | R1 原生 CF_DIB→PNG、中文文件/外部文件真实导入；混合内容次序测试 | 纯图/混合输入的真实模型理解缺活动模型 |
| S04 | `@` 防抖检索、文件/符号行引用、最近引用；模型视觉能力未知时明确展示 | 上下键/Enter/Escape；路径、行和本条上下文；推荐与附加分开 | 检索交互与模型能力拒绝测试，实际文件版本读取 | 真实符号检索大项目和视觉服务结果仍需补验收 |
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

## 3. 构建与验证产物

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

## 4. 明确未完成的验收

1. 保留的独立打包配置没有活动模型。真实请求得到 `No active model is configured.`（此前显式空选择也得到 `Unknown or ambiguous model for Manual Model`）。10 月 1 日仅在独立测试配置中使用本机 HTTP 协议记录端点，验证实际内核图片传输、顺序、哈希和落盘，不进行视觉推理。因此纯图片理解、长任务 Steer/暂停/Stop、模型只读发现、两 worktree 同时模型写入与审批隔离的完整服务验收仍未完成。
2. 没有真实认证插件、托管远端凭据或活跃授权 RATS 服务参与本次验证。页面显示实际内核可调用工具、安装/信任状态及未知授权；账户与服务操作成功尚未证明。
3. IME `isComposing` 和 229 防误发已实现；中文路径、内容与真实 PTY 已验证。原生中文输入法候选窗、组合输入后 Enter 的完整人工实机验收仍缺证据。
4. Windows 最小化后台通知已获得真实 `shown` 事件，应用内列表独立保留。系统通知点击回跳与 OS 禁用通知设置的实机场景未测试；审批通知仍需真实模型触发。`requested` 本身不视为送达通过。

## 5. 使用入口

输入器：剪贴板图片、附件按钮/拖放、`@`、上下文详情、运行中的 Queue/Steer/Stop。队列重启后暂停，需显式继续。

“工作面板”：Git → 范围、文件/区块、提交、普通推送；文件预览 → 路径/行、图像/PDF/静态 HTML；只读审查 → 明确范围或指定文件；运行与终端 → 独立工作目录、用户终端、项目动作、运行记录、目标、通知、生效能力。

独立工作目录的初始化不会自动执行。打开目录后在项目动作中检查命令并确认运行。归档前检查所有忽略文件；默认保留。恢复后的 HEAD 分离，原提交祖先和本地恢复引用保留。归档不使用强制 dirty 删除；进行中的任务和终端必须先结束。

退出有运行中的后台任务/终端时给出目录、会话和 PID 影响说明。普通停止优先合作取消；强制停止需要核对部分副作用。未知状态不会自动重放文件写入或命令。
