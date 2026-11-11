# Computer Use 内置工具

Reverie 在 `reverie` 和 `aio` 模式中提供相同的 29 个 `computer_*` 内置工具。Windows x64 包内置 agent-desktop 1.2.0；运行时不安装依赖、不查询 PATH、不通过 PowerShell 或 MCP 转发桌面操作。

旧 Computer 模式入口现迁移为 AiO，使用独立助手主线和任务分支，历史迁移保留原文件与旧模式来源。AiO 使用当前选择的模型、提供方和推理设置，不绑定 NVIDIA。NVIDIA 仍是正常可选的模型来源。助手使用、迁移与后台调度范围见 [AiO 与独立对话](AIO_CONVERSATIONS.md)。

核心路线是不依赖截图和像素匹配的无障碍语义控制。截图和物理鼠键是显式补充能力；普通观察、语义点击和语义输入不会为了执行操作而接管指针或前台焦点。

## 开始使用

1. 在模型选择器选择模型，并按原有设置启用 `full_control`。`computer_status` 可以在基础只读权限下诊断引擎；其他桌面观察和操作都要求 `full_control`。
2. 通过 `computer_list_windows` 得到目标 `window_id`，再调用 `computer_snapshot`。多个候选必须明确选择。
3. 从返回结果取出完整的 `@<snapshot_id>:eN` 引用，调用 `computer_set_value`、`computer_click` 等工具。
4. 用 `computer_get`、`computer_is` 或 `computer_wait` 验证所需的属性或状态。需要重新理解布局时再获取树；只有需要视觉判断时才截图。

文本模型使用无障碍树。视觉模型可以额外接收截图。截图也会保存为 PNG，供界面的文件预览打开；文本模型和启用纯文本 API Compatibility 的会话不会接收图片，也不能使用图片坐标。

## 工具接口

完整机器可读 schema 由 `reverie/tools/computer.py` 定义。所有工具拒绝未知参数、错误枚举、越界数字和不符合嵌套结构的值。常用 `timeout_ms` 范围为 1–60000，默认 5000；原生子进程另有 2 秒退出余量。

| 工具 | 核心参数与用途 | 操作性质 |
|---|---|---|
| `computer_status` | 引擎、权限、平台能力诊断 | 只读，基础权限 |
| `computer_list_apps` | 可选 `app`；运行中的应用 | 只读 |
| `computer_list_windows` | 可选 `app` / `window_id`；返回窗口、进程身份、位置和焦点 | 只读 |
| `computer_list_displays` | 显示器、尺寸和缩放 | 只读 |
| `computer_list_surfaces` | `app`；窗口、菜单、sheet 等界面 | 只读 |
| `computer_snapshot` | `app` / `window_id` / `root` / `surface`；支持 `compact`、`skeleton`、`interactive_only`、`include_bounds`、`max_depth` | 只读，无隐式截图或聚焦 |
| `computer_find` | 目标范围，以及 `role`、`name`、`text`、`value`、`native_id`、`exact`、`limit` | 只读，返回匹配项 |
| `computer_get` | `ref`，`property`: text/value/title/bounds/role/states | 只读，实时属性 |
| `computer_is` | `ref`，`property`: visible/enabled/checked/focused/expanded/selected | 只读，实时状态 |
| `computer_screenshot` | `window_id` / `app` 或 `screen`；可选 `region` 和 `max_dimension` | 只读，显式图片 |
| `computer_launch_app` | `target`，可选字符串数组 `arguments` | 启动请求 |
| `computer_close_app` | `app` / `window_id`；正常关闭，绝不强制杀进程 | 应用操作 |
| `computer_window` | 目标窗口；`action`: focus/move/resize/minimize/maximize/restore；几何参数 | 窗口操作 |
| `computer_open_system_surface` | `surface`: start-menu/taskbar/system-tray/system-tray-overflow | 可能改变焦点 |
| `computer_click` | `ref` 或 `image_id,x,y`；`button`、`count`、`physical` | 默认语义单击 |
| `computer_focus` | `ref` | 控件及前台焦点 |
| `computer_set_value` | `ref,value` | 语义写入并由原生引擎回读 |
| `computer_type_text` | `ref,text`；可选 `physical=true` | 默认语义输入；显式物理输入可能改变焦点 |
| `computer_select` | `ref,value`；选择指定选项 | 语义选择 |
| `computer_set_state` | `ref,state,value`；state=checked/expanded，value 为布尔值 | 设置明确状态 |
| `computer_press_key` | 目标范围和 `key`；可选 `force` | 按键/快捷键 |
| `computer_scroll` | `ref` 或图片坐标；direction=up/down/left/right，amount | 语义滚动或物理滚轮 |
| `computer_scroll_to` | `ref` | 滚入视野 |
| `computer_drag` | 两端各自的 `from_ref/to_ref` 或 `from_image_id,from_x,from_y` 等 | 完整原子拖动 |
| `computer_pointer` | `ref` 或图片坐标；action=hover/move | 悬停/移动指针 |
| `computer_wait` | `ref,predicate,value`，或目标范围加 `selector/gone/text/window` | 有限条件等待 |
| `computer_clipboard_get` | format=text/image/auto | 只读 |
| `computer_clipboard_set` | `text` 或工作区 PNG 的 `image_path`，二选一 | 剪贴板写入 |
| `computer_clipboard_clear` | 无参数 | 剪贴板清空 |

