# 普通会话压缩、同 ID 分段和接续

此记录对应 `native_modes` 的独立实施切片；不覆盖其他 Rust 任务的状态。当前已写入 `core/src/compaction.rs`、`core/src/session/context.rs`、独立事务检查 `core/src/session/context/checks.rs` 及 `scripts/verification/rust-compaction-smoke.mjs`。主会话已经完成初次 Host 接入并提供调试程序；本代理的第一轮实际 SDK 检查在第一项检查点发布处失败，未通过任何项。下面的修正及新增测试仍待统一构建和运行，不能称为普通会话链路已验收。固定提示词与 Python 归档逐字相同。

后续增加普通会话的 `SessionStore::begin_resumed_run(&mut self, source: &ContextSource, user_sequence: i64, run_id: &str, configuration: &Value, request: &Value, user: &Value) -> Result<()>`。Host 从一致性快照的最后一个活跃 user 取得原 sequence 与完整 message，传入全量 prompt／message 和已有附件字段；不得重建只含正文的新 user，成功后也不得再次 push／保存 user。

该入口在同一个 `BEGIN IMMEDIATE` 事务核对来源 revision／SHA-256、工作区、最后一个活跃 user sequence、完整 user Value、正文及显式附件、来源配置和未使用的 run ID，并拒绝同会话的非终态 run。成功只新增运行记录、引用原 user ID／digest 并增加会话 revision；原文、活跃投影、配置版本和导航不变。configuration_revision 取 source.revision；已有 runtime_config 按脱敏快照核对，缺失时沿用既有 Host 从工作区默认配置派生的口径。原 `begin_run` 的 AiO `promptAlreadySaved` 契约未改变；新普通入口拒绝借用该标记和应用级 AiO作用域。

Writer 首次接续需要补充推断绑定时，`bind_resumed_writer(source, binding)` 在 `BEGIN IMMEDIATE` 事务先核对完整原来源及 SHA-256，再只更新 `writer_project`、会话 revision 和更新时间，并返回更新后的来源快照供普通 resume 使用。相同绑定不重复写入；来源冲突和同会话其他非终态运行拒绝更新。不能直接读取最新 revision 来覆盖外部变更；旧原文、配置版本和选择保持不变。

Python 来源固定为 `070fa25b07692c90c56a6b00a9a969ff2abb7804`。`compressor.py` blob 为 `d8173da8952e291e6fa57db97998ed01856befb2`，`handoff.py` 为 `906208c566b31363b73d36c8abfab5f7fa2a7d49`，`workspace_stats.py` 为 `91e79a29ade1e402868551854185e8646bb38871`，`sqlite_manager.py` 为 `f26f1e7649f598290928c5a85f62cb34e3573076`。第一方行为与提示词按本仓库 MIT 来源迁移。

两个模型调用都是同步纯数据请求准备：调用方执行无工具模型请求，模块只解析结果，不执行工具、不写会话。Host 必须先在 70% 执行 compression，重新计数后仍达 82% 才执行 handoff。普通 compression 保留原 Python 6／8 条默认尾窗并向前扩展完整 assistant/tool 交互；handoff 保留摘要及当前用户原请求，避免重播旧工具调用。

模型 compression 失败或空结果允许原 Python 的确定性本地摘要兜底，明确标为 `deterministic_fallback`，不能报告为模型成功摘要。最终未减小上下文、检查点失败、取消、修订冲突或原子提交失败不切换活跃状态。无实质内容的 handoff 只生成一次无工具修复请求，最终仍无效则保留最后可用投影；不提供本地 handoff 兜底。Host 在模型返回后、切换前仍须检查取消和原 run 归属。

`ContextSnapshot` 在同一 SQLite 读事务中冻结会话 ID、revision、message_count、原 metadata JSON 字符串及所有原 payload／message ID／sequence／SHA-256。检查点写入临时文件、fsync、不覆盖发布，并读回校验完整来源与内容。分段在一个 `BEGIN IMMEDIATE` 事务内验证来源修订、检查点、原 sequence 引用及幂等 event，追加一个摘要边界并切换投影；不改旧行、配置版本、导航和任务归属。

保留 `segment_context` 原签名，新增 `segment_context_checked(..., allowed_run, commit_guard)`。事务内拒绝同会话除明确允许的当前 run 外全部非终态运行，终态集合与普通 resume 相同；手动压缩传 `None`。写入完成后、`COMMIT` 前调用取消／归属检查，检查失败回滚整次切换，返回的许可对象一直持有到提交结束。`ensure_reduction_run` 提供模型调用前的提前检查，但不能代替事务内的最终检查。Host 负责将许可对象与 stop／shutdown 的提交锁相连，并正确区分取消之前或之后已经提交的操作。

