"""A promised notice and the reply's language are checked by CODE, not left to the judge (V2-781 T514, 2026-10-03).

Measured on the pair `remember-and-remind-deadline`: the judge graded the ES round 5/5 with
`scheduled_jobs.created == []` — it accepted an all-day agenda line titled «Aviso: …» on Wednesday, which fires
nothing. The same day it graded 5/5 an EN round the agent answered in Spanish. Both properties are one line of
code each, so they are gates over the verdict: no job on the day the case names ⇒ the round FAILS whatever the
judge scored; a reply in the other language caps naturalness and is named.
"""
from __future__ import annotations

import copy
import json
import pathlib

from tests.use_cases.e2e.agent import gates
from tests.use_cases.e2e.agent import scenarios as SC

ROUND = json.loads((pathlib.Path(__file__).parent / "fixtures/t514_es_round_20261003-112255.json")
                   .read_text(encoding="utf-8"))


def _case(sid):
    return next(s for s in SC.all_scenarios() if s.id == sid)


def test_both_twins_name_the_day_their_notice_must_ring():
    for sid in ("remember-and-remind-deadline", "remember-and-remind-deadline__us"):
        assert _case(sid).notice_on == "wednesday", sid


def test_the_round_the_judge_passed_is_a_fail_on_the_same_evidence():
    run = {"transcript": ROUND["transcript"], "mechanism_report": ROUND["mechanism_report"]}
    v = gates.apply(_case("remember-and-remind-deadline"), run, copy.deepcopy(ROUND["verdict"]))
    assert ROUND["verdict"]["overall"] == 5
    assert v["overall"] <= 2 and v["scores"]["mecanismo"] <= 2 and v["scores"]["resultado"] <= 2
    assert any(f.get("gate") == "notice_on" for f in v["findings"])
    assert v["gates"]["notice_on"]["day"] == "2026-10-07"


def test_a_job_on_that_day_leaves_the_verdict_alone():
    mech = copy.deepcopy(ROUND["mechanism_report"])
    mech["scheduled_jobs"]["created"] = [{"name": "aviso", "schedule": "2026-10-07 09:00", "type": "once"}]
    v = gates.apply(_case("remember-and-remind-deadline"), {"transcript": ROUND["transcript"],
                                                           "mechanism_report": mech}, copy.deepcopy(ROUND["verdict"]))
    assert v["overall"] == 5 and not any(f.get("gate") for f in v["findings"])


def test_a_job_on_the_wrong_day_is_still_a_fail():
    mech = copy.deepcopy(ROUND["mechanism_report"])
    mech["scheduled_jobs"]["created"] = [{"name": "aviso", "schedule": "2026-10-08 07:00", "type": "once"}]
    v = gates.apply(_case("remember-and-remind-deadline"), {"transcript": ROUND["transcript"],
                                                           "mechanism_report": mech}, copy.deepcopy(ROUND["verdict"]))
    assert v["overall"] <= 2


def test_a_reply_in_the_other_language_is_flagged_without_the_judge():
    tx = [{"who": "tester", "text": "Make a note that on Thursday I have to renew the car insurance.", "at": 1791019232.6},
          {"who": "zaelar", "text": "Hecho: te queda apuntado el jueves para renovar el seguro del coche.", "at": 1791019250.0},
          {"who": "zaelar", "text": "Done.", "at": 1791019260.0}]
    verdict = {"scores": {"naturalidad": 5, "adaptacion": 5, "resultado": 5, "mecanismo": 5, "eficiencia": 5},
               "overall": 5, "findings": []}
    case = _case("dentist-appointment-into-agenda__us")
    v = gates.apply(case, {"transcript": tx, "mechanism_report": {}}, verdict)
    assert v["scores"]["naturalidad"] <= 2 and v["overall"] <= 3
    (f,) = [f for f in v["findings"] if f.get("gate") == "reply_language"]
    assert "zaelar@turn1" in f["turno"]


def test_the_right_language_and_short_lines_are_never_flagged():
    for line in ("I've put it in your agenda for Thursday with a reminder on Wednesday.", "OK!", "Netflix, Spotify."):
        assert gates.reply_language(line, "us") in ("", "en"), line
    assert gates.reply_language("Te lo apunto para el jueves y te aviso el miércoles.", "es") == "es"
    assert gates.reply_language("I'll add it to your agenda for Thursday.", "es") == "en"
