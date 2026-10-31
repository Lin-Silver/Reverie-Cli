"""Exercise the actual publication shell without contacting GitHub."""
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("existing,fail_upload", [(True, False), (False, False), (False, True)])
def test_stable_notes_and_publication_after_successful_uploads(tmp_path, existing, fail_upload):
    bash = "C:/Program Files/Git/bin/bash.exe" if os.name == "nt" else shutil.which("bash")
    if not bash or not Path(bash).is_file():
        pytest.skip("Bash is required to exercise the release workflow")
    workflow = yaml.safe_load((ROOT / ".github/workflows/build-core-release.yml").read_text(encoding="utf-8"))
    step = next(s for s in workflow["jobs"]["publish"]["steps"] if s.get("name") == "Publish verified assets")
    notes = tmp_path / "docs/releases/v2.5.3.md"
    notes.parent.mkdir(parents=True)
    notes.write_text("# Reverie v2.5.3\n\n- A concise verified change.\n", encoding="utf-8")
    log = tmp_path / "calls.jsonl"
    stub = tmp_path / "github_stub.py"
    stub.write_text('''import json, os, sys
from pathlib import Path
args = sys.argv[1:]
entry = {"args": args}
if "--notes-file" in args:
    entry["notes"] = Path(args[args.index("--notes-file")+1]).read_text()
with Path(os.environ["PUBLICATION_LOG"]).open("a") as stream:
    stream.write(json.dumps(entry)+"\\n")
if args[:2] == ["release", "view"]:
    if "--json" in args:
        print("retired-old.zip")
    elif os.environ["EXISTING_RELEASE"] == "0":
        sys.exit(1)
elif args[:2] == ["release", "upload"]:
    if os.environ["FAIL_UPLOAD"] == "1" and "linux-x64.AppImage" in args[3]:
        sys.exit(17)
elif args[0] == "api" and "--method" not in args:
    print("42")
''', encoding="utf-8")
    interpreter = shlex.quote(Path(sys.executable).as_posix())
    stub_arg = shlex.quote(stub.as_posix())
    script = f'gh() {{ {interpreter} {stub_arg} "$@"; }}\nnode() {{ echo 2.5.3; }}\n' + step["run"]
    result = subprocess.run([bash, "-s"], input=script, text=True, capture_output=True, cwd=tmp_path,
        env={**os.environ, "RUNNER_TEMP": tmp_path.as_posix(), "GITHUB_REF_TYPE": "tag",
             "GITHUB_REF_NAME": "v2.5.3", "GITHUB_SHA": "a" * 40,
             "GITHUB_REPOSITORY": "example/reverie", "PUBLICATION_LOG": log.as_posix(),
             "EXISTING_RELEASE": str(int(existing)), "FAIL_UPLOAD": str(int(fail_upload))})
    calls = [json.loads(line) for line in log.read_text().splitlines()]
    note_call = next(c for c in calls if "--notes-file" in c["args"])
    assert note_call["notes"].strip() == "- A concise verified change."
    if not existing:
        assert "--draft" in note_call["args"]
    public = [i for i, c in enumerate(calls) if "draft=false" in c["args"]]
    if fail_upload:
        assert result.returncode == 17, result.stderr
        assert not public
    else:
        assert result.returncode == 0, result.stderr
        uploads = [i for i, c in enumerate(calls) if c["args"][:2] == ["release", "upload"]]
        assert len(uploads) == 11
        assert len(public) == 1 and public[0] > max(uploads)
