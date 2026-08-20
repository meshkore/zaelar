"""El traspaso de INICIO DE SESIÓN tiene que OCURRIR en el canal de texto, no solo nombrarse (V2-176).

Medido en `cancel-subscription-before-charge__es` (2026-08-20 10:26). El diálogo era excelente y honesto —
`naturalidad 5`, `adaptacion 5`: se negó a fingir que tenía la cuenta del operador y ofreció el traspaso — y
luego:

    TESTER  Vale, abre la web de Netflix y me dices cuando esté en el login.
    ZAELAR  Aquí lo tienes.
    TESTER  Ya he entrado con mi cuenta. Sigue tú, porfa, que no quiero tocar nada más.
    ZAELAR  Vale, dame un momento que lo miro.

con `navegador_task` VACÍO. `authenticate_web` y `login_done` se resolvían en `probe.py` a una ETIQUETA y nada
más: la voz llamaba a sus dos closures y este canal —el que usan los casos de uso— no ejecutaba nada. No se
abrió ninguna ventana, así que «ya he entrado» no tenía tarea que reanudar y «lo miro» no tenía nada que mirar.
El juez lo llamó «una fachada vacía»; las palabras eran ciertas y lo que faltaba era el cableado.

Es el MISMO agujero que el bloque de cron de `probe.py` ya tenía documentado con estas palabras: «el bloque de
ejecución solo cubría worker + data-op. El canal `probe` es el que usan los casos de uso, así que el aviso NO
PODÍA existir en una corrida por muy bien que el modelo emitiera la tag». Los 54 escenarios del segmento
`credentials` pasan por este traspaso.
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
    """Stub: el modelo pide el login de Netflix, como en la corrida medida."""

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
    """Se espía el DESPACHO al owner del navegador, que es la frontera real: lo que se mide es que la orden
    salga, no que un Chromium arranque en un test."""
    sent: list[tuple] = []
    monkeypatch.setattr("nucleo.flash.procs.dispatch",
                        lambda wid, action, payload=None: sent.append((wid, action, payload or {})) or True)
    return sent


# ── abrir la ventana ────────────────────────────────────────────────────────────────────────────────────────
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
    """El probe sigue siendo un canal que reporta por defecto. `execute` es lo que lo convierte en el ciclo real
    (V2-049), y sin él nada puede abrir una ventana en la máquina del operador."""
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
    """Un "" es la respuesta honesta a «dice que ya entró y no había ningún login esperando» — mismo criterio que
    la confirmación caducada de V2-190. Dar el turno por bueno sería inventar que algo se reanudó."""
    from widgets.navegador import tasks as navtasks
    navtasks._tasks.clear()
    monkeypatch.setattr("nucleo.flash.fast_client.FastClient", _SaysImIn)
    res = asyncio.run(probe.run_turn("Ya he entrado.", sid=sid, ingest=False, execute=True))

    assert res.get("executed") == "login_done"
    assert res.get("resumed") == ""
    assert not any(a == "auth_done" for _w, a, _p in spied)


# ── la decisión compartida ──────────────────────────────────────────────────────────────────────────────────
# Sin esta guarda, cablear el canal de texto habría roto DOS invariantes en su primer turno: un servicio de
# música se conecta en la tarjeta de `musica` y la mensajería por QR dentro de `mensajeria`, nunca conduciendo un
# Chromium a spotify.com. La cadena vivía SOLO dentro del provider de voz.
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
    """Bug de 2026-07-23: sin sitio reconocido esto abría wallapop.com por defecto — un login a un sitio que
    nadie pidió. No hay nada que abrir, así que no se abre nada."""
    assert web_auth.start("") == ""


def test_the_two_channels_share_ONE_body(fresh_db):
    """Guarda contra la divergencia que este repo ya pagó (V2-153: el mismo aviso programado dos veces porque dos
    copias de una decisión no se veían). Las closures de la voz tienen que DELEGAR, no reimplementar."""
    import inspect

    from voice.engine.llm.providers import nucleo as voice_nucleo
    src = inspect.getsource(voice_nucleo)
    start = src[src.index("def _start_web_auth"):]
    start = start[:start.index("\n        def ")] if "\n        def " in start else start
    assert "web_auth" in start, "la voz volvió a implementar el arranque del login por su cuenta"
    assert "procs.dispatch" not in start, "la voz despacha directamente otra vez: son dos cuerpos de nuevo"
