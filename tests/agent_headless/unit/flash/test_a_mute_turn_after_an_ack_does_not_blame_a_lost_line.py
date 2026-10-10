"""A mute turn after «sounds good 👍» with a build running is not «Sorry, I lost that» (V2-781).

Measured in `build-workout-tracker-widget__us` (2026-10-10): the widget build was live, the operator acknowledged
with «sounds good 👍», the model returned nothing, and the backstop — which demotes live work that is not about
THIS line — answered «Sorry, I lost that. Could you say it again?». An acknowledgement asks for nothing new, so
the live work IS what it is about.
"""
from types import SimpleNamespace

from nucleo.flash import reminder_guards as rg
from voice import endpointing


LANG = SimpleNamespace(filler_still_working="Still on it.", mute_lines=("Sorry, I lost that.",))


def test_the_english_acks_are_backchannels():
    for t in ("sounds good 👍", "cool", "great, thanks", "sure", "perfect", "alright"):
        assert endpointing.is_backchannel(t), t
    assert not endpointing.is_backchannel("open telegram")


def test_an_ack_over_live_work_says_still_working(monkeypatch):
    from nucleo import dispatch
    from nucleo.flash import router_guards
    monkeypatch.setattr(dispatch, "pending_summaries", lambda: [{"request": "build a workouts widget"}])
    monkeypatch.setattr(router_guards, "nothing_running_for", lambda *a, **k: True)
    assert rg.mute_backstop([], LANG, True, "sounds good 👍") == "Still on it."
    assert rg.mute_backstop([], LANG, True, "find me a free slot tomorrow") == "Sorry, I lost that."
