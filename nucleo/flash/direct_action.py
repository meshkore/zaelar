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
        if (_refs.id_field_for_action(base, action) or "") == key:
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


#: Spoken numbers reach us as words — Deepgram writes «el vídeo número tres», never «el vídeo 3».
_SPELLED = {"un": 1, "uno": 1, "una": 1, "primero": 1, "primera": 1, "dos": 2, "segundo": 2,
            "segunda": 2, "tres": 3, "tercero": 3, "tercera": 3, "cuatro": 4, "cuarto": 4,
            "cuarta": 4, "cinco": 5, "quinto": 5, "quinta": 5, "seis": 6, "sexto": 6, "sexta": 6,
            "siete": 7, "septimo": 7, "ocho": 8, "octavo": 8, "nueve": 9, "noveno": 9, "diez": 10}


def _spell(m) -> str:
    import unicodedata as _ud
    w = "".join(c for c in _ud.normalize("NFKD", m.group(0).lower()) if not _ud.combining(c))
    return str(_SPELLED.get(w, m.group(0)))


def _word_numbers_re():
    import re as _re
    return _re.compile("|".join(r"\b%s\b" % w for w in sorted(_SPELLED, key=len, reverse=True)),
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
        nums = [int(x) for x in _re.findall(r"\b(\d{1,2})\b", _WORD_NUMBERS.sub(_spell, words or ""))]
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
        rung = resolve(operator_text, brief=brief, operator_text=operator_text)
    except Exception:  # noqa: BLE001
        return ""
    if not rung:
        return ""
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
