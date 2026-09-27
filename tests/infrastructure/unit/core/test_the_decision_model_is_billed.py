"""The decision model (Jev) reports its round trip to Energy (V2-767).

Jev is a PAID external provider — `https://api.typesafe.ai/v1/systemone`, ~$0.0005 per trip — and it
runs on essentially every voice turn (one trip for the turn brief, plus a second on ~36% of turns for
continuation). Until 2026-09-25 it reported nothing: `git grep energy nucleo/jev.py` came back empty.
It was not an exemption anybody had argued for, it was an absence nobody had noticed, and it was
invisible to `test_energy_coverage.py` for the plain reason that `api.typesafe.ai` was not in that
gate's list of signals.

What this pins: the trip is billed ONCE per round trip regardless of how many questions it carries
(that is how Jev bills and why callers batch), and only after the provider actually answered.
"""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from nucleo import jev


class _Resp:
    """Minimal stand-in for what `urllib.request.urlopen` yields as a context manager."""

    def __init__(self, payload: dict):
        self._raw = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return self._raw


_ANSWER = {"answers": {"request_type": {"choice": "question", "confidence": 0.9, "probabilities": {}}}}


@pytest.fixture
def metered():
    calls = []
    with patch("nucleo.energy_meter.report_decision_usage",
               side_effect=lambda **kw: calls.append(kw)):
        yield calls


def test_one_question_bills_one_trip(metered):
    with patch("nucleo.jev._read_key", return_value="k"), \
         patch("urllib.request.urlopen", return_value=_Resp(_ANSWER)):
        jev._post_question("request_type", "hola", "inst", {"question": "d"}, 1.0)
    assert len(metered) == 1
    assert metered[0]["provider"] == "typesafe"


def test_twenty_questions_in_one_trip_still_bill_ONE_trip(metered):
    """The price is the trip. Billing per question would punish exactly the batching that makes Jev
    cheap (1 question 800 ms, 100 questions 1041 ms) and would push callers back to N trips."""
    questions = {f"q{i}": {"instructions": "i", "criteria": {"a": "x", "b": "y"}} for i in range(20)}
    with patch("nucleo.jev._read_key", return_value="k"), \
         patch("urllib.request.urlopen", return_value=_Resp({"answers": {}})):
        jev._post_many("hola", questions, 1.0)
    assert len(metered) == 1
    assert metered[0]["questions"] == 20


def test_a_trip_that_never_answered_is_not_billed(metered):
    """A provider that timed out did not serve anything. Reporting before the answer would bill the
    customer for our own failed calls — and Jev fails open by design (circuit breaker, 3 strikes)."""
    with patch("nucleo.jev._read_key", return_value="k"), \
         patch("urllib.request.urlopen", side_effect=TimeoutError("no answer")):
        with pytest.raises(TimeoutError):
            jev._post_question("request_type", "hola", "inst", {"question": "d"}, 1.0)
    assert metered == []


def test_metering_can_never_break_a_verdict():
    """If the meter itself explodes, the turn still gets its answer. A billing bug must not be able
    to take down the piece that decides what the operator asked for."""
    with patch("nucleo.jev._read_key", return_value="k"), \
         patch("urllib.request.urlopen", return_value=_Resp(_ANSWER)), \
         patch("nucleo.energy_meter.report_decision_usage", side_effect=RuntimeError("boom")):
        payload = jev._post_question("request_type", "hola", "inst", {"question": "d"}, 1.0)
    assert payload == _ANSWER
