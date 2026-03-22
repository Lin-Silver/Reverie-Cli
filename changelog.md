## Reverie CLI v2.1.5 - LLM-First Session Rotation, Faster Streaming, and Better Diff Rendering

### Changed

* Refined automatic context rotation so the carryover memory is now LLM-authored from raw transcript windows, workspace memory, and prior handoff memory instead of falling back to an algorithm-first digest as the main carryover source.
* Added a repair pass for invalid handoff payloads. Reverie now asks the model to re-emit the handoff JSON when the first response is malformed or too empty, rather than silently degrading to a deterministic digest summary.
* Added automatic rotation backoff when handoff generation fails repeatedly, so the CLI does not spam compaction attempts on every follow-up model call.
* Enriched fresh sessions with both the readable working-memory summary and a compact structured handoff payload, improving continuity across multi-rotation implementation loops.
* Optimized streaming output performance by reusing the markdown formatter, switching assistant output to progressive line-level flushing, and replacing the live status token recount path with the agent's lightweight token estimate instead of repeated full re-tokenization.
* Upgraded diff presentation in tool-result cards so fenced `diff` blocks now render as syntax-highlighted previews with `+/-/hunk` stats, and refreshed the standalone diff panel with a cleaner badge header and folded-preview behavior for large patches.

## Reverie CLI v2.1.4 - Automatic Session Handoff, Retrieval Hardening, and Artifact Path Clarification

### Changed

* Replaced the old algorithm-first context compression path with automatic model-authored session handoff rotation. When token usage crosses the rotation threshold, Reverie now generates a structured carryover summary, starts a fresh session, restores the active user request into that new session, and continues the same turn without waiting for a manual `continue`.
* Added persisted session handoff packets under the project cache state (`.reverie/project_caches/<project>/session_handoffs/`) so automatic rotation has a durable audit trail and future recovery surface.
* Hid `context_management` from the model-facing tool surface and updated the system prompts so continuity is driven by automatic rotation, workspace memory, and durable artifacts instead of asking the model to self-compress manually.
* Hardened `codebase-retrieval` so plain-text files such as `README.md`, master documents, and appendix markdown files can be read through a content fallback even when they do not produce code symbols.
* Normalized `codebase-retrieval` search filters more defensively to avoid avoidable failures from non-string tool arguments.
* Clarified the runtime storage split across the codebase and prompts:
  * project documentation and generated docs stay in the project-root `artifacts/`
  * Reverie CLI runtime/session/cache state stays under the exe-root `.reverie/project_caches/`

## Reverie CLI v2.1.4 - Reverie-Atlas + Codex 0.115.0 Alignment

### Added

* Added persisted `atlas_mode` configuration so `Reverie-Atlas` can keep a real execution profile for research-first delivery, master-document naming, appendix expectations, confirmation flow, and post-document implementation behavior.
* Added stronger `Reverie-Atlas` guidance so the mode now produces the document bundle, explains it to the user, confirms the document information, and then continues into slow, rigorous, document-driven implementation instead of stopping at docs alone.
* `Reverie-Atlas` intentionally excludes `task_manager` and `Tasks.md` workflows, replacing them with a research-first, document-architecture-driven prompt and tool playbook.
* Added mode aliases so legacy phrasing like `reverie-deeper` or `deeper` now resolves cleanly to `Reverie-Atlas`.

### Changed

* Re-aligned the built-in Codex model catalog against the downloaded `references/codex-main` source tree, including the current GPT-5.x lineup plus `gpt-oss-120b` and `gpt-oss-20b`, while preserving hidden-but-supported ids for direct selection.
* Updated Codex reverse-proxy URL resolution so ChatGPT roots, `/backend-api`, proxy base URLs, full `/responses` URLs, and `/models` URLs normalize more safely without double-appending or misrouting.
* Updated mode help, prompt routing, config injection, and documentation so `Reverie-Atlas` is described as a document-driven implementation mode rather than a docs-only mode.

## Reverie CLI v2.1.3 - Post-Release Updates (Still v2.1.3) - Reverie-Gamer Production Upgrade + Reverie Engine Lite

**Release Date:** 2026-03-16

