"""
Tool descriptions used inside system prompts.

This module keeps the prompt-side tool playbooks synchronized with the actual
runtime tool surface, especially for Reverie mode where the model is expected
to operate autonomously across planning, implementation, verification, memory,
and mode transitions.
"""

from ..modes import normalize_mode
from ..tools.task_manager import TASK_MANAGER_TOOL_DESCRIPTION


def get_codebase_retrieval_description() -> str:
    """Description for codebase retrieval."""
    return """
## Context Retrieval Tool (codebase-retrieval)

Use this tool before non-trivial edits, design changes, or code explanations.

**Primary query types**:
- `symbol`: inspect one function/class/method in detail
- `file`: inspect a file structure and contents
- `search`: find matching symbols or names
- `dependencies`: inspect incoming/outgoing relationships
- `outline`: get a structural file summary
- `task`: build a curated multi-file context package for an edit, bug, or feature request
- `memory`: query workspace-global memory distilled from earlier sessions
- `lsp`: query diagnostics, definitions, document symbols, workspace symbols, or LSP status

**Best usage pattern**:
1. If the request is multi-file, ambiguous, or phrased as a task, start with `task`.
2. Then use `search` or `symbol` to lock onto the exact implementation.
3. Inspect the containing file or nearby dependencies.
4. Check usages before editing shared code.
5. Use `memory` and `lsp` when session continuity or semantic navigation matters.

**Example calls**:
```
codebase-retrieval(query_type="symbol", query="ReverieInterface._init_agent")
codebase-retrieval(query_type="file", query="reverie/agent/agent.py")
codebase-retrieval(query_type="task", query="add durable logging around context rotation failures")
codebase-retrieval(query_type="dependencies", query="process_message", direction="incoming")
codebase-retrieval(query_type="lsp", query="reverie/agent/agent.py", lsp_action="diagnostics")
```
"""


def get_git_commit_retrieval_description() -> str:
    """Description for git history retrieval."""
    return """
## Git History Tool (git-commit-retrieval)

Use this tool when history is likely to improve the current change.

**Primary query types**:
- `file_history`
- `symbol_history`
- `blame`
- `commit_details`
- `search`
- `recent`
- `uncommitted`

**When to use it**:
- A pattern already exists in earlier commits
- You need to understand why code was written a certain way
- You want to inspect regressions or prior fixes
- You need blame or commit context before changing a fragile area

**Example calls**:
```
git-commit-retrieval(query_type="file_history", target="reverie/config.py", limit=8)
git-commit-retrieval(query_type="search", target="context compression", limit=10)
git-commit-retrieval(query_type="blame", target="reverie/agent/agent.py", start_line=1000, end_line=1100)
```
"""


def get_str_replace_editor_description() -> str:
    """Description for the main file-editing tool."""
    return """
## Editor Tool (str_replace_editor)

This is the primary in-workspace editing tool for modifying existing files.

**Commands**:
- `view`: inspect file contents with line numbers
- `str_replace`: replace one exact unique string with another
- `insert`: insert text before a 1-based line number
- `create`: create a file from inside the editor flow

**Editing rules**:
- Use `codebase-retrieval` first on non-trivial edits.
- For `str_replace`, `old_str` must match exactly, including whitespace.
- Prefer `str_replace` for targeted edits and `insert` for narrow additions.
- Use `create_file` or full rewrites only when that is materially cleaner.

**Example calls**:
```
str_replace_editor(command="view", path="reverie/agent/agent.py", view_range=[100, 180])
str_replace_editor(command="str_replace", path="reverie/agent/agent.py", old_str="return old_value", new_str="return new_value")
str_replace_editor(command="insert", path="reverie/config.py", insert_line=42, new_str="NEW_FLAG = True\\n")
```
"""


def get_create_file_description() -> str:
    """Description for creating new files."""
    return """
## File Creation Tool (create_file)

Create a brand-new file inside the active workspace.

**When to use it**:
- A file does not exist yet
- You are scaffolding a new module or config file
- A clean full-file create is better than piecemeal edits

**Important**:
- Provide the full file content in `content`
- Use `overwrite=true` only when intentionally replacing an existing file
- Prefer `str_replace_editor` for modifying existing files

**Example call**:
```
create_file(path="reverie/modes.py", content="...", overwrite=False)
```
"""


def get_workspace_file_ops_description() -> str:
    """Description for non-destructive file operations."""
    return """
## Workspace File Operations Tool (file_ops)

Use this tool for non-destructive filesystem work inside the active workspace.

**Supported operations**:
- `read`
- `list`
- `exists`
- `info`
- `mkdir`

**When to use it**:
- You need to inspect file contents or directory structure
- You want quick existence or metadata checks
- You need to create a directory without editing a file

**Important**:
- `file_ops` does not delete files
- Use `delete_file` for file deletion
"""


def get_delete_file_description() -> str:
    """Description for dedicated file deletion."""
    return """
## Delete File Tool (delete_file)

Delete exactly one file inside the active workspace.

**Rules**:
- The path must resolve inside the current workspace
- Directory deletion is not allowed
- `confirm_delete=true` is required
- Prefer this tool any time a file should be removed

**Example**:
```
delete_file(path="logs/debug.log", confirm_delete=True)
```
"""


