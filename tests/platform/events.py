"""Append-only event protocol shared by every Zaelar test runner.

The file is deliberately JSONL: a run remains readable after crashes, can be tailed
without a database, and is easy for Codex/Claude/CI to consume directly.
"""
from __future__ import annotations

import json
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
_SENSITIVE_KEYS = {"api_key", "authorization", "cookie", "password", "passphrase", "secret", "token"}


def _redact(value: Any, key: str = "") -> Any:
    if key.lower() in _SENSITIVE_KEYS or any(part in key.lower() for part in ("password", "passphrase", "token")):
        return "[redacted]"
    if isinstance(value, dict):
        return {str(k): _redact(v, str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact(v) for v in value]
    if isinstance(value, tuple):
        return [_redact(v) for v in value]
    return value


class EventWriter:
    """Process-safe-enough append writer (one complete line per O_APPEND write)."""

    def __init__(self, run_dir: str | os.PathLike[str], *, run_id: str | None = None) -> None:
        self.run_dir = Path(run_dir)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.run_dir / "events.jsonl"
        self.run_id = run_id or self.run_dir.name
        self._lock = threading.Lock()

    def emit(self, event_type: str, **fields: Any) -> dict[str, Any]:
        event = {
            "schema": SCHEMA_VERSION,
            "event_id": uuid.uuid4().hex,
            "run_id": self.run_id,
            "ts": time.time(),
            "type": event_type,
            **_redact(fields),
        }
        raw = (json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
        with self._lock:
            fd = os.open(self.path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
            try:
                os.write(fd, raw)
            finally:
                os.close(fd)
        return event


def read_events(run_dir: str | os.PathLike[str]) -> list[dict[str, Any]]:
    path = Path(run_dir) / "events.jsonl"
    if not path.exists():
        return []
    events: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return events
