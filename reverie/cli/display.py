"""
Display Components - Rich UI elements for CLI

Provides:
- Diff display
- Progress bars
- Status messages
- Code highlighting
- Tables
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
from rich import box


class DisplayComponents:
    """Rich display components for the CLI"""
    
    def __init__(self, console: Optional[Console] = None):
        self.console = console or Console()
    
    def show_welcome(self, mode: str = "reverie") -> None:
        """Display the large ASCII banner plus version and mode"""
        from .. import __version__
        
        # Subtle Lavender Gradient (Original Style)
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
        
        info_text = f"\n[bold #f3e5f5]World-Class Context Engine Coding Assistant[/bold #f3e5f5]\n" \
                    f"[dim]v{__version__} | Created by Raiden[/dim]\n" \
                    f"[#ead0fe]Type /help for commands[/#ead0fe]"

        self.console.print(Panel(
            Text.from_markup(styled_banner + info_text),
            border_style="#ead0fe",
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
        """Show a status message"""
        styles = {
            "info": ("i", "blue"),
            "success": ("v", "green"),
            "warning": ("!", "yellow"),
            "error": ("x", "red")
        }
        
        icon, color = styles.get(status, ("•", "white"))
        self.console.print(f"[{color}]{icon}[/{color}] {message}")
    
    def show_diff(
        self,
        old_content: str,
        new_content: str,
        filename: str = "file"
    ) -> None:
        """Display a diff between old and new content"""
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
            self.console.print(Panel(syntax, title=f"Changes: {filename}", border_style="cyan"))
        else:
            self.console.print("[dim]No changes[/dim]")
    
    def show_code(
        self,
        code: str,
        language: str = "python",
        title: Optional[str] = None,
        line_numbers: bool = True
    ) -> None:
        """Display syntax-highlighted code"""
        syntax = Syntax(
            code,
            language,
            theme="monokai",
            line_numbers=line_numbers
        )
        
        if title:
            self.console.print(Panel(syntax, title=title, border_style="blue"))
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
        rows: List[List[str]]
    ) -> None:
        """Display a table"""
        table = Table(title=title, box=box.ROUNDED)
        
        for col in columns:
            table.add_column(col)
        
        for row in rows:
            table.add_row(*row)
        
        self.console.print(table)
    
    def show_panel(
        self,
        content: str,
        title: Optional[str] = None,
        style: str = "cyan"
    ) -> None:
        """Display a panel"""
        self.console.print(Panel(content, title=title, border_style=style))
    
    def show_progress_message(self, message: str) -> None:
        """Show a message with spinner"""
        with self.console.status(message, spinner="dots"):
            pass  # Just show the status
    
    def progress_context(self, description: str = "Processing"):
        """Return a progress context manager"""
        return Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            console=self.console
        )
    
    def show_session_timer(self, elapsed_seconds: float) -> str:
        """Format session timer"""
        hours, remainder = divmod(int(elapsed_seconds), 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"Session Time: {hours}h {minutes}m {seconds}s"
    
    def show_model_info(
        self,
        model_name: str,
        base_url: str,
        is_connected: bool = True
    ) -> None:
        """Display current model information"""
        status = "[bold green]Connected[/bold green]" if is_connected else "[bold red]Disconnected[/bold red]"
        
        info = f"""Model: [bold]{model_name}[/bold]
Endpoint: [dim]{base_url}[/dim]
Status: {status}"""
        
        self.console.print(Panel(info, title="Model", border_style="green" if is_connected else "red"))
    
    def show_indexing_stats(self, stats: dict) -> None:
        """Display Context Engine indexing statistics"""
        symbol_stats = stats.get('symbols', {})
        
        table = Table(title="Context Engine Statistics", box=box.ROUNDED)
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")
        
        table.add_row("Files Indexed", str(stats.get('files_indexed', 0)))
        table.add_row("Total Symbols", str(symbol_stats.get('total_symbols', 0)))
        table.add_row("Total Files", str(symbol_stats.get('total_files', 0)))
        
        # Add by-language breakdown
        by_lang = symbol_stats.get('by_language', {})
        if by_lang:
            langs = ", ".join(f"{k}: {v}" for k, v in list(by_lang.items())[:5])
            table.add_row("By Language", langs)
        
        self.console.print(table)
    
    def clear(self) -> None:
        """Clear the console"""
        self.console.clear()
    
    def print(self, *args, **kwargs) -> None:
        """Proxy to console.print"""
        self.console.print(*args, **kwargs)
    
    def input(self, prompt: str = "") -> str:
        """Get user input"""
        return self.console.input(prompt)
