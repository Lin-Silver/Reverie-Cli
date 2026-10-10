"""The public documentation gate must work without ignored local materials."""

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "reverie_documentation_check", ROOT / "scripts/verification/check_docs.py"
)
CHECKER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECKER)


def public_checkout(tmp_path):
    names = (
        "README.md", "SECURITY.md", "ReverieCli-py/README.md",
        "ReverieCli-ui/README.md", "plugins/README.md",
        "plugins/blender/README.md", "plugins/game_models/README.md",
        "docs/README.md", "docs/VERIFICATION_HISTORY.md",
    )
    for name in names:
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("# Documentation\n", encoding="utf-8")
    return tmp_path


def test_public_checkout_does_not_require_ignored_api_document(tmp_path):
    root = public_checkout(tmp_path)
    report = CHECKER.check(CHECKER.default_paths(root), root)
    assert not (root / "API.md").exists()
    assert report["errors"] == []


def test_gate_checks_subproject_links_to_migrated_history(tmp_path):
    root = public_checkout(tmp_path)
    history = root / "docs/VERIFICATION_HISTORY.md"
    history.write_text('<a id="old-report"></a>\n\n# History\n', encoding="utf-8")
    readme = root / "ReverieCli-py/README.md"
    readme.write_text(
        "[Report](../docs/VERIFICATION_HISTORY.md#old-report)\n",
        encoding="utf-8",
    )
    assert CHECKER.check(CHECKER.default_paths(root), root)["errors"] == []
    history.write_text("# History\n", encoding="utf-8")
    report = CHECKER.check(CHECKER.default_paths(root), root)
    assert report["errors"] == [{
        "source": "ReverieCli-py/README.md", "line": 1,
        "target": "../docs/VERIFICATION_HISTORY.md#old-report",
        "reason": "missing heading anchor",
    }]


def test_present_local_api_document_is_still_checked(tmp_path):
    root = public_checkout(tmp_path)
    (root / "API.md").write_text("[Missing](missing-local-file.md)\n", encoding="utf-8")
    report = CHECKER.check(CHECKER.default_paths(root), root)
    assert report["errors"][0]["source"] == "API.md"
    assert report["errors"][0]["reason"] == "missing file"
