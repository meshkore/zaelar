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


#: What a BLANK card is called. It is not a name, it is the only thing the operator can see about it — and the
#: measured session proves he reads it that way: «uno está vacío y el otro tiene la web del…».
BLANK_LABEL = "la que está en blanco"

#: A card name is SPOKEN, so it is capped at something sayable in one breath.
_LABEL_CHARS = 40


def card_face(widget_id: str) -> dict:
    """`{"label": what this card SHOWS, "blank": has it nothing to show}` — asked of the widget that owns it.

    V2-605. Only `results` and `navegador` instantiate cards, and only `results` could name its own; the browser
    fell through to `_label`'s id fallback, so «¿cuál te enseño, "t1" o "navegador"?» — a suffix and a base id —
    reached the operator five times. A piece that can have two cards has to be able to tell them apart, and the
    only component that can is the piece itself: `data.card_face(instance)`.

    Missing hook, or any failure inside it, means «I cannot describe this card» — an EMPTY face, never a guessed
    one. That keeps the old behaviour for every non-instantiating widget instead of inventing a label for it.
    """
    wid = str(widget_id or "").strip()
    base = base_of(wid)
    inst = wid.split(SEP, 1)[1] if SEP in wid else ""
    if not base:
        return {}
    try:
        import importlib
        face = getattr(importlib.import_module(f"widgets.{base}.data"), "card_face", None)
        if face is None:
            return {}
        out = face(inst) or {}
    except Exception:  # noqa: BLE001
        return {}
    if not isinstance(out, dict):
        return {}
    return {"label": str(out.get("label") or "").strip(), "blank": bool(out.get("blank"))}


def _label(widget_id: str) -> str:
    """What THIS card is called for the operator: what it SHOWS, never its id.

    The id fallback stays for a piece that declares no `card_face` — a suffix distinguishes two cards even when
    it does not describe them, and that is strictly better than nothing. It never crashes: this is called in the
    middle of a voice turn.
    """
    face = card_face(widget_id)
    if face.get("label"):
        # SPOKEN out loud, so it is capped: a page title carries the site's whole marketing line («Reserva en los
        # mejores restaurantes de España | TheFork») and a question is not a place to read one aloud. Cut at a
        # word so the tail is not a fragment.
        lab = " ".join(face["label"].split())
        return lab if len(lab) <= _LABEL_CHARS else lab[:_LABEL_CHARS].rsplit(" ", 1)[0] + "…"
    if face.get("blank"):
        return BLANK_LABEL
    inst = str(widget_id or "").split(SEP, 1)[1] if SEP in str(widget_id or "") else ""
    return inst or str(widget_id or "")


def _with_something_to_show(ids: list[str]) -> list[str]:
    """The cards that have SOMETHING on them, when at least one does.

    Measured 2026-09-07 (session `43b7bf79`): a task tab on thefork.es and a second browser card sitting on
    `about:blank`, and «ábreme el navegador» was answered with a question about which of the two. The operator's
    reply is the specification: *«uno está vacío y el otro tiene la web del… así que no creo que sea muy
    complicado saber la que te estoy preguntando»*. He is right, and it is not a fact about browsers: SHOWING
    somebody a card with nothing on it is never what they asked for while a sibling has content.

    Only ever narrows, and only when it leaves something: all-blank stays all-blank (then the question is real),
    and a piece whose cards cannot describe themselves reports no `blank` at all, so nothing is dropped.
    """
    live = [w for w in ids if not card_face(w).get("blank")]
    return live if live and len(live) < len(ids) else list(ids)


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
        # V2-605 — «la que está en blanco» is a DESCRIPTION, not a name, so once it collides it has already
        # failed at its only job: «¿"la que está en blanco (t1)" o "la que está en blanco (t2)"?» is longer than
        # the id dump and says exactly as much. When every candidate is blank the instance is all there is, and
        # that is the pre-existing contract this must not quietly change.
        if et == BLANK_LABEL:
            et = ""
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


def asked_already(ask: str, last_spoken: str) -> bool:
    """Did we just ask this very question and get no answer we could use?

    The ledger is the last thing we SAID, passed in by the caller — this module stays pure and stateless, and the
    channel already holds that string (`brain._last_spoken`). Compared on letters only, because the spoken copy
    goes through TTS sanitising and comes back with different punctuation; an empty `last_spoken` means «I do not
    know», which keeps the question.
    """
    a, b = _letters(ask), _letters(last_spoken)
    return bool(a) and bool(b) and a in b


def _letters(text: str) -> str:
    return "".join(c for c in _strip_accents(str(text or "")).lower() if c.isalnum())


def show_id(target, open_ids, text: str = "") -> str:
    """The card id to SHOW, resolved to a live instance when that is unambiguous — and never a question.

    V2-605 F2, found by driving the LIVE engine instead of trusting the bench. `resolve_show` was wired into the
    `show_widget` TOOL path in both channels, and «Enséñame el navegador» does not go through it: the model
    called no tool and emitted no tag, and the deterministic fallback resolved the WIDGET and emitted a show for
    the BARE id. Measured on the running engine at 11:45, with four cards reported by the canvas.

    Those backstop doors have no channel to ask through, so this one only ever NARROWS: base → the single live
    (or single non-blank) instance, else the base exactly as before. The asking version stays `resolve_show`,
    for the doors that can hold a conversation. Both share one body, which is the point — the close side has had
    «one decision for the THREE places that close» written at the top of this file since V2-259, and the show
    side had it in one place out of eight.
    """
    out = resolve_show(target, open_ids, text)
    return str(out.get("id") or target or "")


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


def resolve_show(target, open_ids, text: str = "", last_spoken: str = "") -> dict:
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
    # V2-605 — a card with NOTHING on it is never the one somebody asked to be SHOWN, so it is not a candidate
    # while a sibling has content. This is the half that removes the question instead of improving it, and it
    # belongs to SHOWING only: `resolve_close` keeps asking, because there the blank card is the CHEAP one to
    # get wrong and the full one is somebody's work. Same input, opposite risk, opposite default.
    abiertas = _with_something_to_show(abiertas)
    if len(abiertas) == 1:
        return {"id": abiertas[0], "ids": [abiertas[0]], "ask": "", "options": abiertas}
    etiquetas = _distinguibles([_label(w) for w in abiertas], abiertas)
    if len(etiquetas) == 2:
        cuales = f"«{etiquetas[0]}» o «{etiquetas[1]}»"
    else:
        cuales = ", ".join(f"«{e}»" for e in etiquetas[:-1]) + f" o «{etiquetas[-1]}»"
    ask = f"Tienes {len(abiertas)} abiertas: ¿cuál te enseño, {cuales}?"
    if asked_already(ask, last_spoken):
        # V2-605 — ASKED ONCE. Measured on session `43b7bf79`: this exact sentence was spoken FIVE times while
        # the operator answered it, rephrased it, protested and finally insulted it — because `clarify` replaces
        # the model's reply, so nothing the model wanted to say could ever break the loop, and the anti-repetition
        # nudge fired into a sentence the model does not write. A question the operator cannot escape is worse
        # than a choice he can correct: we pick the FIRST card — the oldest, the one that was already on his
        # screen when he started talking — and the caller SAYS which one, so correcting it costs one word.
        return {"id": abiertas[0], "ids": [abiertas[0]], "ask": "", "options": abiertas,
                "chose": _label(abiertas[0])}
    return {"id": None, "ids": [], "ask": ask, "options": abiertas}
