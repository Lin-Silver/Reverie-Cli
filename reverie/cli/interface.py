"""
Main Interface - The primary CLI interface with Dreamscape Theme

Handles:
- Welcome screen with dreamy aesthetics
- Setup wizard
- Main interaction loop
- Real-time status bar with themed styling
"""

import time
import sys
import threading
import _thread
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, List, Dict, Any

from rich.console import Console, Group
from rich.prompt import Prompt, Confirm
from rich.live import Live
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn, TimeRemainingColumn
from rich.panel import Panel
from rich.padding import Padding
from rich.text import Text
from rich.table import Table
from rich.markup import escape
from rich import box

from .display import DisplayComponents
from .commands import CommandHandler
from .input_handler import InputHandler
from .markdown_formatter import MarkdownFormatter, format_markdown
from .theme import THEME, DECO, DREAM
from ..inline_images import (
    build_user_message_content,
    flatten_multimodal_content_for_display,
    parse_inline_image_mentions,
)
from ..config import (
    ConfigManager,
    ModelConfig,
    Config,
    get_computer_controller_data_dir,
    normalize_tti_models,
    resolve_tti_default_display_name,
)
from ..atlas import build_atlas_additional_rules, normalize_atlas_mode_config
from ..mcp import MCPConfigManager, MCPRuntime
from ..engine_lite.modeling import ASHFOX_DEFAULT_ENDPOINT, ASHFOX_MCP_SERVER_NAME
from ..rules_manager import RulesManager
from ..session import SessionManager
from ..agent import (
    ReverieAgent,
    STREAM_EVENT_MARKER,
    THINKING_START_MARKER,
    THINKING_END_MARKER,
    build_system_prompt,
    decode_stream_event,
)
from ..context_engine import CodebaseIndexer, ContextRetriever, GitIntegration
from ..context_engine import LSPManager
from ..modes import normalize_mode
from ..nvidia import (
    build_nvidia_computer_controller_runtime_model_data,
    normalize_nvidia_config,
    resolve_nvidia_selected_model,
)


_THINKING_MARKDOWN_SUBJECT_RE = re.compile(r"^\s*\*\*(.+?)\*\*\s*$")
_THINKING_INLINE_SUBJECT_RE = re.compile(r"\*\*(.+?)\*\*")
_THINKING_LIST_PREFIX_RE = re.compile(r"^(?:[-*]|\d+\.)\s+")
_MARKDOWN_FENCE_RE = re.compile(r"^\s*(```+|~~~+)")
_TABLE_ROW_RE = re.compile(r"^\s*\|(.+)\|\s*$")
_TABLE_SEPARATOR_RE = re.compile(r"^\s*\|?\s*(:?-+:?)\s*(\|\s*(:?-+:?)\s*)+\|?\s*$")
_TOOL_MARKUP_PREFIXES = (
    "[bold #ffb8d1]✧",
    "[bold #ff5252]",
    "[bold #66bb6a]",
    "[#ba68c8]   │",
)


def _find_trailing_incomplete_markdown_block_start(completed_lines: list[str]) -> int:
    """Return the index of a trailing block that must stay buffered for correct rendering."""
    open_fence_token = ""
    open_fence_index = -1
    in_table = False
    table_start_index = -1
    possible_table_header_index = -1
    index = 0

    while index < len(completed_lines):
        line = completed_lines[index]

        if open_fence_token:
            fence_match = _MARKDOWN_FENCE_RE.match(line) if ("`" in line or "~" in line) else None
            if (
                fence_match
                and fence_match.group(1).startswith(open_fence_token[0])
                and len(fence_match.group(1)) >= len(open_fence_token)
            ):
                open_fence_token = ""
                open_fence_index = -1
            index += 1
            continue

        if in_table:
            if _TABLE_SEPARATOR_RE.match(line) or _TABLE_ROW_RE.match(line):
                index += 1
                continue
            in_table = False
            table_start_index = -1

        fence_match = _MARKDOWN_FENCE_RE.match(line) if ("`" in line or "~" in line) else None
        if fence_match:
            open_fence_token = fence_match.group(1)
            open_fence_index = index
            possible_table_header_index = -1
            index += 1
            continue

        if possible_table_header_index >= 0:
            if _TABLE_SEPARATOR_RE.match(line):
                in_table = True
                table_start_index = possible_table_header_index
                possible_table_header_index = -1
                index += 1
                continue
            possible_table_header_index = -1

        if _TABLE_ROW_RE.match(line):
            if index + 1 < len(completed_lines) and _TABLE_SEPARATOR_RE.match(completed_lines[index + 1]):
                in_table = True
                table_start_index = index
                possible_table_header_index = -1
                index += 1
                continue
            possible_table_header_index = index
            index += 1
            continue

        possible_table_header_index = -1
        index += 1

    if open_fence_token and open_fence_index >= 0:
        return open_fence_index
    if in_table and table_start_index >= 0:
        return table_start_index
    if possible_table_header_index >= 0:
        return possible_table_header_index
    return -1


def split_thinking_fragments(pending: str, fragment: str) -> tuple[list[str], str]:
    """Split streamed reasoning text into complete lines plus a pending tail."""
    text = f"{pending}{fragment}".replace("\r\n", "\n").replace("\r", "\n")
    if "\n" not in text:
        return [], text

    parts = text.split("\n")
    return parts[:-1], parts[-1]


def split_markdown_fragments(pending: str, fragment: str) -> tuple[str, str]:
    """Split streamed markdown into flushable complete lines plus a trailing remainder."""
    text = f"{pending}{fragment}".replace("\r\n", "\n").replace("\r", "\n")
    if "\n" not in text:
        return "", text

    parts = text.split("\n")
    completed_lines = parts[:-1]
    remainder = parts[-1]

    buffered_start_index = _find_trailing_incomplete_markdown_block_start(completed_lines)
    flush_lines = completed_lines
    if buffered_start_index >= 0:
        flush_lines = completed_lines[:buffered_start_index]
        buffered_lines = completed_lines[buffered_start_index:]
        buffered_text = "\n".join(buffered_lines)
        if buffered_lines:
            buffered_text += "\n"
        if remainder:
            buffered_text += remainder
        remainder = buffered_text

    completed = "\n".join(flush_lines)
    if completed:
        completed += "\n"
    return completed, remainder


def parse_thinking_line(raw_line: str) -> tuple[str, str]:
    """Normalize one reasoning line for terminal-friendly display."""
    text = str(raw_line or "").replace("\r", "")
    text = re.sub(r"[ \t]+", " ", text).strip()
    if not text:
        return "", ""

    subject_only = _THINKING_MARKDOWN_SUBJECT_RE.fullmatch(text)
    if subject_only:
        return subject_only.group(1).strip(), ""

    inline_subject = _THINKING_INLINE_SUBJECT_RE.search(text)
    if inline_subject:
        subject = inline_subject.group(1).strip()
        description = (
            text[:inline_subject.start()] + text[inline_subject.end():]
        ).strip(" :-")
        description = _THINKING_LIST_PREFIX_RE.sub("", description).strip()
        return subject, description

    return "", _THINKING_LIST_PREFIX_RE.sub("", text).strip()


def _configure_stdio_for_terminal_output() -> None:
    """Avoid UnicodeEncodeError on legacy Windows code pages by falling back to replacement writes."""
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream is None or not hasattr(stream, "reconfigure"):
            continue
        try:
            stream.reconfigure(errors="replace")
        except Exception:
            pass


class StatusLine:
    """Dynamic status line that updates on every render with dreamy styling"""
    def __init__(self, interface):
        self.interface = interface
    
    def __rich__(self):
        return self.interface._get_status_line()


@dataclass
class StreamInputState:
    """Shared state for streaming-time interjection input."""

    buffer: str = ""
    submitted_text: Optional[str] = None
    interrupt_requested: bool = False
    active: bool = False
    paused: bool = False
    lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def snapshot(self) -> dict:
        with self.lock:
            return {
                "buffer": self.buffer,
                "submitted_text": self.submitted_text,
                "interrupt_requested": self.interrupt_requested,
                "active": self.active,
                "paused": self.paused,
            }

    def append(self, value: str) -> None:
        with self.lock:
            self.buffer += value

    def backspace(self) -> None:
        with self.lock:
            self.buffer = self.buffer[:-1]

    def request_interrupt(self) -> None:
        with self.lock:
            self.interrupt_requested = True

    def request_submit(self) -> Optional[str]:
        with self.lock:
            value = self.buffer.rstrip()
            if not value.strip():
                return None
            self.submitted_text = value
            self.interrupt_requested = True
            return value

    def pause(self) -> None:
        with self.lock:
            self.paused = True

    def resume(self) -> None:
        with self.lock:
            self.paused = False

    def stop(self) -> None:
        with self.lock:
            self.active = False


