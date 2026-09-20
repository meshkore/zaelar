"""Node 3.65 — selection over parsed data, and the call's own hygiene (V2-726 F4+F5).

The operator's case: «si le mandamos a Jev los datos parseados de los 100 resultados y la lista de
criterios, nos puede decir cuáles son los que mejor encajan, en una sola request». Measured against
100 listings on 2026-09-20: one trip, 1161 ms, $0.0005, recall 3/3 with ZERO false positives once
the confidence gate is applied.

The trap this file mostly exists to nail: the candidate's identity must travel INSIDE its own
question. Ten identical questions over a shared `state` answered `strong` to all ten — including a
125cc Vespa in a search for motocross bikes — at 0.82-0.89 confidence. Confidently wrong is the
worst failure mode this module has, and it is invisible to a test that only checks the happy path.
"""
from __future__ import annotations

import pytest

from nucleo import jev

BIKES = [
    {"id": 1, "txt": "KTM SX 250 2021, 2-stroke, 3800 EUR, race ready"},
    {"id": 2, "txt": "Honda CRF 450 2019, 4-stroke, 5200 EUR"},
    {"id": 3, "txt": "Scooter Vespa 125, 1900 EUR, city bike"},
]
CRIT = "CRITERIA: motocross bike, 250cc 2-stroke, under 4000 EUR, race ready."


@pytest.fixture(autouse=True)
def _breaker():
    jev.reset_breaker()
    yield
    jev.reset_breaker()


@pytest.fixture
def wire(monkeypatch):
    monkeypatch.setattr(jev, "_read_key", lambda: "k-for-tests")
    monkeypatch.delenv("ZAELAR_JEV", raising=False)

    class _Wire:
        def __init__(self) -> None:
            self.calls: list[dict] = []
            self.by_question: dict[str, tuple[str, float]] = {}
            self.fail = False

        def __call__(self, state, questions, timeout_s):
            if self.fail:
                raise OSError("provider down")
            self.calls.append({"state": state, "questions": questions, "timeout_s": timeout_s})
            return {"answers": {k: (lambda c, f: {"choice": c, "confidence": f,
                                                  "probabilities": {c: f}})(
                *self.by_question.get(k, ("no", 0.9))) for k in questions}}

    w = _Wire()
    monkeypatch.setattr(jev, "_post_many", w)
    return w


# ── F4 · selection ───────────────────────────────────────────────────────────────────────────────
def test_a_hundred_candidates_are_one_trip(wire):
    """The whole point: N candidates cost what one costs, because the cost is the round trip."""
    many = [{"id": i, "txt": f"bike {i}"} for i in range(100)]
    jev.select_many(many, CRIT, key=lambda b: b["id"], label=lambda b: b["txt"])
    assert len(wire.calls) == 1
    assert len(wire.calls[0]["questions"]) == 100


def test_each_candidate_is_named_INSIDE_its_own_question(wire):
    """THE measured trap. With ten identical questions over a shared state, Jev answered `strong`
    to all ten — a 125cc Vespa included — at 0.82-0.89. The identity cannot live only in `state`."""
    jev.select_many(BIKES, CRIT, key=lambda b: b["id"], label=lambda b: b["txt"])
    qs = wire.calls[0]["questions"]
    assert len(qs) == 3
    for bike, q in zip(BIKES, qs.values()):
        assert bike["txt"] in q["instructions"], (
            "a candidate whose text is not in its own question makes every question identical, "
            "and identical questions get identical answers")
    assert len({q["instructions"] for q in qs.values()}) == 3, "the questions must differ"
    assert wire.calls[0]["state"] == CRIT, "the shared state is the CRITERIA, not the candidates"


def test_only_confident_strong_verdicts_come_back(wire):
    """`partial` is a shrug and an unsure `strong` is the false-positive band the measurement
    found: the three real hits sat at 0.64-0.94, the three false ones all under 0.33."""
    wire.by_question = {"cand_1": ("strong", 0.94), "cand_2": ("strong", 0.31),
                        "cand_3": ("partial", 0.99)}
    got = jev.select_many(BIKES, CRIT, key=lambda b: b["id"], label=lambda b: b["txt"])
    assert [r["key"] for r in got] == [1]


