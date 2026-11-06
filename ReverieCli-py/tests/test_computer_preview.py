from pathlib import Path

import pytest
from PIL import Image

from reverie.computer_use.preview import resolve_image
from reverie.config import get_computer_controller_data_dir, get_project_data_dir


@pytest.mark.parametrize('dedicated', [False, True])
def test_generated_image_can_be_previewed_without_general_file_access(tmp_path, monkeypatch, dedicated):
    monkeypatch.setenv('REVERIE_APP_ROOT', str(tmp_path / 'profile'))
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    root = get_computer_controller_data_dir() if dedicated else get_project_data_dir(workspace)
    target = root / 'computer_use/observations/img-test.png'
    target.parent.mkdir(parents=True)
    Image.new('RGB', (16, 16)).save(target)
    assert resolve_image(workspace, str(target)) == target.resolve()


def test_other_external_images_are_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv('REVERIE_APP_ROOT', str(tmp_path / 'profile'))
    target = tmp_path / 'private.png'
    Image.new('RGB', (16, 16)).save(target)
    with pytest.raises(ValueError, match='Only generated'):
        resolve_image(tmp_path, str(target))


def test_extension_does_not_grant_arbitrary_file_preview(tmp_path, monkeypatch):
    monkeypatch.setenv('REVERIE_APP_ROOT', str(tmp_path / 'profile'))
    target = get_computer_controller_data_dir() / 'computer_use/observations/secret.png'
    target.parent.mkdir(parents=True)
    target.write_text('not an image')
    with pytest.raises(OSError):
        resolve_image(tmp_path, str(target))
