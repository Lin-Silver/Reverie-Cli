# ReverieCli-Rs Parity Tracker

This file tracks the Rust rewrite against `ReverieCli-py`.

## Implemented Baseline

- Cargo workspace with `reverie-cli`, `reverie-core`, `reverie-context`, `reverie-tools`, and `reverie-engine-lite`.
- CLI flags compatible with the Python entry point: path, version, SDK bridge, index-only, prompt modes, mode override, report file.
- JSONL SDK bridge with ready event, runtime info, initialize, state, settings, sessions, tools, diagnostics, Git status, indexing, context query, chat, plugin command dispatch, dynamic `rc_*` dispatch, and shutdown.
- UI-compatible SDK bridge actions and event shapes for dashboard state, camelCase commands, settings catalog, plugin/tool lists, totals, workspace indexing, and agent regression smoke runs.
- JSON config compatibility with defaults and unknown-field preservation.
- Project data directory compatibility with Python safe-path naming and legacy hashed-cache migration.
- Mode aliases and command catalog.
- Native rules loading from workspace and user `AGENTS.md`/rules files with agent prompt injection.
- Provider catalogs for Codex, NVIDIA, ModelScope, Gemini, and Ollama seed models with unified transport routing.
- Context indexing, cache persistence, symbol search, dependency records, text search matches, and fallback parsers for Rust/Python/JS-family/Lua/GDScript/config/Markdown surfaces.
- Session index, checkpoint create/list/restore, operation list, and built-in tool audit log.
- Built-in tool registry with mode visibility.
- Core tools: file ops, create/delete, str replace/insert/view, command exec, codebase retrieval, git status, token count, web search fallback, web fetch with readable extraction, skill lookup, MCP cache resources, TTI diagnostics, task manager, user input, tool catalog.
- Gamer artifact tools: request/program artifact, runtime delivery plan, engine-lite scaffold/create/inspect/add-scene/add-entity/register-asset/validation, GDD, asset manifest, playtest score, design and analysis documents.
- Writer, Atlas, Ant, Subagent, and modeling tools produce native Rust compatibility artifacts.
- Runtime plugin scanner, manifest fallback commands, `-RC` handshake probing, `-RC-CALL` command invocation, timeout guards, plugin-root environment setup, and dynamic `rc_*` tool synthesis.
- OpenAI-compatible, Anthropic-compatible, Google Gemini, and Ollama non-streaming model transports; OpenAI/Anthropic/Gemini tool-call extraction; one-step tool execution continuation; provider payload schema tests; retry with exponential backoff on all transports.
- Unified request tuning injection from config/provider catalog into `ChatRequest.extra_body` for `max_tokens`, `temperature`, `top_p`, `reasoning_effort`, Gemini thinking budget, and `tool_choice`.
- Streaming tool-call delta parsing is covered by mock SSE tests for OpenAI, Anthropic, and Gemini.
- `web_fetch` returns readable extracted text instead of raw HTML by default, with script/style/navigation noise stripped.
- SDK bridge streaming chat emits incremental JSONL frames (`stream.start`, `stream.content`, `stream.tool_call`, `stream.end`, `stream.recovered`) and final `chat.complete`.
- CLI integration tests for `--version`, `--index-only`, prompt mode, and report JSON; engine-lite and tool-entry tests for runtime project scaffold/update.
- Dashboard parity helpers for workspace totals, lifecycle audit summaries, and deterministic P0 agent regression reports.
- Reverie UI launch order prefers Rust `reverie.exe --sdk-bridge` with Python fallback.
- GitHub Actions now builds Rust `dist/reverie.exe` for release packaging.

## New Crates Added (Deep Refactoring)

### reverie-mcp
- Full MCP (Model Context Protocol) client implementation with stdio transport
- MCP server implementation for exposing Reverie capabilities
- Type definitions following MCP specification 2024-11-05
- Registry for managing multiple MCP servers
- Support for tools, resources, prompts, and logging
- Based on Codex CLI architecture research

### reverie-skills
- Codex-style skill discovery from multiple scopes (current, parent, repo, user, system)
- SKILL.md file parsing with YAML frontmatter
- Skill loader with caching
- Skill executor for running multi-step workflows
- Built-in skill support (placeholder)

