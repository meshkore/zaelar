"""The turn's ONE Jev call — every enumerated question a turn needs, asked once (V2-726 F1/A2).

WHY ONE CALL. Measured 2026-09-20 over 312 real calls plus a live round against the API: Jev's cost
is the ROUND TRIP, not the questions. One question takes ~800 ms; four heterogeneous ones take
708-826 ms; a hundred take 1041 ms. The engine was making TWO trips per turn for two questions and
would have made a third for the route. Everything a turn asks therefore belongs in one brief.

WHY ONLY POST-MODEL QUESTIONS. The other half of the same measurement, over 87 real turns: the
prompt is assembled 3 ms after the turn is admitted and the tool catalog is settled at 381 ms, while
a Jev verdict lands at 785 ms. Nothing decided BEFORE the model can be served by a brief fired when
the turn starts without making the model wait for it. What is decided AFTER the model — the escalate
gate, an invented action, which open widget an order is aimed at — has 2-4 s of head start, because
TTFT alone is 1.9 s. So this module answers post-model questions and nothing else; a pre-model
question belongs on the interim transcript, which is a different (and unmeasured) design.

⚠️ THE ONE EXCEPTION, and it is the reason the filler's question lives here (A2): the cover phrase is
chosen ~1.1 s after the model starts, which is AFTER the brief lands, so it reads like any other
post-model consumer even though it sounds first. It used to open its own second socket from
`filler_audio.arm`. Same turn, same words, two trips — the exact shape this module exists to remove.

WHEN IT IS FIRED, which A2 corrected. At the ADMITTED sentence and not one line earlier: the fire
used to sit before echo suppression and before the accumulator, so the classifier judged a FRAGMENT
while the model was handed `text = _merged` — two different requests, one verdict. «Ponme música»
fired the brief; «de los 80» arrived 3 s later; the model answered about eighties music and the
brief had never heard of it. Overlap is not lost by moving: the prompt is assembled 3 ms after
admission and the readers are 2-4 s away.

THE CONTRACT, which is the initiative's rule 2 and is not relaxed here: every question is enumerated
per call from DECLARED capabilities — manifest actions of what is open, the escalate pair, the
request-type list — never free text and never a new rail on judgement. Nothing this module answers
executes anything: callers map a confident verdict onto a path that already exists and is already
gated.

NOBODY EVER WAITS. Readers `peek`; a brief still in flight, failed, disabled or unsure reads as the
caller's own fallback, which is today's path bit-for-bit. That matters more than it sounds: 56 of 87
real directed turns died to barge-in before they finished, so a brief that blocked would be paying
for turns that no longer exist.

AND A VERDICT IS RE-VALIDATED WHEN IT IS CONSUMED, not only when it is asked (A2). The brief
enumerates what was open at fire time; two seconds later a card may have closed. `stamp()` records
the turn and the open set, and `owner_still_open()` is what a reader calls before acting on a
verdict about a card. A stale verdict reads as no verdict.
"""
from __future__ import annotations

# ── the escalate gate (T-jev-escalate, now a brief question) ─────────────────────────────────────
ESCALATE_KEY = "escalate_or_inline"

# ── the canvas verb (T-jev-show-close, folded in here by V2-726 F1) ──────────────────────────────
# It used to be its own trip, fired beside this one. Measured over 159 real calls it changed ZERO
# outcomes — the model emits its own show/close tags (165 + 43) and the grammar vetoes the spare
# ones, so the licence is a backstop that two whole sessions never reached. Kept rather than
# retired, because inside a brief it is free (N questions cost one trip) and a backstop that costs
# nothing is worth having; what is retired is its SECOND ROUND TRIP.
CANVAS_KEY = "canvas"

# ── which open widget an order is aimed at (V2-726 F6 prepares this key) ─────────────────────────
TARGET_KEY = "screen_action"
TARGET_INSTRUCTIONS = (
    "The operator is looking at the screen and gives an order. Which declared action of the widgets "
    "ON SCREEN does it mean? Answer 'none' when the order is not aimed at anything on screen.")

# ── what kind of turn this is → which cover pool may sound (V2-726 A2, was the filler's own trip) ─
REQUEST_KEY = "request_type"


