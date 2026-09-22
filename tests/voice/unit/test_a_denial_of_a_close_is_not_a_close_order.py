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

import threading

from nucleo.flash import canvas_license, router_guards, turn_brief


def _brief(canvas: str | None, conf: float = 0.95):
    ev = threading.Event()
    ev.set()
    result = {} if canvas is None else {
        turn_brief.CANVAS_KEY: {"choice": canvas, "confidence": conf, "probs": {}}}
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
        assert not canvas_license.close_license(text, brief=_brief("neither")), (
            f"the turn's own canvas verdict said this is not a close, and it closed his card anyway: {text!r}")


def test_a_real_close_order_still_closes():
    """The cheap direction is a card that stays open one turn too long; the expensive one is an engine
    that has gone deaf to «ciérralo». This is the half that must not move."""
    assert canvas_license.close_license("cierra el widget de vídeo", brief=_brief("close"))
    assert canvas_license.close_license("ciérralo todo", brief=_brief("close"))


def test_an_absent_or_unsure_verdict_leaves_todays_behaviour_untouched():
    """This one NEWLY FORBIDS, unlike `verdict_grants`, so its failure mode has to be the safe one: a
    brief that never lands, or lands unsure, can never make the engine ignore a close."""
    text = "cierra el widget de vídeo"
    assert canvas_license.close_license(text, brief=None), "no brief at all → today's path"
    assert canvas_license.close_license(text, brief=_brief(None)), "brief with no canvas key → today's path"
    assert canvas_license.close_license(text, brief=_brief("neither", conf=0.2)), (
        "an unsure verdict is a shrug, and a shrug may not forbid")


def test_a_show_verdict_does_not_forbid_either():
    """Only a clear `neither` refuses. `show` is a different disagreement and it is not this gate's to
    settle — narrowing to the one answer that means «this turn is not about closing» keeps it from
    becoming a second opinion about everything."""
    assert canvas_license.close_license("cierra la agenda y abre el vídeo", brief=_brief("show"))


def test_the_provider_backstop_reads_the_licence_and_not_the_table():
    """The seam. The backstop lives in the voice provider and used to call `looks_like_close` directly, so
    the repair above would have been invisible to the path that actually closed his card."""
    import pathlib
    src = pathlib.Path(__file__).resolve().parents[3] / "voice/engine/llm/providers/nucleo.py"
    body = src.read_text(encoding="utf-8")
    i = body.index('if (not acted.get("closed"))')
    guard = body[i:i + 400]
    assert "close_license" in guard and "brief=" in guard, (
        "the close backstop must go through the licence, with the turn's brief — otherwise the verdict is "
        "read in a module the closing path never calls")
    assert "_router.looks_like_close(text)" not in guard, (
        "…and not straight through the verb table, which is what closed his card three times")
