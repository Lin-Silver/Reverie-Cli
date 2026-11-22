from __future__ import annotations

from pathlib import Path
import re
from types import SimpleNamespace

import pytest


@pytest.mark.parametrize(
    "event,ref,publish_request,core_allowed,plugins_allowed",
    [
        ("push", "refs/heads/main", False, False, True),
        ("workflow_dispatch", "refs/heads/main", False, False, True),
        ("workflow_dispatch", "refs/heads/main", True, True, True),
        ("pull_request", "refs/heads/main", True, False, False),
        ("push", "refs/heads/codex/python-2.5.5-pure", False, False, False),
        ("workflow_dispatch", "refs/heads/codex/python-2.5.5-pure", True, False, False),
        ("push", "refs/heads/codex/rust-3.0", False, False, False),
        ("workflow_dispatch", "refs/heads/codex/rust-3.0", True, False, False),
        ("push", "refs/heads/Reverie-Cli-py", False, False, False),
        ("workflow_dispatch", "refs/heads/Reverie-Cli-py", True, False, False),
        ("pull_request", "refs/pull/1/merge", True, False, False),
        ("push", "refs/tags/v2.5.5", False, True, False),
        ("workflow_dispatch", "refs/tags/v2.5.5", True, False, False),
        ("push", "refs/tags/latest", False, False, False),
        ("push", "refs/tags/plugins-latest", False, False, False),
        ("push", "refs/tags/history/python-2.5.5-hybrid", False, False, False),
    ],
)
def test_release_jobs_reject_development_and_archive_sources(
    event: str, ref: str, publish_request: bool, core_allowed: bool, plugins_allowed: bool,
) -> None:
    workflows = Path(__file__).resolve().parents[2] / ".github" / "workflows"
    for filename, allowed in (
        ("build-core-release.yml", core_allowed),
        ("build-plugins.yml", plugins_allowed),
    ):
        workflow = (workflows / filename).read_text(encoding="utf-8")
        before_publish, publish = workflow.split("\n  publish:\n", 1)
        assert "permissions:\n  contents: read" in before_publish
        assert "contents: write" not in before_publish
        assert "    needs: build\n" in publish
        assert "      contents: write\n" in publish
        expression = next(line.removeprefix("    if: ") for line in publish.splitlines() if line.startswith("    if: "))
        # Evaluate the actual job condition with the documented string/Boolean contexts.
        actual = eval(
            expression.replace("&&", " and ").replace("||", " or "),
            {"__builtins__": {}, "startsWith": str.startswith},
            {"github": SimpleNamespace(event_name=event, ref=ref), "inputs": SimpleNamespace(publish_release=publish_request)},
        )
        assert actual is allowed, (filename, event, ref, publish_request)


@pytest.mark.parametrize("tag,allowed", [("v2.5.5", True), ("v3.0.0", True), ("v03.0.0", False), ("v3.0", False), ("v3.0.0-rc.1", False), ("v3.0.0-extra", False)])
def test_core_tag_validation_preserves_version_and_source_checks(tag: str, allowed: bool) -> None:
    workflow = (Path(__file__).resolve().parents[2] / ".github" / "workflows" / "build-core-release.yml").read_text(encoding="utf-8")
    publish = workflow.split("\n  publish:\n", 1)[1]
    pattern = re.search(r'\[\[ "\$GITHUB_REF_NAME" =~ (\S+) \]\]', publish)
    assert pattern is not None
    assert (re.fullmatch(pattern.group(1), tag) is not None) is allowed
    assert 'test "$GITHUB_REF_TYPE" = tag' in publish
    assert 'test "$GITHUB_REF_NAME" = "v$version"' in publish
    assert 'test "$python_version" = "$version"' in publish
    assert 'git merge-base --is-ancestor "$GITHUB_SHA" origin/main' in publish
