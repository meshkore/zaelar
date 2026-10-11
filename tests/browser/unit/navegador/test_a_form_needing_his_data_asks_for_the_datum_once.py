"""A form that needs HIS data asks for the DATUM, once, whole, in his language — never an OK to click.

Measured in `rental-car-automatic-airport` (2026-10-11, EN round): three identical spontaneous pings,
«Task 2 needs your OK to click «Para rellenar este formulario me falta t». Shall I?». The gate's missing-datum
sentence went through `owner._confirm`, the yes/no door for an irreversible click, which cut it at 40 characters as
a button label, asked for a consent nobody could give, spoke Spanish to an English operator, and repeated on every
retry of the same click. `widgets/navegador/form_facts.py` is the datum's own door.
"""
from __future__ import annotations

import asyncio

import pytest

from widgets.navegador import click_gate as G
from widgets.navegador import form_facts as F


@pytest.fixture
def notes(monkeypatch):
    sent: list[str] = []

    async def _notify(widget, text, kind="notify"):
        sent.append(text)

    from voice import proactive
    monkeypatch.setattr(proactive, "notify", _notify)
    F.forget()
    yield sent
    F.forget()


def _missing_form_sig():
    return {"name": "Buscar", "role": "button", "isSubmit": True, "inForm": True, "payment": False,
            "identity": False, "method": "get", "targetUrl": "", "pageUrl": "https://example.test/search",
            "signals": "email telefono nombre text", "fields": 3}


class _Handle:
    async def evaluate(self, _js):
        return _missing_form_sig()


@pytest.fixture
def knows_nothing(monkeypatch):
    from memory import api as _mem
    monkeypatch.setattr(_mem, "state", lambda: {})
    monkeypatch.setattr(_mem, "by_slot_prefix", lambda *a, **k: [])


@pytest.mark.parametrize("code,expect", [("es", ("tu nombre", "tu email", "tu teléfono")),
                                         ("en", ("your name", "your email", "your phone number"))])
def test_the_note_names_every_missing_datum_whole_in_his_language(monkeypatch, code, expect):
    monkeypatch.setenv("ZAELAR_LANGUAGE", code)
    line = F.sentence("2", ["operator.name", "operator.email", "operator.phone"])
    for word in expect:
        assert word in line, line
    assert "«" not in line, "a datum ask quotes no button label"
    assert "OK" not in line and "pulsar" not in line, "a datum ask is not a consent to click"


def test_the_same_task_and_facts_are_asked_ONCE(notes, monkeypatch):
    monkeypatch.setenv("ZAELAR_LANGUAGE", "en")
    missing = ["operator.name", "operator.email", "operator.phone"]
    assert asyncio.run(F.ask_once("2", missing)) is True
    assert asyncio.run(F.ask_once("2", list(reversed(missing)))) is False
    assert asyncio.run(F.ask_once("2", ["operator.address"])) is True, "a NEW datum is a new question"
    assert len(notes) == 2


def test_the_gate_never_routes_a_missing_datum_through_the_click_consent(notes, knows_nothing, monkeypatch):
    """Three retries of the same click: the worker gets the refusal each time, he gets ONE note, and the
    yes/no door is never opened (it waited 60 s per retry for an answer the gate then threw away)."""
    monkeypatch.setenv("ZAELAR_LANGUAGE", "en")
    asked: list[str] = []

    async def _confirm(label):
        asked.append(label)
        return True

    for _ in range(3):
        ok, why = asyncio.run(G.may_act(None, _Handle(), confirm=_confirm, task_id="2"))
        assert ok is False and "operator.phone" in why
    assert asked == [], "the click-consent door was asked for a datum"
    assert len(notes) == 1 and "your phone number" in notes[0]
