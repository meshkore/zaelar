"""nucleo/flash/write_outcome.py — what a create REALLY left behind, told back; and a piece of a sentence undone (V2-769).

Measured on the operator's agenda, 2026-09-25 (session a96fdea7). Two defects, one afternoon:

1. THE DROPPED FIELD. The model sent `add_meeting {…, recurrence: "weekly", repeatUntil: "2027-06-30"}`; the
   widget did not know either key, wrote a single Tuesday and answered success. The reply had already been
   spoken — «desde el 22 de septiembre hasta junio de 2027» — and nothing ever went back to it, because the
   failure reporter (`data_ops.report_failure`) only speaks on `ok: False`, and a write that silently loses
   half of what it was told is `ok: True`. So a widget may now say which keys it IGNORED, and this module
   turns that into a correction: a note the model must act on, never a line read out raw.

2. THE PIECE OF A SENTENCE THAT WROTE A ROW. He said «créame una tarea recursiva los jueves de tres y media a
   cuatro y cuarto… llevar a Abril a flauta travesera» in one breath with pauses. The turn layer delivered
   «recursiva los jueves» as a turn of its own; the model wrote `add_task «Tarea semanal de los jueves»`.
   Thirteen seconds later the WHOLE sentence arrived as one turn and wrote the real appointment — beside the
   junk task, which stayed in his list. When a later create on the same card comes from a sentence that
   CONTAINS the earlier create's sentence, the earlier one was a piece of it: its row is taken back out, with
   the call the widget itself named for that (`revert` in its result). Narrow on purpose: same card, both
   creates, within `WINDOW_S`, and containment of the whole earlier sentence — «apunta pan» then «apunta
   leche» shares nothing and both stay.
"""
from __future__ import annotations

import re
import time
import unicodedata

#: How long a create stays «the piece that may still be completed». The measured gap was 13 s; a sentence
#: split by the turn layer is completed within one or two turns, never minutes later.
WINDOW_S = 45.0

_last: dict = {}


def _fold(text: str) -> str:
    s = unicodedata.normalize("NFKD", str(text or "").lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return " ".join(re.findall(r"\w+", s))


def is_create(action: str) -> bool:
    return str(action or "").startswith("add_")


def remember(wid: str, action: str, text: str, res, *, now: float | None = None) -> None:
    """After a create LANDED: keep what could take it back out, and the sentence it came from."""
    if not (is_create(action) and isinstance(res, dict) and isinstance(res.get("revert"), dict)):
        return
    _last[wid] = {"action": action, "text": _fold(text), "revert": res["revert"],
                  "at": time.time() if now is None else now}


def superseded(wid: str, action: str, text: str, *, now: float | None = None) -> dict | None:
    """The earlier create on this card that THIS create's sentence completes, or None."""
    prev = _last.get(wid)
    if not prev or not is_create(action):
        return None
    now = time.time() if now is None else now
    cur = _fold(text)
    if now - float(prev["at"]) > WINDOW_S or not prev["text"] or cur == prev["text"]:
        return None
    if f" {prev['text']} " not in f" {cur} " or len(cur.split()) < len(prev["text"].split()) + 2:
        return None
    return prev


def forget(wid: str) -> None:
    _last.pop(wid, None)


def reset() -> None:
    _last.clear()


def declared_fields(wid: str, action: str) -> list[str]:
    """The payload keys the widget's manifest declares for this action — what the model should have used.
    The model sees action NAMES only (`widgets/brief.py`), so a correction that does not name them invites the
    same guess again."""
    try:
        from widgets import runtime
        for w in runtime.catalog():
            if str(w.get("id")) == wid:
                spec = (w.get("actions") or {}).get(action) or {}
                return [str(k) for k in (spec.get("payload") or {})]
    except Exception:  # noqa: BLE001
        pass
    return []


def ignored_note(wid: str, action: str, res) -> str:
    """The correction for a write that landed WITHOUT some of what it was told, or "" when nothing was lost."""
    if not isinstance(res, dict) or res.get("ok") is False:
        return ""
    lost = [str(k) for k in (res.get("ignored") or []) if str(k).strip()]
    if not lost:
        return ""
    return (f"[SISTEMA] «{action}» sobre «{wid}» SÍ se guardó, pero SIN estos datos, que la tarjeta no sabe "
            f"guardar: {', '.join(lost[:8])}. Si le dijiste que quedaba con eso, corrígelo en tu PRÓXIMA "
            f"respuesta — lo que está guardado es lo que dice la tarjeta, no lo que mandaste."
            + (f" Sus campos son: {', '.join(fields)}; si hay que rehacerlo, usa ESOS."
               if (fields := declared_fields(wid, action)) else ""))
