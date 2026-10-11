"""`search-rent-apartment__es` / `search-buy-sofa__es` (2026-10-11): the model's own words on an escalation turn —
«Estoy investigando a fondo…», «voy a seguir investigando» — were said over a worker chain with no quota, where the
dispatcher refuses the errand. In the text channel the turn's words are replaced by the asleep sentence; a reply
that already names the quota stands. (The voice channel has already spoken by then: the dispatcher's refusal is
spoken right after it — `quota_wait.tell`.)"""
import time
from pathlib import Path

import pytest

from nucleo.workers import providers, quota_wait

ROOT = Path(__file__).resolve().parents[4]


@pytest.fixture
def asleep(monkeypatch):
    monkeypatch.setattr(providers, "exhausted_until", lambda: time.time() + 1800)
    monkeypatch.setenv("ZAELAR_LANGUAGE", "es")


def test_a_claim_of_starting_the_errand_is_replaced(asleep):
    out = quota_wait.over_an_escalation("Estoy investigando a fondo pisos en Valencia; verás los avances en la hoja.")
    assert "cuota" in out and "investigando" not in out


def test_a_reply_that_already_names_the_quota_stands(asleep):
    said = "No puedo lanzarla: me he quedado sin cuota hasta las 20:32."
    assert quota_wait.over_an_escalation(said) == said


def test_an_awake_chain_changes_nothing(monkeypatch):
    monkeypatch.setattr(providers, "exhausted_until", lambda: 0.0)
    assert quota_wait.over_an_escalation("On it.") == "On it."


def test_the_text_channel_wires_it_on_escalation_turns():
    src = (ROOT / "nucleo/flash/probe_after.py").read_text()
    assert 'if action == "escalate":' in src and "_qwait.over_an_escalation(spoken" in src
