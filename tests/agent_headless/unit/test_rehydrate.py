"""
test_rehydrate.py — REHIDRATACIÓN: el trabajo que un reinicio deja a medias no puede desaparecer en silencio.

Anclado al incidente del 2026-08-12, reconstruido evento a evento del log durable:

    12:19:46  🧭 Flash → Brain Worker  «Busca en Wallapop … veleros … mínimo 45 pies»   (task 1)
    12:19:51  ui canvas (instancias): ['navegador::t1']
    12:19:52  ui canvas (instancias): ['navegador::t1', 'navegador']
    12:21:15  ── el proceso REARRANCA (susurro/background/homeostasis start) ──
              …y del worker no se vuelve a saber NADA: ni evento, ni entrada en el ledger, ni aviso.
    12:21:23  la pantalla SIGUE pintando las dos tarjetas de un navegador que ya no existe
    12:27:01  ui canvas (instancias): []          ← el operador recarga; escritorio en blanco

Tres agujeros distintos, uno por bloque de este fichero:
  (1) el registro de sesiones vivas era RAM y NADIE lo leía al arrancar → el trabajo moría sin rastro;
  (2) la continuidad web (`native_sid`) también era RAM → aunque quisiéramos, no había con qué CONTINUAR;
  (3) un reset debe BORRAR ese rastro: matar el trabajo a mano es una orden, no una caída.

La decisión de qué se reanuda vive en `rehydrate.classify`, que es PURA — se prueba entera sin BD ni reloj.
"""
import time

import pytest

from memory import api as memapi
from memory import db as memdb
from memory import embeddings as mememb
from nucleo import rehydrate as R

# El objetivo REAL que se perdió, verbatim del evento de escalada.
VELEROS = ('Busca en Wallapop (el operador dice "Gualapop", es Wallapop) veleros en venta en España con un mínimo '
           'de 45 pies de eslora. Haz una selección de los CINCO mejores.')


@pytest.fixture(autouse=True)
def _hash_backend(monkeypatch):
    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
    mememb.reset()
    yield
    mememb.reset()


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    memdb.reset_db()
    memdb.get_db()
    yield
    memdb.reset_db()


def _live(**kw) -> dict:
    base = {"id": "1", "goal": VELEROS, "kind": "web", "status": "running", "phase": "buscando"}
    base.update(kw)
    return base


# ── 1. la DECISIÓN (pura): qué continúa solo y qué se reporta ────────────────────────────────────────────────
def test_a_search_cut_by_a_restart_is_resumed():
    now = time.time()
    plan = R.classify([_live()], at=now - 90, now=now)
    assert [e["id"] for e in plan["resume"]] == ["1"]
    assert plan["buried"] == []


def test_a_code_worker_is_never_resumed_on_its_own():
    """Reanudar al generador REESCRIBE el código de un widget del operador. Se reporta y se queda quieto."""
    now = time.time()
    plan = R.classify([_live(kind="code", goal="reescribe el widget de agenda")], at=now - 60, now=now)
    assert plan["resume"] == []
    assert "código" in plan["buried"][0]["why"]


def test_work_the_operator_paused_stays_paused():
    now = time.time()
    plan = R.classify([_live(paused=True)], at=now - 60, now=now)
    assert plan["resume"] == [] and "pausad" in plan["buried"][0]["why"]


def test_a_session_waiting_for_an_answer_is_reported_not_relaunched():
    """La pregunta murió con el proceso que la sostenía: relanzar el worker no la recupera."""
    now = time.time()
    plan = R.classify([_live(waiting_on="user", ask="¿te vale con 40 pies?")], at=now - 60, now=now)
    assert plan["resume"] == [] and "respuesta" in plan["buried"][0]["why"]


def test_old_work_is_reported_but_not_resumed():
    """«Busca veleros» de hace horas no es trabajo pendiente. Se ve en Procesos; no se relanza."""
    now = time.time()
    plan = R.classify([_live()], at=now - (R.STALE_S + 60), now=now)
    assert plan["resume"] == [] and plan["stale"] is True
    assert "vieja" in plan["buried"][0]["why"]


def test_a_crash_loop_stops_resurrecting_the_same_goal():
    """Anti-bucle: si ya se reanudó `RESUME_CAP` veces y volvió a caer, deja de respawnearse."""
    now = time.time()
    marks = {R._goal_key(VELEROS): {"n": R.RESUME_CAP, "ts": now}}
    plan = R.classify([_live()], at=now - 60, now=now, marks=marks)
    assert plan["resume"] == [] and "reanudé" in plan["buried"][0]["why"]


def test_one_restart_never_becomes_a_worker_storm():
    now = time.time()
    many = [_live(id=str(i), goal=f"tarea distinta número {i}") for i in range(R.MAX_RESUME + 4)]
    plan = R.classify(many, at=now - 60, now=now)
    assert len(plan["resume"]) == R.MAX_RESUME
    assert all("tope" in e["why"] for e in plan["buried"])


def test_finished_sessions_are_not_pending_work():
    now = time.time()
    plan = R.classify([_live(status="done"), _live(id="2", status="error")], at=now - 60, now=now)
    assert plan["resume"] == [] and plan["buried"] == []