def get_workspace_command_description() -> str:
    """Description for workspace command execution."""
    return """
## Workspace Command Tool (command_exec)

Run audited terminal commands inside the active workspace.

**Rules**:
- Normal project-local commands are allowed
- Terminal move/delete/rename commands are blocked
- Inline scripts and script files are scanned for common file move/delete APIs
- The working directory must remain inside the active workspace
- Use `delete_file` for actual file deletion

**Best uses**:
- builds, tests, lint, type-check, smoke checks
- `git status`, `git diff`, safe diagnostics
- scaffolding commands that do not break workspace safety policy

**Good examples**:
```
command_exec(command="git status")
command_exec(command="python -m py_compile reverie/agent/agent.py")
command_exec(command="dotnet new sln -n Reverie.Downloader")
```
"""


def get_web_search_description() -> str:
    """Description for enhanced web search."""
    return """
## Web Search Tool (web_search)

Search the web with resilient fallback and optional page extraction.

**Minimal call (preferred)**:
```
web_search(query="python contextvars tutorial")
```

**Key parameters**:
- `query`
- `max_results`
- `fetch_content`
- `include_domains` / `exclude_domains`
- `recency`
- `request_timeout` / `max_retries` / `fetch_workers`
- `max_content_chars`
- `output_format`

**Best usage pattern**:
1. Start with just `query`
2. Add domain filters only when needed
3. Use it for unstable external facts, APIs, products, providers, docs, or exact references
"""


def get_tool_catalog_description() -> str:
    """Description for runtime tool discovery."""
    return """
## Tool Catalog Tool (tool_catalog)

Search or inspect the tools currently visible to the active agent.

**Operations**:
- `list`: show the visible tool surface for the current or specified mode
- `search`: search tools by keywords across names, descriptions, and parameter names
- `inspect`: inspect one tool's parameters and schema details
- `recommend`: ask which tools best fit a short task description
- `groups`: summarize the visible tool surface by category and kind

**When to use**:
- You are unsure which built-in, MCP, or runtime-plugin tool best fits the task
- The request may depend on dynamic tools that were loaded after startup
- You need the exact parameter names for a tool before calling it
- You want a safer first pass that favors read-only tools before editing

**Example calls**:
```
tool_catalog(operation="search", query="mcp resource")
tool_catalog(operation="inspect", tool_name="command_exec")
tool_catalog(operation="recommend", query="inspect repo files then run tests")
tool_catalog(operation="list", mode="reverie-gamer")
```
"""


def get_skill_lookup_description() -> str:
    """Description for runtime skill discovery."""
    return """
## Skill Lookup Tool (skill_lookup)

Inspect Codex-style `SKILL.md` files that Reverie has discovered.

**Operations**:
- `list`
- `search`
- `inspect`

**When to use**:
- A detected skill seems relevant and you need its exact instructions
- You want to confirm the summary or path of a skill before following it
- The user references a skill indirectly and you want to search for the closest match

**Example calls**:
```
skill_lookup(operation="list")
skill_lookup(operation="search", query="openai docs")
skill_lookup(operation="inspect", skill_name="plugin-creator")
```
"""


def get_mcp_tool_description() -> str:
    """Description for dynamic MCP tools."""
    return """
## MCP Tools (dynamic `mcp_<server>_<tool>` functions)

Reverie can expose tools discovered from configured MCP servers.

**How they appear**:
- Tool names are generated as `mcp_<server>_<tool>`
- Each tool schema comes directly from the connected MCP server
- Tool visibility can change when MCP config is reloaded

**How to use them well**:
- Prefer built-in workspace tools for repository-local file edits, reads, and commands
- Prefer MCP tools when the capability clearly belongs to an external system or MCP server
- Read the discovered tool description and parameter schema before calling it
- When two tools overlap, choose the narrowest one with the clearest ownership

**Examples**:
```
mcp_filesystem_read_file(path="/workspace/README.md")
mcp_jira_create_issue(project="CLI", summary="Add MCP onboarding docs")
```
"""


def get_mcp_resource_description() -> str:
    """Description for MCP resource discovery and reading."""
    return """
## MCP Resource Tools (`list_mcp_resources`, `read_mcp_resource`)

Use these tools to inspect read-only MCP resources such as documents, datasets, or server-provided context artifacts.

**Typical flow**:
1. Call `list_mcp_resources` to discover what a server exposes
2. Pick the exact `server` + `uri`
3. Call `read_mcp_resource` to inspect the content

**Notes**:
- Prefer these resource tools when the MCP server exposes context as resources instead of callable tools
- `read_mcp_resource` can persist binary blobs into the project cache and return the saved path

**Example calls**:
```
list_mcp_resources(server="filesystem")
read_mcp_resource(server="filesystem", uri="file:///workspace/README.md")
```
"""


