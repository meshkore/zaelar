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
    assert ev["cat"] == "memory", "la familia también se deriva: sin ella la fila cae en «Sin clasificar»"


# ── LA EVIDENCIA: qué trajo el mundo exterior (2026-08-10) ────────────────────────────────────────────────────
# Hasta hoy se registraba la PREGUNTA y la DECISIÓN, no la PRUEBA: de una búsqueda quedaba «7 resultados» y se
# perdía lo que el modelo leyó de verdad. Con eso se puede auditar que el sistema BUSCÓ, nunca si buscó BIEN — la
# pregunta que importa («¿los resultados sostienen lo que respondió?») era inverificable a posteriori.
def test_the_evidence_of_a_search_is_kept_with_its_sources():
    from observability import evidence

    ev = evidence.web_results([
        {"title": "El Tiempo: Soria", "url": "https://www.aemet.es/x", "snippet": "31 grados"},
        {"title": "Meteored", "url": "https://www.tiempo.com/soria.htm", "snippet": "máxima 37"},
    ])
    assert [i["u"] for i in ev["items"]] == ["https://www.aemet.es/x", "https://www.tiempo.com/soria.htm"], \
        "la URL es lo que permite VOLVER a la fuente y comprobar: nunca se recorta fuera"
    assert ev["omitted"] == 0


def test_the_evidence_has_a_budget_and_says_what_it_left_out():
    """Sin tope, una búsqueda con snippets largos pesaría más que el resto del turno junto. Y un recorte SILENCIOSO
    sería peor que el recorte: quien audita creería que eso era todo lo que había."""
    from observability import evidence

    many = [{"title": f"r{i}", "url": f"https://e/{i}", "snippet": "x" * 400} for i in range(30)]
    ev = evidence.web_results(many)
    assert len(ev["items"]) <= evidence.MAX_ITEMS
    assert ev["omitted"] == 30 - len(ev["items"]) > 0
    assert all(len(i["s"]) <= evidence.MAX_SNIPPET for i in ev["items"])
    assert sum(len(i["t"]) + len(i["u"]) + len(i.get("s", "")) for i in ev["items"]) <= evidence.TOTAL


def test_clipping_marks_the_cut():
    from observability import evidence

    assert evidence.clip("abcdefghij", 5).endswith("…"), "un texto recortado tiene que PARECER recortado"
    assert evidence.clip("abc", 50) == "abc"
    assert evidence.clip(None, 10) == ""            # best-effort: la evidencia nunca puede tumbar al emisor


def test_a_worker_tool_result_is_recorded(wired):
    """Los `tool_result` del stream del CLI se descartaban como «ruido interno», y con ellos lo único que permite
    auditar a un worker: se veía qué pidió, nunca qué le contestaron. Un worker que trae basura y otro que trae el
    dato exacto dejaban EL MISMO rastro."""
    from observability import flows
    from voice.observer import emit

    emit("task", "web ↩", text="Tour 2026: ganó Vingegaard", extra={"id": "7", "evidence": True,
                                                                    "span": "worker:7"})
    _settle()
    # Se busca EL EVENTO PROPIO, no «el último de la tabla». `rows[-1]` ataba esta prueba a que nadie más
    # emitiera un `task` después, y el almacén es COMPARTIDO: el 2026-08-25 falló una vez en la corrida
    # completa y pasó sola y al repetir la suite. Un test que depende del orden en que corren los demás no
    # mide lo que dice medir, y su rojo no distingue una regresión de una coincidencia.
    rows = [e for e in flows.events(limit=50) if e["kind"] == "task"]
    assert rows, "el resultado de una tool tiene que quedar registrado"
    mio = [e for e in rows if e.get("span") == "worker:7"]
    assert mio, "…y atribuido a SU actor, o no se puede agrupar por quién lo hizo"


