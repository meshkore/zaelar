"""nucleo/his_words.py — what the OPERATOR said, with when, readable by a door that runs minutes later.

A Brain Worker acts long after the turn that started it, in another process, and the only text it carries is
the brief the turn's model WROTE — which is not his words. `best-plumber-same-day__es` (2026-10-14): he asked
to FIND a well-rated plumber who can come today; the model's brief said «Buscar y contactar fontaneros», and
the worker added two real plumbers as contacts and tried to WhatsApp them. Whether an act was asked for has
to be read against what HE said, so this keeps it.

Fed from `nucleo/flash/dialog.push_user`, the one function both channels (voice and the text probe) call to
record his turn. `[SISTEMA]` notes glued in front of a turn are dropped first: a note that quotes a worker's
own question («¿escribo a Fontanero X?») must never become his words naming that recipient.

In-process and bounded on purpose. Lost on a restart, which fails toward ASKING: a door that cannot find his
words treats the act as not asked for.
"""
from __future__ import annotations

import threading
import time

_CAP = 64
_lock = threading.Lock()
_ring: list[tuple[float, str]] = []


def note(text: str, *, ts: float | None = None) -> None:
    """Record one operator turn. A turn that is only system notes records nothing."""
    try:
        from nucleo.acts.errand import strip_system_notes
        t = strip_system_notes(str(text or ""))
    except Exception:  # noqa: BLE001 — unreadable notes: keep nothing rather than a note as his words
        return
    t = (t or "").strip()
    if not t:
        return
    with _lock:
        if _ring and _ring[-1][1] == t:
            return
        _ring.append((float(ts if ts is not None else time.time()), t))
        del _ring[:-_CAP]


def since(ts: float) -> list[str]:
    """His turns recorded at or after `ts`, oldest first."""
    with _lock:
        return [t for (at, t) in _ring if at >= float(ts or 0)]


def reset() -> None:
    """Tests only."""
    with _lock:
        _ring.clear()
