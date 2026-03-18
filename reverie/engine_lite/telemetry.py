"""Runtime telemetry utilities for Reverie Engine Lite."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict
import json


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class TelemetryRecorder:
    """Collects deterministic runtime events for smoke and playtest analysis."""

    build_id: str = "dev"
    session_id: str = "session"
    events: list[Dict[str, Any]] = field(default_factory=list)
    metrics: Dict[str, float] = field(default_factory=dict)

    def log_event(self, name: str, **fields: Any) -> None:
        self.events.append(
            {
                "timestamp": utc_timestamp(),
                "event": str(name),
                "build_id": self.build_id,
                "session_id": self.session_id,
                **fields,
            }
        )

    def increment(self, metric: str, amount: float = 1.0) -> None:
        self.metrics[str(metric)] = self.metrics.get(str(metric), 0.0) + float(amount)

    def summary(self) -> Dict[str, Any]:
        counters: Dict[str, int] = {}
        for event in self.events:
            event_name = str(event.get("event", "unknown"))
            counters[event_name] = counters.get(event_name, 0) + 1
        return {
            "event_count": len(self.events),
            "events_by_name": counters,
            "metrics": dict(self.metrics),
        }

    def flush(self, output_path: str | Path) -> Path:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "build_id": self.build_id,
            "session_id": self.session_id,
            "events": self.events,
            "metrics": self.metrics,
        }
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        return path
