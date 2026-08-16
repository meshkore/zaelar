"""The operator's 64s-silent-loss bug (session d4b2bc35, 2026-08-15) had two parts once `accumulator.offer()`
was fixed to report a drop on either branch: (a) the drop has to be surfaced — spoken, not just logged — and
(b) a hold that drags on needs SOME sign it's still "listening", not hung. `_acc_notice_plan` is the pure
decision behind both, factored out of `_run_inner` precisely so it is testable without an event loop or a live
voice session — see `voice/engine/llm/providers/nucleo.py::_acc_notice_plan`.
"""
from voice.engine.llm.providers.nucleo import _acc_notice_plan


def test_a_drop_that_resolves_into_hold_still_speaks():
    """The bug itself: the fragment causing the drop is usually incomplete on its own, landing on "hold" — that
    used to mean total silence about the discard."""
    speak, fresh = _acc_notice_plan("hold", "algo que se perdió", n_before=3)
    assert speak is True
    assert fresh is True, "a dropped chain starts fresh — the operator is now waiting on an unseen continuation"


def test_a_drop_that_resolves_into_act_also_speaks():
    speak, fresh = _acc_notice_plan("act", "algo que se perdió", n_before=3)
    assert speak is True
    assert fresh is False, "act already resolved this turn — no nudge to schedule"


def test_no_drop_no_notice():
    speak, fresh = _acc_notice_plan("hold", "", n_before=0)
    assert speak is False


def test_a_fresh_hold_with_nothing_dropped_still_starts_a_nudgeable_chain():
    """The first fragment of an ordinary chain (no drop involved) is exactly the case the nudge exists for: if
    THIS hold drags on past the nudge threshold, the operator gets a sign the system is still waiting."""
    speak, fresh = _acc_notice_plan("hold", "", n_before=0)
    assert fresh is True


def test_a_hold_continuing_an_existing_chain_is_not_fresh():
    """The 2nd/3rd fragment of a chain already in progress must NOT re-schedule a nudge — one per chain, timed
    from its first fragment, not restarted on every continuation."""
    speak, fresh = _acc_notice_plan("hold", "", n_before=2)
    assert fresh is False


def test_act_never_starts_a_fresh_chain():
    speak, fresh = _acc_notice_plan("act", "", n_before=0)
    assert fresh is False


def test_ask_never_starts_a_fresh_chain():
    """V2-102's new action: like "act", "ask" already RESOLVED this turn (a clarifying question was asked) —
    no pending chain to nudge later."""
    speak, fresh = _acc_notice_plan("ask", "", n_before=0)
    assert fresh is False


def test_a_drop_that_resolves_into_ask_also_speaks():
    speak, fresh = _acc_notice_plan("ask", "algo que se perdió", n_before=3)
    assert speak is True
    assert fresh is False
