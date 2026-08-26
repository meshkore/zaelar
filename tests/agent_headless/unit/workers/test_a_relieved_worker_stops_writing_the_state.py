"""El worker relevado seguía escribiendo en el estado de su relevo (V2-350).

Medido en vivo el 2026-08-26, `search-buy-used-car`. El worker escribió estos pasos, que llegaron enteros al
prompt del turno y de ahí al informe del juez:

    51,5 s  «Selección final lista (7 coches con año/km verificados); el motor devuelve 403 al widget
             results, reintentando»
    72,0 s  «Motor sigue devolviendo 403 al widget; primera versión (10 coches) sí se publicó»
    97,8 s  «Sin poder actualizar el widget: motor con 403 persistente»

Dos cosas mal a la vez, y la segunda es la que no se veía:

1. Un worker con SIETE coches verificados no pudo publicarlos. El 403 sale de `/api/worker/act`, que verifica
   `task_id`+token. El token vive EN el SessionRecord, así que para que no case tiene que haber un registro
   NUEVO con el mismo `task_id`: un relevo. El viejo seguía vivo y ya no era el dueño.
2. Y sin embargo SÍ escribía. `/api/agent/report` —fase, progreso, plan, amplitud— solo miraba el `tid`, nunca
   el token, así que las notas del fantasma se escribían en el registro de su relevo. Por eso la traza tenía
   una línea imposible: el worker nuevo «arrancando — lleva 18 s» a los 36,8 s, y a los 51,5 s una «selección
   final lista». No es un worker rápido: son dos escribiendo en el mismo sitio.

Las dos puertas del motor le contestaban cosas OPUESTAS al mismo worker, y en el peor orden posible: no podía
ENTREGAR y sí podía CONTAMINAR. El juez leyó «el motor devuelve 403 al widget» como un hecho de esa ronda y lo
puso de bloqueador nº1 — un instrumento que se cree las notas de un fantasma no mide.

UN TOKEN AUSENTE NO ES UN TOKEN EQUIVOCADO, y esa distinción es todo el diseño: sin token se sigue como
siempre (un worker que arrancó antes del cambio no puede quedarse mudo por una cabecera que nadie le enseñó a
mandar); lo que se corta es el que NO CASA, que es la única señal inequívoca de que quien escribe ya no es el
dueño. Y no se tira nada: lo del huérfano se emite marcado, y se le RESPONDE que lo es — el 403 anterior decía
«task/token no válido» a secas y el worker se pasó 45 s reintentando, convencido de que el fallo era del motor.
"""
import pytest

from nucleo import agent_api, dispatch


def _client():
    """Por HTTP y no llamando a la función: los `Body(...)` de FastAPI solo se resuelven en la ruta real, y esa
    es justo la que usa el worker."""
    from fastapi import FastAPI
    from starlette.testclient import TestClient
    app = FastAPI()
    app.include_router(agent_api.router)
    return TestClient(app)


@pytest.fixture(autouse=True)
def _clean():
    dispatch._SESSIONS.clear()
    yield
    dispatch._SESSIONS.clear()


def _rec(tid="w1"):
    r = dispatch.SessionRecord(task_id=tid, goal="Busca un coche de segunda mano diésel", kind="generic")
    r.status = "running"
    dispatch._SESSIONS[tid] = r
    return r


def test_el_dueño_actual_escribe_como_siempre():
    r = _rec()
    assert agent_api._is_orphan("w1", dispatch.rec_token(r)) is False


def test_el_relevado_NO_es_el_dueño():
    """El caso medido: mismo task_id, registro nuevo, token viejo en la mano del que sigue vivo."""
    viejo = dispatch.rec_token(_rec())
    dispatch._SESSIONS.clear()
    nuevo = dispatch.rec_token(_rec())          # el relevo reusa el id y estrena token
    assert nuevo != viejo
    assert agent_api._is_orphan("w1", viejo) is True