### reverie-subagents
- Subagent definition system (TOML-based)
- Subagent manager with concurrency control
- Built-in subagent types: default, worker, explorer
- Parallel execution support
- Depth and thread limits
- Spawn/cancel/status operations

### reverie-plugins
- Plugin manifest (plugin.json) handling
- Plugin manager with install/activate/deactivate/uninstall
- Support for Git, local, and registry sources
- Component references (skills, MCP servers, agents)
- Installation policies (InstalledByDefault, Available, NotAvailable)

## Still Migrating

- Native text-to-image generation runtime (currently diagnostic PPM only).
- Full Godot/O3DE/Blender runtime adapter code generation (pipeline state management is implemented, but adapter-specific codegen is pending).
- Agent context compaction is fully wired: `compact_session_messages()` with configurable strategy (SlidingWindow/Summary/ImportanceBased/Adaptive), max_messages, max_tokens, keep_start, keep_end; tool-call/tool-result pairs are never split.
- `web_search` now performs real DuckDuckGo HTML lite scraping with title/url/snippet extraction and automatic fallback.
- SDK bridge emits `tool_call.start` and `tool_call.complete` JSONL frames during multi-turn agent tool loops via `ModelStreamEvent::ToolExecStart`/`ToolExecComplete`.

## Recently Completed (P0 Request/Streaming/Web Fetch Round)

### Request Configuration Injection
- `build_request_extra_body()` merges config extras with provider catalog metadata.
- Provider output limits now seed `max_tokens`, with user config overrides for `max_tokens` / `max_output_tokens`.
- `temperature`, `top_p`, `reasoning_effort`, Gemini `thinking_budget`, and `tool_choice` are passed through to provider payload builders where supported.
- Unit tests cover catalog defaults, config overrides, Gemini thinking budget, and provider-specific payload mapping.

### Streaming Tool-Call Coverage
- Mock SSE helpers now test OpenAI text streams, OpenAI tool-call argument deltas, Anthropic `content_block_start` + `partial_json`, and Gemini mixed text + `functionCall` parts.
- Streaming tool-call parsing is treated as implemented with regression coverage rather than a migration gap.

### Web Fetch Readability
- `web_fetch` now extracts readable text from HTML, strips non-content sections, decodes common entities, and collapses whitespace.
- Unit tests cover script/style stripping, nav/header/footer removal, entity decoding, whitespace handling, and empty input.

### SDK Bridge Streaming
- Streaming chat requests on the JSONL bridge emit incremental frames during model streaming and return a final `chat.complete` payload.
- The bridge keeps non-streaming chat behavior compatible while enabling UI-side live rendering.

## Recently Completed (LLM Transport & Mode Prompts)

### Complete Multi-Provider API Support
- **Retry with exponential backoff**: Generic `with_retry` wraps all provider transports; retries on HTTP 429/500/502/503/504 and network errors with doubling delay (500ms base).
- **Google Gemini transport**: Full `send_gemini_compatible` and `stream_gemini_compatible` supporting `generativelanguage.googleapis.com/v1beta`, API key in query param, `?alt=sse` streaming, `systemInstruction`, `contents[].parts`, `functionDeclarations`, and `thinkingConfig`.
- **Ollama local transport**: Full `send_ollama_compatible` targeting `http://localhost:11434/v1` with OpenAI-compatible format, no auth required, reuses `stream_openai_compatible` for streaming.
- **Unified streaming router**: `send_model_streaming_compatible` routes Gemini to its own SSE parser, NVIDIA/Codex/Ollama through `stream_openai_compatible`, and ModelScope through `stream_anthropic_compatible`.
- **Provider API key resolution**: `api_key_for_model` handles nvidia, modelscope, codex/openai, gemini/google, anthropic, and ollama (no-auth) providers.
- **Gemini payload builder**: Converts ChatMessages to Gemini `contents[]` format with `systemInstruction`, tool function calls as `functionCall`/`functionResponse` parts, and `generationConfig`.
- **Gemini extractors**: `extract_gemini_output_text` and `extract_gemini_tool_calls` parse Gemini's `candidates[0].content.parts[]` response format.

### Provider Catalogs Expanded
- **Gemini catalog**: gemini-2.5-pro (1M context), gemini-2.5-flash (1M context), gemini-2.0-flash (1M context, no thinking).
- **Ollama catalog**: llama3.3, qwen3, deepseek-r1, codestral with appropriate context/output limits.
- **`resolve_model`** updated to route "gemini"/"google" and "ollama"/"local" providers.

