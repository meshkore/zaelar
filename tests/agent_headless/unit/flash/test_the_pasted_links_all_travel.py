"""V2-469 · the links the operator PASTED all travel — and the enumeration marks the one playing.

Measured in `build-a-video-playlist-from-links` (23:17): two links pasted in one message, the model called
ONE `add` carrying one of them — «Hecho. Ahora mismo hay: «Rick Astley…»» — and the user had to correct it
(«te pasé dos, ¿no?»), costing two turns. The multi-link add works (V2-384 bis, verified); what failed was
the model's payload. The links are the operator's own words, so completing the payload with the ones his
turn carries invents nothing. Same round, the other half: «¿y qué está sonando ahora?» got the enumeration
WITHOUT marking which one — `named_ack` used labels and dropped the hints ref_index publishes.
"""
import pytest

from nucleo.flash import widget_data_turn as WDT

_TURN = ("Te paso un par de vídeos: https://www.youtube.com/watch?v=dQw4w9WgXcQ y "
         "https://youtu.be/9bZkp7q19f0 — móntame una lista con ellos.")


def test_a_missing_pasted_link_is_completed_into_the_add():
    calls = [{"name": "widget_data",
              "args": {"widget_id": "youtube", "action": "add",
                       "payload": {"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"}}}]
    out = WDT.complete_pasted_links(calls, _TURN)
    url = out[0]["args"]["payload"]["url"]
    assert "dQw4w9WgXcQ" in url and "9bZkp7q19f0" in url


def test_links_already_covered_change_nothing():
    calls = [{"name": "widget_data",
              "args": {"widget_id": "youtube", "action": "add",
                       "payload": {"url": _TURN}}}]
    out = WDT.complete_pasted_links(calls, _TURN)
    assert out[0]["args"]["payload"]["url"] == _TURN


def test_a_turn_without_links_or_a_non_add_op_is_left_alone():
    calls = [{"name": "widget_data",
              "args": {"widget_id": "youtube", "action": "play", "payload": {}}}]
    assert WDT.complete_pasted_links(calls, _TURN) == calls
    calls2 = [{"name": "widget_data",
               "args": {"widget_id": "agenda", "action": "add_meeting", "payload": {"title": "x"}}}]
    assert WDT.complete_pasted_links(calls2, "sin enlaces aquí") == calls2


def test_the_enumeration_marks_the_one_playing(monkeypatch):
    from widgets import refs
    monkeypatch.setattr(refs, "_ref_index", lambda wid: [
        {"id": "1", "label": "Rick Astley", "field": "item", "hint": "la que suena"},
        {"id": "2", "label": "PSY", "field": "item", "hint": ""}])
    parte = {"executed": "widget_data", "widget": "youtube", "act": "play"}
    out = WDT.named_ack(parte, "Hecho.", "¿Y qué está sonando ahora?")
    assert "la que suena" in out and "Rick Astley" in out


def test_the_probe_wires_the_completion():
    from pathlib import Path
    src = Path("nucleo/flash/probe.py").read_text(encoding="utf-8")
    assert "complete_pasted_links" in src


# ── the failure rides along even when the model spoke (V2-469, round 11 turn 7) ──────────────────────────
def test_a_spoken_reply_over_a_failed_op_gets_the_failure_appended():
    """«Ahora en pantalla te muestro el siguiente» over widget_data_failed («No hay más vídeos en la
    lista») — the model spoke, so the honest canned failure never replaced anything, and the narration
    lied over a failure the system had in hand."""
    parte = {"executed": "widget_data_failed", "widget": "youtube", "act": "next",
             "message": "No hay más vídeos en la lista."}
    out = WDT.ensure_failure_named("Ahora en pantalla te muestro el siguiente.", parte)
    assert out.startswith("Ahora en pantalla")
    assert "No hay más vídeos" in out


def test_a_successful_op_appends_nothing():
    parte = {"executed": "widget_data", "widget": "youtube", "act": "next"}
    assert WDT.ensure_failure_named("Hecho.", parte) == "Hecho."


def test_a_mute_turn_keeps_the_plain_failure_line():
    parte = {"executed": "widget_data_failed", "widget": "youtube", "act": "next", "message": "no va"}
    assert WDT.ensure_failure_named("", parte) == ""


# ── «dime qué está sonando» is a question without a question mark (V2-469, round 11 turn 1) ─────────────
def test_dime_counts_as_asking(monkeypatch):
    from widgets import refs
    monkeypatch.setattr(refs, "_ref_index", lambda wid: [
        {"id": "1", "label": "Rick", "field": "item", "hint": "la que suena"}])
    parte = {"executed": "widget_data", "widget": "youtube", "act": "play"}
    out = WDT.named_ack(parte, "Hecho.", "Perfecto, pues ponla y dime qué está sonando ahora mismo.")
    assert "Rick" in out and out != "Hecho."


def test_the_probe_wires_the_failure_augmentation():
    from pathlib import Path
    src = Path("nucleo/flash/probe.py").read_text(encoding="utf-8")
    assert "ensure_failure_named" in src