### Highlights
* Rebuilt `reverie-gamer` into a stronger end-to-end game-production workflow: the active Gamer system prompt now pushes blueprint-first planning, engine-aware scaffolding, playable-first delivery, proactive verification loops, and repeated balance/playtest iteration instead of stopping at design docs.
* Added three major Gamer tools for large-scale game creation: `game_design_orchestrator` for structured blueprints and vertical-slice planning, `game_project_scaffolder` for engine-aware project foundations and content pipelines, and `game_playtest_lab` for telemetry schemas, quality gates, session-log analysis, and feedback synthesis.
* Added `Reverie Engine Lite` as Reverie's first-party built-in runtime, with a data-driven scene/prefab format, project scaffolding helpers, deterministic smoke testing, and three built-in samples spanning `2D`, `2.5D`, and `3D`.
* Added a new `/engine` CLI surface for `profile`, `create`, `sample`, `run`, `smoke`, and `test`, so Reverie can create and validate built-in runtime projects without requiring an external engine.
* Upgraded existing Gamer tools so previously advertised advanced actions now really work: asset dependency/compression/size analysis, narrative consistency and pacing checks, character-arc analysis, NPC placement and spatial analysis, trend/anomaly stats, and custom simulation pipelines.
* Expanded the CLI game workflow with new `/blueprint`, `/scaffold`, and `/playtest` commands, while upgrading `/gdd` with validation/version/export flows and turning `/assets` into a fuller asset workbench for manifests, dependency graphs, optimization, and diagnostics.
* Strengthened generic `reverie` mode as well: mode switching is now more proactive in the system prompt, and verification is treated as a required debug-and-retest loop instead of an optional final step.

### Supported Game Creation Coverage
* **2D games**: platformers, metroidvanias, top-down action games, roguelikes, bullet hell shooters, JRPGs, tactics games, deckbuilders/card games, puzzle games, visual novels, and management/simulation projects.
* **2.5D games**: isometric ARPGs, tactics/strategy games, Diablo-like loot games, cinematic platformers, survival-horror hybrids, and fixed-camera exploration projects.
* **3D games**: action-adventure games, RPGs, open-zone/open-world projects, FPS/TPS combat games, survival/crafting games, dungeon crawlers, immersive sims, racing prototypes, and systemic sandbox experiences.
* **Engine/runtime coverage**: built-in `Reverie Engine Lite`, custom runtime workflows, web stacks (`Phaser`, `PixiJS`, `Three.js`), lightweight Python/Lua stacks (`Pygame`, `Love2D`), and engine-aware project structures for `Godot`, `Unity`, and `Unreal`.

### Notes
* `reverie-gamer` now has the strongest results when used as a production loop: blueprint -> scaffold -> first playable -> simulation -> playtest -> telemetry-informed iteration.
* The CLI now exposes the new game-production surfaces directly, including the first-party engine runtime, so Gamer workflows no longer depend only on in-chat tool calling.

---

## Reverie CLI v2.1.3 - Computer Controller, Mode Switching, and Context Intelligence

**Release Date:** 2026-03-15

### Highlights
* Added `computer-controller` mode as a dedicated desktop-control workflow powered by NVIDIA-hosted `qwen/qwen3.5-397b-a17b`, plus a new unified `computer_control` tool for screenshot observation, mouse actions, keyboard input, scrolling, dragging, waits, and screen-state inspection.
* Added `/nvidia` provider management with interactive API-key entry, model activation, endpoint overrides, and automatic source switching when entering Computer Controller mode.
* Added `switch_mode` so non-desktop modes can proactively move between Reverie, Reverie-Gamer, Reverie-Ant, Spec-Driven, Spec-Vibe, and Writer while updating tool availability and system prompts in-session.
* Reworked the main Reverie system prompt for generic LLMs with stronger repository-first retrieval, spec-style planning discipline, full-project delivery expectations, and a stricter test/build/verification standard.
* Upgraded workspace memory and Context Engine flow: session-level memory is now refreshed back into the active conversation, workspace-global memory summaries are injected automatically, `codebase-retrieval` can query memory/LSP data, and an optional LSP bridge exposes diagnostics, definitions, symbols, and status.
* Improved provider transport reliability: Codex models are standardized to `258K`, iFlow now reads the current CLI settings/remote model catalog more accurately, direct iFlow requests use CLI-style signed headers, and request-provider response parsing is more robust across wrapped text/reasoning payloads.

