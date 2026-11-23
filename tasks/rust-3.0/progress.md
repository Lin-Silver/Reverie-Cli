# Reverie CLI 3.0.0 实施记录

本任务执行用户确认的 [完整计划](plan.md)。计划原文中的“当前状态”是接受计划时的快照；后续实施状态以本文件及验收证据为准。保留全部范围、门槛与许可约束，不覆盖 `tasks/python-2.5.5-closeout/` 的历史记录。

## 当前交接状态（2026-11-23 UTC）

最终纯 Python 2.5.5 已公开并完整归档：来源 `070fa25b07692c90c56a6b00a9a969ff2abb7804`，树 `b7835e45d0cea95e9e5b0790d24b7604c7681002`，正式 Release `454958491`，17 项资产。Python 剩余真实 DPI 验收获维护者明确延后，保持未验证；Rust 四档真实 DPI 门槛保留。最终来源、实包和公开源码核对见 [Python 基线](python-baseline.md)。

已从同一来源建立 `codex/rust-3.0` 隔离工作区并附加到本会话。托管创建在 Git 过滤器发现时超时，原生 Git 创建成功；未改动既有 checkout 的未跟踪收尾资料。G 盘仅约 118 MiB 可用，开发工作区与后续构建、语料、缓存均置于本会话的 C 盘工作区。此时尚未创建 `ReverieCli-rs` 的实现。

当前顺序：冻结正式协议与独立语料并验证原始字节；测量最终 Python 冷/热各至少30次的性能、归因和轻量基线；据证据推进 Rust 首条完整运行链。两组独立复核已全部通过并冻结48题、130 required和23 supplementary；源码API索引诊断冷/热各30次完成，正式评分、发行包性能及轻量基线仍待完成。评价预算固定为Python字符数÷4的12,000估算tokens、72行、完整覆盖和逐题宏平均。ORT 1.31.0 的三平台官方包来源及 Windows API 24 已核验，Intel 同版本源码构建路线已确认但固定源码暂未取得。详见 [阶段0B](phase0B.md)。每一步只在对应检查通过后记录完成。

## 接手快照（2026-11-22）

- main / 本地 HEAD：`f029496d19138176b857bedb54f7eeb225973471`。
- 来源树：`98316a5246dc4b64ed0f016637f6ef91fd5a6172`。
- 远端：`https://github.com/Lin-Silver/Reverie-Cli.git`；远端身份在每次交付前复核。
- 接手时没有受 Git 管理的改动；`tasks/python-2.5.5-closeout/` 为已有未跟踪资料，保留。
- 当前 Context Engine 自动选择 Rust 辅助后端；纯 Python 恢复尚未实施。
- `ReverieCli-rs` 尚不存在；Rust 实施须等待阶段 P 验收完成。
- G 盘剩余 `3698601984` 字节；大型构建前先收整经过核实的可再生输出。

## 顺序与完成检查

| 阶段 | 状态 | 完成检查 |
|---|---|---|
| P1 工程收整 | 九份远端源码归档已复核；Git 仅登记主 checkout，其他可再生残留交由用户手动清理 | 来源/私有数据/证据分开记录；独有 worktree 源码先归档并验证远端；本会话不再自行删除用户接手的残留 |
| P2 纯 Python Context Engine | 最终 `070fa25` 实际 EXE 的 CLI/SDK/Context Engine 6项、旧库备份恢复9项、历史忽略兼容11项通过；第一方 Context Engine 为 Python / in-process | 原始证据与实际程序摘要对应；历史实现和旧失败保留 |
| P3 Python 重验与重发 | 最终 Test、四平台 native Build及17项实际下载核对通过；稳定草稿已公开；完整 Python 归档同源；真实 DPI 按维护者明确决定延后并保持未验证 | 源码/标签/资产/内核身份一致；公开说明披露原失败、零真实模型质量样本及未验证边界 |
| 0A 只读整理 | 候选快照清单与语料草案已整理；未冻结正式基线 | SDK/类型/语料草案与来源 SHA 对应，详见 [阶段 0A](phase0A.md) |
| 0B 正式基线 | 已固定纯 Python 发行身份和评价预算；48题独立候选交叉复核中；源级索引试跑完成但正式样本未完成 | 冷/热各至少30样本、耗时分解、质量及轻量基线；候选字节、复核及冻结分别核对 |
| 1 Rust 首条链路 | 分支与隔离工作区就绪，功能待实施 | 同一 Rust 内核驱动 CLI、SDK、桌面及真实 Provider/工具/会话 |
| 2 Context Engine | 待实施 | 完整结构/基础/本地语义链与性能质量门槛 |
| 3 模式与平台 | 待实施 | 全模式与实际平台工作流 |
| 4 生态与界面 | 待实施 | 四市场/通用组件/真实 OAuth/更新/GUI/TUI/询问与换行 |
| 独立组件 | 待实施 | Gamer 四作品/类型矩阵/导出与 Live2D 原生渲染/许可 |
| 5 核心候选 | 待前序实现及验收 | 四平台实际包、DPI、完整性能门槛、连续7200秒四路 AiO |
| 6 主线发布 | 待候选验收 | 验收 SHA、main/tag、实际资产对应 |
| 7 完整产品 | 待全部组件验收 | 全部必需独立组件验收通过 |

## 阶段 P 增量记录

### P2-1：Python 存储基础

新增尚未接入产品入口的 Python SQLite catalog、可移植 FTS 写入与查询、事务和修订检查。保持原解析器与文本处理算法；不启动 Rust 或子进程。当前产品入口仍为历史混合实现。

验证：Python 3.10.11 / SQLite 3.40.1，`build/venv/Scripts/python.exe -m pytest tests/test_python_context_catalog.py -q`。实际数据库用例覆盖增量替换/删除、符号检索、词频、包含中文及 `#/%` 的数据库路径、字面 `%/_` 路径前缀、失败回滚、并发读写及过期修订、不同工作区和无关 SQLite 数据保护。首次收集失败及修复过程保留于工具记录；通过结果为 4 个用例，尚未执行整体产品验收。

收整：经路径、Git 与 reparse point 核对后清理 `ReverieCli-py/build/pip-cache`（逻辑大小 80991899 字节）。批量删除与 `build/temp` 的递归删除被自动审批拒绝，仅返回 `blocked by policy`；这些目标与其余缓存保留，未通过另一种执行方式绕过。详细调查记录在 `.runtime/rust-3.0/cleanup-approved-build-targets.json`。

### P2-2：Python 产品入口与数据接续

CLI、SDK、桌面索引工厂统一采用 Python `PersistentCodebaseIndexer`。`--context-engine` 的 index/search/chunks/paths/status/serve/help/version 完整实现，JSONL 服务沿用协议 1。新增独立数据库 `python-search.sqlite3` 与按修订分开的 `python-snapshots`；无索引更新时保持修订和快照不变。旧 Rust 数据库先通过 SQLite backup API 一致性备份、完整性检查和摘要核对，保留原数据库及快照，重建 Python 派生索引。

定向回归：`.runtime/rust-3.0/context-regression-2.log`，89 通过 / 0 失败，22.36 秒。覆盖新 Python 合同、实际 CLI/JSONL 服务、Windows 超过 MAX_PATH 的中文及 `#/%` 数据库路径、备份恢复、原有 Context Engine reliability/upgrades、记忆索引原子性。第一轮 2 项中文状态输出失败已修复；第一轮日志保留。

真实历史探针：原 Rust 二进制生成 `.runtime/rust-3.0/legacy-backup-probe/native-search.sqlite3`，Python 完成一致性备份并在旁边生成 `.python.sqlite3`；实际 `--context-engine index` 和 `chunks ... validateInvoice` 返回 Python 后端与正确位置。此探针只证明索引迁移链路，不替代完整四平台及 DPI 验收。

候选分支为 `codex/python-2.5.5-pure`；本任务自己的两个未发布增量提交已移到候选分支，本地 main 恢复到接手来源。远端 main / 正式标签尚未变更。

