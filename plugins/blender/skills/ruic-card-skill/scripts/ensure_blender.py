"""Use Reverie's existing portable Blender without project-local downloads."""
from pathlib import Path
import argparse,os,shutil


def find_blender(project,override=None):
    candidates=[]
    if override:
        candidate=Path(override).expanduser()
        return candidate.resolve() if candidate.is_file() else None
    env_executable=os.environ.get('BLENDER_EXECUTABLE')
    if env_executable:candidates.append(Path(env_executable))
    plugin_root=os.environ.get('REVERIE_BLENDER_PLUGIN_ROOT') or os.environ.get('REVERIE_PLUGIN_ROOT')
    if not plugin_root:
        package=Path(__file__).resolve().parents[2]
        if package.name=='skills':plugin_root=str(package.parent)
    if plugin_root:
        runtime=Path(plugin_root)/'runtime'
        candidates.extend(runtime.glob('**/blender.exe'))
        candidates.extend(runtime.glob('**/blender'))
        candidates.extend(runtime.glob('**/Blender.app/Contents/MacOS/Blender'))
    system=shutil.which('blender')
    if system:candidates.append(Path(system))
    for candidate in candidates:
        if candidate.is_file():return candidate.resolve()
    return None


def ensure_blender(project,override=None):
    executable=find_blender(project,override)
    if executable:return executable
    if override:raise FileNotFoundError('Specified Blender executable does not exist: '+str(override))
    raise RuntimeError('Deploy Blender with rc_blender_ensure_runtime and pass data.detected.path as --blender; Blender stays in the plugin runtime folder.')


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('project')
    parser.add_argument('--blender')
    args=parser.parse_args()
    print(ensure_blender(args.project,args.blender))
