"""Thread-safe controls received by the existing agent at safe boundaries."""
from __future__ import annotations

from collections import deque
import threading
import uuid
from typing import Any, Callable


class RunControl:
    def __init__(self, emit: Callable[[dict], None]) -> None:
        self.cancelled = threading.Event()
        self._condition = threading.Condition()
        self._paused = False
        self._messages: deque[dict] = deque()
        self.emit = emit

    def steer(self, content: Any, display: str) -> str:
        identity = uuid.uuid4().hex
        with self._condition:
            self._messages.append({"id": identity, "content": content, "display": display})
        self.emit({"type": "run.steer", "message_id": identity, "status": "waiting", "reason": "Waiting for a model request boundary; active commands are unchanged."})
        return identity

    def stop(self) -> None:
        self.cancelled.set()
        with self._condition:
            self._condition.notify_all()
        self.emit({"type": "run.control", "state": "stopping"})

    def pause(self, paused: bool) -> None:
        with self._condition:
            self._paused = paused
            self._condition.notify_all()
        self.emit({"type": "run.control", "state": "waiting_pause" if paused else "running"})

    def check_cancel(self) -> None:
        if self.cancelled.is_set():
            raise RuntimeError("Run stopped by user; check completed actions before continuing.")

    def safe_point(self, agent: Any, *, receive: bool = True) -> None:
        self.check_cancel()
        with self._condition:
            if self._paused:
                self.emit({"type": "run.control", "state": "paused"})
            while self._paused and not self.cancelled.is_set():
                self._condition.wait(timeout=0.2)
            self.check_cancel()
            pending = list(self._messages) if receive else []
            if receive:
                self._messages.clear()
        for item in pending:
            agent.messages.append({"role": "user", "content": item["content"]})
            self.emit({"type": "run.steer", "message_id": item["id"], "status": "received", "text": item["display"]})
        if pending:
            manager = agent.tool_executor.context.get("session_manager")
            if manager:
                manager.update_messages(agent.get_history())
