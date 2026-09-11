"""V2-668 · a QUESTION about what a widget holds is answered by READING that widget — `read_widget`.

Measured live, session 53de97d4 (2026-09-11, 10:58:33 → 11:00:03): «¿a qué hora tengo la cita con Hacienda?»
was answered «no la tengo con hora» while the agenda held `11:30–12:30 · Cita Agencia Tributaria` in one
line. Six turns later, after the operator opened the card BY HAND, the model said «hoy a las once y media» —
calling no tool: a widget's interior only ever reached the prompt while the card was OPEN, and no tool could
read a closed one. `widget_data` executes, `recall` remembers his life, `web_search` reads the world; nothing
read what his own widget stores.
"""
from __future__ import annotations

import re
import time
from pathlib import Path

import pytest

from nucleo.flash import router, widget_read


# ── the door exists, is never trimmed, and routes ─────────────────────────────────────────────────────────
def test_read_widget_is_in_the_catalog_and_in_the_untrimmed_memory_family():
    names = {t["function"]["name"] for t in router.TOOLS}
    assert "read_widget" in names
    assert "read_widget" in router.FAMILIES["memory"]
    from nucleo.flash import tool_selection
    assert "memory" in tool_selection.ALWAYS, "a question announces nothing — the reader must always be offered"


def test_the_router_decides_a_read():
    d = router.decide("read_widget", {"widget_id": "agenda", "question": "hora de la cita con Hacienda"})
    assert d.kind == router.READ_WIDGET
    assert d.payload == {"widget_id": "agenda", "question": "hora de la cita con Hacienda"}
    assert router.READ_WIDGET in router._PRIORITY


def test_the_other_doors_point_at_this_one():
    """The model is told where a question about HIS data goes — in the tools it would otherwise reach for."""
    by = {t["function"]["name"]: t["function"]["description"] for t in router.TOOLS}
    assert "read_widget" in by["web_search"], "his own data is not a web fact"
    assert "read_widget" in by["widget_data"], "asking is not acting"
    assert "read_widget" in by["recall"], "the agenda is not his long-term memory"


# ── resolution: names only, never «the card that is open» ────────────────────────────────────────────────
def test_resolve_takes_the_exact_id_or_the_name_the_sentence_carries():
    assert widget_read.resolve("agenda") == "agenda"
    assert widget_read.resolve("la agenda", "¿a qué hora tengo la cita con Hacienda?") == "agenda"
    assert widget_read.resolve("", "abre la agenda y dime qué tengo") == "agenda"
    # (a sentence naming TWO widgets — «la agenda y dime la hora» — resolves to the stronger alias, the clock;
    #  that is the resolver working, not this door: the model names the widget it means in `widget_id`.)


def test_resolve_names_nothing_when_nothing_is_named(monkeypatch):
    """The Hacienda sentence names no widget by alias — resolution is honest about it, and never falls back to
    whatever card is open (V2-666's rule, applied to reading)."""
    from memory import api as _memapi
    monkeypatch.setattr(_memapi, "state", lambda: {"open_widgets": ["youtube"], "recent_widgets": []})
    assert widget_read.resolve("", "¿a qué hora tengo la cita con Hacienda?") is None
    assert widget_read.resolve("hacienda", "¿a qué hora tengo la cita con Hacienda?") is None


# ── the read: the agenda's hour, with the card CLOSED ─────────────────────────────────────────────────────
@pytest.fixture
def _isolated_agenda(tmp_path, monkeypatch):
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    from nucleo import scheduler
    monkeypatch.setattr(scheduler, "create", lambda prompt, stamp, name="": {"ok": True, "id": "job1"})
    monkeypatch.setattr(scheduler, "cancel", lambda ref: None)
    from widgets.agenda import data as agenda
    today = time.strftime("%Y-%m-%d")
    r = agenda.apply_action("add_meeting", {"title": "Cita Agencia Tributaria - certificado de persona jurídica",
                                            "date": today, "startTime": "11:30"})
    assert r.get("ok", True) is not False, r
    return agenda