正常 `cargo clean --manifest-path ReverieCli-py/native/context-engine/Cargo.toml` 已移除 1503 个编译缓存文件（Cargo 报告 799.3 MiB），历史 Rust 二进制仍在原 build 目录用于对照，不进入新打包清单。随后 G 盘可用 4449320960 字节；该值是即时余量，不是承诺可回收空间。

## 证据规则

### P2-3：撤去 Rust 发行接入与候选发布守卫

撤去 Python 子项目内的历史 Rust crate、Rust 准备脚本及 PyInstaller 二进制接入；代码留在原混合版来源提交中。新内核握手记录显式声明 Context Engine 为 Python/in-process；包验证同时检查独立版本输出、SDK 后端、落盘数据库及实际符号检索。

CI 为 Python 候选及未来 Rust 开发分支提供只读测试/构建；核心手动发布限 main，版本标签另验格式、版本和 main 来源关系。插件构建与发布分开；写权限仅给发布 job，开发分支无法更新 `latest`、`plugins-latest` 或正式资产。当前 5 个 workflow 已解析；真实 GitHub 作业尚待本次候选推送验证。

### P1-1：固定 Blender SDK 输入

构建器保留既有 `--archive` 输入与内嵌 SDK 行为，新增默认构建缓存下载。固定 Blender 5.1.1 官方 HTTPS 来源、414370237 字节及 SHA-256；先验证独立候选文件再切换，坏文件不覆盖现有归档。

`.runtime/rust-3.0/sdk-download-2.log`：5 个本地 HTTP 真实传输/文件用例通过，3.27 秒，覆盖完整下载、坏摘要、截断、错误大小及已有坏文件保留。首轮因本机代理未绕过回环地址而失败；修正的是测试环境 NO_PROXY，并收紧负例断言，未改变产品代理设置。官方现有 SDK ZIP 已重新核对完整大小和摘要，ZIP 内 170 项许可/版权路径保留。尚未据此宣称新插件实际编译完成。

测试、构建、运行与发布结果分别记录命令、来源 SHA/工作区状态、退出码、时间及证据位置。旧混合版本结果只作历史事实，不作为新纯 Python 或 Rust 实现的验收。没有取得证据的项目保持待验收；不得降低门槛。

大型临时输出与私有证据放在 `.runtime/rust-3.0/`；公开记录经脱敏后才提交。只读核对不运行真实模型、不操作前台，也不修改独立 Reverie Engine 项目。

### P3-1：恢复执行状态与发布守卫验证（2026-11-22）

恢复候选来源 `33295d68fdc4e95b2ff87c436f85ac3d4a9652bf`。本机完整回归为 3626 通过、8 跳过、1 失败，1117.26 秒；起止来源一致，失败为旧 CI 条件字符串断言。GitHub Test `45018667767` 的六个 Python/coverage 作业同一断言失败，桌面和文档作业通过。保留 `.runtime/rust-3.0/python-full-1.log`、起止身份文件及 `ci-test-33295d-failed.log`，不将该轮记为通过。

该来源 Build `45018667820` 四平台构建与原生验收作业均为 success，发布 job 为 skipped；Plugin Build `45018667769` 为 success。完整候选资产尚未下载复核，真实单屏 DPI 尚未执行；这些作业状态不能替代实际包的独立复核。远端 main 仍为原混合版 `f029496`，正式 `v2.5.5` 标签对象仍为 `6b941a075204df72a449ab906157fd4229725601`。

旧断言改为核对带 main 限制的完整手动发布条件，并新增实际 job 条件的事件矩阵测试。覆盖 Rust/Python 开发分支、Python 归档分支、PR、主线手动发布、正式与历史/滚动标签，另核对写权限归属、版本格式/一致性及主线来源检查。没有放宽发布条件。

验证：`build/venv/Scripts/python.exe -m pytest tests/test_non_game_completion.py tests/test_release_publication.py -q`，29 通过、7.66 秒；JUnit 为 `.runtime/rust-3.0/release-guard-regression-1.xml`。桌面已有本机结果为 527 通过/1 跳过，类型与翻译检查、renderer/Electron 构建通过，仅对应 `33295d6` 的源码。

下一步按依赖推进：复核九个远端 worktree 源码归档并保全私有文件；完成新候选全量回归与四平台资产复核；运行四档真实单屏 DPI；保留原混合版身份和资产后重发纯 Python 2.5.5。上述必要前置全部通过后才建立 Rust 实现工作区。Rust 3.0 功能范围和验收门槛保持完整计划。

### P1-2 / P3-2：接续归档与完整发行清单（2026-11-22）

接续候选来源 `8f09fc8f42a7eccbfa2d57b410685fc12a2239fc`。GitHub 分支清单已核实九个 `codex/archive-pre-rust/` 归档存在；七个受管理 worktree 和 `py255-src` 的移除及私有文件保全记录分别在 `.runtime/rust-3.0/archive-completed-managed.json`、`archive-completed-unmanaged.json`。仅 `.runtime/ce-verify` 仍注册于 Git，原工作区的既有未跟踪 Python 收尾资料继续保留。

`ce-verify` 的三个共享 junction 指向主工作区的 `ReverieCli-py/build/bundle_resources`、`ReverieCli-ui/.cache`、`ReverieCli-ui/node_modules`。归档脚本在发现链接时停止，尚未改动 checkout；只移除链接节点的 PowerShell 操作又被自动审批拒绝，仅返回 `blocked by policy`。该 checkout、链接和共享目标全部保留，不以另一种方式绕过拒绝。源码归档已成立，清理验收仍为部分完成。

未提交候选新增完整发行资产清单生成器：核对十个实际程序、四个内核记录、聚合记录的来源、版本、平台、架构、大小、SHA-256 和 Python/in-process 声明，生成完整清单及 `SHA256SUMS`。发布 job 上传共 17 项资产，纠正两处仍称 Rust 后端的错误诊断。文档区分原混合版历史结果和纯 Python 重发合同。

已有 `.runtime/rust-3.0/release-metadata-regression-1.xml` 记录为 50 项通过、零失败/跳过，19.557 秒，对应上述未提交候选内容。模拟发布测试证明的是守卫与上传次序，尚未替代真实四平台程序、独立下载和 DPI 验收。完整候选提交、全量回归与实际资产验证继续执行；正式标签、main 和 Rust 实现仍未变更。

发行清单及上述记录已提交并推送候选分支 `d34818c`。用户随后确认稳定版采用“CI 生成草稿，最终验收后公开”：版本标签 CI 不公开稳定资产，也不把它标为 Latest；最终独立下载和真实 DPI 必须对应草稿里的实际程序。先更新发布行为测试，旧脚本得到 4 失败 / 1 通过的预期红灯（`.runtime/rust-3.0/stable-draft-red-1.xml`），再修复稳定版创建、更新和完成步骤为草稿；滚动预发布策略保留。该调整尚待定向与完整验证，不提前更新正式标签。

定向验证 `tests/test_release_publication_workflow.py tests/test_release_publication.py tests/test_release_manifest.py tests/test_non_game_completion.py` 为 56 通过、零失败/跳过，27.66 秒（`.runtime/rust-3.0/stable-draft-green-1.xml`）。真实执行工作流中的 Bash 并记录 stub 调用，证明已有/新建稳定 Release 在上传前就是草稿，缺 ID/上传失败不公开，成功后完整 17 项仍为草稿。文档检查为 39 文档、195 链接、零错误；不据此替代真实 GitHub 稳定草稿及包验收。

### P1-3 / 0A-1：当前收整与只读草案（2026-11-22）

本轮重新核对九个 `codex/archive-pre-rust/` 远端分支，均存在于 GitHub。`git worktree list --porcelain` 仅登记 `G:/Reverie/Reverie-Cli`；先前受阻的 `ce-verify` 不再是登记中的 checkout。用户接手可再生残留的手动清理，本会话不再自行删除。已提供的四个旧 pytest 目录及 junction 清单在 `.runtime/rust-3.0/manual-cleanup-current.json`；约 4.42 GiB 为逻辑大小，不承诺可回收空间。

