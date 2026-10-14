"""A click the gate stops is asked about in HIS language, with the reason whole (node 2.647).

find-direct-flight-budget (EN, 2026-10-14, sandbox 020044-en): a spontaneous ping in an English session read
«Task t1 needs your OK to click «Reload — el destino es una página de com…». Shall I?». The reason was a Spanish
literal of `click_gate.decide`, glued to the label and clipped at 40 characters with `label[:40]` in the owner —
mid-word, in the other language. The reasons are now the session language's (`widgets/navegador/click_reason.py`)
and the label travels apart from the reason, clipped on a word.
"""
from __future__ import annotations

import asyncio
import inspect

import pytest

from widgets.navegador import click_gate as G
from widgets.navegador import click_reason as R

FLIGHTS = "https://www.google.com/travel/flights/booking?tfs=CBwQAhpMEgoyMDI2LTExLTA2Ih8KA0pGSxIKMjAyNi0x"


def _sig(**kw):
    base = {"name": "", "role": "button", "isSubmit": True, "inForm": True, "payment": False,
            "identity": False, "method": "get", "targetUrl": "", "pageUrl": "", "signals": "", "fields": 3}
    base.update(kw)
    return base


class _Handle:
    def __init__(self, sig):
        self._sig = sig

    async def evaluate(self, _js):
        return self._sig


def _asked(sig) -> str:
    """What `may_act` hands the confirm door for a click it stops."""
    seen: list[str] = []

    async def confirm(text):
        seen.append(text)
        return False

    ok, _why = asyncio.run(G.may_act(None, _Handle(sig), confirm=confirm, task_id="t1"))
    assert not ok and seen, "the checkout click was not asked about"
    return seen[0]


@pytest.fixture
def english(monkeypatch):
    monkeypatch.setattr("i18n.langs.current_code", lambda: "en")


def test_the_measured_ping_is_english_and_whole(english):
    asked = _asked(_sig(name="Reload", targetUrl=FLIGHTS, pageUrl=FLIGHTS))
    line = R.needs_ok("t1", asked)
    for spanish in ("el destino", "página", "compra", "reserva"):
        assert spanish not in line, line
    assert "«Reload»" in line, line
    assert "purchase, order or booking page" in line, line      # the reason, never cut
    assert R.card_question(asked).startswith("I'm about to click «Reload»"), R.card_question(asked)


@pytest.mark.parametrize("sig,expect", [
    (None, "couldn't read"),
    (_sig(name="Pay now"), "the button says"),
    (_sig(payment=True), "password or payment"),
    (_sig(signals="cc-number cvv"), "payment details"),
])
def test_every_reason_is_in_the_session_language(english, sig, expect):
    ask, why = G.decide(sig)
    assert ask and expect in why, why


def test_spanish_is_still_spanish(monkeypatch):
    monkeypatch.setattr("i18n.langs.current_code", lambda: "es")
    line = R.needs_ok("t1", _asked(_sig(name="Reload", targetUrl=FLIGHTS, pageUrl=FLIGHTS)))
    assert "página de compra, pedido o reserva" in line and "¿Confirmo?" in line, line


def test_a_long_label_is_clipped_on_a_word_never_mid_word(english):
    label = "Continue to the secure payment page of this very long airline booking checkout"
    line = R.needs_ok("t1", f"{label}{R.SEP}{R.why('checkout')}")
    clipped = line.split("«", 1)[1].split("»", 1)[0]
    assert clipped.endswith("…") and label.startswith(clipped[:-1]), clipped
    assert label.split()[len(clipped[:-1].split()) - 1] == clipped[:-1].split()[-1], "cut inside a word"


def test_an_unnamed_control_is_named_in_his_language(english):
    asked = _asked(_sig(name="", pageUrl=FLIGHTS))
    assert asked.startswith("this action"), asked


def test_the_owner_speaks_through_the_reason_module():
    """The wiring: the owner's confirm door words its ping and its card question here, not with a `[:40]` cut."""
    from widgets.navegador import owner
    src = inspect.getsource(owner.TaskBrowser._confirm)
    assert "_click_reason.needs_ok(" in src and "_click_reason.card_question(" in src, src
    assert "label[:40]" not in src and "Voy a pulsar" not in src