### Notes
* Computer Controller mode is intentionally isolated from `switch_mode`; it is entered explicitly and stays focused on desktop control instead of general coding workflows.
* iFlow direct requests now include a compatibility fallback when the upstream rejects tool-related OpenAI fields, reducing `406` failures on stricter accounts or models.

---

## Reverie CLI v2.1.2 - Workspace Sandbox & Command Audit

**Release Date:** 2026-03-14

### Highlights
* Locked AI file access to the active Reverie workspace: file creation, editing, deletion, config/story/game tools, image upload, and path-based helpers now reject escapes, absolute out-of-workspace paths, and `..` traversal.
* Rebuilt `command_exec` into a read-only, audited diagnostic surface: arbitrary shells/interpreters are blocked, unsafe control operators are rejected, workspace cwd is enforced, and every allowed/blocked attempt is written to `.reverie/security/command_audit.jsonl`.
* Hardened archive extraction against zip-slip path escapes and tightened tool-side path validation across asset import/export and checkpoint restore flows.
* Tightened risky subprocess surfaces for security-first deployments: text-to-image auto dependency installation is disabled by default, unsafe passthrough arguments are blocked, and generation now requires the bundled trusted runtime.
* Added regression coverage for workspace escape blocking, command audit logging, and malicious archive extraction attempts.

### Post-Release Updates (Still v2.1.2) - 2026-03-14
* Refined `command_exec` so safe `.NET` scaffolding and solution/project management commands (such as `dotnet new sln -n ...`) are allowed again, but only inside a workspace-local sandbox with redirected `DOTNET_CLI_HOME`, NuGet caches, and temp directories.
* Added `/clean` to delete only the current workspace's memory/cache/audit state, including the matching `project_caches/<workspace-id>` folder and workspace-local `.reverie/context_cache` / `.reverie/security`, while preserving config and rules.
* Kept higher-risk `.NET` execution flows such as `build`, `test`, `run`, `publish`, `restore`, `tool`, `workload`, and `dev-certs` blocked because they cannot guarantee the same strict workspace boundary.

---

## Reverie CLI v2.1.1 - Command Flow, UX, and Memory Upgrade

**Release Date:** 2026-03-12

### Highlights
* Refined the TUI without changing the Dreamscape palette: denser help/settings dashboards, richer tool cards and response headers, better selector layouts, stronger narrow-terminal fit, persistent stream-time input, `Esc` interruption, and the restored original banner.
* Reworked iFlow, Qwen Code, Gemini CLI, and Codex relay integration with cleaner model catalogs, endpoint overrides, safer request formatting, and Codex four-level reasoning mapped onto the supported GPT-5.x Codex lineup.
* Simplified command flow: `/help` is now a focused browser-plus-detail system, `/setting` is faster and more structured, `/codex` directly switches Reverie onto Codex, `/codex model` continues into reasoning selection, and redundant command surfaces were trimmed.
* Strengthened session continuity: context compression now consolidates prior memory blocks, preserves stronger memory anchors and a larger recent interaction window, and session rotation carries a richer working-memory digest forward.
* Hardened local secret handling and config persistence, including environment-based Gemini OAuth credentials and safer writes for local auth/config JSON.

### Post-Release Updates (Still v2.1.1) - 2026-03-12
* Gemini CLI relay now works with personal Google-account login without requiring a project id, preserves Gemini thought signatures across tool loops, and adds `gemini-3-pro-preview` plus `gemini-3-flash-preview`.
* Gemini CLI now mirrors the official Code Assist bootstrap flow before chat requests, automatically resolving the managed project via `loadCodeAssist/onboardUser` so `streamGenerateContent` no longer fails with empty-project 500s.
* Gemini CLI token refresh now falls back to the locally installed official `gemini` bundle when env vars are not set, and expired-token paths fail fast with clearer auth errors instead of opaque upstream 401s.
* Streaming follow-up input is now a plain prompt line instead of a large live box, and unsent draft text is preserved after normal completion or interruption.

---

## Reverie CLI v2.1.0 - Session Memory & Reliability

**Release Date:** 2026-02-27

