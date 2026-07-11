"""Shared helpers for Reverie-Gamer system packet generation."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def unique_strings(values: Iterable[str]) -> List[str]:
    seen: set[str] = set()
    ordered: List[str] = []
    for value in values:
        item = str(value or "").strip()
        if item and item not in seen:
            seen.add(item)
            ordered.append(item)
    return ordered


def creative_references(game_request: Dict[str, Any]) -> List[str]:
    return unique_strings(game_request.get("creative_target", {}).get("references", []) or [])


def specialized_systems(game_request: Dict[str, Any]) -> set[str]:
    return {
        str(item).strip()
        for item in game_request.get("systems", {}).get("specialized", []) or []
        if str(item).strip()
    }


def party_model(game_request: Dict[str, Any]) -> str:
    return str(game_request.get("experience", {}).get("party_model", "single_hero_focus")).strip() or "single_hero_focus"


def live_service_enabled(game_request: Dict[str, Any]) -> bool:
    return bool(game_request.get("production", {}).get("live_service_profile", {}).get("enabled", False))


def project_name(game_request: Dict[str, Any], blueprint: Dict[str, Any]) -> str:
    return str(
        blueprint.get("meta", {}).get("project_name")
        or game_request.get("meta", {}).get("project_name")
        or "Untitled Reverie Slice"
    )


def target_runtime(blueprint: Dict[str, Any], runtime_profile: Dict[str, Any] | None = None) -> str:
    return str(
        (runtime_profile or {}).get("id")
        or blueprint.get("meta", {}).get("target_engine")
        or "reverie_engine"
    )


def required_systems(game_request: Dict[str, Any]) -> List[str]:
    return [
        str(item).strip()
        for item in game_request.get("systems", {}).get("required", [])
        if str(item).strip()
    ]


def source_systems(game_request: Dict[str, Any], candidates: Iterable[str]) -> List[str]:
    requested = required_systems(game_request)
    result = [name for name in candidates if name in requested]
    return result or [name for name in candidates if str(name).strip()]


def reference_titles(game_request: Dict[str, Any]) -> List[str]:
    return creative_references(game_request)


def experience(game_request: Dict[str, Any]) -> Dict[str, Any]:
    return dict(game_request.get("experience", {}) or {})


def production(game_request: Dict[str, Any]) -> Dict[str, Any]:
    return dict(game_request.get("production", {}) or {})


def quality_targets(game_request: Dict[str, Any]) -> Dict[str, Any]:
    return dict(game_request.get("quality_targets", {}) or {})


def packet_header(
    packet_id: str,
    display_name: str,
    game_request: Dict[str, Any],
    blueprint: Dict[str, Any],
    runtime_profile: Dict[str, Any] | None,
    packet_source_systems: Iterable[str],
) -> Dict[str, Any]:
    current_experience = experience(game_request)
    return {
        "id": packet_id,
        "display_name": display_name,
        "project_name": project_name(game_request, blueprint),
        "runtime_owner": target_runtime(blueprint, runtime_profile),
        "dimension": str(current_experience.get("dimension", "3D")),
        "camera_model": str(current_experience.get("camera_model", "third_person")),
        "source_systems": [str(item).strip() for item in packet_source_systems if str(item).strip()],
    }
