"""Losing the instrument is not a finding about the product, and the ledger cannot tell them apart.

2026-08-21: both paid rungs of the tester were down AT THE SAME TIME — Z.AI out of quota until the 25th and
a network outage that left DeepSeek direct on `Connection error` — and the walk spent hours printing «THE
BRAIN CANNOT SPEAK» without measuring a single case. A subscription rung cannot fail that way, so the
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
    monkeypatch.setattr(llm.time, "sleep", lambda _s: None)   # retries do not cost minutes here


# ── The handoff occurs, and is declared ───────────────────────────────────────────────────────────────


def test_when_every_paid_rung_is_out_the_licence_drives(monkeypatch):
    _all_paid_rungs_down(monkeypatch)
    monkeypatch.setattr(llm, "_claude_licence", lambda m, **k: "sigo siendo la persona")
    assert llm.call([{"role": "user", "content": "hola"}]) == "sigo siendo la persona"


def test_the_relay_is_STAMPED(monkeypatch):
    """A silent handoff leaves the board moving forward with two instruments without knowing which rung used which one.
    The licence is a different model: its scores are not comparable with DeepSeek's without saying so."""
    _all_paid_rungs_down(monkeypatch)
    monkeypatch.setattr(llm, "_claude_licence", lambda m, **k: "x")
    llm.call([{"role": "user", "content": "hola"}])
    assert llm.drive_model() == "licencia-claude"


def test_the_licence_is_NOT_used_while_a_paid_rung_answers(monkeypatch):
    """Sensitivity, and this is the side that costs money: the licence comes last because it consumes the
    operator's allowance. Without this case, “there is network underneath” and “it always runs over the
    network” both pass equally green."""
    monkeypatch.setattr(llm, "_deepseek_direct", lambda *a, **k: "titular")
    monkeypatch.setattr(llm, "_claude_licence", lambda m, **k: pytest.fail("la licencia no debía correr"))
    assert llm.call([{"role": "user", "content": "hola"}]) == "titular"
    assert llm.drive_model() == "deepseek-directo"


def test_the_forced_hatch_pins_the_licence(monkeypatch):
    """The manual hatch: measure a specific arm without a failure handing it off behind the scenes."""
    monkeypatch.setenv("ZAELAR_UC_DRIVE", "claude")
    monkeypatch.setattr(llm, "_deepseek_direct", lambda *a, **k: pytest.fail("fijado a la licencia"))
    monkeypatch.setattr(llm, "_claude_licence", lambda m, **k: "fijada")
    assert llm.call([{"role": "user", "content": "hola"}]) == "fijada"
    assert llm.drive_model() == "licencia-claude"


# ── The licence has to be THE LICENCE ─────────────────────────────────────────────────────────────────


def test_the_licence_does_not_inherit_the_redirect(monkeypatch, spawned):
    """THE CASE THAT JUSTIFIES THE FILE. `ANTHROPIC_BASE_URL` and company are the variables with which the
    engine sends this same CLI to Z.AI or DeepSeek. Inherited here, the “Anthropic rung” would be the rung
    that just fell — and the round's stamp would say there was a handoff when there was not."""
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://api.z.ai/api/anthropic")
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "no-debe-viajar")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "tampoco")
    monkeypatch.setenv("PATH", "/usr/bin")            # the rest of the environment DOES travel: it is needed to execute
    llm._claude_licence([{"role": "user", "content": "hola"}])
    env = spawned[0]["env"]
    assert "ANTHROPIC_BASE_URL" not in env and "ANTHROPIC_AUTH_TOKEN" not in env
    assert "ANTHROPIC_API_KEY" not in env
    assert env.get("PATH") == "/usr/bin", "se limpió el entorno entero en vez de las tres variables"


def test_the_licence_runs_from_a_NEUTRAL_directory(spawned):
    """The CLI loads `CLAUDE.md` from the cwd. From `engine/`, every turn by the driver would drag in the
    entire repo — V2-117 measured that blast at 167k tokens per request — and, worse than the cost, a driver
    that has read the engine code stops acting as a PERSON who knows nothing."""
    llm._claude_licence([{"role": "user", "content": "hola"}])
    cwd = Path(spawned[0]["cwd"])
    assert cwd.is_absolute()
    engine = Path(__file__).resolve().parents[3]
    assert engine not in cwd.parents and cwd != engine
    assert not (cwd / "CLAUDE.md").exists()


def test_no_mcp_server_is_loaded(spawned):
    """`--strict-mcp-config` without `--mcp-config` leaves the process without a single MCP server. Here we want a
    model that answers one sentence, not an agent with tools."""
    llm._claude_licence([{"role": "user", "content": "hola"}])
    assert "--strict-mcp-config" in spawned[0]["argv"]


def test_the_system_prompt_travels_and_the_roles_survive(spawned):
    """The driver carries its brief in `system`, and the previous conversation in the turns. Flattening without
    saying who spoke turns the negotiation into a monologue and the tester repeats what it already said."""
    llm._claude_licence([{"role": "system", "content": "Haces de persona."},
                         {"role": "user", "content": "quiero un hotel"},
                         {"role": "assistant", "content": "¿en qué ciudad?"}])
    argv = spawned[0]["argv"]
    assert "--system-prompt" in argv and argv[argv.index("--system-prompt") + 1] == "Haces de persona."
    prompt = argv[argv.index("-p") + 1]
    assert "USUARIO: quiero un hotel" in prompt and "ASISTENTE: ¿en qué ciudad?" in prompt
    assert "Haces de persona." not in prompt, "el system se duplicó dentro del prompt"


def test_a_nonzero_exit_is_an_error_and_not_an_answer(monkeypatch):
    """An `rc != 0` with empty stdout would return `""`, and an empty turn from the person role reads in the
    report as the AGENT having gone silent — a finding against the product fabricated by the instrument."""
    class _R:
        returncode = 1
        stdout = ""
        stderr = "not logged in"
    import subprocess
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _R())
    with pytest.raises(RuntimeError, match="licencia-claude"):
        llm._claude_licence([{"role": "user", "content": "hola"}])


# ── The JUDGE also has network access ─────────────────────────────────────────────────────────────────
# Losing the judge means losing the ENTIRE ROUND: the conversation already happened and was paid for, and without a verdict it does not enter
# the scoreboard. It cost two eight-minute rounds on 2026-08-20 with a 429 and a 503.


# The JUDGE no longer has rungs (V2-779 F2): one ruler, the licence — see `test_one_judge_one_ruler.py`.


def test_the_licence_is_the_LAST_rung_and_not_the_first():
    """Wiring guard for the ORDER. The behavior above would pass just the same if the licence were first and the
    paid ones below — and that would spend the operator's allowance on every round."""
    import inspect
    src = inspect.getsource(llm.call)
    i_chain = src.index("chain = [")
    tail = src[i_chain:src.index("]", i_chain)]
    assert tail.index("deepseek-directo") < tail.index("aimlapi") < tail.index("licencia-claude")
