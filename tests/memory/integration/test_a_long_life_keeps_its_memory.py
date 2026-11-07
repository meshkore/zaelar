"""V2-858 — a year of a generated life on one isolated, time-travelled DB keeps its memory (the long-haul run, scaled).

The full run is `python -m tests.memory.e2e.longhaul.runner --days 1095` (three years, ~25k writes); this is the
same run at one year and a third of the volume, so it fits the integration suite in seconds. The gates are the
run's own (see `tests/memory/e2e/longhaul/runner.py`): named facts asked back by name are found, every singular
fact has one valid row with its latest value and `as_of` answers the past, the allergy survives every diet change,
nothing past its TTL stays valid, no superseded shell stays indexed, the concept hubs stay one per meaning after the
language moves half-way, latency and integrity hold.

It also pins the defect class the run found on its first pass: REM's semantic dedup at 0.86 on the `hash` backend
(a self-host with no embedding key) superseded 24 of 180 named facts with another person's fact sharing the
template. The disarmed check below re-opens that door and must see the recall fall.
"""
import pytest

from tests.memory.e2e.longhaul import runner


@pytest.fixture
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_REM", "1")
    yield str(tmp_path / "zaelar.longhaul.db")


def test_a_year_of_life_passes_every_gate(_isolated):
    rep = runner.run(days=365, scale=0.3, checkpoint_every=120, db_path=_isolated, verbose=False)
    failed = {k: rep["final"] for k, ok in rep["gates"].items() if not ok}
    assert rep["passed"], f"gates failed: {sorted(failed)} · final={rep['final']}"
    assert rep["final"]["writes"] > 2500
    assert all(cp["slot_truth"] == 1.0 for cp in rep["checkpoints"])


def test_an_uncalibrated_dedup_would_lose_named_facts(_isolated, monkeypatch):
    """Disarm: declare `hash` calibrated, as REM did before V2-858 — the run must see named facts disappear."""
    from memory.rem import dedup as remdedup
    monkeypatch.setattr(remdedup, "CALIBRATED_BACKENDS", frozenset({"hash", "ollama", "cloud"}))
    rep = runner.run(days=120, scale=0.3, checkpoint_every=1000, db_path=_isolated, verbose=False)
    assert rep["final"]["found_at_12"] < runner.GATES["found_at_12"], rep["final"]["found_at_12"]