### Complete Tool Parameter Schemas
- All 30+ builtin tools now have full JSON Schema parameter definitions in `builtin_tool_parameter_schema`.
- Covers: file_ops, create_file, delete_file, str_replace_editor, command_exec, codebase-retrieval, git-commit-retrieval, count_tokens, switch_mode, web_fetch, web_search, task_manager, skill_lookup, list_mcp_resources, read_mcp_resource, text_to_image, subagent, userInput, tool_catalog, game_design_orchestrator, game_gdd_manager, game_playtest_lab, game_asset_manager, game_asset_packer, game_config_editor, game_balance/math/stats_analyzer, game_project_scaffolder, reverie_engine, game_modeling_workbench, atlas_delivery_orchestrator, novel_context_manager, consistency_checker, plot_analyzer, ask_clarification, task_boundary, notify_user, computer_control, story_design, level_design.

### Mode-Specific System Prompts
- Each of the 8 modes (Reverie, ReverieAtlas, ReverieGamer, ReverieAnt, SpecDriven, SpecVibe, Writer, ComputerController) now has a dedicated `system_prompt()` method defining its behavioral persona and tool usage guidance.
- System prompt is injected as the first message in the conversation, before user rules.

## Recently Completed (Integration Round)

### Agent Core Integration
- **Multi-turn tool execution loop**: Up to 25 rounds of LLM ↔ tool-call cycles with automatic continuation until the model produces a text-only response.
- **MCP tool injection**: Connected MCP server tools are discovered via the registry and merged into the LLM tool definitions alongside builtins.
- **Sandbox enforcement**: File and command tools are checked against `SandboxPolicy` before execution when sandbox mode is enabled.
- **Subagent nested execution**: `subagent` tool spawns a real nested `ReverieAgent.run_prompt_once()` call, registers the run in `SubagentManager` (with `Mutex<SubagentManager>` for interior mutability), and records completion/failure with output text. Recursive async is resolved via `Box::pin`.
- **Skill execution with tool invocation**: `SkillExecutor.execute_step()` now runs shell commands, reads files, and writes files. `parse_skill_instructions` extracts fenced code blocks (`bash`/`sh`/`cmd`), `@read`/`@write` directives, and numbered step headers. Variable expansion for `{{project_root}}`, `{{cwd}}`, `{{skill_name}}`, and custom arguments.

### Writer Tools (Functional)
- **novel_context_manager**: Persistent memory at `artifacts/writer/novel_memory.json` with characters, locations, timeline, threads, chapters, world rules. Actions: add_character, update_character, add_location, add_timeline_event, add_thread, resolve_thread, add_chapter, update_chapter, search, summary.
- **consistency_checker**: Validates memory for unnamed characters, unresolved threads, empty timelines, locationless characters.
- **plot_analyzer**: Arc progression, thread density, pacing metrics, tension estimation from memory data.

### Atlas Delivery Orchestrator (Functional)
- Persistent state at `artifacts/atlas_delivery_state.json` (schema v2).
- Actions: status, add_slice, update_slice, add_blocker, resolve_blocker, checkpoint, add_milestone, register_document.
- Summary includes progress percentage, open blocker count, delivery status.

### Gamer Production Pipeline (Functional)
- **game_design_orchestrator**: Persistent state with pipeline stages (design → prototype → vertical slice → playtest → polish), system registry, runtime target configs, verification checks with score. Actions: compile_request, add_system, advance_stage, set_runtime_target, verify, status.
- **game_gdd_manager**: Persistent GDD (v2) with sections, systems, content pillars, milestones, revision history. Actions: create, update_section, add_system, add_content_pillar, status.
- **game_playtest_lab**: Persistent playtest state with test plans, individual checks, quality gates, automatic score calculation. Actions: create_test_plan, add_check, run_check, add_quality_gate, status.
- **game_asset_manager**: Persistent asset pipeline with registration, update, list/filter by type, per-type stats. Actions: add, update, list, set_notes, status.
- **game_analysis_tool** (balance_analyzer, math_simulator, stats_analyzer): Persistent analysis state with datasets and simulation runs. Actions: analyze, add_dataset, simulate, status.

## P0 Rust Migration Completed

