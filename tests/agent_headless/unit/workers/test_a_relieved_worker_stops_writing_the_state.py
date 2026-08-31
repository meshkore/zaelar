"""The relieved worker kept writing to the state of its replacement (V2-350).

Observed live on 2026-08-26, `search-buy-used-car`. The worker wrote these steps, which reached the turn
prompt intact and from there the judge's report:

    51,5 s  «Selección final lista (7 coches con año/km verificados); el motor devuelve 403 al widget
             results, reintentando»
    72,0 s  «Motor sigue devolviendo 403 al widget; primera versión (10 coches) sí se publicó»
    97,8 s  «Sin poder actualizar el widget: motor con 403 persistente»

Two things were wrong at once, and the second was the one that was not visible:

1. A worker with SEVEN verified cars could not publish them. The 403 came from `/api/worker/act`, which verifies
   `task_id`+token. The token lives IN the SessionRecord, so for it not to match there must be a NEW record
   with the same `task_id`: a replacement. The old one was still alive and was no longer the owner.
2. And yet it DID write. `/api/agent/report` —phase, progress, plan, breadth— only looked at the `tid`, never
   the token, so the ghost's notes were written to its replacement's record. That is why the trace had
   an impossible line: the new worker «starting — 18 s in» at 36.8 s, and at 51.5 s a «final selection
   ready». It is not a fast worker: there are two writing in the same place.

The engine's two gates answered the same worker with OPPOSITE things, and in the worst possible order: it could not
DELIVER but it could CONTAMINATE. The judge read «the engine returns 403 to the widget» as a fact of that round and
made it blocker no. 1 — an instrument that believes a ghost's notes does not measure.

AN ABSENT TOKEN IS NOT A WRONG TOKEN, and that distinction is the whole design: without a token, proceed as
always (a worker that started before the change cannot be silenced by a header nobody taught it to
send); what gets cut off is the one that DOES NOT MATCH, which is the only unambiguous signal that whoever writes is no longer the
owner. And nothing is discarded: the orphan's output is emitted marked, and it is ANSWERED that it is one — the previous 403 said
«invalid task/token» without further explanation and the worker spent 45 s retrying, convinced that the failure was in the engine.
"""
import pytest

from nucleo import agent_api, dispatch


def _client():
    """Through HTTP rather than by calling the function: FastAPI's `Body(...)` values are resolved only on the real
    route, which is exactly the one the worker uses."""
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
    """The observed case: same task_id, new record, old token held by the one that is still alive."""
    viejo = dispatch.rec_token(_rec())
    dispatch._SESSIONS.clear()
    nuevo = dispatch.rec_token(_rec())          # the replacement reuses the ID and gets a fresh token
    assert nuevo != viejo
    assert agent_api._is_orphan("w1", viejo) is True


def test_un_token_AUSENTE_no_es_un_token_equivocado():
    """Fail-open deliberately: a worker from before the change, or an old bridge, sends no token and cannot
    be silenced because of that. What identifies the orphan is the token that DOES NOT MATCH, not its absence."""
    _rec()
    assert agent_api._is_orphan("w1", "") is False
    assert agent_api._is_orphan("w1", "   ") is False


def test_sin_registro_no_hay_estado_que_corromper():
    """Without a `SessionRecord`, it is not marked as an orphan: `session_progress` and the like already return empty,
    and marking it here would only hide the note from a worker whose assignment closed cleanly."""
    assert agent_api._is_orphan("no-existe", "cualquier-cosa") is False


def test_el_puente_MANDA_el_token_que_ya_tenia_en_el_entorno(monkeypatch):
    """Wiring guard: a check without anything feeding it is a fix that does not exist. `ZAELAR_TASK_TOKEN`
    was already present in the worker's environment (it is used by `mem_cli`); this gate was the only one that did not inspect it."""
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
    """Signature guard: if the parameter disappears, FastAPI silently ignores it and everything becomes fail-open again."""
    import inspect
    assert "token" in inspect.signature(agent_api.agent_report).parameters


def test_la_respuesta_al_huerfano_le_dice_QUE_hacer():
    """An error that does not name the cause tells it to retry the same thing — that is what happened with «invalid task/token»
    without further explanation: 45 s of retries and seven cars that never left its head."""
    viejo = dispatch.rec_token(_rec())
    dispatch._SESSIONS.clear()
    _rec()
    out = _client().post("/api/agent/report",
                         json={"tid": "w1", "token": viejo, "phase": "publicando la selección final"}).json()
    assert out.get("orphan") is True
    assert "relevado" in out["error"] and "NO reintentes" in out["error"]


def test_el_huerfano_no_pisa_el_estado_del_relevo():
    """The measured damage, reproduced: the ghost wrote «final selection ready» to the record that had just
    been created, and it reached the turn prompt as if it belonged to this assignment."""
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
    """The opposite side, and the one that matters: the guard cannot silence the legitimate worker."""
    r = _rec()
    _client().post("/api/agent/report",
                   json={"tid": "w1", "token": dispatch.rec_token(r),
                         "progress": "9 candidatos leídos del listado"})
    assert "9 candidatos" in (r.note or "")
