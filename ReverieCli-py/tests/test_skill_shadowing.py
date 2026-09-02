"""A skill whose name is already taken must be reported, not silently ignored."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from reverie.sdk_bridge import ReverieSdkBridge
from reverie.skills_manager import SkillsManager
from reverie.tools.skill_lookup import SkillLookupTool

# One of the skills Reverie bundles, so the clash below is the real one users hit.
BUNDLED_NAME = "photo-to-3d"
REPO_DESCRIPTION = "My own rewrite of the photogrammetry workflow."


def _repo_skill(root: Path, name: str, description: str) -> Path:
    skill_dir = root / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_md = skill_dir / "SKILL.md"
    skill_md.write_text(
        f"---\nname: {name}\ndescription: {description}\n---\n\n{name} body from the repo.\n",
        encoding="utf-8",
    )
    return skill_md


@pytest.fixture
def isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Keep the developer's own `~/.agents/skills` out of these assertions."""
    home = tmp_path / "home"
    home.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    return home


def _manager(tmp_path: Path, *skills: tuple[str, str]) -> tuple[SkillsManager, Path]:
    project_root = tmp_path / "project"
    skills_root = project_root / ".agents" / "skills"
    skills_root.mkdir(parents=True, exist_ok=True)
    written = skills_root
    for name, description in skills:
        written = _repo_skill(skills_root, name, description)
    manager = SkillsManager(project_root=project_root, app_root=tmp_path / "app")
    manager.scan()
    return manager, written.resolve()


def test_a_repo_skill_that_reuses_a_bundled_name_is_reported_as_shadowed(
    tmp_path: Path, isolated_home: Path
) -> None:
    manager, hidden_path = _manager(tmp_path, (BUNDLED_NAME, REPO_DESCRIPTION))
    snapshot = manager.get_snapshot()

    assert snapshot.shadow_count == 1
    shadow = snapshot.shadowed[0]
    assert shadow.lookup_key == BUNDLED_NAME
    assert shadow.hidden.root.scope == "workspace"
    assert shadow.winner.root.scope == "builtin"
    # The name resolves to the bundled copy, which is exactly why the repo copy
    # needs reporting: it is listed on disk but can never be loaded by name.
    assert manager.get_record(BUNDLED_NAME).root.scope == "builtin"
    assert snapshot.shadowed_paths == frozenset({str(hidden_path).lower()})

    row = manager.list_shadow_rows()[0]
    assert row["name"] == BUNDLED_NAME
    assert row["path"] == str(hidden_path)
    assert row["scope"] == "Workspace"
    assert row["winner_scope"] == "Built-in"
    assert row["winner_root"] == "builtin_skills"
    assert "rename this one or delete it" in row["message"]

    assert manager.get_status_summary()["shadow_count"] == 1
    assert "1 shadowed" in snapshot.summary_label()


def test_a_shadowed_skill_stays_reachable_by_its_own_path(
    tmp_path: Path, isolated_home: Path
) -> None:
    manager, hidden_path = _manager(tmp_path, (BUNDLED_NAME, REPO_DESCRIPTION))

    by_path = manager.get_record(str(hidden_path))

    assert by_path is not None
    assert by_path.description == REPO_DESCRIPTION
    assert by_path.root.scope == "workspace"


def test_unique_names_report_no_shadowing(tmp_path: Path, isolated_home: Path) -> None:
    manager, _ = _manager(tmp_path, ("release-notes", "Draft release notes from the commit log."))
    snapshot = manager.get_snapshot()

    assert snapshot.shadowed == ()
    assert snapshot.shadow_count == 0
    assert "shadowed" not in snapshot.summary_label()
    assert manager.get_status_summary()["shadow_count"] == 0


def test_the_prompt_catalog_offers_a_shadowed_name_only_once(
    tmp_path: Path, isolated_home: Path
) -> None:
    manager, _ = _manager(tmp_path, (BUNDLED_NAME, REPO_DESCRIPTION))

    catalog = manager.describe_for_prompt()

    assert catalog.count(f"- {BUNDLED_NAME}:") == 1
    # Advertising the repo description would promise a body `skill_lookup` cannot return.
    assert REPO_DESCRIPTION not in catalog


def test_skill_lookup_does_not_list_the_unreachable_copy(
    tmp_path: Path, isolated_home: Path
) -> None:
    manager, _ = _manager(tmp_path, (BUNDLED_NAME, REPO_DESCRIPTION))
    tool = SkillLookupTool({"skills_manager": manager, "project_root": tmp_path / "project"})

    listing = tool.execute(operation="list")
    assert listing.success is True
    assert [row["name"] for row in listing.data["items"]].count(BUNDLED_NAME) == 1
    assert REPO_DESCRIPTION not in listing.output

    found = tool.execute(operation="search", query="photogrammetry rewrite")
    assert REPO_DESCRIPTION not in found.output


def test_the_bridge_flags_shadowed_skills_for_the_desktop(
    tmp_path: Path, isolated_home: Path
) -> None:
    manager, hidden_path = _manager(tmp_path, (BUNDLED_NAME, REPO_DESCRIPTION))
    bridge = ReverieSdkBridge()
    bridge.project_root = tmp_path.resolve()
    bridge.interface = SimpleNamespace(skills_manager=manager, agent=None)

    payload = bridge.dispatch({"id": "list", "action": "listSkills", "payload": {}})["skills"]

    assert payload["shadowed_count"] == 1
    assert payload["shadowed"][0]["name"] == BUNDLED_NAME
    assert payload["shadowed"][0]["winner_scope"] == "Built-in"
    flagged = [record for record in payload["records"] if record["shadowed"]]
    assert [record["path"] for record in flagged] == [str(hidden_path)]
    assert all(record["shadowed"] is False for record in payload["records"] if record not in flagged)
