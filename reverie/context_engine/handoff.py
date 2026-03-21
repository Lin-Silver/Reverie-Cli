from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import json
import logging
import re
from typing import Any, Dict, List, Optional

import requests

from .compressor import (
    _collect_codex_summary_text,
    _collect_geminicli_summary_text,
    _get_message_text,
    _message_text_from_value,
    _openai_extra_body_for_model,
    _select_recent_messages,
    _split_system_memory_messages,
    _tool_call_names,
    _truncate_for_memory,
    build_memory_digest,
    make_compression_request_with_retry,
)


logger = logging.getLogger(__name__)


SESSION_HANDOFF_SCHEMA_VERSION = 1
DEFAULT_RECENT_MESSAGE_LIMIT = 14

SESSION_HANDOFF_SYSTEM_PROMPT = """You are Reverie's automatic session-handoff generator.

Your job is to prepare the next model session so it can continue the SAME task without asking the user to restate context.

Rules:
- Return exactly one JSON object and nothing else.
- Preserve only durable, implementation-relevant memory.
- Prefer verified facts over guesses.
- Focus on the current project goal, the user's latest active request, completed work, unresolved blockers, important files, constraints, and the exact next action.
- If the conversation contains partial implementation or unfinished verification, preserve that state explicitly.
- Do not write a status report for the end user.
- Do not say "continue" or "ask the user" unless a real blocker exists.
- If information is unknown, use an empty string or empty array instead of inventing.

Use this schema exactly:
{
  "project_goal": "string",
  "latest_user_request": "string",
  "current_state": ["string"],
  "completed_work": ["string"],
  "open_problems": ["string"],
  "critical_constraints": ["string"],
  "important_files": [{"path": "string", "reason": "string"}],
  "verification_state": ["string"],
  "next_actions": ["string"],
  "resume_instructions": ["string"]
}
"""


@dataclass
class SessionHandoffPacket:
    schema_version: int
    created_at: str
    model: str
    provider: str
    session_id: str
    token_estimate: int
    max_tokens: int
    usage_ratio: float
    latest_user_request: str
    raw_response_text: str
    data: Dict[str, Any]
    carryover_text: str
    context_digest: str = ""
    workspace_memory: str = ""
    recent_transcript: str = ""
    prior_memory: str = ""
    tool_activity: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "created_at": self.created_at,
            "model": self.model,
            "provider": self.provider,
            "session_id": self.session_id,
            "token_estimate": self.token_estimate,
            "max_tokens": self.max_tokens,
            "usage_ratio": self.usage_ratio,
            "latest_user_request": self.latest_user_request,
            "raw_response_text": self.raw_response_text,
            "data": self.data,
            "carryover_text": self.carryover_text,
            "context_digest": self.context_digest,
            "workspace_memory": self.workspace_memory,
            "recent_transcript": self.recent_transcript,
            "prior_memory": self.prior_memory,
            "tool_activity": list(self.tool_activity),
        }


def _collect_recent_transcript(messages: List[Dict[str, Any]], keep_last: int) -> tuple[str, List[str]]:
    transcript_lines: List[str] = []
    tool_activity: List[str] = []

    for message in _select_recent_messages(messages, keep_last):
        role = str(message.get("role", "") or "").strip().lower() or "unknown"
        content = _message_text_from_value(message.get("content"))
        tool_names = _tool_call_names(message)

        if role == "tool":
            tool_name = str(
                message.get("name")
                or message.get("tool_name")
                or message.get("tool_call_id")
                or "tool"
            ).strip()
            text = _truncate_for_memory(content, limit=700)
            if text:
                transcript_lines.append(f"TOOL[{tool_name}]: {text}")
            if tool_name and tool_name not in tool_activity:
                tool_activity.append(tool_name)
            continue

        if tool_names:
            for tool_name in tool_names:
                if tool_name not in tool_activity:
                    tool_activity.append(tool_name)

        text = _truncate_for_memory(content, limit=900)
        if not text and tool_names:
            text = f"Tool calls: {', '.join(tool_names)}"
        if text:
            transcript_lines.append(f"{role.upper()}: {text}")

    return "\n\n".join(transcript_lines).strip(), tool_activity


