"""V2-149 (`reorder-prescription__es`) — cuatro turnos preguntando DÓNDE y ni uno preguntando QUÉ.

El encargo era «pide la reposición de mi receta». zaelar gastó los turnos 1 a 4 en localizar la farmacia —de
uno en uno: nombre, luego ciudad, luego el súper, luego la calle— y **nunca preguntó qué receta reponer**, que
es el objeto del encargo. En el turno 5: «perfecto, con eso me basta… llamo para pedir la reposición de tu
receta», sin saber cuál. El juez lo marca `alta` dos veces y el watchdog cuatro.

Dos reglas simétricas de la que ya existía desde V2-120 (si te preguntan dos cosas, contesta las dos): pedir las
dos mitades de lo que falta en la misma frase, y no dar por completo un encargo cuyo OBJETO sigue sin
identificar.

La otra mitad del caso ya venía arreglada y se pinta aquí para que no se pierda: la petición ya enruta a `web`
(V2-144, `local_business`), así que la tarea tiene navegador — y narrar «lleva unos 70 segundos localizando la
farmacia» sobre una tarea sin página abierta lo cerró V2-145. Las dos landed DESPUÉS de esta corrida.
"""
from __future__ import annotations

import pytest

from nucleo import dispatch
from nucleo.flash import prompt
from nucleo.flash import router_guards as g
from nucleo.flash import site_catalog as sc


ASK = "Pide la reposición de mi receta de la farmacia de siempre."


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    from memory import db as memdb
    from memory import embeddings as mememb
    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    mememb.reset()
    memdb.reset_db()
    memdb.get_db()
    yield
    memdb.reset_db()
    mememb.reset()


def test_ask_for_everything_that_is_missing_at_once(fresh_db):
    system, _ = prompt.build_flash_system()
    assert "Pídelos TODOS de una vez" in system
    assert "no uno por turno" in system


def test_and_do_not_start_an_errand_whose_object_is_unknown(fresh_db):
    system, _ = prompt.build_flash_system()
    assert "comprueba que sabes QUÉ te ha encargado" in system
    assert "sin saber QUÉ receta" in system


def test_asking_is_still_the_correct_answer(fresh_db):
    """The rule sharpens HOW to ask, it does not discourage asking — this suite scores asking well (V2-082)."""
    system, _ = prompt.build_flash_system()
    assert "PÍDELO — preguntar es la respuesta" in system


# ── lo que ya venía arreglado, pinchado para que no se pierda ────────────────────────────────────────────────
@pytest.mark.parametrize("text", [
    ASK,
    "pide la reposición de mi receta en la farmacia del barrio",
    "llama a la farmacia y pide la reposición de mi receta",
    "busca la farmacia al lado del Día en Bravo Murillo, Chamberí",
])
def test_the_errand_gets_a_browser(text):
    """V2-144: sin categoría, esto era `generic` — un worker sin navegador, que es por lo que la tarea no podía
    existir. La familia `widget` que el informe echaba en falta cuelga de aquí."""
    assert sc.category_of(text) == "local_business"
    assert dispatch._classify_kind(text) == "web"
    assert g._needs_real_work(text) is True


def test_and_the_brain_cannot_narrate_a_browser_that_opened_nothing(fresh_db, monkeypatch):
    """V2-145: «lleva unos 70 segundos localizando la farmacia» sobre una tarea con `url=` vacía."""
    from widgets.navegador import tasks as nt
    monkeypatch.setattr(nt, "active_summaries", lambda limit=3: [("t9", "localizar la farmacia de Chamberí")])
    monkeypatch.setattr(nt, "active_progress",
                        lambda limit=3: [{"id": "t9", "goal": "x", "url": "", "phase": "", "steps": 0,
                                          "awaiting_login": False}])
    line = next(l for l in prompt.live_state().splitlines() if l.startswith("NAVEGADOR"))
    assert "TODAVÍA NO HA ABIERTO NINGUNA PÁGINA" in line
