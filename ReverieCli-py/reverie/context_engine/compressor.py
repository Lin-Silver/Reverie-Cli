from typing import List, Dict, Any, Optional
import json
import re
from pathlib import Path
from datetime import datetime
import requests
import logging

from ..nvidia import (
    apply_nvidia_request_defaults,
    build_nvidia_openai_options,
    is_nvidia_api_url,
    is_nvidia_model,
)
from ..sse import iter_sse_data_strings

logger = logging.getLogger(__name__)

REQUEST_RETRY_DELAYS_SECONDS = (1, 3, 5, 7, 15)
REQUEST_RETRY_ATTEMPTS = len(REQUEST_RETRY_DELAYS_SECONDS)


def _collect_codex_summary_text(response: requests.Response) -> str:
    """Collect assistant text from Codex SSE output."""
    from ..codex import parse_codex_sse_event

    parts = []
    parser_state = {}
    for data_str in _iter_sse_data_strings(response):
        events, parser_state = parse_codex_sse_event(data_str, parser_state)
        for event in events:
            if str(event.get("type", "")).strip().lower() == "content":
                parts.append(str(event.get("text", "") or ""))
    return "".join(parts).strip()


def _record_compression_usage(
    workspace_stats_manager: Any,
    *,
    provider: str,
    model: str,
    model_display_name: str,
    prompt_messages: List[Dict[str, Any]],
    summary_text: str,
    usage: Any,
    session_id: str,
) -> None:
    """Persist model usage for compression passes when workspace stats are available."""
    if not workspace_stats_manager:
        return
    try:
        workspace_stats_manager.record_model_usage(
            provider=str(provider or "unknown"),
            source="compression",
            model=str(model or ""),
            model_display_name=str(model_display_name or model or ""),
            request_messages=prompt_messages,
            assistant_text=str(summary_text or ""),
            usage=usage,
            session_id=str(session_id or "default"),
            session_name="",
            interaction_type="compression",
        )
    except Exception:
        logger.debug("Failed to record compression model usage", exc_info=True)


MEMORY_BLOCK_HEADER = "[MEMORY CONSOLIDATION - Context Engine Cache]"
MEMORY_BLOCK_END = "[END MEMORY]"
WORKING_MEMORY_HEADER = "[WORKING MEMORY - Previous Session Context]"
WORKING_MEMORY_END = "[END WORKING MEMORY]"
CONTEXT_ENGINE_NOTE_PREFIX = "[Context Engine"


