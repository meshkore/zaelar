"""nucleo/workers/taint.py — a worker session's taint, read by every exit door it reaches (V2-851 F2, §4a).

Consent measures the OPERATOR's permission; taint measures PROVENANCE: whether this session has put a stranger's text
in front of its model (a web search, a page read, a browser page, an inbound message or mail, a network agent's
answer) since its last confirmed act. The mark lives in `nucleo/untrusted.py` (per session, extended — never forked);
this module is the worker side of it:

  · `during(rec)` wraps one act of the session: every `untrusted.seen()` inside marks THIS session (so a worker's
    read no longer taints his own voice sends), and an act that crossed a thread is caught by `untrusted.marks()`;
  · `mark(rec, source)` — a door that hands the worker unfenced third-party text says so (the browser, recall);
  · `tainted(rec)` — what the exits read; `cleared(rec)` — his yes to one of its acts.

The flag is shadowed on the task row (artefact slot `taint`, through the ledger) so a restart — or a session resumed
after its process ended — still asks: an unknown flag reads the row, and an unreadable row reads tainted only when it
says so (a session that never read a stranger's text is not stopped by a missing row).
"""
from __future__ import annotations

import contextlib

from loguru import logger

from nucleo import untrusted

SLOT = "taint"


def key_of(rec) -> str:
    """The session's key: its task row id, else its dispatch id."""
    return str(getattr(rec, "uid", "") or getattr(rec, "task_id", "") or "")


def _keep(rec, value: bool, source: str = "") -> None:
    uid = str(getattr(rec, "uid", "") or "")
    if not uid:
        return
    try:
        from nucleo.circuit import ledger
        ledger.store().artifact_put(uid, SLOT, {"tainted": bool(value), "source": str(source or "")})
    except Exception as e:  # noqa: BLE001 — the in-process flag still stands
        logger.debug(f"workers.taint: row not written ({e!r})")


def mark(rec, source: str) -> None:
    """This session consumed a stranger's text (`source` names the door)."""
    key = key_of(rec)
    if not key:
        return
    untrusted.seen(session_key=key)
    _keep(rec, True, source)


def tainted(rec) -> bool:
    key = key_of(rec)
    if not key:
        return False
    if untrusted.known(key):
        return untrusted.tainted(key)
    uid = str(getattr(rec, "uid", "") or "")
    if not uid:
        return False
    try:
        from nucleo.circuit import ledger
        got = ledger.artifact(uid, SLOT)
        return bool(isinstance(got, dict) and got.get("tainted"))
    except Exception as e:  # noqa: BLE001
        logger.debug(f"workers.taint: row unread ({e!r})")
        return False


def cleared(rec) -> None:
    """His yes to an act of this session: what it read before is behind his confirmation."""
    key = key_of(rec)
    if key:
        untrusted.cleared(key)
        _keep(rec, False, "his yes")


@contextlib.contextmanager
def during(rec, source: str = "act"):
    """One act of the session: a stranger's text it renders marks the session (and its row)."""
    key = key_of(rec)
    before = untrusted.marks()
    with untrusted.session(key):
        yield
    if key and untrusted.marks() > before:
        mark(rec, source)
