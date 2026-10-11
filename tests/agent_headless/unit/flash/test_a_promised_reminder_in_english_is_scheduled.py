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

from nucleo import scheduler as S
from nucleo.flash import reminder_backing as B
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


def test_the_measured_run_leaves_exactly_one_job_carrying_the_fact():
    """Both turns through the voice half's one decision, against the real (isolated) scheduler."""
    for j in _live():
        S.cancel(str(j.get("name") or j.get("id") or ""))
    events = []
    emit = lambda *a, **k: events.append(a)            # noqa: E731
    w = list(WINDOW)
    for ask, reply in (PROMISE, CLAIM):
        w.append({"role": "user", "content": ask})
        assert B.back_and_check(reply, ask, window=w, emit=emit) == ""     # backed → no correction owed
        w.append({"role": "assistant", "content": reply})
    jobs = _live()
    assert len(jobs) == 1, jobs
    assert str(jobs[0]["schedule"]).startswith("2026-10-30"), jobs
    assert "Dexter" in str(jobs[0].get("prompt") or ""), jobs


@pytest.mark.parametrize("ask, reply", [PROMISE, CLAIM])
def test_each_english_form_alone_resolves_the_day(no_jobs, ask, reply):
    got = R.dated_reminder_backstop(reply, ask, window=WINDOW + [{"role": "user", "content": ask}])
    assert got and got["schedule"] == "2026-10-30 09:00", got
    assert "October 30" in got["prompt"], got


def test_a_promise_naming_no_day_rings_on_the_day_his_ask_named(no_jobs):
    """«ok 👍» → «I'll set that reminder.»: the day is the one «remind me on the 30th» named two turns back."""
    got = R.dated_reminder_backstop("On it — I'll set that reminder.", "ok 👍",
                                    window=WINDOW + [{"role": "user", "content": "ok 👍"}])
    assert got and got["schedule"] == "2026-10-30 09:00", got


def test_the_dentist_neighbour_rings_tomorrow_at_nine(no_jobs):
    ask = "remind me tomorrow at 9 to call the dentist"
    got = R.dated_reminder_backstop("Sure — I'll set a reminder for tomorrow at 9.", ask, window=[])
    assert got and got["schedule"] == "2026-10-11 09:00", got
    assert "dentist" in got["prompt"], got


def test_a_curly_apostrophe_and_a_polite_lead_still_promise(no_jobs):
    got = R.dated_reminder_backstop("Sure, no problem — I’ll set that reminder for October 30, 2026.", "ok",
                                    window=[])
    assert got and got["schedule"] == "2026-10-30 09:00", got


@pytest.mark.parametrize("reply", [
    "I can't set a reminder for October 30, sorry.",
    "I haven't set that reminder for October 30 yet.",
    "Your reminder isn't set for October 30.",
    "Shall I set that reminder for October 30, 2026?",
    "Want me to set that reminder for October 30, 2026?",
    "No te pongo ningún aviso para el 30 de octubre.",
    "No te pongo un aviso para el 30 de octubre.",
    "¿Te pongo un aviso para el 30 de octubre?",
])
def test_a_negation_or_a_question_promises_nothing(no_jobs, reply):
    assert P.find(reply) is None, reply
    assert R.dated_reminder_backstop(reply, "ok", window=[]) is None


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


def test_the_voice_half_says_the_correction_when_nothing_could_be_scheduled(no_jobs):
    """No date anywhere → nothing to back the claim with → the correction is returned for the voice to say."""
    events = []
    fix = B.back_and_check("Done — your reminder's all set!", "thanks", window=[],
                           emit=lambda *a, **k: events.append(a))
    assert fix and "reminder" in fix.lower()
    assert any("not scheduled" in str(e[1]) for e in events), events


def test_the_text_channel_appends_the_correction(no_jobs):
    from nucleo.flash import probe_after as PA
    sess = types.SimpleNamespace(window=[])
    out = asyncio.run(PA.the_words_it_owes(
        _hw=False, _parts=None, _show_chose=None, action="chat", images_req=None, return_extra_exec={},
        sess=sess, spoken="Done — your reminder's all set!", tags=[], text="thanks", video_req=None))
    assert out["spoken"].startswith("Done — your reminder's all set!")
    assert len(out["spoken"]) > len("Done — your reminder's all set!")