### Highlights
* Session snapshots, cross-session memory indexing, and improved session rotation
* Safer payload handling, faster Context Engine indexing, and steadier CLI integrations

### Post-Release Updates (Still v2.1.0) - 2026-03-04
* Stabilized Python 3.14 build flow, web search fallback, and TTI dependency retries
* Tightened prompt/tool-calling reliability and packaging checks

### Post-Release Updates (Still v2.1.0) - 2026-03-09
* Reworked iFlow, Qwen, Gemini CLI, and Codex relay integration with native commands and endpoint overrides
* Fixed provider catalogs: Qwen now uses `coder-model` at 1M context, iFlow aligns to the current CLI list, and Codex is limited to the supported GPT-5.x Codex models
* Added Codex reasoning-depth selection and extra message/tool-call sanitization to reduce relay format errors

### Post-Release Updates (Still v2.1.0) - 2026-03-10
* Added CLI-style Codex reasoning selection with `Low`, `Medium`, `High`, and `Extra High` labels
* Reworked live tool/log rendering into structured tool cards with clearer status details

### Post-Release Updates (Still v2.1.0) - 2026-03-11
* Fixed the `/codex thinking` selector path and refreshed `/help` into a denser grouped layout
* Expanded `/help` into a full command catalog with all subcommands, per-command drill-down via `/help <command>`, and synced command-completion descriptions
* Turned `/help` into a browser-style command guide: live navigation, full child-command previews, filterable help pages, and pinned detail panels that stay in the transcript after exit
* Added per-subcommand examples to the detailed help panels and expanded `/setting` into a richer settings dashboard with direct subcommands for mode, model, theme, API, workspace, and rules controls
* Optimized startup and settings performance: terminal clear is now lightweight, `/setting` no longer hits provider runtime resolution while rendering, and the settings TUI now refreshes only on input with better full-screen detail visibility
* Fixed non-maximized terminal behavior for interactive help/settings/selectors: normal scrollback is preserved, wheel scrolling stays with the terminal, and medium-width windows keep more panels side-by-side instead of clipping the lower content
* Streaming replies can now be interrupted with `Esc`, and Reverie keeps a live bottom input bar so you can type and submit a follow-up while output is still in progress
* Hardened secret handling: Gemini OAuth client credentials now come from environment variables, local config/oauth JSON writes use safer file writes, and token refresh errors no longer echo raw response bodies
* Normalized supported Codex model metadata so all GPT-5.x Codex variants now report a 258K context window in Reverie
* Reworked the core TUI: responsive welcome card, compact live status panel, clearer response headers, richer tool cards, denser selectors, and cleaner command completion
* Improved terminal adaptation and input UX: multiline input now preserves structure, selector focus/empty states are clearer, and narrow terminals get more compact layouts

---

## 🚀 Reverie CLI v2.0.4 — Qwen Code Integration Fix & Enhancement

**Release Date:** 2025-02-22

### 🔧 Critical Fixes
* **Built-in Qwen Code Proxy**: Added native Qwen Code credential support with automatic endpoint detection
* **Dynamic Endpoint**: Reads `resource_url` from OAuth credentials for user-specific API endpoints
* **Model Context Length**: Fixed all Qwen Code model context lengths (Qwen3.5-Plus: 262K, Qwen3-Coder-Plus: 32K, Qwen3-Coder-Flash: 8K, Qwen3-Vision: 32K)
* **Token Display**: Real-time token counting with color-coded warnings (green/yellow/red)

### ✨ New Features
* **Enhanced Credential Management**: Automatic `resource_url` extraction with DashScope fallback
* **Helper Functions**: OAuth login, credential saving, and improved detection with `resource_url` support

### 🔄 Technical Improvements
* API endpoint now correctly uses DashScope compatible mode
* Credential priority: `oauth_creds.json` > `qwen_accounts.json`
* Full compatibility with qwen-code CLI v1.x and OAuth 2.0 device flow

---

## 🚀 Reverie CLI v2.0.3 — Critical Fixes & Enhanced Context Management

**Release Date:** 2026-02-17

### 🔧 Critical Fixes
* **Session Preservation on Model Switch**: Fixed critical bug where switching models would delete conversation history and session context. Messages are now properly preserved when changing models.
* **Request Provider Thinking Mode**: Enhanced API calling for request provider to properly support thinking mode with `chat_template_kwargs` parameter
* **Vision Support**: Added vision file upload capability for request provider models that support image analysis

