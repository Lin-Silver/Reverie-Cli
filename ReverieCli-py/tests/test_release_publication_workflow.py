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


@pytest.mark.parametrize("event,ref,publish_requested,expected", [
    ("push", "refs/heads/main", False, False),
    ("push", "refs/tags/v2.5.5", False, True),
    ("push", "refs/tags/plugins-latest", False, False),
    ("pull_request", "refs/heads/main", False, False),
    ("workflow_dispatch", "refs/heads/main", False, False),
    ("workflow_dispatch", "refs/heads/main", True, True),
])
def test_publication_requires_a_version_tag_or_explicit_dispatch(event, ref, publish_requested, expected):
    from types import SimpleNamespace

    workflow = yaml.safe_load((ROOT / ".github/workflows/build-core-release.yml").read_text(encoding="utf-8"))
    expression = workflow["jobs"]["publish"]["if"].replace("&&", " and ").replace("||", " or ")
    allowed = eval(expression, {"__builtins__": {}, "startsWith": str.startswith}, {
        "github": SimpleNamespace(event_name=event, ref=ref),
        "inputs": SimpleNamespace(publish_release=publish_requested),
    })
    assert bool(allowed) is expected


@pytest.mark.parametrize("verdict,expected", [("success", True), ("failure", False),
                                             ("cancelled", False), ("missing", False)])
def test_publication_requires_successful_tests_for_the_same_source(tmp_path, verdict, expected):
    bash = "C:/Program Files/Git/bin/bash.exe" if os.name == "nt" else shutil.which("bash")
    if not bash or not Path(bash).is_file():
        pytest.skip("Bash is required to exercise the release workflow")
    workflow = yaml.safe_load((ROOT / ".github/workflows/build-core-release.yml").read_text(encoding="utf-8"))
    step = next(s for s in workflow["jobs"]["publish"]["steps"]
                if s.get("name") == "Require successful tests for the exact source")
    script = f"gh() {{ printf '%s\\n' {shlex.quote(verdict)}; }}\n" + step["run"]
    result = subprocess.run([bash, "-s"], input=script, text=True, capture_output=True,
                            cwd=tmp_path, timeout=10,
                            env={**os.environ, "GITHUB_SHA": "a" * 40, "GITHUB_REPOSITORY": "example/reverie"})
    assert (result.returncode == 0) is expected, result.stderr


@pytest.mark.parametrize("changed,native_passed", [(False, True), (True, True), (False, False)])
def test_native_release_gate_rejects_changed_assets_and_failed_runtime(tmp_path, changed, native_passed):
    import hashlib

    bash = "C:/Program Files/Git/bin/bash.exe" if os.name == "nt" else shutil.which("bash")
    if not bash or not Path(bash).is_file():
        pytest.skip("Bash is required to exercise the release workflow")
    workflow = yaml.safe_load((ROOT / ".github/workflows/build-core-release.yml").read_text(encoding="utf-8"))
    step = next(s for s in workflow["jobs"]["build"]["steps"]
                if s.get("name") == "Verify staged assets were not changed during native checks")
    assets = tmp_path / "release-assets"
    assets.mkdir()
    artifact = assets / "Reverie-Setup-2.5.3-x64.exe"
    artifact.write_bytes(b"tested release payload")
    evidence = tmp_path / ".runtime/riu-package-native"
    evidence.mkdir(parents=True)
    (evidence / "report.json").write_text(json.dumps({"passed": native_passed}))
    (evidence.parent / "release-native-provenance.json").write_text(json.dumps({
        "assets": {artifact.name: hashlib.sha256(artifact.read_bytes()).hexdigest()},
    }))
    if changed:
        artifact.write_bytes(b"replacement after native verification")
    result = subprocess.run([bash, "-s"], input=step["run"], text=True, capture_output=True,
                            cwd=tmp_path, env={**os.environ, "PATH": str(Path(sys.executable).parent) + os.pathsep + os.environ["PATH"]})
    assert (result.returncode == 0) == (not changed and native_passed), result.stderr


@pytest.mark.parametrize("existing,fail_upload,release_ids,created_id,identity_fault", [
    (True, False, "42", "42", "none"), (False, False, "42", "42", "none"),
    (False, True, "42", "42", "none"),
    (True, False, "", "42", "none"), (True, False, "42\n43", "42", "none"),
    (False, False, "", "42", "none"),
    (False, False, "", "", "none"), (False, False, "", "null", "none"),
    (False, False, "", "42\n43", "none"),
    *[(False, False, "", "42", fault) for fault in
      ("tag", "source", "public", "prerelease", "missing_asset", "extra_asset")],
])
def test_stable_notes_and_draft_after_successful_uploads(tmp_path, existing, fail_upload, release_ids, created_id, identity_fault):
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
    entry["notes"] = Path(args[args.index("--notes-file")+1]).read_text(encoding="utf-8")
for argument in args:
    if argument.startswith("body=@"):
        entry["notes"] = Path(argument.removeprefix("body=@")).read_text(encoding="utf-8")
with Path(os.environ["PUBLICATION_LOG"]).open("a") as stream:
    stream.write(json.dumps(entry)+"\\n")
