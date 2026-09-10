"""V2-655 — ⏻ parado: no se resucita nada, no se lanza ningún worker, y no se PIERDE nada.

Medido 2026-09-10. El motor arrancó con `{"state":"stopped","src":"operator"}` persistido —el operador había
pulsado ⏻— y aun así:

    19:18:55 | rehidratación: re-escalada «Busca en fuentes de torrent/magnet …»
    19:18:56 | dispatch: tarea 1 dirigida por BRIEF · kind=research
    19:18:56 | worker[1]: ClaudeCodeSession start (model=glm-5.3, tools=33, …)

Un Brain Worker de verdad, gastando dinero de verdad, sobre un agente apagado. `nucleo/rehydrate.py` no
consultaba el interruptor en ninguna línea, y la puerta que sí lo consulta —`dispatch.run_listener`— llega
seis segundos TARDE: para entonces el rastro ya está borrado y una vida de `RESUME_CAP` ya está quemada, así
que un rechazo correcto allí destruye el trabajo interrumpido en silencio.

La regla que fijan estos casos es la del cron: **aplazar, no perder.**
"""
import asyncio

import pytest

from memory import db as memdb
from nucleo import rehydrate as R
from nucleo import runstate


@pytest.fixture(autouse=True)
def _isolated_switch(tmp_path, monkeypatch):
    """Base de datos limpia + caché del interruptor a cero. `state()` cachea en proceso a propósito (la ruta
    caliente lo consulta), así que sin esto un caso hereda el interruptor del anterior. El `conftest` raíz
    fuerza EN MARCHA para toda la suite; aquí hace falta poder pararlo de verdad."""
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    memdb.reset_db()
    memdb.get_db()
    runstate._reset_for_tests()
    yield
    runstate._reset_for_tests()
    memdb.reset_db()


def _trail(monkeypatch, sessions):
    monkeypatch.setattr(R, "snapshot", lambda: {"at": 1000.0, "sessions": sessions})


_LIVE = [{"id": "t1", "goal": "Busca en fuentes de torrent el archivo X", "status": "running",
          "kind": "generic", "beat": 1000.0}]


def test_a_stopped_agent_resumes_NOTHING(monkeypatch):
    fired = []
    monkeypatch.setattr("nucleo.flash.escalate.escalate_to_slowbrain",
                        lambda req, **k: fired.append(req) or 1)
    _trail(monkeypatch, _LIVE)
    asyncio.run(runstate.stop("operator"))
    plan = R.at_boot(now=1010.0, delay=0.0)
    assert plan["resume"] == [] and plan.get("halted") is True
    assert fired == [], "un agente apagado no levanta workers"


def test_the_trail_SURVIVES_so_the_next_boot_can_pick_it_up(monkeypatch):
    """El fallo caro no es no reanudar: es no reanudar Y borrar el rastro. Gatear solo en la puerta de
    dispatch hace exactamente eso, seis segundos más tarde y en silencio."""
    forgotten = []
    monkeypatch.setattr(R, "forget", lambda: forgotten.append(1))
    bumped = []
    monkeypatch.setattr(R, "_bump", lambda goals, now=None: bumped.append(goals))
    _trail(monkeypatch, _LIVE)
    asyncio.run(runstate.stop("operator"))
    R.at_boot(now=1010.0, delay=0.0)
    assert forgotten == [], "el rastro se queda: el próximo arranque encendido lo recoge"
    assert bumped == [], "y no se quema una vida de RESUME_CAP por un intento que ni ocurrió"


def test_it_still_says_how_many_are_waiting(monkeypatch):
    _trail(monkeypatch, _LIVE)
    asyncio.run(runstate.stop("operator"))
    assert R.at_boot(now=1010.0, delay=0.0)["found"] == 1, (
        "aplazar en silencio absoluto es la otra mitad del mismo fallo")