def _message_text_from_value(value: Any) -> str:
    """Convert provider-specific message content shapes into plain text."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        parts: List[str] = []
        for item in value:
            if isinstance(item, str):
                text = item.strip()
            elif isinstance(item, dict):
                text = (
                    item.get("text")
                    or item.get("content")
                    or item.get("output_text")
                    or item.get("input_text")
                    or ""
                )
                text = str(text).strip()
            else:
                text = str(item).strip()
            if text:
                parts.append(text)
        return "\n".join(parts).strip()
    return str(value).strip()


def _get_message_text(message: Dict[str, Any]) -> str:
    """Extract displayable text from a message dict."""
    return _message_text_from_value(message.get("content"))


def _truncate_for_memory(text: Any, limit: int = 320) -> str:
    """Trim text for memory digests without losing the key facts."""
    compact = " ".join(str(text or "").split())
    if len(compact) <= limit:
        return compact
    return f"{compact[: limit - 3].rstrip()}..."


def _tool_call_names(message: Dict[str, Any]) -> List[str]:
    """Return normalized tool-call names from an assistant message."""
    names: List[str] = []
    tool_calls = message.get("tool_calls")
    if not isinstance(tool_calls, list):
        return names
    for tool_call in tool_calls:
        if not isinstance(tool_call, dict):
            continue
        function_obj = tool_call.get("function")
        if isinstance(function_obj, dict):
            name = str(function_obj.get("name", "")).strip()
        else:
            name = str(tool_call.get("name", "")).strip()
        if name and name not in names:
            names.append(name)
    return names


def _unwrap_memory_block(content: str) -> str:
    """Strip Reverie memory wrappers and return the inner summary."""
    text = str(content or "").strip()
    if text.startswith(MEMORY_BLOCK_HEADER):
        text = text[len(MEMORY_BLOCK_HEADER):].lstrip()
        if text.endswith(MEMORY_BLOCK_END):
            text = text[:-len(MEMORY_BLOCK_END)].rstrip()
    elif text.startswith(WORKING_MEMORY_HEADER):
        text = text[len(WORKING_MEMORY_HEADER):].lstrip()
        if text.endswith(WORKING_MEMORY_END):
            text = text[:-len(WORKING_MEMORY_END)].rstrip()
    return text.strip()


def _split_system_memory_messages(messages: List[Dict[str, Any]]) -> tuple[List[Dict[str, Any]], List[str]]:
    """Separate durable system prompts from Reverie-generated memory wrappers."""
    system_msgs: List[Dict[str, Any]] = []
    memory_blocks: List[str] = []

    for message in messages:
        if str(message.get("role", "")).strip().lower() != "system":
            continue
        content = _get_message_text(message)
        stripped = content.lstrip()
        if stripped.startswith(MEMORY_BLOCK_HEADER) or stripped.startswith(WORKING_MEMORY_HEADER):
            memory_text = _unwrap_memory_block(content)
            if memory_text:
                memory_blocks.append(memory_text)
            continue
        if stripped.startswith(CONTEXT_ENGINE_NOTE_PREFIX):
            continue
        system_msgs.append(message)

    return system_msgs, memory_blocks


def _select_recent_messages(messages: List[Dict[str, Any]], keep_last: int) -> List[Dict[str, Any]]:
    """Keep a recent window while preserving the start of the final interaction block."""
    if len(messages) <= keep_last:
        return list(messages)

    start = max(0, len(messages) - keep_last)
    while start > 0:
        role = str(messages[start].get("role", "")).strip().lower()
        previous_role = str(messages[start - 1].get("role", "")).strip().lower()
        if role == "tool":
            start -= 1
            continue
        if role == "assistant" and previous_role in ("user", "tool"):
            start -= 1
            continue
        break

    return list(messages[start:])


def _format_compression_message(message: Dict[str, Any]) -> str:
    """Render one bounded transcript entry for provider-side compression."""
    role = str(message.get("role", "unknown") or "unknown").strip().lower()
    content = _get_message_text(message)
    tool_names = _tool_call_names(message)
    if tool_names:
        tool_line = f"Tool calls: {', '.join(tool_names)}"
        content = f"{content}\n{tool_line}".strip() if content else tool_line
    if not content:
        return ""

    role_label = role.upper()
    if role == "tool":
        tool_name = str(
            message.get("name")
            or message.get("tool_name")
            or message.get("tool_call_id")
            or "tool"
        ).strip()
        role_label = f"TOOL[{tool_name}]"
    content_limit = 6000 if role == "tool" else 10000 if role == "user" else 14000
    if len(content) > content_limit:
        head_length = int(content_limit * 0.62)
        tail_length = content_limit - head_length - 40
        content = (
            content[:head_length].rstrip()
            + "\n...[middle truncated for compression]...\n"
            + content[-tail_length:].lstrip()
        )
    return f"{role_label}: {content}"


def _build_compression_transcript(
    messages: List[Dict[str, Any]],
    *,
    max_chars: int = 160000,
) -> str:
    """Build a bounded transcript that preserves both early decisions and the newest work."""
    parts = [part for part in (_format_compression_message(message) for message in messages) if part]
    if not parts:
        return ""
    joined = "\n\n".join(parts)
    max_chars = max(20000, int(max_chars or 160000))
    if len(joined) <= max_chars:
        return joined

    head_budget = max_chars // 5
    tail_budget = max_chars - head_budget - 120
    head: List[str] = []
    head_chars = 0
    split_index = 0
    for index, part in enumerate(parts):
        cost = len(part) + (2 if head else 0)
        if head and head_chars + cost > head_budget:
            break
        head.append(part)
        head_chars += cost
        split_index = index + 1

    tail: List[str] = []
    tail_chars = 0
    for index in range(len(parts) - 1, split_index - 1, -1):
        part = parts[index]
        cost = len(part) + (2 if tail else 0)
        if tail and tail_chars + cost > tail_budget:
            break
        tail.append(part)
        tail_chars += cost
    tail.reverse()

    omitted = max(0, len(parts) - len(head) - len(tail))
    marker = f"[... {omitted} older transcript entries omitted for faster compression ...]"
    return "\n\n".join(head + [marker] + tail)[:max_chars]


def build_memory_digest(messages: List[Dict[str, Any]]) -> str:
    """Build a compact, deterministic digest for session carry-over and anchors."""
    if not messages:
        return ""

    _, memory_blocks = _split_system_memory_messages(messages)
    non_system = [
        message
        for message in messages
        if str(message.get("role", "")).strip().lower() != "system"
    ]

    recent_user: List[str] = []
    recent_assistant: List[str] = []
    recent_tool_outputs: List[str] = []
    recent_tools: List[str] = []

    for message in reversed(non_system):
        role = str(message.get("role", "")).strip().lower()
        content = _truncate_for_memory(_get_message_text(message))
        if role == "user" and content and len(recent_user) < 4:
            recent_user.append(content)
        elif role == "assistant" and len(recent_assistant) < 3:
            assistant_text = content or ", ".join(_tool_call_names(message))
            assistant_text = _truncate_for_memory(assistant_text)
            if assistant_text:
                recent_assistant.append(assistant_text)
            for tool_name in _tool_call_names(message):
                if tool_name not in recent_tools:
                    recent_tools.append(tool_name)
        elif role == "tool" and content and len(recent_tool_outputs) < 3:
            tool_name = str(
                message.get("name")
                or message.get("tool_name")
                or message.get("tool_call_id")
                or "tool"
            ).strip()
            recent_tool_outputs.append(f"{tool_name}: {_truncate_for_memory(content, limit=240)}")

    sections: List[str] = []
    if memory_blocks:
        sections.append(
            "Prior consolidated memory\n"
            + "\n".join(f"- {_truncate_for_memory(block, limit=420)}" for block in memory_blocks[-2:])
        )
    if recent_user:
        sections.append(
            "Recent user requests\n"
            + "\n".join(f"- {item}" for item in reversed(recent_user))
        )
    if recent_assistant:
        sections.append(
            "Recent assistant state\n"
            + "\n".join(f"- {item}" for item in reversed(recent_assistant))
        )
    if recent_tools or recent_tool_outputs:
        tool_lines: List[str] = []
        if recent_tools:
            tool_lines.append(f"- Tools in play: {', '.join(reversed(recent_tools[:8]))}")
        tool_lines.extend(f"- {item}" for item in reversed(recent_tool_outputs))
        sections.append("Recent tool activity\n" + "\n".join(tool_lines))

    return "\n\n".join(section for section in sections if section.strip())


def _build_deterministic_compression_summary(
    history_to_compress: List[Dict[str, Any]],
    memory_blocks: List[str],
    *,
    max_chars: int = 8000,
) -> str:
    """Build a bounded local summary when provider compression is unavailable."""
    important_user: List[str] = []
    important_assistant: List[str] = []
    important_tools: List[str] = []
    file_mentions: List[str] = []
    commands: List[str] = []
    decisions: List[str] = []
    seen: set[str] = set()

    def add_unique(target: List[str], value: str, limit: int) -> None:
        compact = _truncate_for_memory(value, limit=limit)
        key = compact.lower()
        if not compact or key in seen:
            return
        seen.add(key)
        target.append(compact)

    path_pattern = re.compile(r"[\w./\\:-]+\.(?:py|ts|tsx|js|jsx|md|json|toml|yaml|yml|rs|go|java|cpp|h|css|html)")
    command_pattern = re.compile(r"`([^`\n]*(?:pytest|python|git|npm|pnpm|uv|pip|node)[^`\n]*)`")

    for message in history_to_compress:
        role = str(message.get("role", "") or "").strip().lower()
        content = _get_message_text(message)
        if not content:
            tool_names = _tool_call_names(message)
            if tool_names:
                add_unique(important_tools, "Tool calls: " + ", ".join(tool_names), 280)
            continue

        for match in path_pattern.findall(content):
            add_unique(file_mentions, match, 180)
        for match in command_pattern.findall(content):
            add_unique(commands, match, 220)

        lower = content.lower()
        if any(marker in lower for marker in ("decided", "fixed", "implemented", "changed", "must", "should", "bug", "error", "failed", "todo", "pending")):
            add_unique(decisions, content, 420)

        if role == "user":
            add_unique(important_user, content, 360)
        elif role == "assistant":
            tool_names = _tool_call_names(message)
            if tool_names:
                add_unique(important_tools, "Tool calls: " + ", ".join(tool_names), 240)
            add_unique(important_assistant, content, 360)
        elif role == "tool":
            tool_name = str(message.get("name") or message.get("tool_name") or message.get("tool_call_id") or "tool").strip()
            add_unique(important_tools, f"{tool_name}: {content}", 360)

    lines: List[str] = [
        "Current Goal",
        "- Continue the coding session using the preserved recent messages and this bounded fallback memory.",
    ]
    if memory_blocks:
        lines.extend(["", "Durable Prior Memory"])
        lines.extend(f"- {_truncate_for_memory(block, limit=520)}" for block in memory_blocks[-2:])
    if important_user:
        lines.extend(["", "Recent User Intent"])
        lines.extend(f"- {item}" for item in important_user[-6:])
    if decisions:
        lines.extend(["", "Durable Decisions and Open Issues"])
        lines.extend(f"- {item}" for item in decisions[-8:])
    if file_mentions:
        lines.extend(["", "Important Files"])
        lines.extend(f"- {item}" for item in file_mentions[-16:])
    if commands:
        lines.extend(["", "Important Commands"])
        lines.extend(f"- `{item}`" for item in commands[-8:])
    if important_tools:
        lines.extend(["", "Recent Tool Activity"])
        lines.extend(f"- {item}" for item in important_tools[-8:])
    if important_assistant:
        lines.extend(["", "Assistant State"])
        lines.extend(f"- {item}" for item in important_assistant[-5:])

    summary = "\n".join(lines).strip()
    if len(summary) > max_chars:
        summary = summary[: max_chars - 3].rstrip() + "..."
    return summary

def validate_payload_for_compression(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate and sanitize payload for context compression API calls.
    
    Args:
        payload: The payload dictionary to validate
        
    Returns:
        A sanitized payload dictionary
        
    Raises:
        ValueError: If the payload cannot be sanitized
    """
    try:
        # Test JSON serialization
        json_str = json.dumps(payload, ensure_ascii=False)
        # Verify it can be parsed back
        json.loads(json_str)
        return payload
    except (TypeError, ValueError) as e:
        logger.error(f"Payload validation failed in compressor: {e}")
        # Try to fix by truncating overly long messages
        if "messages" in payload:
            messages = payload["messages"]
            sanitized_messages = []
            for msg in messages:
                if isinstance(msg, dict) and "content" in msg:
                    content = msg["content"]
                    if isinstance(content, str) and len(content) > 100000:
                        # Truncate very long messages
                        logger.warning(f"Truncating message from {len(content)} to 100000 chars")
                        content = content[:100000] + "... [truncated]"
                    sanitized_messages.append({
                        "role": msg.get("role", "user"),
                        "content": content
                    })
                else:
                    sanitized_messages.append(msg)
            payload["messages"] = sanitized_messages
        
        # Try again
        try:
            json_str = json.dumps(payload, ensure_ascii=False)
            json.loads(json_str)
            return payload
        except (TypeError, ValueError) as e2:
            logger.error(f"Failed to sanitize payload: {e2}")
            raise ValueError(f"Cannot sanitize payload: {e2}")


