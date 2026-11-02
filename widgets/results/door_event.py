"""widgets/results/door_event.py — ONE event per push through the sheet's door (V2-837 G10).

What landed was recorded; why the rest did not travelled only for the category gate and a correction — a dedupe, a
page filed as a source, a row past the list's cap or kept in the pool left no trace, so «the worker found 30 cars and
the sheet shows 3» could not be read off the record. Every `present`/`append` now emits `widget door` with:

    handed      rows the push carried (after cleaning)          landed   rows on the list from this push
    off         {gate: n} — the gate that turned each away (`category · route · ceiling · place · spec`)
    candidacy   rows filed as pages (Sources tab)                dedupe   rows the list already had
    capped      rows past the list's cap                         pool     candidates kept off the list
"""
from __future__ import annotations

from loguru import logger


def emit(sheet: str, action: str, *, handed: int, landed: int, off: dict | None = None, candidacy: int = 0,
         dedupe: int = 0, capped: int = 0, pool: int = 0) -> None:
    try:
        from voice.observer import emit as _emit
        from widgets.results import data as _d
        gates = {k: int(v) for k, v in (off or {}).items() if v}
        _emit("widget", "door", text=f"{landed}/{handed} landed", extra={
            "id": _d.instance_id(str(sheet or "")), "action": action, "handed": int(handed), "landed": int(landed),
            **({"off": gates} if gates else {}),
            **{k: int(v) for k, v in (("candidacy", candidacy), ("dedupe", dedupe), ("capped", capped),
                                        ("pool", pool)) if v}})
    except Exception as e:  # noqa: BLE001 — recording a push never undoes it
        logger.debug(f"door_event.emit: {e!r}")
        pass
