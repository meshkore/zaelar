"""V2-469 · a bare «Hecho.» to a QUESTION is a non-answer.

Measured in `build-a-video-playlist-from-links` (2026-08-28 23:05): «¿Y qué hay en la lista?» → the model
went mute over a redundant `add` → the canned data ack said «Hecho.» — twice, with the watchdog nudging
both times and the user asking FIVE times before getting the titles (naturalidad 2, eficiencia 2). The
outcome the operator asked about was one read away: when the operator's turn asked something and the model
said nothing, the ack enumerates what the acted-on widget now holds — true, generic (any widget publishing
`ref_index`: the agenda, the player list, the photo strip), and it answers what the canned word ignored.
"""
import pytest

from nucleo.flash import widget_data_turn as WDT


@pytest.fixture(autouse=True)
def _labels(monkeypatch):
    from widgets import refs
    monkeypatch.setattr(refs, "_ref_index", lambda wid: (
        [{"id": "a", "label": "Rick Astley - Never Gonna Give You Up", "field": "item"},
         {"id": "b", "label": "PSY - Gangnam Style", "field": "item"}] if wid == "youtube" else []))


_OK = {"executed": "widget_data", "widget": "youtube", "act": "add", "ops": [{"widget": "youtube", "act": "add"}]}


def test_the_measured_question_gets_the_list_not_hecho():
    out = WDT.named_ack(_OK, "Hecho.", "¿Y qué hay en la lista?")
    assert "Rick Astley" in out and "PSY" in out
    assert out != "Hecho."


def test_a_plain_order_keeps_the_plain_ack():
    assert WDT.named_ack(_OK, "Hecho.", "Añade también este enlace") == "Hecho."


def test_a_widget_that_publishes_nothing_never_invents_an_enumeration():
    parte = {"executed": "widget_data", "widget": "meteo", "act": "refresh"}
    assert WDT.named_ack(parte, "Hecho.", "¿Qué tiempo hace?") == "Hecho."


def test_a_failed_op_keeps_its_failure_message():
    parte = {"executed": "widget_data_failed", "widget": "youtube", "act": "add", "message": "no lo aceptó"}
    out = WDT.named_ack(parte, "Hecho.", "¿Qué hay en la lista?")
    assert "No he podido" in out


def test_the_probe_wires_it():
    """Wiring guard (V2-199): the cases above pass whole with the probe's call deleted."""
    from pathlib import Path
    src = Path("nucleo/flash/probe.py").read_text(encoding="utf-8")
    assert "named_ack" in src
