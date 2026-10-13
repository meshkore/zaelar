"""nucleo/flash/commission_keep.py — a commission whose deliverable is a SHEET keeps its worker.

Two turns of 2026-10-14, one shape. The brief read `escalate_or_inline=escalate` with a list as the deliverable, and
a repair pass (`act_repair.call_for_promise_or_order`) replaced the commission with ONE data-op on the errand's own
instruments; the model's words were dropped for the op, and the text channel's ack said «Done.»:
  · compare-insurance-quotes EN, turn 1 — «can you compare a few insurers and see which one's actually worth it?» →
    `navegador:search {q: "comparativa seguros de coche"}` → «Done.», no worker; «Wait, done? I don't see any
    quotes».
  · best-plumber-same-day EN, turn 10 — «I need to know if any of them are top-rated and can actually come today» →
    `results:progress` (a note on the sheet) instead of the refinement reaching the live worker → «Done.»;
    «wait, "Done"? I still don't know if they're top-rated».

The V2-770 rung exists for a two-field op on a card that holds HIS data («a partir de noviembre ya no hay piano» →
`agenda:cancel_meeting`). A shortlist, a comparison or a report is produced by a worker INTO a sheet; a single call
on that sheet, or on the browser that fills it, is never that deliverable. So when the brief is sure the turn goes to
a worker and names a sheet as where it lands, the repair keeps its hands off those cards. Every other card, and every
turn the brief does not route to a worker, repairs as before.
"""
from __future__ import annotations

#: The errand's instruments: the browser it drives and the sheets its deliverable lands in.
_INSTRUMENTS = frozenset({"navegador", "results", "documento"})


def keeps_the_worker(brief, widget_id: str) -> bool:
    """True when the repair must NOT replace this turn's commission with a call on `widget_id`. Never raises."""
    base = str(widget_id or "").split("::", 1)[0].strip().lower()
    if brief is None or base not in _INSTRUMENTS:
        return False
    try:
        from nucleo import surfaces as _sf
        from nucleo.flash import turn_brief as _tb
        route, _ = _tb.read(brief, _tb.ESCALATE_KEY, "")
        surface, _ = _tb.read(brief, _sf.SURFACE_KEY, "", min_confidence=0.7)
        keep = str(route) == "escalate" and str(surface) in (_sf.LIST, _sf.ITEM, _sf.DOC)
    except Exception:  # noqa: BLE001 — without verdicts, the repair runs as it always did
        return False
    if keep:
        try:
            from voice.observer import emit
            emit("brain", "🧰 repair skipped: the commission's deliverable is a sheet, its worker keeps it",
                 role="system", extra={"cat": "flash", "widget": base, "surface": str(surface)})
        except Exception as e:  # noqa: BLE001 — the decision stands without its event
            __import__("logging").getLogger("zaelar.flash").debug(f"commission_keep: emit failed — {e}")
    return keep
