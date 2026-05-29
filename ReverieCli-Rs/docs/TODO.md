# ReverieCli-Rs — 未完成功能清单

> 根据 Python 源码 (`ReverieCli-py/reverie/`) 与 Rust 代码库对比，列出所有尚未完成或需要补全的功能。
> 最后更新：2026-05-29

---

## 1. LLM Transport & API 层

- [x] OpenAI-compatible (非流式 + 流式)
- [x] Anthropic-compatible (非流式 + 流式)
- [x] NVIDIA NIM transport
- [x] ModelScope transport
- [x] Codex/OpenAI transport
- [x] Google Gemini transport (非流式 + 流式 + tool calls)
- [x] Ollama local transport
- [x] Retry with exponential backoff (`with_retry`)
- [x] API key 自动解析 (nvidia/modelscope/codex/gemini/anthropic/ollama)
- [x] Provider catalog (5 providers, seed models)
- [x] Tool call extraction (OpenAI/Anthropic/Gemini)
- [x] **Anthropic streaming tool-call delta 累积**: `parse_anthropic_sse_response` 已实现 `content_block_start` (tool_use) + `content_block_delta` (partial_json) 拼接，并有 mock SSE 单元测试覆盖。
- [x] **Gemini streaming tool-call delta**: `stream_gemini_compatible` 已处理流式 `functionCall` part 并发出 `ToolCallDelta` 事件，并有 mock SSE 单元测试覆盖。
- [x] **Streaming tool-call mock SSE tests**: OpenAI / Anthropic / Gemini 的文本流、tool-call delta、partial JSON、多 tool call、混合 text + functionCall 场景已覆盖。
- [x] **Anthropic vision content blocks**: `build_anthropic_payload` 已转换 inline `image_url` blocks，并有 `anthropic_payload_converts_inline_image_blocks` 测试覆盖。
- [ ] **Token 使用量统计**: 流式结束时需从 `usage` 字段提取 prompt/completion tokens 并反馈给 session
- [ ] **Model fallback chain**: 当主 model 返回 401/403 时自动尝试备用 model（Python 有此逻辑）
- [ ] **自定义 base_url + headers**: `ModelConfig.base_url` 已存在但 transport 函数中部分 provider 没有使用它

## 2. Agent Core

- [x] Multi-turn tool execution loop (最多 25 轮)
- [x] MCP tool injection
- [x] Sandbox enforcement
- [x] Subagent nested execution
- [x] Mode-specific system prompts
- [x] Rules injection
- [x] Inline image 解析 (Markdown / @ 语法)
- [x] **Context compaction 实际接入**: `compact_session_messages()` 已接入 `agent.rs` 的 `context_messages()`。通过 `compaction_config_from_extras()` 从 config.extra 读取策略/max_messages/max_tokens/keep_start/keep_end。默认 SlidingWindow(100)，支持 Summary/ImportanceBased/Adaptive。tool_call/tool_result pair 不被拆开。
- [x] **Conversation history restore**: `context_messages()` 从 `SessionStore` 加载历史 messages，基础 persistence 已完成
- [x] **Reasoning effort / thinking budget**: `build_request_extra_body()` 已从 config/provider catalog 注入 `reasoning_effort` 与 Gemini `thinking`/`thinking_budget`。
- [x] **Max output tokens 配置**: `build_request_extra_body()` 已按 config override → provider catalog `output_limit` → default 的顺序生成 `max_tokens`，provider payload builder 已映射到对应字段。
- [x] **Temperature / top_p 配置**: `build_request_extra_body()` 已读取 config.extra 中的 `temperature` / `top_p` 并注入请求。`frequency_penalty` 如需支持可作为后续兼容项单独添加。
- [x] **Tool choice 策略**: `build_request_extra_body()` 已支持从 config.extra 透传 `tool_choice`。
- [ ] **Agent interrupt / cancel**: 无法中途取消正在运行的 LLM 请求（TUI/SDK bridge 需要此功能）

## 3. Context Engine (`reverie-context`)

