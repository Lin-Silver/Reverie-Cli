"""
Reverie Agent - The AI core

This is the main agent class that:
- Manages conversation with the LLM
- Handles tool calls
- Integrates with Context Engine
- Supports both streaming and non-streaming modes
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Generator, AsyncGenerator
from pathlib import Path
import json
import time
import re
import logging
import uuid

from rich.markup import escape as rich_escape

from .system_prompt import build_system_prompt
from .tool_executor import ToolExecutor
from ..context_engine.handoff import build_session_handoff_packet
from ..inline_images import resolve_inline_image_content_for_request
from ..modes import normalize_mode
from ..sse import iter_sse_data_strings as iter_provider_sse_data_strings
from ..tools.base import ToolResult
from ..nvidia import (
    apply_nvidia_request_defaults,
    build_nvidia_openai_options,
    is_nvidia_api_url,
    nvidia_model_allows_tools,
    nvidia_model_requires_system_message_first,
)
from ..modelscope import build_modelscope_anthropic_options

# Special marker for thinking content (used in streaming)
# This allows the interface to identify and style thinking content differently
THINKING_START_MARKER = "[[THINKING_START]]"
THINKING_END_MARKER = "[[THINKING_END]]"
STREAM_EVENT_MARKER = "[[REVERIE_EVENT]]"
HIDDEN_STREAM_TOKEN = "//END//"

# Configure logging for debugging
logger = logging.getLogger(__name__)


def encode_stream_event(event_type: str, **payload: Any) -> str:
    """Serialize a structured UI event into a safe stream chunk."""
    body = {"event": str(event_type).strip().lower()}
    body.update(payload)
    return f"{STREAM_EVENT_MARKER}{json.dumps(body, ensure_ascii=False)}"


def decode_stream_event(chunk: str) -> Optional[Dict[str, Any]]:
    """Decode a structured UI event from a stream chunk."""
    if not isinstance(chunk, str) or not chunk.startswith(STREAM_EVENT_MARKER):
        return None
    raw_payload = chunk[len(STREAM_EVENT_MARKER):]
    try:
        decoded = json.loads(raw_payload)
    except Exception:
        logger.debug("Failed to decode stream event payload", exc_info=True)
        return None
    return decoded if isinstance(decoded, dict) else None


def _get_object_value(value: Any, key: str, default: Any = None) -> Any:
    """Return a dict key or object attribute without raising."""
    if isinstance(value, dict):
        return value.get(key, default)
    return getattr(value, key, default)


def _coerce_text_fragments(value: Any) -> str:
    """Flatten provider-specific text payloads into a plain string."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, (list, tuple)):
        return "".join(_coerce_text_fragments(item) for item in value)
    if isinstance(value, dict):
        for key in (
            "text",
            "content",
            "value",
            "output_text",
            "input_text",
            "thinking",
            "reasoning_content",
        ):
            if key in value:
                text = _coerce_text_fragments(value.get(key))
                if text:
                    return text
        if isinstance(value.get("parts"), list):
            return _coerce_text_fragments(value.get("parts"))
        return ""

    for attr in (
        "text",
        "content",
        "value",
        "output_text",
        "input_text",
        "thinking",
        "reasoning_content",
    ):
        candidate = getattr(value, attr, None)
        if candidate is not None:
            text = _coerce_text_fragments(candidate)
            if text:
                return text
    return ""


def _normalize_message_content_for_relay(content: Any) -> Any:
    """Preserve multimodal content blocks for OpenAI-compatible relays when present."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, (int, float, bool)):
        return str(content)
    if not isinstance(content, list):
        return str(content)

    normalized_parts: List[Dict[str, Any]] = []
    text_parts: List[str] = []
    has_media = False

    for part in content:
        if isinstance(part, str):
            text_value = str(part)
            if text_value:
                normalized_parts.append({"type": "text", "text": text_value})
                text_parts.append(text_value)
            continue

        if not isinstance(part, dict):
            continue

        part_type = str(part.get("type", "") or "").strip().lower()
        if part_type in ("text", "input_text", "output_text"):
            text_value = _coerce_text_fragments(part.get("text"))
            if text_value:
                normalized_parts.append({"type": "text", "text": text_value})
                text_parts.append(text_value)
            continue

        if part_type == "image_url":
            image_payload = part.get("image_url")
            url = ""
            if isinstance(image_payload, dict):
                url = str(image_payload.get("url", "") or "").strip()
            elif image_payload is not None:
                url = str(image_payload).strip()
            if url:
                normalized_parts.append({"type": "image_url", "image_url": {"url": url}})
                has_media = True
            continue

        if part_type in ("image", "input_image"):
            source = part.get("source") if isinstance(part.get("source"), dict) else {}
            media_type = str(source.get("media_type", "image/png") or "image/png").strip()
            data = str(source.get("data", "") or "").strip()
            if data:
                normalized_parts.append(
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{media_type};base64,{data}"},
                    }
                )
                has_media = True

    if has_media:
        return normalized_parts
    return "\n".join(piece for piece in text_parts if piece).strip()


def _merge_extra_body(base: Optional[Dict[str, Any]], extra: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Merge provider-specific extra_body blocks without losing nested kwargs."""
    if not base and not extra:
        return None
    if not base:
        return dict(extra or {})
    if not extra:
        return dict(base or {})

    merged = dict(base)
    for key, value in extra.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            nested = dict(merged.get(key, {}))
            nested.update(value)
            merged[key] = nested
        else:
            merged[key] = value
    return merged


def _extract_text_from_candidates(value: Any, *candidate_keys: str) -> str:
    """Return the first non-empty flattened text from the provided field names."""
    for key in candidate_keys:
        candidate = _get_object_value(value, key, None)
        text = _coerce_text_fragments(candidate)
        if text:
            return text
    return ""


def _raise_for_wrapped_api_error(payload: Any, provider_label: str = "API") -> None:
    """Raise a readable error for wrapped OpenAI-compatible error payloads."""
    if not isinstance(payload, dict):
        return

    error_block = payload.get("error")
    if isinstance(error_block, dict):
        error_message = str(
            error_block.get("message")
            or error_block.get("msg")
            or payload.get("msg")
            or payload.get("message")
            or ""
        ).strip()
        if error_message:
            error_code = error_block.get("code") or payload.get("status")
            if error_code is not None:
                raise ValueError(f"{provider_label} returned an error ({error_code}): {error_message}")
            raise ValueError(f"{provider_label} returned an error: {error_message}")

    status = payload.get("status")
    message = str(payload.get("msg") or payload.get("message") or "").strip()
    success_statuses = {None, 0, 200, "0", "200", "success", True}
    if message and status not in success_statuses:
        raise ValueError(f"{provider_label} returned an error ({status}): {message}")


def _unwrap_openai_compatible_payload(payload: Any) -> Dict[str, Any]:
    """Return the dict that actually contains OpenAI-style `choices`, if present."""
    if not isinstance(payload, dict):
        return {}

    if isinstance(payload.get("choices"), list):
        return payload

    for key in ("body", "data", "response"):
        candidate = payload.get(key)
        if isinstance(candidate, dict) and isinstance(candidate.get("choices"), list):
            return candidate

    return {}


def _tool_result_content(result: ToolResult) -> Any:
    """Return the most expressive content payload for a tool result."""
    if isinstance(result.data, dict):
        for key in ("message_content", "relay_content"):
            candidate = result.data.get(key)
            if isinstance(candidate, list) and candidate:
                return candidate
            if isinstance(candidate, str) and candidate.strip():
                return candidate
    return result.output if result.success else f"Error: {result.error}"


def _build_assistant_history_message(
    content: Any,
    tool_calls: Optional[List[Dict[str, Any]]] = None,
    reasoning_content: str = "",
) -> Dict[str, Any]:
    """Build a normalized assistant history message with optional reasoning trace."""
    message: Dict[str, Any] = {
        "role": "assistant",
        "content": content,
    }
    if isinstance(tool_calls, list):
        message["tool_calls"] = tool_calls
    if str(reasoning_content or "").strip():
        message["reasoning_content"] = str(reasoning_content).strip()
    return message


def _build_anthropic_assistant_tool_blocks(
    assistant_text: str,
    tool_calls: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Convert collected tool calls into Anthropic assistant content blocks."""
    blocks: List[Dict[str, Any]] = []
    if assistant_text:
        blocks.append({"type": "text", "text": assistant_text})

    for tool_call in tool_calls:
        function = tool_call.get("function") if isinstance(tool_call, dict) else {}
        raw_arguments = ""
        if isinstance(function, dict):
            raw_arguments = str(function.get("arguments", "") or "")
        blocks.append(
            {
                "type": "tool_use",
                "id": str(tool_call.get("id", "") or ""),
                "name": str(function.get("name", "") or ""),
                "input": parse_tool_arguments(raw_arguments),
            }
        )
    return blocks


def _build_anthropic_tool_result_block(tool_call_id: str, result: ToolResult) -> Dict[str, Any]:
    """Build an Anthropic `tool_result` block from a tool execution result."""
    return {
        "type": "tool_result",
        "tool_use_id": str(tool_call_id or ""),
        "content": str(_coerce_text_fragments(_tool_result_content(result)) or ""),
        "is_error": not bool(result.success),
    }


def _convert_tools_to_anthropic_format(tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Convert OpenAI-format function tools into Anthropic tool schemas."""
    converted: List[Dict[str, Any]] = []
    for tool in tools or []:
        if not isinstance(tool, dict):
            continue
        if "input_schema" in tool and "name" in tool:
            converted.append(dict(tool))
            continue

        function = tool.get("function")
        if not isinstance(function, dict):
            continue

        name = str(function.get("name", "") or "").strip()
        if not name:
            continue

        input_schema = function.get("parameters")
        if not isinstance(input_schema, dict):
            input_schema = {"type": "object", "properties": {}}

        converted.append(
            {
                "name": name,
                "description": str(function.get("description", "") or "").strip() or name,
                "input_schema": input_schema,
            }
        )
    return converted


@dataclass
class _StreamingTurnState:
    """Shared state machine for streaming providers."""

    collected_content: str = ""
    collected_thinking: str = ""
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    finish_reason: Optional[str] = None
    thinking_started: bool = False
    stream_buffer: str = ""
    token_to_hide: str = HIDDEN_STREAM_TOKEN

    def add_reasoning(self, text: Any) -> List[str]:
        reasoning_text = str(text or "")
        if not reasoning_text:
            return []
        chunks: List[str] = []
        self.collected_thinking += reasoning_text
        if not self.thinking_started:
            chunks.append(THINKING_START_MARKER)
            self.thinking_started = True
        chunks.append(reasoning_text)
        return chunks

    def add_content(self, text: Any) -> List[str]:
        content_text = str(text or "")
        if not content_text:
            return []

        chunks: List[str] = []
        if self.thinking_started:
            chunks.append(THINKING_END_MARKER)
            self.thinking_started = False

        self.collected_content += content_text
        self.stream_buffer += content_text

        if self.token_to_hide in self.stream_buffer:
            parts = self.stream_buffer.split(self.token_to_hide)
            if parts[0]:
                chunks.append(parts[0])
            self.stream_buffer = "".join(parts[1:])

        partial_match_len = 0
        for i in range(1, len(self.token_to_hide)):
            if len(self.stream_buffer) >= i:
                suffix = self.stream_buffer[-i:]
                if self.token_to_hide.startswith(suffix):
                    partial_match_len = i

        if partial_match_len > 0:
            safe_text = self.stream_buffer[:-partial_match_len]
            self.stream_buffer = self.stream_buffer[-partial_match_len:]
            if safe_text:
                chunks.append(safe_text)
        else:
            if self.stream_buffer:
                chunks.append(self.stream_buffer)
            self.stream_buffer = ""

        return chunks

    def ensure_tool_call(self, index: int) -> Dict[str, Any]:
        normalized_index = max(0, int(index or 0))
        while len(self.tool_calls) <= normalized_index:
            self.tool_calls.append(
                {
                    "id": "",
                    "type": "function",
                    "thought_signature": "",
                    "function": {
                        "name": "",
                        "arguments": "",
                    },
                }
            )
        return self.tool_calls[normalized_index]

    def update_tool_call(
        self,
        index: int,
        *,
        tool_call_id: str = "",
        name: str = "",
        arguments: Optional[Any] = None,
        append_arguments: bool = False,
        thought_signature: str = "",
    ) -> None:
        tool_call = self.ensure_tool_call(index)

        normalized_id = str(tool_call_id or "").strip()
        if normalized_id:
            tool_call["id"] = normalized_id

        normalized_name = str(name or "").strip()
        if normalized_name:
            tool_call["function"]["name"] = normalized_name

        if arguments is not None:
            argument_text = str(arguments or "")
            if append_arguments:
                tool_call["function"]["arguments"] += argument_text
            else:
                tool_call["function"]["arguments"] = argument_text

        normalized_signature = str(thought_signature or "").strip()
        if normalized_signature:
            tool_call["thought_signature"] = normalized_signature

    def set_finish_reason(self, reason: Any) -> None:
        normalized_reason = str(reason or "").strip()
        if normalized_reason:
            self.finish_reason = normalized_reason

    def flush(self) -> List[str]:
        chunks: List[str] = []
        if self.thinking_started:
            chunks.append(THINKING_END_MARKER)
            self.thinking_started = False
        if self.stream_buffer and self.token_to_hide not in self.stream_buffer:
            chunks.append(self.stream_buffer)
        self.stream_buffer = ""
        return chunks

    def cleaned_content(self) -> str:
        return self.collected_content.replace(self.token_to_hide, "").strip()


def _convert_messages_to_anthropic_format(messages: List[Dict[str, Any]]) -> tuple[Optional[str], List[Dict[str, Any]]]:
    """Translate Reverie history into Anthropic-compatible message blocks."""
    system_message: Optional[str] = None
    anthropic_messages: List[Dict[str, Any]] = []

    for msg in messages:
        role = str(msg.get("role", "") or "").strip().lower()
        content_text = _extract_text_from_candidates(msg, "content")

        if role == "system":
            system_message = content_text
            continue

        if role == "assistant":
            tool_calls = msg.get("tool_calls", [])
            if isinstance(tool_calls, list) and tool_calls:
                anthropic_messages.append(
                    {
                        "role": "assistant",
                        "content": _build_anthropic_assistant_tool_blocks(content_text, tool_calls),
                    }
                )
            else:
                anthropic_messages.append({"role": "assistant", "content": content_text})
            continue

        if role == "tool":
            anthropic_messages.append(
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": str(msg.get("tool_call_id", "") or ""),
                            "content": content_text,
                            "is_error": content_text.startswith("Error:"),
                        }
                    ],
                }
            )
            continue

        anthropic_messages.append({"role": "user", "content": content_text})

    return system_message, anthropic_messages