def escalate_question(*, running_goals: list | None = None, has_workers: bool = False,
                      ask_pending: bool = False) -> dict:
    """The escalate pair, worded exactly as `escalation_guard` worded it when it asked alone.

    The STATE FACTS it used to put in `context` move into the instructions, because a brief has one
    shared `state` (the operator's words) and per-question instructions — so a fact that belongs to
    ONE question has to travel with that question or it would colour the others.

    ⚠️ A2: `has_workers` and `ask_pending` were never passed. The question therefore said «Workers
    active now: no. A worker is waiting for the operator's answer: no» on EVERY turn, including the
    turns where one was — and «answer the worker» is precisely the shape that must not be escalated
    into a second worker. The facts are read by `ask_for_turn` now, from the same two functions the
    tool gate reads 1300 lines later in the provider.
    """
    from nucleo.flash import escalation_guard as _eg
    goals = [str(g)[:120] for g in (running_goals or []) if str(g or "").strip()][:3]
    facts = ("Goals already in flight: " + ("; ".join(goals) if goals else "none")
             + f". Workers active now: {'yes' if has_workers else 'no'}."
             + f" A worker is waiting for the operator's answer: {'yes' if ask_pending else 'no'}.")
    return {"instructions": f"{_eg.ESCALATE_INSTRUCTIONS} {facts}",
            "criteria": dict(_eg.ESCALATE_CHOICE)}


def request_question(last_reply: str = "") -> dict:
    """What kind of turn this is — the question `filler_audio.arm` used to ask on its own socket.

    The previous reply travels in THIS question's instructions rather than in the shared state, for
    the reason `escalate_question` gives: a brief has one state and N instruction blocks, so a fact
    belonging to one question must ride with it. It is load-bearing for exactly one verdict —
    `answer`, «the user answers a question WE just asked» — which is what keeps a curt «enduro» from
    being read as an order (V2-716).
    """
    from nucleo import jev as _jev
    instructions = _jev._RT_INSTRUCTIONS
    lr = (last_reply or "").strip()
    if lr:
        instructions += f" [Our previous reply: {lr[:200]}]"
    return {"instructions": instructions, "criteria": dict(_jev.REQUEST_TYPES)}


#: A canvas with more than eight open cards is not a turn. Kept as a name because A4 added a second
#: cap below it and the two are different decisions.
MAX_OPEN_CARDS = 8


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
    criteria: dict[str, str] = {}
    for wid in ids[:MAX_OPEN_CARDS]:
        face = _card_label(wid)
        for name, spec in (_fe.declared_actions(_base_of(wid)) or {}).items():
            if not _possible_now(wid, name):
                continue
            desc = str((spec if isinstance(spec, dict) else {}).get("desc") or name)[:90]
            criteria[f"{wid}:{name}"] = f"[{face}] {desc}"
    if not criteria:
        return None
    criteria["none"] = "the order is not aimed at anything on screen"
    return {"instructions": TARGET_INSTRUCTIONS, "criteria": criteria}


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


#: Which widget of the CATALOG an order names, when nothing is open to aim at. `screen_action`'s
#: twin: same question one step earlier, and the only one of the two that can answer «ábreme el
#: vídeo» with nothing on screen.
CATALOG_KEY = "catalog_widget"
CATALOG_INSTRUCTIONS = (
    "The operator asks for a card that is NOT on screen. Which widget of the catalogue does he "
    "mean, by the words he uses for it? Answer 'none' when no widget is being named.")

#: A catalogue question is worth one when the whole catalogue fits in it. Past this the answer is
#: retrieval, not a bigger enumeration (INI-027 §7: an index narrows, a model chooses).
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


def build(operator_text: str, *, open_ids=None, running_goals=None, has_workers: bool = False,
          ask_pending: bool = False, last_reply: str = "") -> dict:
    """The questions this turn will need after the model answers. Empty dict = nothing to ask."""
    if not (operator_text or "").strip():
        return {}
    from nucleo.flash import show_target as _st
    qs: dict[str, dict] = {
        CANVAS_KEY: {"instructions": _st.CANVAS_INSTRUCTIONS, "criteria": dict(_st.CANVAS_VERBS)},
        REQUEST_KEY: request_question(last_reply),
        ESCALATE_KEY: escalate_question(
            running_goals=running_goals, has_workers=has_workers, ask_pending=ask_pending)}
    target = target_question(open_ids)
    if target:
        qs[TARGET_KEY] = target
    else:
        # Nothing on screen to aim at, so the question one step earlier is the useful one. They are
        # never both asked: with cards open the ACTION is what disambiguates (0.94 vs 0.26 measured),
        # and asking both would put two answers about the same order in one brief.
        catalog = catalog_question()
        if catalog:
            qs[CATALOG_KEY] = catalog
    return qs


