"""RIU P1 ``render_view`` tool: register a workspace HTML artifact as a view.

This is the model-facing entry to the Intelligent UI pipeline
(``docs/INTELLIGENT_UI_SPEC.md`` §4.1 / §5). The model writes an HTML artifact
into the workspace with the ordinary file tools, then calls ``render_view``
with that artifact's path, a title and a one-line summary. The tool:

* reads the owning identity (session / turn / tool-call) from the *kernel*
  context -- never from the model's arguments -- so a model cannot claim
  another session's identity or forge provenance;
* hands the artifact to the restricted :class:`~reverie.views.ViewStore`, which
  validates workspace containment, size, suffix and UTF-8, copies the exact
  bytes into a managed per-revision directory and returns a manifest -- the
  view is persisted *before* anyone is told it exists;
* emits a ``view_ready`` (or ``view_error``) event on the unforgeable
  out-of-band tool-stream channel, carrying only the manifest reference, never
  the HTML or a filesystem path;
* returns a short text summary naming the opaque view id, keeping the HTML and
  the path out of the tool result so the bytes are never re-added to a later
  model request.

A forged ``[[REVERIE_EVENT]]`` ``view_ready`` in model text cannot create a
view: the renderer dereferences the id through the ``ViewStore``, and only this
tool, running in the kernel, ever mints one. Nothing here touches the network.
"""

from __future__ import annotations

import secrets
import re
from datetime import datetime, timezone
from html.parser import HTMLParser
from typing import Any

from .base import BaseTool, ToolResult
from ..diagnostics import report_suppressed_exception
from ..views import ViewIdentity, ViewStore, ViewStoreError


class _BrowserStorageReferences(HTMLParser):
    """Advisory authoring hints, never a JavaScript validator or security gate."""

    def __init__(self) -> None:
        super().__init__()
        self.apis: set[str] = set()
        self.in_script = False
        self.has_controls = False
        self.initializes_host = False
        self.saves_state = False
        self.has_capability_reference = False
        self.has_empty_capability_literal = False

    def handle_starttag(self, tag, attrs):
        if tag in {'input', 'select', 'textarea', 'button'}:
            self.has_controls = True
        if tag == "script":
            values = dict(attrs)
            script_type = (values.get("type") or "").split(";")[0].strip().lower()
            self.in_script = "src" not in values and script_type in {"", "module", "text/javascript", "application/javascript", "text/ecmascript", "application/ecmascript"}

    def handle_endtag(self, tag):
        if tag == "script":
            self.in_script = False

    def handle_data(self, data):
        if self.in_script:
            self.apis.update(re.findall(r"\b(localStorage|sessionStorage)\s*\.\s*(?:getItem|setItem|removeItem|clear|key)\s*\(", data))
            self.initializes_host |= 'ui/initialize' in data
            self.saves_state |= 'reverie/view-state' in data
            self.has_capability_reference |= bool(re.search(r'\bcapability\b', data))
            self.has_empty_capability_literal |= bool(re.search(r'''\bcapability\s*:\s*(?:"\s*"|'\s*')''', data))


