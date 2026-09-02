"""widgets/instances.py — WHICH CARD the operator means when a piece has several open (V2-259 F3).

Literal operator request: «if there are 2 results widgets and the user says "close the results", the command
should ask: which of the 2 searches should I close, the car one or the plumber one?». 

This is a NEW AMBIGUITY, on a different axis from the one already handled by `runtime.identify()`. That one decides WHICH PIECE
(«results» → `results`) and asks when there is no name or alias match (V2-082). This one comes afterward: the
piece is clear and what is unknown is WHICH OF ITS CARDS. It could not exist before, because the only instantiated piece
was the browser and its cards close themselves when the task ends; since the sheet became instantiated
(V2-259), the operator has two identically named boxes in front of them.

THREE DECISIONS, each with an obvious opposite:

  · **Ask, do not choose.** With two sheets, closing «the first» or «the last» is right half the time, and the
    other half it erases the search the operator was viewing — without telling them. It is the same V2-082 rule,
    already written down: without certainty, ASK.
  · **The question names the REQUESTS, not the ids.** «¿results::t1 o results::t2?» is not a question, it is a
    dump. Each sheet's title is already what the operator requested («Plumbers in central Madrid»), so the
    question writes itself using what they said.
  · **One decision for the THREE places that close.** `voice/engine/llm/providers/nucleo.py` emits
    `widget/close` with an id from three different points (the close≠delete guard, the turn backstop, and the
    canvas fallback). Writing the rule three times is exactly how one copy ends up missing — for the fourth
    time this week, and in V2-256 the missing copy caused a submission to fail silently.

Pure and stateless: it receives what is open and returns the decision. Fail-soft in the sense that matters here —
when unsure whether there is ambiguity, it does NOT ask: a spurious question on every close would be worse than the
failure this removes.
"""
from __future__ import annotations

import re as _re
import unicodedata as _ud

SEP = "::"


def base_of(widget_id) -> str:
    """`results::t7` → `results`. An id without an instance is its own base."""
    return str(widget_id or "").split(SEP, 1)[0].strip().lower()


def instances_of(base: str, open_ids) -> list[str]:
    """The OPEN cards for this piece, with their full ids and in the order reported by the canvas."""
    b = base_of(base)
    out: list[str] = []
    for wid in (open_ids or []):
        w = str(wid or "").strip()
        if w and base_of(w) == b and w not in out:
            out.append(w)
    return out


def _label(widget_id: str) -> str:
    """What THIS card is called for the operator: the request it displays, not its id.

    Only the sheet knows how to title itself today; for any other piece it falls back to the suffix, which at least
    distinguishes it. It never crashes: this is called in the middle of a voice turn.
    """
    inst = str(widget_id or "").split(SEP, 1)[1] if SEP in str(widget_id or "") else ""
    if base_of(widget_id) == "results":
        try:
            from widgets.results import data as _sheet
            t = str((_sheet.view_data(inst) or {}).get("title") or "").strip()
            # «Resultados» is the filler that `view_data` supplies when there is no title (setdefault), not a name:
            # returning it would make two sheets without a request have the same name and leave the question unable to distinguish anything.
            if t and t.lower() != "resultados":
                return t
        except Exception:  # noqa: BLE001
            pass
    return inst or str(widget_id or "")


def _distinguibles(etiquetas: list[str], ids: list[str]) -> list[str]:
    """A question that cannot be answered is not a question.

    Two sheets without a title, or with the same title, would produce «¿cuál cierro, «Resultados» o «Resultados»?», which is worse
    than not asking: it forces the operator to answer something that distinguishes nothing. When labels collide,
    the only thing guaranteed to differ — their instance — is added to them.
    """
    if len(set(etiquetas)) == len(etiquetas):
        return etiquetas
    out = []
    for et, wid in zip(etiquetas, ids):
        inst = str(wid).split(SEP, 1)[1] if SEP in str(wid) else str(wid)
        out.append(f"{et} ({inst})" if et and et != inst else inst)
    return out


_EVERY_RE = _re.compile(
    r"\b(?:ambos|ambas|todas?|todos|both|all\s+of\s+them|"
    r"(?:los|las)\s+(?:dos|tres|cuatro|\d+))\b", _re.I)


