"""Small helper framework for Reverie CLI runtime plugin executables."""

from __future__ import annotations

from typing import Any
import json
import sys


class ReverieRuntimePluginHost:
    """Base host that implements the fixed `-RC` / `-RC-CALL` protocol shell."""

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
                return self.write_json(
                    {
                        "success": False,
                        "output": "",
                        "error": "Usage: -RC-CALL <command> <json-payload>",
                        "data": {},
                    }
                )

            command_name = str(argv[2] or "").strip().lower()
            raw_payload = str(argv[3] or "").strip()
            try:
                payload = json.loads(raw_payload) if raw_payload else {}
            except Exception as exc:
                return self.write_json(
                    {
                        "success": False,
                        "output": "",
                        "error": f"Invalid JSON payload: {exc}",
                        "data": {},
                    }
                )

            try:
                result = self.handle_command(command_name, payload)
            except Exception as exc:
                result = {
                    "success": False,
                    "output": "",
                    "error": str(exc),
                    "data": {},
                }
            if not isinstance(result, dict):
                result = {
                    "success": False,
                    "output": "",
                    "error": "Plugin command handler must return a JSON object.",
                    "data": {},
                }
            result.setdefault("success", False)
            result.setdefault("output", "")
            result.setdefault("error", "")
            result.setdefault("data", {})
            return self.write_json(result)

        sys.stderr.write("This runtime plugin only supports -RC and -RC-CALL.\n")
        return 1
