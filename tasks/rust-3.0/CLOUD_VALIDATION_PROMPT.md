# 云端 Agent 验证提示词

你负责 Reverie CLI 3.0.0 Rust 重写的独立验收。本地主会话继续实施 Rust；请检查当前 `main` 的真实状态，不能把计划、旧 Python 成绩、模拟服务或编译成功写成完整产品通过。

仓库：`https://github.com/Lin-Silver/Reverie-Cli`。仅保留 `main` 与 `Reverie-Cli-py` 两个分支，不创建额外分支或 PR，不移动归档分支，不修改版本标签、Release、latest 或 plugins-latest。最终纯 Python 2.5.5 的源码为 `070fa25b07692c90c56a6b00a9a969ff2abb7804`，标签对象为 `c3c160329c2af044ef8e2061266a48df03aca5ee`，Release ID 为 `454958491`。Python 已结束本会话收尾，不重新构建或重发 2.5.5。

先读取仓库的适用指令和 `tasks/rust-3.0/plan.md`、`phase1.md`、`phase0B.md`、`UNVERIFIED.md`、`progress.md`。固定当前 `main` 的提交 SHA、Rust/Cargo 版本、系统、CPU、内存、缓存策略和输入摘要。实施状态以源码和实际运行结果为准；发现尚未实现的功能，列为未实现，不用占位响应验收，也不因缺实现而降低题集或门槛。

按以下顺序工作：

新增四种模型协议的基本检查为 node scripts/verification/rust-provider-smoke.mjs：运行实际 Rust HTTP、文件工具及持久化，不能把测试用不透明签名当成真实模型签名验证。Linux／macOS 运行 PTY 前须用 npm_config_build_from_source=true npm rebuild node-pty --prefix ReverieCli-ui 生成原生验证依赖；这是第三方 node-pty 的构建准备，客户端不依赖该构建时的 Python。原 CI 的缺模块和 posix_spawnp 失败保留，不通过跳过终端用例使其通过。

新增原生命令检查为 `node scripts/verification/rust-command-smoke.mjs`，须运行当前来源的真实 Rust 程序，验证实际 argv、stdin、双路 Unicode、输出上限、权限／审计、取消、超时、正常退出后的后代回收；平台的脚本审查是启发式策略，不能改称系统级沙箱。桌面探针已增加命令进度的单卡片和审批后运行状态，终端探针增加完成前可见输出；应根据 `run.finished` 判断完成，运行中可输入的 composer 不应被当作已结束证据。提交 `5a479f8` 的四平台 CI 现已回读通过，后续命令代码仍须按其实际新来源独立验证。

1. 执行 Rust 锁定构建、测试、格式和 Clippy：`cargo fmt --manifest-path ReverieCli-rs/Cargo.toml --all -- --check`、`cargo test --manifest-path ReverieCli-rs/Cargo.toml --workspace --locked`、`cargo clippy --manifest-path ReverieCli-rs/Cargo.toml --workspace --all-targets --locked -- -D warnings`、`cargo build --manifest-path ReverieCli-rs/Cargo.toml --release --locked`；缺少工作区时明确记录缺失，不能伪造命令成功。
2. 对实际构建的程序运行 `node scripts/verification/rust-smoke.mjs`、`node scripts/verification/rust-session-smoke.mjs`、`node scripts/verification/rust-context-smoke.mjs`、`node scripts/verification/rust-run-smoke.mjs`、`node scripts/verification/rust-tui-smoke.mjs`，以及帮助、版本、`--kernel-info`、`--context-engine` 和 `--sdk-bridge`；先 `npm ci --prefix ReverieCli-ui --ignore-scripts` 准备实际 PTY 和 headless xterm。检查 UTF-8 JSONL、请求 ID、事件到最终响应、实际文件工具、审批和自定义回答、并发项目隔离、取消、EOF 和正常关闭，确认第一方运行进程树不依赖 Python。本地 HTTP 模型夹具只能证明协议及真实 Rust 工具行为，不证明外部真实模型的质量或服务兼容。扩展终端探针设置 `REVERIE_TUI_SPLIT_HOST_MARKERS=1`，核对跨 host write 的边界；本机 ConPTY 已实测失败，不能将正常完整边界通过改称该扩展用例通过。
3. 比对 `sdk-protocol-baseline-v1.json`、`component-protocol-baseline-v1.json` 的全部协议与生命周期；按实际已实现 action 执行配置、独立会话、原文持久化、Provider、流式响应和真实工具链。
   桌面桥接另执行 `npm run build:main --prefix ReverieCli-ui` 和 `node scripts/verification/rust-desktop-bridge-smoke.mjs`；具备 Electron 原生窗口环境时，再执行 `npm run build:kernel --prefix ReverieCli-ui`、`npm run build --prefix ReverieCli-ui` 和 `node scripts/verification/rust-electron-smoke.mjs`。先检查 `npm run check:core-types --prefix ReverieCli-ui`，不可重新生成类型掩盖契约差异。核对三选项加自定义、明确提交、普通询问与权限状态分离、后台会话、原文和中断恢复；基础窗口夹具不等于完整产品或真实模型验收。