def get_vision_tool_description() -> str:
    """Description for vision upload."""
    return """
## Vision Upload Tool (vision_upload)

Upload and process visual files for AI analysis.

**Supported formats**:
- PNG, JPG, JPEG, GIF, BMP, WEBP, TIFF

**Parameters**:
- `file_path` (required)
- `description` (optional context for what to inspect)

**When to use**:
- The user asks you to inspect a screenshot, diagram, or UI mockup
- You need OCR-style reading, layout review, or visual debugging
- A local image file should be passed into a vision-capable model flow

**Example call**:
```
vision_upload(file_path="screenshots/ui.png", description="Inspect layout regressions")
```
"""


def get_text_to_image_description() -> str:
    """Description for text-to-image generation."""
    return """
## Text-to-Image Tool (text_to_image)

Generate images with the local configured text-to-image runtime.

**Actions**:
- `list_models`
- `generate`

**Important parameters for `generate`**:
- `prompt`
- `negative_prompt`
- `model` or `display_name`
- `width`, `height`, `steps`, `cfg`, `seed`
- `sampler`, `scheduler`, `batch_size`
- `use_cpu`, `output_path`, `timeout_seconds`

**Usage notes**:
- Choose models by configured display name, not raw path
- Use `list_models` first when model availability is unclear
- Keep `output_path` workspace-safe and relative when you override it

**Example calls**:
```
text_to_image(action="list_models")
text_to_image(action="generate", prompt="cinematic neon skyline", model="cinematic-xl", width=1024, height=576)
```
"""


def get_token_counter_description() -> str:
    """Description for token counting."""
    return """
## Token Counter Tool (count_tokens)

Count tokens in text or the current conversation to manage context limits effectively.

**Parameters**:
- `text`
- `check_current_conversation`

**When to use**:
- Before large edits or long outputs
- When the session feels large
- Before expensive multi-step work
- To estimate whether automatic session rotation is likely soon

**Example calls**:
```
count_tokens(text="Some text to analyze")
count_tokens(check_current_conversation=True)
```
"""


def get_context_management_description() -> str:
    """Description for context management."""
    return """
## Context Management Tool (context_management)

Manage conversation context by compressing, truncating, or checkpointing message history.

**Actions**:
- `compress`
- `truncate`
- `checkpoint`
- `restore`

**Parameters**:
- `action`
- `keep_recent`
- `checkpoint_id`

**When to use**:
- Context usage is getting high
- The session has become long or repetitive
- You want to preserve progress before a risky operation
- You need to restore a prior checkpoint

**Atlas-safe compression pattern**:
1. Call `context_management(action="checkpoint")` before compression
2. Emit a compact handoff summary in conversation that preserves confirmed scope, doc baseline, completed work, active slice, risks, and next action
3. Compress only after that handoff summary exists
4. After compression or resume, retrieve workspace memory and re-anchor on the document baseline before continuing

**Example calls**:
```
context_management(action="compress")
context_management(action="truncate", keep_recent=10)
context_management(action="checkpoint")
```
"""


def get_task_manager_description() -> str:
    """Description for task management."""
    return TASK_MANAGER_TOOL_DESCRIPTION


def get_reverie_progress_review_description() -> str:
    """Prompt-side progress review playbook for Reverie mode."""
    return """
## Reverie Progress Review Playbook

Use this playbook whenever you need to judge project progress, completion status, or release readiness.

**Core principle**:
- Evaluate progress against requested outcomes and acceptance criteria, not against effort, code volume, or elapsed time

**Evidence to gather**:
1. Compare intended deliverables against your current implementation and verification evidence
2. Use `codebase-retrieval` to inspect what is actually implemented and how far it is integrated
3. Use `command_exec` to collect build, test, lint, type-check, or smoke-check evidence
4. Use `git-commit-retrieval` when earlier behavior or partial regressions may affect the completion judgment

**Report with precision**:
- Separate `planned`, `implemented`, `integrated`, `verified`, and `done`
- Call out what is still missing, unverified, blocked, or only partially wired
- If you give a percentage, anchor it to explicit deliverables or milestone counts
- If acceptance criteria are ambiguous, state the uncertainty clearly instead of pretending they were met
"""


def get_user_input_description() -> str:
    """Description for user input collection."""
    return """
## User Input Tool (userInput)

Ask the user for explicit feedback, confirmation, or missing requirements.

**Parameters**:
- `question`
- `reason`
- `multiline`
- `default_value`
- `allow_cancel`

**When to use**:
- A decision has non-obvious consequences
- Requirements are missing and cannot be inferred safely
- You need approval before a risky or irreversible action

**Example call**:
```
userInput(question="Should we migrate existing sessions to the new schema?", reason="migration-confirmation", multiline=False)
```
"""


def get_mode_switch_description() -> str:
    """Description for the mode switch tool."""
    return """
## Mode Switch Tool (switch_mode)

Switch between Reverie's non-desktop-control modes when another workflow is clearly a better fit.

**Available targets**:
- `reverie`: general-purpose coding and delivery
- `reverie-atlas`: document-driven spec development for complex systems
- `reverie-gamer`: game development
- `reverie-ant`: long-running planning, execution, and verification
- `spec-driven`: spec authoring for requirements, design, and task breakdown
- `spec-vibe`: lighter spec implementation for approved plans
- `writer`: writing and narrative continuity

**When to use**:
- The task changes from coding to specs, writing, game design, or long-running structured execution
- Another mode has a meaningfully better workflow or tool surface
- A phased mode is better for the current job than generic execution
- The task would benefit from a specialized planning or verification loop before more implementation work
- The current specialist mode is heavier than the request, and a focused task should be downgraded back to `reverie`

**Never use this tool**:
- To switch into Computer Controller mode
- Repeatedly without a clear reason tied to progress
"""


