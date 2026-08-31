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


_STATUS_ES = {"ok": "entró", "partial": "entró con límite", "auth": "pedía autenticación",
              "blocked": "bloqueó el acceso", "error": "dio error", "pending": "pendiente"}


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
        L.append(f"[el operador está viendo la pestaña «{tab}»]")
    s, c = data.get("summary") or {}, data.get("counts") or {}
    # Only REPORTED data opens the summary line. How many cards are on screen is already visible in the list right
    # below: announcing it separately bloated EVERY turn prompt while the sheet was open without saying anything new.
    bits = []
    if s.get("state"):
        bits.append(str(s["state"]))
    if s.get("explored"):
        bits.append(f"{s['explored']} explorados")
    if s.get("discarded"):
        bits.append(f"{s['discarded']} descartados")
    if bits:
        if c.get("shown"):
            bits.append(f"{c['shown']} en pantalla")
        L.append("SUMARIO: " + " · ".join(bits))
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
        L.append(f"FUENTES ({len(src)}):")
        for s0 in order[:6]:
            bit = f"  · {s0.get('name','')}: {_STATUS_ES.get(s0.get('status'), s0.get('status', ''))}"
            if s0.get("found"):
                bit += f", {s0['found']} resultados"
            if s0.get("detail"):
                bit += f" — {s0['detail'][:_MAX_HEAD_ITEM]}"
            L.append(bit)
        if len(src) > 6:
            L.append(f"  (+{len(src) - 6} fuentes más)")
    crit = data.get("criteria") or {}
    if crit.get("goal"):
        L.append(f"CRITERIOS · objetivo: {crit['goal'][:140]}")
    for key, label in (("hard", "duros"), ("changes", "correcciones del operador")):
        row = _head_list(crit.get(key), label)
        if row:
            L.append(row)
    out = "\n".join(L)
    if len(out) > _MAX_HEAD_CHARS:
        tail = "\n  (…el resto, en la tarjeta)"
        out = out[:_MAX_HEAD_CHARS - len(tail)].rsplit("\n", 1)[0] + tail
    return out


def one(data: dict) -> str:
    """The digest of ONE sheet. Extracted as-is so that N sheets do not mean N copies of these rules."""
    items = data.get("items") or []
    cabecera = head(data)
    if not items:
        return (cabecera + "\n" if cabecera else "") + "hoja VACÍA — no hay ningún resultado en pantalla todavía"
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
        cuantos = ("TODOS estos resultados llevan" if con_enlace == len(items)
                   else f"{con_enlace} de los {len(items)} resultados llevan")
        lines.append(f"[{cuantos} su ENLACE en la ficha, ya en pantalla. Si te pide el enlace o el anuncio, NO "
                     "busques otra vez: dile de cuál es y ábrele su ficha.]")
    if data.get("view") == "detail" and data.get("focus"):
        lines.append(f"[viendo el DETALLE de «{data['focus']}»]")
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
            bit = f"   · {p.get('kind') or 'pieza'}: {p.get('title','')}"
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
        lines.append(f"(+{len(items) - 12} resultados más en la hoja)")
    return "\n".join(lines)