- [x] Codebase indexer (file scan + symbol extraction)
- [x] Cache persistence
- [x] Symbol search
- [x] Dependency records
- [x] Text search matches
- [x] Fallback parsers (Rust/Python/JS/Lua/GDScript/config/Markdown)
- [ ] **Tree-sitter parser**: Python 版有 `treesitter_parser.py` 用于精确 AST 解析；Rust 端仅有 regex-based fallback parsers
- [ ] **Semantic indexer / embedding search**: Python 版有 `semantic_indexer.py`（向量化搜索）；Rust 端完全缺失
- [ ] **Knowledge graph**: Python 版 `knowledge_graph.py` 构建符号间关系图；Rust 未实现
- [ ] **Commit history indexer**: Python 版 `commit_history_indexer.py`；Rust `git-commit-retrieval` 仅返回 changed files，无 diff / blame
- [ ] **Context compressor**: Python 版 `compressor.py`（智能截断）；Rust `context_compaction.rs` 框架存在但未连接
- [ ] **Handoff / continuity**: Python 版 `handoff.py` + `continuity_validator.py` 支持跨 session 上下文传递；Rust 无对应
- [ ] **Novel index**: Python 版 `novel_index.py` 为 Writer 模式提供章节级索引；Rust 无对应
- [ ] **Emotion tracker**: Python 版 `emotion_tracker.py`；Rust 无对应
- [ ] **Fragment-based retrieval**: Python 版 `fragments.py` + `retriever.py` 实现 chunk-level 检索；Rust 仅有 whole-file symbol search
- [ ] **LSP integration for context**: Python 版 `lsp_manager.py` 从运行中的 LSP 服务器获取符号信息；Rust `reverie-lsp` crate 有类型定义但未连接到 context engine

## 4. Tools

### 4.1 已完成工具
- [x] file_ops, create_file, delete_file, str_replace_editor
- [x] command_exec
- [x] codebase-retrieval, git-commit-retrieval
- [x] count_tokens (chars/4 estimation)
- [x] web_search (fallback URL), web_fetch (real HTTP GET + readable HTML extraction)
- [x] task_manager (markdown checklist)
- [x] skill_lookup
- [x] list_mcp_resources, read_mcp_resource
- [x] text_to_image (diagnostic PPM preview only)
- [x] tool_catalog
- [x] switch_mode
- [x] userInput (non-interactive stub)
- [x] game_design_orchestrator, game_gdd_manager, game_playtest_lab
- [x] game_asset_manager, game_asset_packer, game_config_editor
- [x] game_balance_analyzer, game_math_simulator, game_stats_analyzer
- [x] game_project_scaffolder, reverie_engine, reverie_engine_lite
- [x] story_design, level_design
- [x] atlas_delivery_orchestrator
- [x] novel_context_manager, consistency_checker, plot_analyzer
- [x] task_boundary, notify_user (Ant tools)
- [x] subagent (nested execution via agent.rs execute_subagent_tool)
- [x] game_modeling_workbench, blender_modeling_workbench
- [x] ask_clarification

### 4.2 工具功能缺失

- [x] **web_search 真实搜索**: `ddg_html_search()` 通过 DuckDuckGo HTML lite endpoint 实时搜索，返回 title/url/snippet 结构化结果。网络失败或无结果时自动 fallback 到搜索 URL。`parse_ddg_html_results()` 有完整 mock HTML 单元测试覆盖。
- [x] **web_fetch HTML 提取**: `web_fetch` 已通过 `html_to_readable_text()` 去除 script/style/nav/header/footer/aside 等噪音、解码 HTML entities、折叠空白并返回可读正文。
- [ ] **count_tokens 真实 tokenizer**: 当前 `chars / 4` 估算；Python 版可选 tiktoken
- [ ] **computer_control**: 完全是 stub (`available: false`)；Python 版有截图 + pyautogui 操作
- [x] **subagent 实际嵌套调用**: agent tool dispatch 已路由到 `execute_subagent_tool()`，通过 `SubagentManager` + nested `ReverieAgent.run_prompt_once()` 执行。剩余 mode/model/depth/output merge 见 Subagents 章节。
- [ ] **userInput 交互式**: 当前返回 `not_interactive`；TUI 模式下需要真正阻塞等待用户输入
- [ ] **text_to_image 真实生成**: 仅输出诊断 PPM；需接入 ComfyUI / Stable Diffusion API

