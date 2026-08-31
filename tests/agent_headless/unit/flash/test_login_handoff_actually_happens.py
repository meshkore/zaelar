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
"""
from __future__ import annotations

import asyncio

import pytest

from memory import db as memdb
from memory import embeddings as mememb
from nucleo.flash import probe
from nucleo.flash import web_auth
from voice import brain_notes


class _CallsAuth:
    """Stub: the model requests the Netflix login, as in the measured run."""

    async def stream(self, *_a, on_tool_call=None, **_kw):
        if on_tool_call:
            on_tool_call("authenticate_web", {"site": "netflix.com"})
        yield "Aquí lo tienes."


class _SaysImIn:
    async def stream(self, *_a, on_tool_call=None, **_kw):
        if on_tool_call:
            on_tool_call("login_done", {})
        yield "Vale, sigo yo."


@pytest.fixture(autouse=True)
def _hash_backend(monkeypatch):
    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
    mememb.reset()
    yield
    mememb.reset()


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    memdb.reset_db()
    memdb.get_db()
    yield
    memdb.reset_db()


@pytest.fixture
def sid():
    s = "test-login-handoff"
    brain_notes.drain()
    yield s
    probe._SESSIONS.pop(s, None)
    brain_notes.drain()


@pytest.fixture
def spied(monkeypatch):
    """Spy on the DISPATCH to the browser owner, which is the real boundary: what is measured is that the command
    goes out, not that Chromium starts in a test."""
    sent: list[tuple] = []
    monkeypatch.setattr("nucleo.flash.procs.dispatch",
                        lambda wid, action, payload=None: sent.append((wid, action, payload or {})) or True)
    return sent


# ── open the window ─────────────────────────────────────────────────────────────────────────────────────────
def test_the_login_window_is_actually_opened(fresh_db, sid, spied, monkeypatch):
    monkeypatch.setattr("nucleo.flash.fast_client.FastClient", _CallsAuth)
    res = asyncio.run(probe.run_turn("Abre la web de Netflix y me dices cuando esté en el login.",
                                     sid=sid, ingest=False, execute=True))

    assert res["action"] == "authenticate_web"
    assert any(a == "authenticate" for _w, a, _p in spied), "no se encoló nada al owner del navegador"
    assert res.get("executed") == "authenticate_web"
    assert res.get("task"), "no se creó la tarjeta de la tarea de login"


def test_it_opens_the_site_the_operator_named(fresh_db, sid, spied, monkeypatch):
    monkeypatch.setattr("nucleo.flash.fast_client.FastClient", _CallsAuth)
    asyncio.run(probe.run_turn("Abre Netflix.", sid=sid, ingest=False, execute=True))
    urls = [p.get("url") for _w, a, p in spied if a == "authenticate"]
    assert urls and "netflix.com" in urls[0]


def test_without_execute_it_still_only_REPORTS(fresh_db, sid, spied, monkeypatch):
    """The probe remains a reporting channel by default. `execute` is what turns it into the real cycle
    (V2-049), and without it nothing can open a window on the operator's machine."""
    monkeypatch.setattr("nucleo.flash.fast_client.FastClient", _CallsAuth)
    res = asyncio.run(probe.run_turn("Abre Netflix.", sid=sid, ingest=False))
    assert res["action"] == "authenticate_web"
    assert not spied


# ── «ya he entrado» ─────────────────────────────────────────────────────────────────────────────────────────
def test_the_operator_saying_he_is_in_resumes_the_waiting_task(fresh_db, sid, spied, monkeypatch):
    from widgets.navegador import tasks as navtasks
    navtasks._tasks.clear()
    tid = navtasks.create("Iniciar sesión · netflix.com")
    navtasks.awaiting_login(tid, True) if hasattr(navtasks, "awaiting_login") else None
    if not navtasks.login_waiting_id():
        navtasks._tasks[tid]["awaiting_login"] = True

    monkeypatch.setattr("nucleo.flash.fast_client.FastClient", _SaysImIn)
    res = asyncio.run(probe.run_turn("Ya he entrado con mi cuenta. Sigue tú.",
                                     sid=sid, ingest=False, execute=True))

    assert any(a == "auth_done" for _w, a, _p in spied), "el login confirmado no llegó a la tarea"
    assert res.get("resumed") == tid
    navtasks._tasks.clear()


def test_and_saying_it_with_NOTHING_waiting_reports_that_honestly(fresh_db, sid, spied, monkeypatch):
    """An "" is the honest response to «it says it is already logged in and no login was waiting» — the same
    criterion as the expired confirmation in V2-190. Treating the turn as successful would invent that something resumed."""
    from widgets.navegador import tasks as navtasks
    navtasks._tasks.clear()
    monkeypatch.setattr("nucleo.flash.fast_client.FastClient", _SaysImIn)
    res = asyncio.run(probe.run_turn("Ya he entrado.", sid=sid, ingest=False, execute=True))

    assert res.get("executed") == "login_done"
    assert res.get("resumed") == ""
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


def test_a_music_service_does_not_open_a_browser_from_the_text_channel(fresh_db, sid, spied, monkeypatch):
    class _CallsSpotify:
        async def stream(self, *_a, on_tool_call=None, **_kw):
            if on_tool_call:
                on_tool_call("authenticate_web", {"site": "spotify"})
            yield "Te lo abro."

    monkeypatch.setattr("nucleo.flash.fast_client.FastClient", _CallsSpotify)
    res = asyncio.run(probe.run_turn("Conéctame a mi cuenta de Spotify.", sid=sid, ingest=False, execute=True))

    assert not any(a == "authenticate" for _w, a, _p in spied), "abrió un navegador para un servicio de música"
    assert res.get("authenticate_kind") == web_auth.KIND_MUSIC, "no se dijo cuál era el camino"


def test_no_site_no_guessing():
    """Bug from 2026-07-23: without a recognized site this opened wallapop.com by default — a login to a site that
    nobody requested. There is nothing to open, so nothing is opened."""
    assert web_auth.start("") == ""


def test_the_two_channels_share_ONE_body(fresh_db):
    """Guard against the divergence this repo has already paid for (V2-153: the same notification scheduled twice
    because two copies of a decision could not see each other). The voice closures must DELEGATE, not reimplement."""
    import inspect

    from voice.engine.llm.providers import nucleo as voice_nucleo
    src = inspect.getsource(voice_nucleo)
    start = src[src.index("def _start_web_auth"):]
    start = start[:start.index("\n        def ")] if "\n        def " in start else start
    assert "web_auth" in start, "la voz volvió a implementar el arranque del login por su cuenta"
    assert "procs.dispatch" not in start, "la voz despacha directamente otra vez: son dos cuerpos de nuevo"
