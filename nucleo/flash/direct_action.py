"""nucleo/flash/direct_action.py — the rung between «answer it» and «spend five minutes on it».

THE DEFECT THIS EXISTS FOR (live session 092569ab, 2026-09-21). The operator asked for a catalogue
of Apollo 11 videos. The turn brief answered `screen_action = youtube:search` at 0.97 — the right
card and the right action, the cheap one, already paid for. The model then called the global
`play_video` tool with `query="Apollo 11 documentales"`, which was also right. A grammar license read
the sentence, found no verb from its table («preparar» and «podrías» are not in it), called the call
context-bleed and ATE it. With no tool fired the reply became a promise with nothing behind it, the
friction auditor noticed, and its repair was a generic `claude_code` worker. That worker took
**195 seconds to reach its first `youtube:search`** — the same action the brief had named before the
model even answered.

So the ladder had two rungs, «answer inline» and «a background worker», and the engine fell to the
expensive one having already named the cheap one out loud. This module is the missing middle.

WHAT IT DECIDES, AND WHAT IT REFUSES TO DECIDE. It answers one question — «is there a DECLARED
action that serves this commission, and can we fill its payload?» — and it answers it from two
sources that already exist, never from a table of ours:

  · WHICH action: the turn brief's `screen_action` verdict (`turn_brief.TARGET_KEY`), enumerated per
    call from the manifests of what is on screen and re-validated against what is STILL on screen.
    That is the same verdict `frontend.which_card` reads for the other half of the same question —
    V2-740 wired WHICH CARD, this wires WHICH ACTION, and neither invents an action the model did
    not mean.
  · WHICH payload: the action's own declared `payload` block. Exactly one key may be filled from
    words (the others must be declared «(opcional)»), and that key may not be a selector naming a
    row that already exists — `refs.id_field_for_action` is the narrower question and it is the one
    this needs, the same trap `turn_brief._possible_now` documents one layer over.

ITS LIMIT, WRITTEN DOWN RATHER THAN HIDDEN. When the model produced no tool at all, the words that
fill the payload are the operator's own sentence, and a sentence is not always a good query. So the
fill is BOUNDED: past `MAX_QUERY_WORDS` this module declines and the commission escalates exactly as
it does today. A long, rambling errand IS worker work; a short one that names a declared action is
not. The bound is the honest part — it is not a claim that a sentence is a query, it is a refusal to
pretend it is when it plainly is not.

AND IT NEVER ACTS. Like `frontend.card_decision`, it returns a decision and the channel spends it,
so voice and text cannot diverge (V2-252's parallel-implementation rule, applied rather than
maintained). Never raises: an unreadable manifest, a stale verdict or a brief still in flight all
read as «no rung», which is today's path bit for bit.
"""
from __future__ import annotations
from nucleo.flash.payload_fill import (  # noqa: E402,F401 — V2-778 F1: moved, imported back under their names
    _ENUM_MARKS, _OPTIONAL_MARKS, _WORD_NUMBERS, _base_of, _optional, _payload_spec, _spell, _word_numbers_re,
    enum_fill, fill_missing, fillable_key, number_fill, person_fill, choice_or_order_fill, named_row)


#: Past this, the operator's sentence is an errand and not a query. See the module docstring: this is
#: a refusal, not a heuristic dressed up as one.
MAX_QUERY_WORDS = 14


def from_brief(brief) -> tuple:
    """`(widget_id, action)` the turn's own verdict points at, or `("", "")`.

    Re-validated against what is still open, for the reason `turn_brief.owner_still_open` exists: the
    brief enumerates the screen at fire time and this is read 2-4 s later. A stale verdict is no
    verdict.
    """
    if not brief:
        # NOT an optimisation: `turn_brief.read` emits a read-attribution event per call (V2-726 A6a); with no
        # brief there is no verdict, and asking printed `jev read screen_action → off` noise on every video turn.
        return ("", "")
    try:
        from nucleo.turn import brief as _tb
        choice, _info = _tb.read(brief, _tb.TARGET_KEY, "")
        raw = str(choice or "").strip()
        if not raw or raw == "none":
            return ("", "")
        owner, sep, name = raw.rpartition(":")
        if not sep or not owner or not name:
            return ("", "")
        if not _tb.owner_still_open(brief, owner):
            return ("", "")
        return (owner, name)
    except Exception:  # noqa: BLE001
        return ("", "")


