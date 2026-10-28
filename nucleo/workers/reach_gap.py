"""The worker's FIRST step: is what the errand asks for inside what the resource can see? (V2-825 F6)

Measured: an errand over «mail before 2025-01-01» against a mailbox whose oldest message is from 2026-09-04 kept
peeking 2026 threads, went silent twice and was buried without a reason. No amount of searching meets that spec.

The window is DECLARED — the brief's `window` or the escalation's `context["window"]`, `{"resource": <family>,
"before": <ISO date>}` — and the reach is MEASURED by `connectors.reach`; the comparison is two dates, never words.
A gap ends the errand before any worker spawns, says so in his language, leaves the reason on its task row, and is
never retried. Fail-open: no window, an undeclared family or a reach the resource could not give starts the worker.
"""
from __future__ import annotations

import logging

logger = logging.getLogger("zaelar.workers.reach_gap")


def window_of(brief: dict | None, context: dict | None) -> dict:
    """The declared window, brief first: `{}` when neither says which resource and how far back."""
    for w in ((brief or {}).get("window"), (context or {}).get("window")):
        if isinstance(w, dict) and str(w.get("resource") or "").strip() and str(w.get("before") or "").strip():
            return {"resource": str(w["resource"]).strip(), "before": str(w["before"]).strip()[:10]}
    return {}


def gap(window: dict) -> dict | None:
    """`{resource, earliest, asked_before}` when the window asks for what the resource cannot hold, else None."""
    if not window:
        return None
    from connectors import reach as _reach
    r = _reach.reach(window["resource"])
    earliest = (r.earliest or "")[:10]
    found = ({"resource": r.family, "earliest": earliest, "asked_before": window["before"]}
             if r.known and earliest and window["before"] <= earliest else None)
    _observe(window, r, found)
    return found


def _observe(window: dict, r, found: dict | None) -> None:
    """One `spec` event per comparison, with its verdict — beside the `spec/reach` measurement it read."""
    try:
        from voice.observer import emit
        emit("spec", "reach vs spec", role="system",
             text=(f"{found['resource']} reaches back to {found['earliest']}; asked before {found['asked_before']}"
                   if found else ""),
             extra={"resource": window["resource"], "before": window["before"], "earliest": r.earliest or "",
                    "known": r.known, "detail": r.detail, "verdict": "gap" if found else "inside"})
    except Exception as e:  # noqa: BLE001 — the timeline is a witness; the verdict stands without it
        logger.debug("reach-vs-spec event not emitted: %s", e)


async def end(_d, key: str, rec, found: dict) -> None:
    """End the errand on its capability gap: said once, its reason on the row, and no retry (verdict `cannot`)."""
    from nucleo.workers.relay import _say
    rec.status, rec.ok, rec.verdict = "done", False, "cannot"
    rec.result_summary = _say().worker_reach_gap.format(asked=found["asked_before"], earliest=found["earliest"])
    await _d._deliver_confirm(rec)
    _d._SESSIONS.pop(key, None)
    _d._task_row("ended_early", rec, state="failed",
                 outcome=f"cannot: {found['resource']} reaches back to {found['earliest']}; "
                         f"the errand asks for before {found['asked_before']}")
    _d.sync_state()