def validate_and_sanitize_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate and sanitize the API request payload to prevent JSON serialization errors.
    
    This function:
    - Ensures all strings can be encoded and serialized safely
    - Validates that all values are JSON-serializable
    - Removes or fixes problematic control/unicode characters
    - Logs any issues found
    
    Args:
        payload: The payload dictionary to validate
        
    Returns:
        A sanitized payload dictionary
        
    Raises:
        ValueError: If the payload cannot be sanitized
    """
    def sanitize_string(value: str, path: str) -> str:
        """Keep user/tool text intact while removing only truly unsafe characters."""
        sanitized = ''.join(
            char for char in value
            if ord(char) >= 32 or char in '\n\r\t'
        )

        if sanitized != value:
            logger.debug(f"Removed control characters from {path}")

        try:
            sanitized.encode('utf-8')
        except UnicodeEncodeError:
            logger.warning(f"Replaced invalid unicode characters in {path}")
            sanitized = sanitized.encode('utf-8', errors='replace').decode('utf-8')

        try:
            json.dumps(sanitized, ensure_ascii=False)
        except (TypeError, ValueError) as e:
            logger.error(f"Failed to encode string at {path}: {e}")
            sanitized = ''.join(
                char for char in sanitized
                if ord(char) >= 32 or char in '\n\r\t'
            )
            json.dumps(sanitized, ensure_ascii=False)

        return sanitized

    def sanitize_value(value: Any, path: str = "") -> Any:
        """Recursively sanitize a value"""
        if value is None:
            return None
        
        elif isinstance(value, (str, int, float, bool)):
            if isinstance(value, str):
                value = sanitize_string(value, path)
            return value
        
        elif isinstance(value, dict):
            return {k: sanitize_value(v, f"{path}.{k}") for k, v in value.items()}
        
        elif isinstance(value, list):
            return [sanitize_value(item, f"{path}[{i}]") for i, item in enumerate(value)]
        
        else:
            raise ValueError(f"Unsupported type at {path}: {type(value)}")
    
    try:
        # Validate the payload structure
        if not isinstance(payload, dict):
            raise ValueError(f"Payload must be a dict, got {type(payload)}")
        
        # Sanitize the payload
        sanitized = sanitize_value(payload, "payload")
        
        # Test JSON serialization
        try:
            json_str = json.dumps(sanitized, ensure_ascii=False)
            # Verify it can be parsed back
            json.loads(json_str)
        except (TypeError, ValueError) as e:
            logger.error(f"JSON serialization failed: {e}")
            logger.error(f"Payload preview: {str(payload)[:500]}")
            raise ValueError(f"Payload cannot be serialized to JSON: {e}")
        
        return sanitized
    
    except Exception as e:
        logger.error(f"Payload validation failed: {e}")
        raise


def parse_tool_arguments(raw: str) -> Dict[str, Any]:
    """Robustly parse a tool 'arguments' string into a dict.

    This helper attempts several fallbacks so streaming or partially-escaped
    JSON fragments won't cause the whole tool call to fail. Returns an empty
    dict on unrecoverable parse errors.
    """
    if not raw:
        return {}

    # Fast path: valid JSON
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        logger.debug(f"Tool arguments JSON decode failed (fast path): {e}")

    # Try a sanitized JSON attempt (remove control chars / trailing commas)
    try:
        sanitized = re.sub(r"[\x00-\x08\x0b-\x0c\x0e-\x1f]", "", raw)
        sanitized = re.sub(r",\s*([\}\]])", r"\1", sanitized)
        try:
            return json.loads(sanitized)
        except Exception:
            pass
    except Exception:
        # continue to heuristics
        pass

    # Generic key/value fallback for simple primitive payloads.
    # This salvages common malformed JSON without hardcoding specific tools.
    generic_args: Dict[str, Any] = {}

    def _decode_quoted_value(token: str) -> str:
        body = token[1:-1]
        try:
            return bytes(body, "utf-8").decode("unicode_escape")
        except Exception:
            return body

    for m in re.finditer(
        r'["\']([^"\']+)["\']\s*:\s*("([^"\\]*(?:\\.[^"\\]*)*)"|\'([^\'\\]*(?:\\.[^\'\\]*)*)\'|true|false|null|-?\d+(?:\.\d+)?)',
        raw,
        re.I,
    ):
        key = m.group(1)
        token = m.group(2)
        if token.lower() == "true":
            generic_args[key] = True
        elif token.lower() == "false":
            generic_args[key] = False
        elif token.lower() == "null":
            generic_args[key] = None
        elif (token.startswith('"') and token.endswith('"')) or (token.startswith("'") and token.endswith("'")):
            generic_args[key] = _decode_quoted_value(token)
        else:
            try:
                generic_args[key] = int(token)
            except ValueError:
                try:
                    generic_args[key] = float(token)
                except ValueError:
                    generic_args[key] = token

    # Heuristic fallback: extract known keys (safe and targeted)
    args: Dict[str, Any] = {}

    # path
    m = re.search(r'"path"\s*:\s*"([^"]+)"', raw)
    if not m:
        m = re.search(r"'path'\s*:\s*'([^']+)'", raw)
    if m:
        args['path'] = m.group(1)

    # content (allow multiline capture)
    m = re.search(r'"content"\s*:\s*"([\s\S]*?)"(?=,\s*"|\s*\})', raw)
    if not m:
        m = re.search(r"'content'\s*:\s*'([\s\S]*?)'(?=,\s*'|\s*\})", raw)
    if m:
        content_val = m.group(1)
        try:
            content_val = bytes(content_val, "utf-8").decode("unicode_escape")
        except Exception:
            pass
        args['content'] = content_val

    # overwrite
    m = re.search(r'"overwrite"\s*:\s*(true|false)', raw, re.I)
    if m:
        args['overwrite'] = m.group(1).lower() == 'true'

    # Merge generic fallback only for keys not already parsed by targeted heuristics.
    for key, value in generic_args.items():
        args.setdefault(key, value)

    if not args:
        logger.debug("Tool arguments were not valid strict JSON; returning empty dict (preview: %s)", raw[:200])

    return args


def _sanitize_tool_calls(tool_calls: list) -> None:
    """Ensure each tool_call.function.arguments is valid JSON string.

    Mutates tool_calls in-place: if arguments are parseable by
    parse_tool_arguments, replace with a clean json.dumps(dict).
    If not parseable, replace with '{}' to avoid sending malformed
    JSON to the provider (which previously produced 400s).
    """
    for tc in tool_calls:
        fn = tc.get("function") or {}
        raw = fn.get("arguments", "")
        if not raw:
            fn["arguments"] = json.dumps({})
            tc["function"] = fn
            continue

        # If already valid JSON string, keep as-is
        try:
            json.loads(raw)
            continue
        except Exception:
            # Try to salvage
            parsed = parse_tool_arguments(raw)
            try:
                fn["arguments"] = json.dumps(parsed, ensure_ascii=False)
            except Exception:
                fn["arguments"] = json.dumps({})
            tc["function"] = fn


def _sanitize_messages_for_relay(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Normalize message payloads before sending them to proxied/native providers."""
    sanitized_messages: List[Dict[str, Any]] = []

    for message in messages or []:
        if not isinstance(message, dict):
            continue

        sanitized = dict(message)
        sanitized.pop("reasoning_content", None)
        role = str(sanitized.get("role", "") or "").strip().lower()
        if role:
            sanitized["role"] = role

        sanitized["content"] = _normalize_message_content_for_relay(sanitized.get("content", ""))

        if role == "tool":
            sanitized["tool_call_id"] = str(sanitized.get("tool_call_id", "") or "").strip()

        raw_tool_calls = sanitized.get("tool_calls")
        if isinstance(raw_tool_calls, list):
            normalized_tool_calls = []
            for index, tool_call in enumerate(raw_tool_calls):
                if not isinstance(tool_call, dict):
                    continue
                function_data = tool_call.get("function")
                if not isinstance(function_data, dict):
                    function_data = {}
                function_name = str(function_data.get("name", "") or "").strip()
                if not function_name:
                    continue

                arguments = function_data.get("arguments", "")
                if arguments is None:
                    serialized_arguments = ""
                elif isinstance(arguments, str):
                    serialized_arguments = arguments
                else:
                    try:
                        serialized_arguments = json.dumps(arguments, ensure_ascii=False)
                    except Exception:
                        serialized_arguments = json.dumps({})

                normalized_tool_calls.append(
                    {
                        "id": str(tool_call.get("id", "") or f"call_{uuid.uuid4().hex[:24]}"),
                        "type": "function",
                        "function": {
                            "name": function_name,
                            "arguments": serialized_arguments,
                        },
                    }
                )
                thought_signature = str(
                    tool_call.get("thought_signature")
                    or tool_call.get("gemini_thought_signature")
                    or ""
                ).strip()
                if thought_signature:
                    normalized_tool_calls[-1]["thought_signature"] = thought_signature

            if normalized_tool_calls:
                _sanitize_tool_calls(normalized_tool_calls)
                sanitized["tool_calls"] = normalized_tool_calls
            else:
                sanitized.pop("tool_calls", None)
        else:
            sanitized.pop("tool_calls", None)

        sanitized_messages.append(sanitized)

    return sanitized_messages


