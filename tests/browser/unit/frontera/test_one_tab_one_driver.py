"""One tab, one driver — measured LIVE on 2026-08-21 (`search-secondhand-monitor`, harness test set).

Three workers for the same request each received the SAME browser task (`t6`) and drove it at the same time:
46, 27, and 7 interleaved actions on a single page. The trace, verbatim:

    15:43:43  worker:1  navigate → es.wallapop.com
    15:43:57  worker:2  navigate → es.wallapop.com          ← pisa al 1
    15:44:05  worker:1  type «monitor 27 pulgadas»
    15:44:43  worker:1  click [29]
    15:44:49  worker:2  click [29]                          ← misma ref, página ya cambiada por el otro

The clicks are the real harm, and V2-248 already documented it: element references are assigned when observing,
so the same number refers to another element as soon as the page changes. `worker:2` pressed the «29» from a
snapshot that `worker:1` had just invalidated. On a page with a payment button, that is not a dirty result: it is
a WRONG ACTION, which is why this is treated as contention rather than hygiene.

THE CAUSE is that there are TWO similarity judges and they disagree about the SAME pair of texts:

    dispatch.find_duplicate      Jaccard ≥ 0.60 sobre palabras de ≥4 letras   → «encargos distintos»  → 3 workers
    navegador.tasks._similar     ≥2 raíces compartidas O Jaccard ≥ 0.40       → «misma navegación»    → 1 pestaña

Measured by the harness on those texts: Jaccard 0.333-0.375 — it falls in the EXACT gap between the two bars. Each
predicate stands on its own; what does not stand is the combination, so the contradiction is resolved where it
becomes physical: when assigning the tab. Unifying the bar is a separate task (contention separates the two
populations where Jaccard cannot) and is NOT what fixes this file: even if the two judges agreed, two drivers on
one tab would still be indefensible.

What is NOT touched: the continuation for what was written — the operator clarifying a request whose worker is no
longer there («no, de enduro»). That still reopens its card.
"""
import asyncio

import pytest

from nucleo import dispatch
from nucleo.workers.session import SessionRecord
from widgets.navegador import tasks as nt


@pytest.fixture(autouse=True)
def _aislado(monkeypatch):
    """A unit test does not touch live artifacts: its own, empty session and tab registries."""
    monkeypatch.setattr(dispatch, "_SESSIONS", {})
    with nt._lock:
        nt._tasks.clear()
    yield
    with nt._lock:
        nt._tasks.clear()


@pytest.fixture(autouse=True)
def _sin_modelo(monkeypatch):
    """`_prepare_web` asks the model for the gist of the goal for the header. Not here: a test that depends on an
    LLM measures the network, not the decision."""
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
    """The measured case: the second worker for the same request MUST NOT inherit the first worker's tab."""
    primero = _rec("1", _ENCARGO)
    t1 = asyncio.run(dispatch._prepare_web(primero, _ENCARGO))
    assert t1, "el primer worker tiene que conseguir su pestaña"
    assert primero.nav_task == t1

    # The browser judge WOULD say it is the same navigation — that is precisely the starting point of the failure.
    assert nt.find_continuation(_REFORMULADO) is not None, \
        "si esto deja de casar, el test ya no está midiendo la contradicción que existe"

    segundo = _rec("2", _REFORMULADO)
    t2 = asyncio.run(dispatch._prepare_web(segundo, _REFORMULADO))
    assert t2 and t2 != t1, "dos conductores en una pestaña: refs invalidadas y clics sobre la página del otro"


def test_three_live_workers_are_three_tabs():
    """The three from the test set. The invariant is about COUNT: as many tabs as live drivers."""
    tabs = []
    for i, texto in enumerate((_ENCARGO, _REFORMULADO, "busca monitores 27\" segunda mano baratos en Wallapop"), 1):
        rec = _rec(str(i), texto)
        tabs.append(asyncio.run(dispatch._prepare_web(rec, texto)))
    assert all(tabs), "ninguno se queda sin tarjeta"
    assert len(set(tabs)) == 3, f"tres conductores vivos comparten pestaña: {tabs}"


def test_a_finished_worker_still_hands_its_tab_over():
    """The continuation is NOT broken: if whoever had the tab has already finished, the next one reopens it — that
    is what it was written for («no, de enduro» about a just-completed search)."""
    primero = _rec("1", _ENCARGO)
    t1 = asyncio.run(dispatch._prepare_web(primero, _ENCARGO))
    primero.status = "done"
    nt.set_status(t1, "done")

    segundo = _rec("2", _REFORMULADO)
    t2 = asyncio.run(dispatch._prepare_web(segundo, _REFORMULADO))
    assert t2 == t1, "sin nadie conduciendo, el follow-up sigue reabriendo la misma tarjeta"


def test_the_worker_that_owns_the_tab_keeps_it():
    """The same record coming through here again (resumption) keeps ITS tab: the guard checks whether SOMEONE ELSE
    is driving it, not whether it is occupied."""
    rec = _rec("1", _ENCARGO)
    t1 = asyncio.run(dispatch._prepare_web(rec, _ENCARGO))
    t2 = asyncio.run(dispatch._prepare_web(rec, _REFORMULADO))
    assert t2 == t1, "el dueño de la pestaña no se echa a sí mismo"
