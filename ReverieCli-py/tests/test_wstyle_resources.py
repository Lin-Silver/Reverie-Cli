from importlib import resources
import os
from pathlib import Path
import stat

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
    import _winapi

    target = tmp_path / "outside-cards"
    target.mkdir()
    repo = WStyleRepository(tmp_path / "app")
    repo.root.parent.mkdir(parents=True)
    _winapi.CreateJunction(str(target), str(repo.root))
    assert repo.root.lstat().st_reparse_tag == stat.IO_REPARSE_TAG_MOUNT_POINT
    with pytest.raises(WStyleError, match="reparse"):
        repo.list_cards()
    assert not list(target.iterdir())
