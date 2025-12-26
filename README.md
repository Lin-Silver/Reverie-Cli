# Reverie Cli

**World-Class Context Engine Coding Assistant**

Reverie is an agentic coding tool that uses a sophisticated Context Engine to understand large codebases and significantly reduce AI model hallucinations.

## Features

- **World-Class Context Engine**: Intelligent code indexing and retrieval
  - Symbol table with fast lookup
  - Dependency graph for relationship tracking
  - Multi-language support (Python, JS/TS, C/C++, C#, Rust, Go, Java, Zig, HTML, CSS)
  - Incremental updates for large codebases (>5MB)

- **AI Agent with Tool Calling**: 
  - OpenAI-compatible API support
  - Streaming and non-streaming modes
  - 7 built-in tools for coding tasks

- **Rich CLI Interface**:
  - Syntax-highlighted code display
  - Diff visualization
  - Session management
  - Real-time progress indicators

- **Git Integration**:
  - Commit history analysis
  - Blame information
  - Historical context for code changes

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

Configuration is stored in `.reverie/config.json` in your project directory.

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
│   └── task_manager.py  # Task organization
├── cli/                 # User interface
│   ├── interface.py     # Main CLI
│   ├── commands.py      # Command handler
│   └── display.py       # Rich components
├── session/             # Session management
├── config.py            # Configuration
└── __main__.py          # Entry point
```

## Context Engine Principle

The Context Engine follows a "minimal but complete" strategy:
- Indexes all code symbols and their relationships
- Tracks dependencies to understand impact of changes
- Provides only the context the AI needs - no more, no less

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
