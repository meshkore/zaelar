"""widgets/results/digest.py — the SHEET AS THE BRAIN SEES IT: what travels in every turn prompt while the
card is open.

Extracted from `widgets/results/data.py` on 2026-08-24 because the architecture ratchet asked for a module
instead of a taller ceiling, and this was the seam already there: everything here is a pure function of one
sheet's data dict, reads no store and writes nothing. `data.py` keeps `prompt_digest()` — it is the one piece
that needs the store (which sheets exist, and their contents) and it is the name `widgets/refs.py` looks up by
convention.

What lives here is the rule that a digest is a SUMMARY FOR REASONING and not the record: it is bounded twice,
by this module's own header ceiling and by `refs._MAX_DIGEST_CHARS` over the whole thing, and both ceilings
exist because the same mistake keeps costing the same way — the part that gets clipped is the part at the
bottom, so anything the turn must not lose goes UP, not down (see `head` and V2-287's link line).
"""
from __future__ import annotations


def _t(key: str, default: str, **kw) -> str:
    """One line of this digest in the INSTANCE's language (`results.digest.<key>` of the `ui` pack), English floor
    (V2-831): the brain reads it every turn the sheet is open, and it was Spanish in every session."""
    try:
        from i18n import runtime as _rt
        tpl = _rt.text(f"results.digest.{key}", default=default)
    except Exception:  # noqa: BLE001 — the English line is an honest fallback, never a key
        tpl = default
    for k, v in kw.items():
        tpl = tpl.replace("{" + k + "}", str(v))
    return tpl


_MAX_HEAD_CHARS = 620      # header ceiling: the RESULTS must not be left without room (see _digest_head)
_MAX_HEAD_LIST = 4         # criterios/fuentes que se enumeran; el resto se cuenta
_MAX_HEAD_ITEM = 90


def _head_list(items, label: str) -> str:
    """A header list, bounded AND counted. Enumerating 14 hard criteria at 220 chars each is 3 KB in EVERY turn prompt
    — and would also consume the digest budget, leaving out the actual results. Show the first ones and SAY how many
    remain (silencing the rest would imply there are no more)."""
    xs = [str(x)[:_MAX_HEAD_ITEM] for x in (items or [])]
    if not xs:
        return ""
    out = f"  {label}: " + " · ".join(xs[:_MAX_HEAD_LIST])
    if len(xs) > _MAX_HEAD_LIST:
        out += f" (+{len(xs) - _MAX_HEAD_LIST})"
    return out


def head(data: dict) -> str:
    """The THREE tabs that are not the list, compressed for the prompt. This enables answering "why is nothing coming
    from that website?" or "what criterion did you discard by?" WITHOUT searching again: the data is already on screen,
    the brain only needed it in front of it.

    BOUNDED WITH ITS OWN CEILING, not only by the global digest cap: this header goes FIRST, so without its own limit
    long criteria would push results out of the clipping — the brain would know what is being searched for but not
    what was found, which is exactly the opposite of useful."""
    L: list[str] = []
    tab = data.get("tab") or "results"
    if tab != "results":
        L.append(_t("tab", "[the operator is looking at the «{tab}» tab]", tab=tab))
    s, c = data.get("summary") or {}, data.get("counts") or {}
    # Only REPORTED data opens the summary line. How many cards are on screen is already visible in the list right
    # below: announcing it separately bloated EVERY turn prompt while the sheet was open without saying anything new.
    bits = []
    if s.get("state"):
        bits.append(str(s["state"]))
    if s.get("explored"):
        bits.append(_t("explored", "{n} explored", n=s["explored"]))
    if s.get("discarded"):
        bits.append(_t("discarded", "{n} discarded", n=s["discarded"]))
    if bits:
        if c.get("shown"):
            bits.append(_t("shown", "{n} on screen", n=c["shown"]))
        L.append(_t("summary", "SUMMARY") + ": " + " · ".join(bits))
    if s.get("note"):
        L.append(f"  {s['note'][:_MAX_HEAD_ITEM * 2]}")
    # ORDER BY IRREPLACEABILITY, not by abstract importance: first comes what exists NOWHERE else. A source's status
    # ("Wallapop required login") is only known by this screen; criteria, by contrast, were said aloud and the brain
    # has them in recent conversation. So if the ceiling forces clipping, criteria are clipped and sources survive —
    # not the reverse, which was the old order.
    src = data.get("sources") or []
    if src:
        # And within sources, FAILED ones first: they are the ones that change an answer. Yachtworld going well adds
        # nothing to reasoning.
        order = sorted(src, key=lambda s0: 0 if s0.get("status") in ("auth", "blocked", "error", "partial") else 1)
        L.append(_t("sources", "SOURCES ({n}):", n=len(src)))
        for s0 in order[:6]:
            _st = str(s0.get("status") or "")
            bit = f"  · {s0.get('name','')}: {_t('status.' + _st, _st) if _st else ''}"
            if s0.get("found"):
                bit += _t("found", ", {n} results", n=s0["found"])
            if s0.get("detail"):
                bit += f" — {s0['detail'][:_MAX_HEAD_ITEM]}"
            L.append(bit)
        if len(src) > 6:
            L.append(_t("more_sources", "  (+{n} more sources)", n=len(src) - 6))
    crit = data.get("criteria") or {}
    if crit.get("goal"):
        L.append(_t("goal", "CRITERIA · goal: {goal}", goal=crit["goal"][:140]))
    for key, label in (("hard", "hard"), ("changes", "operator's corrections")):
        row = _head_list(crit.get(key), _t(key, label))
        if row:
            L.append(row)
    out = "\n".join(L)
    if len(out) > _MAX_HEAD_CHARS:
        tail = _t("rest", "\n  (…the rest, on the card)")
        out = out[:_MAX_HEAD_CHARS - len(tail)].rsplit("\n", 1)[0] + tail
    return out


