# 云端 Agent 验证提示词

你负责 Reverie CLI 3.0.0 Rust 重写的独立验收。本地主会话继续实施 Rust；请检查当前 `main` 的真实状态，不能把计划、旧 Python 成绩、模拟服务或编译成功写成完整产品通过。

仓库：`https://github.com/Lin-Silver/Reverie-Cli`。仅保留 `main` 与 `Reverie-Cli-py` 两个分支，不创建额外分支或 PR，不移动归档分支，不修改版本标签、Release、latest 或 plugins-latest。最终纯 Python 2.5.5 的源码为 `070fa25b07692c90c56a6b00a9a969ff2abb7804`，标签对象为 `c3c160329c2af044ef8e2061266a48df03aca5ee`，Release ID 为 `454958491`。Python 已结束本会话收尾，不重新构建或重发 2.5.5。

先读取仓库的适用指令和 `tasks/rust-3.0/plan.md`、`phase1.md`、`phase0B.md`、`UNVERIFIED.md`、`progress.md`。固定当前 `main` 的提交 SHA、Rust/Cargo 版本、系统、CPU、内存、缓存策略和输入摘要。实施状态以源码和实际运行结果为准；发现尚未实现的功能，列为未实现，不用占位响应验收，也不因缺实现而降低题集或门槛。

按以下顺序工作：

新增四种模型协议的基本检查为 node scripts/verification/rust-provider-smoke.mjs：运行实际 Rust HTTP、文件工具及持久化，不能把测试用不透明签名当成真实模型签名验证。Linux／macOS 运行 PTY 前须用 npm_config_build_from_source=true npm rebuild node-pty --prefix ReverieCli-ui 生成原生验证依赖；这是第三方 node-pty 的构建准备，客户端不依赖该构建时的 Python。原 CI 的缺模块和 posix_spawnp 失败保留，不通过跳过终端用例使其通过。

新增原生命令检查为 `node scripts/verification/rust-command-smoke.mjs`，须运行当前来源的真实 Rust 程序，验证实际 argv、stdin、双路 Unicode、输出上限、权限／审计、取消、超时、正常退出后的后代回收；平台的脚本审查是启发式策略，不能改称系统级沙箱。桌面探针已增加命令进度的单卡片和审批后运行状态，终端探针增加完成前可见输出；应根据 `run.finished` 判断完成，运行中可输入的 composer 不应被当作已结束证据。提交 `5a479f8` 和 `9ca0212` 的四平台 Test 现已回读通过，后续代码仍须按其实际新来源独立验证。

Context Engine 的实际检查增加 `--context-engine lookup` 的七种查询和 `rust-run-smoke.mjs` 的显式 `codebase-retrieval`。重点验证父子作用域、歧义／未解析引用、变更源文件与引用目标后拒绝旧证据、schema 2 一致性备份及实际恢复、Windows 深层索引路径、关闭自动索引时的显式查询，以及切换项目后原任务仍使用原执行目录。严格权限只在已配置 `strict_allow_read_only=true` 时豁免读取审批，不能扩大该规则。当前推断解析和文本 task／explore 不等于完整语言服务器、语义、记忆或历史；这些功能须继续按真实实现验证。

增加 `node scripts/verification/rust-parser-smoke.mjs`，检查十种新增原生语法的定义、正文和内容摘要，再扩展全部语言构造、导入／别名、动态接收者与文档／配置矩阵。相同文件 stem 中的同名定义必须保持歧义，不能因集合去重变成唯一目标。解析修订变化必须重建派生分析。`4b1d087` 的四平台 Context Engine 检查通过，但 macOS arm64 的终端取消检查失败：旧探针只等服务端发出数据就取消，未等 Rust 接收。当前探针先核对原生显示与 SQLite 部分文本，再取消并保留原断言；必须以新来源的真实 Mac CI 确认修复，不能把 Windows 通过改称 Mac 通过。`b38e130` 的 Apple Silicon 新语法检查通过，但终端在碎片粘贴阶段提前退出；失败日志保存继续完善，不假定其根因等同前一个取消问题。

执行 `node scripts/verification/rust-resources-smoke.mjs` 和 `cargo test --manifest-path ReverieCli-rs/Cargo.toml -p reverie-context --test resources --locked`。分别核对清单固定身份、模型／tokenizer／runtime／许可文件、实际大小／SHA-256、原生架构及危险路径拒绝；被暂存的目录不能被当作已激活模型。夹具只有格式头和测试字节，不证明 ORT 或推理健康。后续真实包必须取得原始模型及量化过程摘要，并验证加载、更新、回退、卸载和取消。

新增真实模型检查：取得适用平台的固定资源包后执行 `node scripts/verification/rust-semantic-smoke.mjs <actual-executable> <real-bundle> <manifest-sha256>`。Windows 通用 Gather INT8 候选 manifest 为 `f87fd5c838935dfdb5ede89886d9896000aa76a4a9592d9cdb8553abeb3f7d91`，共 449,946,508 字节，已通过本机小语料 7 项；不要将 Windows 包用于其它架构。当前向量近邻是精确余弦堆，资源激活和自动 Agent／GUI／TUI 接入尚未完成。完整 FP32／INT8 质量、预热 N=16 p95、模型更新／旧任务和四平台加载须另外验收。资源生产脚本是外部 Python 工具链，Rust 第一方程序不调用它。`294497d` 的 Test `45232927374` 六个 job 已回读成功，Mac 光标及取消修复有该来源的基本证据，后续代码须按新来源核对。

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
