# Reverie Cli

**World-Class Context Engine Coding Assistant**

Reverie is an agentic coding tool that uses a sophisticated Context Engine to understand large codebases and significantly reduce AI model hallucinations.

## Features

- **Advanced Context Engine**: Deep code understanding with multiple analysis layers
  - Semantic indexing for intent-based code search
  - Knowledge graph for relationship tracking and impact analysis
  - Commit history learning from past implementations
  - Symbol table with fast lookup
  - Dependency graph for relationship tracking
  - Multi-language support (Python, JS/TS, C/C++, C#, Rust, Go, Java, Zig, HTML, CSS)
  - Incremental updates for large codebases (>5MB)

- **Nexus - Large-Scale Project Development**:
  - 24+ hour continuous work sessions
  - External context management to bypass token limits
  - Phase-based workflow (Planning, Design, Implementation, Testing, Integration, Documentation, Verification)
  - Automatic checkpoint and recovery
  - Self-healing and error recovery

- **AI Agent with Tool Calling**: 
  - OpenAI-compatible API support
  - Streaming and non-streaming modes
  - 10+ built-in tools for coding tasks
  - Nexus tool for large-scale projects

- **Rich CLI Interface**:
  - Modern TUI with keyboard navigation (arrow keys, Enter, Escape)
  - Syntax-highlighted code display
  - Diff visualization
  - Session management with timestamp-based naming
  - Real-time progress indicators
  - Interactive selectors for models, settings, sessions, and checkpoints

- **Enhanced Checkpoint System**:
  - File-level checkpoints with automatic snapshots
  - TUI rollback interface for version restoration
  - Version history tracking
  - Automatic cleanup of old checkpoints

- **Git Integration**:
  - Commit history analysis
  - Blame information
  - Historical context for code changes
  - Pattern extraction from past implementations

- **Writer Mode**:
  - Mandatory outline phase with user approval
  - Novel memory and consistency systems
  - Character and location tracking
  - Plot thread management
  - Quality analysis and validation

## Installation

```bash
# Clone the repository
git clone https://github.com/raiden/reverie-cli.git
cd reverie-cli

# Create virtual environment
python -m venv venv
venv\Scripts\activate  # Windows
# source venv/bin/activate  # Linux/Mac

# Install in development mode
pip install -e .
```

## Quick Start

```bash
# Run in a project directory
reverie

# Or specify a path
reverie /path/to/your/project

# Index only (no interactive mode)
reverie --index-only
```

## Configuration

On first run, Reverie will guide you through configuration:

1. **API Base URL**: Your LLM provider endpoint (e.g., `https://api.openai.com/v1`)
2. **API Key**: Your authentication key
3. **Model**: The model to use (e.g., `gpt-4o`)

### Configuration Modes

Reverie supports two configuration modes:

**Global Mode (Default)**:
- Configuration stored in `<app_root>/.reverie/config.json`
- Shared across all workspaces
- Quick setup for single workspace use

**Workspace Mode**:
- Configuration stored in `<project_root>/.reverie/config.json`
- Each workspace has independent configuration
- Perfect for multi-workspace scenarios

### Managing Workspace Configuration

```bash
# View current configuration status
/workspace

# Enable workspace-local configuration
/workspace enable

# Disable workspace-local configuration (use global)
/workspace disable

# Copy global config to workspace
/workspace copy-to-workspace

# Copy workspace config to global
/workspace copy-to-global
```

See [WORKSPACE_CONFIG.md](WORKSPACE_CONFIG.md) for detailed documentation on multi-workspace configuration.

### Text-to-Image Configuration (v2.0.1)

Reverie now supports a built-in `text_to_image` tool (available in all modes) that calls `Comfy/generate_image.py`.

Add this section to your `config.json`:

```json
"tti-models": [
  {
    "path": "Comfy/models/t2i/bluePencilXL_v700.safetensors",
    "display_name": "blue-pencil-xl",
    "introduction": "General illustration model"
  },
  {
    "path": "D:/AI/models/another_model.safetensors",
    "display_name": "another-model",
    "introduction": ""
  }
],
"text_to_image": {
  "enabled": true,
  "python_executable": "",
  "script_path": "Comfy/generate_image.py",
  "output_dir": ".",
  "models": [],
  "default_model_display_name": "blue-pencil-xl"
}
```

`tti-models` is the top-level editable model list. On load/save, Reverie automatically syncs `tti-models` and `text_to_image.models`.
`models[].path` supports both relative paths (relative to project root/config directory) and absolute paths.
`text_to_image.output_dir` defaults to project root (`"."`).
When calling `text_to_image(action="generate")`, `output_path` should be a relative path under project root.
If `python_executable` is empty, Reverie uses the current Python (dev mode) or discovers `python/py` from PATH (packaged exe mode).

When building `reverie.exe` with `build.bat`, required runtime assets for text-to-image (`generate_image.py` and `embedded_comfy.b64`) are embedded into the executable bundle path automatically. You do not need to keep a separate `Comfy` folder next to `reverie.exe` for these two files.

### Optional TTI Dependencies

If you want to run `/tti` image generation in environments without a prepared Comfy Python environment, install optional dependencies manually:

```bash
pip install -r requirements-tti.txt
```

These dependencies are intentionally kept separate from the main project requirements.

## CLI Commands

| Command | Description |
|---------|-------------|
| `/help` | Show available commands |
| `/model` | List and select models |
| `/status` | Show current status |
| `/search <query>` | Search the web |
| `/sessions` | Manage sessions |
| `/history [limit]` | View conversation history |
| `/clear` | Clear the screen |
| `/index` | Re-index the codebase |
| `/tti models` | Show configured TTI models and interactively select default model |
| `/tti add` | Add a new TTI model entry (`path`, `display_name`, `introduction`) |
| `/tti <prompt>` | Generate an image with default TTI model and default parameters |
| `/exit` | Exit Reverie |

## Architecture

```
reverie/
├── context_engine/      # The heart of Reverie
│   ├── symbol_table.py  # Symbol storage and lookup
│   ├── dependency_graph.py  # Relationship tracking
│   ├── indexer.py       # Codebase scanning
│   ├── retriever.py     # Context selection
│   ├── cache.py         # Persistent storage
│   ├── git_integration.py  # Git context
│   ├── semantic_indexer.py  # Semantic code understanding
│   ├── knowledge_graph.py   # Advanced relationship tracking
│   ├── commit_history_indexer.py  # Learn from past changes
│   ├── context_engine_core.py  # Unified context management
│   └── parsers/         # Multi-language parsing
├── agent/               # AI Agent
│   ├── agent.py         # Main agent class
│   ├── system_prompt.py # AI instructions
│   └── tool_executor.py # Tool execution
├── tools/               # Agent tools
│   ├── codebase_retrieval.py  # Query codebase
│   ├── git_commit_retrieval.py  # Git history
│   ├── str_replace_editor.py  # File editing
│   ├── file_ops.py      # File operations
│   ├── command_exec.py  # Shell commands
│   ├── web_search.py    # Web search
│   ├── task_manager.py  # Task organization
│   ├── nexus.py         # Large-scale project development
│   └── nexus_tool.py    # Nexus workflow management
├── cli/                 # User interface
│   ├── interface.py     # Main CLI
│   ├── commands.py      # Command handler
│   ├── display.py       # Rich components
│   └── tui_selector.py  # Interactive TUI selectors
├── session/             # Session management
│   ├── manager.py       # Session persistence
│   ├── checkpoint.py    # File-level checkpoints
│   └── archive.py       # Long-term storage
├── config.py            # Configuration
└── __main__.py          # Entry point
```

## Context Engine Principle

The Context Engine follows a "minimal but complete" strategy with advanced capabilities:
- **Semantic Indexing**: Understand code intent and meaning, not just structure
- **Knowledge Graph**: Track complex relationships and predict impact of changes
- **Commit History Learning**: Extract patterns and learn from successful implementations
- **Symbol Table**: Index all code symbols and their relationships
- **Dependency Tracking**: Understand dependencies to predict impact of changes
- **Intelligent Context Selection**: Provide only the context the AI needs - no more, no less

This approach significantly reduces hallucinations by ensuring the AI has accurate, up-to-date information about the codebase.

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Type checking
mypy reverie

# Format code
black reverie
```

## License

MIT License - Developed by Raiden
