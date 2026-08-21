"""Losing the instrument is not a finding about the product, and the ledger cannot tell them apart.

2026-08-21: both paid rungs of the tester were down AT THE SAME TIME — Z.AI out of quota until the 25th and
a network outage that left DeepSeek direct on `Connection error` — and the walk spent hours printing «EL
CEREBRO NO PUEDE HABLAR» without measuring a single case. A subscription rung cannot fail that way, so the
local Claude Code licence is the net under both the DRIVE and the JUDGE.

The operator's separation (2026-08-21) is what these tests pin: the Brain WORKERS keep running DeepSeek/GLM
because that is what the cloud has, and measuring the product with a chain the product does not use measures
something else. What may run on any model — Anthropic included — is the TESTER: who plays the person and who
scores the round.

The trap this file mostly exists for is #4: the engine redirects THIS SAME CLI to Z.AI/DeepSeek through
`ANTHROPIC_*`. A licence rung that inherits those variables is the rung that just fell over, wearing a new
name in the ledger.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from tests.use_cases.e2e.agent import llm  # noqa: E402


@pytest.fixture
def spawned(monkeypatch):
    """Captures the subprocess the licence rung WOULD have run. It never runs it: a unit test that shelled
    out to `claude` would bill the operator's licence and take seven seconds per case."""
    calls: list[dict] = []

    class _R:
        returncode = 0
        stdout = "respuesta de la licencia"
        stderr = ""

    def _run(argv, cwd=None, env=None, capture_output=False, text=False, timeout=None):
        calls.append({"argv": argv, "cwd": cwd, "env": env})
        return _R()

    import subprocess
    monkeypatch.setattr(subprocess, "run", _run)
    return calls


def _all_paid_rungs_down(monkeypatch):
    def _boom(*a, **k):
        raise RuntimeError("Connection error")
    monkeypatch.setattr(llm, "_deepseek_direct", _boom)
    monkeypatch.setattr(llm, "_call", _boom)
    monkeypatch.setattr(llm, "glm_call", _boom)
    monkeypatch.setattr(llm.time, "sleep", lambda _s: None)   # los reintentos no cuestan minutos aquí


# ── El relevo ocurre, y se declara ────────────────────────────────────────────────────────────────────


def test_when_every_paid_rung_is_out_the_licence_drives(monkeypatch):
    _all_paid_rungs_down(monkeypatch)
    monkeypatch.setattr(llm, "_claude_licence", lambda m, **k: "sigo siendo la persona")
    assert llm.call([{"role": "user", "content": "hola"}]) == "sigo siendo la persona"


def test_the_relay_is_STAMPED(monkeypatch):
    """Un relevo silencioso deja el tablero avanzando con dos instrumentos y sin saber qué fila usó cuál.
    La licencia es un modelo distinto: sus notas no son comparables con las de DeepSeek sin decirlo."""
    _all_paid_rungs_down(monkeypatch)
    monkeypatch.setattr(llm, "_claude_licence", lambda m, **k: "x")
    llm.call([{"role": "user", "content": "hola"}])
    assert llm.drive_model() == "licencia-claude"


def test_the_licence_is_NOT_used_while_a_paid_rung_answers(monkeypatch):
    """Sensibilidad, y es el lado que cuesta dinero: la licencia va la última porque consume el forfait del
    operador. Sin este caso, «hay red debajo» y «siempre corre por la red» pasan igual de verdes."""
    monkeypatch.setattr(llm, "_deepseek_direct", lambda *a, **k: "titular")
    monkeypatch.setattr(llm, "_claude_licence", lambda m, **k: pytest.fail("la licencia no debía correr"))
    assert llm.call([{"role": "user", "content": "hola"}]) == "titular"
    assert llm.drive_model() == "deepseek-directo"


def test_the_forced_hatch_pins_the_licence(monkeypatch):
    """La escotilla manual: medir un brazo concreto sin que un fallo lo releve por detrás."""
    monkeypatch.setenv("ZAELAR_UC_DRIVE", "claude")
    monkeypatch.setattr(llm, "_deepseek_direct", lambda *a, **k: pytest.fail("fijado a la licencia"))
    monkeypatch.setattr(llm, "_claude_licence", lambda m, **k: "fijada")
    assert llm.call([{"role": "user", "content": "hola"}]) == "fijada"
    assert llm.drive_model() == "licencia-claude"


# ── La licencia tiene que ser LA LICENCIA ─────────────────────────────────────────────────────────────


def test_the_licence_does_not_inherit_the_redirect(monkeypatch, spawned):
    """EL CASO QUE JUSTIFICA EL FICHERO. `ANTHROPIC_BASE_URL` y compañía son las variables con las que el
    motor manda este mismo CLI a Z.AI o a DeepSeek. Heredadas aquí, el «escalón de Anthropic» sería el
    escalón que se acaba de caer — y el sello de la ronda diría que hubo relevo cuando no lo hubo."""
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://api.z.ai/api/anthropic")
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "no-debe-viajar")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "tampoco")
    monkeypatch.setenv("PATH", "/usr/bin")            # el resto del entorno SÍ viaja: hace falta para ejecutar
    llm._claude_licence([{"role": "user", "content": "hola"}])
    env = spawned[0]["env"]
    assert "ANTHROPIC_BASE_URL" not in env and "ANTHROPIC_AUTH_TOKEN" not in env
    assert "ANTHROPIC_API_KEY" not in env
    assert env.get("PATH") == "/usr/bin", "se limpió el entorno entero en vez de las tres variables"


