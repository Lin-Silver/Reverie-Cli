"""Shared helpers for Reverie-Gamer system packet generation."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List


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
    return [
        str(item).strip()
        for item in game_request.get("creative_target", {}).get("references", [])
        if str(item).strip()
    ]


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
