# 阶段 1：同一 Rust 内核的首条真实运行链

本阶段承接 [完整 3.0.0 计划](plan.md)、[阶段 0B](phase0B.md) 和最终纯 Python `070fa25`。维护者已决定结束本地扩展测评，立即实施不依赖 ORT 的运行链；本地完成基本构建与实际行为检查，全面验收交云端。原生入口、配置与会话、结构和基础 Context Engine、四种模型协议、实际文件／命令工具、询问、审批与取消已在 `main` 实施。Context Engine 增加符号元数据、方向引用和七种显式证据查询，见 [最新实施证据](progress.md)。滚动终端直接调用内核库，Electron 已接入同一个常驻 Rust 内核，完成本机基本运行验证。完整 Provider 库存、模式、平台与扩展继续迁移；整个 3.0.0 的全部功能、语义、游戏和发行范围保持主计划不变。

## 工作区、来源与完成证据

在 `G:\Reverie\Reverie-Cli` 的 `main` 上建立 `ReverieCli-rs`，固定 Rust/Cargo 1.96.0、Edition 2024 和 Cargo.lock。产品归属仍为 3.0.0；开发程序明确记录开发状态和来源，源码直接推送 `main`。正式标签、`latest` 和 `plugins-latest` 不承接未完成的迁移增量。

每个任务保存对应提交、实际命令、测试及程序摘要。开发阶段能力声明列出实际实现；未完成迁移的 action 继续留在完整矩阵中，不能用成功空响应代替功能实现。第一方 Rust 链路的进程树不得出现 Python 解释器或旧索引 worker。

| 任务 | 实施范围 | 验证检查 |
|---|---|---|
| R1-1：协议与入口 | `reverie`、帮助/版本、`--kernel-info`、UTF-8 JSONL SDK、请求 ID、错误和实际能力声明 | 构建后的 EXE 实际握手；同一 ID 的事件不能提前结束请求；非 ASCII、坏 JSON、EOF、关闭及 stdout 纯 JSONL |
| R1-2：配置与会话 | 现有模型/规则配置、独立会话、持久消息、分页、修订保护及有效配置 | 原始文本及未知配置字段保留；重启接续；两个会话互不修改；冲突修订被拒绝；元数据更新不重写完整原文或改变选中会话 |
| R1-3：Provider 与执行 | 首条 OpenAI Chat 兼容 HTTP/流式请求、真实工具执行、权限与取消 | 本地服务只提供模型协议响应，Rust 实际读取/执行并存结果；逐块 UTF-8/SSE、工具参数错误、取消、许可拒绝及进程正常回收 |
| R1-4：基础 Context Engine | 同进程 Rust 扫描、索引持久化、词法/符号/路径查询、片段和状态 | 完整固定语料、增量变化、删除/重命名、Git 标准忽略、内容修订及真实查询；默认最多 72 行，保持估算预算；资源缺失仍能基础检索 |
| R1-5：滚动终端 | 直接调用内核库的输入、流式对话、命令、审批及正常退出 | 真实终端输入输出、scrollback、复制、多行/CJK/Emoji、取消和状态恢复，不能只观察静态帧 |
| R1-6：Electron 接入 | 既有桌面连接同一个 Rust 程序，保留初始化/完整状态/会话/事件链 | 实际 renderer/Electron 构建和原生窗口；输入可用，真实流式回复及工具结果出现，切页/重启不丢草稿和会话 |
| R1-7：开发 CI | 锁定构建、测试、格式、Clippy、类型生成一致性和四平台开发程序 | Windows x64、Linux x64、macOS arm64/x64 真实构建/运行；仅 CI artifacts；开发分支及其手动事件无发布能力 |
| R3-命令首增量 | 原生命令与别名、工作目录／脚本审查、关闭 stdin、输出、审计、审批、取消和进程树 | 本机实际程序及双路输出；原文、执行状态、审批前无副作用、正常／取消／超时后的后代回收；GUI 单卡片和终端完成前可见输出 |
| R2-语言矩阵增量 | Python、JS、TS/TSX、Rust 及新增 C/C++、C#、Go、Java、Zig、HTML/CSS、Lua、GDScript 原生语法，分析版本重建 | 本机 27 项 Rust 检查；十种新增语言的实际 CLI 13 项；完整源码／72 行／哈希、作用域、选定调用、跨文件歧义、旧分析事务重建；四平台新来源另行核对 |
| R2-资源暂存增量 | 固定模型及 ORT 契约、资产身份、独立版本目录和显式 SHA-256 的离线校验／暂存 | 本机资源行为 2 项及实际 CLI 4 项；暂存不激活／不执行入口；实际模型健康、量化及激活继续实施 |
| R2-共享语义与资源管理 | SDK／Agent、后台索引、资源健康、原子激活、任务版本、回退、卸载、GUI 页及 `/context` 命令 | 本机 Rust 35 项、真实模型 SDK 10 项、Electron 窗口 8 项、原生 PTY 9 项；坏模型与取消保护、重启、明确删除和完整中文证据；正式质量／延迟及其他平台另计 |
| R2-原生后台监听 | 原生目录事件、结构与语义追赶、自动进度、暂停恢复、项目取消、关闭和派生库隔离 | 本机 Rust 38 项、真实模型监听 6 项、PTY 9 项和第二次 Electron 窗口 9 项；首次窗口安装超时原因及完整平台故障矩阵继续未验证 |
| R4-Skills 首增量 | 原生内置/本地发现、正文与资源、会话固定完整加载、GUI/TUI 及独立分发 | 实际部署的来源摘要、JSONL/文件/模型请求、强制正文与拒绝、重启和真实界面；证据见 [阶段 4](phase4.md) |

