"""Regression checks for skill metadata, search, and packaged resources."""

from pathlib import Path
import subprocess

import pytest

from reverie.skills_manager import SkillsManager
from reverie.tools.registry import get_tool_classes_for_mode
from reverie.tools.skill_lookup import SkillLookupTool


@pytest.fixture
def local_skill(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "home"))
    directory = tmp_path / "project" / ".agents" / "skills" / "sample"
    directory.mkdir(parents=True)
    (directory / "SKILL.md").write_text(
        "---\nname: sample\ndescription: 逆向工程与安全分析。\n---\n\n检查二进制文件。\n",
        encoding="utf-8",
    )
    manager = SkillsManager(tmp_path / "project", tmp_path / "app")
    return directory, manager, SkillLookupTool({"skills_manager": manager})


def test_utf8_bom_preserves_skill_identity_and_frontmatter(local_skill):
    directory, manager, tool = local_skill
    (directory / "SKILL.md").write_text(
        "---\nname: bom-workflow\ndescription: Metadata survives a BOM.\n---\n\nOnly instructions.\n",
        encoding="utf-8-sig",
    )
    record = manager.get_record("bom-workflow", force_refresh=True)
    assert record is not None
    assert record.description == "Metadata survives a BOM."
    assert record.body == "Only instructions."
    assert manager.resolve_explicit_mentions("$bom-workflow")["records"] == [record]
    assert tool.execute(operation="inspect", skill_name="bom-workflow").data["body"] == record.body


@pytest.mark.parametrize("query", ["逆向工程", "安全分析", "二进制文件"])
def test_search_finds_chinese_description_and_body(local_skill, query):
    _, _, tool = local_skill
    result = tool.execute(operation="search", query=query)
    assert result.success
    assert "sample" in {item["name"] for item in result.data["items"]}
    assert tool.execute(operation="search", query="不存在的关键词").data["count"] == 0


@pytest.mark.parametrize("resource_path", ["bad\x00path", "../outside.md", "missing.md", "", "."])
def test_invalid_resource_paths_return_failure(local_skill, resource_path):
    directory, _, tool = local_skill
    (directory.parent / "outside.md").write_text("Outside package.", encoding="utf-8")
    result = tool.execute(operation="read_resource", skill_name="sample", resource_path=resource_path)
    assert not result.success


def test_resource_chunks_reconstruct_utf8_text_and_preserve_offsets(local_skill):
    directory, _, tool = local_skill
    body = "中文参考资源\n" * 100
    (directory / "reference.md").write_bytes(body.encode("utf-8-sig"))
    chunks = []
    offset = 0
    while True:
        result = tool.execute(
            operation="read_resource", skill_name="sample", resource_path="reference.md",
            body_offset=offset, max_body_chars=200,
        )
        assert result.success
        assert result.data["body_offset"] == offset
        chunks.append(result.data["body"])
        if result.data["complete"]:
            assert result.data["next_body_offset"] is None
            break
        assert result.data["next_body_offset"] > offset
        offset = result.data["next_body_offset"]
    assert "".join(chunks) == body


@pytest.mark.parametrize(
    "content", [b"binary\x00data", b"\xff\xfe", b"a" * (2 * 1024 * 1024 + 1)],
    ids=["binary", "invalid-utf8", "oversized"],
)
def test_resource_rejects_binary_invalid_utf8_and_oversized_files(local_skill, content):
    directory, _, tool = local_skill
    (directory / "reference").write_bytes(content)
    assert not tool.execute(operation="read_resource", skill_name="sample", resource_path="reference").success


def test_resource_rejects_absolute_and_symlink_escape(local_skill):
    directory, _, tool = local_skill
    outside = directory.parent / "outside.md"
    outside.write_text("Outside package.", encoding="utf-8")
    assert not tool.execute(operation="read_resource", skill_name="sample", resource_path=str(outside)).success
    try:
        (directory / "escape.md").symlink_to(outside)
    except OSError:
        pytest.skip("Creating symbolic links is unavailable on this host")
    assert not tool.execute(operation="read_resource", skill_name="sample", resource_path="escape.md").success


def test_nested_builtin_references_are_not_git_ignored():
    root = Path(__file__).resolve().parents[2]
    paths = sorted(
        path.relative_to(root).as_posix()
        for path in (root / "ReverieCli-py/reverie/builtin_skills").rglob("*")
        if path.is_file() and "references" in path.parts
    )
    result = subprocess.run(
        ["git", "check-ignore", "--no-index", "-z", "--stdin"], cwd=root,
        input=("\0".join(paths) + "\0").encode("utf-8"), capture_output=True,
    )
    assert result.returncode == 1, result.stdout.decode("utf-8", errors="replace")


def test_photo_to_3d_requests_input_through_an_available_tool(local_skill):
    _, manager, _ = local_skill
    body = manager.get_record("photo-to-3d").body
    tools = {tool.name for tool in get_tool_classes_for_mode("reverie")}
    assert "userInput" in tools and "`userInput`" in body
    assert "`ask_clarification`" not in body


def test_builtin_reverse_skill_is_one_discoverable_package(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    manager = SkillsManager(tmp_path / "project", tmp_path / "app")
    record = manager.get_record("reverse-skill")
    assert record is not None and record.root.scope == "builtin"
    assert len([item for item in manager.get_snapshot().records if record.skill_dir in item.path_to_skill_md.parents]) == 1
    assert manager.resolve_explicit_mentions("$reverse-skill")["records"] == [record]
    assert "reverse-skill" in manager.describe_for_prompt()
    for relative in ("skills/config/routing.json", "skills/scripts/master-route.ps1", "skills/scripts/master-route.sh",
                     "skills/ida-reverse/SKILL.md", "skills/js-reverse/SKILL.md", "skills/apk-reverse/SKILL.md",
                     "LICENSE", "CTF-Sandbox-Orchestrator/LICENSE"):
        assert (record.skill_dir / "upstream" / relative).is_file(), relative


def test_skill_resources_are_chunked_and_confined_to_package(tmp_path, monkeypatch):
    from reverie.tools.skill_lookup import SkillLookupTool
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    manager = SkillsManager(tmp_path / "project", tmp_path / "app")
    tool = SkillLookupTool({"skills_manager": manager})
    result = tool.execute(operation="read_resource", skill_name="reverse-skill",
                          resource_path="upstream/skills/ida-reverse/SKILL.md", max_body_chars=200)
    assert result.success and not result.data["complete"]
    assert result.data["next_body_offset"] == 200
    next_chunk = tool.execute(operation="read_resource", skill_name="reverse-skill",
                             resource_path="upstream/skills/ida-reverse/SKILL.md", body_offset=200, max_body_chars=200)
    assert next_chunk.success and next_chunk.data["body"] != result.data["body"]
    assert not tool.execute(operation="read_resource", skill_name="reverse-skill",
                            resource_path="../../skills_manager.py").success
    assert not tool.execute(operation="read_resource", skill_name="reverse-skill",
                            resource_path=str(manager.get_record("reverse-skill").path_to_skill_md)).success
