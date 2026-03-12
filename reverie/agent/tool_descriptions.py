"""
Tool Descriptions for System Prompts

This module contains detailed descriptions of all available tools
that can be included in system prompts across different modes.
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
        get_vision_tool_description(),
        get_token_counter_description(),
        get_context_management_description(),
        get_tool_calling_reliability_notes(),
    ])


def get_tool_descriptions_for_mode(mode: str) -> str:
    """
    Get tool descriptions relevant for a specific mode.
    
    Args:
        mode: The mode name (reverie, writer, gamer, etc.)
        
    Returns:
        Combined tool descriptions for the mode
    """
    # All modes get these core tools
    descriptions = [
        get_web_search_description(),
        get_vision_tool_description(),
        get_token_counter_description(),
        get_context_management_description(),
        get_tool_calling_reliability_notes(),
    ]
    
    return "\n".join(descriptions)
