"""V2-753 — «Páralo, y vuelve al inicio»: the right call, eaten five times by a verb table.

MEASURED, live session 46dcfcb4 (2026-09-22, 22:0x). The operator had opened the video card, searched
for Boeing 747 videos and played the third result. Everything worked. Then:

    «Uf, me he equivocado. Páralo, y vuelve al inicio.»

The model answered with the CORRECT call. `youtube:close` is declared as «lo detiene de verdad y lo
quita del reproductor», which is both halves of that order. The V2-635 data-op guard read the
sentence, found no verb from `_CLOSE_VERB_RE` — «parar» is not a close verb and must never be one —
called it context-bleed and ATE it. Then again. And again. Five `🛡️ data-op close ignorada` in ninety
seconds, under a voice that kept saying «lo paro y vuelvo al inicio» over a video that never stopped:

    +3053.7  zaelar   «Vale… lo paro y vuelvo al inicio.»          ← no widget/action in the turn
    +3067.2  🗣       «Pero veo que es incapaz de pararlo.»
    +3070.7  🗣       «Y tampoco vuelves al inicio a ver el catálogo.»
    +3077.9  zaelar   «perdona, Paco. Lo corto y te dejo el catálogo a la vista.»  ← nothing again

He had reported the same failure in the previous session. THREE independent defects were stacked on
that one order, and each is pinned below.

## 1 · The question's own answer was decapitated at 90 characters

`turn_brief.target_question` cut every declared `desc` at 90 chars. `youtube:show_tab` declares:

    «CAMBIA de pantalla dentro del reproductor SIN tocar lo que está sonando. 'inicio' es el
     catálogo/dashboard donde están los resultados… es lo que responde a «vuelve al catálogo», «a la
     página de inicio», «enséñame otra vez la lista para cambiar»…»

V2-742 wrote that second sentence INTO the manifest so the decision could find the action. The cut
fell at «'inicio' es el ca». Measured against the real API over his own words:

    «vuelve al catálogo»                          90 chars → none 0.77   ·  200 → show_tab 0.96
    «y tampoco vuelves al inicio a ver el catálogo» 90 → show_tab 0.32   ·  200 → show_tab 0.83
    pause 1.00 · next 0.94 · search 0.99 · volume_up 1.00 — unmoved in both

A description is product data and the right place to repair a routing miss (V2-726 §4-bis) — but only
the part of it that ARRIVES can decide anything.

## 2 · «vuelve al inicio» is ambiguous, and the manifest did nothing to help

`restart` said «reinicia el vídeo desde el principio», so «Páralo, y vuelve al inicio» came back as
`youtube:restart` — a verdict that would have RESTARTED the video he had just asked to stop. With the
two descriptions sharpened (restart says it keeps playing; close says it PARA), the same sentence
comes back `youtube:close` at 0.93, and «ponlo otra vez desde el principio» stays `restart` at 0.99.

## 3 · A grammar decided a route, alone, and the fix already existed one branch over

The canvas [[close]] guard has consulted a second reader since V2-635 (`show_target.close_has_order`:
grammar first, a confident Jev second). The DATA-OP close guard never got the escape hatch — the same
rule installed on one of two branches, and the un-repaired one is the branch that fires on a real
player. And then it cascaded: the empty promise tripped the promise backstop, which FORCED a
`claude_code` worker that drove a headless browser for four minutes to stop a video, over a brief
that had answered `escalate_or_inline = handle_inline` at 1.00. He had to say «yo no te he pedido que
hagas nada… páralo inmediatamente».

Deterministic here on purpose — the live half is the numbers above. What this pins is the RULE and
its WIRING.

Run: .venv/bin/pytest tests/voice/unit/test_stopping_the_video_is_not_a_close_verb.py
"""
from __future__ import annotations

import json
import pathlib
import threading

import pytest

from nucleo.flash import close_guards as _cg
from nucleo.flash import direct_action as _da
from nucleo.flash import turn_brief as _tb

_ENGINE = pathlib.Path(__file__).resolve().parents[3]
_PROVIDER = _ENGINE / "voice" / "engine" / "llm" / "providers" / "nucleo.py"

#: His sentence, verbatim from the transcript. A paraphrase would be a test of a test.
HIS_WORDS = "Páralo, y vuelve al al inicio."


def _brief(answers: dict, *, open_ids=("youtube",)):
    """A brief handle in the REAL shape `jev.ask_many` returns — the same builder node 2.68 uses.

    Built rather than mocked: what is under test is `turn_brief.read`'s own path through it, and a
    double with a convenient shape would pass with the reader disconnected.
    """
    ev = threading.Event()
    ev.set()                    # `jev.peek` returns None on an unset event: an unset one tests nothing
    return {"event": ev, "turn_id": "t-1", "open_ids": list(open_ids),
            "result": {k: {"choice": c, "confidence": f} for k, (c, f) in answers.items()}}