def test_un_token_AUSENTE_no_es_un_token_equivocado():
    """Fail-open a propósito: un worker de antes del cambio, o un puente viejo, no manda token y no puede
    quedarse mudo por eso. Lo que delata al huérfano es el token que NO CASA, no su ausencia."""
    _rec()
    assert agent_api._is_orphan("w1", "") is False
    assert agent_api._is_orphan("w1", "   ") is False


def test_sin_registro_no_hay_estado_que_corromper():
    """Sin `SessionRecord` no se marca huérfano: `session_progress` y compañía ya salen de vacío, y marcarlo
    aquí solo serviría para esconder la nota de un worker cuyo encargo se cerró limpiamente."""
    assert agent_api._is_orphan("no-existe", "cualquier-cosa") is False


def test_el_puente_MANDA_el_token_que_ya_tenia_en_el_entorno(monkeypatch):
    """Guarda de cableado: la comprobación sin quien la alimente es el arreglo que no existe. `ZAELAR_TASK_TOKEN`
    ya viajaba en el entorno del worker (lo usa `mem_cli`); esta puerta era la única que no lo miraba."""
    from nucleo import agent_report
    enviado = {}
    monkeypatch.setenv("ZAELAR_TASK_ID", "w1")
    monkeypatch.setenv("ZAELAR_TASK_TOKEN", "tok-abc")
    monkeypatch.setattr(agent_report.urllib.request, "urlopen", lambda *a, **k: None)
    monkeypatch.setattr(agent_report.urllib.request, "Request",
                        lambda url, data=b"", headers=None, method="": enviado.update(
                            __import__("json").loads(data.decode("utf-8"))) or object())
    agent_report._post({"phase": "entrando en coches.net"})
    assert enviado.get("token") == "tok-abc", "sin el token, la comprobación del endpoint no puede disparar nunca"
    assert enviado.get("tid") == "w1"


def test_el_endpoint_lee_el_token_del_cuerpo():
    """Guarda de firma: si el parámetro se cae, FastAPI lo ignora en silencio y todo vuelve a fail-open."""
    import inspect
    assert "token" in inspect.signature(agent_api.agent_report).parameters


def test_la_respuesta_al_huerfano_le_dice_QUE_hacer():
    """Un error que no nombra la causa manda a reintentar lo mismo — es lo que pasó con «task/token no válido»
    a secas: 45 s de reintentos y siete coches que nunca salieron de su cabeza."""
    viejo = dispatch.rec_token(_rec())
    dispatch._SESSIONS.clear()
    _rec()
    out = _client().post("/api/agent/report",
                         json={"tid": "w1", "token": viejo, "phase": "publicando la selección final"}).json()
    assert out.get("orphan") is True
    assert "relevado" in out["error"] and "NO reintentes" in out["error"]


def test_el_huerfano_no_pisa_el_estado_del_relevo():
    """El daño medido, reproducido: el fantasma escribía «selección final lista» en el registro del que acababa
    de nacer, y eso llegaba al prompt del turno como si fuera de este encargo."""
    viejo = dispatch.rec_token(_rec())
    dispatch._SESSIONS.clear()
    nuevo = _rec()
    nuevo.note = "arrancando"
    _client().post("/api/agent/report",
                   json={"tid": "w1", "token": viejo, "phase": "publicando",
                         "progress": "Selección final lista (7 coches con año/km verificados)"})
    assert nuevo.note == "arrancando", "la nota del huérfano se escribió en el estado de su relevo"
    assert (nuevo.phase or "") != "publicando"


def test_el_dueño_SI_pisa_su_propio_estado():
    """El lado contrario, y el que importa: la guarda no puede dejar mudo al worker legítimo."""
    r = _rec()
    _client().post("/api/agent/report",
                   json={"tid": "w1", "token": dispatch.rec_token(r),
                         "progress": "9 candidatos leídos del listado"})
    assert "9 candidatos" in (r.note or "")
