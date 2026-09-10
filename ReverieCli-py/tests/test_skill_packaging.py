"""Both distribution paths retain nested references and omit local artifacts."""

import ast
from pathlib import Path
import runpy
import shutil

import setuptools
import pytest


@pytest.mark.parametrize("parent_name", ["checkout", "reports/checkout"])
def test_skill_package_data_excludes_reports_and_caches(tmp_path, monkeypatch, parent_name):
    source = Path(__file__).resolve().parents[1]
    tmp_path = tmp_path / parent_name
    skill_root = tmp_path / "reverie" / "builtin_skills"
    resources = {
        "example/SKILL.md", "example/upstream/references/workflow.md", "example/upstream/LICENSE",
    }
    artifacts = {
        "example/upstream/reports/local.md", "example/__pycache__/module.pyc",
        "example/.pytest_cache/README.md", "example/.mypy_cache/state.json",
        "example/.ruff_cache/state", "example/cache.pyo",
    }
    for name in resources | artifacts:
        path = skill_root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("Fixture.", encoding="utf-8")
    shutil.copy2(source / "setup.py", tmp_path / "setup.py")
    shutil.copy2(source / "reverie/version.py", tmp_path / "reverie/version.py")
    metadata = {}
    monkeypatch.setattr(setuptools, "setup", lambda **kwargs: metadata.update(kwargs))
    runpy.run_path(str(tmp_path / "setup.py"))
    files = {name.removeprefix("builtin_skills/") for name in metadata["package_data"]["reverie"] if name.startswith("builtin_skills/")}
    assert files == resources

    # Execute the spec's collector and its real Skills call without launching a
    # PyInstaller build or requiring bundled Chromium/Comfy resources.
    spec = ast.parse((source / "reverie.spec").read_text(encoding="utf-8"))
    nodes = [node for node in spec.body if isinstance(node, ast.FunctionDef) and node.name == "add_tree_if_exists"]
    nodes += [
        node for node in spec.body
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Name) and node.value.func.id == "add_tree_if_exists"
        and "builtin_skills" in ast.unparse(node)
    ]
    assert len(nodes) == 2
    namespace = {"Path": Path, "repo_root": tmp_path, "datas": []}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "reverie.spec", "exec"), namespace)
    assert {Path(name).relative_to(skill_root).as_posix() for name, _ in namespace["datas"]} == resources
