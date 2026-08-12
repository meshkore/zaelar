"""El backend `codex` traduce el JSONL de Codex al vocabulario normalizado `WorkerEvent` (V2-038).

Hasta el 2026-08-12 este backend era un STUB: si el operador ponía el proveedor a `codex` se quedaba sin Brain
Workers y el síntoma era una tarea que moría al instante, no un mensaje de configuración. Los objetos de este
fichero son trazas REALES capturadas del CLI (`codex exec --json`, v0.137.0), no inventadas — un mapper probado
contra un protocolo imaginado no prueba nada.

Se prueba la TRADUCCIÓN pura (sin procesos ni colas, con `object.__new__` como el test del mapper de Claude Code)
y la postura FAIL-CLOSED, que es la parte con consecuencias de seguridad.
"""
import asyncio

import pytest

from nucleo.workers.base import WorkerSpec
from nucleo.workers.codex_session import CodexSession


def _map(obj):
    s = object.__new__(CodexSession)
    s._task_id = "42"
    s._native_sid = ""
    s._model = "gpt-5.5"
    s._done = False
    s._last_message = ""
    s._usage = {}
    s._failed = ""
    return list(s._map(obj))


# ── traducción del protocolo (trazas reales) ──────────────────────────────────────────────────────────────
def test_thread_started_captures_the_id_used_to_resume():
    """`thread_id` es lo ÚNICO con lo que se reanuda un worker de Codex (`exec resume <id>`). Sin capturarlo, la
    continuidad de V2-049 no existe: cada reintento re-navegaría y re-teclearía todo lo ya hecho."""
    evs = _map({"type": "thread.started", "thread_id": "019ff785-bbe7-77b3-8313-980ef00a6189"})
    assert len(evs) == 1 and evs[0].type == "spawned"
    assert evs[0].data["native_session_id"] == "019ff785-bbe7-77b3-8313-980ef00a6189"
    assert evs[0].task_id == "42"


def test_command_execution_becomes_a_step_and_then_its_evidence():
    started = _map({"type": "item.started", "item": {
        "id": "item_0", "type": "command_execution", "command": "/bin/zsh -lc 'wc -l < datos.txt'",
        "aggregated_output": "", "exit_code": None, "status": "in_progress"}})
    steps = [e for e in started if e.type == "step"]
    assert len(steps) == 1
    # el envoltorio del shell (`/bin/zsh -lc '…'`) no se pinta: ocupa la fila entera y no dice nada
    assert steps[0].data["target"] == "wc -l < datos.txt"
    assert steps[0].data["where"] == "sistema"

    done = _map({"type": "item.completed", "item": {
        "id": "item_0", "type": "command_execution", "command": "/bin/zsh -lc 'wc -l < datos.txt'",
        "aggregated_output": "       2\n", "exit_code": 0, "status": "completed"}})
    res = [e for e in done if e.type == "step_result"]
    assert len(res) == 1 and "2" in res[0].data["text"]
    assert res[0].data["is_error"] is False


def test_a_failed_command_is_marked_as_an_error_result():
    """La EVIDENCIA tiene que distinguir un paso que trajo el dato de uno que falló: sin eso, un worker que trae
    basura deja el mismo rastro que uno que acierta (el hallazgo del 2026-08-10)."""
    evs = _map({"type": "item.completed", "item": {
        "type": "command_execution", "command": "/bin/zsh -lc 'cat nope'",
        "aggregated_output": "cat: nope: No such file or directory\n", "exit_code": 1, "status": "completed"}})
    res = [e for e in evs if e.type == "step_result"]
    assert len(res) == 1 and res[0].data["is_error"] is True


def test_bridge_commands_are_attributed_to_their_own_place():
    """Un comando que ES un puente pertenece a la memoria / al navegador / a zaelar, no a «sistema» — si no, TODO
    el trabajo de un worker de Codex se ve como un montón indistinguible de comandos."""
    for cmd, where in ((".venv/bin/python -m nucleo.mem_cli recall 'coche'", "memoria"),
                       ("python3 -m nucleo.nav_cli navigate https://example.com", "navegador"),
                       ("python3 -m nucleo.widget_cli read agenda", "widget"),
                       ("python3 -m nucleo.worker_bridge ask '¿sigo?'", "zaelar")):
        evs = _map({"type": "item.started", "item": {"type": "command_execution", "command": cmd}})
        steps = [e for e in evs if e.type == "step"]
        assert steps and steps[0].data["where"] == where, cmd


def test_hbnote_does_not_produce_a_row():
    """`agent_report` fija su propia fase, más rica que cualquiera que derivemos — duplicarla es ruido."""
    evs = _map({"type": "item.started", "item": {
        "type": "command_execution", "command": "python3 -m nucleo.agent_report phase 'leyendo fichas'"}})
    assert not [e for e in evs if e.type in ("step", "phase")]


def test_agent_message_is_narration_and_the_last_one_is_the_result():
    s = object.__new__(CodexSession)
    s._task_id, s._model, s._native_sid = "42", "gpt-5.5", ""
    s._done, s._last_message, s._usage, s._failed = False, "", {}, ""
    notes = list(s._map({"type": "item.completed", "item": {"type": "agent_message", "text": "Voy a leerlo."}}))
    assert [e.type for e in notes] == ["note"]              # narración, NUNCA `say` (no se habla por voz)
    list(s._map({"type": "item.completed", "item": {"type": "agent_message", "text": "Son 2 líneas."}}))
    evs = list(s._map({"type": "turn.completed",
                       "usage": {"input_tokens": 28294, "cached_input_tokens": 16128, "output_tokens": 89}}))
    result = next(e for e in evs if e.type == "result")
    assert result.data["summary"] == "Son 2 líneas."         # el ÚLTIMO mensaje es la entrega
    assert result.data["ok"] is True
    # los tokens llegan con los nombres que `session.py::_finish` lee para tarifar Energy — un worker que trabaja
    # y no metera es dinero perdido en silencio (el agujero que cerró el metering de 2026-08-05).
    assert result.data["usage"]["input_tokens"] == 28294
    assert result.data["usage"]["output_tokens"] == 89
    assert evs[-1].type == "done"


