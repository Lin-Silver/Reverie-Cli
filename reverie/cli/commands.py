"""
Command Handler - Process CLI commands with Dreamscape Theme

Handles all commands starting with / with dreamy pink-purple-blue aesthetics
"""

from typing import Optional, Callable, Dict, Any
from pathlib import Path
import time

from rich.console import Console
from rich.table import Table
from rich.prompt import Prompt, Confirm
from rich.panel import Panel
from rich.text import Text
from rich.align import Align
from rich.columns import Columns
from rich.padding import Padding
from rich import box
from rich.markup import escape

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
            'rollback': self.cmd_rollback,
            'undo': self.cmd_undo,
            'redo': self.cmd_redo,
            'checkpoints': self.cmd_checkpoints,
            'operations': self.cmd_operations,
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
            self.console.print(f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} Unknown command: /{cmd}[/{self.theme.CORAL_SOFT}]")
            self.console.print(f"[{self.theme.TEXT_DIM}]Type /help for available commands.[/{self.theme.TEXT_DIM}]")
            return True
    
    def cmd_help(self, args: str) -> bool:
        """Show detailed help with beautiful dreamy formatting"""
        
        # Main title with sparkles
        self.console.print()
        title_panel = Panel(
            f"[bold {self.theme.PINK_SOFT}]{self.deco.SPARKLE} Reverie CLI - Command Help {self.deco.SPARKLE}[/bold {self.theme.PINK_SOFT}]\n"
            f"[{self.theme.PURPLE_MEDIUM}]World-class context engine coding assistant[/{self.theme.PURPLE_MEDIUM}]",
            border_style=self.theme.BORDER_PRIMARY,
            padding=(0, 2),
            box=box.ROUNDED
        )
        self.console.print(title_panel)
        self.console.print()
        
        # Basic commands
        basic_commands = Table(
            title=f"[bold {self.theme.PINK_SOFT}]{self.deco.DIAMOND} Basic Commands[/bold {self.theme.PINK_SOFT}]",
            box=box.ROUNDED,
            border_style=self.theme.BORDER_PRIMARY,
            show_lines=True,
            title_justify="left"
        )
        basic_commands.add_column("Command", style=f"bold {self.theme.BLUE_SOFT}", width=15)
        basic_commands.add_column("Description", style=self.theme.TEXT_SECONDARY)
        basic_commands.add_column("Example", style=f"dim {self.theme.MINT_SOFT}")
        
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
            title=f"[bold {self.theme.PINK_SOFT}]{self.deco.DIAMOND} Models & Settings[/bold {self.theme.PINK_SOFT}]",
            box=box.ROUNDED,
            border_style=self.theme.BORDER_PRIMARY,
            show_lines=True,
            title_justify="left"
        )
        config_commands.add_column("Command", style=f"bold {self.theme.BLUE_SOFT}", width=15)
        config_commands.add_column("Description", style=self.theme.TEXT_SECONDARY)
        config_commands.add_column("Example", style=f"dim {self.theme.MINT_SOFT}")
        
        config_commands.add_row(
            "/model",
            f"Model manager:\n{self.deco.DOT_MEDIUM} List configured models\n{self.deco.DOT_MEDIUM} Switch active model\n{self.deco.DOT_MEDIUM} Add model: /model add\n{self.deco.DOT_MEDIUM} Delete: /model delete <#>",
            "/model\n/model add\n/model delete 2"
        )
        config_commands.add_row(
            "/setting",
            f"Interactive settings menu:\n{self.deco.DOT_MEDIUM} Mode (reverie/spec-driven/spec-vibe)\n{self.deco.DOT_MEDIUM} Theme\n{self.deco.DOT_MEDIUM} Custom rules\n{self.deco.DOT_MEDIUM} Auto-index toggle",
            "/setting"
        )
        config_commands.add_row(
            "/rules",
            f"Manage custom rules:\n{self.deco.DOT_MEDIUM} List rules\n{self.deco.DOT_MEDIUM} Edit rules.txt: /rules edit\n{self.deco.DOT_MEDIUM} Add rule: /rules add <text>\n{self.deco.DOT_MEDIUM} Remove: /rules remove <#>",
            "/rules\n/rules edit\n/rules add Always use async\n/rules remove 1"
        )
        
        self.console.print(config_commands)
        self.console.print()
        
        # Tools and features
        tool_commands = Table(
            title=f"[bold {self.theme.PINK_SOFT}]{self.deco.DIAMOND} Tools & Features[/bold {self.theme.PINK_SOFT}]",
            box=box.ROUNDED,
            border_style=self.theme.BORDER_PRIMARY,
            show_lines=True,
            title_justify="left"
        )
        tool_commands.add_column("Command", style=f"bold {self.theme.BLUE_SOFT}", width=15)
        tool_commands.add_column("Description", style=self.theme.TEXT_SECONDARY)
        tool_commands.add_column("Example", style=f"dim {self.theme.MINT_SOFT}")
        
        tool_commands.add_row(
            "/search <q>",
            "Web search (DuckDuckGo) for docs and answers. Results show in Markdown.",
            "/search rust async patterns\n/search python FastAPI"
        )
        tool_commands.add_row(
            "/tools",
            f"List available tools the AI can use:\n{self.deco.DOT_MEDIUM} Read/write files\n{self.deco.DOT_MEDIUM} Run commands\n{self.deco.DOT_MEDIUM} Search code\n{self.deco.DOT_MEDIUM} Git actions, etc.",
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
            title=f"[bold {self.theme.PINK_SOFT}]{self.deco.DIAMOND} Session Management[/bold {self.theme.PINK_SOFT}]",
            box=box.ROUNDED,
            border_style=self.theme.BORDER_PRIMARY,
            show_lines=True,
            title_justify="left"
        )
        session_commands.add_column("Command", style=f"bold {self.theme.BLUE_SOFT}", width=15)
        session_commands.add_column("Description", style=self.theme.TEXT_SECONDARY)
        session_commands.add_column("Example", style=f"dim {self.theme.MINT_SOFT}")
        
        session_commands.add_row(
            "/sessions",
            f"Manage conversation sessions:\n{self.deco.DOT_MEDIUM} List history\n{self.deco.DOT_MEDIUM} Load previous\n{self.deco.DOT_MEDIUM} Create new\n{self.deco.DOT_MEDIUM} Delete old",
            "/sessions"
        )
        session_commands.add_row(
            "/history [n]",
            "Show conversation history. Display the last n messages (default 10).",
            "/history\n/history 20"
        )
        session_commands.add_row(
            "/rollback",
            f"Rollback to previous state:\n{self.deco.DOT_MEDIUM} Rollback to previous question\n{self.deco.DOT_MEDIUM} Rollback to previous tool call\n{self.deco.DOT_MEDIUM} Rollback to specific checkpoint",
            "/rollback question\n/rollback tool\n/rollback <id>"
        )
        session_commands.add_row(
            "/undo",
            "Undo the last rollback operation.",
            "/undo"
        )
        session_commands.add_row(
            "/redo",
            "Redo the last undone rollback operation.",
            "/redo"
        )
        session_commands.add_row(
            "/checkpoints",
            f"Interactive checkpoint manager:\n{self.deco.DOT_MEDIUM} Browse checkpoints with arrow keys\n{self.deco.DOT_MEDIUM} Select to restore\n{self.deco.DOT_MEDIUM} View checkpoint details",
            "/checkpoints"
        )
        session_commands.add_row(
            "/operations",
            "Show operation history and statistics.",
            "/operations"
        )
        
        self.console.print(session_commands)
        self.console.print()
        
        # Quick tips with dreamy panel
        tips = Panel(
            f"[bold {self.theme.PURPLE_MEDIUM}]{self.deco.SPARKLE} Tips[/bold {self.theme.PURPLE_MEDIUM}]\n\n"
            f"[{self.theme.PINK_SOFT}]{self.deco.CHEVRON_RIGHT} Input[/{self.theme.PINK_SOFT}]  Type questions or requests directly; the AI will respond.\n"
            f"[{self.theme.PINK_SOFT}]{self.deco.CHEVRON_RIGHT} Multi-line[/{self.theme.PINK_SOFT}]  Use a trailing \\ or triple quotes to enter multi-line text.\n"
            f"[{self.theme.PINK_SOFT}]{self.deco.CHEVRON_RIGHT} Interrupt[/{self.theme.PINK_SOFT}]  Ctrl+C once cancels input; twice exits the program.\n"
            f"[{self.theme.PINK_SOFT}]{self.deco.CHEVRON_RIGHT} History[/{self.theme.PINK_SOFT}]  Use ↑/↓ to browse input history.\n"
            f"[{self.theme.PINK_SOFT}]{self.deco.CHEVRON_RIGHT} Completion[/{self.theme.PINK_SOFT}]  Type /command to see available completions.",
            border_style=self.theme.BORDER_PRIMARY,
            padding=(0, 2),
            box=box.ROUNDED
        )
        self.console.print(tips)
        self.console.print()
        
        return True
    
    def cmd_tools(self, args: str) -> bool:
        """List available tools with dreamy styling"""
        agent = self.app.get('agent')
        if not agent:
            self.console.print(f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} Agent not initialized[/{self.theme.CORAL_SOFT}]")
            return True
            
        tools = agent.tool_executor._tools
        
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

    def cmd_status(self, args: str) -> bool:
        """Show current status with dreamy styling"""
        config_manager = self.app.get('config_manager')
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
                     config = config_manager.load()
                     max_tokens = getattr(config, 'max_context_tokens', 128000)

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
        
        if not sessions:
            self.console.print(f"[{self.theme.TEXT_DIM}]{self.deco.DOT_MEDIUM} No sessions yet.[/{self.theme.TEXT_DIM}]")
            return True
        
        table = Table(
            title=f"[bold {self.theme.PINK_SOFT}]{self.deco.CRYSTAL} Sessions[/bold {self.theme.PINK_SOFT}]",
            box=box.ROUNDED,
            border_style=self.theme.BORDER_PRIMARY
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
        
        self.console.print(f"\n[{self.theme.TEXT_DIM}]{self.deco.DOT_MEDIUM} Actions: (n)ew, (number) to load, (d) to delete[/{self.theme.TEXT_DIM}]")
        
        try:
            choice = Prompt.ask(f"[{self.theme.PURPLE_SOFT}]Action[/{self.theme.PURPLE_SOFT}]", default="")
            
            if choice.lower() == 'n':
                name = Prompt.ask(f"[{self.theme.BLUE_SOFT}]{self.deco.CHEVRON_RIGHT}[/{self.theme.BLUE_SOFT}] Session name", default="")
                session = session_manager.create_session(name or None)
                self.console.print(f"[{self.theme.MINT_VIBRANT}]{self.deco.CHECK_FANCY} Created session: {session.name}[/{self.theme.MINT_VIBRANT}]")
                
            elif choice.lower() == 'd':
                idx = Prompt.ask(f"[{self.theme.PURPLE_SOFT}]Delete session #[/{self.theme.PURPLE_SOFT}]")
                try:
                    idx = int(idx) - 1
                    if 0 <= idx < len(sessions):
                        if Confirm.ask(f"Delete '{sessions[idx].name}'?"):
                            session_manager.delete_session(sessions[idx].id)
                            self.console.print(f"[{self.theme.MINT_VIBRANT}]{self.deco.CHECK_FANCY} Deleted[/{self.theme.MINT_VIBRANT}]")
                except ValueError:
                    pass
                    
            elif choice.isdigit():
                idx = int(choice) - 1
                if 0 <= idx < len(sessions):
                    session = session_manager.load_session(sessions[idx].id)
                    if session:
                        self.console.print(f"[{self.theme.MINT_VIBRANT}]{self.deco.CHECK_FANCY} Loaded: {session.name}[/{self.theme.MINT_VIBRANT}]")
                        # Update agent history
                        if self.app.get('agent'):
                            self.app['agent'].set_history(session.messages)
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
        """Interactive settings menu with keyboard navigation and dreamy styling"""
        import os
        import sys
        
        # We need msvcrt for Windows key detection
        try:
            import msvcrt
        except ImportError:
            self.console.print(f"[{self.theme.CORAL_SOFT}]{self.deco.CROSS} Keyboard navigation is only supported on Windows.[/{self.theme.CORAL_SOFT}]")
            return True
            
        config_manager = self.app.get('config_manager')
        if not config_manager:
            return True
            
        config = config_manager.load()
        
        # Settings categories
        rules_manager = self.app.get('rules_manager')
        categories = [
            {"name": "Mode", "key": "mode", "options": ["reverie", "Reverie-ant", "Reverie-Spec-driven", "spec-vibe", "writer"]},
            {"name": "Active Model", "key": "active_model_index", "options": list(range(len(config.models)))},
            {"name": "Theme", "key": "theme", "options": ["default", "dark", "light", "ocean"]},
            {"name": "Auto Index", "key": "auto_index", "options": [True, False]},
            {"name": "Status Line", "key": "show_status_line", "options": [True, False]},
            {"name": "Rules", "key": "rules", "type": "text"}
        ]
        
        selected_cat_idx = 0
        
        from rich.live import Live
        from rich.layout import Layout
        
        def generate_settings_view(cat_idx, current_config):
            table = Table(box=box.SIMPLE, show_header=False)
            table.add_column("Category", style=f"bold {self.theme.BLUE_SOFT}", width=20)
            table.add_column("Value", style=f"bold {self.theme.MINT_SOFT}")
            
            for i, cat in enumerate(categories):
                marker = f"{self.deco.CHEVRON_RIGHT} " if i == cat_idx else "   "
                style = f"bold {self.theme.PINK_SOFT}" if i == cat_idx else self.theme.TEXT_SECONDARY
                
                name = cat["name"]
                key = cat["key"]
                
                if key == "rules":
                    val = rules_manager.get_rules_text() if rules_manager else ""
                else:
                    val = getattr(current_config, key)
                
                if key == "active_model_index":
                    display_val = current_config.models[val].model_display_name if current_config.models else "None"
                elif isinstance(val, bool):
                    display_val = f"[{self.theme.MINT_SOFT}]ON[/{self.theme.MINT_SOFT}]" if val else f"[{self.theme.TEXT_DIM}]OFF[/{self.theme.TEXT_DIM}]"
                elif key == "rules":
                    display_val = val.replace('\n', ' ')
                    if not val: display_val = f"[{self.theme.TEXT_DIM}](empty) - Press Enter to edit[/{self.theme.TEXT_DIM}]"
                else:
                    display_val = str(val)
                
                if i == cat_idx:
                    table.add_row(f"[{self.theme.PINK_SOFT}]{marker}{name}[/{self.theme.PINK_SOFT}]", f"[reverse] {display_val} [/reverse]", style=style)
                else:
                    table.add_row(f"{marker}{name}", display_val, style=style)
            
            help_text = (
                f"\n[{self.theme.TEXT_DIM}]{self.deco.DOT_MEDIUM} ↑/↓: Navigate "
                f"{self.deco.DOT_MEDIUM} ←/→: Change "
                f"{self.deco.DOT_MEDIUM} Enter: Edit/Confirm "
                f"{self.deco.DOT_MEDIUM} Esc: Exit[/{self.theme.TEXT_DIM}]"
            )
            return Panel(
                Align.center(table),
                title=f"[bold {self.theme.PINK_SOFT}]{self.deco.SPARKLE} Reverie Settings {self.deco.SPARKLE}[/bold {self.theme.PINK_SOFT}]",
                subtitle=help_text,
                border_style=self.theme.BORDER_PRIMARY,
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
                            self.console.print(f"\n[bold {self.theme.PINK_SOFT}]{self.deco.SPARKLE} Edit Rules (One per line, empty line to finish):[/bold {self.theme.PINK_SOFT}]")
                            
                            # Clear existing rules if user wants to start over, 
                            # or just let them add. The prompt says "Edit Rules".
                            # Let's show current rules first.
                            current_rules = rules_manager.get_rules()
                            if current_rules:
                                self.console.print(f"[{self.theme.TEXT_DIM}]Current rules:[/{self.theme.TEXT_DIM}]")
                                for r in current_rules:
                                    self.console.print(f" [{self.theme.PURPLE_SOFT}]{self.deco.DOT_MEDIUM}[/{self.theme.PURPLE_SOFT}] {r}")
                            
                            new_rules = []
                            while True:
                                line = input(f"{self.deco.CHEVRON_RIGHT} ").strip()
                                if not line: break
                                new_rules.append(line)
                            
                            if new_rules:
                                # Replace all rules for simplicity in this menu
                                rules_manager._rules = new_rules
                                rules_manager.save()
                                self.console.print(f"[{self.theme.MINT_VIBRANT}]{self.deco.CHECK_FANCY} Rules updated.[/{self.theme.MINT_VIBRANT}]")
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
            
        self.console.print(f"[{self.theme.MINT_VIBRANT}]{self.deco.CHECK_FANCY} Settings saved and applied.[/{self.theme.MINT_VIBRANT}]")
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

    def cmd_exit(self, args: str) -> bool:
        """Exit the application with styled prompt"""
        if Confirm.ask(f"[{self.theme.PURPLE_SOFT}]Exit Reverie?[/{self.theme.PURPLE_SOFT}]", default=True):
            return False
        return True