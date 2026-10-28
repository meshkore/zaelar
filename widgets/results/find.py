"""widgets/results/find.py — which item the operator means, and what the brain is told is on the sheet:
`_named`/`_find` resolve a reference (title, ordinal, badge), `ref_index`/`prompt_digest` publish the sheets.

Names tests patch on `data` (`view_data`, `sheets`) are read through it (`_d.<name>`), so the patch governs every
call; `data` re-exports these names because `widgets/refs.py` looks the hooks up there.
"""
import re as _re

from i18n import langs as _langs


def _named(payload: dict) -> str:
    """The item a payload names, under whichever key the caller used (`item` is what other cards use for a row)."""
    for k in ("title", "item", "name"):
        v = payload.get(k)
        if isinstance(v, str) and v.strip():
            return v
    return ""


def _find(items: list[dict], title: str = "", index=None) -> dict | None:
    """Resolve WHICH item the operator means: by ordinal, exact title, contains-match, decorated title, or badge.
    The ordinal matters because this arrives from VOICE: «number one» survives STT better than a full name."""
    if isinstance(index, (int, float)) and not isinstance(index, bool):
        i = int(index)
        if 1 <= i <= len(items):                 # 1-based: the operator counts from one, not from zero
            return items[i - 1]
    t = (title or "").strip().lower()
    if not t and isinstance(index, str) and not index.strip().isdigit():
        t = index.strip().lower()           # a reference in words arrived in the index slot (the resolver's habit)
    elif not t and isinstance(index, str) and index.strip().isdigit():
        i = int(index.strip())
        if 1 <= i <= len(items):
            return items[i - 1]
    if not t:
        return None
    for it in items:
        if (it.get("title") or "").strip().lower() == t:
            return it
    for it in items:
        if t in (it.get("title") or "").strip().lower():
            return it
    # A reference may carry the view's decoration («KTC H27P22S — $254.98»): the head before it is the title; and a
    # row whose whole title sits inside the reference is named by it (one such row, never a guess).
    head = _re.split(r"\s+[—–|·]\s+|\s+-\s+", t, maxsplit=1)[0].strip()
    if head and head != t:
        for it in items:
            if (it.get("title") or "").strip().lower() == head:
                return it
        for it in items:
            if head in (it.get("title") or "").strip().lower():
                return it
    inside = [it for it in items if (tt := (it.get("title") or "").strip().lower()) and len(tt) >= 6 and tt in t]
    if len(inside) == 1:
        return inside[0]
    # …and by the BADGE printed on the card («the best value option»): one badge named = that item; two = no guess
    # (V2-776).
    named = [it for it in items if (b := str(it.get("badge") or "").strip().lower()) and b in t]
    return named[0] if len(named) == 1 else None


def _sheets_for_brain(sheet) -> list[str]:
    """WHICH sheets the brain sees. With `sheet` given, that one; without it, ALL that exist.

    «All» is deliberate: reading only one of two live sheets lets the turn answer confidently about the wrong one,
    with nothing saying another existed (V2-257).
    """
    if sheet is not None and _d._safe_sheet(sheet):
        return [_d._safe_sheet(sheet)]
    if sheet == "":
        return [""]
    found = _d.sheets()
    return found or [""]


def ref_index(sheet=None) -> list[dict]:
    """The items currently ON SCREEN, so the brain can let the operator pick one by talking about it and can SEE
    that the sheet is empty. The hint leads with the ORDINAL («number two» is how it is said aloud); with several
    sheets each reference also names its sheet, since the ordinal only disambiguates within one (V2-259).
    """
    out = []
    todas = _sheets_for_brain(sheet)
    varias = len(todas) > 1
    for sid in todas:
        data = _d.view_data(sid)
        titulo = str(data.get("title") or "").strip()
        for n, it in enumerate(data.get("items", []), 1):
            bits = [f"#{n}"]
            if varias and titulo:
                bits.append(_langs.words("hints.from_sheet", default="«{title}»").format(title=titulo))
            if it.get("price"):
                bits.append(it["price"])
            if it.get("parts"):
                bits.append(" + ".join(p.get("kind") or p.get("title") or "" for p in it["parts"]))
            elif it.get("subtitle"):
                bits.append(it["subtitle"])
            out.append({"id": it["title"], "label": it["title"], "field": "title",
                        "sheet": sid, "hint": " · ".join(b for b in bits if b)})
    return out


def prompt_digest(sheet=None) -> str:
    """What is ACTUALLY on screen, compact enough to ride in every prompt while this widget is open, so the brain
    can answer about a result it already holds instead of guessing or searching again. Bounded: a digest, not the
    dossier. With several sheets, all are traversed, each block headed by its task; the item limit is PER SHEET.
    """
    todas = _sheets_for_brain(sheet)
    if len(todas) > 1:
        bloques = []
        for sid in todas:
            d = _d.view_data(sid)
            t = str(d.get("title") or "").strip() or "(sin título)"
            bloques.append(f"── HOJA «{t}» ──\n" + _digest.one(d))
        return "\n".join(bloques)
    return _digest.one(_d.view_data(todas[0]))


from . import data as _d          # noqa: E402 — the facade; read at call time, never at import
from . import digest as _digest   # noqa: E402