def get_reverie_atlas_documentation_description() -> str:
    """Prompt-side playbook for Reverie-Atlas."""
    return """
## Reverie-Atlas Research And Delivery Playbook

Use this playbook when the task is a complex, interdependent project that benefits from deep research, detailed documents, and document-driven implementation.

**Core pattern**:
1. Retrieve repository context and workspace memory before outlining the docs
2. Build an evidence-backed structure for the document set
3. Author a master document for overview and appendices for subsystem depth
4. Explain the documents to the user and confirm the document information before broad implementation
5. Use the confirmed documents as the execution baseline for slow, step-by-step, high-quality implementation
6. Refresh the docs as code sharpens the design, and preserve continuity with checkpoints, handoff summaries, and memory updates

**Important rules**:
- Do not use `task_manager` or `artifacts/Tasks.md` in this mode
- Use `atlas_delivery_orchestrator` as the durable delivery ledger for contract state, slice progress, blockers, checkpoints, and closure readiness
- Treat `artifacts/` as Atlas's document system of record and re-open those artifacts first on new or resumed sessions
- Keep a detailed, user-readable task tree in `artifacts/task.md`, synchronized with the current Atlas slices and completion state
- Start resumed Atlas sessions from `artifacts/atlas/resume_index.md` when it exists, then expand into the linked docs instead of relying on chat history alone
- Prefer document architecture over checklist management
- Use `codebase-retrieval(query_type="memory", ...)` when previous sessions may contain relevant findings
- Keep major claims tied to files, commands, or clearly marked inference
- If the documentation is broad, split it into `Master Document.md` plus appendix files instead of flattening everything into one file
- Use `userInput` for the post-document confirmation gate when the implementation scope is significant
- Do not ask for redundant reconfirmation after every small implementation step; re-confirm only if the baseline scope or architecture materially changes
- After the confirmation gate, do not stop at documents alone if the user asked for the project to be built
- Treat user messages like `continue`, `继续`, `开始`, `go on`, or `keep going` as permission to resume the next unfinished slice, not as a cue to emit a project-status recap
- If the next safe implementation action is already known, execute it immediately instead of ending with a "next step" summary
- Treat ordinary compile errors, test failures, missing imports, incomplete insertions, and similar in-flight engineering issues as work to fix inside the active slice, not as blockers to report by default
- Before any final-style summary or handoff, run `atlas_delivery_orchestrator(action="assess_completion")`; if the gate is not green, keep implementing or surface a concrete blocker
- Atlas should compress context only after a checkpoint plus a durable handoff summary that preserves the current delivery state
"""


def get_atlas_delivery_orchestrator_description() -> str:
    """Description for the Atlas delivery orchestrator tool."""
    return """
## Atlas Delivery Orchestrator Tool (atlas_delivery_orchestrator)

Use this tool to turn Atlas's document-driven workflow into a durable delivery state machine under `artifacts/atlas/`, while keeping the broader `artifacts/` document system synchronized for resume.

**Actions**:
- `bootstrap_delivery`
- `register_contract`
- `plan_slices`
- `record_slice`
- `record_verification`
- `record_blocker`
- `resolve_blocker`
- `sync_documents`
- `checkpoint_delivery`
- `assess_completion`
- `prepare_final_report`

**Best uses**:
- Create the Atlas charter, tracker, document manifest, handoff summary, and state ledger before a long implementation loop
- Keep `artifacts/task.md` synchronized as a detailed task tree derived from Atlas delivery slices
- Keep `artifacts/atlas/resume_index.md` synchronized as the first file a fresh Atlas session should read
- Record implementation slices so Atlas keeps building instead of drifting into premature status summaries
- Capture blocker and verification state explicitly so closure is based on facts, not optimism
- Check completion gates before final reports or major handoffs
"""


def get_game_design_orchestrator_description() -> str:
    """Description for the game design orchestrator tool."""
    return """
## Game Design Orchestrator Tool (game_design_orchestrator)

Use this tool to move from one prompt to a compiled request, structured blueprint, production plan, system packets, task graph, continuity artifacts, and slice plan.

**Actions**:
- `compile_request`
- `compile_program`
- `create_blueprint`
- `plan_production`
- `expand_system`
- `generate_gameplay_factory`
- `plan_boss_arc`
- `expand_region`
- `generate_character_kit`
- `build_enemy_faction`
- `generate_vertical_slice`
- `analyze_scope`
- `export_markdown`

**Best uses**:
- Compile a raw game prompt into `artifacts/game_program.json`, `game_bible.md`, `feature_matrix.json`, `design_intelligence.json`, `design_playbook.md`, `milestone_board.json`, and `reference_intelligence.json`
- Compile a raw game prompt into `artifacts/game_request.json`
- Create a real blueprint before broad game implementation
- Generate a production plan, runtime decision packet, design-intelligence packet, local-reference intelligence packet, capability graph, world program, system specs, task graph, and durable continuity artifacts before scaffolding
- Expand one system into verbs, states, resources, tuning knobs, telemetry, and tests
- Generate gameplay factories, boss arcs, region-expansion packets, character kits, and enemy-faction packets for follow-up production turns
- Generate a vertical-slice plan before scaling content scope
- Analyze scope and risk when the request implies a large or multi-genre game
"""


