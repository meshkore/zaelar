"""What the turn's verdict says about a CARD: the action it is sure of, whether it lands inside the card or
escalates, whether it endorses the model's call. Moved from `nucleo/flash/direct_action.py` (refactor2710-05 T-04);
its names are read through `_da`."""
from __future__ import annotations

from nucleo.flash import direct_action as _da


def verdict_card(brief) -> str:
    """The card the verdict names, OPEN OR NOT — for a close, a card already gone is an answer («nothing left to
    do»), not a reason to look for another one (demo pass 2026-09-28, V7)."""
    try:
        from nucleo.flash import turn_brief as _tb
        choice, _info = _tb.read(brief, _tb.TARGET_KEY, "")
        owner, sep, _name = str(choice or "").rpartition(":")
        return owner if sep else ""
    except Exception:  # noqa: BLE001
        return ""


def order_is_inside(brief, widget_id: str = "") -> bool:
    """Does the verdict put this turn's order INSIDE a card — on one of its declared actions — so that a
    [[close]] of that same card is not the order?

    Measured live on the agenda (V2-770): «vale, ya la puedes cerrar» with a detail card open. The brief
    answered `screen_action = agenda:close_meeting` at 0.99; the model called exactly that AND emitted
    [[close]], the grammar saw «cerrar» and licensed the tag, and the canvas precedence closed the whole
    AGENDA. The canvas verb reads «close»; only the action question knows WHAT closes."""
    try:
        owner, name = _da.from_brief(brief)
        if not owner or not name:
            return False
        # With the CANVAS verdict sure of a close, only an equally sure action verdict says otherwise (demo pass
        # 2026-09-28, M4: «ok close that», close 1.00 vs agenda:close_meeting 0.55, closed the AGENDA, not the chart).
        if _da.sure_canvas(brief) == "close" and not _da._action_sure(brief):
            return False
        return not widget_id or _da._base_of(owner) == _da._base_of(widget_id)
    except Exception:  # noqa: BLE001
        return False


def _action_sure(brief, floor: float = 0.8) -> bool:
    try:
        from nucleo.flash import turn_brief as _tb
        _c, info = _tb.read(brief, _tb.TARGET_KEY, "", min_confidence=floor)
        return bool(info) and bool(info.get("used"))
    except Exception:  # noqa: BLE001
        return False


def verdict_shows(brief) -> bool:
    """Did the brief say, SURE, that this order brings a card up (`canvas = show`) on an order turn?

    V2-776 (verification after the demo pass, 2026-09-27): «Show me the monitors.» — canvas=show 0.98, the model
    said «Bringing the monitor comparison back up» and called nothing. The promise backstop that shows the named
    card gated on a verb table that knows «te lo abro», not «bringing it back up»; the verdict was already paid for."""
    try:
        from nucleo.flash import turn_brief as _tb
        verb, info = _tb.read(brief, _tb.CANVAS_KEY, "")
        if info is None or str(verb or "") != "show":
            return False
        kind, k = _tb.read(brief, _tb.REQUEST_KEY, "")
        return k is not None and str(kind) == "order"
    except Exception:  # noqa: BLE001
        return False


def aims_at_a_card(brief) -> bool:
    """Is this turn's order aimed at a CARD on screen — an action of one, or the canvas itself (show/close)?

    V2-773 (demo, kickoff + video): «Stop it and close the video widget» with the verdict at
    `youtube:close` 0.97 and canvas=close 1.0 — and the deterministic stop-worker backstop read «stop it» as
    «stop the background work» and CANCELLED the two errands launched a minute earlier. A verdict that names
    a card says whose the order is; a worker kill over it is the wrong reading of the same words."""
    try:
        from nucleo.flash import turn_brief as _tb
        if _da.from_brief(brief)[0]:
            return True
        verb, _info = _tb.read(brief, _tb.CANVAS_KEY, "neither")
        return str(verb or "") in ("show", "close")
    except Exception:  # noqa: BLE001
        return False


