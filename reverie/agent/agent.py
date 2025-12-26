"""
Reverie Agent - The AI core

This is the main agent class that:
- Manages conversation with the LLM
- Handles tool calls
- Integrates with Context Engine
- Supports both streaming and non-streaming modes
"""

from typing import List, Dict, Any, Optional, Generator, AsyncGenerator
from pathlib import Path
import json
import time

from rich.markup import escape as rich_escape

from .system_prompt import build_system_prompt
from .tool_executor import ToolExecutor
from ..tools.base import ToolResult


class ReverieAgent:
    """
    The Reverie AI Agent.
    
    Uses OpenAI SDK for API interaction and integrates deeply
    with the Context Engine for reduced hallucinations.
    """
    
    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        model_display_name: Optional[str] = None,
        project_root: Optional[Path] = None,
        retriever=None,
        indexer=None,
        git_integration=None,
        additional_rules: str = "",
        mode: str = "reverie"
    ):
        self.base_url = base_url
        self.api_key = api_key
        self.model = model
        self.model_display_name = model_display_name or model
        self.project_root = project_root or Path.cwd()
        self.additional_rules = additional_rules
        self.mode = mode
        
        # Initialize OpenAI client
        self._client = None
        self._init_client()
        
        # Initialize tool executor
        self.tool_executor = ToolExecutor(
            project_root=self.project_root,
            retriever=retriever,
            indexer=indexer,
            git_integration=git_integration
        )
        # Inject agent instance into tool context
        self.tool_executor.update_context('agent', self)
        
        # Conversation history
        self.messages: List[Dict] = []
        
        self.system_prompt = build_system_prompt(
            model_name=self.model_display_name,
            additional_rules=additional_rules,
            mode=self.mode
        )

    def update_mode(self, mode: str) -> None:
        """Update the agent's mode and rebuild the system prompt"""
        self.mode = mode
        self.system_prompt = build_system_prompt(
            model_name=self.model_display_name,
            additional_rules=self.additional_rules,
            mode=self.mode
        )
    
    def _init_client(self) -> None:
        """Initialize OpenAI client"""
        try:
            from openai import OpenAI
            self._client = OpenAI(
                base_url=self.base_url,
                api_key=self.api_key
            )
        except ImportError:
            raise ImportError(
                "OpenAI SDK not installed. Run: pip install openai"
            )
    
    def set_context_engine(self, retriever, indexer, git_integration) -> None:
        """Update Context Engine references"""
        self.tool_executor = ToolExecutor(
            project_root=self.project_root,
            retriever=retriever,
            indexer=indexer,
            git_integration=git_integration
        )
    
    def _build_messages(self) -> List[Dict]:
        """Build message list for API call"""
        messages = [{"role": "system", "content": self.system_prompt}]
        messages.extend(self.messages)
        return messages
    
    def process_message(
        self,
        user_message: str,
        stream: bool = True
    ) -> Generator[str, None, None]:
        """
        Process a user message and yield responses.
        
        Args:
            user_message: The user's input
            stream: Whether to stream the response
        
        Yields:
            Response chunks (or full response if not streaming)
        """
        # Add user message to history
        self.messages.append({
            "role": "user",
            "content": user_message
        })
        
        # Check for context threshold (60%)
        # Injected as a hidden system prompt update or a message
        token_estimate = self.get_token_estimate()
        
        # Get max tokens from config or active model
        max_tokens = 128000
        config_manager = self.tool_executor.context.get('config_manager')
        if config_manager:
            model_config = config_manager.get_active_model()
            if model_config and model_config.max_context_tokens:
                max_tokens = model_config.max_context_tokens
            else:
                config = config_manager.load()
                max_tokens = getattr(config, 'max_context_tokens', 128000)
        elif hasattr(self, 'config'):
            max_tokens = getattr(self.config, 'max_context_tokens', 128000)
        
        # Call model with tools
        try:
            if stream:
                yield from self._process_streaming()
            else:
                response = self._process_non_streaming()
                yield response
        except Exception as e:
            error_msg = f"Error processing message: {str(e)}"
            yield error_msg
    
    def _process_streaming(self) -> Generator[str, None, None]:
        """Process with streaming response"""
        messages = self._build_messages()
        tools = self.tool_executor.get_tool_schemas(mode=self.mode)
        
        while True:
            response = self._client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=tools if tools else None,
                stream=True
            )
            
            # Collect streamed response
            collected_content = ""
            collected_tool_calls = []
            current_tool_call = None
            
            for chunk in response:
                delta = chunk.choices[0].delta if chunk.choices else None
                
                if delta is None:
                    continue
                
                # Content streaming
                if delta.content:
                    collected_content += delta.content
                    yield delta.content
                
                # Tool call streaming
                if delta.tool_calls:
                    for tool_call in delta.tool_calls:
                        if tool_call.index >= len(collected_tool_calls):
                            collected_tool_calls.append({
                                "id": tool_call.id or "",
                                "type": "function",
                                "function": {
                                    "name": tool_call.function.name or "" if tool_call.function else "",
                                    "arguments": ""
                                }
                            })
                        
                        if tool_call.function:
                            if tool_call.function.name:
                                collected_tool_calls[tool_call.index]["function"]["name"] = tool_call.function.name
                            if tool_call.function.arguments:
                                collected_tool_calls[tool_call.index]["function"]["arguments"] += tool_call.function.arguments
                        if tool_call.id:
                            collected_tool_calls[tool_call.index]["id"] = tool_call.id
            
            # Check for tool calls
            if collected_tool_calls:
                # Add assistant message with tool calls
                assistant_message = {
                    "role": "assistant",
                    "content": collected_content or None,
                    "tool_calls": collected_tool_calls
                }
                self.messages.append(assistant_message)
                messages.append(assistant_message)
                
                # Execute tools
                for tool_call in collected_tool_calls:
                    tool_name = tool_call["function"]["name"]
                    tool = self.tool_executor.get_tool(tool_name)
                    
                    try:
                        args = json.loads(tool_call["function"]["arguments"])
                    except json.JSONDecodeError:
                        args = {}
                    
                    # Tool call header - minimalist style
                    exec_msg = tool.get_execution_message(**args) if tool else f"Executing {tool_name}..."
                    yield f"\n[bold #ffb8d1]◈ {exec_msg}[/bold #ffb8d1]\n"
                    
                    # Execute tool
                    result = self.tool_executor.execute(tool_name, args)
                    
                    if result.success:
                        output_preview = result.output.strip()
                        if output_preview:
                            # Use a simple indentation instead of a heavy box
                            preview_lines = output_preview.split('\n')
                            is_task_list = tool_name == "task_manager"
                            
                            # Keep full output for tasks, and now for everything else too
                            # max_lines = 2000 if is_task_list else 15
                            
                            formatted_output = ""
                            for line in preview_lines:
                                formatted_output += f"[dim #ce93d8]   │ [/dim #ce93d8]{line}\n"
                            
                            yield formatted_output
                    else:
                        yield f"[bold #ff5555]   ❌ Failed:[/bold #ff5555] [red]{rich_escape(result.error or '')}[/red]\n"
                    
                    # Add tool result to messages
                    tool_result_message = {
                        "role": "tool",
                        "tool_call_id": tool_call["id"],
                        "content": result.output if result.success else f"Error: {result.error}"
                    }
                    self.messages.append(tool_result_message)
                    messages.append(tool_result_message)
                
                # Continue loop to get model's response to tool results
                # Only yield newline if there's actual content following or if we had tool calls
                # yield "\n"
                continue
            
            # No tool calls, we're done
            if collected_content:
                self.messages.append({
                    "role": "assistant",
                    "content": collected_content
                })
            
            break
    
    def _process_non_streaming(self) -> str:
        """Process without streaming"""
        messages = self._build_messages()
        tools = self.tool_executor.get_tool_schemas(mode=self.mode)
        
        all_content = []
        
        while True:
            response = self._client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=tools if tools else None,
                stream=False
            )
            
            choice = response.choices[0]
            message = choice.message
            
            # Check for tool calls
            if message.tool_calls:
                # Add assistant message
                assistant_message = {
                    "role": "assistant",
                    "content": message.content,
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments
                            }
                        }
                        for tc in message.tool_calls
                    ]
                }
                self.messages.append(assistant_message)
                messages.append(assistant_message)
                
                if message.content:
                    all_content.append(message.content)
                
                # Execute each tool
                for tool_call in message.tool_calls:
                    tool_name = tool_call.function.name
                    tool = self.tool_executor.get_tool(tool_name)
                    
                    try:
                        args = json.loads(tool_call.function.arguments)
                    except json.JSONDecodeError:
                        args = {}
                    
                    exec_msg = tool.get_execution_message(**args) if tool else f"Executing {tool_name}..."
                    
                    all_content.append(f"[bold #ead0fe]◈[/bold #ead0fe] [bold]{exec_msg}[/bold]")
                    
                    result = self.tool_executor.execute(tool_name, args)
                    
                    if result.success:
                        all_content.append(f"[bold green]   ✅ Success[/bold green]")
                    else:
                        all_content.append(f"[bold red]   ❌ Failed:[/bold red] [red]{rich_escape(result.error or '')}[/red]")
                    
                    # Add tool result
                    tool_result_message = {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": result.output if result.success else f"Error: {result.error}"
                    }
                    self.messages.append(tool_result_message)
                    messages.append(tool_result_message)
                
                # Continue to get response to tool results
                continue
            
            # No tool calls, final response
            if message.content:
                self.messages.append({
                    "role": "assistant",
                    "content": message.content
                })
                all_content.append(message.content)
            
            break
        
        return '\n'.join(all_content)
    
    def clear_history(self) -> None:
        """Clear conversation history"""
        self.messages = []
    
    def get_history(self) -> List[Dict]:
        """Get conversation history"""
        return self.messages.copy()
    
    def set_history(self, messages: List[Dict]) -> None:
        """Set conversation history (for session restore)"""
        self.messages = messages.copy()
    
    def get_token_estimate(self) -> int:
        """Estimate tokens in current conversation"""
        total_chars = len(self.system_prompt)
        for msg in self.messages:
            content = msg.get('content', '')
            if content:
                total_chars += len(content)
        
        # Rough estimate: 1 token ≈ 4 characters
        return total_chars // 4