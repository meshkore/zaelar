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

#: The declared marker for «this payload key may be left out». Both spellings, because the manifests
#: are product data and carry the operator's language as well as the engine's.
_OPTIONAL_MARKS = ("(opcional)", "(optional)")

#: Past this, the operator's sentence is an errand and not a query. See the module docstring: this is
#: a refusal, not a heuristic dressed up as one.
MAX_QUERY_WORDS = 14

#: How a manifest spells «this key takes ONE OF THESE», e.g. `"tab": "inicio | player | cola"` or
#: `"by": "'title' o 'added'"`. A key like that is a CHOICE, and a sentence is not one of its values.
#: Found while declaring `youtube:show_tab` (V2-742): its payload is an enumeration, and without this
#: the rung would have filled it with «vuelve al catálogo de vídeos» and the widget would have
#: refused an order the operator had given perfectly well.
_ENUM_MARKS = (" | ", "' o '", "' or '", '" o "', '" or "')


def _optional(desc) -> bool:
    d = str(desc or "").lower()
    return any(m in d for m in _OPTIONAL_MARKS)


def _base_of(widget_id: str) -> str:
    from nucleo.flash import turn_brief as _tb
    return _tb._base_of(widget_id)


def fillable_key(widget_id: str, action: str) -> str:
    """The ONE payload key that words may fill for this action, or "" when there is not exactly one.

    «Exactly one» is the whole rule and it is deliberately strict: two required keys mean the action
    needs a DATUM we do not have, and that is a question to ask (V2-712's ASK_FACT), not a call to
    make. Zero required keys is fine and returns "" too — the caller fires with an empty payload,
    which is what a no-argument action wants.
    """
    try:
        from nucleo.flash import frontend as _fe
        from widgets import refs as _refs
        base = _base_of(widget_id)
        spec = (_fe.declared_actions(base) or {}).get(action) or {}
        payload = spec.get("payload") if isinstance(spec, dict) else None
        if not isinstance(payload, dict):
            return ""
        required = [k for k, v in payload.items() if not _optional(v)]
        if len(required) != 1:
            return ""
        key = str(required[0])
        # A key that names an item ALREADY ON the card is a selector, not a query: filling it with a
        # sentence would ask the widget to play a row that does not exist.
        # …unless the widget publishes no row index and matches the reference ITSELF (a passage in a document):
        # there his words ARE the reference (refs.resolve's own rule — demo pass 2026-09-28, F2).
        if (_refs.id_field_for_action(base, action) or "") == key and _refs._exposes_ref_index(base):
            return ""
        # Nor is a sentence one of an enumeration's values (V2-742).
        if any(m in str(payload.get(key) or "") for m in _ENUM_MARKS):
            return ""
        return key
    except Exception:  # noqa: BLE001
        return ""


def from_brief(brief) -> tuple:
    """`(widget_id, action)` the turn's own verdict points at, or `("", "")`.

    Re-validated against what is still open, for the reason `turn_brief.owner_still_open` exists: the
    brief enumerates the screen at fire time and this is read 2-4 s later. A stale verdict is no
    verdict.
    """
    if not brief:
        # NOT an optimisation. `turn_brief.read` emits one `brain` read-attribution event per call
        # (V2-726 A6a) so the timeline can say whether a verdict was USED — and with no brief there
        # is no verdict to attribute. Asking anyway printed a `jev read screen_action → off` line on
        # every video turn of a channel that fires no brief at all, which is noise in the one place
        # that has to stay readable. Caught by the flow test that counts a turn's events by kind.
        return ("", "")
    try:
        from nucleo.flash import turn_brief as _tb
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
        owner, name = from_brief(brief)
        if not owner or not name:
            return False
        return not widget_id or _base_of(owner) == _base_of(widget_id)
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
        if from_brief(brief)[0]:
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
        if _k is None or kind in NOT_AIMED_AT_THE_SCREEN:
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