def names_an_order(brief, *, sure: float = 0.0) -> bool:
    """Does the turn's verdict name a declared action of an open card, on a turn it does not read as a remark?

    `sure` — a floor on the ACTION verdict's confidence for the callers that will WRITE on it (V2-773, demo v3
    C2): «Find me a free 45-minute slot» read `agenda:add_meeting` at 0.54, the reply was an ANSWER (the day's
    gaps), and the promise repair booked «Call with Rowan» — a write nobody ordered. An answer with an unsure
    action behind it is not a promise left hanging; a PROMISE in the reply is judged by its own detector.

    The gate for the promise repair (`act_repair`), in both channels (V2-770). That repair used to wait for a
    regex to find a PROMISE in the reply, and a reply that CLAIMS instead of promising slipped under it: measured
    live on the agenda, «el piano del martes pásalo al miércoles» → «Ya está: la del miércoles», «el martes 6
    no hay clase» → «Vale, quito la del 6», with no tool and a card that still had both. The verdict was already
    paid for and named the action; the wording of the reply is not the evidence, the verdict is."""
    try:
        from nucleo.flash import build_decision as _bd
        from nucleo.turn import brief as _tb
        # V2-773 — either twin names the card: `screen_action` while open, the CATALOGUE while closed («Message
        # Rowan on Telegram», «Show me only today's emails» were promised or denied with no call and no repair).
        if not from_brief(brief)[1] and not _bd.named_card(brief):
            return False
        # A SURE «tell me» over an UNSURE action is no order (`verdicts.tell_vetoes_unsure_action`): «did you actually skip it? what's
        # playing now» ran a second `youtube:next` and reported a false «no more videos» (2026-10-11).
        from nucleo.turn import verdicts as _verdicts
        if _verdicts.tell_vetoes_unsure_action(brief):
            return False
        named_sure = False
        if sure and from_brief(brief)[1]:
            _c, _i = _tb.read(brief, _tb.TARGET_KEY, "", min_confidence=sure)
            if _i is None or not _i.get("used"):
                return False
            named_sure = True
        kind, info = _tb.read(brief, _tb.REQUEST_KEY, "")
        if info is not None:
            return kind not in NOT_AIMED_AT_THE_SCREEN
        # An UNSURE request type is no veto over a surely named action (demo pass 2026-09-28, E3: mensajeria:draft
        # 0.74, request_type 0.48, «I've got a draft ready» and no call). Only a SURE non-order stops the repair.
        return named_sure
    except Exception:  # noqa: BLE001
        return False


