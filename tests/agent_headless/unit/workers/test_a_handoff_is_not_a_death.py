"""Un relevo no es una muerte (V2-238).

Un worker se queda sin cuota de proveedor y `_finish` hace lo correcto: releva. Relanza el encargo con el
siguiente escalón y se vacía la entrega a propósito, para que el operador no vea dos. Lo que hacía era dejar
`ok=False` y `status="error"` — es decir, la sesión relevada quedaba **indistinguible de un worker muerto**. Y
de ahí salían tres cosas, las tres medidas o leídas en el código:

1. El motor le empujaba al cerebro «la tarea de fondo ha MUERTO sin resultado y no se va a reintentar sola»
   (V2-222) **mientras el relevo trabajaba**. Un aviso falso, y de los caros: pide una decisión al operador
   sobre algo que ya está en marcha.
2. `_resumable` lee exactamente ese `ok=False`, así que en una gestión web disparaba ADEMÁS el auto-resume de
   V2-049: **dos escaladas para una sola muerte**, dos workers sobre el mismo encargo — y hasta V2-237 los dos
   reanudando la MISMA sesión del CLI, que es como morían a los 400 ms.
3. El arnés cuenta muertes leyendo la observabilidad, y contaba esta. En `best-plumber-same-day` y en
   `weekend-barber`, «worker 1 murió tras el relevo de proveedor» (1459 y 1445 ms) no era una muerte.

El arreglo es un HECHO nuevo, no una heurística: `rec.handoff` dice a dónde pasó el testigo, y con él la sesión
tiene su propio final —`relevada`— en vez de disfrazarse del final de al lado.
"""
import asyncio

import pytest

from nucleo.workers.session import SessionRecord, WorkerSession


class _Backend:
    name = "fake"

    async def start(self, prompt, *, spec):
        pass

    async def send(self, text):
        pass

    async def events(self):
        return
        yield  # pragma: no cover

    async def stop(self):
        pass


@pytest.fixture
def sesion(monkeypatch):
    """Sesión real con un backend de mentira, y el escalado interceptado: lo que se mide aquí es lo que `_finish`
    DEJA ESCRITO en el registro, que es lo que leen dispatch, la hoja y el panel."""
    lanzadas = []
    from nucleo.flash import escalate as _esc
    monkeypatch.setattr(_esc, "escalate_to_slowbrain",
                        lambda goal, context=None, **kw: lanzadas.append((goal, context or {})), raising=False)
    rec = SessionRecord(task_id="t1", goal="un fontanero que pueda venir hoy", kind="web")
    s = WorkerSession(_Backend(), type("S", (), {"model": "", "kind": "web"})(), rec)
    s._lanzadas = lanzadas
    return s


def _run(coro):
    return asyncio.get_event_loop_policy().new_event_loop().run_until_complete(coro)


# ── el caso medido ───────────────────────────────────────────────────────────────────────────────────────────

def test_un_relevo_de_proveedor_NO_termina_en_error(sesion):
    rec = sesion._rec
    rec.provider_down = {"provider": "z.ai", "next": "deepseek", "text": "insufficient balance"}
    _run(sesion._finish())
    assert sesion._lanzadas, "el relevo tiene que relanzar el encargo"
    assert rec.status == "relevada", "una sesión que pasó el testigo se leía igual que un worker muerto"
    assert rec.handoff and "deepseek" in rec.handoff


def test_el_relevo_dice_A_DONDE_paso_el_testigo(sesion):
    rec = sesion._rec
    rec.provider_down = {"provider": "z.ai", "next": "deepseek", "text": "insufficient balance"}
    _run(sesion._finish())
    assert "proveedor" in rec.handoff and "deepseek" in rec.handoff
    assert rec.phase == "relevada"


def test_compactar_y_continuar_tambien_es_un_relevo(sesion):
    """La otra entrega de `_finish` (V2-218): el contexto reventó, se retoma con lo aprendido. Misma verdad —el
    encargo sigue— y por tanto el mismo final."""
    rec = sesion._rec
    rec.context_full = {"text": "context window", "tokens": 138000}
    _run(sesion._finish())
    assert sesion._lanzadas
    assert rec.status == "relevada" and "contexto" in rec.handoff


# ── la otra dirección: un final de verdad SIGUE siendo un error ──────────────────────────────────────────────

def test_un_worker_que_muere_de_verdad_sigue_en_error(sesion):
    rec = sesion._rec
    rec.ok = False
    rec.result_summary = "No pude completar la tarea."
    _run(sesion._finish())
    assert rec.status == "error" and not rec.handoff
    assert rec.phase == "sin completar"


def test_un_relevo_SIN_a_donde_ir_es_una_muerte(sesion):
    """Sin escalón siguiente no hay testigo que pasar: eso sí se acabó, y el operador tiene que enterarse."""
    rec = sesion._rec
    rec.provider_down = {"provider": "z.ai", "next": "", "text": "insufficient balance"}
    _run(sesion._finish())
    assert not sesion._lanzadas
    assert rec.status == "error" and not rec.handoff
    assert "sin cuota" in rec.result_summary


