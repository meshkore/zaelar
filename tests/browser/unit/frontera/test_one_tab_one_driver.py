"""Una pestaña, un conductor — medido EN VIVO el 2026-08-21 (`search-secondhand-monitor`, plató del arnés).

Tres workers del mismo encargo recibieron cada uno la MISMA tarea de navegador (`t6`) y la condujeron a la vez:
46, 27 y 7 acciones entrelazadas sobre una sola página. La traza, verbatim:

    15:43:43  worker:1  navigate → es.wallapop.com
    15:43:57  worker:2  navigate → es.wallapop.com          ← pisa al 1
    15:44:05  worker:1  type «monitor 27 pulgadas»
    15:44:43  worker:1  click [29]
    15:44:49  worker:2  click [29]                          ← misma ref, página ya cambiada por el otro

Lo de los clics es el daño de verdad, y V2-248 ya lo dejó escrito: las referencias de elemento se REPARTEN al
mirar, así que el mismo número es otro elemento en cuanto la página cambia. `worker:2` pulsó el «29» de un
vistazo que `worker:1` acababa de invalidar. En una página con botón de pagar eso no es un resultado sucio: es
una ACCIÓN equivocada, y por eso esto se trata como contención y no como higiene.

LA CAUSA es que hay DOS jueces de parecido y se contradicen sobre el MISMO par de textos:

    dispatch.find_duplicate      Jaccard ≥ 0.60 sobre palabras de ≥4 letras   → «encargos distintos»  → 3 workers
    navegador.tasks._similar     ≥2 raíces compartidas O Jaccard ≥ 0.40       → «misma navegación»    → 1 pestaña

Medido por el arnés sobre esos textos: Jaccard 0.333-0.375 — cae en el hueco EXACTO entre las dos varas. Cada
predicado se defiende solo; lo que no se defiende es la combinación, y por eso la contradicción se resuelve donde
se vuelve física: al repartir la pestaña. Unificar la vara es otro trabajo (la contención separa las dos
poblaciones donde el Jaccard no puede) y NO es lo que arregla este fichero: aunque los dos jueces coincidieran,
dos conductores en una pestaña seguiría siendo indefendible.

Lo que NO se toca: la continuación para lo que se escribió — el operador aclarando un encargo cuyo worker ya no
está («no, de enduro»). Eso sigue reabriendo su tarjeta.
"""
import asyncio

import pytest

from nucleo import dispatch
from nucleo.workers.session import SessionRecord
from widgets.navegador import tasks as nt


@pytest.fixture(autouse=True)
def _aislado(monkeypatch):
    """Un test unitario no toca artefactos vivos: registro de sesiones y de pestañas, propios y vacíos."""
    monkeypatch.setattr(dispatch, "_SESSIONS", {})
    with nt._lock:
        nt._tasks.clear()
    yield
    with nt._lock:
        nt._tasks.clear()


@pytest.fixture(autouse=True)
def _sin_modelo(monkeypatch):
    """`_prepare_web` pide al modelo la esencia del objetivo para la cabecera. Aquí no: un test que dependa de un
    LLM mide la red, no la decisión."""
    async def _fake(_req):
        return ""
    import nucleo.agentes.web as _web
    monkeypatch.setattr(_web, "_synthesize_goal", _fake)


def _rec(tid: str, goal: str, nav: str = "", status: str = "running") -> SessionRecord:
    rec = SessionRecord(task_id=tid, goal=goal, kind="web")
    rec.status = status
    if nav:
        rec.nav_task = nav
    dispatch._SESSIONS[tid] = rec
    return rec


_ENCARGO = "busca un monitor de 27 pulgadas de segunda mano en Wallapop"
_REFORMULADO = "mira monitores de segunda mano de 27 pulgadas en Wallapop y compara precios"


def test_a_second_worker_never_inherits_a_tab_someone_is_driving():
    """El caso medido: el segundo worker del mismo encargo NO puede heredar la pestaña del primero."""
    primero = _rec("1", _ENCARGO)
    t1 = asyncio.run(dispatch._prepare_web(primero, _ENCARGO))
    assert t1, "el primer worker tiene que conseguir su pestaña"
    assert primero.nav_task == t1

    # El juez del navegador SÍ diría que es la misma navegación — ese es justo el punto de partida del fallo.
    assert nt.find_continuation(_REFORMULADO) is not None, \
        "si esto deja de casar, el test ya no está midiendo la contradicción que existe"

    segundo = _rec("2", _REFORMULADO)
    t2 = asyncio.run(dispatch._prepare_web(segundo, _REFORMULADO))
    assert t2 and t2 != t1, "dos conductores en una pestaña: refs invalidadas y clics sobre la página del otro"


def test_three_live_workers_are_three_tabs():
    """Los tres del plató. El invariante es de CONTEO: tantas pestañas como conductores vivos."""
    tabs = []
    for i, texto in enumerate((_ENCARGO, _REFORMULADO, "busca monitores 27\" segunda mano baratos en Wallapop"), 1):
        rec = _rec(str(i), texto)
        tabs.append(asyncio.run(dispatch._prepare_web(rec, texto)))
    assert all(tabs), "ninguno se queda sin tarjeta"
    assert len(set(tabs)) == 3, f"tres conductores vivos comparten pestaña: {tabs}"


def test_a_finished_worker_still_hands_its_tab_over():
    """La continuación NO se rompe: si quien tenía la pestaña ya terminó, el siguiente la reabre — que es para
    lo que se escribió («no, de enduro» sobre una búsqueda recién acabada)."""
    primero = _rec("1", _ENCARGO)
    t1 = asyncio.run(dispatch._prepare_web(primero, _ENCARGO))
    primero.status = "done"
    nt.set_status(t1, "done")

    segundo = _rec("2", _REFORMULADO)
    t2 = asyncio.run(dispatch._prepare_web(segundo, _REFORMULADO))
    assert t2 == t1, "sin nadie conduciendo, el follow-up sigue reabriendo la misma tarjeta"


def test_the_worker_that_owns_the_tab_keeps_it():
    """Un mismo record que vuelve a pasar por aquí (reanudación) conserva SU pestaña: el guarda mira si la
    conduce OTRO, no si está ocupada."""
    rec = _rec("1", _ENCARGO)
    t1 = asyncio.run(dispatch._prepare_web(rec, _ENCARGO))
    t2 = asyncio.run(dispatch._prepare_web(rec, _REFORMULADO))
    assert t2 == t1, "el dueño de la pestaña no se echa a sí mismo"
