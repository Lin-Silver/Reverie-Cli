"""Verify the tested directory package contains the current compiled UI and core."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

from PyInstaller.archive.readers import CArchiveReader

ROOT = Path(__file__).resolve().parents[2]


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, default=ROOT / "ReverieCli-ui/release/win-unpacked")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--module", action="append", default=[], help="Additional reverie module to compare with the shipped frozen code.")
    args = parser.parse_args()
    package = args.package.resolve()
    output = args.output.resolve()
    if not output.is_relative_to(ROOT): raise ValueError("Evidence must stay in the repository.")
    archive = CArchiveReader(str(package / "reverie.exe")).open_embedded_archive("PYZ.pyz")
    modules = []
    for name in dict.fromkeys(["mcp", "mcp_apps", "views", "view_execution", "tools.mcp_dynamic", "agent.tool_executor", "sdk_bridge", *args.module]):
        frozen = archive.extract("reverie." + name)
        source = ROOT / "ReverieCli-py/reverie" / (name.replace(".", "/") + ".py")
        compiled = compile(source.read_bytes(), frozen.co_filename, "exec", dont_inherit=True, optimize=0)
        # Code equality compares executable code, constants and nested functions;
        # marshal bytes also encode interning choices and are not a useful test.
        modules.append({"module": "reverie." + name, "matches_current_source": frozen == compiled, "source_sha256": sha256(source)})
    script = r"""
const {extractFile}=require('@electron/asar');const fs=require('node:fs');const path=require('node:path');
const asar=process.argv[1],root=process.argv[2],results=[];
function check(dir){for(const entry of fs.readdirSync(path.join(root,dir),{withFileTypes:true})){const file=path.join(dir,entry.name);if(entry.isDirectory())check(file);else if(entry.isFile()){const saved=extractFile(asar,file),built=fs.readFileSync(path.join(root,file));results.push({file:file.replaceAll('\\','/'),matches:saved.equals(built)});}}}
check('dist');check('dist-electron');
const build=JSON.parse(extractFile(asar,'dist-electron/reverie-build.json'));
const trusted=JSON.parse(extractFile(asar,path.join('build','generated','reverie-trusted-kernels.json')));
process.stdout.write(JSON.stringify({files:results,build,trusted}));
"""
    ui = ROOT / "ReverieCli-ui"
    result = subprocess.run([shutil.which("node"), "-e", script, str(package / "resources/app.asar"), str(ui)], cwd=ui, capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(result.stderr[:3000])
    ui_evidence = json.loads(result.stdout)
    manifest = ROOT / "ReverieCli-py/reverie/agent/tool_manifest.json"
    shipped_manifest = package / "reverie-runtime/reverie/agent/tool_manifest.json"
    data_files = [{"file": "reverie/agent/tool_manifest.json", "matches_current_source": shipped_manifest.read_bytes() == manifest.read_bytes(), "source_sha256": sha256(manifest)}]
    files = [{"path": str(package / name), "bytes": (package / name).stat().st_size, "sha256": sha256(package / name)} for name in ("ReverieUI.exe", "reverie.exe", "resources/app.asar")]
    report = {"passed": all(item["matches_current_source"] for item in modules + data_files) and all(item["matches"] for item in ui_evidence["files"]), "frozen_modules": modules, "data_files": data_files, "ui": ui_evidence, "artifacts": files}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"passed": report["passed"], "build": ui_evidence["build"], "modules": len(modules), "ui_files": len(ui_evidence["files"]), "output": str(output)}))
    if not report["passed"]: raise SystemExit(1)


if __name__ == "__main__": main()
