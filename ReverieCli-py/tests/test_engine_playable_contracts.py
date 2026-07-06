from __future__ import annotations

from pathlib import Path

import pytest

from reverie.engine import create_project_skeleton, run_project_smoke, supported_game_families


FAMILY_IDS = [item["id"] for item in supported_game_families()]


@pytest.mark.parametrize("family_id", FAMILY_IDS)
def test_each_game_family_smoke_proves_a_stateful_slice_loop(tmp_path: Path, family_id: str) -> None:
    project_root = tmp_path / family_id
    create_project_skeleton(
        project_root,
        project_name=f"{family_id}-contract",
        dimension="2D",
        genre=family_id,
    )

    result = run_project_smoke(project_root)
    summary = result["summary"]
    events = summary["events_by_name"]
    world_state = summary["world_state"]

    assert result["success"] is True
    assert events["slice_completed"] == 1
    assert events["quest_updated"] >= 2
    assert events["inventory_changed"] >= 1
    assert events["reward_claimed"] == 1
    assert events["save_written"] == 1
    assert events["save_roundtrip_verified"] == 1
    assert world_state["quests"]["slice_objective"] == "completed"
    assert world_state["flags"]["slice:completed"] is True
    assert summary["metrics"]["frames_executed"] > 0
    assert summary["metrics"]["frame_time_ms_average"] >= 0
