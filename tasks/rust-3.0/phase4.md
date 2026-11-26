# 阶段 4：扩展生态与共用管理流程

这一阶段承接 [完整 3.0.0 计划](plan.md)，包括四个内置市场、手动来源、Skills、MCP、命令、子代理、Hooks、LSP、配置、公开 Connector 授权和 GUI/TUI。所有内容仍属于 3.0.0；以可运行链路逐项推进，不能把单个增量称为完整扩展生态交付。只在 `main` 开发，Python 归档和版本发布保持冻结。

## 当前实施顺序：市场来源与目录

1. 完成四来源、手动 Git/HTTP/目录、缓存、固定内容身份与分页；以实际 Rust JSONL、Git 和 HTTP 检查验证。
2. 将下载登记为可取消后台任务，保持 SDK、会话及关闭响应；用等待中的 HTTP 请求和并发修改验证。
3. 桌面和滚动终端共用管理接口，保留切页草稿；以实际窗口和 PTY 验证添加、查询、切换和恢复。
4. 核对当前公开来源及对应许可，更新逐行未验证清单和云端提示词，再将已验证增量提交、推送 main。

目录读取不运行来源中的安装命令、不授予插件信任或 Connector 授权。安装、统一组件注册、更新、Hooks 和 OAuth 按完整计划接续实施。

| 工作项 | 交付 | 基本验证 |
| --- | --- | --- |
| 本地与内置 Skills | 发现、同名优先级、YAML、Gamer 包模式限制、搜索、按需正文/引用资源、固定正文强制加载、会话与草稿恢复 | 实际独立 Rust 部署、JSONL、文件原文、完整正文/Unicode 分块、模型 HTTP 请求、无效固定阻止执行、GUI 和 PTY |
| 市场与通用组件 | 四个来源、手动 Git/清单/本地/离线来源、详情、组件与许可、安装和移除 | 固定来源和实际文件、格式及注册契约、明确启用状态；安装不等于信任或授权 |
| MCP 与 Connector | 共用连接/发现/调用、公开 MCP、OAuth/PKCE、凭据存储、刷新和撤销 | 实际 MCP 服务和正常关闭，真实 Connector 授权另计 |
| 插件执行与信任 | 用户授予插件级信任、命令、子代理、Hooks、LSP、配置映射 | 正反权限案例、Hooks 首次确认、同类能力注册、会话隔离和取消 |
| 更新与恢复 | 固定身份、摘要/签名、兼容/路径/权限/依赖/许可/健康检查、原子激活 | 保留旧任务版本、拒绝坏候选、失败回退、重启和并发；按主计划完整矩阵验收 |

## Skills 首增量

资源从最终 Python 主线的内置目录迁入 Rust 资源目录。629 份迁移文件的 Git blob 与来源 `b5168c4f458a8fc913c83ffb23ec77537aebf37e` 完全一致，原 Python `__init__.py` 暂保留为未迁移源码，不参与 Rust 构建。原初暂存时三份 ELAYA 文件被换行规则归一化，已从原提交恢复原始字节；属性规则跟随目录更新，不能仅凭文本 diff 相同宣称字节相同。

CLI 的 Rust 构建脚本生成相邻资源目录与 `reverie-builtin-skills.json`，包括必要正文、引用、脚本和许可；不会启动其中的第三方脚本。桌面及 CI 候选携带相同目录，内置注册来自清单，避免陈旧目录自动成为新增包。完整构建残留清理和依赖分发许可另行验收。

发现沿用 Python 的来源顺序：内置、用户 `.agents/skills`、应用历史目录、工作区祖先到当前目录；同名记录显示遮蔽者，名称解析优先级不变。YAML 多行描述、`agents/openai.yaml` 显式调用策略、Gamer 专用 `reverie-engine`、正文修订及局部文本资源边界均由原生代码处理。模式别名兼容不代表该模式的完整工作流已经完成。

固定项最多四个，属于会话或项目草稿。变更同时写入会话 metadata 与运行配置，并使用修订保护。新会话继承草稿，切换、重启及未解析固定项保持独立。每轮加载完整固定正文和正文摘要，128,000 字符上限沿用 Python 整个强制说明块的口径；加载活动进入流式事件和持久运行记录。未固定项只注入有界描述，由模型按需 inspect；资源读取不执行脚本或扩大工具权限。

SDK 新增原生 `lookupSkill`，并迁移原有 list/refresh/inspect/pin/unpin/clear actions。Rust 协议生成前端 Skill 类型；GUI 目录和 composer 共用状态，刷新绑定发起时的项目与会话，遮蔽行使用实际路径作 React identity。终端支持 `/skills`、`/skill <name>`、pin/use、unpin/remove、search、inspect 和 resource。

新 YAML 依赖 `serde-saphyr 2.2.0`、`granit-parser 2.2.0` 的本地 Cargo manifest 均为 `MIT OR Apache-2.0`，MSRV 分别 1.89 与 1.81.0；已经参与锁定原生构建。ELAYA 和 Emil Kowalski 两个已有上游清单的 25 个固定 SHA-256 与许可文件已核对。完整传递依赖和最终发行 NOTICE 继续保留为发行验收事项。

基本验证命令：

```text
cargo test --manifest-path ReverieCli-rs/Cargo.toml --workspace --locked
cargo clippy --manifest-path ReverieCli-rs/Cargo.toml --workspace --all-targets --locked -- -D warnings
cargo build --manifest-path ReverieCli-rs/Cargo.toml --release --locked
node scripts/verification/rust-skills-smoke.mjs
node scripts/verification/rust-tui-smoke.mjs
node scripts/verification/rust-electron-smoke.mjs
node ReverieCli-ui/scripts/build-kernel.mjs
npm run typecheck --prefix ReverieCli-ui
```

实际命令、最终程序摘要及报告路径记录在 [实施记录](progress.md)。本地协议夹具证明 Rust 工具链路和真实文件处理；不证明外部模型能语义遵循、市场已经实现或四平台全面通过。完整剩余项目保持 [逐行清单](UNVERIFIED.md) 和 [云端验收提示词](CLOUD_VALIDATION_PROMPT.md)。

### 2026-11-26 · 内置 Reverie Motion

隐式技能目录取消总字符数限制。Windows x64 解包版中的 release 内核以 `--sdk-bridge` 连接回环模型。普通提示收到 26 个符合条件的名称及路径，目录共 10,183 字符。添加同名用户和工作区包后，内置记录依然是唯一可隐式调用的胜者。模型通过 `skill_lookup` 读回原始正文、参考文件和受审查的绝对入口。

原包的 30 个文件在来源目录、Git 暂存区和部署资源中逐项核对。Node 从当前工作区调用内置入口，通过 doctor、design、真实 Chrome 156.0.8078.4 预览和 export。八个采样帧、接触表 PNG、减少动态效果检查以及 CSS、WAAPI、TypeScript 声明文件均已读回。严格审批拒绝无写入，会话授权覆盖后续导出，显式只读在启动前拒绝命令。命令日志记录了各阶段和拒绝事件。

同一开发工作区通过 149 项 Rust 测试，3 项标记为 ignored 的原生夹具分别由对应 smoke 驱动；现有 28 个 Rust smoke 入口在本机全部通过。独立核对仅包含此次 Skills 提交的内核与平台库，18 项库测试通过。开发工作区还含上一轮 Rust 3.0 功能，以上 Windows 实包结果不代表单独提交的跨平台发行验收。复验已安装的内核可运行 `node scripts/verification/rust-skills-smoke.mjs <reverie程序> <临时验收目录> --installed`。公开模型自主选择和签名安装器另行验证。