def get_game_project_scaffolder_description() -> str:
    """Description for the game project scaffolder tool."""
    return """
## Game Project Scaffolder Tool (game_project_scaffolder)

Use this tool to plan or create an engine-aware project foundation, upgrade an existing runtime project, apply one system packet, and materialize a request-backed vertical slice.

**Actions**:
- `plan_structure`
- `create_foundation`
- `create_from_request`
- `generate_vertical_slice`
- `upgrade_runtime_project`
- `apply_system_packet`
- `generate_module_map`
- `generate_content_pipeline`

**Best uses**:
- Choose a practical structure for 2D, 2.5D, or 3D projects
- Create a repeatable foundation for runtime, data, tests, and playtest folders
- Turn a compiled request directly into artifacts, local-reference intelligence, runtime selection, system specs, task graph, content expansion seeds, resume state, slice score, and a bootable slice scaffold
- Refresh a long-running project foundation without restarting the whole planning flow
- Stage one system packet into runtime-facing artifact output when the project is growing subsystem by subsystem
- Generate module and content-pipeline docs before major implementation expands
"""


def get_game_playtest_lab_description() -> str:
    """Description for the game playtest lab tool."""
    return """
## Game Playtest Lab Tool (game_playtest_lab)

Use this tool to build the feedback and verification loop for game projects.

**Actions**:
- `create_test_plan`
- `generate_telemetry_schema`
- `create_quality_gates`
- `run_quality_gates`
- `score_combat_feel`
- `plan_next_iteration`
- `analyze_session_log`
- `synthesize_feedback`

**Best uses**:
- Define playtest goals before content and balancing work scale up
- Generate telemetry and quality gates for first playable and vertical-slice milestones
- Turn current project artifacts into performance budgets, combat-feel reports, and next-iteration prompt packs
- Analyze session logs and synthesize tester feedback into clear next actions
"""


def get_game_modeling_workbench_description() -> str:
    """Description for the game modeling workbench tool."""
    return """
## Game Modeling Workbench Tool (game_modeling_workbench)

Use this tool to run Reverie-Gamer's built-in Blockbench and Ashfox MCP content workflow.

**Actions**:
- `inspect_stack`
- `setup_workspace`
- `sync_registry`
- `create_model_stub`
- `import_export`
- `list_ashfox_tools`
- `ashfox_call`

**Best uses**:
- Standardize source `.bbmodel` files under `assets/models/source`
- Import runtime `.glb` or `.gltf` exports into `assets/models/runtime`
- Regenerate `data/models/model_registry.yaml` after authoring changes
- Validate, inspect, preview, or export active Blockbench projects through the built-in Ashfox MCP integration
"""


def get_reverie_engine_lite_description() -> str:
    """Description for the built-in Reverie Engine tool."""
    return """
## Reverie Engine Tool (`reverie_engine`, compatibility alias `reverie_engine_lite`)

Use this tool when the game should target Reverie's built-in runtime.

**Actions**:
- `create_project`
- `inspect_project`
- `generate_scene`
- `generate_prefab`
- `generate_archetype`
- `author_scene_blueprint`
- `author_prefab_blueprint`
- `validate_authoring_payload`
- `materialize_sample`
- `run_smoke`
- `validate_project`
- `project_health`
- `package_project`
- `benchmark_project`

**Best uses**:
- Create a first-party runtime foundation when no external engine is required
- Generate or inspect `.relscene.json` and `.relprefab.json` content
- Materialize built-in 2D, 2.5D, 3D, galgame, and tower-defense samples for fast iteration
- Run deterministic runtime smoke checks and validate the built-in engine project layout
- Produce health reports, delivery packages, and baseline performance measurements for engine projects
"""


def get_computer_control_description() -> str:
    """Description for the computer control tool."""
    return """
## Computer Controller Tool (computer_control)

Observe and control the Windows desktop from one unified tool.

**Observation actions**:
- `observe`: full screen or explicit region capture
- `active_window`: inspect foreground window title and bounds
- `observe_window`: capture the active window, optionally with padding and grid overlays
- `screen_info`, `cursor`

**Interaction actions**:
- `move_mouse`, `click`, `double_click`, `right_click`
- `drag`, `scroll`
- `type_text` for native keyboard text entry, `key_press`, `hotkey`
- `wait`

**High-value parameters for observation**:
- `x`, `y`, `width`, `height`
- `padding`
- `grid_cols`, `grid_rows`
- `highlight_cursor`
- `observation_name`

**Best usage pattern**:
1. Start with `observe` or `observe_window`
2. If coordinates are uncertain, recapture with `grid_cols` and `grid_rows`
3. Take one small action
4. Observe again to verify the outcome

**Example calls**:
```
computer_control(action="observe", grid_cols=3, grid_rows=3)
computer_control(action="observe_window", padding=12, grid_cols=4, grid_rows=4, highlight_cursor=True)
computer_control(action="click", x=640, y=420)
```
"""


