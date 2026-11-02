"""nucleo/circuit/continuation.py — a relaunch is judged by its COMMISSION's end state (V2-835 T4).

search-buy-used-car ES (2026-11-02): worker:1 was born with its spec on the task row; the provider relay relaunched onto
the next tier carrying the `task_uid` but not the `done_when`, the fresh record never read the row, and the circuit
judged the errand `undeclared` — nothing measured whether it was done. The same hole was open on the blown-context
handoff, the stall restart and the rate-limit retry.

Carrying `done_when` in each caller's context was the alternative, and it is the bug: a rule every caller must
remember is not a rule. Every relaunch carries the `task_uid` and is recorded at one door (`ledger.opened`, its
continuation branch included), which hands it to `spec.born` — and `born` asks THIS module first. The row holds the
end state AND its `tries`, so the retry budget is neither reset nor burned, and it survives a restart.

The second half is the same lie seen from the other side: a follow-up commission that INHERITED the sheet of an
errand that just ended was born with `results.empty = false` already true — rows somebody else found — and the pulse
settled it «met and verified» half a second in. Such an end state is never read as met (`mark_met_at_birth`).
"""
from __future__ import annotations

import copy
import json
import time

from loguru import logger


def continues(rec, ctx: dict | None) -> bool:
    uid = str(getattr(rec, "uid", "") or "")
    return bool(uid) and str((ctx or {}).get("task_uid") or "") == uid


def _row_entry(rec, uid: str) -> dict | None:
    """The live entry this process still holds (its `tries` are the ones `close` counts), else the row's, restored."""
    from nucleo.circuit import spec as _spec
    e = next((x for x in _spec._OPEN if x.get("task_id") == uid and _spec._is_started(x)), None)
    if e is not None:
        return e
    row = _spec.of_task(uid)
    if not isinstance(row, dict) or not (row.get("done_when") or row.get("unverifiable")):
        return None
    e = {**row, "id": f"r{int(time.time() * 1000) % 10_000_000}", "task_id": uid, "widget": "", "action": "",
         "trace": str(getattr(rec, "trace_id", "") or ""), "born": time.time()}
    if not e.get("unverifiable"):
        e["status"] = "started"                      # the commission goes on: its end state is owed again
        _spec._OPEN.append(e)
        del _spec._OPEN[:-_spec._MAX]
    return e


def takes_over(rec, ctx: dict | None) -> bool:
    """`spec.born` for a CONTINUATION: True when it is handled here and `born` must do nothing else.

    The row's end state goes onto the fresh record and is told to its worker. A continuation is NEVER re-inferred
    with a model — a row with no end state yet (inference pending; a quota-parked resume carries no `relay_gen`)
    stays without one, because a second guess opens a second spec and resets its tries. Only a continuation that
    brought its own `done_when` and finds none on the row (the harness retry of a spec that never reached it) goes on
    to `born`'s ordinary open."""
    if not continues(rec, ctx):
        return False
    from nucleo.circuit import spec as _spec
    uid = str(getattr(rec, "uid", "") or "")
    e = _row_entry(rec, uid)
    if e is None:
        return not getattr(rec, "done_when", None)
    try:
        if e.get("unverifiable"):
            rec.spec_unverifiable = True
        else:
            rec.done_when = copy.deepcopy(e.get("done_when") or {})
            _spec._schedule(_spec._tell_worker(rec, e))
    except Exception as ex:  # noqa: BLE001
        logger.debug(f"spec: continuation of {uid} not handed over: {ex!r}")
    return True


def mark_met_at_birth(e: dict | None, rec, ctx: dict | None) -> None:
    """A NEW commission born on a card ANOTHER commission filled, whose end state reads that card and is already
    true: kept for the record, never attested as met.

    Narrow on purpose. A card's own idempotent order («volume to 50» at 50, «add X» with X there) and a write the
    card absorbed into a row it already held (`existing`, T-19 R10) stay MET — there the state is the order's own
    effect. The lie is only a state somebody else produced: the continuity decision (`request/append.py`) hands a
    follow-up the sheet of an errand that just ended, and a row and its sheet are named by the same composition, so
    a sheet that is not the commission's own uid was filled by another commission."""
    if not e or not e.get("task_id") or e.get("existing"):
        return
    sheet = str((ctx or {}).get("sheet") or getattr(rec, "sheet", "") or "").strip()
    if not sheet or sheet == e["task_id"] or f"::{sheet}" not in json.dumps(e.get("done_when"), default=str):
        return
    from nucleo.circuit import spec as _spec
    from nucleo.circuit import verify as _verify
    try:
        if _verify.check(e.get("done_when")) is True:
            e["met_at_birth"] = True
            _spec.persist(e["task_id"], e)
            _spec._emit("🫥 spec: ya se cumplía al nacer, en una hoja heredada — no atestigua este encargo", e,
                        sheet=sheet)
    except Exception as ex:  # noqa: BLE001
        logger.debug(f"spec: met-at-birth check of {e.get('task_id')} skipped: {ex!r}")


def met_at_birth(rec) -> bool:
    """`verdict_of`'s reading: the record's commission was born with its end state already true."""
    from nucleo import circuit as _circuit
    from nucleo.circuit import spec as _spec
    try:
        e = _circuit._entry_for(rec) or _spec.of_task(str(getattr(rec, "uid", "") or "")) or {}
    except Exception as ex:  # noqa: BLE001
        return bool(logger.debug(f"circuit: met-at-birth unreadable: {ex!r}"))
    return bool(e.get("met_at_birth"))