阶段 0A 从固定候选 `5725d076999a64a13f3d80b4235dc2d39b122022` 做 AST 和声明清点：Python 分派 109、桌面请求/响应各 102、动作并集 110、TypeScript 导出类型 87。`releaseView` 在 Electron 宿主实现，其余静态差异须继续核对调用与运行合同。组件清单包括 14 个 Python 文件和 41 个类；Gamer 23 类型乘三维度形成 69 行适用性草案；公开语料与查询各 26 条。完整结果及事实/未知边界在 [阶段 0A](phase0A.md)，不把草案当作功能迁移或质量验收。

用户确认 Recall@10 按证据片段评价，已写入完整计划。位置、内容版本、最小相关范围、预算、去重及独立难例由阶段 0B 正式冻结；当前草案全部标记 `formal_baseline_frozen: false`，没有提前计算成绩。FastEmbed 等依赖只核对固定来源元数据和许可证，没有安装 Rust 工作区或运行本地模型。

### P3-3：修复前候选的完整回归与原生记录

来源 `5725d07` 的本机完整 Python 回归为 **3658 通过、8 跳过、45 警告，1019.92 秒**，起止 SHA 一致，退出码 0。证据为 `.runtime/rust-3.0/python-full-2.log`、`.xml` 和起止身份文件。跳过的三项本机 Electron/display 生命周期、两项真实独立 Engine 配对、三项 symlink 权限用例保持未验证。

GitHub Test `45025265450` 为 success。Build `45025265425` 第二次运行的四个平台作业均为 success，`Publish core release` 为 skipped。首轮 Intel 原生 P4 就绪 p95 为 **1223.598 ms**，超过 1000 ms；同 SHA 重跑为 **389.922 ms**，输入 p95 为 85.5 ms。两轮桌面程序 SHA-256 相同，但没有足够证据确定首轮延迟根因；保留失败，不把重跑通过表述为已修复延迟。

Intel 第二轮证据按不可变 artifact ID `14757628612` 下载，9564325 字节、SHA-256 和 ZIP CRC 均通过，位于 `.runtime/rust-3.0/candidate-5725/intel-native-14757628612/`。首轮失败证据和包身份另行保留。同名 artifact 跨 attempt 存在，不能只按名称混合下载。

Windows artifact ID `14756320495` 已完成续传：**1101056577 字节**，SHA-256 `728843672c6f5ac70a1d0a4c5bcaffec670dce6e7046123f3f8ade48f3746f5d`，ZIP CRC 通过，四项资产逐项计算摘要。独立执行下载得到的 `reverie.exe`，握手与内核记录一致，版本为 2.5.5，声明 Python/in-process。原始记录在 `.runtime/rust-3.0/candidate-5725/windows-retry2/`。完整四平台资产下载复核仍未完成。

### P2-4：JSONL 请求与事务合同修复

修复提交为 `7354f70215a9dd8b13c860085d52a8a489f33935`。先在专用数据库以相同请求对照历史 Rust worker 和当前 Python 服务，实际确认：Python 接受 `replace: "false"`，随后 commit 会清空已提交索引；布尔值修订号也被接受；非法 JSON、非法 begin 或失败的读请求会撤销合法的未提交更新。对照报告在 `.runtime/rust-3.0/serve-contract-before/report.json`。

上述字符串替换缺陷又在实际下载的 Windows 程序复现，程序 SHA-256 为 `512e99e86acfad70f064e7e7b0d8cdb8f116a1631a6352653704c855fdb3db7a`，证据在 `candidate-5725/windows-retry2/local-check/report.json`。因此 `5725d07` 不满足最终服务合同，不能重发或充当正式纯 Python 性能基线。

修复只涉及服务边界及必要验证：在调用 Catalog 前验证请求、布尔值、整数范围、文档/片段、扫描选项和查询类型，拒绝重复字段、非有限数字及畸形 JSON。解析失败和失败的读请求保留正在进行的合法更新；实际写操作失败仍由 Catalog 回滚整个更新。没有修改索引后端选择、上层检索算法或 Rust 实现。

先增加真实 JSONL 子进程回归，旧实现得到 **24 失败、4 通过**（`serve-contract-red.log` / `.xml`）。修复后的最后定向运行为 **59 通过，57.66 秒**（`serve-contract-green-3.log` / `.xml`），含拒绝替换、修订类型、保留事务、重新打开数据库、真实写失败回滚、合法检索/片段/词频/路径/扫描和重命名合同。源码 console launcher 的 CLI、SDK、索引及新增实包验证流程也实际运行通过，报告在 `source-service-smoke-2.log`；该运行使用 Python 环境入口，不冒充冻结发行程序。

`smoke_context_engine.py` 已加入服务负例和 pending 更新提交后的实际检索检查，四平台新包构建须执行这些断言。新候选必须重新完成全量回归、真实构建、独立包复核与 DPI；不得把上面的旧候选成绩转写为新候选通过。

### 尚未满足的前置

真实单屏 100%、125%、150%、200% DPI 仍未执行。用户暂时无法保持“设置 → 系统 → 显示”前台，等待恢复；没有更改系统缩放，也没有用显示清单、模拟公式或字体缩放替代实际命中验收。最终验收必须对应稳定草稿最终上传程序。

远端 main 和正式 `v2.5.5` peeled 来源仍为 `f029496d19138176b857bedb54f7eeb225973471`，标签对象仍为 `6b941a075204df72a449ab906157fd4229725601`。本轮只准备候选，不公开稳定 Release，不移动 Python 主线，不创建 `ReverieCli-rs`。阶段 P 完成后再建立 Python 归档分支、冻结阶段 0B 和开始 Rust 实施。整个 3.0.0 的范围继续保留完整计划。

### P3-4：修复后候选的全量、CI 与独立资产核对（2026-11-22）

当前候选来源为 `34e4dcd572ec6aa086ba3cec78cc45856b4df04b`，本地与远端候选分支一致。本机完整 Python 回归为 **3693 通过、8 跳过、45 警告，971.16 秒**；执行起止 SHA 一致，退出码 0，证据为 `.runtime/rust-3.0/python-full-3.log`、JUnit 及起止身份文件。原有跳过不改称通过。

GitHub Test `45035299724` 的八个作业和 Build `45035299684` 的四个平台作业均为 success；候选分支 `Publish core release` 为 skipped。四个平台的原生证据按不可变 artifact ID 下载并校验全 ZIP/成员字节、SHA-256 和 CRC。每平台五个原生阶段及 31 项 P4 检查通过；就绪 p95 为 Windows 382.472 ms、Linux 261.920 ms、macOS arm64 489.277 ms、macOS x64 367.515 ms。证据汇总为 `candidate-34e4dcd/native-summary.json`。这些是实际安装包配合受控回环夹具的结果，真实模型样本数为 0，不证明物理 DPI 或 Rust 性能门槛。

实际 Windows 构建日志中的已安装内核声明 Python/in-process；`smoke_context_engine.py` 对新包验证非法替换被拒绝、合法待提交更新成功提交及 revision=2。两个 macOS 程序资产包全部字节、SHA-256、CRC、平台/架构和内核记录均已独立核对；对应 artifact ID 为 `14759163678`（arm64）和 `14759143904`（x64）。没有在 Windows 上冒称运行 macOS 程序。

Linux artifact `14760235638` 首轮在已收到 968884224 字节时遇到 GitHub TLS EOF，退出码 1；失败完整记录保存在其 `stream-original-failure.log`。未生成完整校验结果，使用当前已补重试的传输工具重新验证，不能按部分传输宣称通过。

