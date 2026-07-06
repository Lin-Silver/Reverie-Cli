# Reverie CLI

**Reverie** is an open-source, terminal-based agentic coding assistant that wraps large language models to enable natural language interaction with your local codebase. It combines multi-provider LLM access, a powerful Context Engine for codebase intelligence, session management, inline media support, 3D/Game modeling workflows, browser automation, and more — all in a unified terminal interface.

- **Multi-provider LLM** support: NVIDIA, ModelScope, Codex (ChatGPT), SenseNova, unlimited.surf, AIHubMix, Agnes, WebGemini
- **Multiple modes**: General coding, spec-driven development, game production, creative writing, computer control, and more
- **Context Engine**: Augment-style codebase retrieval, LSP integration, git history analysis
- **Session management**: Conversation persistence, rotation, working memory injection, handoff packets
- **Inline media**: Attach images and video directly in conversations
- **3D/Game workflows**: Built-in Blender authoring, Blockbench `.bbmodel` validation, legacy Godot/O3DE inspection and migration into Reverie Engine, Ashfox MCP support
- **Browser automation**: Embedded Chromium runtime for web inspection and interaction
- **Subagent delegation**: Parallel investigation and implementation tasks
- **Harness audit**: Prompt-level reporting, verification tracking, playbook recommendations
- **Specialist runtime plugins**: Ren'Py and Live2D/Cubism Galgame workflows are delivered through plugin-owned `rc_*` tools, skills, and prompt guidance

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
16. [Links](#links)

---

## Key Features

### Multi-Provider LLM Access

Reverie supports a wide range of LLM providers out of the box. Each provider has its own configuration section in `config.json`:

| Provider | Description | Key Models |
|----------|-------------|------------|
| **NVIDIA** | NVIDIA-hosted catalog via `integrate.api.nvidia.com` | Qwen3.5 397B, DeepSeek V4 Pro/V4 Flash, Kimi K2.6, GLM-5.1/4.7, MiniMax M2.7/M3, Mistral Small 4, Mistral Medium 3.5, Mistral Large 3, Step-3.5/3.7-Flash, GPT-OSS-120B, Nemotron 3 Super, Qwen3.5 122B |
| **ModelScope** | Anthropic-compatible API on `api-inference.modelscope.cn` — all models supporting the Anthropic SDK can be used | GLM-5.1, GLM-5, DeepSeek V4 Pro, DeepSeek V4 Flash, MiniMax M2.7, Qwen3.5 397B A17B (catalog is statically defined in code) |
| **Codex** | ChatGPT backend (OpenAI-compatible Responses API) | GPT-5.5 and other ChatGPT/Codex models (auto-detected from local Codex source or CLI cache) |
| **SenseNova** | SenseTime SenseNova API with model-specific OpenAI/Anthropic transports | DeepSeek V4 Flash (1M context), SenseNova 6.7 Flash Lite (vision) |
| **unlimited.surf** | Gateway service with request transport | GPT-5 (via `unlimited.surf`), with selectable effort (low/medium/high) |
| **AIHubMix** | Third-party API gateway (OpenAI-compatible) | GPT-5.5 Free (with/without reasoning), GPT-4o Free, GPT-4.1 Free |
| **Agnes** | Agnes AI OpenAI-compatible API (text, image, video) | Agnes 2.0 Flash (vision + thinking), Agnes 1.5 Flash (vision), image/video generation |
| **WebGemini** | Anonymous Gemini Web access via `gemini.google.com` | Gemini 3.5 Flash, Gemini 3.5 Flash Thinking, Gemini 3.5 Flash Thinking Lite, Gemini 3.1 Pro, Gemini Auto, Gemini Flash Lite |

All providers support streaming responses where applicable. Reasoning/thinking toggles, temperature, top_p, max_tokens, and other parameters are configurable per provider.

### Operating Modes

Reverie ships with specialized modes that change tooling, system prompt rules, and domain focus:

| Mode | Display Name | Description |
|------|-------------|-------------|
| `reverie` | Reverie | Default general coding and automation mode. Context Engine retrieval, core workspace tools, Blender/3D modeling. |
| `reverie-atlas` | Reverie-Atlas | Document-driven spec development. Deep research paired with Context Engine and Atlas delivery artifacts. |
| `reverie-gamer` | Reverie-Gamer | ⚠️ **Work in Progress** — Full game production pipeline (blueprints, system packets, vertical slices, playtest loops, modeling pipelines). Not yet complete. |
| `reverie-ant` | Reverie-Ant | Structured long-running execution: planning, checkpoints, verification. |
| `spec-driven` | Spec-Driven | Spec authoring: requirements, design, implementation task breakdown. |
| `spec-vibe` | Spec-Vibe | Implementation mode for executing approved specs with a lighter workflow. |
| `writer` | Writer | Creative writing: persistent long-form fiction planning, serialized drafting, continuity control, and verified completion. |
| `computer-controller` | Computer Controller | Pinned NVIDIA desktop orchestrator using an embedded Open Computer Use-compatible desktop runtime and managed Reverie SubAgents. Entered explicitly; it can still hand off to another mode when the task changes. |

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

Reverie-Gamer mode currently includes a work-in-progress modeling toolchain:

- **Blender integration**: Blender plugin-assisted authoring workflow — generate scripts, run in background mode, export `.blend`/`.glb`/`.gltf`, render previews
- **Blockbench `.bbmodel`**: Headless validation and export without launching Blockbench
- **Ashfox MCP**: Live Blockbench automation via the Ashfox plugin (when running)
- **Model registry sync**: Auto-generate `model_registry.yaml` from `assets/models/` directories
- **Unified Reverie Engine**: Godot scene patterns and O3DE data/asset-pipeline patterns are integrated into the built-in runtime; existing projects can be inspected and migrated
- **Source/Runtime separation**: `assets/models/source/` for authoring, `assets/models/runtime/` for engine-facing exports
- **Galgame integration**: Reverie Engine directly inspects, validates, and imports Ren'Py scripts; the optional Ren'Py plugin is limited to native SDK lint/compile/distribute and Live2D/Cubism remains specialized

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
├── comfy/                     ← ComfyUI image generation (embedded)
│   ├── generate_image.py
│   ├── pack_embedded.py
│   └── ...
├── plugins/                   ← Optional runtime plugins (release assets: Blender + game_models; source plugins: Ren'Py SDK + Live2D)
│   ├── blender/
│   └── game_models/
├── ReverieCli-py/             ← Python source (primary runtime)
│   ├── reverie/
│   │   ├── __main__.py        ← Entry point
│   │   ├── config.py          ← Configuration management & source registry
│   │   ├── harness.py         ← Prompt audit & verification
│   │   ├── modes.py           ← Mode registry
│   │   ├── session/
│   │   │   └── manager.py     ← Session persistence
│   │   ├── agent/
│   │   │   ├── agent.py       ← Core agent loop
│   │   │   ├── subagents.py   ← Subagent delegation
│   │   │   ├── system_prompt.py← System prompt building
│   │   │   └── tool_executor.py← Tool execution
│   │   ├── cli/
│   │   │   └── interface.py   ← Terminal UI (Rich-based)
│   │   ├── nvidia.py          ← NVIDIA provider integration (16 models)
│   │   ├── codex.py           ← Codex/ChatGPT provider integration
│   │   ├── modelscope.py      ← ModelScope Anthropic-compatible provider
│   │   ├── sensenova.py       ← SenseNova OpenAI-compatible provider
│   │   ├── unlimitedsurf.py   ← unlimited.surf gateway provider
│   │   ├── aihubmix.py        ← AIHubMix OpenAI-compatible provider
│   │   ├── agnes.py           ← Agnes AI provider (text/image/video)
│   │   ├── webgemini.py       ← WebGemini anonymous Gemini Web provider
│   │   ├── builtin_skills/    ← Bundled skills
│   │   └── ...
│   ├── requirements.txt
│   ├── setup.py
│   └── ...
└── dist/
    └── reverie.exe            ← Windows executable (packaged)
```

---

## Installation & Setup

### Prerequisites

- **Python 3.10+**
- **Git** (for session history and Context Engine)
- **Windows 10/11** (primary target; Linux/macOS supported with minor adjustments)
- **PowerShell** (Windows) or Bash (Unix)

### Install from Source (Python)

```powershell
# Clone the repository
git clone https://github.com/Lin-Silver/Reverie-Cli.git
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

### Pre-built Executable

Download the latest `reverie.exe` from the `dist/` directory and run it directly. No Python installation required.

### First-Run Setup

On first launch, Reverie guides you through a setup wizard:

1. **Select an LLM provider** — choose from NVIDIA, ModelScope, Codex, SenseNova, unlimited.surf, AIHubMix, Agnes, WebGemini, or Standard
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
  "config_version": "2.3.4",
  "active_model_source": "standard",
  "models": [
    {
      "base_url": "https://api.openai.com/v1",
      "api_key": "",
      "model": "gpt-4o",
      "model_display_name": "GPT-4o",
      "provider": "openai-chat"
    }
  ],
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
  "modelscope": {
    "enabled": true,
    "api_key": "",
    "selected_model_id": "ZhipuAI/GLM-5.1",
    "selected_model_display_name": "GLM-5.1",
    "api_url": "https://api-inference.modelscope.cn",
    "max_context_tokens": 202752,
    "timeout": 300,
    "max_tokens": 16384
  },
  "sensenova": {
    "enabled": true,
    "api_key": "",
    "selected_model_id": "deepseek-v4-flash",
    "selected_model_display_name": "DeepSeek V4 Flash",
    "api_url": "https://token.sensenova.cn/v1",
    "max_context_tokens": 1000000,
    "timeout": 60,
    "max_tokens": 65536,
    "temperature": 0.6,
    "top_p": 0.95,
    "reasoning_effort": "medium"
  },
  "unlimitedsurf": {
    "enabled": true,
    "api_key": "",
    "selected_model_id": "gateway-gpt-5",
    "selected_model_display_name": "GPT-5",
    "api_url": "https://unlimited.surf",
    "endpoint": "/api/chat",
    "max_context_tokens": 128000,
    "timeout": 60,
    "max_tokens": 16384,
    "effort": "medium"
  },
  "aihubmix": {
    "enabled": true,
    "api_key": "",
    "selected_model_id": "gpt-5.5-free",
    "selected_model_display_name": "GPT-5.5 Free",
    "api_url": "https://aihubmix.com/v1",
    "max_context_tokens": 128000,
    "timeout": 60,
    "max_tokens": 16384,
    "temperature": 0.7,
    "top_p": 1.0
  },
  "agnes": {
    "enabled": true,
    "api_key": "",
    "selected_model_id": "agnes-2.0-flash",
    "selected_model_display_name": "Agnes 2.0 Flash",
    "api_url": "https://apihub.agnes-ai.com/v1",
    "max_context_tokens": 256000,
    "timeout": 60,
    "max_tokens": 65536,
    "temperature": 0.7,
    "top_p": 1.0,
    "thinking_mode": "low"
  },
  "webgemini": {
    "enabled": true,
    "selected_model_id": "gemini-3.5-flash-thinking",
    "selected_model_display_name": "Gemini 3.5 Flash Thinking",
    "timeout": 180,
    "retry_attempts": 2,
    "retry_delay": 1,
    "max_context_tokens": 128000
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
| `active_model_source` | string | `"standard"` | Active provider: `standard`, `nvidia`, `codex`, `modelscope`, `sensenova`, `unlimitedsurf`, `aihubmix`, `agnes`, `webgemini` |
| `tool_output_style` | string | `"compact"` | Tool result display: `compact`, `condensed`, `full` |
| `thinking_output_style` | string | `"full"` | Reasoning display: `hidden`, `compact`, `full` |
| `nvidia.enable_thinking` | bool | `true` | Enable provider-side thinking for NVIDIA models |
| `nvidia.reasoning_effort` | string | `"high"` | Reasoning depth: `max`, `high`, `medium`, `low`, `none` |
| `codex.reasoning_effort` | string | `"medium"` | Codex effort: `minimal`, `low`, `medium`, `high`, `xhigh` |

---

## Modes

Switch modes with `/mode <name>` or `--mode` at launch.

### Reverie (default)

General-purpose coding and automation. Full Context Engine, all workspace tools, Blender modeling, browser control.

### Reverie-Atlas

Document-driven development for complex systems. Produces structured specs, architecture documents, and delivery artifacts. Focus tools: `codebase-retrieval`, `create_file`, `command_exec`.

### Reverie-Gamer

> ⚠️ **Work in Progress** — This mode is not yet complete.

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
- `serial_novel` disk-backed project control
- Chapter control cards, continuity ledgers, and resumable drafting
- One TXT export per committed chapter plus merged `manuscript.txt`
- Completion audits that verify the persisted novel state before finishing

### Computer Controller

Desktop orchestration through an embedded Open Computer Use-compatible desktop runtime, with scoped Reverie SubAgents for coding, repository work, and verification. The main controller remains the only desktop actor, is pinned to the NVIDIA provider, is entered explicitly for desktop work, and may hand off to another mode when the task is no longer primarily desktop work.

---

## LLM Providers & Models

### NVIDIA (Recommended for High-Throughput)

NVIDIA's hosted API at `integrate.api.nvidia.com` provides access to 16 models. Key configurations:

**Model catalog (hardcoded in `reverie/nvidia.py`):**

| Model ID | Display Name | Transport | Vision | Thinking | Context |
|----------|-------------|-----------|--------|----------|---------|
| `qwen/qwen3.5-397b-a17b` | Qwen3.5 397B A17B | request | ✅ | toggle | 262K |
| `qwen/qwen3.5-122b-a10b` | Qwen3.5 122B A10B | request | ✅ | toggle | 262K |
| `z-ai/glm-5.1` | GLM-5.1 | openai-sdk | ❌ | toggle | 131K |
| `z-ai/glm4.7` | GLM-4.7 | openai-sdk | ❌ | toggle | 131K |
| `deepseek-ai/deepseek-v4-pro` | DeepSeek V4 Pro | openai-sdk | ❌ | effort (none/high/max) | 1M |
| `deepseek-ai/deepseek-v4-flash` | DeepSeek V4 Flash | openai-sdk | ❌ | effort (none/low/med/high) | 1M |
| `minimaxai/minimax-m2.7` | MiniMax M2.7 | openai-sdk | ❌ | ❌ | 204K |
| `minimaxai/minimax-m3` | MiniMax M3 | request | ✅ (img+vid) | effort (none/high) | 1M |
| `mistralai/mistral-small-4-119b-2603` | Mistral Small 4 119B | request | ✅ | effort (none/high) | 262K |
| `mistralai/mistral-medium-3.5-128b` | Mistral Medium 3.5 128B | request | ✅ | effort (none/high) | 262K |
| `mistralai/mistral-large-3-675b-instruct-2512` | Mistral Large 3 675B | request | ✅ | ❌ | 262K |
| `stepfun-ai/step-3.5-flash` | Step-3.5-Flash | openai-sdk | ❌ | fixed (always-on) | 256K |
| `stepfun-ai/step-3.7-flash` | Step-3.7-Flash | request | ✅ (img) | ❌ | 256K |
| `moonshotai/kimi-k2.6` | Kimi K2.6 | request | ✅ | toggle | 262K |
| `openai/gpt-oss-120b` | GPT-OSS-120B | openai-sdk | ❌ | effort (low/med/high) | 128K |
| `nvidia/nemotron-3-super-120b-a12b` | Nemotron 3 Super 120B | openai-sdk | ❌ | effort (none/low/high) | 1M |

**Transport types:**
- `request` — Direct HTTP POST with chat-template kwargs (for models like Kimi K2.6, MiniMax M3, Qwen3.5, Mistral)
- `openai-sdk` — OpenAI-compatible SDK transport (for models like DeepSeek V4 Pro, GLM-5.1, GPT-OSS-120B)

**Thinking control:**
- `toggle` — Binary on/off (Qwen3.5, GLM-5.1/4.7, Kimi K2.6)
- `effort` — Selectable levels: `none`/`low`/`medium`/`high`/`max` (DeepSeek V4 Pro, Nemotron, Mistral models, GPT-OSS-120B, MiniMax M3)
- `fixed` — Always-on thinking (Step-3.5-Flash)

**Vision models:** MiniMax M3, Mistral Small 4, Mistral Medium 3.5, Mistral Large 3, Qwen3.5 122B/397B, Kimi K2.6, Step-3.7-Flash support image and/or video input.

### ModelScope

ModelScope provides an **Anthropic-compatible** inference API at `https://api-inference.modelscope.cn`. Any model on ModelScope that supports the Anthropic SDK can be used — it is not limited to Zhipu models. The built-in catalog in `reverie/modelscope.py` includes:

| Model ID | Display Name | Context | Thinking | Vision |
|----------|-------------|---------|----------|--------|
| `ZhipuAI/GLM-5.1` | GLM-5.1 | 202,752 | ✅ | ❌ |
| `ZhipuAI/GLM-5` | GLM-5 | 202,752 | ✅ | ❌ |
| `deepseek-ai/DeepSeek-V4-Pro` | DeepSeek V4 Pro | 1,048,576 | ✅ | ❌ |
| `deepseek-ai/DeepSeek-V4-Flash` | DeepSeek V4 Flash | 1,048,576 | ✅ | ❌ |
| `MiniMax/MiniMax-M2.7` | MiniMax M2.7 | 204,800 | ✅ | ❌ |
| `Qwen/Qwen3.5-397B-A17B` | Qwen3.5 397B A17B | 262,144 | ✅ | ✅ |

**API key:** Get a token from `https://www.modelscope.cn/my/access/token`. Environment variables `MODELSCOPE_API_KEY`, `MODELSCOPE_TOKEN`, or `MODELSCOPE_ACCESS_TOKEN` are also read.

**Important:** The API URL should be the provider root (e.g., `https://api-inference.modelscope.cn`). Reverie normalizes pasted `/v1`, `/v1/messages`, or `/v1/chat/completions` URLs back to the root because the Anthropic SDK appends the Messages path automatically.

### Codex (ChatGPT Backend)

Connects to ChatGPT's backend API. Supports:
- OAuth login via `~/.codex/auth.json` (auto-detected)
- Responses API format with reasoning effort control
- Vision input support
- Model catalog loaded from local Codex source or CLI cache

### SenseNova

[SenseTime SenseNova](https://www.sensenova.cn/) with model-specific OpenAI/Anthropic-compatible transports at `https://token.sensenova.cn`:

| Model ID | Display Name | Context | Thinking | Vision |
|----------|-------------|---------|----------|--------|
| `deepseek-v4-flash` | DeepSeek V4 Flash | 1,000,000 | ✅ (effort) | ❌ |
| `sensenova-6.7-flash-lite` | SenseNova 6.7 Flash Lite | 262,144 | ❌ | ✅ |

Reasoning effort is selectable: `none`, `low`, `medium`, `high`.

### unlimited.surf

A gateway service at `https://unlimited.surf` with request transport:

| Model ID | Display Name | Provider | Tier |
|----------|-------------|----------|------|
| `gateway-gpt-5` | GPT-5 | openai | flagship |

Effort is selectable: `low`, `medium`, `high`. Note: tool calling is not supported.

### AIHubMix

Third-party API gateway (OpenAI-compatible) at `https://aihubmix.com/v1`:

| Model ID | Display Name | Reasoning Variant |
|----------|-------------|-------------------|
| `gpt-5.5-free` | GPT-5.5 Free | none |
| `gpt-5.5-free-high` | GPT-5.5 Free High | high |
| `gpt-5.5-free-low` | GPT-5.5 Free Low | low |
| `gpt-4o-free` | GPT-4o Free | — |
| `gpt-4.1-free` | GPT-4.1 Free | — |

### Agnes

Agnes AI OpenAI-compatible API at `https://apihub.agnes-ai.com/v1`:

| Model ID | Display Name | Context | Vision | Thinking |
|----------|-------------|---------|--------|----------|
| `agnes-2.0-flash` | Agnes 2.0 Flash | 256,000 | ✅ | ✅ (low/med/high) |
| `agnes-1.5-flash` | Agnes 1.5 Flash | 256,000 | ✅ | ❌ |
| `agnes-1.5-pro` | Agnes 1.5 Pro (Deprecated) | 256,000 | ❌ | ❌ |

Thinking budgets: `low` (1024), `medium` (4096), `high` (8192).

Agnes also supports **text-to-image** and **text-to-video** generation through the `text_to_image` and `text_to_video` subsystems.

### WebGemini

Anonymous Gemini Web access via `gemini.google.com`. Models are selected by mode and thinking parameters:

| Model ID | Display Name | Mode | Think | Max Output |
|----------|-------------|------|-------|-----------|
| `gemini-3.5-flash` | Gemini 3.5 Flash | 1 | 4 | 12,000 |
| `gemini-3.5-flash-thinking` | Gemini 3.5 Flash Thinking | 2 | 0 | 20,000 |
| `gemini-3.5-flash-thinking-lite` | Gemini 3.5 Flash Thinking Lite | 5 | 0 | 15,000 |
| `gemini-3.1-pro` | Gemini 3.1 Pro | 3 | 4 | 12,000 |
| `gemini-auto` | Gemini Auto | 4 | 4 | 12,000 |
| `gemini-flash-lite` | Gemini Flash Lite | 6 | 4 | 10,000 |

> **Note:** `gemini-3.1-pro` requires cookies for proper routing. Default model: `gemini-3.5-flash-thinking`.

### Standard (OpenAI-Compatible Presets)

The `standard` source uses user-defined model presets stored in the `models` array of `config.json`. Each entry specifies a `base_url`, `api_key`, `model`, and `provider` call method. Canonical methods are `openai-chat`, `openai-responses`, `anthropic`, `request`, and `curl`. For `curl`, URLs ending in `/responses` use the Responses format; URLs ending in `/chat/completions` use Chat Completions, while a bare API root defaults to Chat Completions. Legacy names such as `openai`, `openai-sdk`, `openai-old`, and `openai-res` are accepted on load and rewritten to the canonical names when the configuration is saved.

---

## CLI Usage

### Command-Line Arguments

```
reverie [OPTIONS]

Options:
  --mode <MODE>            Start in a specific mode (reverie, atlas, gamer, etc.)
  --provider <PROVIDER>    Override active provider (nvidia, codex, modelscope, sensenova, unlimitedsurf, aihubmix, agnes, webgemini...)
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

### Provider Model Catalog (Python API)

Each built-in source exposes a model catalog and config normalization functions:

```python
# NVIDIA
from reverie.nvidia import (
    get_nvidia_model_catalog,
    get_nvidia_model_metadata,
    build_nvidia_runtime_model_data,
    default_nvidia_config,
    normalize_nvidia_config,
    resolve_nvidia_api_key,
    get_nvidia_thinking_options,
)

catalog = get_nvidia_model_catalog()  # List of model dicts
metadata = get_nvidia_model_metadata("qwen/qwen3.5-397b-a17b")

# ModelScope
from reverie.modelscope import (
    get_modelscope_model_catalog,
    get_modelscope_model_metadata,
    build_modelscope_runtime_model_data,
    default_modelscope_config,
    normalize_modelscope_config,
    resolve_modelscope_anthropic_base_url,
    resolve_modelscope_api_key,
)

# Codex
from reverie.codex import (
    build_codex_runtime_model_data,
    detect_codex_cli_credentials,
    default_codex_config,
    normalize_codex_config,
)

# AIHubMix
from reverie.aihubmix import (
    build_aihubmix_runtime_model_data,
    default_aihubmix_config,
    normalize_aihubmix_config,
    get_aihubmix_model_catalog,
)

# Agnes
from reverie.agnes import (
    build_agnes_runtime_model_data,
    default_agnes_config,
    normalize_agnes_config,
    get_agnes_model_catalog,
)

# SenseNova
from reverie.sensenova import (
    build_sensenova_runtime_model_data,
    default_sensenova_config,
    normalize_sensenova_config,
    get_sensenova_model_catalog,
)

# unlimited.surf
from reverie.unlimitedsurf import (
    build_unlimitedsurf_runtime_model_data,
    default_unlimitedsurf_config,
    normalize_unlimitedsurf_config,
)

# WebGemini
from reverie.webgemini import (
    build_webgemini_runtime_model_data,
    default_webgemini_config,
    normalize_webgemini_config,
    get_webgemini_model_catalog,
)
```

### External Model Sources Registry

```python
from reverie.config import EXTERNAL_MODEL_SOURCES, SUPPORTED_ACTIVE_MODEL_SOURCES

# All external (non-standard) model sources
print(EXTERNAL_MODEL_SOURCES)
# ("codex", "aihubmix", "agnes", "sensenova", "unlimitedsurf", "nvidia", "modelscope", "webgemini")

# All supported active model source values (includes "standard")
print(SUPPORTED_ACTIVE_MODEL_SOURCES)
# ("standard", "codex", "aihubmix", "agnes", "sensenova", "unlimitedsurf", "nvidia", "modelscope", "webgemini")
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
- For NVIDIA: verify key at `https://build.nvidia.com/settings/api-keys`
- For ModelScope: verify token at `https://www.modelscope.cn/my/access/token`
- For WebGemini: ensure proxy/cookie settings are correct if needed

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

Contributions are welcome:

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Make your changes with tests
4. Run verification: `pytest` (Python)
5. Submit a pull request

### Development Setup

```powershell
# Python development
py -m venv venv
.\venv\Scripts\Activate.ps1
py -m pip install -r ReverieCli-py\requirements.txt
py -m pip install -r ReverieCli-py\requirements-dev.txt

# Run tests
py -m pytest
```

---

## License

This project is shared as open-source software. See the repository for details.

---

## Links

- **Repository**: https://github.com/Lin-Silver/Reverie-Cli
- **Issues**: https://github.com/Lin-Silver/Reverie-Cli/issues
- **NVIDIA API Docs**: https://build.nvidia.com
- **Claude API Docs**: https://docs.anthropic.com
- **Gemini API Docs**: https://ai.google.dev

---

*Reverie CLI — Open-source agentic coding assistant. Built with Python and modern LLM APIs.*
