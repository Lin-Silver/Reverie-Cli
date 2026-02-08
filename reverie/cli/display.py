"""
Display Components - Rich UI elements for CLI

Enhanced with Dreamscape Theme featuring:
- Dreamy pink-purple-blue color palette
- Elegant decorative elements
- Flowing gradient effects
- Immersive visual experience
"""

from typing import Optional, List, Any
import difflib
import re

from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.markdown import Markdown
from rich.text import Text
from rich.align import Align
from rich import box
from rich.pager import Pager

from .theme import THEME, DECO, DREAM, DreamBoxes


class DisplayComponents:
    """Rich display components for the CLI with Dreamscape theme"""
    
    def __init__(self, console: Optional[Console] = None):
        self.console = console or Console()
        self.theme = THEME
        self.deco = DECO
    
    def show_welcome(self, mode: str = "reverie") -> None:
        """Display the large ASCII banner plus version and mode"""
        from .. import __version__
        
        # IMPORTANT: Keep original banner colors as requested
        # Subtle Lavender Gradient (Original Style - DO NOT MODIFY)
        colors = ["#f3e5f5", "#f0e0f8", "#ede0fb", "#ead0fe", "#e7c0ff", "#e4b0ff"]
        
        banner_lines = [
            "   ██████╗ ███████╗██╗   ██╗███████╗██████╗ ██╗███████╗",
            "   ██╔══██╗██╔════╝██║   ██║██╔════╝██╔══██╗██║██╔════╝",
            "   ██████╔╝█████╗  ██║   ██║█████╗  ██████╔╝██║█████╗  ",
            "   ██╔══██╗██╔══╝  ╚██╗ ██╔╝██╔══╝  ██╔══██╗██║██╔══╝  ",
            "   ██║  ██║███████╗ ╚████╔╝ ███████╗██║  ██║██║███████╗",
            "   ╚═╝  ╚═╝╚══════╝  ╚═══╝  ╚══════╝╚═╝  ╚═╝╚═╝╚══════╝"
        ]
        
        styled_banner = ""
        for i, line in enumerate(banner_lines):
            color = colors[min(i, len(colors)-1)]
            styled_banner += f"[bold {color}]{line}[/bold {color}]\n"
        
        # Enhanced info section with dreamy aesthetics
        sparkle_line = f"[{self.theme.PURPLE_MEDIUM}]{self.deco.SPARKLE_LINE * 6}[/{self.theme.PURPLE_MEDIUM}]"
        
        info_text = (
            f"\n{sparkle_line}\n"
            f"[bold {self.theme.PINK_SOFT}]{self.deco.SPARKLE} World-Class Context Engine Coding Assistant {self.deco.SPARKLE}[/bold {self.theme.PINK_SOFT}]\n"
            f"[{self.theme.TEXT_DIM}]v{__version__} {self.deco.DOT_MEDIUM} Created by Raiden[/{self.theme.TEXT_DIM}]\n"
            f"{sparkle_line}\n\n"
            f"[{self.theme.PURPLE_SOFT}]{self.deco.CHEVRON_RIGHT} Type [bold]/help[/bold] for commands • Mode: [bold {self.theme.BLUE_SOFT}]{mode.upper()}[/bold {self.theme.BLUE_SOFT}][/{self.theme.PURPLE_SOFT}]"
        )

        # Use width=None to auto-detect terminal width, remove expand=True to prevent display issues
        self.console.print(Panel(
            Align.center(Text.from_markup(styled_banner + info_text)),
            border_style=self.theme.BORDER_PRIMARY,
            padding=(1, 2),
            width=None,
            box=box.ROUNDED
        ))
        self.console.print()
    
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
                padding=(0, 1)
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
                padding=(0, 1)
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
                padding=(0, 1)
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
                padding=(0, 1)
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
        
        # Display file separator (Requirement 7.8)
        # Use a simple format that preserves the filename for testing
        separator = f"[bold {self.theme.PINK_SOFT}]{self.deco.DIAMOND * 3} {filename} {self.deco.DIAMOND * 3}[/bold {self.theme.PINK_SOFT}]"
        self.console.print(separator)
        
        if side_by_side:
            # Side-by-side display mode (Requirement 7.9)
            self._show_diff_side_by_side(old_lines, new_lines, filename, context_lines)
        else:
            # Standard unified diff display
            self._show_diff_unified(diff_lines, max_lines)
    
    def _show_diff_unified(self, diff_lines: List[str], max_lines: int) -> None:
        """
        Display unified diff with colored lines and line numbers.
        
        **Validates: Requirements 7.1-7.7, 7.10**
        """
        output = Text()
        old_line_num = 0
        new_line_num = 0
        displayed_lines = 0
        folded_sections = []
        
        for line in diff_lines:
            # Skip file headers
            if line.startswith('---') or line.startswith('+++'):
                continue
            
            # Parse hunk headers to get line numbers (Requirement 7.5)
            if line.startswith('@@'):
                # Extract line numbers from hunk header
                import re
                match = re.search(r'@@ -(\d+),?\d* \+(\d+),?\d* @@', line)
                if match:
                    old_line_num = int(match.group(1))
                    new_line_num = int(match.group(2))
                
                # Display hunk header with theme colors (Requirement 7.10)
                output.append(f"\n{line}\n", style=self.theme.BLUE_SOFT)
                continue
            
            # Check if we need to fold (Requirement 7.7)
            if displayed_lines >= max_lines and line.startswith(' '):
                if not folded_sections or folded_sections[-1][1] != displayed_lines - 1:
                    folded_sections.append((displayed_lines, displayed_lines))
                else:
                    folded_sections[-1] = (folded_sections[-1][0], displayed_lines)
                displayed_lines += 1
                continue
            
            # Format line with colors and line numbers
            if line.startswith('+'):
                # Addition - green background (Requirements 7.1, 7.2)
                line_nums = f"    {new_line_num:4d} "
                output.append(line_nums, style=self.theme.TEXT_DIM)
                output.append(f"{line}\n", style=f"bold {self.theme.MINT_VIBRANT} on #1a3a1a")
                new_line_num += 1
            elif line.startswith('-'):
                # Deletion - red background (Requirements 7.1, 7.3)
                line_nums = f"{old_line_num:4d}     "
                output.append(line_nums, style=self.theme.TEXT_DIM)
                output.append(f"{line}\n", style=f"bold {self.theme.CORAL_VIBRANT} on #3a1a1a")
                old_line_num += 1
            elif line.startswith(' '):
                # Context line - gray (Requirements 7.1, 7.6)
                line_nums = f"{old_line_num:4d} {new_line_num:4d} "
                output.append(line_nums, style=self.theme.TEXT_DIM)
                output.append(f"{line}\n", style=self.theme.TEXT_DIM)
                old_line_num += 1
                new_line_num += 1
            else:
                # Other lines (shouldn't happen in unified diff)
                output.append(f"{line}\n", style=self.theme.TEXT_SECONDARY)
            
            displayed_lines += 1
        
        # Show folded sections info (Requirement 7.7)
        if folded_sections:
            total_folded = sum(end - start + 1 for start, end in folded_sections)
            output.append(
                f"\n[{self.deco.LOADING_DOTS} {total_folded} context lines folded]\n",
                style=self.theme.TEXT_DIM
            )
        
        # Display in panel with theme consistency (Requirement 7.10)
        self.console.print(Panel(
            output,
            border_style=self.theme.BORDER_PRIMARY,
            box=box.ROUNDED,
            padding=(0, 1)
        ))
    
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
            padding=(0, 1)
        ))
    
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
