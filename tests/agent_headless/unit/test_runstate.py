#
# test_runstate.py — el INTERRUPTOR GLOBAL del agente (V2-092): parar es parar.
#
# El botón ⏻ existía desde V2-039 y congelaba los Brain Workers desde V2-065, pero su estado vivía SOLO en el
# localStorage del navegador. El operador lo vio así (2026-08-13), con el agente parado en pantalla: un vídeo
# seguía reproduciéndose, recargar la página lo volvía a arrancar, la música sonaba a la vez, y los ciclos de
# background seguían sondeando conectores. El ⏻ paraba la voz y los workers; nada más se enteraba, porque el
# servidor no sabía que el operador había parado.
#
# Lo que este test fija es la POLÍTICA, que es donde están las decisiones que se pueden perder en una refactorización:
#   · parar CONGELA a todos (workers + widgets que producen) y persiste;
#   · arrancar CONTINÚA el trabajo pero NO reanuda los widgets (asimetría deliberada, petición del operador);
#   · con el agente parado no hay ticks de background, ni crons, ni trabajo NUEVO;
#   · un fallo de una pieza no puede dejar la parada a medias.
#
# Ejecutar: .venv/bin/pytest tests/agent_headless/unit/test_runstate.py
#
from __future__ import annotations

import asyncio
import json

import pytest

from memory import db as memdb
from nucleo import runstate


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    """Base limpia + caché del interruptor a cero: `state()` cachea en proceso a propósito (lo consultan caminos
    calientes), así que sin esto un test heredaría el interruptor del anterior."""
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    memdb.reset_db()
    memdb.get_db()
    runstate._reset_for_tests()
    yield
    runstate._reset_for_tests()
    memdb.reset_db()


@pytest.fixture
def piezas(monkeypatch):
    """Sustituye las dos piezas que la parada gobierna, y registra lo que se les pidió."""
    log = {"pause": 0, "resume": 0, "suspend": [], "reason": ""}

    from nucleo import dispatch
    monkeypatch.setattr(dispatch, "pause_all", lambda: log.__setitem__("pause", log["pause"] + 1) or 3)
    monkeypatch.setattr(dispatch, "resume_all", lambda: log.__setitem__("resume", log["resume"] + 1) or 3)

    from widgets import producers
    async def suspend_all(*, reason="", channel=None, keep=""):
        log["suspend"].append(reason)
        log["reason"] = reason
        return ["youtube", "musica"]
    monkeypatch.setattr(producers, "suspend_all", suspend_all)
    return log


# ── el estado por defecto y su persistencia ─────────────────────────────────────────────────────────────────
def test_por_defecto_en_marcha():
    """Sin nada guardado el agente está EN MARCHA. Lo contrario sería una instalación nueva que no trabaja y no
    dice por qué."""
    assert runstate.state() == runstate.RUNNING
    assert runstate.running() is True
    assert runstate.stopped() is False


def test_parar_persiste_y_sobrevive_al_proceso(piezas):
    asyncio.run(runstate.stop("operator"))
    assert runstate.stopped() is True
    runstate._reset_for_tests()                    # simula reiniciar el motor
    assert runstate.stopped() is True, "una parada es una INTENCIÓN del operador, no un estado de proceso"


def test_arrancar_persiste(piezas):
    asyncio.run(runstate.stop())
    asyncio.run(runstate.start())
    runstate._reset_for_tests()
    assert runstate.running() is True


def test_una_lectura_imposible_no_deja_el_agente_muerto(monkeypatch):
    """Ante un `sys_kv` ilegible se asume EN MARCHA: un fallo de lectura no puede dejar al operador con un agente
    que se niega a trabajar y sin forma de saber por qué."""
    from memory import api as memapi
    monkeypatch.setattr(memapi, "kv_get", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("db caída")))
    runstate._reset_for_tests()
    assert runstate.state() == runstate.RUNNING


def test_snapshot_es_lo_que_ve_el_frontend(piezas):
    asyncio.run(runstate.stop("operator"))
    snap = runstate.snapshot()
    assert snap["state"] == "stopped" and snap["running"] is False
    assert snap["src"] == "operator" and snap["at"] > 0


