"""widgets/results/live.py — what the PROCESS tab paints WHILE the job is running.

Extracted from `widgets/results/data.py` on 2026-08-24 to pay the architecture ratchet when adding the
HARVEST (V2-296), and the boundary was already drawn: everything here is DERIVED from the dispatcher's live
record on each read, while what remains in `data.py` is the sheet's CONTENT — its records, its sources,
its criteria—which the sheet does possess and store.

They are two different questions about the same job and therefore live separately even though they are painted
together: `_progress` counts WHAT it is doing (narrative, trimmed to the ring of the last 40 lines) and
`_harvest` how much has been done (arithmetic, which would be false if trimmed).

Neither stores anything: `nucleo/sheets.py` owns the narrative and the browser tab owns the numbers. Once the
job is finished, the live record disappears and both fall back to what the sheet persisted when it closed — a
report without the explanation of how it was reached accounts for half of what happened.
"""
from __future__ import annotations

_MAX_PHASES = 40           # the same ring retained by the live record (`dispatch.PHASES_KEPT`)
_MAX_PHASE_CHARS = 160


def _clean_phases(raw) -> list:
    """Bounded process phrases. They already arrive readable from `nucleo/workers/progress.py`; none is
    interpreted here — they are trimmed and empty ones filtered, which is all a presentation surface can do
    with someone else's narrative."""
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, (list, tuple)):
        return []
    return [str(x)[:_MAX_PHASE_CHARS] for x in raw if str(x or "").strip()][-_MAX_PHASES:]


def _progress(data: dict, sheet: str = "") -> dict:
    """`{alive, phases}` — DERIVED on each read, never stored, just like `counts` (V2-227 scope C).

    The live dispatcher record owns “what is happening”: the sheet READS it. Storing it here would mean having
    the same state in two places, and the one left on screen is always stale.

    Once the job is FINISHED, the record no longer exists, so it falls back to the history the sheet itself saved
    when it closed (`process`). That is the only persisted part, and there is a reason for it: the report survives
    a restart, and a report whose explanation of how it was reached has disappeared accounts for half of what happened.

    Fail-soft: without a dispatcher (a test of the sheet alone, the widget mounted outside the engine), this is
    the stored history and `alive: False`, which is exactly what is seen — not an error.
    """
    live = {}
    try:
        from nucleo import dispatch as _disp
        # V2-259 — the narrative of ITS job. `dispatch._phrases` interleaved the phases of all live jobs
        # IN TIME ORDER, and that was “the honest answer while there is only one sheet”; with one sheet per
        # job it ceases to be: two boxes both telling the same mixed-up story is lying with more surface area,
        # which is exactly what V2-259 exists to avoid.
        live = _disp.sheet_progress(sheet) or {}
    except Exception:  # noqa: BLE001
        live = {}
    if live.get("alive"):
        return {"alive": True, "phases": _clean_phases(live.get("phases"))}
    stored = _clean_phases(data.get("process"))
    return {"alive": False, "phases": _clean_phases(live.get("phases")) or stored}


def _harvest(data: dict, sheet: str = "") -> dict:
    """The HARVEST of this job: how much has been inspected and what survived each cutoff (V2-296).

    Operator request with the tab in front: the narrative already said WHAT it is doing (“entering
    es.wallapop.com…”) and there was nothing saying HOW MUCH. It remains separate from `progress` because they
    are two different things — one is narrative and the other arithmetic — and because the narrative is trimmed
    to the last 40 lines while a trimmed total is a false total.

    DERIVED on each read like `counts` and `progress`: the browser tab owns the numbers, and the sheet READS
    them. Once the job is finished, the live record no longer exists, so it falls back to what the sheet itself
    saved when it closed — the same treatment as the narrative, and for the same reason: a report whose explanation
    of how much it cost to reach it has disappeared accounts for half of what happened.

    `{}` means “we do not know”, and is NOT filled with zeroes: a zero says “it was inspected and there was none”,
    which is a different fact and would be false here.
    """
    live = {}
    try:
        from nucleo import dispatch as _disp
        live = _disp.sheet_harvest(sheet) or {}
    except Exception:  # noqa: BLE001
        live = {}
    if live:
        return live
    stored = data.get("harvest")
    return dict(stored) if isinstance(stored, dict) and any(stored.values()) else {}
