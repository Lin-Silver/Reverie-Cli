# ReverieCli-Rs

Native Rust rewrite workspace for Reverie CLI.

This implementation establishes the Rust crate boundaries, compatible command
line surface, JSONL SDK bridge, configuration model, mode/tool registry,
context indexer, and engine-lite data contracts. It intentionally avoids
importing or embedding the Python runtime.

See [docs/PARITY.md](docs/PARITY.md) for the current migration tracker.

## Workspace Structure

```
crates/
├── reverie-cli/          # CLI entry point
├── reverie-core/         # Core functionality (LLM, config, session, streaming)
├── reverie-context/      # Context engine (indexing, caching, retrieval)
├── reverie-tools/        # Built-in tools (file ops, commands, web, etc.)
├── reverie-engine-lite/  # Engine-lite for game development
├── reverie-mcp/          # Model Context Protocol implementation
├── reverie-skills/       # Skill system (Codex-style workflows)
├── reverie-subagents/    # Subagent management
├── reverie-plugins/      # Plugin lifecycle and management
├── reverie-tui/          # Terminal User Interface (ratatui)
├── reverie-lsp/          # Language Server Protocol integration
└── reverie-sandbox/      # Secure sandbox execution environment
```

## Features Implemented

### Core
- ✅ CLI with compatible flags
- ✅ JSONL SDK bridge
- ✅ Configuration management
- ✅ Mode and tool registry
- ✅ Context indexing and retrieval
- ✅ Session management with checkpoints
- ✅ Streaming response handling
- ✅ Provider transports (OpenAI, Anthropic, Ollama, vLLM)
- ✅ Tool execution framework

### MCP (Model Context Protocol)
- ✅ Full MCP 2024-11-05 specification
- ✅ Client and server implementations
- ✅ Multi-server registry
- ✅ Tools, resources, prompts support

### Skills
- ✅ Codex-style skill discovery
- ✅ SKILL.md parsing with YAML frontmatter
- ✅ Skill executor with tool invocation

### Subagents
- ✅ Subagent definition and management
- ✅ Concurrency control (max threads, max depth)
- ✅ Run lifecycle: spawn, complete, fail, cancel
- ✅ Status tracking: Pending, Running, Completed, Failed, Cancelled
- ✅ Wait with timeout support
- ✅ Spawn helpers for default/worker/explorer subagents
- ✅ Nested subagent spawning

### Plugins
- ✅ Plugin manifest handling
- ✅ Install/activate/deactivate/uninstall
- ✅ Git, local, and registry sources

### TUI
- ✅ Full TUI rendering with ratatui
- ✅ Event handling with keyboard shortcuts
- ✅ Message display with role-based styling
- ✅ Input box with cursor management
- ✅ Tool call panels
- ✅ Session management
- ✅ Help, settings, history overlays

### LSP
- ✅ LSP 3.17.0 type definitions
- ✅ LSP client with document sync
- ✅ LSP manager for multi-server
- ✅ Transport layer

### Sandbox
- ✅ Policy-based access control
- ✅ File and network access rules
- ✅ Process and resource limits
- ✅ Audit logging

## Quick checks

```powershell
cargo fmt --check
cargo test --workspace
cargo run -p reverie-cli -- --version
cargo run -p reverie-cli -- --index-only .
cargo run -p reverie-cli -- -p "status" --report-file artifacts/prompt_report.json
```

## Development

### Building

```powershell
cargo build --release
```

### Testing

```powershell
cargo test --workspace
cargo test -p reverie-tui
cargo test -p reverie-lsp
cargo test -p reverie-sandbox
```

### Linting

```powershell
cargo clippy --workspace --all-targets -- -D warnings
```

### Formatting

```powershell
cargo fmt --all
```

## License

MIT