def _latest_user_request(messages: List[Dict[str, Any]], fallback: str = "") -> str:
    for message in reversed(messages):
        if str(message.get("role", "") or "").strip().lower() != "user":
            continue
        text = _get_message_text(message)
        if text:
            return text
    return str(fallback or "").strip()


def _extract_json_object(text: str) -> Dict[str, Any]:
    cleaned = str(text or "").strip()
    if not cleaned:
        return {}

    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", cleaned, flags=re.DOTALL)
    if fenced:
        cleaned = fenced.group(1).strip()

    try:
        parsed = json.loads(cleaned)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        pass

    decoder = json.JSONDecoder()
    for match in re.finditer(r"\{", cleaned):
        try:
            parsed, _ = decoder.raw_decode(cleaned[match.start():])
        except Exception:
            continue
        if isinstance(parsed, dict):
            return parsed
    return {}


def _normalize_string_list(value: Any, limit: int = 8) -> List[str]:
    items: List[str] = []
    if isinstance(value, list):
        for item in value:
            text = " ".join(str(item or "").split()).strip()
            if text:
                items.append(text)
            if len(items) >= limit:
                break
    elif value:
        text = " ".join(str(value).split()).strip()
        if text:
            items.append(text)
    return items


def _normalize_important_files(value: Any, limit: int = 10) -> List[Dict[str, str]]:
    files: List[Dict[str, str]] = []
    if not isinstance(value, list):
        return files

    for item in value:
        if not isinstance(item, dict):
            continue
        path = " ".join(str(item.get("path", "") or "").split()).strip()
        reason = " ".join(str(item.get("reason", "") or "").split()).strip()
        if not path and not reason:
            continue
        files.append({"path": path, "reason": reason})
        if len(files) >= limit:
            break
    return files


def _normalize_handoff_payload(payload: Dict[str, Any], latest_user_request: str) -> Dict[str, Any]:
    return {
        "project_goal": " ".join(str(payload.get("project_goal", "") or "").split()).strip(),
        "latest_user_request": " ".join(
            str(payload.get("latest_user_request", "") or latest_user_request or "").split()
        ).strip(),
        "current_state": _normalize_string_list(payload.get("current_state"), limit=8),
        "completed_work": _normalize_string_list(payload.get("completed_work"), limit=10),
        "open_problems": _normalize_string_list(payload.get("open_problems"), limit=10),
        "critical_constraints": _normalize_string_list(payload.get("critical_constraints"), limit=10),
        "important_files": _normalize_important_files(payload.get("important_files"), limit=10),
        "verification_state": _normalize_string_list(payload.get("verification_state"), limit=8),
        "next_actions": _normalize_string_list(payload.get("next_actions"), limit=8),
        "resume_instructions": _normalize_string_list(payload.get("resume_instructions"), limit=8),
    }


def _render_carryover_text(payload: Dict[str, Any], *, reason: str) -> str:
    lines: List[str] = [
        "Auto Session Handoff",
        f"- Rotation reason: {reason}",
    ]

    project_goal = payload.get("project_goal", "")
    latest_user_request = payload.get("latest_user_request", "")
    if project_goal:
        lines.append(f"- Project goal: {project_goal}")
    if latest_user_request:
        lines.append(f"- Latest user request: {latest_user_request}")

    section_map = [
        ("Current state", payload.get("current_state", [])),
        ("Completed work", payload.get("completed_work", [])),
        ("Open problems", payload.get("open_problems", [])),
        ("Critical constraints", payload.get("critical_constraints", [])),
        ("Verification state", payload.get("verification_state", [])),
        ("Next actions", payload.get("next_actions", [])),
        ("Resume instructions", payload.get("resume_instructions", [])),
    ]

    for title, items in section_map:
        if not items:
            continue
        lines.append("")
        lines.append(f"{title}:")
        for item in items:
            lines.append(f"- {item}")

    important_files = payload.get("important_files", [])
    if important_files:
        lines.append("")
        lines.append("Important files:")
        for item in important_files:
            path = str(item.get("path", "") or "").strip()
            reason_text = str(item.get("reason", "") or "").strip()
            if path and reason_text:
                lines.append(f"- {path}: {reason_text}")
            elif path:
                lines.append(f"- {path}")

    lines.append("")
    lines.append("Resume behavior:")
    lines.append("- Continue the active implementation or investigation immediately.")
    lines.append("- Do not reply with a status recap unless the user explicitly asked for one.")

    return "\n".join(lines).strip()


