"""A spoken consent rule moves the consent gate — in production, not only in tests (2026-09-29).

A consent rule once existed with its parser and tests and NO production caller: the sentence reached the model as
prose and the gate that decides act-or-ask never heard it. Since V2-806 both channels hand the sentence to
`rules.shape`, which writes the gate row the decision reads.
"""
import asyncio
import pathlib

import pytest

from memory import db as memdb
from memory import embeddings as mememb
from nucleo import consent, style_policy as sp
from nucleo.flash import style_directive

ENGINE = pathlib.Path(__file__).resolve().parents[3]


@pytest.fixture(autouse=True)
def _fresh(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    monkeypatch.setenv("ZAELAR_WORKSPACE", str(tmp_path))
    mememb.reset(); memdb.reset_db(); memdb.get_db()
    consent._reset_for_tests(); sp._reset_for_tests()
    yield
    memdb.reset_db(); mememb.reset(); consent._reset_for_tests(); sp._reset_for_tests()


class _Sess:
    directive = ""


def _answer(monkeypatch, plan):
    import json
    from rules import shape
    monkeypatch.setattr(shape, "_chat", lambda system, user: json.dumps(plan))


def test_the_written_rule_moves_the_gate_and_a_retraction_restores_genesis(monkeypatch):
    assert consent.ask_at() == "critical", "genesis"
    rule = "pregúntame siempre antes de tocar nada"
    _answer(monkeypatch, {"op": "add", "say": "ok",
                          "rows": [{"scope": "global", "kind": "gate", "key": "ask_at", "value": "sensitive"}]})
    asyncio.run(style_directive.write_rule(rule, rule, lambda *a, **k: None, _Sess(), speak=False))
    assert consent.ask_at() == "sensitive", "the spoken rule governs the very next decision"
    import rules
    rid = rules.deciding_rule(rules.path(), "ask_at")["id"]
    gone = "olvida lo de preguntarme siempre antes"
    _answer(monkeypatch, {"op": "remove", "remove": [rid], "say": "ok"})
    asyncio.run(style_directive.write_rule(gone, gone, lambda *a, **k: None, _Sess(), speak=False))
    assert consent.ask_at() == "critical", "back to genesis"


