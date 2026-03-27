"""
Display Components - Rich UI elements for CLI

Enhanced with Dreamscape Theme featuring:
- Dreamy pink-purple-blue color palette
- Elegant decorative elements
- Flowing gradient effects
- Immersive visual experience
"""

from typing import Optional, List, Any, Dict, Tuple
from pathlib import Path
import json
import difflib
import re

from rich.console import Console, Group
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.markdown import Markdown
from rich.text import Text
from rich.align import Align
from rich.columns import Columns
from rich.padding import Padding
from rich.markup import escape
from rich import box
from rich.pager import Pager

from .theme import THEME, DECO, DREAM, DreamBoxes


class DisplayComponents:
    """Rich display components for the CLI with Dreamscape theme"""
    
    def __init__(self, console: Optional[Console] = None):
        self.console = console or Console()
        self.theme = THEME
        self.deco = DECO

    def _console_width(self) -> int:
        """Best-effort terminal width with a sane fallback."""
        try:
            width = int(getattr(self.console.size, "width", 0) or self.console.width or 0)
        except Exception:
            width = 0
        return max(width, 60)

    def _is_compact(self, cutoff: int = 108) -> bool:
        """Whether the current terminal should prefer compact layouts."""
        return self._console_width() < cutoff

    def _fit_panel_width(self, preferred: int = 118, margin: int = 4, min_width: int = 56) -> int:
        """Choose a panel width that behaves well across narrow and wide terminals."""
        available = max(min_width, self._console_width() - max(0, margin))
        return max(min_width, min(preferred, available))

    def _truncate_text(self, value: Any, max_length: int) -> str:
        """Trim long labels without destroying readability."""
        text = str(value or "").strip()
        if len(text) <= max_length:
            return text
        if max_length <= 3:
            return text[:max_length]
        return f"{text[:max_length - 3]}..."

    def _format_compact_number(self, value: Any) -> str:
        """Render large counts in a compact, terminal-friendly form."""
        try:
            number = int(value)
        except (TypeError, ValueError):
            return str(value or "0")

        abs_number = abs(number)
        if abs_number >= 1_000_000:
            return f"{number / 1_000_000:.2f}M".rstrip("0").rstrip(".")
        if abs_number >= 1_000:
            return f"{number / 1_000:.1f}K".rstrip("0").rstrip(".")
        return str(number)

    def _safe_symbol(self, preferred: str, fallback: str) -> str:
        """Prefer Unicode glyphs, but degrade cleanly on legacy console encodings."""
        encoding = str(getattr(getattr(self.console, "file", None), "encoding", "") or "utf-8")
        try:
            preferred.encode(encoding)
        except Exception:
            return fallback
        return preferred

    def _safe_separator(self) -> str:
        """Compact divider used by lightweight Gemini-style surfaces."""
        return self._safe_symbol("\u00b7", "|")

    def _build_badge_line(
        self,
        badges: List[Tuple[str, str, str, str]],
        separator_color: Optional[str] = None,
    ) -> Text:
        """Build a compact metrics/badges line."""
        text = Text()
        joiner_color = separator_color or self.theme.TEXT_DIM
        for index, (label, value, label_color, value_color) in enumerate(badges):
            if index:
                text.append(f" {self.deco.DOT_MEDIUM} ", style=joiner_color)
            if label:
                text.append(f"{label} ", style=label_color)
            text.append(str(value), style=f"bold {value_color}")
        return text
    
    def show_welcome(self, mode: str = "reverie") -> None:
        """Display the large ASCII banner plus version and mode."""
        from .. import __version__

        # IMPORTANT: Keep original banner colors as requested.
        colors = ["#f3e5f5", "#f0e0f8", "#ede0fb", "#ead0fe", "#e7c0ff", "#e4b0ff"]

        banner_lines = [
            "   ██████╗ ███████╗██╗   ██╗███████╗██████╗ ██╗███████╗",
            "   ██╔══██╗██╔════╝██║   ██║██╔════╝██╔══██╗██║██╔════╝",
            "   ██████╔╝█████╗  ██║   ██║█████╗  ██████╔╝██║█████╗  ",
            "   ██╔══██╗██╔══╝  ╚██╗ ██╔╝██╔══╝  ██╔══██╗██║██╔══╝  ",
            "   ██║  ██║███████╗ ╚████╔╝ ███████╗██║  ██║██║███████╗",
            "   ╚═╝  ╚═╝╚══════╝  ╚═══╝  ╚══════╝╚═╝  ╚═╝╚═╝╚══════╝",
        ]

        styled_banner = ""
        for index, line in enumerate(banner_lines):
            color = colors[min(index, len(colors) - 1)]
            styled_banner += f"[bold {color}]{line}[/bold {color}]\n"

        compact = self._is_compact(112)
        banner_text = Text.from_markup(styled_banner.rstrip())
        banner_text.no_wrap = True

        intro_text = Text.from_markup(
            f"[bold {self.theme.PINK_SOFT}]{self.deco.SPARKLE} World-Class Context Engine Coding Assistant {self.deco.SPARKLE}[/bold {self.theme.PINK_SOFT}]\n"
            f"[{self.theme.TEXT_SECONDARY}]Sharper hierarchy, cleaner output rhythm, and stronger terminal fit without changing the Dreamscape palette.[/{self.theme.TEXT_SECONDARY}]"
        )

        session_panel = Panel(
            Group(
                self._build_badge_line(
                    [
                        ("Version", f"v{__version__}", self.theme.TEXT_DIM, self.theme.MINT_SOFT),
                        ("Mode", str(mode or "reverie").upper(), self.theme.TEXT_DIM, self.theme.BLUE_SOFT),
                    ]
                ),
                Text.from_markup(f"[{self.theme.TEXT_DIM}]Created by Raiden[/{self.theme.TEXT_DIM}]"),
            ),
            title=f"[bold {self.theme.PURPLE_SOFT}]{self.deco.DIAMOND} Session[/bold {self.theme.PURPLE_SOFT}]",
            border_style=self.theme.BORDER_SUBTLE,
            box=box.ROUNDED,
            padding=(0, 1),
        )

        quickstart_panel = Panel(
            Text.from_markup(
                f"[bold {self.theme.BLUE_SOFT}]/help[/bold {self.theme.BLUE_SOFT}] command guide\n"
                f"[bold {self.theme.BLUE_SOFT}]/status[/bold {self.theme.BLUE_SOFT}] model and token state\n"
                f"[bold {self.theme.BLUE_SOFT}]/model[/bold {self.theme.BLUE_SOFT}] standard catalog\n"
                f"[bold {self.theme.BLUE_SOFT}]/CE[/bold {self.theme.BLUE_SOFT}] context engine controls"
            ),
            title=f"[bold {self.theme.PURPLE_SOFT}]{self.deco.DIAMOND} Quick Start[/bold {self.theme.PURPLE_SOFT}]",
            border_style=self.theme.BORDER_SUBTLE,
            box=box.ROUNDED,
            padding=(0, 1),
        )

        info_renderable = (
            Group(session_panel, quickstart_panel)
            if compact
            else Columns([session_panel, quickstart_panel], equal=True, expand=True)
        )

        body = Group(
            Align.center(banner_text) if self._console_width() >= 110 else Align.left(banner_text),
            Align.center(intro_text) if not compact else intro_text,
            info_renderable,
        )

        self.console.print(
            Panel(
                body,
                border_style=self.theme.BORDER_PRIMARY,
                padding=(1 if not compact else 0, 1 if compact else 2),
                width=self._fit_panel_width(120, margin=2 if compact else 4),
                box=box.ROUNDED,
            )
        )
        self.console.print()

    def show_response_header(
        self,
        model_name: str,
        provider_label: str = "",
        mode: str = "",
    ) -> None:
        """Render a compact Codex-like response banner."""
        compact = self._is_compact(100)
        separator = self._safe_separator()
        bullet = self._safe_symbol("\u25cf", "*")
        line = Text()
        line.append(f"{bullet} ", style=self.theme.BLUE_SOFT)
        line.append(
            self._truncate_text(model_name or "Assistant", 28 if compact else 42),
            style=f"bold {self.theme.TEXT_PRIMARY}",
        )
        if provider_label:
            line.append(f"  {separator}  ", style=self.theme.TEXT_DIM)
            line.append(provider_label, style=self.theme.BLUE_SOFT)
        if mode:
            line.append(f"  {separator}  ", style=self.theme.TEXT_DIM)
            line.append(str(mode or "reverie").upper(), style=self.theme.TEXT_DIM)
        self.console.print(line)

    def show_user_message(
        self,
        message: str,
        attachments: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        """Render the user's prompt as a dedicated high-contrast transcript block."""
        attachment_items = [item for item in (attachments or []) if isinstance(item, dict)]
        message_text = str(message or "").strip() or "Attached image input."

        body_parts: List[Any] = [Text(message_text, style=f"bold {self.theme.TEXT_PRIMARY}")]

        if attachment_items:
            labels: List[str] = []
            for item in attachment_items[:4]:
                label = str(item.get("file_name") or item.get("file_path") or "image").strip()
                if label:
                    labels.append(label)
            suffix = ""
            if len(attachment_items) > len(labels):
                suffix = f" +{len(attachment_items) - len(labels)} more"
            attachment_line = ", ".join(labels) + suffix if labels else f"{len(attachment_items)} image(s)"
            body_parts.append(Text(f"Images: {attachment_line}", style=f"bold {self.theme.BLUE_GLOW}"))

        separator = self._safe_separator()
        self._show_timeline_block(
            title=f"You  {separator}  input",
            accent=self.theme.BLUE_VIBRANT,
            body=Group(*body_parts),
            footer="prompt queued",
        )

    def show_thinking_banner(self, model_name: str = "") -> None:
        """Render a lightweight thinking marker before streamed reasoning."""
        prefix = self._safe_symbol("\u2502", "|")
        line = Text()
        line.append(f"{prefix} ", style=self.theme.TEXT_DIM)
        line.append("Thinking...", style=f"italic {self.theme.THINKING_MEDIUM}")
        if model_name:
            line.append("  ", style=self.theme.TEXT_DIM)
            line.append(
                self._truncate_text(model_name, 28),
                style=self.theme.TEXT_DIM,
            )
        self.console.print(line)

    def _show_timeline_block(
        self,
        *,
        title: str,
        accent: str,
        body: Optional[Any] = None,
        footer: str = "",
    ) -> None:
        """Render a compact timeline block closer to Codex's transcript rhythm."""
        top_prefix = self._safe_symbol("│ ", "| ")
        bottom_prefix = self._safe_symbol("└ ", "\\- ")
        top = Text()
        top.append(top_prefix, style=accent)
        top.append(title, style=f"bold {accent}")

        renderables: List[Any] = [top]
        if body is not None:
            renderables.append(Padding(body, (0, 0, 0, 2)))
        if footer:
            bottom = Text()
            bottom.append(bottom_prefix, style=accent)
            bottom.append(footer, style=self.theme.TEXT_DIM)
            renderables.append(bottom)
        self.console.print(Group(*renderables))

    def show_activity_event(
        self,
        category: str,
        message: str,
        *,
        status: str = "info",
        detail: str = "",
        meta: str = "",
    ) -> None:
        """Render system/session activity as a compact timeline event."""
        status_key = str(status or "info").strip().lower()
        styles = {
            "info": (self.theme.BLUE_SOFT, "info", self.theme.TEXT_PRIMARY, self.theme.TEXT_DIM),
            "success": (self.theme.MINT_VIBRANT, "done", self.theme.TEXT_PRIMARY, self.theme.TEXT_DIM),
            "warning": (self.theme.AMBER_GLOW, "warning", self.theme.PEACH_SOFT, self.theme.TEXT_DIM),
            "error": (self.theme.CORAL_VIBRANT, "failed", self.theme.CORAL_SOFT, self.theme.TEXT_DIM),
            "working": (self.theme.PURPLE_SOFT, "running", self.theme.TEXT_PRIMARY, self.theme.TEXT_DIM),
        }
        accent, status_label, message_color, detail_color = styles.get(
            status_key,
            styles["info"],
        )

        separator = self._safe_separator()
        compact = self._is_compact(96)
        category_label = self._truncate_text(category or "Activity", 18 if compact else 26)
        title = f"{category_label}  {separator}  {status_label}"

        parts: List[Any] = []
        message_text = str(message or "").strip()
        detail_text = str(detail or "").strip()
        meta_text = str(meta or "").strip()

        if message_text:
            parts.append(Text(message_text, style=f"bold {message_color}"))
        if detail_text:
            parts.append(Text(detail_text, style=detail_color))

        self._show_timeline_block(
            title=title,
            accent=accent,
            body=Group(*parts) if parts else None,
            footer=meta_text,
        )

    def show_status(
        self,
        message: str,
        status: str = "info"
    ) -> None:
        """Show a status message with dreamy styling"""
        styles = {
            "info": (self.deco.RHOMBUS, self.theme.BLUE_SOFT, self.theme.TEXT_SECONDARY),
            "success": (self.deco.CHECK_FANCY, self.theme.MINT_VIBRANT, self.theme.MINT_SOFT),
            "warning": ("!", self.theme.AMBER_GLOW, self.theme.PEACH_SOFT),
            "error": (self.deco.CROSS_FANCY, self.theme.CORAL_VIBRANT, self.theme.CORAL_SOFT)
        }
        
        icon, icon_color, msg_color = styles.get(status, (self.deco.DOT_MEDIUM, self.theme.TEXT_DIM, self.theme.TEXT_SECONDARY))
        self.console.print(f"[bold {icon_color}]{icon}[/bold {icon_color}] [{msg_color}]{message}[/{msg_color}]")
    
    def show_success_message(
        self,
        message: str,
        details: Optional[str] = None,
        use_panel: bool = False
    ) -> None:
        """
        Display a success message with positive colors and icons.
        
        Args:
            message: Main success message
            details: Optional detailed information
            use_panel: Whether to display in a panel
        """
        if use_panel:
            content = f"[{self.theme.MINT_SOFT}]{message}[/{self.theme.MINT_SOFT}]"
            if details:
                content += f"\n\n[{self.theme.TEXT_DIM}]{details}[/{self.theme.TEXT_DIM}]"
            
            self.console.print(Panel(
                content,
                title=f"[bold {self.theme.MINT_VIBRANT}]{self.deco.CHECK_FANCY} Success[/bold {self.theme.MINT_VIBRANT}]",
                border_style=self.theme.MINT_SOFT,
                box=box.ROUNDED,
                padding=(0, 1),
                width=self._fit_panel_width(108),
            ))
        else:
            msg = f"[bold {self.theme.MINT_VIBRANT}]{self.deco.CHECK_FANCY}[/bold {self.theme.MINT_VIBRANT}] [{self.theme.MINT_SOFT}]{message}[/{self.theme.MINT_SOFT}]"
            if details:
                msg += f"\n  [{self.theme.TEXT_DIM}]{details}[/{self.theme.TEXT_DIM}]"
            self.console.print(msg)
    
    def show_error_message(
        self,
        message: str,
        details: Optional[str] = None,
        use_panel: bool = True
    ) -> None:
        """
        Display an error message with prominent colors and icons.
        
        Args:
            message: Main error message
            details: Optional detailed error information
            use_panel: Whether to display in a panel (recommended for errors)
        """
        if use_panel:
            content = f"[bold {self.theme.CORAL_SOFT}]{message}[/bold {self.theme.CORAL_SOFT}]"
            if details:
                content += f"\n\n[{self.theme.TEXT_SECONDARY}]{details}[/{self.theme.TEXT_SECONDARY}]"
            
            self.console.print(Panel(
                content,
                title=f"[bold {self.theme.CORAL_VIBRANT}]{self.deco.CROSS_FANCY} Error[/bold {self.theme.CORAL_VIBRANT}]",
                border_style=self.theme.CORAL_VIBRANT,
                box=box.ROUNDED,
                padding=(0, 1),
                width=self._fit_panel_width(108),
            ))
        else:
            msg = f"[bold {self.theme.CORAL_VIBRANT}]{self.deco.CROSS_FANCY}[/bold {self.theme.CORAL_VIBRANT}] [{self.theme.CORAL_SOFT}]{message}[/{self.theme.CORAL_SOFT}]"
            if details:
                msg += f"\n  [{self.theme.TEXT_DIM}]{details}[/{self.theme.TEXT_DIM}]"
            self.console.print(msg)
    
    def show_warning_message(
        self,
        message: str,
        details: Optional[str] = None,
        use_panel: bool = False
    ) -> None:
        """
        Display a warning message with warning colors and icons.
        
        Args:
            message: Main warning message
            details: Optional detailed information
            use_panel: Whether to display in a panel
        """
        if use_panel:
            content = f"[{self.theme.PEACH_SOFT}]{message}[/{self.theme.PEACH_SOFT}]"
            if details:
                content += f"\n\n[{self.theme.TEXT_DIM}]{details}[/{self.theme.TEXT_DIM}]"
            
            self.console.print(Panel(
                content,
                title=f"[bold {self.theme.AMBER_GLOW}]! Warning[/bold {self.theme.AMBER_GLOW}]",
                border_style=self.theme.AMBER_GLOW,
                box=box.ROUNDED,
                padding=(0, 1),
                width=self._fit_panel_width(108),
            ))
        else:
            msg = f"[bold {self.theme.AMBER_GLOW}]![/bold {self.theme.AMBER_GLOW}] [{self.theme.PEACH_SOFT}]{message}[/{self.theme.PEACH_SOFT}]"
            if details:
                msg += f"\n  [{self.theme.TEXT_DIM}]{details}[/{self.theme.TEXT_DIM}]"
            self.console.print(msg)
    
    def show_info_message(
        self,
        message: str,
        details: Optional[str] = None,
        use_panel: bool = False
    ) -> None:
        """
        Display an info message with info colors and icons.
        
        Args:
            message: Main info message
            details: Optional detailed information
            use_panel: Whether to display in a panel
        """
        if use_panel:
            content = f"[{self.theme.TEXT_SECONDARY}]{message}[/{self.theme.TEXT_SECONDARY}]"
            if details:
                content += f"\n\n[{self.theme.TEXT_DIM}]{details}[/{self.theme.TEXT_DIM}]"
            
            self.console.print(Panel(
                content,
                title=f"[{self.theme.BLUE_SOFT}]{self.deco.RHOMBUS} Info[/{self.theme.BLUE_SOFT}]",
                border_style=self.theme.BLUE_SOFT,
                box=box.ROUNDED,
                padding=(0, 1),
                width=self._fit_panel_width(108),
            ))
        else:
            msg = f"[{self.theme.BLUE_SOFT}]{self.deco.RHOMBUS}[/{self.theme.BLUE_SOFT}] [{self.theme.TEXT_SECONDARY}]{message}[/{self.theme.TEXT_SECONDARY}]"
            if details:
                msg += f"\n  [{self.theme.TEXT_DIM}]{details}[/{self.theme.TEXT_DIM}]"
            self.console.print(msg)
    
    def show_diff(
        self,
        old_content: str,
        new_content: str,
        filename: str = "file",
        context_lines: int = 3,
        side_by_side: bool = False,
        max_lines: int = 100
    ) -> None:
        """
        Display a diff between old and new content with enhanced themed styling.
        
        Args:
            old_content: Original content
            new_content: New content
            filename: Name of the file being diffed
            context_lines: Number of context lines to show around changes
            side_by_side: Whether to use side-by-side display mode
            max_lines: Maximum lines to display before folding
        
        Features:
            - Colored diff display (green for additions, red for deletions, yellow for modifications)
            - Line numbers for both old and new content
            - Context lines around changes
            - File separators for multiple files
            - Side-by-side display mode
            - Large diff optimization with folding
            - Theme consistency with Dreamscape colors
        
        **Validates: Requirements 7.1-7.10**
        """
        old_lines = old_content.splitlines()
        new_lines = new_content.splitlines()
        
        # Generate unified diff
        diff_lines = list(difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile=f"a/{filename}",
            tofile=f"b/{filename}",
            lineterm='',
            n=context_lines
        ))
        
        if not diff_lines:
            self.console.print(f"[{self.theme.TEXT_DIM}]{self.deco.DOT_MEDIUM} No changes in {filename}[/{self.theme.TEXT_DIM}]")
            return
        
        if side_by_side:
            # Side-by-side display mode (Requirement 7.9)
            self._show_diff_side_by_side(old_lines, new_lines, filename, context_lines)
        else:
            # Standard unified diff display
            self._show_diff_unified(diff_lines, max_lines, filename)
    
    def _show_diff_unified(self, diff_lines: List[str], max_lines: int, filename: str) -> None:
        """
        Display unified diff with colored lines and line numbers.
        
        **Validates: Requirements 7.1-7.7, 7.10**
        """
        additions, deletions, hunks = self._summarize_diff_text("\n".join(diff_lines))
        visible_lines = list(diff_lines)
        hidden_count = 0
        if len(visible_lines) > max_lines:
            head = max(8, max_lines // 2)
            tail = max(6, max_lines - head - 1)
            hidden_count = max(0, len(visible_lines) - head - tail)
            visible_lines = (
                visible_lines[:head]
                + [f"@@ ... {hidden_count} diff lines folded for preview ... @@"]
                + visible_lines[-tail:]
            )

        header = self._build_badge_line(
            [
                ("File", self._truncate_text(filename, 42), self.theme.TEXT_DIM, self.theme.PINK_SOFT),
                ("Add", f"+{additions}", self.theme.TEXT_DIM, self.theme.MINT_VIBRANT),
                ("Del", f"-{deletions}", self.theme.TEXT_DIM, self.theme.CORAL_VIBRANT),
                ("Hunks", hunks, self.theme.TEXT_DIM, self.theme.BLUE_SOFT),
            ]
        )
        syntax = Syntax(
            "\n".join(visible_lines),
            "diff",
            theme="ansi_dark",
            line_numbers=False,
            word_wrap=True,
        )
        parts: List[Any] = [header, syntax]
        if hidden_count:
            parts.append(
                Text(
                    f"{self.deco.LOADING_DOTS} {hidden_count} diff lines folded for preview",
                    style=self.theme.TEXT_DIM,
                )
            )

        self.console.print(
            Panel(
                Group(*parts),
                title=f"[bold {self.theme.PINK_SOFT}]{self.deco.SPARKLE} Diff Preview[/bold {self.theme.PINK_SOFT}]",
                border_style=self.theme.BORDER_PRIMARY,
                box=box.ROUNDED,
                padding=(0, 1),
                width=self._fit_panel_width(118),
            )
        )
    
    def _show_diff_side_by_side(
        self,
        old_lines: List[str],
        new_lines: List[str],
        filename: str,
        context_lines: int
    ) -> None:
        """
        Display diff in side-by-side mode.
        
        **Validates: Requirement 7.9**
        """
        from rich.columns import Columns
        
        # Create a table for side-by-side comparison
        table = Table(
            show_header=True,
            header_style=f"bold {self.theme.PURPLE_SOFT}",
            border_style=self.theme.BORDER_PRIMARY,
            box=box.ROUNDED,
            expand=True
        )
        
        table.add_column(
            f"Old ({len(old_lines)} lines)",
            style=self.theme.TEXT_SECONDARY,
            width=50
        )
        table.add_column(
            f"New ({len(new_lines)} lines)",
            style=self.theme.TEXT_SECONDARY,
            width=50
        )
        
        # Use difflib to find matching blocks
        matcher = difflib.SequenceMatcher(None, old_lines, new_lines)
        
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == 'equal':
                # Show context lines
                for i in range(min(context_lines, i2 - i1)):
                    old_line = old_lines[i1 + i] if i1 + i < len(old_lines) else ""
                    new_line = new_lines[j1 + i] if j1 + i < len(new_lines) else ""
                    table.add_row(
                        f"{i1 + i + 1:4d} {old_line}",
                        f"{j1 + i + 1:4d} {new_line}"
                    )
            elif tag == 'delete':
                # Deleted lines (red)
                for i in range(i1, i2):
                    old_line = old_lines[i] if i < len(old_lines) else ""
                    table.add_row(
                        f"[{self.theme.CORAL_VIBRANT}]{i + 1:4d} - {old_line}[/{self.theme.CORAL_VIBRANT}]",
                        ""
                    )
            elif tag == 'insert':
                # Inserted lines (green)
                for j in range(j1, j2):
                    new_line = new_lines[j] if j < len(new_lines) else ""
                    table.add_row(
                        "",
                        f"[{self.theme.MINT_VIBRANT}]{j + 1:4d} + {new_line}[/{self.theme.MINT_VIBRANT}]"
                    )
            elif tag == 'replace':
                # Modified lines (yellow)
                max_lines = max(i2 - i1, j2 - j1)
                for k in range(max_lines):
                    old_line = old_lines[i1 + k] if i1 + k < i2 else ""
                    new_line = new_lines[j1 + k] if j1 + k < j2 else ""
                    
                    old_display = f"[{self.theme.AMBER_GLOW}]{i1 + k + 1:4d} ~ {old_line}[/{self.theme.AMBER_GLOW}]" if old_line else ""
                    new_display = f"[{self.theme.AMBER_GLOW}]{j1 + k + 1:4d} ~ {new_line}[/{self.theme.AMBER_GLOW}]" if new_line else ""
                    
                    table.add_row(old_display, new_display)
        
        self.console.print(table)
    
    def show_code(
        self,
        code: str,
        language: str = "python",
        title: Optional[str] = None,
        line_numbers: bool = True
    ) -> None:
        """Display syntax-highlighted code with dreamy panel"""
        syntax = Syntax(
            code,
            language,
            theme="monokai",
            line_numbers=line_numbers
        )
        
        if title:
            self.console.print(Panel(
                syntax, 
                title=f"[{self.theme.PINK_SOFT}]{self.deco.SPARKLE} {title}[/{self.theme.PINK_SOFT}]",
                border_style=self.theme.PURPLE_MEDIUM
            ))
        else:
            self.console.print(syntax)
    
    def show_markdown(self, text: str) -> None:
        """Render and display markdown"""
        md = Markdown(text)
        self.console.print(md)
    
    def show_long_text(
        self,
        text: str,
        title: Optional[str] = None,
        use_pager: bool = True,
        max_lines: int = 50
    ) -> None:
        """
        Display long text with scrolling and paging support.
        
        Args:
            text: The text to display
            title: Optional title for the content
            use_pager: Whether to use pager for very long text
            max_lines: Maximum lines before using pager
        """
        lines = text.split('\n')
        
        # If text is short enough, display directly
        if len(lines) <= max_lines:
            if title:
                self.console.print(Panel(
                    text,
                    title=f"[bold {self.theme.PINK_SOFT}]{title}[/bold {self.theme.PINK_SOFT}]",
                    border_style=self.theme.BORDER_PRIMARY,
                    box=box.ROUNDED,
                    padding=(0, 1)
                ))
            else:
                self.console.print(text)
            return
        
        # For long text, use pager if enabled
        if use_pager:
            # Create formatted content
            if title:
                formatted = f"[bold {self.theme.PINK_SOFT}]{self.deco.SPARKLE} {title} {self.deco.SPARKLE}[/bold {self.theme.PINK_SOFT}]\n\n{text}"
            else:
                formatted = text
            
            # Use Rich's pager
            with self.console.pager(styles=True):
                self.console.print(formatted)
        else:
            # Display with truncation notice
            truncated_text = '\n'.join(lines[:max_lines])
            remaining = len(lines) - max_lines
            
            footer = f"\n\n[{self.theme.TEXT_DIM}]{self.deco.LOADING_DOTS} {remaining} more lines (use pager to view all)[/{self.theme.TEXT_DIM}]"
            
            if title:
                self.console.print(Panel(
                    truncated_text + footer,
                    title=f"[bold {self.theme.PINK_SOFT}]{title}[/bold {self.theme.PINK_SOFT}]",
                    border_style=self.theme.BORDER_PRIMARY,
                    box=box.ROUNDED,
                    padding=(0, 1)
                ))
            else:
                self.console.print(truncated_text + footer)
    
    def show_paginated_list(
        self,
        items: List[str],
        title: str,
        items_per_page: int = 20
    ) -> None:
        """
        Display a list with pagination support.
        
        Args:
            items: List of items to display
            title: Title for the list
            items_per_page: Number of items per page
        """
        total_items = len(items)
        total_pages = (total_items + items_per_page - 1) // items_per_page
        
        if total_pages <= 1:
            # Display all items
            content = "\n".join(f"[{self.theme.TEXT_SECONDARY}]{self.deco.DOT_MEDIUM} {item}[/{self.theme.TEXT_SECONDARY}]" for item in items)
            self.console.print(Panel(
                content,
                title=f"[bold {self.theme.PINK_SOFT}]{title}[/bold {self.theme.PINK_SOFT}]",
                border_style=self.theme.BORDER_PRIMARY,
                box=box.ROUNDED,
                padding=(0, 1)
            ))
        else:
            # Display with pagination
            current_page = 0
            
            while True:
                start_idx = current_page * items_per_page
                end_idx = min(start_idx + items_per_page, total_items)
                page_items = items[start_idx:end_idx]
                
                content = "\n".join(f"[{self.theme.TEXT_SECONDARY}]{self.deco.DOT_MEDIUM} {item}[/{self.theme.TEXT_SECONDARY}]" for item in page_items)
                footer = f"[{self.theme.TEXT_DIM}]Page {current_page + 1}/{total_pages} • Items {start_idx + 1}-{end_idx}/{total_items}[/{self.theme.TEXT_DIM}]"
                
                self.console.print(Panel(
                    content + "\n\n" + footer,
                    title=f"[bold {self.theme.PINK_SOFT}]{title}[/bold {self.theme.PINK_SOFT}]",
                    border_style=self.theme.BORDER_PRIMARY,
                    box=box.ROUNDED,
                    padding=(0, 1)
                ))
                
                # Ask for next action
                if current_page < total_pages - 1:
                    action = self.console.input(f"[{self.theme.PURPLE_SOFT}]Press Enter for next page, 'q' to quit: [/{self.theme.PURPLE_SOFT}]")
                    if action.lower() == 'q':
                        break
                    current_page += 1
                else:
                    self.console.print(f"[{self.theme.TEXT_DIM}]End of list[/{self.theme.TEXT_DIM}]")
                    break

    
    def show_table(
        self,
        title: str,
        columns: List[str],
        rows: List[List[str]],
        style: str = "default"
    ) -> None:
        """Display a table with dreamy styling"""
        table = Table(
            title=f"[bold {self.theme.PINK_SOFT}]{self.deco.SPARKLE} {title}[/bold {self.theme.PINK_SOFT}]",
            box=box.ROUNDED,
            border_style=self.theme.BORDER_PRIMARY,
            header_style=f"bold {self.theme.PURPLE_SOFT}",
            show_lines=style == "detailed"
        )
        
        for i, col in enumerate(columns):
            col_style = [self.theme.BLUE_SOFT, self.theme.PINK_SOFT, self.theme.PURPLE_SOFT][i % 3]
            table.add_column(col, style=col_style)
        
        for row in rows:
            table.add_row(*row)
        
        self.console.print(table)
    
    def show_panel(
        self,
        content: str,
        title: Optional[str] = None,
        style: str = "default",
        subtitle: Optional[str] = None
    ) -> None:
        """Display a panel with dreamy styling"""
        border_styles = {
            "default": self.theme.BORDER_PRIMARY,
            "success": self.theme.MINT_SOFT,
            "warning": self.theme.AMBER_GLOW,
            "error": self.theme.CORAL_SOFT,
            "info": self.theme.BLUE_SOFT
        }
        
        border = border_styles.get(style, self.theme.BORDER_PRIMARY)
        formatted_title = f"[bold {self.theme.PINK_SOFT}]{title}[/bold {self.theme.PINK_SOFT}]" if title else None
        formatted_subtitle = f"[{self.theme.TEXT_DIM}]{subtitle}[/{self.theme.TEXT_DIM}]" if subtitle else None
        
        self.console.print(Panel(
            content, 
            title=formatted_title, 
            subtitle=formatted_subtitle,
            border_style=border,
            box=box.ROUNDED,
            padding=(0, 1),
            width=self._fit_panel_width(118),
        ))

    def _resolve_tool_color(self, tool_name: str) -> str:
        """Pick a stable accent color for a tool family."""
        tool_colors = {
            "gdd": self.theme.TOOL_GDD,
            "story": self.theme.TOOL_STORY,
            "asset": self.theme.TOOL_ASSET,
            "balance": self.theme.TOOL_BALANCE,
            "level": self.theme.TOOL_LEVEL,
            "config": self.theme.TOOL_CONFIG,
            "computer": self.theme.BLUE_SOFT,
            "read": self.theme.BLUE_SOFT,
            "write": self.theme.PINK_SOFT,
            "edit": self.theme.PURPLE_SOFT,
            "search": self.theme.BLUE_SOFT,
            "grep": self.theme.BLUE_SOFT,
            "web": self.theme.BLUE_SOFT,
            "image": self.theme.PEACH_SOFT,
        }
        lowered = str(tool_name or "").strip().lower()
        for key, color in tool_colors.items():
            if key in lowered:
                return color
        return self.theme.PURPLE_SOFT

    def _format_tool_argument_summary(self, arguments: Optional[Dict[str, Any]], max_items: int = 4) -> str:
        """Build a compact, one-line summary of tool arguments."""
        if not isinstance(arguments, dict) or not arguments:
            return ""

        compact = self._is_compact(96)
        max_items = min(max_items, 2 if compact else 4)
        value_limit = 24 if compact else 42
        parts = []
        for key, value in list(arguments.items())[:max_items]:
            rendered = value
            if isinstance(rendered, (dict, list)):
                rendered = json.dumps(rendered, ensure_ascii=False)
            rendered_text = str(rendered or "").replace("\n", " ").strip()
            if len(rendered_text) > value_limit:
                rendered_text = f"{rendered_text[:value_limit - 3]}..."
            parts.append(f"{key}={rendered_text}")

        extra = len(arguments) - max_items
        if extra > 0:
            parts.append(f"+{extra} more")
        return "  |  ".join(parts)

    def _extract_fenced_block(self, raw_text: str) -> Tuple[str, str]:
        """Return the language and body for a single fenced code block."""
        match = re.fullmatch(r"\s*```([A-Za-z0-9_+-]*)\n(.*?)\n```\s*", raw_text, flags=re.DOTALL)
        if not match:
            return "", ""
        return match.group(1).strip().lower(), match.group(2)

    def _summarize_diff_text(self, diff_text: str) -> Tuple[int, int, int]:
        """Return additions, deletions, and hunk counts for unified diff text."""
        additions = 0
        deletions = 0
        hunks = 0
        for line in str(diff_text or "").splitlines():
            if line.startswith("@@"):
                hunks += 1
            elif line.startswith("+") and not line.startswith("+++"):
                additions += 1
            elif line.startswith("-") and not line.startswith("---"):
                deletions += 1
        return additions, deletions, hunks

    def _build_diff_renderable(self, diff_text: str, preview_line_limit: int) -> Tuple[Any, str]:
        """Render diff text with a tighter, syntax-highlighted preview."""
        lines = str(diff_text or "").splitlines()
        preview_lines = lines[:preview_line_limit]
        hidden = max(0, len(lines) - len(preview_lines))
        additions, deletions, hunks = self._summarize_diff_text(diff_text)
        renderable = Syntax(
            "\n".join(preview_lines),
            "diff",
            theme="ansi_dark",
            line_numbers=False,
            word_wrap=True,
        )
        footer_parts = [f"{len(lines)} lines", f"+{additions}", f"-{deletions}"]
        if hunks:
            footer_parts.append(f"{hunks} hunks")
        if hidden:
            footer_parts.append(f"showing first {len(preview_lines)}")
        return renderable, "  |  ".join(footer_parts)

    def _build_tool_output_renderable(
        self,
        output: Any,
        arguments: Optional[Dict[str, Any]] = None,
    ) -> Tuple[Any, str]:
        """Convert tool output into a rich renderable plus a metadata footer."""
        raw_text = str(output or "").rstrip()
        if not raw_text:
            empty_text = Text("No textual output returned.", style=self.theme.TEXT_DIM)
            return empty_text, "empty output"

        parsed_json = None
        compact = self._is_compact(96)
        preview_line_limit = 10 if compact else 16
        fenced_language, fenced_body = self._extract_fenced_block(raw_text)
        if fenced_language == "diff":
            return self._build_diff_renderable(fenced_body, preview_line_limit=18 if compact else 28)
        if fenced_language:
            fenced_lines = fenced_body.splitlines()
            preview_text = "\n".join(fenced_lines[:preview_line_limit])
            renderable = Syntax(
                preview_text,
                fenced_language,
                theme="monokai",
                line_numbers=False,
                word_wrap=True,
            )
            footer_parts = [f"{len(fenced_lines)} lines", f"{len(fenced_body):,} chars"]
            if len(fenced_lines) > preview_line_limit:
                footer_parts.append(f"showing first {preview_line_limit}")
            return renderable, "  |  ".join(footer_parts)
        if raw_text.startswith("{") or raw_text.startswith("["):
            try:
                parsed_json = json.loads(raw_text)
            except Exception:
                parsed_json = None

        if isinstance(parsed_json, dict) and parsed_json and len(parsed_json) <= 8:
            table = Table(
                box=box.SIMPLE_HEAVY if not compact else box.SIMPLE,
                show_header=False,
                border_style=self.theme.BORDER_SUBTLE,
                pad_edge=False,
            )
            table.add_column(style=self.theme.BLUE_SOFT, no_wrap=True)
            table.add_column(style=self.theme.TEXT_SECONDARY)
            for key, value in parsed_json.items():
                rendered_value = value
                if isinstance(rendered_value, (dict, list)):
                    rendered_value = json.dumps(rendered_value, ensure_ascii=False)
                table.add_row(str(key), str(rendered_value))
            footer = f"{len(parsed_json)} fields"
            return table, footer

        if isinstance(parsed_json, list):
            preview = parsed_json[:6]
            syntax = Syntax(
                json.dumps(preview, indent=2, ensure_ascii=False),
                "json",
                theme="monokai",
                line_numbers=False,
                word_wrap=True,
            )
            extra = len(parsed_json) - len(preview)
            footer = f"{len(parsed_json)} items"
            if extra > 0:
                footer = f"{footer}  |  showing first {len(preview)}"
            return syntax, footer

        inferred_language = ""
        path_value = ""
        if isinstance(arguments, dict):
            path_value = str(arguments.get("path", "") or arguments.get("file_path", "")).strip()
        suffix = Path(path_value).suffix.lower()
        suffix_to_language = {
            ".py": "python",
            ".js": "javascript",
            ".ts": "typescript",
            ".tsx": "tsx",
            ".json": "json",
            ".md": "markdown",
            ".yml": "yaml",
            ".yaml": "yaml",
            ".html": "html",
            ".css": "css",
            ".sh": "bash",
            ".ps1": "powershell",
        }
        if suffix in suffix_to_language:
            inferred_language = suffix_to_language[suffix]

        lines = raw_text.splitlines()
        preview_lines = lines[:preview_line_limit]
        preview_text = "\n".join(preview_lines)
        if inferred_language and len(preview_lines) >= 4:
            renderable = Syntax(
                preview_text,
                inferred_language,
                theme="monokai",
                line_numbers=False,
                word_wrap=True,
            )
        else:
            renderable = Text(preview_text, style=self.theme.TEXT_SECONDARY)

        footer_parts = [f"{len(lines)} lines", f"{len(raw_text):,} chars"]
        if len(lines) > len(preview_lines):
            footer_parts.append(f"showing first {len(preview_lines)}")
        return renderable, "  |  ".join(footer_parts)

    def show_tool_invocation(
        self,
        tool_name: str,
        message: str,
        arguments: Optional[Dict[str, Any]] = None,
        tool_call_id: str = "",
    ) -> None:
        """Render a Gemini-inspired lightweight tool execution block."""
        accent = self._resolve_tool_color(tool_name)
        argument_summary = self._format_tool_argument_summary(arguments)
        separator = self._safe_separator()
        title_label = "Computer Controller" if str(tool_name or "").strip().lower() == "computer_control" else f"Tool {separator} {tool_name}"
        title = str(message or f"Executing {tool_name}...").strip() or title_label
        title_text = f"{title_label}  {separator}  running"
        parts: List[Any] = [Text(title, style=f"bold {self.theme.TEXT_PRIMARY}")]
        if argument_summary:
            parts.append(Text(argument_summary, style=self.theme.TEXT_DIM))
        if tool_call_id:
            parts.append(Text(f"call {tool_call_id[-8:]}", style=self.theme.TEXT_DIM))
        self._show_timeline_block(
            title=title_text,
            accent=accent,
            body=Group(*parts),
            footer="waiting for result",
        )

    def show_tool_result_card(
        self,
        tool_name: str,
        success: bool,
        output: Any = "",
        error: str = "",
        arguments: Optional[Dict[str, Any]] = None,
        tool_call_id: str = "",
    ) -> None:
        """Render a structured tool result block with lower visual noise."""
        accent = self._resolve_tool_color(tool_name) if success else self.theme.CORAL_VIBRANT
        title_body = "Computer Controller" if str(tool_name or "").strip().lower() == "computer_control" else tool_name
        argument_summary = self._format_tool_argument_summary(arguments)
        separator = self._safe_separator()
        if success:
            renderable, footer = self._build_tool_output_renderable(output, arguments=arguments)
            parts: List[Any] = []
            if argument_summary:
                parts.append(Text(argument_summary, style=self.theme.TEXT_DIM))
            if str(output or "").strip():
                parts.append(renderable)
            else:
                parts.extend(
                    [
                        Text("No textual output returned", style=self.theme.TEXT_SECONDARY),
                        Text("The tool may have completed through file changes, state updates, or side effects.", style=self.theme.TEXT_DIM),
                    ]
                )
            if tool_call_id:
                footer = f"{footer}  {separator}  call {tool_call_id[-8:]}" if footer else f"call {tool_call_id[-8:]}"
            self._show_timeline_block(
                title=f"{title_body}  {separator}  done",
                accent=accent,
                body=Group(*parts),
                footer=footer,
            )
        else:
            message = str(error or "Tool execution failed").strip()
            parts = []
            if argument_summary:
                parts.append(Text(argument_summary, style=self.theme.TEXT_DIM))
            parts.extend([
                Text(message, style=self.theme.CORAL_SOFT),
                Text("execution error", style=self.theme.TEXT_DIM),
            ])
            footer = f"call {tool_call_id[-8:]}" if tool_call_id else "tool failure"
            self._show_timeline_block(
                title=f"{title_body}  {separator}  failed",
                accent=accent,
                body=Group(*parts),
                footer=footer,
            )

    def show_stream_event(self, event: Dict[str, Any]) -> bool:
        """Render a structured stream event if supported."""
        event_type = str(event.get("event", "") or "").strip().lower()
        if event_type == "tool_start":
            self.show_tool_invocation(
                tool_name=str(event.get("tool_name", "") or "tool"),
                message=str(event.get("message", "") or "").strip(),
                arguments=event.get("arguments") if isinstance(event.get("arguments"), dict) else None,
                tool_call_id=str(event.get("tool_call_id", "") or "").strip(),
            )
            return True
        if event_type == "tool_result":
            self.show_tool_result_card(
                tool_name=str(event.get("tool_name", "") or "tool"),
                success=bool(event.get("success")),
                output=event.get("output", ""),
                error=str(event.get("error", "") or "").strip(),
                arguments=event.get("arguments") if isinstance(event.get("arguments"), dict) else None,
                tool_call_id=str(event.get("tool_call_id", "") or "").strip(),
            )
            return True
        return False

    def show_tool_output(
        self,
        tool_name: str,
        output: Any,
        status: str = "success",
        format_type: str = "auto"
    ) -> None:
        """
        Display tool output with formatted panels or tables.
        
        Args:
            tool_name: Name of the tool
            output: Tool output (can be dict, list, or string)
            status: Status of the tool execution (success, error, warning)
            format_type: How to format the output (auto, table, panel, json)
        """
        # Determine tool category color
        tool_colors = {
            "gdd": self.theme.TOOL_GDD,
            "story": self.theme.TOOL_STORY,
            "asset": self.theme.TOOL_ASSET,
            "balance": self.theme.TOOL_BALANCE,
            "level": self.theme.TOOL_LEVEL,
            "config": self.theme.TOOL_CONFIG,
        }
        
        # Find matching color
        tool_color = self.theme.PURPLE_SOFT
        for key, color in tool_colors.items():
            if key in tool_name.lower():
                tool_color = color
                break
        
        # Format title with icon
        icon = self.deco.SPARKLE if status == "success" else self.deco.CROSS_FANCY if status == "error" else "!"
        title = f"[bold {tool_color}]{icon} {tool_name}[/bold {tool_color}]"
        
        # Auto-detect format type
        if format_type == "auto":
            if isinstance(output, dict):
                format_type = "table" if len(output) <= 10 else "json"
            elif isinstance(output, list):
                format_type = "table"
            else:
                format_type = "panel"
        
        # Format output based on type
        if format_type == "table" and isinstance(output, dict):
            table = Table(
                title=title,
                box=box.ROUNDED,
                border_style=tool_color,
                show_header=True,
                header_style=f"bold {self.theme.PURPLE_SOFT}"
            )
            table.add_column("Key", style=self.theme.BLUE_SOFT)
            table.add_column("Value", style=self.theme.TEXT_SECONDARY)
            
            for key, value in output.items():
                table.add_row(str(key), str(value))
            
            self.console.print(table)
        
        elif format_type == "table" and isinstance(output, list):
            if output and isinstance(output[0], dict):
                # List of dicts - create table with columns
                table = Table(
                    title=title,
                    box=box.ROUNDED,
                    border_style=tool_color,
                    show_header=True,
                    header_style=f"bold {self.theme.PURPLE_SOFT}"
                )
                
                # Add columns from first item
                for key in output[0].keys():
                    table.add_column(str(key), style=self.theme.TEXT_SECONDARY)
                
                # Add rows
                for item in output:
                    table.add_row(*[str(v) for v in item.values()])
                
                self.console.print(table)
            else:
                # Simple list
                content = "\n".join(f"[{self.theme.TEXT_SECONDARY}]{self.deco.DOT_MEDIUM} {item}[/{self.theme.TEXT_SECONDARY}]" for item in output)
                self.console.print(Panel(
                    content,
                    title=title,
                    border_style=tool_color,
                    box=box.ROUNDED,
                    padding=(0, 1)
                ))
        
        elif format_type == "json":
            import json
            json_str = json.dumps(output, indent=2, ensure_ascii=False)
            syntax = Syntax(json_str, "json", theme="monokai", line_numbers=False)
            self.console.print(Panel(
                syntax,
                title=title,
                border_style=tool_color,
                box=box.ROUNDED
            ))
        
        else:
            # Default panel format
            content = str(output)
            self.console.print(Panel(
                content,
                title=title,
                border_style=tool_color,
                box=box.ROUNDED,
                padding=(0, 1)
            ))

    
    def show_progress_message(self, message: str) -> None:
        """Show a message with spinner in dreamy style"""
        with self.console.status(
            f"[bold {self.theme.PURPLE_SOFT}]{self.deco.SPARKLE}[/bold {self.theme.PURPLE_SOFT}] [{self.theme.TEXT_SECONDARY}]{message}[/{self.theme.TEXT_SECONDARY}]",
            spinner="dots"
        ):
            pass  # Just show the status
    
    def progress_context(self, description: str = "Processing"):
        """Return a progress context manager with dreamy styling"""
        return Progress(
            SpinnerColumn(spinner_name="dots", style=self.theme.PURPLE_SOFT),
            TextColumn(f"[{self.theme.PURPLE_SOFT}]{{task.description}}[/{self.theme.PURPLE_SOFT}]"),
            BarColumn(complete_style=self.theme.PINK_SOFT, finished_style=self.theme.MINT_SOFT),
            TextColumn(f"[{self.theme.BLUE_SOFT}]{{task.percentage:>3.0f}}%[/{self.theme.BLUE_SOFT}]"),
            console=self.console
        )
    
    def show_session_timer(self, elapsed_seconds: float) -> str:
        """Format session timer with styling"""
        hours, remainder = divmod(int(elapsed_seconds), 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"[{self.theme.PURPLE_SOFT}]{self.deco.SPARKLE}[/{self.theme.PURPLE_SOFT}] Session: [{self.theme.PINK_SOFT}]{hours}h {minutes}m {seconds}s[/{self.theme.PINK_SOFT}]"
    
    def show_model_info(
        self,
        model_name: str,
        base_url: str,
        is_connected: bool = True
    ) -> None:
        """Display current model information with dreamy styling"""
        if is_connected:
            status = f"[bold {self.theme.MINT_VIBRANT}]{self.deco.CHECK_FANCY} Connected[/bold {self.theme.MINT_VIBRANT}]"
            border = self.theme.MINT_SOFT
        else:
            status = f"[bold {self.theme.CORAL_VIBRANT}]{self.deco.CROSS_FANCY} Disconnected[/bold {self.theme.CORAL_VIBRANT}]"
            border = self.theme.CORAL_SOFT
        
        info = f"""[{self.theme.TEXT_SECONDARY}]Model:[/{self.theme.TEXT_SECONDARY}] [bold {self.theme.PINK_SOFT}]{model_name}[/bold {self.theme.PINK_SOFT}]
[{self.theme.TEXT_SECONDARY}]Endpoint:[/{self.theme.TEXT_SECONDARY}] [{self.theme.TEXT_DIM}]{base_url}[/{self.theme.TEXT_DIM}]
[{self.theme.TEXT_SECONDARY}]Status:[/{self.theme.TEXT_SECONDARY}] {status}"""
        
        self.console.print(Panel(
            info, 
            title=f"[{self.theme.PINK_SOFT}]{self.deco.RHOMBUS} Model Info[/{self.theme.PINK_SOFT}]",
            border_style=border,
            box=box.ROUNDED
        ))
    
    def show_indexing_stats(self, stats: dict) -> None:
        """Display Context Engine indexing statistics with dreamy styling"""
        symbol_stats = stats.get('symbols', {})
        
        table = Table(
            title=f"[bold {self.theme.PINK_SOFT}]{self.deco.CRYSTAL} Context Engine Statistics[/bold {self.theme.PINK_SOFT}]",
            box=box.ROUNDED,
            border_style=self.theme.BORDER_PRIMARY
        )
        table.add_column("Metric", style=f"bold {self.theme.BLUE_SOFT}")
        table.add_column("Value", style=self.theme.MINT_SOFT)
        
        table.add_row(f"{self.deco.DOT_MEDIUM} Files Indexed", str(stats.get('files_indexed', 0)))
        table.add_row(f"{self.deco.DOT_MEDIUM} Total Symbols", str(symbol_stats.get('total_symbols', 0)))
        table.add_row(f"{self.deco.DOT_MEDIUM} Total Files", str(symbol_stats.get('total_files', 0)))
        
        # Add by-language breakdown
        by_lang = symbol_stats.get('by_language', {})
        if by_lang:
            langs = ", ".join(f"[{self.theme.PURPLE_SOFT}]{k}[/{self.theme.PURPLE_SOFT}]: {v}" for k, v in list(by_lang.items())[:5])
            table.add_row(f"{self.deco.DOT_MEDIUM} By Language", langs)
        
        self.console.print(table)
    
    def show_dream_divider(self, style: str = "sparkle") -> None:
        """Show a dreamy divider line"""
        self.console.print(DREAM.divider(width=50, style=style))
    
    def show_gradient_header(self, text: str) -> None:
        """Show a header with gradient effect"""
        gradient = DREAM.gradient_text(text, self.theme.get_gradient_pink_purple())
        self.console.print(Align.center(gradient))
    
    def clear(self) -> None:
        """Clear the console"""
        self.console.clear()
    
    def print(self, *args, **kwargs) -> None:
        """Proxy to console.print"""
        self.console.print(*args, **kwargs)
    
    def input(self, prompt: str = "") -> str:
        """Get user input"""
        return self.console.input(prompt)