### 🎯 New Features
* **Vision Upload Tool**: New `vision_upload` tool for uploading and processing images (PNG, JPG, GIF, BMP, WEBP, TIFF)
  - Supports image analysis, description, and OCR
  - Base64 encoding for AI model processing
  - Works with request provider models that have vision capabilities
* **Token Counter Tool**: New `count_tokens` tool for accurate token counting
  - Uses tiktoken library for precise token counts
  - Can check current conversation token usage
  - Displays usage percentage and warnings
  - Helps manage context limits proactively
* **Real-time Token Display**: Status bar now shows current token usage
  - Color-coded display (green < 60%, yellow 60-80%, red > 80%)
  - Shows total tokens, max tokens, and usage percentage
  - Updates in real-time during conversation
* **Context Engine Command**: New `/CE` command for manual context management
  - `/CE` - Show context status and token usage with color-coded warnings
  - `/CE compress` - Manually compress conversation context
  - `/CE info` - Show detailed context information and message breakdown
  - `/CE stats` - Show comprehensive context statistics
  - Case-sensitive command (must use uppercase CE)
* **Enhanced Context Management**: Updated system prompts to encourage proactive context management
  - AI now monitors token usage and suggests compression at 60% threshold
  - Automatic context optimization before large operations
  - Better integration with Context Engine for long conversations

### 📚 System Prompt Updates
* Added comprehensive tool descriptions for vision upload, token counting, and context management
* Separated tool descriptions into dedicated module (`tool_descriptions.py`) for maintainability
* Enhanced instructions for proactive context management across all modes
* Updated all 5+ mode-specific system prompts with new tool capabilities

### 🔄 API Improvements
* Enhanced request provider to support `chat_template_kwargs` for thinking mode
* Improved thinking mode detection and parameter passing
* Better handling of model suffixes like `model(thinking)` for request provider
* Fixed API payload validation and sanitization

---

## 🚀 Reverie CLI v2.0.2 — iFlow CLI Integration

**Release Date:** 2026-02-15

### ✨ iFlow CLI Integration
* **Direct API Integration**: Built-in iFlow CLI credential support for direct API access
* **Model Access**: Free access to powerful iFlow models including GLM-5-thinking
* **Credential Auto-Detection**: Automatically reads iFlow credentials from `~/.iflow/`
* **Proxy Compatibility**: Seamless integration with existing iFlow proxy servers

### 🎯 Key Improvements
* **Simplified Setup**: No need for external proxy server configuration
* **Enhanced Reliability**: Direct connection handling for better stability
* **Credential Management**: Automatic credential detection and refreshing

---

## 🚀 Reverie CLI v2.0.1 — Text-to-Image Integration & Stability Fixes

**Release Date:** 2026-02-13

### 🖼️ Text-to-Image Tool (All Modes)
* Added new `text_to_image` tool, available across all modes
* Integrated local generation flow through `Comfy/generate_image.py`
* Added support to list configured text-to-image models from `config.json`
* Added support to generate images using:
  - Configured model index
  - Explicit absolute model path
  - Explicit relative model path

### ⚙️ Config Upgrade
* `config.json` now includes `text_to_image` section with:
  - `model_paths` list for multiple model files
  - Runtime options (script path, Python executable, output directory, defaults)
* Config migration now auto-fills missing `text_to_image` fields
* Config schema version bumped to `2.0.1`
* Build pipeline now embeds required text-to-image resources (`generate_image.py`, `embedded_comfy.b64`) into the EXE bundle path

### 🐛 Logic Fixes
* Fixed duplicate `UserInputTool` registration in tool export/executor lists
* Fixed potential `NameError` in `Comfy/generate_image.py` when resolving fallback model paths
* Unified mode values in settings menu to canonical names (`reverie-ant`, `spec-driven`)
* Added advanced parameter passthrough support (`extra_options`, `extra_args`) for text-to-image generation

---

## 🚀 Reverie CLI v2.0.0 — Reverie-Gamer Mode & Game Dev Toolchain

**Release Date:** 2026-02-04