def test_the_best_fit_comes_first(wire):
    wire.by_question = {"cand_1": ("strong", 0.6), "cand_2": ("strong", 0.99),
                        "cand_3": ("strong", 0.8)}
    got = jev.select_many(BIKES, CRIT, key=lambda b: b["id"], label=lambda b: b["txt"])
    assert [r["key"] for r in got] == [2, 3, 1]


def test_nothing_fitting_is_an_empty_answer_not_a_guess(wire):
    wire.by_question = {f"cand_{i}": ("no", 0.99) for i in (1, 2, 3)}
    assert jev.select_many(BIKES, CRIT, key=lambda b: b["id"], label=lambda b: b["txt"]) == []


def test_a_failure_or_a_kill_switch_selects_nothing(wire, monkeypatch):
    wire.fail = True
    assert jev.select_many(BIKES, CRIT) == []
    wire.fail = False
    monkeypatch.setenv("ZAELAR_JEV", "0")
    assert jev.select_many(BIKES, CRIT) == []
    assert wire.calls == []


def test_too_many_candidates_are_refused_not_truncated(wire):
    """A caller with a thousand rows must page them, not silently score the first hundred."""
    with pytest.raises(jev.JevBriefTooBig):
        jev.select_many([{"txt": f"x{i}"} for i in range(jev.MAX_QUESTIONS + 1)], CRIT)


# ── F5 · the call's hygiene ──────────────────────────────────────────────────────────────────────
def test_the_timeout_stopped_cancelling_its_own_calls(monkeypatch):
    """900 ms against a measured p50 of 800 dropped 5% of canvas verdicts and 28% of the escalate
    gate's AFTER paying for them. Since F1 nobody blocks on the answer, so 2 s costs a thread."""
    monkeypatch.delenv("ZAELAR_JEV_TIMEOUT_MS", raising=False)
    assert jev._timeout_s() == 2.0
    monkeypatch.setenv("ZAELAR_JEV_TIMEOUT_MS", "500")
    assert jev._timeout_s() == 0.5


def test_an_outage_stops_being_paid_for_every_turn(wire):
    """Without a breaker, a provider down costs a thread and a full timeout on EVERY turn forever,
    for a verdict that was never going to arrive. An open breaker reads as a slow call."""
    wire.fail = True
    for _ in range(jev._BREAK_AFTER):
        jev.select_many(BIKES, CRIT)
    assert jev._breaker_open(), "three consecutive failures must open the breaker"
    assert jev.enabled() is False, "an open breaker asks for no thread and no socket"
    wire.fail = False
    wire.calls.clear()
    assert jev.select_many(BIKES, CRIT) == [], "while open, nothing is dialled"
    assert wire.calls == []
    jev.reset_breaker()
    jev.select_many(BIKES, CRIT)
    assert len(wire.calls) == 1, "a closed breaker dials again"


def test_one_success_closes_the_breaker(wire):
    wire.fail = True
    jev.select_many(BIKES, CRIT)
    jev.select_many(BIKES, CRIT)
    assert not jev._breaker_open(), "two failures are not an outage yet"
    wire.fail = False
    jev.select_many(BIKES, CRIT)
    for _ in range(jev._BREAK_AFTER - 1):
        wire.fail = True
        jev.select_many(BIKES, CRIT)
        wire.fail = False
    assert not jev._breaker_open(), "a success in between must reset the streak"


def test_the_key_file_is_read_once(monkeypatch, tmp_path):
    """`enabled()` runs on every Jev touch and `_post_*` reads the key again for the header — on a
    machine where the key lives in the file rather than the environment, that was two file reads
    per verdict, on the turn's thread."""
    jev._KEY_CACHE["env"], jev._KEY_CACHE["value"] = None, ""
    reads = []
    real = jev.Path.read_text

    def _counting(self, *a, **k):
        if self.name == "jev.md":
            reads.append(1)
        return real(self, *a, **k)

    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    monkeypatch.setattr(jev.Path, "read_text", _counting)
    first = jev._read_key()
    for _ in range(5):
        jev._read_key()
    if first:                        # only meaningful where a key file actually exists
        assert len(reads) == 1, f"the key file was read {len(reads)} times"
    monkeypatch.setenv("TYPESAFE_API_KEY", "from-env")
    assert jev._read_key() == "from-env", "an exported key still wins immediately"
