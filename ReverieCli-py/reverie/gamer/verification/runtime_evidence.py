"""Structured runtime evidence evaluation for Reverie-Gamer."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Tuple


_FAILURE_MARKERS = ("failed", "failure", "error", "exception", "crash", "fatal")


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _event_name(value: Any) -> str:
    return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")


def _event_names(run: Dict[str, Any], summary: Dict[str, Any]) -> Tuple[List[str], int, bool]:
    names: List[str] = []
    events = run.get("events")
    if not isinstance(events, list):
        events = summary.get("events")
    has_event_details = isinstance(events, list)
    if has_event_details:
        for event in events:
            if not isinstance(event, dict):
                continue
            name = _event_name(event.get("event") or event.get("name") or event.get("type"))
            if not name:
                continue
            names.append(name)
            state = _event_name(event.get("state") or event.get("status") or event.get("outcome"))
            if state:
                names.append(f"{name}:{state}")

    counts = summary.get("events_by_name")
    has_event_counts = isinstance(counts, dict)
    counted_events = 0
    if has_event_counts:
        for raw_name, raw_count in counts.items():
            name = _event_name(raw_name)
            count = int(_number(raw_count) or 0)
            if name and count > 0:
                names.extend([name] * count)
                counted_events += count

    reported_count = int(_number(summary.get("event_count")) or _number(run.get("event_count")) or 0)
    event_count = max(reported_count, len(events) if isinstance(events, list) else 0, counted_events)
    failure_visibility = (
        "failed_event_count" in summary
        or "failed_event_count" in run
        or isinstance(summary.get("failed_events", run.get("failed_events")), list)
    )
    return names, event_count, has_event_details or has_event_counts or failure_visibility


def _failed_event_count(run: Dict[str, Any], summary: Dict[str, Any], names: Iterable[str]) -> int:
    explicit = _number(summary.get("failed_event_count"))
    if explicit is None:
        explicit = _number(run.get("failed_event_count"))
    failed_events = summary.get("failed_events", run.get("failed_events"))
    listed = len(failed_events) if isinstance(failed_events, list) else 0
    named = sum(any(marker in name for marker in _FAILURE_MARKERS) for name in names)

    detailed = 0
    events = run.get("events")
    if not isinstance(events, list):
        events = summary.get("events")
    if isinstance(events, list):
        for event in events:
            if not isinstance(event, dict):
                continue
            status = _event_name(event.get("status") or event.get("outcome"))
            if event.get("success") is False or any(marker in status for marker in _FAILURE_MARKERS):
                detailed += 1
    return max(int(explicit or 0), listed, named, detailed)


def _frame_count(run: Dict[str, Any], summary: Dict[str, Any]) -> int:
    rendering = summary.get("rendering") if isinstance(summary.get("rendering"), dict) else {}
    metrics = summary.get("metrics") if isinstance(summary.get("metrics"), dict) else {}
    last_frame = rendering.get("last_frame") if isinstance(rendering.get("last_frame"), dict) else {}
    frames = summary.get("frames")
    candidates = [
        _number(run.get("frame_count")),
        _number(summary.get("frame_count")),
        _number(rendering.get("frame_count")),
        _number(metrics.get("frames_executed")),
    ]
    if isinstance(frames, list):
        candidates.append(float(len(frames)))
    last_index = _number(last_frame.get("frame_index"))
    if last_index is not None:
        candidates.append(last_index + 1)
    return int(max((item for item in candidates if item is not None), default=0.0))


def _frame_time(run: Dict[str, Any], summary: Dict[str, Any]) -> Tuple[float, str]:
    rendering = summary.get("rendering") if isinstance(summary.get("rendering"), dict) else {}
    metrics = summary.get("metrics") if isinstance(summary.get("metrics"), dict) else {}
    sources = (
        (run.get("avg_frame_time_ms"), "run.avg_frame_time_ms", 1.0),
        (summary.get("avg_frame_time_ms"), "summary.avg_frame_time_ms", 1.0),
        (summary.get("frame_time_ms"), "summary.frame_time_ms", 1.0),
        (rendering.get("avg_frame_time_ms"), "summary.rendering.avg_frame_time_ms", 1.0),
        (metrics.get("avg_frame_time_ms"), "summary.metrics.avg_frame_time_ms", 1.0),
        (metrics.get("frame_time_ms"), "summary.metrics.frame_time_ms", 1.0),
        (metrics.get("frame_time_ms_average"), "summary.metrics.frame_time_ms_average", 1.0),
    )
    for raw_value, source, scale in sources:
        value = _number(raw_value)
        if value is not None and value > 0:
            return value * scale, source

    engine_config = run.get("engine_config") if isinstance(run.get("engine_config"), dict) else {}
    runtime_config = engine_config.get("runtime") if isinstance(engine_config.get("runtime"), dict) else {}
    fixed_step = _number(runtime_config.get("fixed_step"))
    if fixed_step is not None and fixed_step > 0:
        return fixed_step * 1000.0, "engine_config.runtime.fixed_step"
    return 0.0, ""


def _target_fps(game_request: Dict[str, Any], runs: List[Dict[str, Any]]) -> int:
    requested = _number(game_request.get("quality_targets", {}).get("target_fps"))
    if requested is not None and requested > 0:
        return int(requested)
    for run in runs:
        engine_config = run.get("engine_config") if isinstance(run.get("engine_config"), dict) else {}
        runtime_config = engine_config.get("runtime") if isinstance(engine_config.get("runtime"), dict) else {}
        configured = _number(runtime_config.get("target_fps"))
        if configured is not None and configured > 0:
            return int(configured)
    return 60


def _required_loops(
    game_request: Dict[str, Any],
    blueprint: Dict[str, Any],
    system_bundle: Dict[str, Any],
) -> List[str]:
    packets = set((system_bundle.get("packets", {}) or {}).keys())
    requested = {_event_name(item) for item in game_request.get("systems", {}).get("required", []) or []}
    blueprint_systems = blueprint.get("gameplay_blueprint", {}).get("systems", {}) or {}
    if isinstance(blueprint_systems, dict):
        requested.update(_event_name(item) for item in blueprint_systems.keys())
    elif isinstance(blueprint_systems, list):
        requested.update(_event_name(item) for item in blueprint_systems)

    required: List[str] = []
    if "combat" in packets or requested.intersection({"combat", "encounter", "boss"}):
        required.append("combat")
    if "quest" in packets or requested.intersection({"quest", "quests", "objective"}):
        required.append("quest")
    if "progression" in packets or requested.intersection({"reward", "rewards", "progression"}):
        required.append("reward")
    if "save_load" in packets or requested.intersection({"save", "load", "save_load", "persistence"}):
        required.append("save")
    return required


def _contains_completion(names: Iterable[str], subjects: Tuple[str, ...], outcomes: Tuple[str, ...]) -> bool:
    return any(any(subject in name for subject in subjects) and any(outcome in name for outcome in outcomes) for name in names)


def _observed_loops(names: Iterable[str]) -> List[str]:
    event_names = list(names)
    observed: List[str] = []
    if _contains_completion(
        event_names,
        ("combat", "encounter", "enemy", "wave", "boss"),
        ("completed", "cleared", "defeated", "destroyed", "won"),
    ):
        observed.append("combat")
    if _contains_completion(
        event_names,
        ("quest", "objective", "goal", "slice"),
        ("completed", "complete", "reached", "cleared"),
    ):
        observed.append("quest")
    if _contains_completion(
        event_names,
        ("reward",),
        ("claimed", "granted", "earned", "received", "unlocked"),
    ):
        observed.append("reward")

    save_verified = any(
        name in {"save_load_verified", "save_roundtrip_verified", "persistence_verified"}
        for name in event_names
    )
    save_completed = _contains_completion(event_names, ("save",), ("completed", "complete", "written"))
    load_completed = _contains_completion(event_names, ("load", "restore"), ("completed", "complete", "restored"))
    if save_verified or (save_completed and load_completed):
        observed.append("save")
    return observed


def _check(check_id: str, passed: bool, summary: str, evidence: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": check_id,
        "passed": bool(passed),
        "summary": summary,
        "evidence": evidence,
    }


def evaluate_runtime_evidence(
    game_request: Dict[str, Any],
    blueprint: Dict[str, Any],
    system_bundle: Dict[str, Any],
    *,
    verification: Dict[str, Any] | None = None,
    runtime_result: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Evaluate only observed smoke/playtest telemetry; never synthesize missing evidence."""

    verification = dict(verification or {})
    runtime_result = dict(runtime_result or {})
    runs: List[Dict[str, Any]] = []
    for container_name, container in (("verification", verification), ("runtime_result", runtime_result)):
        nested_run = False
        for key in ("smoke", "playtest"):
            candidate = container.get(key)
            if isinstance(candidate, dict):
                runs.append({"kind": key, **candidate})
                nested_run = True
        listed_runs = container.get("runs")
        if isinstance(listed_runs, list):
            for candidate in listed_runs:
                if isinstance(candidate, dict):
                    runs.append(dict(candidate))
                    nested_run = True
        if not nested_run and ("success" in container or "summary" in container):
            runs.append({"kind": container_name, **container})

    event_names: List[str] = []
    event_count = 0
    failed_event_count = 0
    frame_count = 0
    frame_time_ms = 0.0
    frame_time_source = ""
    event_visibility = False
    successful_run_count = 0
    failed_run_count = 0
    run_summaries: List[Dict[str, Any]] = []

    for run in runs:
        summary = run.get("summary") if isinstance(run.get("summary"), dict) else {}
        names, current_event_count, current_visibility = _event_names(run, summary)
        current_failed_events = _failed_event_count(run, summary, names)
        current_frame_count = _frame_count(run, summary)
        current_frame_time, current_frame_time_source = _frame_time(run, summary)
        success = run.get("success") is True
        successful_run_count += int(success)
        failed_run_count += int(not success)
        event_names.extend(names)
        event_count += current_event_count
        failed_event_count += current_failed_events
        frame_count = max(frame_count, current_frame_count)
        event_visibility = event_visibility or current_visibility
        if current_frame_time > 0 and (frame_time_ms <= 0 or current_frame_time > frame_time_ms):
            frame_time_ms = current_frame_time
            frame_time_source = current_frame_time_source
        run_summaries.append(
            {
                "kind": str(run.get("kind", "runtime")),
                "success": success,
                "event_count": current_event_count,
                "failed_event_count": current_failed_events,
                "frame_count": current_frame_count,
                "frame_time_ms": round(current_frame_time, 4),
                "frame_time_source": current_frame_time_source,
            }
        )

    unique_event_names = sorted(set(event_names))
    has_session_start = "session_start" in unique_event_names
    has_session_end = "session_end" in unique_event_names
    target_fps = _target_fps(game_request, runs)
    frame_budget_ms = 1000.0 / target_fps
    required_loops = _required_loops(game_request, blueprint, system_bundle)
    observed_loops = _observed_loops(unique_event_names)
    missing_loops = [loop_id for loop_id in required_loops if loop_id not in observed_loops]

    run_observed = bool(runs) and successful_run_count > 0
    checks = [
        _check("run_recorded", run_observed, "A successful smoke or playtest run was recorded.", {"run_count": len(runs), "successful_runs": successful_run_count}),
        _check("session_lifecycle", has_session_start and has_session_end, "Runtime telemetry contains session start and end events.", {"session_start": has_session_start, "session_end": has_session_end}),
        _check("event_count", event_count > 0, "Runtime emitted at least one telemetry event.", {"event_count": event_count}),
        _check("failed_events", event_visibility and failed_event_count == 0 and failed_run_count == 0, "No failed run or failure event was observed, and event names are inspectable.", {"failed_event_count": failed_event_count, "failed_run_count": failed_run_count, "event_visibility": event_visibility}),
        _check("frame_count", frame_count > 0, "The runtime reported rendered or simulated frames.", {"frame_count": frame_count}),
        _check("frame_time", frame_time_ms > 0 and frame_time_ms <= frame_budget_ms * 1.05, "Frame timing is reported and stays within the requested frame budget.", {"frame_time_ms": round(frame_time_ms, 4), "frame_time_source": frame_time_source, "budget_ms": round(frame_budget_ms, 4), "target_fps": target_fps}),
        _check("requested_gameplay_loops", not missing_loops, "Requested gameplay loops have completion evidence from runtime events.", {"required": required_loops, "observed": observed_loops, "missing": missing_loops}),
    ]
    blockers = [check["summary"] for check in checks if not check["passed"]]
    return {
        "schema_version": "reverie.runtime_evidence/1",
        "valid": not blockers,
        "run_observed": run_observed,
        "event_count": event_count,
        "failed_event_count": failed_event_count,
        "frame_count": frame_count,
        "frame_time_ms": round(frame_time_ms, 4),
        "frame_time_source": frame_time_source,
        "target_fps": target_fps,
        "required_loop_evidence": required_loops,
        "observed_loop_evidence": observed_loops,
        "missing_loop_evidence": missing_loops,
        "event_names": unique_event_names,
        "runs": run_summaries,
        "checks": checks,
        "blockers": blockers,
    }
