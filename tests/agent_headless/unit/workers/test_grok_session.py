"""El backend `grok_build` (Grok Build CLI) — V2-038, 2026-08-13.

Grok Build emite el MISMO wire format que Claude Code, así que `GrokSession` HEREDA la traducción entera y solo
sobrescribe su vocabulario. Lo que se prueba aquí es exactamente eso: que la herencia no se rompa y que las tres
diferencias reales (nombres de tools, argumentos, envoltorio de la evidencia) queden traducidas.

Todas las formas de este fichero son REALES, capturadas sondeando `grok` 1.0.3 contra la cuenta del operador.
"""
import pathlib

import pytest

from nucleo.workers.base import WorkerSpec
from nucleo.workers.claude_session import _BRIDGE_TOOLS
from nucleo.workers.grok_session import GrokSession, _translate, _unwrap_evidence


def _map(obj):
    s = object.__new__(GrokSession)
    s._task_id, s._model, s._native_sid = "7", "grok-4.5", ""
    s._done = False
    s._steps_by_id, s._last_step = {}, {}
    return list(s._map(obj))


# ── la HERENCIA: el mismo wire format se traduce sin tocar el mapper ───────────────────────────────────────
def test_init_and_result_come_through_the_inherited_mapper():
    evs = _map({"type": "system", "subtype": "init", "session_id": "019ffa23-7b1e-7ed3-8c60-9542078d9a1c",
                "model": "grok-4.5", "permissionMode": "acceptEdits"})
    assert [e.type for e in evs] == ["spawned"]
    assert evs[0].data["native_session_id"] == "019ffa23-7b1e-7ed3-8c60-9542078d9a1c"

    evs = _map({"type": "result", "subtype": "success", "is_error": False, "result": "3",
                "total_cost_usd": 0.0380156,
                "usage": {"input_tokens": 17971, "output_tokens": 96, "cache_read_input_tokens": 4992}})
    res = next(e for e in evs if e.type == "result")
    assert res.data["ok"] is True and res.data["summary"] == "3"
    # tokens con los nombres que lee `session.py::_finish` para tarifar Energy, y el coste que reporta el CLI
    assert res.data["usage"]["input_tokens"] == 17971
    assert res.data["cost"] == pytest.approx(0.0380156)
    assert evs[-1].type == "done"


def test_a_grok_command_row_says_where_it_worked():
    """Su Bash se llama `run_terminal_command`: sin traducir el nombre, la fila caía al cajón «sistema» y un worker
    que consulta la memoria se veía igual que uno que borra un fichero."""
    evs = _map({"type": "assistant", "message": {"content": [{
        "type": "tool_use", "id": "call-1", "name": "run_terminal_command",
        "input": {"command": ".venv/bin/python -m nucleo.mem_cli recall 'velero'",
                  "description": "consulta memoria"}}]}})
    step = next(e for e in evs if e.type == "step")
    assert step.data["where"] == "memoria" and step.data["action"] == "recall"
    assert "velero" in step.data["target"]


def test_read_uses_target_file_not_path():
    """VERIFICADO en el CLI: `read_file` manda `target_file`. Con el nombre mal la fila salía con `target=''`, o sea
    el operador veía «lee» sin saber QUÉ lee — que es justo el dato que hace auditable el paso."""
    assert _translate("read_file", {"target_file": "informe.json"})[1]["file_path"] == "informe.json"
    evs = _map({"type": "assistant", "message": {"content": [{
        "type": "tool_use", "id": "c", "name": "read_file", "input": {"target_file": "widgets/agenda/data.py"}}]}})
    step = next(e for e in evs if e.type == "step")
    assert step.data["where"] == "archivo" and step.data["target"] == "agenda/data.py"


def test_thinking_is_never_a_row_nor_a_note():
    """Grok emite su razonamiento como bloque `thinking`. Es largo e interno: el panel muestra TRABAJO, no monólogo
    (y la firma criptográfica que lo acompaña no le dice nada a nadie)."""
    evs = _map({"type": "assistant", "message": {"content": [
        {"type": "thinking", "thinking": "El usuario quiere que cuente las líneas…", "signature": "abc123"},
        {"type": "text", "text": "Voy a contarlas."}]}})
    assert [e.type for e in evs] == ["note"]
    assert evs[0].data["text"] == "Voy a contarlas."


