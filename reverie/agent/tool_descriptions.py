"""
Tool Descriptions for System Prompts

This module contains detailed descriptions of available tools and mode-specific
tool-calling guidance used by system prompts.
"""


def get_vision_tool_description() -> str:
    """Description for vision upload tool"""
    return """
## Vision Upload Tool (vision_upload)

Upload and process visual files (images) for AI analysis. Use this when you need to analyze, describe, or process image files.

**Supported formats**: PNG, JPG, JPEG, GIF, BMP, WEBP, TIFF

**Parameters**:
- `file_path` (required): Path to the image file (relative to project root or absolute)
- `description` (optional): Context about what to analyze in the image

**Example usage**:
```
vision_upload(file_path="screenshots/ui_mockup.png", description="Analyze the UI layout and suggest improvements")
vision_upload(file_path="diagrams/architecture.jpg")
```

**When to use**:
- User asks you to look at, analyze, or describe an image
- Need to extract information from screenshots, diagrams, or photos
- Reviewing UI/UX designs, mockups, or wireframes
- Analyzing charts, graphs, or visual data
- Reading text from images (OCR)
"""


def get_token_counter_description() -> str:
    """Description for token counter tool"""
    return """
## Token Counter Tool (count_tokens)

Count tokens in text or the current conversation to manage context limits effectively. This tool provides accurate token counting using the tiktoken library.

**Parameters**:
- `text` (optional): Text to count tokens in
- `check_current_conversation` (optional): If true, count tokens in current conversation

**Example usage**:
```
count_tokens(text="Some text to analyze")
count_tokens(check_current_conversation=True)
```

**When to use**:
- Before making large edits or additions to check remaining context
- When conversation feels long and you want to check usage
- To decide if context compression is needed
- To verify you're within token limits before complex operations

**Important**: When context usage exceeds 60%, you should proactively use the Context Management tool to compress or optimize the conversation history.
"""


def get_context_management_description() -> str:
    """Description for context management tool"""
    return """
## Context Management Tool (context_management)

Manage conversation context by compressing, truncating, or optimizing message history. This is CRITICAL for long conversations to prevent context overflow.

**Actions**:
- `compress`: Intelligently compress conversation history while preserving key information
- `truncate`: Remove older messages to free up context space
- `checkpoint`: Save current conversation state for potential rollback
- `restore`: Restore from a previous checkpoint

**Parameters**:
- `action` (required): The action to perform (compress, truncate, checkpoint, restore)
- `keep_recent` (optional): Number of recent messages to keep when truncating
- `checkpoint_id` (optional): Checkpoint ID for restore action

**Example usage**:
```
context_management(action="compress")
context_management(action="truncate", keep_recent=10)
context_management(action="checkpoint")
context_management(action="restore", checkpoint_id="checkpoint_123")
```

**CRITICAL USAGE RULES**:
1. **Proactive Management**: When token count exceeds 80% of max context, you MUST proactively call this tool
2. **Before Large Operations**: Always check and compress context before:
   - Large file operations
   - Complex multi-step tasks
   - Extensive code generation
3. **Automatic Triggers**: The system will automatically remind you at 80% usage
4. **User Transparency**: Always inform the user when compressing context

**Compression Strategy**:
- Preserves system prompt and recent messages
- Summarizes middle conversation history
- Maintains tool call results and important decisions
- Keeps error messages and corrections
"""


def get_web_search_description() -> str:
    """Description for enhanced web search tool"""
    return """
## Web Search Tool (web_search)

Search the web with resilient fallback and optional page extraction.

**Minimal call (preferred)**:
```
web_search(query="python contextvars tutorial")
```

**Key parameters**:
- `query` (required): Search text
- `max_results` (optional): Result count (default 5, max 12)
- `fetch_content` (optional): Fetch readable content from results (default true)
- `include_domains` / `exclude_domains` (optional): Domain filters
- `recency` (optional): One of `d`, `w`, `m`, `y` (DuckDuckGo recency hint)
- `request_timeout` / `max_retries` / `fetch_workers` (optional): Network robustness and concurrency
- `max_content_chars` (optional): Per-page output cap
- `output_format` (optional): `text` or `markdown`

**Best usage pattern**:
1. Start with minimal call (`query` only)
2. Add filters only when needed
3. Use domain include filters for docs/release-note queries
4. Keep `max_results` small for focused retrieval
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

**Good examples**:
```
command_exec(command="git status")
command_exec(command="python -c \\"print(1); print(2)\\"")
command_exec(command="dotnet new sln -n Reverie.Downloader")
```

**Blocked examples**:
```
command_exec(command="del old.log")
command_exec(command="git mv a.txt b.txt")
command_exec(command="python -c \\"import os; os.remove('a.txt')\\"")
```
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

**Important**:
- `file_ops` does not delete files
- Use `delete_file` for file deletion
"""