`role` 应使用观察结果中的标准名称，例如 `textfield`、`button`、`combobox`、`option`、`treeitem`。下拉框支持哪些操作取决于应用的 UI Automation provider：若容器不支持 Select，应先观察它的展开能力，再定位具体 option；不要将“没有提供此模式”误当作元素不存在。

## 引用、坐标与结果

- 引用属于创建它的原生 session。每个活跃 Reverie 会话拥有独立随机命名空间；切换会话、清空历史或恢复同一个会话都会废弃旧运行时。磁盘历史不能恢复引用的操作权限。
- `complete`、`truncated`、`identity_unproven` 必须参与判断。过大的结果保存至项目工具结果目录；发送给模型的结果仍是有效 JSON，并明确标记不完整，保留交付、错误和目标信息。条件等待只返回条件及完整性信息，不额外发送整个树。
- 截图默认最长边 1400 像素，可设置 64–2800。`region` 是原始截图内的裁剪范围；动作的 `x,y` 是返回图片内的坐标。运行时记录原始尺寸、裁剪、缩放、窗口/进程身份和截图时间。
- 坐标引用最长保留 120 秒，每个运行时最多保留 64 个截图记录。任何桌面写操作都会使现有截图坐标失效。执行前检查模型是否收到图片、边界、窗口身份、位置、尺寸及焦点；窗口坐标还检查实际命中的顶层窗口，拒绝遮挡。外部应用仍可能在检查和原生交付之间改变界面，交付后的结果必须验证。
- 普通 ref 左键单击默认走语义路径。其他按钮、多次点击、坐标点击需要显式 `physical=true`。不提供独立 key-down/key-up、mouse-down/mouse-up，也不提供任意命令或批处理入口。
- `ToolResult.data.computer_use` 保留 JSON 2.6 envelope，输出和错误中都保留结构化信息。`ok=true` 表示引擎调用返回成功，不等于用户任务完成。`delivered_unverified`、`delivery_uncertain` 或 `unknown` 不能自动重放；`retry=unsafe` 必须先重新观察。没有窗口或焦点变化不证明动作未发生。
- 当前模型请求在所有关联工具结果之后携带图片，适配 Chat Completions、Responses 与 Anthropic。历史只存路径/会话图片标记，不存 base64。会话压缩保留近期桌面交付状态；旧截图不会因恢复历史而重新获得坐标权限。剪贴板图片可供视觉模型查看，但没有桌面坐标空间。

## 权限、取消与兼容

工具分别声明 `read_only` 和 `required_permission`，并沿用 `default / auto_check / strict` 审批策略。主代理的桌面工具不可并行；原生引擎还提供跨进程交互锁。子代理看不到桌面 schema，直接调用新名称和旧别名也会被拒绝。

