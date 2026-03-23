import os
import base64
import zipfile
import io
import pathlib

root = pathlib.Path('ComfyUI-master')
mem = io.BytesIO()
z = zipfile.ZipFile(mem, 'w', zipfile.ZIP_DEFLATED)
dirs = set()

def should_skip(path: pathlib.Path) -> bool:
    parts = path.parts
    skip_names = {'.git', '__pycache__', '.venv', 'venv', '.gitignore', '.gitattributes'}
    return any(p in skip_names for p in parts)

# Include all files under ComfyUI-master (to keep tokenizers, configs, etc.)
for dirpath, dirnames, files in os.walk(root):
    dirpath = pathlib.Path(dirpath)
    if should_skip(dirpath):
        continue
    rel_dir = dirpath.relative_to(root)
    if str(rel_dir) != '.':
        dirs.add(rel_dir)
    # filter dirnames in-place to skip __pycache__ etc.
    dirnames[:] = [d for d in dirnames if not should_skip(dirpath / d)]
    for f in files:
        full = dirpath / f
        if should_skip(full):
            continue
        rel = full.relative_to(root)
        z.write(full, arcname=str(rel).replace('\\', '/'))

# ensure __init__.py for all dirs inside comfy package
for d in dirs:
    if d.parts[0] != 'comfy':
        continue
    init_path = d / '__init__.py'
    arc = str(init_path).replace('\\', '/')
    if arc not in z.namelist():
        z.writestr(arc, '')

# top-level package init
if 'comfy/__init__.py' not in z.namelist():
    z.writestr('comfy/__init__.py', '')

z.close()
mem.seek(0)
pathlib.Path('embedded_comfy.b64').write_text(base64.b64encode(mem.read()).decode())
print('rebuilt embedded_comfy.b64 with', len(z.namelist()), 'entries')