def test_an_UNREADABLE_switch_does_not_authorise_spending(monkeypatch):
    """Asimetría deliberada con `runstate._load()`, que ante una lectura imposible responde EN MARCHA para no
    dejar al operador con un agente muerto: allí lo que está en juego es que él pueda USARLO, aquí que
    nosotros GASTEMOS sin que nos lo pida."""
    def _boom():
        raise RuntimeError("sys_kv no está listo")
    monkeypatch.setattr(runstate, "stopped", _boom)
    fired = []
    monkeypatch.setattr("nucleo.flash.escalate.escalate_to_slowbrain",
                        lambda req, **k: fired.append(req) or 1)
    monkeypatch.setattr(R, "forget", lambda: pytest.fail("no puede consumir el rastro sin saber si puede"))
    _trail(monkeypatch, _LIVE)
    assert R.at_boot(now=1010.0, delay=0.0).get("halted") is True
    assert fired == []


def test_a_RUNNING_agent_still_resumes_exactly_as_before(monkeypatch):
    """El contrapeso: este módulo existe para que un reinicio no pierda trabajo. Si el gate se pasa de
    listo, el arreglo cuesta más que el fallo."""
    fired = []
    monkeypatch.setattr("nucleo.flash.escalate.escalate_to_slowbrain",
                        lambda req, **k: fired.append(req) or 1)
    _trail(monkeypatch, _LIVE)
    asyncio.run(runstate.start("operator"))
    plan = R.at_boot(now=1010.0, delay=0.0)
    assert len(plan["resume"]) == 1 and plan.get("halted") is not True


# ── la puerta de los workers falla CERRADO ───────────────────────────────────────────────────────────────

def test_an_unreadable_switch_blocks_new_work_everywhere_at_once(monkeypatch):
    """UNA respuesta para las tres puertas que pueden gastar. Antes cada una llevaba su propio `try/except` y
    **las tres fallaban ABIERTAS**: un interruptor ilegible significaba «adelante, gasta»."""
    def _boom():
        raise RuntimeError("sys_kv no está listo")
    monkeypatch.setattr(runstate, "stopped", _boom)
    assert runstate.blocks_new_work(who="test") is True


def test_a_running_agent_is_never_blocked_by_this():
    """El contrapeso: si el gate se pasa de listo, el arreglo cuesta más que el fallo."""
    asyncio.run(runstate.stop("operator"))
    assert runstate.blocks_new_work() is True
    asyncio.run(runstate.start("operator"))
    assert runstate.blocks_new_work() is False


def test_the_three_spending_doors_all_ask_the_SAME_question():
    """La regla que cerró V2-654 en el micro, aquí otra vez: una regla que cada llamador tiene que recordar no
    es una regla. Tres copias de un `try/except` derivan; una función no."""
    import re
    from pathlib import Path
    root = Path(__file__).resolve().parents[3]
    for rel, why in (("nucleo/dispatch.py", "el chokepoint de TODO Brain Worker"),
                     ("nucleo/rehydrate.py", "la resurrección de encargos al arrancar"),
                     ("widgets/server_api.py", "el relanzamiento de generaciones de widget")):
        text = re.sub(r"(?m)#.*$", "", (root / rel).read_text(encoding="utf-8"))
        assert "runstate.blocks_new_work(" in text, f"{rel} ({why}) no pasa por la puerta única"


# ── la SEGUNDA puerta: el relanzamiento de generaciones de widget ───────────────────────────────────────

def test_the_widget_generation_resume_also_obeys_the_switch():
    """Relanza `generate_widget`, que abre un `claude -p` de verdad, y no estaba gateada ni por el
    interruptor ni por el cerebro activo. El gate va ANTES de `take_pending_jobs()`, que DRENA el diario."""
    import re
    from pathlib import Path
    src = Path(__file__).resolve().parents[3] / "widgets/server_api.py"
    text = re.sub(r"(?m)#.*$", "", src.read_text(encoding="utf-8"))
    i = text.find("async def resume_interrupted_generations")
    assert i >= 0
    body = text[i:i + 1400]
    gate, drain = body.find("runstate.blocks_new_work("), body.find("take_pending_jobs()")
    assert gate >= 0, "el relanzamiento de generaciones tiene que mirar el interruptor"
    assert drain > gate, (
        "gatear DESPUÉS de drenar el diario borra el trabajo pendiente del operador en silencio — "
        "aplazar, no perder")
