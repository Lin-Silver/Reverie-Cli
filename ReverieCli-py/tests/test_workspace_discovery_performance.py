"""Workspace discovery must spend its scan budget on source projects."""

from reverie.context_engine import workspace


def test_workspace_discovery_keeps_source_boundaries_and_focused_instructions(tmp_path):
    python_project = tmp_path / "packages" / "backend"
    ui_project = tmp_path / "packages" / "frontend"
    python_project.mkdir(parents=True)
    ui_project.mkdir(parents=True)
    (python_project / "pyproject.toml").write_text("[project]\nname='fixture'\n", encoding="utf-8")
    (ui_project / "package.json").write_text("{}", encoding="utf-8")
    (tmp_path / "AGENTS.md").write_text("Keep source changes scoped.", encoding="utf-8")
    (python_project / "AGENTS.md").write_text("Verify the Python kernel.", encoding="utf-8")
    for ignored in (".runtime", ".kernel", ".cache", "release"):
        for index in range(16):
            cached = tmp_path / ignored / f"package-{index}"
            cached.mkdir(parents=True)
            (cached / "Cargo.toml").write_text("[package]\nname='cached'\n", encoding="utf-8")

    profile = workspace.detect_workspace_profile(tmp_path, focus_files=[str(python_project / "main.py")])
    roots = {boundary.root for boundary in profile.project_boundaries}
    assert roots == {str(python_project), str(ui_project)}
    instructions = {layer.path: layer.excerpt for layer in profile.instruction_layers}
    assert instructions[str(tmp_path / "AGENTS.md")] == "Keep source changes scoped."
    assert instructions[str(python_project / "AGENTS.md")] == "Verify the Python kernel."


def test_workspace_scan_budget_bounds_empty_directories(tmp_path, monkeypatch):
    for index in range(50):
        (tmp_path / f"empty-{index}").mkdir()
    visited = []
    original = workspace.os.walk

    def walk(*args, **kwargs):
        for entry in original(*args, **kwargs):
            visited.append(entry[0])
            yield entry

    monkeypatch.setattr(workspace.os, "walk", walk)
    workspace.detect_workspace_profile(tmp_path, max_scan_entries=5)
    assert len(visited) <= 6