Windows artifact `14760101770` 在 G 盘容量不足时仅停止经 PID、父进程、创建时间及命令核实的本任务传输进程，保留所有 `.part` 文件和日志；记录为其 `stopped-for-space.json`。这轮未完成全 ZIP 校验。源码及原始证据不移动，新的可续传 Windows ZIP 和验证资产存于本会话已授权的 C 盘工作目录；准确路径记在 `candidate-34e4dcd/windows-task-storage.json`。该存储例外由 G 盘实际不足触发，没有删除用户接手清理的缓存或用户数据。

源代码复核确认 CLI 与 SDK/桌面使用同一 Python 索引工厂；Python 子项目已无受管理的历史 Context Engine Rust crate。原混合版仍由 main、原提交和正式标签保存。受 Git 管理的桌面 build 目录仅保留六个启动器、安装和卸载脚本；运行缓存与发行产物未进入候选源码提交。

本节的独立资产验证完成后仍须核对 Windows 下载程序的实际 CLI/SDK/服务行为、最终稳定草稿资产和同一程序的四档真实单屏 DPI。稳定版公开、Python 正式归档、阶段 0B 与 Rust 实施继续等待这些前置，完整 3.0 范围不缩减。

Linux 重试最终完整校验 1062301973 字节，SHA-256 为 `62f8dafbc333279cc43f2ffc9bda5658da6757ce2c64fb4862c52aac9a4a54fc`，全部成员 CRC、资产及内核身份通过。Windows 在本会话 C 盘工作目录完成可续传 ZIP 下载，首轮 HTTP 中断保留 1006632960 字节，第二轮完成 1101068746 字节；完整 SHA-256 为 `9462816cf26ba7a4aa4d70afdaec5a9e400f0e9fd3d8af9e4c7c979dd3a18e1b`。四个实际文件与独立下载的原生验证 provenance 摘要完全相同。

下载得到的 Windows `reverie.exe` 为 271994348 字节，SHA-256 为 `cf4e88479b635f88debbd3dccda2dbd777f03a8b9c0219bb7bc54c911f5ba677`，PE machine=x64。清除测试环境 PATH 中的 Python/venv 目录和外部 Python 配置，使用独立应用数据及临时目录实际执行版本、内核握手、SDK ready/shutdown、持久索引/符号检索和 JSONL 服务合同，全部通过；程序运行后摘要未变。报告位置记在 C 盘 depot 的 `local-check/report.json`。这是实际冻结程序运行，不是源码 console launcher 或模拟后端。

`.runtime/rust-3.0/verify-candidate-set.py` 将四个平台的全部 14 项候选文件（十个程序、四个内核记录）逐项绑定原生实包测试的摘要，资产集合、来源、版本、系统、架构、大小及 SHA-256 均一致；总字节 3844806239，结果为 `candidate-34e4dcd/candidate-assets-verified.json`。正式稳定草稿的三个聚合元数据仍须由最终 CI 产生并独立核对，不把 14 项候选检查改称 17 项正式草稿已通过。

GitHub 连接器读取的索引工厂、JSONL CLI 与发布 workflow，Git blob 分别为 `71cb2be9febddb7e2f002162e63372cf3b4edf8f`、`a25b36adb203adb70358a7fd6e32ed1dad8c62e4`、`d7b5998c20a5644661bcb981ed0ebe43c0ac6719`，与本地候选完全相同。阶段 0A 原有六个协议来源也逐个核实 blob 未变，并补充了生命周期及真实 DPI 待验证点；没有扩充实现或计算成绩。

已再次请求用户恢复“设置 → 系统 → 显示”前台，以完成实际四档 DPI；在取得可用环境前不执行缩放或输入。当前仅本任务计划记录有本地修改，候选代码 SHA、远端 main、正式标签和 Release 未改变；没有残留的本任务资产传输或 CLI 验证进程。

### P2-5：实际历史数据库恢复与增量合同补充（2026-11-22）

继续使用下载得到的 Windows 候选 `34e4dcd`，EXE SHA-256 为 `cf4e88479b635f88debbd3dccda2dbd777f03a8b9c0219bb7bc54c911f5ba677`。验证脚本及报告位于此前已授权的 C 盘候选工作目录，准确位置仍由 `candidate-34e4dcd/windows-task-storage.json` 指定；没有改动产品源码或 G 盘原探针。

原探针数据库为历史实际 Rust worker 生成的 RVCE/schema=1/revision=1。用 SQLite 只读一致性备份建立测试副本，新 EXE 先拒绝直接读取未重建的旧索引，再自动备份并重建独立 Python 派生索引。新程序的路径/符号检索通过，备份清单、大小、哈希、原 revision 和工作区身份一致。恢复出的备份由历史 Rust EXE 实际执行状态、内容及符号检索通过；故意损坏的测试备份被新 EXE 拒绝，原旧数据库及已有 Python 派生索引未改变。

增量实包检查覆盖无变更、重命名、内容/符号替换、删除、Git 忽略及重新纳入、Reverie 文件级忽略。`continuation-check-1/report.json` 保存 24 次实际 CLI 调用；最后一项目录级忽略断言失败，记录保持 `passed=false`。随后 `explicit-ignore-check-1/report.json` 的六项独立检查通过：明确新增文件级忽略后，旧路径和符号移除，再次无变更刷新不增加 revision。没有修改原失败结果或把它计为通过。

目录差异已用 Git `check-ignore --no-index -v`、当前 pathspec 和原混合版源码直接核实：先 `!目录/keep.py`，再忽略整个目录时，当前引擎仍重新纳入 keep.py，Git 则忽略它。原版与当前候选的四个相关方法 AST 完全相同，既有测试允许被忽略目录内的指定文件重新纳入。它是既有合同差异，尚未改变实现。已询问用户选择 2.5.5 保留兼容并在 3.0 明确规则，或现在统一 Git 规则并重建/重验四平台。

原 G 盘数据库、WAL 和探针源码的前后 SHA-256 一致；旧库备份恢复和实际检索已取得证据。本次实际旧库没有 native-snapshots，原快照组合的测试仍只具有既有测试夹具证据，不能改称真实历史快照全部恢复通过。

### P3-5：完整原版保全与发布恢复次序（2026-11-22）

原混合版 Release `454302327` 的全部 17 项资产已保存到 C 盘 `original-mixed-2.5.5/assets`，总字节 **3869554236**。逐项核对不可变资产 ID、名称、大小、GitHub digest 与实际 SHA-256，并核对原发行清单和 `SHA256SUMS`；完整记录为 `original-mixed-2.5.5/assets-preserved.json`。七项元数据复用此前独立下载的文件并再次核对字节，其余十项程序实际下载。原 Release 前后身份及资产集合一致，未修改或公开新候选。

原源码 ZIP 为 22884299 字节，SHA-256 `410121acac5c2413e707138ecfbda08dc327a7a1f90ca00cb989e1252e9bd8f1`；1933 项归档条目、全部 CRC、ZIP 内提交注释及 Git 源码树一致。原注释标签内容按 Git 对象算法复核，仍为 `6b941a075204df72a449ab906157fd4229725601`。

历史引用 `history/python-2.5.5-mixed-f029496` 已推送并回读，保留原注释标签对象本身，解引用到原混合版 `f029496`。当前五个 workflow 的事件规则全部核对，该历史标签不会触发它们。远端 main、正式 `v2.5.5` 和原 Release 仍保持原版身份。历史引用及工作流结果保存在 `historical-tag-preserved.json`；历史 Release 的归档尚未执行。

新增 [发布转换与恢复次序](release-transition.md)，落实保全、历史 Release、正常 main 推进、单标签 lease、最终稳定草稿、独立资产/DPI 核对及公开次序。新文档所在目录被现有 `*.0` 规则忽略，后续只将本任务必要文档显式纳入提交，不改写其他会话资料。