Windows 检查点发布使用已创建父目录的 canonical IO 路径，`NamedTempFile::new_in` 和 `persist_noclobber` 均使用该路径；公开 `checkpoint.path` 与受管路径检查保持原逻辑路径。首轮实际故障来源是 tempfile 3.27.0 的 Windows `MoveFileExW(flags=0)` 长路径边界。失败程序 SHA-256 为 `756c6826293a8b51075b543218482291c3d169cd311a95fe3235dc9f7dd544ad`；原始失败、身份和 SQLite 读回位于 `.runtime/rust-3.0/compaction-review/case-v5cio5/`。相同目录下的隔离 syscall 复现中，316 UTF-16 单位的普通目标返回错误 3，给目标添加 `\\?\` 后成功。该诊断只证明路径原因；不是修正版 SDK 验收结果。原失败保留，未缩短题集目录、来源摘要或检查点文件名。

同 ID 接续引用旧系统指令、完整尾窗或当前用户所在的原 sequence，当前用户不会再次落成新原文。正常历史读取只查询活跃引用及边界后的新行；完整原文只用于归档快照与压缩准备。重启根据 `native_context_projection` 恢复同一投影，Provider 历史不包含 `segment_boundary`、`context_replay` 或摘要审计 metadata。原文分页仍由既有 `page` 完整读取。

SQLite 主 schema 仍为最终 Python 的 `user_version=7`，没有删除或改写旧历史版本。新投影使用 Rust 专属 metadata 引用旧 sequence；旧 Python 二进制不会解释这套新引用，不能声称它可直接恢复 Rust 分段后的同一活跃尾窗。原始数据库行和完整检查点保留恢复依据；真正的手动检查点 restore／旧运行时数据回退仍另行实施与验证。

对话文本采用真正离线 `tiktoken-rs = { version = "=0.12.1", default-features = false }` cl100k。该 crate 未 yanked、MIT、MSRV 1.85；官方 crate SHA-256 为 `2aeff724640cfe13037336ddf35befdffd2909cbdb65cf041cc8a4cf8c584cfa`，固定上游提交 `72a5a800651a1cea1ad609292446ba02c80e3bcd`。内嵌 cl100k 词表 1,681,126 字节，SHA-256 `223921b76ee99bde995b7ff738513eef100fb51d18c93597a113bcffe865b2a7`，与 Python 固定词表相同。原始许可见 [固定 MIT LICENSE](https://github.com/zurawiki/tiktoken-rs/blob/72a5a800651a1cea1ad609292446ba02c80e3bcd/LICENSE)；Copyright (c) 2023 Roger Zurawicki，LICENSE blob `39aa2a22b04e732499c3f3cf6df84f50215d8f5f`。Cargo、锁文件和最终许可证材料由主会话整合。

文本失败按 Python 的 Unicode 字符数÷4 回退并披露；图片、视频使用原 Python 的尺寸档位，不将其 base64 全部计作文本。每条消息 4 tokens、name 扣 1、回复引导 2 的包装仍是历史估算。`TokenUsage.tokenizer.exact=false` 指整条消息并非 Provider 精确用量；`text_exact` 单列本地文本算法是否发生回退，`media_estimated` 单列媒体估算。不得借用检索的 72 行／估算 12,000 tokens 规则，也不能把 cl100k 当作所有 Provider 的真实 tokenizer。

Compression 固定提示词 LF SHA-256：`a4568c8742776db27eea428bd33f65820b21bc81dd0af4f663a5070d75e866f7`。Handoff 固定提示词 LF SHA-256：`5cc403604db63d685066fd3f1ea4d86dab1e20bf794b43fc90315b8ab4e1613b`。本轮直接读取归档 blob 后逐字对照得到以上值，不是模型质量结果。

原有定向 Rust 测试共 20 项，原 14 项覆盖本地计数及精度披露、媒体和签名、阈值、fallback、handoff 一次修复、完整尾窗、未知桌面投递记忆、原文检查点、同 ID／重启、配置／导航、修订、SQL 失败、检查点篡改和幂等事件；另 6 项覆盖普通 resume 的完整 payload／附件、来源与 aliases 不匹配、所有非终态 run、两连接竞争、重复 run ID、SQL 失败／删除及 multipart 原文。本轮另增加 6 项：Windows 超过 260 字符的实际发布与完整校验、提交检查拒绝后的全部回滚、许可持有到实际提交可见、两连接非终态过滤与当前 run 允许、Writer 来源绑定及完整原文／配置／选择保护、Writer 错误来源与 SQL 失败保护。共 26 项，其中长路径项仅 Windows 执行；代码已写入，尚未运行。

基础验证命令：`cargo test --manifest-path ReverieCli-rs/Cargo.toml -p reverie-core compaction`、`cargo test --manifest-path ReverieCli-rs/Cargo.toml -p reverie-core session::context`、对应 Clippy；实际链路为 `node scripts/verification/rust-compaction-smoke.mjs ReverieCli-rs/target/release/reverie.exe`。Windows 路径可替换为已构建的相同原生候选。脚本含 13 项基础检查，只在 `.runtime/rust-3.0/compaction-smoke` 新建隔离 fixture，注入历史时原生桥已停止；对照原文、实际工具效果和运行身份。附件接续用例核对原字段保存，不代表真实图像已解析或发送给 Provider；multipart helper 用例也不代表 Host／GUI 附件流程已迁移。全部 fixture 不代表真实用户迁移、真实模型质量或多平台发行通过。

待验证／未实现内容：

1. 修正后的实际 Cargo 构建、26 项定向测试、Clippy 与 13 项 SDK smoke；第一轮实际 SDK 失败保留，尚不能报告会话压缩已通过。
2. Host 的 automatic compression／handoff／resumePrompt／compactContext 新事务入口接入、取消与提交的线性化、Writer 最终 system 加入后的容量检查及 GUI/TUI 实际事件验证。
3. 真实 Provider 的摘要事实保留、handoff 修复、提示注入抵抗及跨 Provider native response／reasoning／媒体精度。
4. 完整手动 context_management、truncate／summarize／checkpoint／restore 及所有既有命令别名。
5. fork／rewind／export／history versions 兼容与真实用户历史数据的完整恢复验证。
6. 项目 MemoryOS／MemoryIndexer 的来源、版本、预算、跨会话检索及更正／删除后下一请求刷新。
7. 文件检查点与操作历史的真实回滚；未知投递必须先观察，不能因接续自动重播。
8. 多平台实际包、长会话内存与耗时、AiO 长稳及桌面真实交互。
