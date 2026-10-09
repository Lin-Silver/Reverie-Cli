"""The installed design library must be discoverable, complete and pinnable."""
import hashlib
import json
from pathlib import Path

from reverie.skills_manager import SkillsManager
from reverie.tools.skill_lookup import SkillLookupTool


def test_design_skills_retain_upstream_resources_and_license(tmp_path):
    root = Path(__file__).resolve().parents[1] / "reverie" / "builtin_skills"
    manifest = json.loads((root / "emilkowalski-source.json").read_text(encoding="utf-8"))
    assert manifest["revision"] == "e8a175de22ae1e49370fc144c1f3bb9aeedf988d"
    assert "MIT License" in (root / manifest["license_file"]).read_text(encoding="utf-8")
    for name, expected in manifest["files"].items():
        assert hashlib.sha256((root / name).read_bytes()).hexdigest() == expected, name
    names = {name.split("/")[0] for name in manifest["files"] if name.endswith("/SKILL.md")}
    assert len(names) == 14
    manager = SkillsManager(tmp_path / "workspace", tmp_path / "app")
    catalog = manager.describe_for_prompt()
    for name in names:
        record = manager.get_record(name)
        assert record is not None and record.root.scope == "builtin", name
        assert f"- {name}:" in catalog, name
    assert manager.pin_skill("apple-design")["status"] == "pinned"
    assert "apple-design [PINNED]" in manager.describe_for_prompt()
    assert "before taking any task action" in manager.describe_pinned_for_prompt()
    tool = SkillLookupTool({"skills_manager": manager})
    result = tool.execute(operation="inspect", skill_name="apple-design", max_body_chars=20000)
    assert result.success and "Typography" in result.output
    result = tool.execute(operation="read_resource", skill_name="break-ui", resource_path="CATALOG.md")
    assert result.success and "Worst-Case Catalog" in result.output
