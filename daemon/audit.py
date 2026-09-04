"""Every operation the daemon performed, on one line each — allowed AND refused.

This exists because the daemon is the one component that reads the user's own files, and "what did the agent
look at?" must have an answer that does not depend on anyone remembering. It is written for the person whose
files these are, not for debugging: one line per operation, with the path, the outcome, and who asked.

REFUSALS ARE LOGGED TOO, and that is the half that earns the file. A run of `outside_allowlist` refusals against
the same folder is the signal that something is probing the boundary — invisible if only successes were kept.

Append-only JSONL, best-effort, never raising: a full disk must not stop the daemon from answering, and an
audit write that could fail the operation would be an audit that gets removed the first time it does.
"""
from __future__ import annotations

import json
import os
import threading
import time

from .paths import audit_file

_LOCK = threading.Lock()

# Rotated at a size a person could still open. One generation kept: this is a recent-activity log, not an
# archive, and quietly filling the user's disk to prove we are careful would be its own kind of careless.
MAX_BYTES = 4 * 1024 * 1024


def record(op: str, *, caller: str = "local", path: str | None = None, outcome: str = "ok",
           reason: str | None = None, detail: dict | None = None) -> None:
    """Write one line. `caller` distinguishes the local engine over loopback from a cloud agent over the relay
    (P3) — the distinction the user cares about most, since only one of those is on their machine."""
    line = {
        "at": int(time.time()),
        "op": op,
        "caller": caller,
        "outcome": outcome,
    }
    if path:
        line["path"] = path
    if reason:
        line["reason"] = reason
    if detail:
        line["detail"] = detail
    try:
        with _LOCK:
            target = audit_file()
            try:
                if target.stat().st_size > MAX_BYTES:
                    os.replace(target, str(target) + ".1")
            except FileNotFoundError:
                pass
            with open(target, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(line, ensure_ascii=False) + "\n")
    except Exception:           # noqa: BLE001 — see the module docstring: logging never fails an operation
        pass


def tail(limit: int = 200) -> list[dict]:
    """The most recent entries, newest first. For the daemon panel in the frontend (P1) and for the operator's
    Master (P3) — the same one data, two surfaces, per the observability rule."""
    try:
        with open(audit_file(), encoding="utf-8") as fh:
            lines = fh.readlines()[-max(1, limit):]
    except Exception:           # noqa: BLE001 — no log yet is not an error
        return []
    out: list[dict] = []
    for raw in reversed(lines):
        try:
            out.append(json.loads(raw))
        except Exception:       # noqa: BLE001 — a torn last line after a crash: skip it
            continue
    return out