首条 Provider 路由为可验证增量，全部现有 Provider 及 Atlas、Writer/WStyle、AiO、Gamer、平台和扩展继续在主计划的阶段 2–4 迁移。协议夹具只证明对应协议与实际 Rust 执行，真实模型和 OAuth 验收另计。

## crate 职责及接口归属

六个职责保持主计划不变：协议、内核、Context Engine、平台、终端、游戏运行时。首条链使用前五项；Gamer 在契约固定后按独立组件完成，不加入基础桌面内存和启动样本。

| 路径 | 归属及边界 |
|---|---|
| `ReverieCli-rs/crates/protocol` | 共享 DTO、请求/事件/结果、身份、能力和询问；生成前端类型的权威来源 |
| `ReverieCli-rs/crates/core` | 模型路由、会话与配置、Agent、权限、取消、扩展及资源的生命周期 |
| `ReverieCli-rs/crates/context` | 结构/词法索引、查询、修订、证据和预算；通过库接口供内核调用 |
| `ReverieCli-rs/crates/platform` | 工作区文件、进程、命令及后续原生浏览器/Computer Use，保留实际权限边界 |
| `ReverieCli-rs/crates/cli` | `reverie` 原生入口、SDK 适配和滚动终端，共用内核库 |
| `ReverieCli-rs/crates/gamer` | 按需游戏运行时、四作品及完整类型矩阵，按独立组件构建/验收 |

终端及 Electron 共用同一内核行为，区别在传输/显示。请求生命周期携带项目、会话及运行身份；不在等待模型、审批或用户回答时占用其他会话所需的锁。网络、工具和索引取消分别记录是否已经产生副作用。

既有 SDK 声明 [110 项并集及 87 个导出类型](sdk-protocol-baseline-v1.json) 继续逐项迁移及运行验证。第一批按实际需要实现 `hello`、`initialize`、`getState`、`getContextStatus`、会话/模型管理、`listTools`、`runPrompt`、`stopPrompt`、`resolveApproval`、`indexWorkspace` 和 `shutdown`；新增结构化询问走相同身份和生命周期，回答不会代替权限批准。

## 兼容及实现约束

- 最终 Python 分支和源码保持冻结。实际旧数据迁移先一致性备份、再兼容接续与恢复演练；开发验证使用本工作区隔离资料。
- SDK 保持 `reverie.kernel.v1`、`sdk-bridge.v1`、UTF-8 JSONL、既有请求 ID 和流事件。Windows 平台/架构字段对应既有 `win32`/`x64`，Mac 对应 `darwin`/`arm64` 或 `x64`。
- 会话模型与工作区默认配置分别保存；保持当前源码的 `get_page`、`update_metadata` 和 `expected_revision` 行为。未知字段不能因 Rust 反序列化而丢失。
- 默认忽略采用已确认的 Git 标准语义。正式对照的文件与解析工作量分别核对，不把 1,454 扫描条目、1,451 解析文件及 1,449 可词法搜索文件混称。
- 旧 Rust 索引来源 `f029496` 可经审查择用，保留本仓库 MIT 许可及来源记录；改为同进程库接口，不能把旧 worker IPC 的移除当作纯 Python 基线的优化空间。
- 本阶段不需要 ORT。Intel 的 ORT 1.31.0 固定源码、四平台本地模型、INT8 质量及语义 CPU p95 仍是正式交付门槛。
- Rust 正式程序仍须真实验证四档 DPI。Gamer 的独立门槛不拆分产品版本，Live2D 插件可选安装但必须原生 Cubism 渲染。

## 第一条链的依赖事实

2026-11-23 只读查询 Crates.io 官方元数据，以下版本存在、未撤回，声明 MSRV 可由 Rust 1.96.0 覆盖；尚未以本工作区的完整依赖图编译验证。

| 依赖 | 版本 | 许可证 | 声明 MSRV |
|---|---|---|---|
| Tokio | 1.54.1 | MIT | 1.85 |
| tokio-util | 0.7.20 | MIT | 1.85 |
| Reqwest | 0.13.5 | MIT OR Apache-2.0 | 1.85.0 |
| Clap | 4.6.9 | MIT OR Apache-2.0 | 1.85 |

来源：[Tokio](https://crates.io/api/v1/crates/tokio)、[tokio-util](https://crates.io/api/v1/crates/tokio-util)、[Reqwest](https://crates.io/api/v1/crates/reqwest/0.13.5)、[Clap](https://crates.io/api/v1/crates/clap)。Reqwest 0.13.5 的 TLS feature 为 `rustls`，按官方清单选取 JSON、流式和必要协议能力；不能沿用旧版本的 feature 名称。传递依赖、二进制来源和实际使用的许可仍须由锁定构建及完整许可清单核验。

## 后续可并行的实现边界

协议与内核接口固定后，Context Engine、扩展市场及 GUI 可按以下边界并行。此前子代理仅获只读语料标注及交叉复核授权，扩大到实现需维护者明确授权；未获授权时由主代理顺序实施，不把授权问题当作缩减目标的依据。

- Context Engine：限定 `crates/context` 与相应测试，冻结语料/标签只读，不能按失败成绩修改题集。
- 扩展市场：限定内核的扩展/资源管理模块及对应测试，保留统一协议；信任、OAuth、Hooks、校验及原子激活按完整主计划。
- GUI：限定 `ReverieCli-ui` 必需的接入、结构化询问及换行交互，使用 Rust 生成类型，保留视觉体系及现有页面状态。

共享 workspace/锁文件、协议权威、Git 提交、CI 和发布由主代理协调。每个方向必须交付实际构建/运行和失败边界；不改 Python 归档、独立 Engine 或正式发布引用。