停止会阻止后续操作。只读原生进程可以取消；已经开始的有限原子输入允许完成或到达截止时间。进程超时、异常退出或无效协议不能确定交付时会返回结果未知，绝不自动重试。操作系统或进程被强制终止时不作“所有输入状态已恢复”的保证。

会话保留模型所需的文本结果与轻量图片标记。操作诊断和 Electron 运行日志只保留必要元数据、交付状态和错误码，不重复记录输入正文、剪贴板内容或图片 base64；导出日志也保持这一约束。

旧名称 `list_apps`、`launch_app`、`get_app_state`、`click`、`drag`、`scroll`、`type_text`、`press_key`、`set_value`、`perform_secondary_action` 作为隐藏入口继续存在。它们调用相同运行时，模型的新请求只接收一套新 schema。旧数字索引只能来自本会话新调用的 `get_app_state`。

可执行文件使用原生 launch，裸名称额外支持 Windows App Paths。带参数的可执行文件启动使用 `--no-attach`：若目标已经运行则明确拒绝，避免上游连接现有进程时丢弃参数。HTTP(S) URL、文档和文件夹保留 Windows ShellExecute 启动方式，随后通过新引擎观察。启动已交付之后，即使观察失败，也保留 `delivered_unverified/unsafe`。原生 close 按应用执行，因此多个同名窗口时接口返回候选并拒绝默认关闭第一个；可观察具体窗口的关闭控件。

`complete=true` 仅表示已完整遍历应用提供的无障碍树，不证明所有可见控件都被该 provider 暴露。若渲染内容未暴露，应报告缺少无障碍证据；视觉模型可显式请求截图，文本模型不可猜测坐标。

## 构建与分发

固定版本和来源见 `ReverieCli-py/reverie/computer_use/native_manifest.json`：

- agent-desktop **1.2.0**，commit `2b0a7334fc111730454b726e6800aa41cdafc093`，JSON **2.6**。
- Windows x64 归档 SHA-256：`a4199f741a441cedd349bf56c5eba01783b1261258b498efeb7ec9945220c3e8`。
- 原生程序 SHA-256：`d274667031322e50b9c2b1ab81c2ca46835d52cc932769a5c34bd4d481fd94c3`。

`scripts/prepare_computer_use.py` 只在构建阶段下载并校验归档和程序，同时保存固定提交的 Apache-2.0 LICENSE、来源和 receipt。缓存也必须匹配 manifest 的程序校验值。PyInstaller 和 Windows wheel 均包含该原生目录；wheel 标记为 `py3-none-win_amd64`。运行时只访问包内绝对路径，首次调用会再次校验程序，不要求用户另装 agent-desktop、Node 或 Python 来运行便携包。

源码环境可在 `ReverieCli-py` 运行 `python scripts/prepare_computer_use.py` 后使用。UI 发行包使用现有 `npm run build:kernel`、`npm run build` 及 Windows 打包流程。引擎缺失不会阻止其他内置工具初始化，桌面工具会返回可操作的 `ENGINE_UNAVAILABLE` 诊断。

上游参考：[发布版本](https://github.com/vercel-labs/agent-desktop/releases/tag/v1.2.0)、[引用机制](https://github.com/vercel-labs/agent-desktop/blob/v1.2.0/apps/docs/content/docs/snapshots-and-refs.mdx)、[JSON 结果协议](https://github.com/vercel-labs/agent-desktop/blob/v1.2.0/apps/docs/content/docs/json-output.mdx)。Reverie 的 Python 工具、权限和模型适配是本项目实现，原生二进制保持上游发行版本。

本轮验收事实与限制见 [初次验证记录](verification/computer-use-2026-11-05.md) 和 [实机与 Harness² 补充记录](verification/computer-use-live-harness2-2026-11-05.md)。Windows ARM64、macOS、Linux、通知中心管理和操作动画不在本轮验收范围内。
