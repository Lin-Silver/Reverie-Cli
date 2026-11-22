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
| P1 工程收整 | 进行中：只读核对 | 来源/私有数据/证据分开记录；独有 worktree 源码先归档并验证远端；删除可再生输出前验证绝对路径、Git 状态、链接及占用 |
| P2 纯 Python Context Engine | 已接入 Python；定向验证通过，完整候选验收待完成 | 真实 Python CLI/SDK/桌面、索引/检索/状态/服务、增量与事务、失败保护、旧数据备份接续通过 |
| P3 Python 重验与重发 | 进行中：修复候选验证；尚未重发 | 完整回归、四平台实际包、单屏四档真实 DPI、原混合版来源/资产归档与重发身份核对 |
| 0A 只读整理 | 待开始 | SDK/类型/语料草案与来源 SHA 对应 |
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