# Helper to build OpenAI `extra_body` when a model requires 'thinking' mode
def _openai_extra_body_for_model(model: str) -> Optional[Dict[str, Any]]:
    """Return extra_body dict with chat_template_kwargs if model indicates thinking.

    Detects explicit 'thinking' suffixes (e.g. model(thinking), glm-*-thinking) or
    numeric thinking suffixes. For GLM-family models set clear_thinking=False.
    """
    if not model:
        return None
    mn = str(model).strip().lower()
    # Quick check for explicit 'thinking' token
    if "thinking" in mn:
        chat_kwargs = {"enable_thinking": True, "thinking": True}
        if "glm" in mn:
            chat_kwargs["clear_thinking"] = False
        return {"chat_template_kwargs": chat_kwargs}

    # Parenthesis suffix detection
    if "(" in mn and ")" in mn:
        suffix = mn.split("(", 1)[1].split(")", 1)[0].strip()
        thinking_suffixes = {"auto", "low", "medium", "high", "xhigh", "minimal"}
        if suffix in thinking_suffixes or suffix.isdigit():
            chat_kwargs = {"enable_thinking": True, "thinking": True}
            if "glm" in mn:
                chat_kwargs["clear_thinking"] = False
            return {"chat_template_kwargs": chat_kwargs}
    return None


