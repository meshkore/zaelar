"""The bank is not a tautology: break a mechanism it relies on and its case goes RED (V2-776 A1).

Three disarms, each against a real rung of today's decision, each restored in `finally`:

1. the ACTION MAP off → the phrases a deterministic lane owns fall to the (recorded) model, and the cases
   that forbid a model consultation fail;
2. the action map AND the close grammar off → «Stop it and close the video widget» decides `show youtube`
   again, the exact v5 demo defect;
3. the recorded BRIEF ignored → «Vale, para el vídeo.» with the model calling nothing decides `talk`,
   which is the turn the operator had to repeat.

If any of these stays green, the harness is measuring itself and not the product.
"""
from __future__ import annotations

import os

import pytest

from tests.brain import harness

BY_ID = {c["id"]: c for c in harness.load_cases()}


def _run(case_id: str) -> tuple[dict, harness.Outcome]:
    case = BY_ID[case_id]
    return case, harness.run_case(case)


def test_a_map_phrase_goes_red_when_the_map_is_switched_off():
    case, before = _run("v2-567-cierra-los-mensajes")
    assert before.failures(case) == [], before.as_dict()
    os.environ["ZAELAR_ACTIONMAP"] = "0"
    try:
        _, disarmed = _run("v2-567-cierra-los-mensajes")
    finally:
        os.environ.pop("ZAELAR_ACTIONMAP", None)
    why = disarmed.failures(case)
    assert any("model was consulted" in w for w in why), (why, disarmed.as_dict())


def test_the_close_case_goes_red_only_when_both_of_its_defenders_are_disarmed(monkeypatch):
    """«Stop it and close the video widget» is defended twice on the voice turn (refactor2710-01: the bank runs on
    it): the stop's remainder reaches the ACTION MAP, which closes the card without the model; with the map off the
    recorded model's `show_widget youtube` meets the CLOSE GRAMMAR (`close_guards.looks_like_close`, read by
    the canvas door's `close_ordered`), which keeps the close. Disarming one leaves it green — the layering the compaction exists to
    remove; the first assertion pins it, so the day one defender is retired this proof says which is left."""
    from nucleo.flash import close_guards
    case, before = _run("demo-v7-stop-it-and-close-the-video")
    assert before.failures(case) == [], before.as_dict()
    monkeypatch.setenv("ZAELAR_ACTIONMAP", "0")
    _, one_down = _run("demo-v7-stop-it-and-close-the-video")
    assert one_down.failures(case) == [], "the close grammar no longer covers for the action map — update this proof"
    monkeypatch.setattr(close_guards, "looks_like_close", lambda text: False)   # the door reads it through the module
    _, both_down = _run("demo-v7-stop-it-and-close-the-video")
    why = both_down.failures(case)
    assert why, "both defenders gone and the case stayed green — the bank measured nothing"
    # Measured: with both down the turn decides `talk` — the model's show over an already-open card is
    # swallowed and NOTHING closes the video, which is the v5 defect's outcome (the card stays up).
    assert both_down.decision != "close youtube", both_down.as_dict()


def test_a_verdict_case_goes_red_when_the_brief_is_ignored(monkeypatch):
    case, before = _run("v2-755-vale-para-el-video-model-called-nothing")
    assert before.failures(case) == [], before.as_dict()
    monkeypatch.setattr(harness, "brief_handle", lambda case: None)
    _, disarmed = _run("v2-755-vale-para-el-video-model-called-nothing")
    why = disarmed.failures(case)
    assert any("decided 'talk'" in w for w in why), (why, disarmed.as_dict())


def test_the_case_files_are_valid_and_unique():
    cases = harness.load_cases()
    assert len({c["id"] for c in cases}) == len(cases)
    for c in cases:
        harness.validate(c)


@pytest.mark.parametrize("bad", [
    {"id": "x", "lang": "fr", "phrase": "p", "screen": {"open": []}, "expect": "talk", "source": "s"},
    {"id": "x", "lang": "en", "phrase": "p", "screen": {"open": []}, "expect": "open youtube", "source": "s"},
    {"id": "x", "lang": "en", "phrase": "p", "screen": {"focus": "a"}, "expect": "talk", "source": "s"},
    {"id": "x", "lang": "en", "phrase": "p", "screen": {"open": []}, "expect": "talk", "source": "s", "forbid": ["worker", "cards"]},
    {"id": "x", "lang": "en", "phrase": "p", "screen": {"open": []}, "expect": "talk"},
])
def test_a_malformed_case_is_refused(bad):
    """A case outside the grammar would be a case nobody can judge; it is refused at load, not at run."""
    with pytest.raises(ValueError):
        harness.validate(bad)
