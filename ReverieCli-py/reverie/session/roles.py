"""On-disk role spelling for session transcripts.

In memory and on the wire, model turns keep the provider-facing ``assistant``
role. On disk they are written as ``Reverie`` so saved transcripts read as a
conversation with Reverie rather than a generic assistant. Everything that
reads a session file directly should normalize through these helpers.
"""

from __future__ import annotations

from typing import Any, Dict, List

STORED_ASSISTANT_ROLE = 'Reverie'
WIRE_ASSISTANT_ROLE = 'assistant'


def to_stored_role(role: Any) -> str:
    """Map an in-memory role onto its on-disk spelling."""
    return STORED_ASSISTANT_ROLE if str(role or '') == WIRE_ASSISTANT_ROLE else str(role or '')


def from_stored_role(role: Any) -> str:
    """Map an on-disk role back onto the provider-facing spelling."""
    return WIRE_ASSISTANT_ROLE if str(role or '') == STORED_ASSISTANT_ROLE else str(role or '')


def to_stored_messages(messages: Any) -> List[Dict]:
    """Label model turns as ``Reverie`` on disk, leaving other roles untouched."""
    stored: List[Dict] = []
    for message in messages or []:
        if isinstance(message, dict) and message.get('role') == WIRE_ASSISTANT_ROLE:
            relabelled = dict(message)
            relabelled['role'] = STORED_ASSISTANT_ROLE
            stored.append(relabelled)
        else:
            stored.append(message)
    return stored


def from_stored_messages(messages: Any) -> List[Dict]:
    """Restore the provider-facing ``assistant`` role when loading from disk."""
    restored: List[Dict] = []
    for message in messages or []:
        if isinstance(message, dict) and str(message.get('role') or '') == STORED_ASSISTANT_ROLE:
            relabelled = dict(message)
            relabelled['role'] = WIRE_ASSISTANT_ROLE
            restored.append(relabelled)
        else:
            restored.append(message)
    return restored
