"""«I'll check in as soon as it's ready» promises a FOLLOW-UP, not a look (V2-781, build-workout-tracker-widget__us).

The widget build was running; the operator said «sounds good 👍»; the reply «Got it. I'll check in as soon as it's
ready.» was read as a promise to look at something nothing live was doing, and the retraction «Sorry — I haven't
actually looked at that yet, and nothing is running» was glued on — a contradiction over live work.
"""
from nucleo.flash import answer_guards as ag


def test_checking_in_or_back_is_not_a_look():
    for reply in ("Got it. I'll check in as soon as it's ready.", "I'll check back with you when it lands."):
        assert not ag.a_promise_left_hanging("sounds good 👍", reply, acted=False, anything_running=False), reply


def test_a_real_promise_to_check_is_still_caught():
    assert ag.a_promise_left_hanging("what's on telegram?", "Let me check your Telegram.", acted=False,
                                     anything_running=False)
    assert ag.a_promise_left_hanging("x", "I'll check the inbox now.", acted=False, anything_running=False)
