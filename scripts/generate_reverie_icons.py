from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image


ICO_SIZES = ((256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16))


def generate_icon(source: Path, output: Path) -> None:
    if not source.exists():
        raise FileNotFoundError(f"Missing icon source: {source}")

    output.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(source) as image:
        image.convert("RGBA").save(output, format="ICO", sizes=ICO_SIZES)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate Reverie .ico files from reverie.png.")
    parser.add_argument("--source", type=Path, default=Path("reverie.png"))
    parser.add_argument("outputs", nargs="+", type=Path)
    args = parser.parse_args()

    source = args.source.resolve()
    for output in args.outputs:
        generate_icon(source, output.resolve())
        print(f"Generated {output} from {source}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
