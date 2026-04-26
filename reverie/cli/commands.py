"""
Command Handler - Process CLI commands with Dreamscape Theme

Handles all commands starting with / with dreamy pink-purple-blue aesthetics
"""

from typing import Optional, Callable, Dict, Any, List
from pathlib import Path
import json
import re
import shlex
import time

from rich.console import Console, Group
from rich.table import Table
from rich.prompt import Prompt, Confirm
from rich.panel import Panel
from rich.syntax import Syntax
from rich.text import Text
from rich.align import Align
from rich.columns import Columns
from rich.padding import Padding
from rich import box
from rich.markup import escape

from .help_catalog import HELP_SECTION_ORDER, HELP_TOPICS, normalize_help_topic
from .markdown_formatter import MarkdownFormatter, format_markdown
from .theme import THEME, DECO, DREAM
from ..harness import build_harness_capability_report
from ..modes import (
    get_mode_description,
    get_mode_display_name,
    list_modes,
    normalize_mode,
)
from ..config import normalize_thinking_output_style, normalize_tool_output_style
from ..tools.tool_catalog import ToolCatalogTool


class CommandHandler:
    """Handles CLI commands (starting with /) with Dreamscape styling"""
    
    def __init__(
        self,
        console: Console,
        app_context: Dict[str, Any]
    ):
        self.console = console
        self.app = app_context
        self.theme = THEME
        self.deco = DECO
        self._markdown_formatter = MarkdownFormatter(console=self.console)
        
        # Command registry
        self.commands = {
            'help': self.cmd_help,
            'model': self.cmd_model,
            'subagent': self.cmd_subagent,
            'subagents': self.cmd_subagent,
            'geminicli': self.cmd_geminicli,
            'codex': self.cmd_codex,
            'nvidia': self.cmd_nvidia,
            'modelscope': self.cmd_modelscope,
            'mode': self.cmd_mode,
            'status': self.cmd_status,
            'doctor': self.cmd_doctor,
            'harness': self.cmd_doctor,
            'search': self.cmd_search,
            'sessions': self.cmd_sessions,
            'history': self.cmd_history,
            'total': self.cmd_total,
            'clear': self.cmd_clear,
            'clean': self.cmd_clean,
            'index': self.cmd_index,
            'tools': self.cmd_tools,
            'skills': self.cmd_skills,
            'plugins': self.cmd_plugins,
            'mcp': self.cmd_mcp,
            'setting': self.cmd_setting,
            'settings': self.cmd_setting,
            'rules': self.cmd_rules,
            'workspace': self.cmd_workspace,
            'tti': self.cmd_tti,
            'exit': self.cmd_exit,
            'quit': self.cmd_exit,
            'rollback': self.cmd_rollback,
            'undo': self.cmd_undo,
            'redo': self.cmd_redo,
            'checkpoints': self.cmd_checkpoints,
            'operations': self.cmd_operations,
            'gdd': self.cmd_gdd,
            'assets': self.cmd_assets,
            'blueprint': self.cmd_blueprint,
            'bp': self.cmd_blueprint,
            'scaffold': self.cmd_scaffold,
            'engine': self.cmd_engine,
            'modeling': self.cmd_modeling,
            'blender': self.cmd_blender,
            'playtest': self.cmd_playtest,
            'pt': self.cmd_playtest,
            'CE': self.cmd_context_engine,  # Context Engine management (case-sensitive)
        }
        self._help_topic_items_cache: tuple[Dict[str, object], ...] = tuple()
        self._help_preview_cache: Dict[str, str] = {}
        self._help_search_cache: Dict[str, str] = {}
        self._prime_help_catalog_cache()

    def _console_width(self) -> int:
        """Best-effort terminal width with a safe minimum."""
        try:
            width = int(getattr(self.console.size, "width", 0) or self.console.width or 0)
        except Exception:
            width = 0
        return max(width, 60)

    def _console_height(self) -> int:
        """Best-effort terminal height with a safe minimum."""
        try:
            height = int(getattr(self.console.size, "height", 0) or 0)
        except Exception:
            height = 0
        return max(height, 20)

    def _console_size(self) -> tuple[int, int]:
        """Return the current terminal width/height tuple."""
        return (self._console_width(), self._console_height())

    def _is_compact(self, cutoff: int = 108) -> bool:
        """Whether the current terminal should prefer denser layouts."""
        return self._console_width() < cutoff

    def _truncate_middle(self, value: Any, max_length: int) -> str:
        """Trim long values by preserving both ends."""
        text = str(value or "").strip()
        if len(text) <= max_length:
            return text
        if max_length <= 5:
            return text[:max_length]
        left = max(2, (max_length - 3) // 2)
        right = max(2, max_length - 3 - left)
        return f"{text[:left]}...{text[-right:]}"

    def _build_metric_panel(
        self,
        label: str,
        value: Any,
        *,
        accent: str,
        detail: str = "",
    ) -> Panel:
        """Build a compact stat card for dashboard-like command pages."""
        body: List[Any] = [
            Text(str(value), style=f"bold {accent}"),
            Text(str(label), style=self.theme.TEXT_DIM),
        ]
        if detail:
            body.append(Text(str(detail), style=self.theme.TEXT_SECONDARY))
        return Panel(
            Group(*body),
            border_style=accent,
            box=box.ROUNDED,
            padding=(0, 1),
        )

    def _build_roster_text(
        self,
        labels: List[str],
        *,
        accent: Optional[str] = None,
        limit: int = 12,
    ) -> Text:
        """Render a wrapped badge-like label line."""
        color = accent or self.theme.BLUE_SOFT
        text = Text()
        visible = [str(label).strip() for label in labels if str(label).strip()][:limit]
        for index, label in enumerate(visible):
            if index:
                text.append(f" {self.deco.DOT_MEDIUM} ", style=self.theme.TEXT_DIM)
            text.append(label, style=f"bold {color}")
        remaining = len([label for label in labels if str(label).strip()]) - len(visible)
        if remaining > 0:
            if visible:
                text.append(f" {self.deco.DOT_MEDIUM} ", style=self.theme.TEXT_DIM)
            text.append(f"+{remaining} more", style=self.theme.TEXT_SECONDARY)
        if not text.plain:
            text.append("(none)", style=self.theme.TEXT_DIM)
        return text

    def _resolve_activity_style(self, status: str) -> tuple[str, str, str, str]:
        """Resolve colors and labels for lightweight command activity blocks."""
        styles = {
            "info": (self.theme.BLUE_SOFT, "info", self.theme.TEXT_PRIMARY, self.theme.TEXT_DIM),
            "success": (self.theme.MINT_VIBRANT, "done", self.theme.TEXT_PRIMARY, self.theme.TEXT_DIM),
            "warning": (self.theme.AMBER_GLOW, "warning", self.theme.PEACH_SOFT, self.theme.TEXT_DIM),
            "error": (self.theme.CORAL_VIBRANT, "failed", self.theme.CORAL_SOFT, self.theme.TEXT_DIM),
            "working": (self.theme.PURPLE_SOFT, "running", self.theme.TEXT_PRIMARY, self.theme.TEXT_DIM),
        }
        return styles.get(str(status or "info").strip().lower(), styles["info"])

    def _show_activity_event(
        self,
        category: str,
        message: str,
        *,
        status: str = "info",
        detail: str = "",
        meta: str = "",
        blank_before: bool = False,
        blank_after: bool = False,
    ) -> None:
        """Render a compact Codex-like timeline event inside command pages."""
        if blank_before:
            self.console.print()

        accent, status_label, message_color, detail_color = self._resolve_activity_style(status)
        title = Text()
        title.append("│ ", style=accent)
        title.append(str(category or "Activity"), style=f"bold {accent}")
        title.append("  |  ", style=self.theme.TEXT_DIM)
        title.append(status_label, style=self.theme.TEXT_DIM)

        renderables: List[Any] = [title]
        message_text = str(message or "").strip()
        detail_text = str(detail or "").strip()
        meta_text = str(meta or "").strip()

        body_parts: List[Any] = []
        if message_text:
            body_parts.append(Text(message_text, style=f"bold {message_color}"))
        if detail_text:
            body_parts.append(Text(detail_text, style=detail_color))
        if body_parts:
            renderables.append(Padding(Group(*body_parts), (0, 0, 0, 3)))

        if meta_text:
            footer = Text()
            footer.append("└ ", style=accent)
            footer.append(meta_text, style=self.theme.TEXT_DIM)
            renderables.append(footer)

        self.console.print(Group(*renderables))

        if blank_after:
            self.console.print()

    def _show_command_panel(
        self,
        title: str,
        *,
        subtitle: str = "",
        accent: Optional[str] = None,
        meta: str = "",
    ) -> None:
        """Render a shared section banner for command pages."""
        accent_color = accent or self.theme.BORDER_PRIMARY
        compact = self._is_compact(104)

        eyebrow = Text()
        eyebrow.append("Command Center", style=self.theme.TEXT_DIM)
        if meta:
            eyebrow.append(f"  {self.deco.DOT_MEDIUM}  ", style=self.theme.TEXT_DIM)
            eyebrow.append(self._truncate_middle(meta, 64 if compact else 92), style=self.theme.TEXT_SECONDARY)

        title_text = Text()
        title_text.append(f"{self.deco.DIAMOND_FILLED} ", style=accent_color)
        title_text.append(str(title), style=f"bold {accent_color}")

        body: List[Any] = [eyebrow, title_text]
        if subtitle:
            body.append(Text(subtitle, style=self.theme.TEXT_SECONDARY))
        divider = Text("─" * min(58 if compact else 78, max(self._console_width() - 14, 12)), style=self.theme.BORDER_SUBTLE)
        body.append(divider)

        self.console.print()
        self.console.print(
            Panel(
                Group(*body),
                border_style=accent_color,
                box=box.ROUNDED,
                padding=(1 if compact else 0, 1 if compact else 2),
            )
        )
        self.console.print()

    def _build_key_value_table(self, rows: List[tuple[str, Any]], *, value_style: Optional[str] = None) -> Table:
        """Build a simple two-column detail table."""
        compact = self._is_compact(104)
        table = Table(
            show_header=False,
            box=box.SIMPLE_HEAVY if not compact else box.SIMPLE,
            padding=(0, 1 if compact else 2),
            pad_edge=False,
            expand=True,
        )
        table.add_column("Label", style=f"bold {self.theme.BLUE_SOFT}", width=18 if compact else 24)
        table.add_column("Value", style=value_style or self.theme.TEXT_PRIMARY, ratio=1)
        for label, value in rows:
            table.add_row(str(label), str(value))
        return table

    def _build_skill_overview_panels(
        self,
        summary: Dict[str, Any],
        rows: List[Dict[str, str]],
        error_rows: List[Dict[str, str]],
    ) -> Any:
        """Build the top summary row for `/skills`."""
        panels = [
            self._build_metric_panel(
                "Detected",
                summary.get("skill_count", 0),
                accent=self.theme.MINT_VIBRANT,
                detail="valid SKILL.md directories",
            ),
            self._build_metric_panel(
                "Invalid",
                summary.get("error_count", 0),
                accent=self.theme.AMBER_GLOW if error_rows else self.theme.BLUE_SOFT,
                detail="needs cleanup before loading",
            ),
            self._build_metric_panel(
                "Roots",
                len(summary.get("root_paths", []) or []),
                accent=self.theme.PURPLE_SOFT,
                detail="scan targets under .reverie",
            ),
        ]
        return Columns(panels, equal=True, expand=True)

    def _build_skill_table(self, rows: List[Dict[str, str]]) -> Table:
        """Build a denser, easier-to-scan skill table."""
        compact = self._is_compact(118)
        table = Table(
            title=f"[bold {self.theme.PINK_SOFT}]{self.deco.CRYSTAL} Detected Skills[/bold {self.theme.PINK_SOFT}]",
            box=box.SIMPLE_HEAVY if compact else box.ROUNDED,
            border_style=self.theme.BORDER_PRIMARY,
            header_style=f"bold {self.theme.TEXT_SECONDARY}",
            expand=True,
            show_lines=not compact,
            pad_edge=False,
        )
        table.add_column("Skill", width=26 if compact else 30)
        table.add_column("Description", ratio=3, min_width=26)
        table.add_column("Path", width=26 if compact else 40, no_wrap=True)

        for row in rows:
            scope = str(row.get("scope", "")).strip()
            root = str(row.get("root", "")).strip()

            skill_cell = Group(
                Text(str(row.get("name", "")), style=f"bold {self.theme.BLUE_GLOW}"),
                Text(f"{scope} {self.deco.DOT_MEDIUM} {root}", style=self.theme.TEXT_DIM),
            )
            description_cell = Text(str(row.get("description", "")), style=self.theme.TEXT_PRIMARY)
            path_cell = Text(
                self._truncate_middle(row.get("path", ""), 40 if compact else 56),
                style=self.theme.TEXT_DIM,
                overflow="ellipsis",
                no_wrap=True,
            )
            table.add_row(skill_cell, description_cell, path_cell)
        return table

    def _build_invalid_skill_table(self, error_rows: List[Dict[str, str]]) -> Table:
        """Build the invalid-skill diagnostics table."""
        compact = self._is_compact(118)
        table = Table(
            title=f"[bold {self.theme.AMBER_GLOW}]{self.deco.CRYSTAL} Invalid Skills[/bold {self.theme.AMBER_GLOW}]",
            box=box.SIMPLE_HEAVY if compact else box.ROUNDED,
            border_style=self.theme.AMBER_GLOW,
            header_style=f"bold {self.theme.TEXT_SECONDARY}",
            expand=True,
            show_lines=not compact,
            pad_edge=False,
        )
        table.add_column("Where", width=24 if compact else 28)
        table.add_column("Issue", ratio=2, min_width=22)
        table.add_column("Path", width=26 if compact else 40, no_wrap=True)

        for row in error_rows:
            where_cell = Group(
                Text(str(row.get("scope", "")), style=f"bold {self.theme.PEACH_SOFT}"),
                Text(str(row.get("root", "")), style=self.theme.TEXT_DIM),
            )
            issue_cell = Text(str(row.get("message", "")), style=self.theme.CORAL_SOFT)
            path_cell = Text(
                self._truncate_middle(row.get("path", ""), 40 if compact else 56),
                style=self.theme.TEXT_DIM,
                overflow="ellipsis",
                no_wrap=True,
            )
            table.add_row(where_cell, issue_cell, path_cell)
        return table

    def _print_skills_status_view(
        self,
        summary: Dict[str, Any],
        rows: List[Dict[str, str]],
        error_rows: List[Dict[str, str]],
    ) -> None:
        """Print the non-interactive skill overview page."""
        self._show_command_panel(
            "Skills",
            subtitle="Codex-style `SKILL.md` instructions discovered from the application `.reverie` skill roots.",
            accent=self.theme.BLUE_SOFT,
        )

        self.console.print(self._build_skill_overview_panels(summary, rows, error_rows))
        self.console.print()

        compact = self._is_compact(124)
        roster_panel = Panel(
            Group(
                Text("Available skill names", style=self.theme.TEXT_DIM),
                self._build_roster_text([row.get("name", "") for row in rows], accent=self.theme.BLUE_GLOW),
            ),
            title=f"[bold {self.theme.BLUE_SOFT}]{self.deco.DIAMOND} Roster[/bold {self.theme.BLUE_SOFT}]",
            border_style=self.theme.BORDER_SUBTLE,
            box=box.ROUNDED,
            padding=(0, 1),
        )
        roots_panel = Panel(
            Group(
                *[
                    Text(self._truncate_middle(path, 58 if compact else 92), style=self.theme.TEXT_SECONDARY)
                    for path in (summary.get("root_paths", []) or [])
                ]
                or [Text("(none configured)", style=self.theme.TEXT_DIM)]
            ),
            title=f"[bold {self.theme.PURPLE_SOFT}]{self.deco.DIAMOND} Scan Roots[/bold {self.theme.PURPLE_SOFT}]",
            border_style=self.theme.BORDER_SUBTLE,
            box=box.ROUNDED,
            padding=(0, 1),
        )
        shortcuts_panel = Panel(
            Text.from_markup(
                f"[bold {self.theme.BLUE_SOFT}]/skills inspect <name>[/bold {self.theme.BLUE_SOFT}] preview one skill\n"
                f"[bold {self.theme.BLUE_SOFT}]/skills path[/bold {self.theme.BLUE_SOFT}] show scan directories\n"
                f"[bold {self.theme.BLUE_SOFT}]/skills rescan[/bold {self.theme.BLUE_SOFT}] refresh prompt guidance"
            ),
            title=f"[bold {self.theme.PINK_SOFT}]{self.deco.DIAMOND} Shortcuts[/bold {self.theme.PINK_SOFT}]",
            border_style=self.theme.BORDER_SUBTLE,
            box=box.ROUNDED,
            padding=(0, 1),
        )

        if compact:
            self.console.print(Group(roster_panel, roots_panel, shortcuts_panel))
        else:
            right_stack = Group(roots_panel, shortcuts_panel)
            self.console.print(Columns([roster_panel, right_stack], expand=True, equal=False))
        self.console.print()

        if not rows:
            self.console.print(
                f"[{self.theme.TEXT_DIM}]{self.deco.DOT_MEDIUM} No valid `SKILL.md` files are currently detected.[/{self.theme.TEXT_DIM}]"
            )
        else:
            self.console.print(self._build_skill_table(rows))

        if error_rows:
            self.console.print()
            self.console.print(self._build_invalid_skill_table(error_rows))

        self.console.print()

    def _build_skill_browser_search_document(self, record: Any) -> str:
        """Build a search document for one skill record."""
        metadata = getattr(record, "metadata", {}) or {}
        metadata_parts: List[str] = []
        for key, value in metadata.items():
            if isinstance(value, dict):
                metadata_parts.extend(str(inner) for inner in value.values() if inner not in (None, ""))
            elif isinstance(value, list):
                metadata_parts.extend(str(inner) for inner in value if inner not in (None, ""))
            elif value not in (None, ""):
                metadata_parts.append(str(value))
            metadata_parts.append(str(key))
        parts = [
            getattr(record, "name", ""),
            getattr(record, "description", ""),
            getattr(record, "scope_label", ""),
            getattr(record, "root_label", ""),
            getattr(record, "display_path", ""),
            getattr(record, "body", ""),
            " ".join(metadata_parts),
        ]
        return " ".join(str(part).lower() for part in parts if str(part).strip())

    def _filter_skill_records(self, records: List[Any], query: str) -> List[Any]:
        """Filter skills by name, description, path, root, and body content."""
        raw_query = str(query or "").strip().lower()
        if not raw_query:
            return list(records)

        terms = [term for term in raw_query.split() if term]
        filtered: List[Any] = []
        for record in records:
            haystack = self._build_skill_browser_search_document(record)
            if all(term in haystack for term in terms):
                filtered.append(record)
        return filtered

    def _skill_browser_visible_count(self) -> int:
        """Choose a stable visible-row count for the skill browser list."""
        width = self._console_width()
        reserve = 18 if width >= 140 else 20 if width >= 110 else 22
        return max(5, min(9, self._console_height() - reserve))

    def _build_skill_browser_summary_panel(
        self,
        records: List[Any],
        filtered_records: List[Any],
        selected_record: Any,
        search_query: str,
        is_searching: bool,
        invalid_count: int,
        root_count: int,
    ) -> Panel:
        """Build the top summary panel for the interactive skills browser."""
        name = str(getattr(selected_record, "name", "") or "").strip()
        summary = str(getattr(selected_record, "summary", "") or getattr(selected_record, "description", "") or "").strip()
        scope = str(getattr(selected_record, "scope_label", "") or "").strip()
        root = str(getattr(selected_record, "root_label", "") or "").strip()
        compact = self._console_width() < 110
        count_text = f"{len(filtered_records)}/{len(records)} skills" if len(filtered_records) != len(records) else f"{len(records)} skills"
        if invalid_count:
            count_text = f"{count_text} · {invalid_count} invalid"
        if root_count:
            count_text = f"{count_text} · {root_count} roots"

        title_grid = Table.grid(expand=True)
        title_grid.add_column(ratio=1)
        title_grid.add_column(justify="right", no_wrap=True)
        title_grid.add_row(
            Text.assemble(
                (f"{self.deco.SPARKLE} ", self.theme.PINK_SOFT),
                ("Skill Browser", f"bold {self.theme.PINK_SOFT}"),
            ),
            Text(count_text, style=self.theme.TEXT_DIM),
        )

        search_display = search_query + ("_" if is_searching else "")
        body_lines = [
            f"[{self.theme.TEXT_DIM}]Focused:[/{self.theme.TEXT_DIM}] [bold {self.theme.BLUE_SOFT}]{escape(name)}[/bold {self.theme.BLUE_SOFT}] [{self.theme.TEXT_DIM}]· {escape(scope)} · {escape(root)}[/{self.theme.TEXT_DIM}]",
        ]
        if summary:
            body_lines.append(
                f"[{self.theme.TEXT_PRIMARY}]{escape(self._truncate_middle(summary, 120 if compact else 180))}[/{self.theme.TEXT_PRIMARY}]"
            )
        if search_query or is_searching:
            body_lines.append(
                f"[bold {self.theme.PURPLE_SOFT}]{self.deco.SEARCH} Filter[/bold {self.theme.PURPLE_SOFT}] "
                f"[{self.theme.TEXT_PRIMARY}]{escape(search_display)}[/{self.theme.TEXT_PRIMARY}]"
            )
        else:
            body_lines.append(
                f"[{self.theme.TEXT_DIM}]Use ↑↓ / j k to browse, only a small window of skills is shown at once, and Enter or Esc keeps the focused skill page in the transcript.[/{self.theme.TEXT_DIM}]"
            )

        return Panel(
            Group(title_grid, Text.from_markup("\n".join(body_lines))),
            border_style=self.theme.BORDER_PRIMARY,
            padding=(1, 2),
            box=box.ROUNDED,
        )

    def _build_skill_browser_list_panel(
        self,
        filtered_records: List[Any],
        selected_idx: int,
        scroll_offset: int,
        max_visible: int,
    ) -> Panel:
        """Build the skill list panel for the interactive browser."""
        if not filtered_records:
            return Panel(
                Text.from_markup(
                    f"[{self.theme.TEXT_DIM}]No matching skills. Refine the filter or press Esc to keep the previously focused skill page.[/{self.theme.TEXT_DIM}]"
                ),
                title=f"[bold {self.theme.BLUE_SOFT}]{self.deco.DIAMOND} Skills[/bold {self.theme.BLUE_SOFT}]",
                border_style=self.theme.BORDER_SUBTLE,
                padding=(1, 2),
                box=box.ROUNDED,
            )

        table = Table(
            box=box.SIMPLE_HEAVY,
            border_style=self.theme.BORDER_SUBTLE,
            expand=True,
            show_header=True,
            pad_edge=False,
            show_lines=False,
        )
        table.add_column("", width=2, no_wrap=True)
        table.add_column("#", style=self.theme.TEXT_DIM, width=4, justify="right", no_wrap=True)
        table.add_column("Skill", width=28, no_wrap=True)
        table.add_column("Scope", width=10, no_wrap=True)
        table.add_column("Root", width=18, no_wrap=True)
        table.add_column("Summary", style=self.theme.TEXT_SECONDARY, ratio=1)

        end_idx = min(scroll_offset + max_visible, len(filtered_records))
        visible_records = filtered_records[scroll_offset:end_idx]
        for row_index, record in enumerate(visible_records):
            actual_idx = scroll_offset + row_index
            is_selected = actual_idx == selected_idx
            indicator = Text("›" if is_selected else "", style=f"bold {self.theme.PINK_SOFT}")
            skill_style = f"bold {self.theme.TEXT_PRIMARY} on {self.theme.PURPLE_DEEP}" if is_selected else f"bold {self.theme.BLUE_SOFT}"
            meta_style = self.theme.TEXT_PRIMARY if is_selected else self.theme.TEXT_DIM
            preview_style = self.theme.TEXT_PRIMARY if is_selected else self.theme.TEXT_SECONDARY
            table.add_row(
                indicator,
                Text(str(actual_idx + 1), style=self.theme.TEXT_DIM),
                Text(self._truncate_middle(str(getattr(record, "name", "") or "").strip(), 26), style=skill_style, overflow="ellipsis", no_wrap=True),
                Text(str(getattr(record, "scope_label", "") or "").strip(), style=meta_style, overflow="ellipsis", no_wrap=True),
                Text(str(getattr(record, "root_label", "") or "").strip(), style=meta_style, overflow="ellipsis", no_wrap=True),
                Text(
                    self._truncate_middle(str(getattr(record, "summary", "") or "").strip(), 72 if self._console_width() >= 130 else 48),
                    style=preview_style,
                    overflow="ellipsis",
                    no_wrap=True,
                ),
            )

        visible_range = (
            f"{scroll_offset + 1}-{end_idx} / {len(filtered_records)}"
            if visible_records
            else f"0 / {len(filtered_records)}"
        )
        return Panel(
            table,
            title=f"[bold {self.theme.BLUE_SOFT}]{self.deco.DIAMOND} Skills[/bold {self.theme.BLUE_SOFT}]",
            subtitle=f"[{self.theme.TEXT_DIM}]Visible window: {visible_range}  {self.deco.DOT_MEDIUM}  Scroll down to reveal more[/{self.theme.TEXT_DIM}]",
            border_style=self.theme.BORDER_SUBTLE,
            padding=(0, 1),
            box=box.ROUNDED,
        )

    def _build_skill_browser_detail_panel(self, record: Any, *, compact: bool = False) -> Panel:
        """Build the detail side for the interactive skills browser."""
        body_text = str(getattr(record, "body", "") or "").strip()
        excerpt_source = [line.strip() for line in body_text.splitlines() if line.strip()]
        excerpt_lines = excerpt_source[:4]
        overview = Table(show_header=False, box=box.SIMPLE, pad_edge=False, expand=True)
        overview.add_column(style=self.theme.TEXT_DIM, width=9)
        overview.add_column(style=self.theme.TEXT_PRIMARY, ratio=1)
        overview.add_row("Scope", str(getattr(record, "scope_label", "") or ""))
        overview.add_row("Root", str(getattr(record, "root_label", "") or ""))
        overview.add_row("Path", self._truncate_middle(getattr(record, "display_path", ""), 68 if compact else 112))

        content: List[Any] = [
            Text(str(getattr(record, "name", "") or ""), style=f"bold {self.theme.PURPLE_SOFT}"),
            Text(str(getattr(record, "description", "") or ""), style=self.theme.TEXT_SECONDARY),
            overview,
        ]
        if excerpt_lines:
            content.append(Text("Instruction excerpt", style=self.theme.TEXT_DIM))
            for line in excerpt_lines:
                content.append(Text(self._truncate_middle(line, 120 if compact else 180), style=self.theme.TEXT_PRIMARY))
        content.append(
            Text("Press Enter or Esc to keep the full skill page in the transcript.", style=self.theme.TEXT_DIM)
        )

        return Panel(
            Group(*content),
            title=f"[bold {self.theme.PURPLE_SOFT}]{self.deco.DIAMOND} Focused Skill[/bold {self.theme.PURPLE_SOFT}]",
            border_style=self.theme.BORDER_SUBTLE,
            padding=(0, 1),
            box=box.ROUNDED,
        )

    def _build_skill_browser_footer_panel(
        self,
        filtered_count: int,
        search_query: str,
        is_searching: bool,
    ) -> Panel:
        """Build the navigation footer for the interactive skills browser."""
        footer_text = Text()
        footer_text.append("Navigate ", style=self.theme.TEXT_DIM)
        footer_text.append("↑↓ / j k", style=self.theme.BLUE_SOFT)
        footer_text.append("  Page ", style=self.theme.TEXT_DIM)
        footer_text.append("PgUp/PgDn", style=self.theme.BLUE_SOFT)
        footer_text.append("  Keep page ", style=self.theme.TEXT_DIM)
        footer_text.append("Enter / Esc", style=self.theme.BLUE_SOFT)
        footer_text.append("  Filter ", style=self.theme.TEXT_DIM)
        footer_text.append("/", style=self.theme.BLUE_SOFT)
        footer_text.append("  Edit ", style=self.theme.TEXT_DIM)
        footer_text.append("Backspace", style=self.theme.BLUE_SOFT)
        footer_text.append("  Jump ", style=self.theme.TEXT_DIM)
        footer_text.append("Home/End", style=self.theme.BLUE_SOFT)

        status_text = "Typing filter" if is_searching else ("Filter active" if search_query else "Live browser")
        status_color = self.theme.PURPLE_SOFT if (is_searching or search_query) else self.theme.TEXT_DIM

        footer_grid = Table.grid(expand=True)
        footer_grid.add_column(ratio=1)
        footer_grid.add_column(justify="right", no_wrap=True)
        footer_grid.add_row(
            footer_text,
            Text(f"{filtered_count} visible · {status_text}", style=status_color),
        )

        return Panel(
            footer_grid,
            border_style=self.theme.BORDER_SUBTLE,
            padding=(0, 1),
            box=box.ROUNDED,
        )

    def _render_skill_browser_ui(
        self,
        records: List[Any],
        filtered_records: List[Any],
        selected_idx: int,
        scroll_offset: int,
        max_visible: int,
        selected_record: Any,
        search_query: str,
        is_searching: bool,
        invalid_count: int,
        root_count: int,
    ) -> Group:
        """Compose the full interactive skills browser layout."""
        summary_panel = self._build_skill_browser_summary_panel(
            records,
            filtered_records,
            selected_record,
            search_query,
            is_searching,
            invalid_count,
            root_count,
        )
        list_panel = self._build_skill_browser_list_panel(filtered_records, selected_idx, scroll_offset, max_visible)
        width = self._console_width()
        detail_panel = self._build_skill_browser_detail_panel(selected_record, compact=width < 138)
        footer_panel = self._build_skill_browser_footer_panel(len(filtered_records), search_query, is_searching)
        return Group(summary_panel, list_panel, detail_panel, footer_panel)

    def _print_skill_detail_page(self, record: Any) -> None:
        """Print one selected skill page into the transcript."""
        self._show_command_panel(
            f"Skill {getattr(record, 'name', '')}",
            subtitle="Detected Codex-style skill metadata and instruction preview.",
            accent=self.theme.BLUE_SOFT,
            meta=str(getattr(record, "display_path", "") or ""),
        )

        overview = self._build_key_value_table(
            [
                ("Skill", getattr(record, "name", "")),
                ("Scope", getattr(record, "scope_label", "")),
                ("Root", getattr(record, "root_label", "")),
                ("Path", getattr(record, "display_path", "")),
                ("Description", getattr(record, "description", "")),
            ]
        )
        self.console.print(overview)
        self.console.print()

        body_preview = str(getattr(record, "body", "") or "").strip() or "(empty skill body)"
        preview_lines = body_preview.splitlines()
        if len(preview_lines) > 24:
            body_preview = "\n".join(preview_lines[:24]).rstrip() + "\n..."

        self.console.print(
            Panel(
                Syntax(body_preview, "markdown", word_wrap=True, line_numbers=False, background_color="default"),
                title=f"[bold {self.theme.PINK_SOFT}]SKILL.md Preview[/bold {self.theme.PINK_SOFT}]",
                border_style=self.theme.BORDER_PRIMARY,
                box=box.ROUNDED,
                padding=(0, 1),
            )
        )
        self.console.print()

    def _cmd_skills_ui(self, initial_query: str = "", *, force_refresh: bool = False) -> bool:
        """Launch the interactive skills browser and keep the focused page on exit."""
        skills_manager = self.app.get('skills_manager')
        if not skills_manager:
            self.console.print(
                f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} Skills manager is not available.[/{self.theme.CORAL_SOFT}]"
            )
            return True

        summary = skills_manager.get_status_summary(force_refresh=force_refresh)
        rows = skills_manager.list_display_rows(force_refresh=False)
        error_rows = skills_manager.list_error_rows(force_refresh=False)
        snapshot = skills_manager.get_snapshot(force_refresh=False)
        records = list(getattr(snapshot, "records", ()) or [])
        if force_refresh and self.app.get('refresh_agent_prompt_guidance'):
            self.app['refresh_agent_prompt_guidance']()

        try:
            import msvcrt
        except ImportError:
            self._print_skills_status_view(summary, rows, error_rows)
            return True

        if not records:
            self._print_skills_status_view(summary, rows, error_rows)
            return True

        search_query = str(initial_query or "").strip()
        is_searching = bool(search_query)
        filtered_records = self._filter_skill_records(records, search_query)
        selected_idx = 0
        scroll_offset = 0
        selected_record = filtered_records[0] if filtered_records else records[0]
        max_visible = self._skill_browser_visible_count()

        from rich.live import Live

        with Live(
            self._render_skill_browser_ui(
                records,
                filtered_records,
                selected_idx,
                scroll_offset,
                max_visible,
                selected_record,
                search_query,
                is_searching,
                len(error_rows),
                len(summary.get("root_paths", []) or []),
            ),
            auto_refresh=False,
            screen=True,
            transient=True,
            vertical_overflow="ellipsis",
            console=self.console,
        ) as live:
            last_size = self._console_size()
            while True:
                state_changed = False
                if msvcrt.kbhit():
                    key = msvcrt.getch()

                    if key == b"\x1b":
                        break
                    if key == b"/":
                        is_searching = True
                        state_changed = True
                    elif key in (b"\r", b"\n"):
                        break
                    elif key == b"\x08":
                        if search_query:
                            search_query = search_query[:-1]
                            filtered_records = self._filter_skill_records(records, search_query)
                            selected_idx = min(selected_idx, max(0, len(filtered_records) - 1))
                            scroll_offset = 0
                            if filtered_records:
                                selected_record = filtered_records[selected_idx]
                            state_changed = True
                        else:
                            is_searching = False
                            state_changed = True
                    elif key in (b"k", b"K") and filtered_records:
                        selected_idx = (selected_idx - 1) % len(filtered_records)
                        selected_record = filtered_records[selected_idx]
                        state_changed = True
                    elif key in (b"j", b"J") and filtered_records:
                        selected_idx = (selected_idx + 1) % len(filtered_records)
                        selected_record = filtered_records[selected_idx]
                        state_changed = True
                    elif key in (b"\x00", b"\xe0"):
                        key = msvcrt.getch()
                        if key == b"H" and filtered_records:
                            selected_idx = (selected_idx - 1) % len(filtered_records)
                            selected_record = filtered_records[selected_idx]
                            state_changed = True
                        elif key == b"P" and filtered_records:
                            selected_idx = (selected_idx + 1) % len(filtered_records)
                            selected_record = filtered_records[selected_idx]
                            state_changed = True
                        elif key == b"I" and filtered_records:
                            selected_idx = max(0, selected_idx - max_visible)
                            selected_record = filtered_records[selected_idx]
                            state_changed = True
                        elif key == b"Q" and filtered_records:
                            selected_idx = min(len(filtered_records) - 1, selected_idx + max_visible)
                            selected_record = filtered_records[selected_idx]
                            state_changed = True
                        elif key == b"G" and filtered_records:
                            selected_idx = 0
                            selected_record = filtered_records[selected_idx]
                            state_changed = True
                        elif key == b"O" and filtered_records:
                            selected_idx = len(filtered_records) - 1
                            selected_record = filtered_records[selected_idx]
                            state_changed = True
                    elif 32 <= key[0] <= 126:
                        search_query += key.decode("ascii", errors="ignore")
                        is_searching = True
                        filtered_records = self._filter_skill_records(records, search_query)
                        selected_idx = 0
                        scroll_offset = 0
                        if filtered_records:
                            selected_record = filtered_records[0]
                        state_changed = True

                current_size = self._console_size()
                if current_size != last_size:
                    last_size = current_size
                    state_changed = True

                if state_changed:
                    max_visible = self._skill_browser_visible_count()
                    scroll_offset = self._clamp_help_browser_scroll(selected_idx, scroll_offset, len(filtered_records), max_visible)
                    if filtered_records:
                        selected_record = filtered_records[selected_idx]
                    live.update(
                        self._render_skill_browser_ui(
                            records,
                            filtered_records,
                            selected_idx,
                            scroll_offset,
                            max_visible,
                            selected_record,
                            search_query,
                            is_searching,
                            len(error_rows),
                            len(summary.get("root_paths", []) or []),
                        ),
                        refresh=True,
                    )
                time.sleep(0.025)

        self.console.print()
        self._print_skill_detail_page(selected_record)
        return True

    def _build_command_table(
        self,
        rows: List[tuple[str, str]],
        *,
        title: str = "Available Commands",
        accent: Optional[str] = None,
    ) -> Table:
        """Build a consistent command reference table."""
        accent_color = accent or self.theme.BORDER_SECONDARY
        table = Table(
            title=escape(title),
            title_style=f"bold {accent_color}",
            show_header=True,
            box=box.ROUNDED,
            border_style=accent_color,
            expand=True,
        )
        table.add_column("Command", style=f"bold {self.theme.PINK_SOFT}", width=28)
        table.add_column("Description", style=self.theme.TEXT_SECONDARY)
        for command, description in rows:
            table.add_row(command, description)
        return table

    def _get_context_usage_snapshot(self, agent: Any, config_manager: Any) -> Optional[Dict[str, Any]]:
        """Fetch current context usage statistics for the active conversation."""
        from ..tools.token_counter import TokenCounterTool

        token_counter = TokenCounterTool({'project_root': self.app.get('project_root')})
        token_counter.context = {'agent': agent, 'config_manager': config_manager}
        result = token_counter.execute(check_current_conversation=True)
        if result.success and result.data:
            return result.data
        return None
    
    def handle(self, command_line: str) -> bool:
        """
        Handle a command.
        
        Returns True if the app should continue, False if should exit.
        """
        parts = command_line[1:].split(maxsplit=1)  # Remove leading /
        if not parts:
            return True
        
        cmd_original = parts[0]  # Keep original case
        cmd = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""
        
        # Check for case-sensitive commands first (like CE)
        if cmd_original in self.commands:
            return self.commands[cmd_original](args)
        
        # Then check case-insensitive
        if cmd in self.commands:
            return self.commands[cmd](args)
        else:
            self._show_activity_event(
                "Command",
                f"Unknown command: /{cmd_original}",
                status="error",
                detail="Type /help for available commands.",
            )
            return True
    
    def cmd_help(self, args: str) -> bool:
        """Show the full command guide or detailed help for a specific command."""
        query = args.strip()
        self.console.print()

        if not query:
            return self._cmd_help_ui()

        if query.lower() == "all":
            self._print_help_hero(detail_mode=True)
            for section in HELP_SECTION_ORDER:
                entries = self._get_help_entries_for_section(section)
                if entries:
                    self._print_help_section_details(section, entries)
            self._print_help_tips()
            self.console.print()
            return True

        normalized = normalize_help_topic(query)
        if not normalized or normalized not in HELP_TOPICS:
            self.console.print(
                f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} No help topic found for: {escape(query)}[/{self.theme.CORAL_SOFT}]"
            )
            self.console.print(
                f"[{self.theme.TEXT_DIM}]Try /help, /help all, or /help codex.[/{self.theme.TEXT_DIM}]"
            )
            self.console.print()
            return True

        self._print_help_hero(detail_mode=True)
        self.console.print(self._build_help_detail_panel(HELP_TOPICS[normalized]))
        self._print_help_tips(compact=True)
        self.console.print()
        return True

    def _get_help_entries_for_section(self, section: str) -> List[Dict[str, object]]:
        """Return help topics for a section in catalog order."""
        return [
            topic
            for topic in HELP_TOPICS.values()
            if str(topic.get("section", "")).strip() == section
        ]

    def _help_section_accent(self, section: str) -> str:
        """Resolve accent color for help sections."""
        accents = {
            "Core": self.theme.BLUE_SOFT,
            "Models & Modes": self.theme.PURPLE_SOFT,
            "Providers": self.theme.MINT_SOFT,
            "Tools & Context": self.theme.AMBER_GLOW,
            "Sessions & Recovery": self.theme.BLUE_MEDIUM,
            "Project & Rules": self.theme.PEACH_SOFT,
            "Game": self.theme.PINK_SOFT,
        }
        return accents.get(section, self.theme.BORDER_PRIMARY)

    def _print_help_hero(self, detail_mode: bool = False) -> None:
        """Render the help hero banner."""
        subtitle = (
            "Focused command reference with full forms and runnable examples."
            if detail_mode
            else "Interactive browser for every command, subcommand, and example in one place."
        )
        hero = Panel(
            f"[bold {self.theme.PINK_SOFT}]{self.deco.SPARKLE} Reverie Command Guide {self.deco.SPARKLE}[/bold {self.theme.PINK_SOFT}]\n"
            f"[{self.theme.PURPLE_MEDIUM}]{subtitle}[/{self.theme.PURPLE_MEDIUM}]\n\n"
            f"[bold {self.theme.BLUE_SOFT}]Quick Start[/bold {self.theme.BLUE_SOFT}]\n"
            f"[{self.theme.TEXT_SECONDARY}]1.[/{self.theme.TEXT_SECONDARY}] /help for the live browser and pinned detail pages\n"
            f"[{self.theme.TEXT_SECONDARY}]2.[/{self.theme.TEXT_SECONDARY}] /help <command> for one detailed command page\n"
            f"[{self.theme.TEXT_SECONDARY}]3.[/{self.theme.TEXT_SECONDARY}] /help all for the full printable reference",
            border_style=self.theme.BORDER_PRIMARY,
            padding=(1, 2),
            box=box.ROUNDED,
        )
        self.console.print(hero)
        self.console.print()

    def _build_help_overview_table(self, title: str, entries: List[Dict[str, object]]) -> Panel:
        """Build one grouped help table."""
        accent = self._help_section_accent(title)
        table = Table(
            box=box.SIMPLE_HEAVY,
            border_style=accent,
            expand=True,
            show_lines=False,
            pad_edge=False,
        )
        table.add_column("Command", style=f"bold {accent}", width=16, no_wrap=True)
        table.add_column("Description", style=self.theme.TEXT_SECONDARY, ratio=3)
        table.add_column("Subcommands / Forms", style=self.theme.TEXT_DIM, ratio=4)

        for topic in entries:
            aliases = topic.get("aliases", []) or []
            alias_text = ""
            if aliases:
                alias_text = f"\n[{self.theme.TEXT_DIM}]Aliases: {escape(', '.join(str(alias) for alias in aliases))}[/{self.theme.TEXT_DIM}]"
            table.add_row(
                escape(str(topic.get("command", ""))),
                f"{escape(str(topic.get('summary', '')))}{alias_text}",
                escape(str(topic.get("overview", ""))),
            )

        return Panel(
            table,
            title=f"[bold {accent}]{self.deco.DIAMOND} {escape(title)}[/bold {accent}]",
            border_style=accent,
            padding=(0, 1),
            box=box.ROUNDED,
        )

    def _build_help_detail_panel(self, topic: Dict[str, object], compact: bool = False) -> Panel:
        """Build the detailed help panel for a single command."""
        section = str(topic.get("section", "")).strip()
        accent = self._help_section_accent(section)
        command = str(topic.get("command", "")).strip()
        aliases = topic.get("aliases", []) or []
        summary = str(topic.get("summary", "")).strip()
        detail = str(topic.get("detail", "")).strip()
        subcommands = topic.get("subcommands", []) or []
        examples = topic.get("examples", []) or []

        header_lines = [
            f"[bold {accent}]{escape(command)}[/bold {accent}]",
            f"[{self.theme.TEXT_SECONDARY}]{escape(summary)}[/{self.theme.TEXT_SECONDARY}]",
        ]
        if detail:
            header_lines.append(f"[{self.theme.TEXT_DIM}]{escape(detail)}[/{self.theme.TEXT_DIM}]")
        if aliases:
            header_lines.append(
                f"[{self.theme.TEXT_DIM}]Aliases: {escape(', '.join(str(alias) for alias in aliases))}[/{self.theme.TEXT_DIM}]"
            )

        forms = Table(
            box=box.SIMPLE_HEAVY,
            border_style=accent,
            expand=True,
            show_header=True,
            pad_edge=False,
        )
        forms.add_column("Form / Action", style=f"bold {accent}", width=26 if compact else 32)
        forms.add_column("What It Does", style=self.theme.TEXT_SECONDARY, ratio=3)
        forms.add_column("Example", style=self.theme.TEXT_DIM, ratio=2)
        for item in subcommands:
            forms.add_row(
                escape(str(item.get("usage", ""))),
                escape(str(item.get("description", ""))),
                escape(self._resolve_help_example(item)),
            )

        renderables: List[object] = [Text.from_markup("\n".join(header_lines)), forms]
        if examples:
            example_lines = [
                f"[{self.theme.TEXT_DIM}]{self.deco.CHEVRON_RIGHT} {escape(str(example))}[/{self.theme.TEXT_DIM}]"
                for example in examples
            ]
            renderables.append(
                Text.from_markup(
                    f"[bold {accent}]Examples[/bold {accent}]\n" + "\n".join(example_lines)
                )
            )

        return Panel(
            Group(*renderables),
            title=f"[bold {accent}]{self.deco.DIAMOND} {escape(command)}[/bold {accent}]",
            subtitle=f"[{self.theme.TEXT_DIM}]Section: {escape(section)}[/{self.theme.TEXT_DIM}]",
            border_style=accent,
            padding=(1, 2),
            box=box.ROUNDED,
        )

    def _resolve_help_example(self, item: Dict[str, object]) -> str:
        """Resolve an example string for a help subcommand row."""
        explicit = str(item.get("example", "")).strip()
        if explicit:
            return explicit

        usage = str(item.get("usage", "")).strip()
        if not usage:
            return ""

        if usage == "Categories":
            return "In /setting, highlight a row and press Enter to edit it."
        if usage.startswith("Action: "):
            action = usage.split(": ", 1)[1].strip()
            if action == "n":
                return "At the /sessions prompt, enter n"
            if action == "d":
                return "At the /sessions prompt, enter d, then choose a session number"
            if action == "<number>":
                return "At the /sessions prompt, enter 2"

        example = usage
        replacements = [
            ("<command>", "codex"),
            ("<query>", "latest sqlite wal docs"),
            ("<number>", "2"),
            ("<count>", "20"),
            ("<model-id>", "gpt-5.4"),
            ("<mode-name>", "spec-driven"),
            ("<theme>", "ocean"),
            ("<project-id>", "my-project-123"),
            ("<url|/path|clear>", "http://127.0.0.1:8000/v1/chat/completions"),
            ("<low|medium|high|extra high>", "high"),
            ("<seconds>", "120"),
            ("<prompt>", "cinematic neon skyline concept art"),
            ("<your prompt>", "cinematic neon skyline concept art"),
            ("<text>", "Always run tests before finalizing"),
            ("<checkpoint-id>", "cp_20260311_001"),
            ("<index>", "2"),
            ("<count>", "4"),
        ]
        for placeholder, replacement in replacements:
            example = example.replace(placeholder, replacement)
        return example

    def _print_help_section_details(self, section: str, entries: List[Dict[str, object]]) -> None:
        """Print all detailed panels for a section."""
        accent = self._help_section_accent(section)
        self.console.print(
            Panel(
                f"[bold {accent}]{self.deco.DIAMOND} {escape(section)}[/bold {accent}]",
                border_style=accent,
                padding=(0, 2),
                box=box.ROUNDED,
            )
        )
        self.console.print()
        for topic in entries:
            self.console.print(self._build_help_detail_panel(topic))
            self.console.print()

    def _print_help_tips(self, compact: bool = False) -> None:
        """Render help footer tips."""
        lines = [
            f"[{self.theme.PINK_SOFT}]{self.deco.CHEVRON_RIGHT}[/{self.theme.PINK_SOFT}] Ask normally; slash commands are for control paths and tooling",
            f"[{self.theme.PINK_SOFT}]{self.deco.CHEVRON_RIGHT}[/{self.theme.PINK_SOFT}] Use a trailing \\ or triple quotes for multi-line input",
            f"[{self.theme.PINK_SOFT}]{self.deco.CHEVRON_RIGHT}[/{self.theme.PINK_SOFT}] Ctrl+C once cancels input; twice exits",
        ]
        if compact:
            lines.append(
                f"[{self.theme.PINK_SOFT}]{self.deco.CHEVRON_RIGHT}[/{self.theme.PINK_SOFT}] Use /help to reopen the live browser or /help all for the full reference"
            )
        else:
            lines.append(
                f"[{self.theme.PINK_SOFT}]{self.deco.CHEVRON_RIGHT}[/{self.theme.PINK_SOFT}] Bare /help opens the live browser; /help <command> prints one detailed page"
            )

        self.console.print(
            Panel(
                f"[bold {self.theme.PURPLE_MEDIUM}]{self.deco.SPARKLE} Input Tips[/bold {self.theme.PURPLE_MEDIUM}]\n\n"
                + "\n".join(lines),
                border_style=self.theme.BORDER_PRIMARY,
                padding=(0, 2),
                box=box.ROUNDED,
            )
        )

    def _help_topic_cache_key(self, topic: Dict[str, object]) -> str:
        return str(topic.get("_topic_key", "") or topic.get("command", "")).strip().lower()

    def _compute_help_topic_preview(self, topic: Dict[str, object], limit: int = 3) -> str:
        forms = [
            str(item.get("usage", "")).strip()
            for item in (topic.get("subcommands", []) or [])
            if str(item.get("usage", "")).strip()
        ]
        if not forms:
            fallback = str(topic.get("overview", "")).strip()
            return fallback or str(topic.get("summary", "")).strip()

        preview = "  |  ".join(forms[:limit])
        if len(forms) > limit:
            preview = f"{preview}  |  +{len(forms) - limit} more"
        return preview

    def _build_help_topic_search_document(self, topic: Dict[str, object]) -> str:
        search_parts = [
            str(topic.get("command", "")),
            str(topic.get("section", "")),
            str(topic.get("summary", "")),
            str(topic.get("detail", "")),
            str(topic.get("overview", "")),
            " ".join(str(alias) for alias in (topic.get("aliases", []) or [])),
        ]
        for subcommand in topic.get("subcommands", []) or []:
            search_parts.extend(
                [
                    str(subcommand.get("usage", "")),
                    str(subcommand.get("description", "")),
                    self._resolve_help_example(subcommand),
                ]
            )
        return " ".join(part.lower() for part in search_parts if part)

    def _prime_help_catalog_cache(self) -> None:
        items: List[Dict[str, object]] = []
        seen: set[str] = set()

        for section in HELP_SECTION_ORDER:
            for key, topic in HELP_TOPICS.items():
                if str(topic.get("section", "")).strip() != section:
                    continue
                item = dict(topic)
                item["_topic_key"] = key
                items.append(item)
                seen.add(key)

        for key, topic in HELP_TOPICS.items():
            if key in seen:
                continue
            item = dict(topic)
            item["_topic_key"] = key
            items.append(item)

        self._help_topic_items_cache = tuple(items)
        self._help_preview_cache = {
            self._help_topic_cache_key(item): self._compute_help_topic_preview(item)
            for item in items
        }
        self._help_search_cache = {
            self._help_topic_cache_key(item): self._build_help_topic_search_document(item)
            for item in items
        }

    def _get_help_topic_items(self) -> List[Dict[str, object]]:
        """Flatten help topics into UI-friendly items while preserving catalog order."""
        if not self._help_topic_items_cache:
            self._prime_help_catalog_cache()
        return list(self._help_topic_items_cache)

    def _build_help_topic_preview(self, topic: Dict[str, object], limit: int = 3) -> str:
        """Build a compact preview of full command forms for the help browser list."""
        cache_key = self._help_topic_cache_key(topic)
        cached = self._help_preview_cache.get(cache_key)
        if cached is not None and limit == 3:
            return cached
        return self._compute_help_topic_preview(topic, limit=limit)

    def _filter_help_topic_items(self, items: List[Dict[str, object]], query: str) -> List[Dict[str, object]]:
        """Filter help topics by command, aliases, summaries, and full subcommand forms."""
        raw_query = str(query or "").strip().lower()
        if not raw_query:
            return list(items)

        terms = [term for term in raw_query.split() if term]
        filtered: List[Dict[str, object]] = []

        for item in items:
            cache_key = self._help_topic_cache_key(item)
            haystack = self._help_search_cache.get(cache_key)
            if haystack is None:
                haystack = self._build_help_topic_search_document(item)
                self._help_search_cache[cache_key] = haystack
            if all(term in haystack for term in terms):
                filtered.append(item)

        return filtered

    def _help_browser_visible_count(self) -> int:
        """Choose a stable visible-row count for the help browser list."""
        height = int(getattr(self.console.size, "height", 0) or 32)
        width = int(getattr(self.console.size, "width", 0) or self.console.width or 100)
        reserve = 17 if width >= 124 else 22
        return max(6, min(14, height - reserve))

    def _clamp_help_browser_scroll(self, selected_idx: int, scroll_offset: int, total: int, max_visible: int) -> int:
        """Keep the selected row inside the visible range."""
        if total <= 0:
            return 0
        max_visible = max(1, min(max_visible, total))
        if selected_idx < scroll_offset:
            scroll_offset = selected_idx
        elif selected_idx >= scroll_offset + max_visible:
            scroll_offset = selected_idx - max_visible + 1
        return max(0, min(scroll_offset, max(0, total - max_visible)))

    def _build_help_browser_summary_panel(
        self,
        total_count: int,
        filtered_count: int,
        selected_topic: Dict[str, object],
        search_query: str,
        is_searching: bool,
    ) -> Panel:
        """Build the top summary panel for the interactive help browser."""
        command = str(selected_topic.get("command", "")).strip()
        section = str(selected_topic.get("section", "")).strip()
        summary = str(selected_topic.get("summary", "")).strip()
        accent = self._help_section_accent(section)
        count_text = f"{filtered_count}/{total_count} commands" if filtered_count != total_count else f"{total_count} commands"

        title_grid = Table.grid(expand=True)
        title_grid.add_column(ratio=1)
        title_grid.add_column(justify="right", no_wrap=True)
        title_grid.add_row(
            Text.assemble(
                (f"{self.deco.SPARKLE} ", self.theme.PINK_SOFT),
                ("Help Browser", f"bold {self.theme.PINK_SOFT}"),
            ),
            Text(count_text, style=self.theme.TEXT_DIM),
        )

        search_display = search_query + ("_" if is_searching else "")
        body_lines = [
            f"[{self.theme.TEXT_SECONDARY}]Browse commands, runnable forms, and examples. Press [bold {self.theme.BLUE_SOFT}]Enter[/bold {self.theme.BLUE_SOFT}] or [bold {self.theme.BLUE_SOFT}]Esc[/bold {self.theme.BLUE_SOFT}] to pin the focused page into the transcript.[/{self.theme.TEXT_SECONDARY}]",
            f"[{self.theme.TEXT_DIM}]Focused:[/{self.theme.TEXT_DIM}] [bold {accent}]{escape(command)}[/bold {accent}] [{self.theme.TEXT_DIM}]· {escape(section)}[/{self.theme.TEXT_DIM}]",
        ]
        if summary:
            body_lines.append(f"[{self.theme.TEXT_PRIMARY}]{escape(summary)}[/{self.theme.TEXT_PRIMARY}]")
        if search_query or is_searching:
            body_lines.append(
                f"[bold {self.theme.PURPLE_SOFT}]{self.deco.SEARCH} Filter[/bold {self.theme.PURPLE_SOFT}] "
                f"[{self.theme.TEXT_PRIMARY}]{escape(search_display)}[/{self.theme.TEXT_PRIMARY}]"
            )
        else:
            body_lines.append(
                f"[{self.theme.TEXT_DIM}]Press / to filter by command, section, subcommand usage, or example text.[/{self.theme.TEXT_DIM}]"
            )

        return Panel(
            Group(title_grid, Text.from_markup("\n".join(body_lines))),
            border_style=self.theme.BORDER_PRIMARY,
            padding=(1, 2),
            box=box.ROUNDED,
        )

    def _build_help_browser_list_panel(
        self,
        filtered_items: List[Dict[str, object]],
        selected_idx: int,
        scroll_offset: int,
        max_visible: int,
    ) -> Panel:
        """Build the command list panel for the interactive help browser."""
        if not filtered_items:
            return Panel(
                Text.from_markup(
                    f"[{self.theme.TEXT_DIM}]No matching commands. Refine the filter or press Esc to pin the last selected help page.[/{self.theme.TEXT_DIM}]"
                ),
                title=f"[bold {self.theme.BLUE_SOFT}]{self.deco.DIAMOND} Commands[/bold {self.theme.BLUE_SOFT}]",
                border_style=self.theme.BORDER_SUBTLE,
                padding=(1, 2),
                box=box.ROUNDED,
            )

        table = Table(
            box=box.SIMPLE_HEAVY,
            border_style=self.theme.BORDER_SUBTLE,
            expand=True,
            show_header=True,
            pad_edge=False,
            show_lines=False,
        )
        table.add_column("", width=2, no_wrap=True)
        table.add_column("#", style=self.theme.TEXT_DIM, width=4, justify="right", no_wrap=True)
        table.add_column("Command", style=f"bold {self.theme.BLUE_SOFT}", width=16, no_wrap=True)
        table.add_column("Preview", style=self.theme.TEXT_SECONDARY, ratio=3)

        end_idx = min(scroll_offset + max_visible, len(filtered_items))
        visible_items = filtered_items[scroll_offset:end_idx]
        for row_index, topic in enumerate(visible_items):
            actual_idx = scroll_offset + row_index
            is_selected = actual_idx == selected_idx
            indicator = Text("›" if is_selected else "", style=f"bold {self.theme.PINK_SOFT}")
            command_style = f"bold {self.theme.TEXT_PRIMARY} on {self.theme.PURPLE_DEEP}" if is_selected else f"bold {self.theme.BLUE_SOFT}"
            preview_style = self.theme.TEXT_PRIMARY if is_selected else self.theme.TEXT_SECONDARY
            section = str(topic.get("section", "")).strip()
            preview = f"[{section}] {self._build_help_topic_preview(topic)}" if section else self._build_help_topic_preview(topic)
            table.add_row(
                indicator,
                Text(str(actual_idx + 1), style=self.theme.TEXT_DIM),
                Text(str(topic.get("command", "")).strip(), style=command_style),
                Text(preview, style=preview_style, overflow="fold"),
            )

        visible_range = (
            f"{scroll_offset + 1}-{end_idx} / {len(filtered_items)}"
            if visible_items
            else f"0 / {len(filtered_items)}"
        )
        return Panel(
            table,
            title=f"[bold {self.theme.BLUE_SOFT}]{self.deco.DIAMOND} Commands[/bold {self.theme.BLUE_SOFT}]",
            subtitle=f"[{self.theme.TEXT_DIM}]Visible: {visible_range}[/{self.theme.TEXT_DIM}]",
            border_style=self.theme.BORDER_SUBTLE,
            padding=(0, 1),
            box=box.ROUNDED,
        )

    def _build_help_browser_footer_panel(
        self,
        filtered_count: int,
        search_query: str,
        is_searching: bool,
    ) -> Panel:
        """Build the navigation footer for the interactive help browser."""
        footer_text = Text()
        footer_text.append("Navigate ", style=self.theme.TEXT_DIM)
        footer_text.append("↑↓ / j k", style=self.theme.BLUE_SOFT)
        footer_text.append("  Page ", style=self.theme.TEXT_DIM)
        footer_text.append("PgUp/PgDn", style=self.theme.BLUE_SOFT)
        footer_text.append("  Pin ", style=self.theme.TEXT_DIM)
        footer_text.append("Enter / Esc", style=self.theme.BLUE_SOFT)
        footer_text.append("  Filter ", style=self.theme.TEXT_DIM)
        footer_text.append("/", style=self.theme.BLUE_SOFT)
        footer_text.append("  Edit ", style=self.theme.TEXT_DIM)
        footer_text.append("Backspace", style=self.theme.BLUE_SOFT)
        footer_text.append("  Jump ", style=self.theme.TEXT_DIM)
        footer_text.append("Home/End", style=self.theme.BLUE_SOFT)

        status_text = "Typing filter" if is_searching else ("Filter active" if search_query else "Live browser")
        status_color = self.theme.PURPLE_SOFT if (is_searching or search_query) else self.theme.TEXT_DIM

        footer_grid = Table.grid(expand=True)
        footer_grid.add_column(ratio=1)
        footer_grid.add_column(justify="right", no_wrap=True)
        footer_grid.add_row(
            footer_text,
            Text(f"{filtered_count} visible · {status_text}", style=status_color),
        )

        return Panel(
            footer_grid,
            border_style=self.theme.BORDER_SUBTLE,
            padding=(0, 1),
            box=box.ROUNDED,
        )

    def _render_help_ui(
        self,
        filtered_items: List[Dict[str, object]],
        selected_idx: int,
        scroll_offset: int,
        max_visible: int,
        selected_topic: Dict[str, object],
        search_query: str,
        is_searching: bool,
        total_count: int,
    ) -> Group:
        """Compose the full interactive help browser layout."""
        summary_panel = self._build_help_browser_summary_panel(
            total_count,
            len(filtered_items),
            selected_topic,
            search_query,
            is_searching,
        )
        list_panel = self._build_help_browser_list_panel(filtered_items, selected_idx, scroll_offset, max_visible)
        width = int(getattr(self.console.size, "width", 0) or self.console.width or 100)
        detail_panel = self._build_help_detail_panel(selected_topic, compact=width < 138)
        footer_panel = self._build_help_browser_footer_panel(len(filtered_items), search_query, is_searching)

        if width >= 106:
            body = Columns([list_panel, detail_panel], expand=True, equal=False)
        else:
            body = Group(list_panel, detail_panel)
        return Group(summary_panel, body, footer_panel)

    def _cmd_help_ui(self, initial_query: str = "") -> bool:
        """Launch the interactive help browser and pin the selected page on exit."""
        try:
            import msvcrt
        except ImportError:
            self._print_help_hero(detail_mode=False)
            for section in HELP_SECTION_ORDER:
                entries = self._get_help_entries_for_section(section)
                if entries:
                    self.console.print(self._build_help_overview_table(section, entries))
                    self.console.print()
            self._print_help_tips()
            self.console.print()
            return True

        all_items = self._get_help_topic_items()
        if not all_items:
            self.console.print(f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} Help catalog is empty.[/{self.theme.CORAL_SOFT}]")
            return True

        search_query = str(initial_query or "").strip()
        is_searching = bool(search_query)
        filtered_items = self._filter_help_topic_items(all_items, search_query)
        selected_idx = 0
        scroll_offset = 0
        selected_topic = filtered_items[0] if filtered_items else all_items[0]
        max_visible = self._help_browser_visible_count()

        from rich.live import Live

        with Live(
            self._render_help_ui(
                filtered_items,
                selected_idx,
                scroll_offset,
                max_visible,
                selected_topic,
                search_query,
                is_searching,
                len(all_items),
            ),
            auto_refresh=False,
            screen=True,
            transient=True,
            vertical_overflow="ellipsis",
            console=self.console,
        ) as live:
            last_size = self._console_size()
            while True:
                if msvcrt.kbhit():
                    key = msvcrt.getch()

                    if key == b"\x1b":
                        break
                    if key == b"/":
                        is_searching = True
                    elif key in (b"\r", b"\n"):
                        break
                    elif key == b"\x08":
                        if search_query:
                            search_query = search_query[:-1]
                            filtered_items = self._filter_help_topic_items(all_items, search_query)
                            selected_idx = min(selected_idx, max(0, len(filtered_items) - 1))
                            scroll_offset = 0
                            if filtered_items:
                                selected_topic = filtered_items[selected_idx]
                        else:
                            is_searching = False
                    elif key in (b"k", b"K") and filtered_items:
                        selected_idx = (selected_idx - 1) % len(filtered_items)
                        selected_topic = filtered_items[selected_idx]
                    elif key in (b"j", b"J") and filtered_items:
                        selected_idx = (selected_idx + 1) % len(filtered_items)
                        selected_topic = filtered_items[selected_idx]
                    elif key in (b"\x00", b"\xe0"):
                        key = msvcrt.getch()
                        if key == b"H" and filtered_items:
                            selected_idx = (selected_idx - 1) % len(filtered_items)
                            selected_topic = filtered_items[selected_idx]
                        elif key == b"P" and filtered_items:
                            selected_idx = (selected_idx + 1) % len(filtered_items)
                            selected_topic = filtered_items[selected_idx]
                        elif key == b"I" and filtered_items:
                            selected_idx = max(0, selected_idx - max_visible)
                            selected_topic = filtered_items[selected_idx]
                        elif key == b"Q" and filtered_items:
                            selected_idx = min(len(filtered_items) - 1, selected_idx + max_visible)
                            selected_topic = filtered_items[selected_idx]
                        elif key == b"G" and filtered_items:
                            selected_idx = 0
                            selected_topic = filtered_items[selected_idx]
                        elif key == b"O" and filtered_items:
                            selected_idx = len(filtered_items) - 1
                            selected_topic = filtered_items[selected_idx]
                    elif 32 <= key[0] <= 126:
                        search_query += key.decode("ascii", errors="ignore")
                        is_searching = True
                        filtered_items = self._filter_help_topic_items(all_items, search_query)
                        selected_idx = 0
                        scroll_offset = 0
                        if filtered_items:
                            selected_topic = filtered_items[0]
                    else:
                        time.sleep(0.025)
                        continue

                    max_visible = self._help_browser_visible_count()
                    scroll_offset = self._clamp_help_browser_scroll(selected_idx, scroll_offset, len(filtered_items), max_visible)
                    if filtered_items:
                        selected_topic = filtered_items[selected_idx]

                    live.update(
                        self._render_help_ui(
                            filtered_items,
                            selected_idx,
                            scroll_offset,
                            max_visible,
                            selected_topic,
                            search_query,
                            is_searching,
                            len(all_items),
                        ),
                        refresh=True,
                    )
                current_size = self._console_size()
                if current_size != last_size:
                    last_size = current_size
                    max_visible = self._help_browser_visible_count()
                    scroll_offset = self._clamp_help_browser_scroll(selected_idx, scroll_offset, len(filtered_items), max_visible)
                    if filtered_items:
                        selected_topic = filtered_items[selected_idx]
                    live.update(
                        self._render_help_ui(
                            filtered_items,
                            selected_idx,
                            scroll_offset,
                            max_visible,
                            selected_topic,
                            search_query,
                            is_searching,
                            len(all_items),
                        ),
                        refresh=True,
                    )
                time.sleep(0.025)

        self.console.print()
        self.console.print(self._build_help_detail_panel(selected_topic))
        self.console.print()
        return True
    
    def cmd_tools(self, args: str) -> bool:
        """Browse tools with mode-aware discovery and inspection."""
        agent = self.app.get('agent')
        if not agent:
            self.console.print(f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} Agent not initialized[/{self.theme.CORAL_SOFT}]")
            return True

        parsed = self._parse_tools_args(args)
        if parsed.get("error"):
            self._show_activity_event(
                "Tools",
                "Could not parse `/tools` arguments.",
                status="error",
                detail=str(parsed.get("error", "")),
            )
            self.console.print(self._build_tools_shortcuts_table())
            self.console.print()
            return True

        operation = str(parsed.get("operation", "overview") or "overview").lower()
        mode = self._resolve_tools_mode(agent, str(parsed.get("mode_override", "") or ""))
        query = str(parsed.get("query", "") or "").strip()
        tool_name = str(parsed.get("tool_name", "") or "").strip()

        if operation in {"overview", "list", "status"}:
            return self._render_tools_overview(agent, mode)
        if operation == "all":
            return self._render_tools_all(agent, mode)
        if operation == "details":
            return self._render_tools_details(agent, mode)
        if operation == "groups":
            return self._render_tools_groups(agent, mode)
        if operation == "search":
            return self._render_tools_search(agent, mode, query)
        if operation == "recommend":
            return self._render_tools_recommend(agent, mode, query)
        if operation == "inspect":
            return self._render_tools_inspect(agent, mode, tool_name)

        self._show_activity_event(
            "Tools",
            f"Unknown `/tools` action: {operation}",
            status="error",
            detail="Use `/tools`, `/tools all`, `/tools details`, `/tools search <query>`, `/tools recommend <task>`, `/tools inspect <tool>`, or `/tools groups`.",
        )
        self.console.print(self._build_tools_shortcuts_table())
        self.console.print()
        return True

    def _parse_tools_args(self, args: str) -> Dict[str, Any]:
        """Parse `/tools` arguments with optional `--mode` support."""
        raw = str(args or "").strip()
        if not raw:
            return {"operation": "overview", "mode_override": "", "query": "", "tool_name": ""}

        try:
            tokens = shlex.split(raw, posix=False)
        except ValueError as exc:
            return {"error": str(exc)}

        filtered: List[str] = []
        mode_override = ""
        index = 0
        while index < len(tokens):
            token = str(tokens[index] or "").strip()
            lowered = token.lower()
            if lowered in {"--mode", "-m"}:
                index += 1
                if index >= len(tokens):
                    return {"error": "Missing mode name after --mode."}
                mode_override = str(tokens[index] or "").strip()
            elif token:
                filtered.append(token)
            index += 1

        if not filtered:
            return {"operation": "overview", "mode_override": mode_override, "query": "", "tool_name": ""}

        known_operations = {"overview", "list", "status", "all", "details", "search", "recommend", "inspect", "groups"}
        available_modes = {normalize_mode(mode_name) for mode_name in list_modes()}

        operation = str(filtered[0] or "").strip().lower()
        if operation not in known_operations:
            shorthand_mode = normalize_mode(operation)
            if shorthand_mode in available_modes:
                return {
                    "operation": "overview",
                    "mode_override": shorthand_mode,
                    "query": "",
                    "tool_name": "",
                }
            return {"operation": operation, "mode_override": mode_override, "query": "", "tool_name": ""}

        remainder = list(filtered[1:])
        if operation in {"overview", "list", "status", "all", "details", "groups"} and remainder and not mode_override:
            maybe_mode = normalize_mode(remainder[0])
            if maybe_mode in available_modes:
                mode_override = maybe_mode
                remainder = remainder[1:]

        payload = " ".join(str(item).strip() for item in remainder if str(item).strip()).strip()
        return {
            "operation": operation,
            "mode_override": mode_override,
            "query": payload if operation in {"search", "recommend"} else "",
            "tool_name": payload if operation == "inspect" else "",
        }

    def _resolve_tools_mode(self, agent: Any, mode_override: str = "") -> str:
        """Resolve the tool view mode, honoring explicit overrides first."""
        if str(mode_override or "").strip():
            return normalize_mode(mode_override)

        mode = getattr(agent, "mode", "reverie") or "reverie"
        config_manager = self.app.get('config_manager')
        if config_manager:
            try:
                config = config_manager.load()
                if getattr(config, "mode", None):
                    mode = config.mode
            except Exception:
                pass
        return normalize_mode(mode)

    def _execute_tool_catalog(
        self,
        agent: Any,
        *,
        operation: str,
        mode: str,
        query: str = "",
        tool_name: str = "",
        max_results: int = 8,
        include_schema: bool = False,
    ) -> Any:
        """Call the shared tool catalog so CLI and model discovery stay aligned."""
        tool = ToolCatalogTool({"agent": agent, "project_root": self.app.get("project_root")})
        kwargs: Dict[str, Any] = {
            "operation": operation,
            "mode": mode,
            "max_results": max_results,
            "include_schema": include_schema,
        }
        if query:
            kwargs["query"] = query
        if tool_name:
            kwargs["tool_name"] = tool_name
        return tool.execute(**kwargs)

    def _build_tool_items_table(
        self,
        items: List[Dict[str, Any]],
        *,
        title: str,
        accent: str,
        detail_label: str,
        detail_key: str,
    ) -> Table:
        """Build a reusable tool result table for list/search/recommend views."""
        compact = self._is_compact(128)
        table = Table(
            title=f"[bold {accent}]{self.deco.CRYSTAL} {escape(title)}[/bold {accent}]",
            box=box.SIMPLE_HEAVY if compact else box.ROUNDED,
            border_style=accent,
            header_style=f"bold {self.theme.TEXT_SECONDARY}",
            expand=True,
            show_lines=not compact,
            pad_edge=False,
        )
        table.add_column("Name", style=f"bold {self.theme.BLUE_SOFT}", width=24 if compact else 28)
        table.add_column("Category", style=self.theme.PURPLE_SOFT, width=16, no_wrap=True)
        table.add_column("Traits", style=self.theme.TEXT_DIM, width=18 if compact else 22)
        table.add_column(detail_label, style=self.theme.MINT_SOFT, ratio=1)
        table.add_column("Description", style=self.theme.TEXT_SECONDARY, ratio=2)

        for item in items:
            detail_value = item.get(detail_key, [])
            if isinstance(detail_value, list):
                detail_text = ", ".join(str(part) for part in detail_value if str(part).strip()) or "(none)"
            else:
                detail_text = str(detail_value or "").strip() or "(none)"
            description = str(item.get("description", "") or "").strip().splitlines()[0] if str(item.get("description", "") or "").strip() else "(no description)"
            table.add_row(
                str(item.get("name", "") or ""),
                str(item.get("category", "") or "general"),
                ", ".join(str(part) for part in (item.get("traits", []) or [])) or "(none)",
                self._truncate_middle(detail_text, 56 if compact else 84),
                self._truncate_middle(description, 90 if compact else 140),
            )
        return table

    def _build_tool_details_table(
        self,
        items: List[Dict[str, Any]],
        *,
        title: str,
        accent: str,
        show_modes: bool = False,
    ) -> Table:
        """Build a detailed `/tools` table with schema-adjacent fields."""
        compact = self._is_compact(130)
        table = Table(
            title=f"[bold {accent}]{self.deco.CRYSTAL} {escape(title)}[/bold {accent}]",
            box=box.SIMPLE_HEAVY if compact else box.ROUNDED,
            border_style=accent,
            header_style=f"bold {self.theme.TEXT_SECONDARY}",
            expand=True,
            show_lines=not compact,
            pad_edge=False,
        )
        table.add_column("Tool", style=f"bold {self.theme.BLUE_SOFT}", width=24 if compact else 28)
        table.add_column("Kind", style=self.theme.MINT_SOFT, width=14, no_wrap=True)
        table.add_column("Category", style=self.theme.PURPLE_SOFT, width=16, no_wrap=True)
        if show_modes:
            table.add_column("Modes", style=self.theme.TEXT_DIM, width=24)
        table.add_column("Required", style=self.theme.PINK_SOFT, width=18)
        table.add_column("Parameters", style=self.theme.TEXT_DIM, ratio=1)
        table.add_column("Description", style=self.theme.TEXT_SECONDARY, ratio=2)

        for item in sorted(items, key=lambda entry: str(entry.get("name", "")).lower()):
            properties = [str(part) for part in (item.get("properties", []) or []) if str(part).strip()]
            required = [str(part) for part in (item.get("required", []) or []) if str(part).strip()]
            modes = [str(part) for part in (item.get("visible_modes", []) or item.get("supported_modes", []) or []) if str(part).strip()]
            description = str(item.get("description", "") or "").strip().splitlines()[0] if str(item.get("description", "") or "").strip() else "(no description)"
            row = [
                str(item.get("name", "") or ""),
                str(item.get("kind", "") or "built-in"),
                str(item.get("category", "") or "general"),
            ]
            if show_modes:
                row.append(self._truncate_middle(", ".join(modes) or "dynamic/all", 42 if compact else 64))
            row.extend(
                [
                    self._truncate_middle(", ".join(required) or "(none)", 30),
                    self._truncate_middle(", ".join(properties) or "(none)", 56 if compact else 84),
                    self._truncate_middle(description, 90 if compact else 150),
                ]
            )
            table.add_row(*row)
        return table

    def _build_tool_group_table(
        self,
        mapping: Dict[str, List[str]],
        *,
        title: str,
        accent: str,
        label: str,
    ) -> Table:
        """Build a compact grouping table for `/tools groups`."""
        compact = self._is_compact(118)
        table = Table(
            title=f"[bold {accent}]{self.deco.CRYSTAL} {escape(title)}[/bold {accent}]",
            box=box.SIMPLE_HEAVY if compact else box.ROUNDED,
            border_style=accent,
            header_style=f"bold {self.theme.TEXT_SECONDARY}",
            expand=True,
            pad_edge=False,
        )
        table.add_column(label, style=f"bold {self.theme.BLUE_SOFT}", width=16 if compact else 20)
        table.add_column("Count", style=self.theme.MINT_SOFT, width=7, justify="right")
        table.add_column("Sample Tools", style=self.theme.TEXT_SECONDARY, ratio=1)

        for group_name, tools in sorted(mapping.items()):
            sample = ", ".join(str(item) for item in (tools or [])[:5])
            if len(tools or []) > 5:
                sample = f"{sample}, +{len(tools) - 5} more"
            table.add_row(str(group_name or "general"), str(len(tools or [])), sample or "(none)")
        return table

    def _build_tools_shortcuts_table(self) -> Table:
        """Build the `/tools` shortcut reference."""
        return self._build_command_table(
            [
                ("/tools", "Show the mode-aware tool overview with quick picks and groups"),
                ("/tools all", "Show every loaded tool across modes with mode visibility and parameters"),
                ("/tools details", "Show detailed tool information for the current or selected mode"),
                ("/tools search <query>", "Keyword search against visible tool names, aliases, tags, and parameters"),
                ("/tools recommend <task>", "Get intent-ranked tool suggestions for a task description"),
                ("/tools inspect <tool>", "Inspect one tool or alias with supported modes and schema"),
                ("/tools groups", "Summarize the current mode's categories and runtime kinds"),
                ("/tools --mode <mode>", "Preview another mode's tool surface without switching the session"),
            ],
            title="Tool Browser Shortcuts",
            accent=self.theme.BORDER_SECONDARY,
        )

    _TOOL_LIST_LABELS: Dict[str, tuple[str, str]] = {
        "codebase-retrieval": ("Search Code", "codebase-retrieval"),
        "command_exec": ("Shell", "command_exec"),
        "count_tokens": ("Count Tokens", "count_tokens"),
        "create_file": ("WriteFile", "create_file"),
        "delete_file": ("DeleteFile", "delete_file"),
        "file_ops": ("File Ops", "file_ops"),
        "git-commit-retrieval": ("Search Git History", "git-commit-retrieval"),
        "list_mcp_resources": ("List MCP Resources", "list_mcp_resources"),
        "read_mcp_resource": ("Read MCP Resource", "read_mcp_resource"),
        "skill_lookup": ("Activate Skill", "skill_lookup"),
        "str_replace_editor": ("Edit", "str_replace_editor"),
        "subagent": ("Invoke Subagent", "subagent"),
        "switch_mode": ("Switch Mode", "switch_mode"),
        "task_manager": ("WriteTodos", "task_manager"),
        "text_to_image": ("Generate Image", "text_to_image"),
        "tool_catalog": ("List Tools", "tool_catalog"),
        "userInput": ("Ask User", "ask_user"),
        "vision_upload": ("Vision Upload", "vision_upload"),
        "web_search": ("WebSearch", "web_search"),
    }

    def _get_tool_records_for_cli(self, agent: Any, mode: str) -> List[Dict[str, Any]]:
        """Fetch normalized tool records without building heavyweight catalog text."""
        tool = ToolCatalogTool({"agent": agent, "project_root": self.app.get("project_root")})
        try:
            return tool.list_visible_records(mode)
        except Exception:
            result = self._execute_tool_catalog(agent, operation="list", mode=mode, max_results=200)
            data = result.data if result.success and isinstance(result.data, dict) else {}
            return list(data.get("items", []) or [])

    def _get_all_tool_records_for_cli(self, agent: Any) -> List[Dict[str, Any]]:
        """Fetch a union of tools visible across all registered modes."""
        tool = ToolCatalogTool({"agent": agent, "project_root": self.app.get("project_root")})
        merged: Dict[str, Dict[str, Any]] = {}
        for mode_name in list_modes(include_computer=True, switchable_only=False):
            normalized_mode = normalize_mode(mode_name)
            try:
                records = tool.list_visible_records(normalized_mode)
            except Exception:
                records = []
            for record in records:
                name = str(record.get("name", "") or "").strip()
                if not name:
                    continue
                existing = merged.setdefault(name, dict(record))
                visible_modes = set(existing.get("visible_modes", []) or [])
                visible_modes.add(normalized_mode)
                supported_modes = {
                    str(item).strip()
                    for item in (record.get("supported_modes", []) or existing.get("supported_modes", []) or [])
                    if str(item).strip()
                }
                if supported_modes:
                    visible_modes |= supported_modes
                existing["visible_modes"] = sorted(visible_modes)
                if not existing.get("description") and record.get("description"):
                    existing["description"] = record.get("description")
                if not existing.get("properties") and record.get("properties"):
                    existing["properties"] = record.get("properties")
                if not existing.get("required") and record.get("required"):
                    existing["required"] = record.get("required")
        return sorted(merged.values(), key=lambda item: str(item.get("name", "")).lower())

    def _get_total_tool_count_for_cli(self, agent: Any, fallback: int) -> int:
        """Return loaded tool count across all modes for compact totals."""
        executor = getattr(agent, "tool_executor", None)
        if executor and callable(getattr(executor, "list_tools", None)):
            try:
                return max(len(executor.list_tools(mode=None)), fallback)
            except Exception:
                return fallback
        return fallback

    def _format_cli_tool_name(self, item: Dict[str, Any]) -> tuple[str, str]:
        """Return the concise display label and invocation name for `/tools`."""
        name = str(item.get("name", "") or "").strip()
        label, invocation = self._TOOL_LIST_LABELS.get(name, ("", ""))
        if not label:
            label = re.sub(r"[^A-Za-z0-9]+", " ", name).strip().title().replace(" ", "") or name or "Tool"
        if not invocation:
            invocation = name
        return label, invocation

    def _build_tools_plain_list(
        self,
        items: List[Dict[str, Any]],
        *,
        mode: str,
        total_tool_count: int,
    ) -> Group:
        """Build the simplified `/tools` list."""
        body = Text()
        body.append("Available Reverie CLI tools:\n", style=f"bold {self.theme.TEXT_PRIMARY}")

        formatted: List[tuple[str, str]] = []
        seen: set[str] = set()
        for item in items:
            label, invocation = self._format_cli_tool_name(item)
            key = f"{label}\0{invocation}".lower()
            if key in seen:
                continue
            formatted.append((label, invocation))
            seen.add(key)

        formatted.sort(key=lambda pair: (pair[0].lower(), pair[1].lower()))
        if not formatted:
            body.append("\n  - No tools are currently visible in this mode.\n", style=self.theme.TEXT_DIM)
        else:
            for label, invocation in formatted:
                body.append("\n  - ", style=self.theme.TEXT_DIM)
                body.append(label, style=f"bold {self.theme.TEXT_PRIMARY}")
                body.append(f" ({invocation})", style=self.theme.TEXT_SECONDARY)
            body.append("\n")

        current_count = len(formatted)
        total_count = max(int(total_tool_count or 0), current_count)
        footer = Text()
        footer.append("All tools: ", style=f"bold {self.theme.TEXT_PRIMARY}")
        footer.append(f"{current_count} listed for {get_mode_display_name(mode)}", style=self.theme.TEXT_SECONDARY)
        footer.append("\n")
        footer.append("Total: ", style=f"bold {self.theme.TEXT_PRIMARY}")
        footer.append(f"{current_count}/{total_count} tools available in current mode", style=self.theme.TEXT_SECONDARY)
        footer.append("\n")
        footer.append("Use /tools all, /tools details, /tools search <query>, /tools inspect <tool>, or /tools --mode <mode> for narrower views.", style=self.theme.TEXT_DIM)
        return Group(body, Text(""), footer)

    def _render_tools_overview(self, agent: Any, mode: str) -> bool:
        """Render the default `/tools` overview page."""
        self._show_command_panel(
            "Tools",
            subtitle="Live tool surface for the selected mode, powered by the shared discovery catalog.",
            accent=self.theme.BORDER_PRIMARY,
            meta=f"{get_mode_display_name(mode)}  {self.deco.DOT_MEDIUM}  {mode}",
        )

        try:
            items = self._get_tool_records_for_cli(agent, mode)
        except Exception as exc:
            self._show_activity_event(
                "Tools",
                "Tool catalog could not load the visible tool surface.",
                status="error",
                detail=str(exc),
            )
            self.console.print()
            return True

        total_tool_count = self._get_total_tool_count_for_cli(agent, len(items))
        self.console.print(self._build_tools_plain_list(items, mode=mode, total_tool_count=total_tool_count))
        self.console.print()
        return True

    def _render_tools_details(self, agent: Any, mode: str) -> bool:
        """Render `/tools details` for the selected mode."""
        self._show_command_panel(
            "Tool Details",
            subtitle="Detailed schema-adjacent tool surface for the selected mode.",
            accent=self.theme.BORDER_PRIMARY,
            meta=f"{get_mode_display_name(mode)}  {self.deco.DOT_MEDIUM}  {mode}",
        )
        try:
            items = self._get_tool_records_for_cli(agent, mode)
        except Exception as exc:
            self._show_activity_event(
                "Tools",
                "Tool catalog could not load detailed records.",
                status="error",
                detail=str(exc),
            )
            self.console.print()
            return True

        self.console.print(f"[{self.theme.TEXT_DIM}]Details include Required fields, Parameters, mode/kind/category, and descriptions.[/{self.theme.TEXT_DIM}]")
        self.console.print()
        self.console.print(
            self._build_tool_details_table(
                items,
                title=f"{get_mode_display_name(mode)} Tools",
                accent=self.theme.BORDER_PRIMARY,
                show_modes=False,
            )
        )
        self.console.print()
        return True

    def _render_tools_all(self, agent: Any, mode: str) -> bool:
        """Render `/tools all` with a union across every mode."""
        self._show_command_panel(
            "All Tools",
            subtitle="Complete tool inventory across built-in, MCP, and runtime-plugin surfaces.",
            accent=self.theme.BORDER_PRIMARY,
            meta=f"Current mode: {get_mode_display_name(mode)}  {self.deco.DOT_MEDIUM}  {mode}",
        )
        try:
            items = self._get_all_tool_records_for_cli(agent)
        except Exception as exc:
            self._show_activity_event(
                "Tools",
                "Tool catalog could not load the full inventory.",
                status="error",
                detail=str(exc),
            )
            self.console.print()
            return True

        self.console.print(f"[{self.theme.TEXT_DIM}]Details include Required fields, Parameters, mode/kind/category, and descriptions.[/{self.theme.TEXT_DIM}]")
        self.console.print()
        self.console.print(
            self._build_tool_details_table(
                items,
                title=f"All Tools ({len(items)})",
                accent=self.theme.BORDER_PRIMARY,
                show_modes=True,
            )
        )
        self.console.print()
        return True

    def _render_tools_groups(self, agent: Any, mode: str) -> bool:
        """Render `/tools groups`."""
        result = self._execute_tool_catalog(agent, operation="groups", mode=mode)
        if not result.success:
            self._show_activity_event(
                "Tools",
                "Could not summarize the tool groups.",
                status="error",
                detail=str(result.error or ""),
            )
            return True

        data = result.data if isinstance(result.data, dict) else {}
        self._show_command_panel(
            "Tool Groups",
            subtitle="Category and runtime grouping for the selected mode.",
            accent=self.theme.BORDER_PRIMARY,
            meta=f"{get_mode_display_name(mode)}  {self.deco.DOT_MEDIUM}  {mode}",
        )
        self.console.print(
            Columns(
                [
                    self._build_metric_panel(
                        "Visible",
                        data.get("count", 0),
                        accent=self.theme.MINT_VIBRANT,
                        detail="tools in this mode",
                    ),
                    self._build_metric_panel(
                        "Categories",
                        len(data.get("by_category", {}) or {}),
                        accent=self.theme.BLUE_SOFT,
                        detail="mode groupings",
                    ),
                    self._build_metric_panel(
                        "Kinds",
                        len(data.get("by_kind", {}) or {}),
                        accent=self.theme.PURPLE_SOFT,
                        detail="built-in, MCP, plugin...",
                    ),
                ],
                equal=True,
                expand=True,
            )
        )
        self.console.print()
        self.console.print(
            Columns(
                [
                    self._build_tool_group_table(
                        data.get("by_category", {}) or {},
                        title="By Category",
                        accent=self.theme.BLUE_SOFT,
                        label="Category",
                    ),
                    self._build_tool_group_table(
                        data.get("by_kind", {}) or {},
                        title="By Kind",
                        accent=self.theme.PINK_SOFT,
                        label="Kind",
                    ),
                ],
                equal=True,
                expand=True,
            )
        )
        self.console.print()
        return True

    def _render_tools_search(self, agent: Any, mode: str, query: str) -> bool:
        """Render `/tools search`."""
        if not query:
            self._show_activity_event(
                "Tools",
                "Search needs a keyword or task description.",
                status="warning",
                detail="Example: `/tools search vertical slice telemetry --mode reverie-gamer`",
            )
            return True

        result = self._execute_tool_catalog(agent, operation="search", mode=mode, query=query, max_results=12)
        if not result.success:
            self._show_activity_event(
                "Tools",
                "Tool search failed.",
                status="error",
                detail=str(result.error or ""),
            )
            return True

        data = result.data if isinstance(result.data, dict) else {}
        self._show_command_panel(
            "Tool Search",
            subtitle=f"Search results for `{query}` in the selected mode.",
            accent=self.theme.BORDER_PRIMARY,
            meta=f"{get_mode_display_name(mode)}  {self.deco.DOT_MEDIUM}  {mode}",
        )
        self.console.print(
            self._build_key_value_table(
                [
                    ("Mode", f"{get_mode_display_name(mode)} ({mode})"),
                    ("Query", query),
                    ("Matches", data.get("count", 0)),
                ]
            )
        )
        self.console.print()
        items = data.get("items", []) or []
        if items:
            self.console.print(
                self._build_tool_items_table(
                    items,
                    title="Matches",
                    accent=self.theme.BORDER_PRIMARY,
                    detail_label="Aliases",
                    detail_key="aliases",
                )
            )
        else:
            self._show_activity_event(
                "Tools",
                "No matching tools were found.",
                status="warning",
                detail="Try broader keywords or `/tools recommend <task>` for intent-based suggestions.",
            )
        self.console.print()
        return True

    def _render_tools_recommend(self, agent: Any, mode: str, query: str) -> bool:
        """Render `/tools recommend`."""
        if not query:
            self._show_activity_event(
                "Tools",
                "Recommendations need a short task description.",
                status="warning",
                detail="Example: `/tools recommend inspect MCP docs --mode reverie-atlas`",
            )
            return True

        result = self._execute_tool_catalog(agent, operation="recommend", mode=mode, query=query, max_results=8)
        if not result.success:
            self._show_activity_event(
                "Tools",
                "Tool recommendation failed.",
                status="error",
                detail=str(result.error or ""),
            )
            return True

        data = result.data if isinstance(result.data, dict) else {}
        self._show_command_panel(
            "Tool Recommendations",
            subtitle=f"Intent-ranked suggestions for `{query}`.",
            accent=self.theme.BORDER_PRIMARY,
            meta=f"{get_mode_display_name(mode)}  {self.deco.DOT_MEDIUM}  {mode}",
        )
        self.console.print(
            self._build_key_value_table(
                [
                    ("Mode", f"{get_mode_display_name(mode)} ({mode})"),
                    ("Task", query),
                    ("Candidates", data.get("count", 0)),
                ]
            )
        )
        self.console.print()
        items = data.get("items", []) or []
        if items:
            self.console.print(
                self._build_tool_items_table(
                    items,
                    title="Recommendations",
                    accent=self.theme.PURPLE_SOFT,
                    detail_label="Why",
                    detail_key="reasons",
                )
            )
        else:
            self._show_activity_event(
                "Tools",
                "No strong recommendations were found.",
                status="warning",
                detail="Try `/tools search <keywords>` or inspect the full mode surface with bare `/tools`.",
            )
        self.console.print()
        return True

    def _render_tools_inspect(self, agent: Any, mode: str, tool_name: str) -> bool:
        """Render `/tools inspect`."""
        if not tool_name:
            self._show_activity_event(
                "Tools",
                "Inspect needs a tool name or alias.",
                status="warning",
                detail="Example: `/tools inspect shell` or `/tools inspect game_design_orchestrator --mode reverie-gamer`",
            )
            return True

        result = self._execute_tool_catalog(
            agent,
            operation="inspect",
            mode=mode,
            tool_name=tool_name,
            include_schema=True,
        )
        if not result.success:
            self._show_activity_event(
                "Tools",
                f"Could not inspect `{tool_name}` in this mode.",
                status="error",
                detail=str(result.error or ""),
            )
            return True

        data = result.data if isinstance(result.data, dict) else {}
        self._show_command_panel(
            "Tool Inspection",
            subtitle="Deep capability, schema, and mode-visibility view for one tool.",
            accent=self.theme.BORDER_PRIMARY,
            meta=f"{data.get('name', tool_name)}  {self.deco.DOT_MEDIUM}  {get_mode_display_name(mode)}",
        )
        self.console.print(
            self._build_key_value_table(
                [
                    ("Name", data.get("name", tool_name)),
                    ("Mode", f"{get_mode_display_name(mode)} ({mode})"),
                    ("Kind", data.get("kind", "")),
                    ("Category", data.get("category", "")),
                    ("Supported Modes", ", ".join(data.get("supported_modes", []) or []) or "(dynamic or runtime-managed)"),
                    ("Aliases", ", ".join(data.get("aliases", []) or []) or "(none)"),
                    ("Tags", ", ".join(data.get("tags", []) or []) or "(none)"),
                    ("Traits", ", ".join(data.get("traits", []) or []) or "(none)"),
                    ("Search Hint", data.get("search_hint", "") or "(none)"),
                    ("Required", ", ".join(data.get("required", []) or []) or "(none)"),
                ]
            )
        )
        self.console.print()

        properties = data.get("properties", {}) or {}
        if properties:
            parameter_table = Table(
                title=f"[bold {self.theme.BLUE_SOFT}]{self.deco.CRYSTAL} Parameters[/bold {self.theme.BLUE_SOFT}]",
                box=box.ROUNDED,
                border_style=self.theme.BORDER_PRIMARY,
                expand=True,
            )
            parameter_table.add_column("Parameter", style=f"bold {self.theme.PINK_SOFT}", width=18)
            parameter_table.add_column("Type", style=self.theme.BLUE_SOFT, width=14)
            parameter_table.add_column("Requirement", style=self.theme.PURPLE_SOFT, width=12)
            parameter_table.add_column("Description", style=self.theme.TEXT_SECONDARY)
            required = set(data.get("required", []) or [])
            for parameter_name, parameter_schema in properties.items():
                schema = parameter_schema if isinstance(parameter_schema, dict) else {}
                description = str(schema.get("description", "") or "").strip() or "(no description)"
                enum_values = schema.get("enum")
                enum_hint = ""
                if isinstance(enum_values, list) and enum_values:
                    preview = ", ".join(str(item) for item in enum_values[:4])
                    if len(enum_values) > 4:
                        preview = f"{preview}, +{len(enum_values) - 4} more"
                    enum_hint = f" | {preview}"
                parameter_table.add_row(
                    str(parameter_name),
                    str(schema.get("type", "any") or "any"),
                    "required" if parameter_name in required else "optional",
                    self._truncate_middle(f"{description}{enum_hint}", 110 if self._is_compact(124) else 160),
                )
            self.console.print(parameter_table)
            self.console.print()

        schema = data.get("schema")
        if schema:
            self.console.print(
                Panel(
                    Syntax(
                        json.dumps(schema, indent=2, ensure_ascii=False),
                        "json",
                        line_numbers=False,
                        word_wrap=True,
                    ),
                    title=f"[bold {self.theme.PURPLE_SOFT}]{self.deco.DIAMOND} Schema[/bold {self.theme.PURPLE_SOFT}]",
                    border_style=self.theme.BORDER_SUBTLE,
                    box=box.ROUNDED,
                    padding=(0, 1),
                )
            )
            self.console.print()
        return True

    def _get_mcp_services(self):
        manager = self.app.get('mcp_config_manager')
        runtime = self.app.get('mcp_runtime')
        if not manager or not runtime:
            self._show_activity_event(
                "MCP",
                "MCP runtime is not available.",
                status="error",
                detail="Restart Reverie after updating to a build that includes MCP support.",
            )
            return None, None
        return manager, runtime

    def _refresh_mcp_runtime(self, *, force_reload: bool = False) -> tuple[Any, Any] | tuple[None, None]:
        manager, runtime = self._get_mcp_services()
        if not manager or not runtime:
            return None, None

        runtime.reload(force=force_reload)
        refresh_prompt = self.app.get('refresh_agent_prompt_guidance')
        if callable(refresh_prompt):
            try:
                refresh_prompt()
            except Exception:
                pass
        return manager, runtime

    def _resolve_mcp_server_name(self, server_name: str, config: Dict[str, Any]) -> str:
        wanted = str(server_name or "").strip()
        if not wanted:
            return ""
        for existing in (config.get("mcpServers", {}) or {}).keys():
            if str(existing).strip().lower() == wanted.lower():
                return str(existing)
        return wanted

    def _shorten_mcp_text(self, value: Any, max_length: int = 72) -> str:
        text = str(value or "").strip()
        if len(text) <= max_length:
            return text
        if max_length <= 3:
            return text[:max_length]
        return f"{text[:max_length - 3]}..."

    def _summarize_mcp_target(self, server_cfg: Dict[str, Any]) -> str:
        server_type = str(server_cfg.get("type", "stdio") or "stdio").strip().lower()
        if server_type == "stdio":
            command = str(server_cfg.get("command", "") or "").strip()
            args = [str(arg).strip() for arg in (server_cfg.get("args", []) or []) if str(arg).strip()]
            command_line = " ".join([command, *args]).strip()
            return command_line or "(command not set)"
        if server_type == "http":
            return str(server_cfg.get("httpUrl", "") or server_cfg.get("url", "") or "").strip() or "(URL not set)"
        return str(server_cfg.get("url", "") or server_cfg.get("httpUrl", "") or "").strip() or "(URL not set)"

    def _load_mcp_ui_state(self, manager, runtime, *, force_refresh: bool = False) -> tuple[Dict[str, Any], List[Dict[str, Any]]]:
        config = manager.load()
        rows = runtime.list_server_status(force_refresh=force_refresh)
        return config, rows

    def _save_mcp_ui_config(
        self,
        manager,
        runtime,
        config: Dict[str, Any],
        *,
        force_refresh: bool = False,
    ) -> tuple[Dict[str, Any], List[Dict[str, Any]]]:
        manager.save(config)
        runtime.reload(force=True)
        refresh_prompt = self.app.get('refresh_agent_prompt_guidance')
        if callable(refresh_prompt):
            try:
                refresh_prompt()
            except Exception:
                pass
        return self._load_mcp_ui_state(manager, runtime, force_refresh=force_refresh)

    def _get_mcp_ui_items(self, config: Dict[str, Any], rows: List[Dict[str, Any]], manager) -> List[Dict[str, Any]]:
        from ..mcp import normalize_mcp_server_config

        mcp_cfg = dict(config.get("mcp", {}) or {})
        items: List[Dict[str, Any]] = [
            {
                "name": "MCP Enabled",
                "kind": "global-bool",
                "description": "Master switch for all configured MCP servers and dynamic MCP tools.",
                "command": "/mcp",
                "value": bool(mcp_cfg.get("enabled", True)),
            },
            {
                "name": "Discovery Timeout",
                "kind": "global-int",
                "description": "Timeout used while discovering tools, resources, and prompts from each server.",
                "command": "Edit in panel or .reverie/mcp.json",
                "value": int(mcp_cfg.get("discovery_timeout_ms", 15000) or 15000),
                "min": 1000,
                "max": 600000,
                "step": 5000,
            },
            {
                "name": "Refresh Discovery",
                "kind": "action",
                "action": "refresh",
                "description": "Re-run MCP discovery for enabled servers and refresh tool counts/errors.",
                "command": "/mcp reload",
            },
            {
                "name": "Add Server",
                "kind": "action",
                "action": "add",
                "description": "Create a new stdio, streamable HTTP, or legacy SSE MCP server entry.",
                "command": "/mcp add ...",
            },
            {
                "name": "Config Path",
                "kind": "readonly",
                "description": "Persisted MCP configuration file used by Reverie.",
                "command": "/mcp path",
                "value": str(manager.get_config_path()),
            },
        ]

        server_entries = config.get("mcpServers", {}) or {}
        for row in rows:
            server_name = str(row.get("name", "") or "").strip()
            if not server_name:
                continue
            raw_server_cfg = server_entries.get(server_name, {})
            server_cfg = normalize_mcp_server_config(server_name, raw_server_cfg)
            items.append(
                {
                    "name": server_name,
                    "kind": "server",
                    "description": "Configured MCP server. Use quick actions to enable, trust, refresh, or remove it.",
                    "command": "/mcp enable|disable|trust|remove",
                    "server_name": server_name,
                    "state": str(row.get("state", "unknown") or "unknown"),
                    "transport": str(row.get("type", server_cfg.get("type", "stdio")) or "stdio"),
                    "trust": bool(row.get("trust", server_cfg.get("trust", False))),
                    "enabled": bool(server_cfg.get("enabled", True)),
                    "tools": row.get("tools"),
                    "resources": row.get("resources"),
                    "prompts": row.get("prompts"),
                    "notes": str(row.get("error", "") or "").strip(),
                    "target": self._summarize_mcp_target(server_cfg),
                }
            )

        return items

    def _mcp_display_value(self, item: Dict[str, Any]) -> str:
        kind = str(item.get("kind", "")).strip()
        if kind == "global-bool":
            return f"[{self.theme.MINT_SOFT}]ON[/{self.theme.MINT_SOFT}]" if bool(item.get("value")) else f"[{self.theme.TEXT_DIM}]OFF[/{self.theme.TEXT_DIM}]"
        if kind == "global-int":
            return f"{int(item.get('value', 0) or 0):,} ms"
        if kind == "readonly":
            return escape(self._shorten_mcp_text(item.get("value", ""), max_length=60))
        if kind == "action":
            action = str(item.get("action", "")).strip().lower()
            label = "Run now" if action == "refresh" else "Open prompt"
            return f"[{self.theme.BLUE_SOFT}]{label}[/{self.theme.BLUE_SOFT}]"
        if kind == "server":
            state = str(item.get("state", "unknown") or "unknown")
            enabled_label = "ON" if bool(item.get("enabled", True)) else "OFF"
            enabled_style = self.theme.MINT_SOFT if bool(item.get("enabled", True)) else self.theme.TEXT_DIM
            trust_label = "trusted" if bool(item.get("trust")) else "confirm"
            transport = str(item.get("transport", "stdio") or "stdio")
            tools = item.get("tools")
            tools_label = "-" if tools is None else str(tools)
            state_style = self.theme.MINT_VIBRANT if state == "enabled" else (self.theme.TEXT_DIM if state == "disabled" else self.theme.AMBER_GLOW)
            return (
                f"[{enabled_style}]{enabled_label}[/{enabled_style}] · "
                f"[{self.theme.TEXT_PRIMARY}]{escape(transport)}[/{self.theme.TEXT_PRIMARY}] · "
                f"[{self.theme.PURPLE_SOFT}]{escape(trust_label)}[/{self.theme.PURPLE_SOFT}] · "
                f"[{self.theme.BLUE_SOFT}]{escape(tools_label)} tools[/{self.theme.BLUE_SOFT}] · "
                f"[{state_style}]{escape(state)}[/{state_style}]"
            )
        return f"[{self.theme.TEXT_DIM}](n/a)[/{self.theme.TEXT_DIM}]"

    def _build_mcp_summary_panel(self, config: Dict[str, Any], rows: List[Dict[str, Any]], manager, *, selected_item: Optional[Dict[str, Any]] = None, changed: bool = False) -> Panel:
        total_servers = len(rows)
        enabled_servers = sum(1 for row in rows if str(row.get("state", "")).strip().lower() == "enabled")
        trusted_servers = sum(1 for row in rows if bool(row.get("trust", False)))
        total_tools = sum(int(row.get("tools") or 0) for row in rows if row.get("tools") is not None)
        focus_label = str((selected_item or {}).get("name", "") or "MCP Enabled").strip()
        state_label = "Updated this session" if changed else "Live view"
        state_style = self.theme.AMBER_GLOW if changed else self.theme.MINT_SOFT
        global_enabled = bool((config.get("mcp", {}) or {}).get("enabled", True))

        summary = Table(box=box.SIMPLE, show_header=False, pad_edge=False)
        summary.add_column(style=self.theme.TEXT_DIM, width=14)
        summary.add_column(style=f"bold {self.theme.TEXT_PRIMARY}")
        summary.add_column(style=self.theme.TEXT_DIM, width=14)
        summary.add_column(style=f"bold {self.theme.TEXT_PRIMARY}")
        summary.add_row("Global MCP", "ON" if global_enabled else "OFF", "Config", str(manager.get_config_path()))
        summary.add_row("Servers", str(total_servers), "Enabled", str(enabled_servers))
        summary.add_row("Trusted", str(trusted_servers), "Tools", str(total_tools))
        summary.add_row("Focus", escape(focus_label), "State", f"[{state_style}]{state_label}[/{state_style}]")

        return Panel(
            summary,
            title=f"[bold {self.theme.PINK_SOFT}]{self.deco.SPARKLE} Reverie MCP {self.deco.SPARKLE}[/bold {self.theme.PINK_SOFT}]",
            subtitle=f"[{self.theme.TEXT_DIM}]Interactive control panel for MCP servers, discovery, and dynamic tool exposure.[/{self.theme.TEXT_DIM}]",
            border_style=self.theme.BORDER_PRIMARY,
            padding=(0, 2),
            box=box.ROUNDED,
        )

    def _build_mcp_list_panel(self, items: List[Dict[str, Any]], selected_idx: int) -> Panel:
        table = Table(box=box.SIMPLE, show_header=True, pad_edge=False)
        table.add_column("#", style=self.theme.TEXT_DIM, width=4, justify="right")
        table.add_column("Item", style=f"bold {self.theme.BLUE_SOFT}", width=24)
        table.add_column("Value", style=self.theme.TEXT_PRIMARY)

        for index, item in enumerate(items):
            is_selected = index == selected_idx
            marker = f"{self.deco.CHEVRON_RIGHT}" if is_selected else " "
            item_name = f"{marker} {item['name']}"
            value_text = self._mcp_display_value(item)
            if is_selected:
                table.add_row(
                    f"[{self.theme.TEXT_DIM}]{index + 1}[/{self.theme.TEXT_DIM}]",
                    f"[bold {self.theme.PINK_SOFT}]{escape(item_name)}[/bold {self.theme.PINK_SOFT}]",
                    f"[reverse]{value_text}[/reverse]",
                )
            else:
                table.add_row(str(index + 1), escape(item_name), value_text)

        return Panel(
            table,
            title=f"[bold {self.theme.BLUE_SOFT}]{self.deco.DIAMOND} MCP Items[/bold {self.theme.BLUE_SOFT}]",
            border_style=self.theme.BORDER_SUBTLE,
            padding=(0, 1),
            box=box.ROUNDED,
        )

    def _build_mcp_detail_panel(self, item: Dict[str, Any]) -> Panel:
        kind = str(item.get("kind", "")).strip()
        description = str(item.get("description", "")).strip()
        command = str(item.get("command", "")).strip()

        detail_lines = [
            f"[bold {self.theme.PURPLE_SOFT}]{escape(str(item.get('name', 'MCP')))}[/bold {self.theme.PURPLE_SOFT}]",
            f"[{self.theme.TEXT_SECONDARY}]{escape(description)}[/{self.theme.TEXT_SECONDARY}]",
            "",
            f"[{self.theme.TEXT_DIM}]Current[/{self.theme.TEXT_DIM}] {self._mcp_display_value(item)}",
        ]

        if kind == "global-int":
            detail_lines.append(f"[{self.theme.TEXT_DIM}]Range[/{self.theme.TEXT_DIM}] {item.get('min', 1000)} - {item.get('max', 600000)} ms")
            detail_lines.append(f"[{self.theme.TEXT_DIM}]Step[/{self.theme.TEXT_DIM}] {item.get('step', 5000)} ms")
        elif kind == "readonly":
            detail_lines.append(f"[{self.theme.TEXT_DIM}]Path[/{self.theme.TEXT_DIM}] {escape(str(item.get('value', '')))}")
        elif kind == "action":
            if str(item.get("action", "")).strip().lower() == "refresh":
                detail_lines.append(f"[{self.theme.TEXT_DIM}]Behavior[/{self.theme.TEXT_DIM}] Re-runs discovery for enabled servers and updates notes/counts.")
            else:
                detail_lines.append(f"[{self.theme.TEXT_DIM}]Behavior[/{self.theme.TEXT_DIM}] Prompts for transport, name, and target, then saves the server into `.reverie/mcp.json`.")
        elif kind == "server":
            notes = str(item.get("notes", "") or "").strip() or "ready"
            detail_lines.extend(
                [
                    f"[{self.theme.TEXT_DIM}]Transport[/{self.theme.TEXT_DIM}] {escape(str(item.get('transport', 'stdio')))}",
                    f"[{self.theme.TEXT_DIM}]State[/{self.theme.TEXT_DIM}] {escape(str(item.get('state', 'unknown')))}",
                    f"[{self.theme.TEXT_DIM}]Trust[/{self.theme.TEXT_DIM}] {'trusted' if bool(item.get('trust')) else 'confirmation-required'}",
                    f"[{self.theme.TEXT_DIM}]Target[/{self.theme.TEXT_DIM}] {escape(str(item.get('target', '')))}",
                    f"[{self.theme.TEXT_DIM}]Discovery[/{self.theme.TEXT_DIM}] tools={item.get('tools', '-')}, resources={item.get('resources', '-')}, prompts={item.get('prompts', '-')}",
                    f"[{self.theme.TEXT_DIM}]Notes[/{self.theme.TEXT_DIM}] {escape(notes)}",
                ]
            )

        detail_lines.extend(
            [
                "",
                f"[{self.theme.TEXT_DIM}]Quick adjust[/{self.theme.TEXT_DIM}] h/l toggles enabled rows or adjusts numeric values.",
                f"[{self.theme.TEXT_DIM}]Fast actions[/{self.theme.TEXT_DIM}] t toggles trust, a adds a server, r refreshes discovery, x removes the selected server.",
                f"[{self.theme.TEXT_DIM}]Command equivalent[/{self.theme.TEXT_DIM}] {escape(command)}",
            ]
        )

        return Panel(
            Text.from_markup("\n".join(detail_lines)),
            title=f"[bold {self.theme.PURPLE_SOFT}]{self.deco.DIAMOND} Details[/bold {self.theme.PURPLE_SOFT}]",
            border_style=self.theme.BORDER_SUBTLE,
            padding=(1, 2),
            box=box.ROUNDED,
        )

    def _build_mcp_footer_panel(self, *, changed: bool, selected_idx: int, total_items: int) -> Panel:
        footer_grid = Table.grid(expand=True)
        footer_grid.add_column(ratio=1)
        footer_grid.add_column(justify="right", no_wrap=True)
        footer_grid.add_row(
            Text.from_markup(
                f"[{self.theme.TEXT_DIM}]"
                f"{self.deco.DOT_MEDIUM} ↑/↓ or j/k: Navigate  "
                f"{self.deco.DOT_MEDIUM} ←/→ or h/l: Quick change  "
                f"{self.deco.DOT_MEDIUM} t: Trust  "
                f"{self.deco.DOT_MEDIUM} a: Add  "
                f"{self.deco.DOT_MEDIUM} r: Refresh  "
                f"{self.deco.DOT_MEDIUM} x: Remove  "
                f"{self.deco.DOT_MEDIUM} Enter: Edit  "
                f"{self.deco.DOT_MEDIUM} Esc: Exit"
                f"[/{self.theme.TEXT_DIM}]"
            ),
            Text(
                f"{selected_idx + 1}/{max(1, total_items)} · {'updated' if changed else 'ready'}",
                style=self.theme.AMBER_GLOW if changed else self.theme.TEXT_DIM,
            ),
        )
        return Panel(
            footer_grid,
            border_style=self.theme.BORDER_SUBTLE,
            padding=(0, 1),
            box=box.ROUNDED,
        )

    def _render_mcp_ui(self, config: Dict[str, Any], rows: List[Dict[str, Any]], manager, selected_idx: int, *, changed: bool = False) -> Group:
        items = self._get_mcp_ui_items(config, rows, manager)
        selected_idx = max(0, min(selected_idx, max(0, len(items) - 1)))
        selected_item = items[selected_idx]
        summary_panel = self._build_mcp_summary_panel(config, rows, manager, selected_item=selected_item, changed=changed)
        list_panel = self._build_mcp_list_panel(items, selected_idx)
        detail_panel = self._build_mcp_detail_panel(selected_item)
        footer_panel = self._build_mcp_footer_panel(changed=changed, selected_idx=selected_idx, total_items=len(items))

        width = int(getattr(self.console.size, "width", 0) or self.console.width or 0)
        if width >= 92:
            body = Columns([list_panel, detail_panel], expand=True, equal=False)
        else:
            body = Group(list_panel, detail_panel)
        return Group(summary_panel, body, footer_panel)

    def _mcp_step_item(self, item: Dict[str, Any], config: Dict[str, Any], manager, runtime, direction: int) -> tuple[bool, Dict[str, Any], List[Dict[str, Any]]]:
        from ..mcp import normalize_mcp_config

        working = normalize_mcp_config(config)
        kind = str(item.get("kind", "")).strip()
        if kind == "global-bool":
            working.setdefault("mcp", {})["enabled"] = not bool(working.get("mcp", {}).get("enabled", True))
            new_config, new_rows = self._save_mcp_ui_config(manager, runtime, working, force_refresh=False)
            return True, new_config, new_rows
        if kind == "global-int":
            step = int(item.get("step", 5000))
            min_value = int(item.get("min", 1000))
            max_value = int(item.get("max", 600000))
            current = int((working.get("mcp", {}) or {}).get("discovery_timeout_ms", 15000) or 15000)
            updated = max(min_value, min(max_value, current + (step * direction)))
            working.setdefault("mcp", {})["discovery_timeout_ms"] = updated
            new_config, new_rows = self._save_mcp_ui_config(manager, runtime, working, force_refresh=False)
            return True, new_config, new_rows
        if kind == "server":
            resolved = self._resolve_mcp_server_name(str(item.get("server_name", "")), working)
            entry = (working.get("mcpServers", {}) or {}).get(resolved)
            if not isinstance(entry, dict):
                return False, config, self._load_mcp_ui_state(manager, runtime, force_refresh=False)[1]
            entry["enabled"] = not bool(entry.get("enabled", True))
            working["mcpServers"][resolved] = entry
            new_config, new_rows = self._save_mcp_ui_config(manager, runtime, working, force_refresh=False)
            return True, new_config, new_rows
        return False, config, self._load_mcp_ui_state(manager, runtime, force_refresh=False)[1]

    def _mcp_toggle_selected_trust(self, item: Dict[str, Any], config: Dict[str, Any], manager, runtime) -> tuple[bool, Dict[str, Any], List[Dict[str, Any]]]:
        from ..mcp import normalize_mcp_config

        if str(item.get("kind", "")).strip() != "server":
            return False, config, self._load_mcp_ui_state(manager, runtime, force_refresh=False)[1]

        working = normalize_mcp_config(config)
        resolved = self._resolve_mcp_server_name(str(item.get("server_name", "")), working)
        entry = (working.get("mcpServers", {}) or {}).get(resolved)
        if not isinstance(entry, dict):
            return False, config, self._load_mcp_ui_state(manager, runtime, force_refresh=False)[1]

        entry["trust"] = not bool(entry.get("trust", False))
        working["mcpServers"][resolved] = entry
        new_config, new_rows = self._save_mcp_ui_config(manager, runtime, working, force_refresh=False)
        return True, new_config, new_rows

    def _mcp_remove_selected_server(self, item: Dict[str, Any], config: Dict[str, Any], manager, runtime) -> tuple[bool, Dict[str, Any], List[Dict[str, Any]]]:
        from ..mcp import normalize_mcp_config

        if str(item.get("kind", "")).strip() != "server":
            return False, config, self._load_mcp_ui_state(manager, runtime, force_refresh=False)[1]

        server_name = str(item.get("server_name", "")).strip()
        if not server_name:
            return False, config, self._load_mcp_ui_state(manager, runtime, force_refresh=False)[1]
        if not Confirm.ask(f"Remove MCP server '{server_name}'?", default=False):
            return False, config, self._load_mcp_ui_state(manager, runtime, force_refresh=False)[1]

        working = normalize_mcp_config(config)
        resolved = self._resolve_mcp_server_name(server_name, working)
        if resolved not in (working.get("mcpServers", {}) or {}):
            return False, config, self._load_mcp_ui_state(manager, runtime, force_refresh=False)[1]

        working["mcpServers"].pop(resolved, None)
        new_config, new_rows = self._save_mcp_ui_config(manager, runtime, working, force_refresh=True)
        return True, new_config, new_rows

    def _mcp_add_server_interactive(self, config: Dict[str, Any], manager, runtime) -> tuple[bool, Dict[str, Any], List[Dict[str, Any]]]:
        from ..mcp import normalize_mcp_config, normalize_mcp_server_config

        working = normalize_mcp_config(config)
        transport = Prompt.ask("Transport", choices=["stdio", "http", "sse"], default="stdio").strip().lower()
        name = Prompt.ask("Server name", default="").strip()
        if not name:
            self.console.print(f"[{self.theme.AMBER_GLOW}]{self.deco.DOT_MEDIUM} Server name cannot be empty.[/{self.theme.AMBER_GLOW}]")
            return False, config, self._load_mcp_ui_state(manager, runtime, force_refresh=False)[1]

        resolved = self._resolve_mcp_server_name(name, working)
        if resolved in (working.get("mcpServers", {}) or {}) and not Confirm.ask(f"Replace existing MCP server '{resolved}'?", default=False):
            return False, config, self._load_mcp_ui_state(manager, runtime, force_refresh=False)[1]

        server_payload: Dict[str, Any]
        if transport == "stdio":
            command_line = Prompt.ask("Command line", default="").strip()
            try:
                parsed = shlex.split(command_line, posix=False)
            except ValueError as exc:
                self.console.print(f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} Failed to parse command: {escape(str(exc))}[/{self.theme.CORAL_SOFT}]")
                return False, config, self._load_mcp_ui_state(manager, runtime, force_refresh=False)[1]
            command_parts = [str(part).strip().strip('"').strip("'") for part in parsed if str(part).strip()]
            if not command_parts:
                self.console.print(f"[{self.theme.AMBER_GLOW}]{self.deco.DOT_MEDIUM} Command line cannot be empty.[/{self.theme.AMBER_GLOW}]")
                return False, config, self._load_mcp_ui_state(manager, runtime, force_refresh=False)[1]
            server_payload = {
                "enabled": True,
                "type": "stdio",
                "command": command_parts[0],
                "args": command_parts[1:],
            }
        else:
            prompt_label = "Streamable HTTP URL" if transport == "http" else "Legacy SSE URL"
            url = Prompt.ask(prompt_label, default="").strip()
            if not url:
                self.console.print(f"[{self.theme.AMBER_GLOW}]{self.deco.DOT_MEDIUM} URL cannot be empty.[/{self.theme.AMBER_GLOW}]")
                return False, config, self._load_mcp_ui_state(manager, runtime, force_refresh=False)[1]
            server_payload = {
                "enabled": True,
                "type": transport,
                "httpUrl": url if transport == "http" else "",
                "url": url if transport == "sse" else "",
            }

        working.setdefault("mcpServers", {})[resolved] = normalize_mcp_server_config(resolved, server_payload)
        new_config, new_rows = self._save_mcp_ui_config(manager, runtime, working, force_refresh=True)
        return True, new_config, new_rows

    def _mcp_edit_item(self, item: Dict[str, Any], config: Dict[str, Any], manager, runtime) -> tuple[bool, Dict[str, Any], List[Dict[str, Any]]]:
        from ..mcp import normalize_mcp_config

        kind = str(item.get("kind", "")).strip()
        if kind == "global-bool":
            return self._mcp_step_item(item, config, manager, runtime, 1)
        if kind == "global-int":
            working = normalize_mcp_config(config)
            current = int((working.get("mcp", {}) or {}).get("discovery_timeout_ms", 15000) or 15000)
            raw = Prompt.ask("Discovery timeout (ms)", default=str(current)).strip()
            try:
                parsed = int(raw)
            except ValueError:
                self.console.print(f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} Discovery timeout must be an integer.[/{self.theme.CORAL_SOFT}]")
                return False, config, self._load_mcp_ui_state(manager, runtime, force_refresh=False)[1]
            parsed = max(int(item.get("min", 1000)), min(int(item.get("max", 600000)), parsed))
            working.setdefault("mcp", {})["discovery_timeout_ms"] = parsed
            new_config, new_rows = self._save_mcp_ui_config(manager, runtime, working, force_refresh=False)
            return True, new_config, new_rows
        if kind == "action":
            action = str(item.get("action", "")).strip().lower()
            if action == "refresh":
                return False, *self._load_mcp_ui_state(manager, runtime, force_refresh=True)
            if action == "add":
                return self._mcp_add_server_interactive(config, manager, runtime)
            return False, config, self._load_mcp_ui_state(manager, runtime, force_refresh=False)[1]
        if kind == "server":
            action = Prompt.ask(
                "Server action",
                choices=["toggle-enabled", "toggle-trust", "remove", "refresh", "cancel"],
                default="toggle-enabled",
            ).strip().lower()
            if action == "toggle-enabled":
                return self._mcp_step_item(item, config, manager, runtime, 1)
            if action == "toggle-trust":
                return self._mcp_toggle_selected_trust(item, config, manager, runtime)
            if action == "remove":
                return self._mcp_remove_selected_server(item, config, manager, runtime)
            if action == "refresh":
                return False, *self._load_mcp_ui_state(manager, runtime, force_refresh=True)
            return False, config, self._load_mcp_ui_state(manager, runtime, force_refresh=False)[1]
        return False, config, self._load_mcp_ui_state(manager, runtime, force_refresh=False)[1]

    def _cmd_mcp_ui(self) -> bool:
        try:
            import msvcrt
        except ImportError:
            return self._cmd_mcp_status(force_refresh=False)

        manager, runtime = self._get_mcp_services()
        if not manager or not runtime:
            return True

        config, rows = self._load_mcp_ui_state(manager, runtime, force_refresh=False)
        selected_idx = 0
        changed = False

        from rich.live import Live

        with Live(
            self._render_mcp_ui(config, rows, manager, selected_idx, changed=changed),
            auto_refresh=False,
            vertical_overflow="visible",
            console=self.console,
        ) as live:
            last_size = self._console_size()
            while True:
                if msvcrt.kbhit():
                    key = msvcrt.getch()
                    items = self._get_mcp_ui_items(config, rows, manager)
                    if not items:
                        break
                    selected_idx = max(0, min(selected_idx, len(items) - 1))
                    selected_item = items[selected_idx]

                    if key == b"\x1b":
                        break
                    if key in (b"k", b"K"):
                        selected_idx = (selected_idx - 1) % len(items)
                    elif key in (b"j", b"J"):
                        selected_idx = (selected_idx + 1) % len(items)
                    elif key in (b"h", b"H"):
                        did_change, config, rows = self._mcp_step_item(selected_item, config, manager, runtime, -1)
                        changed = changed or did_change
                    elif key in (b"l", b"L", b" "):
                        did_change, config, rows = self._mcp_step_item(selected_item, config, manager, runtime, 1)
                        changed = changed or did_change
                    elif key in (b"a", b"A"):
                        live.stop()
                        did_change, config, rows = self._mcp_add_server_interactive(config, manager, runtime)
                        changed = changed or did_change
                        live.start()
                    elif key in (b"t", b"T"):
                        live.stop()
                        did_change, config, rows = self._mcp_toggle_selected_trust(selected_item, config, manager, runtime)
                        changed = changed or did_change
                        live.start()
                    elif key in (b"x", b"X"):
                        live.stop()
                        did_change, config, rows = self._mcp_remove_selected_server(selected_item, config, manager, runtime)
                        changed = changed or did_change
                        live.start()
                    elif key in (b"r", b"R"):
                        config, rows = self._load_mcp_ui_state(manager, runtime, force_refresh=True)
                    elif key == b"\r":
                        live.stop()
                        did_change, config, rows = self._mcp_edit_item(selected_item, config, manager, runtime)
                        changed = changed or did_change
                        live.start()
                    elif key in (b"\x00", b"\xe0"):
                        key = msvcrt.getch()
                        if key == b"H":
                            selected_idx = (selected_idx - 1) % len(items)
                        elif key == b"P":
                            selected_idx = (selected_idx + 1) % len(items)
                        elif key == b"K":
                            did_change, config, rows = self._mcp_step_item(selected_item, config, manager, runtime, -1)
                            changed = changed or did_change
                        elif key == b"M":
                            did_change, config, rows = self._mcp_step_item(selected_item, config, manager, runtime, 1)
                            changed = changed or did_change
                    else:
                        time.sleep(0.025)
                        continue

                    items = self._get_mcp_ui_items(config, rows, manager)
                    selected_idx = max(0, min(selected_idx, max(0, len(items) - 1)))
                    live.update(self._render_mcp_ui(config, rows, manager, selected_idx, changed=changed), refresh=True)
                current_size = self._console_size()
                if current_size != last_size:
                    last_size = current_size
                    items = self._get_mcp_ui_items(config, rows, manager)
                    selected_idx = max(0, min(selected_idx, max(0, len(items) - 1)))
                    live.update(self._render_mcp_ui(config, rows, manager, selected_idx, changed=changed), refresh=True)
                time.sleep(0.025)

        self.console.print()
        if changed:
            self.console.print(f"[{self.theme.MINT_VIBRANT}]{self.deco.CHECK_FANCY} MCP updated and applied.[/{self.theme.MINT_VIBRANT}]")
        else:
            self.console.print(f"[{self.theme.TEXT_SECONDARY}]{self.deco.DOT_MEDIUM} MCP reviewed.[/{self.theme.TEXT_SECONDARY}]")
        self.console.print()
        return True

    def cmd_mcp(self, args: str) -> bool:
        """Inspect and manage MCP servers."""
        raw = args.strip()
        lowered = raw.lower()

        if not raw or lowered in ("ui", "open", "menu", "panel"):
            return self._cmd_mcp_ui()
        if lowered in ("status", "list", "show"):
            return self._cmd_mcp_status(force_refresh=True)
        if lowered == "reload":
            return self._cmd_mcp_reload()
        if lowered == "path":
            return self._cmd_mcp_path()
        if lowered.startswith("add "):
            return self._cmd_mcp_add(raw[4:].strip())
        if lowered.startswith("remove "):
            return self._cmd_mcp_remove(raw[7:].strip())
        if lowered.startswith("enable "):
            return self._cmd_mcp_toggle(raw[7:].strip(), enabled=True)
        if lowered.startswith("disable "):
            return self._cmd_mcp_toggle(raw[8:].strip(), enabled=False)
        if lowered.startswith("trust "):
            return self._cmd_mcp_trust(raw[6:].strip())

        self._show_activity_event(
            "MCP",
            "Usage: /mcp [status|reload|path|add|remove|enable|disable|trust]",
            status="warning",
            detail="Examples: /mcp add filesystem npx -y @modelcontextprotocol/server-filesystem .  |  /mcp add http myserver http://127.0.0.1:8080/mcp  |  /mcp add sse legacy http://127.0.0.1:8081/sse",
        )
        return True

    def _cmd_mcp_status(self, *, force_refresh: bool = False) -> bool:
        manager, runtime = self._refresh_mcp_runtime(force_reload=False)
        if not manager or not runtime:
            return True

        self._show_command_panel(
            "MCP Servers",
            subtitle="Codex/Gemini-style MCP integration for dynamic external tools.",
            accent=self.theme.BLUE_SOFT,
            meta=str(manager.get_config_path()),
        )

        rows = runtime.list_server_status(force_refresh=force_refresh)
        if not rows:
            self._show_activity_event(
                "MCP",
                "No MCP servers are configured yet.",
                status="info",
                detail="Use /mcp add <name> <command...> for stdio, /mcp add http <name> <url> for streamable HTTP, or /mcp add sse <name> <url> for legacy SSE.",
            )
            return True

        table = Table(
            title=f"[bold {self.theme.BLUE_SOFT}]Configured MCP Servers[/bold {self.theme.BLUE_SOFT}]",
            box=box.ROUNDED,
            border_style=self.theme.BORDER_SECONDARY,
            expand=True,
        )
        table.add_column("Name", style=f"bold {self.theme.BLUE_SOFT}", min_width=14)
        table.add_column("Transport", style=self.theme.TEXT_SECONDARY, min_width=8)
        table.add_column("State", style=self.theme.TEXT_SECONDARY, min_width=10)
        table.add_column("Trust", style=self.theme.TEXT_SECONDARY, min_width=8)
        table.add_column("Tools", style=self.theme.TEXT_PRIMARY, justify="right", min_width=5)
        table.add_column("Res", style=self.theme.TEXT_PRIMARY, justify="right", min_width=3)
        table.add_column("Prompts", style=self.theme.TEXT_PRIMARY, justify="right", min_width=7)
        table.add_column("Notes", style=self.theme.TEXT_DIM)

        for row in rows:
            state = str(row.get("state", "unknown"))
            if state == "enabled":
                state_style = self.theme.MINT_VIBRANT
            elif state in {"disabled", "globally-disabled"}:
                state_style = self.theme.TEXT_DIM
            else:
                state_style = self.theme.AMBER_GLOW

            trust_text = "trusted" if row.get("trust") else "confirm"
            tools_text = "-" if row.get("tools") is None else str(row.get("tools"))
            resources_text = "-" if row.get("resources") is None else str(row.get("resources"))
            prompts_text = "-" if row.get("prompts") is None else str(row.get("prompts"))
            notes = str(row.get("error", "") or "").strip()
            if not notes:
                notes = "ready" if state == "enabled" else state

            table.add_row(
                str(row.get("name", "")),
                str(row.get("type", "")),
                f"[{state_style}]{state}[/{state_style}]",
                trust_text,
                tools_text,
                resources_text,
                prompts_text,
                notes,
            )

        self.console.print(table)
        self.console.print()
        self.console.print(
            f"[{self.theme.TEXT_DIM}]Dynamic tool names are exposed as `mcp_<server>_<tool>`. Use /tools to see the tools currently visible to the model.[/{self.theme.TEXT_DIM}]"
        )
        return True

    def _cmd_mcp_path(self) -> bool:
        manager, _runtime = self._get_mcp_services()
        if not manager:
            return True
        self._show_activity_event(
            "MCP",
            "MCP configuration path",
            status="info",
            detail=str(manager.get_config_path()),
        )
        return True

    def _cmd_mcp_reload(self) -> bool:
        _manager, runtime = self._refresh_mcp_runtime(force_reload=True)
        if not runtime:
            return True
        self._show_activity_event(
            "MCP",
            "Reloaded MCP configuration and refreshed server discovery.",
            status="success",
        )
        return self._cmd_mcp_status(force_refresh=True)

    def _cmd_mcp_add(self, spec: str) -> bool:
        raw = spec.strip()
        lowered = raw.lower()
        if not raw:
            self._show_activity_event(
                "MCP",
                "Usage: /mcp add [stdio] <name> <command...> | /mcp add http <name> <url> | /mcp add sse <name> <url>",
                status="warning",
            )
            return True
        if lowered.startswith("http "):
            return self._cmd_mcp_add_http(raw[5:].strip())
        if lowered.startswith("sse "):
            return self._cmd_mcp_add_sse(raw[4:].strip())
        if lowered.startswith("stdio "):
            return self._cmd_mcp_add_stdio(raw[6:].strip())
        return self._cmd_mcp_add_stdio(raw)

    def _cmd_mcp_add_stdio(self, spec: str) -> bool:
        manager, runtime = self._get_mcp_services()
        if not manager or not runtime:
            return True

        parts = spec.split(maxsplit=1)
        if len(parts) < 2:
            self._show_activity_event(
                "MCP",
                "Usage: /mcp add [stdio] <name> <command...>",
                status="warning",
                detail="Example: /mcp add filesystem npx -y @modelcontextprotocol/server-filesystem .",
            )
            return True

        name = parts[0].strip()
        command_line = parts[1].strip()
        try:
            parsed = shlex.split(command_line, posix=False)
        except ValueError as exc:
            self._show_activity_event("MCP", "Failed to parse MCP stdio command.", status="error", detail=str(exc))
            return True

        command_parts = [str(item).strip().strip('"').strip("'") for item in parsed if str(item).strip()]
        if not name or not command_parts:
            self._show_activity_event("MCP", "An MCP server name and command are required.", status="error")
            return True

        manager.upsert_server(
            name,
            {
                "enabled": True,
                "type": "stdio",
                "command": command_parts[0],
                "args": command_parts[1:],
            },
        )
        runtime.reload(force=True)
        refresh_prompt = self.app.get('refresh_agent_prompt_guidance')
        if callable(refresh_prompt):
            refresh_prompt()

        self._show_activity_event(
            "MCP",
            f"Added MCP stdio server: {name}",
            status="success",
            detail=command_line,
        )
        return self._cmd_mcp_status(force_refresh=True)

    def _cmd_mcp_add_http(self, spec: str) -> bool:
        manager, runtime = self._get_mcp_services()
        if not manager or not runtime:
            return True

        parts = spec.split(maxsplit=1)
        if len(parts) < 2:
            self._show_activity_event(
                "MCP",
                "Usage: /mcp add http <name> <url>",
                status="warning",
                detail="Example: /mcp add http internal-api http://127.0.0.1:8080/mcp",
            )
            return True

        name = parts[0].strip()
        url = parts[1].strip()
        if not name or not url:
            self._show_activity_event("MCP", "An MCP server name and URL are required.", status="error")
            return True

        manager.upsert_server(
            name,
            {
                "enabled": True,
                "type": "http",
                "httpUrl": url,
            },
        )
        runtime.reload(force=True)
        refresh_prompt = self.app.get('refresh_agent_prompt_guidance')
        if callable(refresh_prompt):
            refresh_prompt()

        self._show_activity_event(
            "MCP",
            f"Added MCP HTTP server: {name}",
            status="success",
            detail=url,
        )
        return self._cmd_mcp_status(force_refresh=True)

    def _cmd_mcp_add_sse(self, spec: str) -> bool:
        manager, runtime = self._get_mcp_services()
        if not manager or not runtime:
            return True

        parts = spec.split(maxsplit=1)
        if len(parts) < 2:
            self._show_activity_event(
                "MCP",
                "Usage: /mcp add sse <name> <url>",
                status="warning",
                detail="Example: /mcp add sse legacy-api http://127.0.0.1:8081/sse",
            )
            return True

        name = parts[0].strip()
        url = parts[1].strip()
        if not name or not url:
            self._show_activity_event("MCP", "An MCP server name and URL are required.", status="error")
            return True

        manager.upsert_server(
            name,
            {
                "enabled": True,
                "type": "sse",
                "url": url,
            },
        )
        runtime.reload(force=True)
        refresh_prompt = self.app.get('refresh_agent_prompt_guidance')
        if callable(refresh_prompt):
            refresh_prompt()

        self._show_activity_event(
            "MCP",
            f"Added MCP SSE server: {name}",
            status="success",
            detail=url,
        )
        return self._cmd_mcp_status(force_refresh=True)

    def _cmd_mcp_remove(self, server_name: str) -> bool:
        manager, runtime = self._get_mcp_services()
        if not manager or not runtime:
            return True

        name = server_name.strip()
        if not name:
            self._show_activity_event("MCP", "Usage: /mcp remove <name>", status="warning")
            return True

        if not manager.remove_server(name):
            self._show_activity_event("MCP", f"MCP server not found: {name}", status="error")
            return True

        runtime.reload(force=True)
        refresh_prompt = self.app.get('refresh_agent_prompt_guidance')
        if callable(refresh_prompt):
            refresh_prompt()
        self._show_activity_event("MCP", f"Removed MCP server: {name}", status="success")
        return self._cmd_mcp_status(force_refresh=True)

    def _cmd_mcp_toggle(self, server_name: str, *, enabled: bool) -> bool:
        manager, runtime = self._get_mcp_services()
        if not manager or not runtime:
            return True

        name = server_name.strip()
        if not name:
            self._show_activity_event("MCP", f"Usage: /mcp {'enable' if enabled else 'disable'} <name>", status="warning")
            return True

        if not manager.set_server_enabled(name, enabled):
            self._show_activity_event("MCP", f"MCP server not found: {name}", status="error")
            return True

        runtime.reload(force=True)
        refresh_prompt = self.app.get('refresh_agent_prompt_guidance')
        if callable(refresh_prompt):
            refresh_prompt()
        self._show_activity_event(
            "MCP",
            f"{'Enabled' if enabled else 'Disabled'} MCP server: {name}",
            status="success",
        )
        return self._cmd_mcp_status(force_refresh=True)

    def _cmd_mcp_trust(self, spec: str) -> bool:
        manager, runtime = self._get_mcp_services()
        if not manager or not runtime:
            return True

        parts = spec.split(maxsplit=1)
        name = parts[0].strip() if parts else ""
        mode = parts[1].strip().lower() if len(parts) > 1 else "on"
        if not name:
            self._show_activity_event("MCP", "Usage: /mcp trust <name> [on|off]", status="warning")
            return True

        if mode not in {"on", "off", "true", "false"}:
            self._show_activity_event("MCP", "Trust value must be on or off.", status="error")
            return True

        trusted = mode in {"on", "true"}
        if not manager.set_server_trust(name, trusted):
            self._show_activity_event("MCP", f"MCP server not found: {name}", status="error")
            return True

        runtime.reload(force=True)
        refresh_prompt = self.app.get('refresh_agent_prompt_guidance')
        if callable(refresh_prompt):
            refresh_prompt()
        self._show_activity_event(
            "MCP",
            f"Marked MCP server {name} as {'trusted' if trusted else 'confirmation-required'}.",
            status="success",
        )
        return self._cmd_mcp_status(force_refresh=True)

    def _load_tti_config(self):
        """Load normalized TTI configuration from config manager."""
        from ..config import (
            default_text_to_image_config,
            normalize_tti_models,
            normalize_tti_source,
            resolve_tti_default_display_name,
        )

        config_manager = self.app.get('config_manager')
        if not config_manager:
            return None

        config = config_manager.load()
        raw_tti = config.text_to_image if isinstance(config.text_to_image, dict) else default_text_to_image_config()
        tti_cfg = dict(raw_tti)
        models = normalize_tti_models(
            tti_cfg.get("models", []),
            legacy_model_paths=tti_cfg.get("model_paths", []),
        )
        tti_cfg["active_source"] = normalize_tti_source(tti_cfg.get("active_source", "local"))
        default_display_name = resolve_tti_default_display_name(tti_cfg)
        return config_manager, config, tti_cfg, models, default_display_name

    def cmd_tti(self, args: str) -> bool:
        """
        Text-to-image CLI command.

        Supported:
        - /tti models      -> list TTI models and pick default model
        - /tti add         -> add a TTI model to config
        - /tti source      -> confirm the active local TTI source
        - /tti <prompt>    -> generate one image with default model/default params
        """
        raw = args.strip()
        if not raw:
            self.console.print(
                f"[{self.theme.AMBER_GLOW}]{self.deco.DOT_MEDIUM} "
                f"Usage: /tti models OR /tti source [local] OR /tti add OR /tti <your prompt>"
                f"[/{self.theme.AMBER_GLOW}]"
            )
            return True

        if raw.lower() == "models":
            return self._cmd_tti_models()
        if raw.lower() == "source":
            return self._cmd_tti_source("")
        if raw.lower().startswith("source "):
            return self._cmd_tti_source(raw[7:].strip())
        if raw.lower() == "add":
            return self._cmd_tti_add()

        prompt = raw
        if prompt.startswith("<") and prompt.endswith(">") and len(prompt) >= 2:
            prompt = prompt[1:-1].strip()
        if not prompt:
            self.console.print(f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} Empty prompt. Use: /tti <your prompt>[/{self.theme.CORAL_SOFT}]")
            return True

        from ..tools import TextToImageTool

        context = {"project_root": Path.cwd()}
        loaded = self._load_tti_config()
        if loaded:
            config_manager, _, _, _, _ = loaded
            context["project_root"] = Path(config_manager.project_root)
            context["config_manager"] = config_manager

        tool = TextToImageTool(context)
        with self.console.status(f"[{self.theme.PURPLE_SOFT}]{self.deco.SPARKLE} Generating image...[/{self.theme.PURPLE_SOFT}]"):
            result = tool.execute(action="generate", prompt=prompt)

        if result.success:
            self.console.print(f"[{self.theme.MINT_VIBRANT}]{self.deco.CHECK_FANCY} TTI generation finished.[/{self.theme.MINT_VIBRANT}]")
            if result.output:
                self.console.print(result.output)
            if result.error:
                self.console.print(f"[{self.theme.AMBER_GLOW}]{self.deco.DOT_MEDIUM} {result.error}[/{self.theme.AMBER_GLOW}]")
        else:
            self.console.print(f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} TTI generation failed: {result.error}[/{self.theme.CORAL_SOFT}]")
        return True

    def _cmd_tti_add(self) -> bool:
        """Interactively add a new TTI model configuration entry."""
        loaded = self._load_tti_config()
        if not loaded:
            self.console.print(f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} Config manager not available[/{self.theme.CORAL_SOFT}]")
            return True

        from ..config import normalize_tti_models, normalize_tti_source, sanitize_tti_path

        config_manager, config, tti_cfg, models, _ = loaded
        if normalize_tti_source(tti_cfg.get("active_source", "local")) != "local":
            self.console.print(
                f"[{self.theme.AMBER_GLOW}]{self.deco.DOT_MEDIUM} /tti add is only used for local models. Switch with /tti source local first if needed.[/{self.theme.AMBER_GLOW}]"
            )
            return True

        self.console.print()
        self.console.print(Panel(
            f"[bold {self.theme.PINK_SOFT}]{self.deco.SPARKLE} Add TTI Model {self.deco.SPARKLE}[/bold {self.theme.PINK_SOFT}]",
            border_style=self.theme.BORDER_PRIMARY,
            box=box.ROUNDED,
            padding=(0, 2)
        ))
        self.console.print()

        try:
            model_path = Prompt.ask(
                f"[{self.theme.BLUE_SOFT}]{self.deco.CHEVRON_RIGHT}[/{self.theme.BLUE_SOFT}] Model path (absolute or relative)"
            ).strip()
            model_path = sanitize_tti_path(model_path)
            if not model_path:
                self.console.print(f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} Model path cannot be empty.[/{self.theme.CORAL_SOFT}]")
                return True

            suggested_name = Path(model_path).stem.strip() or "tti-model"
            display_name = Prompt.ask(
                f"[{self.theme.BLUE_SOFT}]{self.deco.CHEVRON_RIGHT}[/{self.theme.BLUE_SOFT}] Display name",
                default=suggested_name
            ).strip()
            if not display_name:
                self.console.print(f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} Display name cannot be empty.[/{self.theme.CORAL_SOFT}]")
                return True

            introduction = Prompt.ask(
                f"[{self.theme.BLUE_SOFT}]{self.deco.CHEVRON_RIGHT}[/{self.theme.BLUE_SOFT}] Introduction (optional)",
                default=""
            )

            model_path_key = model_path.replace("\\", "/").strip().lower()
            existing_by_path = any(
                sanitize_tti_path(m.get("path", "")).replace("\\", "/").strip().lower() == model_path_key
                for m in models
            )
            existing_by_name = any(m.get("display_name", "").strip().lower() == display_name.lower() for m in models)
            if existing_by_path:
                self.console.print(f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} A model with the same path already exists.[/{self.theme.CORAL_SOFT}]")
                return True
            if existing_by_name:
                self.console.print(f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} A model with the same display name already exists.[/{self.theme.CORAL_SOFT}]")
                return True

            updated_models = models + [{
                "path": model_path,
                "display_name": display_name,
                "introduction": introduction or "",
            }]
            normalized_models = normalize_tti_models(updated_models)

            tti_cfg["models"] = normalized_models

            # If there is no default yet, or user wants it, make the new model default.
            current_default = str(tti_cfg.get("default_model_display_name", "")).strip()
            set_default = not current_default
            if current_default:
                set_default = Confirm.ask(
                    f"Set '{display_name}' as default TTI model?",
                    default=False
                )
            if set_default:
                default_name = display_name
                for item in normalized_models:
                    item_path_key = sanitize_tti_path(item.get("path", "")).replace("\\", "/").strip().lower()
                    if item_path_key == model_path_key:
                        default_name = item.get("display_name", display_name)
                        break
                tti_cfg["default_model_display_name"] = default_name

            tti_cfg.pop("model_paths", None)
            tti_cfg.pop("default_model_index", None)
            config.text_to_image = tti_cfg
            config_manager.save(config)

            self.console.print(f"[{self.theme.MINT_VIBRANT}]{self.deco.CHECK_FANCY} Added TTI model: {display_name}[/{self.theme.MINT_VIBRANT}]")
            if set_default:
                self.console.print(f"[{self.theme.MINT_VIBRANT}]{self.deco.CHECK_FANCY} Default TTI model updated.[/{self.theme.MINT_VIBRANT}]")

            # Rebuild prompt context to include the latest TTI model list.
            if self.app.get('reinit_agent'):
                self.app['reinit_agent']()

        except KeyboardInterrupt:
            self.console.print()
            self.console.print(f"[{self.theme.AMBER_GLOW}]{self.deco.DOT_MEDIUM} Cancelled.[/{self.theme.AMBER_GLOW}]")

        return True

    def _cmd_tti_source(self, value: str) -> bool:
        """Keep text-to-image source pinned to the local runtime."""
        loaded = self._load_tti_config()
        if not loaded:
            self.console.print(f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} Config manager not available[/{self.theme.CORAL_SOFT}]")
            return True

        from ..config import normalize_tti_source

        config_manager, config, tti_cfg, _, _ = loaded
        raw_value = str(value or "").strip().lower()
        candidate = normalize_tti_source(raw_value, default="") if raw_value else ""
        if raw_value and not candidate:
            self.console.print(
                f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} Invalid TTI source: {escape(raw_value)}. Use local.[/{self.theme.CORAL_SOFT}]"
            )
            return True
        if not candidate:
            current = normalize_tti_source(tti_cfg.get("active_source", "local"))
            candidate = Prompt.ask("TTI source", default=current, choices=["local"]).strip().lower()
            candidate = normalize_tti_source(candidate)

        tti_cfg["active_source"] = candidate
        config.text_to_image = tti_cfg
        config_manager.save(config)

        self.console.print(
            f"[{self.theme.MINT_VIBRANT}]{self.deco.CHECK_FANCY} TTI source set to: {candidate}[/{self.theme.MINT_VIBRANT}]"
        )
        if self.app.get('reinit_agent'):
            self.app['reinit_agent']()
        return True

    def _cmd_tti_models(self) -> bool:
        """Show TTI model selector and set default model."""
        loaded = self._load_tti_config()
        if not loaded:
            self.console.print(f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} Config manager not available[/{self.theme.CORAL_SOFT}]")
            return True

        config_manager, config, tti_cfg, models, default_display_name = loaded

        if not models:
            self.console.print(f"[{self.theme.AMBER_GLOW}]{self.deco.DOT_MEDIUM} No TTI models configured in config.json.[/{self.theme.AMBER_GLOW}]")
            return True

        from .tui_selector import ModelSelector, SelectorAction

        models_data = []
        current_model_id = None
        for i, model in enumerate(models):
            intro = model.get("introduction", "")
            intro_text = intro if intro else "(empty introduction)"
            models_data.append({
                "id": str(i),
                "name": model["display_name"],
                "description": f"{model['path']} • {intro_text}",
                "model": model,
            })
            if model["display_name"].lower() == default_display_name.lower():
                current_model_id = str(i)

        selector = ModelSelector(
            console=self.console,
            models=models_data,
            current_model=current_model_id,
        )
        result = selector.run()

        if result.action != SelectorAction.SELECT or not result.selected_item:
            return True

        try:
            selected_idx = int(result.selected_item.id)
        except (TypeError, ValueError):
            self.console.print(f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} Invalid model selection.[/{self.theme.CORAL_SOFT}]")
            return True

        if selected_idx < 0 or selected_idx >= len(models):
            self.console.print(f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} Invalid model index.[/{self.theme.CORAL_SOFT}]")
            return True

        selected_name = models[selected_idx]["display_name"]
        tti_cfg["models"] = models
        tti_cfg["default_model_display_name"] = selected_name
        tti_cfg.pop("model_paths", None)
        tti_cfg.pop("default_model_index", None)
        config.text_to_image = tti_cfg
        config_manager.save(config)

        self.console.print(f"[{self.theme.MINT_VIBRANT}]{self.deco.CHECK_FANCY} Default TTI model set to: {selected_name}[/{self.theme.MINT_VIBRANT}]")

        # Rebuild agent prompt so model context includes latest TTI default/meta.
        if self.app.get('reinit_agent'):
            self.app['reinit_agent']()

        return True

    def cmd_status(self, args: str) -> bool:
        """Show current status with dreamy styling"""
        config_manager = self.app.get('config_manager')
        config = config_manager.load() if config_manager else None
        skills_manager = self.app.get('skills_manager')
        runtime_plugin_manager = self.app.get('runtime_plugin_manager')
        indexer = self.app.get('indexer')
        ensure_context_engine = self.app.get('ensure_context_engine')
        ensure_git_integration = self.app.get('ensure_git_integration')
        ensure_lsp_manager = self.app.get('ensure_lsp_manager')
        git_integration = self.app.get('git_integration')
        lsp_manager = self.app.get('lsp_manager')
        session_manager = self.app.get('session_manager')
        start_time = self.app.get('start_time')
        agent = self.app.get('agent')
        
        self.console.print()
        table = Table(
            title=f"[bold {self.theme.PINK_SOFT}]{self.deco.CRYSTAL} Reverie System Status[/bold {self.theme.PINK_SOFT}]",
            box=box.ROUNDED,
            border_style=self.theme.BORDER_PRIMARY
        )
        table.add_column("Component", style=f"bold {self.theme.BLUE_SOFT}")
        table.add_column("Value", style=self.theme.TEXT_SECONDARY)
        
        # Model info
        if config_manager:
            model = config_manager.get_active_model()
            if model:
                table.add_row(
                    f"{self.deco.SPARKLE} Model",
                    f"[bold {self.theme.PINK_SOFT}]{model.model_display_name}[/bold {self.theme.PINK_SOFT}]"
                )
                table.add_row(
                    f"{self.deco.DOT_MEDIUM} Endpoint",
                    f"[{self.theme.TEXT_DIM}]{model.base_url}[/{self.theme.TEXT_DIM}]"
                )
                source = str(getattr(config, "active_model_source", "standard")).lower() if config else "standard"
                source_label = self._format_model_source_label(source)
                table.add_row(
                    f"{self.deco.DOT_MEDIUM} Source",
                    f"[{self.theme.TEXT_DIM}]{source_label}[/{self.theme.TEXT_DIM}]"
                )
            active_config_path = ""
            try:
                active_config_path = str(config_manager.get_active_config_path())
            except Exception:
                active_config_path = ""
            if active_config_path:
                table.add_row(
                    f"{self.deco.DOT_MEDIUM} Config Path",
                    f"[{self.theme.TEXT_DIM}]{escape(active_config_path)}[/{self.theme.TEXT_DIM}]"
                )

        if runtime_plugin_manager:
            plugin_summary = runtime_plugin_manager.get_status_summary()
            plugin_label = plugin_summary.get("summary_label", "0 detected | 0 ready | 0 rc | 0 tools")
            ready_names = str(plugin_summary.get("ready_names", "") or "").strip()
            protocol_names = str(plugin_summary.get("protocol_names", "") or "").strip()
            table.add_row(
                f"{self.deco.SPARKLE} Runtime Plugins",
                f"[{self.theme.BLUE_SOFT}]{escape(plugin_label)}[/{self.theme.BLUE_SOFT}]",
            )
            if ready_names:
                table.add_row(
                    f"{self.deco.DOT_MEDIUM} Ready Plugins",
                    f"[{self.theme.MINT_SOFT}]{escape(ready_names)}[/{self.theme.MINT_SOFT}]",
                )
            if protocol_names:
                table.add_row(
                    f"{self.deco.DOT_MEDIUM} RC Plugins",
                    f"[{self.theme.MINT_SOFT}]{escape(protocol_names)}[/{self.theme.MINT_SOFT}]",
                )
            table.add_row(
                f"{self.deco.DOT_MEDIUM} Plugin Root",
                f"[{self.theme.TEXT_DIM}]{escape(str(plugin_summary.get('install_root', '')))}[/{self.theme.TEXT_DIM}]",
            )
        if skills_manager:
            skill_summary = skills_manager.get_status_summary()
            skill_label = str(skill_summary.get("summary_label", "0 skills | 0 invalid") or "0 skills | 0 invalid")
            table.add_row(
                f"{self.deco.SPARKLE} Skills",
                f"[{self.theme.BLUE_SOFT}]{escape(skill_label)}[/{self.theme.BLUE_SOFT}]",
            )
            skill_names = str(skill_summary.get("skill_names", "") or "").strip()
            if skill_names:
                table.add_row(
                    f"{self.deco.DOT_MEDIUM} Skill Names",
                    f"[{self.theme.MINT_SOFT}]{escape(skill_names)}[/{self.theme.MINT_SOFT}]",
                )
        
        # Session info
        if session_manager:
            session = session_manager.get_current_session()
            if session:
                table.add_row(
                    f"{self.deco.SPARKLE} Session",
                    f"[bold {self.theme.PURPLE_SOFT}]{session.name}[/bold {self.theme.PURPLE_SOFT}]"
                )
                table.add_row(f"{self.deco.DOT_MEDIUM} Messages", str(len(session.messages)))

        if indexer:
            table.add_row(
                f"{self.deco.SPARKLE} Context Engine",
                f"[{self.theme.MINT_SOFT}]Ready[/{self.theme.MINT_SOFT}]",
            )
        elif ensure_context_engine:
            table.add_row(
                f"{self.deco.SPARKLE} Context Engine",
                f"[{self.theme.TEXT_DIM}]Lazy load on first message or /index[/{self.theme.TEXT_DIM}]",
            )
        if git_integration:
            git_status = "Ready" if getattr(git_integration, "is_available", False) else "Unavailable"
            git_color = self.theme.MINT_SOFT if getattr(git_integration, "is_available", False) else self.theme.TEXT_DIM
            table.add_row(
                f"{self.deco.DOT_MEDIUM} Git Integration",
                f"[{git_color}]{git_status}[/{git_color}]",
            )
        elif ensure_git_integration:
            table.add_row(
                f"{self.deco.DOT_MEDIUM} Git Integration",
                f"[{self.theme.TEXT_DIM}]Lazy load on first git history query[/{self.theme.TEXT_DIM}]",
            )
        if lsp_manager:
            lsp_status = lsp_manager.build_status_report()
            lsp_available = bool(lsp_status.get("available"))
            lsp_label = f"Ready ({len(lsp_status.get('servers', []))} server(s))" if lsp_available else "Ready (no local servers detected)"
            lsp_color = self.theme.MINT_SOFT if lsp_available else self.theme.TEXT_DIM
            table.add_row(
                f"{self.deco.DOT_MEDIUM} LSP Bridge",
                f"[{lsp_color}]{lsp_label}[/{lsp_color}]",
            )
        elif ensure_lsp_manager:
            table.add_row(
                f"{self.deco.DOT_MEDIUM} LSP Bridge",
                f"[{self.theme.TEXT_DIM}]Lazy load on first LSP query[/{self.theme.TEXT_DIM}]",
            )

        # Token info
        if agent:
            tokens = agent.get_token_estimate()
            # Default to 128k if config not found
            max_tokens = 128000
            if config_manager:
                 model_config = config_manager.get_active_model()
                 if model_config and model_config.max_context_tokens:
                     max_tokens = model_config.max_context_tokens
                 else:
                     # Fallback to global config if available
                     max_tokens = getattr(config, 'max_context_tokens', 128000) if config else 128000

            percentage = (tokens / max_tokens) * 100
            
            # Color based on percentage
            if percentage < 40:
                pct_color = self.theme.MINT_SOFT
            elif percentage < 70:
                pct_color = self.theme.AMBER_GLOW
            else:
                pct_color = self.theme.CORAL_SOFT
                
            table.add_row(
                f"{self.deco.SPARKLE} Context Usage",
                f"{tokens:,} / {max_tokens:,} ([bold {pct_color}]{percentage:.1f}%[/bold {pct_color}])"
            )
        
        # Context Engine stats
        if indexer:
            stats = indexer.get_statistics()
            table.add_row(
                f"{self.deco.DOT_MEDIUM} Files Indexed",
                f"[{self.theme.MINT_SOFT}]{stats.get('files_indexed', 0)}[/{self.theme.MINT_SOFT}]"
            )
            symbols = stats.get('symbols', {})
            table.add_row(
                f"{self.deco.DOT_MEDIUM} Total Symbols",
                f"[{self.theme.MINT_SOFT}]{symbols.get('total_symbols', 0)}[/{self.theme.MINT_SOFT}]"
            )
        
        # Timer
        if start_time:
            elapsed = time.time() - start_time
            hours, remainder = divmod(int(elapsed), 3600)
            minutes, seconds = divmod(remainder, 60)
            table.add_row(
                f"{self.deco.SPARKLE} Total Time",
                f"[bold {self.theme.PURPLE_SOFT}]{hours}h {minutes}m {seconds}s[/bold {self.theme.PURPLE_SOFT}]"
            )
            
            active_elapsed = self.app.get('total_active_time', 0.0)
            cur_start = self.app.get('current_task_start')
            if cur_start:
                active_elapsed += (time.time() - cur_start)
            
            a_hours, a_remainder = divmod(int(active_elapsed), 3600)
            a_minutes, a_seconds = divmod(a_remainder, 60)
            table.add_row(
                f"{self.deco.DOT_MEDIUM} Active Time",
                f"[{self.theme.MINT_SOFT}]{a_hours}h {a_minutes}m {a_seconds}s[/{self.theme.MINT_SOFT}]"
            )
        
        self.console.print(table)
        self.console.print()
        return True

    def cmd_doctor(self, args: str) -> bool:
        """Audit Reverie's current harness readiness for the active workspace."""
        raw = str(args or "").strip().lower()
        if raw not in ("", "json", "--json", "history", "runs"):
            self.console.print(
                f"[{self.theme.AMBER_GLOW}]{self.deco.DOT_MEDIUM} Usage: /doctor, /doctor json, or /doctor history[/{self.theme.AMBER_GLOW}]"
            )
            return True

        project_root = Path(self.app.get("project_root") or Path.cwd()).resolve()
        config_manager = self.app.get("config_manager")
        config = config_manager.load() if config_manager else None
        project_data_dir = self.app.get("project_data_dir") or getattr(config_manager, "project_data_dir", None)
        agent = self.app.get("agent")
        mode = normalize_mode(
            getattr(agent, "mode", "")
            or getattr(config, "mode", "")
            or "reverie"
        )

        report = build_harness_capability_report(
            project_root,
            project_data_dir=project_data_dir,
            mode=mode,
            agent=agent,
            indexer=self.app.get("indexer"),
            ensure_context_engine=self.app.get("ensure_context_engine"),
            git_integration=self.app.get("git_integration"),
            ensure_git_integration=self.app.get("ensure_git_integration"),
            lsp_manager=self.app.get("lsp_manager"),
            ensure_lsp_manager=self.app.get("ensure_lsp_manager"),
            session_manager=self.app.get("session_manager"),
            memory_indexer=self.app.get("memory_indexer"),
            operation_history=self.app.get("operation_history"),
            rollback_manager=self.app.get("rollback_manager"),
            runtime_plugin_manager=self.app.get("runtime_plugin_manager"),
            skills_manager=self.app.get("skills_manager"),
            mcp_runtime=self.app.get("mcp_runtime"),
        )

        if raw in ("json", "--json"):
            self._show_command_panel(
                "Harness Doctor",
                subtitle="Structured harness audit for the current workspace.",
                accent=self.theme.BLUE_SOFT,
                meta=str(project_root),
            )
            self.console.print(
                Syntax(
                    json.dumps(report, ensure_ascii=False, indent=2),
                    "json",
                    word_wrap=True,
                    line_numbers=False,
                )
            )
            self.console.print()
            return True

        summary = report.get("summary", {})
        history_summary = report.get("history_summary", {}) or {}
        self._show_command_panel(
            "Harness Doctor",
            subtitle="Audit the goal, context, tools, execution, memory, evaluation, and recovery layers around the model.",
            accent=self.theme.BLUE_SOFT,
            meta=str(project_root),
        )

        panels = [
            self._build_metric_panel(
                "Harness Score",
                report.get("overall_score", 0),
                accent=self.theme.MINT_VIBRANT,
                detail=f"mode {report.get('mode', mode)}",
            ),
            self._build_metric_panel(
                "Visible Tools",
                summary.get("visible_tools", 0),
                accent=self.theme.BLUE_SOFT,
                detail="current mode surface",
            ),
            self._build_metric_panel(
                "Verification",
                summary.get("verification_commands", 0),
                accent=self.theme.PURPLE_SOFT,
                detail="explicit checks seen",
            ),
            self._build_metric_panel(
                "Recent Runs",
                summary.get("prompt_runs", 0),
                accent=self.theme.AMBER_GLOW,
                detail=history_summary.get("score_trend_label", "no history yet"),
            ),
        ]
        self.console.print(Columns(panels, expand=True, equal=True))
        self.console.print()

        artifacts = report.get("artifacts", {})
        tasks = artifacts.get("tasks", {})
        audit = artifacts.get("command_audit", {})
        verification = artifacts.get("verification", {})
        operations = artifacts.get("operation_history", {})
        checkpoints = artifacts.get("checkpoints", {})
        sessions = artifacts.get("sessions", {})
        git_workspace = artifacts.get("git_workspace", {})
        completion_gate = report.get("completion_gate", {}) or {}
        recovery_playbooks = report.get("recovery_playbooks", []) or []
        self.console.print(
            self._build_key_value_table(
                [
                    ("Workspace", report.get("workspace_root", "")),
                    ("Project Cache", report.get("project_data_dir", "")),
                    ("Task Source", tasks.get("source", "missing")),
                    ("Tasks", f"{tasks.get('completed', 0)}/{tasks.get('total', 0)} completed"),
                    ("Operations", f"{operations.get('operations', 0)} tracked"),
                    ("Command Audit", f"{audit.get('entries', 0)} event(s)"),
                    ("Checkpoints", f"{checkpoints.get('count', 0)} recorded"),
                    ("Sessions", f"{sessions.get('count', 0)} total"),
                    ("Recent Success", f"{history_summary.get('recent_success_rate', 0)}%"),
                    ("Verification Coverage", f"{history_summary.get('recent_verification_coverage', 0)}%"),
                    ("Git Workspace", f"{git_workspace.get('dirty_files', 0)} dirty path(s)"),
                    ("Closure Gate", completion_gate.get("label", "n/a")),
                ]
            )
        )
        self.console.print()

        if raw in ("history", "runs"):
            run_table = Table(
                title=f"[bold {self.theme.BLUE_SOFT}]{self.deco.CRYSTAL} Recent Harness Runs[/bold {self.theme.BLUE_SOFT}]",
                box=box.ROUNDED,
                border_style=self.theme.BORDER_PRIMARY,
                expand=True,
            )
            run_table.add_column("Ended", style=f"bold {self.theme.BLUE_SOFT}", width=20)
            run_table.add_column("Mode", style=self.theme.TEXT_PRIMARY, width=14)
            run_table.add_column("Score", style=self.theme.TEXT_SECONDARY, justify="right", width=7)
            run_table.add_column("Verified", style=self.theme.TEXT_SECONDARY, justify="right", width=9)
            run_table.add_column("Gate", style=self.theme.TEXT_SECONDARY, width=12)
            run_table.add_column("Status", style=self.theme.TEXT_SECONDARY, width=10)
            run_table.add_column("Task", style=self.theme.TEXT_PRIMARY, ratio=1)
            for item in history_summary.get("recent_runs", []) or []:
                timestamp = str(item.get("timestamp", "") or "")[:19].replace("T", " ")
                run_table.add_row(
                    escape(timestamp or "(unknown)"),
                    escape(str(item.get("mode", "") or "(none)")),
                    str(int(item.get("overall_score", 0) or 0)),
                    str(int(item.get("verification_commands", 0) or 0)),
                    escape(str(item.get("completion_gate_status", "") or "-")),
                    "success" if item.get("success") else "failed",
                    escape(str(item.get("task_active", "") or "(none)")),
                )
            if not (history_summary.get("recent_runs", []) or []):
                run_table.add_row("(none)", "-", "0", "0", "-", "-", "No prompt runs recorded yet")
            self.console.print(run_table)
            self.console.print()
            return True

        category_table = Table(
            title=f"[bold {self.theme.PINK_SOFT}]{self.deco.CRYSTAL} Harness Layers[/bold {self.theme.PINK_SOFT}]",
            box=box.ROUNDED,
            border_style=self.theme.BORDER_PRIMARY,
            expand=True,
        )
        category_table.add_column("Layer", style=f"bold {self.theme.BLUE_SOFT}", width=14)
        category_table.add_column("Score", style=self.theme.TEXT_SECONDARY, width=8, justify="right")
        category_table.add_column("Highlights", style=self.theme.TEXT_PRIMARY, ratio=1)
        for name, payload in (report.get("categories", {}) or {}).items():
            highlights = "; ".join(str(item) for item in payload.get("highlights", []) if str(item).strip())
            category_table.add_row(
                name.title(),
                f"{int(payload.get('score', 0))}",
                escape(highlights or "(none)"),
            )
        self.console.print(category_table)
        self.console.print()

        verification_lines = [
            f"Explicit verification commands: {int(verification.get('explicit_commands', 0) or 0)}",
            f"Successful verification commands: {int(verification.get('successful_commands', 0) or 0)}",
            f"Failed verification commands: {int(verification.get('failed_commands', 0) or 0)}",
            f"Detected categories: {', '.join((verification.get('categories', {}) or {}).keys()) or '(none)'}",
        ]
        examples = verification.get("examples", []) or []
        if examples:
            verification_lines.append(f"Recent examples: {', '.join(str(item) for item in examples[:3])}")
        self.console.print(
            Panel(
                Text("\n".join(verification_lines), style=self.theme.TEXT_SECONDARY),
                title=f"[bold {self.theme.PURPLE_SOFT}]{self.deco.CRYSTAL} Verification Posture[/bold {self.theme.PURPLE_SOFT}]",
                border_style=self.theme.BORDER_SECONDARY,
                box=box.ROUNDED,
                padding=(0, 1),
            )
        )
        self.console.print()

        closure_lines = [
            f"Status: {completion_gate.get('label', 'n/a')}",
            f"Confidence: {int(completion_gate.get('confidence', 0) or 0)}%",
        ]
        for reason in completion_gate.get("reasons", []) or []:
            closure_lines.append(f"Reason: {reason}")
        for action in completion_gate.get("next_actions", []) or []:
            closure_lines.append(f"Next: {action}")
        self.console.print(
            Panel(
                Text("\n".join(closure_lines), style=self.theme.TEXT_SECONDARY),
                title=f"[bold {self.theme.BLUE_SOFT}]{self.deco.CRYSTAL} Closure Gate[/bold {self.theme.BLUE_SOFT}]",
                border_style=self.theme.BORDER_SECONDARY,
                box=box.ROUNDED,
                padding=(0, 1),
            )
        )
        self.console.print()

        if recovery_playbooks:
            playbook_lines = []
            for item in recovery_playbooks[:3]:
                title = str(item.get("title", "") or "(untitled)")
                severity = str(item.get("severity", "medium") or "medium").upper()
                why = str(item.get("why", "") or "").strip()
                playbook_lines.append(f"[{severity}] {title}")
                if why:
                    playbook_lines.append(f"Why: {why}")
                actions = item.get("actions", []) or []
                if actions:
                    playbook_lines.append(f"Next: {actions[0]}")
                playbook_lines.append("")
            while playbook_lines and not playbook_lines[-1].strip():
                playbook_lines.pop()
            self.console.print(
                Panel(
                    Text("\n".join(playbook_lines), style=self.theme.TEXT_SECONDARY),
                    title=f"[bold {self.theme.MINT_SOFT}]{self.deco.CRYSTAL} Recovery Playbooks[/bold {self.theme.MINT_SOFT}]",
                    border_style=self.theme.BORDER_SECONDARY,
                    box=box.ROUNDED,
                    padding=(0, 1),
                )
            )
            self.console.print()

        recommendations = report.get("recommendations", []) or []
        if recommendations:
            lines = [
                f"{index}. {item}"
                for index, item in enumerate(recommendations, start=1)
            ]
            self.console.print(
                Panel(
                    Text("\n".join(lines), style=self.theme.TEXT_SECONDARY),
                    title=f"[bold {self.theme.AMBER_GLOW}]{self.deco.SPARKLE} Recommended Next Steps[/bold {self.theme.AMBER_GLOW}]",
                    border_style=self.theme.BORDER_SECONDARY,
                    box=box.ROUNDED,
                    padding=(0, 1),
                )
            )
            self.console.print()

        run_history = history_summary.get("recent_runs", []) or []
        if run_history:
            run_table = Table(
                title=f"[bold {self.theme.BLUE_SOFT}]{self.deco.CRYSTAL} Recent Harness Runs[/bold {self.theme.BLUE_SOFT}]",
                box=box.ROUNDED,
                border_style=self.theme.BORDER_SECONDARY,
                expand=True,
            )
            run_table.add_column("Ended", style=f"bold {self.theme.BLUE_SOFT}", width=20)
            run_table.add_column("Mode", style=self.theme.TEXT_PRIMARY, width=14)
            run_table.add_column("Score", style=self.theme.TEXT_SECONDARY, justify="right", width=7)
            run_table.add_column("Verified", style=self.theme.TEXT_SECONDARY, justify="right", width=9)
            run_table.add_column("Gate", style=self.theme.TEXT_SECONDARY, width=12)
            run_table.add_column("Status", style=self.theme.TEXT_SECONDARY, width=10)
            for item in run_history:
                timestamp = str(item.get("timestamp", "") or "")[:19].replace("T", " ")
                run_table.add_row(
                    escape(timestamp or "(unknown)"),
                    escape(str(item.get("mode", "") or "(none)")),
                    str(int(item.get("overall_score", 0) or 0)),
                    str(int(item.get("verification_commands", 0) or 0)),
                    escape(str(item.get("completion_gate_status", "") or "-")),
                    "success" if item.get("success") else "failed",
                )
            self.console.print(run_table)
            self.console.print()

        top_commands = audit.get("top_commands", []) or []
        if top_commands:
            command_table = Table(
                title=f"[bold {self.theme.MINT_SOFT}]{self.deco.CRYSTAL} Recent Command Surface[/bold {self.theme.MINT_SOFT}]",
                box=box.ROUNDED,
                border_style=self.theme.BORDER_SECONDARY,
                expand=True,
            )
            command_table.add_column("Command", style=f"bold {self.theme.BLUE_SOFT}")
            command_table.add_column("Count", style=self.theme.TEXT_SECONDARY, justify="right", width=8)
            for item in top_commands:
                command_table.add_row(
                    escape(str(item.get("command", "") or "")),
                    str(int(item.get("count", 0) or 0)),
                )
            self.console.print(command_table)
            self.console.print()

        return True

    def cmd_skills(self, args: str) -> bool:
        """Inspect Codex-style skill discovery and prompt injection roots."""
        skills_manager = self.app.get('skills_manager')
        if not skills_manager:
            self.console.print(
                f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} Skills manager is not available.[/{self.theme.CORAL_SOFT}]"
            )
            return True

        raw_query = str(args or "").strip()
        query = raw_query.lower()
        if query in ("", "status", "list"):
            return self._cmd_skills_ui(force_refresh=True)
        elif query in ("rescan", "reload", "refresh"):
            return self._cmd_skills_ui(force_refresh=True)
        elif query.startswith("inspect "):
            return self._cmd_skills_inspect(raw_query[8:].strip())
        elif query == "path":
            summary = skills_manager.get_status_summary(force_refresh=True)
            rows = [(f"Root {idx + 1}", path) for idx, path in enumerate(summary.get("root_paths", []) or [])]
            if not rows:
                rows = [("Roots", "(none configured)")]
            self._show_command_panel(
                "Skill Roots",
                subtitle="Reverie scans Codex-style `SKILL.md` directories from the application `.reverie` root.",
                accent=self.theme.BLUE_SOFT,
            )
            self.console.print(self._build_key_value_table(rows))
            self.console.print()
            return True

        record = skills_manager.get_record(raw_query, force_refresh=True)
        if record is not None:
            self._print_skill_detail_page(record)
            return True

        return self._cmd_skills_ui(initial_query=raw_query, force_refresh=False)

    def _cmd_skills_inspect(self, skill_name: str) -> bool:
        """Inspect one detected skill and preview its instructions."""
        skills_manager = self.app.get('skills_manager')
        if not skills_manager:
            self.console.print(
                f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} Skills manager is not available.[/{self.theme.CORAL_SOFT}]"
            )
            return True

        wanted = str(skill_name or "").strip()
        if not wanted:
            self.console.print(
                f"[{self.theme.AMBER_GLOW}]{self.deco.DOT_MEDIUM} Usage: /skills inspect <skill-name>[/{self.theme.AMBER_GLOW}]"
            )
            return True

        record = skills_manager.get_record(wanted, force_refresh=True)
        if record is None:
            self.console.print(
                f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} Skill not found: {escape(wanted)}[/{self.theme.CORAL_SOFT}]"
            )
            return True

        self._print_skill_detail_page(record)
        return True

    def cmd_plugins(self, args: str) -> bool:
        """Inspect plugin-style runtime discovery and install locations."""
        runtime_plugin_manager = self.app.get('runtime_plugin_manager')
        if not runtime_plugin_manager:
            self.console.print(
                f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} Runtime plugin manager is not available.[/{self.theme.CORAL_SOFT}]"
            )
            return True

        raw_query = str(args or "").strip()
        query = raw_query.lower()
        if query in ("", "status", "list"):
            force_refresh = False
        elif query in ("rescan", "reload", "refresh"):
            force_refresh = True
        elif query.startswith("inspect "):
            return self._cmd_plugins_inspect(raw_query[8:].strip())
        elif query == "scaffold":
            return self._cmd_plugins_scaffold("")
        elif query.startswith("scaffold "):
            return self._cmd_plugins_scaffold(raw_query[9:].strip())
        elif query == "validate":
            return self._cmd_plugins_validate("")
        elif query.startswith("validate "):
            return self._cmd_plugins_validate(raw_query[9:].strip())
        elif query == "build":
            return self._cmd_plugins_build("")
        elif query.startswith("build "):
            return self._cmd_plugins_build(raw_query[6:].strip())
        elif query == "deploy":
            return self._cmd_plugins_deploy("")
        elif query.startswith("deploy "):
            return self._cmd_plugins_deploy(raw_query[7:].strip())
        elif query in ("models", "model", "game-models", "game_models"):
            return self._cmd_plugins_models("")
        elif query.startswith("models "):
            return self._cmd_plugins_models(raw_query[7:].strip())
        elif query.startswith("model "):
            return self._cmd_plugins_models(raw_query[6:].strip())
        elif query.startswith("game-models "):
            return self._cmd_plugins_models(raw_query[12:].strip())
        elif query.startswith("game_models "):
            return self._cmd_plugins_models(raw_query[12:].strip())
        elif query == "run":
            return self._cmd_plugins_run("")
        elif query.startswith("run "):
            return self._cmd_plugins_run(raw_query[4:].strip())
        elif query == "sdk":
            return self._cmd_plugins_sdk("")
        elif query.startswith("sdk "):
            return self._cmd_plugins_sdk(raw_query[4:].strip())
        elif query in ("template", "templates"):
            return self._cmd_plugins_templates("")
        elif query.startswith("template "):
            return self._cmd_plugins_templates(raw_query[9:].strip())
        elif query.startswith("templates "):
            return self._cmd_plugins_templates(raw_query[10:].strip())
        elif query == "path":
            summary = runtime_plugin_manager.get_status_summary()
            self._show_command_panel(
                "Plugin SDK Depot Paths",
                subtitle="Portable SDKs and optional RC wrappers live beside the executable.",
                accent=self.theme.BLUE_SOFT,
            )
            self.console.print(
                self._build_key_value_table(
                    [
                        ("Source Root", summary.get("source_root", "")),
                        ("SDK/Install Root", summary.get("install_root", "")),
                        ("Catalog Code", summary.get("catalog_root", "")),
                        ("Template Root", summary.get("template_root", "")),
                    ]
                )
            )
            self.console.print()
            return True
        else:
            self.console.print(
                f"[{self.theme.AMBER_GLOW}]{self.deco.DOT_MEDIUM} Usage: /plugins [status|rescan|path|sdk [plugin-id]|deploy <plugin-id>|models [list|plan|select|download|status]|run <plugin-id>|inspect <plugin-id>|scaffold <plugin-id>|validate <plugin-id>|build <plugin-id>|templates|template inspect <template-id>][/{self.theme.AMBER_GLOW}]"
            )
            return True

        summary = runtime_plugin_manager.get_status_summary(force_refresh=force_refresh)
        rows = runtime_plugin_manager.list_display_rows(force_refresh=False)
        if force_refresh and self.app.get('refresh_agent_prompt_guidance'):
            self.app['refresh_agent_prompt_guidance']()

        self._show_command_panel(
            "Runtime Plugins / SDK Depot",
            subtitle="Plugins now anchor portable SDK/runtime folders under `.reverie/plugins`; RC tools are optional add-ons.",
            accent=self.theme.BLUE_SOFT,
            meta=str(summary.get("install_root", "")),
        )

        overview = self._build_key_value_table(
            [
                ("Summary", summary.get("summary_label", "0 detected | 0 ready | 0 rc | 0 tools")),
                ("Detected", str(summary.get("detected_count", 0))),
                ("Ready", str(summary.get("ready_count", 0))),
                ("Invalid Manifests", str(summary.get("invalid_count", 0))),
                ("RC Ready", str(summary.get("protocol_ready_count", 0))),
                ("Noncompliant", str(summary.get("noncompliant_count", 0))),
                ("RC Tools", str(summary.get("tool_count", 0))),
                ("Templates", str(summary.get("template_count", 0))),
                ("Ready Plugins", summary.get("ready_names", "") or "(none)"),
                ("RC Plugins", summary.get("protocol_names", "") or "(none)"),
            ]
        )
        self.console.print(overview)
        self.console.print()

        if not rows:
            self.console.print(
                f"[{self.theme.TEXT_DIM}]{self.deco.DOT_MEDIUM} No plugin directories are currently present under `.reverie/plugins`.[/{self.theme.TEXT_DIM}]"
            )
            self.console.print()
            return True

        table = Table(
            title=f"[bold {self.theme.PINK_SOFT}]{self.deco.CRYSTAL} Detected Runtime Plugins[/bold {self.theme.PINK_SOFT}]",
            box=box.ROUNDED,
            border_style=self.theme.BORDER_PRIMARY,
            expand=True,
        )
        table.add_column("Runtime", style=f"bold {self.theme.BLUE_SOFT}", width=20)
        table.add_column("Type", style=self.theme.TEXT_SECONDARY, width=12)
        table.add_column("Delivery", style=self.theme.TEXT_SECONDARY, width=14)
        table.add_column("Status", style=self.theme.TEXT_SECONDARY, width=16)
        table.add_column("Protocol", style=self.theme.TEXT_SECONDARY, width=14)
        table.add_column("Tools", style=self.theme.TEXT_SECONDARY, width=6)
        table.add_column("Source", style=self.theme.TEXT_DIM, width=16)
        table.add_column("Entry", style=self.theme.TEXT_PRIMARY, ratio=2)
        table.add_column("Notes", style=self.theme.TEXT_DIM, ratio=3)

        for row in rows:
            status = row.get("status", "")
            protocol_status = row.get("protocol_status", "")
            if status == "ready":
                status_color = self.theme.MINT_SOFT
            elif status == "entry-missing":
                status_color = self.theme.AMBER_GLOW
            elif status == "invalid-manifest":
                status_color = self.theme.CORAL_SOFT
            else:
                status_color = self.theme.TEXT_DIM

            if protocol_status == "supported":
                protocol_color = self.theme.MINT_SOFT
            elif protocol_status in ("timeout", "invalid-json", "error"):
                protocol_color = self.theme.CORAL_SOFT
            elif protocol_status == "unsupported":
                protocol_color = self.theme.AMBER_GLOW
            else:
                protocol_color = self.theme.TEXT_DIM

            table.add_row(
                row.get("name", ""),
                row.get("family", ""),
                row.get("delivery", ""),
                f"[{status_color}]{escape(row.get('status_label', ''))}[/{status_color}]",
                f"[{protocol_color}]{escape(row.get('protocol_label', ''))}[/{protocol_color}]",
                row.get("tool_count", "0"),
                row.get("source", ""),
                escape(row.get("entry", "-")),
                escape(row.get("notes", "")),
            )

        self.console.print(table)
        self.console.print()
        return True

    def _parse_plugins_action_tokens(self, args: str) -> tuple[List[str], Dict[str, str], set[str]]:
        """Split plugin subcommand args into positional tokens, key/value options, and flags."""
        tokens = self._split_command_args(args)
        positional: List[str] = []
        options: Dict[str, str] = {}
        flags: set[str] = set()
        for token in tokens:
            text = str(token or "").strip()
            if not text:
                continue
            lowered = text.lower()
            if lowered.startswith("--"):
                lowered = lowered[2:]
            if "=" in lowered:
                key, value = lowered.split("=", 1)
                options[key.strip()] = text.split("=", 1)[1].strip().strip('"').strip("'")
                continue
            if lowered in {"overwrite", "install", "dry-run", "dry_run", "download", "allow-heavy", "allow_heavy", "only-8gb", "only_8gb"}:
                flags.add(lowered)
                continue
            positional.append(text)
        return positional, options, flags

    def _bool_plugin_flag(self, flags: set[str], *names: str) -> bool:
        normalized = {item.replace("-", "_") for item in flags}
        return any(name.replace("-", "_") in normalized for name in names)

    def _ensure_game_models_protocol(self) -> tuple[bool, str]:
        """Install the source plugin if needed so user-facing model commands work."""
        runtime_plugin_manager = self.app.get('runtime_plugin_manager')
        if not runtime_plugin_manager:
            return False, "Runtime plugin manager is not available."

        record = runtime_plugin_manager.get_record("game_models", force_refresh=True)
        if record is not None and record.protocol_supported:
            return True, ""

        try:
            installed = runtime_plugin_manager.install_source_plugin("game_models", overwrite=False)
        except Exception as exc:
            return False, str(exc)
        if not installed.get("success", False):
            return False, str(installed.get("error") or "Unable to install source game_models plugin.")
        record = runtime_plugin_manager.get_record("game_models", force_refresh=True)
        if record is None or not record.protocol_supported:
            return False, "game_models plugin is installed but does not expose the RC protocol."
        return True, ""

    def _call_game_models_tool(self, command_name: str, payload: Dict[str, object]) -> Dict[str, object]:
        runtime_plugin_manager = self.app.get('runtime_plugin_manager')
        ready, error = self._ensure_game_models_protocol()
        if not ready:
            return {"success": False, "output": "", "error": error, "data": {}}
        try:
            return runtime_plugin_manager.call_tool("game_models", command_name, payload)
        except Exception as exc:
            return {"success": False, "output": "", "error": str(exc), "data": {}}

    def _cmd_plugins_models(self, args: str) -> bool:
        """User-facing helper for selecting and downloading game auxiliary models."""
        positional, options, flags = self._parse_plugins_action_tokens(args)
        action = positional[0].lower() if positional else "list"
        model_id = positional[1] if len(positional) > 1 else options.get("model", options.get("model_id", ""))
        if action not in {"list", "plan", "select", "download", "status"}:
            model_id = positional[0] if positional else model_id
            action = "status" if model_id else "list"

        payload: Dict[str, object] = {}
        if model_id:
            payload["model_id"] = model_id
        if options.get("repo") or options.get("repo_id"):
            payload["repo_id"] = options.get("repo") or options.get("repo_id", "")
        if options.get("profile"):
            payload["profile"] = options.get("profile", "")
        if options.get("ram") or options.get("ram_gb"):
            payload["ram_gb"] = options.get("ram") or options.get("ram_gb", "")
        if options.get("vram") or options.get("vram_gb"):
            payload["vram_gb"] = options.get("vram") or options.get("vram_gb", "")
        if options.get("revision"):
            payload["revision"] = options.get("revision", "")
        if self._bool_plugin_flag(flags, "dry_run", "dry-run"):
            payload["dry_run"] = True
        if self._bool_plugin_flag(flags, "allow_heavy", "allow-heavy"):
            payload["allow_heavy"] = True
        if self._bool_plugin_flag(flags, "download"):
            payload["download"] = True
        if self._bool_plugin_flag(flags, "only_8gb", "only-8gb"):
            payload["only_8gb"] = True

        command = {
            "list": "list_models",
            "plan": "deployment_plan",
            "select": "select_model",
            "download": "download_model",
            "status": "model_status",
        }[action]
        if action in {"select", "download", "status"} and not model_id and not payload.get("repo_id"):
            self.console.print(
                f"[{self.theme.AMBER_GLOW}]{self.deco.DOT_MEDIUM} Usage: /plugins models {action} <model-id> [profile=low_vram] [download] [dry_run] [allow_heavy][/{self.theme.AMBER_GLOW}]"
            )
            return True

        result = self._call_game_models_tool(command, payload)
        title = {
            "list": "Game Model Catalog",
            "plan": "Game Model Plan",
            "select": "Game Model Selection",
            "download": "Game Model Download",
            "status": "Game Model Status",
        }[action]
        self._show_command_panel(
            title,
            subtitle="Choose and deploy auxiliary open models inside `.reverie/plugins/game_models`.",
            accent=self.theme.BLUE_SOFT,
        )
        if not result.get("success", False):
            self._show_activity_event(
                "Game Models",
                "Command failed.",
                status="error",
                detail=str(result.get("error") or ""),
            )
            self.console.print()
            return True

        data = result.get("data", {}) if isinstance(result.get("data"), dict) else {}
        self._show_activity_event("Game Models", str(result.get("output") or "Command completed."), status="success")
        self.console.print()

        if action == "list":
            table = Table(box=box.ROUNDED, border_style=self.theme.BORDER_PRIMARY, expand=True)
            table.add_column("Model", style=f"bold {self.theme.BLUE_SOFT}", width=22)
            table.add_column("8GB", style=self.theme.TEXT_SECONDARY, width=6)
            table.add_column("Profile", style=self.theme.TEXT_SECONDARY, width=14)
            table.add_column("Repo", style=self.theme.TEXT_DIM, ratio=2)
            table.add_column("Role", style=self.theme.TEXT_DIM, ratio=3)
            for item in data.get("models", []) if isinstance(data.get("models"), list) else []:
                profile = str(item.get("default_profile", "default"))
                table.add_row(
                    str(item.get("id", "")),
                    "yes" if item.get("recommended_for_8gb_vram") else "no",
                    profile,
                    str(item.get("repo_id", "")),
                    str(item.get("pipeline_role", "")),
                )
            self.console.print(table)
        elif action == "plan":
            rows = []
            for section_name, items in (("Recommended", data.get("recommended", [])), ("Guarded/Blocked", data.get("guarded_or_blocked", []))):
                if isinstance(items, list):
                    for item in items:
                        profile = item.get("selected_profile", {}) if isinstance(item, dict) else {}
                        rows.append((
                            section_name,
                            str(item.get("id", "")),
                            str(profile.get("id", item.get("default_profile", "default"))),
                            str(item.get("repo_id", "")),
                        ))
            table = Table(box=box.ROUNDED, border_style=self.theme.BORDER_PRIMARY, expand=True)
            table.add_column("Bucket", style=self.theme.TEXT_SECONDARY, width=18)
            table.add_column("Model", style=f"bold {self.theme.BLUE_SOFT}", width=22)
            table.add_column("Profile", style=self.theme.TEXT_SECONDARY, width=14)
            table.add_column("Repo", style=self.theme.TEXT_DIM, ratio=2)
            for row in rows:
                table.add_row(*row)
            self.console.print(table)
        else:
            model = data.get("model", {}) if isinstance(data.get("model"), dict) else data.get("selected_model", {}).get("model", {}) if isinstance(data.get("selected_model"), dict) else {}
            profile = data.get("profile", {}) if isinstance(data.get("profile"), dict) else data.get("selected_model", {}).get("profile", {}) if isinstance(data.get("selected_model"), dict) else {}
            self.console.print(
                self._build_key_value_table(
                    [
                        ("Model", str(model.get("id", data.get("model_id", model_id)))),
                        ("Repo", str(model.get("repo_id", ""))),
                        ("Profile", str(profile.get("id", ""))),
                        ("Target", str(data.get("target") or data.get("path") or "")),
                        ("Manifest", str(data.get("manifest_path") or "")),
                        ("Cache Root", str(data.get("cache_root") or "")),
                    ]
                )
            )
        self.console.print()
        return True

    def _cmd_plugins_scaffold(self, args: str) -> bool:
        """Create a new source plugin tree from a bundled template."""
        runtime_plugin_manager = self.app.get('runtime_plugin_manager')
        if not runtime_plugin_manager:
            self.console.print(
                f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} Runtime plugin manager is not available.[/{self.theme.CORAL_SOFT}]"
            )
            return True

        positional, options, flags = self._parse_plugins_action_tokens(args)
        plugin_id = positional[0] if positional else ""
        if not plugin_id:
            self.console.print(
                f"[{self.theme.AMBER_GLOW}]{self.deco.DOT_MEDIUM} Usage: /plugins scaffold <plugin-id> [template=<template-id>] [family=<runtime-family>] [name=<display-name>] [description=<text>] [command=<primary-command>] [overwrite][/{self.theme.AMBER_GLOW}]"
            )
            return True

        template_id = options.get("template") or (positional[1] if len(positional) > 1 else "runtime_python_exe")
        runtime_family = options.get("family") or options.get("runtime_family") or "runtime"
        display_name = options.get("name") or options.get("display_name") or ""
        description = options.get("description") or ""
        command_name = options.get("command") or options.get("tool") or "run_task"

        result = runtime_plugin_manager.scaffold_source_plugin(
            template_id=template_id,
            plugin_id=plugin_id,
            display_name=display_name,
            runtime_family=runtime_family,
            description=description,
            command_name=command_name,
            overwrite="overwrite" in flags,
        )

        source_dir = result.get("source_dir")
        self._show_command_panel(
            "Plugin Scaffold",
            subtitle="Generate a source plugin workspace from a bundled runtime-plugin template.",
            accent=self.theme.BLUE_SOFT,
            meta=str(source_dir or runtime_plugin_manager.source_root),
        )

        if not result.get("success", False):
            self._show_activity_event(
                "Plugins",
                "Source plugin scaffold failed.",
                status="error",
                detail=str(result.get("error") or ""),
            )
            self.console.print()
            return True

        validation = result.get("validation", {}) or {}
        self.console.print(
            self._build_key_value_table(
                [
                    ("Plugin ID", validation.get("plugin_id", plugin_id)),
                    ("Template", result.get("template_id", template_id)),
                    ("Runtime Family", validation.get("runtime_family", runtime_family)),
                    ("Delivery", validation.get("delivery", "(unknown)")),
                    ("Source Dir", source_dir or "(none)"),
                ]
            )
        )
        self.console.print()

        created = [str(item) for item in result.get("files_created", []) if str(item).strip()]
        overwritten = [str(item) for item in result.get("files_overwritten", []) if str(item).strip()]
        self.console.print(
            Panel(
                "\n".join(created[:12]) if created else "(none)",
                title=f"[bold {self.theme.MINT_VIBRANT}]Created Files[/bold {self.theme.MINT_VIBRANT}]",
                border_style=self.theme.MINT_VIBRANT,
                box=box.ROUNDED,
            )
        )
        if overwritten:
            self.console.print()
            self.console.print(
                Panel(
                    "\n".join(overwritten[:12]),
                    title=f"[bold {self.theme.AMBER_GLOW}]Overwritten Files[/bold {self.theme.AMBER_GLOW}]",
                    border_style=self.theme.AMBER_GLOW,
                    box=box.ROUNDED,
                )
            )

        warnings = [str(item) for item in validation.get("warnings", []) if str(item).strip()]
        if warnings:
            self.console.print()
            self.console.print(
                Panel(
                    "\n".join(f"- {item}" for item in warnings[:10]),
                    title=f"[bold {self.theme.AMBER_GLOW}]Validation Notes[/bold {self.theme.AMBER_GLOW}]",
                    border_style=self.theme.AMBER_GLOW,
                    box=box.ROUNDED,
                )
            )

        self.console.print()
        return True

    def _cmd_plugins_validate(self, args: str) -> bool:
        """Validate one source plugin tree and summarize manifest/build health."""
        runtime_plugin_manager = self.app.get('runtime_plugin_manager')
        if not runtime_plugin_manager:
            self.console.print(
                f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} Runtime plugin manager is not available.[/{self.theme.CORAL_SOFT}]"
            )
            return True

        positional, _options, _flags = self._parse_plugins_action_tokens(args)
        plugin_id = positional[0] if positional else ""
        if not plugin_id:
            self.console.print(
                f"[{self.theme.AMBER_GLOW}]{self.deco.DOT_MEDIUM} Usage: /plugins validate <plugin-id>[/{self.theme.AMBER_GLOW}]"
            )
            return True

        validation = runtime_plugin_manager.validate_source_plugin(plugin_id)
        self._show_command_panel(
            f"Validate {plugin_id}",
            subtitle="Check source plugin manifest health, runtime handshake readiness, and build prerequisites.",
            accent=self.theme.BLUE_SOFT,
            meta=str(validation.get("source_dir", "")),
        )

        self.console.print(
            self._build_key_value_table(
                [
                    ("Plugin ID", validation.get("plugin_id", plugin_id)),
                    ("Runtime Family", validation.get("runtime_family", "(unknown)")),
                    ("Delivery", validation.get("delivery", "(unknown)")),
                    ("Template", validation.get("template_id", "(none)") or "(none)"),
                    ("Entry Strategy", validation.get("entry_strategy", "(none)") or "(none)"),
                    ("Packaging", validation.get("packaging_format", "(none)") or "(none)"),
                    ("Protocol", "RC Ready" if validation.get("protocol_supported") else validation.get("protocol_status", "unknown")),
                    ("Entry", validation.get("entry_path", "(none)") or "(none)"),
                ]
            )
        )
        self.console.print()

        errors = [str(item) for item in validation.get("errors", []) if str(item).strip()]
        warnings = [str(item) for item in validation.get("warnings", []) if str(item).strip()]
        unresolved = [str(item) for item in validation.get("unresolved_tokens", []) if str(item).strip()]

        if errors:
            self.console.print(
                Panel(
                    "\n".join(f"- {item}" for item in errors),
                    title=f"[bold {self.theme.CORAL_SOFT}]Errors[/bold {self.theme.CORAL_SOFT}]",
                    border_style=self.theme.CORAL_SOFT,
                    box=box.ROUNDED,
                )
            )
            self.console.print()

        if warnings:
            self.console.print(
                Panel(
                    "\n".join(f"- {item}" for item in warnings[:12]),
                    title=f"[bold {self.theme.AMBER_GLOW}]Warnings[/bold {self.theme.AMBER_GLOW}]",
                    border_style=self.theme.AMBER_GLOW,
                    box=box.ROUNDED,
                )
            )
            self.console.print()

        if unresolved:
            self.console.print(
                Panel(
                    "\n".join(unresolved[:12]),
                    title=f"[bold {self.theme.PURPLE_SOFT}]Unresolved Tokens[/bold {self.theme.PURPLE_SOFT}]",
                    border_style=self.theme.PURPLE_SOFT,
                    box=box.ROUNDED,
                )
            )
            self.console.print()

        build_commands = [str(item) for item in validation.get("build_commands", []) if str(item).strip()]
        if build_commands:
            self.console.print(
                Panel(
                    "\n".join(build_commands),
                    title=f"[bold {self.theme.BLUE_SOFT}]Build Commands[/bold {self.theme.BLUE_SOFT}]",
                    border_style=self.theme.BORDER_PRIMARY,
                    box=box.ROUNDED,
                )
            )
            self.console.print()

        return True

    def _cmd_plugins_build(self, args: str) -> bool:
        """Build one source plugin and optionally install it into `.reverie/plugins`."""
        runtime_plugin_manager = self.app.get('runtime_plugin_manager')
        if not runtime_plugin_manager:
            self.console.print(
                f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} Runtime plugin manager is not available.[/{self.theme.CORAL_SOFT}]"
            )
            return True

        positional, _options, flags = self._parse_plugins_action_tokens(args)
        plugin_id = positional[0] if positional else ""
        if not plugin_id:
            self.console.print(
                f"[{self.theme.AMBER_GLOW}]{self.deco.DOT_MEDIUM} Usage: /plugins build <plugin-id> [install] [overwrite][/{self.theme.AMBER_GLOW}]"
            )
            return True

        result = runtime_plugin_manager.build_source_plugin(
            plugin_id,
            install="install" in flags,
            overwrite_install="overwrite" in flags,
        )
        validation = result.get("validation", {}) or {}

        self._show_command_panel(
            f"Build {plugin_id}",
            subtitle="Run the declared plugin build commands and optionally sync the result into the runtime install root.",
            accent=self.theme.BLUE_SOFT,
            meta=str(validation.get("source_dir", runtime_plugin_manager.source_root)),
        )

        commands = result.get("commands", []) or []
        if not result.get("success", False):
            self._show_activity_event(
                "Plugins",
                "Plugin build failed.",
                status="error",
                detail=str(result.get("error") or ""),
            )
        else:
            self._show_activity_event(
                "Plugins",
                "Plugin build completed.",
                status="success",
                detail="Compiled entry resolved and validation passed.",
            )

        self.console.print()
        self.console.print(
            self._build_key_value_table(
                [
                    ("Plugin ID", validation.get("plugin_id", plugin_id)),
                    ("Compiled Entry", validation.get("compiled_entry_path", "(none)") or "(none)"),
                    ("Source Fallback", validation.get("source_entry_path", "(none)") or "(none)"),
                    ("Install Requested", "yes" if "install" in flags else "no"),
                    (
                        "Install Target",
                        (
                            ((result.get("install_result", {}) or {}).get("target_path") if isinstance(result.get("install_result"), dict) else "")
                            or ((result.get("install_result", {}) or {}).get("target_dir") if isinstance(result.get("install_result"), dict) else "")
                        )
                        or "(none)",
                    ),
                    (
                        "Install Mode",
                        ((result.get("install_result", {}) or {}).get("install_mode") if isinstance(result.get("install_result"), dict) else "")
                        or "directory-sync",
                    ),
                ]
            )
        )
        self.console.print()

        if commands:
            command_table = Table(
                title=f"[bold {self.theme.PINK_SOFT}]{self.deco.CRYSTAL} Build Steps[/bold {self.theme.PINK_SOFT}]",
                box=box.ROUNDED,
                border_style=self.theme.BORDER_PRIMARY,
                expand=True,
            )
            command_table.add_column("Command", style=f"bold {self.theme.BLUE_SOFT}", ratio=2)
            command_table.add_column("Status", style=self.theme.TEXT_SECONDARY, width=10)
            command_table.add_column("Detail", style=self.theme.TEXT_DIM, ratio=3)
            for item in commands:
                success = bool(item.get("success", False))
                status_color = self.theme.MINT_SOFT if success else self.theme.CORAL_SOFT
                detail = str(item.get("error") or item.get("stderr") or item.get("stdout") or "").strip()
                command_table.add_row(
                    str(item.get("command", "")),
                    f"[{status_color}]{'ok' if success else 'failed'}[/{status_color}]",
                    escape(self._truncate_middle(detail, 120) or "(no output)"),
                )
            self.console.print(command_table)
            self.console.print()

        if not result.get("success", False):
            return True

        warnings = [str(item) for item in validation.get("warnings", []) if str(item).strip()]
        if warnings:
            self.console.print(
                Panel(
                    "\n".join(f"- {item}" for item in warnings[:12]),
                    title=f"[bold {self.theme.AMBER_GLOW}]Warnings[/bold {self.theme.AMBER_GLOW}]",
                    border_style=self.theme.AMBER_GLOW,
                    box=box.ROUNDED,
                )
            )
            self.console.print()
        return True

    def _cmd_plugins_sdk(self, args: str) -> bool:
        """Inspect or prepare portable SDK/runtime plugin depots."""
        runtime_plugin_manager = self.app.get('runtime_plugin_manager')
        if not runtime_plugin_manager:
            self.console.print(
                f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} Runtime plugin manager is not available.[/{self.theme.CORAL_SOFT}]"
            )
            return True

        positional, _options, flags = self._parse_plugins_action_tokens(args)
        plugin_id = positional[0] if positional else ""
        if str(plugin_id).lower() in {"inspect", "prepare", "deploy"} and len(positional) > 1:
            plugin_id = positional[1]

        if plugin_id:
            result = runtime_plugin_manager.materialize_sdk_package(plugin_id, overwrite="overwrite" in flags)
            status = result.get("status", {}) if isinstance(result, dict) else {}
            self._show_command_panel(
                f"Plugin SDK {plugin_id}",
                subtitle="Prepare a portable SDK/runtime folder under `.reverie/plugins`.",
                accent=self.theme.BLUE_SOFT,
                meta=str(status.get("sdk_dir", "")),
            )
            if not result.get("success", False):
                self._show_activity_event(
                    "Plugins",
                    "SDK depot preparation failed.",
                    status="error",
                    detail=str(result.get("error") or ""),
                )
                self.console.print()
                return True

            self._show_activity_event(
                "Plugins",
                "SDK depot prepared.",
                status="success",
                detail="Portable SDK manifest and runtime folder are ready.",
            )
            self.console.print()
            self.console.print(
                self._build_key_value_table(
                    [
                        ("Plugin ID", status.get("plugin_id", plugin_id)),
                        ("Name", status.get("display_name", plugin_id)),
                        ("Status", status.get("status", "(unknown)")),
                        ("SDK Dir", status.get("sdk_dir", "")),
                        ("Manifest", status.get("manifest_path", "")),
                        ("Entry", status.get("entry_path") or "(not found yet)"),
                        ("Download Page", status.get("download_page", "") or "(none)"),
                        ("Install Hint", status.get("install_hint", "") or status.get("archive_hint", "") or "(none)"),
                    ]
                )
            )
            self.console.print()
            return True

        rows = runtime_plugin_manager.list_sdk_package_rows(force_refresh=False)
        summary = runtime_plugin_manager.get_status_summary(force_refresh=False)
        self._show_command_panel(
            "Plugin SDK Depot",
            subtitle="Portable SDK/runtime packages managed under `.reverie/plugins`.",
            accent=self.theme.BLUE_SOFT,
            meta=str(summary.get("sdk_root", summary.get("install_root", ""))),
        )

        self.console.print(
            self._build_key_value_table(
                [
                    ("SDK Root", summary.get("sdk_root", summary.get("install_root", ""))),
                    ("Known SDKs", str(len(rows))),
                    ("Prepare", "/plugins sdk blender"),
                ]
            )
        )
        self.console.print()

        table = Table(
            title=f"[bold {self.theme.PINK_SOFT}]{self.deco.CRYSTAL} Portable SDK Plugins[/bold {self.theme.PINK_SOFT}]",
            box=box.ROUNDED,
            border_style=self.theme.BORDER_PRIMARY,
            expand=True,
        )
        table.add_column("SDK", style=f"bold {self.theme.BLUE_SOFT}", width=18)
        table.add_column("Type", style=self.theme.TEXT_SECONDARY, width=10)
        table.add_column("Status", style=self.theme.TEXT_SECONDARY, width=10)
        table.add_column("Entry", style=self.theme.TEXT_PRIMARY, ratio=2)
        table.add_column("Hint", style=self.theme.TEXT_DIM, ratio=3)
        for row in rows:
            status = row.get("status", "missing")
            status_color = self.theme.MINT_SOFT if status == "ready" else (self.theme.AMBER_GLOW if status == "prepared" else self.theme.TEXT_DIM)
            table.add_row(
                row.get("name", ""),
                row.get("family", ""),
                f"[{status_color}]{escape(status)}[/{status_color}]",
                escape(row.get("entry", "-")),
                escape(row.get("hint", "")),
            )
        self.console.print(table)
        self.console.print()
        return True

    def _cmd_plugins_deploy(self, args: str) -> bool:
        """Deploy a portable SDK package into `.reverie/plugins/<plugin-id>/runtime`."""
        runtime_plugin_manager = self.app.get('runtime_plugin_manager')
        if not runtime_plugin_manager:
            self.console.print(
                f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} Runtime plugin manager is not available.[/{self.theme.CORAL_SOFT}]"
            )
            return True

        positional, options, flags = self._parse_plugins_action_tokens(args)
        plugin_id = positional[0] if positional else ""
        if not plugin_id:
            self.console.print(
                f"[{self.theme.AMBER_GLOW}]{self.deco.DOT_MEDIUM} Usage: /plugins deploy <plugin-id> [archive=<zip-path>] [overwrite][/{self.theme.AMBER_GLOW}]"
            )
            return True

        result = runtime_plugin_manager.deploy_sdk_package(
            plugin_id,
            archive_path=options.get("archive", ""),
            overwrite="overwrite" in flags,
        )
        status = result.get("status", {}) if isinstance(result, dict) else {}
        self._show_command_panel(
            f"Deploy {plugin_id}",
            subtitle="Extract a portable SDK archive beside the executable.",
            accent=self.theme.BLUE_SOFT,
            meta=str(status.get("sdk_dir", "")),
        )
        if not result.get("success", False):
            self._show_activity_event(
                "Plugins",
                "Plugin deployment failed.",
                status="error",
                detail=str(result.get("error") or ""),
            )
            self.console.print()
            return True

        self._show_activity_event(
            "Plugins",
            "Plugin deployment completed.",
            status="success",
            detail=f"Archive extracted into {status.get('sdk_dir', '')}",
        )
        self.console.print()
        self.console.print(
            self._build_key_value_table(
                [
                    ("Plugin ID", status.get("plugin_id", plugin_id)),
                    ("Archive", result.get("archive_path", "(none)") or "(none)"),
                    ("SDK Dir", status.get("sdk_dir", "")),
                    ("Entry", status.get("entry_path") or "(not detected)"),
                    ("Extracted Items", str(result.get("extracted_count", 0))),
                ]
            )
        )
        self.console.print()
        return True

    def _cmd_plugins_run(self, args: str) -> bool:
        """Launch one portable SDK plugin for the user."""
        runtime_plugin_manager = self.app.get('runtime_plugin_manager')
        if not runtime_plugin_manager:
            self.console.print(
                f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} Runtime plugin manager is not available.[/{self.theme.CORAL_SOFT}]"
            )
            return True

        positional, _options, _flags = self._parse_plugins_action_tokens(args)
        plugin_id = positional[0] if positional else ""
        if not plugin_id:
            self.console.print(
                f"[{self.theme.AMBER_GLOW}]{self.deco.DOT_MEDIUM} Usage: /plugins run <plugin-id>[/{self.theme.AMBER_GLOW}]"
            )
            return True

        result = runtime_plugin_manager.run_sdk_package(plugin_id)
        status = result.get("status", {}) if isinstance(result, dict) else {}
        self._show_command_panel(
            f"Run {plugin_id}",
            subtitle="Launch the portable SDK/runtime entry.",
            accent=self.theme.BLUE_SOFT,
            meta=str(status.get("entry_path", "")),
        )
        if not result.get("success", False):
            self._show_activity_event(
                "Plugins",
                "Plugin launch failed.",
                status="error",
                detail=str(result.get("error") or ""),
            )
            self.console.print()
            return True

        self._show_activity_event(
            "Plugins",
            "Plugin launched.",
            status="success",
            detail=f"PID {result.get('pid', '?')}",
        )
        self.console.print()
        self.console.print(
            self._build_key_value_table(
                [
                    ("Plugin ID", status.get("plugin_id", plugin_id)),
                    ("Entry", status.get("entry_path", "")),
                    ("PID", str(result.get("pid", ""))),
                    ("Command", " ".join(str(item) for item in result.get("command", []))),
                ]
            )
        )
        self.console.print()
        return True

    def _cmd_plugins_templates(self, args: str) -> bool:
        """Inspect available source templates for runtime plugins."""
        runtime_plugin_manager = self.app.get('runtime_plugin_manager')
        if not runtime_plugin_manager:
            self.console.print(
                f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} Runtime plugin manager is not available.[/{self.theme.CORAL_SOFT}]"
            )
            return True

        query = str(args or "").strip()
        lowered = query.lower()
        if lowered.startswith("inspect "):
            return self._cmd_plugins_template_inspect(query[8:].strip())
        if query and lowered not in {"", "list", "status"}:
            return self._cmd_plugins_template_inspect(query)

        rows = runtime_plugin_manager.list_template_rows(force_refresh=False)
        summary = runtime_plugin_manager.get_status_summary(force_refresh=False)

        self._show_command_panel(
            "Plugin Templates",
            subtitle="Source templates for authoring compiled runtime plugins with Reverie CLI protocol support.",
            accent=self.theme.BLUE_SOFT,
            meta=str(summary.get("template_root", "")),
        )

        self.console.print(
            self._build_key_value_table(
                [
                    ("Template Root", summary.get("template_root", "")),
                    ("Template Count", str(summary.get("template_count", 0))),
                    ("Recommended", "runtime_python_exe" if rows else "(none bundled)"),
                ]
            )
        )
        self.console.print()

        if not rows:
            self.console.print(
                f"[{self.theme.TEXT_DIM}]{self.deco.DOT_MEDIUM} No plugin templates are currently available.[/{self.theme.TEXT_DIM}]"
            )
            self.console.print()
            return True

        table = Table(
            title=f"[bold {self.theme.PINK_SOFT}]{self.deco.CRYSTAL} Runtime Plugin Templates[/bold {self.theme.PINK_SOFT}]",
            box=box.ROUNDED,
            border_style=self.theme.BORDER_PRIMARY,
            expand=True,
        )
        table.add_column("Template", style=f"bold {self.theme.BLUE_SOFT}", width=24)
        table.add_column("Delivery", style=self.theme.TEXT_SECONDARY, width=14)
        table.add_column("Entry", style=self.theme.TEXT_SECONDARY, width=18)
        table.add_column("Manifest", style=self.theme.TEXT_SECONDARY, width=18)
        table.add_column("Build", style=self.theme.TEXT_DIM, width=22)
        table.add_column("Description", style=self.theme.TEXT_PRIMARY, ratio=3)

        for row in rows:
            table.add_row(
                row.get("id", ""),
                row.get("delivery", ""),
                row.get("entry_template", "-"),
                row.get("manifest_template", "-"),
                self._truncate_middle(row.get("build_hint", ""), 22) or "-",
                row.get("description", ""),
            )

        self.console.print(table)
        self.console.print()
        self.console.print(
            Panel(
                Text.from_markup(
                    f"[bold {self.theme.BLUE_SOFT}]/plugins templates[/bold {self.theme.BLUE_SOFT}] list available templates\n"
                    f"[bold {self.theme.BLUE_SOFT}]/plugins template inspect <template-id>[/bold {self.theme.BLUE_SOFT}] inspect one template"
                ),
                title=f"[bold {self.theme.PURPLE_SOFT}]{self.deco.DIAMOND} Shortcuts[/bold {self.theme.PURPLE_SOFT}]",
                border_style=self.theme.BORDER_SUBTLE,
                box=box.ROUNDED,
                padding=(0, 1),
            )
        )
        self.console.print()
        return True

    def _cmd_plugins_template_inspect(self, template_id: str) -> bool:
        """Inspect one runtime-plugin authoring template."""
        runtime_plugin_manager = self.app.get('runtime_plugin_manager')
        if not runtime_plugin_manager:
            self.console.print(
                f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} Runtime plugin manager is not available.[/{self.theme.CORAL_SOFT}]"
            )
            return True

        wanted = str(template_id or "").strip()
        if not wanted:
            self.console.print(
                f"[{self.theme.AMBER_GLOW}]{self.deco.DOT_MEDIUM} Usage: /plugins template inspect <template-id>[/{self.theme.AMBER_GLOW}]"
            )
            return True

        record = runtime_plugin_manager.get_template(wanted, force_refresh=False)
        if record is None:
            self.console.print(
                f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} Runtime plugin template not found: {escape(wanted)}[/{self.theme.CORAL_SOFT}]"
            )
            return True

        self._show_command_panel(
            f"Template {record.display_name}",
            subtitle="Reusable source template for Reverie CLI runtime plugins.",
            accent=self.theme.BLUE_SOFT,
            meta=str(record.template_dir),
        )

        overview = self._build_key_value_table(
            [
                ("Template ID", record.template_id),
                ("Delivery", record.delivery),
                ("Entry Template", record.entry_template or "(none)"),
                ("Manifest Template", record.manifest_template or "(none)"),
                ("Build Hint", record.build_hint or "(none)"),
                ("Template Dir", record.template_dir),
            ]
        )
        self.console.print(overview)
        self.console.print()

        if record.description:
            self.console.print(
                Panel(
                    escape(record.description),
                    title=f"[bold {self.theme.PINK_SOFT}]Description[/bold {self.theme.PINK_SOFT}]",
                    border_style=self.theme.BORDER_SUBTLE,
                    box=box.ROUNDED,
                )
            )
            self.console.print()

        files_table = Table(
            title=f"[bold {self.theme.PURPLE_SOFT}]{self.deco.CRYSTAL} Template Files[/bold {self.theme.PURPLE_SOFT}]",
            box=box.ROUNDED,
            border_style=self.theme.BORDER_SUBTLE,
            expand=True,
        )
        files_table.add_column("Path", style=f"bold {self.theme.BLUE_SOFT}", ratio=2)
        files_table.add_column("Kind", style=self.theme.TEXT_SECONDARY, width=16)
        files_table.add_column("Bytes", style=self.theme.TEXT_DIM, width=10)

        template_files = sorted(
            [item for item in record.template_dir.rglob("*") if item.is_file()],
            key=lambda path: str(path.relative_to(record.template_dir)).lower(),
        )
        for item in template_files:
            relative_path = str(item.relative_to(record.template_dir))
            kind = item.suffix.lstrip(".") or "file"
            try:
                size_text = str(item.stat().st_size)
            except Exception:
                size_text = "?"
            files_table.add_row(relative_path, kind, size_text)
        self.console.print(files_table)
        self.console.print()

        previews: list[tuple[str, str, str]] = []
        manifest_path = record.template_dir / record.manifest_template
        if manifest_path.is_file():
            previews.append(("Manifest Preview", str(manifest_path), "json"))
        entry_path = record.template_dir / record.entry_template
        if entry_path.is_file():
            previews.append(("Entry Preview", str(entry_path), "python"))

        for title, path_text, language in previews:
            try:
                content = Path(path_text).read_text(encoding="utf-8")
            except Exception as exc:
                content = f"Failed to read template preview: {exc}"
                language = "text"
            self.console.print(
                Panel(
                    Syntax(content, language, theme="monokai", line_numbers=False, word_wrap=False),
                    title=f"[bold {self.theme.BLUE_SOFT}]{escape(title)}[/bold {self.theme.BLUE_SOFT}]",
                    subtitle=self._truncate_middle(path_text, 88),
                    border_style=self.theme.BORDER_PRIMARY,
                    box=box.ROUNDED,
                    padding=(0, 1),
                )
            )
            self.console.print()
        return True

    def _cmd_plugins_inspect(self, plugin_id: str) -> bool:
        """Inspect one runtime plugin and its RC protocol metadata."""
        runtime_plugin_manager = self.app.get('runtime_plugin_manager')
        if not runtime_plugin_manager:
            self.console.print(
                f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} Runtime plugin manager is not available.[/{self.theme.CORAL_SOFT}]"
            )
            return True

        wanted = str(plugin_id or "").strip()
        if not wanted:
            self.console.print(
                f"[{self.theme.AMBER_GLOW}]{self.deco.DOT_MEDIUM} Usage: /plugins inspect <plugin-id>[/{self.theme.AMBER_GLOW}]"
            )
            return True

        record = runtime_plugin_manager.get_record(wanted, force_refresh=False)
        if record is None:
            self.console.print(
                f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} Runtime plugin not found: {escape(wanted)}[/{self.theme.CORAL_SOFT}]"
            )
            return True

        self._show_command_panel(
            f"Plugin {record.display_name}",
            subtitle="Reverie CLI runtime plugin protocol details.",
            accent=self.theme.BLUE_SOFT,
            meta=record.install_display,
        )

        overview = self._build_key_value_table(
            [
                ("Plugin ID", record.plugin_id),
                ("Runtime Type", record.runtime_family),
                ("Delivery", record.delivery_label),
                ("Entry Status", record.status_label),
                ("Protocol", record.protocol_label),
                ("Entry", record.entry_display),
                ("Compiled Entry", record.compiled_entry_display),
                ("Source Fallback", record.source_entry_display),
                ("Entry Strategy", record.entry_strategy or "(default)"),
                ("Packaging", record.packaging_format or "(default)"),
                ("Manifest Schema", record.manifest_schema_version or "(legacy)"),
                ("Template", record.template_id or "(none)"),
                ("Build Commands", ", ".join(record.build_commands) if record.build_commands else "(none)"),
                ("Version", record.version or "(none)"),
                ("Manifest", record.manifest_path or "(none)"),
                ("Install Dir", record.install_display),
            ]
        )
        self.console.print(overview)
        self.console.print()

        if record.manifest_warnings:
            warning_lines = "\n".join(f"- {item}" for item in record.manifest_warnings)
            self.console.print(
                Panel(
                    warning_lines,
                    title=f"[bold {self.theme.AMBER_GLOW}]Manifest Warnings[/bold {self.theme.AMBER_GLOW}]",
                    border_style=self.theme.AMBER_GLOW,
                    box=box.ROUNDED,
                )
            )
            self.console.print()

        if record.protocol is None:
            message = record.protocol_error or "This runtime has not responded to the Reverie CLI `-RC` handshake yet."
            self.console.print(
                Panel(
                    escape(message),
                    title=f"[bold {self.theme.AMBER_GLOW}]RC Status[/bold {self.theme.AMBER_GLOW}]",
                    border_style=self.theme.AMBER_GLOW,
                    box=box.ROUNDED,
                )
            )
            self.console.print()
            return True

        protocol = record.protocol
        protocol_rows = [
            ("Protocol Version", protocol.protocol_version),
            ("Display Name", protocol.display_name),
            ("Tool Call Hint", protocol.tool_call_hint or "(none)"),
            ("System Prompt", protocol.system_prompt or "(none)"),
            ("Commands", str(len(protocol.commands))),
            ("Exposed Tools", str(len(protocol.tool_commands))),
        ]
        self.console.print(self._build_key_value_table(protocol_rows))
        self.console.print()

        table = Table(
            title=f"[bold {self.theme.PINK_SOFT}]{self.deco.CRYSTAL} RC Commands[/bold {self.theme.PINK_SOFT}]",
            box=box.ROUNDED,
            border_style=self.theme.BORDER_PRIMARY,
            expand=True,
        )
        table.add_column("Command", style=f"bold {self.theme.BLUE_SOFT}", width=20)
        table.add_column("Tool", style=self.theme.TEXT_SECONDARY, width=28)
        table.add_column("As Tool", style=self.theme.TEXT_SECONDARY, width=8)
        table.add_column("Modes", style=self.theme.TEXT_DIM, width=20)
        table.add_column("Description", style=self.theme.TEXT_PRIMARY, ratio=3)

        plugin_tool_map = {
            (str(item.get("plugin_id", "")), str(item.get("command_name", ""))): str(item.get("name", ""))
            for item in runtime_plugin_manager.get_tool_definitions(force_refresh=False)
        }

        for command in protocol.commands:
            include_modes = ", ".join(command.include_modes) if command.include_modes else "all modes"
            if command.exclude_modes:
                include_modes = f"{include_modes} / !{', '.join(command.exclude_modes)}"
            table.add_row(
                command.name,
                plugin_tool_map.get((record.plugin_id, command.name), "(not exposed)"),
                "yes" if command.expose_as_tool else "no",
                include_modes,
                command.description,
            )

        self.console.print(table)
        self.console.print()
        return True

    def _format_model_source_label(self, source: str) -> str:
        """Return a readable model source label."""
        mapping = {
            "standard": "config.json",
            "geminicli": "Gemini CLI",
            "codex": "Codex",
            "nvidia": "NVIDIA",
            "modelscope": "ModelScope",
        }
        return mapping.get(str(source or "").strip().lower(), "config.json")

    def _configure_provider_endpoint(
        self,
        *,
        config_attr: str,
        normalize_config: Callable[[Any], Dict[str, Any]],
        provider_label: str,
        endpoint_value: str,
    ) -> bool:
        """Configure endpoint override for an external provider."""
        config_manager = self.app.get('config_manager')
        if not config_manager:
            self.console.print(
                f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} Config manager not available[/{self.theme.CORAL_SOFT}]"
            )
            return True

        config = config_manager.load()
        provider_cfg = normalize_config(getattr(config, config_attr, {}))

        candidate = str(endpoint_value or "").strip()
        if not candidate:
            current_endpoint = str(provider_cfg.get("endpoint", "")).strip()
            placeholder = current_endpoint or "(none)"
            self.console.print(
                f"[{self.theme.TEXT_DIM}]Current endpoint override: {placeholder}[/{self.theme.TEXT_DIM}]"
            )
            self.console.print(
                f"[{self.theme.TEXT_DIM}]Use 'clear' to remove endpoint override.[/{self.theme.TEXT_DIM}]"
            )
            candidate = Prompt.ask(
                "Endpoint override (absolute URL or relative path)",
                default=current_endpoint
            ).strip()

        lowered = candidate.lower()
        if lowered in ("clear", "default", "none", "off"):
            candidate = ""

        if candidate and not (
            candidate.startswith("http://")
            or candidate.startswith("https://")
            or candidate.startswith("/")
        ):
            self.console.print(
                f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} Invalid endpoint. Use absolute URL or path starting with '/'.[/{self.theme.CORAL_SOFT}]"
            )
            return True

        provider_cfg["endpoint"] = candidate
        setattr(config, config_attr, provider_cfg)
        config_manager.save(config)

        self.console.print()
        if candidate:
            self.console.print(
                f"[{self.theme.MINT_VIBRANT}]{self.deco.CHECK_FANCY} {provider_label} endpoint override set to: {candidate}[/{self.theme.MINT_VIBRANT}]"
            )
        else:
            self.console.print(
                f"[{self.theme.MINT_VIBRANT}]{self.deco.CHECK_FANCY} {provider_label} endpoint override cleared.[/{self.theme.MINT_VIBRANT}]"
            )

        if self.app.get('reinit_agent'):
            self.app['reinit_agent']()

        self.console.print()
        return True

    def _resolve_catalog_selection(
        self,
        *,
        catalog,
        current_selected_id: str,
        model_query: str,
        provider_label: str,
        normalize_query: Optional[Callable[[str], str]] = None,
    ):
        """Resolve selected model by query or TUI selector."""
        selected_model = None
        query = str(model_query or "").strip().lower()
        normalized_query = ""
        if query and normalize_query:
            try:
                normalized_query = str(normalize_query(query) or "").strip().lower()
            except Exception:
                normalized_query = ""

        if query:
            exact_queries = [query]
            if normalized_query and normalized_query not in exact_queries:
                exact_queries.append(normalized_query)

            for item in catalog:
                model_id = str(item.get("id", "")).lower()
                name = str(item.get("display_name", "")).lower()
                if any(q == model_id or q == name for q in exact_queries):
                    selected_model = item
                    break

            if not selected_model:
                partial_queries = [query]
                if normalized_query and normalized_query not in partial_queries:
                    partial_queries.append(normalized_query)
                for item in catalog:
                    model_id = str(item.get("id", "")).lower()
                    name = str(item.get("display_name", "")).lower()
                    if any(q and (q in model_id or q in name) for q in partial_queries):
                        selected_model = item
                        break

            if not selected_model:
                self.console.print(
                    f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} {provider_label} model not found: {model_query}[/{self.theme.CORAL_SOFT}]"
                )
                self.console.print(
                    f"[{self.theme.TEXT_DIM}]Use /{provider_label.lower().replace(' ', '')} model to open the full selector.[/{self.theme.TEXT_DIM}]"
                )
                return None
            return selected_model

        from .tui_selector import ModelSelector, SelectorAction

        models_data = []
        current_model_id = None
        selected_id = str(current_selected_id or "").strip().lower()
        for i, item in enumerate(catalog):
            model_id = str(item.get("id", ""))
            description_parts = [model_id]
            visibility = str(item.get("visibility", "")).strip().lower()
            if visibility:
                description_parts.append("hidden" if visibility == "hide" else visibility)
            context_length = item.get("context_length")
            if context_length:
                try:
                    description_parts.append(f"{int(context_length):,} ctx")
                except (TypeError, ValueError):
                    pass
            item_description = str(item.get("description", "") or "").strip()
            if item_description:
                description_parts.append(item_description)
            description = " | ".join(description_parts)
            models_data.append(
                {
                    "id": str(i),
                    "name": item.get("display_name", model_id),
                    "description": description,
                    "model": item,
                }
            )
            if model_id.lower() == selected_id:
                current_model_id = str(i)

        selector = ModelSelector(
            console=self.console,
            models=models_data,
            current_model=current_model_id
        )
        result = selector.run()
        if result.action != SelectorAction.SELECT or not result.selected_item:
            return None

        try:
            selected_index = int(result.selected_item.id)
        except (TypeError, ValueError):
            self.console.print(
                f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} Invalid {provider_label} model selection.[/{self.theme.CORAL_SOFT}]"
            )
            return None

        if selected_index < 0 or selected_index >= len(catalog):
            self.console.print(
                f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} Invalid {provider_label} model index.[/{self.theme.CORAL_SOFT}]"
            )
            return None

        return catalog[selected_index]

    def _select_external_provider_model(
        self,
        *,
        config_attr: str,
        normalize_config: Callable[[Any], Dict[str, Any]],
        catalog,
        provider_label: str,
        active_source: str,
        model_query: str,
        normalize_query: Optional[Callable[[str], str]] = None,
        post_select_config: Optional[Callable[[Dict[str, Any], Dict[str, Any]], Dict[str, Any]]] = None,
    ) -> bool:
        """Persist model selection for an external provider."""
        config_manager = self.app.get('config_manager')
        if not config_manager:
            self.console.print(
                f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} Config manager not available[/{self.theme.CORAL_SOFT}]"
            )
            return True

        if not catalog:
            self.console.print(
                f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} {provider_label} model catalog is empty.[/{self.theme.CORAL_SOFT}]"
            )
            return True

        config = config_manager.load()
        provider_cfg = normalize_config(getattr(config, config_attr, {}))
        selected_model = self._resolve_catalog_selection(
            catalog=catalog,
            current_selected_id=str(provider_cfg.get("selected_model_id", "")),
            model_query=model_query,
            provider_label=provider_label,
            normalize_query=normalize_query,
        )
        if not selected_model:
            return True

        provider_cfg["selected_model_id"] = selected_model["id"]
        provider_cfg["selected_model_display_name"] = selected_model["display_name"]
        if post_select_config is not None:
            provider_cfg = post_select_config(provider_cfg, selected_model)
        setattr(config, config_attr, provider_cfg)
        config.active_model_source = active_source
        config_manager.save(config)

        self.console.print()
        self.console.print(
            f"[{self.theme.MINT_VIBRANT}]{self.deco.CHECK_FANCY} Switched to {provider_label} model: {selected_model['display_name']} ({selected_model['id']})[/{self.theme.MINT_VIBRANT}]"
        )

        if self.app.get('reinit_agent'):
            self.app['reinit_agent']()

        return True

    def _ensure_nvidia_configuration(self, config) -> bool:
        """Prompt for NVIDIA API key when needed and bind the source."""
        from ..nvidia import (
            NVIDIA_API_KEY_HINT_URL,
            get_nvidia_default_vision_model,
            normalize_nvidia_config,
            resolve_nvidia_selected_model,
            resolve_nvidia_api_key,
        )

        nvidia_cfg = normalize_nvidia_config(getattr(config, "nvidia", {}))
        api_key = resolve_nvidia_api_key(nvidia_cfg)
        if not api_key:
            self.console.print()
            self.console.print(
                f"[{self.theme.TEXT_DIM}]Computer Controller mode uses a NVIDIA request-based vision model. Get an API key from {NVIDIA_API_KEY_HINT_URL} and paste it here to continue.[/{self.theme.TEXT_DIM}]"
            )
            api_key = Prompt.ask(
                f"[{self.theme.BLUE_SOFT}]{self.deco.CHEVRON_RIGHT}[/{self.theme.BLUE_SOFT}] NVIDIA API Key",
                password=True,
            ).strip()
            if not api_key:
                self.console.print(
                    f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} NVIDIA API key is required for Computer Controller mode.[/{self.theme.CORAL_SOFT}]"
                )
                return False
        nvidia_cfg["api_key"] = api_key

        selected = resolve_nvidia_selected_model(nvidia_cfg)
        if not selected or str(selected.get("transport", "")).strip().lower() != "request" or not bool(selected.get("vision")):
            fallback = get_nvidia_default_vision_model()
            nvidia_cfg["selected_model_id"] = fallback["id"]
            nvidia_cfg["selected_model_display_name"] = fallback["display_name"]
            self.console.print(
                f"[{self.theme.AMBER_GLOW}]{self.deco.DOT_MEDIUM} Computer Controller requires a NVIDIA request-based vision model, so Reverie switched this source to {fallback['display_name']}.[/{self.theme.AMBER_GLOW}]"
            )

        config.nvidia = normalize_nvidia_config(nvidia_cfg)
        config.active_model_source = "nvidia"
        return True

    def _prepare_computer_controller_nvidia_configuration(self, config) -> bool:
        """Pin Computer Controller mode to the fixed NVIDIA request model."""
        from ..nvidia import (
            NVIDIA_COMPUTER_CONTROLLER_MODEL_ID,
            NVIDIA_COMPUTER_CONTROLLER_MODEL_DISPLAY_NAME,
            build_nvidia_computer_controller_runtime_model_data,
            normalize_nvidia_config,
        )

        if not self._ensure_nvidia_configuration(config):
            return False

        nvidia_cfg = normalize_nvidia_config(getattr(config, "nvidia", {}))
        runtime_nvidia = build_nvidia_computer_controller_runtime_model_data(nvidia_cfg)
        if not runtime_nvidia:
            self.console.print(
                f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} Computer Controller mode requires a NVIDIA API key in config or NVIDIA_API_KEY before it can start.[/{self.theme.CORAL_SOFT}]"
            )
            return False

        nvidia_cfg["enabled"] = True
        nvidia_cfg["api_key"] = runtime_nvidia.get("api_key", "")
        nvidia_cfg["selected_model_id"] = str(runtime_nvidia.get("model", NVIDIA_COMPUTER_CONTROLLER_MODEL_ID))
        nvidia_cfg["selected_model_display_name"] = str(
            runtime_nvidia.get("model_display_name", NVIDIA_COMPUTER_CONTROLLER_MODEL_DISPLAY_NAME)
        )
        config.nvidia = normalize_nvidia_config(nvidia_cfg)
        config.active_model_source = "nvidia"
        return True

    def _apply_mode_selection(self, config, candidate: str) -> bool:
        """Apply normalized mode changes with any mode-specific provider setup."""
        normalized_mode = normalize_mode(candidate)
        config.mode = normalized_mode
        if normalized_mode == "computer-controller":
            return self._prepare_computer_controller_nvidia_configuration(config)
        return True

    def cmd_geminicli(self, args: str) -> bool:
        """Gemini CLI integration command."""
        raw = args.strip()
        if not raw:
            return self._cmd_geminicli_status()

        lowered = raw.lower()
        if lowered in ("status", "check"):
            return self._cmd_geminicli_status()
        if lowered == "login":
            return self._cmd_geminicli_login()
        if lowered == "model":
            return self._cmd_geminicli_model("")
        if lowered.startswith("model "):
            return self._cmd_geminicli_model(raw[6:].strip())
        if lowered == "endpoint":
            return self._cmd_geminicli_endpoint("")
        if lowered.startswith("endpoint "):
            return self._cmd_geminicli_endpoint(raw[9:].strip())
        if lowered == "project":
            return self._cmd_geminicli_project("")
        if lowered.startswith("project "):
            return self._cmd_geminicli_project(raw[8:].strip())

        self.console.print(
            f"[{self.theme.AMBER_GLOW}]{self.deco.DOT_MEDIUM} Usage: /Geminicli [status|login|model|endpoint][/{self.theme.AMBER_GLOW}]"
        )
        return True

    def _cmd_geminicli_status(self) -> bool:
        """Detect local Gemini CLI credentials and show current Gemini selection."""
        from ..geminicli import (
            detect_geminicli_cli_credentials,
            infer_geminicli_project_id,
            normalize_geminicli_config,
            resolve_geminicli_selected_model,
        )

        config_manager = self.app.get('config_manager')
        config = config_manager.load() if config_manager else None

        cred = detect_geminicli_cli_credentials(refresh_if_needed=True)
        self.console.print()

        if cred.get("found"):
            self.console.print(
                f"[{self.theme.MINT_VIBRANT}]{self.deco.CHECK_FANCY} Gemini CLI credentials detected.[/{self.theme.MINT_VIBRANT}]"
            )
            self.console.print(
                f"[{self.theme.MINT_SOFT}]Gemini CLI is installed and logged in. Use /Geminicli model to select a model.[/{self.theme.MINT_SOFT}]"
            )
            if cred.get("refreshed"):
                self.console.print(
                    f"[{self.theme.MINT_SOFT}]Access token was auto-refreshed from local OAuth cache.[/{self.theme.MINT_SOFT}]"
                )
            source_file = cred.get("source_file", "")
            if source_file:
                self.console.print(
                    f"[{self.theme.TEXT_DIM}]Credential source: {source_file}[/{self.theme.TEXT_DIM}]"
                )
            email = str(cred.get("email", "")).strip()
            if email:
                self.console.print(
                    f"[{self.theme.TEXT_DIM}]Active account: {email}[/{self.theme.TEXT_DIM}]"
                )
            expires_at = cred.get("expires_at")
            if isinstance(expires_at, int) and expires_at > 0:
                expires_at_text = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(expires_at / 1000))
                self.console.print(
                    f"[{self.theme.TEXT_DIM}]Token expiry: {expires_at_text}[/{self.theme.TEXT_DIM}]"
                )
        else:
            self.console.print(
                f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} Gemini CLI credentials were not found under ~/.gemini.[/{self.theme.CORAL_SOFT}]"
            )
            self.console.print(
                f"[{self.theme.AMBER_GLOW}]Use /Geminicli login to authenticate, or install Gemini CLI first.[/{self.theme.AMBER_GLOW}]"
            )
            if cred.get("errors"):
                self.console.print(
                    f"[{self.theme.TEXT_DIM}]Details: {' | '.join(str(x) for x in cred.get('errors', []))}[/{self.theme.TEXT_DIM}]"
                )

        if config_manager and config:
            geminicli_cfg = normalize_geminicli_config(getattr(config, "geminicli", {}))
            selected = resolve_geminicli_selected_model(geminicli_cfg)
            agent = self.app.get('agent')
            project_root = self.app.get('project_root') or getattr(agent, 'project_root', None) or Path.cwd()
            if selected:
                self.console.print(
                    f"[{self.theme.BLUE_SOFT}]Current Gemini model:[/{self.theme.BLUE_SOFT}] {selected['display_name']} ({selected['id']})"
                )
                context_length = selected.get('context_length', 0)
                if context_length:
                    self.console.print(
                        f"[{self.theme.TEXT_DIM}]Context length: {context_length:,} tokens[/{self.theme.TEXT_DIM}]"
                    )
            else:
                self.console.print(
                    f"[{self.theme.TEXT_DIM}]Current Gemini model: (none)[/{self.theme.TEXT_DIM}]"
                )

            model_source = str(getattr(config, "active_model_source", "standard")).lower()
            self.console.print(
                f"[{self.theme.BLUE_SOFT}]Active model source:[/{self.theme.BLUE_SOFT}] {self._format_model_source_label(model_source)}"
            )

            configured_project = str(geminicli_cfg.get("project_id", "")).strip()
            inferred_project = infer_geminicli_project_id(project_root)
            if configured_project:
                self.console.print(
                    f"[{self.theme.TEXT_DIM}]Gemini project override: {configured_project} (optional)[/{self.theme.TEXT_DIM}]"
                )
            elif inferred_project:
                self.console.print(
                    f"[{self.theme.TEXT_DIM}]Gemini project override (inferred): {inferred_project} (optional)[/{self.theme.TEXT_DIM}]"
                )
            else:
                self.console.print(
                    f"[{self.theme.TEXT_DIM}]Gemini project override: (none, personal Google login works without it)[/{self.theme.TEXT_DIM}]"
                )

            api_url = str(geminicli_cfg.get("api_url", "")).strip()
            if api_url:
                self.console.print(
                    f"[{self.theme.TEXT_DIM}]Gemini API endpoint: {api_url}[/{self.theme.TEXT_DIM}]"
                )
            endpoint = str(geminicli_cfg.get("endpoint", "")).strip()
            if endpoint:
                self.console.print(
                    f"[{self.theme.TEXT_DIM}]Endpoint override: {endpoint}[/{self.theme.TEXT_DIM}]"
                )

        self.console.print()
        return True

    def _cmd_geminicli_login(self) -> bool:
        """Validate or refresh local Gemini OAuth credentials."""
        from ..geminicli import geminicli_oauth_login

        self.console.print()
        self.console.print(
            f"[{self.theme.PURPLE_SOFT}]{self.deco.SPARKLE} Validating Gemini OAuth credentials...[/{self.theme.PURPLE_SOFT}]"
        )
        self.console.print()

        with self.console.status(f"[{self.theme.PURPLE_SOFT}]Checking local CLI cache...[/{self.theme.PURPLE_SOFT}]"):
            login_result = geminicli_oauth_login(force_refresh=False)

        if not login_result.get("success"):
            error_msg = login_result.get("error", "Unknown error")
            self.console.print(
                f"[{self.theme.CORAL_VIBRANT}]{self.deco.CROSS} Login failed: {error_msg}[/{self.theme.CORAL_VIBRANT}]"
            )
            self.console.print(
                f"[{self.theme.AMBER_GLOW}]Please run `gemini`, complete OAuth login, then run /Geminicli login again.[/{self.theme.AMBER_GLOW}]"
            )
            self.console.print()
            return True

        if login_result.get("refreshed"):
            self.console.print(
                f"[{self.theme.MINT_VIBRANT}]{self.deco.CHECK_FANCY} Gemini OAuth token refreshed successfully.[/{self.theme.MINT_VIBRANT}]"
            )
        else:
            self.console.print(
                f"[{self.theme.MINT_VIBRANT}]{self.deco.CHECK_FANCY} Gemini OAuth credentials are valid.[/{self.theme.MINT_VIBRANT}]"
            )

        source_file = str(login_result.get("source_file", "")).strip()
        if source_file:
            self.console.print(
                f"[{self.theme.TEXT_DIM}]Credential source: {source_file}[/{self.theme.TEXT_DIM}]"
            )
        email = str(login_result.get("email", "")).strip()
        if email:
            self.console.print(
                f"[{self.theme.TEXT_DIM}]Active account: {email}[/{self.theme.TEXT_DIM}]"
            )
        expires_at = login_result.get("expires_at")
        if isinstance(expires_at, int) and expires_at > 0:
            expires_at_text = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(expires_at / 1000))
            self.console.print(
                f"[{self.theme.TEXT_DIM}]Token expiry: {expires_at_text}[/{self.theme.TEXT_DIM}]"
            )
        if login_result.get("errors"):
            self.console.print(
                f"[{self.theme.TEXT_DIM}]Notes: {' | '.join(str(x) for x in login_result.get('errors', []))}[/{self.theme.TEXT_DIM}]"
            )
        self.console.print(
            f"[{self.theme.TEXT_DIM}]Use /Geminicli model to select a model. Project override is optional.[/{self.theme.TEXT_DIM}]"
        )
        self.console.print()
        return True

    def _cmd_geminicli_endpoint(self, endpoint_value: str) -> bool:
        """Configure custom endpoint override for Gemini CLI requests."""
        from ..geminicli import normalize_geminicli_config

        return self._configure_provider_endpoint(
            config_attr="geminicli",
            normalize_config=normalize_geminicli_config,
            provider_label="Gemini CLI",
            endpoint_value=endpoint_value,
        )

    def _cmd_geminicli_project(self, project_value: str) -> bool:
        """Configure Gemini CLI project id."""
        from ..geminicli import infer_geminicli_project_id, normalize_geminicli_config

        config_manager = self.app.get('config_manager')
        if not config_manager:
            self.console.print(
                f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} Config manager not available[/{self.theme.CORAL_SOFT}]"
            )
            return True

        config = config_manager.load()
        geminicli_cfg = normalize_geminicli_config(getattr(config, "geminicli", {}))
        agent = self.app.get('agent')
        project_root = self.app.get('project_root') or getattr(agent, 'project_root', None) or Path.cwd()
        inferred_project = infer_geminicli_project_id(project_root)

        candidate = str(project_value or "").strip()
        if not candidate:
            current_project = str(geminicli_cfg.get("project_id", "")).strip()
            placeholder = current_project or inferred_project or "(none)"
            self.console.print(
                f"[{self.theme.TEXT_DIM}]Current Gemini project id: {placeholder}[/{self.theme.TEXT_DIM}]"
            )
            self.console.print(
                f"[{self.theme.TEXT_DIM}]Use 'clear' to remove stored project id.[/{self.theme.TEXT_DIM}]"
            )
            candidate = Prompt.ask(
                "Gemini project id",
                default=current_project or inferred_project
            ).strip()

        if candidate.lower() in ("clear", "none", "off", "default"):
            candidate = ""

        geminicli_cfg["project_id"] = candidate
        config.geminicli = geminicli_cfg
        config_manager.save(config)

        self.console.print()
        if candidate:
            self.console.print(
                f"[{self.theme.MINT_VIBRANT}]{self.deco.CHECK_FANCY} Gemini project id set to: {candidate}[/{self.theme.MINT_VIBRANT}]"
            )
        else:
            self.console.print(
                f"[{self.theme.MINT_VIBRANT}]{self.deco.CHECK_FANCY} Gemini project id cleared.[/{self.theme.MINT_VIBRANT}]"
            )

        if self.app.get('reinit_agent'):
            self.app['reinit_agent']()

        self.console.print()
        return True

    def _cmd_geminicli_model(self, model_query: str) -> bool:
        """Select Gemini CLI model from dedicated catalog."""
        from ..geminicli import (
            detect_geminicli_cli_credentials,
            get_geminicli_model_catalog,
            normalize_geminicli_config,
        )

        cred = detect_geminicli_cli_credentials(refresh_if_needed=True)
        if not cred.get("found"):
            self.console.print(
                f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} Gemini CLI credentials are unavailable.[/{self.theme.CORAL_SOFT}]"
            )
            self.console.print(
                f"[{self.theme.AMBER_GLOW}]Run /Geminicli first after logging into Gemini CLI.[/{self.theme.AMBER_GLOW}]"
            )
            if cred.get("errors"):
                self.console.print(
                    f"[{self.theme.TEXT_DIM}]Details: {' | '.join(str(x) for x in cred.get('errors', []))}[/{self.theme.TEXT_DIM}]"
                )
            return True

        return self._select_external_provider_model(
            config_attr="geminicli",
            normalize_config=normalize_geminicli_config,
            catalog=get_geminicli_model_catalog(),
            provider_label="Gemini CLI",
            active_source="geminicli",
            model_query=model_query,
        )

    def cmd_codex(self, args: str) -> bool:
        """Codex CLI integration command."""
        raw = args.strip()
        if not raw:
            return self._cmd_codex_activate()

        lowered = raw.lower()
        if lowered in ("low", "medium", "high", "xhigh", "extra high", "extra-high", "extra_high"):
            return self._cmd_codex_thinking(raw)
        if lowered == "login":
            return self._cmd_codex_login()
        if lowered == "model":
            return self._cmd_codex_model("", prompt_reasoning=True)
        if lowered.startswith("model "):
            return self._cmd_codex_model(raw[6:].strip(), prompt_reasoning=False)
        if lowered == "thinking":
            return self._cmd_codex_thinking("")
        if lowered.startswith("thinking "):
            return self._cmd_codex_thinking(raw[9:].strip())
        if lowered in ("status", "check"):
            self.console.print(
                f"[{self.theme.TEXT_DIM}]Use /codex to switch to the Codex source and inspect the current Codex setup.[/{self.theme.TEXT_DIM}]"
            )
            return True
        if lowered == "reasoning" or lowered.startswith("reasoning "):
            self.console.print(
                f"[{self.theme.TEXT_DIM}]Use /codex thinking instead. Reverie now keeps the Codex command surface tighter.[/{self.theme.TEXT_DIM}]"
            )
            return True
        if lowered == "endpoint":
            return self._cmd_codex_endpoint("")
        if lowered.startswith("endpoint "):
            return self._cmd_codex_endpoint(raw[9:].strip())

        self.console.print(
            f"[{self.theme.AMBER_GLOW}]{self.deco.DOT_MEDIUM} Usage: /codex [login|model|thinking|endpoint] or /codex [low|medium|high|extra high][/{self.theme.AMBER_GLOW}]"
        )
        return True

    def _cmd_codex_activate(self) -> bool:
        """Switch Reverie to Codex using the stored Codex selection."""
        from ..codex import (
            detect_codex_cli_credentials,
            normalize_codex_config,
            resolve_codex_selected_model,
        )

        config_manager = self.app.get('config_manager')
        if not config_manager:
            self.console.print(
                f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} Config manager not available[/{self.theme.CORAL_SOFT}]"
            )
            return True

        cred = detect_codex_cli_credentials()
        if not cred.get("found"):
            self.console.print(
                f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} Codex CLI credentials were not found under ~/.codex.[/{self.theme.CORAL_SOFT}]"
            )
            self.console.print(
                f"[{self.theme.AMBER_GLOW}]Use /codex login to authenticate, then run /codex again.[/{self.theme.AMBER_GLOW}]"
            )
            return True

        config = config_manager.load()
        codex_cfg = normalize_codex_config(getattr(config, "codex", {}))
        selected = resolve_codex_selected_model(codex_cfg)
        if not selected:
            self.console.print(
                f"[{self.theme.TEXT_DIM}]No Codex model is selected yet. Launching the Codex model flow.[/{self.theme.TEXT_DIM}]"
            )
            return self._cmd_codex_model("", prompt_reasoning=True)

        previous_source = str(getattr(config, "active_model_source", "standard")).lower()
        config.codex = codex_cfg
        config.active_model_source = "codex"
        config_manager.save(config)

        if previous_source != "codex" and self.app.get('reinit_agent'):
            self.app['reinit_agent']()

        self.console.print()
        self.console.print(
            f"[{self.theme.MINT_VIBRANT}]{self.deco.CHECK_FANCY} Switched Reverie to Codex: {selected['display_name']} ({selected['id']})[/{self.theme.MINT_VIBRANT}]"
        )
        return self._cmd_codex_status()

    def _cmd_codex_status(self) -> bool:
        """Detect local Codex CLI credentials and show current Codex selection."""
        from ..codex import (
            detect_codex_cli_credentials,
            get_codex_reasoning_label,
            get_codex_reasoning_efforts,
            normalize_codex_config,
            resolve_codex_selected_model,
        )

        config_manager = self.app.get('config_manager')
        config = config_manager.load() if config_manager else None

        cred = detect_codex_cli_credentials()
        self.console.print()

        if cred.get("found"):
            self.console.print(
                f"[{self.theme.MINT_VIBRANT}]{self.deco.CHECK_FANCY} Codex CLI credentials detected.[/{self.theme.MINT_VIBRANT}]"
            )
            self.console.print(
                f"[{self.theme.MINT_SOFT}]Codex CLI is installed and logged in. Use /codex to activate it, or /codex model to change models.[/{self.theme.MINT_SOFT}]"
            )
            source_file = cred.get("source_file", "")
            if source_file:
                self.console.print(
                    f"[{self.theme.TEXT_DIM}]Credential source: {source_file}[/{self.theme.TEXT_DIM}]"
                )
            auth_mode = str(cred.get("auth_mode", "")).strip()
            if auth_mode:
                self.console.print(
                    f"[{self.theme.TEXT_DIM}]Auth mode: {auth_mode}[/{self.theme.TEXT_DIM}]"
                )
            account_id = str(cred.get("account_id", "")).strip()
            if account_id:
                self.console.print(
                    f"[{self.theme.TEXT_DIM}]Account id: {account_id}[/{self.theme.TEXT_DIM}]"
                )
        else:
            self.console.print(
                f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} Codex CLI credentials were not found under ~/.codex.[/{self.theme.CORAL_SOFT}]"
            )
            self.console.print(
                f"[{self.theme.AMBER_GLOW}]Use /codex login to authenticate, or install Codex CLI first.[/{self.theme.AMBER_GLOW}]"
            )
            if cred.get("errors"):
                self.console.print(
                    f"[{self.theme.TEXT_DIM}]Details: {' | '.join(str(x) for x in cred.get('errors', []))}[/{self.theme.TEXT_DIM}]"
                )

        if config_manager and config:
            codex_cfg = normalize_codex_config(getattr(config, "codex", {}))
            selected = resolve_codex_selected_model(codex_cfg)
            if selected:
                self.console.print(
                    f"[{self.theme.BLUE_SOFT}]Current Codex model:[/{self.theme.BLUE_SOFT}] {selected['display_name']} ({selected['id']})"
                )
                context_length = selected.get('context_length', 0)
                if context_length:
                    self.console.print(
                        f"[{self.theme.TEXT_DIM}]Context length: {context_length:,} tokens[/{self.theme.TEXT_DIM}]"
                    )
                levels = get_codex_reasoning_efforts(selected["id"])
                current_effort = str(codex_cfg.get("reasoning_effort", "")).strip().lower()
                if current_effort:
                    self.console.print(
                        f"[{self.theme.TEXT_DIM}]Reasoning depth: {get_codex_reasoning_label(current_effort)} ({', '.join(get_codex_reasoning_label(level) for level in levels)})[/{self.theme.TEXT_DIM}]"
                    )
            else:
                self.console.print(
                    f"[{self.theme.TEXT_DIM}]Current Codex model: (none)[/{self.theme.TEXT_DIM}]"
                )

            model_source = str(getattr(config, "active_model_source", "standard")).lower()
            self.console.print(
                f"[{self.theme.BLUE_SOFT}]Active model source:[/{self.theme.BLUE_SOFT}] {self._format_model_source_label(model_source)}"
            )
            api_url = str(codex_cfg.get("api_url", "")).strip()
            if api_url:
                self.console.print(
                    f"[{self.theme.TEXT_DIM}]Codex API endpoint: {api_url}[/{self.theme.TEXT_DIM}]"
                )
            endpoint = str(codex_cfg.get("endpoint", "")).strip()
            if endpoint:
                self.console.print(
                    f"[{self.theme.TEXT_DIM}]Endpoint override: {endpoint}[/{self.theme.TEXT_DIM}]"
                )

        self.console.print()
        return True

    def _cmd_codex_login(self) -> bool:
        """Validate or refresh local Codex credentials."""
        from ..codex import codex_oauth_login

        self.console.print()
        self.console.print(
            f"[{self.theme.PURPLE_SOFT}]{self.deco.SPARKLE} Validating Codex credentials...[/{self.theme.PURPLE_SOFT}]"
        )
        self.console.print()

        with self.console.status(f"[{self.theme.PURPLE_SOFT}]Checking local CLI cache...[/{self.theme.PURPLE_SOFT}]"):
            login_result = codex_oauth_login(force_refresh=True)

        if not login_result.get("success"):
            error_msg = login_result.get("error", "Unknown error")
            self.console.print(
                f"[{self.theme.CORAL_VIBRANT}]{self.deco.CROSS} Login failed: {error_msg}[/{self.theme.CORAL_VIBRANT}]"
            )
            self.console.print(
                f"[{self.theme.AMBER_GLOW}]Please run `codex login`, complete authentication, then run /codex login again.[/{self.theme.AMBER_GLOW}]"
            )
            self.console.print()
            return True

        if login_result.get("refreshed"):
            self.console.print(
                f"[{self.theme.MINT_VIBRANT}]{self.deco.CHECK_FANCY} Codex access token refreshed successfully.[/{self.theme.MINT_VIBRANT}]"
            )
        else:
            self.console.print(
                f"[{self.theme.MINT_VIBRANT}]{self.deco.CHECK_FANCY} Codex credentials are valid.[/{self.theme.MINT_VIBRANT}]"
            )

        source_file = str(login_result.get("source_file", "")).strip()
        if source_file:
            self.console.print(
                f"[{self.theme.TEXT_DIM}]Credential source: {source_file}[/{self.theme.TEXT_DIM}]"
            )
        auth_mode = str(login_result.get("auth_mode", "")).strip()
        if auth_mode:
            self.console.print(
                f"[{self.theme.TEXT_DIM}]Auth mode: {auth_mode}[/{self.theme.TEXT_DIM}]"
            )
        account_id = str(login_result.get("account_id", "")).strip()
        if account_id:
            self.console.print(
                f"[{self.theme.TEXT_DIM}]Account id: {account_id}[/{self.theme.TEXT_DIM}]"
            )
        if login_result.get("errors"):
            self.console.print(
                f"[{self.theme.TEXT_DIM}]Notes: {' | '.join(str(x) for x in login_result.get('errors', []))}[/{self.theme.TEXT_DIM}]"
            )
        self.console.print(
            f"[{self.theme.TEXT_DIM}]Use /codex to activate Codex, or /codex model to change models.[/{self.theme.TEXT_DIM}]"
        )
        self.console.print()
        return True

    def _cmd_codex_endpoint(self, endpoint_value: str) -> bool:
        """Configure custom endpoint override for Codex requests."""
        from ..codex import normalize_codex_config

        return self._configure_provider_endpoint(
            config_attr="codex",
            normalize_config=normalize_codex_config,
            provider_label="Codex",
            endpoint_value=endpoint_value,
        )

    def _cmd_codex_thinking(self, value: str) -> bool:
        """Configure reasoning depth for the selected Codex model."""
        from ..codex import (
            get_codex_reasoning_catalog,
            get_codex_reasoning_label,
            normalize_codex_config,
            normalize_codex_reasoning_choice,
            resolve_codex_selected_model,
        )

        config_manager = self.app.get('config_manager')
        if not config_manager:
            self.console.print(
                f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} Config manager not available[/{self.theme.CORAL_SOFT}]"
            )
            return True

        config = config_manager.load()
        codex_cfg = normalize_codex_config(getattr(config, "codex", {}))
        selected = resolve_codex_selected_model(codex_cfg)
        if not selected:
            self.console.print(
                f"[{self.theme.AMBER_GLOW}]{self.deco.DOT_MEDIUM} Select a Codex model first with /codex model.[/{self.theme.AMBER_GLOW}]"
            )
            return True

        reasoning_items = get_codex_reasoning_catalog(selected["id"])
        if not reasoning_items:
            reasoning_items = [
                {
                    "id": "medium",
                    "label": "Medium",
                    "description": "Balances speed and reasoning depth for everyday tasks",
                }
            ]

        chosen_level = ""
        raw_value = str(value or "").strip().lower()
        if raw_value:
            normalized_value = normalize_codex_reasoning_choice(raw_value)
            available_levels = {item["id"] for item in reasoning_items}
            if normalized_value not in available_levels:
                self.console.print(
                    f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} Unsupported Codex reasoning depth: {value}[/{self.theme.CORAL_SOFT}]"
                )
                self.console.print(
                    f"[{self.theme.TEXT_DIM}]Available for {selected['display_name']}: {', '.join(item['label'] for item in reasoning_items)}[/{self.theme.TEXT_DIM}]"
                )
                return True
            chosen_level = normalized_value
        else:
            from .tui_selector import ModelSelector, SelectorAction

            levels_data = []
            current_level = str(codex_cfg.get("reasoning_effort", "")).strip().lower()
            current_selector_id = None
            for index, item in enumerate(reasoning_items):
                levels_data.append(
                    {
                        "id": str(index),
                        "name": item["label"],
                        "description": item["description"],
                        "model": {"id": item["id"]},
                    }
                )
                if item["id"] == current_level:
                    current_selector_id = str(index)

            selector = ModelSelector(
                console=self.console,
                models=levels_data,
                current_model=current_selector_id,
            )
            result = selector.run()
            if result.action != SelectorAction.SELECT or not result.selected_item:
                return True

            try:
                selected_index = int(result.selected_item.id)
            except (TypeError, ValueError):
                self.console.print(
                    f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} Invalid Codex reasoning selection.[/{self.theme.CORAL_SOFT}]"
                )
                return True

            if selected_index < 0 or selected_index >= len(reasoning_items):
                self.console.print(
                    f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} Invalid Codex reasoning index.[/{self.theme.CORAL_SOFT}]"
                )
                return True
            chosen_level = reasoning_items[selected_index]["id"]

        codex_cfg["reasoning_effort"] = chosen_level
        config.codex = codex_cfg
        config_manager.save(config)

        self.console.print()
        self.console.print(
            f"[{self.theme.MINT_VIBRANT}]{self.deco.CHECK_FANCY} Codex reasoning depth set to {get_codex_reasoning_label(chosen_level)} for {selected['display_name']}.[/{self.theme.MINT_VIBRANT}]"
        )
        self.console.print(
            f"[{self.theme.TEXT_DIM}]Reverie keeps the model id fixed and applies the selected depth automatically during Codex requests.[/{self.theme.TEXT_DIM}]"
        )

        if str(getattr(config, "active_model_source", "standard")).lower() == "codex" and self.app.get('reinit_agent'):
            self.app['reinit_agent']()

        return True

    def _cmd_codex_model(self, model_query: str, prompt_reasoning: Optional[bool] = None) -> bool:
        """Select Codex model from dedicated catalog."""
        from ..codex import (
            detect_codex_cli_credentials,
            get_codex_model_catalog,
            get_codex_reasoning_label,
            normalize_codex_config,
        )

        cred = detect_codex_cli_credentials()
        if not cred.get("found"):
            self.console.print(
                f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} Codex CLI credentials were not found under ~/.codex.[/{self.theme.CORAL_SOFT}]"
            )
            self.console.print(
                f"[{self.theme.AMBER_GLOW}]Run /codex first after logging into Codex CLI.[/{self.theme.AMBER_GLOW}]"
            )
            return True

        config_manager = self.app.get('config_manager')
        if not config_manager:
            self.console.print(
                f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} Config manager not available[/{self.theme.CORAL_SOFT}]"
            )
            return True

        catalog = get_codex_model_catalog()
        if not catalog:
            self.console.print(
                f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} Codex model catalog is empty.[/{self.theme.CORAL_SOFT}]"
            )
            return True

        config = config_manager.load()
        codex_cfg = normalize_codex_config(getattr(config, "codex", {}))
        selected_model = self._resolve_catalog_selection(
            catalog=catalog,
            current_selected_id=str(codex_cfg.get("selected_model_id", "")),
            model_query=model_query,
            provider_label="Codex",
        )
        if not selected_model:
            return True

        codex_cfg["selected_model_id"] = selected_model["id"]
        codex_cfg["selected_model_display_name"] = selected_model["display_name"]
        codex_cfg = normalize_codex_config(codex_cfg)
        config.codex = codex_cfg
        config.active_model_source = "codex"
        config_manager.save(config)

        self.console.print()
        self.console.print(
            f"[{self.theme.MINT_VIBRANT}]{self.deco.CHECK_FANCY} Switched to Codex model: {selected_model['display_name']} ({selected_model['id']})[/{self.theme.MINT_VIBRANT}]"
        )
        self.console.print(
            f"[{self.theme.TEXT_DIM}]Reasoning depth: {get_codex_reasoning_label(codex_cfg.get('reasoning_effort', 'medium'))}[/{self.theme.TEXT_DIM}]"
        )

        if self.app.get('reinit_agent'):
            self.app['reinit_agent']()

        should_prompt_reasoning = prompt_reasoning if prompt_reasoning is not None else not str(model_query or "").strip()
        available_levels = selected_model.get("reasoning_levels", []) or []
        if should_prompt_reasoning and len(available_levels) > 1:
            self.console.print(
                f"[{self.theme.TEXT_DIM}]Continuing into Codex reasoning-depth selection.[/{self.theme.TEXT_DIM}]"
            )
            return self._cmd_codex_thinking("")

        return True

    def cmd_modelscope(self, args: str) -> bool:
        """Manage ModelScope source settings."""
        raw = args.strip()
        if not raw:
            return self._cmd_modelscope_status()

        lowered = raw.lower()
        if lowered in ("status", "check"):
            return self._cmd_modelscope_status()
        if lowered in ("key", "apikey", "api-key", "login"):
            return self._cmd_modelscope_key()
        if lowered in ("activate", "use"):
            return self._cmd_modelscope_activate()
        if lowered == "model":
            return self._cmd_modelscope_model("")
        if lowered.startswith("model "):
            return self._cmd_modelscope_model(raw[6:].strip())
        if lowered in ("endpoint", "url", "base-url", "baseurl"):
            return self._cmd_modelscope_endpoint("")
        if lowered.startswith("endpoint "):
            return self._cmd_modelscope_endpoint(raw[9:].strip())
        if lowered.startswith("url "):
            return self._cmd_modelscope_endpoint(raw[4:].strip())
        if lowered.startswith("base-url "):
            return self._cmd_modelscope_endpoint(raw[9:].strip())
        if lowered.startswith("baseurl "):
            return self._cmd_modelscope_endpoint(raw[8:].strip())

        self.console.print(
            f"[{self.theme.AMBER_GLOW}]{self.deco.DOT_MEDIUM} Usage: /modelscope [status|key|activate|model|endpoint][/{self.theme.AMBER_GLOW}]"
        )
        return True

    def _ensure_modelscope_configuration(self, config) -> bool:
        """Prompt for ModelScope API key when needed and bind the source."""
        from ..modelscope import (
            MODELSCOPE_API_KEY_HINT_URL,
            normalize_modelscope_config,
            resolve_modelscope_api_key,
        )

        modelscope_cfg = normalize_modelscope_config(getattr(config, "modelscope", {}))
        api_key = resolve_modelscope_api_key(modelscope_cfg)
        if not api_key:
            self.console.print()
            self.console.print(
                f"[{self.theme.TEXT_DIM}]Get your ModelScope token here: {MODELSCOPE_API_KEY_HINT_URL}[/{self.theme.TEXT_DIM}]"
            )
            api_key = Prompt.ask(
                f"[{self.theme.BLUE_SOFT}]{self.deco.CHEVRON_RIGHT}[/{self.theme.BLUE_SOFT}] ModelScope API Key",
                password=True,
            ).strip()
            if not api_key:
                self.console.print(
                    f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} ModelScope API key is required to activate this source.[/{self.theme.CORAL_SOFT}]"
                )
                return False
        modelscope_cfg["api_key"] = api_key
        config.modelscope = normalize_modelscope_config(modelscope_cfg)
        config.active_model_source = "modelscope"
        return True

    def _cmd_modelscope_status(self) -> bool:
        from ..modelscope import (
            MODELSCOPE_API_KEY_HINT_URL,
            mask_secret,
            normalize_modelscope_config,
            resolve_modelscope_api_key,
            resolve_modelscope_selected_model,
        )

        config_manager = self.app.get('config_manager')
        if not config_manager:
            self.console.print(
                f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} Config manager not available[/{self.theme.CORAL_SOFT}]"
            )
            return True

        config = config_manager.load()
        modelscope_cfg = normalize_modelscope_config(getattr(config, "modelscope", {}))
        selected = resolve_modelscope_selected_model(modelscope_cfg)
        effective_api_key = resolve_modelscope_api_key(modelscope_cfg)
        key_origin = " (from environment)" if effective_api_key and not str(modelscope_cfg.get("api_key", "") or "").strip() else ""
        model_source = str(getattr(config, "active_model_source", "standard") or "standard").strip().lower()

        lines = [
            f"[{self.theme.BLUE_SOFT}]Active model source:[/{self.theme.BLUE_SOFT}] {self._format_model_source_label(model_source)}",
            f"[{self.theme.BLUE_SOFT}]Configured key:[/{self.theme.BLUE_SOFT}] {mask_secret(effective_api_key) if effective_api_key else '(not set)'}{key_origin}",
            f"[{self.theme.BLUE_SOFT}]Anthropic base URL:[/{self.theme.BLUE_SOFT}] {escape(str(modelscope_cfg.get('api_url', '')))}",
            f"[{self.theme.BLUE_SOFT}]Default max tokens:[/{self.theme.BLUE_SOFT}] {modelscope_cfg.get('max_tokens', 16384)}",
            f"[{self.theme.BLUE_SOFT}]API key help:[/{self.theme.BLUE_SOFT}] {escape(MODELSCOPE_API_KEY_HINT_URL)}",
        ]
        if selected:
            lines.insert(1, f"[{self.theme.BLUE_SOFT}]Selected model:[/{self.theme.BLUE_SOFT}] {escape(selected['display_name'])} ({escape(selected['id'])})")
            lines.insert(2, f"[{self.theme.BLUE_SOFT}]Transport:[/{self.theme.BLUE_SOFT}] Anthropic SDK")
            lines.insert(3, f"[{self.theme.BLUE_SOFT}]Context:[/{self.theme.BLUE_SOFT}] {int(selected.get('context_length') or 0):,} tokens")
            lines.insert(4, f"[{self.theme.BLUE_SOFT}]Vision input:[/{self.theme.BLUE_SOFT}] {'YES' if bool(selected.get('vision')) else 'NO'}")

        self.console.print()
        self.console.print(
            Panel(
                Text.from_markup("\n".join(lines)),
                title=f"[bold {self.theme.PINK_SOFT}]{self.deco.SPARKLE} ModelScope Source {self.deco.SPARKLE}[/bold {self.theme.PINK_SOFT}]",
                border_style=self.theme.BORDER_PRIMARY,
                box=box.ROUNDED,
                padding=(1, 2),
            )
        )
        self.console.print()
        return True

    def _cmd_modelscope_key(self) -> bool:
        from ..modelscope import MODELSCOPE_API_KEY_HINT_URL, normalize_modelscope_config

        config_manager = self.app.get('config_manager')
        if not config_manager:
            self.console.print(
                f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} Config manager not available[/{self.theme.CORAL_SOFT}]"
            )
            return True

        config = config_manager.load()
        modelscope_cfg = normalize_modelscope_config(getattr(config, "modelscope", {}))
        self.console.print(
            f"[{self.theme.TEXT_DIM}]Get your ModelScope token here: {MODELSCOPE_API_KEY_HINT_URL}[/{self.theme.TEXT_DIM}]"
        )
        api_key = Prompt.ask(
            f"[{self.theme.BLUE_SOFT}]{self.deco.CHEVRON_RIGHT}[/{self.theme.BLUE_SOFT}] ModelScope API Key",
            password=True,
        ).strip()
        if not api_key:
            self.console.print(
                f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} ModelScope API key cannot be empty.[/{self.theme.CORAL_SOFT}]"
            )
            return True

        modelscope_cfg["api_key"] = api_key
        config.modelscope = normalize_modelscope_config(modelscope_cfg)
        config_manager.save(config)

        if self.app.get('reinit_agent'):
            self.app['reinit_agent']()

        self.console.print(
            f"[{self.theme.MINT_VIBRANT}]{self.deco.CHECK_FANCY} ModelScope API key saved.[/{self.theme.MINT_VIBRANT}]"
        )
        return True

    def _cmd_modelscope_activate(self) -> bool:
        config_manager = self.app.get('config_manager')
        if not config_manager:
            self.console.print(
                f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} Config manager not available[/{self.theme.CORAL_SOFT}]"
            )
            return True

        config = config_manager.load()
        if not self._ensure_modelscope_configuration(config):
            return True
        config.active_model_source = "modelscope"
        config_manager.save(config)
        if self.app.get('reinit_agent'):
            self.app['reinit_agent']()
        self.console.print(
            f"[{self.theme.MINT_VIBRANT}]{self.deco.CHECK_FANCY} ModelScope source activated.[/{self.theme.MINT_VIBRANT}]"
        )
        return True

    def _cmd_modelscope_endpoint(self, endpoint_value: str) -> bool:
        from ..modelscope import MODELSCOPE_DEFAULT_API_URL, normalize_modelscope_config

        config_manager = self.app.get('config_manager')
        if not config_manager:
            self.console.print(
                f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} Config manager not available[/{self.theme.CORAL_SOFT}]"
            )
            return True

        config = config_manager.load()
        modelscope_cfg = normalize_modelscope_config(getattr(config, "modelscope", {}))
        candidate = str(endpoint_value or "").strip()
        if not candidate:
            current_url = str(modelscope_cfg.get("api_url", MODELSCOPE_DEFAULT_API_URL)).strip()
            self.console.print(
                f"[{self.theme.TEXT_DIM}]Current Anthropic base URL: {current_url}[/{self.theme.TEXT_DIM}]"
            )
            self.console.print(
                f"[{self.theme.TEXT_DIM}]Use 'clear' to restore the default. Do not include /v1 for the Anthropic SDK path.[/{self.theme.TEXT_DIM}]"
            )
            candidate = Prompt.ask(
                "ModelScope Anthropic base URL",
                default=current_url
            ).strip()

        if candidate.lower() in ("clear", "default", "none", "off"):
            candidate = MODELSCOPE_DEFAULT_API_URL

        if candidate and not candidate.startswith(("http://", "https://")):
            candidate = f"https://{candidate}"

        modelscope_cfg["api_url"] = candidate or MODELSCOPE_DEFAULT_API_URL
        config.modelscope = normalize_modelscope_config(modelscope_cfg)
        config_manager.save(config)

        if self.app.get('reinit_agent'):
            self.app['reinit_agent']()

        self.console.print()
        self.console.print(
            f"[{self.theme.MINT_VIBRANT}]{self.deco.CHECK_FANCY} ModelScope Anthropic base URL set to: {escape(config.modelscope.get('api_url', MODELSCOPE_DEFAULT_API_URL))}[/{self.theme.MINT_VIBRANT}]"
        )
        self.console.print()
        return True

    def _cmd_modelscope_model(self, model_query: str) -> bool:
        from ..modelscope import get_modelscope_model_catalog, normalize_modelscope_config

        return self._select_external_provider_model(
            config_attr="modelscope",
            normalize_config=normalize_modelscope_config,
            catalog=get_modelscope_model_catalog(),
            provider_label="ModelScope",
            active_source="modelscope",
            model_query=model_query,
        )

    def cmd_nvidia(self, args: str) -> bool:
        """Manage NVIDIA source settings."""
        raw = args.strip()
        if not raw:
            return self._cmd_nvidia_status()

        lowered = raw.lower()
        if lowered in ("status", "check"):
            return self._cmd_nvidia_status()
        if lowered in ("key", "apikey", "api-key", "login"):
            return self._cmd_nvidia_key()
        if lowered in ("activate", "use"):
            return self._cmd_nvidia_activate()
        if lowered == "model":
            return self._cmd_nvidia_model("")
        if lowered.startswith("model "):
            return self._cmd_nvidia_model(raw[6:].strip())
        if lowered in ("thinking", "reasoning", "effort"):
            return self._cmd_nvidia_thinking("")
        if lowered.startswith(("thinking ", "reasoning ", "effort ")):
            return self._cmd_nvidia_thinking(raw.split(None, 1)[1].strip())
        if lowered == "endpoint":
            return self._cmd_nvidia_endpoint("")
        if lowered.startswith("endpoint "):
            return self._cmd_nvidia_endpoint(raw[9:].strip())

        self.console.print(
            f"[{self.theme.AMBER_GLOW}]{self.deco.DOT_MEDIUM} Usage: /nvidia [status|key|activate|model|thinking|endpoint][/{self.theme.AMBER_GLOW}]"
        )
        return True

    def _cmd_nvidia_status(self) -> bool:
        from ..nvidia import (
            NVIDIA_API_KEY_HINT_URL,
            get_nvidia_thinking_choice_label,
            mask_secret,
            normalize_nvidia_config,
            resolve_nvidia_api_key,
            resolve_nvidia_selected_model,
            resolve_nvidia_thinking_choice,
        )

        config_manager = self.app.get('config_manager')
        if not config_manager:
            self.console.print(
                f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} Config manager not available[/{self.theme.CORAL_SOFT}]"
            )
            return True

        config = config_manager.load()
        nvidia_cfg = normalize_nvidia_config(getattr(config, "nvidia", {}))
        selected = resolve_nvidia_selected_model(nvidia_cfg)
        effective_api_key = resolve_nvidia_api_key(nvidia_cfg)
        key_origin = " (from NVIDIA_API_KEY)" if effective_api_key and not str(nvidia_cfg.get("api_key", "") or "").strip() else ""
        model_source = str(getattr(config, "active_model_source", "standard") or "standard").strip().lower()
        selected_id = str((selected or {}).get("id", "") if selected else "").strip()
        thinking_control = str((selected or {}).get("thinking_control", "none") if selected else "none").strip().lower()
        if thinking_control in {"toggle", "effort"}:
            choice = resolve_nvidia_thinking_choice(nvidia_cfg, selected_id)
            thinking_label = get_nvidia_thinking_choice_label(selected_id, choice)
        elif thinking_control == "fixed":
            thinking_label = "FIXED"
        else:
            thinking_label = "N/A"

        lines = [
            f"[{self.theme.BLUE_SOFT}]Active model source:[/{self.theme.BLUE_SOFT}] {self._format_model_source_label(model_source)}",
            f"[{self.theme.BLUE_SOFT}]Configured key:[/{self.theme.BLUE_SOFT}] {mask_secret(effective_api_key) if effective_api_key else '(not set)'}{key_origin}",
            f"[{self.theme.BLUE_SOFT}]API URL:[/{self.theme.BLUE_SOFT}] {escape(str(nvidia_cfg.get('api_url', '')))}",
            f"[{self.theme.BLUE_SOFT}]Endpoint:[/{self.theme.BLUE_SOFT}] {escape(str(nvidia_cfg.get('endpoint', '')))}",
            f"[{self.theme.BLUE_SOFT}]Thinking:[/{self.theme.BLUE_SOFT}] {thinking_label}",
            f"[{self.theme.BLUE_SOFT}]Default max tokens:[/{self.theme.BLUE_SOFT}] {nvidia_cfg.get('max_tokens', 16384)}",
            f"[{self.theme.BLUE_SOFT}]API key help:[/{self.theme.BLUE_SOFT}] {escape(NVIDIA_API_KEY_HINT_URL)}",
        ]
        if selected:
            lines.insert(1, f"[{self.theme.BLUE_SOFT}]Selected model:[/{self.theme.BLUE_SOFT}] {escape(selected['display_name'])} ({escape(selected['id'])})")
            lines.insert(2, f"[{self.theme.BLUE_SOFT}]Transport:[/{self.theme.BLUE_SOFT}] {escape(str(selected.get('transport', 'unknown')))}")
            lines.insert(3, f"[{self.theme.BLUE_SOFT}]Vision input:[/{self.theme.BLUE_SOFT}] {'YES' if bool(selected.get('vision')) else 'NO'}")

        self.console.print()
        self.console.print(
            Panel(
                Text.from_markup("\n".join(lines)),
                title=f"[bold {self.theme.PINK_SOFT}]{self.deco.SPARKLE} NVIDIA Source {self.deco.SPARKLE}[/bold {self.theme.PINK_SOFT}]",
                border_style=self.theme.BORDER_PRIMARY,
                box=box.ROUNDED,
                padding=(1, 2),
            )
        )
        self.console.print()
        return True

    def _cmd_nvidia_key(self) -> bool:
        from ..nvidia import NVIDIA_API_KEY_HINT_URL, normalize_nvidia_config

        config_manager = self.app.get('config_manager')
        if not config_manager:
            self.console.print(
                f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} Config manager not available[/{self.theme.CORAL_SOFT}]"
            )
            return True

        config = config_manager.load()
        nvidia_cfg = normalize_nvidia_config(getattr(config, "nvidia", {}))
        self.console.print(
            f"[{self.theme.TEXT_DIM}]Get your NVIDIA API key here: {NVIDIA_API_KEY_HINT_URL}[/{self.theme.TEXT_DIM}]"
        )
        api_key = Prompt.ask(
            f"[{self.theme.BLUE_SOFT}]{self.deco.CHEVRON_RIGHT}[/{self.theme.BLUE_SOFT}] NVIDIA API Key",
            password=True,
        ).strip()
        if not api_key:
            self.console.print(
                f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} NVIDIA API key cannot be empty.[/{self.theme.CORAL_SOFT}]"
            )
            return True

        nvidia_cfg["api_key"] = api_key
        config.nvidia = normalize_nvidia_config(nvidia_cfg)
        if normalize_mode(getattr(config, "mode", "reverie")) == "computer-controller":
            config.active_model_source = "nvidia"
        config_manager.save(config)

        if self.app.get('reinit_agent'):
            self.app['reinit_agent']()

        self.console.print(
            f"[{self.theme.MINT_VIBRANT}]{self.deco.CHECK_FANCY} NVIDIA API key saved.[/{self.theme.MINT_VIBRANT}]"
        )
        return True

    def _cmd_nvidia_login(self) -> bool:
        """Backward-compatible alias for the older `/nvidia login` command."""
        return self._cmd_nvidia_key()

    def _cmd_nvidia_activate(self) -> bool:
        config_manager = self.app.get('config_manager')
        if not config_manager:
            self.console.print(
                f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} Config manager not available[/{self.theme.CORAL_SOFT}]"
            )
            return True

        config = config_manager.load()
        if not self._ensure_nvidia_configuration(config):
            return True
        config.active_model_source = "nvidia"
        config_manager.save(config)
        if self.app.get('reinit_agent'):
            self.app['reinit_agent']()
        self.console.print(
            f"[{self.theme.MINT_VIBRANT}]{self.deco.CHECK_FANCY} NVIDIA source activated.[/{self.theme.MINT_VIBRANT}]"
        )
        return True

    def _cmd_nvidia_endpoint(self, endpoint_value: str) -> bool:
        from ..nvidia import normalize_nvidia_config

        return self._configure_provider_endpoint(
            config_attr="nvidia",
            normalize_config=normalize_nvidia_config,
            provider_label="NVIDIA",
            endpoint_value=endpoint_value,
        )

    def _cmd_nvidia_thinking(self, effort_value: str) -> bool:
        from ..nvidia import (
            apply_nvidia_thinking_choice,
            get_nvidia_thinking_choice_label,
            get_nvidia_thinking_options,
            normalize_nvidia_config,
            normalize_nvidia_thinking_choice,
            resolve_nvidia_selected_model,
            resolve_nvidia_thinking_choice,
        )

        config_manager = self.app.get('config_manager')
        if not config_manager:
            self.console.print(
                f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} Config manager not available[/{self.theme.CORAL_SOFT}]"
            )
            return True

        config = config_manager.load()
        nvidia_cfg = normalize_nvidia_config(getattr(config, "nvidia", {}))
        selected = resolve_nvidia_selected_model(nvidia_cfg)
        selected_name = str((selected or {}).get("display_name", "NVIDIA model"))
        selected_id = str((selected or {}).get("id", "") if selected else "").strip()
        thinking_control = str((selected or {}).get("thinking_control", "none") if selected else "none").strip().lower()

        if thinking_control not in {"toggle", "effort"} or not get_nvidia_thinking_options(selected_id):
            self.console.print(
                f"[{self.theme.AMBER_GLOW}]{self.deco.DOT_MEDIUM} {selected_name} does not expose configurable NVIDIA thinking depth.[/{self.theme.AMBER_GLOW}]"
            )
            return True

        if not str(effort_value or "").strip():
            updated_cfg = self._select_nvidia_thinking_choice(nvidia_cfg, selected or {})
            if updated_cfg is None:
                return True
            nvidia_cfg = updated_cfg
        else:
            choice = normalize_nvidia_thinking_choice(selected_id, effort_value)
            nvidia_cfg = apply_nvidia_thinking_choice(nvidia_cfg, selected_id, choice)

        status_text = get_nvidia_thinking_choice_label(
            selected_id,
            resolve_nvidia_thinking_choice(nvidia_cfg, selected_id),
        )
        config.nvidia = normalize_nvidia_config(nvidia_cfg)
        config.active_model_source = "nvidia"
        config_manager.save(config)
        if self.app.get('reinit_agent'):
            self.app['reinit_agent']()
        self.console.print(
            f"[{self.theme.MINT_VIBRANT}]{self.deco.CHECK_FANCY} NVIDIA thinking set to {status_text} for {selected_name}.[/{self.theme.MINT_VIBRANT}]"
        )
        return True

    def _select_nvidia_thinking_choice(self, nvidia_cfg: Dict[str, Any], selected_model: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Open a fixed NVIDIA thinking selector for the selected model."""
        from ..nvidia import (
            apply_nvidia_thinking_choice,
            get_nvidia_thinking_options,
            normalize_nvidia_config,
            resolve_nvidia_thinking_choice,
        )
        from .tui_selector import SelectorAction, SelectorItem, TUISelector

        cfg = normalize_nvidia_config(nvidia_cfg)
        selected_id = str(selected_model.get("id", "") or "").strip()
        options = get_nvidia_thinking_options(selected_id)
        if not selected_id or not options:
            return cfg

        current_choice = resolve_nvidia_thinking_choice(cfg, selected_id)
        items = [
            SelectorItem(
                id=str(option["id"]),
                title=str(option["label"]),
                description=str(option.get("description", "")),
                metadata={"model": {"id": str(option["id"])}},
            )
            for option in options
        ]

        selector = TUISelector(
            console=self.console,
            title=f"NVIDIA Thinking: {selected_model.get('display_name', selected_model.get('id', 'Model'))}",
            items=items,
            allow_search=False,
            allow_cancel=True,
            show_descriptions=True,
        )
        for index, item in enumerate(items):
            if item.id == current_choice:
                selector.selected_index = index
                selector.scroll_offset = max(0, index - selector.max_visible + 1)
                break

        result = selector.run()
        if result.action != SelectorAction.SELECT or not result.selected_item:
            return None

        return apply_nvidia_thinking_choice(cfg, selected_id, result.selected_item.id)

    def _configure_nvidia_thinking_for_model(self, nvidia_cfg: Dict[str, Any], selected_model: Dict[str, Any]) -> Dict[str, Any]:
        """Ask for NVIDIA thinking mode when the selected model exposes fixed options."""
        from ..nvidia import get_nvidia_thinking_options, normalize_nvidia_config

        cfg = normalize_nvidia_config(nvidia_cfg)
        if not get_nvidia_thinking_options(selected_model.get("id", "")):
            return cfg
        selected_cfg = self._select_nvidia_thinking_choice(cfg, selected_model)
        return normalize_nvidia_config(selected_cfg or cfg)

    def _cmd_nvidia_model(self, model_query: str) -> bool:
        from ..nvidia import get_nvidia_model_catalog, normalize_nvidia_config

        return self._select_external_provider_model(
            config_attr="nvidia",
            normalize_config=normalize_nvidia_config,
            catalog=get_nvidia_model_catalog(),
            provider_label="NVIDIA",
            active_source="nvidia",
            model_query=model_query,
            post_select_config=self._configure_nvidia_thinking_for_model,
        )

    def cmd_web(self, args: str) -> bool:
        """Legacy compatibility stub for the removed WebAI2API integration."""
        self.console.print(
            f"[{self.theme.AMBER_GLOW}]{self.deco.DOT_MEDIUM} The WebAI2API integration has been removed from this build.[/{self.theme.AMBER_GLOW}]"
        )
        return True

    def cmd_model(self, args: str) -> bool:
        """List and select models, or add/delete one"""
        args = args.strip().lower()
        if args == 'add':
            return self.cmd_add_model(args)
        
        config_manager = self.app.get('config_manager')
        if not config_manager:
            self.console.print(f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} Config manager not available[/{self.theme.CORAL_SOFT}]")
            return True
        
        # Handle delete
        if args.startswith('delete') or args.startswith('remove'):
            parts = args.split()
            if len(parts) > 1:
                try:
                    index_to_delete = int(parts[1]) - 1
                    if Confirm.ask(f"Delete model #{index_to_delete + 1}?"):
                         if config_manager.remove_model(index_to_delete):
                             self.console.print(f"[{self.theme.MINT_VIBRANT}]{self.deco.CHECK_FANCY} Model deleted.[/{self.theme.MINT_VIBRANT}]")
                             # Reinit agent if needed
                             if self.app.get('reinit_agent'):
                                 self.app['reinit_agent']()
                         else:
                             self.console.print(f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} Invalid model index.[/{self.theme.CORAL_SOFT}]")
                except ValueError:
                    self.console.print(f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} Invalid index format. Use: /model delete <number>[/{self.theme.CORAL_SOFT}]")
            else:
                 self.console.print(f"[{self.theme.AMBER_GLOW}]{self.deco.DOT_MEDIUM} Usage: /model delete <number>[/{self.theme.AMBER_GLOW}]")
            return True

        config = config_manager.load()
        
        if not config.models:
            self.console.print(f"[{self.theme.AMBER_GLOW}]{self.deco.DOT_MEDIUM} No models configured.[/{self.theme.AMBER_GLOW}]")
            if Confirm.ask("Would you like to add one now?"):
                return self.cmd_add_model("")
            return True
        
        # Use TUI selector for model selection
        from .tui_selector import ModelSelector, SelectorAction
        
        # Prepare model data
        models_data = []
        current_model_id = None
        for i, model in enumerate(config.models):
            models_data.append({
                'id': str(i),
                'name': model.model_display_name,
                'description': f"{model.base_url} • {model.model}",
                'model': model
            })
            if i == config.active_model_index:
                current_model_id = str(i)
        
        # Create and run selector
        selector = ModelSelector(
            console=self.console,
            models=models_data,
            current_model=current_model_id
        )
        
        result = selector.run()
        
        if result.action == SelectorAction.SELECT and result.selected_item:
            try:
                index = int(result.selected_item.id)
                if 0 <= index < len(config.models):
                    config_manager.set_active_model(index)
                    self.console.print()
                    self.console.print(
                        f"[{self.theme.MINT_VIBRANT}]{self.deco.CHECK_FANCY} Switched to: {config.models[index].model_display_name}[/{self.theme.MINT_VIBRANT}]"
                    )
                    
                    # Reinitialize agent
                    if self.app.get('reinit_agent'):
                        self.app['reinit_agent']()
            except (ValueError, IndexError):
                self.console.print(f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} Invalid selection[/{self.theme.CORAL_SOFT}]")
        
        return True

    def _require_subagent_mode(self) -> bool:
        if self._current_mode_name() == "reverie":
            return True
        self.console.print(
            f"[{self.theme.AMBER_GLOW}]{self.deco.DOT_MEDIUM} Subagents are only available in base Reverie mode. Switch with `/mode reverie`.[/{self.theme.AMBER_GLOW}]"
        )
        return False

    def _subagent_manager(self):
        manager = self.app.get("subagent_manager")
        if manager is None:
            self.console.print(f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} Subagent manager is not available.[/{self.theme.CORAL_SOFT}]")
        return manager

    def _print_subagent_usage(self) -> None:
        self.console.print(
            Panel(
                Text.from_markup(
                    f"[bold {self.theme.BLUE_SOFT}]/subagent[/bold {self.theme.BLUE_SOFT}] open the Subagent roster TUI\n"
                    f"[bold {self.theme.BLUE_SOFT}]/subagent create[/bold {self.theme.BLUE_SOFT}] choose a model and create a Subagent\n"
                    f"[bold {self.theme.BLUE_SOFT}]/subagent list[/bold {self.theme.BLUE_SOFT}] show configured Subagents\n"
                    f"[bold {self.theme.BLUE_SOFT}]/subagent model <id>[/bold {self.theme.BLUE_SOFT}] change a Subagent model\n"
                    f"[bold {self.theme.BLUE_SOFT}]/subagent run <id> <task>[/bold {self.theme.BLUE_SOFT}] run a direct delegated task"
                ),
                title=f"[bold {self.theme.PINK_SOFT}]{self.deco.SPARKLE} Subagents[/bold {self.theme.PINK_SOFT}]",
                border_style=self.theme.BORDER_PRIMARY,
                box=box.ROUNDED,
                padding=(1, 2),
            )
        )

    def _build_subagent_table(self, specs: List[Any]) -> Table:
        table = Table(
            title=f"[bold {self.theme.PINK_SOFT}]{self.deco.CRYSTAL} Reverie Subagents[/bold {self.theme.PINK_SOFT}]",
            box=box.ROUNDED,
            border_style=self.theme.BORDER_PRIMARY,
            show_lines=True,
            expand=True,
        )
        table.add_column("ID", style=f"bold {self.theme.BLUE_SOFT}", no_wrap=True)
        table.add_column("Model", style=self.theme.TEXT_PRIMARY)
        table.add_column("Source", style=self.theme.TEXT_SECONDARY, width=12)
        table.add_column("Color", style=self.theme.TEXT_SECONDARY, width=12)
        table.add_column("Status", style=self.theme.TEXT_SECONDARY, width=10)
        for spec in specs:
            ref = dict(getattr(spec, "model_ref", {}) or {})
            model = str(ref.get("display_name") or ref.get("model") or "(unresolved)")
            source = str(ref.get("source") or "standard")
            status = "enabled" if getattr(spec, "enabled", True) else "disabled"
            color = str(getattr(spec, "color", "") or "")
            table.add_row(
                str(getattr(spec, "id", "")),
                model,
                source,
                Text(color or "(auto)", style=color or self.theme.TEXT_DIM),
                status,
            )
        return table

    def _print_subagent_list(self, manager: Any) -> None:
        specs = manager.list_specs()
        self.console.print()
        if not specs:
            self.console.print(
                f"[{self.theme.TEXT_DIM}]{self.deco.DOT_MEDIUM} No Subagents configured yet. Use `/subagent create` to choose a model and create one.[/{self.theme.TEXT_DIM}]"
            )
            return
        self.console.print(self._build_subagent_table(specs))
        self.console.print()

    def _resolve_subagent_model_choice(self, manager: Any, query: str = "") -> Optional[Dict[str, Any]]:
        choices = manager.available_model_refs()
        if not choices:
            self.console.print(f"[{self.theme.AMBER_GLOW}]{self.deco.DOT_MEDIUM} No configured models are available for Subagents.[/{self.theme.AMBER_GLOW}]")
            return None

        wanted = str(query or "").strip().lower()
        if wanted:
            for choice in choices:
                ref = dict(choice.get("model_ref") or {})
                values = {
                    str(choice.get("id") or "").lower(),
                    str(choice.get("name") or "").lower(),
                    str(ref.get("model") or "").lower(),
                    str(ref.get("display_name") or "").lower(),
                }
                if wanted in values:
                    return dict(ref)

        from .tui_selector import ModelSelector, SelectorAction

        selector = ModelSelector(console=self.console, models=choices)
        result = selector.run()
        if result.action != SelectorAction.SELECT or not result.selected_item:
            return None
        ref = result.selected_item.metadata.get("model_ref") if isinstance(result.selected_item.metadata, dict) else None
        return dict(ref or {})

    def _show_selected_subagent(self, spec: Any) -> None:
        ref = dict(getattr(spec, "model_ref", {}) or {})
        rows = [
            ("ID", getattr(spec, "id", "")),
            ("Model", ref.get("display_name") or ref.get("model") or "(unresolved)"),
            ("Source", ref.get("source") or "standard"),
            ("Color", getattr(spec, "color", "")),
            ("Status", "enabled" if getattr(spec, "enabled", True) else "disabled"),
        ]
        self.console.print()
        self.console.print(
            Panel(
                self._build_key_value_table(rows),
                title=f"[bold {getattr(spec, 'color', '') or self.theme.BLUE_SOFT}]{escape(getattr(spec, 'id', 'Subagent'))}[/bold {getattr(spec, 'color', '') or self.theme.BLUE_SOFT}]",
                border_style=getattr(spec, "color", "") or self.theme.BORDER_PRIMARY,
                box=box.ROUNDED,
                padding=(1, 2),
            )
        )
        self.console.print()

    def cmd_subagent(self, args: str) -> bool:
        """Manage base Reverie Subagents and run delegated tasks."""
        if not self._require_subagent_mode():
            return True
        manager = self._subagent_manager()
        if manager is None:
            return True

        raw_args = str(args or "").strip()
        parts = self._split_command_args(raw_args)
        action = str(parts[0] if parts else "").strip().lower()

        if not action:
            specs = manager.list_specs()
            if not specs:
                self._print_subagent_usage()
                return True
            from .tui_selector import SelectorAction, SubagentSelector

            selector = SubagentSelector(self.console, [spec.to_dict() for spec in specs])
            result = selector.run()
            if result.action == SelectorAction.SELECT and result.selected_item:
                spec = manager.get_spec(result.selected_item.id)
                if spec:
                    self._show_selected_subagent(spec)
            return True

        if action in {"help", "-h", "--help"}:
            self._print_subagent_usage()
            return True

        if action in {"list", "ls"}:
            self._print_subagent_list(manager)
            return True

        if action == "create":
            model_query = parts[1] if len(parts) > 1 else ""
            model_ref = self._resolve_subagent_model_choice(manager, model_query)
            if not model_ref:
                return True
            try:
                spec = manager.create_subagent(model_ref)
            except Exception as exc:
                self.console.print(f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} Failed to create Subagent: {escape(str(exc))}[/{self.theme.CORAL_SOFT}]")
                return True
            self.console.print(
                f"[{self.theme.MINT_VIBRANT}]{self.deco.CHECK_FANCY} Created {spec.id} with model {escape(model_ref.get('display_name') or model_ref.get('model') or 'selected model')}.[/{self.theme.MINT_VIBRANT}]"
            )
            return True

        if action in {"delete", "remove"}:
            if len(parts) < 2:
                self.console.print(f"[{self.theme.AMBER_GLOW}]{self.deco.DOT_MEDIUM} Usage: /subagent delete <id>[/{self.theme.AMBER_GLOW}]")
                return True
            subagent_id = parts[1]
            if Confirm.ask(f"Delete Subagent {subagent_id}?"):
                if manager.delete_subagent(subagent_id):
                    self.console.print(f"[{self.theme.MINT_VIBRANT}]{self.deco.CHECK_FANCY} Deleted {subagent_id}.[/{self.theme.MINT_VIBRANT}]")
                else:
                    self.console.print(f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} Unknown Subagent: {escape(subagent_id)}[/{self.theme.CORAL_SOFT}]")
            return True

        if action == "model":
            if len(parts) < 2:
                self.console.print(f"[{self.theme.AMBER_GLOW}]{self.deco.DOT_MEDIUM} Usage: /subagent model <id>[/{self.theme.AMBER_GLOW}]")
                return True
            subagent_id = parts[1]
            model_ref = self._resolve_subagent_model_choice(manager, parts[2] if len(parts) > 2 else "")
            if not model_ref:
                return True
            spec = manager.set_model(subagent_id, model_ref)
            if not spec:
                self.console.print(f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} Unknown Subagent: {escape(subagent_id)}[/{self.theme.CORAL_SOFT}]")
                return True
            self.console.print(
                f"[{self.theme.MINT_VIBRANT}]{self.deco.CHECK_FANCY} Updated {spec.id} model to {escape(model_ref.get('display_name') or model_ref.get('model') or 'selected model')}.[/{self.theme.MINT_VIBRANT}]"
            )
            return True

        if action == "run":
            if len(parts) < 3:
                self.console.print(f"[{self.theme.AMBER_GLOW}]{self.deco.DOT_MEDIUM} Usage: /subagent run <id> <task>[/{self.theme.AMBER_GLOW}]")
                return True
            subagent_id = parts[1]
            task = raw_args.split(subagent_id, 1)[1].strip() if subagent_id in raw_args else " ".join(parts[2:])
            try:
                run = manager.run_task(subagent_id, task, stream=False)
            except Exception as exc:
                self.console.print(f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} Subagent run failed: {escape(str(exc))}[/{self.theme.CORAL_SOFT}]")
                return True
            if run.status == "completed":
                self._show_activity_event(
                    "Subagent",
                    f"{run.subagent_id} completed {run.run_id}",
                    status="success",
                    detail=run.summary[:240],
                    meta=run.log_path,
                )
            else:
                self._show_activity_event(
                    "Subagent",
                    f"{run.subagent_id} failed {run.run_id}",
                    status="error",
                    detail=run.error,
                    meta=run.log_path,
                )
            return True

        self._print_subagent_usage()
        return True

    def cmd_mode(self, args: str) -> bool:
        """Quickly switch modes or display current mode and available modes"""
        config_manager = self.app.get('config_manager')
        if not config_manager:
            self.console.print(f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} Config manager not available[/{self.theme.CORAL_SOFT}]")
            return True

        config = config_manager.load()
        raw_mode = args.strip()
        mode = normalize_mode(raw_mode) if raw_mode else ""
        
        # Available modes
        available_modes = list_modes(include_computer=True)
        
        # If no mode specified, show current mode and available modes
        if not mode:
            current_mode = normalize_mode(config.mode or "reverie")
            if current_mode not in available_modes:
                current_mode = "reverie"
            
            self.console.print()
            self.console.print(Panel(
                f"[bold {self.theme.PINK_SOFT}]{self.deco.SPARKLE} Mode Configuration {self.deco.SPARKLE}[/bold {self.theme.PINK_SOFT}]",
                border_style=self.theme.BORDER_PRIMARY,
                box=box.ROUNDED,
                padding=(0, 2)
            ))
            self.console.print()
            
            # Current mode
            self.console.print(f"[bold {self.theme.BLUE_SOFT}]{self.deco.CHEVRON_RIGHT} Current Mode:[/bold {self.theme.BLUE_SOFT}] [{self.theme.MINT_VIBRANT}]{current_mode}[/{self.theme.MINT_VIBRANT}]")
            self.console.print()
            
            # Available modes table
            table = Table(
                title=f"[bold {self.theme.PINK_SOFT}]{self.deco.DIAMOND} Available Modes[/bold {self.theme.PINK_SOFT}]",
                box=box.ROUNDED,
                border_style=self.theme.BORDER_PRIMARY,
                show_lines=True
            )
            table.add_column("Mode", style=f"bold {self.theme.BLUE_SOFT}", width=20)
            table.add_column("Description", style=self.theme.TEXT_SECONDARY)
            table.add_column("", style=self.theme.MINT_SOFT, width=5)
            
            for mode_name in available_modes:
                is_current = f"{self.deco.CHECK_FANCY}" if mode_name == current_mode else ""
                description = get_mode_description(mode_name)
                table.add_row(mode_name, description, is_current)
            
            self.console.print(table)
            self.console.print()
            self.console.print(f"[{self.theme.TEXT_DIM}]{self.deco.DOT_MEDIUM} Usage: /mode <mode-name> to switch modes[/{self.theme.TEXT_DIM}]")
            self.console.print()
            
            return True
        
        # Validate mode
        if mode not in available_modes:
            self.console.print(f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} Invalid mode: {mode}[/{self.theme.CORAL_SOFT}]")
            self.console.print(f"[{self.theme.TEXT_DIM}]Available modes: {', '.join(available_modes)}[/{self.theme.TEXT_DIM}]")
            return True

        # Switch mode
        if not self._apply_mode_selection(config, mode):
            return True
        config_manager.save(config)

        # Reinit agent to apply new mode
        if self.app.get('reinit_agent'):
            self.app['reinit_agent']()

        self.console.print(f"[{self.theme.MINT_VIBRANT}]{self.deco.CHECK_FANCY} Mode switched to {mode}[/{self.theme.MINT_VIBRANT}]")
        return True

    def _get_project_root(self) -> Path:
        """Resolve the active project root used by local game tools."""
        config_manager = self.app.get('config_manager')
        if config_manager and getattr(config_manager, "project_root", None):
            return Path(config_manager.project_root)
        return Path.cwd()

    def _split_command_args(self, args: str) -> List[str]:
        """Split slash-command arguments while respecting simple quoted values."""
        raw = str(args or "").strip()
        if not raw:
            return []
        try:
            return [
                part.strip().strip('"').strip("'")
                for part in shlex.split(raw, posix=False)
                if str(part).strip()
            ]
        except ValueError:
            return [part.strip() for part in raw.split() if str(part).strip()]

    def _format_bytes(self, size: Any) -> str:
        """Render file sizes consistently for game command output."""
        try:
            value = float(size)
        except (TypeError, ValueError):
            return str(size)
        if value < 1024:
            return f"{int(value)} B"
        if value < 1024 * 1024:
            return f"{value / 1024:.1f} KB"
        if value < 1024 * 1024 * 1024:
            return f"{value / (1024 * 1024):.2f} MB"
        return f"{value / (1024 * 1024 * 1024):.2f} GB"

    def _print_game_hint(self) -> None:
        """Show a gentle reminder when game commands are used outside Gamer mode."""
        current_mode = self._current_mode_name()
        if current_mode != "reverie-gamer":
            self.console.print(
                f"[{self.theme.TEXT_DIM}]{self.deco.DOT_MEDIUM} Tip: /mode reverie-gamer unlocks the strongest in-chat workflow for these game commands.[/{self.theme.TEXT_DIM}]"
            )

    def _current_mode_name(self) -> str:
        """Return the normalized active mode."""
        config_manager = self.app.get('config_manager')
        if not config_manager:
            return "reverie"
        config = config_manager.load()
        return normalize_mode(getattr(config, "mode", "reverie"))

    def _require_gamer_mode(self, feature_name: str) -> bool:
        """Render a friendly guardrail for Gamer-only command surfaces."""
        if self._current_mode_name() == "reverie-gamer":
            return True
        self._print_game_panel(
            "Reverie-Gamer Required",
            "\n".join(
                [
                    f"`{feature_name}` is a Reverie-Gamer-only workflow.",
                    "Switch with `/mode reverie-gamer` and run the command again.",
                ]
            ),
        )
        return False

    def _print_game_panel(self, title: str, body: str, accent: Optional[str] = None) -> None:
        """Render a styled game-command panel."""
        accent_color = accent or self.theme.BORDER_PRIMARY
        self.console.print()
        self.console.print(
            Panel(
                body,
                title=f"[bold {self.theme.PINK_SOFT}]{self.deco.CRYSTAL} {escape(title)}[/bold {self.theme.PINK_SOFT}]",
                border_style=accent_color,
                box=box.ROUNDED,
                padding=(1, 2),
            )
        )
        self.console.print()

    def _print_tool_result(self, title: str, result, *, markdown: bool = False) -> None:
        """Render tool results with consistent success and error styling."""
        if result.success:
            if markdown:
                from rich.markdown import Markdown

                body = Markdown(result.output)
            else:
                body = escape(result.output)
            self._print_game_panel(title, body if isinstance(body, str) else body, self.theme.BORDER_PRIMARY)
            return

        message = result.error or "Unknown error"
        self.console.print(
            f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} {escape(message)}[/{self.theme.CORAL_SOFT}]"
        )
        self.console.print()

    def _load_json_file(self, path: Path) -> Optional[Dict[str, Any]]:
        """Read a JSON file if it exists."""
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            return payload if isinstance(payload, dict) else {"value": payload}
        except Exception:
            return None

    def cmd_gdd(self, args: str) -> bool:
        """Create, inspect, validate, and export the game design document."""
        from ..tools.game_gdd_manager import GameGDDManagerTool

        self._print_game_hint()
        tokens = self._split_command_args(args)
        action = tokens[0].lower() if tokens else "view"
        project_root = self._get_project_root()
        tool = GameGDDManagerTool({"project_root": str(project_root)})
        gdd_path = "artifacts/GDD.md"

        if action in {"help", "?"}:
            self._print_game_panel(
                "GDD Commands",
                "\n".join(
                    [
                        "/gdd view",
                        "/gdd create",
                        "/gdd summary",
                        "/gdd validate",
                        "/gdd append",
                        "/gdd metadata",
                        "/gdd version [create|list]",
                        "/gdd export [html|markdown] [output_path]",
                    ]
                ),
            )
            return True

        if action == "create":
            self._print_game_panel("Create Game Design Document", "Fill in the core project details for the initial GDD.")
            project_name = Prompt.ask(
                f"[{self.theme.BLUE_SOFT}]{self.deco.CHEVRON_RIGHT}[/{self.theme.BLUE_SOFT}] Project Name",
                default=project_root.name
            )
            genre = Prompt.ask(
                f"[{self.theme.BLUE_SOFT}]{self.deco.CHEVRON_RIGHT}[/{self.theme.BLUE_SOFT}] Genre",
                default="RPG"
            )
            target_engine = Prompt.ask(
                f"[{self.theme.BLUE_SOFT}]{self.deco.CHEVRON_RIGHT}[/{self.theme.BLUE_SOFT}] Target Engine",
                default="reverie_engine",
                choices=["reverie_engine", "reverie_engine_lite", "custom", "phaser", "pixijs", "threejs", "pygame", "love2d", "godot", "o3de"]
            )
            target_platform = Prompt.ask(
                f"[{self.theme.BLUE_SOFT}]{self.deco.CHEVRON_RIGHT}[/{self.theme.BLUE_SOFT}] Target Platform",
                default="PC"
            )
            is_rpg = Confirm.ask(
                f"[{self.theme.BLUE_SOFT}]{self.deco.CHEVRON_RIGHT}[/{self.theme.BLUE_SOFT}] Is this an RPG game?",
                default=True
            )
            template_type = Prompt.ask(
                f"[{self.theme.BLUE_SOFT}]{self.deco.CHEVRON_RIGHT}[/{self.theme.BLUE_SOFT}] Template Type",
                default="rpg" if is_rpg else "standard",
                choices=["standard", "rpg", "minimal"],
            )
            result = tool.execute(
                action="create",
                gdd_path=gdd_path,
                project_name=project_name,
                genre=genre,
                target_engine=target_engine,
                target_platform=target_platform,
                is_rpg=is_rpg,
                template_type=template_type,
            )
            self._print_tool_result("GDD Created", result)
            return True

        if action == "view":
            result = tool.execute(action="view", gdd_path=gdd_path)
            if result.success:
                self._print_tool_result("Game Design Document", result, markdown=True)
            else:
                self.console.print(f"[{self.theme.AMBER_GLOW}]{self.deco.DOT_MEDIUM} {result.error}[/{self.theme.AMBER_GLOW}]")
                self.console.print(f"[{self.theme.TEXT_DIM}]Use /gdd create to generate a new GDD.[/{self.theme.TEXT_DIM}]")
            return True

        if action == "summary":
            result = tool.execute(action="summary", gdd_path=gdd_path)
            self._print_tool_result("GDD Summary", result)
            return True

        if action == "validate":
            result = tool.execute(action="validate", gdd_path=gdd_path)
            self._print_tool_result("GDD Validation", result)
            return True

        if action == "append":
            section_name = Prompt.ask(
                f"[{self.theme.BLUE_SOFT}]{self.deco.CHEVRON_RIGHT}[/{self.theme.BLUE_SOFT}] Section Name"
            ).strip()
            section_content = Prompt.ask(
                f"[{self.theme.BLUE_SOFT}]{self.deco.CHEVRON_RIGHT}[/{self.theme.BLUE_SOFT}] Section Content"
            ).strip()
            result = tool.execute(
                action="append_section",
                gdd_path=gdd_path,
                section_name=section_name,
                section_content=section_content,
            )
            self._print_tool_result("GDD Section Appended", result)
            return True

        if action == "metadata":
            metadata: Dict[str, Any] = {}
            kv_tokens = tokens[1:]
            if kv_tokens:
                for token in kv_tokens:
                    if "=" in token:
                        key, value = token.split("=", 1)
                        if key.strip():
                            metadata[key.strip()] = value.strip()
            if not metadata:
                metadata["status"] = Prompt.ask(
                    f"[{self.theme.BLUE_SOFT}]{self.deco.CHEVRON_RIGHT}[/{self.theme.BLUE_SOFT}] Status",
                    default="draft",
                ).strip()
                metadata["version"] = Prompt.ask(
                    f"[{self.theme.BLUE_SOFT}]{self.deco.CHEVRON_RIGHT}[/{self.theme.BLUE_SOFT}] Version",
                    default="0.1.0",
                ).strip()
                owner = Prompt.ask(
                    f"[{self.theme.BLUE_SOFT}]{self.deco.CHEVRON_RIGHT}[/{self.theme.BLUE_SOFT}] Owner",
                    default="Reverie",
                ).strip()
                if owner:
                    metadata["owner"] = owner
            result = tool.execute(action="set_metadata", gdd_path=gdd_path, metadata=metadata)
            self._print_tool_result("GDD Metadata Updated", result)
            return True

        if action == "version":
            version_action = tokens[1].lower() if len(tokens) > 1 else "list"
            if version_action not in {"create", "list"}:
                version_action = Prompt.ask(
                    f"[{self.theme.BLUE_SOFT}]{self.deco.CHEVRON_RIGHT}[/{self.theme.BLUE_SOFT}] Version Action",
                    default="list",
                    choices=["create", "list"],
                ).strip().lower()
            result = tool.execute(action="version", gdd_path=gdd_path, version_action=version_action)
            self._print_tool_result("GDD Versions", result)
            return True

        if action == "export":
            export_format = tokens[1].lower() if len(tokens) > 1 else Prompt.ask(
                f"[{self.theme.BLUE_SOFT}]{self.deco.CHEVRON_RIGHT}[/{self.theme.BLUE_SOFT}] Export Format",
                default="html",
                choices=["html", "markdown"],
            ).strip().lower()
            export_path = tokens[2] if len(tokens) > 2 else (
                "artifacts/GDD.html" if export_format == "html" else ""
            )
            kwargs = {"action": "export", "gdd_path": gdd_path, "export_format": export_format}
            if export_path:
                kwargs["export_path"] = export_path
            result = tool.execute(**kwargs)
            self._print_tool_result("GDD Export", result)
            return True

        self.console.print(
            f"[{self.theme.AMBER_GLOW}]{self.deco.DOT_MEDIUM} Usage: /gdd [view|create|summary|validate|append|metadata|version|export][/{self.theme.AMBER_GLOW}]"
        )
        return True

    def cmd_assets(self, args: str) -> bool:
        """Inspect and manage game assets from the CLI."""
        from ..tools.game_asset_manager import GameAssetManagerTool

        self._print_game_hint()
        project_root = self._get_project_root()
        tool = GameAssetManagerTool({"project_root": str(project_root)})
        tokens = self._split_command_args(args)
        valid_types = ["all", "sprite", "audio", "model", "animation"]

        if not tokens:
            subcommand = "list"
            asset_type = "all"
        elif tokens[0].lower() in valid_types:
            subcommand = "list"
            asset_type = tokens[0].lower()
        else:
            subcommand = tokens[0].lower()
            asset_type = tokens[1].lower() if len(tokens) > 1 and tokens[1].lower() in valid_types else "all"

        if subcommand in {"help", "?"}:
            self._print_game_panel(
                "Asset Commands",
                "\n".join(
                    [
                        "/assets [all|sprite|audio|model|animation]",
                        "/assets analyze [type]",
                        "/assets manifest [path]",
                        "/assets missing",
                        "/assets unused",
                        "/assets graph [type]",
                        "/assets compress [type]",
                        "/assets size [type]",
                        "/assets naming [regex]",
                        "/assets atlas [max_size]",
                    ]
                ),
            )
            return True

        if asset_type not in valid_types:
            self.console.print(f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} Invalid asset type: {asset_type}[/{self.theme.CORAL_SOFT}]")
            self.console.print(f"[{self.theme.TEXT_DIM}]Valid types: {', '.join(valid_types)}[/{self.theme.TEXT_DIM}]")
            return True

        if subcommand == "list":
            result = tool.execute(action="list", asset_type=asset_type)
            if not result.success:
                self.console.print(f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} {result.error}[/{self.theme.CORAL_SOFT}]")
                return True

            self.console.print()
            data = result.data or {}

            if asset_type == "all":
                assets_by_type = data.get("assets", {})
                total_count = data.get("total_count", 0)
                title_panel = Panel(
                    f"[bold {self.theme.PINK_SOFT}]{self.deco.CRYSTAL} Game Assets Overview {self.deco.CRYSTAL}[/bold {self.theme.PINK_SOFT}]\n"
                    f"[{self.theme.TEXT_SECONDARY}]Total: {total_count} asset(s)[/{self.theme.TEXT_SECONDARY}]",
                    border_style=self.theme.BORDER_PRIMARY,
                    box=box.ROUNDED,
                    padding=(0, 2)
                )
                self.console.print(title_panel)
                self.console.print()

                for atype in ["sprite", "audio", "model", "animation"]:
                    assets = assets_by_type.get(atype, [])
                    if not assets:
                        continue
                    table = Table(
                        title=f"[bold {self.theme.BLUE_SOFT}]{self.deco.DIAMOND} {atype.upper()}S ({len(assets)})[/bold {self.theme.BLUE_SOFT}]",
                        box=box.ROUNDED,
                        border_style=self.theme.BORDER_PRIMARY,
                        show_lines=False,
                        title_justify="left"
                    )
                    table.add_column("Name", style=f"bold {self.theme.MINT_SOFT}", width=30)
                    table.add_column("Size", style=self.theme.TEXT_SECONDARY, justify="right", width=12)
                    table.add_column("Path", style=f"dim {self.theme.TEXT_DIM}", no_wrap=False)
                    for asset in assets[:10]:
                        table.add_row(
                            f"{self.deco.DOT_MEDIUM} {asset.get('name', '')}",
                            self._format_bytes(asset.get("size", 0)),
                            str(asset.get("path", "")),
                        )
                    if len(assets) > 10:
                        table.add_row(
                            f"[dim {self.theme.TEXT_DIM}]... and {len(assets) - 10} more[/dim {self.theme.TEXT_DIM}]",
                            "",
                            ""
                        )
                    self.console.print(table)
                    self.console.print()
                return True

            assets = data.get("assets", [])
            count = data.get("count", 0)
            title_panel = Panel(
                f"[bold {self.theme.PINK_SOFT}]{self.deco.CRYSTAL} {asset_type.upper()} Assets {self.deco.CRYSTAL}[/bold {self.theme.PINK_SOFT}]\n"
                f"[{self.theme.TEXT_SECONDARY}]Found: {count} asset(s)[/{self.theme.TEXT_SECONDARY}]",
                border_style=self.theme.BORDER_PRIMARY,
                box=box.ROUNDED,
                padding=(0, 2)
            )
            self.console.print(title_panel)
            self.console.print()
            if not assets:
                self.console.print(f"[{self.theme.TEXT_DIM}]{self.deco.DOT_MEDIUM} No {asset_type} assets found.[/{self.theme.TEXT_DIM}]")
                self.console.print()
                return True

            table = Table(box=box.ROUNDED, border_style=self.theme.BORDER_PRIMARY, show_lines=True)
            table.add_column("#", style=f"dim {self.theme.TEXT_DIM}", width=5, justify="right")
            table.add_column("Name", style=f"bold {self.theme.MINT_SOFT}", width=35)
            table.add_column("Size", style=self.theme.TEXT_SECONDARY, justify="right", width=12)
            table.add_column("Path", style=self.theme.TEXT_DIM, no_wrap=False)
            for idx, asset in enumerate(assets, 1):
                table.add_row(
                    str(idx),
                    f"{self.deco.DOT_MEDIUM} {asset.get('name', '')}",
                    self._format_bytes(asset.get("size", 0)),
                    str(asset.get("path", "")),
                )
            self.console.print(table)
            self.console.print()
            return True

        if subcommand == "manifest":
            manifest_path = tokens[1] if len(tokens) > 1 else "assets/manifest.json"
            result = tool.execute(action="generate_manifest", asset_type=asset_type, manifest_path=manifest_path)
            self._print_tool_result("Asset Manifest", result)
            return True

        if subcommand == "analyze":
            result = tool.execute(action="analyze", asset_type=asset_type)
            self._print_tool_result("Asset Analysis", result)
            return True

        if subcommand == "missing":
            result = tool.execute(action="check_missing", asset_type=asset_type, code_dirs=["src", "scripts", "data"])
            self._print_tool_result("Missing Asset References", result)
            return True

        if subcommand == "unused":
            result = tool.execute(action="find_unused", asset_type=asset_type, code_dirs=["src", "scripts", "data"])
            self._print_tool_result("Unused Assets", result)
            return True

        if subcommand == "graph":
            result = tool.execute(action="dependency_graph", asset_type=asset_type, code_dirs=["src", "scripts", "data"])
            self._print_tool_result("Asset Dependency Graph", result)
            return True

        if subcommand == "compress":
            result = tool.execute(action="compress_recommend", asset_type=asset_type)
            self._print_tool_result("Asset Compression Recommendations", result)
            return True

        if subcommand == "size":
            result = tool.execute(action="total_size", asset_type=asset_type)
            self._print_tool_result("Asset Size Report", result)
            return True

        if subcommand == "naming":
            pattern = tokens[1] if len(tokens) > 1 else r"^[a-z0-9_]+$"
            result = tool.execute(action="validate_naming", asset_type=asset_type, naming_pattern=pattern)
            self._print_tool_result("Asset Naming Validation", result)
            return True

        if subcommand == "atlas":
            atlas_size = 2048
            if len(tokens) > 1 and tokens[1].isdigit():
                atlas_size = int(tokens[1])
            result = tool.execute(action="build_atlas_plan", atlas_max_size=atlas_size)
            self._print_tool_result("Sprite Atlas Plan", result)
            return True

        if subcommand == "import":
            source_path = tokens[1] if len(tokens) > 1 else Prompt.ask(
                f"[{self.theme.BLUE_SOFT}]{self.deco.CHEVRON_RIGHT}[/{self.theme.BLUE_SOFT}] Source Asset Path"
            ).strip()
            import_type = tokens[2].lower() if len(tokens) > 2 and tokens[2].lower() in valid_types else Prompt.ask(
                f"[{self.theme.BLUE_SOFT}]{self.deco.CHEVRON_RIGHT}[/{self.theme.BLUE_SOFT}] Asset Type",
                default="sprite",
                choices=["sprite", "audio", "model", "animation"],
            ).strip().lower()
            target_name = tokens[3] if len(tokens) > 3 else ""
            kwargs = {"action": "import_asset", "source_path": source_path, "asset_type": import_type}
            if target_name:
                kwargs["target_name"] = target_name
            result = tool.execute(**kwargs)
            self._print_tool_result("Asset Imported", result)
            return True

        self.console.print(
            f"[{self.theme.AMBER_GLOW}]{self.deco.DOT_MEDIUM} Usage: /assets [list|manifest|analyze|missing|unused|graph|compress|size|naming|atlas|import][/{self.theme.AMBER_GLOW}]"
        )
        return True

    def cmd_blueprint(self, args: str) -> bool:
        """Create, inspect, and export game blueprints."""
        from ..tools.game_design_orchestrator import GameDesignOrchestratorTool

        self._print_game_hint()
        tokens = self._split_command_args(args)
        action = tokens[0].lower() if tokens else "view"
        tool = GameDesignOrchestratorTool({"project_root": str(self._get_project_root())})
        blueprint_path = "artifacts/game_blueprint.json"

        if action in {"help", "?"}:
            self._print_game_panel(
                "Blueprint Commands",
                "\n".join(
                    [
                        "/blueprint view",
                        "/blueprint create",
                        "/blueprint analyze",
                        "/blueprint slice [output_path]",
                        "/blueprint export [output_path]",
                        "/blueprint expand <system_name>",
                    ]
                ),
            )
            return True

        if action == "view":
            payload = self._load_json_file(self._get_project_root() / blueprint_path)
            if not payload:
                self.console.print(f"[{self.theme.AMBER_GLOW}]{self.deco.DOT_MEDIUM} Blueprint not found. Use /blueprint create first.[/{self.theme.AMBER_GLOW}]")
                return True

            meta = payload.get("meta", {})
            creative = payload.get("creative_direction", {})
            systems = payload.get("gameplay_blueprint", {}).get("systems", {})
            body = "\n".join(
                [
                    f"Project: {meta.get('project_name', 'Unknown')}",
                    f"Genre: {meta.get('genre', 'Unknown')}",
                    f"Dimension: {meta.get('dimension', 'Unknown')}",
                    f"Engine: {meta.get('target_engine', 'Unknown')}",
                    f"Camera: {meta.get('camera_model', 'Unknown')}",
                    f"Scope: {meta.get('scope', 'Unknown')}",
                    f"Pillars: {', '.join(creative.get('pillars', [])) or 'none'}",
                    f"Systems: {len(systems)}",
                ]
            )
            self._print_game_panel("Game Blueprint Overview", body)
            if systems:
                table = Table(box=box.ROUNDED, border_style=self.theme.BORDER_PRIMARY, show_lines=True)
                table.add_column("System", style=f"bold {self.theme.MINT_SOFT}")
                table.add_column("Tuning", style=self.theme.TEXT_SECONDARY, justify="right")
                table.add_column("Telemetry", style=self.theme.TEXT_SECONDARY, justify="right")
                for key, spec in systems.items():
                    table.add_row(
                        spec.get("name", key),
                        str(len(spec.get("tuning_knobs", []))),
                        str(len(spec.get("telemetry", []))),
                    )
                self.console.print(table)
                self.console.print()
            return True

        if action == "create":
            project_root = self._get_project_root()
            project_name = Prompt.ask(
                f"[{self.theme.BLUE_SOFT}]{self.deco.CHEVRON_RIGHT}[/{self.theme.BLUE_SOFT}] Project Name",
                default=project_root.name,
            ).strip()
            genre = Prompt.ask(
                f"[{self.theme.BLUE_SOFT}]{self.deco.CHEVRON_RIGHT}[/{self.theme.BLUE_SOFT}] Genre",
                default="Action Adventure",
            ).strip()
            dimension = Prompt.ask(
                f"[{self.theme.BLUE_SOFT}]{self.deco.CHEVRON_RIGHT}[/{self.theme.BLUE_SOFT}] Dimension",
                default="2D",
                choices=["2D", "2.5D", "3D"],
            ).strip()
            target_engine = Prompt.ask(
                f"[{self.theme.BLUE_SOFT}]{self.deco.CHEVRON_RIGHT}[/{self.theme.BLUE_SOFT}] Target Engine",
                default="reverie_engine",
                choices=["reverie_engine", "reverie_engine_lite", "custom", "phaser", "pixijs", "threejs", "pygame", "love2d", "godot", "o3de"],
            ).strip()
            camera_model = Prompt.ask(
                f"[{self.theme.BLUE_SOFT}]{self.deco.CHEVRON_RIGHT}[/{self.theme.BLUE_SOFT}] Camera Model",
                default="side_view" if dimension == "2D" else ("isometric" if dimension == "2.5D" else "third_person"),
            ).strip()
            scope = Prompt.ask(
                f"[{self.theme.BLUE_SOFT}]{self.deco.CHEVRON_RIGHT}[/{self.theme.BLUE_SOFT}] Scope",
                default="full_game",
                choices=["prototype", "vertical_slice", "full_game"],
            ).strip()
            pillars_raw = Prompt.ask(
                f"[{self.theme.BLUE_SOFT}]{self.deco.CHEVRON_RIGHT}[/{self.theme.BLUE_SOFT}] Pillars (comma-separated)",
                default="Immediate player fantasy,Depth from interacting systems,Readable feedback and pacing",
            ).strip()
            pillars = [item.strip() for item in pillars_raw.split(",") if item.strip()]
            result = tool.execute(
                action="create_blueprint",
                blueprint_path=blueprint_path,
                project_name=project_name,
                genre=genre,
                dimension=dimension,
                target_engine=target_engine,
                camera_model=camera_model,
                scope=scope,
                pillars=pillars,
            )
            self._print_tool_result("Blueprint Created", result)
            return True

        if action == "analyze":
            result = tool.execute(action="analyze_scope", blueprint_path=blueprint_path)
            self._print_tool_result("Blueprint Scope Analysis", result)
            return True

        if action == "slice":
            output_path = tokens[1] if len(tokens) > 1 else "artifacts/vertical_slice_plan.md"
            result = tool.execute(
                action="generate_vertical_slice",
                blueprint_path=blueprint_path,
                output_path=output_path,
            )
            self._print_tool_result("Vertical Slice Plan", result)
            return True

        if action == "export":
            output_path = tokens[1] if len(tokens) > 1 else "artifacts/game_blueprint.md"
            result = tool.execute(
                action="export_markdown",
                blueprint_path=blueprint_path,
                output_path=output_path,
            )
            self._print_tool_result("Blueprint Export", result)
            return True

        if action == "expand":
            system_name = " ".join(tokens[1:]).strip() if len(tokens) > 1 else ""
            if not system_name:
                system_name = Prompt.ask(
                    f"[{self.theme.BLUE_SOFT}]{self.deco.CHEVRON_RIGHT}[/{self.theme.BLUE_SOFT}] System Name",
                    default="Combat",
                ).strip()
            result = tool.execute(
                action="expand_system",
                blueprint_path=blueprint_path,
                system_name=system_name,
            )
            self._print_tool_result("Blueprint System Expansion", result)
            return True

        self.console.print(
            f"[{self.theme.AMBER_GLOW}]{self.deco.DOT_MEDIUM} Usage: /blueprint [view|create|analyze|slice|export|expand][/{self.theme.AMBER_GLOW}]"
        )
        return True

    def cmd_scaffold(self, args: str) -> bool:
        """Plan or create the engine-aware project foundation."""
        from ..tools.game_project_scaffolder import GameProjectScaffolderTool

        self._print_game_hint()
        tokens = self._split_command_args(args)
        action = tokens[0].lower() if tokens else "plan"
        tool = GameProjectScaffolderTool({"project_root": str(self._get_project_root())})
        output_dir = "."
        blueprint_path = "artifacts/game_blueprint.json"

        if action in {"help", "?"}:
            self._print_game_panel(
                "Scaffold Commands",
                "\n".join(
                    [
                        "/scaffold plan",
                        "/scaffold create",
                        "/scaffold modules [output_path]",
                        "/scaffold pipeline [output_path]",
                    ]
                ),
            )
            return True

        if action == "plan":
            result = tool.execute(action="plan_structure", output_dir=output_dir, blueprint_path=blueprint_path)
            self._print_tool_result("Project Structure Plan", result)
            return True

        if action == "create":
            include_tests = Confirm.ask(
                f"[{self.theme.BLUE_SOFT}]{self.deco.CHEVRON_RIGHT}[/{self.theme.BLUE_SOFT}] Include tests?",
                default=True,
            )
            include_tools = Confirm.ask(
                f"[{self.theme.BLUE_SOFT}]{self.deco.CHEVRON_RIGHT}[/{self.theme.BLUE_SOFT}] Include tooling and playtest folders?",
                default=True,
            )
            overwrite = Confirm.ask(
                f"[{self.theme.BLUE_SOFT}]{self.deco.CHEVRON_RIGHT}[/{self.theme.BLUE_SOFT}] Overwrite starter files if they exist?",
                default=False,
            )
            result = tool.execute(
                action="create_foundation",
                output_dir=output_dir,
                blueprint_path=blueprint_path,
                include_tests=include_tests,
                include_tools=include_tools,
                overwrite=overwrite,
            )
            self._print_tool_result("Project Foundation", result)
            return True

        if action == "modules":
            output_path = tokens[1] if len(tokens) > 1 else "artifacts/module_map.json"
            result = tool.execute(
                action="generate_module_map",
                output_dir=output_dir,
                blueprint_path=blueprint_path,
                output_path=output_path,
            )
            self._print_tool_result("Module Map", result)
            return True

        if action == "pipeline":
            output_path = tokens[1] if len(tokens) > 1 else "artifacts/content_pipeline.md"
            result = tool.execute(
                action="generate_content_pipeline",
                output_dir=output_dir,
                blueprint_path=blueprint_path,
                output_path=output_path,
            )
            self._print_tool_result("Content Pipeline", result)
            return True

        self.console.print(
            f"[{self.theme.AMBER_GLOW}]{self.deco.DOT_MEDIUM} Usage: /scaffold [plan|create|modules|pipeline][/{self.theme.AMBER_GLOW}]"
        )
        return True

    def cmd_playtest(self, args: str) -> bool:
        """Create playtest plans and analyze playtest artifacts."""
        from ..tools.game_playtest_lab import GamePlaytestLabTool

        self._print_game_hint()
        tokens = self._split_command_args(args)
        action = tokens[0].lower() if tokens else "plan"
        tool = GamePlaytestLabTool({"project_root": str(self._get_project_root())})
        blueprint_path = "artifacts/game_blueprint.json"

        if action in {"help", "?"}:
            self._print_game_panel(
                "Playtest Commands",
                "\n".join(
                    [
                        "/playtest plan [focus]",
                        "/playtest telemetry [focus]",
                        "/playtest gates [focus]",
                        "/playtest analyze <session_log_path>",
                        "/playtest feedback [feedback_path]",
                    ]
                ),
            )
            return True

        if action == "plan":
            focus = tokens[1] if len(tokens) > 1 else Prompt.ask(
                f"[{self.theme.BLUE_SOFT}]{self.deco.CHEVRON_RIGHT}[/{self.theme.BLUE_SOFT}] Test Focus",
                default="full_loop",
            ).strip()
            audience = Prompt.ask(
                f"[{self.theme.BLUE_SOFT}]{self.deco.CHEVRON_RIGHT}[/{self.theme.BLUE_SOFT}] Audience",
                default="new_players",
            ).strip()
            session_minutes = int(Prompt.ask(
                f"[{self.theme.BLUE_SOFT}]{self.deco.CHEVRON_RIGHT}[/{self.theme.BLUE_SOFT}] Session Minutes",
                default="30",
            ).strip() or "30")
            result = tool.execute(
                action="create_test_plan",
                blueprint_path=blueprint_path,
                test_focus=focus,
                audience=audience,
                session_minutes=session_minutes,
            )
            self._print_tool_result("Playtest Plan", result)
            return True

        if action == "telemetry":
            focus = tokens[1] if len(tokens) > 1 else "full_loop"
            result = tool.execute(
                action="generate_telemetry_schema",
                blueprint_path=blueprint_path,
                test_focus=focus,
            )
            self._print_tool_result("Telemetry Schema", result)
            return True

        if action == "gates":
            focus = tokens[1] if len(tokens) > 1 else "full_loop"
            result = tool.execute(
                action="create_quality_gates",
                blueprint_path=blueprint_path,
                test_focus=focus,
            )
            self._print_tool_result("Quality Gates", result)
            return True

        if action == "analyze":
            log_path = tokens[1] if len(tokens) > 1 else Prompt.ask(
                f"[{self.theme.BLUE_SOFT}]{self.deco.CHEVRON_RIGHT}[/{self.theme.BLUE_SOFT}] Session Log Path",
                default="playtest/logs/session.json",
            ).strip()
            result = tool.execute(action="analyze_session_log", session_log_path=log_path)
            self._print_tool_result("Playtest Session Analysis", result)
            return True

        if action == "feedback":
            feedback_path = tokens[1] if len(tokens) > 1 else Prompt.ask(
                f"[{self.theme.BLUE_SOFT}]{self.deco.CHEVRON_RIGHT}[/{self.theme.BLUE_SOFT}] Feedback File Path",
                default="playtest/feedback.txt",
            ).strip()
            result = tool.execute(action="synthesize_feedback", feedback_path=feedback_path)
            self._print_tool_result("Feedback Synthesis", result)
            return True

        self.console.print(
            f"[{self.theme.AMBER_GLOW}]{self.deco.DOT_MEDIUM} Usage: /playtest [plan|telemetry|gates|analyze|feedback][/{self.theme.AMBER_GLOW}]"
        )
        return True

    def cmd_engine(self, args: str) -> bool:
        """Manage the built-in Reverie Engine runtime."""
        from ..engine import run_project, runtime_capabilities
        from ..tools.reverie_engine import ReverieEngineTool

        self._print_game_hint()
        tokens = self._split_command_args(args)
        action = tokens[0].lower() if tokens else "profile"
        tool = ReverieEngineTool({"project_root": str(self._get_project_root())})
        output_dir = "."

        if action in {"help", "?"}:
            self._print_game_panel(
                "Engine Commands",
                "\n".join(
                    [
                        "/engine profile",
                        "/engine create",
                        "/engine sample [2d_platformer|topdown_action|iso_adventure|3d_arena|galgame_live2d|tower_defense]",
                        "/engine run [scene_path]",
                        "/engine validate",
                        "/engine smoke [scene_path]",
                        "/engine video [mp4|gif|frames] [scene_path]",
                        "/engine renpy <script_path> [conversation_id] [entry_label]",
                        "/engine health",
                        "/engine benchmark",
                        "/engine package",
                        "/engine test",
                    ]
                ),
            )
            return True

        if action == "profile":
            result = tool.execute(action="inspect_project", output_dir=output_dir)
            capability_text = "\n".join(
                f"- {name}: {'available' if available else 'missing'}"
                for name, available in runtime_capabilities(self._get_project_root()).items()
            )
            if result.success:
                self._print_game_panel("Reverie Engine Profile", f"{result.output}\n\nCapabilities:\n{capability_text}")
            else:
                self._print_tool_result("Reverie Engine Profile", result)
            return True

        if action == "create":
            project_root = self._get_project_root()
            project_name = Prompt.ask(
                f"[{self.theme.BLUE_SOFT}]{self.deco.CHEVRON_RIGHT}[/{self.theme.BLUE_SOFT}] Project Name",
                default=project_root.name,
            ).strip()
            dimension = Prompt.ask(
                f"[{self.theme.BLUE_SOFT}]{self.deco.CHEVRON_RIGHT}[/{self.theme.BLUE_SOFT}] Dimension",
                default="2D",
                choices=["2D", "2.5D", "3D"],
            ).strip()
            include_sample = Confirm.ask(
                f"[{self.theme.BLUE_SOFT}]{self.deco.CHEVRON_RIGHT}[/{self.theme.BLUE_SOFT}] Materialize a built-in sample?",
                default=True,
            )
            sample_name = None
            if include_sample:
                sample_name = Prompt.ask(
                    f"[{self.theme.BLUE_SOFT}]{self.deco.CHEVRON_RIGHT}[/{self.theme.BLUE_SOFT}] Sample",
                    default="2d_platformer" if dimension == "2D" else ("iso_adventure" if dimension == "2.5D" else "3d_arena"),
                    choices=["2d_platformer", "topdown_action", "iso_adventure", "3d_arena", "galgame_live2d", "tower_defense"],
                ).strip()
            overwrite = Confirm.ask(
                f"[{self.theme.BLUE_SOFT}]{self.deco.CHEVRON_RIGHT}[/{self.theme.BLUE_SOFT}] Overwrite starter files if they exist?",
                default=False,
            )
            result = tool.execute(
                action="create_project",
                output_dir=output_dir,
                project_name=project_name,
                dimension=dimension,
                sample_name=sample_name or "",
                overwrite=overwrite,
            )
            self._print_tool_result("Reverie Engine Project", result)
            return True

        if action == "sample":
            sample_name = tokens[1] if len(tokens) > 1 else Prompt.ask(
                f"[{self.theme.BLUE_SOFT}]{self.deco.CHEVRON_RIGHT}[/{self.theme.BLUE_SOFT}] Sample",
                default="2d_platformer",
                choices=["2d_platformer", "topdown_action", "iso_adventure", "3d_arena", "galgame_live2d", "tower_defense"],
            ).strip()
            overwrite = Confirm.ask(
                f"[{self.theme.BLUE_SOFT}]{self.deco.CHEVRON_RIGHT}[/{self.theme.BLUE_SOFT}] Overwrite sample files if they exist?",
                default=True,
            )
            result = tool.execute(
                action="materialize_sample",
                output_dir=output_dir,
                sample_name=sample_name,
                overwrite=overwrite,
            )
            self._print_tool_result("Reverie Engine Sample", result)
            return True

        if action == "run":
            scene_path = tokens[1] if len(tokens) > 1 else "data/scenes/main.relscene.json"
            headless = Confirm.ask(
                f"[{self.theme.BLUE_SOFT}]{self.deco.CHEVRON_RIGHT}[/{self.theme.BLUE_SOFT}] Run headless?",
                default=False,
            )
            result_data = run_project(
                self._get_project_root(),
                scene_path=scene_path,
                headless=headless,
                output_log=self._get_project_root() / "playtest/logs/manual_run.json",
            )
            self._print_game_panel(
                "Reverie Engine Run",
                "\n".join(
                    [
                        f"Success: {result_data['success']}",
                        f"Events: {result_data['summary']['event_count']}",
                        f"Log: {result_data['log_path']}",
                        f"Capabilities: {result_data['capabilities']}",
                    ]
                ),
            )
            return True

        if action == "validate":
            validation = tool.execute(action="validate_project", output_dir=output_dir)
            self._print_tool_result("Reverie Engine Validation", validation)
            return True

        if action == "smoke":
            scene_path = tokens[1] if len(tokens) > 1 else ""
            result = tool.execute(
                action="run_smoke",
                output_dir=output_dir,
                scene_path=scene_path,
            )
            self._print_tool_result("Reverie Engine Smoke", result)
            return True

        if action == "video":
            export_format = tokens[1] if len(tokens) > 1 else Prompt.ask(
                f"[{self.theme.BLUE_SOFT}]{self.deco.CHEVRON_RIGHT}[/{self.theme.BLUE_SOFT}] Export Format",
                default="mp4",
                choices=["mp4", "gif", "frames"],
            ).strip()
            scene_path = tokens[2] if len(tokens) > 2 else "data/scenes/main.relscene.json"
            frame_count = int(
                (tokens[3] if len(tokens) > 3 else Prompt.ask(
                    f"[{self.theme.BLUE_SOFT}]{self.deco.CHEVRON_RIGHT}[/{self.theme.BLUE_SOFT}] Runtime Frames",
                    default="180",
                ).strip())
                or "180"
            )
            result = tool.execute(
                action="export_video",
                output_dir=output_dir,
                scene_path=scene_path,
                format=export_format,
                frames=frame_count,
            )
            self._print_tool_result("Reverie Engine Video", result)
            return True

        if action in {"renpy", "import-renpy"}:
            script_path = tokens[1] if len(tokens) > 1 else Prompt.ask(
                f"[{self.theme.BLUE_SOFT}]{self.deco.CHEVRON_RIGHT}[/{self.theme.BLUE_SOFT}] Ren'Py Script Path",
                default="scripts/dialogue.rpy",
            ).strip()
            conversation_id = tokens[2] if len(tokens) > 2 else Prompt.ask(
                f"[{self.theme.BLUE_SOFT}]{self.deco.CHEVRON_RIGHT}[/{self.theme.BLUE_SOFT}] Conversation ID (optional)",
                default="",
            ).strip()
            entry_label = tokens[3] if len(tokens) > 3 else Prompt.ask(
                f"[{self.theme.BLUE_SOFT}]{self.deco.CHEVRON_RIGHT}[/{self.theme.BLUE_SOFT}] Entry Label (optional)",
                default="",
            ).strip()
            autostart = Confirm.ask(
                f"[{self.theme.BLUE_SOFT}]{self.deco.CHEVRON_RIGHT}[/{self.theme.BLUE_SOFT}] Update the main scene to autostart this conversation?",
                default=True,
            )
            result = tool.execute(
                action="import_renpy",
                output_dir=output_dir,
                script_path=script_path,
                conversation_id=conversation_id,
                entry_label=entry_label,
                autostart=autostart,
                overwrite=True,
            )
            self._print_tool_result("Reverie Engine Ren'Py Import", result)
            return True

        if action == "test":
            validation = tool.execute(action="validate_project", output_dir=output_dir)
            self._print_tool_result("Reverie Engine Validation", validation)
            if not validation.success or not validation.data.get("validation", {}).get("valid", False):
                return True
            smoke = tool.execute(action="run_smoke", output_dir=output_dir)
            self._print_tool_result("Reverie Engine Smoke", smoke)
            return True

        if action == "health":
            include_smoke = Confirm.ask(
                f"[{self.theme.BLUE_SOFT}]{self.deco.CHEVRON_RIGHT}[/{self.theme.BLUE_SOFT}] Include smoke validation?",
                default=False,
            )
            result = tool.execute(action="project_health", output_dir=output_dir, include_smoke=include_smoke)
            self._print_tool_result("Reverie Engine Health", result)
            return True

        if action == "benchmark":
            iterations = int(
                (tokens[1] if len(tokens) > 1 else Prompt.ask(
                    f"[{self.theme.BLUE_SOFT}]{self.deco.CHEVRON_RIGHT}[/{self.theme.BLUE_SOFT}] Iterations",
                    default="10",
                ).strip())
                or "10"
            )
            result = tool.execute(
                action="benchmark_project",
                output_dir=output_dir,
                iterations=iterations,
                output_path="playtest/logs/engine_benchmark.json",
            )
            self._print_tool_result("Reverie Engine Benchmark", result)
            return True

        if action == "package":
            include_smoke = Confirm.ask(
                f"[{self.theme.BLUE_SOFT}]{self.deco.CHEVRON_RIGHT}[/{self.theme.BLUE_SOFT}] Run smoke validation before packaging?",
                default=True,
            )
            result = tool.execute(
                action="package_project",
                output_dir=output_dir,
                include_smoke=include_smoke,
            )
            self._print_tool_result("Reverie Engine Package", result)
            return True

        self.console.print(
            f"[{self.theme.AMBER_GLOW}]{self.deco.DOT_MEDIUM} Usage: /engine [profile|create|sample|run|validate|smoke|video|renpy|health|benchmark|package|test][/{self.theme.AMBER_GLOW}]"
        )
        return True

    def cmd_modeling(self, args: str) -> bool:
        """Manage the Reverie-Gamer modeling pipeline."""
        from ..tools.game_modeling_workbench import GameModelingWorkbenchTool

        self._print_game_hint()
        if not self._require_gamer_mode("/modeling"):
            return True

        tokens = self._split_command_args(args)
        action = tokens[0].lower() if tokens else "status"
        tool = GameModelingWorkbenchTool(
            {
                "project_root": str(self._get_project_root()),
                "mcp_runtime": self.app.get("mcp_runtime"),
                "config_manager": self.app.get("config_manager"),
            }
        )
        output_dir = "."

        if action in {"help", "?"}:
            self._print_game_panel(
                "Modeling Commands",
                "\n".join(
                    [
                        "/modeling status",
                        "/modeling setup",
                        "/modeling sync",
                        "/modeling stub [model_name]",
                        "/modeling primitive [box|plane|pyramid|sphere] [model_name]",
                        "/modeling validate-bbmodel <source_bbmodel>",
                        "/modeling export-bbmodel <source_bbmodel> [dest_name]",
                        "/modeling import <runtime_export> [source_bbmodel] [preview_image] [dest_name]",
                        "/tools  # shows built-in Ashfox MCP tools when Blockbench + plugin are running",
                        "/modeling ashfox tools",
                        "/modeling ashfox capabilities",
                        "/modeling ashfox state [summary|full]",
                        "/modeling ashfox validate",
                        "/modeling ashfox export <format> <dest_path>",
                        "/modeling ashfox call <tool_name> <json_arguments>",
                    ]
                ),
            )
            return True

        if action in {"status", "inspect"}:
            result = tool.execute(action="inspect_stack", output_dir=output_dir)
            self._print_tool_result("Modeling Stack", result)
            return True

        if action == "setup":
            overwrite = Confirm.ask(
                f"[{self.theme.BLUE_SOFT}]{self.deco.CHEVRON_RIGHT}[/{self.theme.BLUE_SOFT}] Overwrite existing modeling manifest and README files?",
                default=False,
            )
            result = tool.execute(action="setup_workspace", output_dir=output_dir, overwrite=overwrite)
            self._print_tool_result("Modeling Workspace", result)
            return True

        if action in {"sync", "registry"}:
            result = tool.execute(action="sync_registry", output_dir=output_dir)
            self._print_tool_result("Model Registry", result)
            return True

        if action in {"stub", "new"}:
            model_name = tokens[1] if len(tokens) > 1 else Prompt.ask(
                f"[{self.theme.BLUE_SOFT}]{self.deco.CHEVRON_RIGHT}[/{self.theme.BLUE_SOFT}] Model Name",
                default="starter_prop",
            ).strip()
            overwrite = Confirm.ask(
                f"[{self.theme.BLUE_SOFT}]{self.deco.CHEVRON_RIGHT}[/{self.theme.BLUE_SOFT}] Overwrite the stub if it already exists?",
                default=False,
            )
            result = tool.execute(
                action="create_model_stub",
                output_dir=output_dir,
                model_name=model_name,
                overwrite=overwrite,
            )
            self._print_tool_result("Model Stub", result)
            return True

        if action == "primitive":
            primitive = tokens[1] if len(tokens) > 1 else Prompt.ask(
                f"[{self.theme.BLUE_SOFT}]{self.deco.CHEVRON_RIGHT}[/{self.theme.BLUE_SOFT}] Primitive",
                default="box",
                choices=["box", "plane", "pyramid", "sphere"],
            ).strip()
            model_name = tokens[2] if len(tokens) > 2 else Prompt.ask(
                f"[{self.theme.BLUE_SOFT}]{self.deco.CHEVRON_RIGHT}[/{self.theme.BLUE_SOFT}] Model Name",
                default=f"{primitive}_asset",
            ).strip()
            size = float(
                (tokens[3] if len(tokens) > 3 else Prompt.ask(
                    f"[{self.theme.BLUE_SOFT}]{self.deco.CHEVRON_RIGHT}[/{self.theme.BLUE_SOFT}] Base Size",
                    default="1.0",
                ).strip())
                or "1.0"
            )
            create_preview = Confirm.ask(
                f"[{self.theme.BLUE_SOFT}]{self.deco.CHEVRON_RIGHT}[/{self.theme.BLUE_SOFT}] Generate a preview image?",
                default=True,
            )
            overwrite = Confirm.ask(
                f"[{self.theme.BLUE_SOFT}]{self.deco.CHEVRON_RIGHT}[/{self.theme.BLUE_SOFT}] Overwrite generated files if they exist?",
                default=False,
            )
            result = tool.execute(
                action="generate_primitive",
                output_dir=output_dir,
                primitive=primitive,
                model_name=model_name,
                size=size,
                create_preview=create_preview,
                overwrite=overwrite,
            )
            self._print_tool_result("Primitive Model", result)
            return True

        if action in {"validate-bbmodel", "validate_bbmodel", "bbvalidate"}:
            bbmodel_path = tokens[1] if len(tokens) > 1 else Prompt.ask(
                f"[{self.theme.BLUE_SOFT}]{self.deco.CHEVRON_RIGHT}[/{self.theme.BLUE_SOFT}] `.bbmodel` Path"
            ).strip()
            result = tool.execute(
                action="validate_blockbench_model",
                output_dir=output_dir,
                bbmodel_path=bbmodel_path,
            )
            self._print_tool_result("Blockbench Headless Validation", result)
            return True

        if action in {"export-bbmodel", "export_bbmodel", "bbexport"}:
            bbmodel_path = tokens[1] if len(tokens) > 1 else Prompt.ask(
                f"[{self.theme.BLUE_SOFT}]{self.deco.CHEVRON_RIGHT}[/{self.theme.BLUE_SOFT}] `.bbmodel` Path"
            ).strip()
            dest_name = tokens[2] if len(tokens) > 2 else Prompt.ask(
                f"[{self.theme.BLUE_SOFT}]{self.deco.CHEVRON_RIGHT}[/{self.theme.BLUE_SOFT}] Target Name (optional)",
                default="",
            ).strip()
            overwrite = Confirm.ask(
                f"[{self.theme.BLUE_SOFT}]{self.deco.CHEVRON_RIGHT}[/{self.theme.BLUE_SOFT}] Overwrite generated runtime export if it exists?",
                default=False,
            )
            kwargs = {
                "action": "export_blockbench_model",
                "output_dir": output_dir,
                "bbmodel_path": bbmodel_path,
                "overwrite": overwrite,
            }
            if dest_name:
                kwargs["dest_name"] = dest_name
            result = tool.execute(**kwargs)
            self._print_tool_result("Blockbench Headless Export", result)
            return True

        if action == "import":
            runtime_export = tokens[1] if len(tokens) > 1 else Prompt.ask(
                f"[{self.theme.BLUE_SOFT}]{self.deco.CHEVRON_RIGHT}[/{self.theme.BLUE_SOFT}] Runtime Export Path"
            ).strip()
            source_model = tokens[2] if len(tokens) > 2 else Prompt.ask(
                f"[{self.theme.BLUE_SOFT}]{self.deco.CHEVRON_RIGHT}[/{self.theme.BLUE_SOFT}] Source `.bbmodel` Path (optional)",
                default="",
            ).strip()
            preview_image = tokens[3] if len(tokens) > 3 else Prompt.ask(
                f"[{self.theme.BLUE_SOFT}]{self.deco.CHEVRON_RIGHT}[/{self.theme.BLUE_SOFT}] Preview Image Path (optional)",
                default="",
            ).strip()
            dest_name = tokens[4] if len(tokens) > 4 else Prompt.ask(
                f"[{self.theme.BLUE_SOFT}]{self.deco.CHEVRON_RIGHT}[/{self.theme.BLUE_SOFT}] Target Name (optional)",
                default="",
            ).strip()
            overwrite = Confirm.ask(
                f"[{self.theme.BLUE_SOFT}]{self.deco.CHEVRON_RIGHT}[/{self.theme.BLUE_SOFT}] Overwrite existing imported files?",
                default=False,
            )
            kwargs = {
                "action": "import_export",
                "output_dir": output_dir,
                "source_path": runtime_export,
                "overwrite": overwrite,
            }
            if source_model:
                kwargs["source_model_path"] = source_model
            if preview_image:
                kwargs["preview_path"] = preview_image
            if dest_name:
                kwargs["dest_name"] = dest_name
            result = tool.execute(**kwargs)
            self._print_tool_result("Model Import", result)
            return True

        if action == "ashfox":
            subcommand = tokens[1].lower() if len(tokens) > 1 else "tools"
            if subcommand in {"tools", "list"}:
                result = tool.execute(action="list_ashfox_tools")
                self._print_tool_result("Ashfox Tool List", result)
                return True

            if subcommand == "capabilities":
                result = tool.execute(action="ashfox_call", tool_name="list_capabilities", arguments={})
                self._print_tool_result("Ashfox Capabilities", result)
                return True

            if subcommand == "state":
                detail = tokens[2] if len(tokens) > 2 else "summary"
                result = tool.execute(
                    action="ashfox_call",
                    tool_name="get_project_state",
                    arguments={"detail": detail},
                )
                self._print_tool_result("Ashfox Project State", result)
                return True

            if subcommand == "validate":
                result = tool.execute(action="ashfox_call", tool_name="validate", arguments={})
                self._print_tool_result("Ashfox Validation", result)
                return True

            if subcommand == "export":
                export_format = tokens[2] if len(tokens) > 2 else "gltf"
                dest_path = tokens[3] if len(tokens) > 3 else "assets/models/runtime/export.glb"
                result = tool.execute(
                    action="ashfox_call",
                    tool_name="export",
                    arguments={"format": export_format, "destPath": dest_path},
                )
                self._print_tool_result("Ashfox Export", result)
                return True

            if subcommand == "call":
                raw_command = args.strip()
                parts = raw_command.split(None, 3)
                tool_name = parts[2] if len(parts) > 2 else ""
                if not tool_name:
                    tool_name = Prompt.ask(
                        f"[{self.theme.BLUE_SOFT}]{self.deco.CHEVRON_RIGHT}[/{self.theme.BLUE_SOFT}] Ashfox Tool Name"
                    ).strip()
                raw_json = parts[3] if len(parts) > 3 else "{}"
                try:
                    arguments = json.loads(raw_json) if raw_json.strip() else {}
                except json.JSONDecodeError:
                    self.console.print(
                        f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} Invalid JSON arguments for `/modeling ashfox call`[/{self.theme.CORAL_SOFT}]"
                    )
                    return True
                result = tool.execute(
                    action="ashfox_call",
                    tool_name=tool_name,
                    arguments=arguments,
                )
                self._print_tool_result("Ashfox Tool Call", result)
                return True

        self.console.print(
            f"[{self.theme.AMBER_GLOW}]{self.deco.DOT_MEDIUM} Usage: /modeling [status|setup|sync|stub|primitive|validate-bbmodel|export-bbmodel|import|ashfox][/{self.theme.AMBER_GLOW}]"
        )
        return True

    def cmd_blender(self, args: str) -> bool:
        """Manage the built-in Blender modeling workflow."""
        from ..tools.blender_modeling_workbench import BlenderModelingWorkbenchTool

        tokens = self._split_command_args(args)
        action = tokens[0].lower() if tokens else "status"
        tool = BlenderModelingWorkbenchTool(
            {
                "project_root": str(self._get_project_root()),
                "config_manager": self.app.get("config_manager"),
            }
        )
        output_dir = "."

        if action in {"help", "?"}:
            self._show_command_panel(
                "Blender Modeling",
                subtitle="First-party Blender authoring without an external MCP server or Skill.",
                accent=self.theme.BLUE_SOFT,
            )
            self.console.print(
                self._build_command_table(
                    [
                        ("/blender status", "Inspect Blender install, generated scripts, and model counts"),
                        ("/blender setup", "Create Blender source/script/plan folders inside the modeling workspace"),
                        ("/blender script <model_name> <brief>", "Generate a Blender Python authoring script without running Blender"),
                        ("/blender script hero \"Genshin / ZZZ style anime action character\"", "Generate a richer stylized character blockout preset"),
                        ("/blender create <model_name> <brief>", "Generate and run Blender to save `.blend`, export `.glb`, and render a preview"),
                        ("/blender run <script_path>", "Run a workspace-local Blender Python script in background mode"),
                        ("/blender validate <script_path>", "Run Reverie's conservative static scan against a Blender script"),
                        ("/blender audit <model_name>", "Audit generated `.blend`/`.glb`/textures/rig/actions/collision/LOD gates"),
                        ("/blender repair <model_name>", "Consume the black-box repair queue: regenerate, rerun Blender, and re-audit"),
                        ("/blender sync", "Regenerate `data/models/model_registry.yaml`"),
                    ],
                    title="Blender Commands",
                    accent=self.theme.BORDER_SECONDARY,
                )
            )
            self.console.print()
            return True

        if action in {"status", "inspect"}:
            result = tool.execute(action="inspect_stack", output_dir=output_dir)
            self._print_tool_result("Blender Modeling Stack", result)
            return True

        if action == "setup":
            overwrite = Confirm.ask(
                f"[{self.theme.BLUE_SOFT}]{self.deco.CHEVRON_RIGHT}[/{self.theme.BLUE_SOFT}] Overwrite existing Blender modeling README/manifest files?",
                default=False,
            )
            result = tool.execute(action="setup_workspace", output_dir=output_dir, overwrite=overwrite)
            self._print_tool_result("Blender Modeling Workspace", result)
            return True

        if action in {"script", "generate"}:
            model_name = tokens[1] if len(tokens) > 1 else Prompt.ask(
                f"[{self.theme.BLUE_SOFT}]{self.deco.CHEVRON_RIGHT}[/{self.theme.BLUE_SOFT}] Model Name",
                default="blender_asset",
            ).strip()
            brief = " ".join(tokens[2:]).strip() if len(tokens) > 2 else Prompt.ask(
                f"[{self.theme.BLUE_SOFT}]{self.deco.CHEVRON_RIGHT}[/{self.theme.BLUE_SOFT}] Modeling Brief",
                default=model_name,
            ).strip()
            overwrite = Confirm.ask(
                f"[{self.theme.BLUE_SOFT}]{self.deco.CHEVRON_RIGHT}[/{self.theme.BLUE_SOFT}] Overwrite existing generated plan/script?",
                default=False,
            )
            result = tool.execute(
                action="generate_script",
                output_dir=output_dir,
                model_name=model_name,
                brief=brief,
                overwrite=overwrite,
            )
            self._print_tool_result("Blender Authoring Script", result)
            return True

        if action in {"create", "model", "new"}:
            model_name = tokens[1] if len(tokens) > 1 else Prompt.ask(
                f"[{self.theme.BLUE_SOFT}]{self.deco.CHEVRON_RIGHT}[/{self.theme.BLUE_SOFT}] Model Name",
                default="blender_asset",
            ).strip()
            brief = " ".join(tokens[2:]).strip() if len(tokens) > 2 else Prompt.ask(
                f"[{self.theme.BLUE_SOFT}]{self.deco.CHEVRON_RIGHT}[/{self.theme.BLUE_SOFT}] Modeling Brief",
                default=model_name,
            ).strip()
            render_preview = Confirm.ask(
                f"[{self.theme.BLUE_SOFT}]{self.deco.CHEVRON_RIGHT}[/{self.theme.BLUE_SOFT}] Render a preview image?",
                default=True,
            )
            overwrite = Confirm.ask(
                f"[{self.theme.BLUE_SOFT}]{self.deco.CHEVRON_RIGHT}[/{self.theme.BLUE_SOFT}] Overwrite existing generated files?",
                default=False,
            )
            result = tool.execute(
                action="create_model",
                output_dir=output_dir,
                model_name=model_name,
                brief=brief,
                export_format="glb",
                render_preview=render_preview,
                run_blender=True,
                overwrite=overwrite,
            )
            self._print_tool_result("Blender Model", result)
            return True

        if action == "run":
            script_path = tokens[1] if len(tokens) > 1 else Prompt.ask(
                f"[{self.theme.BLUE_SOFT}]{self.deco.CHEVRON_RIGHT}[/{self.theme.BLUE_SOFT}] Script Path"
            ).strip()
            result = tool.execute(action="run_script", output_dir=output_dir, script_path=script_path)
            self._print_tool_result("Blender Script Run", result)
            return True

        if action == "validate":
            script_path = tokens[1] if len(tokens) > 1 else Prompt.ask(
                f"[{self.theme.BLUE_SOFT}]{self.deco.CHEVRON_RIGHT}[/{self.theme.BLUE_SOFT}] Script Path"
            ).strip()
            result = tool.execute(action="validate_script", output_dir=output_dir, script_path=script_path)
            self._print_tool_result("Blender Script Validation", result)
            return True

        if action in {"audit", "qa", "quality"}:
            model_name = tokens[1] if len(tokens) > 1 else Prompt.ask(
                f"[{self.theme.BLUE_SOFT}]{self.deco.CHEVRON_RIGHT}[/{self.theme.BLUE_SOFT}] Model Name"
            ).strip()
            result = tool.execute(action="audit_model", output_dir=output_dir, model_name=model_name)
            self._print_tool_result("Blender Model Audit", result)
            return True

        if action in {"repair", "fix", "iterate"}:
            model_name = tokens[1] if len(tokens) > 1 else Prompt.ask(
                f"[{self.theme.BLUE_SOFT}]{self.deco.CHEVRON_RIGHT}[/{self.theme.BLUE_SOFT}] Model Name"
            ).strip()
            max_iterations = int(tokens[2]) if len(tokens) > 2 and tokens[2].isdigit() else 3
            result = tool.execute(
                action="repair_model",
                output_dir=output_dir,
                model_name=model_name,
                max_iterations=max_iterations,
            )
            self._print_tool_result("Blender Black-Box Repair", result)
            return True

        if action in {"sync", "registry"}:
            result = tool.execute(action="sync_registry", output_dir=output_dir)
            self._print_tool_result("Blender Model Registry", result)
            return True

        self.console.print(
            f"[{self.theme.AMBER_GLOW}]{self.deco.DOT_MEDIUM} Usage: /blender [status|setup|script|create|run|validate|audit|repair|sync][/{self.theme.AMBER_GLOW}]"
        )
        return True
    
    def cmd_add_model(self, args: str) -> bool:
        """Add a new model configuration with dreamy wizard"""
        from ..config import ModelConfig  # Import locally to avoid circular imports if any
        
        self.console.print()
        self.console.print(Panel(
            f"[bold {self.theme.PINK_SOFT}]{self.deco.SPARKLE} Add New Model Configuration {self.deco.SPARKLE}[/bold {self.theme.PINK_SOFT}]",
            border_style=self.theme.BORDER_PRIMARY,
            box=box.ROUNDED,
            padding=(0, 2)
        ))
        self.console.print()
        
        try:
            # interactive wizard
            base_url = Prompt.ask(
                f"[{self.theme.BLUE_SOFT}]{self.deco.CHEVRON_RIGHT}[/{self.theme.BLUE_SOFT}] API Base URL",
                default="https://api.openai.com/v1"
            )
            
            api_key = Prompt.ask(
                f"[{self.theme.BLUE_SOFT}]{self.deco.CHEVRON_RIGHT}[/{self.theme.BLUE_SOFT}] API Key (hidden)",
                password=True
            )
            
            model_name = Prompt.ask(
                f"[{self.theme.BLUE_SOFT}]{self.deco.CHEVRON_RIGHT}[/{self.theme.BLUE_SOFT}] Model Identifier (e.g. gpt-4, claude-3-opus)",
                default="gpt-4"
            )
            
            display_name = Prompt.ask(
                f"[{self.theme.BLUE_SOFT}]{self.deco.CHEVRON_RIGHT}[/{self.theme.BLUE_SOFT}] Display Name",
                default=model_name
            )

            max_tokens_str = Prompt.ask(
                f"[{self.theme.BLUE_SOFT}]{self.deco.CHEVRON_RIGHT}[/{self.theme.BLUE_SOFT}] Max Context Tokens (Optional, default 128000)",
                default="128000"
            )
            try:
                max_tokens = int(max_tokens_str)
            except ValueError:
                max_tokens = 128000
            
            # Create config object
            new_model = ModelConfig(
                model=model_name,
                model_display_name=display_name,
                base_url=base_url,
                api_key=api_key,
                max_context_tokens=max_tokens
            )
            
            # Optional: Verify connection
            if Confirm.ask("Verify connection before saving?", default=True):
                 with self.console.status(f"[{self.theme.PURPLE_SOFT}]{self.deco.SPARKLE} Verifying connection...[/{self.theme.PURPLE_SOFT}]"):
                     try:
                         from openai import OpenAI
                         client = OpenAI(
                             base_url=base_url,
                             api_key=api_key
                         )
                         # Try to list models to verify auth and availability
                         models = client.models.list()
                         model_ids = [m.id for m in models.data]
                         
                         self.console.print(f"[{self.theme.MINT_VIBRANT}]{self.deco.CHECK_FANCY} Connection successful![/{self.theme.MINT_VIBRANT}]")
                         
                         # If the user entered a model name that exists, confirm it
                         if model_name in model_ids:
                             self.console.print(f"[{self.theme.MINT_VIBRANT}]{self.deco.CHECK_FANCY} Model '{model_name}' found in provider list.[/{self.theme.MINT_VIBRANT}]")
                         else:
                             self.console.print(f"[{self.theme.AMBER_GLOW}]{self.deco.DOT_MEDIUM} Model '{model_name}' not found in provider's list. Available: {', '.join(model_ids[:5])}...[/{self.theme.AMBER_GLOW}]")
                             if Confirm.ask("Would you like to select a model from the list?", default=True):
                                 # Simple selection
                                 # (In a real app, use a fuzzy selector or list)
                                 pass 
                     except Exception as e:
                         self.console.print(f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} Verification failed: {str(e)}[/{self.theme.CORAL_SOFT}]")
                         if not Confirm.ask("Save anyway?", default=False):
                             return True
 
            config_manager = self.app.get('config_manager')
            if config_manager:
                config_manager.add_model(new_model)
                self.console.print(f"\n[{self.theme.MINT_VIBRANT}]{self.deco.CHECK_FANCY} Model '{display_name}' added successfully![/{self.theme.MINT_VIBRANT}]")
                
                # Ask to switch
                if Confirm.ask("Switch to this model now?", default=True):
                    config = config_manager.load()
                    # The new model is last
                    new_index = len(config.models) - 1
                    config_manager.set_active_model(new_index)
                    self.console.print(f"[{self.theme.MINT_VIBRANT}]{self.deco.CHECK_FANCY} Active model updated.[/{self.theme.MINT_VIBRANT}]")
                    
                    if self.app.get('reinit_agent'):
                        self.app['reinit_agent']()
            else:
                self.console.print(f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} Error: Config manager not found.[/{self.theme.CORAL_SOFT}]")
                
        except KeyboardInterrupt:
            self.console.print(f"\n[{self.theme.AMBER_GLOW}]{self.deco.DOT_MEDIUM} Cancelled.[/{self.theme.AMBER_GLOW}]")
            
        return True
    
    def cmd_search(self, args: str) -> bool:
        """Web search with styled output"""
        if not args:
            self.console.print(f"[{self.theme.AMBER_GLOW}]{self.deco.DOT_MEDIUM} Usage: /search <query>[/{self.theme.AMBER_GLOW}]")
            return True
        
        from ..tools import WebSearchTool
        
        tool = WebSearchTool()
        with self.console.status(f"[{self.theme.PURPLE_SOFT}]{self.deco.SPARKLE} Searching: {args}...[/{self.theme.PURPLE_SOFT}]"):
            result = tool.execute(query=args, max_results=5)
        
        if result.success:
            from rich.markdown import Markdown
            self.console.print(Markdown(result.output))
        else:
            self.console.print(f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} Search failed: {result.error}[/{self.theme.CORAL_SOFT}]")
        
        return True
    
    def cmd_sessions(self, args: str) -> bool:
        """Session management with dreamy styling"""
        session_manager = self.app.get('session_manager')
        workspace_stats_manager = self.app.get('workspace_stats_manager')
        if not session_manager:
            self._show_activity_event("Sessions", "Session manager not available.", status="error")
            return True

        sessions = session_manager.list_sessions()
        current = session_manager.get_current_session()
        agent = self.app.get('agent')
        workspace_path = getattr(session_manager, 'workspace_path', '')

        self._show_command_panel(
            "Session Browser",
            subtitle="Load, create, and review saved conversations for this workspace.",
            accent=self.theme.BORDER_PRIMARY,
            meta=f"Workspace: {workspace_path}" if workspace_path else "",
        )

        if sessions:
            table = Table(
                box=box.ROUNDED,
                border_style=self.theme.BORDER_PRIMARY,
                caption=f"[{self.theme.TEXT_DIM}]Current directory: {escape(str(workspace_path))}[/{self.theme.TEXT_DIM}]" if workspace_path else ""
            )
            table.add_column("#", style=self.theme.TEXT_DIM)
            table.add_column("Name", style=f"bold {self.theme.BLUE_SOFT}")
            table.add_column("Messages", style=self.theme.TEXT_SECONDARY)
            table.add_column("Updated", style=self.theme.TEXT_DIM)
            table.add_column("", style=self.theme.MINT_SOFT)

            for i, session in enumerate(sessions, 1):
                is_current = f"[{self.theme.MINT_VIBRANT}]{self.deco.CHECK_FANCY}[/{self.theme.MINT_VIBRANT}]" if current and session.id == current.id else ""
                table.add_row(
                    str(i),
                    session.name,
                    str(session.message_count),
                    session.updated_at[:16].replace('T', ' '),
                    is_current
                )

            self.console.print(table)
        else:
            self._show_activity_event(
                "Sessions",
                "No saved sessions in this workspace yet.",
                detail="Create one with 'n' to start building transcript history.",
                meta=str(workspace_path) if workspace_path else "",
            )

        actions_text = "Actions: (n)ew, (number) to load, (d) to delete" if sessions else "Actions: (n)ew"
        self._show_activity_event(
            "Sessions",
            "Choose an action to continue.",
            detail=actions_text,
            meta="Press Enter to keep the current session.",
            blank_before=True,
        )

        try:
            choice = Prompt.ask(f"[{self.theme.PURPLE_SOFT}]Action[/{self.theme.PURPLE_SOFT}]", default="")

            if choice.lower() == 'n':
                name = Prompt.ask(f"[{self.theme.BLUE_SOFT}]{self.deco.CHEVRON_RIGHT}[/{self.theme.BLUE_SOFT}] Session name", default="")
                session = session_manager.create_session(name or None)
                if agent:
                    agent.set_history(session.messages)
                if workspace_stats_manager:
                    workspace_stats_manager.update_session_snapshot(
                        session.id,
                        session_name=session.name,
                        message_count=len(session.messages),
                    )
                self._show_activity_event(
                    "Sessions",
                    f"Created session: {session.name}",
                    status="success",
                    detail="The agent context now points at the new conversation.",
                )

            elif choice.lower() == 'd':
                if not sessions:
                    self._show_activity_event("Sessions", "Nothing to delete.", status="warning")
                    return True

                idx = Prompt.ask(f"[{self.theme.PURPLE_SOFT}]Delete session #[/{self.theme.PURPLE_SOFT}]")
                try:
                    idx = int(idx) - 1
                    if 0 <= idx < len(sessions):
                        target = sessions[idx]
                        if Confirm.ask(f"Delete '{target.name}'?"):
                            was_current = bool(current and target.id == current.id)
                            session_manager.delete_session(target.id)

                            if was_current:
                                replacement = session_manager.restore_last_session()
                                if replacement is None:
                                    replacement = session_manager.create_session()
                                if agent:
                                    agent.set_history(replacement.messages)
                                if workspace_stats_manager:
                                    workspace_stats_manager.update_session_snapshot(
                                        replacement.id,
                                        session_name=replacement.name,
                                        message_count=len(replacement.messages),
                                    )
                                self._show_activity_event(
                                    "Sessions",
                                    f"Deleted session and switched to: {replacement.name}",
                                    status="success",
                                )
                            else:
                                self._show_activity_event("Sessions", "Deleted session.", status="success")
                except ValueError:
                    self._show_activity_event(
                        "Sessions",
                        "Invalid session number.",
                        status="warning",
                        detail="Use the index shown in the sessions table.",
                    )

            elif choice.isdigit():
                idx = int(choice) - 1
                if 0 <= idx < len(sessions):
                    session = session_manager.load_session(sessions[idx].id)
                    if session:
                        self._show_activity_event(
                            "Sessions",
                            f"Loaded session: {session.name}",
                            status="success",
                            detail="Showing the full transcript below.",
                        )
                        if agent:
                            agent.set_history(session.messages)
                        if workspace_stats_manager:
                            workspace_stats_manager.update_session_snapshot(
                                session.id,
                                session_name=session.name,
                                message_count=len(session.messages),
                            )
                        self._show_session_transcript(
                            session.to_dict(),
                            title=f"Loaded Session {self.deco.DOT_MEDIUM} {session.name}",
                        )
        except KeyboardInterrupt:
            self._show_activity_event("Sessions", "Session browser cancelled.", status="warning")

        return True
    
    def cmd_history(self, args: str) -> bool:
        """View conversation history with themed styling"""
        agent = self.app.get('agent')
        session_manager = self.app.get('session_manager')
        if not agent:
            self.console.print(f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} Agent not available[/{self.theme.CORAL_SOFT}]")
            return True
        
        limit = 999999
        if args:
            try:
                limit = int(args)
            except ValueError:
                pass
        
        history = agent.get_history()
        
        if not history:
            self.console.print(f"[{self.theme.TEXT_DIM}]{self.deco.DOT_MEDIUM} No conversation history yet.[/{self.theme.TEXT_DIM}]")
            return True

        current_session = session_manager.get_current_session() if session_manager else None
        payload = {
            "id": current_session.id if current_session else "current",
            "name": current_session.name if current_session else "Current Conversation",
            "created_at": current_session.created_at if current_session else "",
            "updated_at": current_session.updated_at if current_session else "",
            "messages": history[-limit:] if limit < len(history) else history,
        }
        self._show_session_transcript(payload, title="Conversation History")
        return True

    def _message_text(self, value: Any) -> str:
        """Flatten persisted message content into readable transcript text."""
        if value is None:
            return ""
        if isinstance(value, str):
            return value
        if isinstance(value, (int, float, bool)):
            return str(value)
        if isinstance(value, list):
            parts: List[str] = []
            for item in value:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict):
                    text = (
                        item.get("text")
                        or item.get("content")
                        or item.get("output_text")
                        or item.get("input_text")
                        or item.get("value")
                    )
                    if text is not None:
                        parts.append(str(text))
                    else:
                        parts.append(json.dumps(item, ensure_ascii=False))
                else:
                    parts.append(str(item))
            return "\n".join(part for part in parts if part).strip()
        if isinstance(value, dict):
            text = (
                value.get("text")
                or value.get("content")
                or value.get("output_text")
                or value.get("input_text")
                or value.get("value")
            )
            if text is not None:
                return self._message_text(text)
            return json.dumps(value, ensure_ascii=False, indent=2)
        return str(value)

    def _format_duration(self, seconds: Any) -> str:
        try:
            total_seconds = max(0, int(float(seconds or 0)))
        except (TypeError, ValueError):
            total_seconds = 0
        hours, remainder = divmod(total_seconds, 3600)
        minutes, secs = divmod(remainder, 60)
        if hours:
            return f"{hours}h {minutes}m {secs}s"
        if minutes:
            return f"{minutes}m {secs}s"
        return f"{secs}s"

    def _show_session_transcript(self, session_payload: Dict[str, Any], title: str = "Session Transcript") -> None:
        """Render one session with readable role blocks and full transcript paging."""
        messages = session_payload.get("messages", []) or []
        session_name = str(session_payload.get("name", "") or "Session").strip()
        session_id = str(session_payload.get("id", "") or "").strip()
        created_at = str(session_payload.get("created_at", "") or "").strip()
        updated_at = str(session_payload.get("updated_at", "") or "").strip()
        transcript_width = max(int(getattr(self.console, "width", 80) or 80) - 3, 40)

        header = Panel(
            Group(
                Text.from_markup(
                    f"[bold {self.theme.PINK_SOFT}]{escape(title)}[/{self.theme.PINK_SOFT}]"
                ),
                Text.from_markup(
                    f"[{self.theme.TEXT_SECONDARY}]Name: {escape(session_name)}[/{self.theme.TEXT_SECONDARY}]"
                ),
                Text.from_markup(
                    f"[{self.theme.TEXT_DIM}]ID: {escape(session_id or 'n/a')}  {self.deco.DOT_MEDIUM}  "
                    f"Created: {escape(created_at or 'n/a')}  {self.deco.DOT_MEDIUM}  "
                    f"Updated: {escape(updated_at or 'n/a')}  {self.deco.DOT_MEDIUM}  "
                    f"Messages: {len(messages)}[/{self.theme.TEXT_DIM}]"
                ),
            ),
            border_style=self.theme.BORDER_PRIMARY,
            box=box.ROUNDED,
            padding=(0, 1),
        )

        with self.console.pager(styles=True):
            self.console.print()
            self.console.print(header)
            self.console.print()

            for index, message in enumerate(messages, start=1):
                role = str(message.get("role", "") or "unknown").strip().lower()
                reasoning_content = self._message_text(message.get("reasoning_content"))
                content_text = self._message_text(message.get("content"))
                accent = {
                    "user": self.theme.BLUE_SOFT,
                    "assistant": self.theme.PINK_SOFT,
                    "system": self.theme.PURPLE_SOFT,
                    "tool": self.theme.MINT_SOFT,
                }.get(role, self.theme.TEXT_SECONDARY)
                label = {
                    "user": "User",
                    "assistant": "Assistant",
                    "system": "System",
                    "tool": "Tool",
                }.get(role, "Message")
                if role == "tool":
                    tool_name = str(message.get("name") or message.get("tool_name") or "").strip()
                    if tool_name:
                        label = f"Tool {self.deco.DOT_MEDIUM} {tool_name}"

                label_line = Text()
                label_line.append("+- ", style=accent)
                label_line.append(f"#{index:03d} ", style=self.theme.TEXT_DIM)
                label_line.append(label, style=f"bold {accent}")
                self.console.print(label_line)

                if reasoning_content:
                    self.console.print(
                        Padding(
                            Text("Thinking...", style=f"italic {self.theme.THINKING_MEDIUM}"),
                            (0, 0, 0, 2),
                        )
                    )
                    for thought_line in reasoning_content.splitlines():
                        if not thought_line.strip():
                            continue
                        rendered = Text()
                        rendered.append("│ ", style=self.theme.THINKING_BORDER)
                        rendered.append(thought_line.strip(), style=f"italic {self.theme.THINKING_SOFT}")
                        self.console.print(Padding(rendered, (0, 0, 0, 3)))

                if content_text:
                    if role in {"assistant", "system"}:
                        self.console.print(
                            Padding(
                                format_markdown(
                                    content_text,
                                    formatter=self._markdown_formatter,
                                    max_width=transcript_width,
                                ),
                                (0, 0, 0, 2),
                            )
                        )
                    else:
                        self.console.print(
                            Padding(
                                Text(content_text, style=self.theme.TEXT_PRIMARY),
                                (0, 0, 0, 2),
                            )
                        )

                tool_calls = message.get("tool_calls")
                if isinstance(tool_calls, list) and tool_calls:
                    tool_lines: List[str] = []
                    for tool_call in tool_calls:
                        if not isinstance(tool_call, dict):
                            continue
                        function = tool_call.get("function") if isinstance(tool_call.get("function"), dict) else {}
                        tool_name = str(function.get("name", "") or tool_call.get("name", "") or "tool").strip()
                        arguments = function.get("arguments", "")
                        argument_text = self._message_text(arguments)
                        tool_lines.append(f"- {tool_name}")
                        if argument_text:
                            tool_lines.append(argument_text)
                    if tool_lines:
                        self.console.print(
                            Padding(
                                Text("\n".join(tool_lines), style=self.theme.TEXT_SECONDARY),
                                (0, 0, 0, 2),
                            )
                        )

                self.console.print(Text("\\-", style=accent))
                self.console.print()

    def cmd_total(self, args: str) -> bool:
        """Show persistent workspace totals and let the user inspect another workspace."""
        from ..config import get_app_root
        from ..session import WorkspaceStatsManager, get_known_workspaces
        from .tui_selector import TUISelector, SelectorItem, SelectorAction

        workspaces = get_known_workspaces(get_app_root())
        if not workspaces:
            self.console.print(f"[{self.theme.TEXT_DIM}]{self.deco.DOT_MEDIUM} No workspace statistics found yet.[/{self.theme.TEXT_DIM}]")
            return True

        selected_workspace = None
        if len(workspaces) == 1 and args.strip().lower() not in {"choose", "select"}:
            selected_workspace = workspaces[0]
        else:
            selector_items = [
                SelectorItem(
                    id=str(index),
                    title=str(item.get("workspace_name") or Path(str(item.get("workspace_path") or item.get("cache_dir"))).name),
                    description=(
                        f"{Path(str(item.get('workspace_path') or item.get('cache_dir'))).name}  "
                        f"{self.deco.DOT_MEDIUM}  {item.get('session_count', 0)} sessions  "
                        f"{self.deco.DOT_MEDIUM}  active {self._format_duration(item.get('total_active_seconds', 0))}"
                    ),
                    metadata=item,
                )
                for index, item in enumerate(workspaces, start=1)
            ]
            selector = TUISelector(
                self.console,
                title="Workspace Totals",
                items=selector_items,
                allow_search=True,
                allow_cancel=True,
                show_descriptions=True,
                max_visible=10,
            )
            result = selector.run()
            if result.action != SelectorAction.SELECT or not result.selected_item:
                return True
            selected_workspace = result.selected_item.metadata

        cache_dir = Path(str(selected_workspace.get("cache_dir") or ""))
        active_stats_manager = self.app.get("workspace_stats_manager")
        if active_stats_manager:
            try:
                active_stats_manager.flush()
            except Exception:
                pass

        if active_stats_manager and Path(getattr(active_stats_manager, "project_data_dir", cache_dir)).resolve() == cache_dir.resolve():
            stats_manager = active_stats_manager
        else:
            stats_manager = WorkspaceStatsManager.from_cache_dir(cache_dir)
        dashboard = stats_manager.build_dashboard_data()
        session_rows = WorkspaceStatsManager.list_session_files(cache_dir)
        session_usage_map = {
            str(item.get("session_id")): item
            for item in dashboard.get("session_usage", [])
            if isinstance(item, dict) and str(item.get("session_id", "")).strip()
        }

        self.console.print()
        summary = Table(show_header=False, box=box.SIMPLE_HEAVY, border_style=self.theme.BORDER_PRIMARY, expand=True)
        summary.add_column(style=self.theme.TEXT_SECONDARY, width=22)
        summary.add_column(style=self.theme.TEXT_PRIMARY)
        summary.add_row("Workspace", f"[bold {self.theme.PINK_SOFT}]{escape(str(dashboard.get('workspace_name') or cache_dir.name))}[/bold {self.theme.PINK_SOFT}]")
        summary.add_row("Path", f"[{self.theme.TEXT_DIM}]{escape(str(dashboard.get('workspace_path') or cache_dir))}[/{self.theme.TEXT_DIM}]")
        summary.add_row("CLI Runtime", f"[{self.theme.BLUE_SOFT}]{self._format_duration(dashboard.get('total_runtime_seconds', 0))}[/{self.theme.BLUE_SOFT}]")
        summary.add_row("Active Work", f"[{self.theme.MINT_SOFT}]{self._format_duration(dashboard.get('total_active_seconds', 0))}[/{self.theme.MINT_SOFT}]")
        summary.add_row("Model Calls", f"[{self.theme.PURPLE_SOFT}]{dashboard.get('total_calls', 0):,}[/{self.theme.PURPLE_SOFT}]")
        summary.add_row("Input Tokens", f"[{self.theme.BLUE_SOFT}]{dashboard.get('total_input_tokens', 0):,}[/{self.theme.BLUE_SOFT}]")
        summary.add_row("Output Tokens", f"[{self.theme.PINK_SOFT}]{dashboard.get('total_output_tokens', 0):,}[/{self.theme.PINK_SOFT}]")
        summary.add_row("Sessions", f"[{self.theme.TEXT_SECONDARY}]{len(session_rows)}[/{self.theme.TEXT_SECONDARY}]")
        self.console.print(
            Panel(
                summary,
                title=f"[bold {self.theme.PINK_SOFT}]{self.deco.SPARKLE} Workspace Totals[/bold {self.theme.PINK_SOFT}]",
                border_style=self.theme.BORDER_PRIMARY,
                box=box.ROUNDED,
                padding=(0, 1),
            )
        )

        source_table = Table(
            title=f"[bold {self.theme.MINT_SOFT}]{self.deco.CRYSTAL} Source Usage[/bold {self.theme.MINT_SOFT}]",
            box=box.ROUNDED,
            border_style=self.theme.BORDER_SECONDARY,
            expand=True,
        )
        source_table.add_column("Source", style=f"bold {self.theme.MINT_VIBRANT}", no_wrap=True)
        source_table.add_column("Calls", style=self.theme.TEXT_SECONDARY, justify="right")
        source_table.add_column("Input", style=self.theme.BLUE_SOFT, justify="right")
        source_table.add_column("Output", style=self.theme.PINK_SOFT, justify="right")
        source_table.add_column("Models", style=self.theme.TEXT_DIM, justify="right")
        source_table.add_column("Providers", style=self.theme.TEXT_DIM, justify="right")
        for row in dashboard.get("source_usage", []) or []:
            source_table.add_row(
                str(row.get("source") or "standard"),
                f"{int(row.get('calls', 0)):,}",
                f"{int(row.get('input_tokens', 0)):,}",
                f"{int(row.get('output_tokens', 0)):,}",
                str(int(row.get("model_count", 0))),
                str(int(row.get("provider_count", 0))),
            )
        if not (dashboard.get("source_usage") or []):
            source_table.add_row("No source usage recorded yet", "", "", "", "", "")
        self.console.print(source_table)

        atlas_source_rows = [
            row
            for row in (dashboard.get("source_usage") or [])
            if str(row.get("source") or "").strip().lower() in {"chat", "compression", "handoff"}
        ]
        if atlas_source_rows:
            total_source_calls = sum(int(row.get("calls", 0) or 0) for row in atlas_source_rows) or 1
            atlas_lines = [
                "Atlas Context Cost View",
                "",
            ]
            for row in atlas_source_rows:
                source_name = str(row.get("source") or "unknown").strip().lower()
                call_ratio = (int(row.get("calls", 0) or 0) / total_source_calls) * 100.0
                atlas_lines.append(
                    f"- {source_name}: {int(row.get('calls', 0) or 0):,} calls, "
                    f"{int(row.get('input_tokens', 0) or 0):,} in, {int(row.get('output_tokens', 0) or 0):,} out "
                    f"({call_ratio:.1f}% of tracked Atlas calls)"
                )
            atlas_lines.extend(
                [
                    "",
                    "- `chat` should usually be the main cost: it means the model is spending budget on real delivery work.",
                    "- `compression` is maintenance cost: high values mean Atlas is spending too much effort shrinking context.",
                    "- `handoff` is continuity cost: high values mean session rotation or resume overhead is getting expensive.",
                ]
            )
            self.console.print(
                Panel(
                    Text("\n".join(atlas_lines), style=self.theme.TEXT_SECONDARY),
                    title=f"[bold {self.theme.AMBER_GLOW}]{self.deco.SPARKLE} Atlas Context Cost[/bold {self.theme.AMBER_GLOW}]",
                    border_style=self.theme.BORDER_SECONDARY,
                    box=box.ROUNDED,
                    padding=(0, 1),
                )
            )

        model_table = Table(
            title=f"[bold {self.theme.PURPLE_SOFT}]{self.deco.CRYSTAL} Model Usage[/bold {self.theme.PURPLE_SOFT}]",
            box=box.ROUNDED,
            border_style=self.theme.BORDER_SECONDARY,
            expand=True,
        )
        model_table.add_column("Model", style=f"bold {self.theme.BLUE_SOFT}")
        model_table.add_column("Provider", style=self.theme.TEXT_DIM, no_wrap=True)
        model_table.add_column("Source", style=self.theme.MINT_SOFT, no_wrap=True)
        model_table.add_column("Calls", style=self.theme.TEXT_SECONDARY, justify="right")
        model_table.add_column("Input", style=self.theme.BLUE_SOFT, justify="right")
        model_table.add_column("Output", style=self.theme.PINK_SOFT, justify="right")
        for row in dashboard.get("model_usage", []) or []:
            model_label = str(row.get("model_display_name") or row.get("model") or "unknown")
            provider_label = str(row.get("provider") or "unknown")
            source_label = str(row.get("source") or "standard")
            model_table.add_row(
                model_label,
                provider_label,
                source_label,
                f"{int(row.get('calls', 0)):,}",
                f"{int(row.get('input_tokens', 0)):,}",
                f"{int(row.get('output_tokens', 0)):,}",
            )
        if not (dashboard.get("model_usage") or []):
            model_table.add_row("No model usage recorded yet", "", "", "", "", "")
        self.console.print(model_table)

        sessions_table = Table(
            title=f"[bold {self.theme.BLUE_SOFT}]{self.deco.CRYSTAL} Session Summary[/bold {self.theme.BLUE_SOFT}]",
            box=box.ROUNDED,
            border_style=self.theme.BORDER_SECONDARY,
            expand=True,
        )
        sessions_table.add_column("#", style=self.theme.TEXT_DIM, width=4, justify="right")
        sessions_table.add_column("Session", style=f"bold {self.theme.PINK_SOFT}")
        sessions_table.add_column("Messages", style=self.theme.TEXT_SECONDARY, justify="right")
        sessions_table.add_column("Input", style=self.theme.BLUE_SOFT, justify="right")
        sessions_table.add_column("Output", style=self.theme.PINK_SOFT, justify="right")
        sessions_table.add_column("Updated", style=self.theme.TEXT_DIM, no_wrap=True)
        for index, row in enumerate(session_rows, start=1):
            usage_row = session_usage_map.get(str(row.get("id") or ""))
            sessions_table.add_row(
                str(index),
                str(row.get("name") or row.get("id") or ""),
                str(row.get("message_count", 0)),
                f"{int((usage_row or {}).get('input_tokens', 0)):,}",
                f"{int((usage_row or {}).get('output_tokens', 0)):,}",
                str(row.get("updated_at") or "")[:16].replace("T", " "),
            )
        if not session_rows:
            sessions_table.add_row("", "No sessions recorded", "", "", "", "")
        self.console.print(sessions_table)
        self.console.print()

        if not session_rows:
            return True

        try:
            choice = Prompt.ask(
                f"[{self.theme.PURPLE_SOFT}]Open session #[/{self.theme.PURPLE_SOFT}]",
                default="",
            ).strip()
        except KeyboardInterrupt:
            self.console.print()
            return True

        if not choice:
            return True

        if not choice.isdigit():
            self.console.print(f"[{self.theme.AMBER_GLOW}]{self.deco.DOT_MEDIUM} Enter a session number from the table to inspect its transcript.[/{self.theme.AMBER_GLOW}]")
            return True

        selected_index = int(choice) - 1
        if selected_index < 0 or selected_index >= len(session_rows):
            self.console.print(f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} Invalid session selection.[/{self.theme.CORAL_SOFT}]")
            return True

        session_payload = WorkspaceStatsManager.load_session_payload(cache_dir, str(session_rows[selected_index].get("id") or ""))
        if not session_payload:
            self.console.print(f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} Failed to load the selected session transcript.[/{self.theme.CORAL_SOFT}]")
            return True

        self._show_session_transcript(
            session_payload,
            title=f"Workspace Session {self.deco.DOT_MEDIUM} {session_payload.get('name', session_payload.get('id', 'session'))}",
        )
        return True
    
    def cmd_clear(self, args: str) -> bool:
        """Clear the screen"""
        self.console.clear()
        return True

    def cmd_clean(self, args: str) -> bool:
        """Delete current-workspace cache, memory, and audit logs."""
        raw = args.strip().lower()
        if raw not in ("", "force", "--force"):
            self.console.print(
                f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} Usage: /clean or /clean force[/{self.theme.CORAL_SOFT}]"
            )
            return True

        clean_workspace_state = self.app.get('clean_workspace_state')
        config_manager = self.app.get('config_manager')
        if not callable(clean_workspace_state) or not config_manager:
            self.console.print(
                f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} Workspace clean is not available in the current session.[/{self.theme.CORAL_SOFT}]"
            )
            return True

        workspace_root = getattr(config_manager, 'project_root', None)
        project_data_dir = getattr(config_manager, 'project_data_dir', None)

        if raw not in ("force", "--force"):
            self.console.print()
            self.console.print(
                f"[{self.theme.AMBER_GLOW}]{self.deco.DOT_MEDIUM} This will delete only the current workspace's memories, sessions, caches, checkpoints, and command audit logs.[/{self.theme.AMBER_GLOW}]"
            )
            if workspace_root:
                self.console.print(
                    f"[{self.theme.TEXT_DIM}]Workspace: {escape(str(workspace_root))}[/{self.theme.TEXT_DIM}]"
                )
            if project_data_dir:
                self.console.print(
                    f"[{self.theme.TEXT_DIM}]Project cache: {escape(str(project_data_dir))}[/{self.theme.TEXT_DIM}]"
                )
            self.console.print(
                f"[{self.theme.TEXT_DIM}]Workspace config and rules are preserved.[/{self.theme.TEXT_DIM}]"
            )
            self.console.print()
            confirmed = Confirm.ask(
                f"[{self.theme.CORAL_SOFT}]Run /clean for this workspace?[/{self.theme.CORAL_SOFT}]",
                default=False,
            )
            if not confirmed:
                self.console.print(
                    f"[{self.theme.TEXT_DIM}]{self.deco.DOT_MEDIUM} Workspace clean cancelled.[/{self.theme.TEXT_DIM}]"
                )
                return True

        self.console.print()
        self.console.print(
            f"[{self.theme.PURPLE_SOFT}]{self.deco.SPARKLE} Cleaning current workspace state...[/{self.theme.PURPLE_SOFT}]"
        )

        try:
            result = clean_workspace_state()
        except Exception as exc:
            self.console.print(
                f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} Workspace clean failed: {escape(str(exc))}[/{self.theme.CORAL_SOFT}]"
            )
            return True

        if result.get("success"):
            deleted = result.get("deleted", []) or []
            missing = result.get("missing", []) or []
            session_name = str(result.get("session_name", "") or "").strip()

            self.console.print(
                f"[{self.theme.MINT_VIBRANT}]{self.deco.CHECK_FANCY} Workspace memory cleared.[/{self.theme.MINT_VIBRANT}]"
            )
            if deleted:
                self.console.print(
                    f"[{self.theme.TEXT_SECONDARY}]Deleted {len(deleted)} workspace cache target(s).[/{self.theme.TEXT_SECONDARY}]"
                )
            if missing:
                self.console.print(
                    f"[{self.theme.TEXT_DIM}]Skipped {len(missing)} target(s) that did not exist.[/{self.theme.TEXT_DIM}]"
                )
            if session_name:
                self.console.print(
                    f"[{self.theme.TEXT_DIM}]Started fresh session: {escape(session_name)}[/{self.theme.TEXT_DIM}]"
                )
        else:
            self.console.print(
                f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} Workspace clean failed.[/{self.theme.CORAL_SOFT}]"
            )
            for error in (result.get("errors", []) or [])[:5]:
                self.console.print(
                    f"[{self.theme.TEXT_DIM}] - {escape(str(error))}[/{self.theme.TEXT_DIM}]"
                )

        self.console.print()
        return True
    
    def cmd_index(self, args: str) -> bool:
        """Re-index the codebase with styled output"""
        indexer = self.app.get('indexer')
        ensure_context_engine = self.app.get('ensure_context_engine')
        run_full_index = self.app.get('run_full_index')
        if not indexer and ensure_context_engine:
            ensure_context_engine()
            indexer = self.app.get('indexer')
            run_full_index = self.app.get('run_full_index')
        if not indexer:
            self.console.print(f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} Indexer not available[/{self.theme.CORAL_SOFT}]")
            return True
        
        if callable(run_full_index):
            result = run_full_index()
        else:
            result = indexer.full_index()

        if not result:
            self.console.print(f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} Indexing failed before a result could be produced.[/{self.theme.CORAL_SOFT}]")
            return True

        status_label = "complete" if result.success else "completed with issues"
        self.console.print(f"[{self.theme.MINT_VIBRANT}]{self.deco.CHECK_FANCY} Indexing {status_label}.[/{self.theme.MINT_VIBRANT}]")
        self.console.print(f"  [{self.theme.TEXT_SECONDARY}]{self.deco.DOT_MEDIUM} Files scanned: [{self.theme.BLUE_SOFT}]{result.files_scanned}[/{self.theme.BLUE_SOFT}][/{self.theme.TEXT_SECONDARY}]")
        self.console.print(f"  [{self.theme.TEXT_SECONDARY}]{self.deco.DOT_MEDIUM} Files parsed: [{self.theme.BLUE_SOFT}]{result.files_parsed}[/{self.theme.BLUE_SOFT}][/{self.theme.TEXT_SECONDARY}]")
        self.console.print(f"  [{self.theme.TEXT_SECONDARY}]{self.deco.DOT_MEDIUM} Files skipped: [{self.theme.BLUE_SOFT}]{result.files_skipped}[/{self.theme.BLUE_SOFT}][/{self.theme.TEXT_SECONDARY}]")
        self.console.print(f"  [{self.theme.TEXT_SECONDARY}]{self.deco.DOT_MEDIUM} Files failed: [{self.theme.BLUE_SOFT}]{result.files_failed}[/{self.theme.BLUE_SOFT}][/{self.theme.TEXT_SECONDARY}]")
        self.console.print(f"  [{self.theme.TEXT_SECONDARY}]{self.deco.DOT_MEDIUM} Symbols: [{self.theme.BLUE_SOFT}]{result.symbols_extracted}[/{self.theme.BLUE_SOFT}][/{self.theme.TEXT_SECONDARY}]")
        self.console.print(f"  [{self.theme.TEXT_SECONDARY}]{self.deco.DOT_MEDIUM} Time: [{self.theme.PURPLE_SOFT}]{result.total_time_ms:.0f}ms[/{self.theme.PURPLE_SOFT}][/{self.theme.TEXT_SECONDARY}]")
        
        if result.warnings:
            self.console.print(f"\n[{self.theme.AMBER_GLOW}]{self.deco.DOT_MEDIUM} Warnings ({len(result.warnings)}):[/{self.theme.AMBER_GLOW}]")
            for warning in result.warnings[:5]:
                self.console.print(f"  [{self.theme.TEXT_DIM}]- {warning}[/{self.theme.TEXT_DIM}]")

        if result.errors:
            self.console.print(f"\n[{self.theme.AMBER_GLOW}]{self.deco.DOT_MEDIUM} Errors ({len(result.errors)}):[/{self.theme.AMBER_GLOW}]")
            for err in result.errors[:5]:
                self.console.print(f"  [{self.theme.TEXT_DIM}]- {err}[/{self.theme.TEXT_DIM}]")
        
        return True
    
    def cmd_setting(self, args: str) -> bool:
        """Manage settings through a richer TUI or direct subcommands."""
        raw = args.strip()
        lowered = raw.lower()

        if not raw or lowered in ("ui", "open", "menu"):
            return self._cmd_setting_ui()
        if lowered in ("status", "show"):
            return self._cmd_setting_status()
        if lowered.startswith("rules"):
            rule_args = raw[5:].strip() if len(raw) > 5 else ""
            return self._cmd_setting_rules(rule_args)

        parts = raw.split(maxsplit=1)
        action = parts[0].strip().lower().replace("_", "-")
        value = parts[1].strip() if len(parts) > 1 else ""

        if action == "mode":
            return self._cmd_setting_mode(value)
        if action == "model":
            return self._cmd_setting_model(value)
        if action == "theme":
            return self._cmd_setting_theme(value)
        if action == "auto-index":
            return self._cmd_setting_bool("auto_index", "Auto Index", value)
        if action == "status-line":
            return self._cmd_setting_bool("show_status_line", "Status Line", value)
        if action in ("tool-output", "tool-output-style", "output-style"):
            return self._cmd_setting_tool_output_style(value)
        if action in ("thinking", "thinking-output", "reasoning", "reasoning-output"):
            return self._cmd_setting_thinking_output_style(value)
        if action == "stream":
            return self._cmd_setting_bool("stream_responses", "Stream Responses", value)
        if action in ("timeout", "api-timeout"):
            return self._cmd_setting_int("api_timeout", "API Timeout", value, min_value=10, max_value=3600)
        if action in ("retries", "api-retries"):
            return self._cmd_setting_int("api_max_retries", "API Retries", value, min_value=0, max_value=12)
        if action in ("debug", "debug-logging"):
            return self._cmd_setting_bool("api_enable_debug_logging", "Debug Logging", value)
        if action == "workspace":
            return self._cmd_setting_workspace(value)

        self.console.print(
            f"[{self.theme.AMBER_GLOW}]{self.deco.DOT_MEDIUM} "
            f"Usage: /setting [status|ui|mode|model|theme|auto-index|status-line|tool-output|thinking|stream|timeout|retries|debug|workspace|rules]"
            f"[/{self.theme.AMBER_GLOW}]"
        )
        return True

    def _setting_mode_options(self) -> List[str]:
        """Available runtime modes for `/mode` and `/setting`."""
        return list_modes(include_computer=True)

    def _setting_theme_options(self) -> List[str]:
        """Available theme values stored in config."""
        return ["default", "dark", "light", "ocean"]

    def _setting_tool_output_choices(self) -> List[str]:
        """Available transcript styles for completed tool output."""
        return ["compact", "condensed", "full"]

    def _setting_thinking_output_choices(self) -> List[str]:
        """Available transcript styles for streamed reasoning content."""
        return ["full", "compact", "hidden"]

    def _get_setting_items(self, config, config_manager, rules_manager) -> List[Dict[str, Any]]:
        """Build setting metadata for the interactive settings view."""
        return [
            {
                "name": "Mode",
                "key": "mode",
                "kind": "choice",
                "choices": self._setting_mode_options(),
                "description": "Switch the active Reverie operating mode and prompt strategy.",
                "command": "/setting mode <mode-name>",
            },
            {
                "name": "Active Source",
                "key": "active_model_source",
                "kind": "readonly",
                "description": "Current model source. Use /model or provider-native commands to switch sources.",
                "command": "/status",
            },
            {
                "name": "Standard Model",
                "key": "active_model_index",
                "kind": "choice",
                "choices": list(range(len(config.models))),
                "description": "Active model inside the standard catalog. Selecting here also switches source back to Standard.",
                "command": "/setting model <index> or /model",
            },
            {
                "name": "Theme",
                "key": "theme",
                "kind": "choice",
                "choices": self._setting_theme_options(),
                "description": "Persisted theme preset used by the CLI.",
                "command": "/setting theme <theme>",
            },
            {
                "name": "Auto Index",
                "key": "auto_index",
                "kind": "bool",
                "description": "Automatically index the workspace when cache is cold.",
                "command": "/setting auto-index on|off",
            },
            {
                "name": "Status Line",
                "key": "show_status_line",
                "kind": "bool",
                "description": "Show the live status line before and after responses.",
                "command": "/setting status-line on|off",
            },
            {
                "name": "Tool Output Style",
                "key": "tool_output_style",
                "kind": "choice",
                "choices": self._setting_tool_output_choices(),
                "description": "Choose how completed tool results appear after the live running panel collapses.",
                "command": "/setting tool-output compact|condensed|full",
            },
            {
                "name": "Thinking Output",
                "key": "thinking_output_style",
                "kind": "choice",
                "choices": self._setting_thinking_output_choices(),
                "description": "Choose whether streamed reasoning stays fully visible, compact, or hidden in the transcript.",
                "command": "/setting thinking full|compact|hidden",
            },
            {
                "name": "Stream Responses",
                "key": "stream_responses",
                "kind": "bool",
                "description": "Stream assistant output token-by-token when the provider supports it.",
                "command": "/setting stream on|off",
            },
            {
                "name": "API Timeout",
                "key": "api_timeout",
                "kind": "int",
                "min": 10,
                "max": 3600,
                "step": 10,
                "description": "Default API timeout in seconds for model requests.",
                "command": "/setting timeout <seconds>",
            },
            {
                "name": "API Retries",
                "key": "api_max_retries",
                "kind": "int",
                "min": 0,
                "max": 12,
                "step": 1,
                "description": "Retry count for recoverable API failures.",
                "command": "/setting retries <count>",
            },
            {
                "name": "Debug Logging",
                "key": "api_enable_debug_logging",
                "kind": "bool",
                "description": "Enable verbose API logging for troubleshooting.",
                "command": "/setting debug on|off",
            },
            {
                "name": "Workspace Config",
                "key": "use_workspace_config",
                "kind": "workspace",
                "description": "Choose whether settings are stored in the current workspace or the global Reverie config.",
                "command": "/setting workspace on|off",
            },
            {
                "name": "Rules",
                "key": "rules",
                "kind": "rules",
                "description": "Edit additional instruction rules applied to the active session.",
                "command": "/setting rules",
            },
        ]

    def _setting_display_value(self, item: Dict[str, Any], config, config_manager, rules_manager) -> str:
        """Render a compact value label for a settings item."""
        key = str(item.get("key", "")).strip()
        kind = str(item.get("kind", "")).strip()

        if kind == "readonly" and key == "active_model_source":
            return self._format_model_source_label(str(getattr(config, "active_model_source", "standard")).lower())
        if kind == "workspace":
            enabled = bool(config_manager.is_workspace_mode())
            return f"[{self.theme.MINT_SOFT}]Workspace[/{self.theme.MINT_SOFT}]" if enabled else f"[{self.theme.PURPLE_MEDIUM}]Global[/{self.theme.PURPLE_MEDIUM}]"
        if key == "tool_output_style":
            labels = {
                "compact": f"[{self.theme.MINT_SOFT}]Compact[/{self.theme.MINT_SOFT}]",
                "condensed": f"[{self.theme.BLUE_SOFT}]Condensed[/{self.theme.BLUE_SOFT}]",
                "full": f"[{self.theme.PURPLE_SOFT}]Full[/{self.theme.PURPLE_SOFT}]",
            }
            return labels.get(normalize_tool_output_style(getattr(config, key, "compact")), escape(str(getattr(config, key, "compact"))))
        if key == "thinking_output_style":
            labels = {
                "full": f"[{self.theme.MINT_SOFT}]Full[/{self.theme.MINT_SOFT}]",
                "compact": f"[{self.theme.BLUE_SOFT}]Compact[/{self.theme.BLUE_SOFT}]",
                "hidden": f"[{self.theme.TEXT_DIM}]Hidden[/{self.theme.TEXT_DIM}]",
            }
            return labels.get(normalize_thinking_output_style(getattr(config, key, "full")), escape(str(getattr(config, key, "full"))))
        if kind == "rules":
            if not rules_manager:
                return f"[{self.theme.TEXT_DIM}](rules manager unavailable)[/{self.theme.TEXT_DIM}]"
            rules = [rule.strip() for rule in rules_manager.get_rules() if str(rule).strip()]
            if not rules:
                return f"[{self.theme.TEXT_DIM}](none)[/{self.theme.TEXT_DIM}]"
            preview = rules[0]
            if len(rules) > 1:
                preview += f" +{len(rules) - 1} more"
            return escape(preview[:56] + ("..." if len(preview) > 56 else ""))

        value = getattr(config, key, None)
        if key == "active_model_index":
            if not config.models:
                return f"[{self.theme.TEXT_DIM}](no standard models)[/{self.theme.TEXT_DIM}]"
            if 0 <= int(value) < len(config.models):
                label = escape(config.models[int(value)].model_display_name)
                if str(getattr(config, "active_model_source", "standard")).lower() != "standard":
                    label += f" [{self.theme.TEXT_DIM}](inactive while provider source is external)[/{self.theme.TEXT_DIM}]"
                return label
            return f"[{self.theme.TEXT_DIM}](invalid)[/{self.theme.TEXT_DIM}]"
        if isinstance(value, bool):
            return f"[{self.theme.MINT_SOFT}]ON[/{self.theme.MINT_SOFT}]" if value else f"[{self.theme.TEXT_DIM}]OFF[/{self.theme.TEXT_DIM}]"
        if value is None or value == "":
            return f"[{self.theme.TEXT_DIM}](empty)[/{self.theme.TEXT_DIM}]"
        return escape(str(value))

    def _resolve_setting_active_model_label(self, config) -> str:
        """Resolve a lightweight active-model label without provider credential lookups."""
        source = str(getattr(config, "active_model_source", "standard") or "standard").strip().lower()
        if source == "standard":
            index = int(getattr(config, "active_model_index", 0) or 0)
            if 0 <= index < len(getattr(config, "models", [])):
                return str(config.models[index].model_display_name).strip() or "(unnamed standard model)"
            return "(no standard model)"

        source_label = self._format_model_source_label(source)
        return f"{source_label} provider selection"

    def _build_setting_summary_panel(self, config, config_manager, rules_manager, *, selected_item: Optional[Dict[str, Any]] = None, changed: bool = False, item_count: int = 0) -> Panel:
        """Top summary panel for the settings UI."""
        active_model_name = self._resolve_setting_active_model_label(config)
        source_label = self._format_model_source_label(str(getattr(config, "active_model_source", "standard")).lower())
        storage_label = "Workspace" if config_manager.is_workspace_mode() else "Global"
        focus_label = str((selected_item or {}).get("name", "") or "Mode").strip()
        pending_label = "Unsaved changes" if changed else "Live view"
        pending_style = self.theme.AMBER_GLOW if changed else self.theme.MINT_SOFT

        summary = Table(box=box.SIMPLE, show_header=False, pad_edge=False)
        summary.add_column(style=self.theme.TEXT_DIM, width=14)
        summary.add_column(style=f"bold {self.theme.TEXT_PRIMARY}")
        summary.add_column(style=self.theme.TEXT_DIM, width=14)
        summary.add_column(style=f"bold {self.theme.TEXT_PRIMARY}")
        summary.add_row("Mode", escape(str(config.mode or "reverie")), "Source", source_label)
        summary.add_row("Model", escape(active_model_name), "Storage", storage_label)
        summary.add_row(
            "Streaming",
            "ON" if bool(getattr(config, "stream_responses", True)) else "OFF",
            "Thinking",
            normalize_thinking_output_style(getattr(config, "thinking_output_style", "full")).title(),
        )
        summary.add_row(
            "Tool Output",
            normalize_tool_output_style(getattr(config, "tool_output_style", "compact")).title(),
            "State",
            f"[{pending_style}]{pending_label}[/{pending_style}]",
        )
        summary.add_row("Rules", str(len(rules_manager.get_rules())) if rules_manager else "0", "Status Line", "ON" if bool(getattr(config, "show_status_line", True)) else "OFF")
        summary.add_row("Focus", escape(focus_label), "Scope", "Runtime & persistence")
        if item_count:
            summary.add_row("Items", str(item_count), "Storage", storage_label)

        return Panel(
            summary,
            title=f"[bold {self.theme.PINK_SOFT}]{self.deco.SPARKLE} Reverie Settings {self.deco.SPARKLE}[/bold {self.theme.PINK_SOFT}]",
            subtitle=f"[{self.theme.TEXT_DIM}]Fast controls for runtime behavior, persistence, model routing, and API defaults.[/{self.theme.TEXT_DIM}]",
            border_style=self.theme.BORDER_PRIMARY,
            padding=(0, 2),
            box=box.ROUNDED,
        )

    def _setting_visible_count(self) -> int:
        """Choose a stable visible-row count for the settings browser."""
        width = self._console_width()
        reserve = 18 if width >= 140 else 20 if width >= 110 else 22
        return max(5, min(9, self._console_height() - reserve))

    def _build_setting_list_panel(
        self,
        items: List[Dict[str, Any]],
        selected_idx: int,
        scroll_offset: int,
        max_visible: int,
        config,
        config_manager,
        rules_manager,
    ) -> Panel:
        """Settings list panel for the TUI."""
        table = Table(box=box.SIMPLE, show_header=True, pad_edge=False)
        table.add_column("#", style=self.theme.TEXT_DIM, width=4, justify="right")
        table.add_column("Setting", style=f"bold {self.theme.BLUE_SOFT}", width=24, no_wrap=True)
        table.add_column("Kind", style=self.theme.TEXT_DIM, width=10, no_wrap=True)
        table.add_column("Value", style=self.theme.TEXT_PRIMARY, ratio=1, no_wrap=True)

        end_idx = min(scroll_offset + max_visible, len(items))
        visible_items = items[scroll_offset:end_idx]

        for row_index, item in enumerate(visible_items):
            actual_idx = scroll_offset + row_index
            is_selected = actual_idx == selected_idx
            value_text = self._setting_display_value(item, config, config_manager, rules_manager)
            kind_label = str(item.get("kind", "") or "").strip()
            if is_selected:
                table.add_row(
                    f"[{self.theme.TEXT_DIM}]{actual_idx + 1}[/{self.theme.TEXT_DIM}]",
                    f"[bold {self.theme.PINK_SOFT}]{escape(self._truncate_middle(item['name'], 22))}[/bold {self.theme.PINK_SOFT}]",
                    f"[{self.theme.TEXT_PRIMARY}]{escape(kind_label)}[/{self.theme.TEXT_PRIMARY}]",
                    f"[reverse]{value_text}[/reverse]",
                )
            else:
                table.add_row(
                    str(actual_idx + 1),
                    escape(self._truncate_middle(item["name"], 22)),
                    escape(kind_label),
                    value_text,
                )

        visible_range = (
            f"{scroll_offset + 1}-{end_idx} / {len(items)}"
            if visible_items
            else f"0 / {len(items)}"
        )

        return Panel(
            table,
            title=f"[bold {self.theme.BLUE_SOFT}]{self.deco.DIAMOND} Settings[/bold {self.theme.BLUE_SOFT}]",
            subtitle=f"[{self.theme.TEXT_DIM}]Visible window: {visible_range}  {self.deco.DOT_MEDIUM}  Scroll down to reveal more[/{self.theme.TEXT_DIM}]",
            border_style=self.theme.BORDER_SUBTLE,
            padding=(0, 1),
            box=box.ROUNDED,
        )

    def _build_setting_detail_panel(self, item: Dict[str, Any], config, config_manager, rules_manager) -> Panel:
        """Detailed description panel for the selected setting."""
        kind = str(item.get("kind", "")).strip()
        key = str(item.get("key", "")).strip()
        description = str(item.get("description", "")).strip()
        command = str(item.get("command", "")).strip()

        detail_lines = [
            f"[bold {self.theme.PURPLE_SOFT}]{escape(item['name'])}[/bold {self.theme.PURPLE_SOFT}]",
            f"[{self.theme.TEXT_SECONDARY}]{escape(description)}[/{self.theme.TEXT_SECONDARY}]",
            "",
            f"[{self.theme.TEXT_DIM}]Current[/{self.theme.TEXT_DIM}] {self._setting_display_value(item, config, config_manager, rules_manager)}",
        ]

        if kind == "choice":
            choices = item.get("choices", []) or []
            if key == "active_model_index":
                if config.models:
                    preview = ", ".join(f"{idx + 1}:{model.model_display_name}" for idx, model in enumerate(config.models[:4]))
                    if len(config.models) > 4:
                        preview += ", ..."
                else:
                    preview = "(no standard models configured)"
            else:
                preview = ", ".join(str(choice) for choice in choices)
            detail_lines.append(f"[{self.theme.TEXT_DIM}]Choices[/{self.theme.TEXT_DIM}] {escape(preview)}")
        elif kind == "int":
            detail_lines.append(
                f"[{self.theme.TEXT_DIM}]Range[/{self.theme.TEXT_DIM}] {item.get('min', 0)} - {item.get('max', 0)}"
            )
        elif kind == "workspace":
            workspace_path = getattr(config_manager, "workspace_config_path", "")
            global_path = getattr(config_manager, "global_config_path", "")
            detail_lines.append(f"[{self.theme.TEXT_DIM}]Workspace file[/{self.theme.TEXT_DIM}] {escape(str(workspace_path))}")
            detail_lines.append(f"[{self.theme.TEXT_DIM}]Global file[/{self.theme.TEXT_DIM}] {escape(str(global_path))}")
        elif kind == "rules" and rules_manager:
            rules = [rule.strip() for rule in rules_manager.get_rules() if str(rule).strip()]
            if rules:
                detail_lines.append(f"[{self.theme.TEXT_DIM}]Rules[/{self.theme.TEXT_DIM}]")
                detail_lines.extend(
                    f"[{self.theme.TEXT_SECONDARY}]{self.deco.DOT_MEDIUM} {escape(rule)}[/{self.theme.TEXT_SECONDARY}]"
                    for rule in rules[:3]
                )
                if len(rules) > 3:
                    detail_lines.append(f"[{self.theme.TEXT_DIM}]... and {len(rules) - 3} more[/{self.theme.TEXT_DIM}]")

        detail_lines.extend(
            [
                "",
                f"[{self.theme.TEXT_DIM}]Quick adjust[/{self.theme.TEXT_DIM}] Use h/l or left/right for one-step edits when available.",
                f"[{self.theme.TEXT_DIM}]Precise edit[/{self.theme.TEXT_DIM}] Press Enter for prompts, selectors, or rule editing.",
                f"[{self.theme.TEXT_DIM}]Command equivalent[/{self.theme.TEXT_DIM}] {escape(command)}",
            ]
        )

        return Panel(
            Text.from_markup("\n".join(detail_lines)),
            title=f"[bold {self.theme.PURPLE_SOFT}]{self.deco.DIAMOND} Details[/bold {self.theme.PURPLE_SOFT}]",
            border_style=self.theme.BORDER_SUBTLE,
            padding=(1, 2),
            box=box.ROUNDED,
        )

    def _build_setting_footer_panel(self, *, changed: bool, selected_idx: int, total_items: int) -> Panel:
        """Footer panel with setting TUI controls."""
        footer_grid = Table.grid(expand=True)
        footer_grid.add_column(ratio=1)
        footer_grid.add_column(justify="right", no_wrap=True)
        footer_grid.add_row(
            Text.from_markup(
                f"[{self.theme.TEXT_DIM}]"
                f"{self.deco.DOT_MEDIUM} ↑/↓ or j/k: Navigate  "
                f"{self.deco.DOT_MEDIUM} ←/→ or h/l: Quick change  "
                f"{self.deco.DOT_MEDIUM} Enter: Edit precisely  "
                f"{self.deco.DOT_MEDIUM} One focused page at a time  "
                f"{self.deco.DOT_MEDIUM} Esc: Save & exit"
                f"[/{self.theme.TEXT_DIM}]"
            ),
            Text(
                f"{selected_idx + 1}/{max(1, total_items)} · {'pending save' if changed else 'ready'}",
                style=self.theme.AMBER_GLOW if changed else self.theme.TEXT_DIM,
            ),
        )
        return Panel(
            footer_grid,
            border_style=self.theme.BORDER_SUBTLE,
            padding=(0, 1),
            box=box.ROUNDED,
        )

    def _render_setting_ui(
        self,
        selected_idx: int,
        scroll_offset: int,
        config,
        config_manager,
        rules_manager,
        *,
        changed: bool = False,
    ) -> Group:
        """Compose the full settings TUI renderable."""
        items = self._get_setting_items(config, config_manager, rules_manager)
        selected_item = items[selected_idx]
        max_visible = self._setting_visible_count()
        summary_panel = self._build_setting_summary_panel(
            config,
            config_manager,
            rules_manager,
            selected_item=selected_item,
            changed=changed,
            item_count=len(items),
        )
        list_panel = self._build_setting_list_panel(
            items,
            selected_idx,
            scroll_offset,
            max_visible,
            config,
            config_manager,
            rules_manager,
        )
        detail_panel = self._build_setting_detail_panel(selected_item, config, config_manager, rules_manager)
        footer_panel = self._build_setting_footer_panel(changed=changed, selected_idx=selected_idx, total_items=len(items))
        return Group(summary_panel, list_panel, detail_panel, footer_panel)

    def _setting_parse_bool(self, value: str):
        """Parse common boolean input values."""
        lowered = str(value or "").strip().lower()
        if lowered in ("on", "true", "1", "yes", "enable", "enabled"):
            return True
        if lowered in ("off", "false", "0", "no", "disable", "disabled"):
            return False
        return None

    def _setting_save_and_reinit(self, config, message: str, reinit: bool = True) -> bool:
        """Save config and optionally reinitialize the agent."""
        config_manager = self.app.get('config_manager')
        if not config_manager:
            self.console.print(f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} Config manager not available[/{self.theme.CORAL_SOFT}]")
            return True
        config_manager.save(config)
        if self.app.get('apply_display_preferences'):
            try:
                self.app['apply_display_preferences'](config)
            except Exception:
                pass
        if reinit and self.app.get('reinit_agent'):
            self.app['reinit_agent']()
        self.console.print(f"[{self.theme.MINT_VIBRANT}]{self.deco.CHECK_FANCY} {message}[/{self.theme.MINT_VIBRANT}]")
        return True

    def _cmd_setting_status(self) -> bool:
        """Show a settings dashboard without entering the interactive TUI."""
        config_manager = self.app.get('config_manager')
        if not config_manager:
            self.console.print(f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} Config manager not available[/{self.theme.CORAL_SOFT}]")
            return True

        rules_manager = self.app.get('rules_manager')
        config = config_manager.load()
        self.console.print()
        items = self._get_setting_items(config, config_manager, rules_manager)
        self.console.print(
            self._build_setting_summary_panel(
                config,
                config_manager,
                rules_manager,
                selected_item=items[0] if items else None,
                changed=False,
                item_count=len(items),
            )
        )
        self.console.print()
        self.console.print(
            self._build_setting_list_panel(
                items,
                selected_idx=0,
                scroll_offset=0,
                max_visible=min(len(items), self._setting_visible_count()),
                config=config,
                config_manager=config_manager,
                rules_manager=rules_manager,
            )
        )
        self.console.print()
        self.console.print(
            Panel(
                f"[{self.theme.TEXT_DIM}]Direct edits:[/{self.theme.TEXT_DIM}] "
                f"[bold {self.theme.BLUE_SOFT}]/setting mode writer[/bold {self.theme.BLUE_SOFT}]  "
                f"[bold {self.theme.BLUE_SOFT}]/setting tool-output condensed[/bold {self.theme.BLUE_SOFT}]  "
                f"[bold {self.theme.BLUE_SOFT}]/setting thinking full[/bold {self.theme.BLUE_SOFT}]  "
                f"[bold {self.theme.BLUE_SOFT}]/setting timeout 120[/bold {self.theme.BLUE_SOFT}]  "
                f"[bold {self.theme.BLUE_SOFT}]/setting workspace on[/bold {self.theme.BLUE_SOFT}]",
                border_style=self.theme.BORDER_SUBTLE,
                padding=(0, 2),
                box=box.ROUNDED,
            )
        )
        self.console.print()
        return True

    def _select_standard_model_index(self, model_query: str, prompt_if_missing: bool = False) -> int:
        """Resolve a standard-model selection by index or fuzzy name."""
        config_manager = self.app.get('config_manager')
        if not config_manager:
            return -1

        config = config_manager.load()
        if not config.models:
            return -1

        if not model_query and prompt_if_missing:
            choices_preview = "\n".join(
                f"[{self.theme.TEXT_SECONDARY}]{idx + 1}.[/{self.theme.TEXT_SECONDARY}] {escape(model.model_display_name)}"
                for idx, model in enumerate(config.models)
            )
            self.console.print()
            self.console.print(
                Panel(
                    Text.from_markup(choices_preview),
                    title=f"[bold {self.theme.BLUE_SOFT}]{self.deco.DIAMOND} Standard Models[/bold {self.theme.BLUE_SOFT}]",
                    border_style=self.theme.BORDER_SUBTLE,
                    padding=(0, 2),
                    box=box.ROUNDED,
                )
            )
            model_query = Prompt.ask("Select model number", default=str(config.active_model_index + 1)).strip()

        if not model_query:
            return -1

        if model_query.isdigit():
            idx = int(model_query) - 1
            if 0 <= idx < len(config.models):
                return idx
            return -1

        wanted = model_query.strip().lower()
        exact_match = None
        partial_matches = []
        for idx, model in enumerate(config.models):
            display = str(model.model_display_name).strip().lower()
            model_id = str(model.model).strip().lower()
            if wanted in (display, model_id):
                exact_match = idx
                break
            if wanted in display or wanted in model_id:
                partial_matches.append(idx)
        if exact_match is not None:
            return exact_match
        if len(partial_matches) == 1:
            return partial_matches[0]
        return -1

    def _cmd_setting_mode(self, value: str) -> bool:
        """Change the active mode from `/setting`."""
        config_manager = self.app.get('config_manager')
        if not config_manager:
            self.console.print(f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} Config manager not available[/{self.theme.CORAL_SOFT}]")
            return True
        config = config_manager.load()
        choices = self._setting_mode_options()
        raw_value = str(value or "").strip()
        candidate = normalize_mode(raw_value) if raw_value else ""
        if not candidate:
            candidate = normalize_mode(Prompt.ask("Mode", default=config.mode or "reverie", choices=choices).strip().lower())
        if candidate not in choices:
            self.console.print(f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} Invalid mode: {candidate}[/{self.theme.CORAL_SOFT}]")
            return True
        if not self._apply_mode_selection(config, candidate):
            return True
        return self._setting_save_and_reinit(config, f"Mode set to {candidate}.")

    def _cmd_setting_model(self, value: str) -> bool:
        """Change the active standard model from `/setting`."""
        if not value:
            return self.cmd_model("")
        config_manager = self.app.get('config_manager')
        if not config_manager:
            self.console.print(f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} Config manager not available[/{self.theme.CORAL_SOFT}]")
            return True
        index = self._select_standard_model_index(value, prompt_if_missing=False)
        config = config_manager.load()
        if index < 0 or index >= len(config.models):
            self.console.print(f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} Standard model not found: {escape(value)}[/{self.theme.CORAL_SOFT}]")
            return True
        config.active_model_index = index
        config.active_model_source = "standard"
        selected_name = config.models[index].model_display_name
        return self._setting_save_and_reinit(config, f"Standard model set to {selected_name}.")

    def _cmd_setting_theme(self, value: str) -> bool:
        """Update the stored theme value."""
        config_manager = self.app.get('config_manager')
        if not config_manager:
            self.console.print(f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} Config manager not available[/{self.theme.CORAL_SOFT}]")
            return True
        config = config_manager.load()
        choices = self._setting_theme_options()
        candidate = str(value or "").strip().lower()
        if not candidate:
            candidate = Prompt.ask("Theme", default=config.theme or "default", choices=choices).strip().lower()
        if candidate not in choices:
            self.console.print(f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} Invalid theme: {candidate}[/{self.theme.CORAL_SOFT}]")
            return True
        config.theme = candidate
        return self._setting_save_and_reinit(config, f"Theme set to {candidate}.", reinit=False)

    def _cmd_setting_tool_output_style(self, value: str) -> bool:
        """Update how completed tool output is shown after live execution ends."""
        config_manager = self.app.get('config_manager')
        if not config_manager:
            self.console.print(f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} Config manager not available[/{self.theme.CORAL_SOFT}]")
            return True

        config = config_manager.load()
        choices = self._setting_tool_output_choices()
        raw_candidate = str(value or "").strip().lower()
        candidate = normalize_tool_output_style(raw_candidate, default="") if raw_candidate else ""
        if raw_candidate and not candidate:
            self.console.print(f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} Invalid tool output style: {escape(raw_candidate)}[/{self.theme.CORAL_SOFT}]")
            return True
        if not candidate:
            candidate = normalize_tool_output_style(
                Prompt.ask(
                    "Tool output style",
                    default=normalize_tool_output_style(getattr(config, "tool_output_style", "compact")),
                    choices=choices,
                ).strip().lower()
            )
        if candidate not in choices:
            self.console.print(f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} Invalid tool output style: {escape(candidate)}[/{self.theme.CORAL_SOFT}]")
            return True

        config.tool_output_style = candidate
        return self._setting_save_and_reinit(
            config,
            f"Tool output style set to {candidate}.",
            reinit=False,
        )

    def _cmd_setting_thinking_output_style(self, value: str) -> bool:
        """Update how streamed thinking/reasoning content is rendered."""
        config_manager = self.app.get('config_manager')
        if not config_manager:
            self.console.print(f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} Config manager not available[/{self.theme.CORAL_SOFT}]")
            return True

        config = config_manager.load()
        choices = self._setting_thinking_output_choices()
        raw_candidate = str(value or "").strip().lower()
        candidate = normalize_thinking_output_style(raw_candidate, default="") if raw_candidate else ""
        if raw_candidate and not candidate:
            self.console.print(f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} Invalid thinking output style: {escape(raw_candidate)}[/{self.theme.CORAL_SOFT}]")
            return True
        if not candidate:
            candidate = normalize_thinking_output_style(
                Prompt.ask(
                    "Thinking output style",
                    default=normalize_thinking_output_style(getattr(config, "thinking_output_style", "full")),
                    choices=choices,
                ).strip().lower()
            )
        if candidate not in choices:
            self.console.print(f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} Invalid thinking output style: {escape(candidate)}[/{self.theme.CORAL_SOFT}]")
            return True

        config.thinking_output_style = candidate
        return self._setting_save_and_reinit(
            config,
            f"Thinking output style set to {candidate}.",
            reinit=False,
        )

    def _cmd_setting_bool(self, attr: str, label: str, value: str) -> bool:
        """Toggle or set a boolean config value."""
        config_manager = self.app.get('config_manager')
        if not config_manager:
            self.console.print(f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} Config manager not available[/{self.theme.CORAL_SOFT}]")
            return True
        config = config_manager.load()
        current = bool(getattr(config, attr))
        parsed = self._setting_parse_bool(value)
        if parsed is None:
            parsed = Confirm.ask(f"{label}", default=current)
        setattr(config, attr, parsed)
        return self._setting_save_and_reinit(config, f"{label} set to {'ON' if parsed else 'OFF'}.", reinit=False)

    def _cmd_setting_int(self, attr: str, label: str, value: str, min_value: int, max_value: int) -> bool:
        """Set a numeric config value with validation."""
        config_manager = self.app.get('config_manager')
        if not config_manager:
            self.console.print(f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} Config manager not available[/{self.theme.CORAL_SOFT}]")
            return True
        config = config_manager.load()
        raw = str(value or "").strip()
        if not raw:
            raw = Prompt.ask(label, default=str(getattr(config, attr))).strip()
        try:
            parsed = int(raw)
        except ValueError:
            self.console.print(f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} {label} must be an integer.[/{self.theme.CORAL_SOFT}]")
            return True
        if parsed < min_value or parsed > max_value:
            self.console.print(
                f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} {label} must be between {min_value} and {max_value}.[/{self.theme.CORAL_SOFT}]"
            )
            return True
        setattr(config, attr, parsed)
        return self._setting_save_and_reinit(config, f"{label} set to {parsed}.", reinit=False)

    def _apply_workspace_mode_setting(self, enabled: bool):
        """Apply workspace/global config mode and return success with a user-facing message."""
        config_manager = self.app.get('config_manager')
        if not config_manager:
            return False, "Config manager not available."

        if enabled:
            if config_manager.is_workspace_mode():
                return True, "Workspace mode is already enabled."
            if not config_manager.has_workspace_config():
                if not config_manager.has_global_config():
                    return False, "No configuration found. Configure a model before enabling workspace mode."
                if not config_manager.copy_config_to_workspace():
                    return False, "Failed to copy the global config into the workspace."
            if not config_manager.set_workspace_config_enabled(True):
                return False, "Failed to mark the workspace profile as enabled."
            config_manager.set_workspace_mode(True)
            config = config_manager.load()
            config.use_workspace_config = True
            config_manager.save(config)
            return True, f"Workspace mode enabled. Config path: {config_manager.workspace_config_path}"

        if not config_manager.is_workspace_mode():
            return True, "Workspace mode is already disabled."
        if not config_manager.set_workspace_config_enabled(False):
            return False, "Failed to mark the workspace profile as disabled."
        config_manager.set_workspace_mode(False)
        config = config_manager.load()
        config.use_workspace_config = False
        config_manager.save(config)
        return True, f"Workspace mode disabled. Config path: {config_manager.global_config_path}"

    def _cmd_setting_workspace(self, value: str) -> bool:
        """Toggle workspace config mode from `/setting`."""
        config_manager = self.app.get('config_manager')
        if not config_manager:
            self.console.print(f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} Config manager not available[/{self.theme.CORAL_SOFT}]")
            return True

        parsed = self._setting_parse_bool(value)
        if parsed is None:
            parsed = Confirm.ask("Enable workspace-local config?", default=config_manager.is_workspace_mode())

        success, message = self._apply_workspace_mode_setting(parsed)
        color = self.theme.MINT_VIBRANT if success else self.theme.CORAL_SOFT
        icon = self.deco.CHECK_FANCY if success else self.deco.CROSS
        self.console.print(f"[{color}]{icon} {escape(message)}[/{color}]")
        if success and self.app.get('reinit_agent'):
            self.app['reinit_agent']()
        return True

    def _cmd_setting_rules(self, value: str = "") -> bool:
        """Open or delegate rules editing from `/setting`."""
        if value:
            return self.cmd_rules(value)

        rules_manager = self.app.get('rules_manager')
        if not rules_manager:
            self.console.print(f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} Rules manager not available[/{self.theme.CORAL_SOFT}]")
            return True

        self.console.print()
        self.console.print(
            Panel(
                f"[bold {self.theme.PINK_SOFT}]{self.deco.SPARKLE} Edit Session Rules {self.deco.SPARKLE}[/bold {self.theme.PINK_SOFT}]\n"
                f"[{self.theme.TEXT_SECONDARY}]Enter one rule per line. Submit a blank line to finish. Existing rules will be replaced.[/{self.theme.TEXT_SECONDARY}]",
                border_style=self.theme.BORDER_PRIMARY,
                padding=(1, 2),
                box=box.ROUNDED,
            )
        )

        existing_rules = [rule.strip() for rule in rules_manager.get_rules() if str(rule).strip()]
        if existing_rules:
            self.console.print(f"[{self.theme.TEXT_DIM}]Current rules:[/{self.theme.TEXT_DIM}]")
            for rule in existing_rules:
                self.console.print(f"  [{self.theme.PURPLE_SOFT}]{self.deco.DOT_MEDIUM}[/{self.theme.PURPLE_SOFT}] {escape(rule)}")

        new_rules: List[str] = []
        try:
            while True:
                line = input(f"{self.deco.CHEVRON_RIGHT} ").strip()
                if not line:
                    break
                new_rules.append(line)
        except KeyboardInterrupt:
            self.console.print()
            self.console.print(f"[{self.theme.AMBER_GLOW}]{self.deco.DOT_MEDIUM} Rules edit cancelled.[/{self.theme.AMBER_GLOW}]")
            return True

        rules_manager._rules = new_rules
        rules_manager.save()
        if self.app.get('reinit_agent'):
            self.app['reinit_agent']()
        self.console.print(f"[{self.theme.MINT_VIBRANT}]{self.deco.CHECK_FANCY} Rules updated ({len(new_rules)} total).[/{self.theme.MINT_VIBRANT}]")
        self.console.print()
        return True

    def _setting_step_item(self, item: Dict[str, Any], config, config_manager, rules_manager, direction: int) -> bool:
        """Apply a quick left/right change in the settings TUI."""
        kind = str(item.get("kind", "")).strip()
        key = str(item.get("key", "")).strip()

        if kind in ("readonly", "rules"):
            return False
        if kind == "workspace":
            target = not bool(config_manager.is_workspace_mode())
            success, _ = self._apply_workspace_mode_setting(target)
            return success
        if kind == "bool":
            setattr(config, key, not bool(getattr(config, key)))
            return True
        if kind == "int":
            step = int(item.get("step", 1))
            min_value = int(item.get("min", 0))
            max_value = int(item.get("max", 999999))
            current = int(getattr(config, key))
            current += step * direction
            current = max(min_value, min(max_value, current))
            setattr(config, key, current)
            return True
        if kind == "choice":
            choices = item.get("choices", []) or []
            if not choices:
                return False
            current = getattr(config, key)
            try:
                current_index = choices.index(current)
            except ValueError:
                current_index = 0
            new_index = (current_index + direction) % len(choices)
            new_value = choices[new_index]
            setattr(config, key, new_value)
            if key == "active_model_index":
                config.active_model_source = "standard"
            return True
        return False

    def _setting_edit_item(self, item: Dict[str, Any], config, config_manager, rules_manager) -> bool:
        """Edit the selected setting with a precise prompt."""
        kind = str(item.get("kind", "")).strip()
        key = str(item.get("key", "")).strip()

        if kind == "rules":
            self._cmd_setting_rules("")
            return True
        if kind == "readonly":
            return False
        if kind == "workspace":
            success, _ = self._apply_workspace_mode_setting(not bool(config_manager.is_workspace_mode()))
            return success
        if kind == "bool":
            setattr(config, key, not bool(getattr(config, key)))
            return True
        if kind == "int":
            raw = Prompt.ask(item["name"], default=str(getattr(config, key))).strip()
            try:
                parsed = int(raw)
            except ValueError:
                return False
            min_value = int(item.get("min", 0))
            max_value = int(item.get("max", 999999))
            if parsed < min_value or parsed > max_value:
                return False
            setattr(config, key, parsed)
            return True
        if kind == "choice":
            if key == "active_model_index":
                selected_idx = self._select_standard_model_index("", prompt_if_missing=True)
                if selected_idx < 0:
                    return False
                config.active_model_index = selected_idx
                config.active_model_source = "standard"
                return True
            choices = [str(choice) for choice in (item.get("choices", []) or [])]
            current = str(getattr(config, key) or "")
            picked = Prompt.ask(item["name"], default=current, choices=choices).strip()
            setattr(config, key, picked)
            return True
        return False

    def _cmd_setting_ui(self) -> bool:
        """Launch the richer interactive settings TUI."""
        try:
            import msvcrt
        except ImportError:
            self.console.print(f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} Interactive settings UI is only supported on Windows.[/{self.theme.CORAL_SOFT}]")
            self.console.print(f"[{self.theme.TEXT_DIM}]Use /setting status or /setting <subcommand> instead.[/{self.theme.TEXT_DIM}]")
            return True

        config_manager = self.app.get('config_manager')
        if not config_manager:
            self.console.print(f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} Config manager not available[/{self.theme.CORAL_SOFT}]")
            return True
        rules_manager = self.app.get('rules_manager')
        config = config_manager.load()
        selected_idx = 0
        scroll_offset = 0
        changed = False

        from rich.live import Live

        with Live(
            self._render_setting_ui(selected_idx, scroll_offset, config, config_manager, rules_manager, changed=changed),
            auto_refresh=False,
            screen=True,
            transient=True,
            vertical_overflow="ellipsis",
            console=self.console,
        ) as live:
            last_size = self._console_size()
            while True:
                if msvcrt.kbhit():
                    key = msvcrt.getch()
                    items = self._get_setting_items(config, config_manager, rules_manager)
                    selected_item = items[selected_idx]
                    should_reload_config = False

                    if key == b"\x1b":
                        break
                    if key in (b"k", b"K"):
                        selected_idx = (selected_idx - 1) % len(items)
                    elif key in (b"j", b"J"):
                        selected_idx = (selected_idx + 1) % len(items)
                    elif key in (b"h", b"H", b"a", b"A"):
                        changed = self._setting_step_item(selected_item, config, config_manager, rules_manager, -1) or changed
                        should_reload_config = str(selected_item.get("kind", "")).strip() == "workspace"
                    elif key in (b"l", b"L", b"d", b"D", b" "):
                        changed = self._setting_step_item(selected_item, config, config_manager, rules_manager, 1) or changed
                        should_reload_config = str(selected_item.get("kind", "")).strip() == "workspace"
                    elif key == b"\r":
                        live.stop()
                        changed = self._setting_edit_item(selected_item, config, config_manager, rules_manager) or changed
                        kind = str(selected_item.get("kind", "")).strip()
                        should_reload_config = kind == "workspace"
                        if kind == "rules":
                            should_reload_config = False
                        if should_reload_config:
                            config = config_manager.load()
                        live.start()
                    elif key in (b"\x00", b"\xe0"):
                        key = msvcrt.getch()
                        if key == b"H":
                            selected_idx = (selected_idx - 1) % len(items)
                        elif key == b"P":
                            selected_idx = (selected_idx + 1) % len(items)
                        elif key == b"K":
                            changed = self._setting_step_item(selected_item, config, config_manager, rules_manager, -1) or changed
                            should_reload_config = str(selected_item.get("kind", "")).strip() == "workspace"
                        elif key == b"M":
                            changed = self._setting_step_item(selected_item, config, config_manager, rules_manager, 1) or changed
                            should_reload_config = str(selected_item.get("kind", "")).strip() == "workspace"

                    if should_reload_config:
                        config = config_manager.load()
                    scroll_offset = self._clamp_help_browser_scroll(
                        selected_idx,
                        scroll_offset,
                        len(items),
                        self._setting_visible_count(),
                    )
                    live.update(
                        self._render_setting_ui(selected_idx, scroll_offset, config, config_manager, rules_manager, changed=changed),
                        refresh=True,
                    )
                current_size = self._console_size()
                if current_size != last_size:
                    last_size = current_size
                    items = self._get_setting_items(config, config_manager, rules_manager)
                    scroll_offset = self._clamp_help_browser_scroll(
                        selected_idx,
                        scroll_offset,
                        len(items),
                        self._setting_visible_count(),
                    )
                    live.update(
                        self._render_setting_ui(selected_idx, scroll_offset, config, config_manager, rules_manager, changed=changed),
                        refresh=True,
                    )
                time.sleep(0.025)

        if changed:
            config_manager.save(config)
        if changed and self.app.get('reinit_agent'):
            self.app['reinit_agent']()

        self.console.print()
        self.console.print(
            f"[{self.theme.MINT_VIBRANT}]{self.deco.CHECK_FANCY} Settings {'updated and applied' if changed else 'reviewed'}.[/{self.theme.MINT_VIBRANT}]"
        )
        self.console.print()
        return True
    
    def cmd_rules(self, args: str) -> bool:
        """Manage custom rules with dreamy styling"""
        rules_manager = self.app.get('rules_manager')
        if not rules_manager:
            self.console.print(f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} Rules manager not available[/{self.theme.CORAL_SOFT}]")
            return True
            
        args = args.strip()
        parts = args.split(maxsplit=1)
        action = parts[0].lower() if parts else "list"
        
        if action == "list":
            rules = rules_manager.get_rules()
            if not rules:
                self.console.print(f"[{self.theme.TEXT_DIM}]{self.deco.DOT_MEDIUM} No custom rules defined.[/{self.theme.TEXT_DIM}]")
            else:
                table = Table(
                    title=f"[bold {self.theme.PINK_SOFT}]{self.deco.CRYSTAL} Custom Rules[/bold {self.theme.PINK_SOFT}]",
                    box=box.ROUNDED,
                    border_style=self.theme.BORDER_PRIMARY
                )
                table.add_column("#", style=self.theme.TEXT_DIM, width=4)
                table.add_column("Rule", style=self.theme.TEXT_SECONDARY)
                
                for i, rule in enumerate(rules, 1):
                    table.add_row(str(i), rule)
                
                self.console.print(table)
                self.console.print(f"[{self.theme.TEXT_DIM}]{self.deco.DOT_MEDIUM} Use '/rules edit' to edit rules.txt directly.[/{self.theme.TEXT_DIM}]")
                
        elif action == "edit":
            # Open rules.txt in default editor
            import subprocess
            import os
            
            rules_path = rules_manager.rules_txt_path
            
            # Ensure the file exists
            if not rules_path.exists():
                rules_path.parent.mkdir(parents=True, exist_ok=True)
                rules_path.write_text("", encoding='utf-8')
            
            self.console.print(f"[bold {self.theme.PINK_SOFT}]{self.deco.SPARKLE} Opening rules.txt...[/bold {self.theme.PINK_SOFT}]")
            self.console.print(f"[{self.theme.TEXT_DIM}]Path: {rules_path}[/{self.theme.TEXT_DIM}]")
            self.console.print(f"[{self.theme.TEXT_DIM}]Edit the file and save your changes. Each line is a separate rule.[/{self.theme.TEXT_DIM}]")
            self.console.print(f"[{self.theme.TEXT_DIM}]Press Enter when done editing to apply changes...[/{self.theme.TEXT_DIM}]")
            
            # Open with default text editor
            try:
                if os.name == 'nt':  # Windows
                    os.startfile(str(rules_path))
                elif os.name == 'posix':  # macOS/Linux
                    if os.uname().sysname == 'Darwin':  # macOS
                        subprocess.run(['open', str(rules_path)])
                    else:  # Linux
                        subprocess.run(['xdg-open', str(rules_path)])
                
                # Wait for user to finish editing
                Prompt.ask(f"[{self.theme.BLUE_SOFT}]{self.deco.CHEVRON_RIGHT}[/{self.theme.BLUE_SOFT}] Press Enter when done")
                
                # Reload rules
                rules_manager._load()
                rules = rules_manager.get_rules()
                self.console.print(f"[{self.theme.MINT_VIBRANT}]{self.deco.CHECK_FANCY} Rules reloaded. {len(rules)} rule(s) loaded.[/{self.theme.MINT_VIBRANT}]")
                
                # Reinit agent to apply changes
                if self.app.get('reinit_agent'):
                    self.app['reinit_agent']()
                    
            except Exception as e:
                self.console.print(f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} Failed to open editor: {str(e)}[/{self.theme.CORAL_SOFT}]")
                
        elif action == "add":
            if len(parts) < 2:
                # Interactive add
                self.console.print(f"[bold {self.theme.PINK_SOFT}]{self.deco.SPARKLE} Add New Rule[/bold {self.theme.PINK_SOFT}]")
                self.console.print(f"[{self.theme.TEXT_DIM}]Enter the rule text below (single line):[/{self.theme.TEXT_DIM}]")
                rule_text = Prompt.ask(f"[{self.theme.BLUE_SOFT}]{self.deco.CHEVRON_RIGHT}[/{self.theme.BLUE_SOFT}]")
            else:
                rule_text = parts[1]
                
            if rule_text.strip():
                rules_manager.add_rule(rule_text.strip())
                self.console.print(f"[{self.theme.MINT_VIBRANT}]{self.deco.CHECK_FANCY} Rule added.[/{self.theme.MINT_VIBRANT}]")
                # Reinit agent to apply changes
                if self.app.get('reinit_agent'):
                    self.app['reinit_agent']()
            else:
                self.console.print(f"[{self.theme.AMBER_GLOW}]{self.deco.DOT_MEDIUM} Empty rule text.[/{self.theme.AMBER_GLOW}]")
                
        elif action == "remove" or action == "delete":
            if len(parts) < 2:
                self.console.print(f"[{self.theme.AMBER_GLOW}]{self.deco.DOT_MEDIUM} Usage: /rules remove <number>[/{self.theme.AMBER_GLOW}]")
                return True
                
            try:
                idx = int(parts[1]) - 1
                rules = rules_manager.get_rules()
                if 0 <= idx < len(rules):
                    if Confirm.ask(f"Remove rule: '{rules[idx]}'?"):
                        rules_manager.remove_rule(idx)
                        self.console.print(f"[{self.theme.MINT_VIBRANT}]{self.deco.CHECK_FANCY} Rule removed.[/{self.theme.MINT_VIBRANT}]")
                        # Reinit agent to apply changes
                        if self.app.get('reinit_agent'):
                            self.app['reinit_agent']()
                else:
                    self.console.print(f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} Invalid rule number.[/{self.theme.CORAL_SOFT}]")
            except ValueError:
                self.console.print(f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} Invalid index format.[/{self.theme.CORAL_SOFT}]")
                
        else:
            self.console.print(f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} Unknown action: {action}[/{self.theme.CORAL_SOFT}]")
            self.console.print(f"[{self.theme.TEXT_DIM}]Usage: /rules [list|edit|add|remove][/{self.theme.TEXT_DIM}]")
            
        return True
    
    def cmd_rollback(self, args: str) -> bool:
        """Rollback to a previous state"""
        rollback_manager = self.app.get('rollback_manager')
        operation_history = self.app.get('operation_history')
        
        if not rollback_manager or not operation_history:
            self.console.print(f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} Rollback manager not available.[/{self.theme.CORAL_SOFT}]")
            return True
        
        parts = args.strip().split()
        
        if not parts:
            # Use interactive UI
            from .rollback_ui import RollbackUI
            rollback_ui = RollbackUI(self.console, rollback_manager, operation_history)
            
            action = rollback_ui.show_main_menu()
            
            if action is None:
                return True
            
            session_id = self.app.get('session_manager').current_session.id if self.app.get('session_manager') and self.app['session_manager'].current_session else "default"
            
            if action == rollback_ui.RollbackAction.ROLLBACK_TO_QUESTION:
                result = rollback_manager.rollback_to_previous_question(session_id)
                rollback_ui.show_rollback_summary(result)
                
                # Update agent messages if available
                if result.success and result.restored_messages and self.app.get('agent'):
                    self.app['agent'].messages = result.restored_messages
            
            elif action == rollback_ui.RollbackAction.ROLLBACK_TO_TOOL:
                result = rollback_manager.rollback_to_previous_tool_call(session_id)
                rollback_ui.show_rollback_summary(result)
            
            elif action == rollback_ui.RollbackAction.ROLLBACK_TO_CHECKPOINT:
                checkpoint_id = rollback_ui.show_checkpoint_selector()
                if checkpoint_id:
                    result = rollback_manager.rollback_to_checkpoint(checkpoint_id)
                    rollback_ui.show_rollback_summary(result)
                    
                    # Update agent messages if available
                    if result.success and result.restored_messages and self.app.get('agent'):
                        self.app['agent'].messages = result.restored_messages
            
            elif action == rollback_ui.RollbackAction.UNDO:
                result = rollback_manager.undo()
                rollback_ui.show_rollback_summary(result)
            
            elif action == rollback_ui.RollbackAction.REDO:
                result = rollback_manager.redo()
                rollback_ui.show_rollback_summary(result)
            
        elif parts[0] == 'question':
            # Rollback to previous question
            session_id = self.app.get('session_manager').current_session.id if self.app.get('session_manager') and self.app['session_manager'].current_session else "default"
            result = rollback_manager.rollback_to_previous_question(session_id)
            
            if result.success:
                self.console.print()
                self.console.print(f"[{self.theme.MINT_VIBRANT}]{self.deco.CHECK_FANCY} {result.message}[/{self.theme.MINT_VIBRANT}]")
                
                if result.restored_files:
                    self.console.print(f"[{self.theme.TEXT_DIM}]Restored files:[/{self.theme.TEXT_DIM}]")
                    for file_path in result.restored_files:
                        self.console.print(f"  [{self.theme.MINT_SOFT}]✓[/{self.theme.MINT_SOFT}] {file_path}")
                
                if result.errors:
                    self.console.print()
                    self.console.print(f"[{self.theme.AMBER_GLOW}]{self.deco.DOT_MEDIUM} Errors:[/{self.theme.AMBER_GLOW}]")
                    for error in result.errors:
                        self.console.print(f"  [{self.theme.CORAL_SOFT}]✗[/{self.theme.CORAL_SOFT}] {error}")
                
                # Update agent messages if available
                if result.restored_messages and self.app.get('agent'):
                    self.app['agent'].messages = result.restored_messages
            else:
                self.console.print(f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} {result.message}[/{self.theme.CORAL_SOFT}]")
        
        elif parts[0] == 'tool':
            # Rollback to previous tool call
            session_id = self.app.get('session_manager').current_session.id if self.app.get('session_manager') and self.app['session_manager'].current_session else "default"
            result = rollback_manager.rollback_to_previous_tool_call(session_id)
            
            if result.success:
                self.console.print()
                self.console.print(f"[{self.theme.MINT_VIBRANT}]{self.deco.CHECK_FANCY} {result.message}[/{self.theme.MINT_VIBRANT}]")
                
                if result.restored_files:
                    self.console.print(f"[{self.theme.TEXT_DIM}]Restored files:[/{self.theme.TEXT_DIM}]")
                    for file_path in result.restored_files:
                        self.console.print(f"  [{self.theme.MINT_SOFT}]✓[/{self.theme.MINT_SOFT}] {file_path}")
                
                if result.errors:
                    self.console.print()
                    self.console.print(f"[{self.theme.AMBER_GLOW}]{self.deco.DOT_MEDIUM} Errors:[/{self.theme.AMBER_GLOW}]")
                    for error in result.errors:
                        self.console.print(f"  [{self.theme.CORAL_SOFT}]✗[/{self.theme.CORAL_SOFT}] {error}")
            else:
                self.console.print(f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} {result.message}[/{self.theme.CORAL_SOFT}]")
        
        else:
            # Rollback to specific checkpoint
            checkpoint_id = parts[0]
            result = rollback_manager.rollback_to_checkpoint(checkpoint_id)
            
            if result.success:
                self.console.print()
                self.console.print(f"[{self.theme.MINT_VIBRANT}]{self.deco.CHECK_FANCY} {result.message}[/{self.theme.MINT_VIBRANT}]")
                
                if result.restored_files:
                    self.console.print(f"[{self.theme.TEXT_DIM}]Restored files:[/{self.theme.TEXT_DIM}]")
                    for file_path in result.restored_files:
                        self.console.print(f"  [{self.theme.MINT_SOFT}]✓[/{self.theme.MINT_SOFT}] {file_path}")
                
                if result.errors:
                    self.console.print()
                    self.console.print(f"[{self.theme.AMBER_GLOW}]{self.deco.DOT_MEDIUM} Errors:[/{self.theme.AMBER_GLOW}]")
                    for error in result.errors:
                        self.console.print(f"  [{self.theme.CORAL_SOFT}]✗[/{self.theme.CORAL_SOFT}] {error}")
                
                # Update agent messages if available
                if result.restored_messages and self.app.get('agent'):
                    self.app['agent'].messages = result.restored_messages
            else:
                self.console.print(f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} {result.message}[/{self.theme.CORAL_SOFT}]")
        
        return True
    
    def cmd_undo(self, args: str) -> bool:
        """Undo the last rollback operation"""
        rollback_manager = self.app.get('rollback_manager')
        if not rollback_manager:
            self.console.print(f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} Rollback manager not available.[/{self.theme.CORAL_SOFT}]")
            return True
        
        if not rollback_manager.can_undo():
            self.console.print(f"[{self.theme.TEXT_DIM}]Nothing to undo.[/{self.theme.TEXT_DIM}]")
            return True
        
        result = rollback_manager.undo()
        
        if result.success:
            self.console.print(f"[{self.theme.MINT_VIBRANT}]{self.deco.CHECK_FANCY} {result.message}[/{self.theme.MINT_VIBRANT}]")
        else:
            self.console.print(f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} {result.message}[/{self.theme.CORAL_SOFT}]")
        
        return True
    
    def cmd_redo(self, args: str) -> bool:
        """Redo the last undone rollback operation"""
        rollback_manager = self.app.get('rollback_manager')
        if not rollback_manager:
            self.console.print(f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} Rollback manager not available.[/{self.theme.CORAL_SOFT}]")
            return True
        
        if not rollback_manager.can_redo():
            self.console.print(f"[{self.theme.TEXT_DIM}]Nothing to redo.[/{self.theme.TEXT_DIM}]")
            return True
        
        result = rollback_manager.redo()
        
        if result.success:
            self.console.print(f"[{self.theme.MINT_VIBRANT}]{self.deco.CHECK_FANCY} {result.message}[/{self.theme.MINT_VIBRANT}]")
        else:
            self.console.print(f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} {result.message}[/{self.theme.CORAL_SOFT}]")
        
        return True
    
    def cmd_checkpoints(self, args: str) -> bool:
        """List and manage checkpoints with interactive selection"""
        rollback_manager = self.app.get('rollback_manager')
        if not rollback_manager:
            self.console.print(f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} Rollback manager not available.[/{self.theme.CORAL_SOFT}]")
            return True
        
        # Get checkpoints
        checkpoints = rollback_manager.checkpoint_manager.list_checkpoints()
        
        if not checkpoints:
            self.console.print()
            self.console.print(f"[{self.theme.TEXT_DIM}]No checkpoints available.[/{self.theme.TEXT_DIM}]")
            return True
        
        # Prepare checkpoint data for selector
        checkpoints_data = []
        for cp in checkpoints:
            created_at = cp.created_at[:19].replace('T', ' ')
            description = f"{cp.description} • {cp.message_count} messages"
            
            checkpoints_data.append({
                'id': cp.id,
                'description': cp.description,
                'created_at': created_at,
                'message_count': cp.message_count,
                'checkpoint': cp
            })
        
        # Use TUI selector for checkpoint selection
        from .tui_selector import CheckpointSelector, SelectorAction
        
        # Create and run selector
        selector = CheckpointSelector(
            console=self.console,
            checkpoints=checkpoints_data
        )
        
        result = selector.run()
        
        if result.action == SelectorAction.SELECT and result.selected_item:
            checkpoint_id = result.selected_item.id
            
            # Rollback to selected checkpoint
            session_id = self.app.get('session_manager').current_session.id if self.app.get('session_manager') and self.app['session_manager'].current_session else "default"
            rollback_result = rollback_manager.rollback_to_checkpoint(checkpoint_id)
            
            if rollback_result.success:
                self.console.print()
                self.console.print(f"[{self.theme.MINT_VIBRANT}]{self.deco.CHECK_FANCY} {rollback_result.message}[/{self.theme.MINT_VIBRANT}]")
                
                if rollback_result.restored_files:
                    self.console.print(f"[{self.theme.TEXT_DIM}]Restored files:[/{self.theme.TEXT_DIM}]")
                    for file_path in rollback_result.restored_files:
                        self.console.print(f"  [{self.theme.MINT_SOFT}]✓[/{self.theme.MINT_SOFT}] {file_path}")
                
                if rollback_result.errors:
                    self.console.print()
                    self.console.print(f"[{self.theme.AMBER_GLOW}]{self.deco.DOT_MEDIUM} Errors:[/{self.theme.AMBER_GLOW}]")
                    for error in rollback_result.errors:
                        self.console.print(f"  [{self.theme.CORAL_SOFT}]✗[/{self.theme.CORAL_SOFT}] {error}")
                
                # Update agent messages if available
                if rollback_result.restored_messages and self.app.get('agent'):
                    self.app['agent'].messages = rollback_result.restored_messages
            else:
                self.console.print(f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} {rollback_result.message}[/{self.theme.CORAL_SOFT}]")
        
        return True
    
    def cmd_operations(self, args: str) -> bool:
        """Show operation history and statistics"""
        operation_history = self.app.get('operation_history')
        rollback_manager = self.app.get('rollback_manager')
        
        if not operation_history:
            self.console.print(f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} Operation history not available.[/{self.theme.CORAL_SOFT}]")
            return True
        
        self.console.print()
        title_panel = Panel(
            f"[bold {self.theme.PINK_SOFT}]{self.deco.SPARKLE} Operation History {self.deco.SPARKLE}[/bold {self.theme.PINK_SOFT}]",
            border_style=self.theme.BORDER_PRIMARY,
            padding=(0, 2),
            box=box.ROUNDED
        )
        self.console.print(title_panel)
        self.console.print()
        
        # Show summary
        if rollback_manager:
            summary = rollback_manager.get_operation_summary()
            
            self.console.print(f"[bold {self.theme.PURPLE_SOFT}]Summary:[/bold {self.theme.PURPLE_SOFT}]")
            self.console.print(f"  [{self.theme.TEXT_DIM}]Total Operations:[/{self.theme.TEXT_DIM}] {summary['total_operations']}")
            self.console.print(f"  [{self.theme.TEXT_DIM}]Modified Files:[/{self.theme.TEXT_DIM}] {len(summary['modified_files'])}")
            self.console.print(f"  [{self.theme.TEXT_DIM}]Can Undo:[/{self.theme.TEXT_DIM}] {summary['can_undo']}")
            self.console.print(f"  [{self.theme.TEXT_DIM}]Can Redo:[/{self.theme.TEXT_DIM}] {summary['can_redo']}")
            self.console.print()
        
        # Show recent operations
        recent_ops = operation_history.get_operations(limit=20)
        
        if not recent_ops:
            self.console.print(f"[{self.theme.TEXT_DIM}]No operations recorded yet.[/{self.theme.TEXT_DIM}]")
            return True
        
        table = Table(
            box=box.ROUNDED,
            border_style=self.theme.BORDER_PRIMARY,
            show_lines=True
        )
        table.add_column("#", style=f"bold {self.theme.BLUE_SOFT}", width=4)
        table.add_column("Type", style=self.theme.TEXT_SECONDARY, width=12)
        table.add_column("Description", style=self.theme.TEXT_PRIMARY)
        table.add_column("Time", style=f"dim {self.theme.TEXT_DIM}", width=20)
        
        for i, op in enumerate(recent_ops, 1):
            table.add_row(
                str(i),
                op.operation_type.value,
                op.description[:60],
                op.timestamp[:19].replace('T', ' ')
            )
        
        self.console.print(table)
        self.console.print()
        self.console.print(f"[{self.theme.TEXT_DIM}]Showing last 20 operations.[/{self.theme.TEXT_DIM}]")
        
        return True

    def cmd_workspace(self, args: str) -> bool:
        """Manage workspace configuration mode for multi-workspace support"""
        config_manager = self.app.get('config_manager')
        if not config_manager:
            self._show_activity_event("Workspace", "Config manager not available.", status="error")
            return True

        args = args.strip().lower()

        # Show current status
        if not args or args == 'status':
            is_workspace = config_manager.is_workspace_mode()
            has_workspace = config_manager.has_workspace_config()
            has_global = config_manager.has_global_config()

            self._show_command_panel(
                "Workspace Configuration",
                subtitle="Choose whether this project uses its own local config or the shared global config.",
                accent=self.theme.BORDER_PRIMARY,
            )

            mode_text = "Workspace Mode" if is_workspace else "Global Mode"
            table = self._build_key_value_table(
                [
                    ("Current Mode", mode_text),
                    ("Workspace Config", "Exists" if has_workspace else "Not Found"),
                    ("Global Config", "Exists" if has_global else "Not Found"),
                ],
                value_style=self.theme.MINT_SOFT,
            )
            self.console.print(table)
            self.console.print()
            self.console.print(
                self._build_command_table(
                    [
                        ("/workspace enable", "Enable workspace-local configuration"),
                        ("/workspace disable", "Disable workspace-local configuration and use global"),
                        ("/workspace copy-to-workspace", "Copy the global config into this workspace"),
                        ("/workspace copy-to-global", "Copy the workspace config back to global"),
                    ],
                    title="Workspace Actions",
                    accent=self.theme.BORDER_SECONDARY,
                )
            )
            self.console.print()
            
            return True

        # Enable workspace mode
        elif args == 'enable':
            if config_manager.is_workspace_mode():
                self._show_activity_event("Workspace", "Workspace mode is already enabled.", status="warning")
                return True

            # Check if workspace config exists
            if not config_manager.has_workspace_config():
                if not config_manager.has_global_config():
                    self._show_activity_event(
                        "Workspace",
                        "No configuration found yet.",
                        status="error",
                        detail="Configure a model first before enabling workspace mode.",
                    )
                    return True

                self._show_activity_event(
                    "Workspace",
                    "Workspace config not found.",
                    status="working",
                    detail="Copying the global config into this workspace now.",
                )
                if not config_manager.copy_config_to_workspace():
                    self._show_activity_event(
                        "Workspace",
                        "Failed to copy config into the workspace.",
                        status="error",
                    )
                    return True
            if not config_manager.set_workspace_config_enabled(True):
                self._show_activity_event(
                    "Workspace",
                    "Failed to mark the workspace profile as enabled.",
                    status="error",
                )
                return True

            config_manager.set_workspace_mode(True)
            config = config_manager.load()
            config.use_workspace_config = True
            config_manager.save(config)

            self._show_activity_event(
                "Workspace",
                "Workspace mode enabled.",
                status="success",
                detail="Configuration changes now stay with this project.",
                meta=str(config_manager.workspace_config_path),
            )

            # Reinit agent if needed
            if self.app.get('reinit_agent'):
                self.app['reinit_agent']()

            return True

        # Disable workspace mode
        elif args == 'disable':
            if not config_manager.is_workspace_mode():
                self._show_activity_event("Workspace", "Workspace mode is already disabled.", status="warning")
                return True

            if not config_manager.set_workspace_config_enabled(False):
                self._show_activity_event(
                    "Workspace",
                    "Failed to mark the workspace profile as disabled.",
                    status="error",
                )
                return True

            config_manager.set_workspace_mode(False)
            config = config_manager.load()
            config.use_workspace_config = False
            config_manager.save(config)

            self._show_activity_event(
                "Workspace",
                "Workspace mode disabled.",
                status="success",
                detail="Configuration changes now go to the shared global profile.",
                meta=str(config_manager.global_config_path),
            )

            # Reinit agent if needed
            if self.app.get('reinit_agent'):
                self.app['reinit_agent']()

            return True

        # Copy global config to workspace
        elif args == 'copy-to-workspace':
            if not config_manager.has_global_config():
                self._show_activity_event("Workspace", "No global configuration found.", status="error")
                return True

            if config_manager.copy_config_to_workspace():
                self._show_activity_event(
                    "Workspace",
                    "Copied the global configuration into this workspace.",
                    status="success",
                    meta=str(config_manager.workspace_config_path),
                )
            else:
                self._show_activity_event(
                    "Workspace",
                    "Failed to copy the configuration into the workspace.",
                    status="error",
                )

            return True

        # Copy workspace config to global
        elif args == 'copy-to-global':
            if not config_manager.has_workspace_config():
                self._show_activity_event("Workspace", "No workspace configuration found.", status="error")
                return True

            if config_manager.copy_config_to_global():
                self._show_activity_event(
                    "Workspace",
                    "Copied the workspace configuration back to global.",
                    status="success",
                    meta=str(config_manager.global_config_path),
                )
            else:
                self._show_activity_event(
                    "Workspace",
                    "Failed to copy the workspace configuration to global.",
                    status="error",
                )

            return True

        else:
            self._show_activity_event(
                "Workspace",
                f"Unknown workspace command: {args}",
                status="error",
                detail="Type /workspace for available commands.",
            )
            return True

    def cmd_exit(self, args: str) -> bool:
        """Exit the application with styled prompt"""
        if Confirm.ask(f"[{self.theme.PURPLE_SOFT}]Exit Reverie?[/{self.theme.PURPLE_SOFT}]", default=True):
            return False
        return True

    def cmd_context_engine(self, args: str) -> bool:
        """
        Context Engine management command (/CE)
        
        Usage:
            /CE              - Show Context Engine status and available actions
            /CE compress     - Compress current conversation context
            /CE info         - Show detailed context information
            /CE stats        - Show context statistics
        """
        agent = self.app.get('agent')
        indexer = self.app.get('indexer')
        config_manager = self.app.get('config_manager')

        if not agent:
            self._show_activity_event("Context Engine", "No active agent session.", status="error")
            return True

        args = args.strip().lower()

        # No args - show status and help
        if not args:
            self._show_command_panel(
                "Context Engine",
                subtitle="Inspect context pressure, compression options, and recovery state.",
                accent=self.theme.BORDER_PRIMARY,
            )

            # Get token count
            try:
                usage = self._get_context_usage_snapshot(agent, config_manager)

                if usage:
                    total_tokens = usage.get('total_tokens', 0)
                    max_tokens = usage.get('max_tokens', 128000)
                    percentage = usage.get('percentage', 0)
                    system_tokens = usage.get('system_tokens', 0)
                    messages_tokens = usage.get('messages_tokens', 0)
                    message_count = usage.get('message_count', 0)

                    if percentage >= 80:
                        usage_label = "High"
                    elif percentage >= 60:
                        usage_label = "Moderate"
                    else:
                        usage_label = "Good"

                    table = self._build_key_value_table(
                        [
                            ("System Prompt", f"{system_tokens:,} tokens"),
                            ("Messages", f"{messages_tokens:,} tokens ({message_count} messages)"),
                            ("Total Usage", f"{total_tokens:,} / {max_tokens:,} tokens"),
                            ("Usage", f"{percentage:.1f}% ({usage_label})"),
                        ]
                    )
                    self.console.print(table)
                    self.console.print()

                    if percentage >= 80:
                        self._show_activity_event(
                            "Context Engine",
                            "Context usage is high.",
                            status="warning",
                            detail="Automatic rotation may trigger on the next model call.",
                        )
                    elif percentage >= 60:
                        self._show_activity_event(
                            "Context Engine",
                            "Context usage is moderate.",
                            status="info",
                            detail="A compression or handoff may be needed soon.",
                        )

            except Exception as e:
                self._show_activity_event(
                    "Context Engine",
                    "Failed to inspect current token usage.",
                    status="error",
                    detail=str(e),
                )

            if indexer:
                try:
                    index_status = indexer.get_index_status()
                    status_label = str(index_status.get("display_label") or "").strip() or "idle"
                    status_rows = [
                        ("Index Status", status_label),
                        ("Indexed Files", index_status.get("files_indexed", 0)),
                        ("Symbols", index_status.get("symbols_indexed", 0)),
                        ("Large Files", index_status.get("large_files", 0)),
                    ]
                    self.console.print(self._build_key_value_table(status_rows))
                    self.console.print()

                except Exception as e:
                    self._show_activity_event(
                        "Context Engine",
                        "Failed to inspect current index state.",
                        status="warning",
                        detail=str(e),
                    )

            # Show available commands
            self.console.print(
                self._build_command_table(
                    [
                        ("/CE", "Show current context usage and quick actions"),
                        ("/CE compress", "Manually compact the current conversation context"),
                        ("/CE info", "Show detailed message and mode information"),
                        ("/CE stats", "Print the raw context statistics output"),
                    ],
                    title="Context Actions",
                    accent=self.theme.BORDER_SECONDARY,
                )
            )
            self.console.print()

            return True

        # Compress command
        elif args == "compress":
            self._show_activity_event(
                "Context Engine",
                "Compressing conversation context.",
                status="working",
                detail="Summarizing older turns into a smaller working memory.",
                blank_before=True,
            )

            try:
                from ..tools.context_management import ContextManagementTool
                context_tool = ContextManagementTool({'project_root': self.app.get('project_root')})
                context_tool.context = {
                    'agent': agent,
                    'config_manager': config_manager,
                    'project_root': self.app.get('project_root')
                }
                
                result = context_tool.execute(action="compress")
                
                if result.success:
                    detail = ""
                    # Show new token count
                    try:
                        usage = self._get_context_usage_snapshot(agent, config_manager)
                        if usage:
                            detail = (
                                f"New usage: {usage.get('total_tokens', 0):,} / "
                                f"{usage.get('max_tokens', 128000):,} tokens "
                                f"({usage.get('percentage', 0):.1f}%)"
                            )
                    except Exception:
                        pass

                    self._show_activity_event(
                        "Context Engine",
                        str(result.output or "Context compression completed."),
                        status="success",
                        detail=detail,
                    )
                else:
                    self._show_activity_event(
                        "Context Engine",
                        "Compression failed.",
                        status="error",
                        detail=str(result.error or ""),
                    )

            except Exception as e:
                self._show_activity_event(
                    "Context Engine",
                    "Compression raised an unexpected error.",
                    status="error",
                    detail=str(e),
                )

            self.console.print()
            return True

        # Info command
        elif args == "info":
            self._show_command_panel(
                "Context Engine Information",
                subtitle="Live breakdown of conversation structure and current operating mode.",
                accent=self.theme.BORDER_PRIMARY,
            )

            # Show detailed information
            info_rows: List[tuple[str, Any]] = []
            # Message breakdown
            if hasattr(agent, 'messages'):
                messages = agent.messages
                user_msgs = sum(1 for m in messages if m.get('role') == 'user')
                assistant_msgs = sum(1 for m in messages if m.get('role') == 'assistant')
                tool_msgs = sum(1 for m in messages if m.get('role') == 'tool')

                info_rows.extend(
                    [
                        ("Total Messages", len(messages)),
                        ("User Messages", user_msgs),
                        ("Assistant Messages", assistant_msgs),
                        ("Tool Messages", tool_msgs),
                    ]
                )

            # System prompt info
            if hasattr(agent, 'system_prompt'):
                prompt_length = len(agent.system_prompt)
                info_rows.append(("System Prompt Length", f"{prompt_length:,} characters"))

            # Mode info
            if hasattr(agent, 'mode'):
                info_rows.append(("Current Mode", agent.mode))

            info_table = self._build_key_value_table(info_rows)
            self.console.print(info_table)
            self.console.print()

            return True

        # Stats command
        elif args == "stats":
            self._show_command_panel(
                "Context Statistics",
                subtitle="Raw token and context statistics reported by the context tools.",
                accent=self.theme.BORDER_PRIMARY,
            )

            try:
                from ..tools.token_counter import TokenCounterTool
                token_counter = TokenCounterTool({'project_root': self.app.get('project_root')})
                token_counter.context = {'agent': agent, 'config_manager': config_manager}
                result = token_counter.execute(check_current_conversation=True)

                if result.success:
                    self.console.print(result.output)
                else:
                    self._show_activity_event(
                        "Context Engine",
                        "Failed to get statistics.",
                        status="error",
                        detail=str(result.error or ""),
                    )
            except Exception as e:
                self._show_activity_event(
                    "Context Engine",
                    "Context statistics raised an unexpected error.",
                    status="error",
                    detail=str(e),
                )

            self.console.print()
            return True

        else:
            self._show_activity_event(
                "Context Engine",
                f"Unknown Context Engine command: {args}",
                status="error",
                detail="Type /CE for available commands.",
            )
            return True

