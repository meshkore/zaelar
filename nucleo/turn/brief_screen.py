"""The brief's questions about the SCREEN: which declared action of an open card an order means (`screen_action`), or,
with nothing open, which catalogue card would carry it out (`catalog_widget`). Enumerated per turn (refactor2710-07)."""
from __future__ import annotations


TARGET_INSTRUCTIONS = (
    "The operator is looking at the screen and gives an order. Which declared action of the widgets "
    "ON SCREEN does it mean? Answer 'none' when the order is not aimed at anything on screen.")


#: A canvas with more than eight open cards is not a turn (a name: A4 added a second, different cap below it).
MAX_OPEN_CARDS = 8

#: How much of a declared action's `desc` reaches the question: 90 cut what made `youtube:show_tab` routable (V2-753).
MAX_DESC_CHARS = 200


def target_question(open_ids) -> dict | None:
    """One enumerated question over what is on screen, keyed by INSTANCE, or None when nothing is.

    Measured (V2-726 §4-bis): «which declared action» 0.94 (8/8) against «which widget» 0.26. Keyed by INSTANCE, only what
    is POSSIBLE NOW; both refine downwards only — anything unreadable keeps the candidate."""
    ids = [str(w).strip() for w in (open_ids or []) if str(w or "").strip()]
    if not ids:
        return None
    from nucleo.flash import frontend as _fe
    # Which card the conversation is ABOUT: the one his last turn acted on (demo pass 2026-09-28, E2/U3). Stated in the
    # instructions it moved 3/3 (as a card label 0/3), with the named-kind counterweights still 4/4 on their own card.
    try:
        from nucleo import canvas_focus as _cf
        focus = _cf.last_turn_card(ids)
    except Exception:  # noqa: BLE001
        focus = ""
    criteria: dict[str, str] = {}
    for wid in ids[:MAX_OPEN_CARDS]:
        face = _card_label(wid)
        for name, spec in (_fe.declared_actions(_base_of(wid)) or {}).items():
            if not _possible_now(wid, name):
                continue
            desc = str((spec if isinstance(spec, dict) else {}).get("desc") or name)[:MAX_DESC_CHARS]
            criteria[f"{wid}:{name}"] = f"[{face}] {desc}"
    if not criteria:
        return None
    criteria["none"] = "the order is not aimed at anything on screen"
    instructions = TARGET_INSTRUCTIONS
    if focus:
        instructions += (f" His previous turn acted on «{focus}». An order that points at something ALREADY on "
                         f"screen without naming it («it», «that», «this one», «the most important one», «pause») "
                         f"continues on that card when it can do it. An order that names a kind of thing (a song, a "
                         f"video, an email, a result, the calendar) goes to the card that holds that kind. An order "
                         f"that asks for NEW content («show me a red car», «find flights») is NOT continued by this: "
                         f"the previous turn never makes a search or a new lookup land on its card — judge such an "
                         f"order exactly as if nothing had been acted on.")
    return {"instructions": instructions, "criteria": criteria}


def _base_of(widget_id: str) -> str:
    """`results::t7` → `results`. The manifest belongs to the base; the candidate to the instance."""
    try:
        from widgets import instances as _inst
        return _inst.base_of(widget_id) or widget_id
    except Exception:  # noqa: BLE001
        return widget_id


def _card_label(widget_id: str) -> str:
    """What THIS card is showing, in his terms («YouTube: paused · Música: playing»); falls back to the id."""
    try:
        from widgets import instances as _inst
        label = str((_inst.card_face(widget_id) or {}).get("label") or "").strip()
        return f"{widget_id} — {label}"[:110] if label else widget_id
    except Exception:  # noqa: BLE001
        return widget_id


