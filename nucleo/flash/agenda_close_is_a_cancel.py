"""nucleo/flash/agenda_close_is_a_cancel.py — «quita el piano entero» is a cancellation, not a close (2026-10-14).

Measured on `agenda-everyday-edits` ES (report 20261014-005211, step 14): «Y quita el piano entero, toda la serie»
was answered «Voy a ello. He cerrado Agenda. Ya no queda nada en pantalla.» — the model emitted [[close]] on the
agenda and called nothing; the fourteen piano lessons stayed. The 2026-10-11 fix (nodes 2.440–2.444) stands: it
reads the turn's VERDICT (`direct_action.order_is_inside` / `verdict_card.inner_order_wins`) and backs a «Hecho.»
CLAIM with the cancellation (a backing over our own words, gone with refactor2710-03). This round neither held: the decision model answered
HTTP 529 from turn 6 on, so every verdict read `off`, and the reply was a PROMISE («Voy a ello»), not a claim. With
no verdict, «quita» is a close verb, the grammar licensed the tag, and the card closed.

What decides without a verdict is the CARD'S OWN ROWS: a removal order whose words name ONE appointment on the
agenda — by its title (`_named`) — and do not call the card
itself by its name is an order INSIDE the card. The close is dropped and the agenda's declared, reversible
`cancel_meeting` runs instead (trash + `restore_meeting`, CRIT-C3), with `whole` when he said «toda la serie».
«Quita la agenda», «cierra el calendario» and a sentence naming no appointment keep the close.
"""
from __future__ import annotations

import re

from nucleo.flash.text_norm import _content_words, _norm_txt

_ORDER_RE = re.compile(
    r"\b(?:anul|cancel|qu[ií]t(?:a|al[ao]|ar|amel[ao]|el[ao])\b|borr|elimin|suprim|remove|delete|drop|scrap|get\s+rid\s+of|call\s+(?:it\s+|that\s+)?off|"
    r"take\s+(?:it|that)\s+off)\w*", re.I)
_OTHER_RE = re.compile(
    r"\b(?:lista|list|tarea|task|compra|shopping|item|fila|row|cancion|song|musica|music|video|mensaje|message|"
    r"correo|email|mail|nota|note|foto|photo|contacto|contact)s?\b", re.I)
#: A notice is its own thing in HIS words («cancel the reminder» is `cancel_reminder`).
_NOTICE_RE = re.compile(r"\b(?:recordatorio|reminder|aviso|alarma|alarm|alerta|alert)s?\b", re.I)
#: The WHOLE of a series, in his words — the agenda asks «one day or all of it?» otherwise (V2-769).
_WHOLE_RE = re.compile(r"\b(?:(?:toda|la)\s+(?:la\s+)?serie|serie\s+(?:entera|completa)|enter[oa]|complet[oa]|"
                       r"para\s+siempre|todas?\s+las\s+(?:clases|semanas|veces)|whole\s+(?:series|thing)|"
                       r"entire\s+series|completely|altogether|for\s+good|all\s+of\s+(?:it|them))\b", re.I)


def _named(db: dict, words: set) -> dict | None:
    """The ONE upcoming appointment his words name by its title, or None (none, or more than one).

    Two shared words name a title; failing that, ONE distinctive word does when no other title has it — «quita el
    piano entero» over «Clase de piano de Abril» (agenda-everyday-edits, 2026-10-11: the backing read «piano» as
    something that is not his and left the series standing under «Hecho.»)."""
    if not words:
        return None
    hits, loose = [], []
    for m in db.get("meetings") or []:
        theirs = _content_words(str((m or {}).get("title") or ""))
        if theirs and len(words & theirs) >= min(2, len(theirs)):
            hits.append(m)
        elif any(len(w) >= 4 for w in words & theirs):
            loose.append(m)
    titles = {str(m.get("title") or "").strip().lower() for m in hits or loose}
    return (hits or loose)[0] if len(titles) == 1 else None



def cancel_instead(said: str, card_id: str, db: dict | None = None) -> dict | None:
    """The `widget_data` call that replaces a [[close]] of the agenda, or None to keep the close. Never raises."""
    try:
        if str(card_id or "").split("::", 1)[0].strip().lower() != "agenda" or not str(said or "").strip():
            return None
        n = _norm_txt(said)
        if not _ORDER_RE.search(n) or _OTHER_RE.search(n) or _NOTICE_RE.search(n):
            return None
        from widgets import naming as _naming
        if _naming.says_the_name(said, "agenda"):
            return None                        # «quita la agenda» names the card: that IS the close
        if db is None:
            from widgets import store as _store
            db = _store.load("agenda") or {}
        target = _named(db, _content_words(said) - {"quita", "quitame", "borra", "elimina", "anula", "cancela",
                                                        "remove", "delete", "cancel"})
        if not target or not str(target.get("title") or "").strip():
            return None
        payload = {"title": str(target["title"])}
        series = isinstance(target.get("repeat"), dict) or bool(target.get("fromSeries"))
        if not series and target.get("date"):
            payload["date"] = str(target["date"])
        elif series and _WHOLE_RE.search(n):
            payload["whole"] = True
        return {"widget_id": "agenda", "action": "cancel_meeting", "payload": payload}
    except Exception:  # noqa: BLE001 — a doubt keeps the model's close
        __import__("logging").getLogger("zaelar.flash").debug("close-or-cancel read skipped", exc_info=True)
        return None


def took_the_close(said: str, extra, run) -> bool:
    """True when the close tag is an appointment's cancellation: `run(call)` was given that call instead.
    Shared by the voice `_tag_emit` and the text channel's — one decision, so they cannot diverge."""
    call = cancel_instead(said, str((extra or {}).get("id") or ""))
    if not call:
        return False
    try:
        from voice.observer import emit as _emit
        _emit("brain", "🗓️ close of the agenda over a removal of one of its rows — cancelled instead", role="system",
              text=f"{call['payload'].get('title', '')}"[:120],
              extra={"cat": "flash", "widget": "agenda", "action": "cancel_meeting", "payload": call["payload"]})
    except Exception:  # noqa: BLE001 — the trace is best-effort; the cancellation is not
        __import__("logging").getLogger("zaelar.flash").debug("close-or-cancel trace not emitted", exc_info=True)
    run(call)
    return True


def inside_or_cancelled(brief, said: str, extra, run) -> bool:
    """The close guard both channels ask: the verdict puts the order inside the card (V2-770), or — with no
    verdict to read — the card's own rows do (`took_the_close`). True = the [[close]] is not the order."""
    from nucleo.flash import direct_action as _da
    return _da.order_is_inside(brief, str((extra or {}).get("id") or "")) or took_the_close(said, extra, run)