- UI bridge bootstrap now accepts Python UI payloads such as `projectRoot` and returns the dashboard-ready `state` event with config, session, tool, totals, and runtime summaries.
- Python UI camelCase actions are covered for settings, plugins, tools, totals, regression, and workspace indexing: `getState`, `setWorkspace`, `setMode`, `listSettings`, `setSetting`, `listPlugins`, `refreshPlugins`, `listTools`, `getTotals`, `runAgentRegression`, and `indexWorkspace`.
- P0 dashboard events now include `settings`, `plugins`, `tools`, `totals`, `index.started`, `index.complete`, `agent.regression.started`, and `agent.regression.complete`.
- Agent rules parity is implemented through native Rust rules discovery, parsing, ranking, and prompt injection.
- Agent regression smoke coverage verifies workspace reads, visible directory creation, write-boundary protection, and core tool schema visibility.
- File operation directory creation now uses the writable workspace join path so new directories can be created while traversal protection remains enforced.

## Summary of Completed Work

### Round 1: TUI, LSP, Sandbox
- **reverie-tui**: Full TUI with ratatui, event handling, message display, input box, tool panels, session management, overlays
- **reverie-lsp**: LSP 3.17.0 types, client with document sync, manager for multi-server, transport layer
- **reverie-sandbox**: Policy-based access control, file/network rules, process/resource limits, audit logging

### Round 2: Core Enhancements
- **reverie-core (context_compaction)**: Multiple strategies, importance scoring, token estimation
- **reverie-core (streaming)**: SSE processing, streaming events, usage extraction, aggregation
- **reverie-subagents (manager)**: Complete manager with concurrency control, lifecycle, spawn helpers

### Total Code Added
- ~5,500+ lines across 15+ new files and major rewrites
- 3 test files with comprehensive unit tests
- Updated documentation (README.md, PARITY.md)
- 100 workspace tests passing, clippy clean with `-D warnings`

## Newly Implemented (Round 2)

### Context Compaction (`reverie-core`)
- Multiple compaction strategies: sliding window, summary, importance-based, adaptive
- Importance scoring for messages (recency, tool calls, code content)
- Configuration for max messages, tokens, keep start/end
- Token estimation utilities
- Comprehensive unit tests

### Streaming (`reverie-core`)
- SSE (Server-Sent Events) stream processing
- Streaming event types: Start, Content, ToolCall, End, Error
- Usage information extraction
- Streaming result aggregation
- Message conversion from streaming events
- Async channel-based event handling

### Subagent Manager (`reverie-subagents`)
- Complete subagent manager implementation
- Concurrency control (max threads, max depth)
- Run lifecycle: spawn, complete, fail, cancel
- Status tracking: Pending, Running, Completed, Failed, Cancelled
- Wait with timeout support
- Cleanup of old runs
- Spawn helpers for default/worker/explorer subagents
- Nested subagent spawning

## Newly Implemented

### reverie-tui
- Full TUI rendering with ratatui
- Event handling system with keyboard shortcuts
- Message display with role-based styling
- Input box with cursor management
- Tool call panels
- Session list management
- Help, settings, and history overlays
- Status bar with real-time information
- Search functionality
- Copy, save, load, delete operations
- Thread-safe event handling

### reverie-lsp
- Complete LSP 3.17.0 type definitions
- LSP client with initialization, document sync, diagnostics
- LSP manager for multi-server management
- Transport layer with stdio communication
- Support for: initialize, didOpen, didChange, didClose, didSave
- Request-response matching
- Diagnostic streaming
- File-to-server mapping

### reverie-sandbox
- Complete sandbox policy system
- File access rules with read/write/deny modes
- Network access rules with host/port filtering
- Process limits (CPU, memory, threads, commands)
- Resource limits (files, signals, locks)
- Audit logging for all operations
- Platform-specific implementations (Windows, Linux, macOS)
- Sandbox manager with instance lifecycle

## Local Verification

- `cargo fmt --check`: passing.
- `cargo clippy --workspace --all-targets -- -D warnings`: passing.
- `dotnet build "Reverie UI.slnx"`: passing.
- `cargo test --workspace`: 117 tests passing.
- `cargo run -p reverie-cli -- --version`: passing.
- `cargo run -p reverie-cli -- --index-only .`: passing.
- `cargo run -p reverie-cli -- --sdk-bridge .` JSONL smoke: passing.
