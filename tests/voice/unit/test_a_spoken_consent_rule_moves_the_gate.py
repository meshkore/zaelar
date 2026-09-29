"""A spoken consent rule moves the consent gate — in production, not only in tests (2026-09-29).

`consent.apply_directive` («pregúntame siempre antes de tocar nada» → ask at `sensitive`; «hazlo directamente,
no me preguntes» → `critical`) existed with its regexes and tests and NO production caller: the sentence reached
the model as a rule in `state.rules` and the gate that decides act-or-ask never heard it. The style sibling was
wired in both channels; this one is wired beside it.
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


def test_the_probe_channel_moves_the_gate_and_a_retraction_restores_genesis():
    assert consent.ask_at() == "critical", "genesis"
    rule = "pregúntame siempre antes de tocar nada"
    asyncio.run(style_directive.handle_probe(rule, rule, _Sess(), ingest=True))
    assert consent.ask_at() == "sensitive", "the spoken rule governs the very next decision"
    gone = "olvida lo de preguntarme siempre antes"
    asyncio.run(style_directive.handle_probe(gone, gone, _Sess(), ingest=True))
    assert consent.ask_at() == "critical", "back to genesis"


def test_both_channels_are_wired():
    src = (ENGINE / "nucleo/flash/style_directive.py").read_text("utf-8")
    assert src.count("_consent.apply_directive(") == 2, "voice and probe both move the consent flags"
    assert src.count("_consent.retract_directive(") == 2
