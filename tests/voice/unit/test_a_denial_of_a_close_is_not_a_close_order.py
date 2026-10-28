"""V2-752 — «no te he dicho que lo cerraras» is not an order to close it.

THE INCIDENT (live session fce3eff3, 2026-09-22). The close backstop in the voice provider fires on
`router_guards.looks_like_close`, a verb table. It closed his video card THREE times, and twice of
those on sentences where he was COMPLAINING about the first close:

    +255.1 s  «quita este vídeo y vamos otra vez al No me estás oyendo.»          → closed
              (garbled: the accumulator had glued two unrelated fragments — node 2.69)
    +284.4 s  «He dicho que vuelvas al inicio del widget de vídeo, Yo no te he
               dicho en ningún momento que CERRARAS el widget de vídeo.»          → closed AGAIN
    +288.2 s  «Yo no te he dicho en ningún momento que CERRARAS el widget de vídeo.» → AGAIN

The table matched «quita» and «cerraras» and never asked whether the sentence ORDERS a close or DENIES
one. On both of the last two the turn's own `canvas` verdict had already answered `neither` — asked,
paid for, and read by nobody. CLAUDE.md: «UNA TABLA DE VERBOS NO ES UN ENRUTADOR».

WHAT THIS DELIBERATELY DOES NOT DO: arm the canvas arbiter. It ran in shadow through that whole session
and would have been wrong in this very conversation — `⛔ vetaría · show-drag` at +132.3 s on the
YouTube card he had just asked for. Its own gate to enforcement is zero false vetoes over his real
sessions, and this session fails it. Its `close-grammar` rule also reads the same table, so it could
not have caught the backstop's error either.

Run: .venv/bin/pytest tests/voice/unit/test_a_denial_of_a_close_is_not_a_close_order.py
"""
from __future__ import annotations

from nucleo.acts import canvas as _door

import threading

from nucleo.flash import canvas_license, router_guards, turn_brief


def _brief(canvas: str | None, conf: float = 0.95, kind: str | None = "complaint"):
    """`request_type` rides with `canvas` as in every real brief. Since V2-812 T-05 the `neither` vetoes a grammar
    close only when the turn is also read as something other than an order — these denials read as complaints."""
    ev = threading.Event()
    ev.set()
    result = {} if canvas is None else {
        turn_brief.CANVAS_KEY: {"choice": canvas, "confidence": conf, "probs": {}}}
    if canvas is not None and kind:
        result[turn_brief.REQUEST_KEY] = {"choice": kind, "confidence": 0.9, "probs": {}}
    return {"event": ev, "turn_id": "t", "open_ids": (), "result": result}


DENIALS = [
    "Yo no te he dicho en ningún momento que cerraras el widget de vídeo.",
    "He dicho que vuelvas al inicio del widget de vídeo, Yo no te he dicho en ningún momento que "
    "cerraras el widget de vídeo.",
    "Solo te he dicho que pararas el vídeo en curso y que te fueras al inicio",
]


def test_the_verb_table_still_reads_these_as_close_orders():
    """The premise, measured rather than asserted. If the table ever stopped matching these, the rest of
    this file would be green for the wrong reason — the shape of a guard that goes quiet the day the thing
    it guards disappears."""
    matched = [t for t in DENIALS if router_guards.looks_like_close(t)]
    assert len(matched) >= 2, (
        f"the grammar is supposed to be wrong about these — that is the whole incident: {matched}")


def test_a_denial_of_a_close_does_not_license_one():
    """The verdict said `neither` on both of the measured turns. Now somebody reads it."""
    for text in DENIALS:
        assert not _door.close_ordered(text, brief=_brief("neither"))[0], (
            f"the turn's own canvas verdict said this is not a close, and it closed his card anyway: {text!r}")