4. 运行 `node --test scripts/verification/context-evaluation.node-test.mjs scripts/verification/context-ndcg.node-test.mjs scripts/verification/audit-python-baselines.node-test.mjs`；读取冻结语料与标签摘要，不能修改题干、证据、切块和返回预算以改善分数。
5. 冻结题集共 48 题、四领域各 12，16 basic／32 hard；每题 30 次。每个原生片段评价只计前 72 行，完整原文保留，按完整原文去除完全重复片段后取前 10；预算使用 Python 历史 Unicode 字符数÷4 的向下取整估算 12,000 tokens。证据须完全覆盖且文件、位置、内容版本一致；逐题取 30 次 Recall 均值后宏平均，分领域、范围及波动另报。
6. 基础检索质量不能下降，hard Recall@10 须至少比 Python 的 `0.05260416666666667` 高 `0.10`；nDCG 只观测，required=2、supplementary=1，增益 `2^grade−1`，返回片段与证据一对一、优先 required、同等级增广匹配，理想排名取全部证据降序前 10。
7. 同机、同语料、同输出和持久化合同，冷进程及预热各至少 30 次，测启动、完整索引、基础检索中位数与 nearest-rank p95。必须等实际正文组装和索引提交；缓存返回不算完整重建，分别报告新进程、索引缺失及文件系统缓存。减半的基础检索汇总单位未定，报告逐题和整组 16 题两种分布，不能自行宣布硬门槛通过。
8. Windows 性能参考机为 Ryzen 5 5600X、6 核 12 线程、约 24 GiB；本地 CPU 语义链关闭 GPU、单查询并发、N=16，预热 p95≤2 秒。云端硬件不同时只报告实测和限制，不与该参考机直接判等。
9. 校验 E5／BGE 固定模型、tokenizer、量化和运行时资源的许可与摘要，验证四平台本地 CPU session、离线导入、损坏包和 GPU 失败回退；Intel ORT 1.31.0 固定源码当前取得失败，列为缺失证据，不能替换其他版本后称同版本验收。
10. 执行旧数据一致性备份、兼容接续与实际恢复；执行全模式、市场、通用组件、真实 MCP／OAuth、扩展更新校验／原子激活／失败回退，以及 GUI／TUI 询问与换行等产品流程。
11. 完成 `UNVERIFIED.md` 中环境允许的剩余项目；真实物理 DPI、多屏、真实服务凭据和 Live2D 许可等环境不足时，精确说明缺少什么。云端虚拟屏幕不能证明维护者物理显示器四档系统缩放验收。
12. 在可用原生 runner 上构建并运行 Windows x64、Linux x64、macOS arm64／x64，保存实际程序、摘要、来源与运行证据。不要在 Linux 的交叉编译结果上宣称 Mac／Windows 原生运行通过。

所有输出保存在当前仓库的 `.runtime/cloud-validation/<来源SHA>/`，源码与许可明确的测试资料才能提交；不得提交凭据、真实模型隐私输出、用户会话或大体积构建缓存。本次默认只验收与报告，不修改正在实施的产品源码。发现缺陷时记录实际重现、最小原因与修复建议，交给主会话；若维护者另行授权修复，只触碰直接相关文件，提交并推送 `main`，事先重新核对主会话最新变更，不覆盖并发工作。

最终交付一个自包含报告：实际来源、命令、退出码、通过／失败／未实现／未验证状态、原始证据路径、平台与硬件限制。同步更新 `UNVERIFIED.md`，保持一行一个编号点，只删除有当前来源实际证据证明通过的项目；不得以历史成绩、静态检查或服务替身替代真实验收。
