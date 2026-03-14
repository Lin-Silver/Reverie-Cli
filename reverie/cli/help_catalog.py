"""Shared command-help catalog for Reverie CLI."""

from __future__ import annotations

from typing import Dict, List


HELP_SECTION_ORDER: List[str] = [
    "Core",
    "Models & Modes",
    "Providers",
    "Tools & Context",
    "Sessions & Recovery",
    "Project & Rules",
    "Game",
]


HELP_TOPICS: Dict[str, Dict[str, object]] = {
    "help": {
        "command": "/help",
        "section": "Core",
        "summary": "Browse the live help catalog, pin a detailed page, or print the full reference.",
        "detail": "Bare `/help` opens the interactive browser. Press Enter or Esc to pin the current command panel into the transcript; `/help <command>` prints one detailed page and `/help all` prints the whole catalog.",
        "overview": "browser, <command>, all",
        "subcommands": [
            {"usage": "/help", "description": "Open the interactive help browser with live navigation, filtering, and detailed command pages."},
            {"usage": "/help <command>", "description": "Show detailed help for a single command such as `/help codex` or `/help iflow model`.", "example": "/help iflow model"},
            {"usage": "/help all", "description": "Print the detailed help view for every command in sequence."},
        ],
        "examples": ["/help", "/help codex", "/help iflow model", "/help all"],
    },
    "status": {
        "command": "/status",
        "section": "Core",
        "summary": "Show the active model, provider source, session, and runtime health.",
        "detail": "This is the fast health check for the current session, active model selection, indexing state, and token headroom.",
        "overview": "status snapshot",
        "subcommands": [
            {"usage": "/status", "description": "Show the current model, endpoint, source, session, index, and uptime status."},
        ],
        "examples": ["/status"],
    },
    "clear": {
        "command": "/clear",
        "section": "Core",
        "summary": "Clear the current terminal view without touching session state.",
        "detail": "Only the screen is cleared. Conversation history, sessions, and config stay intact.",
        "overview": "clear screen",
        "subcommands": [
            {"usage": "/clear", "description": "Clear the terminal output."},
        ],
        "examples": ["/clear"],
    },
    "clean": {
        "command": "/clean",
        "section": "Core",
        "summary": "Delete current-workspace memory, backups, caches, and command audit history, then start fresh.",
        "detail": "Only the active workspace is affected. Reverie removes the current workspace's project cache plus workspace-local `.reverie/context_cache` and `.reverie/security`; config and rules remain intact.",
        "overview": "reset workspace memory, force",
        "subcommands": [
            {"usage": "/clean", "description": "Prompt for confirmation, then delete current-workspace sessions, snapshots, caches, backups, and audit logs."},
            {"usage": "/clean force", "description": "Run the same cleanup without the confirmation prompt."},
        ],
        "examples": ["/clean", "/clean force"],
    },
    "exit": {
        "command": "/exit",
        "section": "Core",
        "summary": "Exit Reverie with a confirmation prompt.",
        "detail": "The current session is preserved; `/quit` is a direct alias of `/exit`.",
        "overview": "exit, quit",
        "aliases": ["/quit"],
        "subcommands": [
            {"usage": "/exit", "description": "Prompt for confirmation, then exit Reverie."},
            {"usage": "/quit", "description": "Alias of `/exit`."},
        ],
        "examples": ["/exit", "/quit"],
    },
    "model": {
        "command": "/model",
        "section": "Models & Modes",
        "summary": "Open the standard model selector or manage configured standard models.",
        "detail": "This catalog is separate from provider-native catalogs like `/codex model` or `/iflow model`.",
        "overview": "selector, add, delete/remove <n>",
        "subcommands": [
            {"usage": "/model", "description": "Open the selector for standard configured models."},
            {"usage": "/model add", "description": "Launch the interactive flow for adding a standard model configuration."},
            {"usage": "/model delete <number>", "description": "Delete a configured standard model by its selector index."},
            {"usage": "/model remove <number>", "description": "Alias of `/model delete <number>`."},
        ],
        "examples": ["/model", "/model add", "/model delete 2"],
    },
    "mode": {
        "command": "/mode",
        "section": "Models & Modes",
        "summary": "Show or switch Reverie operating modes.",
        "detail": "The mode affects system prompts, tool framing, and how Reverie approaches the task.",
        "overview": "show, reverie|reverie-gamer|spec-driven|spec-vibe|writer|reverie-ant",
        "subcommands": [
            {"usage": "/mode", "description": "Show the current mode and the full mode table."},
            {"usage": "/mode reverie", "description": "Switch to the general-purpose coding assistant mode."},
            {"usage": "/mode reverie-gamer", "description": "Switch to the game-development oriented mode."},
            {"usage": "/mode spec-driven", "description": "Switch to the structured spec-driven mode."},
            {"usage": "/mode spec-vibe", "description": "Switch to the lighter-weight spec workflow."},
            {"usage": "/mode writer", "description": "Switch to creative writing and documentation mode."},
            {"usage": "/mode reverie-ant", "description": "Switch to the advanced planning/execution mode."},
        ],
        "examples": ["/mode", "/mode spec-driven", "/mode reverie"],
    },
    "iflow": {
        "command": "/iflow",
        "section": "Providers",
        "summary": "Manage the iFlow relay catalog, current model, and endpoint override.",
        "detail": "This command works against the iFlow-specific catalog and credentials discovered from the local CLI cache.",
        "overview": "status, model [id], endpoint [value]",
        "subcommands": [
            {"usage": "/iflow", "description": "Show iFlow credential and model status."},
            {"usage": "/iflow status", "description": "Explicit status view."},
            {"usage": "/iflow model", "description": "Open the iFlow model selector."},
            {"usage": "/iflow model <model-id>", "description": "Switch directly to an iFlow model from the approved catalog."},
            {"usage": "/iflow endpoint", "description": "Show the current endpoint override prompt."},
            {"usage": "/iflow endpoint <url|/path|clear>", "description": "Set or clear the reverse-proxy endpoint override."},
        ],
        "examples": ["/iflow", "/iflow model glm-5", "/iflow endpoint http://127.0.0.1:8000/v1/chat/completions"],
    },
    "qwencode": {
        "command": "/qwencode",
        "section": "Providers",
        "summary": "Manage Qwen Code OAuth relay status, login refresh, model selection, and endpoint override.",
        "detail": "Reverie reads local Qwen OAuth credentials, keeps the provider on the supported `coder-model`, and exposes endpoint override controls for reverse proxies.",
        "overview": "status, login, model [id], endpoint [value]",
        "subcommands": [
            {"usage": "/qwencode", "description": "Show Qwen Code credential and selected-model status."},
            {"usage": "/qwencode status", "description": "Explicit status view."},
            {"usage": "/qwencode login", "description": "Validate or refresh local Qwen OAuth credentials."},
            {"usage": "/qwencode model", "description": "Open the Qwen Code model selector."},
            {"usage": "/qwencode model <model-id>", "description": "Switch directly to a supported Qwen Code model."},
            {"usage": "/qwencode endpoint", "description": "Show the current endpoint override prompt."},
            {"usage": "/qwencode endpoint <url|/path|clear>", "description": "Set or clear the reverse-proxy endpoint override."},
        ],
        "examples": ["/qwencode", "/qwencode login", "/qwencode model coder-model"],
    },
    "geminicli": {
        "command": "/Geminicli",
        "section": "Providers",
        "summary": "Manage Gemini CLI OAuth relay status, models, and endpoint override.",
        "detail": "Personal Google-account login works directly through Gemini CLI. A project override can still be stored for advanced setups, but it is optional.",
        "overview": "status, login, model [id], endpoint [value]",
        "aliases": ["/geminicli"],
        "subcommands": [
            {"usage": "/Geminicli", "description": "Show Gemini CLI credential, model, and optional project-override status."},
            {"usage": "/Geminicli status", "description": "Explicit status view."},
            {"usage": "/Geminicli login", "description": "Validate or refresh Gemini OAuth credentials from the local CLI cache."},
            {"usage": "/Geminicli model", "description": "Open the Gemini CLI model selector."},
            {"usage": "/Geminicli model <model-id>", "description": "Switch directly to a supported Gemini CLI model."},
            {"usage": "/Geminicli endpoint", "description": "Show the current endpoint override prompt."},
            {"usage": "/Geminicli endpoint <url|/path|clear>", "description": "Set or clear the reverse-proxy endpoint override."},
        ],
        "examples": ["/Geminicli", "/Geminicli model gemini-3-pro-preview", "/Geminicli endpoint http://127.0.0.1:8000/v1internal:streamGenerateContent?alt=sse"],
    },
    "codex": {
        "command": "/codex",
        "section": "Providers",
        "summary": "Switch to Codex, choose a model, and set the matching four-level reasoning depth.",
        "detail": "Bare `/codex` switches Reverie to the Codex source and uses the stored Codex model. `/codex model` opens the model selector and immediately continues into the reasoning-depth selector.",
        "overview": "activate, login, model [id], thinking [level], endpoint [value], low|medium|high|extra high",
        "subcommands": [
            {"usage": "/codex", "description": "Switch Reverie to the Codex source and show the active Codex configuration."},
            {"usage": "/codex login", "description": "Validate or refresh Codex credentials from the local CLI cache."},
            {"usage": "/codex model", "description": "Open the Codex model selector, then continue into reasoning-depth selection."},
            {"usage": "/codex model <model-id>", "description": "Switch directly to a supported Codex model and keep its compatible reasoning depth."},
            {"usage": "/codex thinking", "description": "Open the reasoning-depth selector for the current Codex model."},
            {"usage": "/codex thinking <low|medium|high|extra high>", "description": "Set the reasoning depth explicitly."},
            {"usage": "/codex low|medium|high|extra high", "description": "Direct shortcut for reasoning-depth selection."},
            {"usage": "/codex endpoint", "description": "Show the current endpoint override prompt."},
            {"usage": "/codex endpoint <url|/path|clear>", "description": "Set or clear the reverse-proxy endpoint override."},
        ],
        "examples": ["/codex", "/codex model", "/codex model gpt-5.4", "/codex extra high"],
    },
    "tools": {
        "command": "/tools",
        "section": "Tools & Context",
        "summary": "List the tools currently visible in the active mode.",
        "detail": "Tool visibility changes with the active mode and provider setup, so this is the live source of truth.",
        "overview": "tool visibility",
        "subcommands": [
            {"usage": "/tools", "description": "Show all tools currently available to the active agent mode."},
        ],
        "examples": ["/tools"],
    },
    "search": {
        "command": "/search",
        "section": "Tools & Context",
        "summary": "Run a web search and render the result as formatted output.",
        "detail": "Use this when you want an explicit web lookup rather than relying on model memory.",
        "overview": "<query>",
        "subcommands": [
            {"usage": "/search <query>", "description": "Search the web for the given query and show the top extracted results."},
        ],
        "examples": ["/search rust async patterns", "/search latest sqlite wal mode docs"],
    },
    "index": {
        "command": "/index",
        "section": "Tools & Context",
        "summary": "Rebuild the code index for the current workspace.",
        "detail": "Useful after large file changes when you want the symbol and dependency index refreshed immediately.",
        "overview": "full reindex",
        "subcommands": [
            {"usage": "/index", "description": "Run a full codebase re-index and report scan statistics."},
        ],
        "examples": ["/index"],
    },
    "ce": {
        "command": "/CE",
        "section": "Tools & Context",
        "summary": "Inspect or manage the Context Engine state.",
        "detail": "This command is case-sensitive and is the main control surface for manual context compression and token inspection.",
        "overview": "status, compress, info, stats",
        "subcommands": [
            {"usage": "/CE", "description": "Show Context Engine status, token usage, and available actions."},
            {"usage": "/CE compress", "description": "Compress the current conversation context."},
            {"usage": "/CE info", "description": "Show message counts, system-prompt length, and mode details."},
            {"usage": "/CE stats", "description": "Show full token statistics from the token counter tool."},
        ],
        "examples": ["/CE", "/CE compress", "/CE stats"],
    },
    "tti": {
        "command": "/tti",
        "section": "Tools & Context",
        "summary": "Manage text-to-image models or generate an image from the current default model.",
        "detail": "Bare `/tti` needs a child action or prompt. Model management and generation share this single command namespace.",
        "overview": "models, add, <prompt>",
        "subcommands": [
            {"usage": "/tti models", "description": "Open the TTI model selector and change the default image model."},
            {"usage": "/tti add", "description": "Add a new text-to-image model entry to the local config."},
            {"usage": "/tti <prompt>", "description": "Generate one image using the default TTI model and default parameters."},
        ],
        "examples": ["/tti models", "/tti add", "/tti cyberpunk rainy alley concept art"],
    },
    "setting": {
        "command": "/setting",
        "section": "Project & Rules",
        "summary": "Open the settings dashboard or change runtime settings directly from the command line.",
        "detail": "The settings system now supports both a richer TUI and direct subcommands for mode, model, theme, API, workspace, and rules controls.",
        "overview": "ui, status, mode, model, theme, auto-index, status-line, stream, timeout, retries, debug, workspace, rules",
        "subcommands": [
            {"usage": "/setting", "description": "Open the interactive settings interface with keyboard navigation and live detail panels.", "example": "/setting"},
            {"usage": "/setting ui", "description": "Explicitly open the interactive settings interface.", "example": "/setting ui"},
            {"usage": "/setting status", "description": "Show the settings dashboard without entering the TUI.", "example": "/setting status"},
            {"usage": "/setting mode <mode-name>", "description": "Change the active Reverie operating mode.", "example": "/setting mode writer"},
            {"usage": "/setting model", "description": "Open the standard-model selector from settings.", "example": "/setting model"},
            {"usage": "/setting model <index>", "description": "Switch to a standard model by index or fuzzy name.", "example": "/setting model 2"},
            {"usage": "/setting theme <theme>", "description": "Change the stored theme preset.", "example": "/setting theme ocean"},
            {"usage": "/setting auto-index on|off", "description": "Enable or disable automatic indexing on cold starts.", "example": "/setting auto-index off"},
            {"usage": "/setting status-line on|off", "description": "Enable or disable the live status line.", "example": "/setting status-line on"},
            {"usage": "/setting stream on|off", "description": "Enable or disable streaming responses.", "example": "/setting stream off"},
            {"usage": "/setting timeout <seconds>", "description": "Set the default API timeout.", "example": "/setting timeout 120"},
            {"usage": "/setting retries <count>", "description": "Set the retry budget for recoverable API failures.", "example": "/setting retries 5"},
            {"usage": "/setting debug on|off", "description": "Toggle debug logging for API requests.", "example": "/setting debug on"},
            {"usage": "/setting workspace on|off", "description": "Switch between workspace-local and global config storage.", "example": "/setting workspace on"},
            {"usage": "/setting rules", "description": "Open the quick rules editor from the settings command.", "example": "/setting rules"},
        ],
        "examples": ["/setting", "/setting status", "/setting mode spec-driven", "/setting timeout 120"],
    },
    "rules": {
        "command": "/rules",
        "section": "Project & Rules",
        "summary": "List, edit, add, or remove custom rules.",
        "detail": "Rules are applied to the session prompt. Use `/rules edit` for direct file editing or `/rules add` for quick one-line entries.",
        "overview": "list, edit, add [text], remove/delete <n>",
        "subcommands": [
            {"usage": "/rules", "description": "List all custom rules."},
            {"usage": "/rules list", "description": "Explicit list view."},
            {"usage": "/rules edit", "description": "Open `rules.txt` in the default editor and reload it after confirmation."},
            {"usage": "/rules add", "description": "Prompt for a new one-line rule interactively."},
            {"usage": "/rules add <text>", "description": "Add a new rule directly from the command line."},
            {"usage": "/rules remove <number>", "description": "Remove a rule by its list index."},
            {"usage": "/rules delete <number>", "description": "Alias of `/rules remove <number>`."},
        ],
        "examples": ["/rules", "/rules add Always run tests before finalizing", "/rules remove 2"],
    },
    "workspace": {
        "command": "/workspace",
        "section": "Project & Rules",
        "summary": "Control workspace-local config mode and copy config between global and local scopes.",
        "detail": "Use this when you want per-project config instead of a single global config file.",
        "overview": "status, enable, disable, copy-to-workspace, copy-to-global",
        "subcommands": [
            {"usage": "/workspace", "description": "Show workspace-config status and available actions."},
            {"usage": "/workspace status", "description": "Explicit status view."},
            {"usage": "/workspace enable", "description": "Enable workspace-local configuration mode."},
            {"usage": "/workspace disable", "description": "Disable workspace-local configuration and return to global config."},
            {"usage": "/workspace copy-to-workspace", "description": "Copy the global config into the workspace config file."},
            {"usage": "/workspace copy-to-global", "description": "Copy the workspace config into the global config file."},
        ],
        "examples": ["/workspace", "/workspace enable", "/workspace copy-to-workspace"],
    },
    "sessions": {
        "command": "/sessions",
        "section": "Sessions & Recovery",
        "summary": "Open the interactive session browser for create, load, or delete actions.",
        "detail": "This command is prompt-driven rather than subcommand-driven: it shows the session table, then waits for an action.",
        "overview": "open ui; actions: n, d, <number>",
        "subcommands": [
            {"usage": "/sessions", "description": "Open the session browser."},
            {"usage": "Action: n", "description": "Create a new session after the browser opens."},
            {"usage": "Action: <number>", "description": "Load a session by its listed index."},
            {"usage": "Action: d", "description": "Delete a session after entering its index."},
        ],
        "examples": ["/sessions"],
    },
    "history": {
        "command": "/history",
        "section": "Sessions & Recovery",
        "summary": "Show recent conversation history from the active agent.",
        "detail": "Without a number it prints the full retained history. With a number it limits the output to the latest N entries.",
        "overview": "[count]",
        "subcommands": [
            {"usage": "/history", "description": "Show all retained conversation history."},
            {"usage": "/history <count>", "description": "Show only the most recent `<count>` messages."},
        ],
        "examples": ["/history", "/history 20"],
    },
    "rollback": {
        "command": "/rollback",
        "section": "Sessions & Recovery",
        "summary": "Rollback to a previous question, tool call, or checkpoint.",
        "detail": "Bare `/rollback` opens the interactive rollback UI. You can also target common rollback modes directly from the command line.",
        "overview": "interactive, question, tool, <checkpoint-id>",
        "subcommands": [
            {"usage": "/rollback", "description": "Open the interactive rollback UI."},
            {"usage": "/rollback question", "description": "Rollback to the previous user question."},
            {"usage": "/rollback tool", "description": "Rollback to the previous tool call."},
            {"usage": "/rollback <checkpoint-id>", "description": "Rollback directly to a specific checkpoint id."},
        ],
        "examples": ["/rollback", "/rollback question", "/rollback cp_20260311_001"],
    },
    "undo": {
        "command": "/undo",
        "section": "Sessions & Recovery",
        "summary": "Undo the last rollback operation.",
        "detail": "Only available when the rollback manager has something to undo.",
        "overview": "undo last rollback",
        "subcommands": [
            {"usage": "/undo", "description": "Undo the most recent rollback action."},
        ],
        "examples": ["/undo"],
    },
    "redo": {
        "command": "/redo",
        "section": "Sessions & Recovery",
        "summary": "Redo the last undone rollback operation.",
        "detail": "Only available after an undo and while the redo stack still exists.",
        "overview": "redo last undo",
        "subcommands": [
            {"usage": "/redo", "description": "Redo the most recently undone rollback action."},
        ],
        "examples": ["/redo"],
    },
    "checkpoints": {
        "command": "/checkpoints",
        "section": "Sessions & Recovery",
        "summary": "Browse checkpoints and restore one interactively.",
        "detail": "This opens a checkpoint selector rather than accepting textual subcommands.",
        "overview": "interactive selector",
        "subcommands": [
            {"usage": "/checkpoints", "description": "Open the checkpoint selector and restore a checkpoint interactively."},
        ],
        "examples": ["/checkpoints"],
    },
    "operations": {
        "command": "/operations",
        "section": "Sessions & Recovery",
        "summary": "Show operation history and rollback statistics.",
        "detail": "Use this to inspect the recent operation log, counts, modified files, and undo/redo availability.",
        "overview": "history & stats",
        "subcommands": [
            {"usage": "/operations", "description": "Show recent operations and summary statistics."},
        ],
        "examples": ["/operations"],
    },
    "gdd": {
        "command": "/gdd",
        "section": "Game",
        "summary": "Create, view, or summarize the game design document.",
        "detail": "Primarily intended for `reverie-gamer`, but the command is available whenever the game tools are installed.",
        "overview": "create, view, summary",
        "subcommands": [
            {"usage": "/gdd", "description": "View the current game design document."},
            {"usage": "/gdd view", "description": "Explicit view action."},
            {"usage": "/gdd create", "description": "Generate a new game design document interactively."},
            {"usage": "/gdd summary", "description": "Generate a summarized view of the GDD."},
        ],
        "examples": ["/gdd", "/gdd create", "/gdd summary"],
    },
    "assets": {
        "command": "/assets",
        "section": "Game",
        "summary": "List detected game assets, optionally filtered by type.",
        "detail": "When no type is supplied it prints grouped asset tables; otherwise it shows the filtered asset list.",
        "overview": "all, sprite, audio, model, animation",
        "subcommands": [
            {"usage": "/assets", "description": "Show all detected assets grouped by type."},
            {"usage": "/assets all", "description": "Explicit all-assets view."},
            {"usage": "/assets sprite", "description": "Show only sprite assets."},
            {"usage": "/assets audio", "description": "Show only audio assets."},
            {"usage": "/assets model", "description": "Show only 3D model assets."},
            {"usage": "/assets animation", "description": "Show only animation assets."},
        ],
        "examples": ["/assets", "/assets sprite", "/assets audio"],
    },
}


def normalize_help_topic(value: str) -> str:
    """Resolve a help query to a canonical help topic key."""
    raw = str(value or "").strip()
    if not raw:
        return ""

    normalized = raw.lstrip("/").strip().lower().replace("-", "_")
    primary = normalized.split()[0] if normalized.split() else ""
    compact = normalized.replace(" ", "")
    alias_map = {
        "gemini": "geminicli",
        "geminicli": "geminicli",
        "gcli": "geminicli",
        "ce": "ce",
        "contextengine": "ce",
        "context": "ce",
        "quit": "exit",
    }

    for candidate in (compact, primary):
        if candidate in HELP_TOPICS:
            return candidate
        if candidate in alias_map:
            return alias_map[candidate]
    return ""


def build_command_completion_map() -> Dict[str, str]:
    """Build the command-completion descriptions from the shared help catalog."""
    completions: Dict[str, str] = {}
    for topic in HELP_TOPICS.values():
        command = str(topic.get("command", "")).strip()
        summary = str(topic.get("summary", "")).strip()
        if command and summary:
            completions[command] = summary
        for alias in topic.get("aliases", []) or []:
            alias_text = str(alias).strip()
            if alias_text and alias_text not in completions:
                completions[alias_text] = f"Alias of {command}"
    return completions
