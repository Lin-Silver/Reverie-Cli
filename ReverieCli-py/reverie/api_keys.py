"""API key references shared by model and provider configuration surfaces."""

import os
import re
from typing import Any, Dict, List


def normalize_api_key_env(value: Any) -> str:
    name = str(value or "").strip()
    if name and not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
        raise ValueError("API key environment variable must be a name such as OPENAI_API_KEY.")
    return name


def api_key_settings(value: str) -> Dict[str, str]:
    """Parse a CLI key or an explicit ``env:NAME`` reference."""
    text = str(value or "").strip()
    if text.lower().startswith("env:"):
        name = normalize_api_key_env(text[4:])
        if not name:
            raise ValueError("An API key environment variable name is required.")
        return {"api_key": "", "api_key_env": name}
    return {"api_key": text, "api_key_env": ""}


def api_key_environment_names() -> List[str]:
    """Offer credential variable names without exposing their values."""
    return sorted(name for name, value in os.environ.items()
                  if value.strip() and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name)
                  and re.search(r"(?:KEY|TOKEN|SECRET)", name, re.IGNORECASE))