def _possible_now(widget_id: str, action: str) -> bool:
    """Can this action run on THIS card now? Unknown means YES; only an action that must name an EXISTING row on a card that publishes none is out."""
    try:
        from widgets import refs as _refs
        base = _base_of(widget_id)
        field = _refs.id_field_for_action(base, action) or ""
        if not field or _refs.selector_is_optional(base, action, field):
            return True
        if not _refs._exposes_ref_index(base):
            return True                     # the widget does not publish rows: nothing to conclude
        rows = [r for r in _refs._ref_index(base) if r.get("field") == field]
        return bool(rows)
    except Exception:  # noqa: BLE001
        return True


#: V2-773 — «which card would carry it out or answer it», not «which card he names»: on ten sentences the cards read
#: 0.97-1.0 and the errands stayed none (0.63-0.86), where «Message Rowan on Telegram» had read none 0.63.
CATALOG_INSTRUCTIONS = (
    "The operator gives an order with no card of ours on screen. Which widget of the catalogue would CARRY IT "
    "OUT or ANSWER it — the card whose declared actions do what he asks (send a message, add or move an "
    "appointment, play a song, show photos) or whose content holds the answer (his calendar, his contacts, his "
    "files)? Answer 'none' when the order needs the outside world (the web, a booking at an external site, "
    "products, a trip) or fits no widget.")

#: A catalogue question is worth one when the whole catalogue fits in it; past this it is retrieval, not enumeration.
MAX_CATALOG_CANDIDATES = 40


def catalog_question() -> dict | None:
    """Which widget the order NAMES, enumerated as «Name» + aliases + desc (8/9; desc alone 6/9, V2-726 §4-bis)."""
    try:
        from widgets import runtime as _rt
        rows = []
        for w in _rt.catalog():
            wid = str(w.get("id") or "").strip()
            if not wid:
                continue
            name = str(w.get("name") or w.get("title") or wid).strip()
            aliases = [str(a).strip() for a in (w.get("aliases") or []) if str(a or "").strip()]
            desc = str(w.get("description") or w.get("desc") or "").strip()
            said = " · ".join(dict.fromkeys(aliases[:6]))
            rows.append((wid, f"«{name}»" + (f" ({said})" if said else "") + (f" — {desc}" if desc else ""))) 
        if not rows or len(rows) > MAX_CATALOG_CANDIDATES:
            return None
        criteria = {wid: text[:160] for wid, text in rows}
        criteria["none"] = "the order does not name any widget"
        return {"instructions": CATALOG_INSTRUCTIONS, "criteria": criteria}
    except Exception:  # noqa: BLE001
        return None


#: refactor2710-07 — does the thing he NAMES exist on screen? («Close the weekend.» with the video open took the video.)
NAMES_KEY = "names_a_card"
NAMES_ELSEWHERE = "elsewhere"


def names_question(open_ids) -> dict | None:
    """Is what his sentence names one of the cards on screen? None with nothing open (nothing to compare with)."""
    ids = [str(w).strip() for w in (open_ids or []) if str(w or "").strip()]
    if not ids:
        return None
    labels = ", ".join(_card_label(w) for w in ids[:MAX_OPEN_CARDS])
    return {"instructions": f"The cards on screen are: {labels}. What does the operator's sentence name as the thing to act on?",
            "criteria": {"on_screen": "at least one thing he names is a card on screen — by its name, by what it shows, "
                                      "or by a pronoun pointing at it («close it», «quita eso», «the video») — even "
                                      "when he ALSO names something that is not",
                         NAMES_ELSEWHERE: "NOTHING he names is one of those cards: only things such as a period of "
                                          "time, a plan, a task, an event, a message, a person, another app",
                         "nothing": "no object at all, or everything on screen at once"}}


def names_elsewhere(handle, *, against_a_call: bool = False) -> bool:
    """He named something NOT on screen: an unnamed close takes nothing (licence); a close the model named, only at the veto.
    A sure close that this would stop first asks which ON-SCREEN cards he names to close (`named_to_close`)."""
    from nucleo.turn import verdicts
    choice, info = verdicts.read(handle, NAMES_KEY, "")
    held = (verdicts.against_the_model(handle, NAMES_KEY, lambda c: c != NAMES_ELSEWHERE) == verdicts.VETOED
            if against_a_call else bool(info and info.get("used")) and choice == NAMES_ELSEWHERE)
    return held and not named_to_close(handle)