Computer Use 和 CUA 的当前原生清单均只返回两个可操作窗口，没有显示设置。通过已存在的 `SystemSettings.exe` 尝试启动，返回 `launched app did not expose a targetable window`；刷新选择与另一原生入口仍未取得设置窗口。没有改变缩放、发送键鼠输入或以模拟替代 DPI。真实 DPI 和忽略规则处理决定仍待取得；最终 17 项稳定草稿、正式重发、Python 正式归档及 Rust 开工继续等待必需前置。

接续按用户已确认的草稿顺序继续独立准备最终来源和 17 项 CI 草稿。新文档提交将产生新的候选 SHA，因此旧 `34e4dcd` 的清单和实包结果继续以其原身份保存；最终来源重新执行 CI 和程序/元数据核对。文档与现有兼容实现的准备不预先决定新忽略规则；公开和 Rust 开工仍等待合同决定及真实 DPI。

### P3-6：历史 Release 归档、纯 Python 主线与最终 Intel 失败（2026-11-22）

候选 `20ac69e249fafafc4c133d6167fb5270cf0b2234` 的 Test `45050302674` 八个作业通过、Build `45050302665` 四平台通过、插件构建 `45052929908` 通过；候选发布 job 均跳过。独立下载的四平台 14 项文件共 3844796759 字节，逐项核对来源、大小、摘要和原生 provenance，通过记录为 C 盘任务目录 `candidate-20ac69e/candidate-assets-verified.json`。它仍是开发候选的证据。

按已批准的恢复次序，原混合版 Release `454302327` 已改挂历史引用 `history/python-2.5.5-mixed-f029496`，保留全部 17 项原资产及资产 ID、摘要；历史注释标签对象仍为 `6b941a075204df72a449ab906157fd4229725601`。`main` 正常推进到 `20ac69e`，没有强推主线；通过旧对象 lease 将 `v2.5.5` 指向纯 Python 来源，新注释对象为 `6d2ec4307bcfad94a6629f3d8324583e38f9630b`。`latest` 和 `plugins-latest` 未更新；推进 main 时临时关闭的插件 workflow 已恢复 active。所有操作与回读证据保存在 C 盘任务目录的 `release-transition-preflight.json`、`original-release-archived-response.json`、`main-prepared.json` 和 `pure-python-tag-prepared.json`。

主线 Test `45054318320` 八作业通过。主线重复 Build `45054318185` 主动取消，不能计为通过。最终标签 Build `45054438430` 的 Windows、Linux、macOS arm64 成功，Intel 作业 `137306447990` 在实际安装包 P4 检查失败，publish 跳过；新 `v2.5.5` 稳定 Release/草稿尚不存在。

Intel 原始 P4 仅 `local-input-p95-under-100ms` 失败：60 次样本 p50=81.6 ms、p95=101.4 ms、max=122.7 ms；同一已安装失败包的诊断复测 p95=104.8 ms，再次失败。两份追踪分别为 33775 和 32207 个事件，主线程样式计算与 Layout 各 60 次，原追踪 Layout p95=38.121 ms、UpdateLayoutTree p95=26.212 ms、input EventDispatch p95=18.377 ms。追踪耗时包含重叠，不能相加冒充关键路径。此前同来源开发候选 p95=65.8 ms；数据尚不能确定差异是诊断追踪、宿主变化还是产品缺陷。

失败的 Intel DMG 为 497458464 字节、SHA-256 `42c8ed72dfb3b6a22bfc79c4d2fc01219f77a64e4b79afb726ecfef524ea168d`，CLI 为 367207424 字节、SHA-256 `4325403c8b5f206b6b0bd2e78eaf7cc18b27143cd02886f6d2f0a205071aedcf`；两者及内核记录均核对原失败 artifact `14767014245` 的 provenance。完整日志、原始报告和追踪存于 C 盘任务目录 `final-draft-v2.5.5-20ac69e/`，分析摘要为 `intel-input-trace-summary.json`，原报告没有改写。

为在同一实际失败 DMG 上区分追踪开销，扩展 `recheck-riu-macos.yml` 支持已完成的原生验证与 core-release 失败资产；下载前限定来源 workflow 与固定 SHA，执行前核对 manifest、CLI 大小/摘要、DMG 和全资产 provenance。新 `p4-compare` 使用原门槛、60 次样本及完整 P4 工作量分别运行无追踪和有追踪；无发布写权限，诊断结果不改变原验收判定。相关本地回归首轮 39 项通过、YAML/内嵌 Python/Bash 语法及只读权限检查通过，真实失败包也通过身份校验；远端对照结果仍待取得。

真实单屏 DPI、忽略规则处理决定、最终 17 项稳定草稿及正式公开仍等待必需前置。没有创建 Rust 实现或改动其他会话的收尾文档，完整 3.0 范围继续保留。

### P3-7：同包对照、验证脚本与构建词表下载修复（2026-11-22）

诊断提交 `b0fe71f542f77d25b6c333dc9e47eeb668d44939` 只改 macOS 复验 workflow、对应验证代码与测试、本任务计划记录；已推送 Python 候选分支，未推进 main 或标签。Test `45058606509` 八个作业均成功。

复验 `45058634815` / job `137319371891` 在新宿主上安装原失败的 `20ac69e` DMG，没有重建。安装前后摘要、内核与来源一致，两次完整 P4 均通过：无追踪 n=60、p50=61.3 ms、p95=97.4 ms、max=190.8 ms；有追踪 n=60、p50=61.3 ms、p95=67.3 ms、max=69.6 ms。fixture 摘要完全相同，后置身份检查通过；独立下载的 artifact `14769495060` ZIP 摘要为 `5a4affb6b3e790b730d824aefe0288e980880810d2ba2481392ee077e96a446c`。原始失败判定保持 false。这组数据不能把初次失败归因 tracing，宿主波动的具体原因仍缺 CPU 与负载记录；没有修改 fixture 工作量或 100 ms 门槛。

四份 `20ac69e` 最终原生证据全部下载、核对 ZIP digest 与来源，新增 `final-draft-v2.5.5-20ac69e/native-inputs-complete-failed.json`：下载完整为 true，四平台验收为 false（Intel 失败），稳定草稿与真实 DPI 为 false。此前只有三项的输入文件和原报告保留。

DPI 驱动脚本的错误前缀解析及 emitted 记录修正用真实 Windows 开发候选 EXE 验证。自有窗口截图返回 600×421 PNG，独立像素检查发现粉色按钮范围 `[17,43,583,147]` 和绿色画布 `[17,162,583,338]`；未登记 image_id 返回 `STALE_IMAGE` / `not_delivered`，点击和拖拽计数保持 0，SDK shutdown 退出码 0。证据为 C 盘任务目录 `dpi-sdk-parser-check-2-20ac69e/preparation-verified.json`。仅证明脚本、实际截图及拒绝错误图像的链路，不代表最终程序四档 DPI 已通过；当前原生窗口清单仍无显示设置。

Build `45058606286` 的 Intel job `137319279679` 失败发生在 PyInstaller 准备固定 cl100k 词表，尚未构建实际 Intel 包、也没有进入 P4。日志明确为 `reverie.spec` 的 `urlopen(..., timeout=15)` / `response.read()` 发生 `TimeoutError: The read operation timed out`，与原版输入延迟失败分开记录。

最小修复仅针对构建：固定词表来源和 SHA-256 不变，连接/读取中断最多三次、每次超时 30 秒，坏摘要立即拒绝；完整验证后在目标目录写临时文件、flush/fsync 并原子替换，失败保留已有文件。先在原 spec 复现 7 失败/2 通过，包括真实回环 HTTP 503 和截断；修复后相关回归 80 通过（3.18 秒），包含拒绝坏摘要、有限重试、已有有效缓存不下载、切换失败保留旧文件。JUnit 为 C 盘 `tokenizer-download-green-1.xml`。

同一修复 spec 实际从官方固定 URL 无缓存下载并原子写入：1681126 字节、SHA-256 `223921b76ee99bde995b7ff738513eef100fb51d18c93597a113bcffe865b2a7`，2.734 秒，记录为 `tokenizer-download-live-1/report.json`。这项实测不替代四平台完整打包。修复候选须重新执行 CI、原生包与最终稳定草稿核对，main、正式标签、真实 DPI 与正式公开继续按前置次序处理。

