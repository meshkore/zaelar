"""The `grok_build` backend (Grok Build CLI) — V2-038, 2026-08-13.

Grok Build emits the SAME wire format as Claude Code, so `GrokSession` INHERITS the entire translation and only
overrides its vocabulary. That is exactly what is tested here: that inheritance does not break and that the three
real differences (tool names, arguments, and evidence wrapping) are translated.

All forms in this file are REAL, captured by probing `grok` 1.0.3 against the operator's account.
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


# ── INHERITANCE: the same wire format is translated without touching the mapper ───────────────────────────
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
    # tokens with the names that `session.py::_finish` reads to bill Energy, and the cost reported by the CLI
    assert res.data["usage"]["input_tokens"] == 17971
    assert res.data["cost"] == pytest.approx(0.0380156)
    assert evs[-1].type == "done"


def test_a_grok_command_row_says_where_it_worked():
    """Its Bash is called `run_terminal_command`: without translating the name, the row fell into the “system”
    drawer, and a worker that queries memory looked the same as one that deletes a file."""
    evs = _map({"type": "assistant", "message": {"content": [{
        "type": "tool_use", "id": "call-1", "name": "run_terminal_command",
        "input": {"command": ".venv/bin/python -m nucleo.mem_cli recall 'velero'",
                  "description": "consulta memoria"}}]}})
    step = next(e for e in evs if e.type == "step")
    assert step.data["where"] == "memoria" and step.data["action"] == "recall"
    assert "velero" in step.data["target"]


def test_read_uses_target_file_not_path():
    """VERIFIED in the CLI: `read_file` sends `target_file`. With the wrong name, the row appeared with `target=''`,
    meaning the operator saw “reads” without knowing WHAT it reads—the exact datum that makes the step auditable."""
    assert _translate("read_file", {"target_file": "informe.json"})[1]["file_path"] == "informe.json"
    evs = _map({"type": "assistant", "message": {"content": [{
        "type": "tool_use", "id": "c", "name": "read_file", "input": {"target_file": "widgets/agenda/data.py"}}]}})
    step = next(e for e in evs if e.type == "step")
    assert step.data["where"] == "archivo" and step.data["target"] == "agenda/data.py"


def test_thinking_is_never_a_row_nor_a_note():
    """Grok emits its reasoning as a `thinking` block. It is long and internal: the panel shows WORK, not a monologue
    (and the cryptographic signature accompanying it tells nobody anything)."""
    evs = _map({"type": "assistant", "message": {"content": [
        {"type": "thinking", "thinking": "El usuario quiere que cuente las líneas…", "signature": "abc123"},
        {"type": "text", "text": "Voy a contarlas."}]}})
    assert [e.type for e in evs] == ["note"]
    assert evs[0].data["text"] == "Voy a contarlas."


# ── EVIDENCE: each tool wraps it differently ───────────────────────────────────────────────────────────────
@pytest.mark.parametrize("raw,expect", [
    ('{"type":"Bash","output":[51,10],"output_for_prompt":"exit: 0\\n3\\n","exit_code":0}', "exit: 0\n3\n"),
    ('{"type":"ReadFile","FileContent":{"content":"1-alfa\\nbeta\\n","absolute_path":"/x/y"}}', "1-alfa\nbeta\n"),
    ('{"type":"GrepSearch","stdout":[104,111,108,97],"match_count":1}', "hola"),
])
def test_evidence_is_unwrapped_per_tool(raw, expect):
    """Without unwrapping, the row showed the ENVELOPE (log paths, bytes, flags) instead of the letter. Grep was the
    worst: its `stdout` arrives as a LIST OF BYTES and was displayed as «[60,119,111,114,…]», unreadable."""
    assert _unwrap_evidence(raw) == expect


def test_a_denied_tool_keeps_its_policy_message_intact():
    """This is the PROOF that containment worked: if it is truncated or lost, a blocked attempt becomes
    indistinguishable from a step that never occurred."""
    got = _unwrap_evidence([{"type": "content", "content": {
        "type": "text", "text": 'Tool `run_terminal_command` was not executed: Denied by permission policy: '
                                'deny rule on bash matching "whoami"'}}])
    assert got == ['Tool `run_terminal_command` was not executed: Denied by permission policy: '
                   'deny rule on bash matching "whoami"']


def test_unknown_tool_falls_back_without_raising():
    """A new CLI tool cannot break anything. Its evidence is deliberately returned RAW: if the body field is not
    recognized, it is better to show the entire JSON (ugly but auditable) than return empty and lose the evidence."""
    assert _translate("alguna_tool_nueva", {"x": 1}) == ("alguna_tool_nueva", {"x": 1})
    assert _unwrap_evidence('{"type":"CosaNueva","algo":"valor"}') == '{"type":"CosaNueva","algo":"valor"}'
    # but if it contains a KNOWN body field, it is unwrapped even if the tool was not probed
    assert _unwrap_evidence('{"type":"CosaNueva","output_for_prompt":"valor"}') == "valor"
    assert _unwrap_evidence("texto pelado") == "texto pelado"


# ── CONTAINMENT: Grok can uphold the single-writer invariant ───────────────────────────────────────────────
def test_the_prompt_goes_by_file_never_by_stdin_dash():
    """`grok -p -` does NOT read stdin: it takes `-` as a literal prompt and ours is lost WITHOUT ERROR—the CLI starts
    with a nonsensical prompt and the model does something reasonable on its own. Measured: 447,559 input tokens and
    $0.73 exploring the repo when it had been asked to print a version; with the prompt delivered correctly, $0.005.
    This guard exists because the failure is EXPENSIVE and SILENT."""
    src = pathlib.Path(__file__).resolve().parents[4] / "nucleo" / "workers" / "grok_session.py"
    code = "\n".join(ln for ln in src.read_text(encoding="utf-8").splitlines()
                     if not ln.lstrip().startswith("#"))
    assert '"--prompt-file"' in code
    assert '"-p", "-"' not in code


def test_bash_stays_pinned_to_the_bridges():
    """The rule list is LITERALLY `_BRIDGE_TOOLS` from claude_session (single source of truth). A backend that
    invented its own list would become out of sync with the real interpreter at the first change, and the worker
    would start doing permission archaeology instead of the task."""
    src = pathlib.Path(__file__).resolve().parents[4] / "nucleo" / "workers" / "grok_session.py"
    code = src.read_text(encoding="utf-8")
    assert "_BRIDGE_TOOLS" in code
    assert '"--allow"' in code
    assert "dangerously" not in code and "bypassPermissions" not in code
    assert any("mem_cli" in r for r in _BRIDGE_TOOLS)          # the single source still includes the bridges


def test_registry_sends_untrusted_work_to_grok_because_it_can_contain_it(monkeypatch):
    """Unlike Codex, Grok does NOT divert to claude_code: it accepts `--deny` and applies it (tested against the CLI),
    so it can run an untrusted-input task with the tools disabled."""
    from nucleo.workers import registry
    monkeypatch.setenv("WORKER_BACKEND", "")
    monkeypatch.setattr(registry, "_provider_for", lambda kind: "grok_build")
    assert registry.get_backend(WorkerSpec(kind="web")).name == "grok_build"
    assert registry.get_backend(WorkerSpec(kind="web", deny_tools=True)).name == "grok_build"


def test_the_worker_can_write_so_it_never_pushes_against_the_bash_fence():
    """Benchmark of 2026-08-13: `_GROK_TOOLS` only included READ access, so when it was time to leave its report the
    worker had no means to do so and went around through `run_terminal_command`—which the allowlist correctly denies.
    Denying it write access does not make it safer: it pushes it against the fence. Bash's fence provides containment,
    and that one remains.
    """
    from nucleo.workers.grok_session import _GROK_TOOLS
    assert "write" in _GROK_TOOLS and "search_replace" in _GROK_TOOLS
    # …but NOT its own, which would interfere with our components (pool, cron, channel with the operator)
    for pisa in ("spawn_subagent", "scheduler_create", "scheduler_list", "ask_user_question",
                 "image_gen", "image_to_video"):
        assert pisa not in _GROK_TOOLS, f"{pisa} duplicaría una pieza de Zaelar"


def test_a_denied_command_is_not_read_as_the_operator_giving_up():
    """Grok tells the model «User cancelled the execution for tool `run_terminal_command`» when it is OUR allowlist
    that denies it. A model reading that concludes the human aborted it and STOPS: in the benchmark, a single denial
    closed the session with `ok=False` and an empty result after it had worked well. The CLI writes the text inside its
    loop (it does not pass through us), so the only defense is to disarm it beforehand, in the prompt."""
    from nucleo.workers.grok_session import _BACKEND_NOTE
    assert "User cancelled" in _BACKEND_NOTE                    # names the EXACT text it will see
    assert "NO es el operador" in _BACKEND_NOTE                 # and says whose fence it is
    assert "web_fetch" in _BACKEND_NOTE                         # + the capability Grok lacks and where it is


def test_the_backend_note_rides_the_prompt_and_never_reaches_untrusted_work():
    """The note is appended to the prompt by the backend ITSELF (this CLI has an unusual behavior; it does not clutter
    `dispatch`). With `deny_tools`, there is no terminal or bridges to explain, so it is not added there: less surface
    area to read for a task coming from outside."""
    src = pathlib.Path(__file__).resolve().parents[4] / "nucleo" / "workers" / "grok_session.py"
    code = "\n".join(ln for ln in src.read_text(encoding="utf-8").splitlines()
                     if not ln.lstrip().startswith("#"))
    assert "_BACKEND_NOTE + " in code
    assert "spec.deny_tools else _BACKEND_NOTE" in code         # fail-closed: the branch without the note is untrusted


def test_every_tool_gets_its_own_allow_rule_because_the_allowlist_is_strict():
    """As soon as there is ONE `--allow` rule, Grok switches to a STRICT allowlist: `acceptEdits` stops approving what
    is not listed. It took TWO benchmark runs to see this (first `write` was missing from `--tools`; after adding it,
    it still died with «User cancelled the execution for tool `write`», because it had never been granted permission).
    A tool in `_GROK_TOOLS` without an entry in `_TOOL_ALIAS` is a tool WITHOUT PERMISSION—this test prevents it."""
    from nucleo.workers.grok_session import _GROK_TOOLS, _TOOL_ALIAS
    sin_alias = [t for t in _GROK_TOOLS if t not in _TOOL_ALIAS]
    assert not sin_alias, f"sin alias = sin regla --allow = denegada en vivo: {sin_alias}"


def test_writes_show_what_happened_not_the_diff_payload():
    """`write`/`search_replace` return `{"type":"SearchReplace","EditsApplied":{…}}`. Without unwrapping it, the row
    showed the JSON with complete `old_string`/`new_string` values instead of “X has been created”."""
    from nucleo.workers.grok_session import _unwrap_evidence
    raw = ('{"type":"SearchReplace","EditsApplied":{"old_string":"","new_string":"hola\\n",'
           '"tool_output_for_prompt":"The file /tmp/x.txt has been created."}}')
    assert _unwrap_evidence(raw) == "The file /tmp/x.txt has been created."
