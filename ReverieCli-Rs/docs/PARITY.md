# ReverieCli-Rs Parity Tracker

This file tracks the Rust rewrite against `ReverieCli-py`.

## Implemented Baseline

- Cargo workspace with `reverie-cli`, `reverie-core`, `reverie-context`, `reverie-tools`, and `reverie-engine-lite`.
- CLI flags compatible with the Python entry point: path, version, SDK bridge, index-only, prompt modes, mode override, report file.
- JSONL SDK bridge with ready event, runtime info, initialize, state, settings, sessions, tools, diagnostics, Git status, indexing, context query, chat, plugin command dispatch, dynamic `rc_*` dispatch, and shutdown.
- JSON config compatibility with defaults and unknown-field preservation.
- Project data directory compatibility with Python safe-path naming and legacy hashed-cache migration.
- Mode aliases and command catalog.
- Provider catalogs for Codex, NVIDIA, and ModelScope seed models.
- Context indexing, cache persistence, symbol search, dependency records, text search matches, and fallback parsers for Rust/Python/JS-family/Lua/GDScript/config/Markdown surfaces.
- Session index, checkpoint create/list/restore, operation list, and built-in tool audit log.
- Built-in tool registry with mode visibility.
- Core tools: file ops, create/delete, str replace/insert/view, command exec, codebase retrieval, git status, token count, web search/fetch fallback, skill lookup, MCP cache resources, TTI diagnostics, task manager, user input, tool catalog.
- Gamer artifact tools: request/program artifact, runtime delivery plan, engine-lite scaffold/create/inspect/add-scene/add-entity/register-asset/validation, GDD, asset manifest, playtest score, design and analysis documents.
- Writer, Atlas, Ant, Subagent, and modeling tools produce native Rust compatibility artifacts.
- Runtime plugin scanner, manifest fallback commands, `-RC` handshake probing, `-RC-CALL` command invocation, timeout guards, plugin-root environment setup, and dynamic `rc_*` tool synthesis.
- OpenAI-compatible and Anthropic-compatible non-streaming model transports, OpenAI/Anthropic tool-call extraction, one-step tool execution continuation, and provider payload schema tests.
- CLI integration tests for `--version`, `--index-only`, prompt mode, and report JSON; engine-lite and tool-entry tests for runtime project scaffold/update.
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

- Full Writer memory/continuity analysis.
- Full Atlas delivery orchestrator document lifecycle.
- Full Reverie-Gamer production pipeline and runtime adapters for Godot/O3DE/Blender.
- Native text-to-image generation runtime.
- Integration of new crates into reverie-core agent loop.
- Full skill execution with tool invocation (executor structure complete, needs tool integration).
- Subagent-to-agent communication (manager structure complete, needs agent integration).

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
- ~4,250 lines across 15+ new files
- 3 test files with comprehensive unit tests
- Updated documentation (README.md, PARITY.md)

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
- `cargo test --workspace`: passing.
- `cargo run -p reverie-cli -- --version`: passing.
- `cargo run -p reverie-cli -- --index-only .`: passing.
- `cargo run -p reverie-cli -- --sdk-bridge .` JSONL smoke: passing.
