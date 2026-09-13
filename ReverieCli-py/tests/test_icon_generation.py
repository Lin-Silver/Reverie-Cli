from pathlib import Path

from PIL import Image

from scripts.generate_reverie_icons import ICO_SIZES, generate_icon


def test_reverie_ico_contains_every_supported_windows_size(tmp_path: Path) -> None:
    source = tmp_path / "reverie.png"
    output = tmp_path / "reverie.ico"
    Image.new("RGBA", (512, 512), (112, 68, 255, 255)).save(source)

    generate_icon(source, output)

    with Image.open(output) as icon:
        assert icon.format == "ICO"
        assert icon.ico.sizes() == set(ICO_SIZES)
