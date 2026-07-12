from __future__ import annotations

from dataclasses import dataclass
import ast
import logging
from pathlib import Path
import sys

from rich.console import Console

from reverie.cli.session_ui import SessionUI
from reverie.cli.tui_selector import SelectorAction, SelectorItem, SelectorResult
from reverie.context_engine import ContextPackage as LegacyRetrievedContextPackage
from reverie.context_engine import RetrievedContextPackage
from reverie.diagnostics import report_suppressed_exception
from reverie.engine import EngineRuntimeProfile, RuntimeProfile as LegacyEngineRuntimeProfile
from reverie.gamer.runtime_adapters import RuntimeAdapterProfile, RuntimeProfile as LegacyAdapterProfile
from reverie.memory import ContextPackage as LegacyMemoryContextPackage
from reverie.memory import MemoryContextPackage
from scripts.smoke_sdk_bridge import verify_sdk_bridge


@dataclass
class _SessionInfo:
    id: str
    name: str
    created_at: str
    updated_at: str
    message_count: int


class _SessionManager:
    def __init__(self, sessions: list[_SessionInfo]) -> None:
        self.sessions = sessions

    def list_sessions(self) -> list[_SessionInfo]:
        return list(self.sessions)

    def get_current_session(self):
        return None


def test_session_ui_returns_selected_session_id(monkeypatch) -> None:
    manager = _SessionManager([_SessionInfo("session-1", "First", "now", "now", 3)])

    def fake_run(_selector):
        return SelectorResult(SelectorAction.SELECT, SelectorItem("session-1", "First"))

    monkeypatch.setattr("reverie.cli.session_ui.SessionSelector.run", fake_run)
    assert SessionUI(Console(), manager).show_selector() == "session-1"


def test_session_ui_handles_empty_workspace() -> None:
    assert SessionUI(Console(), _SessionManager([])).show_selector() is None


def test_domain_specific_type_names_keep_compatibility_aliases() -> None:
    assert LegacyRetrievedContextPackage is RetrievedContextPackage
    assert LegacyMemoryContextPackage is MemoryContextPackage
    assert LegacyEngineRuntimeProfile is EngineRuntimeProfile
    assert LegacyAdapterProfile is RuntimeAdapterProfile


def test_recoverable_exception_is_observable(caplog) -> None:
    with caplog.at_level(logging.DEBUG, logger="reverie.recovery"):
        try:
            raise RuntimeError("diagnostic sentinel")
        except RuntimeError:
            report_suppressed_exception("test recovery")
    assert "Recoverable operation failed: test recovery" in caplog.text
    assert "diagnostic sentinel" in caplog.text


def test_source_sdk_bridge_ready_shutdown_contract() -> None:
    messages = verify_sdk_bridge([sys.executable, "-m", "reverie", "--sdk-bridge"], timeout=20)
    assert [message["type"] for message in messages] == ["ready", "shutdown"]


def test_modules_do_not_silently_swallow_broad_exceptions() -> None:
    package_root = Path(__file__).resolve().parents[1] / "reverie"
    offenders: list[str] = []
    for path in package_root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ExceptHandler) or len(node.body) != 1 or not isinstance(node.body[0], ast.Pass):
                continue
            if node.type is None or (isinstance(node.type, ast.Name) and node.type.id in {"Exception", "BaseException"}):
                offenders.append(f"{path.relative_to(package_root)}:{node.lineno}")
    assert offenders == []


def test_ci_covers_cross_platform_tests_and_packaged_bridge_contract() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    test_workflow = (repo_root / ".github" / "workflows" / "test.yml").read_text(encoding="utf-8")
    build_workflow = (repo_root / ".github" / "workflows" / "build-windows-exe.yml").read_text(encoding="utf-8")
    assert "ubuntu-latest" in test_workflow
    assert "windows-latest" in test_workflow
    assert 'python-version: ["3.10", "3.12"]' in test_workflow
    assert "python -m pytest -q" in test_workflow
    assert "scripts/smoke_sdk_bridge.py" in test_workflow
    assert "scripts\\smoke_sdk_bridge.py --executable .\\dist\\reverie.exe" in build_workflow
