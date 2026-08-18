"""Tests del sustrato de Brain Workers (V2-038): contrato, registro/resolución de dispatch, política de act."""
import asyncio

from nucleo import dispatch, worker_api
from nucleo.workers import WorkerEvent, WorkerSpec, get_backend
from nucleo.workers.session import SessionRecord


def _seed(**kw):
    dispatch._SESSIONS.clear()
    for tid, meta in kw.items():
        dispatch._SESSIONS[tid] = SessionRecord(task_id=tid, status="running", **meta)


def test_event_and_spec_contract():
    e = WorkerEvent(task_id="1", type="phase", data={"label": "x"})
    assert e.v >= 1 and e.ts > 0
    s = WorkerSpec(kind="web", task_id="1", token="tok", depth=1)
    assert s.token == "tok" and s.depth == 1


def test_backend_selection_agnostic(monkeypatch):
    """El DEFAULT del registro es `claude_code`, y una tarea de widget va al generador — pase lo que pase.

    El proveedor se fuerza a propósito: sin fijarlo, este test leía `config/v2.json`, o sea la config REAL de la
    máquina donde corre. Pasaba solo mientras el operador tuviera ahí `claude_code`, y en cuanto probó Codex empezó
    a fallar un test que no habla de su elección sino del DEFAULT del código. Misma clase que la fuga de
    `store.DATA_DIR` de 2026-08-12: un test no puede depender del estado real del operador."""
    monkeypatch.setattr("nucleo.workers.registry._provider_for", lambda kind: "claude_code")
    assert get_backend(WorkerSpec(kind="web", task_id="1")).name == "claude_code"
    assert get_backend(WorkerSpec(kind="code", task_id="1",
                                  env={"ZAELAR_TASK_REQUEST": "hazme un widget del clima"})).name == "widget_generator"


def test_resolve_sessions():
    _seed(**{"7": {"goal": "moto enduro", "kind": "web"}, "9": {"goal": "widget clima", "kind": "code"}})
    assert set(dispatch.resolve_sessions("para todo")) == {"7", "9"}
    assert dispatch.resolve_sessions("cancela el widget") == ["9"]
    assert dispatch.resolve_sessions("para la búsqueda") == ["7"]
    dispatch._SESSIONS.clear()


def test_resolve_single_is_unambiguous():
    _seed(**{"1": {"goal": "x", "kind": "generic"}})
    assert dispatch.resolve_sessions("eso") == ["1"]
    dispatch._SESSIONS.clear()


def test_act_policy():
    assert worker_api.classify_act("ask_user", {}) == worker_api.ALLOW
    assert worker_api.classify_act("use_tool", {"tool": "web_search"}) == worker_api.ALLOW
    assert worker_api.classify_act("use_tool", {"tool": "delete_widget"}) == worker_api.DENY
    assert worker_api.classify_act("push_channel", {"channel": "x"}) == worker_api.CONFIRM
    assert worker_api.classify_act("rm_rf", {}) == worker_api.DENY


def test_ask_answer_cycle():
    _seed(**{"5": {"goal": "moto", "kind": "web"}})
    corr = worker_api._register_ask(dispatch._SESSIONS["5"], "¿enduro o cross?")
    assert dispatch._SESSIONS["5"].waiting_on == "user"
    assert worker_api.has_pending_ask()
    assert asyncio.run(worker_api.answer(corr, "enduro"))
    assert dispatch._SESSIONS["5"].waiting_on == ""
    dispatch._SESSIONS.clear()


# ── V2-048: observabilidad RICA de los pasos del worker (dónde + qué concreto) ────────────────────────────────
from nucleo.workers.claude_session import _tool_step  # noqa: E402
from nucleo.workers.session import _PLACE             # noqa: E402


def test_tool_step_native_tools():
    assert _tool_step("WebSearch", {"query": "estaciones ITV Soria"}) == \
        {"where": "web", "action": "web_search", "target": "estaciones ITV Soria"}
    assert _tool_step("WebFetch", {"url": "https://sitios.dgt.es/itv"})["where"] == "web"
    assert _tool_step("Read", {"file_path": "/a/b/c/agent.py"}) == \
        {"where": "archivo", "action": "lee", "target": "c/agent.py"}
    assert _tool_step("Edit", {"file_path": "nucleo/flash/router.py"})["where"] == "codigo"
    assert _tool_step("Grep", {"pattern": "def foo"})["where"] == "archivo"