### 🎮 Reverie-Gamer Mode (New)
* **GDD-First Workflow**: Game Design Document must be created/updated before implementation
* **RPG Focus**: Dedicated narrative and quest design emphasis for RPG projects
* **Engine Coverage**: Custom engine development, Web games (Phaser/PixiJS/Three.js), and 2D frameworks (Pygame/Love2D/Cocos2d)

### 🧰 Game Development Toolchain (All Self-Made)
* **GDD Manager**: Create/view/update GDD templates with RPG sections
* **Story Design**: Story bible, questlines, NPC profiles, dialogue samples
* **Asset Manager**: List assets, detect missing references, generate manifests, import assets
* **Asset Packer**: Zip packaging with manifest generation
* **Balance Analyzer**: Combat/economy/difficulty/stat distribution analysis
* **Math Simulator**: Monte Carlo simulations for balance tuning
* **Stats Analyzer**: Percentiles and distribution metrics for datasets
* **Level Design Tool**: Layout generation, logic checks, difficulty analysis
* **Config Editor**: JSON/YAML/XML read/edit/validate/template generation

### 🧭 Task Management Upgrade
* Added phases, priorities, tags, progress, estimates, dependencies, and blockers
* Filtering support for focused task views (state/phase/tag/priority)

### 🧠 Context Engine Integration
* Lightweight script parsing for Love2D (Lua) and Godot (GDScript)
* Game-specific context compression via summarize_game_context

### 🖥️ CLI Enhancements
* New `/mode` command for fast mode switching (including reverie-gamer)
* New `/gdd` and `/assets` commands for gamer workflows

---

## 🚀 Reverie CLI v1.4.1 — Advanced Context Engine & Nexus Integration

**Release Date:** 2026-01-17

### 🧠 Context Engine Major Enhancements
* **Semantic Indexer**: Added deep code understanding through semantic analysis and pattern recognition
* **Knowledge Graph**: Implemented advanced relationship tracking with impact analysis and architecture understanding
* **Commit History Indexer**: Added learning from past changes with pattern extraction and team convention detection
* **Context Engine Core**: Unified context management system integrating all advanced components

### 🔧 Nexus Tool - Large-Scale Project Development
* **24+ Hour Support**: Enabled continuous work sessions for large projects with external context management
* **Phase-Based Workflow**: Structured development phases (Planning, Design, Implementation, Testing, Integration, Documentation, Verification, Completion)
* **Persistent State**: Automatic checkpoint and recovery for long-running tasks
* **Token Limit Bypass**: External context storage to handle projects beyond typical token limits
* **Self-Healing**: Automatic error recovery and state management

### 💾 Enhanced Checkpoint System
* **File-Level Checkpoints**: Automatic snapshots before file modifications
* **TUI Rollback Interface**: Interactive checkpoint selection and restoration
* **Version History**: Track multiple versions of each file with timestamps
* **Automatic Cleanup**: Remove old checkpoints after configurable time period

### 📝 Session Management Improvements
* **Timestamp-Based Naming**: Session files now use creation time (YYYYMMDD_HHMMSS format)
* **Enhanced Metadata**: Improved session tracking with detailed timestamps

### ✍️ Writer Mode Enhancements
* **Mandatory Outline Phase**: Complete novel outline must be created and approved before writing
* **Structured Outline Format**: Comprehensive outline with characters, setting, plot summary, chapter breakdown, themes, and key plot points
* **User Review Workflow**: Outline must be reviewed and approved by user before proceeding to content creation

### 🎨 TUI Interaction Improvements
* **Keyboard Navigation**: Arrow key navigation (up/down) for all selectors
* **Enter to Confirm**: Consistent Enter key behavior for selections
* **Escape to Cancel**: Escape key cancels operations or exits dialogs
* **Visual Highlighting**: Clear visual indication of selected items
* **Search Support**: Filter lists with search functionality (/ key)
* **Smooth Scrolling**: Page Up/Down support for long lists
* **Modern Selectors**: Specialized selectors for models, settings, sessions, and checkpoints

### 🤖 System Prompt Updates
* **Advanced Context Engine Documentation**: Added comprehensive documentation for semantic indexing, knowledge graph, and commit history features
* **Nexus Tool Integration**: Added instructions for using Nexus in large-scale project development
* **Enhanced Context Usage Guidelines**: Updated rules for leveraging advanced context engine capabilities

