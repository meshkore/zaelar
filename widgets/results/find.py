"""widgets/results/find.py — which item the operator means, and what the brain is told is on the sheet:
`_named`/`_find` resolve a reference (title, ordinal, badge), `ref_index`/`prompt_digest` publish the sheets.

Moved out of `widgets/results/data.py` (refactor2710-12). Every module-level name of `data` that tests patch
(`view_data`, `sheets`) is read through it (`_d.<name>`), so a patch on `data` still governs every call; `data`
re-exports these names because `widgets/refs.py` looks `ref_index`/`prompt_digest` up there.
"""
import re as _re

from i18n import langs as _langs


def _named(payload: dict) -> str:
    """The item a payload names, under whichever key the caller used. Demo pass 2026-09-28 (S3): «open the one
    that's the best deal» arrived as `detail {"item": "Dell S2725QS"}` — the name of the first row, under the
    key other cards (map, youtube) use for a row — and was answered «I can't find that result on the sheet»."""
    for k in ("title", "item", "name"):
        v = payload.get(k)
        if isinstance(v, str) and v.strip():
            return v
    return ""


def _find(items: list[dict], title: str = "", index=None) -> dict | None:
    """Resolve WHICH item the operator means. By exact title, else by a forgiving contains-match, else by ordinal.
    The ordinal matters because this arrives from VOICE: "show me proposal number one" is far more likely to
    survive STT intact than a hotel's full commercial name, so the caller may pass index=1 instead of a title."""
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
    # Demo pass 63, S3: «open the one that's the best deal» arrived as title «KTC H27P22S — $254.98» — the compare
    # view's own line, title AND price — and neither match above holds. The head before the decoration is the title;
    # and a row whose whole title sits inside the reference is named by it (one such row, never a guess).
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
    # …and by the BADGE the sheet shows him (V2-776, verification 2026-09-27): «Open the best value option» over a
    # sheet whose cards say BEST VALUE / BEST REVIEWED / CHEAPEST found nothing — only titles and ordinals were
    # read, and the words he used are printed on the card itself. One badge named = that item; two = no guess.
    named = [it for it in items if (b := str(it.get("badge") or "").strip().lower()) and b in t]
    return named[0] if len(named) == 1 else None


def _sheets_for_brain(sheet) -> list[str]:
    """WHICH sheets the brain sees. With `sheet` given, that one; without it, ALL that exist.

    Making the default «all» is deliberate, and the opposite fails silently: with two live tasks, reading only one
    would leave the turn answering confidently about the wrong sheet —«¿el hotel de la propuesta 2 tiene wifi?»
    resolved against the plumber's search— with nothing indicating another existed. It is the same kind of lie that
    V2-257 removed from the card: not a smaller truth, but a different and false one.
    """
    if sheet is not None and _d._safe_sheet(sheet):
        return [_d._safe_sheet(sheet)]
    if sheet == "":
        return [""]
    found = _d.sheets()
    return found or [""]


def ref_index(sheet=None) -> list[dict]:
    """The items currently ON SCREEN, so the brain can (a) let the operator pick one by talking about it ("keep
    the beach club one") and (b) — just as important — SEE that the sheet is empty. Before this, an open but
    blank results card was indistinguishable from a card that simply doesn't publish its items, and the brain
    answered "here it is" over an empty screen (real session, 12:57:57).

    The hint leads with the ORDINAL because that is how the operator refers to a proposal out loud ("number two");
    without it the brain had to guess which card "the second one" was.

    V2-259 — with several sheets open, each reference says WHICH ONE it belongs to. The ordinal only disambiguates
    within a sheet: «number two» with two searches on screen refers to two different things, and without the task
    in front of it the turn would silently choose one.
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
    """What is ACTUALLY on screen, compact enough to ride in every prompt while this widget is open.

    Why this exists: `ref_index()` only publishes title+hint, so the brain could name the items but knew nothing
    about them. Asked "does the hotel in proposal 2 have wifi?" — about a result already on screen, whose own
    card says so — it had to either guess or escalate a whole new search for a fact it was already holding. That
    is the difference between a screen the agent can SEE and one it merely painted. Bounded on purpose: this is
    a digest for reasoning over, not the full dossier (that lives in the detail view).

    V2-259 — with several sheets, ALL are traversed and each block opens with the task it belongs to. The alternative
    (keeping one) gives no warning: the turn would confidently answer about the wrong search, the same kind of lie
    that V2-257 removed from the card. The item limit is PER SHEET.
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
