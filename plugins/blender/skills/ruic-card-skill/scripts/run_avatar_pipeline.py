"""Build an editable 2D portrait avatar and an offline browser/OBS viewer."""

from pathlib import Path
import argparse
import os
import subprocess

from ensure_blender import ensure_blender


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    parser.add_argument("--blender")
    args = parser.parse_args()
    root = Path(args.project).resolve()
    scripts = Path(__file__).resolve().parent
    skill = scripts.parent
    if not (root / "avatar-config.json").is_file():
        raise FileNotFoundError("Write avatar-config.json with the portrait's actual eye and mouth coordinates first")
    blender = ensure_blender(root, args.blender)
    env = os.environ.copy()
    plugin = Path(env.get("REVERIE_BLENDER_PLUGIN_ROOT") or env.get("REVERIE_PLUGIN_ROOT") or skill.parents[1]).resolve()
    for key, folder in (("BLENDER_USER_CONFIG", "config"), ("BLENDER_USER_SCRIPTS", "scripts"),
                        ("BLENDER_USER_DATAFILES", "datafiles")):
        location = plugin / folder
        location.mkdir(parents=True, exist_ok=True)
        env[key] = str(location)
    subprocess.run([str(blender), "--background", "--factory-startup", "--python-exit-code", "23",
                    "--python", str(scripts / "build_avatar.py"), "--", str(root)], check=True, env=env)
    if not (root / "avatar.blend").is_file() or not (root / "web/avatar.json").is_file():
        raise RuntimeError("The avatar build did not produce its editable scene and viewer manifest")
    print("Completed:", root / "avatar.blend")
    print("Preview: node", root / "web/server.mjs")
    print("OBS browser source: append ?obs=1 to the local viewer URL")


if __name__ == "__main__":
    main()