@pytest.fixture
def on_screen(monkeypatch):
    """The card is still open when the verdict is read — `owner_still_open` asks the live state."""
    monkeypatch.setattr(_tb, "owner_still_open", lambda _b, _o: True)


# ── 1 · THE QUESTION CARRIES THE SENTENCE THAT MAKES AN ACTION ROUTABLE ───────────────────────────

def test_the_screen_question_does_not_behead_the_routing_sentence():
    """The measured defect: the clause that says «vuelve al catálogo» never reached the decision."""
    q = _tb.target_question(["youtube"])
    assert q, "the card is open — there is a screen question"
    show_tab = q["criteria"]["youtube:show_tab"]
    assert "catálogo" in show_tab, (
        "`show_tab` declares that it answers «vuelve al catálogo» and the cut threw that away — "
        "with it gone the phrase measured `none` at 0.77")


def test_the_cut_is_a_named_bound_and_not_a_number_in_the_middle_of_a_line():
    """A magic number in two channels that must agree is the R3 class (see `is_short_order`)."""
    assert _tb.MAX_DESC_CHARS >= 200
    body = (_ENGINE / "nucleo/flash/turn_brief.py").read_text(encoding="utf-8")
    assert "[:90]" not in body, "the bare 90 is what beheaded the answer"


def test_the_question_stays_bounded():
    """Not a licence to inline the manifests: a question is enumerated, and it has to stay readable
    and cheap. Measured at 47 candidates: 4.7 KB → 5.8 KB, no latency change."""
    q = _tb.target_question(["youtube"])
    assert len(json.dumps(q["criteria"], ensure_ascii=False)) < 12_000


# ── 2 · THE TWO DESCRIPTIONS THAT MADE «vuelve al inicio» MEAN THE WRONG THING ────────────────────

def test_close_declares_that_it_STOPS_and_restart_declares_that_it_does_not():
    """The repair lives in the widget's own declaration (V2-726 §4-bis), so it reaches every reader
    — the decision model, the prompt catalogue and the probe — instead of one of them."""
    acts = json.loads((_ENGINE / "widgets/youtube/manifest.json").read_text(encoding="utf-8"))["actions"]
    close, restart = acts["close"]["desc"].lower(), acts["restart"]["desc"].lower()
    # V2-755 — the anchor was the literal «PARA» and that literal is what swallowed «Vale, para el
    # vídeo»: `close` opened with «PARA el vídeo de verdad», `pause` was declared in four words, and
    # the bare verb belonged to nobody (`none` 0.65, live session 665e666a). The competitor now is
    # `pause`, so this pins the CLAIM instead: close says it stops for real AND leaves the card empty,
    # which is the half `pause` does not do. His compound order still measures `close` 0.89.
    assert "deja de sonar" in close and "sin vídeo" in close, "close has to SAY that it stops it for real"
    assert "párralo y vuelve al inicio" in close, "…and V2-753's own sentence stays declared"
    assert "sigue sonando" in restart or "sigue reproduci" in restart, (
        "restart has to say it KEEPS PLAYING — «reinicia el vídeo desde el principio» is what made "
        "«Páralo, y vuelve al inicio» come back as `restart`")
    # V2-754 — and it must NOT say «inicio» at all. The first repair wrote «vuelve al inicio DEL VÍDEO»
    # into it to split it from `show_tab`, and «vuelve al inicio del widget de vídeo» then came back as
    # `restart` at 0.99 (session 3afe34a8): the word he uses for the card's home screen cannot live in
    # the description of the action that rewinds the video.
    assert "inicio" not in restart, "«inicio» is the card's home screen in his mouth, not the video's second 0"


# ── 3 · THE GRAMMAR PROPOSES; THE PAID VERDICT DECIDES ────────────────────────────────────────────

def test_the_grammar_still_reads_his_sentence_as_no_close():
    """Left exactly as it was, proposing. «parar» is not a close verb and adding it would be the
    fourth verb table this month (V2-741, V2-748, V2-750)."""
    assert _cg.looks_like_close(HIS_WORDS) is False


def test_the_verdict_licenses_the_data_op_the_grammar_could_not_see(on_screen):
    brief = _brief({_tb.TARGET_KEY: ("youtube:close", 0.93)})
    assert _cg.dataop_close_licensed(HIS_WORDS, "youtube", brief=brief) is True


def test_a_close_verb_needs_no_verdict_at_all():
    """Today's path, bit for bit: grammar hit ends the question and costs nothing."""
    assert _cg.dataop_close_licensed("cierra el vídeo", "youtube", brief=None) is True


@pytest.mark.parametrize("brief_answers,why", [
    ({}, "no verdict at all — V2-635's "),
    ({_tb.TARGET_KEY: ("youtube:pause", 0.99)}, "another action of the SAME card: «pausa el vídeo» "
                                                "must stay a pause, not become an emptied player"),
    ({_tb.TARGET_KEY: ("musica:close", 0.99)}, "another card entirely"),
    ({_tb.TARGET_KEY: ("youtube:close", 0.31)}, "a verdict under the gate is a shrug"),
])
def test_without_a_verdict_for_THIS_action_nothing_is_licensed(on_screen, brief_answers, why):
    """It only ever GRANTS, and only on an exact match. The guard exists because a `close` data-op
    EMPTIES the player — «Johnny eres tonto» dragged one in (V2-635) and that must stay blocked."""
    brief = _brief(brief_answers) if brief_answers else None
    assert _cg.dataop_close_licensed("Johnny eres tonto", "youtube", brief=brief) is False, why


