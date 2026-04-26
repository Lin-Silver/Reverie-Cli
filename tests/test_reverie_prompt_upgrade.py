from reverie.agent.system_prompt import build_system_prompt
from reverie.agent.tool_descriptions import get_tool_descriptions_for_mode
from reverie.modes import get_mode_tool_discovery_profile


def test_reverie_prompt_sets_full_spectrum_ultra_agentic_positioning() -> None:
    prompt = build_system_prompt(model_name="Test Model", mode="reverie")

    assert "You are the default full-spectrum Ultra Agentic mode." in prompt
    assert "Base Reverie is not a reduced-scope fallback or a smallest-toolset mode." in prompt
    assert "Use the strongest available tool or toolchain that matches the task." in prompt
    assert "Switch modes when a specialist workflow offers better artifacts, continuity, or control" in prompt


def test_reverie_prompt_keeps_incremental_task_manager_triggers() -> None:
    prompt = build_system_prompt(model_name="Test Model", mode="reverie")

    assert "Use `task_manager` when any of these triggers apply" in prompt
    assert "multi-file or cross-layer" in prompt
    assert "more than 2 edit/verify cycles likely" in prompt
    assert "more than 5 information-gathering steps likely" in prompt
    assert "batch state updates when switching tasks" in prompt


def test_reverie_prompt_adds_package_and_verification_loop_guidance() -> None:
    prompt = build_system_prompt(model_name="Test Model", mode="reverie")

    assert "Use the appropriate package manager for dependency changes instead of manually editing manifests" in prompt
    assert "If verification fails, diagnose the root cause, fix it, and re-run targeted checks" in prompt
    assert "After editing, run the most relevant verification available" in prompt


def test_reverie_prompt_moves_style_preferences_to_rules_layer() -> None:
    prompt = build_system_prompt(model_name="Test Model", mode="reverie")

    assert "Project, team, or user preferences about tone, verbosity, formatting, explanation depth, or reporting style belong in Rules-layer guidance supplied through `additional_rules`." in prompt
    assert "Let tone, verbosity, formatting, and explanation-depth preferences come from the active Rules layer" in prompt
    assert "Be terse, direct, and engineering-focused." not in prompt
    assert "Do not pad. Do not re-narrate the work. Report outcomes." not in prompt


def test_reverie_prompt_adds_black_box_completion_protocol() -> None:
    prompt = build_system_prompt(model_name="Test Model", mode="reverie")

    assert "Black-Box Completion Protocol" in prompt
    assert "Treat broad directives - `continue`, `complete`, `black box`, `do not stop`, `one-shot`, `keep going`" in prompt
    assert "Maintain the private completion ledger at all times." in prompt
    assert "Escalate to the user **only** for: credentials, paid resources" in prompt
    assert "For Blender, Blockbench, game, runtime, or asset-pipeline requests in base Reverie mode" in prompt
    assert "continuous deformable body core" in prompt
    assert "TRELLIS `profile=low_vram`" in prompt


def test_reverie_tool_workflow_guides_full_spectrum_execution() -> None:
    workflow = get_tool_descriptions_for_mode("reverie")

    assert "Base Reverie is the default full-spectrum Ultra Agentic mode" in workflow
    assert "Use the strongest visible toolchain that matches the task" in workflow
    assert "For black-box, one-shot, `continue`, or \"do not stop\" requests" in workflow
    assert "Ask for `userInput` only for irreversible or externally sensitive choices" in workflow
    assert "For AAA character-art briefs in base Reverie mode" in workflow
    assert "require post-run audit evidence" in workflow
    assert "`game_models` assisted lanes" in workflow
    assert "body-continuity" in workflow
    assert "workflow leverage, artifacts, or continuity instead of because Reverie lacks capability" in workflow


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