if args[:2] == ["release", "view"]:
    if "--json" in args:
        if args[args.index("--json")+1] == "databaseId":
            if os.environ["EXISTING_RELEASE"] == "0":
                sys.exit(1)
            print(os.environ["RELEASE_IDS"])
        else:
            print("retired-old.zip")
    elif os.environ["EXISTING_RELEASE"] == "0":
        sys.exit(1)
elif args[:2] == ["release", "upload"]:
    if os.environ["FAIL_UPLOAD"] == "1" and "linux-x64.AppImage" in args[3]:
        sys.exit(17)
elif args[0] == "api" and "--method" in args:
    if args[args.index("--method")+1] == "POST":
        assert "repos/example/reverie/releases" in args
        assert "tag_name=v2.5.3" in args and "draft=true" in args
        assert "target_commitish=" + "a" * 40 in args
        assert "make_latest=false" in args and "prerelease=false" in args
        assert args[args.index("--jq")+1] == ".id"
        print(os.environ["CREATED_ID"])
elif args[0] == "api":
    if "/releases/tags/" in args[1]:
        sys.exit(22)
    if args[1] == "repos/example/reverie/releases/42":
        fields = ["v2.5.3", "a" * 40, "true", "false", "17"]
        changes = {"tag": (0, "untagged-test"), "source": (1, "b" * 40),
                   "public": (2, "false"), "prerelease": (3, "true"),
                   "missing_asset": (4, "16"), "extra_asset": (4, "18")}
        if os.environ["IDENTITY_FAULT"] in changes:
            index, value = changes[os.environ["IDENTITY_FAULT"]]
            fields[index] = value
        print("\t".join(fields))
    else:
        assert args[1] == "repos/example/reverie/releases?per_page=100"
        assert "--paginate" in args
        assert args[args.index("--jq")+1] == '.[] | select(.tag_name == "v2.5.3") | .id'
        print(os.environ["RELEASE_IDS"])
''', encoding="utf-8")
    interpreter = shlex.quote(Path(sys.executable).as_posix())
    stub_arg = shlex.quote(stub.as_posix())
    script = f'gh() {{ {interpreter} {stub_arg} "$@"; }}\nnode() {{ echo 2.5.3; }}\n' + step["run"]
    result = subprocess.run([bash, "-s"], input=script, text=True, capture_output=True, cwd=tmp_path,
        env={**os.environ, "RUNNER_TEMP": tmp_path.as_posix(), "GITHUB_REF_TYPE": "tag",
             "GITHUB_REF_NAME": "v2.5.3", "GITHUB_SHA": "a" * 40,
             "GITHUB_REPOSITORY": "example/reverie", "PUBLICATION_LOG": log.as_posix(),
             "EXISTING_RELEASE": str(int(existing)), "FAIL_UPLOAD": str(int(fail_upload)),
             "RELEASE_IDS": release_ids, "CREATED_ID": created_id,
             "IDENTITY_FAULT": identity_fault})
    calls = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
    valid_id = release_ids == "42" if existing else created_id == "42"
    note_calls = [c for c in calls if "notes" in c]
    if valid_id or not existing:
        assert len(note_calls) == 1
        note_call = note_calls[0]
        assert note_call["notes"].strip() == "- A concise verified change."
        if existing:
            assert "--draft" in note_call["args"] and "--latest=false" in note_call["args"]
            assert note_call["args"][note_call["args"].index("--target")+1] == "a" * 40
        else:
            assert "draft=true" in note_call["args"] and "make_latest=false" in note_call["args"]
            assert "target_commitish=" + "a" * 40 in note_call["args"]
    else:
        assert not note_calls, "Reject an invalid existing ID before editing any release"
    public = [i for i, c in enumerate(calls) if "draft=false" in c["args"]]
    assert not public, "CI must retain a stable draft until actual downloaded assets and DPI pass"
    if not valid_id:
        assert result.returncode != 0
        assert not public
        assert not any(c["args"][:2] == ["release", "upload"] for c in calls)
    elif fail_upload:
        assert result.returncode == 17, result.stderr
        assert not public
    else:
        assert (result.returncode == 0) == (identity_fault == "none"), result.stderr
        uploads = [i for i, c in enumerate(calls) if c["args"][:2] == ["release", "upload"]]
        assert len(uploads) == 17
        names = {calls[index]["args"][3].split("#", 1)[0].removeprefix("release-assets/") for index in uploads}
        assert {"reverie-kernel-windows-x64.json", "reverie-kernel-linux-x64.json",
                "reverie-kernel-macos-arm64.json", "reverie-kernel-macos-x64.json",
                "reverie-kernels.json", "reverie-release-assets.json", "SHA256SUMS"} <= names
        drafts = [i for i, c in enumerate(calls)
                  if "draft=true" in c["args"] and "PATCH" in c["args"]]
        assert len(drafts) == 1 and drafts[0] > max(uploads)
        assert "make_latest=false" in calls[drafts[0]]["args"]
        assert "tag_name=v2.5.3" in calls[drafts[0]]["args"]
        assert "target_commitish=" + "a" * 40 in calls[drafts[0]]["args"]
        reads = [i for i, c in enumerate(calls)
                 if c["args"][:2] == ["api", "repos/example/reverie/releases/42"]]
        assert len(reads) == 1 and reads[0] > drafts[0]
