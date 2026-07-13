from reverie.cli.theme import DECO, THEME, apply_theme


def test_theme_presets_change_shared_palette_and_can_reset() -> None:
    apply_theme("default")
    default_primary = THEME.TEXT_PRIMARY
    default_border = THEME.BORDER_PRIMARY

    assert apply_theme("light") == "light"
    assert THEME.TEXT_PRIMARY != default_primary
    assert THEME.BORDER_PRIMARY != default_border

    assert apply_theme("default") == "default"
    assert THEME.TEXT_PRIMARY == default_primary
    assert THEME.BORDER_PRIMARY == default_border


def test_unknown_theme_falls_back_to_default() -> None:
    assert apply_theme("not-a-theme") == "default"


def test_accessibility_theme_presets_are_distinct() -> None:
    apply_theme("default")
    default_sparkle = DECO.SPARKLE
    apply_theme("high-contrast")
    assert THEME.TEXT_PRIMARY == "#ffffff"
    assert THEME.BORDER_PRIMARY == "#ffffff"
    apply_theme("minimal")
    assert THEME.BORDER_PRIMARY == "#666666"
    assert DECO.SPARKLE == ""
    apply_theme("default")
    assert DECO.SPARKLE == default_sparkle
