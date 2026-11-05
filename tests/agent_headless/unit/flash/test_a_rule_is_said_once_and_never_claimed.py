"""A rule he states is said once, by the turn, and never claimed when no gate can apply it (V2-852 M3/M4).

Session 94be1e1e: «no me pidas confirmación para mandar mensajes a Raquel» — the turn answered «Got it — no more
confirmations», then the rule writer, off the turn, said «Entendido: no te pido confirmación…» in another language:
two mouths for one fact. And the row was a NOTE at a consent class's scope, which no gate reads (a rule about one
person waits for per-subject exceptions), so the next send asked again — both lines had promised the opposite.
"""
from __future__ import annotations

import asyncio

import pytest

from nucleo.flash import style_directive as sd


def _write(monkeypatch, res: dict, *, open_mouth: bool):
    import rules.shape as shape
    from nucleo.turn import mouth
    said = []
    monkeypatch.setattr(shape, "write", lambda d, t: dict(res))
    monkeypatch.setattr(mouth, "is_open", lambda *_a: open_mouth)
    monkeypatch.setattr(mouth, "say", lambda line, **k: said.append(line) or "out")
    out = asyncio.run(sd.write_rule("d", "t", lambda *a, **k: None))
    return out, said


_NOTE_AT_A_CLASS = {"op": "add", "say": "Entendido: no te pido confirmación para Raquel.",
                    "stored": [{"id": "r1", "scope": "messaging/*/send_new", "kind": "pref", "key": "note", "text": "x"}]}
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
