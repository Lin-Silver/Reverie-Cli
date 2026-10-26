"""Imported Elaya Design skills remain exact, licensed, and built in."""

import hashlib
import json
from pathlib import Path

from reverie.skills_manager import SkillsManager
from reverie.tools.skill_lookup import SkillLookupTool


def test_elayadesign_skills_are_exact_upstream_and_discoverable(tmp_path):
    root = Path(__file__).resolve().parents[1] / "reverie" / "builtin_skills"
    manifest = json.loads((root / "elayadesign-source.json").read_text(encoding="utf-8"))
    assert manifest["revision"] == "a2735a3eaf092eaaffb6dc17df25de33ef3bd048"
    assert "MIT License" in (root / manifest["license_file"]).read_text(encoding="utf-8")
    for name, expected in manifest["files"].items():
        assert hashlib.sha256((root / name).read_bytes()).hexdigest() == expected, name

    names = {name.split("/")[0] for name in manifest["files"] if name.endswith("/SKILL.md")}
    assert names == {"design-to-motion", "landing-page-design"}
    manager = SkillsManager(tmp_path / "workspace", tmp_path / "app")
    catalog = manager.describe_for_prompt()
    for name in names:
        record = manager.get_record(name)
        assert record is not None and record.root.scope == "builtin", name
        assert f"- {name}:" in catalog

    assert manager.pin_skill("landing-page-design")["status"] == "pinned"
    assert "landing-page-design [PINNED]" in manager.describe_for_prompt()
    tool = SkillLookupTool({"skills_manager": manager})
    result = tool.execute(operation="inspect", skill_name="landing-page-design", max_body_chars=20000)
    assert result.success and "one offer" in result.output
    listing = tool.execute(operation="list", max_results=20)
    listed_names = {row["name"] for row in listing.data["items"]}
    assert names <= listed_names
