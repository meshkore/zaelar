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

import re

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


def recent_faces(limit: int = 5) -> list[dict]:
    """The cards an instancing piece could bring BACK, named by what they show — `[{"id", "label"}]`, most
    recent first. Asked of every piece that answers `data.recent_faces` (today: `results`, a finished errand's
    sheet). A closed sheet is still the operator's card (V2-773, demo S1: «Show me the monitors» over a closed,
    finished sheet went to a second worker). Never raises; a piece without the hook contributes nothing."""
    out: list[dict] = []
    try:
        import importlib
        from . import runtime as _rt
        for w in _rt.catalog():
            base = str(w.get("id") or "").strip()
            if not base:
                continue
            try:
                fn = getattr(importlib.import_module(f"widgets.{base}.data"), "recent_faces", None)
                rows = fn(limit) if fn else []
            except Exception:  # noqa: BLE001
                rows = []
            for r in rows or []:
                if isinstance(r, dict) and r.get("id") and r.get("label"):
                    out.append({"id": str(r["id"]), "label": str(r["label"])})
    except Exception:  # noqa: BLE001
        pass
    return out[:max(1, limit)]


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


def data_target(target, open_ids) -> str:
    """WHICH card a data-op on a BASE id lands on: the one open instance of that piece, when there is exactly one.

    V2-773 (demo, «Open the most interesting one» over a worker's sheet `results::9194df-1`): the model calls
    `widget_data(widget_id="results")` — the only name it has for the card — and the op ran on the base
    sheet, which is empty: «no encuentro ese resultado en la hoja». With one instance open there is nothing
    to ask; with several, the base travels as before and the ask paths above decide."""
    tid = str(target or "").strip().lower()
    if not tid or SEP in tid:
        return tid
    abiertas = instances_of(tid, open_ids)
    return abiertas[0] if len(abiertas) == 1 else tid


def also_named(text: str, open_ids, exclude=()) -> list[str]:
    """The OTHER open cards a sentence names — «Close the map and the results» closes both (V2-773). Read by
    the card's own id, name and aliases (the words it declares for itself), never by context; an open card the
    sentence does not name is left alone."""
    t = _strip_accents(str(text or "").lower())
    if not t:
        return []
    skip = {base_of(x) for x in (exclude or [])}
    out: list[str] = []
    try:
        from . import runtime as _rt
    except Exception:  # noqa: BLE001
        return []
    for wid in (open_ids or []):
        w = str(wid or "").strip()
        b = base_of(w)
        if not b or b in skip or w in out:
            continue
        man = _rt.get(b) or {}
        # …and what it is called in every language the catalogue has: the manifest's own name is ONE language, so
        # «close the calendar and the messages» never reached «Mensajería» (demo pass 2026-09-28, C6).
        try:
            from . import naming as _naming
            called = _naming.catalogue_names(b)
        except Exception:  # noqa: BLE001
            called = []
        words = ([b, str(man.get("name") or ""), str(man.get("title") or "")] + list(called)
                 + [str(a) for a in (man.get("aliases") or [])])
        words = [_strip_accents(x.lower()).strip() for x in words if str(x).strip()]
        if any(re.search(r"(?<![a-z0-9])" + re.escape(x) + r"(?![a-z0-9])", t) for x in words if len(x) >= 3):
            out.append(w)
    return out


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
    _named = _named_by_title(abiertas, text)
    if _named:
        return {"id": _named, "ids": [_named], "ask": "", "options": abiertas}
    etiquetas = _distinguibles([_label(w) for w in abiertas], abiertas)
    return {"id": None, "ids": [], "ask": _ask("close", len(abiertas), _which(etiquetas)), "options": abiertas}


_WORD = _re.compile(r"[^\W\d_]{4,}", _re.UNICODE)


def _which(etiquetas: list[str]) -> str:
    """«a» or «b» / «a», «b» or «c» — in the agent's language (demo pass 62, S1)."""
    try:
        from i18n import langs as _lg
        orw = _lg.current_language().instances_or
    except Exception:  # noqa: BLE001
        orw = "o"
    if len(etiquetas) == 2:
        return f"«{etiquetas[0]}» {orw} «{etiquetas[1]}»"
    return ", ".join(f"«{e}»" for e in etiquetas[:-1]) + f" {orw} «{etiquetas[-1]}»"


def _ask(kind: str, n: int, which: str) -> str:
    try:
        from i18n import langs as _lg
        tmpl = getattr(_lg.current_language(), f"instances_which_{kind}")
    except Exception:  # noqa: BLE001
        tmpl = "Tienes {n} abiertas: ¿cuál te enseño, {which}?" if kind == "show" else "Tienes {n} abiertas: ¿cuál cierro, {which}?"
    return tmpl.format(n=n, which=which)


def _named_by_title(abiertas: list[str], text: str) -> str:
    """The ONE open card whose title shares a distinctive word with the phrase, or "" (demo pass 62, S1: «so how did
    the monitors go, show me» with «27-inch 4K monitors under $400» and a second sheet open was asked «which one?»
    — `_closed_card_for` already chose by the title's words; an open card had no such reading)."""
    from .runtime import title_words
    said = title_words(text)
    if not said:
        return ""
    hits = [w for w in abiertas if said & title_words(_label(w))]
    return hits[0] if len(hits) == 1 else ""


def _closed_card_for(base: str, text: str) -> str:
    """With no card of `base` open, the CLOSED one with content that the phrase means — or "" for the bare base.

    Demo pass v7 (2026-09-27, S1): the monitor sheet had been closed two blocks earlier, «Show me the monitors»
    showed the bare `results` — EMPTY — and «compare them» / «open the best value» then worked on nothing. The
    sheet whose title shares a word with the phrase wins; with none sharing one, the only recent sheet if there is
    exactly one — several and no word to choose by is the base, as before."""
    rows = [r for r in recent_faces(8) if str(r.get("id") or "").split(SEP, 1)[0] == base]
    if not rows:
        return ""
    said = {w.lower() for w in _WORD.findall(str(text or ""))}
    for r in rows:
        if said & {w.lower() for w in _WORD.findall(str(r.get("label") or ""))}:
            return str(r["id"])
    # Nothing in the phrase names one: bring the sheet back only when there is ONE to bring. «The most recent»
    # opened the TRIP sheet for «Open the best value option» over the monitors (verification, 2026-09-27).
    return str(rows[0]["id"]) if len(rows) == 1 else ""


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
        back = _closed_card_for(tid, text)
        if back:
            return {"id": back, "ids": [back], "ask": "", "options": [back]}
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
    _named = _named_by_title(abiertas, text)
    if _named:
        return {"id": _named, "ids": [_named], "ask": "", "options": abiertas}
    etiquetas = _distinguibles([_label(w) for w in abiertas], abiertas)
    ask = _ask("show", len(abiertas), _which(etiquetas))
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