def get_tool_calling_reliability_notes() -> str:
    """General notes to reduce tool-call failures."""
    return """
## Tool Calling Reliability Notes

To reduce avoidable tool failures:
- Use exact tool names and schema key names when possible
- Prefer flat argument objects instead of wrapping inside `args` / `parameters`
- Start with required fields, then add optional fields as needed
- Use native numbers and booleans where possible
- If a tool is high-impact, inspect or dry-run context first
"""


def get_all_tool_descriptions() -> str:
    """Return the full engineering tool guide."""
    return "\n".join(
        [
            get_codebase_retrieval_description(),
            get_git_commit_retrieval_description(),
            get_str_replace_editor_description(),
            get_create_file_description(),
            get_workspace_file_ops_description(),
            get_delete_file_description(),
            get_workspace_command_description(),
            get_web_search_description(),
            get_tool_catalog_description(),
            get_skill_lookup_description(),
            get_mcp_resource_description(),
            get_vision_tool_description(),
            get_text_to_image_description(),
            get_token_counter_description(),
            get_task_manager_description(),
            get_user_input_description(),
            get_mode_switch_description(),
            get_computer_control_description(),
            get_tool_calling_reliability_notes(),
        ]
    )


def _normalize_mode(mode: str) -> str:
    normalized = normalize_mode(mode)
    if normalized == "reverie-ant":
        return "ant"
    return normalized