def verdict_escalates(brief, *, answered: bool = False) -> bool:
    """Did the brief say this order needs a WORKER (`escalate_or_inline = escalate`, sure) on an order turn?

    `answered` — the reply already ANSWERED and promised nothing. A QUESTION the model answered from memory is
    not an errand, whatever the verdict guessed before the answer existed (V2-773, demo R1, 2026-09-27: «When
    does my Tesla insurance renew?» → «March 12, 2027», verdict `escalate` 0.84, and a Brain Worker went to
    the web with a browser tab and a sheet over a fact the turn had just said). An order keeps the verdict:
    «find me three monitors» is work whether or not the reply sounds finished.

    V2-773 (demo kickoff, A1): «find me three 27-inch 4K monitors under 400 dollars» — the verdict said
    escalate, the model answered «On it — I'll show you the options as soon as I have them» and called
    nothing, and the promise backstop only knew the verb tables («hazme/búscame…»), so no errand was born.
    The verdict was paid for; it is the evidence the backstop was missing."""
    try:
        from nucleo.flash import turn_brief as _tb
        esc, info = _tb.read(brief, _tb.ESCALATE_KEY, "")
        if info is None or str(esc or "") != "escalate":
            return False
        kind, _k = _tb.read(brief, _tb.REQUEST_KEY, "")
        if _k is None or kind in _da.NOT_AIMED_AT_THE_SCREEN:
            return False
        return not (answered and str(kind) == "question")
    except Exception:  # noqa: BLE001
        return False


def order_over_a_card_left_undone(brief) -> bool:
    """A sure ORDER the catalogue addressed to a card, on a turn the caller knows called nothing and asked for
    nothing — the work is still owed (V2-773, demo F1, 2026-09-27): «Write me a one-page summary of the
    Declaration of Independence in a document» — the catalogue named `documento` (0.86), the card-or-worker
    pass got no call, the escalation verdict was unsure (0.15), the reply said «on its way» and nothing was on
    its way. The caller supplies «nothing called, nothing asked»; this reads only the verdicts."""
    try:
        from nucleo.flash import turn_brief as _tb
        kind, k = _tb.read(brief, _tb.REQUEST_KEY, "")
        if k is None or str(kind) != "order":
            return False
        card, c = _tb.read(brief, _tb.CATALOG_KEY, "")
        return c is not None and bool(card) and str(card) != "none"
    except Exception:  # noqa: BLE001
        return False


def reads_as_order(brief) -> bool:
    """The verdict read this turn as an ORDER — whatever card it names, or none.

    The gate for the act repair when no card was named yet (demo pass 2026-09-28, W1: «put griffith observatory,
    mount baldy and the getty on a map» → «I'll pull those three up on the map for you.», no call, no card open, and
    the promise-wording table knew neither «I'll pull up» nor «I'll put»). The repair finds the card through the
    late catalogue question and judges its own reply; a verb table is not needed for either."""
    try:
        from nucleo.flash import turn_brief as _tb
        kind, info = _tb.read(brief, _tb.REQUEST_KEY, "")
        if info is not None and str(kind or "") == "order":
            return True
        # …or the words question's sure «he only asks for something DONE» (demo pass 2026-09-28, full11 C5: `order`
        # 0.46, `act` 0.92; «Sending it now» over nothing, and the repair was never asked).
        words, winfo = _tb.read(brief, _tb.WORDS_KEY, "")
        return winfo is not None and str(words or "") == "act"
    except Exception:  # noqa: BLE001
        return False


def completes(brief, widget_id: str, *, model_action: str = "") -> str:
    """The verdict's action on THIS card when it is confident, still open and NOT what the model
    called; "" otherwise. The narrow question both arbitration sites ask (V2-754)."""
    wid, name = _da.from_brief(brief)
    if not wid or not name or _da._base_of(wid) != _da._base_of(widget_id):
        return ""
    return "" if name == (model_action or "") else name


