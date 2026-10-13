"""A `show` with no pictures, over a viewer that already HOLDS the ones he asked for, is answered by that set.

Measured in `show-real-photo-of-a-new-car__es` (2026-10-14): «enséñame una foto del Ferrari Amalfi» filled the
viewer with six Amalfi photos; two turns later «¿Me las enseñas? Quiero verlo.» — the model rightly said «las
tienes ya en el visor», the promise repair turned that into `imagenes:show {query: "Ferrari Amalfi"}` with no
items, and the viewer refused it («no llegó ninguna imagen»). The operator heard «No he podido» twice over the
very photos he was asking for. A show with nothing new to show, that NAMES what the viewer holds, is asking to
SEE it. One naming something else is a search (`card_commission.picture_search_for_empty_show`), and one naming
nothing is still refused: demo pass 82 asked for a Ferrari over a viewer of nebulae, and «here they are» over the
nebulae would be a false success.

Stdlib-only, like the rest of the widget.
"""
from __future__ import annotations

import unicodedata

_MIN_TOKEN = 4          # «del», «the», «new» never decide whether two subjects are the same


def _tokens(text: str) -> set[str]:
    s = unicodedata.normalize("NFKD", str(text or "").lower())
    s = "".join(c if c.isalnum() else " " for c in s if not unicodedata.combining(c))
    return {t for t in s.split() if len(t) >= _MIN_TOKEN}


def names_the_held_subject(db: dict, payload: dict) -> bool:
    """True when EVERY meaningful word of the payload's query/title is in what the held set is about: «Ferrari
    Amalfi» over an Amalfi set is that set; «Ferrari Roma» or «Ferrari Amalfi rojo» over it is a new search."""
    p = payload if isinstance(payload, dict) else {}
    asked = _tokens(" ".join(str(p.get(k) or "") for k in ("query", "title")))
    if not asked:
        return False
    held = _tokens(" ".join(str(db.get(k) or "") for k in ("query", "title")))
    for it in db.get("items") or []:
        held |= _tokens(str((it or {}).get("title") or "") if isinstance(it, dict) else "")
    return asked <= held


def answers_show(db: dict, payload: dict) -> dict | None:
    """The result of a picture-less `show` when the viewer's set answers it, else None (the caller refuses)."""
    items = (db or {}).get("items") or []
    if not items or not names_the_held_subject(db, payload):
        return None
    i = int(db.get("i") or 0)
    cur = items[i] if 0 <= i < len(items) else items[0]
    return {"ok": True, "n": len(items), "already_shown": True,
            "shown": cur.get("title") or cur.get("site") or ""}
