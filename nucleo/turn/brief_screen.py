"""The brief's questions about the SCREEN: which declared action of an open card an order means (`screen_action`), or —
with nothing open — which card of the catalogue would carry it out (`catalog_widget`). Enumerated per turn from what is
open and what each card declares (refactor2710-07: moved out of `nucleo/flash/turn_brief.py`, unchanged).
"""
from __future__ import annotations


TARGET_INSTRUCTIONS = (
    "The operator is looking at the screen and gives an order. Which declared action of the widgets "
    "ON SCREEN does it mean? Answer 'none' when the order is not aimed at anything on screen.")


#: A canvas with more than eight open cards is not a turn. Kept as a name because A4 added a second
#: cap below it and the two are different decisions.
MAX_OPEN_CARDS = 8

#: How much of a declared action's `desc` reaches the question: 90 cut the sentence that made `youtube:show_tab`
#: routable («vuelve al catálogo» none 0.77 → show_tab 0.96 at 200, V2-753).
MAX_DESC_CHARS = 200


def target_question(open_ids) -> dict | None:
    """One enumerated question over what is on screen, keyed by INSTANCE, or None when nothing is.

    Measured (V2-726 §4-bis): «which widget» over descriptions put «dale al play» at 0.26; «which declared action of
    what is on screen» at 0.94, 8/8 — what disambiguates two open cards is what each can DO. The key is the INSTANCE
    (two `results` cards are two candidates; `instances.card_face` says what each SHOWS), and only what is POSSIBLE NOW
    is a candidate. Both refine DOWNWARDS only: anything unreadable keeps the candidate."""
    ids = [str(w).strip() for w in (open_ids or []) if str(w or "").strip()]
    if not ids:
        return None
    from nucleo.flash import frontend as _fe
    # Which card the conversation is ABOUT: the one his last turn acted on (demo pass 2026-09-28 — E2: «open the
    # most important one» right after the inbox came up read `results:detail`; U3: «pause it a sec» right after
    # the music started read `youtube:pause`). Two cards that can do the same thing differ in THIS, and the
    # question carried nothing that said it. Measured with the live reader: as a label on the card it moved
    # nothing (0/3); stated in the instructions, 3/3 — with the named-kind counterweights («pause the video»,
    # «next song», «the second monitor in the results») still 4/4 on their own card.
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
    """Can this action run on THIS card right now? Unknown always means YES. The only exclusion is declared: an action
    that must name an EXISTING row (`refs.id_field_for_action`, never `selector_for`, which would hide every creation
    action) on a card that publishes none."""
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


#: V2-773 — the question used to ask which card he NAMES («to open»), and an order a card carries out went
#: unnamed: «Message Rowan on Telegram» none 0.63, «Find me a free slot tomorrow» none 0.52 — both then spent
#: a Brain Worker. Asked as «which card would carry it out or answer it», measured on ten sentences: messaging
#: 1.0 / agenda 0.97 / música 1.0 / markets 0.99, and the errands stay none (weekend plan 0.79, a table at a
#: restaurant 0.86, monitors under $400 0.63).
CATALOG_INSTRUCTIONS = (
    "The operator gives an order with no card of ours on screen. Which widget of the catalogue would CARRY IT "
    "OUT or ANSWER it — the card whose declared actions do what he asks (send a message, add or move an "
    "appointment, play a song, show photos) or whose content holds the answer (his calendar, his contacts, his "
    "files)? Answer 'none' when the order needs the outside world (the web, a booking at an external site, "
    "products, a trip) or fits no widget.")

#: A catalogue question is worth one when the whole catalogue fits in it. Past this the answer is
#: retrieval, not a bigger enumeration (an index narrows, a model chooses).
MAX_CATALOG_CANDIDATES = 40


def catalog_question() -> dict | None:
    """Which widget the order NAMES, enumerated with the words each one answers to: «Name» + aliases + desc got 8 of 9
    (desc alone 6 of 9, V2-726 §4-bis). A miss is repaired in the widget's own declaration, which this makes reach the
    decision."""
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


#: refactor2710-07 — does the thing he NAMES exist on screen? An unnamed close («Close the weekend.» with only the video
#: open) took the only card: the canvas verdict reads «close» (0.94 live) and the model closes too, while what he named
#: is not a card at all. Whether a name points at a card on screen is a judgement about his sentence, asked here.
NAMES_KEY = "names_a_card"
NAMES_ELSEWHERE = "elsewhere"


def names_question(open_ids) -> dict | None:
    """Is what his sentence names one of the cards on screen? None with nothing open (nothing to compare with)."""
    ids = [str(w).strip() for w in (open_ids or []) if str(w or "").strip()]
    if not ids:
        return None
    labels = ", ".join(_card_label(w) for w in ids[:MAX_OPEN_CARDS])
    return {"instructions": f"The cards on screen are: {labels}. What does the operator's sentence name as the thing to "
                            "act on?",
            "criteria": {"on_screen": "at least one thing he names is a card on screen — by its name, by what it shows, "
                                      "or by a pronoun pointing at it («close it», «quita eso», «the video») — even "
                                      "when he ALSO names something that is not",
                         NAMES_ELSEWHERE: "NOTHING he names is one of those cards: only things such as a period of "
                                          "time, a plan, a task, an event, a message, a person, another app",
                         "nothing": "no object at all, or everything on screen at once"}}


def names_elsewhere(handle, *, against_a_call: bool = False) -> bool:
    """He named something NOT on screen: an unnamed close takes nothing (licence); a close the model named, only at the veto."""
    from nucleo.turn import verdicts
    if _calls_a_card_on_screen(handle):
        return False
    if against_a_call:
        return verdicts.against_the_model(handle, NAMES_KEY, lambda c: c != NAMES_ELSEWHERE) == verdicts.VETOED
    choice, info = verdicts.read(handle, NAMES_KEY, "")
    return bool(info and info.get("used")) and choice == NAMES_ELSEWHERE


def _calls_a_card_on_screen(handle) -> bool:
    """The screen outranks a single choice: the judged sentence calls a card open at fire time by its catalogue NAME,
    outside a «keep» clause (sandbox 2026-10-29 C6: «close the calendar and the messages», elsewhere 0.80, agenda open)."""
    try:
        from widgets import naming
        said = naming.without_kept(str((handle or {}).get("judged") or ""))
        return bool(said.strip()) and any(naming.says_the_name(said, w) for w in (handle or {}).get("open_ids") or [])
    except Exception:  # noqa: BLE001 — unreadable: the verdict stands
        return False


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