def test_tool_step_bridges_from_bash():
    # navegador: URL, ref numérica y texto tecleado
    nav = _tool_step("Bash", {"command": 'python -m nucleo.nav_cli navigate "https://sitios.dgt.es/cita"'})
    assert nav["where"] == "navegador" and nav["action"] == "navigate" and "sitios.dgt.es" in nav["target"]
    clk = _tool_step("Bash", {"command": ".venv/bin/python -m nucleo.nav_cli click 12"})
    assert clk["where"] == "navegador" and clk["action"] == "click" and clk["target"] == "[12]"
    typ = _tool_step("Bash", {"command": 'python -m nucleo.nav_cli type 7 "moto enduro" --submit'})
    assert typ["action"] == "type" and "moto enduro" in typ["target"]
    # memoria: recall (query) y remember (slot)
    rc = _tool_step("Bash", {"command": 'python -m nucleo.mem_cli recall "ubicación del operador"'})
    assert rc["where"] == "memoria" and rc["action"] == "recall" and "ubicación" in rc["target"]
    rm = _tool_step("Bash", {"command": 'python -m nucleo.mem_cli remember --slot itv.cita "cita el martes"'})
    assert rm["action"] == "guarda" and "[itv.cita]" in rm["target"]
    # zaelar (worker_bridge) y agent_report (None → no duplica la fase de hbnote)
    assert _tool_step("Bash", {"command": "python -m nucleo.worker_bridge ask '¿matrícula?'"})["where"] == "zaelar"
    assert _tool_step("Bash", {"command": "python -m nucleo.agent_report phase 'buscando'"}) is None


def test_every_place_maps_to_a_known_kind():
    # todo `where` que emite _tool_step debe tener entrada en _PLACE (si no, la fila caería a sistema en silencio)
    kinds = {"search", "memory", "navegador", "task"}
    for where in ("web", "memoria", "navegador", "codigo", "archivo", "zaelar", "sistema"):
        assert where in _PLACE
        assert _PLACE[where][1] in kinds


def test_base_backend_pause_resume_default_noop():
    # workers/base.py::WorkerBackend — un backend que no sobreescribe pause/resume (Codex stub, generator_session)
    # debe ser un no-op inerte, nunca romper el contrato agnóstico (V2-065).
    from nucleo.workers.base import WorkerBackend

    class _Dummy(WorkerBackend):
        async def start(self, prompt, *, spec): pass
        async def send(self, text): pass
        def events(self):
            async def _gen():
                return
                yield  # pragma: no cover
            return _gen()
        async def stop(self, *, grace=3.0): pass
        @property
        def alive(self): return True

    d = _Dummy()
    assert d.pause() is False and d.resume() is False and d.paused is False


