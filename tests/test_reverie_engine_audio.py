from pathlib import Path

from reverie.engine import AudioManager, AudioStream


def test_audio_bus_and_mixer_controls_shape_effective_volume(tmp_path: Path) -> None:
    manager = AudioManager(tmp_path)
    manager.streams["click"] = AudioStream(path="assets/audio/click.wav", source=object(), duration=0.25)

    player = manager.create_player("ui_click", "click", volume=0.8, category="ui")
    assert player is not None
    assert player.bus == "UI"

    assert manager.set_bus_volume("UI", 0.5) is True
    assert manager.get_effective_volume("ui_click") == 0.4

    assert manager.mute_bus("UI", True) is True
    assert manager.get_effective_volume("ui_click") == 0.0

    assert manager.mute_bus("UI", False) is True
    assert manager.solo_bus("Voice", True) is True
    assert manager.get_effective_volume("ui_click") == 0.0

    assert manager.solo_bus("Voice", False) is True
    snapshot = manager.mix_snapshot()
    assert snapshot["bus_count"] >= 6
    assert snapshot["active_players"]["ui_click"]["bus"] == "UI"
