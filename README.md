# Reverie CLI

**Reverie** is an open-source, terminal-based agentic coding assistant that wraps large language models to enable natural language interaction with your local codebase. It combines multi-provider LLM access, a powerful Context Engine for codebase intelligence, session management, inline media support, 3D/Game modeling workflows, browser automation, and more — all in a unified terminal interface.

- **Open-source** under the MIT license
- **Multi-provider LLM** support: NVIDIA, ModelScope, Codex (ChatGPT), Gemini, Ollama, AIHubMix, Agnes, WebGemini
- **Multiple modes**: General coding, spec-driven development, game production, creative writing, computer control, and more
- **Context Engine**: Augment-style codebase retrieval, LSP integration, git history analysis
- **Session management**: Conversation persistence, rotation, working memory injection, handoff packets
- **Inline media**: Attach images and video directly in conversations
- **3D/Game workflows**: Built-in Blender authoring, Blockbench `.bbmodel` validation, Godot project integration, Ashfox MCP support
- **Browser automation**: Embedded Chromium runtime for web inspection and interaction
- **Subagent delegation**: Parallel investigation and implementation tasks
- **Harness audit**: Prompt-level reporting, verification tracking, playbook recommendations

---

## Table of Contents

1. [Key Features](#key-features)
2. [Architecture Overview](#architecture-overview)
3. [Installation & Setup](#installation--setup)
4. [Quick Start](#quick-start)
5. [Configuration](#configuration)
6. [Modes](#modes)
7. [LLM Providers & Models](#llm-providers--models)
8. [CLI Usage](#cli-usage)
9. [Context Engine](#context-engine)
10. [Session Management](#session-management)
11. [Advanced Features](#advanced-features)
12. [API Reference](#api-reference)
13. [Troubleshooting](#troubleshooting)
14. [Contributing](#contributing)
15. [License](#license)

---

## Key Features

### Multi-Provider LLM Access

Reverie supports a wide range of LLM providers out of the box. Each provider has its own configuration section in `config.json`:

| Provider | Description | Key Models |
|----------|-------------|------------|
| **NVIDIA** | NVIDIA-hosted catalog via `integrate.api.nvidia.com` | Qwen3.5 397B, DeepSeek V4 Pro, Kimi K2.6, GLM-5.1, MiniMax M2.7/M3, Mistral Small 4, Mistral Medium 3.5, Step-3.7-Flash, GPT-OSS-120B, Nemotron 3 Super |
| **ModelScope** | Zhipu-hosted models via ModelScope | GLM-5.1, DeepSeek V4 Pro, Kimi K2.6, Qwen3.5 397B A17B |
| **Codex** | ChatGPT backend (OpenAI-compatible Responses API) | GPT-5.5, GPT-5.4, GPT-5.4-Mini, GPT-5.3-Codex, GPT-5.2 |
| **Gemini** | Google Gemini via API | Gemini 2.5 Pro, Gemini 2.5 Flash, Gemini 2.0 Flash |
| **Ollama** | Local models via Ollama | Llama 3.3 70B, Qwen3, DeepSeek R1, Codestral |
| **AIHubMix** | Third-party API gateway | Various models via AIHubMix |
| **Agnes** | Agnes image/video generation backend | Image generation models, video generation |
| **WebGemini** | Web-based Gemini access | Gemini models via web interface |

All providers support streaming responses where applicable. Reasoning/thinking toggles, temperature, top_p, max_tokens, and other parameters are configurable per provider.

### Operating Modes

Reverie ships with specialized modes that change tooling, system prompt rules, and domain focus:

| Mode | Display Name | Description |
|------|-------------|-------------|
| `reverie` | Reverie | Default general coding and automation mode. Context Engine retrieval, core workspace tools, Blender/3D modeling. |
| `reverie-atlas` | Reverie-Atlas | Document-driven spec development. Deep research paired with Context Engine and Atlas delivery artifacts. |
| `reverie-gamer` | Reverie-Gamer | Full game production: blueprints, system packets, vertical slices, playtest loops, modeling pipelines. |
| `reverie-ant` | Reverie-Ant | Structured long-running execution: planning, checkpoints, verification. |
| `spec-driven` | Spec-Driven | Spec authoring: requirements, design, implementation task breakdown. |
| `spec-vibe` | Spec-Vibe | Implementation mode for executing approved specs with a lighter workflow. |
| `writer` | Writer | Creative writing: narrative drafting, continuity, long-form documentation. |
| `computer-controller` | Computer Controller | Pinned NVIDIA desktop-autopilot mode for operating the Windows UI. Non-switchable; requires NVIDIA source. |

### Context Engine

Reverie includes an Augment-style codebase intelligence layer that retrieves a small, relevant workset instead of flooding the prompt with the entire repository:

- **`codebase-retrieval`**: Primary entrypoint — query by task, file, symbol, search, dependencies, outline, memory, or LSP
- **Git integration**: Commit history, blame, prior fixes, uncommitted state inspection via `git-commit-retrieval`
- **LSP bridge**: On-demand language server protocol integration for diagnostics, definitions, workspace symbols
- **Workspace global memory**: Persistent memory across sessions with decay-based ranking
- **Memory OS**: Structured memory items (preferences, decisions, failure experiences, success workflows) with correction and consolidation support

### Session Management

Sessions provide conversation persistence, automatic rotation, and working memory injection:

- **Automatic session rotation** at 80% token threshold
- **Working memory injection**: Compressed session summaries carried forward into new sessions
- **Handoff packets**: Structured JSON artifacts for cross-session continuity
- **Session archiving**: Full transcripts preserved before compaction
- **Checkpoint and resume**: Save/restore sessions by ID
- **Workspace-scoped sessions**: Each project root gets its own session namespace

### Inline Media

Attach images and videos directly in conversations:

- Supported image extensions: `.png`, `.jpg`, `.jpeg`
- Supported video extensions: (configurable via `inline_images.py`)
- Parse `@media_mentions` in messages for inline display
- Flatten multimodal content for both agent API and terminal display
- Automatic attachment notices appended to user text blocks

### 3D / Game Modeling

Reverie-Gamer mode includes a full modeling pipeline:

- **Blender integration**: Built-in Blender authoring workflow — generate scripts, run in background mode, export `.blend`/`.glb`/`.gltf`, render previews
- **Blockbench `.bbmodel`**: Headless validation and export without launching Blockbench
- **Ashfox MCP**: Live Blockbench automation via the Ashfox plugin (when running)
- **Model registry sync**: Auto-generate `model_registry.yaml` from `assets/models/` directories
- **Godot integration**: Project scanning, headless import validation, editor launch
- **Source/Runtime separation**: `assets/models/source/` for authoring, `assets/models/runtime/` for engine-facing exports

### Browser Automation

Embedded Chromium runtime for non-disruptive web interaction:

- Open pages, run DevTools, inspect DOM/network/console
- Selector-based click, type, upload, wait actions
- Screenshot capture, accessibility snapshots, DOM outlines
- Background/minimized sessions for non-blocking operations
- Import user cookie/storage state into embedded profiles

### Harness & Verification

Built-in prompt engineering audit trail:

- **Prompt harness guidance**: Automatic verification hints (test, lint, build, typecheck, e2e)
- **Failure playbooks**: Categorize tool failures (schema mismatch, workspace boundary, missing dependency, timeout)
- **Session audit log**: Every prompt run recorded with tool usage and outcomes
- **Task checklist parsing**: Recognize `[ ]`, `[/]`, `[x]`, `[-]` markers in output for progress tracking

### Rules Engine

Custom rule files can define:

- Project-specific coding standards
- File-type-specific handling rules
- Mode-specific rule injection
- Rule management via `RulesManager` with YAML/JSON rule definitions

---

## Architecture Overview

```
Reverie-Cli/
├── README.md                  ← You are here
├── CHANGELOG.md               ← Version history
├── Cargo.toml                 ← Rust workspace manifest
├── dist/
│   ├── reverie.exe            ← Windows executable
│   └── ...
├── ReverieCli-py/             ← Python source (primary runtime)
│   └── reverie/
│       ├── __main__.py        ← Entry point
│       ├── config.py          ← Configuration management
│       ├── harness.py         ← Prompt audit & verification
│       ├── modes.py           ← Mode registry
│       ├── session/
│       │   └── manager.py     ← Session persistence
│       ├── agent/
│       │   ├── agent.py       ← Core agent loop
│       │   ├── subagents.py   ← Subagent delegation
│       │   ├── system_prompt.py← System prompt building
│       │   └── tool_executor.py← Tool execution
│       ├── cli/
│       │   └── interface.py   ← Terminal UI (Rich-based)
│       ├── llm/               ← LLM client implementations
│       ├── context_engine/    ← Codebase retrieval, LSP, memory
│       ├── memory/            ← Memory OS
│       ├── tools/             ← Tool definitions & registry
│       ├── engine_lite/       ← Modeling pipeline helpers
│       ├── nvidia.py          ← NVIDIA provider integration
│       ├── codex.py           ← Codex provider integration
│       ├── modelscope.py      ← ModelScope provider integration
│       ├── webgemini.py       ← WebGemini provider integration
│       ├── agnes.py           ← Agnes media provider
│       ├── aihubmix.py        ← AIHubMix provider
│       ├── mcp.py             ← MCP runtime
│       ├── inline_images.py   ← Inline media support
│       ├── skills_manager.py  ← Skills system
│       └── ...
│       └── builtin_skills/    ← Bundled skills
├── ReverieCli-Rs/             ← Rust crates
│   └── crates/
│       ├── reverie-core/      ← Core types, providers, modes
│       ├── reverie-cli/       ← CLI binary
│       ├── reverie-tui/       ← Terminal UI (Rust)
│       ├── reverie-context/   ← Context engine (Rust)
│       ├── reverie-tools/     ← Tool definitions
│       ├── reverie-mcp/       ← MCP client
│       ├── reverie-skills/    ← Skills runtime
│       ├── reverie-sandbox/   ← Sandboxed execution
│       └── ...
└── API.md                     ← Provider API documentation
```

### Technology Stack

| Component | Technology |
|-----------|-----------|
| Primary Runtime | Python 3.x with `asyncio` / `tokio` |
| Terminal UI | Rich (Python) / Crossterm (Rust) |
| LLM Transport | HTTP/SSE via `reqwest` / `requests` / OpenAI SDK |
| Configuration | JSON with atomic writes, secure file permissions |
| Git Integration | `git2` (Rust) / subprocess (Python) |
| 3D/Modeling | Blender Python API (`bpy`), Blockbench `.bbmodel` |
| Browser | Embedded Chromium via Playwright/DevTools Protocol |
| Serialization | `serde` / `serde_json` / `toml` / `yaml-rust` |

---

## Installation & Setup

### Prerequisites

- **Python 3.10+** (for Python runtime)
- **Rust 1.70+** (for building Rust components, optional)
- **Git** (for session history and Context Engine)
- **Windows 10/11** (primary target; Linux/macOS supported with minor adjustments)
- **PowerShell** (Windows) or Bash (Unix)

### Install from Source (Python)

```powershell
# Clone the repository
git clone https://github.com/your-org/Reverie-Cli.git
cd Reverie-Cli

# Create and activate a virtual environment
py -m venv venv
.\venv\Scripts\Activate.ps1

# Install dependencies
py -m pip install --upgrade pip
py -m pip install -r ReverieCli-py\requirements.txt

# Run Reverie
py -m reverie
```

### Install from Source (Rust)

```powershell
cd ReverieCli-Rs
cargo build --release
.\target\release\reverie.exe
```

### Pre-built Executable

Download the latest `reverie.exe` from the `dist/` directory and run it directly. No Python installation required.

### First-Run Setup

On first launch, Reverie guides you through a setup wizard:

1. **Select an LLM provider** — choose from NVIDIA, Codex, Gemini, Ollama, etc.
2. **Configure API keys** — enter your provider API key (stored securely in `config.json`)
3. **Select a default model** — pick from the provider's catalog
4. **Choose a workspace** — set your project root directory

Configuration is stored per-project in `.reverie/config.json` and globally in `%APPDATA%\Reverie\config.json`.

---

## Quick Start

```powershell
# Start Reverie in the current directory
reverie

# Start with a specific mode
reverie --mode reverie-atlas

# Start with a specific provider/model
reverie --provider nvidia --model qwen/qwen3.5-397b-a17b

# Resume the last session
reverie --resume
```

Once inside the CLI:

- Type naturally to chat with the AI assistant
- Use `/help` to see available commands
- Use `/tools` to inspect available tools
- Use `/mode <name>` to switch modes mid-session
- Use `/session list` to browse saved sessions
- Attach files by referencing them in your message (e.g., "review `src/main.py`")

---

## Configuration

### Configuration File

Reverie uses `config.json` stored in the project's `.reverie/` directory or the global app data folder. Key sections:

```json
{
  "version": "0.1.0",
  "active_model_source": "nvidia",
  "standard": {
    "base_url": "http://localhost:11434/v1",
    "api_key": "",
    "model": "llama3.3",
    "provider": "ollama"
  },
  "nvidia": {
    "enabled": true,
    "api_key": "nvapi-...",
    "selected_model_id": "qwen/qwen3.5-397b-a17b",
    "selected_model_display_name": "Qwen3.5 397B A17B",
    "api_url": "https://integrate.api.nvidia.com/v1",
    "max_context_tokens": 262144,
    "timeout": 60,
    "max_tokens": 16384,
    "temperature": 0.60,
    "top_p": 0.95,
    "enable_thinking": true,
    "reasoning_effort": "high",
    "reasoning_budget": 16384
  },
  "codex": {
    "selected_model_id": "gpt-5.5",
    "api_url": "https://chatgpt.com/backend-api/codex",
    "reasoning_effort": "medium",
    "timeout": 1200
  },
  "ollama": {
    "base_url": "http://localhost:11434",
    "model": "llama3.3",
    "timeout": 120
  },
  "gemini": {
    "api_key": "",
    "model": "gemini-2.5-pro",
    "timeout": 120
  },
  "tool_output_style": "compact",
  "thinking_output_style": "full",
  "tts_provider": "none",
  "stt_provider": "none"
}
```

### Configuration Options

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `active_model_source` | string | `"standard"` | Active provider: `standard`, `nvidia`, `codex`, `gemini`, `ollama`, `aihubmix`, `agnes`, `modelscope`, `webgemini` |
| `tool_output_style` | string | `"compact"` | Tool result display: `compact`, `condensed`, `full` |
| `thinking_output_style` | string | `"full"` | Reasoning display: `hidden`, `compact`, `full` |
| `nvidia.enable_thinking` | bool | `true` | Enable provider-side thinking for NVIDIA models |
| `nvidia.reasoning_effort` | string | `"high"` | Reasoning depth: `max`, `high`, `medium`, `low`, `none` |
| `codex.reasoning_effort` | string | `"medium"` | Codex effort: `minimal`, `low`, `medium`, `high`, `xhigh` |
| `ollama.base_url` | string | `"http://localhost:11434"` | Ollama server URL |

---

## Modes

Switch modes with `/mode <name>` or `--mode` at launch.

### Reverie (default)

General-purpose coding and automation. Full Context Engine, all workspace tools, Blender modeling, browser control.

### Reverie-Atlas

Document-driven development for complex systems. Produces structured specs, architecture documents, and delivery artifacts. Focus tools: `codebase-retrieval`, `create_file`, `command_exec`.

### Reverie-Gamer

Full game production pipeline:
- **Game Design Orchestrator**: Plan games from concept to vertical slice
- **Game Project Scaffolder**: Generate project structures
- **Game GDD Manager**: Game Design Document management
- **Game Asset Manager**: Asset pipeline and registry
- **Game Balance Analyzer**: Economy and combat balance analysis
- **Game Math Simulator**: Probability and combat simulation
- **Level Design**: Level layout and flow tools
- **Story Design**: Narrative and quest design tools
- **Game Playtest Lab**: Playable slice verification
- **Blender/Blockbench modeling**: Full 3D asset pipeline

### Reverie-Ant

Structured long-running execution with:
- Task boundary management
- Checkpoint and resume
- Progress notifications
- Verification loops

### Spec-Driven

Requirements → Design → Implementation task breakdown. Produces `.reverie/specs/` artifacts.

### Spec-Vibe

Execute approved specs with lighter workflow. Implements the `spec-driven` output.

### Writer

Creative writing mode with:
- Novel context management
- Consistency checking
- Plot analysis
- Character/arc tracking

### Computer Controller

Desktop automation via NVIDIA's computer_control capability. Pinned to NVIDIA provider, non-switchable.

---

## LLM Providers & Models

### NVIDIA (Recommended for High-Throughput)

NVIDIA's hosted API at `integrate.api.nvidia.com` provides access to dozens of models. Key configurations:

**Transport types:**
- `request` — Direct HTTP POST with chat-template kwargs (for models like Kimi K2.6, MiniMax M3, Qwen3.5)
- `openai-sdk` — OpenAI-compatible SDK transport (for models like DeepSeek V4 Pro, GLM-5.1)

**Thinking control:**
- `toggle` — Binary on/off (Qwen3.5, GLM-5.1, Kimi K2.6)
- `effort` — Selectable levels: `none`/`low`/`medium`/`high`/`max` (DeepSeek V4 Pro, Mistral models, GPT-OSS-120B)
- `fixed` — Always-on thinking (Step models)

**Vision models:** MiniMax M3, Mistral Small 4, Mistral Medium 3.5, Qwen3.5 122B, Kimi K2.6 support image and video input.

### Codex (ChatGPT Backend)

Connects to ChatGPT's backend API. Supports:
- OAuth login via `~/.codex/auth.json` (auto-detected)
- Responses API format with reasoning effort control
- Vision input support
- Model catalog loaded from local Codex source or CLI cache

### Gemini

Google Gemini models with thinking and tool use:
- `gemini-2.5-pro` — 1M context, thinking, vision
- `gemini-2.5-flash` — 1M context, fast reasoning
- `gemini-2.0-flash` — 1M context, 8K output limit

### Ollama

Local model serving:
- `llama3.3` (70B)
- `qwen3` (with thinking)
- `deepseek-r1` (reasoning)
- `codestral` (code-optimized)

---

## CLI Usage

### Command-Line Arguments

```
reverie [OPTIONS]

Options:
  --mode <MODE>            Start in a specific mode (reverie, atlas, gamer, etc.)
  --provider <PROVIDER>    Override active provider (nvidia, codex, gemini, ollama...)
  --model <MODEL>          Override selected model
  --resume                 Resume last active session
  --session <ID>           Load a specific session by ID
  --workspace <PATH>       Set project workspace directory
  --no-stream              Disable streaming responses
  --verbose                Enable verbose output
  --help                   Show help message
```

### Interactive Commands

| Command | Description |
|---------|-------------|
| `/help` | Show available commands |
| `/mode <name>` | Switch operating mode |
| `/session list` | List available sessions |
| `/session new [name]` | Create a new session |
| `/session load <id>` | Load a specific session |
| `/session delete <id>` | Delete a session |
| `/tools` | Inspect available tools |
| `/model <name>` | Switch to a different model |
| `/provider <name>` | Switch provider |
| `/clear` | Clear terminal screen |
| `/save` | Save current session |
| `/exit` or `/quit` | Exit Reverie |
| `/thinking on/off` | Toggle thinking display |
| `/compact` | Trigger context compaction |
| `/rules` | Manage custom rules |

---

## Context Engine

The Context Engine is Reverie's codebase intelligence layer, inspired by Augment-style retrieval.

### `codebase-retrieval` Tool

Primary entrypoint for repository queries:

```python
# Task-level retrieval (recommended first call)
codebase-retrieval(query_type="task", query="fix streaming think tag rendering")

# File-level retrieval
codebase-retrieval(query_type="file", query="reverie/agent/agent.py")

# Symbol-level retrieval
codebase-retrieval(query_type="symbol", query="ReverieAgent.run")

# Search across codebase
codebase-retrieval(query_type="search", query="def build_harness")

# Dependency analysis
codebase-retrieval(query_type="dependencies", query="SessionManager", direction="outgoing")

# Outline / structure
codebase-retrieval(query_type="outline", query="reverie/agent/")

# Memory queries
codebase-retrieval(query_type="memory", query="user preferences for model selection")

# LSP diagnostics
codebase-retrieval(query_type="lsp", query="reverie/agent/agent.py", lsp_action="diagnostics")
```

### Query Types

| `query_type` | Use Case |
|-------------|----------|
| `task` | Broad requests — returns ranked workset |
| `file` | Get file structure and contents |
| `symbol` | Detailed info about a function/class/variable |
| `search` | Search for symbols matching a pattern |
| `dependencies` | What a symbol depends on / what depends on it |
| `outline` | File/module structure overview |
| `memory` | Query workspace-global memory |
| `lsp` | LSP-powered diagnostics, definitions, symbols |

### Git Integration

```python
# File history
git-commit-retrieval(query_type="file_history", target="src/main.py", limit=10)

# Blame
git-commit-retrieval(query_type="blame", target="src/main.py", start_line=1, end_line=50)

# Search commits
git-commit-retrieval(query_type="search", target="fix login", limit=10)

# Recent commits
git-commit-retrieval(query_type="recent", limit=20)

# Uncommitted changes
git-commit-retrieval(query_type="uncommitted")
```

---

## Session Management

### Session Structure

Each session is a JSON file containing:
- `id` — Unique session identifier (timestamp-based)
- `name` — Human-readable name
- `created_at` / `updated_at` — ISO timestamps
- `messages` — Full conversation history
- `metadata` — Workspace ID, rotation info, handoff paths

### Session Rotation

When a conversation approaches the model's context limit (80% threshold), Reverie:
1. Archives the full transcript to `full_transcripts/`
2. Compresses the conversation into a working memory summary
3. Creates a new session with the summary injected as a system message
4. Optionally persists a handoff packet for structured continuity

### Session Commands (Python API)

```python
from pathlib import Path
from reverie.session.manager import SessionManager

manager = SessionManager(
    base_dir=Path(".reverie"),
    project_root=Path("."),
    memory_indexer=None,
    always_new_session=False,
    refresh_memory_index_on_save=True,
)

# Create a new session
session = manager.create_session(name="Feature Implementation")

# Save current session
manager.save_session(session)

# Load by ID
loaded = manager.load_session("20240115_143022_123456")

# List all sessions for this workspace
sessions = manager.list_sessions()

# Check rotation threshold
needs_rotation = manager.check_rotation_needed(current_tokens=200000, max_tokens=262144)

# Rotate with working memory
new_session = manager.rotate_session(
    working_memory="User is implementing auth module. Completed JWT setup.",
    reason="Token threshold reached",
    handoff_packet={"data": {"completed_tasks": ["JWT", "refresh tokens"]}},
)
```

---

## Advanced Features

### Inline Images & Video

Attach media files directly:

```
# Reference an image in your message
"Review this screenshot: @./screenshot.png"
"Here's the design: @./mockup.png and @./diagram.jpg"
```

Supported: `.png`, `.jpg`, `.jpeg`, (video extensions configurable).

### Browser Control

Use the embedded Chromium browser:

```
browser_controler(action="open_page", url="http://localhost:3000")
browser_controler(action="devtools_screenshot", port=<port>, full_page=true)
browser_controler(action="devtools_click", port=<port>, selector="button.submit")
browser_controler(action="devtools_type", port=<port>, selector="#search", text="query")
browser_controler(action="extract_page", url="https://example.com")
```

### Subagents

Delegate bounded subtasks:

```python
subagent(action="run", prompt="inspect failing test logs and summarize root cause")
```

### Memory OS

Structured long-term memory:

```python
# Query memory
memory_retrieval(query="user preferences for model selection", limit=8, explain=True)

# Manage memory items
memory_manager(action="list", query="coding standards", limit=20)
memory_manager(action="correct", memory_id="mem_abc123", content="updated preference")
memory_manager(action="delete", memory_id="mem_abc123", hard=False)
memory_manager(action="consolidate", limit=20)
```

### Harness Audit

Every prompt run is audited:

```python
# Build harness guidance
from reverie.harness import build_harness_prompt_guidance
guidance = build_harness_prompt_guidance(task_description="implement auth")

# Persist a run
from reverie.harness import persist_prompt_harness_run
persist_prompt_harness_run(task_description="...", tool_usage=[...], outcome="success")
```

### Task Manager

Checklist-first task tracking:

```python
task_manager(action="add_tasks", tasks=[
    {"target": "Implement JWT auth", "status": "todo", "priority": "high"},
    {"target": "Write tests", "status": "todo", "priority": "medium"},
])
task_manager(action="update", target="Implement JWT auth", status="doing")
task_manager(action="list")
```

---

## API Reference

### Provider Model Data Structures

```python
from reverie.providers import ProviderModel, resolve_model, all_provider_names

# Model catalog entry
model = ProviderModel(
    id="qwen/qwen3.5-397b-a17b",
    display_name="Qwen3.5 397B A17B",
    description="Qwen3.5 397B-A17B model on NVIDIA.",
    transport="request",
    context_length=262144,
    output_limit=65536,
    supports_vision=True,
    supports_thinking=True,
    provider="nvidia",
)

# Resolve a model by provider + id
resolved = resolve_model(provider="nvidia", model_id="qwen/qwen3.5-397b-a17b")

# List all provider names
providers = all_provider_names()  # ["nvidia", "modelscope", "codex", "gemini", "ollama"]
```

### NVIDIA Runtime Model Data

```python
from reverie.nvidia import build_nvidia_runtime_model_data, normalize_nvidia_config

config = normalize_nvidia_config({
    "api_key": "nvapi-...",
    "selected_model_id": "qwen/qwen3.5-397b-a17b",
})
runtime_data = build_nvidia_runtime_model_data(config)
# Returns: {
#   "model": "qwen/qwen3.5-397b-a17b",
#   "base_url": "https://integrate.api.nvidia.com/v1",
#   "api_key": "nvapi-...",
#   "provider": "request",
#   "thinking_mode": "true",
#   "supports_vision": True,
#   ...
# }
```

### Codex Runtime Model Data

```python
from reverie.codex import build_codex_runtime_model_data, detect_codex_cli_credentials

cred = detect_codex_cli_credentials()
# Auto-detects from ~/.codex/auth.json

runtime_data = build_codex_runtime_model_data({
    "selected_model_id": "gpt-5.5",
    "api_url": "https://chatgpt.com/backend-api/codex",
})
```

### Mode Normalization

```python
from reverie.modes import normalize_mode, get_mode_metadata, get_mode_tool_discovery_profile

mode = normalize_mode("atlas")  # → "reverie-atlas"
meta = get_mode_metadata("reverie-gamer")
profile = get_mode_tool_discovery_profile("reverie-gamer")
```

---

## Troubleshooting

### Common Issues

**"File not found" errors**
- Ensure you're running from the correct project root
- Check that `.reverie/` directory exists in your workspace
- Use `--workspace <PATH>` to explicitly set the project root

**LLM connection errors**
- Verify your API key is set in `config.json`
- Check network connectivity to the provider endpoint
- For Ollama: ensure `ollama serve` is running
- For NVIDIA: verify key at `https://build.nvidia.com/settings/api-keys`

**Context Engine not returning results**
- Ensure the project has been indexed (`codebase-retrieval` triggers indexing on first use)
- Check that LSP server is available for your language (optional)
- Large repositories may take time to build the initial index

**Session rotation not working**
- Verify `max_context_tokens` matches your model's context window
- Check that the session directory is writable
- Rotation threshold defaults to 80% — adjust via `session.rotation_threshold`

**Blender/3D modeling not available**
- Blender is optional — headless `.bbmodel` validation works without it
- Install Blender and ensure it's on PATH, or use `blender_modeling_workbench` with explicit `blender_path`
- Blockbench + Ashfox plugin are optional for live editing

**Windows PowerShell execution policy**
```powershell
Set-ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### Debug Mode

```powershell
# Python runtime with verbose logging
py -m reverie --verbose

# Check configuration
py -m reverie --show-config

# Verify provider connection
py -m reverie --provider nvidia --verify
```

---

## Contributing

Reverie is open-source. Contributions are welcome:

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Make your changes with tests
4. Run verification: `cargo test` (Rust) or `pytest` (Python)
5. Submit a pull request

### Development Setup

```powershell
# Python development
py -m venv venv
.\venv\Scripts\Activate.ps1
py -m pip install -r ReverieCli-py\requirements.txt
py -m pip install -r ReverieCli-py\requirements-dev.txt

# Rust development
cd ReverieCli-Rs
cargo build
cargo test
```

---

## License

MIT License — see [LICENSE](LICENSE) for details.

---

## Links

- **Repository**: https://github.com/your-org/Reverie-Cli
- **Issues**: https://github.com/your-org/Reverie-Cli/issues
- **NVIDIA API Docs**: https://build.nvidia.com
- **Claude API Docs**: https://docs.anthropic.com
- **Gemini API Docs**: https://ai.google.dev

---

*Reverie CLI — Open-source agentic coding assistant. Built with Python, Rust, and modern LLM APIs.*

//END//