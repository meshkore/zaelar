"""An errand opens only its DELIVERABLE on his screen (V2-822).

The operator asked for a document describing how he writes. The worker read his sent mail, extracted, analysed — and
on the way its `show_widget` calls opened the results sheet and the messaging card, and only then the document. He
had asked for the document alone: «todo el proceso debería haber sucedido en background dentro de un brain worker y
después el arnés debería decir: el usuario necesita este documento, pues le muestro este documento».

The class: a worker's `show_widget` was a free door to any card. This is the one rule at that door — when the
errand's surface names its card (`surfaces.deliverable_card`: the results sheet for a list, the document for a
report, the viewer for pictures), a show of any OTHER card is refused, with the way through: read it without
opening it, and deliver into the deliverable. The worker still reads every card it needs (`read_widget`,
`widget_data`); nothing about what it may READ or WRITE changes. Closing is never refused. An errand whose surface
names no card (a widget it builds, a told answer) is not this gate's business.
"""
from __future__ import annotations


def refused(rec, action: str, payload: dict) -> str:
    """Why this `show_widget` is refused ("" = let it through)."""
    if action != "show_widget" or not isinstance(payload, dict):
        return ""
    from nucleo import surfaces
    own = surfaces.deliverable_card(str(getattr(rec, "surface", "") or ""))
    wid = str(payload.get("id") or payload.get("widget_id") or "").split("::", 1)[0].strip().lower()
    if not own or not wid or wid == own:
        return ""
    _emit(rec, wid, own)
    return (f"this errand's deliverable is the «{own}» card, and it is the only card the errand opens on his screen — "
            f"«{wid}» stays closed. Read it with read_widget (nothing opens) and deliver your result into «{own}».")


def _emit(rec, wid: str, own: str) -> None:
    try:
        from voice.observer import emit
        emit("widget", "🚫 a card that is not the deliverable stays closed", role="system",
             extra={"id": wid, "deliverable": own, "task": str(getattr(rec, "task_id", "") or "")})
    except Exception as e:  # noqa: BLE001 — an event that cannot be emitted never blocks the bridge
        __import__("logging").getLogger(__name__).debug("deliverable gate emit failed: %s", e)
