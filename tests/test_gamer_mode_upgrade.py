from reverie.agent.system_prompt import build_system_prompt
from reverie.agent.tool_descriptions import get_tool_descriptions_for_mode
from reverie.modes import get_mode_metadata, get_mode_tool_discovery_profile


def test_reverie_gamer_prompt_targets_prompt_to_vertical_slice_delivery() -> None:
    prompt = build_system_prompt(model_name="Test Model", mode="reverie-gamer")

    assert "prompt -> structured request -> blueprint -> engine-aware project foundation" in prompt
    assert "artifacts/game_request.json" in prompt
    assert "artifacts/game_blueprint.json" in prompt
    assert "artifacts/vertical_slice_plan.md" in prompt
    assert "automatically reduce it to the smallest credible prototype, first playable, or vertical slice" in prompt
    assert 'game_design_orchestrator(action="generate_vertical_slice")' in prompt
    assert 'game_playtest_lab(action="create_test_plan")' in prompt


def test_reverie_gamer_workflow_and_discovery_profile_bias_toward_slice_execution() -> None:
    workflow = get_tool_descriptions_for_mode("reverie-gamer")
    metadata = get_mode_metadata("reverie-gamer")
    profile = get_mode_tool_discovery_profile("reverie-gamer")

    assert "prompt-to-production flow" in workflow
    assert "reduce scope to the first credible playable slice" in workflow
    assert "game_playtest_lab" in workflow
    assert "vertical slices" in str(metadata.get("description", ""))
    assert "tool_catalog" in profile["boost_tools"]
    assert "task_manager" in profile["boost_tools"]
    assert "retrieval" in profile["focus_categories"]
    assert "orchestration" in profile["focus_categories"]
    for token in ("vertical", "slice", "scope", "playable", "godot"):
        assert token in profile["domain_tokens"]
