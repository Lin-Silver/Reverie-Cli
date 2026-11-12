"""Application defaults and native novel overrides for request-time WStyles."""

from __future__ import annotations

from datetime import datetime, timezone
from importlib import resources
import json
from pathlib import Path
from typing import Any

from ..config import get_app_root, normalize_writer_mode_config
from ..security_utils import write_json_secure
from .wstyles import WStyleError, WStyleRepository, compose_wstyles, normalize_wstyle_ids


class WStyleRuntime:
    def __init__(self, project_root: Path, *, app_root: Path | None = None, config: Any = None,
                 session_manager: Any = None, session_id: str | None = None):
        self.project_root = Path(project_root).resolve()
        self.app_root = Path(app_root).resolve() if app_root is not None else get_app_root()
        self.repository = WStyleRepository(self.app_root)
        self.global_config_path = self.app_root / ".reverie" / "config.json"
        self.config = config
        self.session_manager = session_manager
        self._explicit_session_id = session_id
        self._binding: dict[str, str] | None = None
        self._session_id = None
        self._inferred = False
        self._binding_issue = ""
        self._global_stamp = None
        self._global_ids: list[str] = []
        self._global_issues: list[dict[str, str]] = []
        self._resources_installed = False
        self._resource_issues: list[dict[str, str]] = []
        self._state_cache: dict[Path, tuple[tuple, dict[str, Any]]] = {}

    def install_bundled(self, source: Any = None) -> None:
        source = source or resources.files("reverie.writer").joinpath("wstyle_cards")
        if not source.is_dir():
            return
        self.repository._check_root()
        marker = self.repository.root / ".bundled.json"
        self.repository._reject_link(marker)
        installed = []
        if marker.is_file():
            if marker.stat().st_size > 64 * 1024:
                raise WStyleError("Bundled Card installation record exceeds its limit.")
            try:
                installed = json.loads(marker.read_text(encoding="utf-8"))["installed_ids"]
                if not isinstance(installed, list):
                    raise ValueError("invalid installed_ids")
            except (ValueError, KeyError, TypeError) as exc:
                raise WStyleError(f"Invalid bundled Card installation record: {exc}") from exc
        updated = list(installed)
        existing = self.repository._paths()
        for entry in sorted(source.iterdir(), key=lambda item: item.name):
            if not entry.name.endswith(".md"):
                continue
            card_id = entry.name[:-3]
            if card_id in installed:
                continue
            if not existing.get(card_id.casefold()):
                self.repository.write_new(card_id, entry.read_text(encoding="utf-8"))
            updated.append(card_id)
        if updated != installed:
            write_json_secure(marker, {"schema": "reverie.writer.wstyle.resources.v1", "installed_ids": updated})

    def ensure_resources(self) -> None:
        if not self._resources_installed:
            try:
                self.install_bundled()
            except (WStyleError, OSError, ValueError) as exc:
                self._resource_issues = [{"id": "resources", "message": str(exc)[:1000]}]
            self._resources_installed = True

    @staticmethod
    def _selection_value(value: Any, source: str) -> tuple[list[str], list[dict[str, str]]]:
        issues = []
        if not isinstance(value, (list, str)) or (isinstance(value, list) and any(not isinstance(v, str) for v in value)):
            issues.append({"id": source, "message": "Saved WStyle selection contains invalid field types; only string IDs are used."})
        return normalize_wstyle_ids(value), issues

    def _defaults(self) -> tuple[list[str], list[dict[str, str]]]:
        self.repository._check_root()
        self.repository._reject_link(self.global_config_path)
        if not self.global_config_path.exists():
            writer = getattr(self.config, "writer_mode", {}) or {}
            return self._selection_value(writer.get("active_wstyles", []), "global")
        info = self.global_config_path.stat()
        stamp = (info.st_mtime_ns, info.st_ctime_ns, info.st_size)
        if stamp != self._global_stamp:
            try:
                data = json.loads(self.global_config_path.read_text(encoding="utf-8-sig"))
                if not isinstance(data, dict):
                    raise ValueError("Application configuration must be an object")
                writer = data.get("writer_mode", {})
                if not isinstance(writer, dict):
                    raise ValueError("writer_mode must be an object")
                self._global_ids, self._global_issues = self._selection_value(writer.get("active_wstyles", writer.get("active_wstyle", [])), "global")
            except (OSError, ValueError, TypeError) as exc:
                self._global_ids = []
                self._global_issues = [{"id": "global", "message": f"Cannot restore application WStyles: {exc}"}]
            self._global_stamp = stamp
        return list(self._global_ids), list(self._global_issues)

    def _session(self):
        if self.session_manager is not None and self._explicit_session_id:
            from types import SimpleNamespace

            page = self.session_manager.get_page(self._explicit_session_id, limit=1)
            return SimpleNamespace(id=page["id"], metadata=page["metadata"])
        return self.session_manager.get_current_session() if self.session_manager is not None else None

    def _ensure_binding(self) -> None:
        session = self._session()
        session_id = session.id if session is not None else ""
        if self._session_id != session_id:
            self._session_id = session_id
            self._binding = None
            self._binding_issue = ""
            self._inferred = False
            saved = session.metadata.get("writer_project") if session is not None else None
            if isinstance(saved, dict):
                try:
                    self._validate_binding(str(saved.get("novel_id", "")), self.project_root / str(saved.get("project_dir", "")))
                    self._binding = dict(saved)
                    self._inferred = True
                except WStyleError as exc:
                    self._binding_issue = str(exc)
                    self._inferred = True
        if not self._inferred:
            self._inferred = True
            from ..tools.serial_novel import SerialNovelTool

            tool = SerialNovelTool({"project_root": self.project_root})
            novel_id = tool._infer_active_novel_id({}, suppress_errors=True)
            if novel_id:
                self.bind_project(novel_id, self.project_root / "novels" / novel_id)

    def _validate_binding(self, novel_id: str, project_dir: Path) -> Path:
        path = Path(project_dir)
        try:
            relative = path.relative_to(self.project_root)
        except ValueError as exc:
            raise WStyleError("Writer project binding escapes the current workspace.") from exc
        if not novel_id or any(ch in novel_id for ch in "/\\") or novel_id in {".", ".."}:
            raise WStyleError("Invalid native novel ID.")
        current = self.project_root
        for part in (*relative.parts, "tracking", "state.json"):
            current = current / part
            self.repository._reject_link(current)
        if self.project_root not in path.resolve().parents:
            raise WStyleError("Writer project binding escapes the current workspace.")
        state_path = path / "tracking" / "state.json"
        try:
            info = state_path.stat()
            signature = (info.st_mtime_ns, info.st_ctime_ns, info.st_size, info.st_ino)
            cached = self._state_cache.get(path)
            state = cached[1] if cached and cached[0] == signature else json.loads(state_path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError) as exc:
            raise WStyleError(f"Cannot restore native Writer project: {exc}") from exc
        if not isinstance(state, dict) or state.get("schema") != "reverie.writer.project.v1" or state.get("novel_id") != novel_id:
            raise WStyleError("Invalid native Writer project state.")
        self._state_cache[path] = (signature, state)
        return path

    def bind_project(self, novel_id: str, project_dir: Path) -> None:
        path = self._validate_binding(novel_id, project_dir)
        binding = {"novel_id": novel_id, "project_dir": path.relative_to(self.project_root).as_posix()}
        session = self._session()
        self._session_id = session.id if session is not None else ""
        self._binding = binding
        self._binding_issue = ""
        self._inferred = True
        if session is not None and session.metadata.get("writer_project") != binding:
            session.metadata["writer_project"] = binding
            if hasattr(self.session_manager, "update_metadata"):
                page = self.session_manager.get_page(session.id, limit=1)
                self.session_manager.update_metadata(session.id, {"writer_project": binding}, expected_revision=page["revision"])
            else:
                self.session_manager.save_session(session)

    def select_novel(self, novel_id: str) -> None:
        self.bind_project(novel_id, self.project_root / "novels" / novel_id)

    def _project(self) -> tuple[Path, dict[str, Any]] | None:
        self._ensure_binding()
        if self._binding is None:
            return None
        path = self._validate_binding(self._binding["novel_id"], self.project_root / self._binding["project_dir"])
        return path, self._state_cache[path][1]

    def selection(self, *, global_scope: bool = False) -> tuple[list[str], str, bool, list[dict[str, str]]]:
        ids, issues = self._defaults()
        if global_scope:
            return ids, "global", False, issues
        try:
            project = self._project()
            if self._binding_issue:
                issues.append({"id": "novel", "message": self._binding_issue})
            if project:
                _, state = project
                scope = f"novel:{state['novel_id']}"
                if "active_wstyles" in state:
                    ids, selection_issues = self._selection_value(state["active_wstyles"], scope)
                    return ids, scope, False, selection_issues + issues
                return ids, scope, True, issues
        except (OSError, WStyleError, ValueError) as exc:
            issues.append({"id": "novel", "message": str(exc)})
        return ids, "global", False, issues

    def composition(self, *, global_scope: bool = False):
        self.ensure_resources()
        ids, scope, inherited, issues = self.selection(global_scope=global_scope)
        result = compose_wstyles(self.repository, ids, strict=False, max_tokens=self._style_token_budget())
        result.scope = scope
        result.inherited = inherited
        result.issues[:0] = issues + self._resource_issues
        return result

    def snapshot(self, *, global_scope: bool = False, composition=None) -> dict[str, Any]:
        result = composition if composition is not None else self.composition(global_scope=global_scope)
        return {**result.snapshot(),
                "saved_matches_effective": [v.casefold() for v in result.saved_ids] == [v.casefold() for v in result.active_ids] and not result.issues,
                "repository": str(self.repository.root)}

    def set_selection(self, ids: list[str], *, global_scope: bool = False, allow_unavailable: bool = False) -> dict[str, Any]:
        self.ensure_resources()
        result = compose_wstyles(self.repository, ids, strict=not allow_unavailable, max_tokens=self._style_token_budget())
        saved_ids = normalize_wstyle_ids(ids) if allow_unavailable else result.active_ids
        project = None if global_scope else self._project()
        if project:
            path, state = project
            state["active_wstyles"] = saved_ids
            state["updated_at"] = datetime.now(timezone.utc).isoformat()
            write_json_secure(path / "tracking" / "state.json", state)
        else:
            self.repository._check_root()
            self.repository._reject_link(self.global_config_path)
            try:
                data = json.loads(self.global_config_path.read_text(encoding="utf-8-sig")) if self.global_config_path.is_file() else {}
            except (OSError, ValueError) as exc:
                raise WStyleError(f"Cannot save application WStyles without damaging configuration: {exc}") from exc
            if not isinstance(data, dict):
                raise WStyleError("Application configuration must be an object.")
            writer = normalize_writer_mode_config(data.get("writer_mode", {}))
            writer["active_wstyles"] = saved_ids
            data["writer_mode"] = writer
            write_json_secure(self.global_config_path, data)
            self._global_stamp = None
        return self.snapshot(global_scope=global_scope)

    def _style_token_budget(self) -> int:
        context_limit = int(getattr(self.config, "max_context_tokens", 128_000) or 128_000)
        model_limit = getattr(getattr(self.config, "active_model", None), "max_context_tokens", None)
        if model_limit:
            context_limit = min(context_limit, int(model_limit))
        return max(0, context_limit // 4)

    def inherit_defaults(self) -> dict[str, Any]:
        project = self._project()
        if project is None:
            raise WStyleError("Select a native novel before restoring inheritance.")
        path, state = project
        state.pop("active_wstyles", None)
        state["updated_at"] = datetime.now(timezone.utc).isoformat()
        write_json_secure(path / "tracking" / "state.json", state)
        return self.snapshot()


def runtime_for_agent(agent) -> WStyleRuntime:
    context = getattr(getattr(agent, "tool_executor", None), "context", {})
    runtime = getattr(agent, "wstyle_runtime", None) or context.get("wstyle_runtime")
    if runtime is None:
        manager = context.get("config_manager")
        runtime = WStyleRuntime(agent.project_root, app_root=getattr(manager, "app_root", None),
                                config=getattr(agent, "config", None), session_manager=context.get("session_manager"))
        agent.wstyle_runtime = runtime
        context["wstyle_runtime"] = runtime
    runtime.config = getattr(agent, "config", None)
    runtime.session_manager = context.get("session_manager") or runtime.session_manager
    return runtime