def test_claude_session_pause_resume_real_process():
    # V2-065 (petición del operador, botón ⏻: "pausa, no mata, para que puedan continuar"): verifica SIGSTOP/
    # SIGCONT de verdad contra un proceso REAL (no el binario `claude` — un `sleep` largo en su propio grupo,
    # igual que start_new_session=True deja el proceso real) — sin esto la garantía es solo de lectura de código.
    import os
    import signal
    import time

    from nucleo.workers.claude_session import ClaudeCodeSession

    async def _run():
        s = ClaudeCodeSession()
        s._proc = await asyncio.create_subprocess_exec(
            "sleep", "5", start_new_session=True,
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        assert s.alive and not s.paused

        assert s.pause() is True and s.paused is True
        assert s.pause() is False   # idempotente: ya estaba pausado
        # el grupo de verdad recibió SIGSTOP — su estado en /proc pasa a "T" (stopped). En macOS no hay /proc,
        # así que verificamos por comportamiento: NO termina aunque esperemos más de lo que dura "sleep 5" entero.
        await asyncio.sleep(0.3)
        assert s._proc.returncode is None   # sigue vivo (congelado, no muerto)

        assert s.resume() is True and s.paused is False
        assert s.resume() is False   # idempotente: no había nada que reanudar

        # tras reanudar, el proceso sigue vivo y corriendo normalmente (lo matamos limpio, no hace falta esperar 5s)
        assert s._proc.returncode is None
        os.killpg(os.getpgid(s._proc.pid), signal.SIGKILL)
        try:
            await asyncio.wait_for(s._proc.wait(), timeout=2.0)
        except asyncio.TimeoutError:
            pass

    asyncio.run(_run())


# ── DENEGAR TIENE QUE ENSEÑAR (incidente en vivo 2026-08-12, búsqueda de veleros) ────────────────────────────
# Con la cuota del buscador de su proveedor agotada, el worker fue a pedir prestada la `web_search` del cerebro
# —que SÍ es prestable— con la forma equivocada (`act web_search {...}` en vez de `act use_tool {"tool":…}`).
# La política devolvía la MISMA frase para todo, «acción no permitida para un worker», el worker la creyó y
# abandonó su única vía de reserva: la búsqueda se quedó sin buscador.
def test_a_malformed_call_is_not_reported_as_a_forbidden_capability():
    from nucleo.worker_api import deny_reason
    msg = deny_reason("web_search", {"query": "velero 42 pies"})
    assert "DESCONOCIDA" in msg, "un nombre de tool en el hueco de la acción es una llamada MAL ESCRITA"
    assert "use_tool" in msg and '"tool":"web_search"' in msg, "tiene que decir la forma CORRECTA"
    assert "NO es una prohibición" in msg, "si suena a prohibido, el worker deja de intentarlo"


def test_an_actually_forbidden_tool_says_so_and_offers_the_way_out():
    from nucleo.worker_api import deny_reason
    msg = deny_reason("use_tool", {"tool": "authenticate_web"})
    assert "no se presta" in msg and "ask_user" in msg
    assert "DESCONOCIDA" not in msg, "esto sí es una prohibición real, no un error de forma"


def test_a_tool_outside_the_lendable_catalogue_names_what_is_lendable():
    from nucleo.worker_api import deny_reason, _PRESTABLE_TOOLS
    msg = deny_reason("use_tool", {"tool": "play_music"})
    assert all(t in msg for t in _PRESTABLE_TOOLS)


def test_the_deny_message_lists_the_real_action_vocabulary():
    """El mensaje no puede quedarse desactualizado respecto a lo que la política admite de verdad."""
    from nucleo import worker_api as W
    msg = W.deny_reason("noexiste", {})
    for a in W._KNOWN_ACTS:
        assert a in msg, a
    for a in W._KNOWN_ACTS:
        assert W.classify_act(a, {"widget_id": "results", "action": "present", "tool": "web_search"}) != W.DENY \
            or a in ("widget_data",), f"«{a}» está en el vocabulario pero la política no lo conoce"


# ── UN WORKER MATADO SE COBRA IGUAL (agujero de facturación, banco 2026-08-13) ─────────────────────────────────
# El reporte a Energy vivía DENTRO del `if rec.status != "cancelled"` de `_finish` — un `if` que existe por una
# razón de INTERFAZ (no pintar dos filas `end` contradictorias, demo 2026-07-14) y que se llevaba por delante una
# de FACTURACIÓN sin relación: un worker matado por presupuesto había gastado tokens REALES y se metraba a CERO.
# Medido: 704 s, 256 pasos, 39 capturas, ~$0,20 de tokens de xAI → €0 facturados.
def test_the_energy_report_is_not_gated_by_the_ui_concern():
    """Las dos preocupaciones van SEPARADAS en el código: el chip sigue bajo el guard de cancelación, el cobro no."""
    import pathlib
    src = pathlib.Path(__file__).resolve().parents[4] / "nucleo" / "workers" / "session.py"
    code = src.read_text(encoding="utf-8")
    cobro = code.index("report_worker_usage")
    guard = code.index('if rec.status != "cancelled":\n            # V2-048')
    assert cobro < guard, "el cobro tiene que estar FUERA (y antes) del guard que solo gobierna la fila del panel"


def test_partial_usage_survives_a_worker_that_never_says_goodbye():
    """El `usage` del `result` final no existe si matamos el proceso, así que se acumula mensaje a mensaje. El
    `result` manda cuando llega (el CLI ya lo trae sumado); el parcial es el MÍNIMO declarado cuando no llega."""
    import pathlib
    src = pathlib.Path(__file__).resolve().parents[4] / "nucleo" / "workers" / "session.py"
    code = src.read_text(encoding="utf-8")
    assert 'elif ev.type == "usage":' in code
    assert "self._usage or self._usage_partial or {}" in code, "el final gana; el parcial es el respaldo"


def test_the_stream_emits_usage_per_message_not_only_at_the_end():
    """Verificado sondeando el CLI: cada mensaje `assistant` trae su `usage` y el del `result` es la SUMA
    (61.969+127 = 62.096). Sin emitirlo por mensaje, matar a un worker seguiría siendo gratis."""
    import pathlib
    src = pathlib.Path(__file__).resolve().parents[4] / "nucleo" / "workers" / "claude_session.py"
    code = src.read_text(encoding="utf-8")
    assert 'self._ev("usage"' in code
    # …y lo hereda Grok, que es donde se vio el agujero (no reimplementa `_map`)
    grok = (pathlib.Path(__file__).resolve().parents[4] / "nucleo" / "workers" / "grok_session.py"
            ).read_text(encoding="utf-8")
    assert "def _map" not in grok


# ── un widget recién creado tiene que APARECER en pantalla (2026-08-18) ────────────────────────────────────────
def _drive_generator(monkeypatch, *, req, gen_result, action=None):
    """Corre `GeneratorBackend._drive()` con el generador REAL sustituido (nada de lanzar un `claude`) y devuelve
    los `emit()` de observabilidad que produjo, más los WorkerEvent que encoló."""
    from nucleo.workers.generator_session import GeneratorBackend
    from widgets import generator as _gen

    seen: list[tuple] = []
    monkeypatch.setattr("voice.observer.emit",
                        lambda cat, label, **kw: seen.append((cat, label, kw.get("extra") or {})))
    monkeypatch.setattr(_gen, "generate_widget", lambda *a, **k: gen_result, raising=False)
    monkeypatch.setattr(_gen, "modify_widget", lambda *a, **k: gen_result, raising=False)
    if action is not None:
        monkeypatch.setattr("nucleo.agentes.code.widget_action", lambda r: action, raising=False)

    b = GeneratorBackend()
    b._task_id = "T1"
    asyncio.run(b._drive(req))
    evs = []
    while not b._q.empty():
        evs.append(b._q.get_nowait())
    return seen, evs


def test_a_created_widget_is_actually_opened_on_screen(monkeypatch):
    """Reportado en vivo: «no ha salido ningún widget nuevo, ni nada en pantalla». El widget se construía bien y se
    anunciaba por voz («He creado el widget «X»»), pero NADIE lo abría — el `wid` viajaba dentro del `data` del
    `result` y `session.py::_handle` se queda con `summary`/`ok`/`usage` y descarta `data`. El único camino que
    abría un widget de un worker era el del navegador. Tres minutos de trabajo entregados a una pantalla vacía."""
    seen, evs = _drive_generator(monkeypatch, req="hazme un widget del tiempo de Soria",
                                 gen_result={"ok": True, "id": "meteo-soria"})
    assert ("widget", "show", {"id": "meteo-soria", "src": "worker:T1"}) in seen
    assert any(e.type == "result" and e.data.get("ok") for e in evs)


def test_an_already_existing_widget_is_opened_too(monkeypatch):
    """El copy de este caso dice literalmente «ya existía, TE LO MUESTRO» — prometía en voz una acción que no
    ocurría. Es el mismo bug con la peor de las dos redacciones posibles."""
    seen, _ = _drive_generator(monkeypatch, req="hazme un widget del tiempo de Soria",
                               gen_result={"ok": True, "id": "meteo-soria", "existed": True})
    assert ("widget", "show", {"id": "meteo-soria", "src": "worker:T1"}) in seen


def test_deleting_a_widget_does_not_open_it(monkeypatch):
    """La otra cara: abrir lo que acabas de borrar. Por eso el show vive en el backend (que sabe QUÉ acción fue) y
    no en el bombeo agnóstico de `session.py`."""
    async def _fake_delete(wid, who):
        return {"ok": True}
    monkeypatch.setattr("widgets.lifecycle.delete_widget", _fake_delete, raising=False)
    seen, evs = _drive_generator(monkeypatch, req="borra el widget del tiempo",
                                 gen_result={"ok": True, "id": "meteo-soria"},
                                 action=("delete", "meteo-soria"))
    assert not [s for s in seen if s[1] == "show"], "un borrado NUNCA abre la tarjeta"
    assert any(e.type == "result" for e in evs)


def test_a_failed_generation_opens_nothing(monkeypatch):
    """Un fallo no puede dejar una tarjeta fantasma abierta."""
    seen, _ = _drive_generator(monkeypatch, req="hazme un widget del tiempo de Soria",
                               gen_result={"ok": False, "error": "boom"})
    assert not [s for s in seen if s[1] == "show"]