def names_an_order(brief, *, sure: float = 0.0) -> bool:
    """Does the turn's verdict name a declared action of an open card, on a turn it does not read as a remark?

    `sure` — a floor on the ACTION verdict's confidence for the callers that will WRITE on it (V2-773, demo v3
    C2): «Find me a free 45-minute slot» read `agenda:add_meeting` at 0.54, the reply was an ANSWER (the day's
    gaps), and the promise repair booked «Call with Ethan» — a write nobody ordered. An answer with an unsure
    action behind it is not a promise left hanging; a PROMISE in the reply is judged by its own detector.

    The gate for the promise repair (`act_repair`), in both channels (V2-770). That repair used to wait for a
    regex to find a PROMISE in the reply, and a reply that CLAIMS instead of promising slipped under it: measured
    live on the agenda, «el piano del martes pásalo al miércoles» → «Ya está: la del miércoles», «el martes 6
    no hay clase» → «Vale, quito la del 6», with no tool and a card that still had both. The verdict was already
    paid for and named the action; the wording of the reply is not the evidence, the verdict is."""
    try:
        from nucleo.flash import build_decision as _bd, turn_brief as _tb
        # V2-773 — either twin names the card: `screen_action` while it is open, the CATALOGUE while it is
        # closed. Read through `screen_action` alone, «Message Ethan on Telegram» (catalogue: messaging 1.0)
        # and «Show me only today's emails» promised or denied with no call and no repair ever looked.
        if not from_brief(brief)[1] and not _bd.named_card(brief):
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
        # An UNSURE request type is not a veto when the action itself is named surely (demo pass 2026-09-28, E3:
        # «draft a short reply…» → mensajeria:draft 0.74, request_type 0.48, the reply «I've got a draft ready»
        # and no call). Only a SURE reading that he was not giving an order stops the repair.
        return named_sure
    except Exception:  # noqa: BLE001
        return False


def resolve(commission: str, *, brief=None, swallowed=None, operator_text: str = "") -> dict:
    """The whole rung in one call. `{}` when there is none — every caller's fallback is today's path.

    `swallowed` is the arguments of a tool the model DID emit and a guard then ate. When it carries a
    payload we use it verbatim: the model had already read the turn and produced the right words, and
    the measured incident is precisely a guard throwing those words away. Only when there is no such
    call do we fall back to the operator's own sentence, under the bound above.

    Returns `{widget, action, payload, key, source, label}`.
    """
    wid, action = from_brief(brief)
    if not wid or not action:
        return {}
    key = fillable_key(wid, action)

    # 1 · the model's own arguments, which a guard swallowed. The best source there is: they were
    #     written by the model that had just read the whole turn.
    args = swallowed if isinstance(swallowed, dict) else {}
    if args:
        payload = {k: v for k, v in args.items() if str(v or "").strip()}
        if payload:
            return {"widget": wid, "action": action, "payload": payload, "key": key,
                    "source": "swallowed-tool",
                    "label": f"{wid}:{action} ← la tool que el guarda se comió"}

    # 2 · no tool at all. The words are the operator's, and only if they are short enough to BE the
    #     thing the payload key asks for.
    words = (operator_text or commission or "").strip()
    if not key:
        # V2-754 — two payload shapes the first version could not fill, and both were the incident:
        #   · an action with NO payload at all (`pause`, `close`, `next`) — nothing to invent, so it fires
        #     bare. An action whose keys are all OPTIONAL is not this case (`load` wants the model's own
        #     arguments, and «which of four to stuff» is the invention this module refuses);
        #   · ONE required key that is a declared CHOICE — filled only by an alias the operator SAID
        #     (`widgets.enums`), never by the sentence. «Vuelve al dashboard» names `inicio`.
        if no_payload(wid, action):
            return {"widget": wid, "action": action, "payload": {}, "key": "",
                    "source": "no-payload", "label": f"{wid}:{action} ← el veredicto de pantalla (sin payload)"}
        filled = enum_fill(wid, action, words)
        if filled:
            return {"widget": wid, "action": action, "payload": filled, "key": next(iter(filled)),
                    "source": "enum-alias", "label": f"{wid}:{action} ← el veredicto de pantalla (alias)"}
        return {}
    # V2-756 — an INDEX key is not a query. Before this, `play_result` got the whole sentence stuffed
    # into `item` («Ahora quiero que me pongas el vídeo número tres»), which the widget can only read as
    # a title and never match. A number he SAID is a reading, not an invention (see `number_fill`).
    if (n := number_fill(wid, action, words)):
        return {"widget": wid, "action": action, "payload": n, "key": next(iter(n)),
                "source": "said-number", "label": f"{wid}:{action} ← el veredicto de pantalla (nº dicho)"}
    if not words or len(words.split()) > MAX_QUERY_WORDS:
        return {}
    return {"widget": wid, "action": action, "payload": {key: words}, "key": key,
            "source": "operator-words",
            "label": f"{wid}:{action} ← el veredicto de pantalla"}