# ── LEER UNA SESIÓN: resumen, cursor y por qué NO una ventana de tiempo ───────────────────────────────────────
def test_one_session_can_be_opened_and_summarised(wired):
    from observability import flows, identity
    from voice import trace
    from voice.observer import emit

    sid = identity.begin_session("test")["id"]
    trace.begin("ponme el tiempo")
    emit("brain", "decide", extra={"brain_ms": 100, "prompt_tokens": 500, "completion_tokens": 20})
    _settle()

    s = flows.session(sid)
    assert s and s["events"] >= 2 and s["flows"] >= 1
    assert s["tokens_in"] == 500
    assert flows.session("no-existe") == {}, "una sesión que no existe devuelve vacío, no una sesión fingida"


def test_the_cursor_never_repeats_nor_skips_an_event(wired):
    """`since_id` sobre una clave monótona, no una ventana de tiempo: dos eventos en el MISMO milisegundo son un
    caso normal (el bus reparte rápido), y una ventana temporal los duplicaría o se comería uno."""
    from observability import flows, identity
    from voice.observer import emit

    identity.begin_session("test")
    for i in range(5):
        emit("brain", f"e{i}")
    _settle()

    first = flows.events(limit=2)
    assert len(first) == 2
    nxt = flows.events(since_id=first[-1]["id"], limit=10)
    assert nxt and all(e["id"] > first[-1]["id"] for e in nxt), "nada anterior al cursor puede volver a salir"
    ids = [e["id"] for e in first + nxt]
    assert ids == sorted(ids) and len(ids) == len(set(ids)), "ni se repite ni se desordena"


def test_raw_events_carry_the_payload_untouched(wired):
    """Quien audita necesita el original, no nuestra proyección: la evidencia y todo lo que no sube a columnas
    viven en el payload."""
    import json

    from observability import flows, identity
    from voice.observer import emit

    identity.begin_session("test")
    emit("search", "🔎 resultados web", text="tiempo soria",
         extra={"evidence": {"items": [{"t": "AEMET", "u": "https://aemet.es"}], "omitted": 0}})
    _settle()
    row = [e for e in flows.events(limit=50) if e["kind"] == "search"][-1]
    payload = json.loads(row["payload"])
    assert payload["evidence"]["items"][0]["u"] == "https://aemet.es"


# ── EL CANDADO: quién puede leer el CONTENIDO ────────────────────────────────────────────────────────────────
# Estas rutas nacieron para el visor local y eran abiertas. En casa da igual; el MISMO código corre en
# despliegues donde el puerto es alcanzable, y ahí «abierto» significa que quien dé con la URL se lleva las
# conversaciones.
class _Req:
    def __init__(self, host="1.2.3.4", token=None):
        self.client = type("C", (), {"host": host})()
        self.headers = {"x-observability-token": token} if token else {}


def test_without_a_token_the_content_is_loopback_only(monkeypatch):
    from observability import api

    monkeypatch.delenv("ZAELAR_OBS_TOKEN", raising=False)
    assert api._allowed(_Req(host="127.0.0.1"))
    assert not api._allowed(_Req(host="203.0.113.9")), "sin token, desde fuera NO se lee el contenido"


def test_with_a_token_it_must_match(monkeypatch):
    from observability import api

    monkeypatch.setenv("ZAELAR_OBS_TOKEN", "s3cr3t")
    assert api._allowed(_Req(host="203.0.113.9", token="s3cr3t")), "con el token correcto se puede operar en remoto"
    assert not api._allowed(_Req(host="203.0.113.9", token="otro"))
    assert not api._allowed(_Req(host="127.0.0.1")), (
        "con token configurado, ni loopback pasa sin él: si no, un proceso local cualquiera de la máquina "
        "seguiría teniendo acceso libre al contenido")


def test_a_request_without_a_known_origin_is_denied(monkeypatch):
    """Fail-closed: si no se puede saber de dónde viene, no se sirve."""
    from observability import api

    monkeypatch.delenv("ZAELAR_OBS_TOKEN", raising=False)
    r = _Req()
    r.client = None
    assert not api._allowed(r)
