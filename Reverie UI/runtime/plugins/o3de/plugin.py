"""O3DE source SDK plugin for Reverie CLI."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen
import json
import os
import shutil
import subprocess
import sys


PLUGIN_VERSION = "0.1.0"
DEFAULT_O3DE_REPOSITORY = "https://github.com/o3de/o3de.git"
DEFAULT_O3DE_RELEASES_API = "https://api.github.com/repos/o3de/o3de/releases"
DEFAULT_O3DE_TAGS_API = "https://api.github.com/repos/o3de/o3de/tags"


class ReverieRuntimePluginHost:
    """Small inlined host for Reverie CLI's fixed `-RC` plugin protocol."""

    def build_handshake(self) -> dict[str, Any]:
        raise NotImplementedError

    def handle_command(self, command_name: str, payload: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    def write_json(self, payload: dict[str, Any]) -> int:
        sys.stdout.write(json.dumps(payload, ensure_ascii=False))
        sys.stdout.flush()
        return 0

    def run(self, argv: list[str]) -> int:
        if len(argv) >= 2 and argv[1] == "-RC":
            return self.write_json(self.build_handshake())
        if len(argv) >= 2 and argv[1] == "-RC-CALL":
            if len(argv) < 4:
                return self.write_json({"success": False, "output": "", "error": "Usage: -RC-CALL <command> <json-payload>", "data": {}})
            command_name = str(argv[2] or "").strip().lower()
            try:
                payload = json.loads(str(argv[3] or "").strip() or "{}")
            except Exception as exc:
                return self.write_json({"success": False, "output": "", "error": f"Invalid JSON payload: {exc}", "data": {}})
            try:
                result = self.handle_command(command_name, payload)
            except Exception as exc:
                result = {"success": False, "output": "", "error": str(exc), "data": {}}
            if not isinstance(result, dict):
                result = {"success": False, "output": "", "error": "Plugin command handler must return a JSON object.", "data": {}}
            result.setdefault("success", False)
            result.setdefault("output", "")
            result.setdefault("error", "")
            result.setdefault("data", {})
            return self.write_json(result)
        sys.stderr.write("This runtime plugin only supports -RC and -RC-CALL.\n")
        return 1


class O3DESourceSDKPlugin(ReverieRuntimePluginHost):
    """Protocol wrapper for O3DE source and local SDK manifest management."""

    def __init__(self) -> None:
        self.plugin_root = self._resolve_plugin_root()
        self.source_root = self.plugin_root / "source"
        self.runtime_root = self.plugin_root / "runtime"
        self.download_root = self.plugin_root / "downloads"
        self.state_path = self.plugin_root / "state" / "runtime_state.json"

    def build_handshake(self) -> dict[str, Any]:
        return {
            "protocol_version": "1.0",
            "plugin_id": "o3de",
            "display_name": "O3DE Source SDK Plugin",
            "version": PLUGIN_VERSION,
            "runtime_family": "engine",
            "description": "O3DE source checkout, version discovery, SDK manifest, and project validation prep.",
            "tool_call_hint": (
                "Use rc_o3de_list_versions before choosing a source version, "
                "rc_o3de_ensure_runtime or rc_o3de_clone_source to create the plugin-local SDK depot, "
                "and rc_o3de_source_status to inspect existing checkouts."
            ),
            "system_prompt": (
                "This plugin keeps O3DE source and SDK metadata inside .reverie/plugins/o3de. "
                "Do not install O3DE into global folders or C drive user caches unless the user explicitly asks."
            ),
            "commands": [
                {
                    "name": "runtime_status",
                    "description": "Inspect plugin-local O3DE source, runtime manifest, and detected command helpers.",
                    "parameters": {"type": "object", "properties": {}, "required": []},
                    "expose_as_tool": True,
                    "include_modes": ["reverie", "reverie-gamer"],
                },
                {
                    "name": "list_versions",
                    "description": "List official O3DE GitHub releases or tags.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "limit": {"type": "integer", "description": "Maximum version count to return."},
                            "include_tags": {"type": "boolean", "description": "When true, use the tags API if releases are sparse."},
                        },
                        "required": [],
                    },
                    "expose_as_tool": True,
                    "include_modes": ["reverie", "reverie-gamer"],
                },
                {
                    "name": "source_status",
                    "description": "Inspect O3DE source checkouts stored in the plugin-local source depot.",
                    "parameters": {"type": "object", "properties": {}, "required": []},
                    "expose_as_tool": True,
                    "include_modes": ["reverie", "reverie-gamer"],
                },
                {
                    "name": "clone_source",
                    "description": "Clone O3DE source from GitHub into the plugin-local source depot.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "version": {"type": "string", "description": "Release tag, branch, commit, or `latest`."},
                            "repository": {"type": "string", "description": "Optional repository URL override."},
                            "target_name": {"type": "string", "description": "Optional folder name under the plugin source depot."},
                            "depth": {"type": "integer", "description": "Shallow clone depth. Defaults to 1."},
                            "with_submodules": {"type": "boolean", "description": "When true, initialize submodules after clone."},
                            "force": {"type": "boolean", "description": "When true, replace an existing target checkout inside the source depot."},
                        },
                        "required": [],
                    },
                    "expose_as_tool": True,
                    "include_modes": ["reverie", "reverie-gamer"],
                },
                {
                    "name": "ensure_runtime",
                    "description": "Ensure a plugin-local O3DE source SDK checkout and runtime manifest exist.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "version": {"type": "string", "description": "Release tag, branch, commit, or `latest`."},
                            "force": {"type": "boolean", "description": "When true, refresh the checkout."},
                            "with_submodules": {"type": "boolean", "description": "When true, initialize submodules after clone."},
                        },
                        "required": [],
                    },
                    "expose_as_tool": True,
                    "include_modes": ["reverie", "reverie-gamer"],
                },
            ],
        }

    def handle_command(self, command_name: str, payload: dict[str, Any]) -> dict[str, Any]:
        if command_name == "runtime_status":
            return self._cmd_runtime_status(payload)
        if command_name == "list_versions":
            return self._cmd_list_versions(payload)
        if command_name == "source_status":
            return self._cmd_source_status(payload)
        if command_name == "clone_source":
            return self._cmd_clone_source(payload)
        if command_name == "ensure_runtime":
            return self._cmd_ensure_runtime(payload)
        return {"success": False, "output": "", "error": f"Unknown command: {command_name}", "data": {}}

    def _cmd_runtime_status(self, payload: dict[str, Any]) -> dict[str, Any]:
        state = self._load_state()
        checkouts = self._source_checkout_details()
        manifest_path = self.runtime_root / "sdk_manifest.json"
        helpers = self._detected_helpers()
        return {
            "success": True,
            "output": f"{len(checkouts)} O3DE source checkout(s); manifest={'yes' if manifest_path.exists() else 'no'}",
            "error": "",
            "data": {
                "plugin_root": str(self.plugin_root),
                "runtime_root": str(self.runtime_root),
                "source_root": str(self.source_root),
                "downloads_root": str(self.download_root),
                "state_path": str(self.state_path),
                "source_checkouts": checkouts,
                "manifest_path": str(manifest_path),
                "manifest_exists": manifest_path.exists(),
                "helpers": helpers,
                "state": state,
            },
        }

    def _cmd_list_versions(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            limit = int(payload.get("limit", 10) or 10)
        except (TypeError, ValueError):
            limit = 10
        limit = max(1, min(limit, 50))
        include_tags = bool(payload.get("include_tags", True))
        try:
            releases = self._http_get_json_list(DEFAULT_O3DE_RELEASES_API)
        except Exception:
            releases = []
        rows: list[dict[str, str]] = []
        for release in releases[:limit]:
            if not isinstance(release, dict):
                continue
            rows.append(
                {
                    "tag": str(release.get("tag_name") or ""),
                    "name": str(release.get("name") or ""),
                    "source": "release",
                    "tarball_url": str(release.get("tarball_url") or ""),
                    "zipball_url": str(release.get("zipball_url") or ""),
                }
            )
        if include_tags and len(rows) < limit:
            try:
                tags = self._http_get_json_list(DEFAULT_O3DE_TAGS_API)
            except Exception:
                tags = []
            for tag in tags:
                if not isinstance(tag, dict):
                    continue
                name = str(tag.get("name") or "")
                if name and name not in {row["tag"] for row in rows}:
                    rows.append({"tag": name, "name": name, "source": "tag", "tarball_url": "", "zipball_url": ""})
                if len(rows) >= limit:
                    break
        return {
            "success": True,
            "output": "\n".join(f"{row['tag']} :: {row['source']}" for row in rows),
            "error": "",
            "data": {"repository": DEFAULT_O3DE_REPOSITORY, "versions": rows},
        }

    def _cmd_source_status(self, payload: dict[str, Any]) -> dict[str, Any]:
        checkouts = self._source_checkout_details()
        return {
            "success": True,
            "output": "\n".join(f"{item['name']} :: {item['head']}" for item in checkouts) or "No O3DE source checkouts found.",
            "error": "",
            "data": {"source_root": str(self.source_root), "repository": DEFAULT_O3DE_REPOSITORY, "checkouts": checkouts},
        }

    def _cmd_clone_source(self, payload: dict[str, Any]) -> dict[str, Any]:
        repository = str(payload.get("repository") or DEFAULT_O3DE_REPOSITORY).strip()
        requested_version = str(payload.get("version") or "latest").strip() or "latest"
        target_name = str(payload.get("target_name") or "").strip()
        force = bool(payload.get("force", False))
        with_submodules = bool(payload.get("with_submodules", False))
        try:
            depth = int(payload.get("depth", 1) or 1)
        except (TypeError, ValueError):
            depth = 1
        depth = max(1, min(depth, 1000))
        git_exe = shutil.which("git.exe") or shutil.which("git")
        if not git_exe:
            return {"success": False, "output": "", "error": "Git executable not found in PATH.", "data": {}}
        try:
            ref = self._resolve_source_ref(requested_version)
        except Exception as exc:
            return {"success": False, "output": "", "error": str(exc), "data": {"version": requested_version}}
        target = self._source_target_path(target_name or f"o3de-{self._sanitize_name(ref)}")
        if target.exists():
            if not force:
                self._write_runtime_manifest(target, ref, repository)
                return {
                    "success": True,
                    "output": f"O3DE source checkout already exists: {target}",
                    "error": "",
                    "data": {"cloned": False, "source_dir": str(target), "ref": ref, "repository": repository},
                }
            self._safe_remove_source_dir(target)
        self.source_root.mkdir(parents=True, exist_ok=True)
        command = self._build_clone_command(git_exe, repository, ref, target, depth, use_http11=False)
        completed = self._run_git_clone(command)
        if completed.returncode != 0 and target.exists():
            self._safe_remove_source_dir(target)
            command = self._build_clone_command(git_exe, repository, ref, target, depth, use_http11=True)
            completed = self._run_git_clone(command)
        if completed.returncode != 0:
            if target.exists():
                self._safe_remove_source_dir(target)
            return {
                "success": False,
                "output": completed.stdout.strip(),
                "error": completed.stderr.strip() or f"git clone failed with exit code {completed.returncode}",
                "data": {"command": command, "source_dir": str(target), "ref": ref, "repository": repository},
            }
        if with_submodules:
            submodule = subprocess.run(
                [git_exe, "submodule", "update", "--init", "--recursive", "--depth", str(depth)],
                cwd=str(target),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=7200,
            )
            if submodule.returncode != 0:
                return {
                    "success": False,
                    "output": completed.stdout.strip() + "\n" + submodule.stdout.strip(),
                    "error": submodule.stderr.strip() or f"git submodule update failed with exit code {submodule.returncode}",
                    "data": {"source_dir": str(target), "ref": ref, "repository": repository},
                }
        self._write_runtime_manifest(target, ref, repository)
        state = self._load_state()
        state.update({"source_checkout_path": str(target), "source_checkout_ref": ref, "source_repository": repository, "updated_at": self._utc_now()})
        self._save_state(state)
        return {
            "success": True,
            "output": f"Cloned O3DE source {ref} into {target}",
            "error": "",
            "data": {"cloned": True, "source_dir": str(target), "ref": ref, "repository": repository},
        }

    def _cmd_ensure_runtime(self, payload: dict[str, Any]) -> dict[str, Any]:
        existing = self._source_checkout_details()
        force = bool(payload.get("force", False))
        if existing and not force:
            source_dir = Path(existing[0]["path"])
            self._write_runtime_manifest(source_dir, existing[0].get("ref") or existing[0].get("head") or "existing", str(existing[0].get("repository") or DEFAULT_O3DE_REPOSITORY))
            return {
                "success": True,
                "output": f"O3DE source SDK already available at {source_dir}",
                "error": "",
                "data": {"deployed": False, "source_dir": str(source_dir), "manifest_path": str(self.runtime_root / "sdk_manifest.json")},
            }
        result = self._cmd_clone_source(
            {
                "version": str(payload.get("version") or "latest"),
                "force": force,
                "with_submodules": bool(payload.get("with_submodules", False)),
            }
        )
        if isinstance(result.get("data"), dict):
            result["data"]["deployed"] = bool(result.get("success", False))
            result["data"]["manifest_path"] = str(self.runtime_root / "sdk_manifest.json")
        return result

    def _write_runtime_manifest(self, source_dir: Path, ref: str, repository: str) -> None:
        self.runtime_root.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema": "reverie.o3de_source_sdk_manifest.v1",
            "runtime": "o3de",
            "repository": repository,
            "ref": ref,
            "source_dir": str(source_dir.resolve(strict=False)),
            "runtime_root": str(self.runtime_root.resolve(strict=False)),
            "helpers": self._detected_helpers(source_dir),
            "generated_at": self._utc_now(),
            "notes": [
                "O3DE is source-managed here; native editor/asset-processor builds are intentionally explicit follow-up steps.",
                "All source and metadata live inside the plugin-local depot rather than global SDK folders.",
            ],
        }
        (self.runtime_root / "sdk_manifest.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _detected_helpers(self, source_dir: Optional[Path] = None) -> dict[str, str]:
        roots = [source_dir] if source_dir is not None else [Path(item["path"]) for item in self._source_checkout_details()]
        candidates: dict[str, str] = {}
        for root in roots:
            if root is None or not root.exists():
                continue
            for key, relative in {
                "o3de_bat": "scripts/o3de.bat",
                "o3de_py": "scripts/o3de.py",
                "python_bootstrap": "python/get_python.bat",
                "editor_windows": "build/windows/bin/profile/Editor.exe",
            }.items():
                candidate = root / relative
                if candidate.exists() and key not in candidates:
                    candidates[key] = str(candidate.resolve(strict=False))
        return candidates

    def _source_checkout_details(self) -> list[dict[str, str]]:
        if not self.source_root.exists():
            return []
        rows: list[dict[str, str]] = []
        for item in sorted([path for path in self.source_root.iterdir() if path.is_dir()], key=lambda path: path.name.lower()):
            rows.append(
                {
                    "name": item.name,
                    "path": str(item.resolve(strict=False)),
                    "head": self._git_output(item, ["rev-parse", "--short", "HEAD"]),
                    "ref": self._git_output(item, ["describe", "--tags", "--always"]),
                    "repository": self._git_output(item, ["config", "--get", "remote.origin.url"]) or DEFAULT_O3DE_REPOSITORY,
                }
            )
        return rows

    def _git_output(self, path: Path, args: list[str]) -> str:
        git_exe = shutil.which("git.exe") or shutil.which("git")
        if not git_exe or not (path / ".git").exists():
            return ""
        try:
            completed = subprocess.run(
                [git_exe, *args],
                cwd=str(path),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=20,
            )
        except Exception:
            return ""
        return completed.stdout.strip() if completed.returncode == 0 else ""

    def _resolve_source_ref(self, requested_version: str) -> str:
        version_text = str(requested_version or "latest").strip()
        if version_text.lower() not in {"", "latest", "stable", "current"}:
            return version_text
        rows = self._http_get_json_list(DEFAULT_O3DE_RELEASES_API)
        for release in rows:
            if isinstance(release, dict) and str(release.get("tag_name") or "").strip():
                return str(release.get("tag_name")).strip()
        tags = self._http_get_json_list(DEFAULT_O3DE_TAGS_API)
        for tag in tags:
            if isinstance(tag, dict) and str(tag.get("name") or "").strip():
                return str(tag.get("name")).strip()
        return "development"

    def _source_target_path(self, target_name: str) -> Path:
        safe = self._sanitize_name(target_name)
        target = (self.source_root / safe).resolve(strict=False)
        root = self.source_root.resolve(strict=False)
        try:
            target.relative_to(root)
        except ValueError as exc:
            raise RuntimeError(f"Refusing to use source target outside plugin source root: {target}") from exc
        return target

    def _build_clone_command(
        self,
        git_exe: str,
        repository: str,
        ref: str,
        target: Path,
        depth: int,
        *,
        use_http11: bool,
    ) -> list[str]:
        prefix = [git_exe]
        if use_http11:
            prefix.extend(["-c", "http.version=HTTP/1.1", "-c", "http.postBuffer=524288000"])
        return [
            *prefix,
            "clone",
            "--depth",
            str(depth),
            "--filter=blob:none",
            "--single-branch",
            "--no-tags",
            "--branch",
            ref,
            repository,
            str(target),
        ]

    def _run_git_clone(self, command: list[str]) -> subprocess.CompletedProcess:
        return subprocess.run(
            command,
            cwd=str(self.source_root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=7200,
        )

    def _safe_remove_source_dir(self, target: Path) -> None:
        resolved_root = self.source_root.resolve(strict=False)
        resolved_target = target.resolve(strict=False)
        try:
            resolved_target.relative_to(resolved_root)
        except ValueError as exc:
            raise RuntimeError(f"Refusing to remove directory outside source root: {resolved_target}") from exc
        if resolved_target.exists():
            shutil.rmtree(resolved_target)

    def _http_get_json_list(self, url: str) -> list[Any]:
        request = Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "Reverie-O3DE-Plugin/0.1"})
        try:
            with urlopen(request, timeout=30) as response:
                payload = response.read().decode("utf-8", errors="replace")
        except HTTPError as exc:
            raise RuntimeError(f"HTTP {exc.code} while requesting {url}") from exc
        except URLError as exc:
            raise RuntimeError(f"Network error while requesting {url}: {exc.reason}") from exc
        try:
            data = json.loads(payload)
        except Exception as exc:
            raise RuntimeError(f"Invalid JSON received from {url}: {exc}") from exc
        if not isinstance(data, list):
            raise RuntimeError(f"GitHub metadata from {url} was not a JSON array.")
        return data

    def _load_state(self) -> dict[str, Any]:
        try:
            payload = json.loads(self.state_path.read_text(encoding="utf-8"))
            return payload if isinstance(payload, dict) else {}
        except Exception:
            return {}

    def _save_state(self, payload: dict[str, Any]) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _sanitize_name(self, raw_value: str) -> str:
        text = str(raw_value or "").strip()
        cleaned = [char if (char.isalnum() or char in {"-", "_", "."}) else "_" for char in text]
        normalized = "".join(cleaned).strip("._-")
        return normalized or "current"

    def _resolve_plugin_root(self) -> Path:
        env_root = os.environ.get("REVERIE_O3DE_PLUGIN_ROOT", "").strip() or os.environ.get("REVERIE_PLUGIN_ROOT", "").strip()
        if env_root:
            return self._normalize_plugin_root(Path(env_root).expanduser().resolve(strict=False))

        if getattr(sys, "frozen", False):
            try:
                executable_dir = Path(sys.executable).resolve(strict=False).parent
                return self._normalize_plugin_root(executable_dir)
            except Exception:
                pass
        return self._normalize_plugin_root(Path(__file__).resolve().parent)

    def _normalize_plugin_root(self, root: Path) -> Path:
        candidate = Path(root).resolve(strict=False)
        if candidate.name.lower() == "dist" and (candidate.parent / "plugin.json").exists():
            return candidate.parent.resolve(strict=False)
        if candidate.name.lower() == "plugins" and candidate.parent.name.lower() == ".reverie":
            return (candidate / "o3de").resolve(strict=False)
        return candidate

    def _utc_now(self) -> str:
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def main(argv: list[str]) -> int:
    return O3DESourceSDKPlugin().run(argv)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