class StreamingFooter:
    """Dynamic footer shown while the model is actively streaming."""

    def __init__(self, interface):
        self.interface = interface

    def __rich__(self):
        return self.interface._get_streaming_footer()


class ReverieInterface:
    """Main interactive interface for Reverie Cli with Dreamscape theme"""
    
    def __init__(self, project_root: Path):
        self.project_root = project_root
        _configure_stdio_for_terminal_output()
        self.console = Console(width=None, force_terminal=True)  # Auto-detect width and force terminal mode
        self.display = DisplayComponents(self.console)
        self.theme = THEME
        self.deco = DECO
        
        # Initialize managers
        self.config_manager = ConfigManager(project_root)
        self.config_manager.ensure_dirs()
        self.mcp_config_manager = MCPConfigManager(self.config_manager.app_root)
        self.mcp_config_manager.ensure_dirs()
        self._ensure_builtin_mcp_servers()
        self.mcp_runtime = MCPRuntime(self.mcp_config_manager, project_root=self.project_root)
        self.rules_manager = RulesManager(project_root)
        self._init_workspace_services()
        
        self.indexer: Optional[CodebaseIndexer] = None
        self.retriever: Optional[ContextRetriever] = None
        self.git_integration: Optional[GitIntegration] = None
        self.lsp_manager: Optional[LSPManager] = None
        self.agent: Optional[ReverieAgent] = None

        self.total_active_time = 0.0
        self.current_task_start: Optional[float] = None
        self.start_time = time.time()
        self._runtime_recorded = False
        self.command_handler: Optional[CommandHandler] = None
        self.input_handler: Optional[InputHandler] = None
        self.status_line = StatusLine(self)
        self.streaming_footer = StreamingFooter(self)
        self._stream_input_state: Optional[StreamInputState] = None
        self._stream_input_thread: Optional[threading.Thread] = None
        self._status_live = None
        self._pending_input_draft = ""
        self._markdown_formatter = MarkdownFormatter(console=self.console)
        self._status_line_cache_key = None
        self._status_line_cache_renderable = None
        self._status_line_cache_time = 0.0
        self._context_engine_ready = False
        self._indexing_in_progress = False
        self._git_integration_ready = False
        self._lsp_manager_ready = False
        self._runtime_scope = ""

    def _ensure_builtin_mcp_servers(self) -> None:
        """Ensure Reverie's built-in Ashfox MCP server entry exists."""
        try:
            config = self.mcp_config_manager.load()
            servers = dict(config.get("mcpServers", {}) or {})
            existing = dict(servers.get(ASHFOX_MCP_SERVER_NAME, {}) or {})

            desired = {
                "enabled": True,
                "type": "http",
                "httpUrl": ASHFOX_DEFAULT_ENDPOINT,
                "trust": True,
                "includeModes": ["reverie-gamer"],
            }

            updated = dict(existing)
            changed = False
            for key, value in desired.items():
                current_value = updated.get(key)
                if key == "includeModes":
                    if not current_value:
                        updated[key] = list(value)
                        changed = True
                    continue
                if current_value is None or current_value == "" or current_value == []:
                    updated[key] = value
                    changed = True

            if not existing or changed:
                self.mcp_config_manager.upsert_server(ASHFOX_MCP_SERVER_NAME, updated or desired)
        except Exception:
            pass

    def _init_workspace_services(self) -> None:
        """Initialize cache/session/rollback services for the active runtime scope."""
        config = self.config_manager.load()
        runtime_scope = "computer-controller" if normalize_mode(getattr(config, "mode", "reverie")) == "computer-controller" else "workspace"
        self._runtime_scope = runtime_scope
        self.project_data_dir = (
            get_computer_controller_data_dir(self.config_manager.app_root)
            if runtime_scope == "computer-controller"
            else self.config_manager.project_data_dir
        )
        self.project_data_dir.mkdir(parents=True, exist_ok=True)

        self.indexer = None
        self.retriever = None
        self._context_engine_ready = False
        self._indexing_in_progress = False

        from ..session import SnapshotManager, MemoryIndexer, WorkspaceStatsManager
        self.snapshot_manager = SnapshotManager(
            project_root=self.project_root,
            snapshots_dir=self.project_data_dir / 'snapshots'
        )
        self.memory_indexer = MemoryIndexer(self.project_data_dir)
        self.workspace_stats_manager = WorkspaceStatsManager(
            self.project_data_dir,
            project_root=None if runtime_scope == "computer-controller" else self.project_root,
        )

        self.session_manager = SessionManager(
            self.project_data_dir,
            project_root=None if runtime_scope == "computer-controller" else self.project_root,
            snapshot_manager=self.snapshot_manager,
            memory_indexer=self.memory_indexer,
            always_new_session=runtime_scope == "computer-controller",
            refresh_memory_index_on_save=runtime_scope == "computer-controller",
        )

        from ..session import OperationHistory, RollbackManager
        self.operation_history = OperationHistory(runtime_scope)
        self.rollback_manager = RollbackManager(self.project_data_dir, self.operation_history)
        self.total_active_time = self.workspace_stats_manager.get_total_active_seconds()

    def _runtime_scope_for_config(self, config: Optional[Config] = None) -> str:
        """Return the active runtime scope for the supplied config."""
        active_config = config or self.config_manager.load()
        return "computer-controller" if normalize_mode(getattr(active_config, "mode", "reverie")) == "computer-controller" else "workspace"

    def _ensure_runtime_services_for_config(self, config: Config) -> bool:
        """Rebuild mode-scoped runtime services when the active scope changes."""
        desired_scope = self._runtime_scope_for_config(config)
        if desired_scope == self._runtime_scope and getattr(self, "session_manager", None) and getattr(self, "memory_indexer", None):
            return False

        self._init_workspace_services()
        return True

    def _refresh_command_context(self) -> None:
        """Refresh command handler context after runtime objects are recreated."""
        if self.command_handler:
            self.command_handler.app = self._get_app_context()

    def clean_workspace_state(self) -> Dict[str, Any]:
        """
        Delete current-workspace memory/cache/audit data and start a fresh session.

        Config and rules are intentionally preserved.
        """
        from ..security_utils import collect_workspace_cleanup_targets, purge_workspace_state

        cleanup_targets = collect_workspace_cleanup_targets(
            self.project_root,
            self.project_data_dir,
        )
        cleanup_result = purge_workspace_state(
            self.project_root,
            self.project_data_dir,
        )

        result: Dict[str, Any] = {
            "success": not cleanup_result["errors"],
            "workspace_root": str(self.project_root),
            "project_data_dir": str(self.project_data_dir),
            "targets": [str(path) for path in cleanup_targets],
            **cleanup_result,
        }

        if cleanup_result["errors"]:
            return result

        self._pending_input_draft = ""
        self._status_live = None
        self.agent = None
        self.indexer = None
        self.retriever = None
        self.git_integration = None
        self.lsp_manager = None
        self._context_engine_ready = False
        self._git_integration_ready = False
        self._lsp_manager_ready = False

        self.config_manager.ensure_dirs()
        self._init_workspace_services()
        self._init_agent()
        self._init_session()
        self._refresh_command_context()

        current_session = self.session_manager.get_current_session()
        result["session_name"] = current_session.name if current_session else ""
        return result

    def _fast_clear_terminal(self) -> None:
        """Clear the terminal without going through a shell command."""
        try:
            self.console.clear()
            return
        except Exception:
            pass

        try:
            if sys.stdout and hasattr(sys.stdout, "write"):
                sys.stdout.write("\033[2J\033[H")
                sys.stdout.flush()
        except Exception:
            pass

        try:
            self.console.clear()
        except Exception:
            pass

    def _truncate_label(self, value: str, max_length: int) -> str:
        """Trim long labels for narrow terminals."""
        text = str(value or "").strip()
        if len(text) <= max_length:
            return text
        if max_length <= 1:
            return text[:max_length]
        return f"{text[:max_length - 1]}…"

    def _format_compact_quantity(self, value: int) -> str:
        """Compact metric formatter for status surfaces."""
        try:
            number = int(value)
        except (TypeError, ValueError):
            return str(value)
        if abs(number) >= 1_000_000:
            return f"{number / 1_000_000:.2f}M".rstrip("0").rstrip(".")
        if abs(number) >= 1_000:
            return f"{number / 1_000:.1f}K".rstrip("0").rstrip(".")
        return str(number)

    def _resolve_provider_label(self, config: Config) -> str:
        """Resolve the user-facing provider/source label."""
        provider_name = str(getattr(config.active_model, "provider", "openai-sdk") if config.active_model else "openai-sdk").strip().lower()
        source_name = str(getattr(config, "active_model_source", "standard") or "standard").strip().lower()
        provider_labels = {
            "openai-sdk": "OpenAI",
            "request": "Relay",
            "anthropic": "Anthropic",
            "gemini-cli": "Gemini",
            "codex": "Codex",
            "nvidia": "NVIDIA",
        }
        source_labels = {
            "standard": "config.json",
            "qwencode": "Qwen Code",
            "geminicli": "Gemini CLI",
            "codex": "Codex",
            "nvidia": "NVIDIA",
        }
        return source_labels.get(source_name, "") or provider_labels.get(provider_name, provider_name or "provider")
    
    def run(self) -> None:
        """Main entry point"""
        try:
            self._fast_clear_terminal()
            
            if not self.config_manager.is_configured():
                self.run_setup_wizard()
            
            config = self.config_manager.load()
            self.display.show_welcome(mode=config.mode)
            
            self._init_agent()
            self.command_handler = CommandHandler(self.console, self._get_app_context())
            self._init_session()
            
            self.main_loop()
            
        except KeyboardInterrupt:
            self.console.print(f"\n[bold {self.theme.PINK_SOFT}]{self.deco.SPARKLE} Goodbye! {self.deco.SPARKLE}[/bold {self.theme.PINK_SOFT}]")
        except Exception as e:
            self.console.print(f"\n[bold {self.theme.CORAL_VIBRANT}]{self.deco.CROSS_FANCY} Error: {escape(str(e))}[/bold {self.theme.CORAL_VIBRANT}]")
            import traceback
            traceback.print_exc()
        finally:
            self._persist_runtime_stats()

    def _get_status_line(self):
        """Generate a responsive live status panel."""
        cache_now = time.time()
        elapsed = self.total_active_time
        if self.current_task_start:
            elapsed += (cache_now - self.current_task_start)

        hours, remainder = divmod(int(elapsed), 3600)
        minutes, seconds = divmod(remainder, 60)
        time_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"

        config = getattr(self.agent, "config", None) or self.config_manager.load()
        active_model = config.active_model
        mode = config.mode or "reverie"
        provider_label = self._resolve_provider_label(config)
        model_name = active_model.model_display_name if active_model else "N/A"
        width = max(int(getattr(self.console.size, "width", 0) or self.console.width or 0), 60)
        compact = width < 112
        tiny = width < 86
        model_label = self._truncate_label(model_name, 24 if tiny else 36 if compact else 52)
        project_label = self._truncate_label(self.project_root.name or str(self.project_root), 12 if tiny else 18)

        reasoning_label = ""
        provider_name = str(getattr(active_model, "provider", "openai-sdk") if active_model else "openai-sdk").strip().lower()
        if provider_name == "codex" and active_model:
            from ..codex import get_codex_reasoning_label

            reasoning_mode = str(getattr(active_model, "thinking_mode", "") or "").strip()
            if reasoning_mode:
                reasoning_label = get_codex_reasoning_label(reasoning_mode)

        index_status_text = self._get_index_status_text()
        index_status_label = index_status_text.plain if index_status_text else None

        total_tokens = None
        max_tokens = 128000
        percentage = 0.0
        token_color = self.theme.MINT_SOFT
        if self.agent:
            try:
                total_tokens = max(int(self.agent.get_token_estimate()), 0)
                if active_model and active_model.max_context_tokens:
                    max_tokens = active_model.max_context_tokens

                percentage = (total_tokens / max_tokens * 100) if max_tokens else 0
                if percentage >= 80:
                    token_color = self.theme.CORAL_VIBRANT
                elif percentage >= 70:
                    token_color = self.theme.AMBER_GLOW
            except Exception:
                total_tokens = None

        cache_key = (
            time_str,
            provider_label,
            str(mode).upper(),
            model_label,
            project_label,
            reasoning_label,
            index_status_label,
            total_tokens,
            max_tokens,
            int(percentage),
            token_color,
            width < 112,
            width < 86,
        )
        if (
            self._status_line_cache_key == cache_key
            and self._status_line_cache_renderable is not None
            and (cache_now - self._status_line_cache_time) < 0.35
        ):
            return self._status_line_cache_renderable

        top_left = Text()
        top_left.append(f"{self.deco.SPARKLE_FILLED} ", style=self.theme.PINK_SOFT)
        top_left.append(model_label, style=f"bold {self.theme.PURPLE_SOFT}")

        top_right = Text()
        top_right.append(project_label, style=self.theme.TEXT_DIM)
        top_right.append(f" {self.deco.DOT_MEDIUM} ", style=self.theme.TEXT_DIM)
        top_right.append(time_str, style=f"bold {self.theme.TEXT_PRIMARY}")

        top_grid = Table.grid(expand=True)
        top_grid.add_column(ratio=1)
        top_grid.add_column(justify="right", no_wrap=True)
        top_grid.add_row(top_left, top_right)

        summary = Text()
        summary.append(provider_label, style=self.theme.BLUE_SOFT)
        summary.append(f" {self.deco.DOT_MEDIUM} ", style=self.theme.TEXT_DIM)
        summary.append(str(mode).upper(), style=f"bold {self.theme.BLUE_SOFT}")
        if reasoning_label:
            summary.append(f" {self.deco.DOT_MEDIUM} ", style=self.theme.TEXT_DIM)
            summary.append(reasoning_label, style=self.theme.AMBER_GLOW)
        if total_tokens is not None:
            summary.append(f" {self.deco.DOT_MEDIUM} ", style=self.theme.TEXT_DIM)
            usage = f"{self._format_compact_quantity(total_tokens)}/{self._format_compact_quantity(max_tokens)}"
            if not tiny:
                usage += f" ({percentage:.0f}%)"
            summary.append(usage, style=token_color)
        if index_status_text:
            summary.append(f" {self.deco.DOT_MEDIUM} ", style=self.theme.TEXT_DIM)
            summary.append_text(index_status_text)

        if compact:
            body = Group(top_grid, summary)
        else:
            secondary = Text()
            secondary.append("Source ", style=self.theme.TEXT_DIM)
            secondary.append(provider_label, style=self.theme.BLUE_SOFT)
            secondary.append(f" {self.deco.DOT_MEDIUM} ", style=self.theme.TEXT_DIM)
            secondary.append("Mode ", style=self.theme.TEXT_DIM)
            secondary.append(str(mode).upper(), style=f"bold {self.theme.BLUE_SOFT}")
            if reasoning_label:
                secondary.append(f" {self.deco.DOT_MEDIUM} ", style=self.theme.TEXT_DIM)
                secondary.append("Reasoning ", style=self.theme.TEXT_DIM)
                secondary.append(reasoning_label, style=self.theme.AMBER_GLOW)
            if total_tokens is not None:
                secondary.append(f" {self.deco.DOT_MEDIUM} ", style=self.theme.TEXT_DIM)
                secondary.append("Context ", style=self.theme.TEXT_DIM)
                secondary.append(
                    f"{self._format_compact_quantity(total_tokens)}/{self._format_compact_quantity(max_tokens)} ({percentage:.0f}%)",
                    style=token_color,
                )
            if index_status_text:
                secondary.append(f" {self.deco.DOT_MEDIUM} ", style=self.theme.TEXT_DIM)
                secondary.append_text(index_status_text)
            body = Group(top_grid, secondary)

        self._status_line_cache_key = cache_key
        self._status_line_cache_renderable = body
        self._status_line_cache_time = cache_now
        return body

    def _snapshot_stream_input_state(self) -> dict:
        """Return a snapshot of the active streaming-input state."""
        if not self._stream_input_state:
            return {
                "buffer": "",
                "submitted_text": None,
                "interrupt_requested": False,
                "active": False,
                "paused": False,
            }
        return self._stream_input_state.snapshot()

    def _build_stream_input_prompt(self) -> Text:
        """Render the streaming-time interjection prompt as a plain prompt line."""
        snapshot = self._snapshot_stream_input_state()
        buffer_text = str(snapshot.get("buffer", "") or "")
        is_paused = bool(snapshot.get("paused"))
        prompt = Text()
        prompt.append(f"{self.deco.SPARKLE_FILLED} ", style=self.theme.PINK_SOFT)
        prompt.append("Reverie", style=f"bold {self.theme.PURPLE_SOFT}")
        prompt.append(f" {self.deco.CHEVRON_RIGHT} ", style=self.theme.BLUE_SOFT)
        if buffer_text:
            prompt.append(buffer_text, style=f"bold {self.theme.TEXT_PRIMARY}")
        elif is_paused:
            prompt.append("(input paused)", style=self.theme.TEXT_DIM)
        return prompt

    def _get_streaming_footer(self):
        """Compose the live footer shown during streaming output."""
        renderables = []
        try:
            config = self.config_manager.load()
            if config.show_status_line:
                renderables.append(self._get_status_line())
        except Exception:
            pass
        renderables.append(self._build_stream_input_prompt())
        return Group(*renderables)

    def _consume_pending_input_draft(self) -> str:
        """Return and clear any draft captured during streaming."""
        draft = str(self._pending_input_draft or "")
        self._pending_input_draft = ""
        return draft

    def _store_pending_input_draft(self, value: str) -> None:
        """Persist an unsent streaming draft for the next prompt."""
        self._pending_input_draft = str(value or "")

    def _pause_stream_input_capture(self) -> None:
        """Pause background streaming-input capture."""
        if self._stream_input_state:
            self._stream_input_state.pause()

    def _resume_stream_input_capture(self) -> None:
        """Resume background streaming-input capture."""
        if self._stream_input_state:
            self._stream_input_state.resume()

    def _stream_input_capture_loop(self, state: StreamInputState) -> None:
        """Background key-capture loop for streaming-time interjections."""
        try:
            import msvcrt
        except ImportError:
            return

        while True:
            snapshot = state.snapshot()
            if not snapshot.get("active"):
                return
            if snapshot.get("paused"):
                time.sleep(0.025)
                continue
            if not msvcrt.kbhit():
                time.sleep(0.025)
                continue

            try:
                key = msvcrt.getwch()
            except OSError:
                time.sleep(0.025)
                continue

            if key in ("\x00", "\xe0"):
                try:
                    msvcrt.getwch()
                except OSError:
                    pass
                continue
            if key == "\x1b":
                state.request_interrupt()
                _thread.interrupt_main()
                return
            if key in ("\r", "\n"):
                if state.request_submit():
                    _thread.interrupt_main()
                    return
                continue
            if key == "\x08":
                state.backspace()
                continue
            if key == "\x03":
                state.request_interrupt()
                _thread.interrupt_main()
                return
            if key.isprintable():
                state.append(key)

    def _start_stream_input_capture(self) -> None:
        """Start background capture for streaming-time follow-up input."""
        self._stop_stream_input_capture()
        state = StreamInputState(active=True)
        thread = threading.Thread(
            target=self._stream_input_capture_loop,
            args=(state,),
            daemon=True,
            name="reverie-stream-input",
        )
        self._stream_input_state = state
        self._stream_input_thread = thread
        thread.start()

    def _stop_stream_input_capture(self) -> None:
        """Stop background capture for streaming-time follow-up input."""
        state = self._stream_input_state
        thread = self._stream_input_thread
        if state:
            state.stop()
        if thread and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=0.15)
        self._stream_input_thread = None

    def _print_interjected_message(self, message: str) -> None:
        """Echo a submitted follow-up into the transcript before dispatching it."""
        text = str(message or "").strip()
        if not text:
            return
        self._show_activity_event(
            "Input",
            "Queued follow-up submitted",
            status="info",
            detail="Dispatching it as the next user turn.",
        )

    def _show_activity_event(
        self,
        category: str,
        message: str,
        *,
        status: str = "info",
        detail: str = "",
        meta: str = "",
    ) -> None:
        """Render a system/session activity event with the shared timeline style."""
        self.display.show_activity_event(
            category=category,
            message=message,
            status=status,
            detail=detail,
            meta=meta,
        )

    def _handle_agent_ui_event(self, event: Dict[str, Any]) -> None:
        """Receive structured agent events and render them through the display layer."""
        if not isinstance(event, dict):
            return
        self._show_activity_event(
            str(event.get("category", "") or "Activity"),
            str(event.get("message", "") or "").strip(),
            status=str(event.get("status", "") or "info"),
            detail=str(event.get("detail", "") or "").strip(),
            meta=str(event.get("meta", "") or "").strip(),
        )

    def _can_attach_inline_images(self, config: Config) -> tuple[bool, str]:
        """Whether the current model/source can accept inline `@image` attachments."""
        active_source = str(getattr(config, "active_model_source", "standard") or "standard").strip().lower()
        if active_source != "nvidia":
            return False, "Inline @image attachments currently require the NVIDIA source."

        selected = resolve_nvidia_selected_model(normalize_nvidia_config(getattr(config, "nvidia", {})))
        if not selected:
            return False, "No NVIDIA model is currently selected."

        model_name = str(selected.get("display_name") or selected.get("id") or "the current model").strip()
        if str(selected.get("transport", "") or "").strip().lower() != "request":
            return False, f"{model_name} uses the OpenAI SDK path and does not accept inline image input."
        if not bool(selected.get("vision")):
            return False, f"{model_name} is not marked as vision-capable."
        return True, ""

    def _dispatch_user_input(self, user_input: str) -> bool:
        """Route raw user input through commands or message handling."""
        normalized_input = str(user_input or "").strip()
        if not normalized_input:
            return True

        if normalized_input.lower() == "tools":
            return self.command_handler.handle("/tools")

        if normalized_input.startswith('/'):
            return self.command_handler.handle(normalized_input)

        return self._process_message(user_input)

    def main_loop(self) -> None:
        """Main interaction loop"""
        self.input_handler = InputHandler(self.console)
        
        while True:
            try:
                user_input = self.input_handler.interactive_input(
                    "Reverie> ",
                    initial_text=self._consume_pending_input_draft(),
                )
                
                if user_input is None: 
                    break 
                if not user_input.strip(): 
                    continue
                if not self._dispatch_user_input(user_input):
                    break
                
            except KeyboardInterrupt:
                self.console.print(f"\n[{self.theme.TEXT_DIM}]{self.deco.DOT_MEDIUM} Use /exit to quit.[/{self.theme.TEXT_DIM}]")
                continue
            except EOFError:
                break
            except Exception as e:
                self.console.print(f"\n[bold {self.theme.CORAL_VIBRANT}]{self.deco.CROSS_FANCY} Unexpected error: {escape(str(e))}[/bold {self.theme.CORAL_VIBRANT}]")
                # Continue running despite unexpected errors
                continue
        
        if self.agent:
            self.session_manager.update_messages(self.agent.get_history())
        try:
            self.workspace_stats_manager.flush()
        except Exception:
            pass
        self.console.print(f"\n[bold {self.theme.PINK_SOFT}]{self.deco.SPARKLE} Session saved. Goodbye! {self.deco.SPARKLE}[/bold {self.theme.PINK_SOFT}]")
    
    def _process_message(self, message: str) -> bool:
        """Process message with direct streaming output to avoid truncation"""
        if not self.agent:
            return True

        self.current_task_start = time.time()
        config = self.config_manager.load()
        follow_up_message: Optional[str] = None
        draft_message: Optional[str] = None
        interrupted_by_user = False
        response_stream = None
        current_markdown_text = ""
        thinking_content = ""
        response_model_name = getattr(config.active_model, "model_display_name", "Reverie")
        response_provider_label = self._resolve_provider_label(config)
        response_mode = config.mode
        parsed_inline = parse_inline_image_mentions(message, self.project_root)
        inline_attachments = parsed_inline.get("attachments", []) if isinstance(parsed_inline, dict) else []
        inline_warnings = parsed_inline.get("warnings", []) if isinstance(parsed_inline, dict) else []
        clean_message = str(parsed_inline.get("clean_text", message) if isinstance(parsed_inline, dict) else message).strip()
        outbound_message: Any = message
        transcript_message = str(message or "").strip()
        agent_display_text = transcript_message

        for warning in inline_warnings:
            self._show_activity_event(
                "Attachment",
                "Inline image skipped",
                status="warning",
                detail=str(warning),
            )

        if inline_attachments:
            allowed, detail = self._can_attach_inline_images(config)
            if not allowed:
                self._show_activity_event(
                    "Attachment",
                    "Inline images are unavailable for the current model",
                    status="warning",
                    detail=detail,
                )
                return True

            outbound_message = build_user_message_content(clean_message, inline_attachments)
            transcript_message = clean_message or "Attached image input."
            agent_display_text = flatten_multimodal_content_for_display(outbound_message)
            self._show_activity_event(
                "Attachment",
                "Inline image attached",
                status="success",
                detail=f"{len(inline_attachments)} image file(s) added to the LLM context.",
            )

        # The interactive shell already shows the typed prompt in-place, so
        # avoid echoing a second transcript block for every user turn.

        # Get current session ID
        session_id = self.session_manager.current_session.id if self.session_manager.current_session else "default"
        
        # Create project snapshot before processing user question
        try:
            snapshot_info = self.snapshot_manager.create_snapshot(
                description=f"Before question: {transcript_message[:50]}..."
            )
            if snapshot_info:
                if getattr(snapshot_info, "reused", False):
                    self._show_activity_event(
                        "Snapshot",
                        "Workspace snapshot unchanged",
                        status="info",
                        detail="Reused the latest snapshot because the workspace has not changed.",
                        meta=snapshot_info.id,
                    )
                else:
                    self._show_activity_event(
                        "Snapshot",
                        "Workspace snapshot saved",
                        status="success",
                        detail=f"{snapshot_info.file_count} files captured before the next model call.",
                        meta=snapshot_info.id,
                    )
        except Exception as e:
            self._show_activity_event(
                "Snapshot",
                "Snapshot creation failed",
                status="warning",
                detail="The turn will continue without a pre-message snapshot.",
                meta=str(e),
            )
        
        try:
            first_non_tool_chunk = True
            response_header_printed = False
            
            # Thinking content state management
            in_thinking_mode = False
            
            # Create live footer with status + input bar during streaming
            from rich.live import Live
            footer_live = Live(
                self.streaming_footer,
                console=self.console,
                refresh_per_second=6,
                transient=True,
                vertical_overflow="visible",
            )
            footer_live.start()
            self._status_live = footer_live
            self._start_stream_input_capture()

            def ensure_response_header() -> None:
                nonlocal response_header_printed
                if response_header_printed:
                    return
                self.display.show_response_header(
                    model_name=response_model_name,
                    provider_label=response_provider_label,
                    mode=response_mode,
                )
                response_header_printed = True
            
            try:
                self.ensure_context_engine()
                response_stream = self.agent.process_message(
                    outbound_message,
                    stream=config.stream_responses,
                    session_id=session_id,
                    user_display_text=agent_display_text,
                )
                for chunk in response_stream:
                    # Handle thinking markers
                    if chunk == THINKING_START_MARKER:
                        # Flush any pending content before entering thinking mode
                        if current_markdown_text:
                            self._flush_markdown_content(current_markdown_text, final=True)
                            current_markdown_text = ""
                        ensure_response_header()
                        in_thinking_mode = True
                        self.display.show_thinking_banner(response_model_name)
                        continue
                    
                    if chunk == THINKING_END_MARKER:
                        # Flush any pending thinking content and exit thinking mode
                        if thinking_content.strip():
                            self._print_thinking_content(thinking_content)
                            thinking_content = ""
                        in_thinking_mode = False
                        # Add a visual separator after thinking
                        self.console.print()
                        continue
                    
                    # Handle thinking content
                    if in_thinking_mode:
                        thinking_content = self._stream_thinking_fragment(
                            thinking_content,
                            chunk,
                        )
                        continue

                    decoded_event = decode_stream_event(chunk) if chunk.startswith(STREAM_EVENT_MARKER) else None
                    if decoded_event:
                        if current_markdown_text:
                            self._flush_markdown_content(current_markdown_text, final=True)
                            current_markdown_text = ""
                        if thinking_content.strip():
                            self._print_thinking_content(thinking_content)
                            thinking_content = ""
                        in_thinking_mode = False
                        ensure_response_header()
                        if not self.display.show_stream_event(decoded_event):
                            self.console.print(chunk)
                        continue
                    
                    # Check for known tool/system styled markers.
                    # Keep this strict so normal markdown like "[text](url)"
                    # doesn't get sent into Rich markup parsing.
                    stripped_chunk = chunk.lstrip('\n')
                    is_tool_markup = stripped_chunk.startswith(_TOOL_MARKUP_PREFIXES)

                    if is_tool_markup:
                        # Flush pending markdown
                        if current_markdown_text:
                            self._flush_markdown_content(current_markdown_text, final=True)
                            current_markdown_text = ""
                        # Add tool output directly; if markup is malformed, render as plain text.
                        try:
                            self.console.print(Text.from_markup(chunk))
                        except Exception:
                            self.console.print(escape(chunk))
                    else:
                        if first_non_tool_chunk and chunk.strip():
                            ensure_response_header()
                            first_non_tool_chunk = False
                        
                        # Stream complete lines progressively while keeping the tail buffered.
                        flushable_text, current_markdown_text = split_markdown_fragments(current_markdown_text, chunk)
                        if flushable_text:
                            self._flush_markdown_content(flushable_text)
                
                # Final flush - print all accumulated content
                if current_markdown_text.strip():
                    self._flush_markdown_content(current_markdown_text, final=True)
                
                # Flush any remaining thinking content
                if thinking_content.strip():
                    self._print_thinking_content(thinking_content)
            
            finally:
                snapshot = self._snapshot_stream_input_state()
                follow_up_message = str(snapshot.get("submitted_text") or "").strip() or None
                draft_message = str(snapshot.get("buffer") or "").rstrip() or None
                interrupted_by_user = bool(snapshot.get("interrupt_requested"))
                if response_stream and hasattr(response_stream, "close"):
                    try:
                        response_stream.close()
                    except Exception:
                        pass
                self._stop_stream_input_capture()
                self._stream_input_state = None
                footer_live.stop()
                self._status_live = None
                
        except KeyboardInterrupt:
            snapshot = self._snapshot_stream_input_state()
            follow_up_message = str(snapshot.get("submitted_text") or "").strip() or follow_up_message
            draft_message = str(snapshot.get("buffer") or "").rstrip() or draft_message
            interrupted_by_user = bool(snapshot.get("interrupt_requested")) or interrupted_by_user
            if response_stream and hasattr(response_stream, "close"):
                try:
                    response_stream.close()
                except Exception:
                    pass
            if current_markdown_text.strip():
                self._flush_markdown_content(current_markdown_text, final=True)
                current_markdown_text = ""
            if thinking_content.strip():
                self._print_thinking_content(thinking_content)
                thinking_content = ""
            if interrupted_by_user:
                message_text = "Output stopped. Ready for your next instruction."
                if follow_up_message:
                    message_text = "Output stopped. Sending your follow-up now."
                self._show_activity_event(
                    "Session",
                    message_text,
                    status="warning",
                )
            else:
                self._show_activity_event(
                    "Session",
                    "Process interrupted by user",
                    status="info",
                )
        except Exception as e:
            self._show_activity_event(
                "Session",
                "Message processing failed",
                status="error",
                detail="The CLI recovered and stayed interactive.",
                meta=str(e),
            )
            # Don't re-raise the exception to prevent app from stopping
        finally:
            self._stop_stream_input_capture()
            self._stream_input_state = None
            self._status_live = None
            if self.current_task_start:
                elapsed_active = time.time() - self.current_task_start
                self.total_active_time += elapsed_active
                try:
                    self.workspace_stats_manager.record_active_time(elapsed_active)
                    self.total_active_time = self.workspace_stats_manager.get_total_active_seconds()
                except Exception:
                    pass
                self.current_task_start = None
            if self.agent:
                try:
                    self.session_manager.update_messages(self.agent.get_history())
                    current_session = self.session_manager.get_current_session()
                    if current_session and self.memory_indexer:
                        self.memory_indexer.refresh_session(current_session.id)
                        self._sync_workspace_memory_message(current_session)
                        self.agent.set_history(current_session.messages)
                    if current_session:
                        try:
                            self.workspace_stats_manager.update_session_snapshot(
                                current_session.id,
                                session_name=current_session.name,
                                message_count=len(current_session.messages),
                            )
                            self.workspace_stats_manager.flush()
                        except Exception:
                            pass
                except Exception as session_error:
                    self._show_activity_event(
                        "Session",
                        "Failed to save session state",
                        status="warning",
                        detail="The current response completed, but the transcript could not be persisted cleanly.",
                        meta=str(session_error),
                    )

        if follow_up_message:
            self._store_pending_input_draft("")
        elif draft_message:
            self._store_pending_input_draft(draft_message)
        else:
            self._store_pending_input_draft("")
        
        # Display updated status line after processing if enabled
        if config.show_status_line and not follow_up_message:
            self.console.print(self.status_line)
        self.console.print() # Final spacer for prompt

        if follow_up_message:
            self._print_interjected_message(follow_up_message)
            return self._dispatch_user_input(follow_up_message)
        return True

    def _persist_runtime_stats(self) -> None:
        """Persist cumulative runtime metrics for the active workspace."""
        if self._runtime_recorded:
            return
        self._runtime_recorded = True
        try:
            if hasattr(self, "workspace_stats_manager") and self.workspace_stats_manager:
                self.workspace_stats_manager.record_runtime(time.time() - self.start_time, force=True)
                self.workspace_stats_manager.flush()
        except Exception:
            pass

    def _flush_markdown_content(self, content: str, *, final: bool = False) -> None:
        """Render assistant markdown with a shared formatter for lower-latency streaming."""
        text = str(content or "")
        if not text:
            return

        renderable = format_markdown(
            text,
            formatter=self._markdown_formatter,
            max_width=max(int(getattr(self.console, "width", 80) or 80) - 2, 40),
        )
        self.console.print(Padding(renderable, (0, 0, 0, 2)))
    
    def _print_thinking_content(self, content: str) -> None:
        """Helper method to print thinking content with proper formatting"""
        for line in content.strip().split('\n'):
            self._render_thinking_line(line)

    def _render_thinking_line(self, raw_line: str) -> None:
        """Render one cleaned reasoning line without leaking raw markdown markers."""
        subject, description = parse_thinking_line(raw_line)
        if not subject and not description:
            return

        prefix = Text(f"{DECO.LINE_VERTICAL} ", style=self.theme.THINKING_DIM)
        line = Text()
        line.append_text(prefix)

        if subject:
            line.append(subject, style=f"italic bold {self.theme.THINKING_MEDIUM}")
            if description:
                line.append(": ", style=self.theme.TEXT_DIM)
                line.append(description, style=f"italic {self.theme.THINKING_SOFT}")
        else:
            line.append(description, style=f"italic {self.theme.THINKING_SOFT}")

        self.console.print(line)

    def _stream_thinking_fragment(
        self,
        pending: str,
        fragment: str,
    ) -> str:
        """Print only complete reasoning lines and keep the trailing fragment buffered."""
        lines, remainder = split_thinking_fragments(pending, fragment)
        for line in lines:
            self._render_thinking_line(line)
        return remainder

    def _get_index_status_text(self) -> Optional[Text]:
        """Return the terse context-index status shown in the status bar."""
        indexer = getattr(self, "indexer", None)
        if not indexer:
            if getattr(self, "_indexing_in_progress", False):
                return Text("Indexing 0%", style=f"bold {self.theme.AMBER_GLOW}")
            return None

        try:
            status = indexer.get_index_status()
        except Exception:
            if getattr(self, "_indexing_in_progress", False):
                return Text("Indexing 0%", style=f"bold {self.theme.AMBER_GLOW}")
            return None

        label = str(status.get("display_label") or "").strip()
        if not label and getattr(self, "_indexing_in_progress", False):
            label = "Indexing 0%"
        if not label:
            return None

        style = f"bold {self.theme.MINT_VIBRANT}" if status.get("is_finished") else f"bold {self.theme.AMBER_GLOW}"
        return Text(label, style=style)

    def _init_context_engine(self) -> None:
        self._init_context_engine_with_options(announce=True)

    def _init_context_engine_with_options(self, *, announce: bool = False) -> None:
        if self._context_engine_ready and self.indexer and self.retriever:
            return
        cache_dir = self.project_data_dir / 'context_cache'
        if announce:
            self._show_activity_event(
                "Context Engine",
                "Initializing code index and retriever",
                status="working",
                detail="Lazy-loading the core retrieval services for this workspace.",
            )
        self.indexer = CodebaseIndexer(project_root=self.project_root, cache_dir=cache_dir)
        config = self.config_manager.load()
        cached = self.indexer.load_cache()
        if not cached and config.auto_index:
            self._show_activity_event(
                "Context Engine",
                "No warm cache available, building a fresh index.",
                status="working",
                detail="The status bar will show index progress as a percentage and switch to index finished when done.",
            )
            self._run_context_indexing_with_progress()
        self.retriever = ContextRetriever(
            self.indexer.symbol_table,
            self.indexer.dependency_graph,
            self.project_root,
            file_info=self.indexer._file_info,
            git_integration=self.git_integration,
            memory_indexer=self.memory_indexer,
        )
        self._context_engine_ready = True
        self._refresh_command_context()

    def _sync_agent_context_engine(self) -> None:
        """Attach the lazily initialized Context Engine to the active agent and refresh prompt guidance."""
        if not self.agent or not self.indexer or not self.retriever:
            return
        self.retriever.git_integration = self.git_integration
        self.retriever.memory_indexer = self.memory_indexer

        self.agent.set_context_engine(self.retriever, self.indexer, self.git_integration)
        self.agent.tool_executor.update_context('lsp_manager', self.lsp_manager)
        self.agent.tool_executor.update_context('memory_indexer', self.memory_indexer)
        self._refresh_agent_prompt_guidance()

    def _refresh_agent_prompt_guidance(self) -> None:
        """Refresh additional rules/system prompt after lazy services change."""
        if not self.agent:
            return
        config = self.config_manager.load()
        self.agent.config = config
        self.agent.additional_rules = self._build_additional_rules_with_tti(config)
        prompt_phase = "EXECUTION" if getattr(self.agent, "ant_phase", "PLANNING") in {"EXECUTION", "VERIFICATION"} else "PLANNING"
        self.agent.system_prompt = build_system_prompt(
            model_name=self.agent.model_display_name,
            additional_rules=self.agent.additional_rules,
            mode=self.agent.mode,
            ant_phase=prompt_phase,
        )

    def _run_context_indexing_with_progress(self) -> Optional[object]:
        """Run a full context index while streaming live progress to the terminal."""
        if not self.indexer:
            return None

        result_holder: dict[str, object] = {"result": None}
        self._indexing_in_progress = True

        with Progress(
            SpinnerColumn(style=self.theme.PURPLE_SOFT),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(bar_width=None),
            TextColumn("{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
            TimeRemainingColumn(),
            console=self.console,
            transient=True,
        ) as progress:
            task_id = progress.add_task("Indexing", total=100)

            def _progress_callback(snapshot) -> None:
                stage = str(getattr(snapshot, "stage", "") or "").lower()
                percent = float(getattr(snapshot, "display_percent", getattr(snapshot, "percent", 0.0)) or 0.0)
                is_finished = stage == "complete"
                progress.update(
                    task_id,
                    description="index finished" if is_finished else "Indexing",
                    completed=min(max(percent, 0.0), 100.0),
                    total=100,
                )

            try:
                result_holder["result"] = self.indexer.full_index(progress_callback=_progress_callback)
            except Exception as exc:
                self._show_activity_event(
                    "Context Engine",
                    "Indexing failed unexpectedly.",
                    status="error",
                    detail=str(exc),
                )
                result_holder["result"] = None
            finally:
                self._indexing_in_progress = False

        result = result_holder["result"]
        if result is not None:
            self._refresh_command_context()
            self._sync_agent_context_engine()
        return result

    def ensure_context_engine(self, *, announce: bool = False) -> bool:
        """Initialize the Context Engine on demand and synchronize it into the active agent."""
        if self._context_engine_ready and self.indexer and self.retriever:
            return False
        self._init_context_engine_with_options(announce=announce)
        self._sync_agent_context_engine()
        self._refresh_command_context()
        return True

    def ensure_git_integration(self, *, announce: bool = False) -> bool:
        """Initialize git integration on demand."""
        if self._git_integration_ready and self.git_integration is not None:
            return False
        if announce:
            self._show_activity_event(
                "Git",
                "Initializing repository integration",
                status="working",
                detail="Preparing commit and diff metadata on demand.",
            )
        self.git_integration = GitIntegration(self.project_root)
        self._git_integration_ready = True
        if self.retriever:
            self.retriever.git_integration = self.git_integration
        if self.agent:
            self.agent.tool_executor.update_context('git_integration', self.git_integration)
        self._refresh_command_context()
        return True

    def ensure_lsp_manager(self, *, announce: bool = False) -> bool:
        """Initialize LSP discovery on demand."""
        if self._lsp_manager_ready and self.lsp_manager is not None:
            return False
        if announce:
            self._show_activity_event(
                "LSP",
                "Initializing language-service bridge",
                status="working",
                detail="Preparing definitions, symbols, and diagnostics on demand.",
            )
        self.lsp_manager = LSPManager(self.project_root)
        self._lsp_manager_ready = True
        if self.agent:
            self.agent.tool_executor.update_context('lsp_manager', self.lsp_manager)
            self._refresh_agent_prompt_guidance()
        self._refresh_command_context()
        return True

    def _init_agent(self) -> None:
        config = self.config_manager.load()
        self.mcp_runtime.set_project_root(self.project_root)
        scope_changed = self._ensure_runtime_services_for_config(config)
        if normalize_mode(config.mode) == "computer-controller":
            runtime_nvidia = build_nvidia_computer_controller_runtime_model_data(getattr(config, "nvidia", {}))
            if not runtime_nvidia:
                self.console.print(
                    f"\n[{self.theme.CORAL_SOFT}]{self.deco.CROSS} Computer Controller mode needs a NVIDIA API key in config or NVIDIA_API_KEY before it can start.[/{self.theme.CORAL_SOFT}]"
                )
                self.agent = None
                self._refresh_command_context()
                return

            nvidia_cfg = normalize_nvidia_config(getattr(config, "nvidia", {}))
            nvidia_cfg["enabled"] = True
            nvidia_cfg["api_key"] = runtime_nvidia.get("api_key", "")
            nvidia_cfg["selected_model_id"] = str(runtime_nvidia.get("model", nvidia_cfg.get("selected_model_id", "")))
            nvidia_cfg["selected_model_display_name"] = str(
                runtime_nvidia.get("model_display_name", nvidia_cfg.get("selected_model_display_name", ""))
            )
            config.nvidia = normalize_nvidia_config(nvidia_cfg)
            if str(getattr(config, "active_model_source", "standard")).lower() != "nvidia":
                config.active_model_source = "nvidia"
            self.config_manager.save(config)
        model = config.active_model
        if not model:
            self.agent = None
            self._refresh_command_context()
            return

        # Check for missing max_context_tokens
        if model.max_context_tokens is None:
            self.console.print(f"\n[{self.theme.AMBER_GLOW}]{self.deco.DOT_MEDIUM} Context window size not configured for model: {model.model_display_name}[/{self.theme.AMBER_GLOW}]")
            val = Prompt.ask("Enter max context tokens for this model", default="128000")
            try:
                model.max_context_tokens = int(val)
            except ValueError:
                model.max_context_tokens = 128000
            
            # Save back to config
            config.models[config.active_model_index] = model
            self.config_manager.save(config)
            self._show_activity_event(
                "Config",
                "Model context window updated",
                status="success",
                detail=f"Saved max context tokens for {model.model_display_name}.",
            )

        # Preserve existing messages when reinitializing within the same runtime scope.
        existing_messages = []
        if not scope_changed and hasattr(self, 'agent') and self.agent is not None:
            existing_messages = self.agent.messages.copy()

        self.agent = ReverieAgent(
            base_url=model.base_url, api_key=model.api_key, model=model.model,
            model_display_name=model.model_display_name, project_root=self.project_root,
            retriever=self.retriever, indexer=self.indexer, git_integration=self.git_integration,
            additional_rules=self._build_additional_rules_with_tti(config),
            mode=config.mode or "reverie",
            provider=getattr(model, 'provider', 'openai-sdk'),
            thinking_mode=getattr(model, 'thinking_mode', None),
            endpoint=getattr(model, 'endpoint', ''),
            custom_headers=getattr(model, 'custom_headers', {}),
            operation_history=self.operation_history,
            rollback_manager=self.rollback_manager,
            config=config
        )
        
        # Restore messages after agent creation when the runtime scope stayed the same.
        if existing_messages:
            self.agent.messages = existing_messages
            self._show_activity_event(
                "Session",
                "Restored prior transcript into the new agent",
                status="info",
                detail=f"{len(existing_messages)} messages were preserved across reinitialization.",
            )
        
        # Ensure the agent picks up values from the loaded Config (e.g. api_timeout)
        self.agent.config = config
        # Also inject config_manager into tool context for context threshold check
        self.agent.tool_executor.update_context('config_manager', self.config_manager)
        self.agent.tool_executor.update_context('mcp_config_manager', self.mcp_config_manager)
        self.agent.tool_executor.update_context('mcp_runtime', self.mcp_runtime)
        # Inject session_manager for context management tool
        self.agent.tool_executor.update_context('session_manager', self.session_manager)
        self.agent.tool_executor.update_context('project_data_dir', self.project_data_dir)
        self.agent.tool_executor.update_context('memory_indexer', self.memory_indexer)
        self.agent.tool_executor.update_context('workspace_stats_manager', self.workspace_stats_manager)
        self.agent.tool_executor.update_context('ensure_context_engine', self.ensure_context_engine)
        self.agent.tool_executor.update_context('ensure_git_integration', self.ensure_git_integration)
        self.agent.tool_executor.update_context('ensure_lsp_manager', self.ensure_lsp_manager)
        self.agent.tool_executor.update_context('lsp_manager', self.lsp_manager)
        self.agent.tool_executor.update_context('git_integration', self.git_integration)
        # Inject console into tool context for proper input handling (especially on Windows)
        self.agent.tool_executor.update_context('console', self.console)
        # Inject status_live control for user input (will be set during _process_message)
        self._status_live = None
        self.agent.tool_executor.update_context('get_status_live', lambda: self._status_live)
        self.agent.tool_executor.update_context('pause_stream_input_capture', self._pause_stream_input_capture)
        self.agent.tool_executor.update_context('resume_stream_input_capture', self._resume_stream_input_capture)
        self.agent.tool_executor.update_context('ui_event_handler', self._handle_agent_ui_event)
        self._show_activity_event(
            "Agent",
            f"Agent ready with {model.model_display_name}",
            status="success",
            detail=f"Provider: {self._resolve_provider_label(config)}",
        )
        self._refresh_command_context()
        if scope_changed:
            self._init_session()

    def _build_additional_rules_with_tti(self, config: Config) -> str:
        """Append TTI model metadata from config.json into model context."""
        base_rules = (self.rules_manager.get_rules_text() or "").strip()
        normalized_mode = normalize_mode(getattr(config, "mode", "reverie"))

        tti_cfg = config.text_to_image if isinstance(config.text_to_image, dict) else {}
        tti_models = normalize_tti_models(
            tti_cfg.get("models", []),
            legacy_model_paths=tti_cfg.get("model_paths", []),
        )
        default_display_name = resolve_tti_default_display_name(tti_cfg)

        lines = [
            "## TTI Models (from config.json)",
            f"- Tool: `text_to_image`",
            f"- Selection rule: use `model` parameter with configured `display_name` (not raw path).",
            f"- Default model: {default_display_name if default_display_name else '(none)'}",
        ]

        if not tti_models:
            lines.append("- Configured models: (none)")
        else:
            lines.append("- Configured models:")
            for idx, item in enumerate(tti_models):
                intro = item.get("introduction", "")
                intro_text = intro if intro else "(empty)"
                lines.append(
                    f"  [{idx}] display_name={item['display_name']}; path={item['path']}; introduction={intro_text}"
                )

        memory_title = "Computer Controller History" if normalized_mode == "computer-controller" else "Workspace Global Memory"
        memory_label = "computer-control history archive" if normalized_mode == "computer-controller" else "workspace global memory"

        lsp_lines = [
            "## Context Engine Enhancements",
            f"- {memory_title}: {'enabled' if self.memory_indexer else 'disabled'}",
            f"- Optional LSP bridge: {'available' if self.lsp_manager and self.lsp_manager.build_status_report().get('available') else 'on-demand (initialize only when needed)'}",
            "- If LSP data is available, prefer it for diagnostics, definitions, workspace symbols, and reference-oriented navigation.",
            "- After implementation work, run the relevant build/test/verification commands before concluding.",
            "- After tool use, always produce a user-visible textual response instead of stopping at tool output only.",
        ]

        workspace_memory = (
            self.memory_indexer.build_memory_summary(max_fragments=6, max_chars=2200, title=memory_title)
            if self.memory_indexer else ""
        )
        memory_block = (
            f"{workspace_memory}"
            if workspace_memory
            else f"## {memory_title}\n- No prior {memory_label} has been indexed yet."
        )

        atlas_block = ""
        if normalized_mode == "reverie-atlas":
            atlas_block = build_atlas_additional_rules(
                normalize_atlas_mode_config(getattr(config, "atlas_mode", {})),
                workspace_memory_available=bool(str(workspace_memory).strip()),
                lsp_available=bool(
                    self.lsp_manager and self.lsp_manager.build_status_report().get("available")
                ),
            )

        merged_blocks = [
            tti_block
            for tti_block in [
                "\n".join(lines),
                "\n".join(lsp_lines),
                self.mcp_runtime.describe_for_prompt(),
                atlas_block,
                memory_block,
            ]
            if tti_block.strip()
        ]
        merged_text = "\n\n".join(merged_blocks)
        if base_rules:
            return f"{base_rules}\n\n{merged_text}"
        return merged_text

    def _sync_workspace_memory_message(self, session) -> None:
        """Inject a fresh workspace-memory note into the active session."""
        if not session or not self.memory_indexer:
            return

        if self._runtime_scope == "computer-controller":
            try:
                self.memory_indexer.refresh_session(session.id)
            except Exception:
                pass
            return

        try:
            self.memory_indexer.refresh_session(session.id)
        except Exception:
            pass

        memory_text = self.memory_indexer.build_workspace_memory_summary(max_fragments=8, max_chars=3200)
        if not memory_text:
            return

        prefix = "[WORKSPACE GLOBAL MEMORY]"
        memory_message = {
            "role": "system",
            "content": f"{prefix}\n{memory_text}\n[END WORKSPACE GLOBAL MEMORY]",
        }
        session.messages = [
            message
            for message in session.messages
            if not (
                isinstance(message, dict)
                and str(message.get("role", "")).strip().lower() == "system"
                and str(message.get("content", "")).startswith(prefix)
            )
        ]
        session.messages.insert(0, memory_message)
        self.session_manager.update_messages(session.messages)

    def _init_session(self) -> None:
        session, resumed = self.session_manager.ensure_session()
        self._sync_workspace_memory_message(session)
        try:
            self.workspace_stats_manager.update_session_snapshot(
                session.id,
                session_name=session.name,
                message_count=len(session.messages),
            )
            self.workspace_stats_manager.flush()
        except Exception:
            pass

        if self.agent:
            self.agent.set_history(session.messages)

        if resumed:
            detail_text = "Loaded the previous transcript and workspace memory."
            if self._runtime_scope == "computer-controller":
                detail_text = "Loaded the previous computer-control transcript and history index."
            self._show_activity_event(
                "Session",
                f"Resumed session {session.name}",
                status="success",
                detail=detail_text,
                meta=session.id,
            )
        else:
            detail_text = "A fresh session is ready for this workspace."
            if self._runtime_scope == "computer-controller":
                detail_text = "A fresh session is ready in the dedicated computer-control archive."
            self._show_activity_event(
                "Session",
                f"Started session {session.name}",
                status="success",
                detail=detail_text,
                meta=session.id,
            )
        self._refresh_command_context()

    def _get_app_context(self) -> dict:
        return {
            'config_manager': self.config_manager, 'rules_manager': self.rules_manager,
            'mcp_config_manager': self.mcp_config_manager, 'mcp_runtime': self.mcp_runtime,
            'session_manager': self.session_manager, 'indexer': self.indexer,
            'retriever': self.retriever, 'git_integration': self.git_integration,
            'lsp_manager': self.lsp_manager, 'memory_indexer': self.memory_indexer,
            'workspace_stats_manager': self.workspace_stats_manager,
            'project_data_dir': self.project_data_dir,
            'agent': self.agent, 'start_time': self.start_time, 
            'total_active_time': self.total_active_time,
            'current_task_start': self.current_task_start,
            'project_root': self.project_root,
            'reinit_agent': self._init_agent,
            'refresh_agent_prompt_guidance': self._refresh_agent_prompt_guidance,
            'ensure_context_engine': self.ensure_context_engine,
            'run_full_index': self._run_context_indexing_with_progress,
            'ensure_git_integration': self.ensure_git_integration,
            'ensure_lsp_manager': self.ensure_lsp_manager,
            'clean_workspace_state': self.clean_workspace_state,
            'operation_history': self.operation_history,
            'rollback_manager': self.rollback_manager
        }

    def run_setup_wizard(self) -> None:
        """Run the first-time setup wizard with dreamy styling"""
        self.console.print()
        self.console.print(Panel(
            f"[bold {self.theme.PINK_SOFT}]{self.deco.SPARKLE} Welcome to Reverie {self.deco.SPARKLE}[/bold {self.theme.PINK_SOFT}]\n\n"
            f"[{self.theme.TEXT_SECONDARY}]Let's set up your first model connection.[/{self.theme.TEXT_SECONDARY}]",
            border_style=self.theme.BORDER_PRIMARY,
            box=box.ROUNDED,
            padding=(1, 2)
        ))
        self.console.print()
        
        try:
            base_url = Prompt.ask(
                f"[{self.theme.BLUE_SOFT}]{self.deco.CHEVRON_RIGHT}[/{self.theme.BLUE_SOFT}] API Base URL",
                default="https://api.openai.com/v1"
            )
            
            api_key = Prompt.ask(
                f"[{self.theme.BLUE_SOFT}]{self.deco.CHEVRON_RIGHT}[/{self.theme.BLUE_SOFT}] API Key",
                password=True
            )
            
            model_name = Prompt.ask(
                f"[{self.theme.BLUE_SOFT}]{self.deco.CHEVRON_RIGHT}[/{self.theme.BLUE_SOFT}] Model Identifier",
                default="gpt-4"
            )
            
            display_name = Prompt.ask(
                f"[{self.theme.BLUE_SOFT}]{self.deco.CHEVRON_RIGHT}[/{self.theme.BLUE_SOFT}] Display Name",
                default=model_name
            )
            
            max_tokens = Prompt.ask(
                f"[{self.theme.BLUE_SOFT}]{self.deco.CHEVRON_RIGHT}[/{self.theme.BLUE_SOFT}] Max Context Tokens",
                default="128000"
            )
            
            try:
                max_tokens_int = int(max_tokens)
            except ValueError:
                max_tokens_int = 128000
            
            model_config = ModelConfig(
                model=model_name,
                model_display_name=display_name,
                base_url=base_url,
                api_key=api_key,
                max_context_tokens=max_tokens_int
            )
            
            config = Config(
                models=[model_config],
                active_model_index=0,
                mode="reverie"
            )
            
            self.config_manager.save(config)
            
            self.console.print()
            self.console.print(f"[{self.theme.MINT_VIBRANT}]{self.deco.CHECK_FANCY}[/{self.theme.MINT_VIBRANT}] [{self.theme.MINT_SOFT}]Setup complete! Starting Reverie...[/{self.theme.MINT_SOFT}]")
            self.console.print()
            
        except KeyboardInterrupt:
            self.console.print(f"\n[{self.theme.AMBER_GLOW}]{self.deco.DOT_MEDIUM} Setup cancelled.[/{self.theme.AMBER_GLOW}]")
            raise
        except EOFError:
            self.console.print(f"\n[{self.theme.AMBER_GLOW}]{self.deco.DOT_MEDIUM} Setup aborted because no interactive input stream is available.[/{self.theme.AMBER_GLOW}]")
            raise KeyboardInterrupt
