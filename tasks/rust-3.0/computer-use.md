# Rust Computer Use

Rust 内核通过 `computer_*` 工具调用随包提供的 agent-desktop 1.2.0，校验协议 2.6。SDK、终端和 Electron 共用这一条执行路径。内置来源为 vercel-labs/agent-desktop 的提交 `2b0a7334fc111730454b726e6800aa41cdafc093`。四种发布目标的归档、可执行文件和辅助程序均有固定 SHA-256，随包分发上游 Apache-2.0 许可。[来源清单](../../ReverieCli-rs/resources/computer-use/manifest.json) · [许可](../../ReverieCli-rs/resources/computer-use/LICENSE)

| 操作 | 约束 |
| --- | --- |
| `computer_status` | 读取引擎、协议与系统权限。可在只读权限下诊断。 |
| `computer_list_apps`、`computer_list_displays`、`computer_list_windows` | 桌面信息需要 `full_control` 权限级别。窗口可按应用名称过滤。 |
| `computer_snapshot`、`computer_find`、`computer_wait` | 仅观察本轮窗口清单中的指定窗口，核对操作系统返回的窗口与进程身份。 |
| `computer_window` | 对本轮列出的窗口执行聚焦、移动、调整尺寸、最小化、最大化或还原。 |
| `computer_screenshot` | 捕获指定窗口，核对捕获前后的进程、窗口边界与显示器配置。支持按原图像素裁剪和等比例缩小。纯文本模型得到 PNG 路径，视觉模型额外收到捕获时的图片字节。 |
| `computer_get`、`computer_is` | 从本轮最近一次观察中取得控件引用，实际读取控件属性或状态。 |
| `computer_focus`、`computer_type_text` | 将键盘焦点交给具体控件，或在其插入点写入文字。一次输入支持 10,000 个 UTF-8 字节。Windows 原生适配器需要 `physical: true` 才会发送物理输入。默认的语义请求若被拒绝，由调用者决定下一步。 |
| Windows `computer_press_key` | 目前支持 `{"window_id":"…","key":"Escape"}`。从本轮窗口列表选择应用当前活动的窗口；打开模态框后使用对话框自己的 ID。成功表示 Windows 接收了消息，使用新的观察确认菜单或对话框已关闭。 |
| `computer_click`、`computer_set_value`、`computer_set_state`、`computer_select`、`computer_scroll`、`computer_scroll_to` | 使用原生无障碍接口。一次输入消耗当前观察，后续输入需要新引用。原生返回实际送达状态；结果不确定时应重新观察。 |
| Windows 坐标点击及 `computer_drag` | 使用本轮视觉模型最近收到的窗口截图。点击须指定 `physical: true`，拖拽两端须在同一张图内。坐标按返回图像像素计算，可使用裁剪和缩小后的图。 |

Strict、Normal、Auto 和 Full Access 采用内核现有审批流程。显式权限级别低于 `full_control` 时只提供状态诊断，直接构造桌面调用也会被拒绝。一次运行使用独立的临时原生目录和快照会话；内核按编译时清单校验复制的程序及辅助程序。取消会终止已派发的子进程。已经派发的输入遇到超时或取消时，向调用方报告送达结果不确定。

Windows 在派发坐标输入前重新核对截图的 120 秒有效期、进程与窗口身份、DWM 物理边界、显示器缩放、前台窗口和投递点遮挡。审批等待计入有效期。一次投递会消耗截图，应用效果须通过新的观察确认。首次获准的非状态桌面工具会为本次运行启用 Escape 停止。多个 Reverie 内核使用同一登录会话的 Windows 互斥锁串行操作桌面，等待者可以取消。独立运行的第三方桌面程序可自行改变焦点和布局。

## 构建与复验

桌面打包和四平台候选工作流自动准备组件。开发者使用裸 Cargo 构建独立 CLI 时，在项目根目录依次执行以下命令。使用自定义 `CARGO_TARGET_DIR` 时将 `release` 目录替换为实际路径。构建机可用 `REVERIE_DESKTOP_ARCHIVE_DIR` 指向已有的官方归档目录以支持离线打包。

```sh
cargo build --manifest-path ReverieCli-rs/Cargo.toml --release --locked
node scripts/prepare-computer-use.mjs ReverieCli-rs/target/release
node scripts/verification/rust-computer-use-smoke.mjs --status-only
```

在已登录的 Windows 桌面运行 `node scripts/verification/rust-computer-use-smoke.mjs` 可执行真实窗口检查。脚本接受 release 可执行文件和证据目录两个可选位置参数。它启动自有 WinForms 窗口和回环模型，用 `--sdk-bridge` 驱动工具，核对实际窗口状态、UTF-8 文件和被取消进程的退出。脚本独立解码 PNG、检查夹具画布颜色，将发往视觉模型的图片与文件逐字节比较，并在替换公开预览后再次核对原图。

追加 `--physical` 会聚焦测试窗口并移动鼠标。该检查从实际截图取得坐标，用窗口自己的事件日志核对按钮点击和拖拽端点，分别验证移动、遮挡、过期引用、Strict 拒绝和会话授权。夹具在纯文本会话的原生等待期间注入 Windows Escape，检查任务取消和子进程退出。另用两个真实 SDK 内核和独立互斥锁探针检查占用与释放。真实键盘按键、四档物理 DPI 和 macOS／Linux 交互仍待单独验收。

文字输入检查让测试窗口自行选中 `A12Z` 中的 `12`。普通调用保留原文；显式物理输入把选区替换为 `中文😀 --headed`。夹具同时检查系统报告的焦点、无障碍接口读回的值及点击“保存”后的 UTF-8 内容。Windows 拒绝前台切换时，工具报告未投递。

普通 Windows 窗口 smoke 还会打开一个模态对话框、一个 WinForms 菜单和一个原生菜单。模型向对话框的父窗口发送 Escape 时，内核拒绝投递。发给正确窗口后，夹具记录对话框的取消结果和菜单关闭状态，SDK 继续同一任务。应用内 Escape 经过目标窗口的消息队列；用户亲按键盘时，桌面任务的停止监听继续读取系统键盘状态。
