"""
CORRELATION ID + identidad + sesión (2026-08-09).

Lo que se prueba es el contrato que hace ANALIZABLE la observabilidad: que un estímulo del operador y todo lo que
desencadena compartan un mismo identificador de flujo, que cada evento diga de qué instalación y de qué sesión de
trabajo salió, y que eso sea CONSULTABLE por columnas indexadas en vez de escaneando JSON.

El caso de referencia es el que puso el operador: «enséñame el tiempo en Soria» → decisión del FlashBrain →
búsqueda web → apertura del widget. Cuatro eventos, cuatro piezas, UN flujo.
"""
from __future__ import annotations

import time

import pytest


@pytest.fixture()
def wired(tmp_path, monkeypatch):
    """Una BD limpia por test + el sink del bus enganchado. `ZAELAR_DB` es el mismo knob de aislamiento que ya
    usan los tests de memoria: nunca se escribe en la base real del operador."""
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "t.db"))
    monkeypatch.setenv("ZAELAR_WORKSPACE", str(tmp_path))
    import bus
    from bus import log as _log

    _log._conn = None
    _log.detach(bus)
    _log.attach(bus)

    from observability import identity as _ident
    _ident._user["id"] = None
    _ident._session["id"] = None
    yield _log
    _log.detach(bus)
    _log._conn = None


def _settle():
    time.sleep(0.25)      # el sink del bus escribe en el hilo que publica; damos margen a la entrega cross-loop


def test_a_whole_flow_shares_one_correlation_id(wired):
    from observability import flows, identity
    from voice import trace
    from voice.observer import emit

    identity.begin_session("test")
    tid = trace.begin("enséñame el tiempo en Soria")
    emit("brain", "decide", extra={"brain_ms": 420, "model": "deepseek-v4-flash",
                                   "prompt_tokens": 4700, "completion_tokens": 120})
    emit("search", "web_search «tiempo Soria»")
    emit("widget", "show", extra={"id": "meteo-soria", "src": "flash"})
    _settle()

    got = flows.flows(limit=5)
    assert got, "no se registró ningún flujo"
    f = got[0]
    assert f["corr_id"] == tid
    assert f["events"] == 4, "el evento raíz + los tres derivados deben caer en el MISMO flujo"
    assert set((f["families"] or "").split(",")) == {"flash", "widget"}
    assert f["tokens_in"] == 4700 and f["tokens_out"] == 120
    assert f["errors"] == 0

    detail = flows.flow(tid)
    assert [e["kind"] for e in detail] == ["trace", "brain", "search", "widget"], "orden cronológico del flujo"
    assert detail[1]["ms"] == 420.0, "la duración real sube del payload a su columna"


def test_a_new_request_is_a_new_flow(wired):
    """Una petición nueva del operador —aunque MODIFIQUE el resultado anterior— abre su propio flujo: es lo que
    permite comparar «la primera búsqueda» con «la corrección» en vez de verlas como una masa."""
    from observability import flows
    from voice import trace
    from voice.observer import emit

    t1 = trace.begin("busca vuelos a Roma")
    emit("brain", "busca")
    t2 = trace.begin("no, mejor a Lisboa")
    emit("brain", "busca")
    _settle()

    assert t1 != t2
    ids = {f["corr_id"] for f in flows.flows(limit=5)}
    assert {t1, t2} <= ids


def test_every_event_carries_installation_and_session(wired):
    from observability import flows, identity
    from voice.observer import emit

    identity.begin_session("test")
    emit("brain", "hola")
    _settle()

    s = flows.stats()
    assert s["events"] >= 1
    assert s["with_user"] == s["events"], "un evento sin instalación no se puede atribuir nunca después"
    assert s["with_session"] == s["events"], "ni sin sesión de trabajo"


def test_local_user_id_is_a_random_uuid_and_persists(wired, tmp_path):
    """UUID4 aleatorio y no correlativo: no identifica a nadie por sí mismo y no puede chocar con el de otra
    instalación."""
    import uuid

    from observability import identity

    uid = identity.user_id()
    uuid.UUID(uid)                                   # lanza si no es un UUID válido
    assert uuid.UUID(uid).version == 4
    identity._user["id"] = None                      # simula un reinicio del proceso
    assert identity.user_id() == uid, "la identidad de la instalación debe sobrevivir al reinicio"


def test_an_environment_provided_user_id_wins(wired, monkeypatch):
    from observability import identity

    monkeypatch.setenv("ZAELAR_USER_ID", "acct_42")
    identity._user["id"] = None
    assert identity.user_id() == "acct_42"


def test_reconnecting_does_not_split_the_work_session(wired):
    """Un `start` repetido (reconexión, reset ligero) REUTILIZA la sesión: partirla en dos falsearía cualquier
    medida de «cuánto duró la sesión y qué hizo»."""
    from observability import identity

    a = identity.begin_session("voice")["id"]
    b = identity.begin_session("voice")["id"]
    assert a == b

    identity.end_session("power_off")
    c = identity.begin_session("voice")["id"]
    assert c != a, "tras cerrarla de verdad, arrancar el agente abre una sesión NUEVA"


def test_hand_published_events_are_stamped_too(wired):
    """`observer.emit` NO es la única puerta: el latido del loop y el puente de `memory.updated` construyen su
    dict a mano y lo publican directos al topic. Se saltaban el sello —50 de 66 filas del primer arranque real
    salieron sin sesión— y un evento sin sesión ya no se puede atribuir después. El sello vive en
    `bus/sse.py::publish`, que sí es la puerta única."""
    from bus import sse as _sse
    from observability import identity

    identity.begin_session("test")
    ev = {"kind": "memory", "label": "updated"}     # dict construido a mano, como el puente de memory.updated
    _sse.publish(ev)
    # Se comprueba sobre el evento PUBLICADO, no sobre la fila: el sello ocurre al publicar, y así el test no
    # depende de si ese kind concreto llega a persistirse (el latido, por ejemplo, se descarta a propósito).
    assert ev["sid"] == identity.session_id()
    assert ev["uid"] == identity.user_id()