def endorses(brief, widget_id: str, action: str = "") -> bool:
    """Does the turn's verdict point at THIS card (and optionally this action)?

    The predicate a grammar license consults before vetoing a tool. `video_license` and its family
    read a table of conjugated verbs, and the table cannot be complete — it had no «preparar» and no
    «podrías», so a plain, polite Spanish request for videos read as context-bleed. The verdict is
    enumerated from the manifests and calibrated; where the two disagree the verdict is the one that
    was asked the question.

    Narrow on purpose: it only ever GRANTS. A license that the grammar already granted is untouched,
    so this can add a permitted call and can never remove one.
    """
    wid, name = _da.from_brief(brief)
    if not wid:
        return False
    if _da._base_of(wid) != _da._base_of(widget_id):
        return False
    return (not action) or name == action


def take_rung(escalate_req: dict, *, brief, operator_text: str, emit, present,
              apply_widget_data) -> bool:
    """Try the rung and SPEND it. `True` when a declared action took the commission's place.

    The body lives here and not in the voice provider for the reason the architecture ratchet keeps
    giving: that file is a god file and the answer to «this block grew» is «extract a module, do not
    raise the ceiling» (V2-726 A7, V2-740). It also means the text channel gets the identical rung
    the day it fires a brief of its own, instead of a hand-mirrored copy — V2-252's rule.

    The caller owns the two facts this cannot know: that a commission survived every guard above, and
    that nothing in the turn acted. Those are the whole precondition — this rung may only ever
    replace *spending minutes*, never a result the turn already produced.
    """
    try:
        rung = _da.resolve(str(escalate_req.get("v") or ""), brief=brief, operator_text=operator_text)
    except Exception:  # noqa: BLE001 — a classifier may never break a turn
        return False
    if not rung:
        return False
    try:
        present(_da.card_to_present(rung["widget"], operator_text), reason="turn-order", src="flash", emit=emit)
        apply_widget_data(rung["widget"], rung["action"], rung["payload"])
        emit("brain", "🎯 acción declarada en vez de un worker", text=rung["label"][:120],
             role="system",
             extra={"cat": "flash", "widget": rung["widget"], "action": rung["action"],
                    "source": rung["source"], "instead_of": str(escalate_req.get("v") or "")[:120]})
    except Exception:  # noqa: BLE001
        return False
    escalate_req["v"] = None
    escalate_req["more"] = []
    return True


def verdict_elsewhere(brief, widget_id: str) -> bool:
    """The verdict SURELY names an action on a card other than `widget_id` — the turn is about something else."""
    wid, name = _da.from_brief(brief)
    return bool(wid and name) and _da._base_of(wid) != _da._base_of(widget_id) and _da._action_sure(brief)


def order_card_after_read(brief, operator_text: str, read_widget: str) -> str:
    """The card an ORDER is on when the turn read a DIFFERENT card for it, or "": the brief is sure it is an order
    and his words name exactly one other card (by its name, an alias or a word it declares)."""
    try:
        from nucleo.flash import turn_brief as _tb
        kind, info = _tb.read(brief, _tb.REQUEST_KEY, "", min_confidence=0.8)
        if str(kind or "") != "order" or not info:
            return ""
        # Demo pass 62, C2: verdict `agenda:find_free` 0.91, the model ran it, and this still sent the order to the
        # monitors sheet. A verdict SURE the order is on the card the turn touched means there is no other card.
        target, t_info = _tb.read(brief, _tb.TARGET_KEY, "", min_confidence=0.8)
        owner = str(target or "").rpartition(":")[0]
        if t_info and owner and _da._base_of(owner) == _da._base_of(read_widget):
            return ""
        named = [c for c in _da.named_cards(operator_text) if _da._base_of(c) != _da._base_of(read_widget)]
        return _da._base_of(named[0]) if len(named) == 1 else ""
    except Exception:  # noqa: BLE001
        return ""
