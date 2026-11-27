# Rust Computer Use

Rust 内核通过 `computer_*` 工具调用随包提供的 agent-desktop 1.2.0，校验协议 2.6。SDK、终端和 Electron 共用这一条执行路径。内置来源为 vercel-labs/agent-desktop 的提交 `2b0a7334fc111730454b726e6800aa41cdafc093`。四种发布目标的归档、可执行文件和辅助程序均有固定 SHA-256，随包分发上游 Apache-2.0 许可。[来源清单](../../ReverieCli-rs/resources/computer-use/manifest.json) · [许可](../../ReverieCli-rs/resources/computer-use/LICENSE)

| 操作 | 约束 |
| --- | --- |
| `computer_status` | 读取引擎、协议与系统权限。可在只读权限下诊断。 |
| `computer_list_apps`、`computer_list_displays`、`computer_list_windows` | 桌面信息需要 `full_control` 权限级别。窗口可按应用名称过滤。 |
| `computer_snapshot`、`computer_find`、`computer_wait` | 仅观察本轮窗口清单中的指定窗口，核对操作系统返回的窗口与进程身份。 |
| `computer_get`、`computer_is` | 从本轮最近一次观察中取得控件引用，实际读取控件属性或状态。 |
| `computer_click`、`computer_set_value`、`computer_set_state`、`computer_select`、`computer_scroll`、`computer_scroll_to` | 使用原生无障碍接口。一次输入消耗当前观察，后续输入需要新引用。原生返回实际送达状态；结果不确定时应重新观察。 |

Strict、Normal、Auto 和 Full Access 采用内核现有审批流程。显式权限级别低于 `full_control` 时只提供状态诊断，直接构造桌面调用也会被拒绝。一次运行使用独立的临时原生目录和快照会话；内核按编译时清单校验复制的程序及辅助程序。取消会终止已派发的子进程。已经派发的输入遇到超时或取消时，向调用方报告送达结果不确定。

## 构建与复验

桌面打包和四平台候选工作流自动准备组件。开发者使用裸 Cargo 构建独立 CLI 时，在项目根目录依次执行以下命令。使用自定义 `CARGO_TARGET_DIR` 时将 `release` 目录替换为实际路径。构建机可用 `REVERIE_DESKTOP_ARCHIVE_DIR` 指向已有的官方归档目录以支持离线打包。

```sh
cargo build --manifest-path ReverieCli-rs/Cargo.toml --release --locked
node scripts/prepare-computer-use.mjs ReverieCli-rs/target/release
node scripts/verification/rust-computer-use-smoke.mjs --status-only
```

在已登录的 Windows 桌面运行 `node scripts/verification/rust-computer-use-smoke.mjs` 可执行真实窗口检查。脚本接受 release 可执行文件和证据目录两个可选位置参数。它启动自有 WinForms 窗口和回环模型，用 `--sdk-bridge` 驱动工具，核对实际窗口状态、UTF-8 文件和被取消进程的退出。模型仅负责发出确定的调用。图像坐标、物理键鼠、真实模型选择与其他平台的桌面交互另行验收。
