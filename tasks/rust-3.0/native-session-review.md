# 会话压缩、恢复与长期上下文只读审查

审查对照为 Python 固定归档 `070fa25b07692c90c56a6b00a9a969ff2abb7804`；Rust 为本轮工作树，开始时 HEAD `881e3f14a1e4b79bc405cab7daa26fd32059aea0`。本项只读取源码和已有报告，未运行 Cargo、模型或新的验收，未修改 Session、Host、Provider、协议、UI 或 Cargo。

后续已获准开始普通会话的独立实施切片，状态单独记于 [native-compaction-notes.md](native-compaction-notes.md)。该切片已写入计数、压缩请求／结果、原文检查点与原子投影模块及定向验证代码，尚待注册、编译和实际 SDK 验收。下表及文件哈希保留为本次只读审查时的历史快照，不以新模块存在宣称普通链路已通过。

**结论：原文持久化和基本中断恢复已有实现及实际包证据；普通长对话的预算触发、压缩、自动 handoff、手动管理和项目长期记忆仍有完整功能缺口。AiO/Writer 的专属恢复以及 Atlas 的交接文档不等于普通会话链路已迁移。**

## 对照事实

| 行为 | Python 归档 | Rust 当前状态 |
|---|---|---|
| 原文与角色 | SQLite 保存完整消息，存储 `Reverie`、传输 `assistant`；分页读取历史 | `SessionStore::append/page` 已保存完整 payload，角色只在存储/传输边界转换 |
| 活跃上下文 | 默认 CLI/桌面用 SQLite；`rotate_session` 保持 ID、配置及完整原文，追加 `segment_boundary` 摘要并更新 `active_context_start` | `history` 能读取旧 `active_context_start`，尚无原生分段提交方法或自动写入链路 |
| 自动触发 | `CONTEXT_COMPACTION_RATIO=0.7`、`CONTEXT_ROTATION_RATIO=0.82`；先压缩，仍超阈值才 handoff；失败有 30 秒重试窗口 | 普通 Host 把活跃历史全部发给模型，在最多 64 次工具迭代中继续追加；没有上述预算检查 |
| 对话计数 | `WorkspaceStatsManager` 优先离线 cl100k，缺资源时回退字符估算；统一计消息包装、工具字段和多模态 | `max_context_tokens` 能保存/展示，普通模型执行未用它限制会话；WStyle 的独立预算检查另算 |
| 压缩 | 固定九节 continuation Markdown；保持系统指令、工作记忆和完整工具链尾窗；压缩前后检查点；模型失败可使用明确的本地确定性摘要 | 未找到普通会话压缩器、原始检查点和对应执行事件 |
| Handoff | schema 2，模型生成结构化目标/约束/状态/证据/下一步；无有效内容时做一次模型修复，仍失败则不切换；保持当前用户任务 | 没有普通会话的模型 handoff 与连续执行；Atlas 的 `handoff_summary.md` 是交付记录 |
| 最近原文 | 默认保留 6/8 条，向前扩展以保持 assistant/tool 关联；`context_replay` 不再次写入用户原文，内部标记不发给 Provider | 没有完整投影/回放实现；已有 AiO `promptAlreadySaved` 只适用于明确的应用级任务分支 |
| 中断 | 流式片段、任务状态和保存的请求用于恢复；不把不确定工具交付当作未执行 | 流式 chunk、运行配置/请求、队列与 `interrupted` 标记已有；自动重放中断任务被避免 |
| 手动管理 | `compactContext`、`resumePrompt`、`context_management`／`manage_context`／`compress_context`；检查点及恢复、fork/rewind/export | 这些旧 action/tool 尚未出现在 Rust 注册表；GUI 仍有调用入口，需要接通。`recovery.available=false` 明确标迁移未完成 |
| 项目长期记忆 | `MemoryOS`、MemoryIndexer、事件/类型/版本/来源、更正/删除、跨会话检索、按预算组装；每次请求刷新记忆，避免重播旧系统记忆 | AiO 有应用级记忆及 tombstone；普通项目没有对应 MemoryOS/MemoryIndexer 注入。代码/文档检索及语义索引不能替代该链路 |

`cli/interface.py:68` 明确使用 `SQLiteSessionManager as SessionManager`。因此最终 2.5.5 的主运行契约是同一个会话 ID 的上下文分段；旧 JSON 管理器另有创建新会话及保存 `session_handoffs/` 文件的实现，不能把它的行为误当默认基线。

归档 Agent 的注释写“80%”，真实 handoff 常量是 **82%**，实施与测试应以常量和调用为准。此前维护者冻结的 **12,000 tokens、Unicode 字符数÷4** 是检索评价预算，不能据此替换普通对话的 cl100k 计数。cl100k 是本地文本计数，Provider 实际包装/媒体 token 仍需披露估算限制。

