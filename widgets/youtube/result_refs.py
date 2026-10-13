"""Which row of the dashboard's search band he NAMED — by number, by title or by channel (2026-10-14).

Use case `find-videos-on-a-topic-no-ai-slop` (EN): «play the Palm Centre one first», twice, with «How to Prune an
Olive Tree — The Palm Centre» as row 5 of the band. The model called `play_item {item: "How to Prune an Olive Tree —
The Palm Centre"}`; the queue was empty, so `play_item` handed the reference to `play_result`, which only read a
NUMBER — `int()` of a title is -1, and he heard «Solo hay 6 resultados.» Nothing ever played. The same turn's
`add {url: "Cómo podar un olivo… — ColtivoBio"}` sent a row he could SEE to a fresh network search.

A row is named the way he names it: its 1-based number, its exact title, or words of its title and channel
(«the Palm Centre one», «el de Iván»). The match is ONE row or none — two rows that both carry the words are an
ambiguity the card refuses, never a guess (the `refs` doctrine). Pure: no store, no network.
"""
from __future__ import annotations

import re

from widgets import textmatch as _tm

#: Words a spoken reference wraps a name in («the X one», «el de X»): never the thing named.
_WRAP = frozenset("one ones video videos el la los las de del lo uno una vídeo video the of by from that this".split())


def _row_text(row: dict) -> str:
    return f"{row.get('title') or ''} {row.get('channel') or ''}"


def _words(s: str) -> set[str]:
    return {t for t in _tm.fold(s).split(" ") if t and t not in _tm._GENERIC and t not in _WRAP}


def resolve(rows: list, ref) -> "int | None":
    """0-based index of the ONE row `ref` names, or None. Never raises."""
    try:
        s = str(ref if ref is not None else "").strip()
        if not s or not rows:
            return None
        if s.isdigit():
            i = int(s) - 1
            return i if 0 <= i < len(rows) else None
        f = _tm.fold(s)
        exact = [i for i, r in enumerate(rows) if f in (_tm.fold(r.get("title")), _tm.fold(_row_text(r)))]
        if len(exact) == 1:
            return exact[0]
        want = _words(s)
        if not want:
            return None
        hits = [i for i, r in enumerate(rows) if want <= set(_tm.fold(_row_text(r)).split(" "))]
        if len(hits) == 1:
            return hits[0]
        if hits:
            return None                                  # two rows carry his words: ask, never guess
        best = _tm.pick_one(s, rows, key=_row_text)
        return rows.index(best) if best is not None else None
    except Exception:  # noqa: BLE001 — an unreadable reference names nothing
        return None


def indices(rows: list, raw) -> list[int]:
    """1-based rows for an `items` payload: numbers, «all», or names separated by commas / «y» / «and».

    `[]` when any NAME in it resolves to no row — a partial add would be a second «Hecho» over less than he said."""
    if isinstance(raw, list):
        parts = [str(x) for x in raw]
    else:
        t = str(raw or "").strip()
        if t.lower() in ("all", "todos", "todas", "*"):
            return list(range(1, len(rows) + 1))
        if re.fullmatch(r"[\d\s,;.\-]*", t):                 # numbers only: today's reading, untouched
            return list(dict.fromkeys(n for n in map(int, re.findall(r"\d+", t)) if 1 <= n <= len(rows)))
        parts = re.split(r"\s*(?:,|;|\by\b|\band\b|\be\b)\s*", t)
    out: list[int] = []
    for p in (x.strip() for x in parts):
        if not p:
            continue
        if p.isdigit():
            n = int(p)
            if 1 <= n <= len(rows):
                out.append(n)
            continue
        i = resolve(rows, p)
        if i is None:
            return []
        out.append(i + 1)
    return list(dict.fromkeys(out))


#: What a removal over an EMPTY queue may have meant while the band is on screen: the band's own two writes.
REDIRECT = ("add_results", "play_result")


def nothing_queued() -> dict:
    """The refusal of `clear_list` over an empty queue with the band on screen (2026-10-14, ES): «Ponme el de Iván,
    el de José Manuel y el de Jaén» reached `clear_list`, the empty queue stayed empty, and «Hecho.» was said twice
    over three videos that were never added. The refusal is TRUE and names the card's two writes that act on the
    band (`redirect`), so the same-turn correction (`nucleo/flash/refusal_redirect.py`) may run one of them."""
    from widgets import hint_lang as _hl
    return {"ok": False, "error": "queue_empty", "redirect": list(REDIRECT),
            "message": _hl.pick("La cola ya está vacía: no había nada que quitar.",
                                "The queue is already empty: there was nothing to remove.")}


def queue_line(db: dict) -> str:
    """The QUEUE beside the band, numbered by its own order (2026-10-14, EN): with the band on screen the digest
    replaced the queue's items line, so the model numbered `remove {items}` by the BAND — «just the Palm Centre one,
    drop the rest» removed 2,3,4,6 of a six-row queue and kept the emoji video he had complained about."""
    lst = [it for it in (db.get("list") or []) if isinstance(it, dict)]
    if not lst:
        return "COLA: vacía (add_results manda ahí los resultados)."
    rows = " · ".join(f"{i}. {str(it.get('title') or '')[:50]}" for i, it in enumerate(lst[:10], 1))
    return f"COLA ({len(lst)}, su número NO es el de la búsqueda; remove/move/play_item la usan): {rows}"