def test_a_real_close_order_still_closes():
    """The cheap direction is a card that stays open one turn too long; the expensive one is an engine
    that has gone deaf to «ciérralo». This is the half that must not move."""
    assert _door.close_ordered("cierra el widget de vídeo", brief=_brief("close"))[0]
    assert _door.close_ordered("ciérralo todo", brief=_brief("close"))[0]


def test_an_absent_or_unsure_verdict_leaves_todays_behaviour_untouched():
    """This one NEWLY FORBIDS, unlike `verdict_grants`, so its failure mode has to be the safe one: a
    brief that never lands, or lands unsure, can never make the engine ignore a close."""
    text = "cierra el widget de vídeo"
    assert _door.close_ordered(text, brief=None)[0], "no brief at all → today's path"
    assert _door.close_ordered(text, brief=_brief(None))[0], "brief with no canvas key → today's path"
    assert _door.close_ordered(text, brief=_brief("neither", conf=0.2))[0], (
        "an unsure verdict is a shrug, and a shrug may not forbid")


def test_a_show_verdict_does_not_forbid_either():
    """Only a clear `neither` refuses. `show` is a different disagreement and it is not this gate's to
    settle — narrowing to the one answer that means «this turn is not about closing» keeps it from
    becoming a second opinion about everything."""
    assert _door.close_ordered("cierra la agenda y abre el vídeo", brief=_brief("show"))[0]


def _voice_turn(phrase: str, brief: dict | None):
    """His sentence through the voice turn itself (the bank harness: the real `run_turn`, a recorded model that only
    apologises, the recorded brief, every consequence door dry). What the close backstop did is read from the turn."""
    from tests.brain import harness as H
    case = {"id": "denial-of-a-close", "lang": "es", "phrase": phrase, "source": "node 2.71",
            "screen": {"open": ["youtube"]}, "model": {"say": "Perdona.", "tools": []}, "expect": "talk"}
    if brief:
        case["brief"] = brief
    try:
        out = H.run_case(case)
    finally:
        from nucleo import canvas_closes, canvas_focus, done_ops
        from nucleo.flash import bulk_close, canvas_license
        canvas_focus._reset()
        done_ops.reset()
        bulk_close.reset()
        canvas_closes._reset_for_tests()
        canvas_license._RECENT_CLOSES.clear()
    assert not out.error, out.error
    backstop = [e for e in out.events if str(e.get("label") or "").startswith("🙈 close por backstop")]
    return out, backstop


#: The verdicts of the measured turns: the screen question answered `neither`, the turn read as a complaint.
_DENIED = {"canvas": ["neither", 0.95], "request_type": ["complaint", 0.9]}


def test_the_voice_turns_close_backstop_does_not_close_on_a_denial():
    """The seam, driven: the backstop in the voice turn used to call `looks_like_close` directly, so the licence
    above would have been invisible to the path that actually closed his card. Another of his denials here."""
    out, backstop = _voice_turn(DENIALS[1], _DENIED)
    assert backstop == [] and not any(d.startswith("close") for d in out.all_decisions), (
        f"his card closed on a denial the turn's verdict had read as not a close: {out.all_decisions}")


def test_the_voice_turns_close_backstop_still_closes_without_a_verdict():
    """The half that must not move: with no brief at all, the same sentence takes today's path (the grammar)."""
    out, backstop = _voice_turn(DENIALS[0], None)
    assert backstop and "close youtube" in out.all_decisions, out.all_decisions


def test_the_disarm_a_licence_that_ignores_the_verdict_closes_on_the_denial(monkeypatch):
    """The licence's negation clause switched off (`_denies_close` never true): the backstop fires on the denial.
    If this stayed quiet, the test above would be green for a reason other than the licence."""
    monkeypatch.setattr(_door, "_denies_close", lambda brief: False)
    assert _door.close_ordered(DENIALS[1], brief=_brief("neither"))[0], "the mutation landed at the door"
    _out, backstop = _voice_turn(DENIALS[1], _DENIED)
    assert backstop, "with the verdict unread the backstop closes on his denial — the incident"
