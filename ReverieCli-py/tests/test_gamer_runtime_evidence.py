from __future__ import annotations

from copy import deepcopy

from reverie.gamer.verification import (
    build_quality_gate_report,
    evaluate_runtime_evidence,
    evaluate_slice_score,
)


def _artifacts() -> tuple[dict, dict, dict, dict, dict]:
    game_request = {
        "creative_target": {"primary_genre": "action_rpg"},
        "experience": {"dimension": "3D", "camera_model": "third_person"},
        "systems": {"required": ["combat", "quest", "progression", "save_load"]},
        "quality_targets": {"target_fps": 60, "must_have": ["combat", "quest", "save"]},
        "production": {
            "delivery_scope": "vertical_slice",
            "complexity_score": 40,
            "deferred_features": ["second_region"],
            "content_scale": {"delivery_target": "one_complete_route"},
        },
    }
    blueprint = {
        "meta": {"project_name": "Evidence Slice", "target_engine": "reverie_engine"},
        "gameplay_blueprint": {
            "core_loop": ["onboard", "fight", "complete quest", "claim reward"],
            "systems": {"combat": {}, "quest": {}, "progression": {}, "save_load": {}},
        },
    }
    packet = {"tests": ["one", "two", "three"]}
    system_bundle = {
        "packets": {
            "character_controller": deepcopy(packet),
            "combat": deepcopy(packet),
            "quest": {**deepcopy(packet), "slice_objectives": [{}, {}, {}], "telemetry": ["quest_completed"]},
            "save_load": {
                **deepcopy(packet),
                "save_schema": {"fields": ["quest", "reward", "world"]},
                "migration_rules": ["preserve", "default"],
            },
            "progression": {**deepcopy(packet), "reward_track": {"nodes": [{}, {}, {}]}},
            "world_structure": {
                **deepcopy(packet),
                "zone_layout": [{}, {}, {}],
                "asset_contracts": {"import_rules": ["naming", "budget", "dependencies"]},
            },
        }
    }
    runtime_profile = {"id": "reverie_engine", "capabilities": ["smoke", "telemetry", "rendering"]}
    runtime_result = {"files": ["scene", "config", "content"]}
    return game_request, blueprint, system_bundle, runtime_profile, runtime_result


def _runtime_verification() -> dict:
    return {
        "valid": True,
        "smoke": {
            "success": True,
            "summary": {
                "event_count": 12,
                "events_by_name": {
                    "session_start": 1,
                    "checkpoint": 3,
                    "combat_completed": 1,
                    "quest_completed": 1,
                    "reward_claimed": 1,
                    "save_completed": 1,
                    "load_completed": 1,
                    "session_end": 1,
                },
                "avg_frame_time_ms": 16.0,
                "rendering": {"frame_count": 180, "last_frame": {"frame_index": 179}},
            },
        },
    }


def test_missing_runtime_evidence_caps_score_and_fails_quality_gate() -> None:
    game_request, blueprint, system_bundle, runtime_profile, runtime_result = _artifacts()
    verification = {"valid": True, "checks": [{"id": "static_validation", "passed": True}]}

    score = evaluate_slice_score(
        game_request,
        blueprint,
        system_bundle,
        runtime_profile=runtime_profile,
        runtime_result=runtime_result,
        verification=verification,
    )
    gates = build_quality_gate_report(
        game_request,
        blueprint,
        system_bundle,
        runtime_profile=runtime_profile,
        runtime_result=runtime_result,
        verification=verification,
        slice_score=score,
    )

    assert score["raw_score"] >= 70
    assert score["score"] == 69
    assert score["verdict"] not in {"credible_vertical_slice_base", "strong_vertical_slice_base"}
    assert score["runtime_evidence"]["valid"] is False
    assert next(gate for gate in gates["gate_sets"] if gate["id"] == "runtime_boot")["status"] == "fail"
    assert next(gate for gate in gates["gate_sets"] if gate["id"] == "slice_readiness")["status"] == "fail"


def test_complete_observed_runtime_evidence_passes_score_and_quality_gate() -> None:
    game_request, blueprint, system_bundle, runtime_profile, runtime_result = _artifacts()
    verification = _runtime_verification()

    evidence = evaluate_runtime_evidence(
        game_request,
        blueprint,
        system_bundle,
        verification=verification,
        runtime_result=runtime_result,
    )
    score = evaluate_slice_score(
        game_request,
        blueprint,
        system_bundle,
        runtime_profile=runtime_profile,
        runtime_result=runtime_result,
        verification=verification,
    )
    gates = build_quality_gate_report(
        game_request,
        blueprint,
        system_bundle,
        runtime_profile=runtime_profile,
        runtime_result=runtime_result,
        verification=verification,
        slice_score=score,
    )

    assert evidence["valid"] is True
    assert evidence["event_count"] >= 10
    assert evidence["failed_event_count"] == 0
    assert evidence["frame_count"] == 180
    assert evidence["frame_time_ms"] == 16.0
    assert evidence["missing_loop_evidence"] == []
    assert score["score"] >= 70
    assert score["verdict"] == "strong_vertical_slice_base"
    assert next(gate for gate in gates["gate_sets"] if gate["id"] == "runtime_boot")["status"] == "pass"
    assert next(gate for gate in gates["gate_sets"] if gate["id"] == "slice_readiness")["status"] == "pass"