### P3-8：新候选完整复核与稳定草稿 ID 修复（2026-11-22）

候选 `b293b7a46718a9373752672518d291bb476df5cc` 的 Test `45060802662` 八个作业通过、Build `45060802409` 四平台通过。四平台 14 项实际开发候选文件独立下载、核对 ZIP digest/CRC、程序摘要及原生 provenance，共 3844806314 字节；证据为 C 盘任务目录 `candidate-b293b7a/candidate-assets-verified.json`。GitHub API 的源码树与本地该提交的 1566 个受管条目一致，树为 `ceaa4f2359eae88c3760bb2c95a08316c104d6d0`；六个 SDK 协议来源的 blob 未变化。

保全与逐项重新核对原混合版 17 项资产后，main 正常推进到 b293b7a；版本标签通过旧对象 `6d2ec4307bcfad94a6629f3d8324583e38f9630b` 的单标签 lease 更新为 `a294896801d6407ba9a2d7af9de7c907324abc27`。前一纯 Python 标签对象保存在 `history/python-2.5.5-pure-20ac69e`。最新滚动与插件标签未变；本次差异未匹配插件工作流的路径筛选，无需停用它。重复 main Build `45063590402` 主动取消，不能计为通过；main Test `45063590366` 八个作业通过。

最终标签 Build `45063670087` 的四平台原生作业均通过，四份原生证据已独立下载并核对来源及 ZIP 摘要。P4 各 31 项检查通过，输入各 60 样本：Windows p95=43.1 ms、Linux=34.7 ms、Apple Silicon=50.5 ms、Intel=82.6 ms。来源均为 b293b7a，各 model-quality samples=0；仅证明对应实际包及受控软件场景，不证明真实模型质量或物理四档 DPI。记录为 `final-draft-v2.5.5-b293b7a/native-evidence-verified.json`；原 20ac69e 的输入失败没有改写。

发布 job `137340121891` 在 `Publish verified assets` 失败：创建返回草稿 URL，随后列表式 ID 提取未取得可接受的单一 ID。独立按 ID 核实草稿 `454721664` 确实存在，tag_name=v2.5.5、draft=true、零资产，target_commitish=main；按公开 tag 接口查询返回 404。完整失败日志及 `failed-draft-identity.json` 保存在该来源的 C 盘目录。暂没有足够证据确定列表提取失败的服务端传播、缓存或其他具体原因；没有据此发布、删除原资产或套用候选结果。

最小 CI 修复先取得已有草稿的单一 ID，在编辑前拒绝无效 ID；新建稳定草稿直接使用 REST 创建响应的 ID，说明按文件读取，target_commitish 固定验收 SHA，draft=true、prerelease=false、make_latest=false。保留 17 项上传、来源 Test、原生包和公开前 DPI 门槛。回归先在旧工作流复现 9 失败/13 通过（13.62 秒），包括草稿未出现在即时列表、来源未固定和无效 ID 编辑；修复后发布、保留失败包及工具链相关回归 94 通过（22.70 秒）。JUnit 为 `publish-id-red.xml`、`publish-id-green.xml`，测试执行真实 Bash 控制流并使用 gh 替身；修复后的真实 CI 与完整草稿尚待取得。

为新的最终来源准备了按实际草稿文件校验、三次 SDK 启停、真实索引/检索、JSONL 事务及历史实际数据库恢复的验证器。旧库输入已保全到 C 盘，不依赖用户正在清理的目录；这些新验证器尚未对最终修复包执行。目录级忽略选择再次保持待用户答复，真实单屏四档 DPI、最终 17 项实际下载、正式公开、Python 正式归档及 Rust 实施继续等待必需前置。没有修改其他会话的收尾记录，完整 Rust 3.0 计划仍保留。

### P3-9：实际草稿完成上传、最终标签绑定与回读修复（2026-11-22）

提交 `84e3c92c4c5a80e491e9da97b2e26735ece3a048` 仅包含发布 ID 修复及本任务必要记录，已推送候选分支。Test `45068369808` 八作业、Build `45068369794` 四平台通过，发布跳过；四份候选原生证据独立下载并核对来源及 ZIP digest。GitHub 树 `d228b3c17036b0a406f075b61e8ea5ae0154daf0` 与本地 1566 个受管条目一致，六个协议文件 blob 未变。证据在 C 盘任务目录 `candidate-84e3c92/`，没有改动其他会话的未跟踪目录。

上一空草稿 ID `454721664` 及注释标签对象 `a294896801d6407ba9a2d7af9de7c907324abc27` 保全到 `history/python-2.5.5-pure-b293b7a`，草稿保持未公开、零资产。逐项回读原混合版历史 Release 的 17 项资产身份不变后，main 正常推进到 84e3c92；`v2.5.5` 用旧对象的明确 lease 更新为 `8897f9afad472c9b4ea3eddc36e216b362268be4`。滚动与插件标签未变化。main Test `45070194116` 八作业通过，重复 main Build `45070194236` 主动取消，不能计为通过。

版本 Build `45070254227` 的四个平台及 publish job `137360706965` 均成功。四份最终原生证据实际下载并核对，P4 各 31 项、输入各 60 样本：Windows p95=35.9 ms、Linux=35.4 ms、Apple Silicon=48.3 ms、Intel=68.9 ms，model-quality samples 均为 0。它们证明对应包的受控软件行为，不证明真实模型质量、物理 DPI 或整个产品验收。记录在 `final-draft-v2.5.5-84e3c92/native-evidence-verified.json`，没有改写较早来源的失败或成绩。

实际稳定草稿 ID `454761433` 已有 17 项上传资产，来源为 84e3c92、draft=true、prerelease=false；独立回读却发现 tag_name 为 `untagged-db1664a31a39675f7ceb`，按 v2.5.5 查询未取得该草稿。完整 37319 字符发布日志及错误身份响应已保存。显式按 ID 写回标签、来源和草稿标志后，tag_name=v2.5.5，全部 17 项资产的 ID、大小、摘要保持不变，未公开。证据为 `draft-tag-mismatch-preserved.json`、`draft-tag-binding-request.json` 和 `draft-tag-binding-verified.json`。缺少此前各中间响应，字段变化的具体服务端原因仍未确定。

工作流补齐最终身份绑定和按 ID 的回读门槛。旧脚本上新增回归先复现 9 失败/19 通过（40.50 秒）；修复后发布、保留失败包及工具链相关回归 100 通过（46.13 秒）。新增反例包含错误标签、来源、公开标志、预发布标志及资产数量，全部仍禁止 CI 公开稳定版。JUnit 为 `release-identity-red.xml` 和 `release-identity-green.xml`。测试执行真实 Bash 控制流并使用 gh 替身；手工恢复旧草稿不等于新脚本真实 CI 通过，新候选尚须验证。

本轮只读依赖和模型来源复核见 [阶段 0A](phase0A.md)。默认 ONNX 原生分发缺 Intel macOS 条目，最终来源与许可未知，已提出不改变四平台门槛的策略选择，等待答复。目录级忽略合同和显示设置恢复也仍等待用户输入；窗口及应用清单没有返回可操作显示页，未发送 UI 输入或改变缩放。最终 17 项实际下载、最终 Windows 验证器执行、四档真实 DPI、正式公开、Python 正式归档及 Rust 实施均未完成。

### P3-10：新候选失败保全与可见性回归修复（2026-11-22）

