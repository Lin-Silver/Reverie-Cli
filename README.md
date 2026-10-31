# Reverie CLI

RIU development continues on `dev`; see the [continuation guide](docs/CONTINUE_RIU.md) for the current goal, retained evidence and open package/platform checks. The latest Linux launcher source fix still needs a verified rebuilt installer.

Start with the [documentation index](docs/README.md), [complete version history](docs/changelog.md), and [Intelligent UI implementation and protocol scope](docs/INTELLIGENT_UI_SPEC.md). Reverie Desktop implements offline interactive views with inline, fullscreen and picture-in-picture presentation. Real-model generation quality and platform acceptance remain separately tracked in [feature status](docs/FEATURE_STATUS.md).

Current stable version: **v2.5.0** (released 2026-07-17).

Current working-tree behavior and remaining gaps were reviewed on **2026-10-26**. Start with the [documentation index](docs/README.md), [feature status](docs/FEATURE_STATUS.md), [Desktop guide](docs/DESKTOP_GUIDE.md), and [roadmap](docs/ROADMAP.md). The dated audit distinguishes implementation from completed acceptance; local updates are not necessarily published releases.

Updated **2026-10-10**: lower desktop startup memory, refreshed Agnes/ModelScope text models, transparent thought blocks, an About repository link, and a standalone Windows CLI EXE. See [the measured results](docs/VERIFICATION_HISTORY.md#desktop-memory-2026-10-10).

**Reverie** is an open-source agentic coding assistant with terminal and Electron desktop interfaces for natural language interaction with your local codebase. Both use the Python core's multi-provider LLM access, Context Engine retrieval, sessions and tools; Desktop adds project/chat navigation, structured input, Git review and runtime evidence surfaces. Optional 3D/game, media and browser workflows have the boundaries documented below.

- **Core function**: terminal-based AI coding assistant with local workspace tools, context retrieval, session continuity, and multi-provider LLM access
- **Native desktop**: Electron workspace host using the same Python core, with project/session management, full-window backgrounds, Context Engine file recommendations, arbitrary attachments, settings, tools, plugins, and recovery views
- **RATS / RTP**: opt-in, executable-local allowlisted Reverie/Rilance provider discovery with Python-core session ownership, exact permissions, compact catalogs, and progressive native tool schemas; Reverie Engine is currently the only implemented provider
- **Optional workflows**: spec-package authoring, creative writing, browser automation, computer control, and game/3D asset authoring
- **Multi-provider LLM** support: NVIDIA, ModelScope, Codex (ChatGPT), SenseNova, AIHubMix, Agnes, WebGemini, Opencode, plus any endpoint you add with `/provider add`
- **Context Engine**: Augment-style codebase retrieval, LSP integration, git history analysis
- **Session management**: Conversation persistence, rotation, working memory injection, handoff packets
- **Approval policy**: Three tool-call approval modes — Default (software policy only), Auto Check (a stateless model review rates each call's risk and pauses only on risky ones), and Strict (every call waits for you); answer allow, deny, or reply in your own words to redirect the model. See [SECURITY_PERMISSIONS.md](docs/SECURITY_PERMISSIONS.md)
- **Inline media**: Attach images and video directly in conversations
- **Image generation**: Choose local or remote image models in Desktop Settings → Image models. Pollinations generation requires an API key; SenseNova editing chooses its output dimensions automatically unless `size` is specified.
- **Experimental integrations**: Blender, Blockbench, legacy Godot/O3DE migration, Ashfox MCP, image/video generation, and agent-operated browser automation
- **Browser automation**: The Python core exposes a Chromium-based browser-control tool. The Desktop app does not include an interactive browser tab panel; see the [recorded scope](docs/FEATURE_STATUS.md).
- **Subagent delegation**: Parallel investigation and implementation tasks
- **Harness audit**: Prompt-level reporting, verification tracking, playbook recommendations
- **Specialist runtime plugins**: Ren'Py and Live2D/Cubism Galgame workflows are delivered through plugin-owned `rc_*` tools, skills, and prompt guidance
- **Skills**: Progressive `SKILL.md` discovery and `/skill <name>` mandatory prompt guidance, with pin tags in CLI/Desktop. Bundled skills include `photo-to-3d` and all 14 Emil Kowalski design skills, including Apple Design. Desktop ordinary session/restart restoration is implemented; fork/rotation, standalone CLI restoration, and per-turn inspection enforcement have [documented limits](docs/SKILLS.md).
- **Roadmap**: Planned CLI, Desktop, provider, runtime and Gamer work is maintained in [one roadmap](docs/ROADMAP.md)

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


| Provider           | Description                                                                                                     | Key Models                                                                                                                                                                                  |
| ------------------ | --------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **NVIDIA**         | NVIDIA-hosted catalog via`integrate.api.nvidia.com`                                                             | DeepSeek V4.1 Flash, GLM 5.3 Flash, Step 5 Preview, Nemotron 3.5 Super VL/Lightning, Muse Glimmer 30B, Nemotron 3 Super/Ultra, GPT-OSS-20B, Laguna XS 2.1 |
| **ModelScope**     | OpenAI Chat Completions API on `api-inference.modelscope.cn` with core-published model capabilities             | Qwen3.8-27B (default), GLM-5.3/Flash, DeepSeek V4.1 Flash, DeepSeek V4 Pro 0813, Step 3.7 Flash |
| **Codex**          | ChatGPT backend or Responses-compatible reverse proxy                                                           | GPT-5.6, GPT-5.5, and other models discovered from the live Codex CLI cache                                                                                                                 |
| **SenseNova**      | SenseTime SenseNova API with live model discovery and OpenAI-compatible transport                              | Live account catalog; fallback includes DeepSeek V4 Flash, GLM-5.2, and SenseNova 6.8 Flash Lite                                                                                            |
| **AIHubMix**       | Third-party API gateway (OpenAI-compatible)                                                                     | GPT-5.5 Free (with/without reasoning), GPT-4o Free, GPT-4.1 Free                                                                                                                            |
| **Agnes**          | Agnes AI OpenAI-compatible API (text, image, video)                                                             | Agnes 3.0 Flash (default), 3.0 Flash Max, stable 2.5 Pro; separate image/video profiles |
| **WebGemini**      | Anonymous Gemini Web access via`gemini.google.com`                                                              | Gemini 3.5 Flash, Gemini 3.5 Flash Thinking, Gemini 3.5 Flash Thinking Lite, Gemini 3.1 Pro, Gemini Auto, Gemini Flash Lite                                                                 |
| **Custom**         | Any endpoint you add with `/provider add` - OpenAI Chat Completions, OpenAI Responses, or Anthropic Messages     | Read live from the provider's own model-list endpoint                                                                                                                                        |

Provider transports support streaming where their model and endpoint implement the required protocol. A listed model, HTTP 200, or availability probe does not prove working content, complete SSE, tool calls or vision. Reasoning/thinking toggles, temperature, top_p, max_tokens, and other parameters are configurable per provider; [current compatibility limits](docs/FEATURE_STATUS.md) and the [JDW sample](docs/VERIFICATION_HISTORY.md#reverie-cli-jdw-compatibility-2026-10-04) are recorded separately.

Use `/provider list` to see every source at once with its API-key flag and a parallel availability probe, and `/provider add` to register your own gateway from four fields: name, base URL, API key, and API request format.

The built-in Agnes and ModelScope text catalogs were reviewed against official documentation on **2026-10-10**: [Agnes Flash](https://wiki.agnes-ai.com/en/docs/agnes-30-flash), [Flash Max](https://wiki.agnes-ai.com/en/docs/agnes-30-flash-max), [stable Pro](https://wiki.agnes-ai.com/en/docs/agnes-25-pro), and [ModelScope's inference catalog](https://www.modelscope.cn/models?filter=inference_type&page=1&sort=default&tabKey=task). New configurations use the defaults above; existing selections keep their model IDs and reasoning settings. Flash uses an explicit thinking switch; Flash Max supports `low`, `medium`, and `xhigh`. The newer ModelScope DeepSeek entries use hosted reasoning defaults until their hosted parameter contract is verified. Catalog entries and conservative request limits do not guarantee account access or quota.

A custom provider keeps two extra settings of its own:

- **Per-model context limit.** Gateways rarely publish a trustworthy context window, so the first time you pick one of a provider's models Reverie asks for that model's limit and remembers it. Every later selection of the same provider and model reuses the saved value without asking, and models you never pick are never asked about. Change a saved limit with `/provider <name> context 256k` (`128000`, `128k`, and `1.2m` are all accepted).
- **Thinking mode**, which is **on by default**. A gateway that rejects the thinking flags degrades to a plain request for that turn instead of failing it; turn it off permanently with `/provider <name> thinking off`.

Every stored provider also extends command completion: once `xkiro` exists, `/provider xkiro models`, `/provider xkiro context`, `/provider xkiro thinking`, and the rest of its actions complete like built-in commands, both in the terminal and in the Desktop command palette.

The Desktop app exposes the same surface under **Settings → 模型与提供商 → Custom Provider**: add, edit, enable/disable, delete, refresh the live catalog, test availability, pick a model, and confirm a model's context limit.

### Debug output

Raw internal stream frames (`[[REVERIE_EVENT]]{...}`) are protocol details that the display turns into activity lines. They are only printed when debug mode is on — start with `reverie --debug`, or set `REVERIE_DEBUG=1`. Debug mode only widens what Reverie prints; it never changes what is sent to a provider or written to disk.

### Prompt Caching

Reverie prefers provider-side prompt-prefix caching for every production text-model call, including streaming and non-streaming chat, Responses, native HTTP/curl compatibility transports, Context Engine compression, and automatic session handoff:

- OpenAI-compatible requests receive a stable privacy-preserving `prompt_cache_key`; raw compatibility requests also try the llama.cpp-compatible `cache_prompt` hint.
- Anthropic requests use automatic five-minute caching through `cache_control: {"type": "ephemeral"}`.
- If a compatible gateway explicitly rejects a cache field, Reverie removes only the cache hints and retries the same request once. Other provider errors keep their existing retry and error behavior.

Cache keys contain hashes of the model, stable system prefix, and tool schema rather than prompt text. Actual cache hits still depend on provider/model support and a sufficiently long identical prefix; WebGemini and media-generation calls do not expose a compatible prompt-cache control.

### Operating Modes

Reverie ships with specialized modes that change tooling, system prompt rules, and domain focus:


| Mode                  | Display Name        | Description                                                                                                                                                                                                       |
| --------------------- | ------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `reverie`             | Reverie             | Default general coding, automation, and long-running execution mode. Context Engine retrieval, core workspace tools, structured task boundaries, Reverie Engine control, Blender/3D modeling.                      |
| `reverie-atlas`       | Reverie-Atlas       | Document-driven spec development. Deep research paired with Context Engine, spec packages (requirements/design/tasks), and Atlas delivery artifacts.                                                               |
| `reverie-gamer`       | Reverie-Gamer       | ⚠️**Work in Progress** — Full game production pipeline (blueprints, system packets, vertical slices, playtest loops, modeling pipelines). Not yet complete.                                                    |
| `writer`              | Writer              | Creative writing: persistent long-form fiction planning, serialized drafting, continuity control, and verified completion.                                                                                        |
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

The Python core's browser-control tool uses an embedded Chromium runtime for web interaction. It is an agent tool, not a visible browser panel in the Electron Desktop app:

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
│   │   ├── nvidia.py          ← NVIDIA provider integration (10 models)
│   │   ├── codex.py           ← Codex/ChatGPT provider integration
│   │   ├── modelscope.py      ← ModelScope OpenAI Chat provider and capability catalog
│   │   ├── sensenova.py       ← SenseNova OpenAI-compatible provider
│   │   ├── aihubmix.py        ← AIHubMix OpenAI-compatible provider
│   │   ├── agnes.py           ← Agnes AI provider (text/image/video)
│   │   ├── prompt_cache.py    ← prompt-prefix cache hints and compatibility fallback
│   │   ├── webgemini.py       ← WebGemini anonymous Gemini Web provider
│   │   ├── builtin_skills/    ← Bundled skills
│   │   └── ...
│   ├── requirements.txt
│   ├── setup.py
│   └── ...
└── dist/
    └── reverie.exe            ← Standalone Windows CLI executable
```

---

## Installation & Setup

### Prerequisites for running from source

- **Python 3.10+**
- **Git** (for session history and Context Engine)
- **Windows 10/11** (primary target; Linux/macOS supported with minor adjustments)
- **PowerShell** (Windows) or Bash (Unix)

### Prebuilt packages

The core/desktop Release is separate from the optional plugin Release:

- Windows x64: standalone `reverie.exe`, the portable GUI executable, and the NSIS installer.
- Linux x64: `reverie`, AppImage, and Debian package. The Debian installer provides both `reverie` and `reverieui` commands.
- macOS: explicitly named Apple Silicon (M-series) and Intel DMGs plus matching native CLI cores. Command-line tools remain an explicit user-installed symlink from the app bundle.
- Official compiled plugins: the dedicated `plugins-latest` Release and `plugins-manifest.json`; plugin paths additionally trigger their isolated plugin build while the rolling desktop prerelease is refreshed by every `main` push.

Every push to `main` rebuilds the rolling `latest` tag as **Reverie CLI Latest (Prerelease)**. Version tags such as `v2.5.0` remain stable Releases. Release notes and upload labels group downloads as Windows, Linux, macOS Apple Silicon, then macOS Intel. `reverie-kernels.json` is the single optional verification file: GitHub already displays a digest for every asset, while this consolidated record additionally maps each kernel to its protocol, interface version, platform, architecture, commit, size, and SHA-256.

`reverie` starts the TUI/core. `reverieui` starts the GUI in the current directory. Packaged GUIs start with their fast onedir kernel; the explicit portable `--tui` route may select a sibling kernel only when its SHA-256 appears in the build-time allowlist and its `--kernel-info` protocol handshake succeeds.

### CLI, TUI, and Desktop GUI

All three use the same Python core for providers, tools, permissions, sessions, and Context Engine:

| Entry point | Interface | Distribution |
| --- | --- | --- |
| `reverie.exe` | Terminal CLI; interactive TUI by default | One EXE, without Electron, an adjacent runtime directory, or an installed Python environment |
| TUI | Rich terminal interface inside the CLI | Included in `reverie.exe`; no separate TUI application is required |
| `ReverieUI.exe` / `reverieui` | Electron/React desktop GUI | Calls a compiled internal CLI kernel through JSONL SDK bridge; desktop packages manage their own internal runtime |

Download the [standalone CLI EXE](https://github.com/Lin-Silver/Reverie-Cli/releases/download/latest/reverie.exe) for terminal-only use. The one-file executable embeds its Python dependencies and extracts them to a temporary directory while running. It needs no external Python installation; normal configuration, session data, and optional tool resources are still written when used. GUI portable packaging is a separate download and manages its extracted application files under `.reverie/desktop/app-runtime`.

Desktop startup creates one administration kernel and starts chat workers on demand. It postpones automatic indexing until a chat needs it or you explicitly request indexing. At most one completed chat worker stays warm for 30 seconds; active chats remain isolated with up to four concurrent workers. This bounds idle kernel retention; memory during active work still depends on workspace and conversation size. Windows measurements and their scope are recorded in [verification history](docs/VERIFICATION_HISTORY.md#desktop-memory-2026-10-10).

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

Download `reverie.exe` and run it in your terminal. You can copy this one file to another directory and run it there. No companion `reverie-runtime/` directory or Python installation is required.

### First-Run Setup

On first launch, Reverie guides you through a setup wizard:

1. **Select an LLM provider** — choose from NVIDIA, ModelScope, Codex, SenseNova, AIHubMix, Agnes, WebGemini, or Standard
2. **Configure API keys** — enter your provider API key (file-stored keys are saved in `config.json`; supported environment variables avoid storing those values there)
3. **Select a default model** — pick from the provider's catalog
4. **Choose a workspace** — set your project root directory

Core configuration uses `<app_root>/.reverie/config.json` by default, or `<app_root>/.reverie/projects/<project-path-key>/config.json` when workspace mode is enabled. Source runs default to the repository's `dist/` app root. Desktop workspace artifacts and browser storage have separate locations; see [Configuration](docs/CONFIGURATION.md).

---

## Quick Start

```powershell
# Start Reverie in the current directory
reverie

# Start with a specific mode
reverie --mode reverie-atlas

# Start with a specific provider/model
reverie --source nvidia --model meta/muse-glimmer-30b

# Start in a specific project; saved sessions are managed inside the CLI
reverie "G:\Projects\MyProject"
```

Once inside the CLI:

- Type naturally to chat with the AI assistant
- Use `/help` to see available commands
- Use `/tools` to inspect available tools
- Use `/mode <name>` to switch modes mid-session
- Use `/sessions` to browse saved sessions
- Attach files by referencing them in your message (e.g., "review `src/main.py`")

For the native desktop interface, build or run `ReverieCli-ui` as described in [Reverie Desktop](ReverieCli-ui/README.md) and the [Desktop guide](docs/DESKTOP_GUIDE.md). A management bridge persists across project switches; task runs use separate session-owned cores. `@` recommends workspace files, the paperclip selects attachments, and `/` opens command/Skill candidates. Only the documented subset of CLI commands executes directly in Desktop.

---

## Configuration

### Configuration File

Reverie uses the shared or project profile under the selected app root, as described in [Configuration](docs/CONFIGURATION.md). Key sections:

```json
{
  "config_version": "2.5.0",
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
    "selected_model_id": "meta/muse-glimmer-30b",
    "selected_model_display_name": "Muse Glimmer 30B",
    "api_url": "https://integrate.api.nvidia.com/v1",
    "max_context_tokens": 131072,
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
    "endpoint": "",
    "auth_mode": "auto",
    "api_key_env": "CODEX_PROXY_API_KEY",
    "custom_headers": {},
    "reasoning_effort": "medium",
    "timeout": 1200
  },
  "modelscope": {
    "enabled": true,
    "api_key": "",
    "selected_model_id": "stepfun-ai/Step-3.7-Flash",
    "selected_model_display_name": "Step-3.7-Flash",
    "api_url": "https://api-inference.modelscope.cn/v1",
    "max_context_tokens": 262144,
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
    "selected_model_id": "agnes-2.5-flash",
    "selected_model_display_name": "Agnes 2.5 Flash",
    "api_url": "https://apihub.agnes-ai.com/v1",
    "max_context_tokens": 512000,
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


| Key                       | Type   | Default      | Description                                                                                                                 |
| ------------------------- | ------ | ------------ | --------------------------------------------------------------------------------------------------------------------------- |
| `active_model_source`     | string | `"standard"` | Active provider:`standard`, `nvidia`, `codex`, `modelscope`, `sensenova`, `aihubmix`, `agnes`, `webgemini`, `opencode`, `custom` |
| `tool_output_style`       | string | `"compact"`  | Tool result display:`compact`, `condensed`, `full`                                                                          |
| `thinking_output_style`   | string | `"full"`     | Reasoning display:`hidden`, `compact`, `full`                                                                               |
| `nvidia.enable_thinking`  | bool   | `true`       | Enable provider-side thinking for NVIDIA models                                                                             |
| `nvidia.reasoning_effort` | string | `"high"`     | Reasoning depth:`max`, `high`, `medium`, `low`, `none`                                                                      |
| `codex.reasoning_effort`  | string | `"medium"`   | Codex effort:`minimal`, `low`, `medium`, `high`, `xhigh`                                                                    |

---

## Modes

Switch modes with `/mode <name>` or `--mode` at launch.

### Reverie (default)

General-purpose coding and automation. Full Context Engine, all workspace tools, Blender modeling, browser control, and direct `reverie_engine` control of Reverie Engine.

It also owns structured long-running execution — planning/execution/verification stages, `task_boundary` progress updates, `notify_user` review checkpoints, and checkpoint-and-resume artifacts — plus implementing an approved spec package from `artifacts/specs/<feature>/`.

### Reverie-Atlas

Document-driven development for complex systems. Produces structured specs, architecture documents, and delivery artifacts. Focus tools: `codebase-retrieval`, `create_file`, `command_exec`.

Atlas also owns spec-package authoring for a single bounded feature: `requirements.md` (EARS acceptance criteria) → `design.md` → `tasks.md`, written in order with review gates between them. Hand the finished package to `reverie` to build it.

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

NVIDIA's hosted API at `integrate.api.nvidia.com` provides access to 11 supported models. Key configurations:

**Model catalog (hardcoded in `reverie/nvidia.py`):**


| Model ID                                         | Display Name                     | Transport  | Vision       | Thinking                            | Context |
| ------------------------------------------------ | -------------------------------- | ---------- | ------------ | ----------------------------------- | ------- |
| `meta/muse-glimmer-30b`                          | Muse Glimmer 30B                 | openai-sdk | ✅           | effort (none/min/low/med/high/max)  | 131K    |
| `nvidia/nemotron-3.5-lightning-30b-a3b`          | Nemotron 3.5 Lightning 30B A3B  | openai-sdk | ❌           | toggle                              | 1M      |
| `nvidia/nemotron-3-ultra-550b-a55b`              | Nemotron 3 Ultra 550B           | openai-sdk | ❌           | fixed thinking                      | 1M      |
| `nvidia/nemotron-3-super-120b-a12b`              | Nemotron 3 Super 120B           | openai-sdk | ❌           | effort (none/low/high)              | 1M      |
| `poolside/laguna-xs-2.1`                         | Laguna XS 2.1                   | openai-sdk | ❌           | ❌                                  | 262K    |
| `deepseek-ai/deepseek-v4-flash-0731`             | DeepSeek V4 Flash 0731          | openai-sdk | ❌           | effort (none/high/max)              | 1M      |
| `deepseek-ai/deepseek-v4-pro-0813`               | DeepSeek V4 Pro 0813            | openai-sdk | ❌           | effort (none/high/max)              | 1M      |
| `moonshotai/kimi-k3`                             | Kimi K3                         | openai-sdk | ✅           | effort (low/high/max; always on)    | 1M      |
| `minimaxai/minimax-m3`                           | MiniMax M3                      | request    | ✅ (img+vid) | effort (none/high)                  | 1M      |
| `stepfun-ai/step-3.7-flash`                      | Step-3.7-Flash                  | request    | ✅           | fixed thinking                      | 256K    |
| `openai/gpt-oss-120b`                            | GPT-OSS-120B                    | openai-sdk | ❌           | effort (low/med/high)               | 128K    |

**Transport types:**

- `request` — Direct HTTP POST with model-specific defaults (for MiniMax M3 and Step-3.7-Flash)
- `openai-sdk` — OpenAI-compatible SDK transport (for models like Kimi K3, DeepSeek V4, Muse Glimmer, Nemotron, and GPT-OSS-120B)

**Thinking control:**

- `toggle` — Binary on/off (Nemotron 3.5 Lightning)
- `effort` — Fixed per-model levels (Kimi K3, DeepSeek V4, Muse Glimmer, Nemotron 3 Super, GPT-OSS-120B, MiniMax M3)
- `fixed` — Always-on provider reasoning (Nemotron 3 Ultra and Step-3.7-Flash)

**Vision models:** Kimi K3, Muse Glimmer, MiniMax M3, and Step-3.7-Flash support image and/or video input. Kimi K3 also replays the provider's `reasoning_content` in multi-turn and tool-call history, as required by its preserved-thinking protocol.

### ModelScope

ModelScope is integrated through its **OpenAI Chat Completions** endpoint at `https://api-inference.modelscope.cn/v1`. The built-in catalog in `reverie/modelscope.py` is the single capability source consumed by both the runtime and desktop GUI:


| Model ID                        | Display Name      | Context   | Reasoning choices      | Vision |
| ------------------------------- | ----------------- | --------- | ---------------------- | ------ |
| `Tencent-Hunyuan/Hy3`           | Hy3               | 262,144   | no-think, low, high    | ❌     |
| `stepfun-ai/Step-3.7-Flash`     | Step 3.7 Flash    | 262,144   | low, medium, high      | ✅     |
| `ZhipuAI/GLM-5.2`               | GLM-5.2           | 1,048,576 | none, high, max        | ❌     |
| `deepseek-ai/DeepSeek-V4-Pro`   | DeepSeek V4 Pro   | 1,048,576 | thinking on/off        | ❌     |
| `deepseek-ai/DeepSeek-V4-Flash` | DeepSeek V4 Flash | 1,048,576 | thinking on/off        | ❌     |

**API key:** Get a token from `https://www.modelscope.cn/my/access/token`. Environment variables `MODELSCOPE_API_KEY`, `MODELSCOPE_TOKEN`, or `MODELSCOPE_ACCESS_TOKEN` are also read.

**Important:** The API URL should be the OpenAI-compatible base (normally `https://api-inference.modelscope.cn/v1`). Reverie normalizes pasted `/v1/messages` and `/v1/chat/completions` URLs to that base automatically.

### Codex (ChatGPT Backend)

Connects to ChatGPT's backend API. Supports:

- OAuth login via `~/.codex/auth.json` (auto-detected)
- Responses-compatible reverse proxies with separate `auto`, local Codex, environment-key, or no-auth modes
- Proxy-safe headers that do not forward ChatGPT account identity to third-party hosts
- Responses API format with reasoning effort control
- Vision input support
- Model catalog loaded from the live Codex CLI cache first, with source and built-in fallbacks

### SenseNova

[SenseTime SenseNova](https://www.sensenova.cn/) with model-specific OpenAI/Anthropic-compatible transports at `https://token.sensenova.cn`:


| Model ID                   | Display Name             | Context   | Thinking    | Vision |
| -------------------------- | ------------------------ | --------- | ----------- | ------ |
| `deepseek-v4-flash`        | DeepSeek V4 Flash        | 1,000,000 | ✅ (effort) | ❌     |
| `sensenova-6.8-flash-lite` | SenseNova 6.8 Flash Lite | 262,144   | ❌          | ✅     |

Reasoning effort is selectable: `none`, `low`, `medium`, `high`.

### AIHubMix

Third-party API gateway (OpenAI-compatible) at `https://aihubmix.com/v1`:


| Model ID            | Display Name      | Reasoning Variant |
| ------------------- | ----------------- | ----------------- |
| `gpt-5.5-free`      | GPT-5.5 Free      | none              |
| `gpt-5.5-free-high` | GPT-5.5 Free High | high              |
| `gpt-5.5-free-low`  | GPT-5.5 Free Low  | low               |
| `gpt-4o-free`       | GPT-4o Free       | —                |
| `gpt-4.1-free`      | GPT-4.1 Free      | —                |

### Agnes

Agnes AI OpenAI-compatible API at `https://apihub.agnes-ai.com/v1`. Reverie classifies the provider's live `/models` response into LLM, text-to-image (TTI), and text-to-video (TTV) catalogs, then exposes only media models that have a local execution profile:


| Modality | Model ID                | Display Name          | Key capability                   |
| -------- | ----------------------- | --------------------- | -------------------------------- |
| LLM      | `agnes-2.5-pro-alpha`   | Agnes 2.5 Pro Alpha   | 1M context, vision, reasoning    |
| LLM      | `agnes-2.5-flash`       | Agnes 2.5 Flash       | 512K context, vision, thinking   |
| LLM      | `agnes-2.0-flash`       | Agnes 2.0 Flash       | 512K context, vision, thinking   |
| TTI      | `agnes-image-2.1-flash` | Agnes Image 2.1 Flash | text/image input and editing     |
| TTI      | `agnes-image-2.0-flash` | Agnes Image 2.0 Flash | text/image input and composition |
| TTV      | `agnes-video-v2.0`      | Agnes Video V2.0      | asynchronous video generation    |

Thinking budgets: `low` (1024), `medium` (4096), `high` (8192).

New configurations default to `agnes-2.5-flash`; existing explicit selections such as `agnes-2.0-flash` remain unchanged.

If live discovery is unavailable, Reverie falls back to this verified built-in catalog. Agnes image and video generation run through the `text_to_image` and `text_to_video` subsystems.

### WebGemini

Anonymous Gemini Web access via `gemini.google.com`. Models are selected by mode and thinking parameters:


| Model ID                         | Display Name                   | Mode | Think | Max Output |
| -------------------------------- | ------------------------------ | ---- | ----- | ---------- |
| `gemini-3.5-flash`               | Gemini 3.5 Flash               | 1    | 4     | 12,000     |
| `gemini-3.5-flash-thinking`      | Gemini 3.5 Flash Thinking      | 2    | 0     | 20,000     |
| `gemini-3.5-flash-thinking-lite` | Gemini 3.5 Flash Thinking Lite | 5    | 0     | 15,000     |
| `gemini-3.1-pro`                 | Gemini 3.1 Pro                 | 3    | 4     | 12,000     |
| `gemini-auto`                    | Gemini Auto                    | 4    | 4     | 12,000     |
| `gemini-flash-lite`              | Gemini Flash Lite              | 6    | 4     | 10,000     |

> **Note:** `gemini-3.1-pro` requires cookies for proper routing. Default model: `gemini-3.5-flash-thinking`.

### Standard (OpenAI-Compatible Presets)

The `standard` source uses user-defined model presets stored in the `models` array of `config.json`. Each entry specifies a `base_url`, `api_key`, `model`, and `provider` call method. Canonical methods are `openai-chat`, `openai-responses`, `anthropic`, `request`, and `curl`. For `curl`, URLs ending in `/responses` use the Responses format; URLs ending in `/chat/completions` use Chat Completions, while a bare API root defaults to Chat Completions. Legacy names such as `openai`, `openai-sdk`, `openai-old`, and `openai-res` are accepted on load and rewritten to the canonical names when the configuration is saved.

---

## CLI Usage

### Command-Line Arguments

```
reverie [OPTIONS] [path]

Options:
  --mode <MODE>            Start in a specific mode (reverie, atlas, gamer, etc.)
  --source <SOURCE>        Temporarily select the model source
  --model <MODEL>          Override selected model
  --reasoning <VALUE>      Temporarily select supported reasoning depth/toggle
  --prompt <TEXT>          Run one non-interactive prompt
  --prompt-file <PATH>     Read one prompt from a file
  --prompt-stdin           Read one prompt from stdin
  --report-file <PATH>     Write prompt-mode JSON results
  --index-only             Index the project and exit
  --no-index               Skip startup indexing
  --debug                  Enable internal diagnostics
  --kernel-info            Print the kernel compatibility record and exit
  --sdk-bridge             Run the JSONL Desktop bridge
  --version                Show version and exit
  --help                   Show help message
```

### Interactive Commands


| Command                | Description                 |
| ---------------------- | --------------------------- |
| `/help`                | Show available commands     |
| `/mode <name>`         | Switch operating mode       |
| `/session list`        | List available sessions     |
| `/session new [name]`  | Create a new session        |
| `/session load <id>`   | Load a specific session     |
| `/session delete <id>` | Delete a session            |
| `/tools`               | Inspect available tools     |
| `/model <name>`        | Switch to a different model |
| `/provider <name>`     | Switch provider             |
| `/clear`               | Clear terminal screen       |
| `/save`                | Save current session        |
| `/exit` or `/quit`     | Exit Reverie                |
| `/thinking on/off`     | Toggle thinking display     |
| `/compact [focus]`     | Compact context now, with optional retention guidance |
| `/rules`               | Manage custom rules         |

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


| `query_type`   | Use Case                                      |
| -------------- | --------------------------------------------- |
| `task`         | Broad requests — returns ranked workset      |
| `file`         | Get file structure and contents               |
| `symbol`       | Detailed info about a function/class/variable |
| `search`       | Search for symbols matching a pattern         |
| `dependencies` | What a symbol depends on / what depends on it |
| `outline`      | File/module structure overview                |
| `memory`       | Query workspace-global memory                 |
| `lsp`          | LSP-powered diagnostics, definitions, symbols |

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

### Context Compaction and Session Rotation

Reverie first attempts in-place context compaction near 70% of the active model's context window. If the compacted context still reaches the rotation threshold near 82%, it creates a structured handoff and rotates the session. Users can trigger the same compaction core at any time with `/compact`; `/compact <focus>` gives extra retention priority to details such as failed tests, provider quirks, or uncommitted files.

Compaction:

1. Saves a full pre-compaction checkpoint and lets session persistence archive the replaced transcript.
2. Preserves the recent interaction window verbatim.
3. Consolidates older turns and prior memory into a numbered continuation summary covering intent, technical decisions, files, pitfalls, verification, explicit constraints, pending work, current work, and the immediate next step.
4. Keeps planned, implemented, tested, committed, pushed, visually verified, and end-to-end verified states distinct.
5. Persists the compacted summary into project memory when that memory layer is active.

If rotation is still required, Reverie creates a new session with a structured handoff injected as working memory and retains the archived transcript and handoff packet for recovery.

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

### Workspace Mentions and Inline Media

Type `@` to search indexed workspace files and symbols. Code-symbol selections include a line range; image and video selections retain inline-media behavior.

```
# Reference code, a symbol, or an image in your message
"Review @src/auth.py"
"Update @src/auth.py#L40-L88"
"Review this screenshot: @./screenshot.png"
"Here's the design: @./mockup.png and @./diagram.jpg"
```

### Browser Control

Call the core's browser-control tool from an agent session. The tool controls Chromium; the Electron Desktop app does not provide an interactive browser tab panel:

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
metadata = get_nvidia_model_metadata("meta/muse-glimmer-30b")

# ModelScope
from reverie.modelscope import (
    get_modelscope_model_catalog,
    get_modelscope_model_metadata,
    build_modelscope_runtime_model_data,
    default_modelscope_config,
    normalize_modelscope_config,
    resolve_modelscope_openai_base_url,
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
# ("codex", "aihubmix", "agnes", "sensenova", "nvidia", "modelscope", "webgemini", "opencode")

# All supported active model source values (includes "standard")
print(SUPPORTED_ACTIVE_MODEL_SOURCES)
# ("standard", "codex", "aihubmix", "agnes", "sensenova", "nvidia", "modelscope", "webgemini", "opencode")
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
- Check the selected app root and project cache described in [Configuration](docs/CONFIGURATION.md)
- Pass the project path as the positional argument: `reverie "G:\Projects\MyProject"`

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
py -m reverie --debug

# Check the compiled/source kernel contract
py -m reverie --kernel-info

# Inside the interactive CLI: inspect source/configuration and probe availability
# /status
# /provider list
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
py -m pip install -e "ReverieCli-py[dev,treesitter,build]"

# Run tests
py -m pytest
```

---

## License

This project is licensed under the [MIT License](LICENSE).

---

## Links

- **Repository**: https://github.com/Lin-Silver/Reverie-Cli
- **Issues**: https://github.com/Lin-Silver/Reverie-Cli/issues
- **NVIDIA API Docs**: https://build.nvidia.com
- **Claude API Docs**: https://docs.anthropic.com
- **Gemini API Docs**: https://ai.google.dev

---

*Reverie CLI — Open-source agentic coding assistant. Built with Python and modern LLM APIs.Codex and Claude Code were of great assistance, especially Codex. GPT-5.6 completed the GUI version.*