# ── la EVIDENCIA: cada tool la envuelve distinto ───────────────────────────────────────────────────────────
@pytest.mark.parametrize("raw,expect", [
    ('{"type":"Bash","output":[51,10],"output_for_prompt":"exit: 0\\n3\\n","exit_code":0}', "exit: 0\n3\n"),
    ('{"type":"ReadFile","FileContent":{"content":"1-alfa\\nbeta\\n","absolute_path":"/x/y"}}', "1-alfa\nbeta\n"),
    ('{"type":"GrepSearch","stdout":[104,111,108,97],"match_count":1}', "hola"),
])
def test_evidence_is_unwrapped_per_tool(raw, expect):
    """Sin desenvolver, la fila enseñaba el SOBRE (rutas de log, bytes, flags) en vez de la carta. El grep era el
    peor: su `stdout` llega como LISTA DE BYTES y se pintaba «[60,119,111,114,…]», ilegible."""
    assert _unwrap_evidence(raw) == expect


def test_a_denied_tool_keeps_its_policy_message_intact():
    """Es la PRUEBA de que la contención funcionó: si se recorta o se pierde, un intento bloqueado se vuelve
    indistinguible de un paso que no ocurrió."""
    got = _unwrap_evidence([{"type": "content", "content": {
        "type": "text", "text": 'Tool `run_terminal_command` was not executed: Denied by permission policy: '
                                'deny rule on bash matching "whoami"'}}])
    assert got == ['Tool `run_terminal_command` was not executed: Denied by permission policy: '
                   'deny rule on bash matching "whoami"']


def test_unknown_tool_falls_back_without_raising():
    """Una tool nueva del CLI no puede romper nada. Y su evidencia se devuelve CRUDA a propósito: si el campo del
    cuerpo no se reconoce, mejor enseñar el JSON entero (feo pero auditable) que devolver vacío y perder la prueba."""
    assert _translate("alguna_tool_nueva", {"x": 1}) == ("alguna_tool_nueva", {"x": 1})
    assert _unwrap_evidence('{"type":"CosaNueva","algo":"valor"}') == '{"type":"CosaNueva","algo":"valor"}'
    # pero si trae un campo de cuerpo CONOCIDO, se desenvuelve aunque la tool no esté sondeada
    assert _unwrap_evidence('{"type":"CosaNueva","output_for_prompt":"valor"}') == "valor"
    assert _unwrap_evidence("texto pelado") == "texto pelado"


# ── CONTENCIÓN: Grok sí puede sostener el invariante del escritor único ────────────────────────────────────
def test_the_prompt_goes_by_file_never_by_stdin_dash():
    """`grok -p -` NO lee stdin: toma el `-` como prompt literal y el nuestro se pierde SIN ERROR — el CLI arranca
    con un prompt sin sentido y el modelo hace algo razonable por su cuenta. Medido: 447.559 tokens de entrada y
    $0,73 explorando el repo cuando se le había pedido imprimir una versión; con el prompt bien entregado, $0,005.
    Este guard existe porque la avería es CARA y MUDA."""
    src = pathlib.Path(__file__).resolve().parents[4] / "nucleo" / "workers" / "grok_session.py"
    code = "\n".join(ln for ln in src.read_text(encoding="utf-8").splitlines()
                     if not ln.lstrip().startswith("#"))
    assert '"--prompt-file"' in code
    assert '"-p", "-"' not in code


def test_bash_stays_pinned_to_the_bridges():
    """La lista de reglas es LITERALMENTE `_BRIDGE_TOOLS` de claude_session (fuente única). Un backend que se
    inventara su propia lista se desincronizaría del intérprete real en el primer cambio, y el worker se pondría a
    hacer arqueología de permisos en vez de la tarea."""
    src = pathlib.Path(__file__).resolve().parents[4] / "nucleo" / "workers" / "grok_session.py"
    code = src.read_text(encoding="utf-8")
    assert "_BRIDGE_TOOLS" in code
    assert '"--allow"' in code
    assert "dangerously" not in code and "bypassPermissions" not in code
    assert any("mem_cli" in r for r in _BRIDGE_TOOLS)          # la fuente única sigue trayendo los puentes


def test_registry_sends_untrusted_work_to_grok_because_it_can_contain_it(monkeypatch):
    """A diferencia de Codex, Grok NO se desvía a claude_code: acepta `--deny` y lo aplica (probado contra el CLI),
    así que puede correr una tarea de entrada no confiable con las tools apagadas."""
    from nucleo.workers import registry
    monkeypatch.setenv("WORKER_BACKEND", "")
    monkeypatch.setattr(registry, "_provider_for", lambda kind: "grok_build")
    assert registry.get_backend(WorkerSpec(kind="web")).name == "grok_build"
    assert registry.get_backend(WorkerSpec(kind="web", deny_tools=True)).name == "grok_build"
