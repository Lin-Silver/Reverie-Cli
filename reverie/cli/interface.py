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
from pathlib import Path
from typing import Optional, List

from rich.console import Console, Group
from rich.prompt import Prompt, Confirm
from rich.live import Live
from rich.panel import Panel
from rich.text import Text
from rich.markup import escape
from rich import box

from .display import DisplayComponents
from .commands import CommandHandler
from .input_handler import InputHandler
from .markdown_formatter import format_markdown
from .theme import THEME, DECO, DREAM
from ..config import ConfigManager, ModelConfig, Config
from ..rules_manager import RulesManager
from ..session import SessionManager
from ..agent import ReverieAgent
from ..context_engine import CodebaseIndexer, ContextRetriever, GitIntegration


class StatusLine:
    """Dynamic status line that updates on every render with dreamy styling"""
    def __init__(self, interface):
        self.interface = interface
    
    def __rich__(self):
        return self.interface._get_status_line()


class ReverieInterface:
    """Main interactive interface for Reverie Cli with Dreamscape theme"""
    
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.console = Console(width=None, force_terminal=True)  # Auto-detect width and force terminal mode
        self.display = DisplayComponents(self.console)
        self.theme = THEME
        self.deco = DECO
        
        # Initialize managers
        self.config_manager = ConfigManager(project_root)
        self.config_manager.ensure_dirs()
        self.rules_manager = RulesManager(project_root)
        
        self.project_data_dir = self.config_manager.project_data_dir
        self.session_manager = SessionManager(self.project_data_dir)
        
        self.indexer: Optional[CodebaseIndexer] = None
        self.retriever: Optional[ContextRetriever] = None
        self.git_integration: Optional[GitIntegration] = None
        self.agent: Optional[ReverieAgent] = None
        
        self.total_active_time = 0.0
        self.current_task_start: Optional[float] = None
        self.start_time = time.time()
        self.command_handler: Optional[CommandHandler] = None
        self.input_handler: Optional[InputHandler] = None
        self.status_line = StatusLine(self)
    
    def run(self) -> None:
        """Main entry point"""
        try:
            # Clear terminal completely including scrollback history
            import os
            import sys
            
            if os.name == 'nt':  # Windows
                # Try multiple methods to clear Windows terminal
                try:
                    # Method 1: Standard cls command
                    os.system('cls')
                except:
                    pass
                
                try:
                    # Method 2: PowerShell clear-host
                    os.system('clear-host')
                except:
                    pass
                
                try:
                    # Method 3: ANSI escape sequences for modern terminals
                    print('\033[2J\033[3J\033[H', end='', flush=True)
                except:
                    pass
                
                # Method 4: Additional clear for stubborn terminals
                try:
                    sys.stdout.write('\033c')
                    sys.stdout.flush()
                except:
                    pass
            else:  # Unix/Linux/Mac
                # Clear screen and scrollback buffer
                print('\033[2J\033[3J\033[H', end='', flush=True)
            
            # Final Rich console clear
            self.console.clear()
            
            if not self.config_manager.is_configured():
                self.run_setup_wizard()
            
            config = self.config_manager.load()
            self.display.show_welcome(mode=config.mode)
            
            self._init_context_engine()
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

    def _get_status_line(self) -> Text:
        """Generate a dreamy status line for real-time display"""
        elapsed = self.total_active_time
        if self.current_task_start:
            elapsed += (time.time() - self.current_task_start)
            
        hours, remainder = divmod(int(elapsed), 3600)
        minutes, seconds = divmod(remainder, 60)
        time_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        
        config = self.config_manager.load()
        model_name = config.active_model.model_display_name if config.active_model else "N/A"
        mode = config.mode or "reverie"
        
        # Dreamscape styled status line
        return Text.from_markup(
            f"[{self.theme.PURPLE_MEDIUM}]{self.deco.LINE_HORIZONTAL * 2}[/{self.theme.PURPLE_MEDIUM}] "
            f"[{self.theme.PINK_SOFT}]{self.deco.SPARKLE}[/{self.theme.PINK_SOFT}] "
            f"[bold {self.theme.TEXT_PRIMARY}]{time_str}[/bold {self.theme.TEXT_PRIMARY}] "
            f"[{self.theme.TEXT_DIM}]{self.deco.DOT_MEDIUM}[/{self.theme.TEXT_DIM}] "
            f"[{self.theme.PURPLE_SOFT}]{model_name}[/{self.theme.PURPLE_SOFT}] "
            f"[{self.theme.TEXT_DIM}]{self.deco.DOT_MEDIUM}[/{self.theme.TEXT_DIM}] "
            f"[bold {self.theme.BLUE_SOFT}]{mode.upper()}[/bold {self.theme.BLUE_SOFT}] "
            f"[{self.theme.PINK_SOFT}]{self.deco.SPARKLE}[/{self.theme.PINK_SOFT}] "
            f"[{self.theme.PURPLE_MEDIUM}]{self.deco.LINE_HORIZONTAL * 2}[/{self.theme.PURPLE_MEDIUM}]"
        )

    def main_loop(self) -> None:
        """Main interaction loop"""
        self.input_handler = InputHandler(self.console)
        
        while True:
            try:
                user_input = self.input_handler.interactive_input("Reverie> ")
                
                if user_input is None: 
                    break 
                if not user_input.strip(): 
                    continue
                
                if user_input.strip().startswith('/'):
                    should_continue = self.command_handler.handle(user_input.strip())
                    if not should_continue: 
                        break
                    continue
                
                self._process_message(user_input)
                
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
        self.console.print(f"\n[bold {self.theme.PINK_SOFT}]{self.deco.SPARKLE} Session saved. Goodbye! {self.deco.SPARKLE}[/bold {self.theme.PINK_SOFT}]")
    
    def _process_message(self, message: str) -> None:
        """Process message with direct streaming output to avoid truncation"""
        if not self.agent: return

        self.current_task_start = time.time()
        config = self.config_manager.load()
        
        try:
            current_markdown_text = ""
            first_non_tool_chunk = True
            
            # Create live display for status line if enabled
            status_live = None
            if config.show_status_line:
                from rich.live import Live
                status_live = Live(self.status_line, console=self.console, refresh_per_second=1, transient=True)
                status_live.start()
            
            try:
                for chunk in self.agent.process_message(message, stream=config.stream_responses):
                    # Check for tool/system markers
                    if chunk.startswith('\n[') or chunk.startswith('['):
                        # Flush pending markdown
                        if current_markdown_text:
                            self.console.print(format_markdown(current_markdown_text), end="")
                            current_markdown_text = ""
                        # Add tool output directly
                        self.console.print(Text.from_markup(chunk))
                    else:
                        # Add "Reverie:" prefix for first non-tool chunk
                        if first_non_tool_chunk and chunk.strip():
                            # Add prefix before the first meaningful content with dreamy styling
                            self.console.print(
                                f"[bold {self.theme.PINK_SOFT}]{self.deco.SPARKLE}[/bold {self.theme.PINK_SOFT}] "
                                f"[bold {self.theme.PURPLE_SOFT}]Reverie:[/bold {self.theme.PURPLE_SOFT}]"
                            )
                            first_non_tool_chunk = False
                        
                        # Accumulate content
                        current_markdown_text += chunk
                
                # Final flush - print all accumulated content
                if current_markdown_text.strip():
                    self.console.print(format_markdown(current_markdown_text))
            
            finally:
                # Stop live display
                if status_live:
                    status_live.stop()
                
        except KeyboardInterrupt:
            self.console.print(f"\n[{self.theme.TEXT_DIM}]{self.deco.DOT_MEDIUM} Process interrupted by user[/{self.theme.TEXT_DIM}]")
        except Exception as e:
            self.console.print(f"\n[bold {self.theme.CORAL_VIBRANT}]{self.deco.CROSS_FANCY} Error: {escape(str(e))}[/bold {self.theme.CORAL_VIBRANT}]")
            # Don't re-raise the exception to prevent app from stopping
        finally:
            if self.current_task_start:
                self.total_active_time += (time.time() - self.current_task_start)
                self.current_task_start = None
            if self.agent:
                try:
                    self.session_manager.update_messages(self.agent.get_history())
                except Exception as session_error:
                    self.console.print(f"\n[{self.theme.AMBER_GLOW}]{self.deco.DOT_MEDIUM} Warning: Failed to save session: {session_error}[/{self.theme.AMBER_GLOW}]")
        
        # Display updated status line after processing if enabled
        if config.show_status_line:
            self.console.print(self.status_line)
        self.console.print() # Final spacer for prompt

    def _init_context_engine(self) -> None:
        cache_dir = self.config_manager.project_data_dir / 'context_cache'
        self.console.print(f"[{self.theme.TEXT_DIM}]{self.deco.DOT_MEDIUM} Initializing Context Engine...[/{self.theme.TEXT_DIM}]")
        self.indexer = CodebaseIndexer(project_root=self.project_root, cache_dir=cache_dir)
        self.git_integration = GitIntegration(self.project_root)
        config = self.config_manager.load()
        from ..context_engine.cache import CacheManager
        cache_manager = CacheManager(cache_dir)
        cached = cache_manager.load()
        if cached:
            self.indexer.symbol_table = cached['symbol_table']
            self.indexer.dependency_graph = cached['dependency_graph']
            self.indexer._file_info = cached['file_info']
        elif config.auto_index:
            with self.console.status(f"[{self.theme.PURPLE_SOFT}]{self.deco.SPARKLE} Indexing...[/{self.theme.PURPLE_SOFT}]"):
                self.indexer.full_index()
        self.retriever = ContextRetriever(self.indexer.symbol_table, self.indexer.dependency_graph, self.project_root)

    def _init_agent(self) -> None:
        config = self.config_manager.load()
        model = config.active_model
        if not model: return

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
            self.console.print(f"[{self.theme.MINT_VIBRANT}]{self.deco.CHECK_FANCY} Config updated.[/{self.theme.MINT_VIBRANT}]")

        self.agent = ReverieAgent(
            base_url=model.base_url, api_key=model.api_key, model=model.model,
            model_display_name=model.model_display_name, project_root=self.project_root,
            retriever=self.retriever, indexer=self.indexer, git_integration=self.git_integration,
            additional_rules=self.rules_manager.get_rules_text(),
            mode=config.mode or "reverie"
        )
        self.agent.config = config
        # Also inject config_manager into tool context for context threshold check
        self.agent.tool_executor.update_context('config_manager', self.config_manager)
        self.console.print(f"[{self.theme.MINT_VIBRANT}]{self.deco.CHECK_FANCY}[/{self.theme.MINT_VIBRANT}] [{self.theme.MINT_SOFT}]Agent ready ({model.model_display_name})[/{self.theme.MINT_SOFT}]")

    def _init_session(self) -> None:
        session = self.session_manager.create_session()
        self.console.print(f"[{self.theme.MINT_VIBRANT}]{self.deco.CHECK_FANCY}[/{self.theme.MINT_VIBRANT}] [{self.theme.MINT_SOFT}]New session: {session.name}[/{self.theme.MINT_SOFT}]")

    def _get_app_context(self) -> dict:
        return {
            'config_manager': self.config_manager, 'rules_manager': self.rules_manager,
            'session_manager': self.session_manager, 'indexer': self.indexer,
            'retriever': self.retriever, 'git_integration': self.git_integration,
            'agent': self.agent, 'start_time': self.start_time, 
            'total_active_time': self.total_active_time,
            'current_task_start': self.current_task_start,
            'reinit_agent': self._init_agent
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
