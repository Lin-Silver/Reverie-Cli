# Reverie CLI 3.0.0 实施记录

本任务执行用户确认的 [完整计划](plan.md)。计划原文中的“当前状态”是接受计划时的快照；后续实施状态以本文件及验收证据为准。保留全部范围、门槛与许可约束，不覆盖 `tasks/python-2.5.5-closeout/` 的历史记录。

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
| P2 纯 Python Context Engine | 已接入 Python；JSONL 类型与事务边界已修复，定向运行通过；新包待验收 | 真实 Python CLI/SDK/桌面、索引/检索/状态/服务、增量与事务、失败保护、旧数据备份接续通过 |
| P3 Python 重验与重发 | 修复前候选全量回归通过，但实包发现服务缺陷；新候选须重验，尚未重发 | 完整回归、四平台实际包、单屏四档真实 DPI、原混合版来源/资产归档与重发身份核对 |
| 0A 只读整理 | 候选快照清单与语料草案已整理；未冻结正式基线 | SDK/类型/语料草案与来源 SHA 对应，详见 [阶段 0A](phase0A.md) |
| 0B 正式基线 | 待开始 | 纯 Python 来源及备份恢复、冷/热各至少 30 样本、耗时分解、质量与轻量基线 |
| 1 Rust 首条链路 | 前置未满足 | 同一 Rust 内核驱动 CLI、SDK、桌面及真实 Provider/工具/会话 |
| 2 Context Engine | 前置未满足 | 完整结构/基础/本地语义链与性能质量门槛 |
| 3 模式与平台 | 前置未满足 | 全模式与实际平台工作流 |
| 4 生态与界面 | 前置未满足 | 四市场/通用组件/真实 OAuth/更新/GUI/TUI/询问与换行 |
| 独立组件 | 前置未满足 | Gamer 四作品/类型矩阵/导出与 Live2D 原生渲染/许可 |
| 5 核心候选 | 前置未满足 | 四平台实际包、DPI、完整性能门槛、连续 7200 秒四路 AiO |
| 6 主线发布 | 前置未满足 | 验收 SHA、main/tag、实际资产对应 |
| 7 完整产品 | 前置未满足 | 全部必需独立组件验收通过 |

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
