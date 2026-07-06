"""SenseNova text-to-image model registry."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from . import sensenova_u1_fast


_PROFILES = {sensenova_u1_fast.MODEL_ID: sensenova_u1_fast}


def get_sensenova_tti_model_catalog() -> List[Dict[str, Any]]:
    return [profile.metadata() for profile in _PROFILES.values()]


def get_sensenova_tti_profile(model_id: Any):
    return _PROFILES.get(str(model_id or "").strip().lower())


def resolve_sensenova_tti_model(model_id_or_name: Any) -> Optional[Dict[str, Any]]:
    wanted = str(model_id_or_name or "").strip().lower()
    catalog = get_sensenova_tti_model_catalog()
    if not wanted:
        return catalog[0]
    for item in catalog:
        if wanted in {str(item["id"]).lower(), str(item["display_name"]).lower()}:
            return item
    return None

