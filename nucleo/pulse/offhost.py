"""nucleo/pulse/offhost.py — an incident stays auditable after the host that had it (V2-831 T-31, engine half).

Events live in this host's own database, so a host that froze took the record of its last minutes with it. When a
deployment sets `ZAELAR_SUMMARY_URL`, a THREAD (it keeps running while the event loop is frozen) POSTs a compact
summary of the last `summary_push_s` there, continuously: turns, the voice's worst lag, the workers, free memory and
the self watchdog's state — counts and numbers only, never words, a transcript or a credential. With
`ZAELAR_SUMMARY_TOKEN` set it rides as a bearer token. Without the URL nothing starts. A push that fails is logged
and the next one carries on; the summary is never stored or queued here.
"""
from __future__ import annotations

import json
import os
import threading
import time
import urllib.request

from loguru import logger

_DEFAULT_PERIOD_S = 30.0
_TIMEOUT_S = 5.0
_state: dict = {"seen": 0, "thread": None, "stop": None, "fails": 0}


def target() -> str:
    return os.getenv("ZAELAR_SUMMARY_URL", "").strip()


def period_s() -> float:
    from nucleo.workers import envelope
    return float(envelope.policy().get("summary_push_s", _DEFAULT_PERIOD_S))


def _turns() -> dict:
    """His turns since the last summary, read from the observer's ring by event kind (never by words)."""
    from voice import observer
    evs = list(observer._events)
    new = [e for e in evs if int(e.get("i") or 0) > _state["seen"]]
    _state["seen"] = max([_state["seen"], *(int(e.get("i") or 0) for e in new)])
    turns = [e for e in new if e.get("kind") == "trace"]
    failed = [e for e in new if e.get("kind") == "brain" and "fail" in str(e.get("kind_diag") or "")]
    return {"turns": len(turns), "turn_failures": len(failed),
            "last_turn_ms": max([0, *(int(e.get("t_ms") or 0) for e in turns)])}


def summary() -> dict:
    """The compact summary, now. Each part read on its own: one unreadable part never hides the others."""
    from nucleo.runtime_ids import boot_id
    out: dict = {"at_ms": round(time.time() * 1000), "boot": boot_id()}
    try:
        import version
        out["build"] = version.build()
    except Exception as e:  # noqa: BLE001
        out["build_error"] = repr(e)[:80]
    for name, read in (("activity", _turns), ("voice", _voice), ("workers", _workers), ("host", _host),
                       ("watchdog", _watchdog)):
        try:
            out[name] = read()
        except Exception as e:  # noqa: BLE001 — the part says it was unreadable
            out[name] = {"error": repr(e)[:120]}
    return out


def _voice() -> dict:
    from voice import lag
    worst, lag._state["worst"] = float(lag._state.get("worst") or 0.0), 0.0     # the worst SINCE the last summary
    return {"worst_lag_s": round(worst, 3), "lag_bound_s": lag.bound_s()}


def _workers() -> dict:
    from nucleo import dispatch
    recs = list(dispatch._SESSIONS.values())
    return {"live": sum(1 for r in recs if getattr(r, "status", "") in dispatch.LIVE_SESSION_STATES),
            "paused": sum(1 for r in recs if getattr(r, "paused", False))}


def _host() -> dict:
    from nucleo.workers import envelope
    total, avail = envelope.measured()
    return {"free_ratio": round(avail / total, 3) if total else None, "total_mb": total // (1 << 20)}


def _watchdog() -> dict:
    from nucleo.pulse import self_watchdog as wd
    beat = float(wd._state.get("beat") or 0.0)
    return {"loop_age_s": round(time.monotonic() - beat, 1) if beat else None,
            "unhealthy_s": round(time.monotonic() - wd._state["since"], 1) if wd._state.get("since") else 0.0,
            "exiting": bool(wd._state.get("exiting"))}


def push(url: str | None = None) -> bool:
    """POST one summary. True when the target took it (2xx). Never raises."""
    url = url or target()
    if not url:
        return False
    headers = {"content-type": "application/json"}
    if tok := os.getenv("ZAELAR_SUMMARY_TOKEN", "").strip():
        headers["authorization"] = f"Bearer {tok}"
    req = urllib.request.Request(url, data=json.dumps(summary()).encode(), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT_S) as r:   # noqa: S310 — the deployment's own URL
            ok = 200 <= r.status < 300
    except Exception as e:  # noqa: BLE001 — the next push carries on
        ok = False
        logger.warning(f"offhost: summary not taken ({type(e).__name__}): the next one carries on")
    _state["fails"] = 0 if ok else _state["fails"] + 1
    return ok


def start() -> bool:
    """Start pushing when a target is set. Idempotent; never raises."""
    if _state["thread"] is not None or not target():
        return False
    stop_ev = threading.Event()

    def run():
        while not stop_ev.wait(period_s()):
            push()
    _state.update(stop=stop_ev, thread=threading.Thread(target=run, name="offhost-summary", daemon=True))
    _state["thread"].start()
    return True


def stop() -> None:
    if _state["stop"] is not None:
        _state["stop"].set()
    _state.update(thread=None, stop=None)
