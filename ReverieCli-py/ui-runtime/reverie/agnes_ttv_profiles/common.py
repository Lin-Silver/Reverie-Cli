"""Shared helpers for Agnes video generation profiles."""

from __future__ import annotations

from typing import Any, Dict, List


def build_metadata(
    *,
    model_id: str,
    display_name: str,
    description: str,
    input_modalities: List[str],
) -> Dict[str, Any]:
    return {
        "id": model_id,
        "display_name": display_name,
        "description": description,
        "source": "agnes",
        "api": "v1.videos",
        "input_modalities": input_modalities,
        "output_modalities": ["video"],
        "requires_api_key": True,
        "parameter_constraints": {
            "num_frames": {
                "rule": "8n+1",
                "minimum": 1,
                "maximum": 441,
                "examples": [81, 121],
            },
            "frame_rate": {"minimum": 1, "maximum": 60},
        },
        "output_capabilities": {
            "async_task": True,
            "downloadable_video": True,
            "status_lookup": ["video_id", "task_id"],
            "formats": ["mp4", "webm", "mov", "mkv"],
        },
    }


def is_valid_num_frames(value: Any, metadata: Dict[str, Any]) -> bool:
    try:
        frames = int(value)
    except (TypeError, ValueError):
        return False
    constraints = (
        metadata.get("parameter_constraints", {})
        .get("num_frames", {})
    )
    minimum = int(constraints.get("minimum", 1) or 1)
    maximum = int(constraints.get("maximum", 441) or 441)
    return frames >= minimum and frames <= maximum and frames % 8 == 1


def num_frames_error(metadata: Dict[str, Any]) -> str:
    constraints = (
        metadata.get("parameter_constraints", {})
        .get("num_frames", {})
    )
    rule = str(constraints.get("rule", "") or "").strip()
    maximum = constraints.get("maximum", "")
    examples = constraints.get("examples", [])
    example_text = ", ".join(str(item) for item in examples) if examples else ""
    detail = f"{rule} and <= {maximum}".strip()
    if example_text:
        detail = f"{detail}, e.g. {example_text}"
    return f"num_frames must follow provider profile constraint: {detail}."