def resolve(commission: str, *, brief=None, swallowed=None, operator_text: str = "", model_words: str = "") -> dict:
    """The whole rung in one call. `{}` when there is none — every caller's fallback is today's path.

    `swallowed` is the arguments of a tool the model DID emit and a guard then ate. When it carries a
    payload we use it verbatim: the model had already read the turn and produced the right words, and
    the measured incident is precisely a guard throwing those words away. Only when there is no such
    call do we fall back to the operator's own sentence, under the bound above.

    Returns `{widget, action, payload, key, source, label}`.
    """
    from nucleo.acts import named_target as _nt   # his answer to our own «which card?» (V2-781)
    p_card, p_action = _nt.parked_answer(operator_text or commission)
    if p_card:
        return {"widget": p_card, "action": p_action, "payload": {}, "key": "", "source": "parked-answer",
                "label": f"{p_card}:{p_action} ← la tarjeta que nombra al contestar «¿cuál?»"}
    wid, action = from_brief(brief)
    if not wid or not action:
        return {}
    from nucleo.flash import undecided as _und   # a turn that ASKED, or a shared control nobody settled (V2-781)
    if _und.stops_the_rung(brief, wid, action, operator_text=operator_text or commission, model_words=model_words):
        return {}
    # V2-776 L1 — a rung is the ENGINE's inference, so when the brief names an attestable END STATE the rung must
    # attest it (pass 60, B2: «set the first one as my background» resolved to `results:choose`, which attests
    # nothing of it). One site for both channels.
    try:
        from nucleo.circuit import spec as _spec
        if (_why := _spec.gate_completion(brief, wid, action)):
            from voice.observer import emit as _emit_ev
            _emit_ev("brain", "🎯 el veredicto NO completa: la acción no atestigua el estado final de la frase",
                     text=_why[:160], role="system",
                     extra={"cat": "flash", "widget": wid, "action": action, "why": _why})
            return {}
    except Exception:  # noqa: BLE001
        pass
    key = fillable_key(wid, action)

    # 1 · the model's own arguments, which a guard swallowed — the best source, written after reading the turn.
    args = swallowed if isinstance(swallowed, dict) else {}
    if args:
        payload = {k: v for k, v in args.items() if str(v or "").strip()}
        if payload:
            return {"widget": wid, "action": action, "payload": payload, "key": key,
                    "source": "swallowed-tool",
                    "label": f"{wid}:{action} ← la tool que el guarda se comió"}

    # 1b · no tool, but the MODEL NAMED the row in its own words (demo pass 80, S3: «the Samsung ViewFinity S7 …
    #      $189.99»). Read off the card it is about — see `payload_fill.row_named_fill`.
    if key and model_words:
        try:
            from nucleo.flash import payload_fill as _pf
            named = _pf.row_named_fill(wid, action, card_to_present(wid, operator_text), model_words)
        except Exception:  # noqa: BLE001
            named = {}
        if named:
            return {"widget": wid, "action": action, "payload": named, "key": key, "source": "model-named-row",
                    "label": f"{wid}:{action} ← la fila que el modelo nombró"}

    # 2 · no tool at all: the operator's words, only if short enough to BE what the payload key asks for.
    words = (operator_text or commission or "").strip()
    if not key:
        # V2-754 — two payload shapes the first version could not fill: an action with NO payload (`pause`, `close`)
        # fires bare (all-OPTIONAL keys are not this case: «which of four to stuff» is invention); ONE required
        # CHOICE key is filled only by an alias he SAID (`widgets.enums`). «Vuelve al dashboard» names `inicio`.
        if no_payload(wid, action):
            return {"widget": wid, "action": action, "payload": {}, "key": "",
                    "source": "no-payload", "label": f"{wid}:{action} ← el veredicto de pantalla (sin payload)"}
        filled, src = choice_or_order_fill(wid, action, words, model_words, brief)   # an alias he said, or «X before Y»
        if not filled and (filled := named_row(wid, action, words)):
            src = "named-row"
        if filled:
            return {"widget": wid, "action": action, "payload": filled, "key": next(iter(filled)),
                    "source": src, "label": f"{wid}:{action} ← el veredicto de pantalla ({src})"}
        return {}
    # V2-756 — an INDEX key is not a query: `play_result` got the whole sentence in `item` and never matched.
    # A number he SAID is a reading, not an invention (`number_fill`).
    if (n := number_fill(wid, action, words)):
        return {"widget": wid, "action": action, "payload": n, "key": next(iter(n)),
                "source": "said-number", "label": f"{wid}:{action} ← el veredicto de pantalla (nº dicho)"}
    if not words or len(words.split()) > MAX_QUERY_WORDS:
        return {}
    return {"widget": wid, "action": action, "payload": {key: words}, "key": key,
            "source": "operator-words",
            "label": f"{wid}:{action} ← el veredicto de pantalla"}


def no_payload(widget_id: str, action: str) -> bool:
    """Declared with NO payload keys at all — the only shape that may fire bare. Undeclared reads as no."""
    try:
        from nucleo.flash import frontend as _fe
        spec = (_fe.declared_actions(_base_of(widget_id)) or {}).get(action)
        if not isinstance(spec, dict):
            return False
        payload = spec.get("payload")
        return payload is None or (isinstance(payload, dict) and not payload)
    except Exception:  # noqa: BLE001
        return False