def one(data: dict) -> str:
    """The digest of ONE sheet. Extracted as-is so that N sheets do not mean N copies of these rules."""
    items = data.get("items") or []
    cabecera = head(data)
    if not items:
        return (cabecera + "\n" if cabecera else "") + _t("empty", "EMPTY sheet — no result on screen yet")
    lines = []
    if cabecera:
        lines.append(cabecera)
    # V2-287 — THE LINK IS ON THE CARD AND THE BRAIN COULD NOT KNOW IT.
    #
    # Every field of an item travels in this digest except the one the operator asks for by name. Measured on
    # `search-buy-guitar__es` (2026-08-24 03:48): the sheet held 42 rows and 42 of them carried a real Wallapop
    # url; the operator said «pásame esas dos con precio y enlace» and the turn answered by RELAUNCHING the
    # search to go and get links it was already holding. That answer is coherent with what it had in front of
    # it — nothing in the prompt said a link existed — so this is not disobedience, it is the same family as
    # the imperative that orders «cuéntale QUÉ has encontrado» to a turn holding nothing (V2-284).
    #
    # The url itself does NOT go in. `_MAX_DIGEST_CHARS` already clipped this sheet at item #6 of 42, and a
    # marketplace url is ~70 chars: carrying twelve of them would cost more than half the budget and push the
    # RESULTS out to make room for their addresses. What the brain needs is not the string — reading a url
    # aloud is useless anyway — it is the FACT that the row has one, so it stops paying for a search to
    # recover what is on screen.
    con_enlace = sum(1 for i in items if i.get("url"))
    if con_enlace:
        cuantos = (_t("links_all", "ALL these results carry") if con_enlace == len(items)
                   else _t("links_some", "{n} of the {total} results carry", n=con_enlace, total=len(items)))
        lines.append(_t("links", "[{who} their LINK saved in the card. If he asks for the link or the listing, do NOT "
                                 "search again: tell him which one it is and open its card.]", who=cuantos))
    # V2-782 — a criterion NO row can show is said missing, so the turn does not offer bare names as meeting it.
    from search.candidacy import unshown_criteria as _unshown
    _gap = _unshown(items, data.get("criteria") or {})
    if _gap:
        lines.append(_t("gap", "[NO row carries data (price, rating, phone) for: {gap}. Tell him that was NOT found; do "
                               "not present them as meeting it.]", gap=" · ".join(_gap)[:200]))
    if data.get("view") == "detail" and data.get("focus"):
        lines.append(_t("detail", "[looking at the DETAIL of «{focus}»]", focus=data["focus"]))
    for n, it in enumerate(items[:12], 1):
        fila = f"#{n} {it.get('title','')}"
        if it.get("price"):
            fila += f" — {it['price']}"
        if it.get("badge"):
            fila += f" [{it['badge']}]"
        lines.append(fila)
        if it.get("subtitle"):
            lines.append(f"   {it['subtitle']}")
        for p in (it.get("parts") or []):
            bit = f"   · {p.get('kind') or _t('part', 'part')}: {p.get('title','')}"
            if p.get("price"):
                bit += f" ({p['price']})"
            lines.append(bit)
            for f in (p.get("facts") or [])[:6]:
                lines.append(f"     - {f['label']}: {f['value']}")
        for f in (it.get("facts") or [])[:8]:
            lines.append(f"   - {f['label']}: {f['value']}")
        for ln in (it.get("lines") or [])[:3]:
            lines.append(f"   {ln}")
    if len(items) > 12:
        lines.append(_t("more_results", "(+{n} more results on the sheet)", n=len(items) - 12))
    return "\n".join(lines)
