"""The `codex` backend translates Codex JSONL into the normalized `WorkerEvent` vocabulary (V2-038).

Until 2026-08-12 this backend was a STUB: if the operator set the provider to `codex`, there were no Brain
Workers, and the symptom was a task that died instantly rather than a configuration message. The objects in this
file are REAL traces captured from the CLI (`codex exec --json`, v0.137.0), not invented — a mapper tested
against an imagined protocol proves nothing.

The pure TRANSLATION is tested (without processes or queues, using `object.__new__` as in the Claude Code mapper
test), along with the FAIL-CLOSED stance, which is the part with security consequences.
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


# ── protocol translation (real traces) ───────────────────────────────────────────────────────────────────
def test_thread_started_captures_the_id_used_to_resume():
    """`thread_id` is the ONLY thing used to resume a Codex worker (`exec resume <id>`). Without capturing it, the
    continuity of V2-049 does not exist: each retry would navigate and retype everything already done."""
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
    # the shell wrapper (`/bin/zsh -lc '…'`) is not rendered: it takes up the entire row and says nothing
    assert steps[0].data["target"] == "wc -l < datos.txt"
    assert steps[0].data["where"] == "sistema"

    done = _map({"type": "item.completed", "item": {
        "id": "item_0", "type": "command_execution", "command": "/bin/zsh -lc 'wc -l < datos.txt'",
        "aggregated_output": "       2\n", "exit_code": 0, "status": "completed"}})
    res = [e for e in done if e.type == "step_result"]
    assert len(res) == 1 and "2" in res[0].data["text"]
    assert res[0].data["is_error"] is False


def test_a_failed_command_is_marked_as_an_error_result():
    """The EVIDENCE must distinguish a step that produced the data from one that failed: without that, a worker
    that produces garbage leaves the same trace as one that succeeds (the finding from 2026-08-10)."""
    evs = _map({"type": "item.completed", "item": {
        "type": "command_execution", "command": "/bin/zsh -lc 'cat nope'",
        "aggregated_output": "cat: nope: No such file or directory\n", "exit_code": 1, "status": "completed"}})
    res = [e for e in evs if e.type == "step_result"]
    assert len(res) == 1 and res[0].data["is_error"] is True


def test_bridge_commands_are_attributed_to_their_own_place():
    """A command that IS a bridge belongs to memory / the browser / zaelar, not to «system» — otherwise ALL of a
    Codex worker's work looks like an indistinguishable pile of commands."""
    for cmd, where in ((".venv/bin/python -m nucleo.mem_cli recall 'coche'", "memoria"),
                       ("python3 -m nucleo.nav_cli navigate https://example.com", "navegador"),
                       ("python3 -m nucleo.widget_cli read agenda", "widget"),
                       ("python3 -m nucleo.worker_bridge ask '¿sigo?'", "zaelar")):
        evs = _map({"type": "item.started", "item": {"type": "command_execution", "command": cmd}})
        steps = [e for e in evs if e.type == "step"]
        assert steps and steps[0].data["where"] == where, cmd


def test_hbnote_does_not_produce_a_row():
    """`agent_report` sets its own phase, which is richer than any phase we could derive — duplicating it is noise."""
    evs = _map({"type": "item.started", "item": {
        "type": "command_execution", "command": "python3 -m nucleo.agent_report phase 'leyendo fichas'"}})
    assert not [e for e in evs if e.type in ("step", "phase")]


def test_agent_message_is_narration_and_the_last_one_is_the_result():
    s = object.__new__(CodexSession)
    s._task_id, s._model, s._native_sid = "42", "gpt-5.5", ""
    s._done, s._last_message, s._usage, s._failed = False, "", {}, ""
    notes = list(s._map({"type": "item.completed", "item": {"type": "agent_message", "text": "Voy a leerlo."}}))
    assert [e.type for e in notes] == ["note"]              # narration, NEVER `say` (there is no voice output)
    list(s._map({"type": "item.completed", "item": {"type": "agent_message", "text": "Son 2 líneas."}}))
    evs = list(s._map({"type": "turn.completed",
                       "usage": {"input_tokens": 28294, "cached_input_tokens": 16128, "output_tokens": 89}}))
    result = next(e for e in evs if e.type == "result")
    assert result.data["summary"] == "Son 2 líneas."         # the LAST message is the deliverable
    assert result.data["ok"] is True
    # tokens arrive with the names that `session.py::_finish` reads to charge Energy — a worker that works
    # without metering is money silently lost (the gap closed by the 2026-08-05 metering change).
    assert result.data["usage"]["input_tokens"] == 28294
    assert result.data["usage"]["output_tokens"] == 89
    assert evs[-1].type == "done"


