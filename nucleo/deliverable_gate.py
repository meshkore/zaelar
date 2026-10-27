"""An errand opens only its DELIVERABLE on his screen (V2-822).

The operator asked for a document describing how he writes. The worker read his sent mail, extracted, analysed — and
on the way its `show_widget` calls opened the results sheet and the messaging card, and only then the document. He
had asked for the document alone: «todo el proceso debería haber sucedido en background dentro de un brain worker y
después el arnés debería decir: el usuario necesita este documento, pues le muestro este documento».

The class: a worker's `show_widget` was a free door to any card. This is the one rule at that door — when the
errand's surface names its card (`surfaces.deliverable_card`: the results sheet for a list, the document for a
report, the viewer for pictures), a show of any OTHER card is refused, with the way through: read it without
opening it, and deliver into the deliverable. The worker still reads every card it needs (`read_widget`,
`widget_data`); nothing about what it may READ or WRITE changes. Closing is never refused.

An errand whose deliverable is NO card — told (`voz`) or just done (`silenciosa`) — opens nothing at all (the
operator's decision 3, 2026-10-27: only the deliverable opens, and a told answer has none). An errand that builds or
fills a card of his (`widget`) opens that card, and is not this gate's business.
"""
from __future__ import annotations


def refused(rec, action: str, payload: dict) -> str:
    """Why this `show_widget` is refused ("" = let it through)."""
    if action != "show_widget" or not isinstance(payload, dict):
        return ""
    from nucleo import surfaces
    surface = str(getattr(rec, "surface", "") or "")
    own = surfaces.deliverable_card(surface)
    wid = str(payload.get("id") or payload.get("widget_id") or "").split("::", 1)[0].strip().lower()
    if not wid:
        return ""
    if surfaces.delivers_no_card(surface) and wid not in _end_state_cards(rec):
        _emit(rec, wid, "")
        return (f"this errand delivers no card — its result is told (or simply done), so it opens nothing on his "
                f"screen and «{wid}» stays closed. Read it with read_widget (nothing opens) and report your result.")
    if not own or wid == own:
        return ""
    _emit(rec, wid, own)
    return (f"this errand's deliverable is the «{own}» card, and it is the only card the errand opens on his screen — "
            f"«{wid}» stays closed. Read it with read_widget (nothing opens) and deliver your result into «{own}».")


def _end_state_cards(rec) -> set:
    """The cards the errand's own END STATE names (`done_when` clauses): when what he asked for is a state of a card
    (the player playing, a row on his list), that card IS the deliverable even if the result is also told."""
    try:
        from nucleo import verify
        _mode, clauses = verify._clauses(getattr(rec, "done_when", None) or {})
        return {str(c.get("widget") or "").split("::", 1)[0].strip().lower() for c in clauses if c.get("widget")}
    except Exception:  # noqa: BLE001 — an unreadable end state names no card
        return set()


def _emit(rec, wid: str, own: str) -> None:
    try:
        from voice.observer import emit
        emit("widget", "🚫 a card that is not the deliverable stays closed", role="system",
             extra={"id": wid, "deliverable": own, "task": str(getattr(rec, "task_id", "") or "")})
    except Exception as e:  # noqa: BLE001 — an event that cannot be emitted never blocks the bridge
        __import__("logging").getLogger(__name__).debug("deliverable gate emit failed: %s", e)
