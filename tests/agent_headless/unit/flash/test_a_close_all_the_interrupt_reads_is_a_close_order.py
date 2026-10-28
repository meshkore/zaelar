# Demo pass in a sandbox, 2026-10-28 (INIT_CLEAN, flow T26·1ea0): «ok, clear everything off the screen» produced
#
#     ambient  ✋ interrupción dura atendida      cmd=close
#     arbiter  ⛔ vetada · close-drag             op=close src=flash
#     flow     end
#
# The engine READ the sentence as a close of the whole canvas (the hard interrupt, `voice/interrupt_grammar.py`,
# which knows «clear», «limpia», «despeja») and then VETOED its own order at the canvas door, because the close
# licence (`nucleo/acts/canvas.close_ordered`) read the same words with a narrower grammar (`close_guards`, which
# knows «close», «hide», «cierra», «quita»…) and found no close in them. Two readers of one act, disagreeing on the
# verbs they share — the class V2-678 named («the close-ALL door knows verbs this module does not») and left open.
#
# With a sure `canvas=close` verdict the door licenses the close one level earlier, which is why it looked fine on
# the operator's engine most days; with the brief silent (off, late, breaker open) every «clear the screen» — the
# wording the demo script uses twice, Z2 included — closes nothing, says nothing, and reads as obedience.
#
# THE CLASS, not the case: a close-all the engine orders deterministically IS a close order, so the one close
# licence consults the whole-canvas reader too. One door, both languages, any of the verbs either reader knows —
# the tables themselves do not grow (node 7.73).
from __future__ import annotations

import pytest

from nucleo.acts import canvas, canvas_arbiter as arb
from voice import attention


@pytest.mark.parametrize("said", [
    "ok, clear everything off the screen",      # the demo's own words (INIT_CLEAN and Z2)
    "clear everything, please",
    "despeja la pantalla",
    "limpia el escritorio",
    "quita todo de la pantalla",
])
def test_a_close_all_the_hard_interrupt_reads_is_a_close_order(said):
    """What the hard interrupt executes as a close of the whole canvas, the close licence orders too."""
    assert attention.hard_interrupt(said) == "close", "the deterministic close still fires — untouched"
    from nucleo.flash import close_guards
    assert close_guards.whole_canvas_close(said), "the close readers' module reads the whole-canvas close"
    ordered, source = canvas.close_ordered(said)
    assert ordered, f"the close licence must read the close the engine just ordered: {said!r}"
    assert source == "grammar"


@pytest.mark.parametrize("said", [
    "ok, clear everything off the screen",
    "despeja la pantalla",
])
def test_the_canvas_door_does_not_veto_the_engines_own_close_all(said):
    """The arbiter judged the hard close on its words and vetoed it (`close-drag`); it licenses it now."""
    v = arb.decide("close", "", "flash", text=said)
    assert v.allow and v.rule == "close-grammar", (v.rule, v.evidence)


@pytest.mark.parametrize("said", [
    "do not clear the screen",                  # a negation stays a negation in the wider reader too
    "no despejes la pantalla",
    "Johnny eres tonto",                        # V2-635: an insult closes nothing
    "clear my calendar for tomorrow",           # «clear» without the canvas is not a close-all
])
def test_what_neither_reader_orders_stays_vetoed(said):
    assert attention.hard_interrupt(said) != "close"
    assert canvas.close_ordered(said)[0] is False
    assert arb.decide("close", "youtube", "flash", text=said).rule == "close-drag"
