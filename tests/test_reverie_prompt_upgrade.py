from reverie.agent.system_prompt import build_system_prompt


def test_reverie_prompt_adds_incremental_task_manager_triggers() -> None:
    prompt = build_system_prompt(model_name="Test Model", mode="reverie")

    assert "Immediately decide whether to work directly or use `task_manager`." in prompt
    assert "Use `task_manager` when any of these triggers apply" in prompt
    assert "multi-file or cross-layer" in prompt
    assert "more than 2 edit/verify cycles are likely" in prompt
    assert "more than 5 information-gathering iterations are likely" in prompt
    assert "batch state updates when switching tasks" in prompt


def test_reverie_prompt_adds_package_and_verification_loop_guidance() -> None:
    prompt = build_system_prompt(model_name="Test Model", mode="reverie")

    assert "Gather only the evidence needed to proceed safely." in prompt
    assert "Use the appropriate package manager for dependency installs, removals, or upgrades" in prompt
    assert "If verification fails, debug, fix, and re-run the targeted checks" in prompt
    assert "Before a burst of related retrieval or command calls, briefly tell the user what you are checking and why." in prompt
