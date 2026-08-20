"""Tres workers reanudando la MISMA sesión del CLI, y los tres muertos a los 400 ms (V2-237).

Medido por el arnés el 2026-08-21 en `best-plumber-same-day` (1/5, mecanismo 2, **cero filas extraídas**), con
una correlación que no deja lugar a la duda:

    worker 3  «REANUDA sesión nativa c5ad1d9e-ad0…»  → ERROR a los 371 ms
    worker 4  «REANUDA sesión nativa c5ad1d9e-ad0…»  → ERROR a los 401 ms   ← LA MISMA
    worker 6  «REANUDA sesión nativa c5ad1d9e-ad0…»  → ERROR a los 374 ms   ← LA MISMA
    workers 2 y 5, sesión NUEVA, sin reanudar        → vivos

**3 de 3 contra 0 de 3.** Su traza entera son cinco eventos en 400 ms: alive → widget show → task start
(«Buscando en la web…») → task end. Una búsqueda web no dura 400 ms: murieron en el arranque, antes de hacer
nada, y el caso se quedó sin una sola extracción.

La causa: `_find_resume` LEÍA la entrada y no la consumía, así que cada escalada de la misma petición —incluidas
las que dispara el auto-resume de V2-049— recibía el MISMO `native_sid`. Una sesión del CLI no se puede reanudar
dos veces a la vez.

Consumirla es seguro porque el ciclo de vida ya la devuelve: al cerrar una gestión web incompleta, `_run_session`
reescribe la entrada con el `native_sid` actual. Y si el worker muere antes de llegar ahí, la reanudación se
pierde y el siguiente encargo empieza de cero — estrictamente mejor que morir en 400 ms.
"""
import time

import pytest

from nucleo import dispatch

PETICION = "busca un fontanero que pueda venir hoy a arreglar una fuga en Madrid"
OTRA = "reserva mesa para dos esta noche en un restaurante de Sevilla"


@pytest.fixture(autouse=True)
def _registro_aislado(monkeypatch):
    monkeypatch.setattr(dispatch, "_WEB_RESUME", {}, raising=False)
    monkeypatch.setattr(dispatch, "_resume_persist", lambda: None, raising=False)
    yield


def _sembrar(req=PETICION, sid="c5ad1d9e-ad0"):
    dispatch._WEB_RESUME[dispatch._goal_key(req)] = {
        "nav_task": "t9", "native_sid": sid, "ts": time.time(), "count": 1, "goal": req[:200]}


# ── el caso medido ───────────────────────────────────────────────────────────────────────────────────────────

def test_solo_el_PRIMERO_se_lleva_la_sesion_nativa():
    _sembrar()
    primero = dispatch._find_resume(PETICION, take=True)
    segundo = dispatch._find_resume(PETICION, take=True)
    tercero = dispatch._find_resume(PETICION, take=True)
    assert primero and primero["native_sid"] == "c5ad1d9e-ad0"
    assert segundo is None, "el segundo worker reanudaba la misma sesión del CLI y moría en el arranque"
    assert tercero is None


def test_sin_reanudacion_el_encargo_ARRANCA_de_cero():
    """Lo que hacen los dos que sobrevivieron: sesión propia. Perder la continuidad es peor que perder el worker,
    pero mucho mejor que perderlo A ÉL y la continuidad."""
    _sembrar()
    dispatch._find_resume(PETICION, take=True)
    assert dispatch._find_resume(PETICION, take=True) is None


# ── la otra dirección: consumir no puede romper la continuidad de V2-049 ─────────────────────────────────────

def test_la_entrada_VUELVE_al_cerrar_una_gestion_incompleta():
    """GUARDA DE CABLEADO: sin la reescritura de `_run_session`, consumir la entrada convertiría el auto-resume en
    un solo intento y la continuidad web de V2-049 moriría en silencio."""
    import inspect
    src = inspect.getsource(dispatch._run_session)
    assert "_WEB_RESUME[gk] = {" in src
    assert "native_sid" in src


def test_leerla_SIN_tomarla_sigue_siendo_posible():
    """`take` es explícito a propósito: quien solo quiera mirar si hay algo que reanudar no debe llevárselo."""
    _sembrar()
    assert dispatch._find_resume(PETICION) is not None
    assert dispatch._find_resume(PETICION) is not None, "una lectura no puede consumir"


def test_una_peticion_DISTINTA_no_se_lleva_la_reanudacion_de_otra():
    _sembrar()
    assert dispatch._find_resume(OTRA, take=True) is None
    assert dispatch._find_resume(PETICION, take=True) is not None


def test_una_entrada_caducada_no_se_entrega():
    dispatch._WEB_RESUME[dispatch._goal_key(PETICION)] = {
        "nav_task": "t9", "native_sid": "viejo", "ts": time.time() - dispatch._RESUME_TTL - 10, "count": 1}
    assert dispatch._find_resume(PETICION, take=True) is None


def test_el_listener_la_TOMA_y_no_solo_la_lee():
    """El defecto no era el predicado sino su llamador. Sin `take=True` en `run_listener`, esto sigue exactamente
    igual de roto y los tests de arriba pasan — la lección de V2-199."""
    import inspect
    src = inspect.getsource(dispatch.run_listener)
    assert "_find_resume(request, take=True)" in src


# ── el otro hallazgo de la misma ronda: un final sin causa ───────────────────────────────────────────────────
# «Un worker que muere no deja ni un evento diciendo por qué»: `task|end` venía con `text:""` y el modelo, y
# nada más. Los únicos eventos de error de la ronda eran del worker que NO murió, así que la causa de los
# cuatro muertos solo se veía cruzando el log del motor por `span=worker:N`. Un final sin causa se lee igual
# que un final normal.

def test_la_fila_del_final_LLEVA_el_motivo_y_el_estado():
    """GUARDA DE FUENTE: la construcción vive dentro de `_finish`, que necesita un backend vivo para llegar hasta
    ahí. Lo que se puede comprobar sin uno es que el motivo y el estado se meten en la fila — y eso es justo lo
    que una regresión desharía sin fallar con ruido, dejando otra vez `text:""` sobre un worker muerto."""
    import inspect

    from nucleo.workers import session as _s
    src = inspect.getsource(_s.WorkerSession._finish)
    assert 'extra["status"] = str(rec.status or "")' in src
    assert "if not rec.ok:" in src and "rec.result_summary" in src
