"""
Command Handler - Process CLI commands

Handles all commands starting with / 
"""

from typing import Optional, Callable, Dict, Any
from pathlib import Path
import time

from rich.console import Console
from rich.table import Table
from rich.prompt import Prompt, Confirm
from rich import box
from rich.markup import escape


class CommandHandler:
    """Handles CLI commands (starting with /)"""
    
    def __init__(
        self,
        console: Console,
        app_context: Dict[str, Any]
    ):
        self.console = console
        self.app = app_context
        
        # Command registry
        self.commands = {
            'help': self.cmd_help,
            'model': self.cmd_model,
            'add_model': self.cmd_add_model,
            'status': self.cmd_status,
            'search': self.cmd_search,
            'sessions': self.cmd_sessions,
            'history': self.cmd_history,
            'clear': self.cmd_clear,
            'index': self.cmd_index,
            'tools': self.cmd_tools,
            'setting': self.cmd_setting,
            'rules': self.cmd_rules,
            'exit': self.cmd_exit,
            'quit': self.cmd_exit,
        }
    
    def handle(self, command_line: str) -> bool:
        """
        Handle a command.
        
        Returns True if the app should continue, False if should exit.
        """
        parts = command_line[1:].split(maxsplit=1)  # Remove leading /
        if not parts:
            return True
        
        cmd = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""
        
        if cmd in self.commands:
            return self.commands[cmd](args)
        else:
            self.console.print(f"[red]Unknown command: /{cmd}[/red]")
            self.console.print("Type /help for available commands.")
            return True
    
    def cmd_help(self, args: str) -> bool:
        """Show detailed help with beautiful formatting"""
        from rich.panel import Panel
        from rich.text import Text
        from rich.columns import Columns
        from rich.padding import Padding
        
        # Main title
        self.console.print()
        self.console.print(Panel(
            "[bold #ffb8d1]Reverie CLI - Command Help[/bold #ffb8d1]\n" 
            "[dim #ce93d8]World-class context engine coding assistant[/dim #ce93d8]",
            border_style="#ce93d8",
            padding=(0, 2),
            box=box.ROUNDED
        ))
        self.console.print()
        
        # Basic commands
        basic_commands = Table(
            title="[bold #ffb8d1]Basic Commands[/bold #ffb8d1]",
            box=box.ROUNDED,
            border_style="#ce93d8",
            show_lines=True,
            title_justify="left"
        )
        basic_commands.add_column("Command", style="bold #81d4fa", width=15)
        basic_commands.add_column("Description", style="white")
        basic_commands.add_column("Example", style="dim #a5d6a7")
        
        basic_commands.add_row(
            "/help",
            "Show this help with all available commands and usage.",
            "/help"
        )
        basic_commands.add_row(
            "/status",
            "View current status: active model, tokens, session time, index stats.",
            "/status"
        )
        basic_commands.add_row(
            "/clear",
            "Clear the terminal to keep the workspace tidy.",
            "/clear"
        )
        basic_commands.add_row(
            "/exit",
            "Save the session and exit. Data is saved for next launch.",
            "/exit or /quit"
        )
        
        self.console.print(basic_commands)
        self.console.print()
        
        # Models and config
        config_commands = Table(
            title="[bold #ffb8d1]Models & Settings[/bold #ffb8d1]",
            box=box.ROUNDED,
            border_style="#ce93d8",
            show_lines=True,
            title_justify="left"
        )
        config_commands.add_column("Command", style="bold #81d4fa", width=15)
        config_commands.add_column("Description", style="white")
        config_commands.add_column("Example", style="dim #a5d6a7")
        
        config_commands.add_row(
            "/model",
            "Model manager:\n• List configured models\n• Switch active model\n• Add model: /model add\n• Delete: /model delete <#>",
            "/model\n/model add\n/model delete 2"
        )
        config_commands.add_row(
            "/setting",
            "Interactive settings menu:\n• Mode (reverie/spec-driven/spec-vibe)\n• Theme\n• Custom rules\n• Auto-index toggle",
            "/setting"
        )
        config_commands.add_row(
            "/rules",
            "Manage custom rules:\n• List rules\n• Add rule: /rules add <text>\n• Remove: /rules remove <#>",
            "/rules\n/rules add Always use async\n/rules remove 1"
        )
        
        self.console.print(config_commands)
        self.console.print()
        
        # Tools and features
        tool_commands = Table(
            title="[bold #ffb8d1]Tools & Features[/bold #ffb8d1]",
            box=box.ROUNDED,
            border_style="#ce93d8",
            show_lines=True,
            title_justify="left"
        )
        tool_commands.add_column("Command", style="bold #81d4fa", width=15)
        tool_commands.add_column("Description", style="white")
        tool_commands.add_column("Example", style="dim #a5d6a7")
        
        tool_commands.add_row(
            "/search <q>",
            "Web search (DuckDuckGo) for docs and answers. Results show in Markdown.",
            "/search rust async patterns\n/search python FastAPI"
        )
        tool_commands.add_row(
            "/tools",
            "List available tools the AI can use:\n• Read/write files\n• Run commands\n• Search code\n• Git actions, etc.",
            "/tools"
        )
        tool_commands.add_row(
            "/index",
            "Re-index the codebase: scan files, extract symbols and dependencies. Use after structure changes.",
            "/index"
        )
        
        self.console.print(tool_commands)
        self.console.print()
        
        # Session management
        session_commands = Table(
            title="[bold #ffb8d1]Session Management[/bold #ffb8d1]",
            box=box.ROUNDED,
            border_style="#ce93d8",
            show_lines=True,
            title_justify="left"
        )
        session_commands.add_column("Command", style="bold #81d4fa", width=15)
        session_commands.add_column("Description", style="white")
        session_commands.add_column("Example", style="dim #a5d6a7")
        
        session_commands.add_row(
            "/sessions",
            "Manage conversation sessions:\n• List history\n• Load previous\n• Create new\n• Delete old",
            "/sessions"
        )
        session_commands.add_row(
            "/history [n]",
            "Show conversation history. Display the last n messages (default 10).",
            "/history\n/history 20"
        )
        
        self.console.print(session_commands)
        self.console.print()
        
        # Quick tips
        tips = Panel(
            "[bold #ce93d8]Tips[/bold #ce93d8]\n\n"
            "[#ffb8d1]• Input[/#ffb8d1]  Type questions or requests directly; the AI will respond.\n"
            "[#ffb8d1]• Multi-line[/#ffb8d1]  Use a trailing \ or triple quotes to enter multi-line text.\n"
            "[#ffb8d1]• Interrupt[/#ffb8d1]  Ctrl+C once cancels input; twice exits the program.\n"
            "[#ffb8d1]• History[/#ffb8d1]  Use ↑/↓ to browse input history.\n"
            "[#ffb8d1]• Completion[/#ffb8d1]  Type /command to see available completions.",
            border_style="#ce93d8",
            padding=(0, 2),
            box=box.ROUNDED
        )
        self.console.print(tips)
        self.console.print()
        
        return True
    
    def cmd_tools(self, args: str) -> bool:
        """List available tools"""
        agent = self.app.get('agent')
        if not agent:
            self.console.print("[red]Agent not initialized[/red]")
            return True
            
        tools = agent.tool_executor._tools
        
        table = Table(title="Available Tools", box=box.ROUNDED, border_style="#ce93d8")
        table.add_column("Name", style="bold #81d4fa")
        table.add_column("Description", style="white")
        
        for name, tool in sorted(tools.items()):
            # Get first line of description
            desc = tool.description.strip().split('\n')[0]
            table.add_row(name, desc)
            
        self.console.print(table)
        return True

    def cmd_status(self, args: str) -> bool:
        """Show current status"""
        config_manager = self.app.get('config_manager')
        indexer = self.app.get('indexer')
        session_manager = self.app.get('session_manager')
        start_time = self.app.get('start_time')
        agent = self.app.get('agent')
        
        self.console.print()
        table = Table(title="[bold #ffb8d1]Reverie System Status[/bold #ffb8d1]", box=box.ROUNDED, border_style="#ce93d8")
        table.add_column("Component", style="bold #81d4fa")
        table.add_column("Value", style="white")
        
        # Model info
        if config_manager:
            model = config_manager.get_active_model()
            if model:
                table.add_row("Model", f"[bold #ffb8d1]{model.model_display_name}[/bold #ffb8d1]")
                table.add_row("Endpoint", f"[dim]{model.base_url}[/dim]")
        
        # Session info
        if session_manager:
            session = session_manager.get_current_session()
            if session:
                table.add_row("Session", f"[bold #ce93d8]{session.name}[/bold #ce93d8]")
                table.add_row("Messages", str(len(session.messages)))
        
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
                     config = config_manager.load()
                     max_tokens = getattr(config, 'max_context_tokens', 128000)

            percentage = (tokens / max_tokens) * 100
            table.add_row("Context Usage", f"{tokens:,} / {max_tokens:,} ([bold #ffb86c]{percentage:.1f}%[/bold #ffb86c])")
        
        # Context Engine stats
        if indexer:
            stats = indexer.get_statistics()
            table.add_row("Files Indexed", f"[bold #a5d6a7]{stats.get('files_indexed', 0)}[/bold #a5d6a7]")
            symbols = stats.get('symbols', {})
            table.add_row("Total Symbols", f"[bold #a5d6a7]{symbols.get('total_symbols', 0)}[/bold #a5d6a7]")
        
        # Timer
        if start_time:
            elapsed = time.time() - start_time
            hours, remainder = divmod(int(elapsed), 3600)
            minutes, seconds = divmod(remainder, 60)
            table.add_row("Total Time", f"[bold #f1fa8c]{hours}h {minutes}m {seconds}s[/bold #f1fa8c]")
            
            active_elapsed = self.app.get('total_active_time', 0.0)
            cur_start = self.app.get('current_task_start')
            if cur_start:
                active_elapsed += (time.time() - cur_start)
            
            a_hours, a_remainder = divmod(int(active_elapsed), 3600)
            a_minutes, a_seconds = divmod(a_remainder, 60)
            table.add_row("Active Time", f"[bold #a5d6a7]{a_hours}h {a_minutes}m {a_seconds}s[/bold #a5d6a7]")
        
        self.console.print(table)
        self.console.print()
        return True

    def cmd_model(self, args: str) -> bool:
        """List and select models, or add/delete one"""
        args = args.strip().lower()
        if args == 'add':
            return self.cmd_add_model(args)
        
        config_manager = self.app.get('config_manager')
        if not config_manager:
            self.console.print("[red]Config manager not available[/red]")
            return True
        
        # Handle delete
        if args.startswith('delete') or args.startswith('remove'):
            parts = args.split()
            if len(parts) > 1:
                try:
                    index_to_delete = int(parts[1]) - 1
                    if Confirm.ask(f"Delete model #{index_to_delete + 1}?"):
                         if config_manager.remove_model(index_to_delete):
                             self.console.print("[green]Model deleted.[/green]")
                             # Reinit agent if needed
                             if self.app.get('reinit_agent'):
                                 self.app['reinit_agent']()
                         else:
                             self.console.print("[red]Invalid model index.[/red]")
                except ValueError:
                    self.console.print("[red]Invalid index format. Use: /model delete <number>[/red]")
            else:
                 self.console.print("[yellow]Usage: /model delete <number>[/yellow]")
            return True

        config = config_manager.load()
        
        if not config.models:
            self.console.print("[yellow]No models configured.[/yellow]")
            if Confirm.ask("Would you like to add one now?"):
                return self.cmd_add_model("")
            return True
        
        # Show model list
        table = Table(title="Available Models", box=box.ROUNDED, border_style="#ce93d8")
        table.add_column("#", style="dim")
        table.add_column("Model", style="bold #81d4fa")
        table.add_column("Endpoint")
        table.add_column("Status")
        
        for i, model in enumerate(config.models):
            active = "*" if i == config.active_model_index else " "
            status = "[bold #a5d6a7]Active[/bold #a5d6a7]" if i == config.active_model_index else ""
            table.add_row(
                str(i + 1),
                model.model_display_name,
                model.base_url,
                status
            )
        
        self.console.print(table)
        self.console.print("[dim #ce93d8]Tip: Use '/model add' to add, or '/model delete <#>' to remove[/dim #ce93d8]")
        
        # Ask to select
        try:
            choice = Prompt.ask(
                "Select model # to activate (or Enter to keep current)",
                default=""
            )
            
            if choice:
                try:
                    index = int(choice) - 1
                    if 0 <= index < len(config.models):
                        config_manager.set_active_model(index)
                        self.console.print(
                            f"[bold #a5d6a7]Switched to: {config.models[index].model_display_name}[/bold #a5d6a7]"
                        )
                        
                        # Reinitialize agent
                        if self.app.get('reinit_agent'):
                            self.app['reinit_agent']()
                    else:
                        self.console.print("[red]Invalid selection[/red]")
                except ValueError:
                    self.console.print("[red]Invalid input[/red]")
        except KeyboardInterrupt:
            self.console.print()
        
        return True
    
    def cmd_add_model(self, args: str) -> bool:
        """Add a new model configuration"""
        from ..config import ModelConfig  # Import locally to avoid circular imports if any
        
        self.console.print("\n[bold #ffb8d1]Add New Model Configuration[/bold #ffb8d1]")
        self.console.print("─" * 30)
        
        try:
            # interactive wizard
            base_url = Prompt.ask(
                "API Base URL",
                default="https://api.openai.com/v1"
            )
            
            api_key = Prompt.ask(
                "API Key (hidden)",
                password=True
            )
            
            model_name = Prompt.ask(
                "Model Identifier (e.g. gpt-4, claude-3-opus)",
                default="gpt-4"
            )
            
            display_name = Prompt.ask(
                "Display Name",
                default=model_name
            )

            max_tokens_str = Prompt.ask(
                "Max Context Tokens (Optional, default 128000)",
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
                 with self.console.status("[bold #ce93d8]Verifying connection...[/bold #ce93d8]"):
                     try:
                         from openai import OpenAI
                         client = OpenAI(
                             base_url=base_url,
                             api_key=api_key
                         )
                         # Try to list models to verify auth and availability
                         models = client.models.list()
                         model_ids = [m.id for m in models.data]
                         
                         self.console.print(f"[bold #a5d6a7]✓ Connection successful![/bold #a5d6a7]")
                         
                         # If the user entered a model name that exists, confirm it
                         if model_name in model_ids:
                             self.console.print(f"[bold #a5d6a7]✓ Model '{model_name}' found in provider list.[/bold #a5d6a7]")
                         else:
                             self.console.print(f"[yellow]! Model '{model_name}' not found in provider's list. Available: {', '.join(model_ids)}[/yellow]")
                             if Confirm.ask("Would you like to select a model from the list?", default=True):
                                 # Simple selection
                                 # (In a real app, use a fuzzy selector or list)
                                 pass 
                     except Exception as e:
                         self.console.print(f"[red]Verification failed: {str(e)}[/red]")
                         if not Confirm.ask("Save anyway?", default=False):
                             return True
 
            config_manager = self.app.get('config_manager')
            if config_manager:
                config_manager.add_model(new_model)
                self.console.print(f"\n[bold #a5d6a7]✓ Model '{display_name}' added successfully![/bold #a5d6a7]")
                
                # Ask to switch
                if Confirm.ask("Switch to this model now?", default=True):
                    config = config_manager.load()
                    # The new model is last
                    new_index = len(config.models) - 1
                    config_manager.set_active_model(new_index)
                    self.console.print("[bold #a5d6a7]Active model updated.[/bold #a5d6a7]")
                    
                    if self.app.get('reinit_agent'):
                        self.app['reinit_agent']()
            else:
                self.console.print("[red]Error: Config manager not found.[/red]")
                
        except KeyboardInterrupt:
            self.console.print("\n[yellow]Cancelled.[/yellow]")
            
        return True
    
    def cmd_search(self, args: str) -> bool:
        """Web search"""
        if not args:
            self.console.print("[yellow]Usage: /search <query>[/yellow]")
            return True
        
        from ..tools import WebSearchTool
        
        tool = WebSearchTool()
        with self.console.status(f"[bold #ce93d8]Searching: {args}...[/bold #ce93d8]"):
            result = tool.execute(query=args, max_results=5)
        
        if result.success:
            from rich.markdown import Markdown
            self.console.print(Markdown(result.output))
        else:
            self.console.print(f"[red]Search failed: {result.error}[/red]")
        
        return True
    
    def cmd_sessions(self, args: str) -> bool:
        """Session management"""
        session_manager = self.app.get('session_manager')
        if not session_manager:
            self.console.print("[red]Session manager not available[/red]")
            return True
        
        sessions = session_manager.list_sessions()
        current = session_manager.get_current_session()
        
        if not sessions:
            self.console.print("[dim #ce93d8]No sessions yet.[/dim #ce93d8]")
            return True
        
        table = Table(title="Sessions", box=box.ROUNDED, border_style="#ce93d8")
        table.add_column("#", style="dim")
        table.add_column("Name", style="bold #81d4fa")
        table.add_column("Messages")
        table.add_column("Updated")
        table.add_column("")
        
        for i, session in enumerate(sessions, 1):
            is_current = "*" if current and session.id == current.id else ""
            table.add_row(
                str(i),
                session.name,
                str(session.message_count),
                session.updated_at[:16].replace('T', ' '),
                is_current
            )
        
        self.console.print(table)
        
        self.console.print("\n[dim #ce93d8]Actions: (n)ew, (number) to load, (d) to delete[/dim #ce93d8]")
        
        try:
            choice = Prompt.ask("Action", default="")
            
            if choice.lower() == 'n':
                name = Prompt.ask("Session name", default="")
                session = session_manager.create_session(name or None)
                self.console.print(f"[bold #a5d6a7]Created session: {session.name}[/bold #a5d6a7]")
                
            elif choice.lower() == 'd':
                idx = Prompt.ask("Delete session #")
                try:
                    idx = int(idx) - 1
                    if 0 <= idx < len(sessions):
                        if Confirm.ask(f"Delete '{sessions[idx].name}'?"):
                            session_manager.delete_session(sessions[idx].id)
                            self.console.print("[bold #a5d6a7]Deleted[/bold #a5d6a7]")
                except ValueError:
                    pass
                    
            elif choice.isdigit():
                idx = int(choice) - 1
                if 0 <= idx < len(sessions):
                    session = session_manager.load_session(sessions[idx].id)
                    if session:
                        self.console.print(f"[bold #a5d6a7]Loaded: {session.name}[/bold #a5d6a7]")
                        # Update agent history
                        if self.app.get('agent'):
                            self.app['agent'].set_history(session.messages)
        except KeyboardInterrupt:
            self.console.print()
        
        return True
    
    def cmd_history(self, args: str) -> bool:
        """View conversation history"""
        agent = self.app.get('agent')
        if not agent:
            self.console.print("[red]Agent not available[/red]")
            return True
        
        limit = 999999
        if args:
            try:
                limit = int(args)
            except ValueError:
                pass
        
        history = agent.get_history()
        
        if not history:
            self.console.print("[dim #ce93d8]No conversation history yet.[/dim #ce93d8]")
            return True
        
        # Show all messages by default
        for msg in history[-limit:]:
            role = msg.get('role', 'unknown')
            content = msg.get('content', '')
            
            if role == 'user':
                self.console.print(f"\n[bold #81d4fa]You:[/bold #81d4fa] {escape(content)}")
            elif role == 'assistant':
                self.console.print(f"\n[bold #ffb8d1]Reverie:[/bold #ffb8d1] {escape(content)}")
            elif role == 'tool':
                self.console.print(f"\n[dim #ce93d8]Tool Result: {escape(content)}[/dim #ce93d8]")
        
        return True
    
    def cmd_clear(self, args: str) -> bool:
        """Clear the screen"""
        self.console.clear()
        return True
    
    def cmd_index(self, args: str) -> bool:
        """Re-index the codebase"""
        indexer = self.app.get('indexer')
        if not indexer:
            self.console.print("[red]Indexer not available[/red]")
            return True
        
        with self.console.status("[bold #ce93d8]Indexing codebase...[/bold #ce93d8]"):
            result = indexer.full_index()
        
        self.console.print(f"[bold #a5d6a7]Indexing complete![/bold #a5d6a7]")
        self.console.print(f"  Files scanned: {result.files_scanned}")
        self.console.print(f"  Files parsed: {result.files_parsed}")
        self.console.print(f"  Symbols: {result.symbols_extracted}")
        self.console.print(f"  Time: {result.total_time_ms:.0f}ms")
        
        if result.errors:
            self.console.print(f"\n[yellow]Errors ({len(result.errors)}):[/yellow]")
            for err in result.errors[:5]:
                self.console.print(f"  - {err}")
        
        return True
    
    def cmd_setting(self, args: str) -> bool:
        """Interactive settings menu with keyboard navigation"""
        import os
        import sys
        
        # We need msvcrt for Windows key detection
        try:
            import msvcrt
        except ImportError:
            self.console.print("[red]Keyboard navigation is only supported on Windows.[/red]")
            return True
            
        config_manager = self.app.get('config_manager')
        if not config_manager:
            return True
            
        config = config_manager.load()
        
        # Settings categories
        rules_manager = self.app.get('rules_manager')
        categories = [
            {"name": "Mode", "key": "mode", "options": ["reverie", "Reverie-Spec-driven", "spec-vibe"]},
            {"name": "Active Model", "key": "active_model_index", "options": list(range(len(config.models)))},
            {"name": "Theme", "key": "theme", "options": ["default", "dark", "light", "ocean"]},
            {"name": "Auto Index", "key": "auto_index", "options": [True, False]},
            {"name": "Rules", "key": "rules", "type": "text"}
        ]
        
        selected_cat_idx = 0
        
        from rich.live import Live
        from rich.panel import Panel
        from rich.layout import Layout
        from rich.align import Align
        
        def generate_settings_view(cat_idx, current_config):
            table = Table(box=box.SIMPLE, show_header=False)
            table.add_column("Category", style="bold #81d4fa", width=20)
            table.add_column("Value", style="bold #a5d6a7")
            
            for i, cat in enumerate(categories):
                marker = ">> " if i == cat_idx else "   "
                style = "bold #ffb8d1" if i == cat_idx else "white"
                
                name = cat["name"]
                key = cat["key"]
                
                if key == "rules":
                    val = rules_manager.get_rules_text() if rules_manager else ""
                else:
                    val = getattr(current_config, key)
                
                if key == "active_model_index":
                    display_val = current_config.models[val].model_display_name if current_config.models else "None"
                elif isinstance(val, bool):
                    display_val = "ON" if val else "OFF"
                elif key == "rules":
                    display_val = val.replace('\n', ' ')
                    if not val: display_val = "(empty) - Press Enter to edit"
                else:
                    display_val = str(val)
                
                if i == cat_idx:
                    table.add_row(f"{marker}{name}", f"[reverse] {display_val} [/reverse]", style=style)
                else:
                    table.add_row(f"{marker}{name}", display_val, style=style)
            
            help_text = "\n[dim #ce93d8]↑/↓: Navigate | ←/→: Change | Enter: Edit/Confirm | Esc: Exit[/dim #ce93d8]"
            return Panel(
                Align.center(table),
                title="[bold #ffb8d1]Reverie Settings[/bold #ffb8d1]",
                subtitle=help_text,
                border_style="#ce93d8",
                padding=(1, 2),
                box=box.ROUNDED
            )

        with Live(generate_settings_view(selected_cat_idx, config), refresh_per_second=10) as live:
            while True:
                if msvcrt.kbhit():
                    key = msvcrt.getch()
                    
                    if key == b'\x1b': # Esc
                        break
                    elif key == b'\r': # Enter
                        cat = categories[selected_cat_idx]
                        if cat["key"] == "rules":
                            live.stop()
                            self.console.print("\n[bold #ffb8d1]Edit Rules (One per line, empty line to finish):[/bold #ffb8d1]")
                            
                            # Clear existing rules if user wants to start over, 
                            # or just let them add. The prompt says "Edit Rules".
                            # Let's show current rules first.
                            current_rules = rules_manager.get_rules()
                            if current_rules:
                                self.console.print("[dim]Current rules:[/dim]")
                                for r in current_rules:
                                    self.console.print(f" - {r}")
                            
                            new_rules = []
                            while True:
                                line = input("> ").strip()
                                if not line: break
                                new_rules.append(line)
                            
                            if new_rules:
                                # Replace all rules for simplicity in this menu
                                rules_manager._rules = new_rules
                                rules_manager.save()
                                self.console.print("[bold #a5d6a7]Rules updated.[/bold #a5d6a7]")
                            live.start()
                        elif cat["key"] == "mode":
                             # Toggle mode
                             idx = (categories[selected_cat_idx]["options"].index(config.mode) + 1) % len(categories[selected_cat_idx]["options"])
                             config.mode = categories[selected_cat_idx]["options"][idx]
                             config_manager.save(config)
                        else:
                            pass
                            
                    elif key == b'\x00' or key == b'\xe0': # Special keys (arrows)
                        key = msvcrt.getch()
                        if key == b'H': # Up
                            selected_cat_idx = (selected_cat_idx - 1) % len(categories)
                        elif key == b'P': # Down
                            selected_cat_idx = (selected_cat_idx + 1) % len(categories)
                        elif key == b'K': # Left
                            cat = categories[selected_cat_idx]
                            if "options" in cat:
                                cur_val = getattr(config, cat["key"])
                                opts = cat["options"]
                                cur_idx = opts.index(cur_val)
                                new_idx = (cur_idx - 1) % len(opts)
                                setattr(config, cat["key"], opts[new_idx])
                                config_manager.save(config)
                        elif key == b'M': # Right
                            cat = categories[selected_cat_idx]
                            if "options" in cat:
                                cur_val = getattr(config, cat["key"])
                                opts = cat["options"]
                                cur_idx = opts.index(cur_val)
                                new_idx = (cur_idx + 1) % len(opts)
                                setattr(config, cat["key"], opts[new_idx])
                                config_manager.save(config)
                    
                    live.update(generate_settings_view(selected_cat_idx, config))
                
                time.sleep(0.01)

        # Apply changes to running app
        if self.app.get('reinit_agent'):
            self.app['reinit_agent']()
            
        self.console.print("[bold #a5d6a7]Settings saved and applied.[/bold #a5d6a7]")
        return True
    
    def cmd_rules(self, args: str) -> bool:
        """Manage custom rules"""
        rules_manager = self.app.get('rules_manager')
        if not rules_manager:
            self.console.print("[red]Rules manager not available[/red]")
            return True
            
        args = args.strip()
        parts = args.split(maxsplit=1)
        action = parts[0].lower() if parts else "list"
        
        if action == "list":
            rules = rules_manager.get_rules()
            if not rules:
                self.console.print("[dim #ce93d8]No custom rules defined.[/dim #ce93d8]")
            else:
                table = Table(title="Custom Rules", box=box.ROUNDED, border_style="#ce93d8")
                table.add_column("#", style="dim", width=4)
                table.add_column("Rule", style="white")
                
                for i, rule in enumerate(rules, 1):
                    table.add_row(str(i), rule)
                
                self.console.print(table)
                self.console.print("[dim #ce93d8]Use '/rules add <text>' or '/rules remove <#>' to manage.[/dim #ce93d8]")
                
        elif action == "add":
            if len(parts) < 2:
                # Interactive add
                self.console.print("[bold #ffb8d1]Add New Rule[/bold #ffb8d1]")
                self.console.print("[dim #ce93d8]Enter the rule text below (single line):[/dim #ce93d8]")
                rule_text = Prompt.ask(">")
            else:
                rule_text = parts[1]
                
            if rule_text.strip():
                rules_manager.add_rule(rule_text.strip())
                self.console.print("[bold #a5d6a7]Rule added.[/bold #a5d6a7]")
                # Reinit agent to apply changes
                if self.app.get('reinit_agent'):
                    self.app['reinit_agent']()
            else:
                self.console.print("[yellow]Empty rule text.[/yellow]")
                
        elif action == "remove" or action == "delete":
            if len(parts) < 2:
                self.console.print("[yellow]Usage: /rules remove <number>[/yellow]")
                return True
                
            try:
                idx = int(parts[1]) - 1
                rules = rules_manager.get_rules()
                if 0 <= idx < len(rules):
                    if Confirm.ask(f"Remove rule: '{rules[idx]}'?"):
                        rules_manager.remove_rule(idx)
                        self.console.print("[bold #a5d6a7]Rule removed.[/bold #a5d6a7]")
                        # Reinit agent to apply changes
                        if self.app.get('reinit_agent'):
                            self.app['reinit_agent']()
                else:
                    self.console.print("[red]Invalid rule number.[/red]")
            except ValueError:
                self.console.print("[red]Invalid index format.[/red]")
                
        else:
            self.console.print(f"[red]Unknown action: {action}[/red]")
            self.console.print("Usage: /rules [list|add|remove]")
            
        return True

    def cmd_exit(self, args: str) -> bool:
        """Exit the application"""
        if Confirm.ask("Exit Reverie?", default=True):
            return False
        return True