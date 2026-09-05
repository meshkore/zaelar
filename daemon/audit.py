"""Every operation the daemon performed, on one line each — allowed AND refused.

This exists because the daemon is the one component that reads the user's own files, and "what did the agent
look at?" must have an answer that does not depend on anyone remembering. It is written for the person whose
files these are, not for debugging: one line per operation, with the path, the outcome, and who asked.

REFUSALS ARE LOGGED TOO, and that is the half that earns the file. A run of `outside_allowlist` against the same
folder is the signal that something is probing the boundary, and a run of `bad_token` is the signal that
something is trying to talk to the daemon that has no business doing so — both invisible if only successes were
kept. The HTTP layer collapses floods (see `daemon.security.throttle`) rather than dropping them, so a noisy
attacker cannot push the interesting line off the end of a rotated log.

IT IS ITSELF SENSITIVE. A list of every path the user's agent opened is a map of their life, so the file is
created 0600 like the config beside it — the log of what was protected must not be the thing that leaks.

Append-only JSONL, best-effort, never raising: a full disk must not stop the daemon from answering, and an audit
write that could fail the operation would be an audit that gets removed the first time it does.
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

# Reading the tail seeks to the end rather than loading the file. `readlines()` on a 4 MB log allocated the
# whole thing on every `/audit` call — for a panel that wants the last screenful.
_BYTES_PER_LINE_GUESS = 512
_TAIL_MAX_BYTES = 2 * 1024 * 1024


def record(op: str, *, caller: str = "local", path: str | None = None, outcome: str = "ok",
           reason: str | None = None, detail: dict | None = None) -> None:
    """Write one line. `caller` distinguishes the local engine over loopback from a cloud agent over the relay —
    the distinction the user cares about most, since only one of those is on their machine."""
    line = {"at": int(time.time()), "op": op, "caller": caller, "outcome": outcome}
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
            existed = target.exists()
            with open(target, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(line, ensure_ascii=False) + "\n")
            if not existed:
                # 0600 at creation, not later: between `open` and a `chmod` the file exists under the umask,
                # and the first thing written to it is already a path the user may not want shared.
                try:
                    os.chmod(target, 0o600)
                except Exception:       # noqa: BLE001 — no-op on Windows, where the ACL is per-user already
                    pass
    except Exception:           # noqa: BLE001 — see the module docstring: logging never fails an operation
        pass


def tail(limit: int = 200) -> list[dict]:
    """The most recent entries, newest first. For the daemon panel in the frontend and for the operator's
    console — one datum, two surfaces."""
    limit = max(1, int(limit))
    want = min(_TAIL_MAX_BYTES, limit * _BYTES_PER_LINE_GUESS)
    try:
        target = audit_file()
        size = target.stat().st_size
        with open(target, "rb") as fh:
            if size > want:
                fh.seek(size - want)
                fh.readline()       # the first line of a mid-file seek is a fragment; drop it
            raw = fh.read()
    except Exception:           # noqa: BLE001 — no log yet is not an error
        return []

    out: list[dict] = []
    for line in reversed(raw.decode("utf-8", errors="replace").splitlines()):
        if len(out) >= limit:
            break
        try:
            out.append(json.loads(line))
        except Exception:       # noqa: BLE001 — a torn last line after a crash: skip it
            continue
    return out
