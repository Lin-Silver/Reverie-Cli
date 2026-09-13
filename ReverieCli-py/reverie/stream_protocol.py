"""Lightweight stream markers shared by the agent and its hosts."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional


THINKING_START_MARKER = "[[THINKING_START]]"
THINKING_END_MARKER = "[[THINKING_END]]"
STREAM_EVENT_MARKER = "[[REVERIE_EVENT]]"
HIDDEN_STREAM_TOKEN = "//END//"

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