## 5. Gamer 生产管线 (深度功能)

- [x] Game design orchestrator (pipeline stages, verification)
- [x] GDD manager, playtest lab, asset manager
- [ ] **AAA Game Compiler**: Python `aaa_game_compiler.py` — 大型游戏编译管线；Rust 无对应
- [ ] **Character / Environment / Gameplay Factories**: Python `character_factory.py`, `environment_factory.py`, `gameplay_factory.py`；Rust 无对应
- [ ] **System Generators**: Python `system_generators/` 目录（abilities, combat, quest, camera, progression, traversal, save_load 等 12+ 子系统生成器）；Rust 无对应
- [ ] **Vertical Slice Builder**: Python `vertical_slice_builder.py`；Rust 无对应
- [ ] **Runtime Adapters**: Python `runtime_adapters/godot.py`, `o3de.py`（Godot / O3DE 代码生成器）；Rust 无对应
- [ ] **Animation Pipeline**: Python `animation_pipeline.py`；Rust 无对应
- [ ] **Asset Budgeting**: Python `asset_budgeting.py`；Rust 无对应
- [ ] **Content Lattice / Faction Graph**: Python `content_lattice.py`, `faction_graph.py`；Rust 无对应
- [ ] **Production Plan / Milestone Planner**: Python `production_plan.py`, `milestone_planner.py`；Rust 无对应
- [ ] **Scope Estimator / Expansion Planner**: Python `scope_estimator.py`, `expansion_planner.py`；Rust 无对应
- [ ] **Verification suite** (combat_feel, perf_budget, quality_gate_runner, slice_score): Python `verification/`；Rust `game_playtest_lab` 有 quality gates 但缺少专项验证器
- [ ] **World Program**: Python `world_program.py`；Rust 无对应
- [ ] **Runtime Capability Graph / Delivery**: Python `runtime_capability_graph.py`, `runtime_delivery.py`；Rust 无对应

## 6. Engine Lite (深度功能)

- [x] Project scaffold / load / save / validate
- [x] Scene + Entity + AssetRef management
- [ ] **Animation system**: Python `animation.py`；Rust 无对应
- [ ] **Audio system**: Python `audio.py`；Rust 无对应
- [ ] **Physics system**: Python `physics.py`；Rust 无对应
- [ ] **Navigation system**: Python `navigation.py`；Rust 无对应
- [ ] **Input system**: Python `input.py`；Rust 无对应
- [ ] **UI system**: Python `ui.py`；Rust 无对应
- [ ] **Rendering**: Python `rendering.py` (pyglet/moderngl)；Rust 无对应
- [ ] **Components / ECS**: Python `components.py`, `systems.py`；Rust `reverie-engine-lite` 仅有 project model
- [ ] **Video capture**: Python `video.py` (ffmpeg)；Rust 无对应
- [ ] **Live2D integration**: Python `live2d.py`；Rust 无对应
- [ ] **Blender modeling**: Python `blender_modeling.py`（Blender Python API bridge）；Rust 仅有 artifact-based stub
- [ ] **Procedural assets**: Python `procedural_assets.py`；Rust 无对应
- [ ] **Ren'Py import**: Python `renpy_import.py`；Rust 无对应
- [ ] **Localization**: Python `localization.py`；Rust 无对应
- [ ] **Save data / migration**: Python `save_data.py`；Rust 无对应
- [ ] **Benchmarking / telemetry**: Python `benchmarking.py`, `telemetry.py`；Rust 无对应
- [ ] **Math3D / scene graph**: Python `math3d.py`, `scene.py`；Rust 无对应

## 7. MCP (Model Context Protocol)

