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

#: How much of a declared action's `desc` reaches the question. It was 90, and 90 DECAPITATED the
#: sentence that made an action routable (V2-753, live session 46dcfcb4). `youtube:show_tab` declares
#: «CAMBIA de pantalla dentro del reproductor SIN tocar lo que está sonando. 'inicio' es el catálogo…
#: es lo que responde a «vuelve al catálogo», «a la página de inicio»» — V2-742 wrote that second
#: sentence INTO the manifest precisely so the decision could find the action, and the cut fell at
#: «'inicio' es el ca». Measured against the real API over the operator's own words: «vuelve al
#: catálogo» → `none` 0.77 at 90 chars, `youtube:show_tab` **0.96** at 200; «y tampoco vuelves al
#: inicio a ver el catálogo» 0.32 → 0.83. Nothing else moved (pause 1.00, next 0.94, search 0.99).
#: The price is +1.1 KB on a 4.7 KB question and no measurable latency (47 candidates, ~850 ms both).
#: ⚠️ This is the cheap half of a two-part rule: a description is product data and the place to
#: repair a routing miss (V2-726 §4-bis) — but only the part of it that ARRIVES can decide anything.
MAX_DESC_CHARS = 200


def target_question(open_ids) -> dict | None:
    """One enumerated question over what is on screen, keyed by INSTANCE, or None when nothing is.

    Measured (V2-726 §4-bis): asking «which widget» over widget DESCRIPTIONS put «dale al play» at
    0.26 — under the gate, discarded. Asking «which declared action of what is on screen» put it at
    0.94, 8/8. The widget falls out of the action, because what disambiguates two open cards is what
    each can DO, not the prose each was described with.

    A4 fixed the two things that measurement also exposed, at five open cards and 132 actions:

    · **The key is the INSTANCE, not the widget type.** Two `results` cards are two candidates, and
      keying by base meant a verdict could not name which one — «enséñame el tercero» came back as
      `youtube:play_result` at 0.70 (confident and wrong) with the third row sitting in `results`.
      `widgets/instances.card_face()` is how a card says what it currently SHOWS, and it is the only
      component that can: the label is the widget's own, never one we guessed for it.

    · **Only what is POSSIBLE NOW.** «reproduce» and «siguiente» chose `musica` over `youtube` with
      nothing to justify it — both declare `play` and `next`, and the question carried nothing but
      the list of what was open. An action that cannot run right now (a list action on a card with
      no rows) is not a candidate, and taking it out is what makes the remaining ones mean something.
      Fewer and more pertinent is also what brings the 15 KB down.

    Both refine DOWNWARDS only: anything unreadable keeps the candidate, so a widget that cannot
    answer about itself is never silently dropped from its own screen.
    """
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
    """What THIS card is showing, in the operator's terms — the RAIL that disambiguates two of a kind.

    «YouTube: paused · Música: playing» is what turns «siguiente» from a coin flip into an answer.
    Falls back to the id, which is what the question carried before A4: never worse, often better.
    """
    try:
        from widgets import instances as _inst
        label = str((_inst.card_face(widget_id) or {}).get("label") or "").strip()
        return f"{widget_id} — {label}"[:110] if label else widget_id
    except Exception:  # noqa: BLE001
        return widget_id


def _possible_now(widget_id: str, action: str) -> bool:
    """Can this action run on THIS card right now? Unknown always means YES.

    The only exclusion is structural and declared: an action that must name an EXISTING row, on a
    card that currently publishes none. That is «play the third one» on an empty list — not a
    capability the operator lacks, a target that does not exist. Anything this cannot read keeps the
    candidate, because a gate that guesses would hide a real capability (V2-085's invariant, one
    layer over).

    ⚠️ EXISTING is the load-bearing word, and getting it wrong costs a capability. The first version
    asked `contract.selector_for`, which answers «which payload key identifies this call» — and for
    `musica:create_playlist` that is `name`, the name of a playlist that does not exist yet. With an
    empty library every CREATION action vanished from the question, so «crea una lista Rock» had no
    candidate to be aimed at. `refs.id_field_for_action` is the narrower question — «which key names
    an item that ALREADY EXISTS» — and it is the one this filter needs. Caught by a test that picked
    the first declared action and found it gone.
    """
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
    """Which widget the order NAMES, enumerated with the words each one answers to.

    Measured (V2-726 §4-bis, against the 15 real manifests): criteria built from the widget's `desc`
    alone got 6 of 9; `«Name» + the same desc` got 8 of 9. The text a widget declares about itself IS
    the product surface of this decision — so this passes the identity ALIASES too (V2-082's table,
    which already exists and was never being handed to the chooser).

    ⚠️ It does not fix the operator's own failing example on its own, and saying so is the point:
    «ábreme el vídeo» answered `none` 0/8 at 0.52-0.61 — over the gate, confidently wrong, the worst
    mode there is — because NOTHING in the catalogue declares the word «vídeo» except the name
    «YouTube». That is repaired where it belongs, in the widget's own declaration, and this question
    is what makes the repair reach the decision.
    """
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
