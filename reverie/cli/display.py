"""
Display Components - Rich UI elements for CLI

Enhanced with Dreamscape Theme featuring:
- Dreamy pink-purple-blue color palette
- Elegant decorative elements
- Flowing gradient effects
- Immersive visual experience
"""

from typing import Optional, List
import difflib

from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.markdown import Markdown
from rich.text import Text
from rich.align import Align
from rich import box

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

        self.console.print(Panel(
            Align.center(Text.from_markup(styled_banner + info_text)),
            border_style=self.theme.BORDER_PRIMARY,
            padding=(1, 2),
            expand=True,
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
    
    def show_diff(
        self,
        old_content: str,
        new_content: str,
        filename: str = "file"
    ) -> None:
        """Display a diff between old and new content with themed styling"""
        old_lines = old_content.splitlines(keepends=True)
        new_lines = new_content.splitlines(keepends=True)
        
        diff = difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile=f"a/{filename}",
            tofile=f"b/{filename}",
            lineterm=''
        )
        
        diff_text = ''.join(diff)
        
        if diff_text:
            syntax = Syntax(diff_text, "diff", theme="monokai", line_numbers=False)
            self.console.print(Panel(
                syntax, 
                title=f"[{self.theme.PINK_SOFT}]{self.deco.DIAMOND} Changes: {filename}[/{self.theme.PINK_SOFT}]",
                border_style=self.theme.BLUE_SOFT
            ))
        else:
            self.console.print(f"[{self.theme.TEXT_DIM}]{self.deco.DOT_MEDIUM} No changes[/{self.theme.TEXT_DIM}]")
    
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