- [x] Stdio transport (spawn + JSON-RPC)
- [x] Client: connect, initialize, list_tools, call_tool, list_resources, read_resource
- [x] Server: tool/resource/prompt handlers
- [x] Registry for multi-server management
- [ ] **SSE transport**: `McpClient::connect()` 对 SSE/WebSocket 返回 error；需实现 HTTP+SSE transport
- [ ] **Streamable HTTP transport**: MCP 2025 spec 新增的 streamable HTTP transport；Rust 无对应
- [ ] **Sampling support**: MCP sampling capability (server 请求 client 做 LLM 采样)；Rust 无对应
- [ ] **Progress notifications**: MCP `$/progress` 通知；Rust 无对应
- [ ] **Resource subscriptions**: MCP 资源变更通知；Rust 无对应
- [ ] **MCP server auto-discovery**: 从 `mcp.json` / `mcp-config.json` 自动发现 servers；当前需手动配置

## 8. Plugins

- [x] Runtime plugin scanner (plugin.json)
- [x] Manifest fallback commands
- [x] `-RC` handshake probing
- [x] `-RC-CALL` command invocation
- [x] Dynamic `rc_*` tool synthesis
- [x] Plugin environment setup
- [ ] **Plugin install/uninstall lifecycle**: `reverie-plugins` crate 有 manager 定义但未连接到 `reverie-core` 的 `RuntimePluginManager`
- [ ] **Git / registry source installation**: `reverie-plugins` 定义了 Git/local/registry sources，但实际 `git clone` / registry fetch 未实现
- [ ] **Plugin activation/deactivation state**: `reverie-plugins` 有 activate/deactivate 但未持久化
- [ ] **Plugin dependency resolution**: 无对应
- [ ] **Plugin update / version check**: 无对应

## 9. TUI (Terminal UI)

- [x] TUI framework (ratatui), event handling, state management, render
- [x] Message display, input box, tool panels, session management
- [x] Help/settings/history overlays, status bar, search
- [ ] **TUI 启动入口**: `reverie-tui` 未连接到 `reverie-cli` main；无法通过命令行启动 TUI 模式
- [ ] **TUI ↔ Agent 集成**: TUI 事件循环未与 `ReverieAgent` 连接；无法在 TUI 中发送 prompt 并接收 streaming 响应
- [ ] **TUI 流式输出渲染**: 收到 `ModelStreamEvent::Content` 后需逐字渲染到 message panel
- [ ] **TUI 工具执行可视化**: tool call 开始/完成状态需在 tool panel 实时显示
- [ ] **TUI session 切换**: session list 存在但未与 `SessionStore` 联动
- [ ] **TUI clipboard / copy**: 框架存在但实际 clipboard 操作未实现

## 10. LSP (Language Server Protocol)

- [x] LSP 3.17.0 type definitions
- [x] LSP client (initialize, document sync, diagnostics)
- [x] LSP manager for multi-server
- [x] Stdio transport
- [ ] **LSP client 实际启动**: 无代码启动语言服务器进程（如 rust-analyzer, pyright）
- [ ] **LSP → Context Engine 连接**: LSP 诊断和符号信息未注入到 codebase indexer
- [ ] **LSP completion / hover / goto-definition**: 类型定义存在但 client 方法未实现
- [ ] **LSP workspace/configuration**: 未实现

## 11. Sandbox

- [x] Policy-based access control (file/network/process/resource rules)
- [x] Audit logging
- [x] Sandbox manager with lifecycle
- [ ] **Agent 实际执行时的 sandbox 检查**: `agent.rs` 引用了 `SandboxManager` 但 `execute_builtin_tool` 不接受 sandbox policy 参数——实际工具调用未经过 sandbox 过滤
- [ ] **Network sandbox**: `command_exec` 中的命令可以自由访问网络；无网络隔离
- [ ] **Platform-specific 实现**: `windows.rs` / `unix.rs` 存在但内容可能是 placeholder

## 12. Skills

- [x] Skill discovery (SKILL.md parsing)
- [x] Skill loader with caching
- [x] Skill executor (shell/read/write steps)
- [x] Variable expansion
- [ ] **Skill scope 优先级**: Codex CLI 支持 current → parent → repo → user → system 5 级 scope；`reverie-skills` discovery 仅搜索 2 个目录
- [ ] **Skill YAML frontmatter**: `reverie-skills` types 定义了 frontmatter 但 `reverie-tools` 中的 `discover_skills` 使用简单解析，未读取 YAML metadata
- [ ] **Skill 执行结果反馈**: 执行后的输出未回传给 agent conversation