def _worker_state() -> tuple[bool, bool]:
    """(workers active, a worker is waiting for an answer) — the two facts the escalate pair needs.

    Read here rather than handed in, for the same reason `open_widgets` is: both are µs lookups on
    caches the turn has already warmed, and the provider is a god file the architecture ratchet
    already lists. Never raises — unknown state reads as «no», which is the escalating answer.
    """
    try:
        from nucleo import dispatch as _dispatch, worker_api as _wapi
        return bool(_dispatch.has_active()), bool(_wapi.has_pending_ask())
    except Exception:  # noqa: BLE001
        return False, False


def ask_for_turn(operator_text: str, *, running_goals=None, last_reply: str = "", turn_id=None):
    """Fire the brief for a live voice turn, reading the screen and worker state itself.

    The provider used to gather `open_widgets` and hand it over, which put the assembly inside a
    file the architecture ratchet already lists as a god file. Reading `memory.state()` is a µs
    dictionary lookup on a cache the turn has already warmed, so it belongs beside the questions it
    feeds, not beside the turn loop. Never raises: no state reads as nothing open.

    `operator_text` must be the ADMITTED sentence — after echo suppression and after the accumulator
    merged its fragments. See this module's docstring for what firing early cost.
    """
    try:
        from memory import api as _memapi
        open_ids = list((_memapi.state() or {}).get("open_widgets") or [])
    except Exception:  # noqa: BLE001
        open_ids = []
    has_workers, ask_pending = _worker_state()
    return ask(operator_text, open_ids=open_ids, running_goals=running_goals,
               has_workers=has_workers, ask_pending=ask_pending, last_reply=last_reply,
               turn_id=turn_id)


def ask(operator_text: str, *, turn_id=None, **kw):
    """Fire the turn's brief. Returns a handle for `read`, or None when there is nothing to ask
    (empty turn, Jev off, no key). Never raises: a brief that cannot be built is simply not asked."""
    try:
        from nucleo import jev as _jev
        if not _jev.enabled():
            return None
        questions = build(operator_text, **kw)
        if not questions:
            return None
        handle = _jev.ask_many(operator_text.strip(), questions, name="jev-turn-brief",
                               question_id="turn-brief")
        return stamp(handle, turn_id=turn_id, open_ids=kw.get("open_ids"))
    except Exception:  # noqa: BLE001 — a classifier may never break a turn
        return None


def stamp(handle, *, turn_id=None, open_ids=None):
    """Record WHICH turn this brief belongs to and WHAT was open when it was asked.

    Without it, same-turn attribution is temporal rather than a join — which is what the audit found
    when it tried to prove that two events in a session belonged to the same turn and could only say
    they happened close together. And a verdict about a card cannot be checked for staleness at all:
    the brief enumerates what is open at fire time, the reader acts 2-4 s later.
    """
    if isinstance(handle, dict):
        handle["turn_id"] = turn_id
        handle["open_ids"] = [str(w) for w in (open_ids or [])]
    return handle


def owner_still_open(handle, widget_id: str) -> bool:
    """Is the card a verdict names STILL on screen? A reader checks this before acting on it.

    `True` when the brief carried no open set (nothing to contradict) — the fail-soft direction is
    today's path, as everywhere in this module.
    """
    known = (handle or {}).get("open_ids") if isinstance(handle, dict) else None
    if not known:
        return True
    wid = (widget_id or "").strip().lower()
    if wid in {str(w).strip().lower() for w in known}:
        try:
            from memory import api as _memapi
            now = {str(w).strip().lower() for w in ((_memapi.state() or {}).get("open_widgets") or [])}
        except Exception:  # noqa: BLE001
            return True
        if not now:
            return True
        # An INSTANCE that closed while its base stayed open is still a stale verdict: the card the
        # operator was looking at is gone, and its sibling is a different card with different rows.
        return wid in now


def read(handle, key: str, fallback, *, min_confidence: float | None = None):
    """One verdict out of the brief, with the caller's own fallback. Never waits, never raises."""
    try:
        from nucleo import jev as _jev
        mc = _jev.MIN_CONFIDENCE if min_confidence is None else min_confidence
        return _jev.read(handle, key, fallback, min_confidence=mc)
    except Exception:  # noqa: BLE001
        return fallback, None
