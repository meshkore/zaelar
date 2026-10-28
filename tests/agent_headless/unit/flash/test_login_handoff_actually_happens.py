"""The LOGIN handoff has to HAPPEN in the text channel, not merely be named (V2-176).

Measured in `cancel-subscription-before-charge__es` (2026-08-20 10:26). The dialogue was excellent and honest —
`naturalidad 5`, `adaptacion 5`: it refused to pretend that it had the operator's account and offered the handoff — and
then:

    TESTER  Vale, abre la web de Netflix y me dices cuando esté en el login.
    ZAELAR  Aquí lo tienes.
    TESTER  Ya he entrado con mi cuenta. Sigue tú, porfa, que no quiero tocar nada más.
    ZAELAR  Vale, dame un momento que lo miro.

with an EMPTY `navegador_task`. `authenticate_web` and `login_done` were resolved in `probe.py` to a LABEL and nothing
else: the voice called its two closures and this channel — the one used by use cases — executed nothing. No
window was opened, so «ya he entrado» had no task to resume and «lo miro» had nothing to look at.
The judge called it «an empty facade»; the words were true and what was missing was the wiring.

It is the SAME hole that the cron block in `probe.py` had already documented in these words: «the execution block
only covered worker + data-op. The `probe` channel is the one used by use cases, so the notification COULD NOT
exist in a run no matter how well the model emitted the tag». All 54 scenarios in the `credentials` segment
go through this handoff.

The typed channel now runs the voice turn itself (`nucleo.cli.turn.run_turn`), so these cases drive it there with
a recorded model; `execute=True` is the real cycle, the default is dry.
"""
from __future__ import annotations

from tests import voice_turn_source as _vts

import asyncio

import pytest

from nucleo.flash import web_auth
from tests.brain import harness as H

AUTH_NETFLIX = {"name": "authenticate_web", "args": {"site": "netflix.com"}}
LOGIN_DONE = {"name": "login_done", "args": {}}


@pytest.fixture
def spied(monkeypatch):
    """Spy on the DISPATCH to the browser owner, which is the real boundary: what is measured is that the command
    goes out, not that Chromium starts in a test."""
    sent: list[tuple] = []
    monkeypatch.setattr("nucleo.flash.procs.dispatch",
                        lambda wid, action, payload=None: sent.append((wid, action, payload or {})) or True)
    return sent


def _turn(text: str, call: dict, say: str, *, execute: bool, before=None) -> dict:
    case = {"id": "login", "lang": "es", "phrase": text, "source": "test", "screen": {"open": []}, "expect": "talk",
            "model": {"say": say, "tools": [call]}}
    with H.Isolated("es") as iso:
        iso.seed(case)
        if before:
            before()
        from nucleo.cli import turn
        try:
            return asyncio.run(turn.run_turn(text, sid="login", ingest=False, execute=execute))
        finally:
            turn.reset("login")


def _called(res: dict, name: str) -> bool:
    return any(c.get("name") == name for c in res.get("tool_calls") or [])


# ── open the window ─────────────────────────────────────────────────────────────────────────────────────────
def test_the_login_window_is_actually_opened(spied):
    res = _turn("Abre la web de Netflix y me dices cuando esté en el login.", AUTH_NETFLIX, "Aquí lo tienes.",
                execute=True)
    assert _called(res, "authenticate_web"), res
    assert any(a == "authenticate" for _w, a, _p in spied), "nothing was queued to the browser owner"


def test_it_opens_the_site_the_operator_named(spied):
    _turn("Abre Netflix.", AUTH_NETFLIX, "Aquí lo tienes.", execute=True)
    urls = [p.get("url") for _w, a, p in spied if a == "authenticate"]
    assert urls and "netflix.com" in urls[0]


def test_without_execute_it_still_only_REPORTS(spied):
    """The typed channel remains a reporting channel by default. `execute` is what turns it into the real cycle
    (V2-049), and without it nothing can open a window on the operator's machine."""
    res = _turn("Abre Netflix.", AUTH_NETFLIX, "Aquí lo tienes.", execute=False)
    assert _called(res, "authenticate_web"), res
    assert not spied


# ── «ya he entrado» ─────────────────────────────────────────────────────────────────────────────────────────
def test_the_operator_saying_he_is_in_resumes_the_waiting_task(spied):
    from widgets.navegador import tasks as navtasks
    navtasks._tasks.clear()

    def _waiting():
        tid = navtasks.create("Iniciar sesión · netflix.com")
        navtasks._tasks[tid]["awaiting_login"] = True
    try:
        _turn("Ya he entrado con mi cuenta. Sigue tú.", LOGIN_DONE, "Vale, sigo yo.", execute=True, before=_waiting)
        assert any(a == "auth_done" for _w, a, _p in spied), "the confirmed login did not reach the task"
    finally:
        navtasks._tasks.clear()


def test_and_saying_it_with_NOTHING_waiting_reports_that_honestly(spied):
    """Nothing resumed is the honest outcome of «it says it is already logged in and no login was waiting» — the
    same criterion as the expired confirmation in V2-190. Treating the turn as successful would invent that
    something resumed."""
    from widgets.navegador import tasks as navtasks
    navtasks._tasks.clear()
    res = _turn("Ya he entrado.", LOGIN_DONE, "Vale, sigo yo.", execute=True)
    assert _called(res, "login_done"), res
    assert not any(a == "auth_done" for _w, a, _p in spied)


# ── the shared decision ─────────────────────────────────────────────────────────────────────────────────────
# Without this guard, wiring the text channel would have broken TWO invariants on its first turn: a music service
# connects through the `musica` card and QR messaging through `mensajeria`, never driving Chromium to spotify.com.
# The chain lived ONLY inside the voice provider.
@pytest.mark.parametrize("site,text,kind", [
    ("netflix.com", "abre la web de Netflix y me dices cuando esté en el login", web_auth.KIND_LOGIN),
    ("spotify", "conéctame a mi cuenta de Spotify", web_auth.KIND_MUSIC),
    ("whatsapp", "conéctame WhatsApp", web_auth.KIND_MESSAGING),
])
def test_which_handoff_this_is_gets_decided_once(site, text, kind):
    assert web_auth.decide(site, text)[0] == kind


def test_a_music_service_does_not_open_a_browser_from_the_text_channel(spied):
    res = _turn("Conéctame a mi cuenta de Spotify.", {"name": "authenticate_web", "args": {"site": "spotify"}},
                "Te lo abro.", execute=True)
    assert _called(res, "authenticate_web"), res
    assert not any(a == "authenticate" for _w, a, _p in spied), "it opened a browser for a music service"


def test_no_site_no_guessing():
    """Bug from 2026-07-23: without a recognized site this opened wallapop.com by default — a login to a site that
    nobody requested. There is nothing to open, so nothing is opened."""
    assert web_auth.start("") == ""


def test_the_voice_turn_delegates_to_ONE_body():
    """Guard against the divergence this repo has already paid for (V2-153: the same notification scheduled twice
    because two copies of a decision could not see each other). The voice closures must DELEGATE, not reimplement."""
    import inspect

    from voice.engine.llm.providers import nucleo as voice_nucleo
    src = _vts.turn_source()
    start = src[src.index("def _start_web_auth"):]
    start = start[:start.index("\n        def ")] if "\n        def " in start else start
    assert "web_auth" in start, "la voz volvió a implementar el arranque del login por su cuenta"
    assert "procs.dispatch" not in start, "la voz despacha directamente otra vez: son dos cuerpos de nuevo"