## 13. Subagents

- [x] Subagent definition system (TOML)
- [x] Subagent manager with concurrency control
- [x] Built-in types (default, worker, explorer)
- [x] Agent-level nested subagent execution
- [ ] **subagent 独立 mode/model**: 子 agent 应可使用不同 mode 或 model；当前继承父 agent mode (hardcoded "reverie")
- [ ] **subagent depth tracking**: agent.rs 限制 max_tool_rounds.min(10) 但不传递递归 depth 给 SubagentManager
- [ ] **Subagent 输出合并**: 子 agent 输出如何合入父 conversation 的策略未定义
- [ ] **Subagent integration tests**: 无 E2E 测试验证嵌套执行

## 14. SDK Bridge (JSONL)

- [x] Ready event, runtime info, initialize, state
- [x] Settings catalog, plugins, tools, totals, sessions
- [x] Git status, indexing, context query, chat
- [x] Plugin command dispatch, dynamic `rc_*` dispatch
- [x] Dashboard events
- [x] **Chat streaming 事件**: `handle_chat_streaming()` 已在 JSONL bridge 上增量输出 `stream.start` / `stream.content` / `stream.tool_call` / `stream.end` / `stream.recovered`，并最终返回 `chat.complete`。
- [ ] **Chat tool-call 中间状态**: 多轮 tool loop 中间的 tool-call 开始/完成事件未作为 JSONL frame 输出
- [ ] **Error recovery**: transport 失败后的 JSONL error frame 格式与 UI 端期望可能不一致
- [ ] **File watch / auto-re-index**: Python SDK bridge 监听文件变更自动重新索引；Rust 无 fs watcher

## 15. CLI

- [x] `--version`, `--index-only`, `--sdk-bridge`, prompt modes, report
- [x] Mode override, prompt file/stdin
- [x] Interactive REPL 基础 stdin loop (run_interactive with streaming output)
- [ ] **Readline/history**: 无 readline 库，无命令历史持久化
- [ ] **Rich terminal output**: Python 使用 `rich` 库做 Markdown 渲染、语法高亮、progress bar；Rust 仅 println
- [ ] **Session UI**: Python `session_ui.py` 提供 session 管理 TUI selector；Rust 无对应
- [ ] **Rollback UI**: Python `cli/rollback_ui.py`；Rust 无对应
- [ ] **Theme support**: Python `cli/theme.py`；Rust config 有 theme 字段但无 terminal 着色实现
- [ ] **Help catalog**: Python `cli/help_catalog.py` 有完整 `/help` 内容；Rust `cli_commands.rs` 有基础版本
- [ ] **TUI selector mode**: Python `cli/tui_selector.py` 提供 fuzzy-select；Rust 无对应

## 16. Writer 模式 (深度功能)

- [x] novel_context_manager (memory persistence)
- [x] consistency_checker, plot_analyzer
- [ ] **Plot analyzer 详细分析**: Python `context_engine/plot_analyzer.py` 有更丰富的 arc/tension 分析；Rust 版较简化
- [ ] **Novel index**: Python `context_engine/novel_index.py` 对章节/场景做结构化索引；Rust 无对应
- [ ] **Emotion tracker**: Python `context_engine/emotion_tracker.py`；Rust 无对应

## 17. Atlas 模式

- [x] Delivery orchestrator (persistent state, slices, blockers, milestones)
- [ ] **Atlas Python 功能对齐**: Python `atlas.py` 可能有额外的 delivery intelligence；需对比

## 18. 构建与发布

- [x] GitHub Actions builds `dist/reverie.exe`
- [x] Reverie UI launch order prefers Rust binary
- [ ] **Cross-platform release**: Linux / macOS 目标构建；当前仅 Windows
- [ ] **Auto-update mechanism**: 无自动更新检查
- [ ] **MSI / installer packaging**: 无安装器
- [ ] **Python fallback integration test**: Reverie UI 在 Rust binary 缺失时回退到 Python 的路径需 CI 验证

## 19. 测试覆盖