class RenderViewTool(BaseTool):
    """Register an in-workspace HTML artifact as an interactive view."""

    name = "render_view"
    aliases = ("show_view", "interactive_view")
    search_hint = "display a generated HTML artifact as an interactive view for the user"
    tool_category = "ui"
    tool_tags = ("view", "ui", "interactive", "render", "html")
    read_only = False
    concurrency_safe = False
    destructive = False
    should_defer = False
    workspace_checkpoint = False
    description = (
        "Register an HTML artifact you have already written inside the workspace "
        "as an interactive view shown to the user. Complete an interactive answer "
        "by calling this in the same turn as create_file; a file path alone does "
        "not display the view in the conversation. Provide the workspace path to "
        "the .html/.htm file, a short title, and a one-line summary. The view's "
        "bytes are stored and displayed by the host; your tool result and the "
        "conversation keep only a short reference, so do NOT paste the HTML into "
        "chat and do not claim the HTML was free. To update a view in place, pass "
        "replaces_view_id with the id returned by an earlier render_view call. "
        "Use responsive, keyboard-accessible controls and useful empty/error text. "
        "Use ui/initialize then ui/notifications/initialized; apply hostContext.theme, "
        "locale and styles.variables and listen for ui/notifications/host-context-changed. "
        "Respect prefers-reduced-motion and hostContext.reverie.reducedMotion. "
        "Persist private UI state with reverie/view-state so it survives lazy unloading. "
        "The display modes are inline, fullscreen and pip; card/carousel are HTML layouts, "
        "not display modes. All assets must be self-contained and offline. "
        "localStorage and sessionStorage are unavailable in the opaque-origin sandbox; "
        "use the Offline host integration example from Interactive Views for host theme "
        "and private state, with your actual controls wired to restore/save."
    )
    parameters = {
        "type": "object",
        "properties": {
            "artifact_path": {
                "type": "string",
                "description": (
                    "Workspace-relative (or in-workspace absolute) path to the "
                    ".html/.htm artifact to display. Must already exist inside the "
                    "current workspace."
                ),
            },
            "title": {
                "type": "string",
                "description": "Short human-readable title for the view.",
            },
            "summary": {
                "type": "string",
                "description": (
                    "One-line summary of what the view shows. This is the only "
                    "description kept in the conversation history."
                ),
            },
            "replaces_view_id": {
                "type": "string",
                "description": (
                    "Optional id of an existing view in this session to revise. A "
                    "new revision is stored and shown in place of the old one."
                ),
            },
            "callable_tools": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Optional allow-list of tool names this view is permitted to "
                    "request at runtime through the host (the component's allowed "
                    "scope). Omit it (the default) and the view can call nothing. "
                    "Listing a tool only lets such a request be considered: every "
                    "call the view makes still passes the same approval and "
                    "permission checks as your own tool calls, and the list is "
                    "intersected with what is already allowed -- it can only "
                    "narrow access, never grant a new capability."
                ),
            },
        },
        "required": ["artifact_path", "title", "summary"],
    }

    def get_execution_message(self, **kwargs: Any) -> str:
        title = str(kwargs.get("title") or "").strip()
        return f"Rendering interactive view: {title}" if title else "Rendering interactive view..."

    # -- kernel-bound identity (never from model arguments) --------------
    def _identity(self) -> ViewIdentity:
        agent = self.context.get("agent")
        session_id = ""
        getter = getattr(agent, "_current_session_details", None)
        if callable(getter):
            try:
                session_id = str((getter("default") or ("", ""))[0] or "").strip()
            except Exception:
                session_id = ""
        if not session_id:
            session_id = str(self.context.get("session_id") or "").strip()
        turn_id = str(self.context.get("turn_id") or "").strip()
        tool_call_id = str(self.context.get("active_tool_call_id") or "").strip()
        if not turn_id:
            # The per-turn id is normally set by the kernel at process_message;
            # fall back to the current tool-call id, then a minted provenance id,
            # so a view always has an owner even on a degraded code path.
            turn_id = tool_call_id or ("t" + secrets.token_hex(8))
        return ViewIdentity(session_id=session_id, turn_id=turn_id, tool_call_id=tool_call_id)

    def _store(self) -> ViewStore:
        injected = self.context.get("view_store")
        if isinstance(injected, ViewStore):
            return injected
        return ViewStore.for_project(self.get_project_root())

    def _emit(self, event_type: str, **payload: Any) -> None:
        """Emit on the unforgeable out-of-band tool-stream channel, if present."""
        emit = getattr(self.context.get("agent"), "_emit_tool_stream_event", None)
        if callable(emit):
            try:
                emit(event_type, **payload)
            except Exception:
                report_suppressed_exception("render_view stream emit")

    # -- execute ---------------------------------------------------------
    def execute(self, **kwargs: Any) -> ToolResult:
        artifact_path = kwargs.get("artifact_path")
        title = kwargs.get("title")
        summary = kwargs.get("summary")
        raw_replaces = kwargs.get("replaces_view_id")
        replaces_view_id = str(raw_replaces).strip() if raw_replaces else None

        # The callable-tool allow-list is advisory authorization that can only
        # narrow: the store cleans/caps it and every later call is still gated.
        # A bare string is wrapped (never iterated into characters); anything
        # that is not a list/tuple/str mints an empty (fail-closed) allow-list.
        raw_tools = kwargs.get("callable_tools")
        if isinstance(raw_tools, str):
            callable_tools = [raw_tools]
        elif isinstance(raw_tools, (list, tuple)):
            callable_tools = [str(item) for item in raw_tools]
        else:
            callable_tools = []

        if not artifact_path or not str(artifact_path).strip():
            return ToolResult.fail(
                "render_view requires 'artifact_path': the path to an .html file inside the workspace."
            )
        if title is None or summary is None:
            return ToolResult.fail("render_view requires both 'title' and 'summary'.")

        try:
            identity = self._identity()
        except ViewStoreError as exc:
            return ToolResult.fail(f"render_view could not establish a kernel-bound view identity: {exc}")

        try:
            store = self._store()
            manifest = store.register(
                artifact_path=str(artifact_path),
                identity=identity,
                title=str(title),
                summary=str(summary),
                workspace_root=self.get_project_root(),
                replaces_view_id=replaces_view_id,
                source_kind="generated",
                callable_tools=callable_tools,
            )
            entry, _ = store.resolve_entry(identity.session_id, manifest.view_id, manifest.revision)
            references = _BrowserStorageReferences()
            references.feed(entry.read_text(encoding="utf-8"))
            warnings = [
                f"Possible {api} call in an inline script: browser storage is unavailable in this sandbox. "
                "Use the Offline host integration example and reverie/view-state, then render a corrected replacement revision. "
                "Registration does not verify runtime behavior."
                for api in sorted(references.apis)
            ]
            desktop = getattr(self.context.get('agent'), 'runtime_surface', 'terminal') == 'desktop'
            if desktop and references.has_controls and not references.initializes_host:
                warnings.append(
                    'Host initialization is not evident in this artifact. Verify ui/initialize, '
                    'host theme updates and the Offline host integration example. Registration does not verify runtime behavior.'
                )
            if desktop and references.has_controls and not references.saves_state:
                warnings.append(
                    'Private state persistence is not evident in this artifact. Preserve meaningful inputs and selections '
                    'with reverie/view-state and verify reopening. Correct the artifact through a replacement revision if needed.'
                )
            if desktop and references.has_controls and references.initializes_host and (
                not references.has_capability_reference or references.has_empty_capability_literal
            ):
                warnings.append(
                    'A missing capability reference or empty capability literal was found in inline scripts. '
                    'Verify that initialized, state and every later host message include the actual capability returned '
                    'by ui/initialize at the top level. Preserve the complete '
                    'Offline host integration helper; registration does not verify runtime behavior.'
                )
        except ViewStoreError as exc:
            self._emit(
                "view_error",
                session_id=identity.session_id,
                turn_id=identity.turn_id,
                replaces_view_id=replaces_view_id,
                error=str(exc),
            )
            return ToolResult.fail(f"render_view rejected the artifact: {exc}")
        except Exception as exc:  # pragma: no cover - defensive
            self._emit(
                "view_error",
                session_id=identity.session_id,
                turn_id=identity.turn_id,
                error=str(exc),
            )
            return ToolResult.fail(f"render_view failed to store the artifact: {exc}")

        # Persist-before-publish: the revision is committed above; only now do we
        # announce it. The reference carries no HTML and no filesystem path.
        reference = manifest.model_reference()
        self._emit("view_ready", session_id=identity.session_id, turn_id=identity.turn_id,
                   committed_at=datetime.now(timezone.utc).isoformat(), **reference)

        output = (
            f'Interactive view ready: "{manifest.title}" '
            f"(view_id={manifest.view_id}, revision={manifest.revision}). "
            f"It is shown to the user in the Reverie view panel. "
            f"Summary: {manifest.summary}"
        )
        data = {"view": {"session_id": identity.session_id, "turn_id": identity.turn_id, **reference}}
        if warnings:
            output += "\nAuthoring warnings: " + " ".join(warnings)
            data["authoring_warnings"] = warnings
        return ToolResult.ok(output, data=data)