### 🐛 Bug Fixes
* Fixed session naming to use precise timestamps
* Improved checkpoint management reliability
* Enhanced TUI selector responsiveness

---

## 🚀 Reverie CLI v1.4.0 — Reverie-Ant Autonomous Agentic Enhancement

**Release Date:** 2026-01-12

### 🤖 Reverie-Ant Mode Major Overhaul

#### Core Autonomy Enhancements
* **Autonomous Decomposition**: Agent intelligently breaks user requests into coherent sub-tasks without requiring explicit instruction
* **Intelligent Planning Phase**:
  - Deep codebase analysis using Context Engine before design
  - Comprehensive design documentation in implementation_plan.md
  - Detailed task breakdown with atomic work items
  - Design decision storage for team alignment and learning
* **Advanced Execution Phase**:
  - Component-by-component implementation with continuous testing
  - Immediate verification after each component
  - Integration testing and cross-interface validation
  - Terminal-based build verification and test execution
  - Browser-based UI/API validation for web applications
* **Comprehensive Verification Phase**:
  - Unit, integration, and end-to-end testing
  - Walkthrough documentation with validation metrics
  - Continuous learning and pattern storage

#### Cross-Interface Automation
* Direct access to editor (code generation, modification, inspection)
* Terminal integration (build, test, execution with PowerShell)
* Browser integration (UI validation, API testing, user flow verification)
* End-to-end development workflows fully automated

#### Transparent Artifact Generation
* **task.md**: Living checklist with atomic work items, continuously updated
* **implementation_plan.md**: Comprehensive technical design for user review
* **walkthrough.md**: Final proof of work with testing results and validation metrics
* All artifacts automatically stored in Context Engine for future reuse

#### Context Engine Deep Integration
* **Planning Phase**: Store design decisions, architectural patterns, and constraints
* **Execution Phase**: Reference stored patterns, document new implementations, record learnings
* **Verification Phase**: Validate against stored design decisions, archive results and metrics
* Artifacts automatically tagged and searchable for knowledge reuse across projects

#### Intelligent Task Tracking
* **task_boundary Tool**: Transparent progress UI with mode (PLANNING/EXECUTION/VERIFICATION) tracking
* Frequent updates showing cumulative progress and next steps
* Real-time status synchronization with user
* Estimated scope communication for each phase

#### Smart User Communication
* **notify_user Tool**: Primary mechanism for artifact review requests and user feedback
* BlockedOnUser flag for clear dependency on user approval
* Batch feedback requests to minimize interruptions
* Graceful mode transitions between planning, execution, and verification

#### Intelligent Debugging & Adaptation
* Systematic error analysis instead of simple retries
* Pattern-based fix strategies using Context Engine
* Continuous learning from debugging experiences
* Automatic documentation of workarounds and solutions

#### Identity Correction
* ✓ Fixed system prompt identity: Agent now correctly identifies as "Reverie" (not "Antigravity")
* Unified identity across all modes while maintaining distinct behavioral patterns

### 🧠 Context Engine Optimization

* **Pattern Learning**: Automatic storage and retrieval of project-specific patterns
* **Design Decision Archiving**: All major decisions stored with rationale and tradeoffs
* **Artifact History**: Searchable record of all task artifacts for knowledge transfer
* **Team Alignment**: Stored decisions enable consistent approach across team members
* **Future Project Boost**: Artifacts from current project accelerate future similar work

### 📋 Advanced Execution Workflow

```
Planning Phase:
  1. Rapid codebase understanding via codebase_retrieval
  2. Complex system analysis and pattern discovery
  3. Design decision documentation in Context Engine
  4. Task breakdown with atomic work items
  5. Implementation plan creation
  6. User review request via notify_user

Execution Phase:
  1. Review and acknowledge implementation_plan.md
  2. Component-by-component implementation
  3. Immediate testing after each component
  4. Context Engine pattern reference and storage
  5. Continuous task_boundary updates
  6. Terminal-based builds and test execution

Verification Phase:
  1. Unit test execution and coverage reporting
  2. Integration testing across components
  3. End-to-end testing (UI, API, user flows)
  4. Walkthrough creation with validation metrics
  5. Context Engine storage of test results
  6. Final quality review before completion
```

