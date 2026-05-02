"""Performance baselines for Reverie Engine Lite."""

from __future__ import annotations

from pathlib import Path
from statistics import mean
from time import perf_counter
from typing import Any, Dict

from .app import load_project_scene
from .serialization import validate_scene_document


def _percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round((len(ordered) - 1) * p))))
    return ordered[index]


def _summary(name: str, durations_ms: list[float]) -> Dict[str, Any]:
    return {
        "name": name,
        "iterations": len(durations_ms),
        "min_ms": round(min(durations_ms) if durations_ms else 0.0, 4),
        "avg_ms": round(mean(durations_ms) if durations_ms else 0.0, 4),
        "p95_ms": round(_percentile(durations_ms, 0.95), 4),
        "max_ms": round(max(durations_ms) if durations_ms else 0.0, 4),
        "samples_ms": [round(value, 4) for value in durations_ms],
    }


def benchmark_scene_instantiation(
    project_root: Path,
    *,
    iterations: int = 10,
    scene_path: str | Path | None = None,
) -> Dict[str, Any]:
    project_root = Path(project_root)
    durations_ms: list[float] = []
    for _ in range(max(1, int(iterations))):
        start = perf_counter()
        load_project_scene(project_root, scene_path)
        durations_ms.append((perf_counter() - start) * 1000.0)
    return _summary("scene_instantiation", durations_ms)


def benchmark_ai_command_latency(project_root: Path, *, iterations: int = 12) -> Dict[str, Any]:
    from ..tools.reverie_engine import ReverieEngineTool

    tool = ReverieEngineTool({"project_root": str(Path(project_root).resolve())})
    scene_payload = {
        "name": "BenchmarkScene",
        "type": "Scene",
        "scene_id": "benchmark_scene",
        "metadata": {"engine": "reverie_engine"},
        "components": [{"type": "Transform", "position": [0, 0, 0]}],
        "children": [],
    }
    validate_scene_document(scene_payload)

    durations_ms: list[float] = []
    for _ in range(max(1, int(iterations))):
        start = perf_counter()
        result = tool.execute(action="author_scene_blueprint", data=scene_payload)
        if not result.success:
            raise RuntimeError(result.error or "author_scene_blueprint failed during benchmark")
        durations_ms.append((perf_counter() - start) * 1000.0)
    return _summary("ai_command_latency", durations_ms)


def benchmark_project(
    project_root: Path,
    *,
    iterations: int = 10,
    scene_path: str | Path | None = None,
) -> Dict[str, Any]:
    project_root = Path(project_root)
    scene_baseline = benchmark_scene_instantiation(project_root, iterations=iterations, scene_path=scene_path)
    ai_baseline = benchmark_ai_command_latency(project_root, iterations=max(6, iterations))
    return {
        "project_root": str(project_root.resolve()),
        "benchmarks": {
            "scene_instantiation": scene_baseline,
            "ai_command_latency": ai_baseline,
        },
    }
