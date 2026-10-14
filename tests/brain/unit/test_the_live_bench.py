"""The live bench (2026-10-15): the bank's cases on the REAL fast model and Jev, N times each.

The operator: «si siete veces se pide un dato, esas siete veces me venga». The recorded bank cannot measure that —
it fixes the model's words — so `run_case(live=True)` keeps the isolation and lets the model and the brief be
real. Two promises are tested here without calling any model: a case can seed the CONTENT of a card (a list of
videos, an inbox), and going live leaves nothing behind — the provider keys it read into the process and the
model routing it pointed at its own copy are put back on exit.

Disarm: drop the env restore in `Isolated.__exit__` → the key leaks; skip the `widgets` seeding → the card is empty.
"""
from __future__ import annotations

import os

from tests.brain import harness as H


def test_a_case_seeds_what_a_card_holds():
    case = {"id": "x", "lang": "en", "phrase": "p", "source": "s", "screen": {"open": ["youtube"]}, "expect": "talk",
            "widgets": {"youtube": {"results": [{"n": 1, "title": "Starship flight 5"}]}}}
    H.validate(case)
    with H.Isolated("en") as iso:
        iso.seed(case)
        from widgets import store
        assert store.load("youtube")["results"][0]["title"] == "Starship flight 5"


def test_going_live_puts_the_keys_and_the_routing_back(tmp_path, monkeypatch):
    from config import credentials, v2
    fake_root = tmp_path / "engine"
    (fake_root / ".meshkore" / "credentials").mkdir(parents=True)
    (fake_root / ".meshkore" / "credentials" / "zaelar.env").write_text("BENCH_FAKE_API_KEY=abc\n", encoding="utf-8")
    monkeypatch.setattr(credentials, "_ROOT", fake_root)
    monkeypatch.delenv("BENCH_FAKE_API_KEY", raising=False)
    path_before = v2._PATH
    with H.Isolated("en", live=True):
        assert os.environ.get("BENCH_FAKE_API_KEY") == "abc"
        assert os.environ.get("ZAELAR_JEV") == "1"
        assert v2._PATH != path_before
    assert "BENCH_FAKE_API_KEY" not in os.environ, "a provider key outlived the live run"
    assert v2._PATH == path_before
