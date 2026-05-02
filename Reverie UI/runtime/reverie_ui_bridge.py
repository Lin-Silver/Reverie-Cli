"""JSONL bridge between Reverie UI and the embedded Reverie Python runtime."""

from __future__ import annotations

import contextlib
import dataclasses
import json
import os
import sys
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Optional


RUNTIME_ROOT = Path(__file__).resolve().parent
if str(RUNTIME_ROOT) not in sys.path:
    sys.path.insert(0, str(RUNTIME_ROOT))

os.environ.setdefault("REVERIE_APP_ROOT", str(RUNTIME_ROOT / "appdata"))
OUT = sys.stdout
for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def emit(payload: Dict[str, Any]) -> None:
    OUT.write(json.dumps(json_safe(payload), ensure_ascii=False) + "\n")
    OUT.flush()


def json_safe(value: Any) -> Any:
    if dataclasses.is_dataclass(value):
        return json_safe(dataclasses.asdict(value))
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [json_safe(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def object_to_dict(value: Any, fields: Iterable[str]) -> Dict[str, Any]:
    return {field: json_safe(getattr(value, field, None)) for field in fields}


class ReverieUiBridge:
    def __init__(self) -> None:
        self.project_root = Path.cwd()
        self.interface = None
        self.last_activity = ""

    def dispatch(self, message: Dict[str, Any]) -> None:
        action = str(message.get("action", "") or "").strip()
        request_id = message.get("id")
        payload = message.get("payload") if isinstance(message.get("payload"), dict) else {}
        if not action:
            emit({"id": request_id, "type": "error", "error": "Missing action."})
            return

        handlers: Dict[str, Callable[[Any, Dict[str, Any]], None]] = {
            "hello": self.handle_hello,
            "initialize": self.handle_initialize,
            "getState": self.handle_get_state,
            "setWorkspace": self.handle_set_workspace,
            "setMode": self.handle_set_mode,
            "saveModel": self.handle_save_model,
            "deleteModel": self.handle_delete_model,
            "selectModel": self.handle_select_model,
            "chat": self.handle_chat,
            "indexWorkspace": self.handle_index_workspace,
            "newSession": self.handle_new_session,
            "switchSession": self.handle_switch_session,
            "deleteSession": self.handle_delete_session,
            "clearSession": self.handle_clear_session,
            "listTools": self.handle_list_tools,
            "diagnostics": self.handle_diagnostics,
            "shutdown": self.handle_shutdown,
        }

        handler = handlers.get(action)
        if handler is None:
            emit({"id": request_id, "type": "error", "error": f"Unknown action: {action}"})
            return

        try:
            with contextlib.redirect_stdout(sys.stderr):
                handler(request_id, payload)
        except SystemExit:
            raise
        except Exception as exc:
            traceback.print_exc(file=sys.stderr)
            emit({"id": request_id, "type": "error", "error": str(exc)})

    def ensure_interface(self, project_root: Optional[Path] = None) -> Any:
        from reverie.cli.interface import ReverieInterface

        root = Path(project_root or self.project_root).expanduser().resolve()
        if not root.exists() or not root.is_dir():
            raise ValueError(f"Workspace does not exist: {root}")

        if self.interface is None or Path(self.project_root).resolve() != root:
            self.project_root = root
            self.interface = ReverieInterface(root, headless=True)
        return self.interface

    def summarize_config(self) -> Dict[str, Any]:
        from reverie.modes import get_mode_display_name, list_modes

        interface = self.ensure_interface()
        config = interface.config_manager.load()
        active_model = config.active_model
        models = []
        for index, model in enumerate(getattr(config, "models", []) or []):
            item = object_to_dict(
                model,
                (
                    "model",
                    "model_display_name",
                    "base_url",
                    "provider",
                    "endpoint",
                    "thinking_mode",
                    "max_context_tokens",
                    "custom_headers",
                ),
            )
            item["index"] = index
            item["has_api_key"] = bool(getattr(model, "api_key", ""))
            models.append(item)

        return {
            "mode": getattr(config, "mode", "reverie"),
            "mode_display_name": get_mode_display_name(getattr(config, "mode", "reverie")),
            "modes": [
                {"id": mode, "name": get_mode_display_name(mode)}
                for mode in list_modes(include_computer=True, switchable_only=False)
            ],
            "stream_responses": bool(getattr(config, "stream_responses", True)),
            "auto_index": bool(getattr(config, "auto_index", True)),
            "active_model_source": getattr(config, "active_model_source", "standard"),
            "active_model_index": int(getattr(config, "active_model_index", 0) or 0),
            "active_model": object_to_dict(
                active_model,
                ("model", "model_display_name", "base_url", "provider", "endpoint", "thinking_mode", "max_context_tokens"),
            )
            if active_model
            else None,
            "models": models,
            "config_path": str(interface.config_manager.config_path),
            "app_root": str(interface.config_manager.app_root),
        }

    def summarize_sessions(self) -> Dict[str, Any]:
        interface = self.ensure_interface()
        sessions = [
            object_to_dict(item, ("id", "name", "created_at", "updated_at", "message_count"))
            for item in interface.session_manager.list_sessions()
        ]
        current = interface.session_manager.get_current_session()
        if current is None:
            current = interface.session_manager.restore_last_session()
        return {
            "current_session_id": getattr(current, "id", ""),
            "current_session_name": getattr(current, "name", ""),
            "sessions": sessions,
            "messages": self.summarize_messages(getattr(current, "messages", []) if current else []),
        }

    def summarize_messages(self, messages: Iterable[Dict[str, Any]]) -> list[Dict[str, Any]]:
        summarized = []
        for message in messages or []:
            role = str(message.get("role", "") or "")
            content = message.get("content", "")
            if isinstance(content, list):
                text_parts = []
                for part in content:
                    if isinstance(part, dict):
                        text_parts.append(str(part.get("text") or part.get("content") or ""))
                    else:
                        text_parts.append(str(part))
                content = "\n".join(part for part in text_parts if part).strip()
            summarized.append({"role": role, "content": str(content or "")})
        return summarized[-80:]

    def summarize_tools(self, mode: Optional[str] = None) -> list[Dict[str, Any]]:
        from reverie.tools.registry import get_tool_registrations

        config = self.ensure_interface().config_manager.load()
        active_mode = mode or getattr(config, "mode", "reverie")
        tools = []
        for registration in get_tool_registrations(include_hidden=True):
            tool_class = registration.tool_class
            tools.append(
                {
                    "name": registration.name,
                    "description": str(getattr(tool_class, "description", "") or "").strip(),
                    "category": str(getattr(tool_class, "tool_category", "general") or "general"),
                    "tags": list(getattr(tool_class, "tool_tags", ()) or ()),
                    "visible": bool(registration.expose_schema and registration.enabled_in_mode(active_mode)),
                    "read_only": bool(getattr(tool_class, "read_only", False)),
                    "destructive": bool(getattr(tool_class, "destructive", False)),
                    "supported_modes": registration.supported_modes(include_hidden=True),
                }
            )
        return tools

    def emit_state(self, request_id: Any, event_type: str = "state") -> None:
        emit(
            {
                "id": request_id,
                "type": event_type,
                "project_root": str(self.project_root),
                "config": self.summarize_config(),
                "sessions": self.summarize_sessions(),
                "tools": self.summarize_tools(),
            }
        )

    def handle_hello(self, request_id: Any, payload: Dict[str, Any]) -> None:
        emit({"id": request_id, "type": "ready", "runtime_root": str(RUNTIME_ROOT), "python": sys.version})

    def handle_initialize(self, request_id: Any, payload: Dict[str, Any]) -> None:
        root = Path(str(payload.get("projectRoot") or self.project_root)).expanduser()
        self.ensure_interface(root)
        self.emit_state(request_id)

    def handle_get_state(self, request_id: Any, payload: Dict[str, Any]) -> None:
        self.ensure_interface()
        self.emit_state(request_id)

    def handle_set_workspace(self, request_id: Any, payload: Dict[str, Any]) -> None:
        root = Path(str(payload.get("projectRoot") or "")).expanduser()
        self.ensure_interface(root)
        self.emit_state(request_id)

    def handle_set_mode(self, request_id: Any, payload: Dict[str, Any]) -> None:
        from reverie.modes import normalize_mode

        interface = self.ensure_interface()
        config = interface.config_manager.load()
        config.mode = normalize_mode(payload.get("mode") or "reverie")
        interface.config_manager.save(config)
        if interface.agent is not None:
            interface._init_agent(config_override=config, persist_config_changes=False)
        self.emit_state(request_id)

    def handle_save_model(self, request_id: Any, payload: Dict[str, Any]) -> None:
        from reverie.config import ModelConfig

        interface = self.ensure_interface()
        config = interface.config_manager.load()
        index = payload.get("index")
        model = ModelConfig(
            model=str(payload.get("model") or "").strip(),
            model_display_name=str(payload.get("model_display_name") or payload.get("model") or "").strip(),
            base_url=str(payload.get("base_url") or "").strip(),
            api_key=str(payload.get("api_key") or "").strip(),
            max_context_tokens=int(payload.get("max_context_tokens") or 128000),
            provider=str(payload.get("provider") or "openai-sdk").strip(),
            endpoint=str(payload.get("endpoint") or "").strip(),
            thinking_mode=payload.get("thinking_mode") or None,
            custom_headers=payload.get("custom_headers") if isinstance(payload.get("custom_headers"), dict) else {},
        )

        if index is None or int(index) < 0 or int(index) >= len(config.models):
            config.models.append(model)
            config.active_model_index = len(config.models) - 1
        else:
            config.models[int(index)] = model
            config.active_model_index = int(index)
        config.active_model_source = "standard"
        interface.config_manager.save(config)
        self.emit_state(request_id)

    def handle_delete_model(self, request_id: Any, payload: Dict[str, Any]) -> None:
        interface = self.ensure_interface()
        index = int(payload.get("index") or -1)
        ok = interface.config_manager.remove_model(index)
        emit({"id": request_id, "type": "model.deleted", "success": ok})
        self.emit_state(request_id, event_type="state")

    def handle_select_model(self, request_id: Any, payload: Dict[str, Any]) -> None:
        interface = self.ensure_interface()
        index = int(payload.get("index") or 0)
        ok = interface.config_manager.set_active_model(index)
        emit({"id": request_id, "type": "model.selected", "success": ok})
        self.emit_state(request_id, event_type="state")

    def handle_new_session(self, request_id: Any, payload: Dict[str, Any]) -> None:
        interface = self.ensure_interface()
        name = str(payload.get("name") or "").strip() or f"GUI Session {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        session = interface.session_manager.create_session(name=name)
        if interface.agent is not None:
            interface.agent.set_history(session.messages)
        self.emit_state(request_id)

    def handle_switch_session(self, request_id: Any, payload: Dict[str, Any]) -> None:
        interface = self.ensure_interface()
        session = interface.session_manager.load_session(str(payload.get("sessionId") or ""))
        if session is None:
            raise ValueError("Session not found.")
        if interface.agent is not None:
            interface.agent.set_history(session.messages)
        self.emit_state(request_id)

    def handle_delete_session(self, request_id: Any, payload: Dict[str, Any]) -> None:
        interface = self.ensure_interface()
        ok = interface.session_manager.delete_session(str(payload.get("sessionId") or ""))
        emit({"id": request_id, "type": "session.deleted", "success": ok})
        self.emit_state(request_id, event_type="state")

    def handle_clear_session(self, request_id: Any, payload: Dict[str, Any]) -> None:
        interface = self.ensure_interface()
        session = interface.session_manager.get_current_session()
        if session is None:
            session, _ = interface.session_manager.ensure_session()
        session.messages = []
        interface.session_manager.save_session(session)
        if interface.agent is not None:
            interface.agent.set_history([])
        self.emit_state(request_id)

    def handle_list_tools(self, request_id: Any, payload: Dict[str, Any]) -> None:
        emit({"id": request_id, "type": "tools", "tools": self.summarize_tools(payload.get("mode"))})

    def handle_diagnostics(self, request_id: Any, payload: Dict[str, Any]) -> None:
        interface = self.ensure_interface()
        config = interface.config_manager.load()
        active_model = config.active_model
        emit(
            {
                "id": request_id,
                "type": "diagnostics",
                "items": [
                    {"label": "Workspace", "value": str(self.project_root), "ok": self.project_root.exists()},
                    {"label": "Config", "value": str(interface.config_manager.config_path), "ok": True},
                    {"label": "Active model", "value": getattr(active_model, "model_display_name", "") if active_model else "not configured", "ok": bool(active_model)},
                    {"label": "Runtime", "value": str(RUNTIME_ROOT), "ok": True},
                    {"label": "Python", "value": sys.version.split()[0], "ok": True},
                ],
            }
        )

    def handle_index_workspace(self, request_id: Any, payload: Dict[str, Any]) -> None:
        from reverie.config import get_project_data_dir
        from reverie.context_engine import CodebaseIndexer

        root = Path(str(payload.get("projectRoot") or self.project_root)).expanduser().resolve()
        self.ensure_interface(root)
        emit({"id": request_id, "type": "index.started", "project_root": str(root)})

        def progress(snapshot: Any) -> None:
            emit(
                {
                    "id": request_id,
                    "type": "index.progress",
                    "stage": getattr(snapshot, "stage", ""),
                    "message": getattr(snapshot, "message", ""),
                    "percent": getattr(snapshot, "display_percent", getattr(snapshot, "percent", 0.0)),
                    "current_file": getattr(snapshot, "current_file", ""),
                    "files_scanned": getattr(snapshot, "files_scanned", 0),
                    "files_parsed": getattr(snapshot, "files_parsed", 0),
                    "files_failed": getattr(snapshot, "files_failed", 0),
                    "files_skipped": getattr(snapshot, "files_skipped", 0),
                }
            )

        indexer = CodebaseIndexer(root, cache_dir=get_project_data_dir(root) / "context_cache")
        result = indexer.full_index(progress_callback=progress)
        emit(
            {
                "id": request_id,
                "type": "index.complete",
                "result": object_to_dict(
                    result,
                    (
                        "files_scanned",
                        "files_parsed",
                        "files_failed",
                        "files_skipped",
                        "symbols_extracted",
                        "dependencies_extracted",
                        "parse_time_ms",
                        "total_time_ms",
                        "total_bytes",
                        "errors",
                        "warnings",
                        "fatal_errors",
                    ),
                ),
                "success": bool(getattr(result, "success", False)),
            }
        )

    def handle_chat(self, request_id: Any, payload: Dict[str, Any]) -> None:
        from reverie.agent import STREAM_EVENT_MARKER, THINKING_END_MARKER, THINKING_START_MARKER, decode_stream_event
        from reverie.agent.agent import HIDDEN_STREAM_TOKEN

        prompt = str(payload.get("message") or "").strip()
        if not prompt:
            raise ValueError("Message is empty.")

        interface = self.ensure_interface(Path(str(payload.get("projectRoot") or self.project_root)))
        config = interface.config_manager.load()
        if payload.get("mode"):
            from reverie.modes import normalize_mode

            config.mode = normalize_mode(payload.get("mode"))
        config.stream_responses = True

        emit({"id": request_id, "type": "chat.started"})
        interface._runtime_config_override = interface._clone_config(config)
        try:
            interface._init_agent(config_override=config, persist_config_changes=False)
            if interface.agent is None:
                raise ValueError("No active model is configured.")

            session_id = str(payload.get("sessionId") or "")
            session = interface.session_manager.load_session(session_id) if session_id else None
            if session is None:
                session, _ = interface.session_manager.ensure_session()

            interface._sync_workspace_memory_message(session)
            interface.agent.set_history(session.messages)
            context_ready = interface.ensure_context_engine(announce=False)
            emit({"id": request_id, "type": "chat.context", "context_engine_initialized": bool(context_ready)})

            thinking = False
            response_text = []
            for chunk in interface.agent.process_message(prompt, stream=True, session_id=session.id, user_display_text=prompt):
                if chunk == THINKING_START_MARKER:
                    thinking = True
                    emit({"id": request_id, "type": "chat.thinking.start"})
                    continue
                if chunk == THINKING_END_MARKER:
                    thinking = False
                    emit({"id": request_id, "type": "chat.thinking.end"})
                    continue
                if chunk == HIDDEN_STREAM_TOKEN:
                    continue

                event = decode_stream_event(chunk) if isinstance(chunk, str) and chunk.startswith(STREAM_EVENT_MARKER) else None
                if event is not None:
                    emit({"id": request_id, "type": "chat.tool", "event": event})
                    continue

                event_type = "chat.thinking" if thinking else "chat.chunk"
                if not thinking:
                    response_text.append(chunk)
                emit({"id": request_id, "type": event_type, "chunk": chunk})

            interface.session_manager.update_messages(interface.agent.get_history())
            emit(
                {
                    "id": request_id,
                    "type": "chat.complete",
                    "message": "".join(response_text),
                    "session": object_to_dict(session, ("id", "name", "created_at", "updated_at")),
                }
            )
            self.emit_state(request_id, event_type="state")
        finally:
            interface._runtime_config_override = None

    def handle_shutdown(self, request_id: Any, payload: Dict[str, Any]) -> None:
        emit({"id": request_id, "type": "shutdown"})
        raise SystemExit(0)


def main() -> int:
    bridge = ReverieUiBridge()
    emit({"type": "ready", "runtime_root": str(RUNTIME_ROOT), "python": sys.version})
    for raw in sys.stdin:
        line = raw.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except Exception as exc:
            emit({"type": "error", "error": f"Invalid JSON: {exc}"})
            continue
        bridge.dispatch(message if isinstance(message, dict) else {})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