def test_reasoning_is_not_a_row():
    assert not _map({"type": "item.completed", "item": {"type": "reasoning", "text": "x" * 500}})


def test_an_unknown_item_type_never_raises():
    """El CLI puede estrenar tipos de item en cualquier versión: uno desconocido no puede tumbar el stream de una
    sesión viva (que es lo que pasa si el mapper lanza)."""
    assert _map({"type": "item.completed", "item": {"type": "quantum_thing", "wat": 1}}) == []
    assert _map({"type": "algo.que.no.existe"}) == []


def test_turn_failed_is_a_fatal_error():
    evs = _map({"type": "turn.failed", "error": {"message": "model not available for this account"}})
    errs = [e for e in evs if e.type == "error"]
    assert len(errs) == 1 and errs[0].data["fatal"] is True
    assert "model not available" in errs[0].data["message"]


# ── postura FAIL-CLOSED (la parte con consecuencias) ──────────────────────────────────────────────────────
def _start(**kw):
    s = CodexSession()
    spec = WorkerSpec(**kw)
    asyncio.run(s.start("haz algo", spec=spec))
    evs = []
    while not s._q.empty():
        evs.append(s._q.get_nowait())
    return evs


@pytest.mark.parametrize("kw,why", [
    ({"kind": "web", "deny_tools": True}, "entrada no confiable"),
    ({"kind": "dev"}, "worker de desarrollo"),
])
def test_codex_refuses_the_tasks_whose_containment_it_cannot_express(kw, why):
    """Claude Code acota `Bash` a nuestros puentes (el invariante del ESCRITOR ÚNICO de la memoria). Codex no tiene
    ese eje —solo modos de sandbox— y headless necesita `workspace-write`, o sea un shell completo. Las dos tareas
    que EXISTEN para estar acotadas (entrada no confiable V2-010 y el dev worker de un peer de cluster) tienen que
    ser RECHAZADAS aquí, no corridas con menos contención de la que el llamador pidió.

    Este test es la guardia de esa decisión: si alguien la afloja, salta."""
    evs = _start(**kw)
    errs = [e for e in evs if e.type == "error"]
    assert errs and errs[0].data["fatal"] is True
    # y tiene que DECIR a qué backend ir: un «no puedo» sin salida deja al operador sin workers y sin pista
    assert "claude_code" in errs[0].data["message"]
    assert evs[-1].type == "done"                      # cierra limpio, no deja la sesión esperando


def test_the_bypass_flag_is_never_used():
    """`--dangerously-bypass-approvals-and-sandbox` apaga el sandbox de Codex por completo. No lo necesitamos
    (verificado: con `workspace-write` ya ejecuta sin pedir aprobación en headless) y no puede colarse."""
    import ast
    from pathlib import Path
    src = Path(__file__).resolve().parents[4] / "nucleo" / "workers" / "codex_session.py"
    tree = ast.parse(src.read_text(encoding="utf-8"))
    # Se mira el CÓDIGO EJECUTABLE, no la prosa: la cabecera del módulo nombra el flag justo para explicar por qué
    # no se usa, y un guard que se rompiera por documentar la decisión enseñaría a borrar la explicación.
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) \
                and ast.get_docstring(node):
            node.body = node.body[1:]
    code = ast.unparse(tree)
    assert "dangerously-bypass" not in code
    assert "danger-full-access" not in code


def test_stderr_noise_is_not_reported_as_the_cause_of_death():
    """Un CLI viejo escupe `failed to load models cache` en CADA invocación. Devolver eso como el motivo del fallo
    manda al operador a mirar el sitio equivocado."""
    from nucleo.workers.codex_session import _stderr_reason
    blob = (b"2026-08-12T19:59:47Z ERROR codex_models_manager::cache: failed to load models cache: unknown variant\n"
            b"2026-08-12T19:59:48Z ERROR codex_models_manager::manager: failed to refresh available models\n"
            b"stream error: 401 Unauthorized\n")
    assert _stderr_reason(blob) == "stream error: 401 Unauthorized"


# ── enrutado por CAPACIDAD (registry) ─────────────────────────────────────────────────────────────────────
def test_registry_routes_the_contained_tasks_to_claude_code_even_with_codex_configured(monkeypatch):
    """Elegir Codex para el trabajo normal NO puede costarle al operador las capacidades del cluster ni la
    protección ante entrada no confiable, ni de forma visible (tarea fallida) ni invisible (worker con shell
    abierto). El registro las enruta al backend que SÍ puede acotarse."""
    from nucleo.workers import registry
    from nucleo.workers.claude_session import ClaudeCodeSession
    monkeypatch.setenv("WORKER_BACKEND", "")
    monkeypatch.setattr(registry, "_provider_for", lambda kind: "codex")

    assert isinstance(registry.get_backend(WorkerSpec(kind="web", deny_tools=True)), ClaudeCodeSession)
    assert isinstance(registry.get_backend(WorkerSpec(kind="dev")), ClaudeCodeSession)
    # y el trabajo normal SÍ va a Codex, que es lo que el operador eligió
    assert isinstance(registry.get_backend(WorkerSpec(kind="web")), CodexSession)
