"""nucleo/wake.py — tell the deployment when this engine must be awake for its next notice (V2-796).

The loop that fires notices lives inside this process. A deployment that stops an idle engine (scale-to-zero
containers) would otherwise sleep straight through a reminder set for next Tuesday: the job is stored correctly
and never fires, because nothing is running to fire it.

So after any change to the schedule, the engine reports its NEXT due instant to a wake endpoint, and the deployment
starts the process a little before it. The mechanism, nothing more:

  * `ZAELAR_WAKE_URL` — POST `{"next_due": <epoch s | null>}` there;
  * otherwise `CONTROL_PLANE_URL` + `/wake`, when `CONTROL_PLANE_SERVICE_TOKEN` is set too (same `X-Service-Token`
    header the engine already sends there).
With neither, this module does nothing — a self-hosted engine that is always on has no use for it.

Debounced: `note_changed()` only marks the report as stale; `flush()` (one call per loop pulse) sends at most one
report every `_MIN_GAP_S`, and only when the value changed. A failed report is retried on the next pulse that is
due — never raised into the loop.
"""
from __future__ import annotations

import logging
import os
import time

logger = logging.getLogger("zaelar.wake")

_MIN_GAP_S = 10.0
_RETRY_S = 120.0
_UNSET = object()
_state = dict(dirty=True, sent=_UNSET, last=0.0)


def url() -> tuple[str, str]:
    """(endpoint, token) — ("", "") when this deployment has nowhere to report to."""
    explicit = (os.getenv("ZAELAR_WAKE_URL") or "").strip()
    token = (os.getenv("CONTROL_PLANE_SERVICE_TOKEN") or "").strip()
    if explicit:
        return explicit, token
    cp = (os.getenv("CONTROL_PLANE_URL") or "").strip().rstrip("/")
    if cp and token:
        return cp + "/wake", token
    return "", ""


def note_changed() -> None:
    _state["dirty"] = True


async def flush(now: float | None = None) -> bool:
    """Send the next due instant if it is stale. True when a report was sent and accepted."""
    now = time.time() if now is None else now
    if not _state["dirty"] or now - _state["last"] < _MIN_GAP_S:
        return False
    endpoint, token = url()
    if not endpoint:
        _state["dirty"] = False
        return False
    from nucleo.pulse import scheduler
    try:
        nxt = scheduler.next_due()
    except Exception as e:  # noqa: BLE001
        logger.debug(f"wake: next_due unreadable: {e!r}")
        return False
    value = int(nxt) if nxt else None
    if value == _state["sent"]:
        _state["dirty"] = False
        return False
    _state["last"] = now
    try:
        import httpx
        async with httpx.AsyncClient(timeout=5.0) as c:
            r = await c.post(endpoint, json={"next_due": value},
                             headers={"X-Service-Token": token} if token else {})
        ok = r.status_code < 300
    except Exception as e:  # noqa: BLE001
        logger.warning(f"wake: report failed, retried later: {e!r}")
        ok = False
    if ok:
        _state.update({"dirty": False, "sent": value})
    else:
        _state["last"] = now - _MIN_GAP_S + _RETRY_S     # back off a couple of minutes, stay dirty
    return ok


def _reset_for_tests() -> None:
    _state.update(dirty=True, sent=_UNSET, last=0.0)