def wants_every(text: str) -> bool:
    """Does the operator mean ALL the open cards of this piece, rather than one of them?

    Measured 2026-08-31 (session `7cab1afd`): with two results sheets open the operator said «cierra los dos»
    and got the disambiguation question BACK — «¿cuál te enseño, "…" o "…"?» — then said «cierra las dos» and
    got it again. He had answered it. The question asks WHICH ONE and the answer was BOTH, an option the
    resolver had no way to express, so every rephrasing round-tripped into the same question.

    A QUANTIFIER, not a verb table: «los dos», «ambas», «todas», «both». What to DO with them is already
    decided by the caller — this only says how many cards the order reaches.
    """
    if not text:
        return False
    return bool(_EVERY_RE.search(_strip_accents(str(text))))


def _strip_accents(text: str) -> str:
    return "".join(c for c in _ud.normalize("NFKD", text or "") if not _ud.combining(c))


def resolve_close(target, open_ids, text: str = "") -> dict:
    """WHICH card a «ciérralo» refers to.

    Returns `{"id": <id a cerrar> | None, "ids": [...], "ask": <pregunta> | "", "options": [...]}`:

      · the operator already named an instance (`results::t7`)       → that one, without asking
      · the piece has 0 or 1 open cards                               → the id as-is (closing an already closed one is
                                                                        a harmless no-op, and that was the
                                                                        longstanding behavior)
      · two or more, and the turn says HOW MANY («los dos», «todas») → all of them, without asking (V2-530)
      · two or more                                                    → `ask`, and `id` set to None

    `ids` is the list to close and is ALWAYS present — a caller that iterates over `ids` is correctly written for all four
    cases, and that is the difference between reading `id` and losing the «los dos» response in two of the three places
    that close. `id` is retained so as not to break anyone.
    """
    tid = str(target or "").strip()
    if not tid:
        return {"id": None, "ids": [], "ask": "", "options": []}
    if SEP in tid:
        return {"id": tid, "ids": [tid], "ask": "", "options": []}   # already disambiguated; nothing to ask
    abiertas = instances_of(tid, open_ids)
    if len(abiertas) <= 1:
        _one = abiertas[0] if abiertas else tid
        return {"id": _one, "ids": [_one], "ask": "", "options": abiertas}
    if wants_every(text):
        return {"id": None, "ids": list(abiertas), "ask": "", "options": abiertas}
    etiquetas = _distinguibles([_label(w) for w in abiertas], abiertas)
    if len(etiquetas) == 2:
        cuales = f"«{etiquetas[0]}» o «{etiquetas[1]}»"
    else:
        cuales = ", ".join(f"«{e}»" for e in etiquetas[:-1]) + f" o «{etiquetas[-1]}»"
    return {"id": None, "ids": [], "ask": f"Tienes {len(abiertas)} abiertas: ¿cuál cierro, {cuales}?",
            "options": abiertas}


def resolve_show(target, open_ids, text: str = "") -> dict:
    """WHICH card a «enséñamelo» refers to — the mirror image of `resolve_close`, measured from the opposite side (V2-300).

    Round 24 of `search-buy-guitar__es` (2026-08-24): the request's sheet (`results::58c1af-1`) was OPEN
    with 20 rows, the operator asked to see a result, the model showed bare `results`… and the canvas opened the
    BARE, empty box — «Te lo abro, aunque de momento está vacío» on a screen with the delivery beside it.
    The V2-209 guard did its part (it told the truth about the wrong box); what was missing was opening the
    CORRECT box. Same contract as closing: the base with ONE live instance in front resolves to that
    instance; with several it ASKS by naming requests; with none, the usual base.
    """
    tid = str(target or "").strip()
    if not tid:
        return {"id": None, "ids": [], "ask": "", "options": []}
    if SEP in tid:
        return {"id": tid, "ids": [tid], "ask": "", "options": []}   # ya vino desambiguado
    abiertas = instances_of(tid, open_ids)
    if not abiertas:
        return {"id": tid, "ids": [tid], "ask": "", "options": []}   # no instances: the base, as always
    if len(abiertas) == 1:
        return {"id": abiertas[0], "ids": [abiertas[0]], "ask": "", "options": abiertas}
    if wants_every(text):
        return {"id": None, "ids": list(abiertas), "ask": "", "options": abiertas}
    etiquetas = _distinguibles([_label(w) for w in abiertas], abiertas)
    if len(etiquetas) == 2:
        cuales = f"«{etiquetas[0]}» o «{etiquetas[1]}»"
    else:
        cuales = ", ".join(f"«{e}»" for e in etiquetas[:-1]) + f" o «{etiquetas[-1]}»"
    return {"id": None, "ids": [], "ask": f"Tienes {len(abiertas)} abiertas: ¿cuál te enseño, {cuales}?",
            "options": abiertas}
