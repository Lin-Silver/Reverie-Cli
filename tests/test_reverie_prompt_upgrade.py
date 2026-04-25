from reverie.agent.system_prompt import build_system_prompt
from reverie.agent.tool_descriptions import get_tool_descriptions_for_mode
from reverie.modes import get_mode_tool_discovery_profile


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


def test_reverie_prompt_adds_black_box_completion_protocol() -> None:
    prompt = build_system_prompt(model_name="Test Model", mode="reverie")

    assert "Black-Box Completion Protocol" in prompt
    assert "Treat broad user directives such as `continue`, `complete`, `black box`, `do not stop`, or `one-shot`" in prompt
    assert "Maintain a private completion ledger" in prompt
    assert "Ask the user only for irreversible or externally sensitive decisions" in prompt
    assert "For Blender, Blockbench, game, runtime, or asset-pipeline requests in base Reverie mode" in prompt
    assert "`production_character_pipeline`" in prompt
    assert "rather than a guarantee of final hand-authored AAA character art" in prompt


def test_reverie_tool_workflow_guides_black_box_character_art() -> None:
    workflow = get_tool_descriptions_for_mode("reverie")

    assert "For black-box, one-shot, `continue`, or \"do not stop\" requests" in workflow
    assert "Ask for `userInput` only for irreversible or externally sensitive choices" in workflow
    assert "For AAA character-art briefs in base Reverie mode" in workflow
    assert "require post-run audit evidence" in workflow
    assert "`game_models` assisted lanes" in workflow


def test_shared_coding_guardrails_are_injected_into_all_modes() -> None:
    for mode in (
        "reverie",
        "reverie-atlas",
        "reverie-gamer",
        "reverie-ant",
        "spec-driven",
        "spec-vibe",
        "writer",
        "computer-controller",
    ):
        prompt = build_system_prompt(model_name="Test Model", mode=mode)

        assert "Project-Wide Coding Guardrails" in prompt
        assert "Think Before Coding" in prompt
        assert "Simplicity First" in prompt
        assert "Surgical Changes" in prompt
        assert "Goal-Driven Execution" in prompt


def test_spec_driven_prompt_allows_one_shot_document_chain() -> None:
    prompt = build_system_prompt(
        model_name="Test Model",
        mode="spec-driven",
        additional_rules="This run was started through Reverie's one-shot prompt mode. There will be no follow-up turn.",
    )

    assert "Exception for one-shot non-interactive prompt runs" in prompt
    assert "treat the initial request as approval to generate requirements, design, and tasks sequentially" in prompt
    assert "Avoid extra spec files beyond requirements, design, and tasks" in prompt


def test_writer_prompt_allows_one_shot_requested_deliverables() -> None:
    prompt = build_system_prompt(
        model_name="Test Model",
        mode="writer",
        additional_rules="This run was started through Reverie's one-shot prompt mode. There will be no follow-up turn.",
    )

    assert "Exception for one-shot non-interactive prompt runs" in prompt
    assert "keep the workflow lean" in prompt
    assert "match the requested scope and avoid unnecessary expansion" in prompt


def test_atlas_prompt_downgrades_simple_tasks_back_to_reverie() -> None:
    prompt = build_system_prompt(model_name="Test Model", mode="reverie-atlas")

    assert "switch back to `reverie`" in prompt
    assert "Simple-task downgrade" in prompt
    assert "switch to `reverie`" in prompt
    assert "Atlas is not the preferred home for tiny, low-ambiguity coding tasks" in prompt


def test_writer_prompt_adds_style_brief_clarification_workflow() -> None:
    prompt = build_system_prompt(model_name="Test Model", mode="writer")

    assert "Phase 0: Story Brief Calibration" in prompt
    assert "use `ask_clarification` to confirm the style brief before outlining" in prompt
    assert "use `userInput`" in prompt
    assert "format, genre/subgenre, tone or atmosphere, target length, point of view, tense" in prompt


def test_writer_tooling_guidance_biases_toward_ask_user_tools() -> None:
    workflow = get_tool_descriptions_for_mode("writer")
    profile = get_mode_tool_discovery_profile("writer")

    assert "Use `ask_clarification` early" in workflow
    assert "Use `userInput` when you need explicit outline approval" in workflow
    assert "ask_clarification" in profile["boost_tools"]
    assert "userInput" in profile["boost_tools"]
    for token in ("style", "tone", "voice", "genre", "pov", "tense", "audience", "length"):
        assert token in profile["domain_tokens"]