def _merge_extra_body(
    base: Optional[Dict[str, Any]],
    extra: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Merge nested OpenAI-compatible extra_body blocks."""
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


def _resolve_nvidia_openai_call_options(
    model: str,
    extra_body: Optional[Dict[str, Any]] = None,
) -> tuple[str, Optional[Dict[str, Any]], Dict[str, Any]]:
    """Attach NVIDIA model-specific OpenAI SDK options when applicable."""
    model_for_sdk = model
    options: Dict[str, Any] = {}

    if is_nvidia_model(model):
        options = build_nvidia_openai_options({"selected_model_id": model}, model)
        option_model = str(options.get("model", "") or "").strip()
        if option_model:
            model_for_sdk = option_model
        extra_body = _merge_extra_body(extra_body, options.get("extra_body"))

    if extra_body is not None and isinstance(model_for_sdk, str) and "(" in model_for_sdk and ")" in model_for_sdk:
        model_for_sdk = model_for_sdk.split("(", 1)[0].strip()

    return model_for_sdk, extra_body, options


def _apply_nvidia_request_payload_defaults(
    base_url: str,
    payload: Dict[str, Any],
) -> Dict[str, Any]:
    """Apply NVIDIA request-model defaults for hosted integrate API calls."""
    prepared = dict(payload or {})
    model = str(prepared.get("model", "") or "").strip()
    if not model:
        return prepared
    if not (is_nvidia_api_url(base_url) or is_nvidia_model(model)):
        return prepared
    return apply_nvidia_request_defaults(prepared, {"selected_model_id": model})


def make_compression_request_with_retry(
    url: str,
    headers: Dict[str, str],
    payload: Dict[str, Any],
    max_retries: int = 2
) -> requests.Response:
    """
    Make a compression API request with fixed retry delays.
    
    Args:
        url: The API endpoint URL
        headers: Request headers
        payload: Request payload
        max_retries: Number of retries after the first request (default: 2).
        
    Returns:
        The response object
        
    Raises:
        requests.RequestException: If all retries fail
    """
    # Validate payload
    payload = validate_payload_for_compression(payload)
    
    last_error = None
    attempts = max(0, min(int(max_retries or 0), REQUEST_RETRY_ATTEMPTS))
    for attempt in range(attempts + 1):
        try:
            logger.debug(f"Compression request attempt {attempt + 1}/{attempts + 1}")
            
            response = requests.post(
                url,
                headers=headers,
                json=payload,
                timeout=120  # Longer timeout for compression
            )
            
            response.raise_for_status()
            return response
            
        except requests.exceptions.RequestException as e:
            last_error = e
            logger.debug(
                "Compression request attempt %s/%s failed",
                attempt + 1,
                attempts + 1,
                exc_info=True,
            )
            
            if attempt < attempts:
                import time
                time.sleep(REQUEST_RETRY_DELAYS_SECONDS[attempt])
    
    raise last_error or requests.RequestException("All compression retry attempts failed")

class ContextCompressor:
    """
    Handles prompt compression and memory checkpointing.
    Used when the active token context exceeds limits.
    
    Inspired by GPT-5.1 codex max, this implementation focuses on technical
    retainment and recursive summary retrieval.
    """
    
    def __init__(self, cache_dir: Path):
        self.cache_dir = cache_dir / 'checkpoints'
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.last_checkpoint = None

    def save_checkpoint(self, messages: List[Dict], note: str = "", session_id: str = "default") -> str:
        """Save current messages to a checkpoint file."""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        checkpoint_data = {
            'timestamp': datetime.now().isoformat(),
            'session_id': session_id,
            'note': note,
            'message_count': len(messages),
            'messages': messages
        }
        filename = f"checkpoint_{session_id}_{timestamp}.json"
        path = self.cache_dir / filename
        
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(checkpoint_data, f, ensure_ascii=False, separators=(',', ':'))
            self.last_checkpoint = str(path)
            return str(path)
        except Exception as e:
            return ""

    def compress(
        self,
        messages: List[Dict],
        client: Any,
        model: str,
        session_id: str = "default",
        provider: str = "openai-sdk",
        base_url: str = "",
        api_key: str = "",
        custom_headers: Optional[Dict[str, str]] = None,
        workspace_stats_manager: Any = None,
        model_display_name: str = "",
    ) -> List[Dict]:
        """
        Compresses the conversation history using the LLM.
        Retains system prompt and last few messages.
        Summarizes the rest using recursive technical retainment.
        
        Args:
            messages: List of messages to compress
            client: Client object (for openai-sdk and anthropic providers)
            model: Model name
            session_id: Session ID for checkpointing
            provider: Provider type (openai-sdk, request, anthropic, codex)
            base_url: Base URL for request provider
            api_key: API key for request provider
            custom_headers: Optional provider-specific extra headers
            workspace_stats_manager: Optional stats recorder for model usage
            model_display_name: Friendly model label for dashboards
        """
        if not messages:
            return []

        system_msgs, memory_blocks = _split_system_memory_messages(messages)
        other_msgs = [
            message
            for message in messages
            if str(message.get("role", "")).strip().lower() != "system"
        ]

        # If conversation is short and we do not need to collapse prior memory wrappers, leave it alone.
        if len(other_msgs) < 8 and not memory_blocks:
            return messages

        keep_last = 6 if len(other_msgs) < 18 else 8
        recent_msgs = _select_recent_messages(other_msgs, keep_last)
        history_to_compress = other_msgs[: max(0, len(other_msgs) - len(recent_msgs))]

        if not history_to_compress:
            compact_history = list(system_msgs)
            if memory_blocks:
                compact_history.append(
                    {
                        "role": "system",
                        "content": f"{MEMORY_BLOCK_HEADER}\n{memory_blocks[-1]}\n{MEMORY_BLOCK_END}",
                    }
                )
            compact_history.extend(recent_msgs)
            return compact_history or messages

        # Save checkpoint before compression (Safety)
        self.save_checkpoint(messages, "Pre-compression auto-save", session_id)

        conversation_text = _build_compression_transcript(history_to_compress)
        if not conversation_text:
            return messages

        prior_memory_text = "\n\n".join(memory_blocks[-2:]).strip()
        anchor_digest = build_memory_digest(other_msgs)
        fallback_summary: Optional[str] = None

        def get_fallback_summary() -> str:
            nonlocal fallback_summary
            if fallback_summary is None:
                fallback_summary = _build_deterministic_compression_summary(
                    history_to_compress,
                    memory_blocks,
                )
            return fallback_summary

        def compact_with_summary(summary_text: str, note: str) -> List[Dict]:
            summary_message = {
                "role": "system",
                "content": f"{MEMORY_BLOCK_HEADER}\n{summary_text}\n{MEMORY_BLOCK_END}",
            }
            new_history = system_msgs + [summary_message] + recent_msgs
            self.save_checkpoint(new_history, note, session_id)
            return new_history

        prompt = [
            {
                "role": "system", 
                "content": (
                    "You are Reverie's Context Engine Optimizer. Compress prior conversation into durable working memory for a long-running coding session. "
                    "Your job is not to summarize everything equally. Act like a selective memory curator: keep only information that will materially help the next model call. "
                    "Prioritize exact technical facts, confirmed user intent, design decisions, constraints, open bugs, pending implementation work, verification state, model/provider quirks, "
                    "important files, commands, paths, and artifact/document locations. Drop filler, social language, repeated reasoning, and transient thought process. "
                    "If older details are superseded, keep only the latest confirmed version. "
                    "Return a concise but high-fidelity summary with these sections: "
                    "Current Goal, Durable Decisions and Constraints, Implemented Work and Key Facts, Open Problems and Pending Work, Important Files Commands and Model Settings. "
                    "Use short bullets, do not invent facts, and preserve actionable specificity."
                )
            },
            {
                "role": "user",
                "content": (
                    "Consolidate the following context for long-term retrieval.\n\n"
                    f"Existing consolidated memory:\n{prior_memory_text or '(none)'}\n\n"
                    f"Memory anchors that must survive:\n{anchor_digest or '(none)'}\n\n"
                    f"Conversation to compress:\n{conversation_text}"
                ),
            },
        ]
        
        try:
            usage_info = None
            # Use the provided client to summarize based on provider
            if provider in {"openai-sdk", "openai-chat"}:
                # If model indicates thinking-capable mode, include chat_template_kwargs
                extra_body = _openai_extra_body_for_model(model)
                model_for_sdk, extra_body, nvidia_options = _resolve_nvidia_openai_call_options(
                    model,
                    extra_body=extra_body,
                )
                kwargs: Dict[str, Any] = {
                    "model": model_for_sdk,
                    "messages": prompt,
                    "stream": False,
                }
                for key in ("temperature", "top_p", "max_tokens"):
                    if nvidia_options.get(key) is not None:
                        kwargs[key] = nvidia_options[key]
                if extra_body is not None:
                    kwargs["extra_body"] = extra_body
                response = client.chat.completions.create(**kwargs)
                summary = response.choices[0].message.content
                usage_info = getattr(response, "usage", None)
            elif provider == "openai-responses":
                from ..codex import build_codex_request_payload

                converted = build_codex_request_payload(model, prompt, tools=None, stream=False)
                response = client.responses.create(
                    model=model,
                    input=converted["input"],
                    stream=False,
                )
                summary = str(getattr(response, "output_text", "") or "")
                usage_info = getattr(response, "usage", None)
            elif provider == "request":
                # Use requests library for request provider
                payload = {
                    "model": model,
                    "messages": prompt,
                    "stream": False
                }
                payload = _apply_nvidia_request_payload_defaults(base_url, payload)
                headers = {
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                }
                for key, value in (custom_headers or {}).items():
                    normalized_key = str(key or "").strip()
                    normalized_value = str(value or "").strip()
                    if normalized_key and normalized_value:
                        headers[normalized_key] = normalized_value
                response = make_compression_request_with_retry(base_url, headers, payload)
                response_data = response.json()
                summary = response_data["choices"][0]["message"]["content"]
                usage_info = response_data.get("usage") if isinstance(response_data, dict) else None
            elif provider == "anthropic":
                # Use Anthropic SDK
                # Convert messages to Anthropic format
                anthropic_messages = []
                system_message = None
                
                for msg in prompt:
                    if msg["role"] == "system":
                        system_message = msg["content"]
                    else:
                        anthropic_messages.append({
                            "role": msg["role"],
                            "content": msg["content"]
                        })
                
                kwargs = {
                    "model": model,
                    "messages": anthropic_messages,
                    "max_tokens": 4096,
                }
                
                if system_message:
                    kwargs["system"] = system_message
                
                response = client.messages.create(**kwargs)
                summary = response.content[0].text
                usage_info = getattr(response, "usage", None)
            elif provider == "codex":
                from ..codex import (
                    build_codex_request_payload,
                    detect_codex_cli_credentials,
                    get_codex_request_headers,
                    resolve_codex_request_url,
                )

                cred = detect_codex_cli_credentials()
                access_token = str(api_key or cred.get("api_key", "") or "").strip()
                if not access_token:
                    return compact_with_summary(get_fallback_summary(), "Post-compression deterministic fallback")
                request_url = resolve_codex_request_url(base_url, "")

                payload = build_codex_request_payload(
                    model_name=model,
                    messages=prompt,
                    tools=None,
                    stream=True,
                )
                headers = get_codex_request_headers(
                    api_key=access_token,
                    account_id=str(cred.get("account_id", "")).strip(),
                    auth_mode=str(cred.get("auth_mode", "")).strip(),
                    extra_headers=custom_headers,
                    stream=True,
                    request_url=request_url,
                )
                response = requests.post(
                    request_url,
                    headers=headers,
                    json=payload,
                    stream=True,
                    timeout=120,
                )
                response.raise_for_status()
                summary = _collect_codex_summary_text(response)
            else:
                raise ValueError(f"Unknown provider: {provider}")

            if not str(summary or "").strip():
                return compact_with_summary(get_fallback_summary(), "Post-compression deterministic fallback")

            _record_compression_usage(
                workspace_stats_manager,
                provider=provider,
                model=model,
                model_display_name=model_display_name,
                prompt_messages=prompt,
                summary_text=str(summary or ""),
                usage=usage_info,
                session_id=session_id,
            )
            
            return compact_with_summary(str(summary or "").strip(), "Post-compression optimized summary")
            
        except Exception as e:
            logger.warning("Provider compression failed; using deterministic local fallback: %s", e)
            return compact_with_summary(get_fallback_summary(), "Post-compression deterministic fallback")

    def list_checkpoints(self, session_id: Optional[str] = None) -> List[Dict]:
        """List all available checkpoints for a session."""
        checkpoints = []
        for p in self.cache_dir.glob("checkpoint_*.json"):
            try:
                with open(p, 'r', encoding='utf-8') as f:
                    # Just read metadata, not the whole message history
                    data = json.load(f)
                    if session_id and data.get('session_id') != session_id:
                        continue
                    checkpoints.append({
                        'path': str(p),
                        'filename': p.name,
                        'timestamp': data.get('timestamp'),
                        'note': data.get('note'),
                        'message_count': data.get('message_count')
                    })
            except Exception:
                continue
        
        return sorted(checkpoints, key=lambda x: x['timestamp'], reverse=True)


def summarize_game_context(
    gdd_path: Optional[str] = None,
    asset_manifest_path: Optional[str] = None,
    task_list_path: Optional[str] = None,
    keep_last_messages: int = 5
) -> Dict[str, Any]:
    """
    Compress game development context for efficient memory usage.
    
    This function creates a compressed summary of game development artifacts:
    - GDD (Game Design Document): Keeps core sections
    - Asset Manifest: Summarizes by type and count
    - Task List: Summarizes by phase and status
    - Recent Messages: Keeps the last N messages
    
    Args:
        gdd_path: Path to the GDD file (Markdown)
        asset_manifest_path: Path to the asset manifest (JSON)
        task_list_path: Path to the task list (JSON)
        keep_last_messages: Number of recent messages to keep
    
    Returns:
        Dictionary containing compressed context
    """
    compressed = {
        'gdd_summary': None,
        'asset_summary': None,
        'task_summary': None,
        'compression_timestamp': datetime.now().isoformat()
    }
    
    # Compress GDD
    if gdd_path and Path(gdd_path).exists():
        try:
            with open(gdd_path, 'r', encoding='utf-8') as f:
                gdd_content = f.read()
            
            # Extract core sections (概述, 核心机制, 角色系统, 剧情系统, 任务系统)
            core_sections = []
            current_section = None
            current_content = []
            
            for line in gdd_content.split('\n'):
                # Check for section headers
                if line.startswith('## '):
                    # Save previous section if it's a core section
                    if current_section and any(keyword in current_section for keyword in 
                                              ['概述', '核心机制', '角色', '剧情', '任务', 'Overview', 'Core', 'Character', 'Story', 'Quest']):
                        core_sections.append({
                            'title': current_section,
                            'content': '\n'.join(current_content[:20])  # Keep first 20 lines
                        })
                    
                    current_section = line[3:].strip()
                    current_content = []
                elif current_section:
                    current_content.append(line)
            
            # Save last section if core
            if current_section and any(keyword in current_section for keyword in 
                                      ['概述', '核心机制', '角色', '剧情', '任务', 'Overview', 'Core', 'Character', 'Story', 'Quest']):
                core_sections.append({
                    'title': current_section,
                    'content': '\n'.join(current_content[:20])
                })
            
            compressed['gdd_summary'] = {
                'core_sections': core_sections,
                'total_sections': gdd_content.count('## ')
            }
        
        except Exception as e:
            logger.error(f"Failed to compress GDD: {e}")
            compressed['gdd_summary'] = {'error': str(e)}
    
    # Compress Asset Manifest
    if asset_manifest_path and Path(asset_manifest_path).exists():
        try:
            with open(asset_manifest_path, 'r', encoding='utf-8') as f:
                manifest = json.load(f)
            
            # Summarize by type
            asset_summary = {}
            
            if 'assets' in manifest:
                for asset_type, assets in manifest['assets'].items():
                    if isinstance(assets, list):
                        total_size = sum(a.get('size', 0) for a in assets if isinstance(a, dict))
                        asset_summary[asset_type] = {
                            'count': len(assets),
                            'total_size_mb': total_size / (1024 * 1024) if total_size > 0 else 0,
                            'examples': [a.get('path', '') for a in assets[:3] if isinstance(a, dict)]
                        }
            
            # Include statistics if available
            if 'statistics' in manifest:
                asset_summary['statistics'] = manifest['statistics']
            
            compressed['asset_summary'] = asset_summary
        
        except Exception as e:
            logger.error(f"Failed to compress asset manifest: {e}")
            compressed['asset_summary'] = {'error': str(e)}
    
    # Compress Task List
    if task_list_path and Path(task_list_path).exists():
        try:
            with open(task_list_path, 'r', encoding='utf-8') as f:
                tasks = json.load(f)
            
            # Summarize by phase and status
            task_summary = {
                'by_phase': {},
                'by_status': {},
                'total_tasks': 0
            }
            
            if isinstance(tasks, list):
                task_summary['total_tasks'] = len(tasks)
                
                for task in tasks:
                    if not isinstance(task, dict):
                        continue
                    
                    # Count by phase
                    phase = task.get('phase', 'unknown')
                    if phase not in task_summary['by_phase']:
                        task_summary['by_phase'][phase] = 0
                    task_summary['by_phase'][phase] += 1
                    
                    # Count by status
                    status = task.get('state', task.get('status', 'unknown'))
                    if status not in task_summary['by_status']:
                        task_summary['by_status'][status] = 0
                    task_summary['by_status'][status] += 1
                
                # Include high-priority tasks
                high_priority = [
                    {
                        'name': t.get('name', ''),
                        'phase': t.get('phase', ''),
                        'status': t.get('state', t.get('status', ''))
                    }
                    for t in tasks
                    if isinstance(t, dict) and t.get('priority') in ['high', 'critical']
                ]
                
                if high_priority:
                    task_summary['high_priority_tasks'] = high_priority[:5]  # Keep top 5
            
            elif isinstance(tasks, dict) and 'tasks' in tasks:
                # Handle nested structure
                task_list = tasks['tasks']
                task_summary['total_tasks'] = len(task_list)
                
                for task in task_list:
                    if not isinstance(task, dict):
                        continue
                    
                    phase = task.get('phase', 'unknown')
                    if phase not in task_summary['by_phase']:
                        task_summary['by_phase'][phase] = 0
                    task_summary['by_phase'][phase] += 1
                    
                    status = task.get('state', task.get('status', 'unknown'))
                    if status not in task_summary['by_status']:
                        task_summary['by_status'][status] = 0
                    task_summary['by_status'][status] += 1
            
            compressed['task_summary'] = task_summary
        
        except Exception as e:
            logger.error(f"Failed to compress task list: {e}")
            compressed['task_summary'] = {'error': str(e)}
    
    return compressed


def format_game_context_summary(summary: Dict[str, Any]) -> str:
    """
    Format a game context summary into a readable string.
    
    Args:
        summary: Dictionary from summarize_game_context
    
    Returns:
        Formatted string representation
    """
    lines = ["=== Game Development Context Summary ===\n"]
    
    # GDD Summary
    if summary.get('gdd_summary'):
        lines.append("📄 Game Design Document:")
        gdd = summary['gdd_summary']
        
        if 'error' in gdd:
            lines.append(f"  Error: {gdd['error']}")
        else:
            lines.append(f"  Total Sections: {gdd.get('total_sections', 0)}")
            lines.append("  Core Sections:")
            for section in gdd.get('core_sections', []):
                lines.append(f"    - {section['title']}")
                # Add first few lines of content
                content_preview = section['content'].split('\n')[:3]
                for line in content_preview:
                    if line.strip():
                        lines.append(f"      {line.strip()[:80]}")
        lines.append("")
    
    # Asset Summary
    if summary.get('asset_summary'):
        lines.append("🎨 Game Assets:")
        assets = summary['asset_summary']
        
        if 'error' in assets:
            lines.append(f"  Error: {assets['error']}")
        else:
            total_count = 0
            total_size = 0.0
            
            for asset_type, info in assets.items():
                if asset_type == 'statistics':
                    continue
                if isinstance(info, dict):
                    count = info.get('count', 0)
                    size = info.get('total_size_mb', 0)
                    total_count += count
                    total_size += size
                    lines.append(f"  {asset_type}: {count} files ({size:.2f} MB)")
                    
                    examples = info.get('examples', [])
                    if examples:
                        lines.append(f"    Examples: {', '.join(examples[:2])}")
            
            lines.append(f"  Total: {total_count} assets ({total_size:.2f} MB)")
        lines.append("")
    
    # Task Summary
    if summary.get('task_summary'):
        lines.append("📋 Tasks:")
        tasks = summary['task_summary']
        
        if 'error' in tasks:
            lines.append(f"  Error: {tasks['error']}")
        else:
            lines.append(f"  Total Tasks: {tasks.get('total_tasks', 0)}")
            
            if tasks.get('by_phase'):
                lines.append("  By Phase:")
                for phase, count in tasks['by_phase'].items():
                    lines.append(f"    {phase}: {count}")
            
            if tasks.get('by_status'):
                lines.append("  By Status:")
                for status, count in tasks['by_status'].items():
                    lines.append(f"    {status}: {count}")
            
            if tasks.get('high_priority_tasks'):
                lines.append("  High Priority:")
                for task in tasks['high_priority_tasks']:
                    lines.append(f"    - {task['name']} ({task['phase']}, {task['status']})")
        lines.append("")
    
    lines.append(f"Compressed at: {summary.get('compression_timestamp', 'unknown')}")
    
    return '\n'.join(lines)