#: Request types that REFUSE to let the verdict complete an EMPTY turn. It used to be the mirror (only a
#: confident `order`/`answer` passed), so an UNSURE reader vetoed a near-certain one: «Para el vídeo» →
#: `youtube:pause` 0.95 with request_type split answer 0.49 / comment 0.39, nothing happened, and he said
#: «He dicho que pares el vídeo. Que no me has oído.» (live session 74be8e9a, 2026-09-23).
#: A REFUSAL list, not an allow list: measured on that session, the screen question already answers `none`
#: for everything not aimed at it («¿el siguiente es de la NASA?» none 0.95, «hoy juega el Barça» none 0.87);
#: «Bórrame los tres últimos…» → remove 0.98; «Para el vídeo» comment  0.45 ← unsure, and the turn IS an order.
#: `complaint` is NOT here: a complaint about what was just done IS an order to redo it (V2-750, node 2.70).
#: V2-757 — NEITHER IS `question` (session f84f91ef, 2026-09-23, +95.2 s): «¿Puedes enseñarme el catálogo?»
#: → show_tab 0.85, question 0.64, refused, and the turn only PROMISED it. A polite Spanish order IS shaped
#: like a question (47 candidates: «¿Me pones el siguiente?» next 0.75, «¿Puedes parar el vídeo?» pause       1.00;
#: every real question → none 0.78-0.94), so it could never save a turn. What stays: the two with no addressee.
NOT_AIMED_AT_THE_SCREEN = ("comment", "greeting")

#: A turn made of NOTHING BUT A NUMBER: a closed class (tens, units, scales, glue words), not a verb table —
#: numerals never grow, so it is not what CLAUDE.md forbids. Digits count too (the STT writes «69»).
_NUMERIC_ONLY = frozenset(
    "cero un uno una dos tres cuatro cinco seis siete ocho nueve diez once doce trece catorce quince "
    "dieciseis diecisiete dieciocho diecinueve veinte veintiuno veintidos veintitres veinticuatro "
    "veinticinco veintiseis veintisiete veintiocho veintinueve treinta cuarenta cincuenta sesenta "
    "setenta ochenta noventa cien ciento cientos doscientos trescientos cuatrocientos quinientos "
    "seiscientos setecientos ochocientos novecientos mil millon millones "
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen "
    "sixteen seventeen eighteen nineteen twenty thirty forty fifty sixty seventy eighty ninety "
    "hundred thousand million "
    "y e el la los las un una de del al o and the of a an".split())


def only_a_number(words: str) -> bool:
    """Is this turn nothing but a spoken number? «sesenta y nueve.» yes; «páusalo» no; "" no."""
    import re as _re
    import unicodedata as _ud
    n = "".join(c for c in _ud.normalize("NFKD", words or "") if not _ud.combining(c)).lower()
    toks = _re.findall(r"[a-z0-9]+", n)
    if not toks:
        return False
    if not any(t.isdigit() or t in _NUMERIC_ONLY for t in toks):
        return False
    return all(t.isdigit() or t in _NUMERIC_ONLY for t in toks)