# ── PARAR: congela a todos ──────────────────────────────────────────────────────────────────────────────────
def test_parar_congela_workers_y_suspende_widgets(piezas):
    res = asyncio.run(runstate.stop("operator"))
    assert piezas["pause"] == 1
    assert piezas["suspend"] == ["agent_stopped"]
    assert res["workers"] == 3 and res["widgets"] == ["youtube", "musica"]


def test_parar_no_mata_los_workers(piezas, monkeypatch):
    """PAUSAR ≠ matar. `cancel_all` es lo que hace Reset y es irreversible; ⏻ tiene que ser reversible o el
    operador pierde una tarea de minutos por apagar un momento."""
    from nucleo import dispatch
    monkeypatch.setattr(dispatch, "cancel_all", lambda **kw: pytest.fail("⏻ NUNCA debe matar tareas"))
    asyncio.run(runstate.stop())


def test_parar_dos_veces_es_inofensivo(piezas):
    asyncio.run(runstate.stop())
    asyncio.run(runstate.stop())
    assert runstate.stopped() is True


def test_un_worker_que_falla_al_congelar_no_impide_parar_los_widgets(monkeypatch):
    """Una parada a medias es peor que ninguna: el operador cree que paró y algo sigue sonando."""
    from nucleo import dispatch
    monkeypatch.setattr(dispatch, "pause_all", lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    called = []
    from widgets import producers
    async def suspend_all(*, reason="", channel=None, keep=""):
        called.append(reason)
        return ["youtube"]
    monkeypatch.setattr(producers, "suspend_all", suspend_all)
    res = asyncio.run(runstate.stop())
    assert res["widgets"] == ["youtube"] and called == ["agent_stopped"]
    assert runstate.stopped() is True               # y el interruptor queda puesto igual


def test_un_widget_que_falla_no_impide_congelar_los_workers(monkeypatch):
    from nucleo import dispatch
    seen = []
    monkeypatch.setattr(dispatch, "pause_all", lambda: seen.append("pause") or 1)
    from widgets import producers
    async def boom(**kw):
        raise RuntimeError("canvas roto")
    monkeypatch.setattr(producers, "suspend_all", boom)
    res = asyncio.run(runstate.stop())
    assert seen == ["pause"] and res["workers"] == 1 and res["widgets"] == []
    assert runstate.stopped() is True


# ── ARRANCAR: continúa el trabajo, NO la reproducción ───────────────────────────────────────────────────────
def test_arrancar_continua_los_workers(piezas):
    asyncio.run(runstate.stop())
    res = asyncio.run(runstate.start())
    assert piezas["resume"] == 1 and res["workers"] == 3


def test_arrancar_NO_reanuda_los_widgets(piezas, monkeypatch):
    """Palabras del operador: «si digo que arranque el sistema no necesariamente hay que volver a arrancar los
    widgets, que ya sea el usuario a mano el que decide si quiere volver a seguir escuchando música». Lo que SÍ
    continúa es el trabajo (un worker a medias de crear un widget o de una búsqueda)."""
    asyncio.run(runstate.stop())
    piezas["suspend"].clear()
    from widgets import producers
    async def resume_should_not_happen(**kw):
        pytest.fail("arrancar el agente NO debe reanudar los widgets")
    monkeypatch.setattr(producers, "resume_all", resume_should_not_happen, raising=False)
    asyncio.run(runstate.start())
    assert piezas["suspend"] == []                  # tampoco se les vuelve a tocar para nada


# ── lo que el resto del sistema consulta ────────────────────────────────────────────────────────────────────
def test_background_no_hace_ticks_con_el_agente_parado(piezas, monkeypatch):
    """Un «agente parado» que sigue sondeando conectores y escribiendo en la memoria no está parado."""
    from widgets import background
    llamadas = []
    monkeypatch.setattr(background, "_call_tick", lambda wid: llamadas.append(wid))
    asyncio.run(runstate.stop())
    asyncio.run(background._tick_once("mensajeria", "passive"))
    assert llamadas == []
    asyncio.run(runstate.start())
    asyncio.run(background._tick_once("mensajeria", "passive"))
    assert llamadas == ["mensajeria"], "arrancar tiene que devolver los ciclos sin reconstruir el planificador"


def test_un_cron_no_dispara_pero_sigue_vencido(piezas, monkeypatch):
    """Se sale ANTES de `mark_fired`, así que el job sigue vencido y salta en cuanto el operador arranca: parar no
    pierde el recordatorio, lo aplaza. Un cron hablando por voz sobre un agente parado es exactamente el fallo que
    ⏻ existe para evitar."""
    from nucleo import loop as nloop
    marcados, entregados = [], []
    monkeypatch.setattr(nloop._scheduler, "due", lambda now=None: [{"id": "j1", "title": "riega",
                                                                   "detail": {"prompt": "riega las plantas"}}])
    monkeypatch.setattr(nloop._scheduler, "mark_fired", lambda job, now=None: marcados.append(job["id"]))

    orq = nloop.OrchestratorLoop.__new__(nloop.OrchestratorLoop)     # sin arrancar el ciclo real
    async def deliver(name, prompt):
        entregados.append(prompt)
    orq._deliver = deliver

    asyncio.run(runstate.stop())
    asyncio.run(orq._fire_due(0.0))
    assert entregados == [] and marcados == [], "el job debe seguir VENCIDO, no consumido"

    asyncio.run(runstate.start())
    asyncio.run(orq._fire_due(0.0))
    assert entregados == ["riega las plantas"] and marcados == ["j1"]


def _escalar(tid: str):
    """Publica una escalada en el bus y deja al listener del dispatcher un momento para atenderla."""
    import bus
    from nucleo import dispatch

    async def escenario():
        stop_ev = asyncio.Event()
        listener = asyncio.create_task(dispatch.run_listener(stop_ev))
        await asyncio.sleep(0.05)
        await bus.publish("escalate.requested", {"id": tid, "request": f"búscame un velero {tid}", "context": {}})
        await asyncio.sleep(0.25)
        stop_ev.set()
        await asyncio.wait_for(listener, timeout=3)

    asyncio.run(escenario())


def test_no_se_abre_trabajo_nuevo_con_el_agente_parado(piezas, monkeypatch):
    """Los workers que ya estaban se congelan y continúan; abrir uno DESDE CERO sobre un agente parado es lo
    contrario de parar. Y se rechaza VISIBLE (evento `task/blocked`), nunca en silencio."""
    from nucleo import dispatch
    monkeypatch.setattr(dispatch, "_run_session", lambda task: asyncio.sleep(5))

    # CONTROL POSITIVO primero: sin él, este test pasaría igual si el listener estuviera roto o el bus no llegara,
    # y sería un test que no prueba nada.
    _escalar("t-viva")
    assert dispatch.get_record("t-viva") is not None, "el arnés tiene que ser capaz de abrir una sesión"
    dispatch.cancel_session("t-viva", reason="test")

    asyncio.run(runstate.stop())
    _escalar("t-nueva")
    assert dispatch.get_record("t-nueva") is None, "con el agente parado no debe nacer ninguna sesión"


# ── no voice session while the agent is stopped (2026-08-15) ───────────────────────────────────────────────
# Real: the operator restarted the engine, saw ⏻ off, and opened a second window/profile — the master showed a
# session "EN CURSO" anyway. Cause: `/api/token` (server/livekit_api.py) minted the LiveKit JWT without checking
# the global switch — a window without its own `hb_power_off` in localStorage could always open a room + kickoff,
# even with the server considering the agent stopped. No token, no room; no room, no kickoff.
def test_token_is_refused_while_the_agent_is_stopped(piezas):
    from server import livekit_api

    asyncio.run(runstate.stop())
    resp = livekit_api.token()
    assert resp.status_code == 409
    assert json.loads(resp.body) == {"error": "engine_stopped"}


def test_token_is_granted_while_running():
    from server import livekit_api

    resp = livekit_api.token()
    assert resp.status_code == 200
    body = json.loads(resp.body)
    assert body["token"] and body["room"].startswith(livekit_api.SETTINGS.room_name)


# ── DEFERRED stop: a turn in flight doesn't get cut mid-way, and no clock is needed for it (2026-08-15) ────────
# The operator was explicit: the stop's completion must be triggered by a CONCRETE ACTION (the turn genuinely
# ending), not a timer — a clock only applies to the case, already covered elsewhere
# (`observability/identity.py`), where no close signal ever arrives.
def test_stopping_with_a_turn_in_flight_defers_and_freezes_nothing_yet(piezas):
    runstate.enter_inflight()
    res = asyncio.run(runstate.stop("operator"))
    assert res == {"ok": True, "state": "pausing"}
    assert runstate.stopped() is False, "underneath it's still RUNNING — nothing has been frozen yet"
    assert piezas["pause"] == 0 and piezas["suspend"] == []
    assert runstate.pending_stop() is True
    assert runstate.snapshot()["state"] == "pausing"
    assert runstate.snapshot()["running"] is True


def test_pressing_again_during_pausing_cancels_the_stop(piezas):
    runstate.enter_inflight()
    asyncio.run(runstate.stop("operator"))
    res = asyncio.run(runstate.stop("operator"))
    assert res == {"ok": True, "state": runstate.RUNNING, "cancelled": True}
    assert runstate.pending_stop() is False
    assert runstate.stopped() is False
    assert piezas["pause"] == 0 and piezas["suspend"] == [], "nothing to undo: nothing was ever frozen"
    asyncio.run(runstate.exit_inflight())          # the turn ends — NOTHING should happen, it was cancelled
    assert runstate.stopped() is False


def test_the_last_turn_to_finish_completes_the_deferred_stop(piezas):
    runstate.enter_inflight()
    runstate.enter_inflight()                      # two turns from TWO different rooms — the switch is global
    asyncio.run(runstate.stop("operator"))
    asyncio.run(runstate.exit_inflight())           # the first one ends — the second is still in flight
    assert runstate.stopped() is False and piezas["pause"] == 0, "a turn is still in flight"
    asyncio.run(runstate.exit_inflight())           # the LAST one ends — NOW it completes the stop
    assert runstate.stopped() is True
    assert piezas["pause"] == 1 and piezas["suspend"] == ["agent_stopped"]


def test_starting_also_cancels_a_deferred_stop(piezas):
    """The frontend's ⏻, on a second click during "pausing", calls the same endpoint as "turn on" (it sees
    `store.powerOff()` already `true` from the first click) — so `start()`, not just `stop()` again, has to
    know how to cancel a pending stop."""
    runstate.enter_inflight()
    asyncio.run(runstate.stop("operator"))
    assert runstate.pending_stop() is True
    res = asyncio.run(runstate.start("operator"))
    assert res["state"] == runstate.RUNNING
    assert runstate.pending_stop() is False
    assert piezas["pause"] == 0 and piezas["suspend"] == [], "nothing was ever frozen: nothing to resume"
    asyncio.run(runstate.exit_inflight())          # the turn ends — cancelled, nothing should stop
    assert runstate.stopped() is False


def test_with_no_turns_in_flight_stopping_is_instant_as_always(piezas):
    assert runstate.inflight_count() == 0
    res = asyncio.run(runstate.stop("operator"))
    assert res["state"] == runstate.STOPPED
    assert piezas["pause"] == 1


# ── stopping closes the observability session (2026-08-16) ───────────────────────────────────────────────
# Real: with the agent stopped and the browser tab left open, background noise (the ~1Hz loop heartbeat,
# the RAM→state projection) kept landing on whatever session was already open when ⏻ was pressed — nothing
# ever closed it, so the backoffice master showed it "EN CURSO" indefinitely, with its flow/event counts
# still climbing. `_do_stop` now closes the observability session; background noise afterward gets no
# session at all (`stamp_identity`'s system/pulse guard only READS the current session, never reopens it).
def test_stopping_closes_the_open_observability_session(piezas):
    from observability import identity
    identity.end_session("test")
    identity.begin_session(source="test")
    assert identity.session_info().get("session_id") is not None, "arrange: a session is open before stopping"

    asyncio.run(runstate.stop("operator"))

    assert identity.session_info().get("session_id") is None, \
        "the session must be closed the moment the agent stops — that's what 'EN CURSO' forever was tracing back to"
    identity.end_session("test")


def test_background_noise_after_stop_does_not_resurrect_the_closed_session(piezas):
    from observability import identity
    from voice import observer

    identity.end_session("test")
    identity.begin_session(source="test")
    asyncio.run(runstate.stop("operator"))
    assert identity.session_info().get("session_id") is None

    ev = observer.emit("pulse", "tick", extra={"cat": "pulse"})
    assert not ev.get("sid"), "background noise after a deliberate stop must not mint a fresh session"
    assert identity.session_info().get("session_id") is None
    identity.end_session("test")