候选 `67d5b52410696cacbb84eb90e984312315d7e075` 已推送，源码树为 `47d539ed9dce355816ded1cd91fe789f8293dc45`；GitHub 的 1566 个受管条目与本地来源一致，六个协议文件 blob 未变。Test `45074404455` 八作业通过。Build `45074404382` 的 Windows、Linux、Apple Silicon 通过，Intel 原输入 60 样本 p95=108.1 ms，未通过原 100 ms 门槛。原失败 DMG、CLI、追踪及四份原生证据已保全；同一 DMG 的对照 `45076754804` 无追踪 p95=70.7 ms、有追踪 p95=69.9 ms，两轮各 31 项通过，仅证明对照，未改写原失败判定。

同来源完整重建 `45077326646` 的 Windows、Linux、Apple Silicon 通过，Intel job `137377360989` 在 P2 `busy-once` 的 120000 ms 回调等待失败，前 13 项通过、后续原生检查未执行、publish 跳过。Intel 原生 artifact `14775989813` 实际 ZIP 的 SHA-256 为 `2396f28780ce4a57204a8872975c264b1cbbeb18fb63e4c17b7cfdc930897b5d`，已下载核对。两轮失败不能算完整四平台通过，也不能以 GPU/network 清理日志推定根因。

定向测试在原 `InteractiveViewRuntime` 上复现：同一批可见性通知依次为不可见、可见时，读取第一条会卸载已可见 iframe 并撤销通道。生产修复只将读取改为最后一条；回归同时检查原 iframe 和通道保留、反向通知正常释放及旧通道拒绝。首次回归 1 失败；修复后相关测试 48 通过，桌面全量 528 通过、原有独立 Engine 集成 1 跳过，类型及生产构建通过，原生验收校准 76 通过。JUnit 在 C 盘任务目录 `candidate-67d5b52/visibility-triage/`。这些结果确认了该可见性缺陷，尚不能证明它解释原 Intel P2 超时。

原生 P2 验证器补充实际 frame attach/navigation/detach、回调前后视口及焦点快照，不改变 workload、120000 ms 超时、失败判定或权限链。下一步依次核对旧失败包、新来源完整四平台以及最终标签草稿；原包与新包各自绑定来源，不交叉使用成绩。新修复提交的原生运行及真实 CI 尚待取得。

旧 `84e3c92` 草稿的 17 项实际文件已全部下载，共 3844008076 字节，独立核对来源、manifest、checksums 和四平台 provenance。原源码 ZIP 22939498 字节，SHA-256 为 `9cd4a01c4f486cf5d1dfab04b96802b7a0a46a3b032788c97de6b7a0cf2dfedd`，CRC 及提交注释通过。这是旧来源的保全，未宣称新候选通过。main 与 `v2.5.5` 解引用仍为 `84e3c92c4c5a80e491e9da97b2e26735ece3a048`，草稿 `454761433` 未公开，滚动标签未变化。

完整 Rust 主计划保持保留。Recall@10 的证据片段口径已确认；正式题集和成绩未冻结。纯 Python 正式重发、最终 Windows 实包与旧库接续、真实单屏四档 DPI、Python 正式归档和 Rust 实施继续等待必需前置。清理残留由用户处理，不再删除或作为独立阻塞；其他会话的收尾目录保持原样。

### P3-11：最终资产独立验证与真实 125% DPI 缺陷修复（2026-11-23 UTC）

来源 `3147b7b287fbc38ac87050219779e3f586c0eff3`，树 `1072df250f8882797b87043558f0c844ec5bb72e`，与本地、main 及候选分支一致。版本标签对象为 `dd3f3d6482bd49ed96059c2840741bec4fccf3ed`。main Test `45084957447` 八作业、标签 Build `45085155620` 的四平台及 publish 共五作业通过；重复 main Build `45084957562` 已取消，不计通过。草稿 ID `454850045` 为 v2.5.5、固定来源 SHA、draft=true、prerelease=false、17 项资产，尚未公开。滚动及插件标签未改变。

全部 17 项实际文件独立下载，共 3844794469 字节，核对资产 ID、大小、GitHub digest、SHA256SUMS、发行清单及四个平台的内核身份。最终 Windows CLI SHA-256 为 `635f8ebb54ceae15a4ca2ed7fa4ab22e65cf7b940a89c68fad00dbbb2d6286fe`，实际报告 Context Engine 为 Python / in-process。CLI、三次 SDK 生命周期及 Context Engine JSONL 事务 6 项通过；旧 Rust 数据库一致性备份、Python 派生索引、实际旧 worker 恢复查询及损坏备份拒绝 9 项通过。用户明确选择 2.5.5 保留历史目录忽略兼容、3.0 再明确，最终程序相应 11 项行为检查通过，无需更改忽略实现。

四份最终 native ZIP 的下载 digest、CRC、内部摘要及来源通过：各 P2 24/24、P3 28/28、rich 88/88、P4 31/31、隔离检查通过，输入各 60 样本。Windows、Linux、Apple Silicon、Intel 输入 p95 分别为 50.5、34.9、51.9、85.2 ms；Intel 原 max=443.8 ms 仍保留，门槛继续为原 p95≤100 ms。全部 model-quality samples=0，不证明真实模型质量或物理 DPI。

使用该最终 EXE，经 SDK→Agent→ToolExecutor→Computer Use 进行真实硬件输入，独立 WinForms 夹具回读实际 DPI、控件物理边界、点击及拖拽计数。在 100% 下普通、最大化、真实拖拽吸附窗口均完成原图、裁剪、缩小及桌面截图的命中验证。旧驱动跨两次 prompt 使用图像导致旧图拒绝；修正为同一 prompt。桌面色标检测曾合并其他图标的相近颜色，已用同一失败 PNG 复现并改为连通区域识别。系统拒绝前台切换及跨工具协调超时的失败分别保留；测试界面协调的等待调整不改变产品操作超时、真实 DPI、坐标或效果断言。

真实切到 125% 后，夹具回读 DPI 120，点击命中但拖拽以 TARGET_OCCLUDED / not_delivered 拒绝。只读现场对照确认同一物理端点 `(1159, 544)`：DPI 未感知线程命中设置窗口，逐显示器 V2 线程命中实际验收窗口；单纯改用 WindowFromPhysicalPoint 在本机仍未消除该差异，不能据函数名假定有效。已恢复系统 100%、原正常几何 `(544,178,716,499)` 及自有窗口原最小化状态。

