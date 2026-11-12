from importlib import resources
import os
from pathlib import Path
import subprocess

import pytest

from reverie.writer.style_runtime import WStyleRuntime
from reverie.writer.wstyles import WStyleError, WStyleRepository


def test_six_complete_resources_install_inactive_and_survive_edits_and_deletion(tmp_path):
    runtime = WStyleRuntime(tmp_path / "workspace", app_root=tmp_path / "app")
    runtime.ensure_resources()
    cards = runtime.repository.list_cards()
    expected = {"delicate-prose", "dual-heroines", "ensemble-heroines", "gl-romance-beats", "isekai-subversion-comedy", "commercial-serial-engagement"}
    assert {card["id"] for card in cards} == expected and all(card["valid"] for card in cards)
    assert all(len(runtime.repository.get(card_id).body) > 600 for card_id in expected)
    assert runtime.selection()[0] == []
    path = runtime.repository.root / "delicate-prose.md"
    modified = path.read_text(encoding="utf-8") + "\n用户保留的修改。\n"
    path.write_text(modified, encoding="utf-8")
    removed = runtime.repository.root / "dual-heroines.md"
    removed.unlink()
    restored = WStyleRuntime(runtime.project_root, app_root=runtime.app_root)
    restored.ensure_resources()
    assert path.read_text(encoding="utf-8") == modified and not removed.exists()
    restored.set_selection(["delicate-prose", "gl-romance-beats"], global_scope=True)
    assert len(restored.composition().cards) == 2


@pytest.mark.skipif(os.name != "nt", reason="Windows junction semantics")
def test_real_windows_junction_is_rejected_without_following_it(tmp_path):
    target = tmp_path / "outside-cards"
    target.mkdir()
    repo = WStyleRepository(tmp_path / "app")
    repo.root.parent.mkdir(parents=True)
    env = {**os.environ, "WSTYLE_JUNCTION_PATH": str(repo.root), "WSTYLE_JUNCTION_TARGET": str(target)}
    result = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
                             "New-Item -ItemType Junction -Path $env:WSTYLE_JUNCTION_PATH -Target $env:WSTYLE_JUNCTION_TARGET | Out-Null"],
                            env=env, capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr
    with pytest.raises(WStyleError, match="reparse"):
        repo.list_cards()
    assert not list(target.iterdir())