def test_his_own_NO_beats_a_confident_verdict(on_screen):
    """The same veto `close_has_order` applies: a cheap model's opinion never overrules the
    operator's «no», and a NARRATED close is not an order either."""
    brief = _brief({_tb.TARGET_KEY: ("youtube:close", 0.99)})
    assert _cg.dataop_close_licensed("no lo cierres", "youtube", brief=brief) is False
    assert _cg.dataop_close_licensed("has cerrado el vídeo", "youtube", brief=brief) is False


def test_the_decision_is_attributable(on_screen):
    """Both outcomes leave a line saying WHICH reader moved — a guard that fires silently is how this
    one spent five turns being blamed on the model (V2-726 A6a)."""
    seen: list[tuple] = []

    def emit(kind, label, **kw):
        seen.append((label, (kw.get("extra") or {}).get("kind_diag")))

    _cg.dataop_close_licensed(HIS_WORDS, "youtube",
                              brief=_brief({_tb.TARGET_KEY: ("youtube:close", 0.93)}), emit=emit)
    _cg.dataop_close_licensed("Johnny eres tonto", "youtube", brief=None, emit=emit)
    assert [d for _l, d in seen] == ["close_jev_licensed", "close_without_order"]


# ── 4 · THE SEAM — a verdict nobody reads is what V2-750 already paid for ─────────────────────────

def test_the_data_op_guard_actually_asks_the_licence():
    body = _PROVIDER.read_text(encoding="utf-8")
    i = body.index('if action_name == "close"')
    assert "dataop_close_licensed" in body[i:i + 200], (
        "the guard must consult the shared reader, not `looks_like_close` alone")


def test_the_pure_show_gate_asks_the_verdict_too():
    """The OTHER gate that ate a close in the same session (`gate_shadow · pure-show`, +3073.7), on
    «…y tampoco vuelves al inicio a ver el catálogo» — a sentence with «ver» in it."""
    body = _PROVIDER.read_text(encoding="utf-8")
    i = body.index("show_request_blocks_data_action(text, wid, action_name, payload)")
    assert "_direct_action.endorses" in body[i:i + 220]


def test_endorses_is_an_exact_match_on_card_and_action(on_screen):
    """The predicate both gates lean on. Narrow on purpose: it only ever GRANTS."""
    brief = _brief({_tb.TARGET_KEY: ("youtube:close", 0.93)})
    assert _da.endorses(brief, "youtube", "close") is True
    assert _da.endorses(brief, "youtube", "pause") is False
    assert _da.endorses(brief, "musica", "close") is False


# ── 5 · AND A PROMISE WE EMPTIED OURSELVES IS NOT AN ERRAND ───────────────────────────────────────

#: His words at +3088.6, verbatim — the turn that actually bought the four-minute worker. They have
#: to be his: `looks_like_web_task` is the trigger above this gate, and a paraphrase of a complaint
#: does not fire it, so a prettier sentence here would make every case below pass for the wrong
#: reason (all three «keeps today's path» cases went green on one, which is how this was caught).
HIS_COMPLAINT = ("No, no lo estás haciendo, ¿por qué? Decir, es que no tienes un arnés "
                 "que te obliga a comprobar")


def _backstop(brief, *, op_text=HIS_COMPLAINT):
    """Fire the real backstop over a promise with nothing behind it; report what it spent."""
    from voice.engine.llm.providers import promise_backstop as _pb
    spent: list[str] = []
    _pb.run("Perdona, Paco. Te lo hago ahora mismo de verdad: cierro el vídeo.",
            did_act=False, op_text=op_text, prev_pending=[],
            emit=lambda *a, **k: None,
            escalate=lambda t, **kw: spent.append(t),
            similar_pending=lambda *a: False, brief=brief)
    return spent


def test_a_confident_handle_inline_annuls_the_forced_escalation(on_screen):
    """Four minutes of a headless browser, on a turn the brief had already called chatter."""
    assert _backstop(_brief({_tb.ESCALATE_KEY: ("handle_inline", 1.0)})) == []


@pytest.mark.parametrize("answers,why", [
    (None, "no brief — a channel that fires none keeps today's path"),
    ({_tb.ESCALATE_KEY: ("handle_inline", 0.3)}, "an unsure verdict is not a verdict"),
    ({_tb.ESCALATE_KEY: ("escalate", 0.99)}, "and a real errand still escalates"),
])
def test_everything_that_is_not_a_confident_inline_keeps_todays_path(on_screen, answers, why):
    assert _backstop(_brief(answers) if answers else None), why