def _get_mode_tool_workflow(mode: str) -> str:
    """Return workflow guidance for the active mode."""
    normalized = _normalize_mode(mode)

    if normalized == "spec-driven":
        return """
## Spec-Driven Mode Tool Workflow

- Start with retrieval and current-state inspection before proposing design.
- Use editing tools only after requirements and acceptance criteria are clear.
- Verify generated specs, plans, and implementation tasks against current project constraints.
"""

    if normalized == "spec-vibe":
        return """
## Spec-Vibe Mode Tool Workflow

- Move quickly, but still retrieve enough project context before editing.
- Use the editor, file, and command tools for implementation loops after the plan is clear.
- Keep changes aligned to the already-approved spec or implementation direction.
"""

    if normalized == "writer":
        return """
## Writer Mode Tool Workflow

- Prioritize narrative or document continuity first, then use generic tools when file work is required.
- Use file and retrieval tools to keep manuscripts, notes, and lore consistent.
- Use `ask_clarification` early when tone, genre, audience, canon, POV, tense, or length expectations are ambiguous.
- Use `userInput` when you need explicit outline approval or writing-direction confirmation from the user.
"""

    if normalized == "reverie-atlas":
        return """
## Reverie-Atlas Mode Tool Workflow

- Start with retrieval, dependency inspection, history review, and workspace-memory retrieval before drafting.
- Bootstrap or refresh `atlas_delivery_orchestrator` early on meaningful Atlas work so the contract, slice ledger, blockers, and checkpoints are durable.
- Treat documentation as an engineering artifact: establish the master document and appendix structure before broad authoring.
- Do not use task-manager workflows; organize progress around evidence gathering, document architecture, and authored artifacts instead.
- Prefer master document plus appendices for complex systems so each deep topic gets real specification depth.
- Use automatic handoff rotation, concise continuity notes, and workspace-memory retrieval to preserve continuity across long Atlas sessions.
- After the document set is drafted, explain it to the user and explicitly confirm the information before broad implementation when the project scope is non-trivial.
- Once confirmed, implement from the documents in small, rigorous increments and keep the document set aligned with delivered code and verification results.
- If the scope has already been confirmed and has not materially changed, continue implementation instead of reopening the confirmation gate.
- Treat `continue` or similar user follow-ups as a directive to advance the next unfinished slice unless the user explicitly asked for a status update.
- Before any final-style summary, run `atlas_delivery_orchestrator(action="assess_completion")` and keep going if the contract is still open.
- Before any risky long-running slice, record the delivery state so Atlas can resume cleanly if automatic rotation occurs.
- If the request is a simple, bounded implementation task that does not benefit from Atlas's document contract, switch to `reverie` proactively instead of keeping Atlas in the lead.
- If the task becomes primarily game design, gameplay systems, runtime work, content pipelines, balance work, or playtest iteration, switch to `reverie-gamer` proactively.
        """

    if normalized == "reverie-gamer":
        return """
## Reverie-Gamer Mode Tool Workflow

- Start with retrieval; if the right tool or schema is unclear, use `tool_catalog` before guessing.
- Treat substantial requests as a prompt-to-production flow: compile the program, compile the request, define the blueprint, choose scope, choose the runtime, scaffold the runtime, build the first playable, verify the slice, then plan continuation.
- Use `game_design_orchestrator(action="compile_program")` first for fresh large-scale game requests, then `game_design_orchestrator(action="compile_request")`, `game_design_orchestrator(action="create_blueprint")`, `game_design_orchestrator(action="plan_production")`, and `game_design_orchestrator(action="generate_vertical_slice")`.
- Expect `plan_production` to emit `artifacts/game_program.json`, `artifacts/design_intelligence.json`, `artifacts/campaign_program.json`, `artifacts/roster_strategy.json`, `artifacts/live_ops_plan.json`, `artifacts/production_operating_model.json`, `artifacts/reference_intelligence.json`, `artifacts/runtime_capability_graph.json`, `artifacts/runtime_delivery_plan.json`, `artifacts/world_program.json`, `artifacts/region_kits.json`, `artifacts/system_specs.json`, `artifacts/task_graph.json`, `artifacts/content_expansion.json`, `artifacts/asset_pipeline.json`, and `artifacts/resume_state.json`, and expect `generate_vertical_slice` to emit `playtest/slice_score.json`.
- For large 3D, open-world, or "AAA-like" requests, automatically reduce scope to the first credible playable slice and record deferred systems explicitly.
- Keep `artifacts/design_intelligence.json` current so personas, onboarding, difficulty, balance probes, accessibility, and large-scene guardrails survive across sessions.
- When `references/` exists, treat local engine, sample-project, and asset-pipeline repos as first-class planning inputs and keep `artifacts/reference_intelligence.json` current.
- Use `game_project_scaffolder(action="generate_vertical_slice")` when the user wants the repository to turn a compiled request into a real slice scaffold and artifact set.
- Use `game_design_orchestrator(action="generate_gameplay_factory")`, `plan_boss_arc`, `expand_region`, `generate_character_kit`, and `build_enemy_faction` for specialized follow-up production passes.
- Default to the repository's existing runtime; otherwise prefer `reverie_engine` for the fastest runnable slice and keep external-engine choices explicit.
- For extensible 3D action RPG foundations, allow the runtime registry to select `godot` and materialize the Godot scaffold under `engine/godot/`.
- Prefer `reverie_engine`; accept `reverie_engine_lite` as a compatibility alias for existing projects.
- Treat the built-in Blockbench plus Ashfox MCP flow as the preferred Reverie-Gamer modeling path when the project needs authored models.
- Bring `game_playtest_lab` in early enough to define quality gates and telemetry before the project sprawls, and use `game_playtest_lab(action="run_quality_gates")`, `game_playtest_lab(action="score_combat_feel")`, and `game_playtest_lab(action="plan_next_iteration")` once the slice exists.
- Treat implementation, balance simulation, runtime testing, playtests, telemetry, and content iteration as one loop.
- Do not stop at documents alone when the user asked to build a game; push through to runnable implementation and verification.
"""

    if normalized == "ant":
        return """
## Reverie-Ant Mode Tool Workflow

- Structure long-running work into planning, execution, and verification phases.
- Use focused tool calls instead of broad, ambiguous action bursts.
- Pair progress signaling with concrete artifacts, edits, or validation steps.
"""

    if normalized == "computer-controller":
        return """
## Computer Controller Mode Tool Workflow

- Start with `computer_control(action="observe")` or `observe_window`.
- If targeting is uncertain, recapture with `grid_cols` and `grid_rows`.
- Prefer one UI action at a time, then re-observe.
- Keep the loop alive until the desktop task is actually complete.
- Treat browsers and desktop apps as normal targets, including Blockbench workflows.
- Historical computer-control sessions live in a dedicated `.reverie/computer-controller` archive and are retrieved on demand, not injected automatically.
- Keep non-desktop tools secondary to the visual desktop-control loop.
"""

    return """
## Reverie Mode Tool Workflow

- For small, clear tasks, use a lightweight loop: targeted retrieval -> focused edit -> narrow verification -> respond.
- Treat user-specified libraries, SDK choices, endpoints, payload fields, config knobs, and requested file layouts as acceptance criteria, not suggestions.
- Retrieve code context first.
- Use git history when conventions or earlier fixes matter.
- Edit with the narrowest correct tool.
- Verify with commands and manage context proactively on long sessions.
- Use planning tools when the work is large enough to benefit from explicit tracking; do not default to formal planning for tiny fixes.
- Do not default to `task_manager` for small deliverables or isolated greenfield scaffolds, even if they span several files.
- For automation, desktop, or agent-style requests, implement the full runtime loop the user described: observe or screenshot -> decide -> act -> verify -> repeat, with explicit stop conditions.
- Feed action results and the latest observation back into later iterations; do not reset the loop into stateless one-shot calls after each action.
- When a model returns normalized coordinates or model-space coordinates, implement a dedicated coordinate-mapping layer into the real runtime space before invoking actions.
- If the user asked for safe or conservative behavior, surface that in runtime defaults such as dry-run, confirmation, bounded retries, or similarly cautious controls.
- Prefer encoding-safe terminal output and verification paths for generated Windows-facing CLIs and scripts.
- If another mode has a better workflow for the current phase, switch proactively instead of forcing generic execution.
- Judge completion using deliverables, integration state, and verification evidence rather than optimistic progress estimates.
"""


