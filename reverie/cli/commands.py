"""
Command Handler - Process CLI commands with Dreamscape Theme

Handles all commands starting with / with dreamy pink-purple-blue aesthetics
"""

from typing import Optional, Callable, Dict, Any, List
from pathlib import Path
import time

from rich.console import Console, Group
from rich.table import Table
from rich.prompt import Prompt, Confirm
from rich.panel import Panel
from rich.text import Text
from rich.align import Align
from rich.columns import Columns
from rich.padding import Padding
from rich import box
from rich.markup import escape

from .help_catalog import HELP_SECTION_ORDER, HELP_TOPICS, normalize_help_topic
from .theme import THEME, DECO, DREAM


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
        
        # Command registry
        self.commands = {
            'help': self.cmd_help,
            'model': self.cmd_model,
            'iflow': self.cmd_iflow,
            'qwencode': self.cmd_qwencode,
            'geminicli': self.cmd_geminicli,
            'codex': self.cmd_codex,
            'mode': self.cmd_mode,
            'status': self.cmd_status,
            'search': self.cmd_search,
            'sessions': self.cmd_sessions,
            'history': self.cmd_history,
            'clear': self.cmd_clear,
            'clean': self.cmd_clean,
            'index': self.cmd_index,
            'tools': self.cmd_tools,
            'setting': self.cmd_setting,
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
            'CE': self.cmd_context_engine,  # Context Engine management (case-sensitive)
        }
    
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
            self.console.print(f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} Unknown command: /{cmd_original}[/{self.theme.CORAL_SOFT}]")
            self.console.print(f"[{self.theme.TEXT_DIM}]Type /help for available commands.[/{self.theme.TEXT_DIM}]")
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

    def _get_help_topic_items(self) -> List[Dict[str, object]]:
        """Flatten help topics into UI-friendly items while preserving catalog order."""
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

        return items

    def _build_help_topic_preview(self, topic: Dict[str, object], limit: int = 3) -> str:
        """Build a compact preview of full command forms for the help browser list."""
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

    def _filter_help_topic_items(self, items: List[Dict[str, object]], query: str) -> List[Dict[str, object]]:
        """Filter help topics by command, aliases, summaries, and full subcommand forms."""
        raw_query = str(query or "").strip().lower()
        if not raw_query:
            return list(items)

        terms = [term for term in raw_query.split() if term]
        filtered: List[Dict[str, object]] = []

        for item in items:
            search_parts = [
                str(item.get("command", "")),
                str(item.get("section", "")),
                str(item.get("summary", "")),
                str(item.get("detail", "")),
                str(item.get("overview", "")),
                " ".join(str(alias) for alias in (item.get("aliases", []) or [])),
            ]
            for subcommand in item.get("subcommands", []) or []:
                search_parts.extend(
                    [
                        str(subcommand.get("usage", "")),
                        str(subcommand.get("description", "")),
                        self._resolve_help_example(subcommand),
                    ]
                )

            haystack = " ".join(part.lower() for part in search_parts if part)
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
            f"[{self.theme.TEXT_SECONDARY}]Browse commands, full child forms, and runnable examples. Press [bold {self.theme.BLUE_SOFT}]Enter[/bold {self.theme.BLUE_SOFT}] or [bold {self.theme.BLUE_SOFT}]Esc[/bold {self.theme.BLUE_SOFT}] to pin the current page into the transcript.[/{self.theme.TEXT_SECONDARY}]",
            f"[{self.theme.TEXT_DIM}]Focused:[/{self.theme.TEXT_DIM}] [bold {accent}]{escape(command)}[/bold {accent}] [{self.theme.TEXT_DIM}]· {escape(section)}[/{self.theme.TEXT_DIM}]",
        ]
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
        table.add_column("Command", style=f"bold {self.theme.BLUE_SOFT}", width=16, no_wrap=True)
        table.add_column("Section", style=self.theme.TEXT_DIM, width=18, no_wrap=True)
        table.add_column("Forms Preview", style=self.theme.TEXT_SECONDARY, ratio=3)

        end_idx = min(scroll_offset + max_visible, len(filtered_items))
        visible_items = filtered_items[scroll_offset:end_idx]
        for row_index, topic in enumerate(visible_items):
            actual_idx = scroll_offset + row_index
            is_selected = actual_idx == selected_idx
            indicator = Text("›" if is_selected else "", style=f"bold {self.theme.PINK_SOFT}")
            command_style = f"bold {self.theme.TEXT_PRIMARY} on {self.theme.PURPLE_DEEP}" if is_selected else f"bold {self.theme.BLUE_SOFT}"
            section_style = self.theme.TEXT_SECONDARY if is_selected else self.theme.TEXT_DIM
            preview_style = self.theme.TEXT_PRIMARY if is_selected else self.theme.TEXT_SECONDARY
            table.add_row(
                indicator,
                Text(str(topic.get("command", "")).strip(), style=command_style),
                Text(str(topic.get("section", "")).strip(), style=section_style),
                Text(self._build_help_topic_preview(topic), style=preview_style, overflow="fold"),
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
                time.sleep(0.025)

        self.console.print()
        self.console.print(self._build_help_detail_panel(selected_topic))
        self.console.print()
        return True
    
    def cmd_tools(self, args: str) -> bool:
        """List available tools with dreamy styling"""
        agent = self.app.get('agent')
        if not agent:
            self.console.print(f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} Agent not initialized[/{self.theme.CORAL_SOFT}]")
            return True

        # Resolve current mode for tool visibility filtering.
        mode = getattr(agent, "mode", "reverie") or "reverie"
        config_manager = self.app.get('config_manager')
        if config_manager:
            try:
                config = config_manager.load()
                if getattr(config, "mode", None):
                    mode = config.mode
            except Exception:
                # Fall back to agent mode if config loading fails.
                pass

        tool_schemas = agent.tool_executor.get_tool_schemas(mode=mode)
        visible_tool_names = {
            schema.get("function", {}).get("name")
            for schema in tool_schemas
            if schema.get("function", {}).get("name")
        }
        tools = {
            name: tool
            for name, tool in agent.tool_executor._tools.items()
            if name in visible_tool_names
        }
        
        table = Table(
            title=f"[bold {self.theme.PINK_SOFT}]{self.deco.CRYSTAL} Available Tools[/bold {self.theme.PINK_SOFT}]",
            box=box.ROUNDED,
            border_style=self.theme.BORDER_PRIMARY
        )
        table.add_column("Name", style=f"bold {self.theme.BLUE_SOFT}")
        table.add_column("Description", style=self.theme.TEXT_SECONDARY)
        
        for name, tool in sorted(tools.items()):
            # Get first line of description
            desc = tool.description.strip().split('\n')[0]
            table.add_row(f"{self.deco.DOT_MEDIUM} {name}", desc)
        
        self.console.print(table)
        return True

    def _load_tti_config(self):
        """Load normalized TTI configuration from config manager."""
        from ..config import (
            default_text_to_image_config,
            normalize_tti_models,
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
        default_display_name = resolve_tti_default_display_name(tti_cfg)
        return config_manager, config, tti_cfg, models, default_display_name

    def cmd_tti(self, args: str) -> bool:
        """
        Text-to-image CLI command.

        Supported:
        - /tti models      -> list TTI models and pick default model
        - /tti add         -> add a TTI model to config
        - /tti <prompt>    -> generate one image with default model/default params
        """
        raw = args.strip()
        if not raw:
            self.console.print(
                f"[{self.theme.AMBER_GLOW}]{self.deco.DOT_MEDIUM} "
                f"Usage: /tti models OR /tti add OR /tti <your prompt>"
                f"[/{self.theme.AMBER_GLOW}]"
            )
            return True

        if raw.lower() == "models":
            return self._cmd_tti_models()
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

        from ..config import normalize_tti_models, sanitize_tti_path

        config_manager, config, tti_cfg, models, _ = loaded

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
        indexer = self.app.get('indexer')
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
        
        # Session info
        if session_manager:
            session = session_manager.get_current_session()
            if session:
                table.add_row(
                    f"{self.deco.SPARKLE} Session",
                    f"[bold {self.theme.PURPLE_SOFT}]{session.name}[/bold {self.theme.PURPLE_SOFT}]"
                )
                table.add_row(f"{self.deco.DOT_MEDIUM} Messages", str(len(session.messages)))
        
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

    def _format_model_source_label(self, source: str) -> str:
        """Return a readable model source label."""
        mapping = {
            "standard": "config.json",
            "iflow": "iFlow",
            "qwencode": "Qwen Code",
            "geminicli": "Gemini CLI",
            "codex": "Codex",
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
            description = f"{model_id} | {item.get('description', '')}"
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

    def cmd_iflow(self, args: str) -> bool:
        """iFlow integration command."""
        raw = args.strip()
        if not raw:
            return self._cmd_iflow_status()

        lowered = raw.lower()
        if lowered in ("status", "check"):
            return self._cmd_iflow_status()
        if lowered == "model":
            return self._cmd_iflow_model("")
        if lowered.startswith("model "):
            return self._cmd_iflow_model(raw[6:].strip())
        if lowered == "endpoint":
            return self._cmd_iflow_endpoint("")
        if lowered.startswith("endpoint "):
            return self._cmd_iflow_endpoint(raw[9:].strip())

        self.console.print(
            f"[{self.theme.AMBER_GLOW}]{self.deco.DOT_MEDIUM} Usage: /iflow [status|model|endpoint][/{self.theme.AMBER_GLOW}]"
        )
        return True

    def _cmd_iflow_status(self) -> bool:
        """Detect local iFlow CLI credentials and show current iFlow selection."""
        from ..iflow import (
            detect_iflow_cli_credentials,
            normalize_iflow_config,
            resolve_iflow_selected_model,
        )

        config_manager = self.app.get('config_manager')
        config = config_manager.load() if config_manager else None

        cred = detect_iflow_cli_credentials()
        self.console.print()

        if cred.get("found"):
            self.console.print(
                f"[{self.theme.MINT_VIBRANT}]{self.deco.CHECK_FANCY} iFlow CLI credentials detected.[/{self.theme.MINT_VIBRANT}]"
            )
            self.console.print(
                f"[{self.theme.MINT_SOFT}]iFlow CLI is installed and logged in. Use /iflow model to select a model.[/{self.theme.MINT_SOFT}]"
            )
            source_file = cred.get("source_file", "")
            if source_file:
                self.console.print(
                    f"[{self.theme.TEXT_DIM}]Credential source: {source_file}[/{self.theme.TEXT_DIM}]"
                )
        else:
            self.console.print(
                f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} iFlow CLI credentials were not found under ~/.iflow.[/{self.theme.CORAL_SOFT}]"
            )
            self.console.print(
                f"[{self.theme.AMBER_GLOW}]Please install and login to iFlow CLI first, then run /iflow again.[/{self.theme.AMBER_GLOW}]"
            )

        if config_manager and config:
            iflow_cfg = normalize_iflow_config(getattr(config, "iflow", {}))
            selected = resolve_iflow_selected_model(iflow_cfg)
            if selected:
                self.console.print(
                    f"[{self.theme.BLUE_SOFT}]Current iFlow model:[/{self.theme.BLUE_SOFT}] {selected['display_name']} ({selected['id']})"
                )
                context_length = selected.get('context_length', 0)
                if context_length:
                    self.console.print(
                        f"[{self.theme.TEXT_DIM}]Context length: {context_length:,} tokens[/{self.theme.TEXT_DIM}]"
                    )
            else:
                self.console.print(
                    f"[{self.theme.TEXT_DIM}]Current iFlow model: (none)[/{self.theme.TEXT_DIM}]"
                )

            model_source = str(getattr(config, "active_model_source", "standard")).lower()
            self.console.print(
                f"[{self.theme.BLUE_SOFT}]Active model source:[/{self.theme.BLUE_SOFT}] {self._format_model_source_label(model_source)}"
            )
            api_url = str(iflow_cfg.get("api_url", "")).strip()
            if api_url:
                self.console.print(
                    f"[{self.theme.TEXT_DIM}]iFlow API endpoint: {api_url}[/{self.theme.TEXT_DIM}]"
                )
            endpoint = str(iflow_cfg.get("endpoint", "")).strip()
            if endpoint:
                self.console.print(
                    f"[{self.theme.TEXT_DIM}]Endpoint override: {endpoint}[/{self.theme.TEXT_DIM}]"
                )

        self.console.print()
        return True

    def _cmd_iflow_endpoint(self, endpoint_value: str) -> bool:
        """Configure custom endpoint override for iFlow reverse proxy requests."""
        from ..iflow import normalize_iflow_config

        return self._configure_provider_endpoint(
            config_attr="iflow",
            normalize_config=normalize_iflow_config,
            provider_label="iFlow",
            endpoint_value=endpoint_value,
        )

    def _cmd_iflow_model(self, model_query: str) -> bool:
        """Select iFlow model from dedicated catalog."""
        from ..iflow import (
            detect_iflow_cli_credentials,
            get_iflow_model_catalog,
            normalize_iflow_config,
        )

        config_manager = self.app.get('config_manager')
        if not config_manager:
            self.console.print(
                f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} Config manager not available[/{self.theme.CORAL_SOFT}]"
            )
            return True

        cred = detect_iflow_cli_credentials()
        if not cred.get("found"):
            self.console.print(
                f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} iFlow CLI credentials were not found under ~/.iflow.[/{self.theme.CORAL_SOFT}]"
            )
            self.console.print(
                f"[{self.theme.AMBER_GLOW}]Run /iflow first after logging into iFlow CLI.[/{self.theme.AMBER_GLOW}]"
            )
            return True

        catalog = get_iflow_model_catalog()
        return self._select_external_provider_model(
            config_attr="iflow",
            normalize_config=normalize_iflow_config,
            catalog=catalog,
            provider_label="iFlow",
            active_source="iflow",
            model_query=model_query,
        )

    def cmd_qwencode(self, args: str) -> bool:
        """Qwen Code integration command."""
        raw = args.strip()
        if not raw:
            return self._cmd_qwencode_status()

        lowered = raw.lower()
        if lowered in ("status", "check"):
            return self._cmd_qwencode_status()
        if lowered == "login":
            return self._cmd_qwencode_login()
        if lowered == "model":
            return self._cmd_qwencode_model("")
        if lowered.startswith("model "):
            return self._cmd_qwencode_model(raw[6:].strip())
        if lowered == "endpoint":
            return self._cmd_qwencode_endpoint("")
        if lowered.startswith("endpoint "):
            return self._cmd_qwencode_endpoint(raw[9:].strip())

        self.console.print(
            f"[{self.theme.AMBER_GLOW}]{self.deco.DOT_MEDIUM} Usage: /qwencode [status|login|model|endpoint][/{self.theme.AMBER_GLOW}]"
        )
        return True

    def _cmd_qwencode_status(self) -> bool:
        """Detect local Qwen Code CLI credentials and show current Qwen Code selection."""
        from ..qwencode import (
            detect_qwencode_cli_credentials,
            normalize_qwencode_config,
            resolve_qwencode_selected_model,
        )

        config_manager = self.app.get('config_manager')
        config = config_manager.load() if config_manager else None

        cred = detect_qwencode_cli_credentials()
        self.console.print()

        if cred.get("found"):
            self.console.print(
                f"[{self.theme.MINT_VIBRANT}]{self.deco.CHECK_FANCY} Qwen Code CLI credentials detected.[/{self.theme.MINT_VIBRANT}]"
            )
            self.console.print(
                f"[{self.theme.MINT_SOFT}]Qwen Code CLI is installed and logged in. Use /qwencode model to select a model.[/{self.theme.MINT_SOFT}]"
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
            expires_at = cred.get("expires_at")
            if isinstance(expires_at, int) and expires_at > 0:
                expires_at_text = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(expires_at / 1000))
                self.console.print(
                    f"[{self.theme.TEXT_DIM}]Token expiry: {expires_at_text}[/{self.theme.TEXT_DIM}]"
                )
            if cred.get("resource_url"):
                self.console.print(
                    f"[{self.theme.TEXT_DIM}]Credential resource_url: {cred.get('resource_url')}[/{self.theme.TEXT_DIM}]"
                )
            if cred.get("is_expired") is True:
                self.console.print(
                    f"[{self.theme.AMBER_GLOW}]Token is expired. Run /qwencode login after completing `qwen` OAuth login.[/{self.theme.AMBER_GLOW}]"
                )
        else:
            self.console.print(
                f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} Qwen Code CLI credentials were not found under ~/.qwen.[/{self.theme.CORAL_SOFT}]"
            )
            self.console.print(
                f"[{self.theme.AMBER_GLOW}]Use /qwencode login to authenticate, or install Qwen Code CLI first.[/{self.theme.AMBER_GLOW}]"
            )
            if cred.get("errors"):
                self.console.print(
                    f"[{self.theme.TEXT_DIM}]Details: {' | '.join(str(x) for x in cred.get('errors', []))}[/{self.theme.TEXT_DIM}]"
                )

        if config_manager and config:
            qwencode_cfg = normalize_qwencode_config(getattr(config, "qwencode", {}))
            selected = resolve_qwencode_selected_model(qwencode_cfg)
            if selected:
                self.console.print(
                    f"[{self.theme.BLUE_SOFT}]Current Qwen Code model:[/{self.theme.BLUE_SOFT}] {selected['display_name']} ({selected['id']})"
                )
                context_length = selected.get('context_length', 0)
                if context_length:
                    self.console.print(
                        f"[{self.theme.TEXT_DIM}]Context length: {context_length:,} tokens[/{self.theme.TEXT_DIM}]"
                    )
            else:
                self.console.print(
                    f"[{self.theme.TEXT_DIM}]Current Qwen Code model: (none)[/{self.theme.TEXT_DIM}]"
                )

            model_source = str(getattr(config, "active_model_source", "standard")).lower()
            self.console.print(
                f"[{self.theme.BLUE_SOFT}]Active model source:[/{self.theme.BLUE_SOFT}] {self._format_model_source_label(model_source)}"
            )
            api_url = str(qwencode_cfg.get("api_url", "")).strip()
            if api_url:
                self.console.print(
                    f"[{self.theme.TEXT_DIM}]Qwen Code API endpoint: {api_url}[/{self.theme.TEXT_DIM}]"
                )
            endpoint = str(qwencode_cfg.get("endpoint", "")).strip()
            if endpoint:
                self.console.print(
                    f"[{self.theme.TEXT_DIM}]Endpoint override: {endpoint}[/{self.theme.TEXT_DIM}]"
                )

        self.console.print()
        return True

    def _cmd_qwencode_login(self) -> bool:
        """Validate or refresh local Qwen OAuth credentials."""
        from ..qwencode import qwen_oauth_login

        self.console.print()
        self.console.print(
            f"[{self.theme.PURPLE_SOFT}]{self.deco.SPARKLE} Validating Qwen OAuth credentials...[/{self.theme.PURPLE_SOFT}]"
        )
        self.console.print()

        with self.console.status(f"[{self.theme.PURPLE_SOFT}]Checking local CLI cache...[/{self.theme.PURPLE_SOFT}]"):
            login_result = qwen_oauth_login(force_refresh=True)

        if not login_result.get("success"):
            error_msg = login_result.get("error", "Unknown error")
            self.console.print(
                f"[{self.theme.CORAL_VIBRANT}]{self.deco.CROSS} Login failed: {error_msg}[/{self.theme.CORAL_VIBRANT}]"
            )
            self.console.print(
                f"[{self.theme.AMBER_GLOW}]Please run `qwen`, complete OAuth login, then run /qwencode login again.[/{self.theme.AMBER_GLOW}]"
            )
            self.console.print()
            return True

        is_expired = login_result.get("is_expired") is True
        if is_expired:
            self.console.print(
                f"[{self.theme.AMBER_GLOW}]{self.deco.DOT_MEDIUM} Credentials found but token is expired.[/{self.theme.AMBER_GLOW}]"
            )
        elif login_result.get("refreshed"):
            self.console.print(
                f"[{self.theme.MINT_VIBRANT}]{self.deco.CHECK_FANCY} Qwen OAuth token refreshed successfully.[/{self.theme.MINT_VIBRANT}]"
            )
        else:
            self.console.print(
                f"[{self.theme.MINT_VIBRANT}]{self.deco.CHECK_FANCY} Qwen OAuth credentials are valid.[/{self.theme.MINT_VIBRANT}]"
            )

        source_file = str(login_result.get("source_file", "")).strip()
        if source_file:
            self.console.print(
                f"[{self.theme.TEXT_DIM}]Credential source: {source_file}[/{self.theme.TEXT_DIM}]"
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
            f"[{self.theme.TEXT_DIM}]Use /qwencode model to select a model.[/{self.theme.TEXT_DIM}]"
        )
        self.console.print()
        return True

    def _cmd_qwencode_endpoint(self, endpoint_value: str) -> bool:
        """Configure custom endpoint override for Qwen OpenAI-compatible requests."""
        from ..qwencode import normalize_qwencode_config

        return self._configure_provider_endpoint(
            config_attr="qwencode",
            normalize_config=normalize_qwencode_config,
            provider_label="Qwen Code",
            endpoint_value=endpoint_value,
        )

    def _cmd_qwencode_model(self, model_query: str) -> bool:
        """Select Qwen Code model from dedicated catalog."""
        from ..qwencode import (
            detect_qwencode_cli_credentials,
            get_qwencode_model_catalog,
            normalize_qwencode_config,
        )

        config_manager = self.app.get('config_manager')
        if not config_manager:
            self.console.print(
                f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} Config manager not available[/{self.theme.CORAL_SOFT}]"
            )
            return True

        cred = detect_qwencode_cli_credentials()
        if not cred.get("found"):
            self.console.print(
                f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} Qwen Code CLI credentials were not found under ~/.qwen.[/{self.theme.CORAL_SOFT}]"
            )
            self.console.print(
                f"[{self.theme.AMBER_GLOW}]Run /qwencode first after logging into Qwen Code CLI.[/{self.theme.AMBER_GLOW}]"
            )
            return True

        catalog = get_qwencode_model_catalog()
        return self._select_external_provider_model(
            config_attr="qwencode",
            normalize_config=normalize_qwencode_config,
            catalog=catalog,
            provider_label="Qwen Code",
            active_source="qwencode",
            model_query=model_query,
            normalize_query=lambda raw_query: str(
                normalize_qwencode_config({"selected_model_id": raw_query}).get("selected_model_id", "")
            ),
        )

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

    def cmd_mode(self, args: str) -> bool:
        """Quickly switch modes or display current mode and available modes"""
        config_manager = self.app.get('config_manager')
        if not config_manager:
            self.console.print(f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} Config manager not available[/{self.theme.CORAL_SOFT}]")
            return True

        config = config_manager.load()
        mode = args.strip()
        
        # Available modes
        available_modes = [
            "reverie",
            "reverie-gamer",
            "spec-driven",
            "spec-vibe",
            "writer",
            "reverie-ant"
        ]
        
        # If no mode specified, show current mode and available modes
        if not mode:
            current_mode = config.mode or "reverie"
            
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
            
            mode_descriptions = {
                "reverie": "General-purpose coding assistant with context engine",
                "reverie-gamer": "Game development mode with specialized tools for RPG and game design",
                "spec-driven": "Specification-driven development with structured workflows",
                "spec-vibe": "Lightweight spec mode with flexible approach",
                "writer": "Creative writing and documentation mode",
                "reverie-ant": "Advanced task management with planning and execution phases"
            }
            
            for mode_name in available_modes:
                is_current = f"{self.deco.CHECK_FANCY}" if mode_name == current_mode else ""
                description = mode_descriptions.get(mode_name, "")
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
        config.mode = mode
        config_manager.save(config)

        # Reinit agent to apply new mode
        if self.app.get('reinit_agent'):
            self.app['reinit_agent']()

        self.console.print(f"[{self.theme.MINT_VIBRANT}]{self.deco.CHECK_FANCY} Mode switched to {mode}[/{self.theme.MINT_VIBRANT}]")
        return True

    def cmd_gdd(self, args: str) -> bool:
        """Create, view, or summarize GDD (Reverie-Gamer)"""
        from ..tools.game_gdd_manager import GameGDDManagerTool
        
        args = args.strip().lower()
        action = args if args in ["create", "view", "summary"] else "view"
        
        config_manager = self.app.get('config_manager')
        project_root = Path(config_manager.project_root) if config_manager else Path.cwd()
        
        # Initialize the tool
        tool = GameGDDManagerTool({"project_root": str(project_root)})
        
        # Default GDD path
        gdd_path = "docs/GDD.md"
        
        if action == "create":
            # Prompt for project details
            self.console.print()
            self.console.print(Panel(
                f"[bold {self.theme.PINK_SOFT}]{self.deco.SPARKLE} Create Game Design Document {self.deco.SPARKLE}[/bold {self.theme.PINK_SOFT}]",
                border_style=self.theme.BORDER_PRIMARY,
                box=box.ROUNDED,
                padding=(0, 2)
            ))
            self.console.print()
            
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
                default="custom",
                choices=["custom", "phaser", "pygame", "love2d", "godot", "unity", "unreal"]
            )
            
            target_platform = Prompt.ask(
                f"[{self.theme.BLUE_SOFT}]{self.deco.CHEVRON_RIGHT}[/{self.theme.BLUE_SOFT}] Target Platform",
                default="PC"
            )
            
            is_rpg = Confirm.ask(
                f"[{self.theme.BLUE_SOFT}]{self.deco.CHEVRON_RIGHT}[/{self.theme.BLUE_SOFT}] Is this an RPG game?",
                default=True
            )
            
            # Call the tool
            result = tool.execute(
                action="create",
                gdd_path=gdd_path,
                project_name=project_name,
                genre=genre,
                target_engine=target_engine,
                target_platform=target_platform,
                is_rpg=is_rpg
            )
            
            if result.success:
                self.console.print()
                self.console.print(f"[{self.theme.MINT_VIBRANT}]{self.deco.CHECK_FANCY} {result.output}[/{self.theme.MINT_VIBRANT}]")
            else:
                self.console.print(f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} {result.error}[/{self.theme.CORAL_SOFT}]")
            
            return True
        
        elif action == "view":
            # Call the tool to view GDD
            result = tool.execute(action="view", gdd_path=gdd_path)
            
            if result.success:
                from rich.markdown import Markdown
                self.console.print()
                self.console.print(Panel(
                    Markdown(result.output),
                    title=f"[bold {self.theme.PINK_SOFT}]{self.deco.CRYSTAL} Game Design Document[/bold {self.theme.PINK_SOFT}]",
                    border_style=self.theme.BORDER_PRIMARY,
                    box=box.ROUNDED,
                    padding=(1, 2)
                ))
            else:
                self.console.print(f"[{self.theme.AMBER_GLOW}]{self.deco.DOT_MEDIUM} {result.error}[/{self.theme.AMBER_GLOW}]")
                self.console.print(f"[{self.theme.TEXT_DIM}]Use /gdd create to generate a new GDD.[/{self.theme.TEXT_DIM}]")
            
            return True
        
        elif action == "summary":
            # Call the tool to generate summary
            result = tool.execute(action="summary", gdd_path=gdd_path)
            
            if result.success:
                self.console.print()
                self.console.print(Panel(
                    result.output,
                    title=f"[bold {self.theme.PINK_SOFT}]{self.deco.CRYSTAL} GDD Summary[/bold {self.theme.PINK_SOFT}]",
                    border_style=self.theme.BORDER_PRIMARY,
                    box=box.ROUNDED,
                    padding=(1, 2)
                ))
            else:
                self.console.print(f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} {result.error}[/{self.theme.CORAL_SOFT}]")
            
            return True
        
        return True

    def cmd_assets(self, args: str) -> bool:
        """List assets using the game asset tool with formatted table display"""
        from ..tools.game_asset_manager import GameAssetManagerTool
        
        config_manager = self.app.get('config_manager')
        project_root = config_manager.project_root if config_manager else Path.cwd()
        tool = GameAssetManagerTool({"project_root": project_root})
        
        # Parse arguments - support /assets or /assets <type>
        asset_type = args.strip().lower() if args.strip() else "all"
        
        # Validate asset type
        valid_types = ["all", "sprite", "audio", "model", "animation"]
        if asset_type not in valid_types:
            self.console.print(f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} Invalid asset type: {asset_type}[/{self.theme.CORAL_SOFT}]")
            self.console.print(f"[{self.theme.TEXT_DIM}]Valid types: {', '.join(valid_types)}[/{self.theme.TEXT_DIM}]")
            return True
        
        # Execute the tool
        result = tool.execute(action="list", asset_type=asset_type)
        
        if not result.success:
            self.console.print(f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} {result.error}[/{self.theme.CORAL_SOFT}]")
            return True
        
        # Display results in formatted table
        self.console.print()
        
        # Get asset data from result
        data = result.data or {}
        
        if asset_type == "all":
            # Display all assets grouped by type
            assets_by_type = data.get("assets", {})
            total_count = data.get("total_count", 0)
            
            # Title panel
            title_panel = Panel(
                f"[bold {self.theme.PINK_SOFT}]{self.deco.CRYSTAL} Game Assets Overview {self.deco.CRYSTAL}[/bold {self.theme.PINK_SOFT}]\n"
                f"[{self.theme.TEXT_SECONDARY}]Total: {total_count} asset(s)[/{self.theme.TEXT_SECONDARY}]",
                border_style=self.theme.BORDER_PRIMARY,
                box=box.ROUNDED,
                padding=(0, 2)
            )
            self.console.print(title_panel)
            self.console.print()
            
            # Display each asset type in a table
            for atype in ["sprite", "audio", "model", "animation"]:
                assets = assets_by_type.get(atype, [])
                if not assets:
                    continue
                
                # Create table for this asset type
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
                
                # Add rows (limit to first 10 for readability)
                for asset in assets[:10]:
                    name = asset.get("name", "")
                    size = asset.get("size", 0)
                    path = asset.get("path", "")
                    
                    # Format size
                    if size < 1024:
                        size_str = f"{size} B"
                    elif size < 1024 * 1024:
                        size_str = f"{size / 1024:.1f} KB"
                    else:
                        size_str = f"{size / (1024 * 1024):.2f} MB"
                    
                    table.add_row(
                        f"{self.deco.DOT_MEDIUM} {name}",
                        size_str,
                        path
                    )
                
                # Show "and X more" if there are more assets
                if len(assets) > 10:
                    table.add_row(
                        f"[dim {self.theme.TEXT_DIM}]... and {len(assets) - 10} more[/dim {self.theme.TEXT_DIM}]",
                        "",
                        ""
                    )
                
                self.console.print(table)
                self.console.print()
        
        else:
            # Display specific asset type
            assets = data.get("assets", [])
            count = data.get("count", 0)
            
            # Title panel
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
            
            # Create table
            table = Table(
                box=box.ROUNDED,
                border_style=self.theme.BORDER_PRIMARY,
                show_lines=True
            )
            table.add_column("#", style=f"dim {self.theme.TEXT_DIM}", width=5, justify="right")
            table.add_column("Name", style=f"bold {self.theme.MINT_SOFT}", width=35)
            table.add_column("Size", style=self.theme.TEXT_SECONDARY, justify="right", width=12)
            table.add_column("Path", style=self.theme.TEXT_DIM, no_wrap=False)
            
            # Add rows
            for idx, asset in enumerate(assets, 1):
                name = asset.get("name", "")
                size = asset.get("size", 0)
                path = asset.get("path", "")
                
                # Format size
                if size < 1024:
                    size_str = f"{size} B"
                elif size < 1024 * 1024:
                    size_str = f"{size / 1024:.1f} KB"
                else:
                    size_str = f"{size / (1024 * 1024):.2f} MB"
                
                table.add_row(
                    str(idx),
                    f"{self.deco.DOT_MEDIUM} {name}",
                    size_str,
                    path
                )
            
            self.console.print(table)
            self.console.print()
        
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
        if not session_manager:
            self.console.print(f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} Session manager not available[/{self.theme.CORAL_SOFT}]")
            return True

        sessions = session_manager.list_sessions()
        current = session_manager.get_current_session()
        agent = self.app.get('agent')
        workspace_path = getattr(session_manager, 'workspace_path', '')

        if sessions:
            table = Table(
                title=f"[bold {self.theme.PINK_SOFT}]{self.deco.CRYSTAL} Sessions[/bold {self.theme.PINK_SOFT}]",
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
            self.console.print(f"[{self.theme.TEXT_DIM}]{self.deco.DOT_MEDIUM} No sessions in the current directory yet.[/{self.theme.TEXT_DIM}]")
            if workspace_path:
                self.console.print(f"[{self.theme.TEXT_DIM}]Current directory: {escape(str(workspace_path))}[/{self.theme.TEXT_DIM}]")

        actions_text = "Actions: (n)ew, (number) to load, (d) to delete" if sessions else "Actions: (n)ew"
        self.console.print(f"\n[{self.theme.TEXT_DIM}]{self.deco.DOT_MEDIUM} {actions_text}[/{self.theme.TEXT_DIM}]")

        try:
            choice = Prompt.ask(f"[{self.theme.PURPLE_SOFT}]Action[/{self.theme.PURPLE_SOFT}]", default="")

            if choice.lower() == 'n':
                name = Prompt.ask(f"[{self.theme.BLUE_SOFT}]{self.deco.CHEVRON_RIGHT}[/{self.theme.BLUE_SOFT}] Session name", default="")
                session = session_manager.create_session(name or None)
                if agent:
                    agent.set_history(session.messages)
                self.console.print(f"[{self.theme.MINT_VIBRANT}]{self.deco.CHECK_FANCY} Created session: {session.name}[/{self.theme.MINT_VIBRANT}]")

            elif choice.lower() == 'd':
                if not sessions:
                    self.console.print(f"[{self.theme.TEXT_DIM}]{self.deco.DOT_MEDIUM} Nothing to delete.[/{self.theme.TEXT_DIM}]")
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
                                self.console.print(f"[{self.theme.MINT_VIBRANT}]{self.deco.CHECK_FANCY} Deleted. Active session: {replacement.name}[/{self.theme.MINT_VIBRANT}]")
                            else:
                                self.console.print(f"[{self.theme.MINT_VIBRANT}]{self.deco.CHECK_FANCY} Deleted[/{self.theme.MINT_VIBRANT}]")
                except ValueError:
                    pass

            elif choice.isdigit():
                idx = int(choice) - 1
                if 0 <= idx < len(sessions):
                    session = session_manager.load_session(sessions[idx].id)
                    if session:
                        self.console.print(f"[{self.theme.MINT_VIBRANT}]{self.deco.CHECK_FANCY} Loaded: {session.name}[/{self.theme.MINT_VIBRANT}]")
                        if agent:
                            agent.set_history(session.messages)
        except KeyboardInterrupt:
            self.console.print()

        return True
    
    def cmd_history(self, args: str) -> bool:
        """View conversation history with themed styling"""
        agent = self.app.get('agent')
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
        
        self.console.print()
        self.console.print(f"[bold {self.theme.PINK_SOFT}]{self.deco.SPARKLE} Conversation History[/bold {self.theme.PINK_SOFT}]")
        self.console.print(f"[{self.theme.PURPLE_MEDIUM}]{self.deco.LINE_HORIZONTAL * 40}[/{self.theme.PURPLE_MEDIUM}]")
        
        # Show all messages by default
        for msg in history[-limit:]:
            role = msg.get('role', 'unknown')
            content = msg.get('content', '')
            
            if role == 'user':
                self.console.print(f"\n[bold {self.theme.BLUE_SOFT}]{self.deco.CHEVRON_RIGHT} You:[/bold {self.theme.BLUE_SOFT}] {escape(content)}")
            elif role == 'assistant':
                self.console.print(f"\n[bold {self.theme.PINK_SOFT}]{self.deco.SPARKLE} Reverie:[/bold {self.theme.PINK_SOFT}] {escape(content)}")
            elif role == 'tool':
                self.console.print(f"\n[{self.theme.TEXT_DIM}]{self.deco.DOT_MEDIUM} Tool Result: {escape(content[:200])}...[/{self.theme.TEXT_DIM}]")
        
        return True
    
    def cmd_clear(self, args: str) -> bool:
        """Clear the screen"""
        self.console.clear()
        return True

    def cmd_clean(self, args: str) -> bool:
        """Delete current-workspace cache, memory, backups, and audit logs."""
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
                f"[{self.theme.AMBER_GLOW}]{self.deco.DOT_MEDIUM} This will delete only the current workspace's memories, sessions, snapshots, backups, and command audit logs.[/{self.theme.AMBER_GLOW}]"
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
        if not indexer:
            self.console.print(f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} Indexer not available[/{self.theme.CORAL_SOFT}]")
            return True
        
        with self.console.status(f"[{self.theme.PURPLE_SOFT}]{self.deco.SPARKLE} Indexing codebase...[/{self.theme.PURPLE_SOFT}]"):
            result = indexer.full_index()
        
        self.console.print(f"[{self.theme.MINT_VIBRANT}]{self.deco.CHECK_FANCY} Indexing complete![/{self.theme.MINT_VIBRANT}]")
        self.console.print(f"  [{self.theme.TEXT_SECONDARY}]{self.deco.DOT_MEDIUM} Files scanned: [{self.theme.BLUE_SOFT}]{result.files_scanned}[/{self.theme.BLUE_SOFT}][/{self.theme.TEXT_SECONDARY}]")
        self.console.print(f"  [{self.theme.TEXT_SECONDARY}]{self.deco.DOT_MEDIUM} Files parsed: [{self.theme.BLUE_SOFT}]{result.files_parsed}[/{self.theme.BLUE_SOFT}][/{self.theme.TEXT_SECONDARY}]")
        self.console.print(f"  [{self.theme.TEXT_SECONDARY}]{self.deco.DOT_MEDIUM} Symbols: [{self.theme.BLUE_SOFT}]{result.symbols_extracted}[/{self.theme.BLUE_SOFT}][/{self.theme.TEXT_SECONDARY}]")
        self.console.print(f"  [{self.theme.TEXT_SECONDARY}]{self.deco.DOT_MEDIUM} Time: [{self.theme.PURPLE_SOFT}]{result.total_time_ms:.0f}ms[/{self.theme.PURPLE_SOFT}][/{self.theme.TEXT_SECONDARY}]")
        
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
            f"Usage: /setting [status|ui|mode|model|theme|auto-index|status-line|stream|timeout|retries|debug|workspace|rules]"
            f"[/{self.theme.AMBER_GLOW}]"
        )
        return True

    def _setting_mode_options(self) -> List[str]:
        """Available runtime modes for `/mode` and `/setting`."""
        return [
            "reverie",
            "reverie-gamer",
            "reverie-ant",
            "spec-driven",
            "spec-vibe",
            "writer",
        ]

    def _setting_theme_options(self) -> List[str]:
        """Available theme values stored in config."""
        return ["default", "dark", "light", "ocean"]

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

    def _build_setting_summary_panel(self, config, config_manager, rules_manager) -> Panel:
        """Top summary panel for the settings UI."""
        active_model_name = self._resolve_setting_active_model_label(config)
        source_label = self._format_model_source_label(str(getattr(config, "active_model_source", "standard")).lower())
        storage_label = "Workspace" if config_manager.is_workspace_mode() else "Global"

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
            "Rules",
            str(len(rules_manager.get_rules())) if rules_manager else "0",
        )

        return Panel(
            summary,
            title=f"[bold {self.theme.PINK_SOFT}]{self.deco.SPARKLE} Reverie Settings {self.deco.SPARKLE}[/bold {self.theme.PINK_SOFT}]",
            subtitle=f"[{self.theme.TEXT_DIM}]Fast controls for runtime behavior, persistence, and API defaults.[/{self.theme.TEXT_DIM}]",
            border_style=self.theme.BORDER_PRIMARY,
            padding=(0, 2),
            box=box.ROUNDED,
        )

    def _build_setting_list_panel(self, items: List[Dict[str, Any]], selected_idx: int, config, config_manager, rules_manager) -> Panel:
        """Settings list panel for the TUI."""
        table = Table(box=box.SIMPLE, show_header=False, pad_edge=False)
        table.add_column("Item", style=f"bold {self.theme.BLUE_SOFT}", width=24)
        table.add_column("Value", style=self.theme.TEXT_PRIMARY)

        for index, item in enumerate(items):
            is_selected = index == selected_idx
            marker = f"{self.deco.CHEVRON_RIGHT}" if is_selected else " "
            item_name = f"{marker} {item['name']}"
            value_text = self._setting_display_value(item, config, config_manager, rules_manager)
            if is_selected:
                table.add_row(
                    f"[bold {self.theme.PINK_SOFT}]{escape(item_name)}[/bold {self.theme.PINK_SOFT}]",
                    f"[reverse]{value_text}[/reverse]",
                )
            else:
                table.add_row(escape(item_name), value_text)

        return Panel(
            table,
            title=f"[bold {self.theme.BLUE_SOFT}]{self.deco.DIAMOND} Settings[/bold {self.theme.BLUE_SOFT}]",
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
                    for rule in rules[:5]
                )
                if len(rules) > 5:
                    detail_lines.append(f"[{self.theme.TEXT_DIM}]... and {len(rules) - 5} more[/{self.theme.TEXT_DIM}]")

        detail_lines.extend(
            [
                "",
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

    def _build_setting_footer_panel(self) -> Panel:
        """Footer panel with setting TUI controls."""
        footer = (
            f"[{self.theme.TEXT_DIM}]"
            f"{self.deco.DOT_MEDIUM} ↑/↓ or j/k: Navigate  "
            f"{self.deco.DOT_MEDIUM} ←/→ or h/l: Quick change  "
            f"{self.deco.DOT_MEDIUM} Enter: Edit precisely  "
            f"{self.deco.DOT_MEDIUM} Esc: Save & exit"
            f"[/{self.theme.TEXT_DIM}]"
        )
        return Panel(
            Text.from_markup(footer),
            border_style=self.theme.BORDER_SUBTLE,
            padding=(0, 1),
            box=box.ROUNDED,
        )

    def _render_setting_ui(self, selected_idx: int, config, config_manager, rules_manager) -> Group:
        """Compose the full settings TUI renderable."""
        items = self._get_setting_items(config, config_manager, rules_manager)
        summary_panel = self._build_setting_summary_panel(config, config_manager, rules_manager)
        list_panel = self._build_setting_list_panel(items, selected_idx, config, config_manager, rules_manager)
        detail_panel = self._build_setting_detail_panel(items[selected_idx], config, config_manager, rules_manager)
        footer_panel = self._build_setting_footer_panel()

        width = int(getattr(self.console.size, "width", 0) or self.console.width or 0)
        if width >= 84:
            body = Columns([list_panel, detail_panel], expand=True, equal=False)
        else:
            body = Group(list_panel, detail_panel)
        return Group(summary_panel, body, footer_panel)

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
        self.console.print(self._build_setting_summary_panel(config, config_manager, rules_manager))
        self.console.print()
        self.console.print(self._build_setting_list_panel(self._get_setting_items(config, config_manager, rules_manager), 0, config, config_manager, rules_manager))
        self.console.print()
        self.console.print(
            Panel(
                f"[{self.theme.TEXT_DIM}]Direct edits:[/{self.theme.TEXT_DIM}] "
                f"[bold {self.theme.BLUE_SOFT}]/setting mode writer[/bold {self.theme.BLUE_SOFT}]  "
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
        candidate = str(value or "").strip().lower()
        if not candidate:
            candidate = Prompt.ask("Mode", default=config.mode or "reverie", choices=choices).strip().lower()
        if candidate not in choices:
            self.console.print(f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} Invalid mode: {candidate}[/{self.theme.CORAL_SOFT}]")
            return True
        config.mode = candidate
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
            config_manager.set_workspace_mode(True)
            config = config_manager.load()
            config.use_workspace_config = True
            config_manager.save(config)
            return True, f"Workspace mode enabled. Config path: {config_manager.workspace_config_path}"

        if not config_manager.is_workspace_mode():
            return True, "Workspace mode is already disabled."
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
            config_manager.save(config)
            return True
        if kind == "int":
            step = int(item.get("step", 1))
            min_value = int(item.get("min", 0))
            max_value = int(item.get("max", 999999))
            current = int(getattr(config, key))
            current += step * direction
            current = max(min_value, min(max_value, current))
            setattr(config, key, current)
            config_manager.save(config)
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
            config_manager.save(config)
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
            config_manager.save(config)
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
            config_manager.save(config)
            return True
        if kind == "choice":
            if key == "active_model_index":
                selected_idx = self._select_standard_model_index("", prompt_if_missing=True)
                if selected_idx < 0:
                    return False
                config.active_model_index = selected_idx
                config.active_model_source = "standard"
                config_manager.save(config)
                return True
            choices = [str(choice) for choice in (item.get("choices", []) or [])]
            current = str(getattr(config, key) or "")
            picked = Prompt.ask(item["name"], default=current, choices=choices).strip()
            setattr(config, key, picked)
            config_manager.save(config)
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
        changed = False

        from rich.live import Live

        with Live(
            self._render_setting_ui(selected_idx, config, config_manager, rules_manager),
            auto_refresh=False,
            vertical_overflow="visible",
            console=self.console,
        ) as live:
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
                    live.update(self._render_setting_ui(selected_idx, config, config_manager, rules_manager), refresh=True)
                time.sleep(0.025)

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
        from rich.table import Table
        
        config_manager = self.app.get('config_manager')
        if not config_manager:
            self.console.print(f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} Config manager not available[/{self.theme.CORAL_SOFT}]")
            return True
        
        args = args.strip().lower()
        
        # Show current status
        if not args or args == 'status':
            is_workspace = config_manager.is_workspace_mode()
            has_workspace = config_manager.has_workspace_config()
            has_global = config_manager.has_global_config()
            
            self.console.print()
            self.console.print(Panel(
                f"[bold {self.theme.PINK_SOFT}]{self.deco.SPARKLE} Workspace Configuration Status {self.deco.SPARKLE}[/bold {self.theme.PINK_SOFT}]",
                border_style=self.theme.BORDER_PRIMARY,
                box=box.ROUNDED,
                padding=(0, 2)
            ))
            self.console.print()
            
            table = Table(box=box.SIMPLE, show_header=False)
            table.add_column("Setting", style=f"bold {self.theme.BLUE_SOFT}", width=30)
            table.add_column("Value", style=self.theme.MINT_SOFT)
            
            mode_text = f"[{self.theme.MINT_SOFT}]Workspace Mode[/{self.theme.MINT_SOFT}]" if is_workspace else f"[{self.theme.PURPLE_MEDIUM}]Global Mode[/{self.theme.PURPLE_MEDIUM}]"
            table.add_row("Current Mode", mode_text)
            table.add_row("Workspace Config", f"[{self.theme.MINT_SOFT}]Exists[/{self.theme.MINT_SOFT}]" if has_workspace else f"[{self.theme.TEXT_DIM}]Not Found[/{self.theme.TEXT_DIM}]")
            table.add_row("Global Config", f"[{self.theme.MINT_SOFT}]Exists[/{self.theme.MINT_SOFT}]" if has_global else f"[{self.theme.TEXT_DIM}]Not Found[/{self.theme.TEXT_DIM}]")
            
            self.console.print(table)
            self.console.print()
            self.console.print(f"[{self.theme.TEXT_DIM}]Available commands:[/{self.theme.TEXT_DIM}]")
            self.console.print(f"  [{self.theme.BLUE_SOFT}]/workspace enable[/{self.theme.BLUE_SOFT}]  - Enable workspace-local configuration")
            self.console.print(f"  [{self.theme.BLUE_SOFT}]/workspace disable[/{self.theme.BLUE_SOFT}] - Disable workspace-local configuration (use global)")
            self.console.print(f"  [{self.theme.BLUE_SOFT}]/workspace copy-to-workspace[/{self.theme.BLUE_SOFT}] - Copy global config to workspace")
            self.console.print(f"  [{self.theme.BLUE_SOFT}]/workspace copy-to-global[/{self.theme.BLUE_SOFT}] - Copy workspace config to global")
            self.console.print()
            
            return True
        
        # Enable workspace mode
        elif args == 'enable':
            if config_manager.is_workspace_mode():
                self.console.print(f"[{self.theme.TEXT_DIM}]{self.deco.DOT_MEDIUM} Workspace mode is already enabled.[/{self.theme.TEXT_DIM}]")
                return True
            
            # Check if workspace config exists
            if not config_manager.has_workspace_config():
                if not config_manager.has_global_config():
                    self.console.print(f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} No configuration found. Please configure a model first.[/{self.theme.CORAL_SOFT}]")
                    return True
                
                self.console.print(f"[{self.theme.AMBER_GLOW}]{self.deco.DOT_MEDIUM} Workspace config not found. Copying from global config...[/{self.theme.AMBER_GLOW}]")
                if not config_manager.copy_config_to_workspace():
                    self.console.print(f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} Failed to copy config to workspace.[/{self.theme.CORAL_SOFT}]")
                    return True
            
            config_manager.set_workspace_mode(True)
            config = config_manager.load()
            config.use_workspace_config = True
            config_manager.save(config)
            
            self.console.print(f"[{self.theme.MINT_VIBRANT}]{self.deco.CHECK_FANCY} Workspace mode enabled![/{self.theme.MINT_VIBRANT}]")
            self.console.print(f"[{self.theme.TEXT_DIM}]Configuration is now stored in: {config_manager.workspace_config_path}[/{self.theme.TEXT_DIM}]")
            
            # Reinit agent if needed
            if self.app.get('reinit_agent'):
                self.app['reinit_agent']()
            
            return True
        
        # Disable workspace mode
        elif args == 'disable':
            if not config_manager.is_workspace_mode():
                self.console.print(f"[{self.theme.TEXT_DIM}]{self.deco.DOT_MEDIUM} Workspace mode is already disabled.[/{self.theme.TEXT_DIM}]")
                return True
            
            config_manager.set_workspace_mode(False)
            config = config_manager.load()
            config.use_workspace_config = False
            config_manager.save(config)
            
            self.console.print(f"[{self.theme.MINT_VIBRANT}]{self.deco.CHECK_FANCY} Workspace mode disabled![/{self.theme.MINT_VIBRANT}]")
            self.console.print(f"[{self.theme.TEXT_DIM}]Configuration is now stored in: {config_manager.global_config_path}[/{self.theme.TEXT_DIM}]")
            
            # Reinit agent if needed
            if self.app.get('reinit_agent'):
                self.app['reinit_agent']()
            
            return True
        
        # Copy global config to workspace
        elif args == 'copy-to-workspace':
            if not config_manager.has_global_config():
                self.console.print(f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} No global configuration found.[/{self.theme.CORAL_SOFT}]")
                return True
            
            if config_manager.copy_config_to_workspace():
                self.console.print(f"[{self.theme.MINT_VIBRANT}]{self.deco.CHECK_FANCY} Configuration copied to workspace![/{self.theme.MINT_VIBRANT}]")
                self.console.print(f"[{self.theme.TEXT_DIM}]Workspace config: {config_manager.workspace_config_path}[/{self.theme.TEXT_DIM}]")
            else:
                self.console.print(f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} Failed to copy configuration to workspace.[/{self.theme.CORAL_SOFT}]")
            
            return True
        
        # Copy workspace config to global
        elif args == 'copy-to-global':
            if not config_manager.has_workspace_config():
                self.console.print(f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} No workspace configuration found.[/{self.theme.CORAL_SOFT}]")
                return True
            
            if config_manager.copy_config_to_global():
                self.console.print(f"[{self.theme.MINT_VIBRANT}]{self.deco.CHECK_FANCY} Configuration copied to global![/{self.theme.MINT_VIBRANT}]")
                self.console.print(f"[{self.theme.TEXT_DIM}]Global config: {config_manager.global_config_path}[/{self.theme.TEXT_DIM}]")
            else:
                self.console.print(f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} Failed to copy configuration to global.[/{self.theme.CORAL_SOFT}]")
            
            return True
        
        else:
            self.console.print(f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} Unknown workspace command: {args}[/{self.theme.CORAL_SOFT}]")
            self.console.print(f"[{self.theme.TEXT_DIM}]Type /workspace for available commands.[/{self.theme.TEXT_DIM}]")
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
        from rich.table import Table
        from rich.panel import Panel
        from rich import box
        
        agent = self.app.get('agent')
        config_manager = self.app.get('config_manager')
        
        if not agent:
            self.console.print(f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} No active agent session.[/{self.theme.CORAL_SOFT}]")
            return True
        
        args = args.strip().lower()
        
        # No args - show status and help
        if not args:
            self.console.print()
            self.console.print(Panel(
                f"[bold {self.theme.PINK_SOFT}]{self.deco.SPARKLE} Context Engine {self.deco.SPARKLE}[/bold {self.theme.PINK_SOFT}]",
                border_style=self.theme.BORDER_PRIMARY,
                box=box.ROUNDED,
                padding=(0, 2)
            ))
            self.console.print()
            
            # Get token count
            try:
                from ..tools.token_counter import TokenCounterTool
                token_counter = TokenCounterTool(self.app.get('project_root'))
                token_counter.context = {'agent': agent, 'config_manager': config_manager}
                result = token_counter.execute(check_current_conversation=True)
                
                if result.success and result.data:
                    total_tokens = result.data.get('total_tokens', 0)
                    max_tokens = result.data.get('max_tokens', 128000)
                    percentage = result.data.get('percentage', 0)
                    system_tokens = result.data.get('system_tokens', 0)
                    messages_tokens = result.data.get('messages_tokens', 0)
                    message_count = result.data.get('message_count', 0)
                    
                    # Create status table
                    table = Table(show_header=False, box=box.SIMPLE, padding=(0, 2))
                    table.add_column(style=self.theme.TEXT_SECONDARY, width=20)
                    table.add_column(style=self.theme.TEXT_PRIMARY)
                    
                    table.add_row("System Prompt", f"[{self.theme.PURPLE_SOFT}]{system_tokens:,} tokens[/{self.theme.PURPLE_SOFT}]")
                    table.add_row("Messages", f"[{self.theme.BLUE_SOFT}]{messages_tokens:,} tokens ({message_count} messages)[/{self.theme.BLUE_SOFT}]")
                    table.add_row("Total Usage", f"[bold {self.theme.MINT_VIBRANT}]{total_tokens:,} / {max_tokens:,} tokens[/bold {self.theme.MINT_VIBRANT}]")
                    
                    # Color-coded percentage
                    if percentage >= 80:
                        perc_color = self.theme.CORAL_VIBRANT
                        status_icon = "⚠️"
                        status_text = "HIGH"
                    elif percentage >= 60:
                        perc_color = self.theme.AMBER_GLOW
                        status_icon = "ℹ️"
                        status_text = "MODERATE"
                    else:
                        perc_color = self.theme.MINT_SOFT
                        status_icon = "✓"
                        status_text = "GOOD"
                    
                    table.add_row("Usage", f"[{perc_color}]{status_icon} {percentage:.1f}% ({status_text})[/{perc_color}]")
                    
                    self.console.print(table)
                    self.console.print()
                    
                    # Show warning if needed
                    if percentage >= 80:
                        self.console.print(f"[{self.theme.CORAL_SOFT}]{self.deco.DOT_MEDIUM} Context usage is high. Consider compression.[/{self.theme.CORAL_SOFT}]")
                        self.console.print()
                    elif percentage >= 60:
                        self.console.print(f"[{self.theme.AMBER_GLOW}]{self.deco.DOT_MEDIUM} Context usage is moderate. Compression may be needed soon.[/{self.theme.AMBER_GLOW}]")
                        self.console.print()
                
            except Exception as e:
                self.console.print(f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} Failed to get token count: {str(e)}[/{self.theme.CORAL_SOFT}]")
            
            # Show available commands
            cmd_table = Table(show_header=True, box=box.ROUNDED, border_style=self.theme.BORDER_SECONDARY)
            cmd_table.add_column("Command", style=f"bold {self.theme.PINK_SOFT}", width=20)
            cmd_table.add_column("Description", style=self.theme.TEXT_SECONDARY)
            
            cmd_table.add_row("/CE", "Show this status information")
            cmd_table.add_row("/CE compress", "Compress conversation context")
            cmd_table.add_row("/CE info", "Show detailed context information")
            cmd_table.add_row("/CE stats", "Show context statistics")
            
            self.console.print(cmd_table)
            self.console.print()
            
            return True
        
        # Compress command
        elif args == "compress":
            self.console.print()
            self.console.print(f"[{self.theme.PURPLE_SOFT}]{self.deco.SPARKLE} Compressing conversation context...[/{self.theme.PURPLE_SOFT}]")
            self.console.print()
            
            try:
                from ..tools.context_management import ContextManagementTool
                context_tool = ContextManagementTool(self.app.get('project_root'))
                context_tool.context = {
                    'agent': agent,
                    'config_manager': config_manager,
                    'project_root': self.app.get('project_root')
                }
                
                result = context_tool.execute(action="compress")
                
                if result.success:
                    self.console.print(f"[{self.theme.MINT_VIBRANT}]{self.deco.CHECK_FANCY} {result.output}[/{self.theme.MINT_VIBRANT}]")
                    
                    # Show new token count
                    try:
                        from ..tools.token_counter import TokenCounterTool
                        token_counter = TokenCounterTool(self.app.get('project_root'))
                        token_counter.context = {'agent': agent, 'config_manager': config_manager}
                        count_result = token_counter.execute(check_current_conversation=True)
                        
                        if count_result.success and count_result.data:
                            total_tokens = count_result.data.get('total_tokens', 0)
                            max_tokens = count_result.data.get('max_tokens', 128000)
                            percentage = count_result.data.get('percentage', 0)
                            
                            self.console.print()
                            self.console.print(f"[{self.theme.TEXT_DIM}]New usage: {total_tokens:,} / {max_tokens:,} tokens ({percentage:.1f}%)[/{self.theme.TEXT_DIM}]")
                    except Exception:
                        pass
                else:
                    self.console.print(f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} Compression failed: {result.error}[/{self.theme.CORAL_SOFT}]")
                
            except Exception as e:
                self.console.print(f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} Error: {str(e)}[/{self.theme.CORAL_SOFT}]")
            
            self.console.print()
            return True
        
        # Info command
        elif args == "info":
            self.console.print()
            self.console.print(Panel(
                f"[bold {self.theme.PINK_SOFT}]{self.deco.SPARKLE} Context Engine Information {self.deco.SPARKLE}[/bold {self.theme.PINK_SOFT}]",
                border_style=self.theme.BORDER_PRIMARY,
                box=box.ROUNDED,
                padding=(0, 2)
            ))
            self.console.print()
            
            # Show detailed information
            info_table = Table(show_header=False, box=box.SIMPLE, padding=(0, 2))
            info_table.add_column(style=f"bold {self.theme.TEXT_SECONDARY}", width=25)
            info_table.add_column(style=self.theme.TEXT_PRIMARY)
            
            # Message breakdown
            if hasattr(agent, 'messages'):
                messages = agent.messages
                user_msgs = sum(1 for m in messages if m.get('role') == 'user')
                assistant_msgs = sum(1 for m in messages if m.get('role') == 'assistant')
                tool_msgs = sum(1 for m in messages if m.get('role') == 'tool')
                
                info_table.add_row("Total Messages", f"{len(messages)}")
                info_table.add_row("User Messages", f"[{self.theme.BLUE_SOFT}]{user_msgs}[/{self.theme.BLUE_SOFT}]")
                info_table.add_row("Assistant Messages", f"[{self.theme.PURPLE_SOFT}]{assistant_msgs}[/{self.theme.PURPLE_SOFT}]")
                info_table.add_row("Tool Messages", f"[{self.theme.MINT_SOFT}]{tool_msgs}[/{self.theme.MINT_SOFT}]")
            
            # System prompt info
            if hasattr(agent, 'system_prompt'):
                prompt_length = len(agent.system_prompt)
                info_table.add_row("System Prompt Length", f"{prompt_length:,} characters")
            
            # Mode info
            if hasattr(agent, 'mode'):
                info_table.add_row("Current Mode", f"[bold {self.theme.PINK_SOFT}]{agent.mode}[/bold {self.theme.PINK_SOFT}]")
            
            self.console.print(info_table)
            self.console.print()
            
            return True
        
        # Stats command
        elif args == "stats":
            self.console.print()
            self.console.print(Panel(
                f"[bold {self.theme.PINK_SOFT}]{self.deco.SPARKLE} Context Statistics {self.deco.SPARKLE}[/bold {self.theme.PINK_SOFT}]",
                border_style=self.theme.BORDER_PRIMARY,
                box=box.ROUNDED,
                padding=(0, 2)
            ))
            self.console.print()
            
            try:
                from ..tools.token_counter import TokenCounterTool
                token_counter = TokenCounterTool(self.app.get('project_root'))
                token_counter.context = {'agent': agent, 'config_manager': config_manager}
                result = token_counter.execute(check_current_conversation=True)
                
                if result.success:
                    # Display the full output from token counter
                    self.console.print(result.output)
                else:
                    self.console.print(f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} Failed to get statistics: {result.error}[/{self.theme.CORAL_SOFT}]")
            except Exception as e:
                self.console.print(f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} Error: {str(e)}[/{self.theme.CORAL_SOFT}]")
            
            self.console.print()
            return True
        
        else:
            self.console.print(f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} Unknown Context Engine command: {args}[/{self.theme.CORAL_SOFT}]")
            self.console.print(f"[{self.theme.TEXT_DIM}]Type /CE for available commands.[/{self.theme.TEXT_DIM}]")
            return True
