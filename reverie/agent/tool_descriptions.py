"""
Tool descriptions used inside system prompts.

This module keeps the prompt-side tool playbooks synchronized with the actual
runtime tool surface, especially for Reverie mode where the model is expected
to operate autonomously across planning, implementation, verification, memory,
and mode transitions.
"""

from ..modes import normalize_mode


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
- `memory`: query workspace-global memory distilled from earlier sessions
- `lsp`: query diagnostics, definitions, document symbols, workspace symbols, or LSP status

**Best usage pattern**:
1. Start with `search` or `symbol` to find the implementation.
2. Inspect the containing file or nearby dependencies.
3. Check usages before editing shared code.
4. Use `memory` and `lsp` when session continuity or semantic navigation matters.

**Example calls**:
```
codebase-retrieval(query_type="symbol", query="ReverieInterface._init_agent")
codebase-retrieval(query_type="file", query="reverie/agent/agent.py")
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
git-commit-retrieval(query_type="file_history", target="reverie/iflow.py", limit=8)
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
- To decide whether `context_management` should compress history

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

**Example calls**:
```
context_management(action="compress")
context_management(action="truncate", keep_recent=10)
context_management(action="checkpoint")
```
"""


def get_task_manager_description() -> str:
    """Description for task management."""
    return """
## Task Manager Tool (task_manager)

Use this tool for structured planning and progress tracking on multi-step work.

**Operations**:
- `add_tasks`
- `update_tasks`
- `view_tasklist`
- `reorganize_tasklist`

**Best usage pattern**:
1. After initial retrieval, create a detailed task list for substantial work
2. Break large requests into many small, concrete, verifiable tasks instead of a few broad milestones
3. Keep the canonical task artifact in `Tasks.md`
4. `Tasks.md` must be checklist-only: one checklist item per line, no headings, prose, summaries, IDs, or metadata blocks
5. Mark only one task `IN_PROGRESS` at a time when practical
6. Batch-update task states when moving from one task to the next

**Common fields**:
- `name`, `description`
- `state`: `NOT_STARTED`, `IN_PROGRESS`, `COMPLETED`, `CANCELLED`
- `priority`: `low`, `medium`, `high`, `critical`
- `phase`: `design`, `implementation`, `content`, `testing`, `release`

**Completion standard**:
- Create tasks around concrete edits, validation steps, integration checks, or narrow deliverables
- Keep a task `IN_PROGRESS` if implementation exists but integration or verification is still pending
- Mark a task `COMPLETED` only when its promised outcome is actually delivered for the intended scope
- If later evidence shows regressions, reopen the task by moving it back to `IN_PROGRESS`
- Use `progress` and `description` to capture partial completion, blockers, or verification gaps instead of overstating status

**Example calls**:
```
task_manager(operation="add_tasks", tasks=[{"name":"Add resource remap loader coverage","phase":"testing","priority":"high"}])
task_manager(operation="update_tasks", task_id="abc123", state="IN_PROGRESS", progress=0.8, description="Feature is wired, but regression checks are still pending")
task_manager(operation="update_tasks", task_id="abc123", state="COMPLETED", progress=1.0)
task_manager(operation="view_tasklist")
```
"""


def get_reverie_progress_review_description() -> str:
    """Prompt-side progress review playbook for Reverie mode."""
    return """
## Reverie Progress Review Playbook

Use this playbook whenever you need to judge project progress, completion status, or release readiness.

**Core principle**:
- Evaluate progress against requested outcomes and acceptance criteria, not against effort, code volume, or elapsed time

**Evidence to gather**:
1. Use `task_manager` to compare intended deliverables against current execution state
2. Use `codebase-retrieval` to inspect what is actually implemented and how far it is integrated
3. Use `command_exec` to collect build, test, lint, type-check, or smoke-check evidence
4. Use `git-commit-retrieval` when earlier behavior or partial regressions may affect the completion judgment

**Report with precision**:
- Separate `planned`, `implemented`, `integrated`, `verified`, and `done`
- Call out what is still missing, unverified, blocked, or only partially wired
- If you give a percentage, anchor it to explicit deliverables or milestone counts
- If acceptance criteria are ambiguous, use `userInput` instead of guessing
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
- `reverie`
- `reverie-gamer`
- `reverie-ant`
- `spec-driven`
- `spec-vibe`
- `writer`

**When to use**:
- The task changes from coding to specs, writing, or game design
- Another mode has a meaningfully better workflow or tool surface
- A phased mode is better for the current job than generic execution
- The task would benefit from a specialized planning or verification loop before more implementation work

**Never use this tool**:
- To switch into Computer Controller mode
- Repeatedly without a clear reason tied to progress
"""


def get_game_design_orchestrator_description() -> str:
    """Description for the game design orchestrator tool."""
    return """
## Game Design Orchestrator Tool (game_design_orchestrator)

Use this tool to move from game idea to structured production blueprint.

**Actions**:
- `create_blueprint`
- `expand_system`
- `generate_vertical_slice`
- `analyze_scope`
- `export_markdown`

**Best uses**:
- Create a real blueprint before broad game implementation
- Expand one system into verbs, states, resources, tuning knobs, telemetry, and tests
- Generate a vertical-slice plan before scaling content scope
- Analyze scope and risk when the request implies a large or multi-genre game
"""


def get_game_project_scaffolder_description() -> str:
    """Description for the game project scaffolder tool."""
    return """
## Game Project Scaffolder Tool (game_project_scaffolder)

Use this tool to plan or create an engine-aware project foundation.

**Actions**:
- `plan_structure`
- `create_foundation`
- `generate_module_map`
- `generate_content_pipeline`

**Best uses**:
- Choose a practical structure for 2D, 2.5D, or 3D projects
- Create a repeatable foundation for runtime, data, tests, and playtest folders
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
- `analyze_session_log`
- `synthesize_feedback`

**Best uses**:
- Define playtest goals before content and balancing work scale up
- Generate telemetry and quality gates for first playable and vertical-slice milestones
- Analyze session logs and synthesize tester feedback into clear next actions
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
- `type_text`, `key_press`, `hotkey`
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
            get_vision_tool_description(),
            get_text_to_image_description(),
            get_token_counter_description(),
            get_context_management_description(),
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
- Ask for clarification when intent, tone, or canon constraints are ambiguous.
"""

    if normalized == "reverie-gamer":
        return """
## Reverie-Gamer Mode Tool Workflow

- Start with retrieval, then create or inspect the game blueprint before broad implementation.
- Use the design orchestrator and project scaffolder to define systems, scope, and runtime structure first.
- Default to Reverie Engine when the user did not choose another engine and the repo does not already depend on one.
- Prefer `reverie_engine`; accept `reverie_engine_lite` as a compatibility alias for existing projects.
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
- Keep non-desktop tools secondary to the visual desktop-control loop.
"""

    return """
## Reverie Mode Tool Workflow

- Retrieve code context first.
- Use git history when conventions or earlier fixes matter.
- Edit with the narrowest correct tool.
- Verify with commands and manage context proactively on long sessions.
- Use planning tools when the work is large enough to benefit from explicit tracking.
- If another mode has a better workflow for the current phase, switch proactively instead of forcing generic execution.
- Judge completion using deliverables, integration state, and verification evidence rather than optimistic progress estimates.
"""


def get_tool_descriptions_for_mode(mode: str) -> str:
    """
    Get tool descriptions relevant for a specific mode.

    For Reverie mode, this is intentionally comprehensive so the system prompt
    contains the actual usage guidance for every main engineering tool exposed to
    the model.
    """
    normalized = _normalize_mode(mode)

    descriptions = [
        _get_mode_tool_workflow(mode),
        get_codebase_retrieval_description(),
        get_git_commit_retrieval_description(),
        get_str_replace_editor_description(),
        get_create_file_description(),
        get_workspace_file_ops_description(),
        get_delete_file_description(),
        get_workspace_command_description(),
        get_web_search_description(),
        get_vision_tool_description(),
        get_token_counter_description(),
        get_context_management_description(),
        get_user_input_description(),
        get_tool_calling_reliability_notes(),
    ]

    if normalized != "computer-controller":
        descriptions.append(get_text_to_image_description())

    if normalized in {"reverie", "reverie-gamer"}:
        descriptions.append(get_task_manager_description())

    if normalized == "reverie":
        descriptions.append(get_reverie_progress_review_description())

    if normalized == "reverie-gamer":
        descriptions.extend(
            [
                get_game_design_orchestrator_description(),
                get_game_project_scaffolder_description(),
                get_game_playtest_lab_description(),
                get_reverie_engine_lite_description(),
            ]
        )

    if normalized != "computer-controller":
        descriptions.append(get_mode_switch_description())

    if normalized == "computer-controller":
        descriptions.append(get_computer_control_description())

    return "\n".join(part for part in descriptions if str(part or "").strip())