生产修复只限定 `receives_point`：临时使用 PER_MONITOR_AWARE_V2，成功、拒绝或异常均恢复原线程上下文；不能建立或恢复时以 GEOMETRY_UNPROVEN 拒绝输入。新增测试在旧代码复现 8 失败/4 通过；修复后与截图、操作、权限、生命周期及 runtime 相关测试共 108 通过（3.39 秒），包含四档、非默认及大句柄上下文、真实遮挡、无窗口、查询异常及切换失败。将逐显示器上下文故意改回 DPI 未感知的变异检查明确失败，恢复原源码摘要后新增 12 项再次通过，证据为 `dpi-mutation-verified.json`。官方依据为 [SetThreadDpiAwarenessContext](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-setthreaddpiawarenesscontext) 和 [高 DPI 桌面开发](https://learn.microsoft.com/en-us/windows/win32/hidpi/high-dpi-desktop-application-development-on-windows)。单元与源级对照不代替新候选四平台及四档最终程序验收。

本轮原始证据、失败、测试 XML 和驱动留在已获准的 C 盘任务目录 `final-draft-v2.5.5-3147b7b/`，真实窗口及私有截图不上传 Git。旧草稿及 17 项资产须先保全再推进新的最终来源。纯 Python 正式公开、完整 Python 归档、0B 及 Rust 实施仍未完成；未改动独立 Engine、其他会话收尾目录或用户接手的清理残留。

### P3-12：固定物理边界下的真实缩放失效修复（2026-11-23 UTC）

来源 `6567ab1afdc5ffd51f37d340c7da3b24fc4dca1b`，树 `6ad65618b44abb1f4a7e07458496a0bbab67da0c`。已回读开发 Test `45094399569` 八作业成功、Build `45094399574` 四平台成功且发布作业 skipped。Windows 候选 ZIP 的下载 digest、CRC 和内部摘要核对通过，实际 EXE SHA-256 为 `6da9976d4410d2b1569a362bc497e0d5388f3d0f0334d088f0b31ab9b8fbb1eb`，四项 Windows 资产与对应 native provenance 一致。该 EXE 的真实 125% 缩小图点击和拖拽四项通过，证明此前命中检测修复在该实际程序有效；不代表四档完整验收完成。

最初固定边界夹具仍被 WinForms 自动缩放，未满足测试前提；跨工具协调超时、前台切换被拒绝、输入会话关闭、图像过期等失败均保留。修改自有夹具以关闭自动缩放并在真实 DPI 事件结束后恢复常量物理边界，独立回读确认 DPI 120→96、窗口始终为 `(220,180,900,520)`。旧 EXE 使用约 84.15 秒前的图像实际投递点击，计数 0→1，确认显示缩放未绑定到窗口截图。这是产品缺陷的实包证据，不是模拟结果。

现有原生 `list-displays` 实测返回同一显示器及物理边界、scale 1.0 和 1.25。生产修复仅在截图模块增加显示身份、物理边界和缩放快照：捕获前后及每次坐标输入前复核；显示顺序变化不误拒绝，几何或缩放无法证明时以 GEOMETRY_UNPROVEN 拒绝。继续保留图像可见性、寿命、目标身份、窗口 frame、真实遮挡和权限检查。无新增依赖、常驻监听或后台进程，原生读取仍受既有超时与取消约束。

新增行为回归在旧生产代码上 10 失败、23 通过；修复后相关截图、命中、操作、runtime 和适配器 115 项通过（2.72 秒）。代码审查故意反转显示状态比较条件，五个缩放回归全部失败，随后按原字节恢复并核对摘要，再次完成 115 项通过；记录为 `dpi-scale-mutation-verified.json`。只说明对应回归有效，不代替四平台 CI 或最终程序。

通过隔离 SDK→Agent→ToolExecutor→Computer Use 的源码进程及现有原生后端重跑真实 125%→100% 固定边界场景，七项通过：约 93.98 秒前的旧图以 STALE_IMAGE / not_delivered 拒绝，独立计数不变，重新截图的点击和拖拽各增加一次并校验实际坐标。系统恢复 100% / DPI 96。该报告明确标为源码链路；Python 启动器摘要不能作为发行 EXE 摘要，也未将 `real_four_scale_dpi_verified` 改为 true。

原始包、失败、夹具源码、审查记录与独立聚合验证留在已获准的 C 盘任务目录 `candidate-6567ab1/`，聚合结果为 `dpi-fixed-bounds-verified.json`。main 和正式标签仍为 `3147b7b`，草稿 `454850045` 未公开；新的修复候选尚待四平台、最终草稿和四档实包验收。完整 Rust 主计划、全部功能和性能门槛继续保留。目录忽略的历史兼容决定已同步，Python 正式归档、阶段 0B 和 Rust 实施仍未开始；未修改独立 Engine、其他会话收尾目录或用户接手的清理内容。

### 0B-1：独立题集冻结与评分合同验证（2026-11-23 UTC）

重新回读远端 `main`、`Reverie-Cli-py`、`v2.5.5` 解引用及正式 Release `454958491`，均对应最终纯Python `070fa25`；Release保持非草稿、非预发布、17项资产。后续开发只在已附加的Rust工作区和`codex/rust-3.0`进行。

两组最终独立复核各24 accept/0 revise/0 reject，未决ID为空。固定修订稿、最终复核及原始源码字节后，于06:15:48 UTC冻结 [queries-v1.json](../../testdata/context-evaluation/queries-v1.json)：48题、四领域各12、basic共16/hard共32、zh/en各24，130 required+23 supplementary。原候选与修订记录保留，不以检索成绩修改题干或证据。完整 [语料清单](../../testdata/context-evaluation/frozen-corpus-v1.json) 的1,588文件与Git对象一致；42个脚本只具有`eol=crlf`声明的精确导出差异，同时保留源字节和工作区字节摘要。标签及清单位于检索快照之外。

评分器确认Unicode字符数÷4的历史预算算法，验证实际返回正文、UTF-8字节位置、顺序、行数和内容身份。顺序反例复现了元数据能把后续命中提到前十的问题，修复后测试13项通过；加入冻结数据完整性核验后14项通过，已接入开发分支CI。空响应只用于检验全部标签的结构和摘要，不构成Python检索测量。正式Recall及nDCG尚未计算。

同源源码API诊断已完成冷进程完整索引30次、预热完整重建30次及开发示例查询30次；单次原始样本和来源摘要见 [source-baseline-v1.json](source-baseline-v1.json)。完整索引中位数/p95分别为20,123.4596/20,724.9936ms（新库），22,654.8821/23,443.5497ms（预热重建）；均保持默认8 workers和相同工作量。文件系统缓存未受控，诊断进程wall time包含结果JSON写入；这些数据不代替发行包启动、端到端检索和轻量的正式30次基线。归因、正式评分与实际包测量继续进行，Rust实现尚未开始。

### 0B-2：重复质量合同及实包重建完成审计（2026-11-23 UTC）

维护者确认每题 30 次：先取单题 Recall 均值再宏平均，报告范围与波动；原生超长片段评价时只计前 72 行，完整原始返回保留。评分器完成这两项修正，17 项聚焦检查通过，包括拒绝缺失/重复试次、完整原文去重、72 行边界、前十顺序、Unicode 和冻结摘要。[采集器](../../scripts/verification/capture-python-context-baseline.py) 的实际未修改源码 API 查询已运行，完整 48×30 采集通过 exec session `92871` 继续，结果位于 `.runtime/phase0B/baseline/python-recall-30-v1/`；此检查点尚未完成正式重复评分。旧单次和配对差异继续按原身份保存，不拿旧单次分数替代新基线。

正式 EXE 的 SDK 新配置/预热配置启动各 30 次、无索引新进程索引 30 次完成，正常退出及所拥有进程回收通过。SDK 内核可用时间的中位数/p95 为 3,130.1841/3,262.7398 ms（新配置）与 3,046.05195/3,123.8687 ms（预热配置）；冷索引为 18,334.884/18,892.446 ms。它们仍不代表完整 GUI 启动或文件系统冷缓存。原始记录 `.runtime/phase0B/baseline/python-sdk-baseline-v1/report.json` 和独立 `completion-audit.json` 保留。

原预热请求只有 16 次新修订，加预热后数据库为 revision 17；14 次在约 2 ms 返回前一轮统计。其 30 次“完整重建”合同判定为未通过，不使用原驱动的成功标志或预热分布。新的测量脚本在计时外分隔请求，并验证每次修订恰好增加一次、1,454 扫描条目、1,451 解析快照及 1,449 可词法检索文件，三类数量不得混用；当前只完成语法和旧实际快照读回，新的 30 次实包预热仍待运行。没有修改 Python 产品或原失败证据。

六个 SDK/桌面来源及 14 个组件来源的最终 Git blob 与早期静态清单原始字节逐一相同。[SDK 清单](sdk-protocol-baseline-v1.json) 和 [组件清单](component-protocol-baseline-v1.json) 已绑定最终 `070fa25`，分别固定摘要 `f3581f329b2dfa01b6cb80dd3b05dad34902ed1983f9177cef181539cf60c37b`、`1de82db58b5402889978ea6f0900cf410db8c433144009bb476e9df01a346093`。109/102/110/87 仍是静态声明数量，不代表各 action 已通过运行和生命周期验收。

本机再次只读核实 Rust/Cargo 1.96.0；远端 main、Python 归档和正式标签解引用仍为 `070fa25`。本轮仅在 Rust 开发工作区准备评价、基线和合同；`ReverieCli-rs` 的产品实现尚未开始。完整 Rust 范围、减半、语义、轻量、四平台、真实 DPI、Gamer 和 Live2D 门槛均保留。
