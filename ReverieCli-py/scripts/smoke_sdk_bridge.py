"""Verify the SDK bridge ready/shutdown JSONL contract."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
from typing import Sequence


def verify_sdk_bridge(command: Sequence[str], *, timeout: float = 30.0) -> list[dict]:
    request = {"id": "smoke", "action": "shutdown"}
    result = subprocess.run(
        list(command),
        input=json.dumps(request) + "\n",
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    messages = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
    if result.returncode != 0:
        raise RuntimeError(f"SDK bridge exited with {result.returncode}: {result.stderr.strip()}")
    if not any(message.get("type") == "ready" for message in messages):
        raise RuntimeError(f"SDK bridge did not emit ready: {messages}")
    if not any(message.get("type") == "shutdown" and message.get("id") == "smoke" for message in messages):
        raise RuntimeError(f"SDK bridge did not acknowledge shutdown: {messages}")
    if any(message.get("type") == "error" for message in messages):
        raise RuntimeError(f"SDK bridge emitted an error: {messages}")
    return messages


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--executable", type=Path)
    parser.add_argument("--timeout", type=float, default=30.0)
    args = parser.parse_args()
    command = [str(args.executable), "--sdk-bridge"] if args.executable else [sys.executable, "-m", "reverie", "--sdk-bridge"]
    messages = verify_sdk_bridge(command, timeout=args.timeout)
    print(json.dumps({"success": True, "messages": messages}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