def a_fragment_moves_nothing(operator_text: str, *, brief=None, last_reply: str = "") -> str:
    """Why this turn may not touch a card at all, or "" when it may.

    THE DEFECT (live session f84f91ef, 2026-09-23, +49.1 s). He said, in one breath:

        «Vale, páralo, y ahora búscame vídeos del alunizaje en el año … sesenta y nueve.»

    The acoustic layer closed the turn on «en el año» — which the lexical rule reads as a FINISHED
    sentence (measured: `segmenter.looks_incomplete` returns False for it, so layer 2 was never even
    consulted) — and handed «sesenta y nueve.» over as a turn of its own 0.7 s later. The model read
    three words with a number in them, called `youtube:set_volume {volume: 69}`, and the card answered
    «Dime un nivel entre 0 y 100.» He said: «Yo no he dicho nada de ningún volumen.» The engine's own
    auditor filed it the same minute: «[P1·routing] Fragmento de cola del mismo turno ejecutado como
    comando de widget».

    THREE CONDITIONS, AND ALL THREE ARE THE INCIDENT. Each one alone is a guard I would not ship:

      · `escalation_guard.is_a_fragment` — the SAME reader that already annuls a commission a turn this
        thin could not have made, exemption and all (a confirmation is short BY NATURE, because the
        directive was in OUR sentence). One rule, two consequences, not two rules.
      · the turn is ONLY A NUMBER (`only_a_number`). Without this the guard reaches «páusalo» and
        «páralo» — measured: `too_thin_to_commission` calls both fragments, because its
        `_ALSO_A_VERB` escape hatch matches «para» and the enclitic «páralo» is a different token. His
        commonest orders are exactly that shape, and putting them behind «Jev must be sure» is the
        regression V2-755 and V2-756 both spent themselves repairing.
      · the VERDICT ANSWERED AND NAMED NOTHING. A text guard may not contradict the screen verdict —
        that rule cost V2-741 and V2-748 — so an absent, failed or disabled brief stands this down
        entirely, the same fail-open V2-754 promised in the other direction. On the measured turn the
        verdict said `none` at **0.31** and the arbiter said `⛔ data-drag`: three readers, no dissent.

    Returns the reason (for the timeline), never raises.
    """
    words = (operator_text or "").strip()
    if not only_a_number(words):
        return ""
    try:
        from nucleo.turn import brief as _tb
        _choice, _info = _tb.read(brief, _tb.TARGET_KEY, "")
        if _info is None:
            return ""                     # nobody asked, or nobody answered: today's path
        wid, name = from_brief(brief)
        if wid and name:
            return ""                     # the verdict names an action on an open card: it decides
    except Exception:  # noqa: BLE001 — a guard may never break a turn
        return ""
    try:
        from nucleo.flash import escalation_guard as _eg
        if not _eg.is_a_fragment(words, brief=brief, last_reply=last_reply):
            return ""
    except Exception:  # noqa: BLE001
        return ""
    return "un número suelto, y el veredicto no nombra ninguna acción"


def subject_card(widget_id: str, action: str, operator_text: str) -> str:
    """The card the verdict's action lands on: the verdict's own, unless HIS words name no card and the card his
    last turn acted on declares the same action — then «it» is that one.

    Demo pass 2026-09-28, U3: «no, put like a prayer» played on the open music card, then «pause it a sec» read
    `youtube:pause` (1.00) — both cards declare `pause`, the video's description is the richer one, and the verdict
    cannot know which card the conversation is about. `canvas_focus` does. A card he NAMES («pause the video»)
    always wins. Never raises; returns `widget_id` whenever in doubt."""
    try:
        from widgets import runtime as _rt
        if _rt.identify_named(operator_text or ""):
            return widget_id
        from memory import api as _memapi
        from nucleo import canvas_focus as _cf
        from nucleo.flash import frontend as _fe
        focus = _cf.last_turn_card(list((_memapi.state() or {}).get("open_widgets") or []))
        if not focus or _base_of(focus) == _base_of(widget_id):
            return widget_id
        if action in (_fe.declared_actions(_base_of(focus)) or {}):
            return focus
    except Exception:  # noqa: BLE001
        pass
    return widget_id


