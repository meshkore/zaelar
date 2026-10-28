"""Use-case rounds 2026-10-11 (z.ai out of quota, DeepSeek 402): with EVERY worker tier in cooldown the dispatcher
refuses to spawn, yet the turn that escalated came back mute and our own holding line said «Still on it; I'll let
you know as soon as I have it» / «Sigue en marcha» — about an errand refused before it was born. The judge filed it
[alta] in seven rounds. The wait lines (holding line, the mute backstop, the ack branch) now say the quota and the
hour instead, both channels, since both reach these three seams."""
import time
from types import SimpleNamespace as NS

import pytest

from i18n import langs
from nucleo.turn import wait_lines as rg
from nucleo.workers import providers, quota_wait

EN = langs.spec("en")
ES = langs.spec("es")


@pytest.fixture
def asleep(monkeypatch):
    until = time.time() + 3600
    monkeypatch.setattr(providers, "exhausted_until", lambda: until)
    monkeypatch.setattr(quota_wait, "_SAID", {"at": 0.0})
    return time.strftime("%H:%M", time.localtime(until))


def test_the_holding_line_says_the_quota_and_the_hour_not_still_on_it(asleep):
    line = rg.holding_line([], EN)
    assert "quota" in line and asleep in line
    assert "Still on it" not in line


def test_the_mute_backstop_with_work_pending_says_the_quota(asleep):
    line = rg.mute_backstop([], ES, True)
    assert "cuota" in line and asleep in line and "Sigue en marcha" not in line


def test_an_ack_over_an_asleep_chain_is_not_told_still_on_it(asleep):
    assert "quota" in rg.mute_backstop([], EN, True, operator_text="ok, sounds good")


def test_it_does_not_repeat_itself_word_for_word(asleep):
    first = rg.holding_line([], EN)
    second = rg.holding_line([{"role": "assistant", "content": first}], EN)
    assert second != first and asleep in second


def test_an_awake_chain_keeps_the_old_wait_lines(monkeypatch):
    monkeypatch.setattr(providers, "exhausted_until", lambda: 0.0)
    assert rg.holding_line([], EN) in EN.holding_lines
    assert rg.mute_backstop([], NS(filler_still_working="Still on it.", mute_lines=("x",)), True) == "Still on it."


def test_the_line_stamps_itself_so_the_dispatcher_does_not_say_it_twice(asleep):
    rg.holding_line([], EN)
    assert quota_wait.said_recently()