def test_the_hour_he_asked_for_is_in_the_block_with_the_card_closed(_isolated_agenda):
    block = widget_read.read("agenda")
    assert "11:30" in block and "Tributaria" in block
    assert len(block) <= widget_read._MAX_BLOCK_CHARS


def test_a_widget_that_publishes_nothing_reads_as_empty_not_invented(monkeypatch):
    from widgets import refs
    monkeypatch.setattr(refs, "prompt_digest", lambda wid: "")
    monkeypatch.setattr(refs, "items_line", lambda wid: "")
    import importlib
    monkeypatch.setattr(importlib, "import_module", lambda name: (_ for _ in ()).throw(ImportError(name)))
    assert widget_read.read("clock") == ""
    assert widget_read.read("") == ""


# ── the second pass: the block is the ONLY source, an absence is stated ───────────────────────────────────
def test_compose_system_makes_the_block_the_only_source():
    sysp = widget_read.compose_system("LOCK", "¿a qué hora tengo la cita con Hacienda?", "agenda",
                                      "hora cita Hacienda", "  · 2026-09-11 11:30 «Cita Agencia Tributaria»")
    assert sysp.startswith("LOCK")
    assert "11:30" in sysp and "Cita Agencia Tributaria" in sysp
    assert "SOLO lo que hay aquí" in sysp and "no lo rellenes" in sysp
    assert "PREGUNTA: hora cita Hacienda" in sysp
    assert "PETICIÓN DEL OPERADOR: ¿a qué hora tengo la cita con Hacienda?" in sysp


def test_an_empty_block_is_declared_empty_never_filled():
    sysp = widget_read.compose_system("LOCK", "¿qué tengo el jueves?", "agenda", "", "")
    assert "no tiene nada guardado" in sysp


# ── both channels are wired (V2-252: parallel implementations drift unless both are read) ────────────────
def _code(rel: str) -> str:
    return re.sub(r"(?m)^\s*#.*$", "", Path(rel).read_text(encoding="utf-8"))


def test_the_voice_provider_captures_and_resolves_the_read():
    code = _code("voice/engine/llm/providers/nucleo.py")
    assert 'elif name == "read_widget":' in code
    assert "read_req = {" in code
    assert "_wread.resolve(" in code and "_wread.read, _rwid" in code and "_wread.compose_system(" in code
    # a read is a light route: it yields to a worker, a search or a secret in the same turn
    assert 'if read_req["v"] is not None and escalate_req["v"] is None and search_req["v"] is None' in code
    # …and recall does not ALSO speak when the turn read a widget
    assert 'and reveal_req["v"] is None and read_req["v"] is None:' in code


def test_the_probe_mirrors_the_route():
    code = _code("nucleo/flash/probe.py")
    assert 'elif "read_widget" in names:' in code
    assert 'if action == "read_widget":' in code
    assert "_wread.resolve(" in code and "_wread.compose_system(" in code


# ── V2-668b: TODAY's agenda rides in the state with the card CLOSED, and says it outranks a recollection ──
# Measured on the live re-run of the incident (11:33): `read_widget` was offered and the model still answered a
# memory pill saying 11:00 over an agenda saying 11:30. A fact IN the prompt beats a tool call away.
def test_todays_agenda_is_in_the_state_with_the_card_closed(_isolated_agenda):
    from widgets import brief
    out = brief.for_prompt(open_ids=[], recent_ids=[], query="¿a qué hora tengo la cita con Hacienda?")
    assert "AGENDA DE HOY" in out and "11:30" in out and "Tributaria" in out
    assert "MANDA esto" in out, "the block must say who wins when a recollection disagrees"
    assert "read_widget" in out, "and where the rest of the calendar is read from"


def test_the_open_card_keeps_its_coach_block_and_gets_no_duplicate_today_line(_isolated_agenda):
    from widgets import brief
    out = brief.for_prompt(open_ids=["agenda"], recent_ids=[], query="")
    assert "AGENDA (abierta)" in out and "11:30" in out
    assert "AGENDA DE HOY — lo que GUARDA" not in out


def test_an_empty_day_costs_nothing(tmp_path, monkeypatch):
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    from widgets.agenda import data as agenda
    assert agenda.today_line() == ""
