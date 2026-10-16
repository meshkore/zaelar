"""widgets/navegador/buy_held.py — a «Buy» click he never ordered is handed back to the worker, not put to him.

things-to-do-nearby-weekend ES (2026-10-14, sandbox 021515-es): he asked «¿para qué día es…?» and then «¿Y de
precio qué tal?» about the jazz row of his sheet, said the price was what interested him most — and the round
ended on «La tarea 2 necesita tu OK para pulsar «Comprar»». The worker had walked into a checkout to read a price;
the click gate (`click_gate.may_act`) did its job and asked, and the ask became the last thing he heard, in place
of the answer he asked for twice. Seventy seconds later the worker had the price (22,80 €) from the event page.

The rule here is about the CONSEQUENCE, not his words: on an errand that delivers a sheet, nothing is bought
before he has CHOSEN one of its rows (`results.choose` writes `chosen`), and an errand on which his only words
about its rows are QUESTIONS (`row_ask.asks`: a «?» clause that names a row) is one where nobody ordered a
purchase. Then the irreversible click is not put to him: it is refused back to the worker with what to do instead
(read the datum on the page it is on). Any other errand — one that names no row, one with a chosen row, a buy he
ordered by name — still asks him, exactly as before. A hold lasts until he speaks again: «¿cuánto cuesta? … vale,
cómpralo» said before the first click is held once (no question to him, the worker reports the price), and his next
word to the errand — any word — makes the next buy click ask him as before. Holding on, without reading his words
for a verb, would deadlock a real order.
"""
from __future__ import annotations

#: browser task → his latest turn when a click was held there (the ring is bounded, so a count would stall).
_HELD: dict[str, str] = {}


def held(task_id: str, why: str, *, readable: bool = True) -> str:
    """The reason handed back to the worker ("" = put the ask to him, as usual). Never raises.

    `readable` is the gate's FACT about the page (`click_gate.decide` got signals), not the text of its reason:
    the reason is the session language's sentence and comparing against it is a guard that dies the day the
    sentence changes — it did on 2026-10-14 (audit V2-783 P0-4)."""
    if not why or not readable:
        return ""                          # an unreadable page is the case that must reach him
    try:
        rec, items, data = _errand_sheet(task_id)
        if rec is None or not items or data.get("chosen"):
            return ""
        from nucleo import on_his_behalf
        from nucleo.flash import row_ask
        said = on_his_behalf.errand_words(rec)
        if str(task_id) in _HELD and _HELD[str(task_id)] != (said[-1] if said else ""):
            return ""                      # he spoke after the hold: whatever he said, the click is his to answer
        asked = [row for text in said for row, _s in row_ask.asks(text, items)]
    except Exception as e:  # noqa: BLE001 — a held click is an allowance; failing to read it asks him, as before
        __import__("logging").getLogger(__name__).debug("buy_held: could not read the errand: %s", e)
        return ""
    if not asked:
        return ""
    names = sorted({str(r.get("title") or "")[:40] for r in asked})
    _HELD[str(task_id)] = said[-1] if said else ""
    _emit(task_id, why, names)
    return (f"not pressed: he asked ABOUT «{'», «'.join(names)}» (a question, not an order to buy) and has chosen "
            "no row of his sheet. Do not go through a buy/checkout button to read a datum: read it on the page you "
            "are on or on the event's own page, put it on the row, and report it — or report that it is not shown.")


def forget() -> None:
    """Tests and a reset."""
    _HELD.clear()


def _errand_sheet(task_id: str):
    """(the errand record, its sheet's rows, the sheet) for the browser task — (None, [], {}) when there is none."""
    from nucleo import dispatch, sheets, surfaces
    rec = dispatch.record_by_nav_task(task_id)
    if rec is None or not surfaces.opens_sheet(str(getattr(rec, "surface", "") or "")):
        return None, [], {}
    sheet = sheets.sheet_of(rec)
    if not sheet:
        return None, [], {}
    from widgets.results import data as _sheet
    data = _sheet.view_data(sheet)
    return rec, [i for i in (data.get("items") or []) if isinstance(i, dict)], data


def _emit(task_id: str, why: str, names: list[str]) -> None:
    try:
        from voice.observer import emit
        emit("widget", "🛑 buy click held: he asked about a row, not to buy", text=why[:80], role="system",
             extra={"id": "navegador", "task": str(task_id), "rows": names[:4]})
    except Exception as e:  # noqa: BLE001 — the trace never stops the gate
        __import__("logging").getLogger(__name__).debug("buy_held emit failed: %s", e)