### 🛠️ Tool Enhancements

* **task_boundary Tool**: Now with detailed documentation and best practices
  - Frequent progress updates (every 2-3 tool calls)
  - Cumulative TaskSummary for full context awareness
  - Mode switching support (PLANNING → EXECUTION → VERIFICATION)
  - Predicted scope estimation

* **notify_user Tool**: Simplified and enhanced
  - Removed complex ShouldAutoProceed logic
  - Cleaner artifact review workflow
  - Better integration with task mode UI
  - Clear BlockedOnUser semantics

### 💡 Continuous Learning System

* **Pattern Recognition**: Agent learns project-specific patterns during execution
* **Best Practice Documentation**: Successful approaches automatically stored
* **Style Adaptation**: Learns user coding style and preferences
* **Context Reusability**: Future tasks benefit from archived knowledge
* **Team Knowledge Base**: Shared patterns and decisions across projects

### 🎯 Development Verification

* **Automated Testing**: Unit, integration, and end-to-end tests run automatically
* **Browser Validation**: Web app features verified through actual UI/API interaction
* **Terminal Operations**: Build, packaging, and deployment commands executed systematically
* **Coverage Reporting**: Test coverage metrics captured in walkthrough

### 🔐 Robustness Improvements

* **Systematic Debugging**: Error analysis with pattern matching instead of retries
* **Graceful Fallback**: Intelligent alternative approaches when standard solutions fail
* **State Tracking**: task.md maintains complete work status throughout project
* **Decision Logging**: All architectural choices documented with rationale

### 📚 Documentation Enhancements

* More detailed system prompts with concrete examples
* Context Engine integration guidelines for each phase
* Tool usage best practices with scenarios
* Planning phase deep-dive workflow documentation
* Execution workflow with intelligent debugging strategies

### ⚡ Performance & Efficiency

* **Reduced Iteration Cycles**: Better planning reduces rework
* **Parallel Operations**: Tool calls optimized for parallel execution
* **Smart Caching**: Context Engine enables pattern reuse
* **Progressive Artifact Building**: task.md and walkthrough.md updated incrementally

---

## ✨ Reverie CLI v1.3.1 — Thinking Display Update

**Release Date:** 2026-01-04

### 💭 Thinking Model Support

* Added support for displaying **thinking/reasoning content** from AI models
* Compatible with thinking models like OpenAI o1, DeepSeek-R1, Claude's extended thinking, etc.
* Thinking content is displayed in a special **italic purple style** to distinguish from regular responses
* Visual header with 💭 emoji indicates when the model is thinking
* Line-by-line streaming of thinking content for better real-time experience

### 🎨 Theme Enhancements

* New **thinking-specific color palette** (twilight purple tones)
* Added thinking-related decorators (💭, 🔮, 🧠, ⟐)
* New `DreamText` helpers for thinking content formatting

### 🔧 Internal Improvements

* Added `THINKING_START_MARKER` and `THINKING_END_MARKER` for stream processing
* Enhanced streaming logic to handle `reasoning_content` and `thinking` API fields
* New `_print_thinking_content()` helper method in interface

---

## ✨ Reverie CLI v1.3.0 — Dreamscape Update

**Release Date:** 2025-12-28

### 🌈 Dreamscape Theme System

* Introduced a brand-new **Dreamscape visual theme**
* Pink / purple / blue aesthetic for a more immersive CLI experience
* Unified colors, decorations, and text styles across the entire interface

### 🎨 UI & UX Improvements

* Refreshed CLI layout, banners, panels, tables, and status messages
* Themed Markdown rendering (headers, lists, inline styles)
* Improved input prompts, command completion, and interactive flows
* Redesigned command outputs, help pages, and settings UI
* Clearer, more readable agent and tool output formatting

### 🐛 Streaming Output Fixes

* Fixed fragmented streaming text issues
* Prevented duplicate model responses
* Improved end-token handling to avoid hiding valid content
* Smoother and more reliable real-time output

### 🔧 Internal Improvements

* Centralized theme management for better consistency
* Simplified streaming and formatting logic
* Slight performance improvements and fewer redundant API calls

### 🧩 Compatibility

* No breaking changes
* No new dependencies added