## 最小完整迁移切片

建议先实施“一次真正可继续的压缩及重启恢复”，再补项目长期记忆和文件回滚。以下是实施建议，不是已实现接口或新的验收降级。

1. **纯规划与模型结果模块。** 在 `core/src/compaction.rs` 独立完成计数入口、70%/82%触发、完整 assistant/tool 尾窗、固定压缩/handoff 提示词、schema 2 解析/修复请求、失败/取消结果。显式输入包含当前会话、完整原始消息及修订、当前请求、配置、记忆提示；模型通过现有无工具 `text_model` 调用。保存模型/Provider、来源范围、摘要身份和计数器精度，不能把摘要当原始事实。
2. **原文不变的原子分段。** `session/context.rs` 扩展 `SessionStore`，在一个事务内核对 ID、修订、原消息范围和摘要身份，追加边界消息并切换活跃上下文；保留旧 payload、事件、配置版本与完整导出能力。尾窗引用原消息，不把回放用户/工具消息再次写进原文。重启后恢复同一投影，而不是只剩摘要或重复最近原文。压缩前原文检查点必须可读取并核对，失败/取消/并发修订变化保留旧活跃状态。
3. **Host 的同任务连续执行与手动入口。** 在每次主模型请求前检查实际组装后的预算；压缩后重算，仍超阈值才模型 handoff。会话 ID、run ID、工作区、模型、任务及权限归属保持原绑定，当前用户原文只存一次；不在尚未完成的工具组中切换。接通 `compactContext` 和普通 `resumePrompt`，返回原 `context.compacted`／`prompt.result` 契约及带归属的进度、取消/失败事件。手动操作与活跃运行竞争时明确阻止或串行协调。
4. **一次真实 SDK 验证。** 新增 `rust-compaction-smoke.mjs`，运行原生程序和可控模型：强制触发、精确尾窗、原始 CRLF/CJK/Emoji/附件字段哈希、跨会话隔离、修改配置不影响旧快照、当前请求不重复、压缩后持续工具执行、关闭/重启恢复、无工具摘要调用、模型失败/无效 handoff/修复失败/取消/修订竞争。检查数据库原文和实际工具效果；模型替身只证明协议与执行链，不证明摘要质量。

以上四项通过才可称“普通会话压缩及分段恢复基本可用”，仍须保留后续完整功能：`context_management` 全动作和别名、手动 truncate/summarize/checkpoint/restore、完整 fork/rewind/export/history versions、项目长期 MemoryOS/MemoryIndexer、更正/删除后下一请求刷新，以及操作历史/文件检查点的真实回滚。

长期记忆建议单独薄切片：项目隔离的事件与 typed memory 持久化→带来源/版本/删除状态的检索→每次请求的预算组装→更正/删除后失效→旧数据兼容与重启。共用 Context Engine 的真实证据和预算能力，保留 AiO 应用级作用域。不要把“搜索全部会话消息”当作已经实现 MemoryOS 的版本、来源和更正语义。

## 接口和文件边界

| 归属 | 最小变更边界 |
|---|---|
| 独立可并行模块 | 新 `core/src/compaction.rs`、`session/context.rs` 的独立实现和定向验证脚本；共享模块注册由主会话完成 |
| Session 整合 | `session.rs` 和必要 schema：原子分段、原文范围/版本读取、幂等提交、恢复投影；不改已有消息字节或借用不兼容的 `history_versions` payload |
| Host 整合 | `host.rs`：预算前置、无工具模型调用、继续同 run、manual action、请求归属、取消和事件；不复用 Auto Check 的风险配置为压缩配置 |
| Provider | 复用已迁移 transport；移除 `context_replay`／`segment_boundary` 等内部状态及不能再用的 provider-native 链接，不重播旧工具调用；真实 Provider 验证另列 |
| SDK/协议 | `compactContext(projectRoot,sessionId,focus)`→`context.compacted`；`resumePrompt`→`prompt.result`；既有 `getRecovery`、`rollbackCheckpoint(confirmed=true)` 等完整恢复 action 继续迁移 |
| GUI/TUI | 接通现有压缩、继续、fork/rewind/export 和检查点入口；计数器、状态、未完成/失败与恢复结果真实展示，复制及原文导出保持一致 |
| 本次允许写入 | 仅本审查文档；未改上述共享实现 |

## 已有实际证据及限制

本轮只读取已有报告，以下是对应旧运行的证据，不能合并宣称本轮新候选全部通过。