def test_reasoning_is_not_a_row():
    assert not _map({"type": "item.completed", "item": {"type": "reasoning", "text": "x" * 500}})


def test_an_unknown_item_type_never_raises():
    """The CLI may introduce item types in any version: an unknown one must not bring down the stream of a live
    session (which is what happens if the mapper raises)."""
    assert _map({"type": "item.completed", "item": {"type": "quantum_thing", "wat": 1}}) == []
    assert _map({"type": "algo.que.no.existe"}) == []


def test_turn_failed_is_a_fatal_error():
    evs = _map({"type": "turn.failed", "error": {"message": "model not available for this account"}})
    errs = [e for e in evs if e.type == "error"]
    assert len(errs) == 1 and errs[0].data["fatal"] is True
    assert "model not available" in errs[0].data["message"]


# ── FAIL-CLOSED stance (the consequential part) ──────────────────────────────────────────────────────────
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
    """Claude Code restricts `Bash` to our bridges (the memory's SINGLE WRITER invariant). Codex has no such
    mechanism —only sandbox modes— and headless needs `workspace-write`, meaning a full shell. The two tasks that
    EXIST to be contained (untrusted input V2-010 and the dev worker of a cluster peer) must be REJECTED here,
    not run with less containment than the caller requested.

    This test guards that decision: if someone weakens it, it fails."""
    evs = _start(**kw)
    errs = [e for e in evs if e.type == "error"]
    assert errs and errs[0].data["fatal"] is True
    # and it must SAY which backend to use: a «cannot» with no way forward leaves the operator without workers or a clue
    assert "claude_code" in errs[0].data["message"]
    assert evs[-1].type == "done"                      # closes cleanly, without leaving the session waiting


def test_the_bypass_flag_is_never_used():
    """`--dangerously-bypass-approvals-and-sandbox` completely disables Codex's sandbox. We do not need it
    (verified: with `workspace-write`, it already runs without requesting approval in headless) and it must not slip in."""
    import ast
    from pathlib import Path
    src = Path(__file__).resolve().parents[4] / "nucleo" / "workers" / "codex_session.py"
    tree = ast.parse(src.read_text(encoding="utf-8"))
    # Inspect the EXECUTABLE CODE, not the prose: the module header names the flag precisely to explain why
    # it is not used, and a guard broken by documenting the decision would teach people to delete the explanation.
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) \
                and ast.get_docstring(node):
            node.body = node.body[1:]
    code = ast.unparse(tree)
    assert "dangerously-bypass" not in code
    assert "danger-full-access" not in code


def test_stderr_noise_is_not_reported_as_the_cause_of_death():
    """An old CLI spews `failed to load models cache` on EVERY invocation. Returning that as the reason for the
    failure sends the operator to look in the wrong place."""
    from nucleo.workers.codex_session import _stderr_reason
    blob = (b"2026-08-12T19:59:47Z ERROR codex_models_manager::cache: failed to load models cache: unknown variant\n"
            b"2026-08-12T19:59:48Z ERROR codex_models_manager::manager: failed to refresh available models\n"
            b"stream error: 401 Unauthorized\n")
    assert _stderr_reason(blob) == "stream error: 401 Unauthorized"


# ── CAPABILITY-based routing (registry) ───────────────────────────────────────────────────────────────────
def test_registry_routes_the_contained_tasks_to_claude_code_even_with_codex_configured(monkeypatch):
    """Choosing Codex for normal work must NOT cost the operator the cluster's capabilities or protection against
    untrusted input, either visibly (a failed task) or invisibly (a worker with an open shell). The registry routes
    them to the backend that CAN be contained."""
    from nucleo.workers import registry
    from nucleo.workers.claude_session import ClaudeCodeSession
    monkeypatch.setenv("WORKER_BACKEND", "")
    monkeypatch.setattr(registry, "_provider_for", lambda kind: "codex")

    assert isinstance(registry.get_backend(WorkerSpec(kind="web", deny_tools=True)), ClaudeCodeSession)
    assert isinstance(registry.get_backend(WorkerSpec(kind="dev")), ClaudeCodeSession)
    # and normal work DOES go to Codex, which is what the operator chose
    assert isinstance(registry.get_backend(WorkerSpec(kind="web")), CodexSession)