def _get_tool_discovery_brief() -> str:
    """Compact Claude-style discovery-first guidance for prompt injection."""
    return """
## Tool Discovery

- If the right tool or exact schema is unclear, start with `tool_catalog`.
- Use `tool_catalog(operation="search", query="...")` to find candidates.
- Use `tool_catalog(operation="recommend", query="...")` when you want the likely best tool sequence for a short task description.
- Use `tool_catalog(operation="inspect", tool_name="...")` before first use of unfamiliar, dynamic, or high-impact tools.
- Use `skill_lookup` only when a discovered `SKILL.md` may materially change the workflow.
- Use `list_mcp_resources` / `read_mcp_resource` for MCP resources, and inspect dynamic `mcp_*` tools through `tool_catalog`.
"""


def _get_compact_tool_surface(mode: str) -> str:
    """Return a compact tool surface summary for the active mode."""
    normalized = _normalize_mode(mode)

    lines = [
        "## Tool Surface",
        "",
        "- `codebase-retrieval`: inspect files, symbols, dependencies, task context, workspace memory, or LSP state before non-trivial edits.",
        "- `str_replace_editor` / `create_file`: modify existing files or create new files in the workspace.",
        "- `file_ops` / `delete_file`: inspect the filesystem, create directories, or delete one file safely.",
        "- `command_exec`: run project-local build, test, lint, smoke, packaging, or git commands.",
        "- `git-commit-retrieval`: inspect history, blame, regressions, or earlier patterns before touching fragile code.",
        "- `web_search`: use only for unstable external facts, external docs, products, or exact references.",
        "- `vision_upload`: inspect screenshots, diagrams, or local image files when visual context matters.",
        "- `count_tokens` / `context_management`: manage long-session context, checkpoint before compression, and avoid context loss.",
        "- `userInput`: ask only when a blocking ambiguity or high-impact decision cannot be resolved safely from local context.",
        "- Dynamic `mcp_*` and runtime-plugin tools may appear at runtime; discover and inspect them with `tool_catalog`.",
    ]

    if normalized != "computer-controller":
        lines.append("- `text_to_image`: generate raster images only when the task explicitly needs image assets.")

    if normalized in {"reverie", "reverie-gamer"}:
        lines.append("- `task_manager`: use for larger multi-step work; skip it for tiny fixes and short greenfield scaffolds.")

    if normalized == "reverie-atlas":
        lines.append("- `atlas_delivery_orchestrator`: keep Atlas contracts, slice state, blockers, checkpoints, and closure checks durable under `artifacts/atlas/`.")

    if normalized == "reverie-gamer":
        lines.extend(
            [
                "- `game_design_orchestrator`: compile raw prompts into `game_request.json`, create blueprints, analyze scope, plan production, expand systems, and generate vertical-slice plans.",
                "- `game_project_scaffolder`: plan or create the runtime, data, tests, playtest, and content-pipeline foundation, upgrade an existing runtime project, apply one system packet, or directly generate a request-backed vertical slice.",
                "- `reverie_engine` / `reverie_engine_lite`: create, inspect, validate, benchmark, and smoke-test Reverie's built-in runtime projects.",
                "- `game_modeling_workbench`: manage the built-in Blockbench plus Ashfox MCP pipeline, model stubs, registry sync, and runtime imports.",
                "- `game_playtest_lab`: generate telemetry schemas, quality gates, playtest plans, performance budgets, combat-feel reports, continuation plans, and feedback analysis artifacts.",
                "- Other Gamer tools such as `game_gdd_manager`, `level_design`, `game_asset_manager`, `game_balance_analyzer`, `game_math_simulator`, `game_stats_analyzer`, and `story_design` remain available through `tool_catalog`.",
            ]
        )

    if normalized == "computer-controller":
        lines.append("- `computer_control`: run an observe -> act -> re-observe desktop loop until the target task is actually complete.")
    else:
        lines.append("- `switch_mode`: move to another specialist mode when its workflow is materially better for the current phase.")

    return "\n".join(lines)


def _get_compact_tool_calling_notes() -> str:
    """Short tool-calling rules suitable for system-prompt injection."""
    return """
## Tool Calling Rules

- Prefer exact tool names and exact schema field names.
- Start with required fields, then add optional fields only when needed.
- Retrieve before editing, and verify after editing.
- When impact is high, choose the narrowest call that can still finish the job.
"""


def get_tool_descriptions_for_mode(mode: str) -> str:
    """
    Get compact, discovery-first tool guidance for the active mode.

    The detailed tool schemas are already available to the model at call time,
    and `tool_catalog` can be used to inspect dynamic or unfamiliar tools. Keep
    the prompt-side guide concise so more context budget remains for the task.
    """
    descriptions = [
        _get_mode_tool_workflow(mode),
        _get_tool_discovery_brief(),
        _get_compact_tool_surface(mode),
        _get_compact_tool_calling_notes(),
    ]

    return "\n".join(part for part in descriptions if str(part or "").strip())