def _request_handoff_summary_text(
    *,
    client: Any,
    model: str,
    provider: str,
    base_url: str,
    api_key: str,
    session_id: str,
    custom_headers: Optional[Dict[str, str]],
    prompt_messages: List[Dict[str, str]],
) -> str:
    if provider == "openai-sdk":
        extra_body = _openai_extra_body_for_model(model)
        model_for_sdk = model
        if extra_body is not None and isinstance(model_for_sdk, str) and "(" in model_for_sdk and ")" in model_for_sdk:
            model_for_sdk = model_for_sdk.split("(", 1)[0].strip()
        if extra_body is not None:
            response = client.chat.completions.create(
                model=model_for_sdk,
                messages=prompt_messages,
                stream=False,
                extra_body=extra_body,
            )
        else:
            response = client.chat.completions.create(
                model=model_for_sdk,
                messages=prompt_messages,
                stream=False,
            )
        return str(response.choices[0].message.content or "").strip()

    if provider == "request":
        payload = {
            "model": model,
            "messages": prompt_messages,
            "stream": False,
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        for key, value in (custom_headers or {}).items():
            normalized_key = str(key or "").strip()
            normalized_value = str(value or "").strip()
            if normalized_key and normalized_value:
                headers[normalized_key] = normalized_value
        response = make_compression_request_with_retry(base_url, headers, payload)
        response_data = response.json()
        return str(
            (((response_data.get("choices") or [{}])[0]).get("message") or {}).get("content")
            or ""
        ).strip()

    if provider == "anthropic":
        anthropic_messages: List[Dict[str, Any]] = []
        system_message = None
        for message in prompt_messages:
            if message.get("role") == "system":
                system_message = message.get("content")
            else:
                anthropic_messages.append(
                    {"role": message.get("role", "user"), "content": message.get("content", "")}
                )

        kwargs: Dict[str, Any] = {
            "model": model,
            "messages": anthropic_messages,
            "max_tokens": 4096,
        }
        if system_message:
            kwargs["system"] = system_message
        response = client.messages.create(**kwargs)
        if not response.content:
            return ""
        return str(getattr(response.content[0], "text", "") or "").strip()

    if provider == "gemini-cli":
        from ..geminicli import (
            build_geminicli_request_payload,
            detect_geminicli_cli_credentials,
            get_geminicli_request_headers,
            resolve_geminicli_project_id,
            resolve_geminicli_request_url,
        )

        cred = detect_geminicli_cli_credentials(refresh_if_needed=True)
        access_token = str(cred.get("api_key", "") or api_key or "").strip()
        if not access_token:
            return ""

        project_id = resolve_geminicli_project_id(
            base_url=base_url,
            access_token=access_token,
            timeout=120,
        )
        payload = build_geminicli_request_payload(
            model_name=model,
            messages=prompt_messages,
            tools=None,
            project_id=project_id,
            session_id=session_id,
        )
        headers = get_geminicli_request_headers(
            model_id=model,
            access_token=access_token,
            stream=True,
        )
        for key, value in (custom_headers or {}).items():
            normalized_key = str(key or "").strip()
            normalized_value = str(value or "").strip()
            if normalized_key and normalized_value:
                headers[normalized_key] = normalized_value
        response = requests.post(
            resolve_geminicli_request_url(base_url, "", stream=True),
            headers=headers,
            json=payload,
            stream=True,
            timeout=120,
        )
        response.raise_for_status()
        try:
            return _collect_geminicli_summary_text(response)
        finally:
            response.close()

    if provider == "codex":
        from ..codex import (
            build_codex_request_payload,
            detect_codex_cli_credentials,
            get_codex_request_headers,
            resolve_codex_request_url,
        )

        cred = detect_codex_cli_credentials()
        access_token = str(cred.get("api_key", "") or api_key or "").strip()
        if not access_token:
            return ""

        payload = build_codex_request_payload(
            model_name=model,
            messages=prompt_messages,
            tools=None,
            stream=True,
        )
        headers = get_codex_request_headers(
            api_key=access_token,
            account_id=str(cred.get("account_id", "")).strip(),
            auth_mode=str(cred.get("auth_mode", "")).strip(),
            stream=True,
        )
        for key, value in (custom_headers or {}).items():
            normalized_key = str(key or "").strip()
            normalized_value = str(value or "").strip()
            if normalized_key and normalized_value:
                headers[normalized_key] = normalized_value
        response = requests.post(
            resolve_codex_request_url(base_url, ""),
            headers=headers,
            json=payload,
            stream=True,
            timeout=120,
        )
        response.raise_for_status()
        try:
            return _collect_codex_summary_text(response)
        finally:
            response.close()

    raise ValueError(f"Unknown provider: {provider}")


def build_session_handoff_packet(
    *,
    messages: List[Dict[str, Any]],
    client: Any,
    model: str,
    provider: str,
    session_id: str,
    current_tokens: int,
    max_tokens: int,
    base_url: str = "",
    api_key: str = "",
    custom_headers: Optional[Dict[str, str]] = None,
    workspace_memory: str = "",
    latest_user_request: str = "",
    recent_message_limit: int = DEFAULT_RECENT_MESSAGE_LIMIT,
    reason: str = "",
) -> SessionHandoffPacket:
    _, prior_memory_blocks = _split_system_memory_messages(messages)
    non_system_messages = [
        message
        for message in messages
        if str(message.get("role", "") or "").strip().lower() != "system"
    ]

    latest_user_request = _latest_user_request(non_system_messages, latest_user_request)
    context_digest = build_memory_digest(non_system_messages)
    recent_transcript, tool_activity = _collect_recent_transcript(
        non_system_messages,
        keep_last=max(6, recent_message_limit),
    )
    prior_memory = "\n\n".join(prior_memory_blocks[-2:]).strip()

    prompt_messages = [
        {"role": "system", "content": SESSION_HANDOFF_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"Rotation reason: {reason or 'context window threshold reached'}\n\n"
                f"Current token usage: {current_tokens} / {max_tokens}\n\n"
                f"Latest active user request:\n{latest_user_request or '(none)'}\n\n"
                f"Workspace memory:\n{workspace_memory or '(none)'}\n\n"
                f"Prior consolidated memory:\n{prior_memory or '(none)'}\n\n"
                f"Whole-session digest:\n{context_digest or '(none)'}\n\n"
                f"Recent transcript window:\n{recent_transcript or '(none)'}\n\n"
                f"Active tools seen recently: {', '.join(tool_activity) if tool_activity else '(none)'}"
            ),
        },
    ]

    raw_response_text = _request_handoff_summary_text(
        client=client,
        model=model,
        provider=provider,
        base_url=base_url,
        api_key=api_key,
        session_id=session_id,
        custom_headers=custom_headers,
        prompt_messages=prompt_messages,
    )

    parsed_payload = _extract_json_object(raw_response_text)
    normalized_payload = _normalize_handoff_payload(parsed_payload, latest_user_request)

    if not any(normalized_payload.values()):
        normalized_payload = {
            "project_goal": "",
            "latest_user_request": latest_user_request,
            "current_state": _normalize_string_list(context_digest, limit=6),
            "completed_work": [],
            "open_problems": [],
            "critical_constraints": [],
            "important_files": [],
            "verification_state": [],
            "next_actions": [],
            "resume_instructions": [
                "Continue the active task without asking the user to restate context.",
            ],
        }

    carryover_text = _render_carryover_text(normalized_payload, reason=reason or "context window threshold reached")

    return SessionHandoffPacket(
        schema_version=SESSION_HANDOFF_SCHEMA_VERSION,
        created_at=datetime.now().isoformat(),
        model=str(model or ""),
        provider=str(provider or ""),
        session_id=str(session_id or ""),
        token_estimate=int(current_tokens),
        max_tokens=int(max_tokens),
        usage_ratio=(float(current_tokens) / float(max_tokens)) if max_tokens else 0.0,
        latest_user_request=latest_user_request,
        raw_response_text=str(raw_response_text or ""),
        data=normalized_payload,
        carryover_text=carryover_text,
        context_digest=context_digest,
        workspace_memory=str(workspace_memory or ""),
        recent_transcript=recent_transcript,
        prior_memory=prior_memory,
        tool_activity=tool_activity,
    )