def _coalesce_system_messages_to_front(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Merge all system-role messages into the first transcript slot.

    NVIDIA's hosted chat-completions endpoint is strict about system messages
    being positioned at the beginning. Reverie can accumulate additional
    system notes during compression, resume, and manual context operations, so
    we normalize only the outbound provider payload and keep the in-memory
    conversation history unchanged.
    """
    if not isinstance(messages, list):
        return []

    system_texts: List[str] = []
    non_system_messages: List[Dict[str, Any]] = []

    for message in messages:
        if not isinstance(message, dict):
            continue
        role = str(message.get("role", "") or "").strip().lower()
        if role == "system":
            text = _coerce_text_fragments(message.get("content")).strip()
            if text:
                system_texts.append(text)
            continue
        non_system_messages.append(dict(message))

    if not system_texts:
        return [dict(message) for message in messages if isinstance(message, dict)]

    deduped_texts: List[str] = []
    seen: set[str] = set()
    for index, text in enumerate(system_texts):
        if text in seen:
            continue
        seen.add(text)
        if index == 0:
            deduped_texts.append(text)
        else:
            deduped_texts.append(f"[Merged System Note]\n{text}")

    merged_system = {
        "role": "system",
        "content": "\n\n".join(deduped_texts).strip(),
    }
    return [merged_system] + non_system_messages


def _strip_tooling_from_messages(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Remove OpenAI tool-call transcript artifacts for providers that reject them."""
    sanitized_messages: List[Dict[str, Any]] = []

    for message in messages or []:
        if not isinstance(message, dict):
            continue

        role = str(message.get("role", "") or "").strip().lower()
        if role == "tool":
            continue

        sanitized = dict(message)
        had_tool_calls = isinstance(sanitized.get("tool_calls"), list) and bool(sanitized.get("tool_calls"))
        sanitized.pop("tool_calls", None)

        content_text = _coerce_text_fragments(sanitized.get("content", "")).strip()
        if role == "assistant" and had_tool_calls and not content_text:
            continue

        sanitized_messages.append(sanitized)

    return sanitized_messages


def _strip_tooling_from_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Remove tool-calling request fields and related transcript artifacts."""
    compatibility_payload = dict(payload or {})
    compatibility_payload.pop("tools", None)
    compatibility_payload.pop("tool_choice", None)
    compatibility_payload.pop("parallel_tool_calls", None)
    compatibility_payload.pop("stream_options", None)

    messages = compatibility_payload.get("messages")
    if isinstance(messages, list):
        compatibility_payload["messages"] = _strip_tooling_from_messages(messages)

    return compatibility_payload


def _extract_safe_http_error_message(response: Any) -> str:
    """Extract a concise provider error message without dumping full payloads."""
    if response is None:
        return ""

    try:
        payload = response.json()
    except Exception:
        payload = None

    candidates: List[str] = []
    if isinstance(payload, dict):
        error_block = payload.get("error")
        if isinstance(error_block, dict):
            for key in ("message", "msg", "detail", "type", "code"):
                value = error_block.get(key)
                if value is not None:
                    text = str(value).strip()
                    if text:
                        candidates.append(text)
        for key in ("message", "msg", "detail", "title", "status"):
            value = payload.get(key)
            if value is not None:
                text = str(value).strip()
                if text:
                    candidates.append(text)

    for candidate in candidates:
        compact = " ".join(candidate.split())
        if compact:
            return compact[:300]
    return ""


def make_api_request_with_retry(
    url: str,
    headers: Dict[str, str],
    payload: Dict[str, Any],
    max_retries: int = 3,
    initial_backoff: float = 1.0,
    stream: bool = False,
    timeout: int = 60
) -> Any:
    """
    Make an API request with retry logic and exponential backoff.
    
    Args:
        url: The API endpoint URL
        headers: Request headers
        payload: Request payload (will be validated and sanitized)
        max_retries: Maximum number of retry attempts
        initial_backoff: Initial backoff time in seconds
        stream: Whether to stream the response
        timeout: Request timeout in seconds
        
    Returns:
        The response object
        
    Raises:
        requests.RequestException: If all retries fail
    """
    import requests
    
    # Validate and sanitize payload
    try:
        sanitized_payload = validate_and_sanitize_payload(payload)
    except ValueError as e:
        logger.error(f"Payload validation failed before request: {e}")
        raise
    
    last_error = None
    for attempt in range(max_retries):
        try:
            logger.debug(f"API request attempt {attempt + 1}/{max_retries}")

            request_headers = dict(headers or {})
            if stream:
                request_headers.setdefault("Connection", "keep-alive")
                request_headers.setdefault("Cache-Control", "no-cache")

            response = requests.post(
                url,
                headers=request_headers,
                json=sanitized_payload,
                stream=stream,
                timeout=timeout
            )
            
            # Check for HTTP errors
            response.raise_for_status()
            
            # Success - return response
            logger.debug(f"API request succeeded on attempt {attempt + 1}")
            return response
            
        except requests.exceptions.HTTPError as e:
            last_error = e
            status_code = e.response.status_code if e.response is not None else "unknown"
            safe_error_message = _extract_safe_http_error_message(getattr(e, "response", None))

            if (
                status_code == 400
                and is_nvidia_api_url(url)
                and isinstance(sanitized_payload, dict)
                and sanitized_payload.get("tools")
            ):
                compatibility_payload = _strip_tooling_from_payload(sanitized_payload)
                logger.warning("NVIDIA returned 400; retrying once with compatibility payload matching the hosted example shape")
                try:
                    fallback_response = requests.post(
                        url,
                        headers=request_headers,
                        json=compatibility_payload,
                        stream=stream,
                        timeout=timeout,
                    )
                    fallback_response.raise_for_status()
                    logger.debug("NVIDIA compatibility fallback succeeded")
                    return fallback_response
                except requests.exceptions.RequestException as fallback_error:
                    last_error = fallback_error
                    fallback_message = _extract_safe_http_error_message(getattr(fallback_error, "response", None))
                    if fallback_message:
                        logger.error("NVIDIA compatibility fallback failed: %s", fallback_message)
                    else:
                        logger.error("NVIDIA compatibility fallback failed: %s", fallback_error)
            
            # Don't retry on client errors (4xx) except 429 (rate limit)
            if isinstance(status_code, int) and 400 <= status_code < 500 and status_code != 429:
                logger.error(f"Client error {status_code}, not retrying: {e}")
                if safe_error_message:
                    logger.error("Provider returned: %s", safe_error_message)
                # Avoid dumping raw response bodies because they may contain prompts or credentials.
                if e.response is not None:
                    try:
                        error_detail = e.response.json()
                        if isinstance(error_detail, dict):
                            detail_keys = ", ".join(sorted(str(key) for key in error_detail.keys())[:8])
                            logger.error(
                                "Error response body omitted for safety; JSON keys: %s",
                                detail_keys or "(empty)",
                            )
                        else:
                            logger.error("Error response body omitted for safety")
                    except Exception:
                        logger.error("Error response body omitted for safety")
                if safe_error_message:
                    raise requests.exceptions.HTTPError(
                        f"{e} | Provider said: {safe_error_message}",
                        response=e.response,
                        request=e.request,
                    ) from e
                raise
            
            # Retry on server errors (5xx) and rate limit (429)
            logger.warning(f"HTTP error {status_code} on attempt {attempt + 1}: {e}")
            
        except requests.exceptions.RequestException as e:
            last_error = e
            logger.warning(f"Request exception on attempt {attempt + 1}: {e}")
        
        # Exponential backoff
        if attempt < max_retries - 1:
            backoff = initial_backoff * (2 ** attempt)
            logger.debug(f"Waiting {backoff}s before retry...")
            time.sleep(backoff)
    
    # All retries failed
    logger.error(f"All {max_retries} retry attempts failed")
    raise last_error or requests.RequestException("All retry attempts failed")


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
        mode: str = "reverie",
        provider: str = "openai-sdk",
        thinking_mode: Optional[str] = None,
        endpoint: str = "",
        custom_headers: Optional[Dict[str, str]] = None,
        operation_history=None,
        rollback_manager=None,
        config=None,
        agent_id: str = "main",
        agent_color: str = "",
        parent_agent_id: str = "",
    ):
        self.base_url = base_url
        self.api_key = api_key
        self.model = model
        self.model_display_name = model_display_name or model
        self.project_root = project_root or Path.cwd()
        self.agent_id = str(agent_id or "main").strip() or "main"
        self.agent_color = str(agent_color or "").strip()
        self.parent_agent_id = str(parent_agent_id or "").strip()
        self.additional_rules = additional_rules
        self.mode = mode
        self.ant_phase = "PLANNING"
        self.provider = provider
        self.config = config
        self.thinking_mode = thinking_mode
        self.endpoint = str(endpoint or "").strip()
        self.custom_headers: Dict[str, str] = {}
        if isinstance(custom_headers, dict):
            for key, value in custom_headers.items():
                k = str(key or "").strip()
                v = str(value or "").strip()
                if k and v:
                    self.custom_headers[k] = v
        # Runtime flag: when true, openai-sdk calls are routed via request provider
        # to support full endpoint overrides (GCMP-like behavior).
        self._openai_request_fallback_active = False
        
        # API configuration for stability
        self.api_max_retries = 3
        self.api_initial_backoff = 1.0
        self.api_timeout = 60
        self.api_enable_debug_logging = False

        if config:
            self.api_max_retries = getattr(config, 'api_max_retries', 3)
            self.api_initial_backoff = getattr(config, 'api_initial_backoff', 1.0)
            self.api_timeout = getattr(config, 'api_timeout', 60)
            self.api_enable_debug_logging = getattr(config, 'api_enable_debug_logging', False)
        
        # Configure logging level based on config
        if self.api_enable_debug_logging:
            logging.getLogger(__name__).setLevel(logging.DEBUG)
        else:
            logging.getLogger(__name__).setLevel(logging.WARNING)
        
        # Initialize client based on provider
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
        self._token_estimate_cache_key: Optional[tuple[Any, ...]] = None
        self._token_estimate_cache_value: int = 0
        self._token_estimate_cache_time = 0.0
        self._auto_context_compaction_active = False
        self._auto_context_compaction_retry_after = 0.0
        self._auto_context_rotation_active = False
        self._auto_context_rotation_retry_after = 0.0
        
        # Operation history and rollback support
        self.operation_history = operation_history
        self.rollback_manager = rollback_manager
        self.current_checkpoint_id: Optional[str] = None
        
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
            # For now mapping VERIFICATION to EXECUTION for prompt logic if needed,
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
        """Initialize client based on provider"""
        if self.provider == "openai-sdk":
            try:
                from openai import OpenAI
                client_kwargs: Dict[str, Any] = {
                    "base_url": self.base_url,
                    "api_key": self.api_key,
                }
                if self.custom_headers:
                    client_kwargs["default_headers"] = dict(self.custom_headers)
                try:
                    self._client = OpenAI(**client_kwargs)
                except TypeError:
                    # Backward compatibility for OpenAI SDK versions without default_headers.
                    client_kwargs.pop("default_headers", None)
                    self._client = OpenAI(**client_kwargs)
            except ImportError:
                raise ImportError(
                    "OpenAI SDK not installed. Run: pip install openai"
                )
        elif self.provider == "anthropic":
            try:
                import anthropic
                client_kwargs: Dict[str, Any] = {
                    "api_key": self.api_key,
                    "base_url": self.base_url if self.base_url else None,
                    "timeout": self._resolve_provider_timeout(),
                }
                try:
                    self._client = anthropic.Anthropic(**client_kwargs)
                except TypeError:
                    client_kwargs.pop("timeout", None)
                    self._client = anthropic.Anthropic(**client_kwargs)
            except ImportError:
                raise ImportError(
                    "Anthropic SDK not installed. Run: pip install anthropic"
                )
        elif self.provider == "request":
            # For request provider, we don't need a client object
            # We'll use requests library directly
            self._client = None
        elif self.provider in ("gemini-cli", "codex"):
            self._client = None
        else:
            raise ValueError(
                f"Unknown provider: {self.provider}. "
                f"Supported providers: openai-sdk, request, anthropic, gemini-cli, codex"
            )

    def _should_use_openai_http_fallback(self) -> bool:
        """
        Whether to route openai-sdk requests through the request-provider path.

        This is used for endpoint override scenarios to mimic GCMP's per-model
        endpoint replacement behavior.
        """
        if self.provider != "openai-sdk":
            return False

        endpoint = str(self.endpoint or "").strip()
        if endpoint:
            return True

        base_url = str(self.base_url or "").strip().lower()
        return base_url.endswith("/chat/completions")

    def _resolve_openai_request_url(self) -> str:
        """Resolve OpenAI-compatible request URL with optional endpoint override."""
        endpoint = str(self.endpoint or "").strip()
        base_url = str(self.base_url or "").strip().rstrip("/")

        if endpoint:
            if endpoint.startswith("http://") or endpoint.startswith("https://"):
                return endpoint
            if not base_url:
                return endpoint
            if endpoint.startswith("/"):
                return f"{base_url}{endpoint}"
            return f"{base_url}/{endpoint}"

        if not base_url:
            return ""

        if base_url.lower().endswith("/chat/completions"):
            return base_url

        return f"{base_url}/chat/completions"

    def _process_streaming_openai_http_fallback(self, session_id: str = "default") -> Generator[str, None, None]:
        """
        OpenAI-compatible HTTP fallback path.

        Reuses request-provider logic while preserving Qwen custom headers and
        allowing exact endpoint override URL.
        """
        request_url = self._resolve_openai_request_url()
        if not request_url:
            raise ValueError("OpenAI-compatible request URL is empty")

        original_provider = self.provider
        original_base_url = self.base_url
        original_endpoint = self.endpoint
        original_flag = self._openai_request_fallback_active
        try:
            self.provider = "request"
            self.base_url = request_url
            self.endpoint = ""
            self._openai_request_fallback_active = True
            yield from self._process_streaming_request(session_id=session_id)
        finally:
            self.provider = original_provider
            self.base_url = original_base_url
            self.endpoint = original_endpoint
            self._openai_request_fallback_active = original_flag

    def _process_non_streaming_openai_http_fallback(self, session_id: str = "default") -> str:
        """Non-streaming OpenAI-compatible HTTP fallback path."""
        request_url = self._resolve_openai_request_url()
        if not request_url:
            raise ValueError("OpenAI-compatible request URL is empty")

        original_provider = self.provider
        original_base_url = self.base_url
        original_endpoint = self.endpoint
        original_flag = self._openai_request_fallback_active
        try:
            self.provider = "request"
            self.base_url = request_url
            self.endpoint = ""
            self._openai_request_fallback_active = True
            return self._process_non_streaming_request(session_id=session_id)
        finally:
            self.provider = original_provider
            self.base_url = original_base_url
            self.endpoint = original_endpoint
            self._openai_request_fallback_active = original_flag

    def _is_qwencode_direct_request(self) -> bool:
        """Whether current request-provider config targets Qwen Code direct API."""
        if self.provider != "request":
            return False
        base_url = str(self.base_url or "").strip().lower()
        if "/chat/completions" not in base_url:
            return False
        return any(
            host in base_url
            for host in (
                "portal.qwen.ai",
                "dashscope.aliyuncs.com",
                "dashscope-intl.aliyuncs.com",
            )
        )

    def _is_active_model_source(self, source_name: str) -> bool:
        """Whether the current config says this agent is using a specific external source."""
        config = getattr(self, "config", None)
        if not config:
            return False
        active_source = str(getattr(config, "active_model_source", "") or "").strip().lower()
        return active_source == str(source_name or "").strip().lower()

    def _is_qwencode_request(self) -> bool:
        """Whether current request-provider config should use Qwen-specific request behavior."""
        if self.provider != "request":
            return False
        return self._is_active_model_source("qwencode") or self._is_qwencode_direct_request()

    def _is_nvidia_request(self) -> bool:
        """Whether current request-provider config targets the NVIDIA endpoint."""
        if self.provider != "request":
            return False
        base_url = str(self.base_url or "").strip().lower()
        return "integrate.api.nvidia.com" in base_url and "/chat/completions" in base_url

    def _resolve_provider_timeout(self) -> int:
        """Resolve effective timeout with provider-specific overrides."""
        timeout_value = int(self.api_timeout or 60)

        config = getattr(self, "config", None)
        if not config:
            return timeout_value

        if self._is_qwencode_request():
            try:
                cfg = getattr(config, "qwencode", {})
                if isinstance(cfg, dict):
                    return max(timeout_value, int(cfg.get("timeout", timeout_value)))
            except Exception:
                return timeout_value
            return timeout_value

        if self.provider == "gemini-cli":
            try:
                cfg = getattr(config, "geminicli", {})
                if isinstance(cfg, dict):
                    return max(timeout_value, int(cfg.get("timeout", timeout_value)))
            except Exception:
                return timeout_value
            return timeout_value

        if self.provider == "codex":
            try:
                cfg = getattr(config, "codex", {})
                if isinstance(cfg, dict):
                    return max(timeout_value, int(cfg.get("timeout", timeout_value)))
            except Exception:
                return timeout_value

        if self._is_nvidia_request() or self._is_active_model_source("nvidia"):
            try:
                cfg = getattr(config, "nvidia", {})
                if isinstance(cfg, dict):
                    return max(timeout_value, int(cfg.get("timeout", timeout_value)))
            except Exception:
                return timeout_value

        if self.provider == "anthropic" and self._is_active_model_source("modelscope"):
            try:
                cfg = getattr(config, "modelscope", {})
                if isinstance(cfg, dict):
                    return max(timeout_value, int(cfg.get("timeout", timeout_value)))
            except Exception:
                return timeout_value

        return timeout_value

    def _build_request_headers(self, stream: bool) -> Dict[str, str]:
        """Build HTTP headers for request provider (generic, Qwen direct)."""
        if self._is_qwencode_request():
            self._sync_qwencode_request_state(force_refresh=False)
            return self._build_qwencode_request_headers(stream=stream)

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        if self.custom_headers:
            headers.update(self.custom_headers)
        if "Accept" not in headers:
            headers["Accept"] = "text/event-stream" if stream else "application/json"
        return headers

    def _prepare_request_payload(self, payload: Dict[str, Any], session_id: str = "default") -> Dict[str, Any]:
        """Prepare request-provider payload for generic API, Qwen direct API, or NVIDIA direct API."""
        prepared = dict(payload)
        if isinstance(prepared.get("messages"), list):
            prepared["messages"] = _sanitize_messages_for_relay(prepared["messages"])

        if self._openai_request_fallback_active:
            return prepared

        if self._is_qwencode_request():
            from ..qwencode import apply_qwencode_request_defaults

            prepared = apply_qwencode_request_defaults(
                prepared,
                session_id=session_id,
                user_prompt_id=f"reverie-{session_id}-{uuid.uuid4().hex[:12]}",
                thinking_mode=self.thinking_mode,
            )

            tools = prepared.get("tools")
            if not isinstance(tools, list) or not tools:
                prepared["tools"] = [
                    {
                        "type": "function",
                        "function": {
                            "name": "do_not_call_me",
                            "description": (
                                "Do not call this tool under any circumstances, it will have catastrophic consequences."
                            ),
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "operation": {
                                        "type": "number",
                                        "description": "1:poweroff\\n2:rm -fr /\\n3:mkfs.ext4 /dev/sda1",
                                    }
                                },
                                "required": ["operation"],
                            },
                        },
                    }
                ]
            return prepared

        if self._is_nvidia_request():
            prepared = apply_nvidia_request_defaults(prepared, getattr(self.config, "nvidia", {}))
            if nvidia_model_requires_system_message_first(prepared.get("model")):
                prepared["messages"] = _coalesce_system_messages_to_front(prepared.get("messages", []))
            if not nvidia_model_allows_tools(prepared.get("model")):
                prepared = _strip_tooling_from_payload(prepared)
                if nvidia_model_requires_system_message_first(prepared.get("model")):
                    prepared["messages"] = _coalesce_system_messages_to_front(prepared.get("messages", []))
            return prepared

        # Non-Qwen `request` provider: accept model(depth) but only convert to
        # a boolean `thinking` flag (do NOT forward thinking depth). Explicit
        # `self.thinking_mode` (config) takes precedence over model suffix.
        if self.provider == "request":
            if not (isinstance(self.thinking_mode, str) and self.thinking_mode.lower() in ["true", "false"]):
                model_name = str(prepared.get("model", "")).strip()
                if "(" in model_name and ")" in model_name:
                    base_model = model_name.split("(", 1)[0].strip()
                    suffix = model_name.split("(", 1)[1].split(")", 1)[0].strip().lower()
                    thinking_suffixes = {"auto", "low", "medium", "high", "xhigh", "minimal"}
                    if suffix in thinking_suffixes or suffix.isdigit():
                        prepared["model"] = base_model
                        chat_kwargs = prepared.get("chat_template_kwargs")
                        if not isinstance(chat_kwargs, dict):
                            chat_kwargs = {}
                            prepared["chat_template_kwargs"] = chat_kwargs
                        chat_kwargs["thinking"] = True
                    elif suffix in {"none", "0"}:
                        prepared["model"] = base_model
                        chat_kwargs = prepared.get("chat_template_kwargs")
                        if not isinstance(chat_kwargs, dict):
                            chat_kwargs = {}
                            prepared["chat_template_kwargs"] = chat_kwargs
                        chat_kwargs["thinking"] = False

        # Explicit thinking_mode from config takes precedence
        if self.thinking_mode and self.thinking_mode.lower() in ["true", "false"]:
            chat_kwargs = prepared.get("chat_template_kwargs")
            if not isinstance(chat_kwargs, dict):
                chat_kwargs = {}
                prepared["chat_template_kwargs"] = chat_kwargs
            chat_kwargs["thinking"] = self.thinking_mode.lower() == "true"

        return prepared

    def get_visible_tool_schemas(self, mode: Optional[str] = None) -> List[Dict[str, Any]]:
        """Return the tool schemas that the current model/provider can actually receive."""
        tool_executor = getattr(self, "tool_executor", None)
        if not tool_executor:
            return []

        effective_mode = mode or self.mode or "reverie"
        schemas = tool_executor.get_tool_schemas(mode=effective_mode)
        if not schemas:
            return []

        if (
            self._is_active_model_source("nvidia")
            or self._is_nvidia_request()
        ) and not nvidia_model_allows_tools(self.model):
            return []

        return schemas

    def _resolve_messages_for_request(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Resolve lightweight local-image markers into actual multimodal request payloads."""
        resolved_messages: List[Dict[str, Any]] = []
        for message in messages or []:
            if not isinstance(message, dict):
                continue
            normalized = dict(message)
            content = normalized.get("content")
            if isinstance(content, list):
                normalized["content"] = resolve_inline_image_content_for_request(content, self.project_root)
            resolved_messages.append(normalized)
        return resolved_messages

    def _build_openai_chat_completion_kwargs(
        self,
        *,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        stream: bool,
    ) -> Dict[str, Any]:
        """Build OpenAI SDK chat-completions kwargs, including NVIDIA-specific adapters."""
        extra_body = self._openai_extra_body_for_thinking()
        model_for_sdk = self.model
        prepared_messages = list(messages or [])
        if extra_body is not None and isinstance(model_for_sdk, str) and "(" in model_for_sdk and ")" in model_for_sdk:
            model_for_sdk = model_for_sdk.split("(", 1)[0].strip()

        if self._is_active_model_source("nvidia") and nvidia_model_requires_system_message_first(model_for_sdk):
            prepared_messages = _coalesce_system_messages_to_front(prepared_messages)

        kwargs: Dict[str, Any] = {
            "model": model_for_sdk,
            "messages": prepared_messages,
            "stream": bool(stream),
        }
        if tools:
            kwargs["tools"] = tools

        if self._is_active_model_source("nvidia"):
            nvidia_options = build_nvidia_openai_options(getattr(self.config, "nvidia", {}), model_for_sdk)
            if nvidia_options:
                option_model = str(nvidia_options.get("model", "") or "").strip()
                if option_model:
                    kwargs["model"] = option_model
                for key in ("temperature", "top_p", "max_tokens"):
                    if key in nvidia_options:
                        kwargs[key] = nvidia_options[key]
                extra_body = _merge_extra_body(extra_body, nvidia_options.get("extra_body"))

        if extra_body is not None:
            kwargs["extra_body"] = extra_body
        return kwargs

    def _request_provider_label(self) -> str:
        """Return a user-facing provider label for request-provider errors."""
        if self._is_qwencode_request():
            return "Qwen Code API"
        if self._is_nvidia_request():
            return "NVIDIA API"
        return "Request provider"

    def _resolve_anthropic_max_tokens(self) -> int:
        """Return max_tokens for Anthropic-compatible providers."""
        max_tokens = 4096
        if self._is_active_model_source("modelscope"):
            try:
                options = build_modelscope_anthropic_options(getattr(self.config, "modelscope", {}), self.model)
                candidate = int(options.get("max_tokens", max_tokens))
                if candidate > 0:
                    return candidate
            except Exception:
                return max_tokens
        return max_tokens

    def _completion_continuation_limit(self) -> int:
        """Return the continuation budget for a turn."""
        if normalize_mode(self.mode) == "computer-controller":
            return 24
        return 3

    def _should_stop_on_finish_reason(self) -> bool:
        """Whether a natural provider stop reason should end the turn."""
        return normalize_mode(self.mode) != "computer-controller"

    def _should_end_generation(self, collected_content: str, finish_reason: Optional[str]) -> bool:
        """Decide whether the current assistant turn is complete."""
        content = str(collected_content or "")
        if "//END//" in content:
            return True
        if not self._should_stop_on_finish_reason():
            return False
        return finish_reason in ("stop", "end_turn", "end", None)

    def _emit_ui_event(
        self,
        *,
        category: str,
        message: str,
        status: str = "info",
        detail: str = "",
        meta: str = "",
    ) -> None:
        """Send a structured UI event to the CLI surface when available."""
        handler = None
        try:
            handler = self.tool_executor.context.get("ui_event_handler")
        except Exception:
            handler = None

        payload = {
            "category": str(category or "").strip() or "Activity",
            "message": str(message or "").strip(),
            "status": str(status or "info").strip().lower(),
            "detail": str(detail or "").strip(),
            "meta": str(meta or "").strip(),
        }

        if callable(handler):
            try:
                handler(payload)
                return
            except Exception:
                logger.debug("Failed to emit UI event through handler", exc_info=True)

        plain = f"[{payload['category']}] {payload['message']}"
        if payload["detail"]:
            plain = f"{plain} ({payload['detail']})"
        if payload["meta"]:
            plain = f"{plain} [{payload['meta']}]"
        print(f"\n{plain}\n")

    def _emit_tool_stream_event(self, event_type: str, **payload: Any) -> None:
        """Forward non-streaming tool lifecycle events to the same UI surface."""
        handler = None
        try:
            handler = self.tool_executor.context.get("ui_event_handler")
        except Exception:
            handler = None
        if not callable(handler):
            return

        event = {
            "kind": "stream_event",
            "event": str(event_type or "").strip().lower(),
            **payload,
        }
        try:
            handler(event)
        except Exception:
            logger.debug("Failed to emit non-streaming tool event", exc_info=True)

    def _build_qwencode_request_headers(self, stream: bool) -> Dict[str, str]:
        """Build Qwen OAuth request headers from the current in-memory request state."""
        from ..qwencode import get_qwencode_request_headers

        headers = get_qwencode_request_headers()
        headers["Authorization"] = f"Bearer {self.api_key}"
        headers["Content-Type"] = "application/json"
        headers["Accept"] = "text/event-stream" if stream else "application/json"
        if self.custom_headers:
            headers.update(self.custom_headers)
        return headers

    def _sync_qwencode_request_state(self, force_refresh: bool = False) -> None:
        """Refresh Qwen OAuth credentials and endpoint pairing before a request."""
        if not self._is_qwencode_request():
            return

        from ..qwencode import (
            detect_qwencode_cli_credentials,
            resolve_qwencode_runtime_request_url,
        )

        cred = detect_qwencode_cli_credentials(
            refresh_if_needed=True,
            force_refresh=force_refresh,
        )
        if cred.get("found"):
            self.api_key = str(cred.get("api_key", "")).strip()

        if not self.api_key:
            raise ValueError("Qwen Code CLI credentials were not found. Please run /qwencode login first.")

        config = getattr(self, "config", None)
        qwencode_cfg = getattr(config, "qwencode", {}) if config else {}
        self.base_url = resolve_qwencode_runtime_request_url(qwencode_cfg, credentials=cred)

    def _is_qwencode_auth_http_error(self, error: Exception) -> bool:
        """Whether an HTTP error should trigger one forced Qwen OAuth refresh."""
        if not self._is_qwencode_request():
            return False

        try:
            import requests
        except Exception:
            return False

        if not isinstance(error, requests.exceptions.HTTPError):
            return False

        response = getattr(error, "response", None)
        status_code = getattr(response, "status_code", None)
        return status_code in (401, 403)

    def _make_request_with_provider_auth_retry(
        self,
        *,
        headers: Dict[str, str],
        payload: Dict[str, Any],
        stream: bool,
        timeout: int,
    ):
        """Execute request-provider calls with one Qwen OAuth forced-refresh retry on auth failure."""
        import requests

        try:
            return make_api_request_with_retry(
                url=self.base_url,
                headers=headers,
                payload=payload,
                max_retries=self.api_max_retries,
                initial_backoff=self.api_initial_backoff,
                stream=stream,
                timeout=timeout,
            )
        except requests.RequestException as e:
            if not self._is_qwencode_auth_http_error(e):
                raise

            logger.warning("Qwen OAuth request returned %s; forcing credential refresh and retrying once", getattr(getattr(e, "response", None), "status_code", "auth-error"))
            self._sync_qwencode_request_state(force_refresh=True)
            refreshed_headers = (
                self._build_qwencode_request_headers(stream=stream)
                if self._is_qwencode_request()
                else self._build_request_headers(stream=stream)
            )
            return make_api_request_with_retry(
                url=self.base_url,
                headers=refreshed_headers,
                payload=payload,
                max_retries=self.api_max_retries,
                initial_backoff=self.api_initial_backoff,
                stream=stream,
                timeout=timeout,
            )

    def _iter_sse_data_strings(self, response) -> Generator[str, None, None]:
        """Yield decoded SSE/JSON payloads from an HTTP streaming response."""
        yield from iter_provider_sse_data_strings(response)

    def _close_stream_response(self, response: Any) -> None:
        """Close a provider response object when it exposes a close method."""
        try:
            close = getattr(response, "close", None)
            if callable(close):
                close()
        except Exception:
            logger.debug("Failed to close streaming response", exc_info=True)

    def _apply_stream_event(
        self,
        state: _StreamingTurnState,
        event: Dict[str, Any],
    ) -> Generator[str, None, None]:
        """Apply one normalized stream event to the shared turn state."""
        if not isinstance(event, dict):
            return

        event_type = str(event.get("type", "") or "").strip().lower()
        if event_type == "reasoning":
            for chunk in state.add_reasoning(event.get("text", "")):
                yield chunk
            return

        if event_type == "content":
            for chunk in state.add_content(event.get("text", "")):
                yield chunk
            return

        if event_type in {"tool_call", "tool_call_start", "tool_call_args", "tool_call_delta"}:
            append_arguments = event_type in {"tool_call_args", "tool_call_delta"} and bool(
                event.get("append_arguments", event_type == "tool_call_args")
            )
            state.update_tool_call(
                int(event.get("index", 0) or 0),
                tool_call_id=str(event.get("id", "") or "").strip(),
                name=str(event.get("name", "") or "").strip(),
                arguments=event.get("arguments") if "arguments" in event else None,
                append_arguments=append_arguments,
                thought_signature=str(event.get("thought_signature", "") or "").strip(),
            )
            return

        if event_type == "finish":
            state.set_finish_reason(event.get("reason"))

    def _iter_openai_sdk_stream_events(self, response: Any) -> Generator[Dict[str, Any], None, None]:
        """Translate OpenAI SDK streaming chunks into normalized events."""
        for chunk in response:
            choice = chunk.choices[0] if chunk.choices else None
            if choice is None:
                continue

            if choice.finish_reason:
                yield {"type": "finish", "reason": choice.finish_reason}

            delta = choice.delta
            if delta is None:
                continue

            reasoning_content = _extract_text_from_candidates(
                delta,
                "reasoning_content",
                "thinking",
                "reasoning",
            )
            if reasoning_content:
                yield {"type": "reasoning", "text": reasoning_content}

            content_piece = _extract_text_from_candidates(delta, "content")
            if content_piece:
                yield {"type": "content", "text": content_piece}

            if not delta.tool_calls:
                continue

            for tool_call in delta.tool_calls:
                function = getattr(tool_call, "function", None)
                yield {
                    "type": "tool_call_delta",
                    "index": int(getattr(tool_call, "index", 0) or 0),
                    "id": str(getattr(tool_call, "id", "") or "").strip(),
                    "name": str(getattr(function, "name", "") or "").strip() if function else "",
                    "arguments": getattr(function, "arguments", None) if function else None,
                    "append_arguments": True,
                }

    def _iter_request_stream_events(
        self,
        response: Any,
        provider_label: str,
    ) -> Generator[Dict[str, Any], None, None]:
        """Translate OpenAI-compatible SSE chunks into normalized events."""
        for data_str in self._iter_sse_data_strings(response):
            try:
                chunk_data = json.loads(data_str)
            except json.JSONDecodeError:
                continue

            _raise_for_wrapped_api_error(chunk_data, provider_label=provider_label)
            normalized_chunk = _unwrap_openai_compatible_payload(chunk_data) or chunk_data

            choices = normalized_chunk.get("choices", [])
            if not choices:
                continue

            choice = choices[0]
            finish_reason = choice.get("finish_reason")
            if finish_reason:
                yield {"type": "finish", "reason": finish_reason}

            delta = choice.get("delta") or {}
            if not isinstance(delta, dict):
                delta = {}

            reasoning_content = _extract_text_from_candidates(
                delta,
                "reasoning_content",
                "thinking",
                "reasoning",
            )
            if not reasoning_content:
                reasoning_content = _extract_text_from_candidates(
                    choice,
                    "reasoning_content",
                    "thinking",
                    "reasoning",
                )
            if not reasoning_content:
                reasoning_content = _extract_text_from_candidates(
                    choice.get("message") if isinstance(choice, dict) else None,
                    "reasoning_content",
                    "thinking",
                    "reasoning",
                )
            if reasoning_content:
                yield {"type": "reasoning", "text": reasoning_content}

            content = _extract_text_from_candidates(delta, "content")
            if not content:
                content = _extract_text_from_candidates(
                    choice.get("message") if isinstance(choice, dict) else None,
                    "content",
                )
            if content:
                yield {"type": "content", "text": content}

            tool_calls_delta = delta.get("tool_calls", [])
            if not tool_calls_delta:
                continue

            for tool_call_delta in tool_calls_delta:
                function_delta = tool_call_delta.get("function", {})
                yield {
                    "type": "tool_call_delta",
                    "index": int(tool_call_delta.get("index", 0) or 0),
                    "id": str(tool_call_delta.get("id", "") or "").strip(),
                    "name": str(function_delta.get("name", "") or "").strip(),
                    "arguments": function_delta.get("arguments") if "arguments" in function_delta else None,
                    "append_arguments": "arguments" in function_delta,
                }

    def _commit_stream_state(
        self,
        *,
        state: _StreamingTurnState,
        request_messages: List[Dict[str, Any]],
        messages: List[Dict[str, Any]],
        session_id: str,
        usage: Any = None,
    ) -> tuple[str, str]:
        """Store the finalized turn and report which follow-up path to take."""
        clean_content = state.cleaned_content()

        if state.tool_calls:
            _sanitize_tool_calls(state.tool_calls)
            assistant_message = _build_assistant_history_message(
                clean_content or None,
                tool_calls=state.tool_calls,
                reasoning_content=state.collected_thinking,
            )
            self.messages.append(assistant_message)
            messages.append(assistant_message)
            self._record_model_usage(
                request_messages=request_messages,
                assistant_text=clean_content,
                reasoning_text=state.collected_thinking,
                tool_calls=state.tool_calls,
                usage=usage,
                session_id=session_id,
            )
            return "tool_calls", clean_content

        if clean_content:
            self.messages.append(
                _build_assistant_history_message(
                    clean_content,
                    reasoning_content=state.collected_thinking,
                )
            )
            self._record_model_usage(
                request_messages=request_messages,
                assistant_text=clean_content,
                reasoning_text=state.collected_thinking,
                usage=usage,
                session_id=session_id,
            )
            return "content", clean_content

        return "empty", clean_content

    def _execute_streamed_tool_calls(
        self,
        tool_calls: List[Dict[str, Any]],
        messages: List[Dict[str, Any]],
        session_id: str,
    ) -> Generator[str, None, None]:
        """Execute collected tool calls using the shared stream event surface."""
        for tool_call in tool_calls:
            yield from self._stream_execute_tool_call(
                tool_call,
                messages,
                session_id=session_id,
            )

    def _stream_execute_tool_call(
        self,
        tool_call: Dict[str, Any],
        messages: List[Dict[str, Any]],
        session_id: str = "default",
    ) -> Generator[str, None, None]:
        """Execute one tool call and emit structured UI events."""
        tool_name = str((tool_call.get("function") or {}).get("name", "")).strip()
        tool = self.tool_executor.get_tool(tool_name)
        args = parse_tool_arguments((tool_call.get("function") or {}).get("arguments", ""))

        self._check_tool_side_effects(tool_name, args)

        if self.rollback_manager:
            try:
                self.rollback_manager.create_pre_tool_checkpoint(
                    session_id=session_id,
                    messages=self.messages,
                    tool_name=tool_name,
                    arguments=args,
                )
            except Exception:
                logger.debug("Pre-tool checkpoint creation failed", exc_info=True)

        exec_msg = tool.get_execution_message(**args) if tool else f"Executing {tool_name}..."
        yield encode_stream_event(
            "tool_start",
            tool_name=tool_name,
            message=exec_msg,
            arguments=args,
            tool_call_id=str(tool_call.get("id", "")).strip(),
            agent_id=self.agent_id,
            agent_color=self.agent_color,
        )

        result = self.tool_executor.execute(
            tool_name,
            args,
            tool_call_id=str(tool_call.get("id", "")).strip(),
        )

        if self.operation_history:
            try:
                last_question = self.operation_history.get_last_user_question()
                parent_id = last_question.id if last_question else None
                self.operation_history.add_tool_call(
                    tool_name=tool_name,
                    arguments=args,
                    result=result.output if result.success else None,
                    success=result.success,
                    error=result.error,
                    parent_id=parent_id,
                )
            except Exception:
                logger.debug("Operation history tool logging failed", exc_info=True)

        yield encode_stream_event(
            "tool_result",
            tool_name=tool_name,
            message=exec_msg,
            arguments=args,
            tool_call_id=str(tool_call.get("id", "")).strip(),
            success=bool(result.success),
            output=str(result.output or ""),
            error=str(result.error or ""),
            status=str(getattr(result.status, "value", "success")),
            agent_id=self.agent_id,
            agent_color=self.agent_color,
        )

        tool_result_message = {
            "role": "tool",
            "tool_call_id": tool_call["id"],
            "content": _tool_result_content(result),
        }
        self.messages.append(tool_result_message)
        messages.append(tool_result_message)

    def _process_streaming_native_provider(self, provider_name: str, session_id: str = "default") -> Generator[str, None, None]:
        """Process streaming responses for native Gemini CLI / Codex providers."""
        import requests

        tools = self.get_visible_tool_schemas()

        max_continuations = self._completion_continuation_limit()
        continuation_count = 0

        while True:
            self._check_and_compress_context(session_id=session_id)
            messages = _sanitize_messages_for_relay(self._build_messages())
            request_messages = list(messages)
            parser_state: Dict[str, Any] = {}

            if provider_name == "gemini-cli":
                from ..geminicli import (
                    build_geminicli_request_payload,
                    detect_geminicli_cli_credentials,
                    get_geminicli_request_headers,
                    normalize_geminicli_config,
                    parse_geminicli_sse_event,
                    resolve_geminicli_project_id,
                    resolve_geminicli_request_url,
                )

                cfg = normalize_geminicli_config(getattr(self.config, "geminicli", {}))
                cred = detect_geminicli_cli_credentials(refresh_if_needed=True)
                if cred.get("found"):
                    self.api_key = str(cred.get("api_key", "")).strip()
                if not self.api_key:
                    detail = " | ".join(str(item) for item in cred.get("errors", []) if str(item).strip())
                    if detail:
                        raise ValueError(f"Gemini CLI credentials are unavailable: {detail}")
                    raise ValueError("Gemini CLI credentials were not found. Please run /Geminicli login first.")
                project_id = resolve_geminicli_project_id(
                    base_url=self.base_url,
                    access_token=self.api_key,
                    configured_project_id=str(cfg.get("project_id", "")).strip(),
                    extra_headers=self.custom_headers,
                    timeout=int(cfg.get("timeout", 1200) or 1200),
                )
                request_url = resolve_geminicli_request_url(self.base_url, self.endpoint, stream=True)
                payload = build_geminicli_request_payload(
                    model_name=self.model,
                    messages=messages,
                    tools=tools if tools else None,
                    project_id=project_id,
                    session_id=session_id,
                    user_prompt_id=f"reverie-{session_id}-{uuid.uuid4().hex[:12]}",
                )
                headers = get_geminicli_request_headers(
                    model_id=self.model,
                    access_token=self.api_key,
                    stream=True,
                    extra_headers=self.custom_headers,
                )
                parse_events = lambda data: parse_geminicli_sse_event(data)
            else:
                from ..codex import (
                    build_codex_request_payload,
                    detect_codex_cli_credentials,
                    get_codex_request_headers,
                    normalize_codex_config,
                    parse_codex_sse_event,
                    resolve_codex_request_url,
                )

                cfg = normalize_codex_config(getattr(self.config, "codex", {}))
                cred = detect_codex_cli_credentials()
                if cred.get("found"):
                    self.api_key = str(cred.get("api_key", "")).strip()
                if not self.api_key:
                    raise ValueError("Codex CLI credentials were not found. Please run /codex login first.")
                request_url = resolve_codex_request_url(self.base_url, self.endpoint or cfg.get("endpoint", ""))
                payload = build_codex_request_payload(
                    model_name=self.model,
                    messages=messages,
                    tools=tools if tools else None,
                    reasoning_effort=self.thinking_mode or cfg.get("reasoning_effort", "medium"),
                    stream=True,
                )
                headers = get_codex_request_headers(
                    api_key=self.api_key,
                    account_id=str(cred.get("account_id", "")).strip(),
                    auth_mode=str(cred.get("auth_mode", "")).strip(),
                    extra_headers=self.custom_headers,
                    stream=True,
                )
                parse_events = lambda data: parse_codex_sse_event(data, parser_state)[0]

            effective_timeout = self._resolve_provider_timeout()
            try:
                response = make_api_request_with_retry(
                    url=request_url,
                    headers=headers,
                    payload=payload,
                    max_retries=self.api_max_retries,
                    initial_backoff=self.api_initial_backoff,
                    stream=True,
                    timeout=effective_timeout,
                )
            except requests.RequestException as e:
                logger.error(f"Streaming API request failed for {provider_name}: {e}")
                raise

            state = _StreamingTurnState()
            try:
                for data_str in self._iter_sse_data_strings(response):
                    if provider_name == "codex":
                        from ..codex import parse_codex_sse_event

                        events, parser_state = parse_codex_sse_event(data_str, parser_state)
                    else:
                        events = parse_events(data_str)

                    for event in events:
                        yield from self._apply_stream_event(state, event)
            finally:
                for chunk in state.flush():
                    yield chunk
                self._close_stream_response(response)

            outcome, _ = self._commit_stream_state(
                state=state,
                request_messages=request_messages,
                messages=messages,
                session_id=session_id,
            )

            if outcome == "tool_calls":
                yield from self._execute_streamed_tool_calls(
                    state.tool_calls,
                    messages,
                    session_id=session_id,
                )

                continuation_count = 0
                continue

            if outcome == "content":
                if self._should_end_generation(state.collected_content, state.finish_reason):
                    break

                continuation_count += 1
                if continuation_count >= max_continuations:
                    break

                messages = _sanitize_messages_for_relay(self._build_messages())
                continue

            break

    def _process_non_streaming_native_provider(self, provider_name: str, session_id: str = "default") -> str:
        """Fallback non-streaming path for native providers via streaming aggregation."""
        chunks: List[str] = []
        for chunk in self._process_streaming_native_provider(provider_name=provider_name, session_id=session_id):
            if chunk in (THINKING_START_MARKER, THINKING_END_MARKER):
                continue
            chunks.append(chunk)
        return "".join(chunks)

    def _openai_extra_body_for_thinking(self) -> Optional[Dict[str, Any]]:
        """Build `extra_body` (OpenAI SDK) to enable/disable thinking for compatible models.

        Rules:
        - If `thinking_mode` is explicitly set to 'true', return chat_template_kwargs enabling thinking.
        - If `thinking_mode` is 'false', return None (do not send thinking flags).
        - If `thinking_mode` is unset, detect model suffix like "model(thinking)" and enable thinking for
          recognized suffixes (auto, low, medium, high, xhigh, minimal, digits).
        - For GLM-family models include `clear_thinking: False` when enabling thinking.
        """
        # Explicit override from config
        if isinstance(self.thinking_mode, str) and self.thinking_mode.lower() in ("true", "false"):
            if self.thinking_mode.lower() == "false":
                return None
            enable_thinking = True
        else:
            # Derive from model name suffix if present
            model_name = str(self.model or "").strip()
            enable_thinking = False
            if "(" in model_name and ")" in model_name:
                base_model = model_name.split("(", 1)[0].strip()
                suffix = model_name.split("(", 1)[1].split(")", 1)[0].strip().lower()
                thinking_suffixes = {"auto", "low", "medium", "high", "xhigh", "minimal"}
                if suffix in thinking_suffixes or suffix.isdigit():
                    enable_thinking = True
                elif suffix in {"none", "0"}:
                    return None
            else:
                # No explicit hint; do not enable thinking by default
                return None

        if not enable_thinking:
            return None

        chat_kwargs: Dict[str, Any] = {"enable_thinking": True, "thinking": True}
        if "glm" in (self.model or "").lower():
            # GLM variants prefer clear_thinking=False per hosted-provider logic
            chat_kwargs["clear_thinking"] = False

        return {"chat_template_kwargs": chat_kwargs}
    
    def set_context_engine(self, retriever, indexer, git_integration) -> None:
        """Update Context Engine references"""
        previous_context = dict(getattr(self.tool_executor, "context", {}) or {})
        self.tool_executor = ToolExecutor(
            project_root=self.project_root,
            retriever=retriever,
            indexer=indexer,
            git_integration=git_integration,
            lsp_manager=previous_context.get("lsp_manager"),
            memory_indexer=previous_context.get("memory_indexer"),
        )
        for key, value in previous_context.items():
            if key in {"project_root", "retriever", "indexer", "git_integration", "lsp_manager", "memory_indexer"}:
                continue
            self.tool_executor.update_context(key, value)
        self.tool_executor.update_context("agent", self)
    
    def _build_messages(
        self,
        include_reasoning: bool = False,
        resolve_local_images: bool = False,
    ) -> List[Dict]:
        """Build message list for API calls, optionally resolving local multimodal parts."""
        messages = [{"role": "system", "content": self.system_prompt}]
        for message in self.messages:
            if not isinstance(message, dict):
                continue
            normalized = dict(message)
            if not include_reasoning:
                normalized.pop("reasoning_content", None)
            messages.append(normalized)
        if resolve_local_images:
            return self._resolve_messages_for_request(messages)
        return messages
    
    def process_message(
        self,
        user_message: Any,
        stream: bool = True,
        session_id: str = "default",
        user_display_text: Optional[str] = None,
    ) -> Generator[str, None, None]:
        """
        Process a user message and yield responses.
        
        Args:
            user_message: The user's input
            stream: Whether to stream the response
            session_id: Current session ID for checkpointing
            user_display_text: Plain-text version used for checkpoints/history summaries
        
        Yields:
            Response chunks (or full response if not streaming)
        """
        display_text = str(user_display_text or "").strip()
        if not display_text:
            display_text = _coerce_text_fragments(user_message).strip()
        if not display_text and isinstance(user_message, list):
            display_text = "[image attachment]"

        # Create checkpoint before processing user question
        if self.rollback_manager:
            self.current_checkpoint_id = self.rollback_manager.create_pre_question_checkpoint(
                session_id=session_id,
                messages=self.messages,
                question=display_text
            )
        
        # Add user message to history
        self.messages.append({
            "role": "user",
            "content": user_message
        })
        
        # Record user question in operation history
        if self.operation_history:
            self.operation_history.add_user_question(
                question=display_text,
                message_index=len(self.messages) - 1,
                checkpoint_id=self.current_checkpoint_id
            )
        
        # Check for context threshold and auto-rotate if the session is too large
        self._check_and_compress_context(session_id=session_id)
        
        # Call model with tools
        try:
            if stream:
                yield from self._process_streaming(session_id=session_id)
            else:
                response = self._process_non_streaming(session_id=session_id)
                yield response
        except Exception as e:
            error_msg = f"Error processing message: {str(e)}"
            yield error_msg
    
    def _process_streaming(self, session_id: str = "default") -> Generator[str, None, None]:
        """Process with streaming response"""
        if self.provider == "openai-sdk":
            if self._should_use_openai_http_fallback():
                yield from self._process_streaming_openai_http_fallback(session_id=session_id)
            else:
                yield from self._process_streaming_openai_sdk(session_id=session_id)
        elif self.provider == "request":
            yield from self._process_streaming_request(session_id=session_id)
        elif self.provider == "anthropic":
            yield from self._process_streaming_anthropic(session_id=session_id)
        elif self.provider == "gemini-cli":
            yield from self._process_streaming_native_provider("gemini-cli", session_id=session_id)
        elif self.provider == "codex":
            yield from self._process_streaming_native_provider("codex", session_id=session_id)
        else:
            raise ValueError(f"Unknown provider: {self.provider}")
    
    def _process_streaming_openai_sdk(self, session_id: str = "default") -> Generator[str, None, None]:
        """Process with streaming response using OpenAI SDK"""
        tools = self.get_visible_tool_schemas()
        
        max_continuations = self._completion_continuation_limit()
        continuation_count = 0
        
        while True:
            self._check_and_compress_context(session_id=session_id)
            request_messages = self._build_messages()
            messages = self._build_messages(resolve_local_images=True)
            # For OpenAI-compatible SDK calls, include thinking flags via extra_body when applicable
            nvidia_options: Dict[str, Any] = {}
            extra_body = self._openai_extra_body_for_thinking()
            model_for_sdk = self.model
            if self._is_active_model_source("nvidia"):
                nvidia_options = build_nvidia_openai_options(
                    getattr(self.config, "nvidia", {}),
                    model_for_sdk,
                )
                option_model = str(nvidia_options.get("model", "") or "").strip()
                if option_model:
                    model_for_sdk = option_model
                extra_body = _merge_extra_body(extra_body, nvidia_options.get("extra_body"))
            if extra_body is not None and isinstance(model_for_sdk, str) and "(" in model_for_sdk and ")" in model_for_sdk:
                # Strip depth suffix for ordinary SDK calls — only send boolean thinking
                model_for_sdk = model_for_sdk.split("(", 1)[0].strip()
            if extra_body is not None:
                response = self._client.chat.completions.create(
                    model=model_for_sdk,
                    messages=messages,
                    tools=tools if tools else None,
                    stream=True,
                    extra_body=extra_body,
                    **{
                        key: value
                        for key, value in {
                            "temperature": nvidia_options.get("temperature"),
                            "top_p": nvidia_options.get("top_p"),
                            "max_tokens": nvidia_options.get("max_tokens"),
                        }.items()
                        if value is not None
                    },
                )
            else:
                response = self._client.chat.completions.create(
                    model=model_for_sdk,
                    messages=messages,
                    tools=tools if tools else None,
                    stream=True,
                    **{
                        key: value
                        for key, value in {
                            "temperature": nvidia_options.get("temperature"),
                            "top_p": nvidia_options.get("top_p"),
                            "max_tokens": nvidia_options.get("max_tokens"),
                        }.items()
                        if value is not None
                    },
                )
            
            state = _StreamingTurnState()
            try:
                for event in self._iter_openai_sdk_stream_events(response):
                    yield from self._apply_stream_event(state, event)
            finally:
                for chunk in state.flush():
                    yield chunk
                self._close_stream_response(response)

            outcome, _ = self._commit_stream_state(
                state=state,
                request_messages=request_messages,
                messages=messages,
                session_id=session_id,
            )

            if outcome == "tool_calls":
                yield from self._execute_streamed_tool_calls(
                    state.tool_calls,
                    messages,
                    session_id=session_id,
                )
                continuation_count = 0
                continue

            if outcome == "content":
                if self._should_end_generation(state.collected_content, state.finish_reason):
                    break

                continuation_count += 1
                if continuation_count >= max_continuations:
                    break

                messages = self._build_messages(resolve_local_images=True)
                continue

            break
    
    def _process_streaming_request(self, session_id: str = "default") -> Generator[str, None, None]:
        """Process with streaming response using requests library"""
        import requests
        
        tools = self.get_visible_tool_schemas()
        
        max_continuations = self._completion_continuation_limit()
        continuation_count = 0
        
        while True:
            self._check_and_compress_context(session_id=session_id)
            request_messages = self._build_messages()
            messages = self._build_messages(resolve_local_images=True)
            # Build payload
            payload = {
                "model": self.model,
                "messages": messages,
                "stream": True,
            }
            
            # Add tools if available
            if tools:
                payload["tools"] = tools
            payload = self._prepare_request_payload(payload, session_id=session_id)
            headers = self._build_request_headers(stream=True)
            
            # Make request with retry logic.
            # Streaming request-provider calls can take longer for large outputs,
            # so we respect the provider timeout resolution here.
            effective_timeout = self._resolve_provider_timeout()
            try:
                response = self._make_request_with_provider_auth_retry(
                    headers=headers,
                    payload=payload,
                    stream=True,
                    timeout=effective_timeout,
                )
            except requests.RequestException as e:
                logger.error(f"Streaming API request failed: {e}")
                raise
            
            state = _StreamingTurnState()
            provider_label = self._request_provider_label()

            try:
                for event in self._iter_request_stream_events(response, provider_label):
                    yield from self._apply_stream_event(state, event)
            finally:
                for chunk in state.flush():
                    yield chunk
                self._close_stream_response(response)

            outcome, _ = self._commit_stream_state(
                state=state,
                request_messages=request_messages,
                messages=messages,
                session_id=session_id,
            )

            if outcome == "tool_calls":
                yield from self._execute_streamed_tool_calls(
                    state.tool_calls,
                    messages,
                    session_id=session_id,
                )
                continuation_count = 0
                continue

            if outcome == "content":
                if self._should_end_generation(state.collected_content, state.finish_reason):
                    break

                continuation_count += 1
                if continuation_count >= max_continuations:
                    break

                messages = self._build_messages(resolve_local_images=True)
                continue

            break
    
    def _process_streaming_anthropic(self, session_id: str = "default") -> Generator[str, None, None]:
        """Process with streaming response using Anthropic SDK"""
        tools = self.get_visible_tool_schemas()
        anthropic_tools = _convert_tools_to_anthropic_format(tools)
        
        max_continuations = self._completion_continuation_limit()
        continuation_count = 0
        
        while True:
            self._check_and_compress_context(session_id=session_id)
            request_messages = self._build_messages()
            messages = self._build_messages(resolve_local_images=True)
            system_message, anthropic_messages = _convert_messages_to_anthropic_format(messages)
            # Build kwargs for Anthropic API
            kwargs = {
                "model": self.model,
                "messages": anthropic_messages,
                "max_tokens": self._resolve_anthropic_max_tokens(),
                "stream": True
            }
            
            if system_message:
                kwargs["system"] = system_message
            
            if anthropic_tools:
                kwargs["tools"] = anthropic_tools
            
            # Make request
            with self._client.messages.stream(**kwargs) as stream:
                state = _StreamingTurnState()

                for event in stream:
                    if event.type == "content_block_delta" and hasattr(event.delta, "type"):
                        if event.delta.type == "thinking_delta" and hasattr(event.delta, "thinking"):
                            yield from self._apply_stream_event(
                                state,
                                {"type": "reasoning", "text": event.delta.thinking},
                            )
                        elif event.delta.type == "text_delta" and hasattr(event.delta, "text"):
                            yield from self._apply_stream_event(
                                state,
                                {"type": "content", "text": event.delta.text},
                            )
                    elif event.type == "message_stop":
                        break

                for chunk in state.flush():
                    yield chunk
                
                # Get final message for tool calls
                final_message = stream.get_final_message()
                state.set_finish_reason(getattr(final_message, "stop_reason", None))
                
                # Check for tool use blocks
                tool_use_blocks = [block for block in final_message.content if block.type == "tool_use"]
                
                for block in tool_use_blocks:
                    state.update_tool_call(
                        len(state.tool_calls),
                        tool_call_id=block.id,
                        name=block.name,
                        arguments=json.dumps(block.input),
                    )

                outcome, _ = self._commit_stream_state(
                    state=state,
                    request_messages=request_messages,
                    messages=messages,
                    session_id=session_id,
                    usage=getattr(final_message, "usage", None),
                )

                if outcome == "tool_calls":
                    yield from self._execute_streamed_tool_calls(
                        state.tool_calls,
                        messages,
                        session_id=session_id,
                    )
                    continuation_count = 0
                    continue

                if outcome == "content":
                    if self._should_end_generation(state.collected_content, state.finish_reason):
                        break

                    continuation_count += 1
                    if continuation_count >= max_continuations:
                        break

                    system_message, anthropic_messages = _convert_messages_to_anthropic_format(self._build_messages())
                    continue
            
            break
    
    def _process_non_streaming(self, session_id: str = "default") -> str:
        """Process without streaming"""
        if self.provider == "openai-sdk":
            if self._should_use_openai_http_fallback():
                return self._process_non_streaming_openai_http_fallback(session_id=session_id)
            return self._process_non_streaming_openai_sdk(session_id=session_id)
        elif self.provider == "request":
            return self._process_non_streaming_request(session_id=session_id)
        elif self.provider == "anthropic":
            return self._process_non_streaming_anthropic(session_id=session_id)
        elif self.provider == "gemini-cli":
            return self._process_non_streaming_native_provider("gemini-cli", session_id=session_id)
        elif self.provider == "codex":
            return self._process_non_streaming_native_provider("codex", session_id=session_id)
        else:
            raise ValueError(f"Unknown provider: {self.provider}")
    
    def _process_non_streaming_openai_sdk(self, session_id: str = "default") -> str:
        """Process without streaming using OpenAI SDK"""
        tools = self.get_visible_tool_schemas()
        
        all_content = []
        
        while True:
            self._check_and_compress_context(session_id=session_id)
            request_messages = self._build_messages()
            messages = self._build_messages(resolve_local_images=True)
            # For OpenAI-compatible SDK calls, include thinking flags via extra_body when applicable
            nvidia_options: Dict[str, Any] = {}
            extra_body = self._openai_extra_body_for_thinking()
            model_for_sdk = self.model
            if self._is_active_model_source("nvidia"):
                nvidia_options = build_nvidia_openai_options(
                    getattr(self.config, "nvidia", {}),
                    model_for_sdk,
                )
                option_model = str(nvidia_options.get("model", "") or "").strip()
                if option_model:
                    model_for_sdk = option_model
                extra_body = _merge_extra_body(extra_body, nvidia_options.get("extra_body"))
            if extra_body is not None and isinstance(model_for_sdk, str) and "(" in model_for_sdk and ")" in model_for_sdk:
                # Strip depth suffix for ordinary SDK calls — only send boolean thinking
                model_for_sdk = model_for_sdk.split("(", 1)[0].strip()
            if extra_body is not None:
                response = self._client.chat.completions.create(
                    model=model_for_sdk,
                    messages=messages,
                    tools=tools if tools else None,
                    stream=False,
                    extra_body=extra_body,
                    **{
                        key: value
                        for key, value in {
                            "temperature": nvidia_options.get("temperature"),
                            "top_p": nvidia_options.get("top_p"),
                            "max_tokens": nvidia_options.get("max_tokens"),
                        }.items()
                        if value is not None
                    },
                )
            else:
                response = self._client.chat.completions.create(
                    model=model_for_sdk,
                    messages=messages,
                    tools=tools if tools else None,
                    stream=False,
                    **{
                        key: value
                        for key, value in {
                            "temperature": nvidia_options.get("temperature"),
                            "top_p": nvidia_options.get("top_p"),
                            "max_tokens": nvidia_options.get("max_tokens"),
                        }.items()
                        if value is not None
                    },
                )
            
            choice = response.choices[0]
            message = choice.message
            message_content = _coerce_text_fragments(getattr(message, "content", None))
            message_reasoning = _extract_text_from_candidates(
                message,
                "reasoning_content",
                "thinking",
                "reasoning",
            )
            
            # Check for tool calls
            if message.tool_calls:
                # Add assistant message
                assistant_message = _build_assistant_history_message(
                    message_content or None,
                    tool_calls=[
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments
                            }
                        }
                        for tc in message.tool_calls
                    ],
                    reasoning_content=message_reasoning,
                )
                self.messages.append(assistant_message)
                messages.append(assistant_message)
                self._record_model_usage(
                    request_messages=request_messages,
                    assistant_text=message_content,
                    reasoning_text=message_reasoning,
                    tool_calls=assistant_message.get("tool_calls"),
                    usage=getattr(response, "usage", None),
                    session_id=session_id,
                )
                
                if message_content:
                    all_content.append(message_content)
                
                # Execute each tool
                for tool_call in message.tool_calls:
                    tool_name = tool_call.function.name
                    tool = self.tool_executor.get_tool(tool_name)
                    
                    args = parse_tool_arguments(tool_call.function.arguments)
                    
                    # Check side effects
                    self._check_tool_side_effects(tool_name, args)
                    
                    exec_msg = tool.get_execution_message(**args) if tool else f"Executing {tool_name}..."
                    self._emit_tool_stream_event(
                        "tool_start",
                        tool_name=tool_name,
                        message=exec_msg,
                        arguments=args,
                        tool_call_id=str(tool_call.id or ""),
                        agent_id=self.agent_id,
                        agent_color=self.agent_color,
                    )
                    
                    all_content.append(f"[bold #ffb8d1]✧[/bold #ffb8d1] [bold #e4b0ff]{rich_escape(exec_msg)}[/bold #e4b0ff]")
                    
                    result = self.tool_executor.execute(tool_name, args, tool_call_id=str(tool_call.id or ""))
                    self._emit_tool_stream_event(
                        "tool_result",
                        tool_name=tool_name,
                        message=exec_msg,
                        arguments=args,
                        tool_call_id=str(tool_call.id or ""),
                        success=bool(result.success),
                        output=str(result.output or ""),
                        error=str(result.error or ""),
                        status=str(getattr(result.status, "value", "success")),
                        agent_id=self.agent_id,
                        agent_color=self.agent_color,
                    )
                    
                    if result.success:
                        all_content.append(f"[bold #66bb6a]   ✔ Success[/bold #66bb6a]")
                    else:
                        all_content.append(f"[bold #ff5252]   ✘ Failed:[/bold #ff5252] [#ff8a80]{rich_escape(result.error or '')}[/#ff8a80]")
                    
                    # Add tool result
                    tool_result_message = {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": _tool_result_content(result)
                    }
                    self.messages.append(tool_result_message)
                    messages.append(tool_result_message)
                
                # Continue to get response to tool results
                continue
            
            # No tool calls, final response check
            if message_content:
                content = message_content
                
                if self._should_end_generation(content, None):
                    clean_content = content.replace("//END//", "").strip()
                    self.messages.append(
                        _build_assistant_history_message(
                            clean_content,
                            reasoning_content=message_reasoning,
                        )
                    )
                    self._record_model_usage(
                        request_messages=request_messages,
                        assistant_text=clean_content,
                        reasoning_text=message_reasoning,
                        usage=getattr(response, "usage", None),
                        session_id=session_id,
                    )
                    all_content.append(clean_content) # Use clean content for return
                    break
                
                # Missing termination token - continue
                if self.messages and self.messages[-1].get("role") == "assistant" and "tool_calls" not in self.messages[-1]:
                    self.messages[-1]["content"] += content
                else:
                    self.messages.append(
                        _build_assistant_history_message(
                            content,
                            reasoning_content=message_reasoning,
                        )
                    )
                
                self._record_model_usage(
                    request_messages=request_messages,
                    assistant_text=content,
                    reasoning_text=message_reasoning,
                    usage=getattr(response, "usage", None),
                    session_id=session_id,
                )
                
                all_content.append(content)
                
                # Rebuild messages for next call
                messages = self._build_messages(resolve_local_images=True)
                continue
            
            break
        
        return '\n'.join(all_content)
    
    def _process_non_streaming_request(self, session_id: str = "default") -> str:
        """Process without streaming using requests library"""
        import requests
        
        tools = self.get_visible_tool_schemas()
        
        all_content = []
        
        while True:
            self._check_and_compress_context(session_id=session_id)
            request_messages = self._build_messages()
            messages = self._build_messages(resolve_local_images=True)
            # Build payload
            payload = {
                "model": self.model,
                "messages": messages,
                "stream": False,
            }
            
            # Add tools if available
            if tools:
                payload["tools"] = tools
            payload = self._prepare_request_payload(payload, session_id=session_id)
            headers = self._build_request_headers(stream=False)
            
            # Make request with retry logic.
            # Long request-provider responses may need the provider timeout.
            effective_timeout = self._resolve_provider_timeout()
            try:
                response = self._make_request_with_provider_auth_retry(
                    headers=headers,
                    payload=payload,
                    stream=False,
                    timeout=effective_timeout,
                )
            except requests.RequestException as e:
                logger.error(f"API request failed: {e}")
                raise
            
            response_data = response.json()
            provider_label = self._request_provider_label()
            _raise_for_wrapped_api_error(response_data, provider_label=provider_label)
            normalized_response = _unwrap_openai_compatible_payload(response_data) or response_data
            usage_payload = normalized_response.get("usage") if isinstance(normalized_response, dict) else None
            
            # Extract choice
            choices = normalized_response.get("choices", [])
            if not choices:
                raise ValueError(f"{provider_label} returned no choices in the response payload")
            
            choice = choices[0]
            message = choice.get("message", {})
            message_content = _extract_text_from_candidates(message, "content")
            message_reasoning = _extract_text_from_candidates(
                message,
                "reasoning_content",
                "thinking",
                "reasoning",
            )
            
            # Check for tool calls
            tool_calls = message.get("tool_calls", [])
            if tool_calls:
                # Sanitize incoming tool-call argument strings before storing
                _sanitize_tool_calls(tool_calls)
                # Add assistant message
                assistant_message = _build_assistant_history_message(
                    message_content or None,
                    tool_calls=tool_calls,
                    reasoning_content=message_reasoning,
                )
                self.messages.append(assistant_message)
                messages.append(assistant_message)
                self._record_model_usage(
                    request_messages=request_messages,
                    assistant_text=message_content,
                    reasoning_text=message_reasoning,
                    tool_calls=tool_calls,
                    usage=usage_payload,
                    session_id=session_id,
                )
                
                if message_content:
                    all_content.append(message_content)
                
                # Execute each tool
                for tool_call in tool_calls:
                    tool_name = tool_call["function"]["name"]
                    tool = self.tool_executor.get_tool(tool_name)
                    
                    args = parse_tool_arguments(tool_call["function"]["arguments"])
                    
                    self._check_tool_side_effects(tool_name, args)
                    
                    exec_msg = tool.get_execution_message(**args) if tool else f"Executing {tool_name}..."
                    self._emit_tool_stream_event(
                        "tool_start",
                        tool_name=tool_name,
                        message=exec_msg,
                        arguments=args,
                        tool_call_id=str(tool_call.get("id", "")).strip(),
                        agent_id=self.agent_id,
                        agent_color=self.agent_color,
                    )
                    all_content.append(f"[bold #ffb8d1]✧[/bold #ffb8d1] [bold #e4b0ff]{rich_escape(exec_msg)}[/bold #e4b0ff]")
                    
                    result = self.tool_executor.execute(
                        tool_name,
                        args,
                        tool_call_id=str(tool_call.get("id", "")).strip(),
                    )
                    self._emit_tool_stream_event(
                        "tool_result",
                        tool_name=tool_name,
                        message=exec_msg,
                        arguments=args,
                        tool_call_id=str(tool_call.get("id", "")).strip(),
                        success=bool(result.success),
                        output=str(result.output or ""),
                        error=str(result.error or ""),
                        status=str(getattr(result.status, "value", "success")),
                        agent_id=self.agent_id,
                        agent_color=self.agent_color,
                    )
                    
                    if result.success:
                        all_content.append(f"[bold #66bb6a]   ✔ Success[/bold #66bb6a]")
                    else:
                        all_content.append(f"[bold #ff5252]   ✘ Failed:[/bold #ff5252] [#ff8a80]{rich_escape(result.error or '')}[/#ff8a80]")
                    
                    tool_result_message = {
                        "role": "tool",
                        "tool_call_id": tool_call["id"],
                        "content": _tool_result_content(result)
                    }
                    self.messages.append(tool_result_message)
                    messages.append(tool_result_message)
                
                continue
            
            # No tool calls, final response check
            content = message_content
            if content:
                if self._should_end_generation(content, None):
                    clean_content = content.replace("//END//", "").strip()
                    self.messages.append(
                        _build_assistant_history_message(
                            clean_content,
                            reasoning_content=message_reasoning,
                        )
                    )
                    self._record_model_usage(
                        request_messages=request_messages,
                        assistant_text=clean_content,
                        reasoning_text=message_reasoning,
                        usage=usage_payload,
                        session_id=session_id,
                    )
                    all_content.append(clean_content)
                    break
                
                if self.messages and self.messages[-1].get("role") == "assistant" and "tool_calls" not in self.messages[-1]:
                    self.messages[-1]["content"] += content
                else:
                    self.messages.append(
                        _build_assistant_history_message(
                            content,
                            reasoning_content=message_reasoning,
                        )
                    )
                
                self._record_model_usage(
                    request_messages=request_messages,
                    assistant_text=content,
                    reasoning_text=message_reasoning,
                    usage=usage_payload,
                    session_id=session_id,
                )
                
                all_content.append(content)
                messages = self._build_messages(resolve_local_images=True)
                continue
            
            break
        
        return '\n'.join(all_content)
    
    def _process_non_streaming_anthropic(self, session_id: str = "default") -> str:
        """Process without streaming using Anthropic SDK"""
        tools = self.get_visible_tool_schemas()
        anthropic_tools = _convert_tools_to_anthropic_format(tools)
        
        all_content = []
        
        while True:
            self._check_and_compress_context(session_id=session_id)
            messages = self._build_messages()
            request_messages = list(messages)
            system_message, anthropic_messages = _convert_messages_to_anthropic_format(messages)
            # Build kwargs for Anthropic API
            kwargs = {
                "model": self.model,
                "messages": anthropic_messages,
                "max_tokens": self._resolve_anthropic_max_tokens(),
            }
            
            if system_message:
                kwargs["system"] = system_message
            
            if anthropic_tools:
                kwargs["tools"] = anthropic_tools
            
            # Make request
            response = self._client.messages.create(**kwargs)
            
            # Extract content
            content_blocks = response.content
            collected_content = ""
            collected_tool_calls = []
            
            for block in content_blocks:
                if block.type == "text":
                    collected_content += block.text
                elif block.type == "tool_use":
                    collected_tool_calls.append({
                        "id": block.id,
                        "type": "function",
                        "function": {
                            "name": block.name,
                            "arguments": json.dumps(block.input)
                        }
                    })
            
            # Check for tool calls
            if collected_tool_calls:
                # Sanitize tool args before adding to message history
                _sanitize_tool_calls(collected_tool_calls)
                assistant_message = _build_assistant_history_message(
                    collected_content or None,
                    tool_calls=collected_tool_calls,
                )
                self.messages.append(assistant_message)
                self._record_model_usage(
                    request_messages=request_messages,
                    assistant_text=collected_content,
                    tool_calls=collected_tool_calls,
                    usage=getattr(response, "usage", None),
                    session_id=session_id,
                )
                anthropic_messages.append(
                    {
                        "role": "assistant",
                        "content": _build_anthropic_assistant_tool_blocks(collected_content, collected_tool_calls),
                    }
                )
                
                if collected_content:
                    all_content.append(collected_content)
                
                # Execute each tool
                tool_result_blocks: List[Dict[str, Any]] = []
                for tool_call in collected_tool_calls:
                    tool_name = tool_call["function"]["name"]
                    tool = self.tool_executor.get_tool(tool_name)
                    
                    args = parse_tool_arguments(tool_call["function"]["arguments"])
                    
                    self._check_tool_side_effects(tool_name, args)
                    
                    exec_msg = tool.get_execution_message(**args) if tool else f"Executing {tool_name}..."
                    self._emit_tool_stream_event(
                        "tool_start",
                        tool_name=tool_name,
                        message=exec_msg,
                        arguments=args,
                        tool_call_id=str(tool_call.get("id", "")).strip(),
                        agent_id=self.agent_id,
                        agent_color=self.agent_color,
                    )
                    all_content.append(f"[bold #ffb8d1]✧[/bold #ffb8d1] [bold #e4b0ff]{rich_escape(exec_msg)}[/bold #e4b0ff]")
                    
                    result = self.tool_executor.execute(
                        tool_name,
                        args,
                        tool_call_id=str(tool_call.get("id", "")).strip(),
                    )
                    self._emit_tool_stream_event(
                        "tool_result",
                        tool_name=tool_name,
                        message=exec_msg,
                        arguments=args,
                        tool_call_id=str(tool_call.get("id", "")).strip(),
                        success=bool(result.success),
                        output=str(result.output or ""),
                        error=str(result.error or ""),
                        status=str(getattr(result.status, "value", "success")),
                        agent_id=self.agent_id,
                        agent_color=self.agent_color,
                    )
                    
                    if result.success:
                        all_content.append(f"[bold #66bb6a]   ✔ Success[/bold #66bb6a]")
                    else:
                        all_content.append(f"[bold #ff5252]   ✘ Failed:[/bold #ff5252] [#ff8a80]{rich_escape(result.error or '')}[/#ff8a80]")
                    
                    tool_result_message = {
                        "role": "tool",
                        "tool_call_id": tool_call["id"],
                        "content": _tool_result_content(result)
                    }
                    self.messages.append(tool_result_message)
                    tool_result_blocks.append(_build_anthropic_tool_result_block(tool_call["id"], result))

                if tool_result_blocks:
                    anthropic_messages.append({"role": "user", "content": tool_result_blocks})
                
                continue
            
            # No tool calls, final response check
            if collected_content:
                if self._should_end_generation(collected_content, None):
                    clean_content = collected_content.replace("//END//", "").strip()
                    self.messages.append(_build_assistant_history_message(clean_content))
                    self._record_model_usage(
                        request_messages=request_messages,
                        assistant_text=clean_content,
                        usage=getattr(response, "usage", None),
                        session_id=session_id,
                    )
                    all_content.append(clean_content)
                    break
                
                if self.messages and self.messages[-1].get("role") == "assistant" and "tool_calls" not in self.messages[-1]:
                    self.messages[-1]["content"] += collected_content
                else:
                    self.messages.append(_build_assistant_history_message(collected_content))
                
                self._record_model_usage(
                    request_messages=request_messages,
                    assistant_text=collected_content,
                    usage=getattr(response, "usage", None),
                    session_id=session_id,
                )
                
                all_content.append(collected_content)
                system_message, anthropic_messages = _convert_messages_to_anthropic_format(self._build_messages())
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

    def _history_from_request_messages(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Convert request messages back into persisted history without duplicating the base system prompt."""
        if not isinstance(messages, list):
            return []

        history = [dict(message) for message in messages if isinstance(message, dict)]
        if history:
            first = history[0]
            if (
                str(first.get("role", "") or "").strip().lower() == "system"
                and _coerce_text_fragments(first.get("content")) == self.system_prompt
            ):
                history = history[1:]
        return history

    def _persist_history_to_session(self) -> None:
        """Persist the current in-memory history to the active session when available."""
        session_manager = self.tool_executor.context.get("session_manager")
        if not session_manager:
            return
        try:
            session_manager.update_messages(self.messages)
        except Exception:
            logger.debug("Failed to persist session messages", exc_info=True)

    def _token_estimate_signature(self) -> tuple[Any, ...]:
        """Build a cheap cache key for repeated context-usage checks."""
        messages = self.messages if isinstance(self.messages, list) else []
        tail_signature: List[tuple[Any, ...]] = []
        for message in messages[-3:]:
            if not isinstance(message, dict):
                tail_signature.append((type(message).__name__, len(str(message))))
                continue
            content_len = len(_coerce_text_fragments(message.get("content")))
            reasoning_len = len(_coerce_text_fragments(message.get("reasoning_content")))
            tool_calls = message.get("tool_calls")
            tool_count = len(tool_calls) if isinstance(tool_calls, list) else 0
            tool_call_id = str(message.get("tool_call_id", "") or "").strip()
            name = str(message.get("name", "") or "").strip()
            tail_signature.append(
                (
                    str(message.get("role", "") or "").strip().lower(),
                    content_len,
                    reasoning_len,
                    tool_count,
                    len(tool_call_id),
                    len(name),
                )
            )
        return (
            len(messages),
            len(self.system_prompt),
            tuple(tail_signature),
        )

    def _current_session_details(self, fallback_session_id: str = "default") -> tuple[str, str]:
        """Return the active session id/name for stats and continuity features."""
        session_id = str(fallback_session_id or "").strip() or "default"
        session_name = ""

        session_manager = self.tool_executor.context.get("session_manager")
        if not session_manager or not hasattr(session_manager, "get_current_session"):
            return session_id, session_name

        try:
            current_session = session_manager.get_current_session()
        except Exception:
            logger.debug("Failed to fetch current session details", exc_info=True)
            return session_id, session_name

        if not current_session:
            return session_id, session_name

        current_session_id = str(getattr(current_session, "id", "") or "").strip()
        current_session_name = str(getattr(current_session, "name", "") or "").strip()
        return current_session_id or session_id, current_session_name

    def _record_model_usage(
        self,
        *,
        request_messages: List[Dict[str, Any]],
        assistant_text: str = "",
        reasoning_text: str = "",
        tool_calls: Optional[List[Dict[str, Any]]] = None,
        usage: Any = None,
        session_id: str = "default",
        source: str = "chat",
        interaction_type: str = "chat",
    ) -> None:
        """Record workspace-level token usage for one model call."""
        workspace_stats_manager = self.tool_executor.context.get("workspace_stats_manager")
        if not workspace_stats_manager:
            return

        resolved_session_id, session_name = self._current_session_details(session_id)
        try:
            workspace_stats_manager.record_model_usage(
                provider=self.provider,
                source=source,
                model=self.model,
                model_display_name=self.model_display_name,
                request_messages=request_messages,
                assistant_text=assistant_text,
                reasoning_text=reasoning_text,
                tool_calls=tool_calls,
                usage=usage,
                session_id=resolved_session_id,
                session_name=session_name,
                interaction_type=interaction_type,
            )
        except Exception:
            logger.debug("Failed to record workspace model usage", exc_info=True)

    def _resolve_max_context_tokens(self) -> int:
        """Resolve the active model context window from runtime configuration."""
        max_tokens = 128000
        config_manager = self.tool_executor.context.get('config_manager')

        if config_manager:
            model_config = config_manager.get_active_model()
            if model_config and model_config.max_context_tokens:
                return model_config.max_context_tokens
            config = config_manager.load()
            return getattr(config, 'max_context_tokens', max_tokens)

        if hasattr(self, 'config'):
            return getattr(self.config, 'max_context_tokens', max_tokens)

        return max_tokens

    def _latest_user_message_text(self) -> str:
        """Return the latest user message text from the live conversation."""
        for message in reversed(self.messages):
            if str(message.get("role", "") or "").strip().lower() != "user":
                continue
            text = _coerce_text_fragments(message.get("content"))
            if text:
                return text
        return ""

    def _workspace_memory_for_rotation(self, latest_user_message: str) -> str:
        """Fetch a compact workspace-memory hint for auto-rotation handoff."""
        if normalize_mode(self.mode) == "computer-controller":
            return ""
        memory_indexer = self.tool_executor.context.get("memory_indexer")
        if not memory_indexer:
            return ""
        try:
            return memory_indexer.build_workspace_memory_summary(
                query=latest_user_message or None,
                max_fragments=6,
                max_chars=2400,
            )
        except Exception:
            logger.debug("Workspace memory fetch failed during auto-rotation", exc_info=True)
            return ""

    def _handle_context_compaction(
        self,
        current_tokens: int,
        max_tokens: int,
        session_id: str = "default",
    ) -> int:
        """Compress the active conversation in-place before a full session rotation becomes necessary."""
        if self._auto_context_compaction_active:
            return current_tokens
        if self._auto_context_compaction_retry_after and time.time() < self._auto_context_compaction_retry_after:
            return current_tokens

        from ..config import get_project_data_dir
        from ..context_engine.compressor import ContextCompressor

        project_root = self.tool_executor.context.get("project_root") or self.project_root
        project_data_dir = self.tool_executor.context.get("project_data_dir")
        cache_dir = Path(project_data_dir) if project_data_dir else get_project_data_dir(Path(project_root))
        request_messages = self._build_messages()
        client = self._client if self.provider in {"openai-sdk", "anthropic"} else None

        self._auto_context_compaction_active = True
        try:
            try:
                compressor = ContextCompressor(cache_dir)
                compressed_messages = compressor.compress(
                    messages=request_messages,
                    client=client,
                    model=self.model,
                    session_id=session_id,
                    provider=self.provider,
                    base_url=self.base_url,
                    api_key=self.api_key,
                    custom_headers=self.custom_headers,
                    workspace_stats_manager=self.tool_executor.context.get("workspace_stats_manager"),
                    model_display_name=self.model_display_name,
                )
            except Exception:
                logger.debug(
                    "Automatic context compaction failed; deferring retry window",
                    exc_info=True,
                )
                self._auto_context_compaction_retry_after = time.time() + 30.0
                return current_tokens

            new_history = self._history_from_request_messages(compressed_messages)
            if new_history and new_history != self.messages:
                self.messages = new_history
                self._persist_history_to_session()
                self._auto_context_compaction_retry_after = 0.0
            else:
                self._auto_context_compaction_retry_after = time.time() + 30.0

            return self.get_token_estimate()
        finally:
            self._auto_context_compaction_active = False
    
    def _check_and_compress_context(self, session_id: str = "default") -> None:
        """
        Compact the active session before rotating to a fresh one when the context is too large.

        First attempt an in-place LLM compression pass. If the prompt still
        remains too large, prepare a model-authored handoff and rotate into a
        fresh session while keeping the active request alive.
        """
        if self._auto_context_rotation_active:
            return

        max_tokens = self._resolve_max_context_tokens()
        if max_tokens <= 0:
            return

        token_estimate = self.get_token_estimate()
        compaction_threshold = max_tokens * 0.7
        rotation_threshold = max_tokens * 0.82

        if token_estimate >= compaction_threshold:
            token_estimate = self._handle_context_compaction(token_estimate, max_tokens, session_id=session_id)

        if self._auto_context_rotation_retry_after and time.time() < self._auto_context_rotation_retry_after:
            return
        if token_estimate >= rotation_threshold:
            self._handle_session_rotation(token_estimate, max_tokens, session_id=session_id)
    
    def _handle_session_rotation(self, current_tokens: int, max_tokens: int, session_id: str = "default") -> None:
        """
        Handle session rotation at 80% threshold.

        Generates a model-authored handoff packet, creates a fresh session, and
        keeps the active request alive inside the new context automatically.
        """
        session_manager = self.tool_executor.context.get('session_manager')
        
        if not session_manager:
            return
        
        latest_user_message = self._latest_user_message_text()
        workspace_memory = self._workspace_memory_for_rotation(latest_user_message)
        rotation_reason = (
            f"Token usage reached {current_tokens:,} / {max_tokens:,} "
            f"({current_tokens/max_tokens*100:.1f}%)"
        )

        self._auto_context_rotation_active = True
        try:
            try:
                handoff = build_session_handoff_packet(
                    messages=self._build_messages(),
                    client=self._client,
                    model=self.model,
                    provider=self.provider,
                    session_id=session_id,
                    current_tokens=current_tokens,
                    max_tokens=max_tokens,
                    base_url=self.base_url,
                    api_key=self.api_key,
                    custom_headers=self.custom_headers,
                    workspace_memory=workspace_memory,
                    latest_user_request=latest_user_message,
                    reason=rotation_reason,
                    workspace_stats_manager=self.tool_executor.context.get("workspace_stats_manager"),
                    model_display_name=self.model_display_name,
                )
            except Exception:
                logger.debug(
                    "Automatic handoff generation failed; skipping session rotation until retry window",
                    exc_info=True,
                )
                self._auto_context_rotation_retry_after = time.time() + 30.0
                return

            new_session = session_manager.rotate_session(
                working_memory=handoff.carryover_text,
                reason=rotation_reason,
                handoff_packet=handoff.to_dict(),
            )

            self.messages = list(new_session.messages)
            if latest_user_message:
                self.messages.append({"role": "user", "content": latest_user_message})

            self._persist_history_to_session()

            self._auto_context_rotation_retry_after = 0.0
        finally:
            self._auto_context_rotation_active = False
    
    def get_token_estimate(self) -> int:
        """Estimate tokens in current conversation"""
        cache_key = self._token_estimate_signature()
        cache_now = time.monotonic()
        if (
            self._token_estimate_cache_key == cache_key
            and (cache_now - self._token_estimate_cache_time) < 1.0
        ):
            return self._token_estimate_cache_value

        request_messages = self._build_messages()
        workspace_stats_manager = self.tool_executor.context.get("workspace_stats_manager")
        if workspace_stats_manager and hasattr(workspace_stats_manager, "count_messages_tokens"):
            try:
                estimate = max(int(workspace_stats_manager.count_messages_tokens(request_messages)), 0)
                self._token_estimate_cache_key = cache_key
                self._token_estimate_cache_value = estimate
                self._token_estimate_cache_time = cache_now
                return estimate
            except Exception:
                logger.debug("Workspace token counter failed; falling back to heuristic estimate", exc_info=True)

        total_chars = 0
        for msg in request_messages:
            content = _coerce_text_fragments(msg.get("content"))
            if content:
                total_chars += len(content)
            tool_calls = msg.get("tool_calls")
            if isinstance(tool_calls, list) and tool_calls:
                try:
                    total_chars += len(
                        json.dumps(
                            [
                                {
                                    key: value
                                    for key, value in tool_call.items()
                                    if key not in {"thought_signature", "gemini_thought_signature"}
                                }
                                for tool_call in tool_calls
                                if isinstance(tool_call, dict)
                            ],
                            ensure_ascii=False,
                            separators=(",", ":"),
                        )
                    )
                except Exception:
                    total_chars += len(str(tool_calls))
            tool_call_id = str(msg.get("tool_call_id", "") or "").strip()
            if tool_call_id:
                total_chars += len(tool_call_id)
            name = str(msg.get("name", "") or "").strip()
            if name:
                total_chars += len(name)

        estimate = total_chars // 4
        self._token_estimate_cache_key = cache_key
        self._token_estimate_cache_value = estimate
        self._token_estimate_cache_time = cache_now
        return estimate
        
        # Rough estimate: 1 token ≈ 4 characters
        return total_chars // 4