- [x] 100 workspace tests passing
- [x] CLI integration tests
- [x] Provider payload schema tests
- [x] Agent regression smoke tests
- [ ] **LLM transport integration tests**: 使用 mock server 验证每种 provider 的完整 request/response 周期
- [x] **Streaming mock SSE tests**: 验证 OpenAI / Anthropic / Gemini 的 SSE 解析 + tool-call delta 累积 + 最终输出
- [ ] **MCP client integration tests**: 使用 mock MCP server 验证 tool discovery + invocation
- [ ] **Sandbox enforcement tests**: 验证文件/命令工具在 sandbox 模式下的拒绝行为
- [ ] **Context compaction tests**: 验证 sliding window / importance-based 策略的输出正确性
- [ ] **Plugin handshake tests with real scripts**: 当前仅 unit tests；需 E2E
- [ ] **Gemini/Ollama real API smoke tests** (opt-in, requires API key)

---

## 优先级建议

### P0 — 核心功能完整性
1. **Context compaction 接入 agent**：`context_compaction.rs` 有 strategy/config/scoring 完整实现，`agent.rs` 的 `context_messages()` 仍只通过 `SessionStore::compacted_messages_for_context(session_id, 40)` 保留最近 N 条。需要将 `CompactionConfig` 从 config/settings 读入 agent，替换硬编码 40，并保证 tool call / tool result 配对不被裁断。
2. ~~**Web search 真实搜索**~~：已完成。`ddg_html_search()` + fallback。
3. ~~**SDK bridge tool-call 中间状态**~~：已完成。`ModelStreamEvent::ToolExecStart`/`ToolExecComplete` 从 agent 多轮 tool loop 发出，bridge 映射为 `tool_call.start`/`tool_call.complete` JSONL frame。
4. **Token usage 统计与反馈**：streaming/non-streaming 响应中的 `usage` 字段尚未统一写入 session/dashboard totals。
5. **Model fallback chain**：当主 model 返回 401/403/429/5xx 等可恢复错误时，尚未按配置自动尝试备用 model。
6. **自定义 headers**：`base_url` 已广泛接入；自定义 provider headers 仍未作为配置面暴露。

### P0 已完成并保留回归关注
1. Conversation history restore：`context_messages()` 从 `SessionStore` 加载历史 messages，基础 persistence 已完成。
2. Config/Model → `ChatRequest.extra_body` 统一注入：已支持 `max_tokens` / `temperature` / `top_p` / `reasoning_effort` / `thinking_budget` / `tool_choice`。
3. Web fetch HTML → 可读正文提取：已完成 readable text extraction。
4. Streaming tool-call delta 累积与 mock SSE tests：OpenAI / Anthropic / Gemini 已覆盖。
5. SDK bridge chat streaming：已输出 `stream.*` 增量 frames 和 `chat.complete`。
6. Subagent tool ↔ Agent 连接：已通过 `execute_subagent_tool()` 接入 nested agent execution。

### P1 — 用户体验
1. ~~Interactive REPL~~：`crates/reverie-cli/src/main.rs` 已有 `run_interactive()` 基础 stdin loop + streaming output。**剩余：readline/history、rich output (Markdown 渲染/语法高亮)、TUI selector、tab completion。**
2. Rich terminal output (Markdown + syntax highlight)：需 `termimad` 或 `syntect` 集成
3. TUI 启动 + Agent 集成：`reverie-tui` 框架完整但未连接 agent event loop
4. Agent interrupt/cancel：无取消正在运行的 LLM 请求的机制
5. Token usage 统计与反馈：streaming 结束时 `usage` 字段未提取并回报 session

### P2 — 高级功能
1. Tree-sitter parser
2. Semantic indexer / embedding search
3. Knowledge graph
4. MCP SSE + streamable HTTP transport
5. LSP ↔ Context Engine 连接
6. Plugin install lifecycle (Git/registry)

### P3 — 游戏引擎深度迁移 (按需)
1. Gamer system generators
2. Runtime adapters (Godot/O3DE)
3. Engine Lite runtime modules (animation/physics/audio/rendering)
4. Vertical slice builder
5. AAA game compiler

---

*此文件由 codebase 对比自动生成，后续开发应逐项勾选完成状态。*
