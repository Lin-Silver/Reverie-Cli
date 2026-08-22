"""Contract tests for the consolidated five-mode registry.

Reverie used to ship eight workflow modes. `reverie-ant`, `spec-driven`, and
`spec-vibe` were folded into `reverie` and `reverie-atlas`; their names were
removed outright rather than aliased, so a stale name must fail loudly instead
of silently landing the user in the default mode.
"""

import json
from pathlib import Path

from reverie.agent.system_prompt import build_system_prompt
from reverie.modes import (
    MODE_ALIASES,
    MODE_METADATA,
    MODE_TOOL_DISCOVERY_PROFILES,
    RETIRED_MODES,
    describe_retired_mode,
    get_retired_mode_replacement,
    is_known_mode,
    list_modes,
    normalize_mode,
)

EXPECTED_MODES = [
    "reverie",
    "reverie-atlas",
    "reverie-gamer",
    "writer",
    "computer-controller",
]

RETIRED_NAMES = [
    "reverie-ant",
    "ant",
    "spec-driven",
    "reverie-spec-driven",
    "spec driven",
    "spec-vibe",
    "spec vibe",
]


def test_registry_exposes_exactly_five_modes() -> None:
    assert list(MODE_METADATA) == EXPECTED_MODES
    assert list_modes(include_computer=True) == EXPECTED_MODES
    assert list_modes(include_computer=False) == EXPECTED_MODES[:-1]
    assert list_modes(switchable_only=True) == EXPECTED_MODES[:-1]


def test_every_mode_has_a_discovery_profile() -> None:
    assert set(MODE_TOOL_DISCOVERY_PROFILES) == set(EXPECTED_MODES)


def test_retired_names_are_not_aliases() -> None:
    for name in RETIRED_NAMES:
        assert name not in MODE_ALIASES, name
        assert not is_known_mode(name), name


def test_retired_names_report_their_replacement() -> None:
    assert set(RETIRED_MODES) == set(RETIRED_NAMES)
    assert get_retired_mode_replacement("spec-driven") == "reverie-atlas"
    assert get_retired_mode_replacement("spec-vibe") == "reverie"
    assert get_retired_mode_replacement("reverie-ant") == "reverie"
    assert get_retired_mode_replacement("reverie") == ""

    for name in RETIRED_NAMES:
        message = describe_retired_mode(name)
        assert message.startswith(f"Mode '{name}' has been removed."), message
        assert f"Use '{RETIRED_MODES[name]}' instead." in message, message

    # Alternate spellings must inherit their own family's note, not whichever
    # retired mode happens to share the same replacement.
    assert "Structured planning" in describe_retired_mode("ant")
    assert "Implementing an approved spec" in describe_retired_mode("spec vibe")
    assert "Spec authoring" in describe_retired_mode("reverie-spec-driven")

    assert describe_retired_mode("reverie") == ""
    assert describe_retired_mode("not-a-mode") == ""


def test_is_known_mode_accepts_live_aliases_and_rejects_noise() -> None:
    assert is_known_mode("atlas") is True
    assert is_known_mode("Deeper") is True
    assert is_known_mode("computer-controler") is True
    assert is_known_mode("") is False
    assert is_known_mode(None) is False
    assert is_known_mode("nope") is False


def test_normalize_mode_still_falls_back_for_runtime_callers() -> None:
    # normalize_mode is the lenient runtime path; validation belongs to
    # is_known_mode, which is what the CLI entrypoints call first.
    assert normalize_mode("spec-driven") == "reverie"
    assert normalize_mode("reverie-ant") == "reverie"
    for mode in EXPECTED_MODES:
        assert normalize_mode(mode) == mode


def test_every_mode_builds_a_prompt() -> None:
    for mode in EXPECTED_MODES:
        prompt = build_system_prompt(model_name="Test Model", mode=mode)
        assert prompt.strip()


def test_retired_prompt_builders_are_gone() -> None:
    from reverie.agent import system_prompt

    for removed in (
        "build_spec_driven_prompt",
        "build_spec_vibe_prompt",
        "build_ant_planning_prompt",
        "build_ant_execution_prompt",
    ):
        assert not hasattr(system_prompt, removed), removed


def test_tool_manifest_covers_exactly_the_live_modes() -> None:
    import reverie.agent as agent_pkg

    manifest_path = Path(agent_pkg.__file__).parent / "tool_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    profiles = manifest.get("mode_profiles", {})

    assert set(profiles) == set(EXPECTED_MODES)
    for retired in ("ant", "spec-driven", "spec-vibe"):
        assert retired not in profiles
