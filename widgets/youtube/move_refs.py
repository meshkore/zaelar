"""How the queue's `move` reads WHICH video and WHERE it goes, and what it says when one of the two is missing.

Video-queue use case, ES round of 2026-10-11 (engine 3.36+d6f4a99f): «El que está sonando ahora, ese ponlo el
primero» reached `move {position: "first", item: "1"}` — `position` is not a declared key, `int("first")` is not
a slot — and the card answered «Dime a qué posición (1-N) lo muevo», naming the slot as the missing half when the
slot («el primero») was the one half he HAD said. The same-turn repair then sent `{item: <the playing title>, to:
"first"}`, right in both halves, and lost again on `int("first")`. Two turns later he had translated his sentence
into coordinates himself («Es el 2 ahora mismo, ponlo el 1»), which was the card's job.

Three readings, all closed classes (`widgets/refs` owns the ordinal table; nothing here is a verb table):
  · a SLOT is a number, an ordinal («first», «primero», «3rd»), or an end of the queue («al principio», «top»,
    «al final», «last»), under `to` or its spelling `position`;
  · an ITEM may be «the one playing» («sonando», «playing», «current»): the queue knows which row that is;
  · a refusal names the half that is MISSING — the video or the slot — through a bundle key, so the operator
    hears it in his language, and a move that would change nothing is refused too: the repair that reads his
    sentence over the card only runs on a refusal, and «Done.» over an unchanged queue is the worse outcome.
"""
from __future__ import annotations

import re

from . import helpers as _h

#: Said of the row that is playing, in either product language. `este`/`this` stay out: «ese ponlo el primero»
#: points at whatever the sentence named before, which the sentence — not this table — decides.
_PLAYING = re.compile(r"\b(?:sonando|suena|reproduciendo|reproduciendose|playing|current|actual|"
                      r"en el reproductor)\b")
#: Words around a slot that say nothing about it: «a la 1», «al puesto 3», «to the top», «position 2».
_SLOT_FILLER = frozenset("a al la el lo the to at in into de del todos todo all of position posicion puesto slot "
                         "spot lugar sitio number numero no n cola queue list lista".split())
_HEAD = frozenset("principio inicio comienzo cabeza arriba top front head start beginning".split())
_TAIL = frozenset("final fin fondo abajo ultimo ultima end bottom back tail".split())

#: What each refusal says, in Spanish (the house convention for `message`) and as the bundle key that speaks it in
#: the session's language (`say`, read by `refusal_line.speakable`).
_REFUSALS = {
    "missing_item": "¿Cuál de los vídeos muevo? Dime su número o parte del título.",
    "missing_position": "¿A qué posición de la cola lo muevo?",
    "bad_position": "No entiendo a qué posición moverlo: dime un número o «el primero» / «el último».",
    "already_there": "Ese vídeo ya está en esa posición.",
}


def refusal(code: str, **extra) -> dict:
    """The refusal for `code`, with its spoken line in both shapes."""
    out = {"ok": False, "error": code, "say": f"widgets.youtube.move_{code}", "message": _REFUSALS[code]}
    out.update(extra)
    return out


def names_the_playing(value) -> bool:
    """Does `value` point at the row that is playing, rather than at a number or a title?"""
    s = _h._norm(value)
    return bool(s) and not any(c.isdigit() for c in s) and bool(_PLAYING.search(s))


def playing_index(db: dict) -> "int | None":
    """0-based row of the video that is playing, or None when nothing in the list is."""
    try:
        pos = int(db.get("pos", -1))
    except (TypeError, ValueError):
        return None
    return pos if 0 <= pos < len(db.get("list") or []) else None


def resolve_item(lst: list, value, db: dict) -> "int | None":
    """`_resolve_item`, plus «the one playing» — a real way to name a row that no title match can find."""
    idx = _h._resolve_item(lst, value)
    if idx is None and names_the_playing(value):
        idx = playing_index(db)
    return idx


def slot(value, n: int) -> "int | None":
    """0-based destination for a spoken or numeric slot, or None when `value` names none.

    A digit is clamped into the queue (the manifest's `1-N`; «ponlo el 20» over four rows is the end); an ordinal
    or an end word resolves through the one table every reader shares."""
    if n <= 0:
        return None
    toks = [t for t in _h._norm(value).replace("#", " ").split() if t not in _SLOT_FILLER]
    if len(toks) != 1:
        return None
    t = toks[0]
    if t.isdigit():
        return max(0, min(n - 1, int(t) - 1))
    if t in _HEAD:
        return 0
    if t in _TAIL:
        return n - 1
    from widgets import refs as _refs
    return _refs.position_index(t, n)


def destination(p: dict, n: int) -> "tuple[int | None, bool]":
    """`(slot, given)` from the payload's `to` — or `position`, the spelling the model reaches for (both rounds,
    ES and EN, 2026-10-11). `given` tells a refusal whether the slot was MISSING or unreadable."""
    raw = next((p.get(k) for k in ("to", "position") if str(p.get(k) if p.get(k) is not None else "").strip()), None)
    if raw is None:
        return None, False
    return slot(raw, n), True
