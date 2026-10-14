"""Node 2.691 — a finding pushed into his turn (a notice with a name and a price) reaches him even when the reply
forgets it: the notice's sentence is said after the reply, once.

search-buy-ski-gear__us (2026-10-14 10:37): «Best pick is a Nordica Nemesis 161 with Dynafit bindings in Oakland for
$150» rode into his turn; the reply answered his complaint and launched a NEW search, and the next said «it's on the
sheet» — the real candidates, every criterion met, were never named. A reply that already names the finding, or a
notice with no finding (a stall, a question), is left alone.

Disarm: `note_owed.owed` returning "" → the first test goes red.
"""
from __future__ import annotations

from nucleo.flash import note_owed as N

from ._claim_scene import SKI_NOTICE_TURN, SKI_SKIPPED

WINDOW = [{"role": "user", "content": SKI_NOTICE_TURN}]


def test_the_skipped_finding_is_said_after_the_reply():
    out = N.deliver(SKI_SKIPPED, WINDOW, "")
    assert out.startswith(SKI_SKIPPED)
    assert out.endswith("Best pick is a Nordica Nemesis 161 with Dynafit bindings in Oakland for $150.")


def test_a_reply_that_named_it_or_a_notice_without_a_finding_is_left_alone():
    named = SKI_SKIPPED + " Meanwhile the Nordica Nemesis with Dynafit bindings in Oakland, $150, is the best pick."
    assert N.deliver(named, WINDOW, "") == named
    stall = [{"role": "user", "content": "[SISTEMA] Aviso para el operador (zaelar): The search on Wallapop is slow, "
              "still on page two. Díselo con tus palabras DESPUÉS de contestar.\n\nok"}]
    assert N.deliver("Sure.", stall, "") == "Sure."
    assert N.deliver("Sure.", [{"role": "user", "content": "thanks"}], "") == "Sure."