def test_si_el_relanzamiento_FALLA_no_se_finge_un_relevo(sesion, monkeypatch):
    """Sensibilidad. Marcar el testigo antes de saber que alguien lo cogió convertiría una muerte silenciosa en
    una muerte silenciosa Y sin aviso: el operador se quedaría esperando a un relevo que nunca arrancó."""
    from nucleo.flash import escalate as _esc
    monkeypatch.setattr(_esc, "escalate_to_slowbrain",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no hay pool")), raising=False)
    rec = sesion._rec
    rec.provider_down = {"provider": "z.ai", "next": "deepseek", "text": "insufficient balance"}
    _run(sesion._finish())
    assert not rec.handoff and rec.status == "error"
    assert "no he podido relevarlo" in rec.result_summary


def test_una_cancelacion_no_se_convierte_en_relevo(sesion):
    rec = sesion._rec
    rec.status = "cancelled"
    rec.provider_down = {"provider": "z.ai", "next": "deepseek", "text": "x"}
    _run(sesion._finish())
    assert not sesion._lanzadas and rec.status == "cancelled" and not rec.handoff


# ── lo que leen los de fuera ─────────────────────────────────────────────────────────────────────────────────

def test_relevada_es_un_final_CLASIFICADO():
    """Si no está en la enumeración de V2-198, una sesión relevada no aparece ni viva ni acabada en el estado
    vivo, y el turno se queda con su memoria de haberla arrancado."""
    from nucleo import dispatch
    assert "relevada" in dispatch.ENDED_SESSION_STATES
    assert not (dispatch.LIVE_SESSION_STATES & dispatch.ENDED_SESSION_STATES)


def test_el_aviso_de_MUERTE_no_se_empuja_sobre_un_relevo():
    """GUARDA DE CABLEADO (V2-199): el predicado puede estar perfecto y el llamador seguir anunciando la muerte.
    Esto es lo que el operador ESCUCHA, así que es la parte que no puede quedarse sin probar."""
    import inspect

    from nucleo import dispatch
    src = inspect.getsource(dispatch._remember_ended)
    assert 'getattr(rec, "handoff", "")' in src, "el aviso de muerte de V2-222 se empuja también sobre un relevo"


def test_un_relevo_NO_dispara_ADEMAS_el_auto_resume():
    """GUARDA DE CABLEADO: dos escaladas para una muerte. `_finish` ya relanzó; si `_will_resume` sigue leyendo
    solo `ok=False`, el auto-resume de V2-049 lanza un SEGUNDO worker sobre el mismo encargo."""
    import inspect

    from nucleo import dispatch
    src = inspect.getsource(dispatch._run_session)
    assert "_handoff = str(getattr(rec, \"handoff\", \"\") or \"\")" in src
    assert "and not _handoff)" in src
    assert "_schedule_auto_resume" in src


def test_la_hoja_NO_se_cierra_cuando_el_encargo_continua():
    """La hoja es del ENCARGO, no de la sesión: cerrarla al relevar apagaría en la cara del operador la superficie
    donde está mirando, con el relevo ya trabajando (V2-227 ámbito C)."""
    import inspect

    from nucleo import dispatch
    src = inspect.getsource(dispatch._run_session)
    assert "if not _continues and surfaces.opens_sheet" in src
    assert "_continues = bool(_will_resume or _handoff)" in src


# ── y el hallazgo que salió al escribir estos tests ──────────────────────────────────────────────────────────
# Las tres ramas de `_finish` que NO son un relevo escriben un `result_summary` que anuncia un fallo, y ninguna
# tocaba `ok`, que nace en True. Con el backend muerto antes de cerrarlo, esa frase se entregaba como logro:
# «Tarea completada: Me he quedado sin cuota en el proveedor…». Visto en el log de la primera pasada de este
# fichero, no razonado.

@pytest.mark.parametrize("montaje", ["sin_relevo", "relevo_roto", "contexto_roto"])
def test_un_fallo_ANUNCIADO_no_se_entrega_como_tarea_completada(sesion, monkeypatch, montaje):
    rec = sesion._rec
    if montaje == "sin_relevo":
        rec.provider_down = {"provider": "z.ai", "next": "", "text": "insufficient balance"}
    else:
        from nucleo.flash import escalate as _esc
        monkeypatch.setattr(_esc, "escalate_to_slowbrain",
                            lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no hay pool")), raising=False)
        if montaje == "relevo_roto":
            rec.provider_down = {"provider": "z.ai", "next": "deepseek", "text": "insufficient balance"}
        else:
            rec.context_full = {"text": "context window", "tokens": 138000}
    _run(sesion._finish())
    assert rec.ok is False, "una frase que ANUNCIA un fallo salía entregada como «Tarea completada: …»"
    assert rec.status == "error"