| 报告 | 已记录通过内容 | 实际程序 SHA-256 |
|---|---|---|
| `.runtime/rust-3.0/session-smoke/case-p1CMS8/report.json` | 20 次实际 JSONL 请求；配置备份、会话隔离、修订冲突、73 条夹具消息的分页/角色转换/原 payload 不变、重启、SQLite 备份可读取 | `3a40980c099e1315d097e7a7999238d84552e035015442f8fd84431da0b098a3` |
| `.runtime/rust-3.0/run-smoke/case-4VlayH/report.json` | 16 项实际执行；原生读写、流式片段、审批、提问、HTTP 取消和部分原文保留、截断流不能完成、并行项目归属、正常关闭和 EOF | `925dff22cfbd390b54e13fc39165a24a8ea942c7da8e6b9a27c5aa1b2243563b` |
| `.runtime/rust-3.0/modes-smoke/case-qWLDyr/report.json` | 13 项、51 次 loopback 调用；Writer 原文/恢复、Atlas 持久证据、AiO 中断与交付不确定状态、记忆更正/删除及 tombstone | `3c65127d354a6b0d5c02f3c96108974b96b41c3f3bbb57e14beda9020b74a7eb` |

会话报告中的 73 条消息由验证脚本直接写入隔离 SQLite，再让 Rust 读取；不能把它称为 73 条真实用户迁移。两个模型报告使用 loopback 替身，不能证明真实摘要或模型任务质量。现有报告未包含普通会话 compaction/handoff 的模型请求或原子分段结果。

## 实质差异与需决定的偏离

1. 保持最终 Python SQLite 的同 ID、原文不变契约已有依据；如改为自动新会话 ID，需先向维护者说明任务/配置/导航迁移并确认，不能沿用旧 JSON 类推断。
2. 对话窗口默认迁移 cl100k 与披露回退已有依据；如要为轻量统一成字符估算，需维护者确认对 70%/82%触发的影响，不能借用检索预算决定。
3. Python 压缩失败有确定性本地摘要，handoff 失败必须模型修复后再切换；若 Rust 改为两者都拒绝或都使用本地兜底，需确认差异并保留真实来源/失败状态。
4. 手动 truncate/rewind/restore 只能改变可恢复的活跃投影或建立保留原文的历史版本；若需物理删原文或回滚真实文件，须按已确认的恢复/授权契约执行，不能让模型摘要触发文件回放。
5. 如果计入真实 Provider 的 native response、reasoning 或多模态预算，需要明确哪些字段可跨压缩继续，缺少证据时拒绝猜测补齐；本地文本 counter 不能宣称 Provider token 精确等价。

## 未验证

1. Rust 普通会话自动70%压缩、82% handoff 及同任务持续执行。
2. 新摘要投影原子提交、原文检查点恢复、修订竞争和崩溃中断矩阵。
3. 普通 `resumePrompt`、手动 `compactContext`、context_management 全动作与 GUI/TUI 接入。
4. 项目 MemoryOS/MemoryIndexer 的跨会话检索、事实来源/版本、更正和删除后失效。
5. 真实 Provider 摘要、handoff 修复、提示注入、长文/代码事实保留和多模态计数。
6. fork/rewind/export、旧 JSON/SQLite 历史版本与所有用户原文数据的完整兼容。
7. 操作历史及文件检查点的真实回滚、明确交付不确定操作的恢复。
8. 多平台原生包、长会话内存/耗时、两小时 AiO 和完整真实故障验收。

## 来源身份

| Python 归档源码 | Git blob |
|---|---|
| `context_engine/compressor.py` | `d8173da8952e291e6fa57db97998ed01856befb2` |
| `context_engine/handoff.py` | `906208c566b31363b73d36c8abfab5f7fa2a7d49` |
| `session/sqlite_manager.py` | `f26f1e7649f598290928c5a85f62cb34e3573076` |
| `tools/context_management.py` | `8ff281efe2c3045ae76376eae33848b904678951` |
| `session/workspace_stats.py` | `91e79a29ade1e402868551854185e8646bb38871` |
| `memory/os.py` | `77deeafb8d79057747587450859ad97394d2ccdb` |

Rust 只读快照文件 SHA-256：`session.rs=d55a007e12c19bd1cdf79714e946f3b8c68c893a1cd040012e124785fa4d84e6`，`session/runs.rs=fb333882e095e876b6884962ac25f73ddc0936719a4c4baac4e2b8b07ec6ffc4`，`host.rs=f11116247dece9c6024c510fe0051de3ad2733aeaebee9bc65e8eca8d4774eda`，`lib.rs=b7d24091ca025c72ce6a3d7839493078e8f5b2311df3ea0c4fc558883dbf5358`，`schema.sql=945096ab4cc37cb4e1cd723a70918ed473000fc6e2fa25e997e75394be7d0ca0`。并行整合可改变这些工作树文件，实施前应复核。
