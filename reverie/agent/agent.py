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
import re

from rich.markup import escape as rich_escape

from .system_prompt import build_system_prompt
from .tool_executor import ToolExecutor
from ..tools.base import ToolResult

# Special marker for thinking content (used in streaming)
# This allows the interface to identify and style thinking content differently
THINKING_START_MARKER = "[[THINKING_START]]"
THINKING_END_MARKER = "[[THINKING_END]]"


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
        self.additional_rules = additional_rules
        self.mode = mode
        self.ant_phase = "PLANNING"
        
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
            mode=self.mode,
            ant_phase=self.ant_phase
        )

    def set_ant_phase(self, phase: str) -> None:
        """Update Antigravity phase (PLANNING/EXECUTION)"""
        if phase in ["PLANNING", "EXECUTION", "VERIFICATION"]:
            # Verification shares EXECUTION prompt but might have minor differences in future
            # For now mapping VERIFICATION to EXECUTION prompt logic if needed,
            # or just keeping the phase state for the tool.
            # System prompt only distinguishes PLANNING vs EXECUTION.
            self.ant_phase = phase
            
            # Map VERIFICATION to EXECUTION for prompt selection if strictly binary
            prompt_phase = "EXECUTION" if phase in ["EXECUTION", "VERIFICATION"] else "PLANNING"
            
            self.system_prompt = build_system_prompt(
                model_name=self.model_display_name,
                additional_rules=self.additional_rules,
                mode=self.mode,
                ant_phase=prompt_phase
            )

    def _check_tool_side_effects(self, tool_name: str, args: Dict[str, Any]) -> None:
        """Check for tools that modify agent state"""
        if tool_name == "task_boundary":
            mode = args.get("Mode")
            if mode and mode in ["PLANNING", "EXECUTION", "VERIFICATION"]:
                if mode != self.ant_phase:
                    self.set_ant_phase(mode)

    def update_mode(self, mode: str) -> None:
        """Update the agent's mode and rebuild the system prompt"""
        self.mode = mode
        self.ant_phase = "PLANNING" # Reset phase on mode switch
        self.system_prompt = build_system_prompt(
            model_name=self.model_display_name,
            additional_rules=self.additional_rules,
            mode=self.mode,
            ant_phase=self.ant_phase
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
        
        # Check for context threshold (60%) and trigger compression if needed
        self._check_and_compress_context()
        
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
        
        max_continuations = 3  # Safety limit to prevent infinite loops
        continuation_count = 0
        
        while True:
            response = self._client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=tools if tools else None,
                stream=True
            )
            
            # Collect streamed response
            collected_content = ""
            collected_thinking = ""  # Collect thinking/reasoning content
            collected_tool_calls = []
            finish_reason = None
            
            # Flag to track if we're in thinking mode
            thinking_started = False
            
            # Buffer for handling split tokens (to hide //END//)
            stream_buffer = ""
            token_to_hide = "//END//"
            
            for chunk in response:
                choice = chunk.choices[0] if chunk.choices else None
                
                if choice is None:
                    continue
                
                # Track finish reason
                if choice.finish_reason:
                    finish_reason = choice.finish_reason
                
                delta = choice.delta
                if delta is None:
                    continue
                
                # Handle reasoning/thinking content FIRST (for thinking models like o1, DeepSeek-R1, etc.)
                # Check for reasoning_content in delta (OpenAI o1 / DeepSeek style)
                reasoning_content = None
                if hasattr(delta, 'reasoning_content') and delta.reasoning_content:
                    reasoning_content = delta.reasoning_content
                elif hasattr(delta, 'thinking') and delta.thinking:
                    # Alternative field name used by some providers
                    reasoning_content = delta.thinking
                
                if reasoning_content:
                    collected_thinking += reasoning_content
                    # Emit thinking content with special markers for the interface
                    if not thinking_started:
                        yield THINKING_START_MARKER
                        thinking_started = True
                    yield reasoning_content
                
                # Content streaming - yield with buffering
                # If we were in thinking mode and now receiving regular content, end thinking first
                if delta.content:
                    # Check if we need to transition from thinking mode to regular content
                    if thinking_started:
                        yield THINKING_END_MARKER
                        thinking_started = False  # Reset so we don't emit again
                    
                    content_piece = delta.content
                    collected_content += content_piece
                    stream_buffer += content_piece
                    
                    if token_to_hide in stream_buffer:
                        # Found the token - split and yield parts
                        parts = stream_buffer.split(token_to_hide)
                        
                        # Yield everything before the first occurrence
                        if parts[0]:
                            yield parts[0]
                        
                        # We suppress the token itself.
                        # Handle text after the token (if any)
                        # Reconstruct remaining text without the token
                        remaining = "".join(parts[1:])
                        stream_buffer = remaining
                        
                    # Check for partial match at the end of buffer to prevent yielding partial token
                    partial_match_len = 0
                    for i in range(1, len(token_to_hide)):
                        if len(stream_buffer) >= i:
                            suffix = stream_buffer[-i:]
                            if token_to_hide.startswith(suffix):
                                partial_match_len = i
                    
                    if partial_match_len > 0:
                        # Yield safe part
                        to_yield = stream_buffer[:-partial_match_len]
                        stream_buffer = stream_buffer[-partial_match_len:]
                        if to_yield:
                            yield to_yield
                    else:
                        # No partial match, yield everything
                        yield stream_buffer
                        stream_buffer = ""
                
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
            
            # If thinking was streamed, emit end marker
            if thinking_started:
                yield THINKING_END_MARKER
            
            # Flush any remaining buffer that isn't the hidden token
            if stream_buffer and token_to_hide not in stream_buffer:
                yield stream_buffer
            
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
                    
                    # Check side effects
                    self._check_tool_side_effects(tool_name, args)
                    
                    # Tool call header - Dreamscape style with sparkle
                    exec_msg = tool.get_execution_message(**args) if tool else f"Executing {tool_name}..."
                    yield f"\n[bold #ffb8d1]✧[/bold #ffb8d1] [bold #e4b0ff]{exec_msg}[/bold #e4b0ff]\n"
                    
                    # Execute tool
                    result = self.tool_executor.execute(tool_name, args)
                    
                    if result.success:
                        output_preview = result.output.strip()
                        if output_preview:
                            preview_lines = output_preview.split('\n')
                            
                            formatted_output = ""
                            for line in preview_lines:
                                formatted_output += f"[#ba68c8]   │[/#ba68c8] [#e0e0e0]{line}[/#e0e0e0]\n"
                            
                            yield formatted_output
                    else:
                        yield f"[bold #ff5252]   ✘ Failed:[/bold #ff5252] [#ff8a80]{rich_escape(result.error or '')}[/#ff8a80]\n"
                    
                    # Add tool result to messages
                    tool_result_message = {
                        "role": "tool",
                        "tool_call_id": tool_call["id"],
                        "content": result.output if result.success else f"Error: {result.error}"
                    }
                    self.messages.append(tool_result_message)
                    messages.append(tool_result_message)
                
                # Reset continuation count for tool calls (this is expected looping)
                continuation_count = 0
                continue
            
            # No tool calls - save content and check if we should continue
            if collected_content:
                # Clean up //END// token if present
                clean_content = collected_content.replace("//END//", "").strip()
                
                # Save to messages
                self.messages.append({
                    "role": "assistant",
                    "content": clean_content
                })
                
                # Check if model finished naturally or needs continuation
                if finish_reason in ('stop', 'end_turn', 'end', None) or "//END//" in collected_content:
                    # Model finished - exit loop
                    break
                
                # Model stopped for other reason (length limit) - try to continue
                continuation_count += 1
                if continuation_count >= max_continuations:
                    break
                
                # Rebuild messages for continuation
                messages = self._build_messages()
                continue
            
            # No content at all, just break
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
                    
                    # Check side effects
                    self._check_tool_side_effects(tool_name, args)
                    
                    exec_msg = tool.get_execution_message(**args) if tool else f"Executing {tool_name}..."
                    
                    all_content.append(f"[bold #ffb8d1]✧[/bold #ffb8d1] [bold #e4b0ff]{exec_msg}[/bold #e4b0ff]")
                    
                    result = self.tool_executor.execute(tool_name, args)
                    
                    if result.success:
                        all_content.append(f"[bold #66bb6a]   ✔ Success[/bold #66bb6a]")
                    else:
                        all_content.append(f"[bold #ff5252]   ✘ Failed:[/bold #ff5252] [#ff8a80]{rich_escape(result.error or '')}[/#ff8a80]")
                    
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
            
            # No tool calls, final response check
            if message.content:
                content = message.content
                
                if "//END//" in content:
                    clean_content = content.replace("//END//", "").strip()
                    self.messages.append({
                        "role": "assistant",
                        "content": clean_content
                    })
                    all_content.append(clean_content) # Use clean content for return
                    break
                
                # Missing termination token - continue
                if self.messages and self.messages[-1].get("role") == "assistant" and "tool_calls" not in self.messages[-1]:
                    self.messages[-1]["content"] += content
                else:
                    self.messages.append({
                        "role": "assistant",
                        "content": content
                    })
                
                all_content.append(content)
                
                # Rebuild messages for next call
                messages = self._build_messages()
                continue
            
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
    
    def _check_and_compress_context(self) -> None:
        """Check if context exceeds 60% threshold and trigger compression if needed"""
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
        
        # Calculate current token estimate
        token_estimate = self.get_token_estimate()
        
        # Check if we've exceeded 60% threshold
        threshold = max_tokens * 0.6
        if token_estimate >= threshold:
            # Import here to avoid circular imports
            from ..context_engine.compressor import ContextCompressor
            from ..config import get_project_data_dir
            
            # Get session ID for checkpointing
            session_manager = self.tool_executor.context.get('session_manager')
            session_id = "default"
            if session_manager and session_manager.get_current_session():
                session_id = session_manager.get_current_session().id
            
            # Initialize compressor
            project_data_dir = get_project_data_dir(self.project_root)
            compressor = ContextCompressor(project_data_dir)
            
            # Build full message list including system prompt
            full_messages = [{"role": "system", "content": self.system_prompt}]
            full_messages.extend(self.messages)
            
            # Compress context
            try:
                compressed_messages = compressor.compress(
                    messages=full_messages,
                    client=self._client,
                    model=self.model,
                    session_id=session_id
                )
                
                # Update messages (exclude system prompt which is handled separately)
                self.messages = compressed_messages[1:]  # Skip system prompt
                
                # Add a notification about the compression
                compression_note = {
                    "role": "system",
                    "content": f"[Context Engine: Session compressed from {token_estimate:,} to {self.get_token_estimate():,} tokens to maintain memory persistence]"
                }
                self.messages.insert(0, compression_note)
                
            except Exception as e:
                # If compression fails, add a warning but continue
                warning_note = {
                    "role": "system", 
                    "content": f"[Context Engine Warning: Auto-compression failed - {str(e)}]"
                }
                self.messages.insert(0, warning_note)
    
    def get_token_estimate(self) -> int:
        """Estimate tokens in current conversation"""
        total_chars = len(self.system_prompt)
        for msg in self.messages:
            content = msg.get('content', '')
            if content:
                total_chars += len(content)
        
        # Rough estimate: 1 token ≈ 4 characters
        return total_chars // 4