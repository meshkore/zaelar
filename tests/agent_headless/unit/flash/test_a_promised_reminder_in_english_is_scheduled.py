"""A spoken promise of a dated reminder is ONE scheduled job in English too; a claimed one is checked (2026-10-10).

`find-a-future-release-and-remind-me__us` (round 2026-10-10 22:08): the lookup said «premieres on October 30»,
he asked «Can you remind me on the 30th then?», and zaelar answered «I'm on it — I'll set that reminder for
October 30, 2026.» then «I've still got that reminder set for 30 October 2026» — with `scheduled_jobs.created`
EMPTY. The ES path of the same suite scheduled through the prose backstop; the EN promise forms only allowed
«a|the» before «reminder», and a CLAIM was not read at all.
"""
from __future__ import annotations

import asyncio
import types

import pytest

from nucleo.pulse import scheduler as S
from nucleo.flash import reminder_guards as R
from nucleo.flash import reminder_promise as P

NOW = 1791662700.0          # 2026-10-10 22:05, the run's own clock

WINDOW = [
    {"role": "user", "content": "Hey, I really like the show Dexter and I think a new season comes out this fall. "
                                "Can you find out when it premieres and let me know?"},
    {"role": "assistant", "content": "Dexter: Resurrection season two premieres on October 30 on Paramount+. "
                                     "That's the new season coming this fall."},
    {"role": "user", "content": "Oh nice, thanks! Can you remind me on the 30th then? Premiere day works."},
    {"role": "assistant", "content": "Alright, give me a moment to look into that."},
]
PROMISE = ("ok 👍", "I'm on it — I'll set that reminder for October 30, 2026.")
CLAIM = ("Perfect, thanks! That’s all I needed.",
         "You're very welcome! I've still got that reminder set for 30 October 2026, your premiere day.")


@pytest.fixture(autouse=True)
def clock(monkeypatch):
    monkeypatch.setattr(S.time, "time", lambda: NOW)


@pytest.fixture
def no_jobs(monkeypatch):
    monkeypatch.setattr(S, "list_jobs", lambda active_only=True: [])


def _live():
    return [j for j in S.list_jobs(active_only=True)]


@pytest.mark.parametrize("reply, lang", [
    ("You're all set! I've got that reminder set for the 30th.", "en"),
    ("Your reminder is set.", "en"),
    ("Ya tienes el aviso puesto para ese día.", "es"),
    ("Te he puesto el aviso para el día del estreno.", "es"),
])
def test_a_claim_with_no_job_behind_it_owes_a_correction(no_jobs, reply, lang):
    line = P.unbacked_claim_line(reply, lang)
    assert line and line != reply
    assert ("reminder" in line) if lang == "en" else ("aviso" in line)


def test_a_claim_with_a_job_behind_it_owes_nothing(monkeypatch):
    monkeypatch.setattr(S, "list_jobs", lambda active_only=True: [{"name": "aviso", "schedule": "2026-10-30 09:00"}])
    assert P.unbacked_claim_line("I've still got that reminder set for 30 October 2026.", "en") == ""


@pytest.mark.parametrize("reply", ["I'll set that reminder for October 30.", "I haven't set a reminder.",
                                   "Should I set the reminder?", "The premiere is on October 30."])
def test_only_a_claim_is_checked(no_jobs, reply):
    assert P.unbacked_claim_line(reply, "en") == ""