#: ONE closed question, asked only when the names verdict would stop a sure close: one candidate per card on screen.
CLOSE_PICK = {"named": "he names this card to close (any word for it, any language)", "not_named": "he does not"}


def named_to_close(handle) -> list[str]:
    """The cards on screen he names to close: ONE yes/no per card, one trip, cached; [] = none or unaskable. Not FIT grades:
    live (pass 4, C6) they split the agenda's «yes» (strong 0.44 · partial 0.31 · no 0.25), dropped at margin 0.16."""
    if isinstance(handle, dict) and "_close_picks" not in handle:
        from nucleo.turn import verdicts
        said, ids = str(handle.get("judged") or "").strip()[:300], [str(w) for w in handle.get("open_ids") or [] if str(w)]
        try:
            qs = {f"card_{n}": {"instructions": f"CARD ON SCREEN: «{_card_label(w)}». Does he name THIS card to close?",
                                "criteria": dict(CLOSE_PICK)} for n, w in enumerate(ids[:MAX_OPEN_CARDS], 1)} if said else {}
            got = __import__("nucleo.jev", fromlist=["x"]).choose_many_sync(f"The operator said «{said}».", qs, question_id="close_pick") if qs and str(verdicts.read(handle, "canvas", "", min_confidence=verdicts.VETO)[0]) == "close" else {}
        except Exception as e:  # noqa: BLE001 — unaskable: the names verdict stands
            got = __import__("loguru").logger.debug(f"brief_screen: close pick not asked — {e!r}") or {}
        handle["_close_picks"] = [w for n, w in enumerate(ids[:MAX_OPEN_CARDS], 1) if float((((got or {}).get(f"card_{n}") or {}).get("probs") or {}).get("named") or 0.0) >= verdicts.LICENCE]
    return list(handle.get("_close_picks") or []) if isinstance(handle, dict) else []


ITEM_REF_KEY = "item_ref"
#: Rows enumerated per brief: a queue on screen is a handful; past that no self-correction is read.
MAX_ITEM_ROWS = 12


def item_ref_question(open_ids) -> dict | None:
    """Which listed row, if any, did he name and then TAKE BACK («el último… no, el penúltimo»)? Asked over the rows
    that EXIST, never read off correction words. None with fewer than two rows on screen."""
    from widgets import refs as _refs
    rows = []
    for wid in [str(w).strip() for w in (open_ids or []) if str(w or "").strip()][:MAX_OPEN_CARDS]:
        base = _base_of(wid)
        rows += [(base, i, r) for i, r in enumerate(_refs._ref_index(base), 1)]
    rows = rows[:MAX_ITEM_ROWS]
    if len(rows) < 2:
        return None
    criteria = {f"{b}#{r['id']}": f"row {i} of {_card_label(b)} («{str(r['label'])[:60]}») — he named it and then "
                                  "corrected himself, naming another row instead" for b, i, r in rows}
    criteria["none"] = "he takes back no row: every row he names is meant, or he names none"
    return {"instructions": "Rows listed on screen, numbered from the top. In one breath the operator may name a row and "
                            "then correct himself («the last… no, the second to last»). Which row did he TAKE BACK?",
            "criteria": criteria}


def withdrawn_rows(handle, base: str) -> set[str]:
    """Ids of the rows of `base` the brief, at its licence, says he named and took back."""
    from nucleo.turn import verdicts
    choice, info = verdicts.read(handle, ITEM_REF_KEY, "")
    if info and info.get("used") and str(choice).startswith(f"{base}#"):
        return {str(choice).split("#", 1)[1]}
    return set()