def _payload_spec(widget_id: str, action: str) -> dict:
    try:
        from nucleo.flash import frontend as _fe
        spec = (_fe.declared_actions(_base_of(widget_id)) or {}).get(action) or {}
        payload = spec.get("payload") if isinstance(spec, dict) else None
        return payload if isinstance(payload, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


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


def enum_fill(widget_id: str, action: str, words: str) -> dict:
    """`{key: value}` when the action's ONE required key is a declared choice and the operator's words
    name exactly one of its values or aliases; `{}` otherwise. See `widgets.enums`."""
    try:
        from widgets import enums as _enums
        payload = _payload_spec(widget_id, action)
        required = [k for k, v in payload.items() if not _optional(v)]
        if len(required) != 1:
            return {}
        key = str(required[0])
        value = _enums.resolve(str(payload.get(key) or ""), "", words)
        return {key: value} if value else {}
    except Exception:  # noqa: BLE001
        return {}


#: Request types that REFUSE to let the verdict complete an EMPTY turn. It used to be the mirror —
#: only a confident `order`/`answer` passed — and that let an UNSURE reader veto a near-certain one:
#: «Para el vídeo» came back `screen_action = youtube:pause` at 0.95 with `request_type` torn between
#: answer 0.49 and comment 0.39, so nothing happened and he said «He dicho que pares el vídeo. Que no
#: me has oído.» (live session 74be8e9a, 2026-09-23).
#:
#: Measured against the real API over that session's own candidates, and the numbers are why this is a
#: REFUSAL list and not an allow list — the screen question already answers `none` for everything not
#: aimed at the screen, so both guards agree where it matters and only this one was ever wrong:
#:
#:     «¿el siguiente es de la NASA?»   question 1.00  · screen_action none 0.95
#:     «ese vídeo es antiguo»           comment  0.82  · screen_action none 0.96
#:     «me gusta mucho este documental» comment  0.95  · screen_action none 0.99
#:     «hoy juega el Barça»             comment  1.00  · screen_action none 0.87
#:     «Bórrame los tres últimos…»      order    1.00  · screen_action remove 0.98
#:     «Para el vídeo»                  comment  0.45 ← unsure, and the turn IS an order
#:
#: `complaint` is deliberately NOT here: a complaint about what was just done IS an order to do it
#: properly (V2-750, node 2.70), and one with nothing to redo answers `none` on the screen question
#: anyway («Vale, hasta aquí bien, aunque te ha costado bastante» → none 0.92).
#:
#: V2-757 — AND NEITHER IS `question`, WHICH THIS LIST GOT WRONG THE SAME WAY. Live session f84f91ef
#: (2026-09-23, +95.2 s): «¿Puedes enseñarme el catálogo?» measured `screen_action = youtube:show_tab`
#: at **0.85** and `request_type = question` at 0.64, so this list refused it, the card never moved,
#: and the turn PROMISED it instead — «Voy a quitar el vídeo para que quede el catálogo a la vista» —
#: which he read out loud: «Bueno, dices que vas a hacer eso, pero no lo haces.»
#:
#: In Spanish a polite order IS shaped like a question, and that is not a rare form — it is how he
#: talks to it. Measured over the same 47 candidates of that session:
#:
#:     «¿Puedes, por favor, reproducir el vídeo número dos?»  question-shaped · play_result 0.56
#:     «¿Me pones el siguiente?»                              question-shaped · next        0.75
#:     «¿Puedes parar el vídeo?»                              question-shaped · pause       1.00
#:     «¿el siguiente es de la NASA?»                          a real question  · none        0.94
#:     «¿cuántos vídeos hay en la cola?»                       a real question  · none        0.78
#:     «¿de qué año es este documental?»                       a real question  · none        0.94
#:     «¿quién sale en el vídeo?»                              a real question  · none        0.91
#:     «¿tú crees que llegaron a la luna de verdad?»           a real question  · none        0.90
#:
#: Every genuine question answers `none`, so this entry could never SAVE a turn — and `complete` only
#: ever fires where the screen question is CONFIDENT about a concrete action, which is exactly the
#: case where it did damage. Same shape as the gate this list replaced: a weaker reader vetoing a
#: stronger one. What stays are the two that name a turn with no addressee at all.
NOT_AIMED_AT_THE_SCREEN = ("comment", "greeting")

#: A turn made of NOTHING BUT A NUMBER. A closed class — the tens, the units, the scales and the words
#: that glue them — not a verb table: nothing is ever added to Spanish's list of numerals, which is why
#: this one can be written down without becoming the thing CLAUDE.md forbids. Digits count too: the STT
#: writes «69» as often as «sesenta y nueve».
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
        from nucleo.flash import turn_brief as _tb
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


#: Spoken numbers reach us as words — Deepgram writes «el vídeo número tres» / «number five», never «3». The
#: words are the ONE closed class `widgets/refs.number_words()` keeps for every language pack we speak.
def _spell(m) -> str:
    import unicodedata as _ud
    from widgets import refs as _refs
    w = "".join(c for c in _ud.normalize("NFKD", m.group(0).lower()) if not _ud.combining(c))
    return str(_refs.number_words().get(w, m.group(0)))


def _word_numbers_re():
    import re as _re
    from widgets import refs as _refs
    return _re.compile("|".join(r"\b%s\b" % w for w in sorted(_refs.number_words(), key=len, reverse=True)),
                       _re.IGNORECASE)


_WORD_NUMBERS = _word_numbers_re()


def number_fill(widget_id: str, action: str, words: str) -> dict:
    """`{key: n}` when the action's ONE fillable key is a 1-based INDEX and he said exactly one number.

    The sibling of `enum_fill` and the same rule: a value he SAID is read, never invented (V2-741).
    «Ahora quiero que me pongas el vídeo número tres» over a band of six is a 3. Two different numbers,
    or none, is not a fill — it is a question to ask.
    """
    try:
        import re as _re
        key = fillable_key(widget_id, action)
        if not key:
            return {}
        spec = str(_payload_spec(widget_id, action).get(key) or "").lower()
        if not any(m in spec for m in ("1-based", "1-n", "número del resultado", "numero del resultado")):
            return {}
        nums = [int(_spell(m)) for m in _WORD_NUMBERS.finditer(words or "")]       # a SPOKEN number counts
        # …a DIGIT only when it is marked as one («number 3», «nº 3», «el 6», «#3») or is all he said: «Apolo 11»
        # is a title, not row eleven.
        nums += [int(x) for x in _re.findall(r"(?:\b(?:number|n[uú]mero|n[º°o]\.?|el|la|the)\s*|#)(\d{1,2})\b",
                                                words or "", _re.IGNORECASE)]
        if _re.fullmatch(r"\s*(\d{1,2})\s*[.!]?\s*", words or ""):
            nums.append(int(_re.sub(r"\D", "", words)))
        nums = [n for n in nums if 1 <= n <= 99]
        return {key: nums[0]} if len(set(nums)) == 1 else {}
    except Exception:  # noqa: BLE001
        return {}


def fill_missing(widget_id: str, action: str, payload: dict, words: str) -> dict:
    """What the MODEL's own call left out and his words can supply honestly, or `{}`.

    V2-756. «Pausa el vídeo. Vuelve al catálogo.» → the model called `widget_data(youtube, show_tab)`
    with an EMPTY payload and the widget answered `unknown_tab`: a correct order, the correct action,
    refused over one missing key whose value was sitting in his sentence («al catálogo» is `inicio`,
    declared right there in the manifest). He asked «¿Has ignorado la orden que te he dado?».

    Only ever ADDS a key the call left empty, and only from the two readings that are not inventions:
    a declared ALIAS of an enumerated value (V2-754) or a number he said. A call that already carries
    its key is untouched — this repairs an omission, it never edits a decision.
    """
    try:
        spec = _payload_spec(widget_id, action)
        required = [k for k, v in spec.items() if not _optional(v)]
        if len(required) != 1:                       # zero or several: nothing single to repair
            return {}
        if str((payload or {}).get(required[0]) or "").strip():
            return {}                                # the call carries its key — not this function's business
        return enum_fill(widget_id, action, words) or number_fill(widget_id, action, words)
    except Exception:  # noqa: BLE001
        return {}


def completes(brief, widget_id: str, *, model_action: str = "") -> str:
    """The verdict's action on THIS card when it is confident, still open and NOT what the model
    called; "" otherwise. The narrow question both arbitration sites ask (V2-754)."""
    wid, name = from_brief(brief)
    if not wid or not name or _base_of(wid) != _base_of(widget_id):
        return ""
    return "" if name == (model_action or "") else name


def sure_canvas(brief) -> str:
    """The canvas gesture this turn SURELY asks for — close, minimize, fullscreen, exit_fullscreen — or ""."""
    try:
        from nucleo.flash import turn_brief as _tb
        verb, _info = _tb.read(brief, _tb.CANVAS_KEY, "", min_confidence=0.9)
        v = str(verb or "")
        return v if v in ("close", "minimize", "fullscreen", "exit_fullscreen") else ""
    except Exception:  # noqa: BLE001
        return ""


def complete_canvas(brief, *, tag_emit, emit, operator_text: str = "") -> str:
    """The model called NOTHING and the brief SURELY names a canvas gesture: do that gesture on the card the
    turn is about (the verdict's card, else the card his last turn acted on, else the only one open), through
    the same tag funnel the model's own calls use. Returns the gesture, or "". Never raises.

    Demo pass 2026-09-28: R4 «ok close the calendar» and V3 «can you make it bigger, like full screen» were both
    answered as done («calendar's closed», «it's full screen now») with nothing called."""
    try:
        verb = sure_canvas(brief)
        if not verb:
            return ""
        from nucleo.flash import show_target as _st
        wid = _st.close_target(from_brief(brief)[0])
        if not wid:
            return ""
        if verb == "close":
            tag_emit("close", {"id": wid})
        elif verb == "minimize":
            tag_emit("minimize", {"id": wid})
        else:
            tag_emit("fullscreen", {"id": wid, "on": verb == "fullscreen"})
        emit("brain", f"🎯 el veredicto completa al modelo (sin tool) — {verb}", text=wid, role="system",
             extra={"cat": "flash", "widget": wid, "action": verb, "said": (operator_text or "")[:120]})
        return verb
    except Exception:  # noqa: BLE001
        return ""


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
             widget_id: str = "", instead_of: str = "", require_order: bool = True) -> str:
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
        from nucleo.flash import turn_brief as _tb
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
        # calendar», canvas=close 1.00 and screen_action=agenda:close_meeting 0.60 — the data action ran, the
        # card was shown again, and the reply said «calendar's closed»). The completion is the card's own close.
        if sure_canvas(brief):
            return ""                         # a canvas gesture is never a data action — `complete_canvas` owns it
        rung = resolve(operator_text, brief=brief, operator_text=operator_text)
    except Exception:  # noqa: BLE001
        return ""
    if not rung:
        return ""
    if rung.get("source") == "no-payload":           # a payload read from words belongs to the card it was read for
        rung = {**rung, "widget": subject_card(rung["widget"], rung["action"], operator_text)}
    try:
        present(rung["widget"], reason="turn-order", src="flash", emit=emit)
        apply_widget_data(rung["widget"], rung["action"], rung["payload"])
        emit("brain", "🎯 el veredicto completa al modelo" + (" (su llamada no resolvía)" if instead_of else " (sin tool)"),
             text=rung["label"][:120], role="system",
             extra={"cat": "flash", "widget": rung["widget"], "action": rung["action"],
                    "source": rung["source"], "instead_of": instead_of, "said": (operator_text or "")[:120]})
    except Exception:  # noqa: BLE001
        return ""
    return rung["action"]


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
    wid, name = from_brief(brief)
    if not wid:
        return False
    if _base_of(wid) != _base_of(widget_id):
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
        rung = resolve(str(escalate_req.get("v") or ""), brief=brief, operator_text=operator_text)
    except Exception:  # noqa: BLE001 — a classifier may never break a turn
        return False
    if not rung:
        return False
    try:
        present(rung["widget"], reason="turn-order", src="flash", emit=emit)
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
