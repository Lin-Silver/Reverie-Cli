"""Novel memory must survive a save/load round trip on a non-UTF-8 locale.

``_save_to_disk`` serializes with ``ensure_ascii=False`` and ``_load_from_disk``
decodes as UTF-8, so writing through the platform's locale codec corrupted every
non-ASCII character name the moment the default encoding was not UTF-8 -- which
is the Windows default.
"""

from __future__ import annotations

from pathlib import Path

from reverie.writer.novel_memory import Character, Location, NovelMemorySystem, Theme


def _seed(storage_dir: Path) -> NovelMemorySystem:
    memory = NovelMemorySystem("round-trip", storage_dir=storage_dir)
    memory.add_character(
        Character(
            name="林清雪",
            description="剑客，来自北境的雪原",
            first_appearance_chapter=1,
            traits=["沉默", "坚韧"],
            relationships={"沈墨": "师兄"},
            development_arc="从复仇走向宽恕",
            last_appearance_chapter=3,
            is_protagonist=True,
            background="雪原孤儿",
        )
    )
    memory.add_location(
        Location(
            name="寒山寺",
            description="山巅的古寺",
            first_appearance_chapter=2,
            connections=["北境"],
            significance="转折点",
            atmosphere="肃穆",
            last_appearance_chapter=2,
        )
    )
    memory.add_theme(
        Theme(
            name="宽恕",
            description="复仇的代价",
            appearances=[1, 3],
            variations=["自我宽恕"],
            symbol="落雪",
        )
    )
    return memory


def test_non_ascii_memory_survives_a_save_and_reload(tmp_path: Path) -> None:
    _seed(tmp_path / "novel").save()

    reloaded = NovelMemorySystem("round-trip", storage_dir=tmp_path / "novel")

    assert list(reloaded.characters) == ["林清雪"]
    character = reloaded.characters["林清雪"]
    assert character.description == "剑客，来自北境的雪原"
    assert character.relationships == {"沈墨": "师兄"}
    assert reloaded.locations["寒山寺"].description == "山巅的古寺"
    assert reloaded.themes["宽恕"].symbol == "落雪"


def test_memory_is_persisted_as_utf8_regardless_of_the_platform_locale(tmp_path: Path) -> None:
    storage = tmp_path / "novel"
    _seed(storage).save()

    for name in ("characters.json", "locations.json", "themes.json", "metadata.json"):
        raw = (storage / name).read_bytes()
        # Decoding as UTF-8 is what _load_from_disk does; a locale-encoded write
        # raises here instead of returning the text that was stored.
        raw.decode("utf-8")
    assert "林清雪" in (storage / "characters.json").read_text(encoding="utf-8")
