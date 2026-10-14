"""nucleo/flash/nothing_claims.py — a reply that says «there is nothing» does not survive a delivery of rows (V2-782).

search-buy-used-car ES (2026-10-11), one reply: «No hay nada que mostrar: no aparece ningún modelo ni precio en la
búsqueda. Bueno, de hecho ya hay candidatos en la hoja de resultados: «Fiat Tipo — € 10.490»; «BMW 730 — € 6.599»…».
The first sentence was the model reading an EMPTY sheet it had just written over the errand's; the second was the
delivery backstop (`delivery.sheet_delivery_backstop`) reading the errand's real one. Both were facts about a
sheet; only the second was about his. The EN round said the same shape: «There's nothing solid yet… Actually, there
are already candidates…».

When the backstop delivers rows, the sentences of the reply that claim there is nothing are cut — the rows are the
fact — and if nothing is left, the delivery loses its «actually» lead, which only made sense after a denial.
"""
from __future__ import annotations

import re

from search.asked import norm as _norm

_NOTHING = re.compile(
    r"(no hay nada|no (aparece|sale) (ningun|ninguna|nada)|no hay (ningun|ninguna) (resultado|candidato|anuncio|opcion|"
    r"ficha|modelo)|(todavia|aun) no (tengo|hay) (nada|ningun)|no tengo nada|sin resultados|nada solido|"
    r"nothing (to show|yet|solid|worth|on the sheet|so far)|there'?s nothing|there is nothing|no results|"
    r"i (don'?t|do not) have anything|haven'?t found anything|not found anything|nothing worth|"
    # boat hunt EN/ES (2026-10-14): the waits that deny in other words — «nothing landed yet», «still nothing»,
    # «no luck on Boat Trader so far», «todavía nada», «aún no tengo nada que darte».
    r"nothing (has )?(landed|come up|turned up|popped up)|still nothing|no luck|nada todavia|(todavia|aun) nada|"
    r"de momento nada|sin nada (todavia|aun))")
_SENT = re.compile(r"(?<=[.!?:])\s+")
_LEADS = ("Bueno, de hecho ya hay", "Actually, there are already")
_BARE = {"Bueno, de hecho ya hay": "Ya hay", "Actually, there are already": "There are already"}


def reconcile(reply: str, delivery: str) -> str:
    """The reply with its «nothing» sentences cut, then the delivery. Never raises; with no delivery, `reply`."""
    try:
        if not delivery:
            return reply
        kept: list[str] = []
        cut = False
        for s in (x for x in _SENT.split(str(reply or "")) if x.strip()):
            if not _NOTHING.search(_norm(s)):
                kept.append(s)
                continue
            cut = True
            if kept and kept[-1].rstrip().endswith(":"):    # «Right now:» announced the denial; it goes with it
                kept.pop()
        out = " ".join(kept).strip()
        if cut and not out:
            for lead in _LEADS:
                if delivery.startswith(lead):
                    delivery = _BARE[lead] + delivery[len(lead):]
        if cut:
            _emit(out, delivery)
        return (out + " " + delivery).strip() if out else delivery
    except Exception as e:  # noqa: BLE001 — never lose the delivery to a repair
        __import__("logging").getLogger(__name__).warning("nothing_claims failed: %s", e)
        return ((reply or "").rstrip() + " " + delivery).strip()


def _emit(kept: str, delivery: str) -> None:
    try:
        from voice.observer import emit
        emit("brain", "🧹 a «nothing» claim cut: the delivery is the fact", role="system",
             extra={"kept": kept[:90], "delivery": delivery[:90]})
    except Exception as e:  # noqa: BLE001
        __import__("logging").getLogger(__name__).debug("nothing_claims emit failed: %s", e)