def complete(brief, *, operator_text: str, emit, present, apply_widget_data,
             widget_id: str = "", instead_of: str = "", require_order: bool = True, model_words: str = "") -> str:
    """THE ARBITER'S ONE RULE, spent (V2-754): the verdict COMPLETES the model, it never overrules it.

    Live session 3afe34a8 (2026-09-23), four orders to get back to the video catalogue. The brief
    answered `screen_action = youtube:show_tab` at 0.96 and 0.88 — right both times — while the model
    called `play_item` on a row that does not exist (→ «¿a cuál te refieres?») and then called nothing
    at all (→ «te dejo otra vez el catálogo», over nothing). Two turns later the brief said `restart`
    at 0.99 — WRONG — while the model called `show_tab` correctly. Each reader was right exactly where
    the other was wrong, and nobody crossed them. This crosses them, in the only direction that is
    safe on that evidence:

      · a VALID, resolvable call from the model runs, whatever the verdict says (T4 would have
        restarted the video on a 0.99);
      · where the model left the turn EMPTY or its call could not resolve, the verdict's action on
        the still-open card fills the gap — with a payload it can fill honestly (`resolve`), through
        `apply_widget_data`, i.e. the same `action_mode_now` gate (FAST / CONFIRM / ESCALATE) every
        model call goes through. Nothing new executes; something declared stops going unrun.

    `require_order`: for the empty-turn site, a turn the brief reads CONFIDENTLY as not aimed at the
    screen is refused — see `NOT_AIMED_AT_THE_SCREEN`. The unresolved-call site skips the gate: the
    model had already decided this was an order on this card. Returns the action fired, or "".
    Never raises.
    """
    try:
        from nucleo.turn import brief as _tb
        if require_order:
            kind, _info = _tb.read(brief, _tb.REQUEST_KEY, "")
            if _info is None:
                return ""                       # no answer at all → fail closed, as V2-754 promised
            if kind in NOT_AIMED_AT_THE_SCREEN:
                return ""                       # a CONFIDENT remark moves nothing (see the constant)
        wid, name = from_brief(brief)
        if not wid or not name:
            return ""
        if widget_id and _base_of(wid) != _base_of(widget_id):
            return ""
        if instead_of and name == instead_of:
            return ""
        # A SURE «close the card» is about the card, never its data (demo pass 2026-09-28, R4: «ok close the
        # calendar» ran agenda:close_meeting 0.60 and the card stayed). The completion is the card's own close.
        if not __import__("nucleo.flash.verdict_card", fromlist=["x"]).canvas_yields(brief):   # V2-781
            return ""                         # a canvas gesture is never a data action — `complete_canvas` owns it
        rung = resolve(operator_text, brief=brief, operator_text=operator_text, model_words=model_words)
    except Exception:  # noqa: BLE001
        return ""
    if not rung:
        return ""
    if rung.get("source") == "no-payload":           # a payload read from words belongs to the card it was read for
        rung = {**rung, "widget": subject_card(rung["widget"], rung["action"], operator_text)}
    try:
        present(card_to_present(rung["widget"], operator_text), reason="turn-order", src="flash", emit=emit)
        apply_widget_data(rung["widget"], rung["action"], rung["payload"])
        emit("brain", "🎯 el veredicto completa al modelo" + (" (su llamada no resolvía)" if instead_of else " (sin tool)"),
             text=rung["label"][:120], role="system",
             extra={"cat": "flash", "widget": rung["widget"], "action": rung["action"],
                    "source": rung["source"], "instead_of": instead_of, "said": (operator_text or "")[:120]})
    except Exception:  # noqa: BLE001
        return ""
    return rung["action"]


def card_to_present(widget_id: str, operator_text: str = "") -> str:
    """The CARD a verdict's action brings up: the base id narrowed to its live instance.

    Demo passes 38/44/47 (2026-09-29, S2): the brief names `results:layout` — the piece, not the sheet — and the
    data-op landed on the sheet (`instances.data_target`) while the present opened a bare, empty `results` card
    beside it; «close the results» then closed the phantom and the sheet stayed. One door for both halves:
    `show_target.show_card` narrows and never asks; a base with no instance stays the base."""
    try:
        from nucleo.flash import show_target as _st
        return _st.show_card(str(widget_id or ""), operator_text or "") or str(widget_id or "")
    except Exception:  # noqa: BLE001
        return str(widget_id or "")

from nucleo.acts.canvas_verdict import (  # noqa: E402,F401
    sure_canvas, named_cards, _open_now, complete_canvas, catalogue_names, _says_the_name, closes_the_named_card,
    close_op_is_the_card, on_screen_now)
from nucleo.acts.card_verdict import (  # noqa: E402,F401
    verdict_card, order_is_inside, _action_sure, verdict_shows, aims_at_a_card, verdict_escalates,
    order_over_a_card_left_undone, reads_as_order, completes, endorses, take_rung, verdict_elsewhere,
    order_card_after_read)