def test_the_licence_runs_from_a_NEUTRAL_directory(spawned):
    """El CLI carga el `CLAUDE.md` del cwd. Desde `engine/`, cada turno del conductor arrastraría el repo
    entero — V2-117 midió esa bomba en 167k tokens por petición — y, peor que el coste, un conductor que ha
    leído el código del motor deja de hacer de PERSONA que no sabe nada."""
    llm._claude_licence([{"role": "user", "content": "hola"}])
    cwd = Path(spawned[0]["cwd"])
    assert cwd.is_absolute()
    engine = Path(__file__).resolve().parents[3]
    assert engine not in cwd.parents and cwd != engine
    assert not (cwd / "CLAUDE.md").exists()


def test_no_mcp_server_is_loaded(spawned):
    """`--strict-mcp-config` sin `--mcp-config` deja el proceso sin un solo servidor MCP. Aquí se quiere un
    modelo que conteste una frase, no un agente con herramientas."""
    llm._claude_licence([{"role": "user", "content": "hola"}])
    assert "--strict-mcp-config" in spawned[0]["argv"]


def test_the_system_prompt_travels_and_the_roles_survive(spawned):
    """El conductor lleva su brief en el `system`, y la conversación anterior en los turnos. Aplanar sin
    decir quién habló convierte la negociación en un monólogo y el tester repite lo que ya dijo."""
    llm._claude_licence([{"role": "system", "content": "Haces de persona."},
                         {"role": "user", "content": "quiero un hotel"},
                         {"role": "assistant", "content": "¿en qué ciudad?"}])
    argv = spawned[0]["argv"]
    assert "--system-prompt" in argv and argv[argv.index("--system-prompt") + 1] == "Haces de persona."
    prompt = argv[argv.index("-p") + 1]
    assert "USUARIO: quiero un hotel" in prompt and "ASISTENTE: ¿en qué ciudad?" in prompt
    assert "Haces de persona." not in prompt, "el system se duplicó dentro del prompt"


def test_a_nonzero_exit_is_an_error_and_not_an_answer(monkeypatch):
    """Un `rc != 0` con stdout vacío devolvería `""`, y un turno vacío del que hace de persona se lee en el
    informe como que el AGENTE se quedó mudo — un hallazgo contra el producto fabricado por el instrumento."""
    class _R:
        returncode = 1
        stdout = ""
        stderr = "not logged in"
    import subprocess
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _R())
    with pytest.raises(RuntimeError, match="licencia-claude"):
        llm._claude_licence([{"role": "user", "content": "hola"}])


# ── El JUEZ también tiene red ─────────────────────────────────────────────────────────────────────────
# Perder al juez es perder la RONDA ENTERA: la conversación ya ocurrió y ya se pagó, y sin veredicto no entra
# en el marcador. Costó dos rondas de ocho minutos el 2026-08-20 con un 429 y un 503.


def test_the_judge_falls_back_to_the_licence(monkeypatch):
    monkeypatch.setattr(llm, "_voice_judge_call", lambda m, max_tokens=2000: (_ for _ in ()).throw(
        RuntimeError("429 sin cuota")))
    monkeypatch.setattr(llm, "_claude_licence", lambda m, **k: '{"verdict":"PASS"}')
    txt, model = llm.judge_call([{"role": "user", "content": "puntúa"}])
    assert txt == '{"verdict":"PASS"}' and model == "licencia-claude"


def test_the_judge_prefers_the_paid_chain(monkeypatch):
    """Sensibilidad: el juez vive fuera del proveedor del conductor a propósito, para ser independiente."""
    monkeypatch.setattr(llm, "_voice_judge_call", lambda m, max_tokens=2000: ("ok", "glm-4.6"))
    monkeypatch.setattr(llm, "_claude_licence", lambda m, **k: pytest.fail("la licencia no debía correr"))
    assert llm.judge_call([{"role": "user", "content": "x"}]) == ("ok", "glm-4.6")


def test_an_EMPTY_licence_answer_is_not_a_verdict(monkeypatch):
    """Un juez que devuelve `""` no falla: el analizador no encuentra JSON, reintenta contra el mismo escalón
    mudo y la ronda muere sin nota. Ya pasó con la pata directa de DeepSeek el 2026-08-20."""
    monkeypatch.setattr(llm, "_voice_judge_call", lambda m, max_tokens=2000: (_ for _ in ()).throw(
        RuntimeError("fuera")))
    monkeypatch.setattr(llm, "_claude_licence", lambda m, **k: "   ")
    with pytest.raises(RuntimeError, match="VAC"):
        llm.judge_call([{"role": "user", "content": "x"}])


def test_the_licence_is_the_LAST_rung_and_not_the_first():
    """Guarda de cableado sobre el ORDEN. La conducta de arriba pasaría igual si la licencia estuviera la
    primera y los de pago debajo — y eso es gastar el forfait del operador en cada ronda."""
    import inspect
    src = inspect.getsource(llm.call)
    i_chain = src.index("chain = [")
    tail = src[i_chain:src.index("]", i_chain)]
    assert tail.index("deepseek-directo") < tail.index("aimlapi") < tail.index("licencia-claude")