# ── 2. el RASTRO durable: sin él, el arranque no tiene nada que leer ─────────────────────────────────────────
def test_live_work_leaves_a_trace_with_a_timestamp(fresh_db):
    R.remember([_live()], now=1000.0)
    snap = R.snapshot()
    assert snap["at"] == 1000.0
    assert snap["sessions"][0]["goal"] == VELEROS


def test_nothing_in_flight_leaves_no_trace(fresh_db):
    R.remember([_live()])
    R.remember([_live(status="done")])          # terminó → no hay nada que rehidratar
    assert R.snapshot() is None


def test_the_trace_is_consumed_once(fresh_db):
    """Si el proceso vuelve a caer en el arranque, el MISMO rastro no puede reanudar dos veces."""
    R.remember([_live()])
    first = R.at_boot(schedule=False)
    assert first["found"] == 1
    assert R.at_boot(schedule=False)["found"] == 0


def test_a_clean_boot_is_a_silent_no_op(fresh_db):
    """El caso normal —no había nada en vuelo— no cuesta ni un evento ni una línea en el ledger."""
    from nucleo.workers import ledger
    out = R.at_boot(schedule=False)
    assert out == {"found": 0, "resume": [], "buried": []}
    assert ledger.history() == []


def test_interrupted_work_shows_up_in_the_operators_process_list(fresh_db):
    """Lo que se perdió tiene que VERSE (regla del operador: un estado que puede engañar tiene que verse)."""
    from nucleo.workers import ledger
    R.remember([_live()])
    R.at_boot(schedule=False)
    hist = ledger.history()
    assert len(hist) == 1
    assert hist[0]["status"] == "interrumpido" and hist[0]["ok"] is False
    assert "Wallapop" in hist[0]["goal"]


def test_resuming_marks_the_goal_so_the_next_crash_gives_up(fresh_db):
    R.remember([_live()])
    R.at_boot(schedule=False, now=2000.0)
    marks = R._marks(2000.0)
    assert marks[R._goal_key(VELEROS)]["n"] == 1
    # …y a las horas el contador caduca: mañana ese objetivo vuelve a tener sus vidas.
    assert R._marks(2000.0 + R.MARK_TTL_S + 1) == {}


def test_the_events_land_in_the_brain_workers_family(fresh_db):
    """Cazado en vivo: `observer.emit` hace `ev.update(extra)`, así que un `kind` dentro de `extra` PISA el kind del
    evento — estas líneas salían clasificadas como `code`/`web` y el chip «Brain Workers» del visor no las
    enseñaba. Un aviso que no se ve es un aviso que no existe."""
    import bus
    seen = []
    sink = lambda rec: seen.append(rec["payload"]) if rec["topic"] == "observer" else None
    bus.add_sink(sink)
    try:
        R.remember([_live(), _live(id="2", kind="code", goal="reescribe el widget de agenda")])
        R.at_boot(schedule=False)
    finally:
        bus.remove_sink(sink)
    mine = [e for e in seen if isinstance(e, dict) and "reiniciar" in str(e.get("label") or "")]
    assert len(mine) == 2
    for ev in mine:
        assert ev["kind"] == "task"       # ← la FAMILIA («Brain Workers»), no el tipo de trabajo
        assert ev["cat"] == "worker"      # la sella observer._CAT; pasarla a mano permitía inventarse una retirada
    assert {e.get("work") for e in mine} == {"web", "code"}


def test_the_resume_really_fires_and_carries_the_goal(fresh_db):
    """El plan no basta: hay que comprobar que la re-escalada SALE. Es diferida a propósito (el listener de
    escaladas tiene que estar suscrito o el evento se publica contra nadie), así que esto ejerce el `create_task`
    y el `sleep` de verdad — la única parte que los tests con `schedule=False` no tocan."""
    import asyncio

    from nucleo.flash import escalate

    calls = []

    async def _run():
        orig = escalate.escalate_to_slowbrain
        escalate.escalate_to_slowbrain = lambda req, context=None: calls.append((req, context or {})) or 1
        try:
            R.remember([_live()])
            out = R.at_boot(delay=0.0)          # schedule=True: crea la task de verdad
            assert len(out["resume"]) == 1
            for _ in range(50):                 # deja que la task diferida corra
                await asyncio.sleep(0.01)
                if calls:
                    break
        finally:
            escalate.escalate_to_slowbrain = orig

    asyncio.run(_run())
    assert len(calls) == 1
    req, ctx = calls[0]
    assert req == VELEROS                       # el objetivo íntegro, no un resumen
    assert ctx["kind"] == "web" and ctx["rehydrated"] is True


def test_at_boot_reports_what_it_decided(fresh_db):
    R.remember([_live(), _live(id="2", kind="code", goal="reescribe el widget de agenda")])
    out = R.at_boot(schedule=False)
    assert out["found"] == 2
    assert [e["id"] for e in out["resume"]] == ["1"]
    assert [e["id"] for e in out["buried"]] == ["2"]


