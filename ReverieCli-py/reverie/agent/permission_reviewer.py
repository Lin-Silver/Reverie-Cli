"""Transport for the Auto Check reviewer call.

Resolves which model performs the review (follow the main model, or a model the
user pinned) and issues one stateless, history-free request per batch.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
import copy
import logging
import time

import requests

from ..request_identity import apply_reverie_client_identity
from ..security_policy import normalize_review_config
from .permission_review import (
    REVIEW_SYSTEM_PROMPT,
    ReviewOutcome,
    build_review_payload,
    fallback_outcome,
    parse_review_response,
)

logger = logging.getLogger(__name__)

_SDK_PROVIDERS = {"openai-sdk", "openai-chat"}
_HTTP_PROVIDERS = {"request", "curl"}
SUPPORTED_REVIEW_PROVIDERS = _SDK_PROVIDERS | _HTTP_PROVIDERS | {"openai-responses", "anthropic"}


class ReviewTarget:
    """The model settings one review call should use."""

    def __init__(
        self,
        *,
        model: str = "",
        model_display_name: str = "",
        provider: str = "",
        base_url: str = "",
        api_key: str = "",
        custom_headers: Optional[Dict[str, str]] = None,
        client: Any = None,
    ) -> None:
        self.model = str(model or "")
        self.model_display_name = str(model_display_name or model or "")
        self.provider = str(provider or "")
        self.base_url = str(base_url or "")
        self.api_key = str(api_key or "")
        self.custom_headers = dict(custom_headers or {})
        self.client = client

    @property
    def usable(self) -> bool:
        return bool(self.model and self.provider in SUPPORTED_REVIEW_PROVIDERS)

    def describe(self) -> str:
        return f"{self.model_display_name or self.model} ({self.provider})"


def target_from_agent(agent: Any) -> ReviewTarget:
    """Reviewer target that follows whatever model the agent is running."""
    return ReviewTarget(
        model=getattr(agent, "model", ""),
        model_display_name=getattr(agent, "model_display_name", "") or getattr(agent, "model", ""),
        provider=getattr(agent, "provider", ""),
        base_url=getattr(agent, "base_url", ""),
        api_key=getattr(agent, "api_key", ""),
        custom_headers=getattr(agent, "custom_headers", None),
        client=getattr(agent, "_client", None),
    )


def target_from_config(config: Any, review: Dict[str, Any]) -> Optional[ReviewTarget]:
    """Reviewer target for a user-pinned model, resolved through Config dispatch."""
    if config is None:
        return None
    source = str(review.get("source") or "").strip().lower() or str(
        getattr(config, "active_model_source", "standard") or "standard"
    ).lower()
    wanted_model = str(review.get("model") or "").strip()
    index = int(review.get("model_index") or 0)

    try:
        probe = copy.copy(config)
        probe.active_model_source = source
        if source == "standard":
            models = list(getattr(config, "models", []) or [])
            if wanted_model:
                for position, candidate in enumerate(models):
                    if str(getattr(candidate, "model", "")).strip() == wanted_model:
                        index = position
                        break
            if not (0 <= index < len(models)):
                return None
            probe.active_model_index = index
        resolved = probe.active_model
    except Exception:
        logger.debug("Failed to resolve pinned reviewer model", exc_info=True)
        return None

    if resolved is None:
        return None
    return ReviewTarget(
        model=wanted_model if (wanted_model and source != "standard") else getattr(resolved, "model", ""),
        model_display_name=getattr(resolved, "model_display_name", ""),
        provider=getattr(resolved, "provider", ""),
        base_url=getattr(resolved, "base_url", ""),
        api_key=getattr(resolved, "api_key", ""),
        custom_headers=getattr(resolved, "custom_headers", None),
        client=None,
    )


def resolve_review_target(agent: Any, config: Any, review: Dict[str, Any]) -> Tuple[ReviewTarget, str]:
    """Pick the reviewer model, falling back to the main model when needed."""
    review = normalize_review_config(review)
    if str(review.get("model_mode") or "follow") == "custom":
        pinned = target_from_config(config, review)
        if pinned is not None and pinned.usable:
            return pinned, ""
        following = target_from_agent(agent)
        note = "Pinned reviewer model is unavailable; followed the main model instead."
        return following, note
    return target_from_agent(agent), ""


def _build_client(target: ReviewTarget) -> Any:
    """Create a throwaway SDK client for a pinned reviewer model."""
    headers = apply_reverie_client_identity(target.custom_headers)
    if target.provider in _SDK_PROVIDERS or target.provider == "openai-responses":
        from openai import OpenAI

        base_url = target.base_url.strip().rstrip("/")
        if target.provider == "openai-responses" and base_url.lower().endswith("/responses"):
            base_url = base_url[: -len("/responses")]
        return OpenAI(base_url=base_url or None, api_key=target.api_key, default_headers=headers)
    if target.provider == "anthropic":
        import anthropic

        return anthropic.Anthropic(
            base_url=target.base_url or None,
            api_key=target.api_key,
            default_headers=headers,
        )
    return None


def _request_review_text(target: ReviewTarget, user_content: str, review: Dict[str, Any]) -> str:
    """Issue one stateless review request and return the raw reply text."""
    max_tokens = int(review.get("max_tokens") or 900)
    timeout = int(review.get("timeout") or 45)
    messages = [
        {"role": "system", "content": REVIEW_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]

    if target.provider in _HTTP_PROVIDERS:
        headers = {
            "Authorization": f"Bearer {target.api_key}",
            "Content-Type": "application/json",
        }
        for key, value in (target.custom_headers or {}).items():
            name = str(key or "").strip()
            text = str(value or "").strip()
            if name and text:
                headers[name] = text
        response = requests.post(
            target.base_url,
            headers=apply_reverie_client_identity(headers),
            json={
                "model": target.model,
                "messages": messages,
                "stream": False,
                "max_tokens": max_tokens,
                "temperature": 0,
            },
            timeout=timeout,
        )
        response.raise_for_status()
        data = response.json()
        return str(((data.get("choices") or [{}])[0].get("message") or {}).get("content") or "")

    client = target.client or _build_client(target)
    if client is None:
        raise RuntimeError(f"No client available for reviewer provider '{target.provider}'.")

    if target.provider in _SDK_PROVIDERS:
        model_for_sdk = target.model.split("(", 1)[0].strip() if "(" in target.model else target.model
        response = client.chat.completions.create(
            model=model_for_sdk,
            messages=messages,
            stream=False,
            max_tokens=max_tokens,
            temperature=0,
            timeout=timeout,
        )
        return str(response.choices[0].message.content or "")

    if target.provider == "openai-responses":
        from ..codex import build_codex_request_payload

        converted = build_codex_request_payload(target.model, messages, tools=None, stream=False)
        response = client.responses.create(
            model=target.model,
            input=converted["input"],
            stream=False,
            timeout=timeout,
        )
        return str(getattr(response, "output_text", "") or "")

    if target.provider == "anthropic":
        response = client.messages.create(
            model=target.model,
            system=REVIEW_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_content}],
            max_tokens=max_tokens,
            timeout=timeout,
        )
        blocks = getattr(response, "content", None) or []
        return "".join(str(getattr(block, "text", "") or "") for block in blocks)

    raise RuntimeError(f"Reviewer provider '{target.provider}' is not supported.")


def review_tool_calls(
    calls: List[Dict[str, Any]],
    *,
    agent: Any = None,
    config: Any = None,
    review: Optional[Dict[str, Any]] = None,
    workspace_root: str = "",
    permission_level: str = "",
) -> ReviewOutcome:
    """Run one Auto Check pass over a batch of pending tool calls."""
    if not calls:
        return ReviewOutcome(verdicts={}, batch_risk="none", ok=True)

    settings = normalize_review_config(review if review is not None else getattr(config, "permission_review", None))
    target, note = resolve_review_target(agent, config, settings)
    if not target.usable:
        reason = (
            f"Reviewer model unavailable (provider '{target.provider or 'unknown'}'); "
            "used static risk priors instead."
        )
        return fallback_outcome(calls, reason)

    payload = build_review_payload(
        calls,
        workspace_root=workspace_root,
        permission_level=permission_level,
    )

    started = time.monotonic()
    try:
        text = _request_review_text(target, payload, settings)
    except Exception as exc:
        logger.warning("Auto Check review call failed: %s", exc)
        outcome = fallback_outcome(calls, f"Reviewer call failed ({exc.__class__.__name__}); used static risk priors.")
        outcome.model_display_name = target.describe()
        outcome.elapsed_ms = int((time.monotonic() - started) * 1000)
        return outcome

    outcome = parse_review_response(text, calls)
    outcome.elapsed_ms = int((time.monotonic() - started) * 1000)
    outcome.model_display_name = target.describe()
    if not outcome.ok:
        fallback = fallback_outcome(calls, outcome.error or "Reviewer reply was unusable; used static risk priors.")
        fallback.model_display_name = outcome.model_display_name
        fallback.elapsed_ms = outcome.elapsed_ms
        return fallback
    if note:
        outcome.error = note
    return outcome
