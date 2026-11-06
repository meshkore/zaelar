"""A rule he states is said once, by the turn, and never claimed when no gate can apply it (V2-852 M3/M4).

Session 94be1e1e: «no me pidas confirmación para mandar mensajes a Raquel» — the turn answered «Got it — no more
confirmations», then the rule writer, off the turn, said «Entendido: no te pido confirmación…» in another language:
two mouths for one fact. And the row was a NOTE at a consent class's scope, which no gate reads, so the next send
asked again — both lines had promised the opposite. Since V2-857 phase 2 a rule about one person IS applicable (a
gate row at `subject:<id>…`, node 2.1612); a note at a class scope that names a person is one the shaper did not
apply, and the line says so — kept, not applied, and how to say it so it applies — never that it cannot.
"""
from __future__ import annotations

import asyncio

import pytest

from nucleo.flash import style_directive as sd


def _write(monkeypatch, res: dict, *, open_mouth: bool):
    import rules.shape as shape
    from nucleo.turn import mouth
    from widgets.contactos import digest
    said = []
    # his directory: one person, Raquel Salvador (a note's words name her or nobody)
    monkeypatch.setattr(digest, "people_named", lambda t, *a, **k: [{"name": "Raquel Salvador"}]
                        if "raquel" in str(t).lower() else [])
    monkeypatch.setattr(shape, "write", lambda d, t: dict(res))
    monkeypatch.setattr(mouth, "is_open", lambda *_a: open_mouth)
    monkeypatch.setattr(mouth, "say", lambda line, **k: said.append(line) or "out")
    out = asyncio.run(sd.write_rule("d", "t", lambda *a, **k: None))
    return out, said


_NOTE_AT_A_CLASS = {"op": "add", "say": "Entendido: no te pido confirmación para Raquel.",
                    "stored": [{"id": "r1", "scope": "messaging/*/send_new", "kind": "pref", "key": "note",
                                "text": "no me pidas confirmación para mandar mensajes a Raquel"}]}
#: a note at the same class scope whose words name nobody: a preference, not a per-person exception (H10)
_NOTE_NAMING_NOBODY = {"op": "add", "say": "Noted: work messages preferably by email.",
                       "stored": [{"id": "r3", "scope": "messaging/*/send_new", "kind": "pref", "key": "note",
                                   "text": "for work things, better by email"}]}
_A_GATE = {"op": "add", "say": "Got it: WhatsApp goes out without asking.",
           "stored": [{"id": "r2", "scope": "messaging/whatsapp/send_new", "kind": "gate", "key": "consent", "text": "x"}]}


def test_a_permission_no_gate_reads_is_said_as_kept_not_applied(monkeypatch):
    out, said = _write(monkeypatch, _NOTE_AT_A_CLASS, open_mouth=False)
    from i18n import langs
    assert said == [langs.spec().rule_kept_not_applied] and out["line"] == said[0]


def test_an_applied_rule_the_turn_already_answered_is_not_said_again(monkeypatch):
    out, said = _write(monkeypatch, _A_GATE, open_mouth=False)
    assert said == [] and out["line"]


def test_while_the_turn_is_live_its_mouth_says_the_rule(monkeypatch):
    _, said = _write(monkeypatch, _A_GATE, open_mouth=True)
    assert said == [_A_GATE["say"]]


@pytest.mark.parametrize("pack", ["en", "es"])
def test_the_line_exists_in_every_pack(pack):
    from i18n import langs
    assert langs.spec(pack).rule_kept_not_applied


def test_a_note_at_a_class_that_names_nobody_is_not_said_to_be_about_one_person(monkeypatch):
    out, said = _write(monkeypatch, _NOTE_NAMING_NOBODY, open_mouth=True)
    assert said == [_NOTE_NAMING_NOBODY["say"]] and out["line"] == said[0]


def test_off_the_turn_a_write_that_applied_nothing_is_said_by_the_writer(monkeypatch):
    """The turn answered before the write ended; a write that kept only a free note backs no «got it» — the writer,
    the one who knows, says what it kept (H11). An applied rule is still not said twice (the test above)."""
    out, said = _write(monkeypatch, _NOTE_NAMING_NOBODY, open_mouth=False)
    assert said == [_NOTE_NAMING_NOBODY["say"]]


def test_disarmed_backed_silences_a_write_that_applied_nothing(monkeypatch):
    monkeypatch.setattr(sd, "backed", lambda _res: True)
    _out, said = _write(monkeypatch, _NOTE_NAMING_NOBODY, open_mouth=False)
    assert said == [], "the disarm did not take"


def test_disarmed_the_person_reading_claims_every_class_note_is_about_one_person(monkeypatch):
    monkeypatch.setattr(sd, "_names_a_person", lambda _t: True)
    _out, said = _write(monkeypatch, _NOTE_NAMING_NOBODY, open_mouth=True)
    from i18n import langs
    assert said == [langs.spec().rule_kept_not_applied], "the disarm did not take"