# ── 3. la costura con dispatch: el rastro lo deja quien ya sabe que algo cambió ──────────────────────────────
def test_dispatch_leaves_the_trace_when_it_projects_live_sessions(fresh_db):
    from nucleo import dispatch
    from nucleo.workers.session import SessionRecord
    dispatch._SESSIONS.clear()
    dispatch._last_sync = None
    try:
        rec = SessionRecord(task_id="1", goal=VELEROS, kind="web", status="running", phase="buscando")
        dispatch._SESSIONS["1"] = rec
        dispatch.sync_state()
        snap = R.snapshot()
        assert snap is not None and snap["sessions"][0]["id"] == "1"
    finally:
        dispatch._SESSIONS.clear()
        dispatch._last_sync = None


def test_web_continuity_survives_the_restart(fresh_db):
    """Sin el `native_sid` persistido, «reanudar» sería empezar la búsqueda de cero."""
    from nucleo import dispatch
    dispatch._WEB_RESUME.clear()
    try:
        dispatch._WEB_RESUME["veleros wallapop"] = {"native_sid": "sess-abc", "nav_task": "t1",
                                                   "ts": time.time(), "count": 1, "goal": VELEROS}
        dispatch._resume_persist()
        dispatch._WEB_RESUME.clear()                      # ← el proceso muere
        assert dispatch._resume_restore() == 1            # ← y el siguiente lo recupera
        assert dispatch._WEB_RESUME["veleros wallapop"]["native_sid"] == "sess-abc"
    finally:
        dispatch._WEB_RESUME.clear()


def test_stale_web_continuity_is_not_revived(fresh_db):
    from nucleo import dispatch
    dispatch._WEB_RESUME.clear()
    try:
        dispatch._WEB_RESUME["viejo"] = {"native_sid": "x", "ts": time.time() - (dispatch._RESUME_TTL + 60)}
        dispatch._resume_persist()
        dispatch._WEB_RESUME.clear()
        assert dispatch._resume_restore() == 0
    finally:
        dispatch._WEB_RESUME.clear()


# ── 4. un RESET es una orden, no una caída ──────────────────────────────────────────────────────────────────
def test_a_reset_does_not_let_the_next_boot_resurrect_the_work(fresh_db):
    """El operador aprieta Reset «para empezar de cero»: el arranque siguiente no puede devolverle el trabajo."""
    from nucleo import reset
    R.remember([_live()])
    reset.reset_all()
    assert R.snapshot() is None
    assert R.at_boot(schedule=False)["found"] == 0


# ── 4. REANUDAR NO ES «NO ME VALE, BUSCA MÁS» ────────────────────────────────────────────────────────────────
# Visto en vivo el 2026-08-12: dos reinicios ajenos seguidos, en mitad de una investigación de veleros, la
# convirtieron en «RONDA 2 de una investigación ya conocida (≥80 candidatos)». La expansión de ronda es correcta
# cuando el OPERADOR vuelve a pedir lo mismo (significa que la respuesta no le sirvió); aplicada a una CAÍDA
# endurece el encargo justo cuando hay que retomarlo, y con el mismo reloj.
def test_a_crash_resume_inherits_the_brief_instead_of_opening_a_harder_round(fresh_db):
    import asyncio

    from nucleo.flash import escalate

    calls = []

    async def _run():
        orig = escalate.escalate_to_slowbrain
        escalate.escalate_to_slowbrain = lambda req, context=None: calls.append((req, context or {})) or 1
        try:
            R.remember([_live(id="7")])
            R.at_boot(delay=0.0)
            for _ in range(50):
                await asyncio.sleep(0.01)
                if calls:
                    break
        finally:
            escalate.escalate_to_slowbrain = orig

    asyncio.run(_run())
    _, ctx = calls[0]
    # la vía YA PREVISTA para esto: `_compose_brief` reutiliza el brief tal cual si le llega su task de origen
    assert ctx["resume"]["brief_task"] == "7", "sin el brief de origen, el objetivo casa por parecido y EXPANDE"


def test_the_brief_of_the_dead_task_is_the_one_reused(fresh_db):
    """La costura completa: el brief guardado por la tarea muerta es el que recoge la reanudación — misma ronda,
    misma amplitud, mismos criterios. Un cambio de criterios a mitad de una búsqueda que el operador cree que
    sigue el mismo guion es peor que empezar de cero."""
    import asyncio

    from nucleo import dispatch, research

    brief = {"goal": "veleros de 42 a 49 pies hasta 50.000 €", "hard": ["≤ 50.000 €"], "round": 1,
             "breadth": {"min_candidates": 40, "angles": []}, "deliverable": {"widget": "results", "n_final": 10}}
    research.save("7", brief)
    research.remember_round(dispatch._goal_key(VELEROS), brief)   # el cebo que provocaba la ronda 2

    out = asyncio.run(dispatch._compose_brief(VELEROS, "", True, {"brief_task": "7"}))
    assert out["round"] == 1, f"reanudar no sube de ronda (salió {out.get('round')})"
    assert (out["breadth"] or {})["min_candidates"] == 40, "ni endurece la amplitud"
    assert out["deliverable"]["n_final"] == 10
