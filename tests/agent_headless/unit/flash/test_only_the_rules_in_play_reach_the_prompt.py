"""V2-806 F4 — only the rules IN PLAY reach the model, and memory no longer carries any.

The class: an always-on block of «the newest eight rules, 90 characters each» rode every voice turn from the memory
state, whatever the turn was about, and every card's notes rode in every card row of the catalogue. Now each
sentence of his is a `note` row of the rules table: the voice turn carries `global` + `voice`, a card's notes ride in
its row only while the card is on screen, named in the turn or recently used, a worker's dossier carries `global` and
the cards' notes but never how the voice speaks — and a rule code applies (a permission, a style knob) never enters
as prose. Generic by construction: three surfaces, two cards, Spanish and English sentences.
"""
from __future__ import annotations

import pytest

import rules
from rules import notes, prompt as rprompt


@pytest.fixture(autouse=True)
def _clean():
    rules._reset_for_tests()
    yield
    rules._reset_for_tests()


def test_each_surface_carries_only_its_scopes():
    notes.add("no me hables de usted", "voice")
    notes.add("never buy from Wish", "global")
    notes.add("en la agenda, las reuniones siempre de 30 minutos", "widget:agenda")
    assert notes.for_surface("voice") == ["no me hables de usted", "never buy from Wish"]
    assert notes.for_surface("worker") == ["never buy from Wish", "en la agenda, las reuniones siempre de 30 minutos"]
    assert notes.for_surface("widget:agenda") == ["en la agenda, las reuniones siempre de 30 minutos"]
    block = rprompt.voice_block()
    assert "never buy from Wish" in block and "usted" in block and "30 minutos" not in block


def test_a_cards_note_rides_in_its_row_only_while_the_card_is_in_play():
    from widgets import brief
    notes.add("en la agenda, las reuniones siempre de 30 minutos", "widget:agenda")
    row = "[agenda] regla del operador: en la agenda, las reuniones siempre de 30 minutos"
    assert row not in brief.for_prompt([], [], query="¿qué tiempo hace?"), "a card nobody is using pays nothing"
    assert row in brief.for_prompt(["agenda"], [], query=""), "on screen"
    assert row in brief.for_prompt([], ["agenda"], query=""), "recently used"
    assert row in brief.for_prompt([], [], query="pon una reunión en la agenda"), "named in the turn"


def test_a_rule_code_applies_never_enters_as_prose():
    rules.add("voice", "pref", "fillers", "off", text="sin muletillas")
    rules.add("messaging/email/send_new", "gate", "consent", "allow", text="no me pidas confirmación para correos")
    block = rprompt.voice_block()
    assert "muletillas" not in block and "no me pidas confirmación" not in block, "his words are not re-read as prose"
    assert "REGLAS DEL OPERADOR" not in block
    assert "messaging · email · send_new = allow" in block, "one compact line for HIS permissions, and only those"
    rules._reset_for_tests()
    assert rprompt.voice_block() == "", "no rows of his: not one byte"


def test_the_voice_line_never_outgrows_the_block_it_replaced():
    for i in range(30):
        notes.add(f"regla número {i:02d}: " + "x" * 120, "global")
    block = rprompt.voice_block()
    body = block.split(": ", 1)[1]
    assert len(body) <= rprompt.VOICE_BUDGET
    assert "regla número 29" in block and "regla número 00" not in block, "the newest fit, the oldest wait"


def test_memory_composes_no_rules():
    from memory import api as memapi
    notes.add("never buy from Wish", "global")
    block, _, _ = memapi.compose_state(mission_fallback="m")
    assert "Wish" not in block and "REGLAS DEL OPERADOR" not in block


def test_the_voice_turn_and_the_worker_read_the_table(monkeypatch):
    import pathlib
    from nucleo.flash import memory_cache
    from nucleo.turn.prompt import builder
    from rules import prompt as rules_prompt
    root = pathlib.Path(__file__).resolve().parents[4]
    monkeypatch.setattr(memory_cache, "get", lambda: ("", ""))
    monkeypatch.setattr(rules_prompt, "voice_block", lambda: "\n\nRULES-IN-PLAY-MARK")
    assert "RULES-IN-PLAY-MARK" in builder.build_flash_system(turn_text="hola")[0]
    assert '_rnotes.for_surface("worker")' in (root / "nucleo/memory_agent/dossier.py").read_text("utf-8")
    assert '_rnotes.for_surface("voice")' in (root / "nucleo/circuit/__init__.py").read_text("utf-8")


# ── the sentences the memory state held move once ────────────────────────────────────────────────────────

def test_the_memory_states_sentences_are_imported_once_with_their_scopes():
    from memory import api as memapi
    memapi.set_state({"rules": ["Trátame de usted", "Nunca compres en Wish",
                                "En la agenda, las reuniones de 30 minutos"],
                      "rule_scopes": {"tratame de usted": "voice",
                                      "en la agenda las reuniones de 30 minutos": "widget:agenda"}})
    got = [(r["scope"], r["text"]) for r in notes.rows()]
    assert got == [("voice", "Trátame de usted"), ("global", "Nunca compres en Wish"),
                   ("widget:agenda", "En la agenda, las reuniones de 30 minutos")]
    assert not memapi.state().get("rules") and not memapi.state().get("rule_scopes"), "memory forgets them"
    from rules import store
    memapi.set_state({"rules": ["Trátame de usted"]})
    store._conn().execute("DELETE FROM rules_meta")
    store._done.clear()
    assert len(notes.rows()) == 3, "a re-run inserts nothing: the ids are derived from the sentence"