def get_tool_calling_reliability_notes() -> str:
    """General notes to reduce tool call errors."""
    return """
## Tool Calling Reliability Notes

To reduce avoidable tool failures:
- Use exact schema key names when possible.
- Prefer flat argument objects (avoid wrapping inside `args` / `parameters`).
- Start with required parameters only, then add optional ones.
- For numeric/boolean values, provide native types when possible (`5`, `true`) instead of quoted strings.

The runtime now auto-normalizes common variants (case-insensitive keys, common aliases, simple type coercion), but canonical key names remain the most reliable.
"""


def get_all_tool_descriptions() -> str:
    """Get all tool descriptions combined"""
    return "\n".join([
        get_web_search_description(),
        get_workspace_command_description(),
        get_workspace_file_ops_description(),
        get_delete_file_description(),
        get_vision_tool_description(),
        get_token_counter_description(),
        get_context_management_description(),
        get_tool_calling_reliability_notes(),
    ])


def _normalize_mode(mode: str) -> str:
    raw = str(mode or "reverie").strip().lower()
    aliases = {
        "reverie-gamer": "reverie-gamer",
        "reverie-spec-driven": "spec-driven",
        "reverie-ant": "ant",
    }
    return aliases.get(raw, raw)


def _get_mode_tool_workflow(mode: str) -> str:
    mode = _normalize_mode(mode)

    if mode == "spec-driven":
        return """
## Spec-Driven Mode Tool Workflow

- Start with retrieval and context tools to understand the existing implementation before proposing changes.
- Use `command_exec` for validation, builds, and diagnostics inside the workspace, but never for file move/delete actions.
- Use `file_ops` for inspection and `delete_file` only when a real file must be removed.
- Keep tool calls tightly aligned to the approved spec and verification plan.
"""

    if mode == "spec-vibe":
        return """
## Spec-Vibe Mode Tool Workflow

- Move quickly, but still gather enough code context before editing.
- Use `command_exec` for fast feedback loops, smoke tests, and scaffolding while respecting the move/delete blacklist.
- Prefer `create_file` and `str_replace_editor` for implementation changes, then verify with focused terminal commands.
- Use `delete_file` only when cleanup is explicitly needed.
"""

    if mode == "writer":
        return """
## Writer Mode Tool Workflow

- Prioritize writer-specific narrative tools first, then fall back to generic code/file tools only when needed.
- Use `file_ops` for reading notes, outlines, and manuscript files.
- Use `delete_file` only when the user explicitly wants a draft file removed.
- Use `command_exec` sparingly for project-local checks and never for terminal delete/move flows.
"""

    if mode == "reverie-gamer":
        return """
## Gamer Mode Tool Workflow

- Prefer game-design, balance, level, and asset tools before generic terminal usage.
- Use `command_exec` for game-project diagnostics, local build checks, and content pipeline verification inside the workspace.
- Keep asset/file deletion out of the terminal; use `delete_file` for single-file cleanup.
- Use `file_ops` for asset inspection and folder listing when game-specific tools are not enough.
"""

    if mode == "ant":
        return """
## Ant Mode Tool Workflow

- Use `task_boundary` and `notify_user` to structure long-running work and communicate progress.
- Pair planning/execution steps with focused tool calls instead of broad terminal scripts.
- Use `command_exec` for audited workspace execution, but never for terminal move/delete/rename operations.
- Use `file_ops` for non-destructive inspection and `delete_file` for explicit file removal.
"""

    return """
## Reverie Mode Tool Workflow

- Gather code context first, then edit with the narrowest effective tool.
- Use `command_exec` for audited workspace commands, builds, tests, and diagnostics that do not move or delete files.
- Use `file_ops` for safe read/list/info/mkdir tasks.
- Use `delete_file` whenever a file truly needs to be removed.
"""


def get_tool_descriptions_for_mode(mode: str) -> str:
    """
    Get tool descriptions relevant for a specific mode.

    Args:
        mode: The mode name (reverie, writer, gamer, etc.)

    Returns:
        Combined tool descriptions for the mode
    """
    descriptions = [
        _get_mode_tool_workflow(mode),
        get_workspace_command_description(),
        get_workspace_file_ops_description(),
        get_delete_file_description(),
        get_web_search_description(),
        get_vision_tool_description(),
        get_token_counter_description(),
        get_context_management_description(),
        get_tool_calling_reliability_notes(),
    ]
    return "\n".join(descriptions)
