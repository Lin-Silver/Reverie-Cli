from reverie.agent.system_prompt import build_system_prompt
from reverie.agent.tool_descriptions import get_tool_descriptions_for_mode
from reverie.modes import get_mode_tool_discovery_profile


def test_reverie_prompt_uses_codex_style_agentic_positioning() -> None:
    prompt = build_system_prompt(model_name="Test Model", mode="reverie")

    assert "You are operating as and within the Reverie CLI" in prompt
    assert "You are Reverie, running in Reverie CLI." in prompt
    assert "The Reverie CLI is open-sourced." in prompt
    assert "Within this context, Reverie refers to the open-source agentic coding interface." in prompt
    assert "Please keep going until the user's query is completely resolved" in prompt
    assert "do NOT guess or make up an answer." in prompt
    assert "`reverie --help`" in prompt
    assert "`codex --help`" not in prompt
    assert "Ultra Agentic" not in prompt


def test_reverie_prompt_keeps_codex_how_you_work_sections() -> None:
    prompt = build_system_prompt(model_name="Test Model", mode="reverie")

    assert "# How you work" in prompt
    assert "## Personality" in prompt
    assert "### Preamble messages" in prompt
    assert "## Planning" in prompt
    assert "## Task execution" in prompt
    assert "## Sandbox and approvals" in prompt
    assert "## Ambition vs. precision" in prompt


def test_reverie_prompt_preserves_codex_coding_guidelines() -> None:
    prompt = build_system_prompt(model_name="Test Model", mode="reverie")

    assert "Fix the problem at the root cause rather than applying surface-level patches" in prompt
    assert "Avoid unneeded complexity in your solution." in prompt
    assert "Keep changes consistent with the style of the existing codebase." in prompt
    assert "NEVER add copyright or license headers unless specifically requested." in prompt
    assert "Do not `git commit` your changes or create new git branches unless explicitly requested." in prompt


def test_reverie_prompt_guides_external_research_and_download_automation() -> None:
    prompt = build_system_prompt(model_name="Test Model", mode="reverie")
    workflow = get_tool_descriptions_for_mode("reverie")

    assert "Prefer `web_search` for broad link discovery" in prompt
    assert "Prefer `web_fetch` for fetching selected pages" in prompt
    assert "Use those tool names and schemas rather than inventing Codex-specific tool names." in prompt
    assert "Search the web for many candidate links" in workflow
    assert "Fetch readable content from selected URLs." in workflow


def test_reverie_prompt_moves_style_preferences_to_rules_layer() -> None:
    prompt = build_system_prompt(model_name="Test Model", mode="reverie")

    assert "Your default personality and tone is concise, direct, and friendly." in prompt
    assert "Final answer structure and style guidelines" in prompt
    assert "Be terse, direct, and engineering-focused." not in prompt
    assert "Do not pad. Do not re-narrate the work. Report outcomes." not in prompt


def test_reverie_prompt_keeps_completion_contract() -> None:
    prompt = build_system_prompt(model_name="Test Model", mode="reverie")

    assert "Only terminate your turn when you are sure that the problem is solved." in prompt
    assert "Autonomously resolve the query to the best of your ability" in prompt
    assert "End every final response with `//END//`; this is Reverie's completion signal." in prompt


def test_reverie_tool_workflow_comes_from_json_manifest() -> None:
    workflow = get_tool_descriptions_for_mode("reverie")

    assert "Source: `reverie/agent/tool_manifest.json`" in workflow
    assert "General-purpose execution loop" in workflow
    assert "`web_search`" in workflow
    assert "`web_fetch`" in workflow
    assert "`command_exec`" in workflow
    assert "`task_manager`" in workflow
    assert "`tool_catalog`" in workflow
    assert "rc_blender_ensure_runtime" in workflow


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
