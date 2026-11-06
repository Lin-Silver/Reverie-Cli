"""Resolve only generated desktop PNGs for the existing read-only file preview."""
from pathlib import Path

from ..config import get_computer_controller_data_dir, get_project_data_dir


def resolve_image(project_root: Path, file: str) -> Path:
    from PIL import Image
    target = Path(file).resolve(strict=True)
    roots = [get_project_data_dir(project_root) / 'computer_use',
             get_computer_controller_data_dir() / 'computer_use']
    if target.suffix.lower() != '.png' or not any(target.is_relative_to(root.resolve()) for root in roots):
        raise ValueError('Only generated Computer Use PNGs can be previewed outside the workspace.')
    if target.stat().st_size > 20 * 1024 * 1024:
        raise ValueError('Computer Use image exceeds the 20 MiB preview limit.')
    with Image.open(target) as image:
        if image.format != 'PNG':
            raise ValueError('Computer Use preview requires a PNG image.')
        image.verify()
    return target
