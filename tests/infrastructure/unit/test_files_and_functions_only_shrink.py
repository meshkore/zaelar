"""Files and functions only shrink (V2-778 F1-15, 2026-09-30).

The operator's axis for the whole cleanup: «una de las cosas más importantes de un proyecto es no tener archivos
demasiado grandes». The demo week added 19.1k product lines, and the de-facto router ended up as ONE coroutine of
~3,500 lines inside the LiveKit adapter. This is the ratchet that stops it growing back while F1 splits it.

Three ceilings over every tracked product `.py` (not tests): a FILE over 800 lines, a FUNCTION over 120 lines,
a function with more than 100 branches. Each offender of the day is NAMED below with its size — the provider and
the probe included. The rule: nothing new may cross a ceiling, and no named offender may grow. Shrinking passes;
when an entry shrinks, lower its number here (or delete it once it is under the ceiling) in the same commit.

The ceilings (800 / 120) are the audit's PROPOSAL; the number is the operator's open decision (V2-778 §Open
decisions). Changing them is one line each.

A function's size is counted from its `def` to its last line, nested functions included, and every nested
function is also counted on its own — so splitting a closure out of `_run_inner` lowers both numbers.
"""
from __future__ import annotations

import ast
import subprocess
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[3]
FILE_MAX, FUNC_MAX, BRANCH_MAX = 800, 120, 100

# V2-778 F1-10a/b (2026-10-01): the tool executor and the post-stream chain MOVED out of `_run_inner` into
# `nucleo/flash/tool_executor.py` and `nucleo/flash/post_stream.py` (same code, same sizes); their entries were
# renamed, not added — and splitting both under the ceilings is owed.
FILES = {
    'connectors/email/mailbox.py': 945,
    'connectors/meshkore/bridge.py': 891,
    'i18n/langs.py': 993,
    'memory/api.py': 1077,
    'nucleo/dispatch.py': 1789,
    'nucleo/energy_meter.py': 820,
    'nucleo/flash/direct_action.py': 988,
    'nucleo/flash/fast_client.py': 900,
    'nucleo/flash/live_blocks.py': 860,
    'nucleo/flash/post_stream.py': 983,
    'nucleo/flash/probe.py': 1335,
    'nucleo/flash/prompt.py': 815,
    'nucleo/flash/tool_executor.py': 1271,
    'nucleo/jev.py': 831,
    'nucleo/mem_processor.py': 831,
    'nucleo/workers/session.py': 858,
    'server/voice_api.py': 993,
    'voice/attention.py': 1033,
    'voice/engine/llm/providers/nucleo.py': 1769,
    'voice/engine/pipeline/agent.py': 924,
    'widgets/agenda/data.py': 933,
    'widgets/mensajeria/data.py': 1069,
    'widgets/navegador/owner.py': 1713,
    'widgets/navegador/tasks.py': 829,
    'widgets/results/data.py': 985,
    'widgets/youtube/data.py': 1073,
}

FUNCTIONS = {
    'config/settings.py::update': 146,
    'connectors/meshkore/bridge.py::ClusterBridge._brain_turn': 142,
    'connectors/meshkore/bridge.py::ClusterBridge.dispatch': 171,
    'connectors/meshkore/bridge.py::ClusterBridge.on_event': 203,
    'i18n/init/detect.py::lock': 132,
    'memory/_prompt.py::compose_state': 258,
    'memory/writer.py::insert_memory': 177,
    'nucleo/actionmap/executor.py::execute': 142,
    'nucleo/dispatch.py::_run_session': 387,
    'nucleo/dispatch.py::run_listener': 213,
    'nucleo/dispatch_prompts.py::_web_prompt': 222,
    'nucleo/errands/wake.py::wake': 153,
    'nucleo/flash/accumulator.py::Accumulator.offer': 158,
    'nucleo/flash/fast_client.py::FastClient._stream_inner': 267,
    'nucleo/flash/listing_turn.py::run': 121,
    'nucleo/flash/live_blocks.py::navegador_lines': 382,
    'nucleo/flash/post_stream.py::run': 951,
    'nucleo/flash/probe.py::run_turn': 1232,
    'nucleo/flash/prompt.py::_flash_layer': 238,
    'nucleo/flash/prompt.py::live_state': 210,
    'nucleo/flash/task_block.py::pending_task_lines': 198,
    'nucleo/flash/tool_executor.py::build': 1240,
    'nucleo/flash/tool_executor.py::build._apply_widget_data': 187,
    'nucleo/flash/tool_executor.py::build._handle_widget_data_tool': 186,
    'nucleo/flash/tool_executor.py::build._on_tool_call': 517,
    'nucleo/flash/tool_executor.py::build._tag_emit': 186,
    'nucleo/flash/widget_data_turn.py::execute': 154,
    'nucleo/loop.py::OrchestratorLoop._supervise_workers': 174,
    'nucleo/mem_processor.py::process': 205,
    'nucleo/memory_agent/ingest.py::_ingest_utterance_locked': 341,
    'nucleo/research_prompts.py::to_prompt_block': 136,
    'nucleo/susurro/apply.py::apply_corrections': 161,
    'nucleo/worker_api.py::_exec_allow': 280,
    'nucleo/workers/claude_session.py::ClaudeCodeSession._map': 145,
    'nucleo/workers/claude_session.py::ClaudeCodeSession.start': 140,
    'server/__init__.py::_lifespan': 511,
    'server/voice_api.py::status': 335,
    'voice/engine/llm/providers/nucleo.py::NucleoLLMStream._run_inner': 1428,
    'voice/engine/pipeline/agent.py::entrypoint': 729,
    'voice/engine/pipeline/agent.py::entrypoint._on_data': 142,
    'voice/engine/speech/filler_audio.py::llm_node_with_filler': 143,
    'voice/proactive.py::notify': 128,
    'voice/tag_protocol.py::strip_tags': 212,
    'widgets/agenda/data.py::apply_action': 544,
    'widgets/agenda/tasklists.py::apply': 170,
    'widgets/archivos/data.py::apply_action': 136,
    'widgets/brief.py::for_prompt': 157,
    'widgets/contactos/data.py::apply_action': 392,
    'widgets/generator.py::_run_agent_once': 125,
    'widgets/imagenes/data.py::apply_action': 136,
    'widgets/mensajeria/data.py::answer_action': 136,
    'widgets/mensajeria/data.py::apply_action': 563,
    'widgets/musica/data.py::apply_action': 271,
    'widgets/navegador/act_api.py::_hand_over': 151,
    'widgets/navegador/act_api.py::navegador_act': 125,
    'widgets/navegador/agent.py::run_task': 134,
    'widgets/navegador/owner.py::TaskBrowser.agent_act': 124,
    'widgets/navegador/owner.py::_automate': 135,
    'widgets/refs.py::resolve': 125,
    'widgets/results/data.py::apply_action': 297,
    'widgets/youtube/data.py::apply_action': 561,
    'widgets/youtube/library.py::apply': 217,
}

BRANCHES = {
    'nucleo/flash/post_stream.py::run': 337,
    'nucleo/flash/probe.py::run_turn': 413,
    'nucleo/flash/tool_executor.py::build': 427,
    'nucleo/flash/tool_executor.py::build._on_tool_call': 208,
    'nucleo/memory_agent/ingest.py::_ingest_utterance_locked': 101,
    'voice/engine/llm/providers/nucleo.py::NucleoLLMStream._run_inner': 225,
    'voice/engine/pipeline/agent.py::entrypoint': 105,
    'widgets/agenda/data.py::apply_action': 236,
    'widgets/agenda/tasklists.py::apply': 115,
    'widgets/contactos/data.py::apply_action': 159,
    'widgets/mensajeria/data.py::apply_action': 221,
    'widgets/musica/data.py::apply_action': 108,
    'widgets/results/data.py::apply_action': 128,
    'widgets/youtube/data.py::apply_action': 239,
    'widgets/youtube/library.py::apply': 123,
}


def _product_files() -> list[str]:
    out = subprocess.run(["git", "ls-files", "*.py"], cwd=ENGINE, capture_output=True, text=True).stdout.split()
    return [p for p in out if not p.startswith("tests/") and "/tests/" not in p]


def _branches(fn) -> int:
    n = 0
    for node in ast.walk(fn):
        if isinstance(node, (ast.If, ast.For, ast.AsyncFor, ast.While, ast.ExceptHandler, ast.IfExp, ast.With,
                             ast.AsyncWith, ast.match_case)):
            n += 1
        elif isinstance(node, ast.BoolOp):
            n += len(node.values) - 1
        elif isinstance(node, ast.comprehension):
            n += 1 + len(node.ifs)
    return n


def _measure():
    files, funcs, branches = {}, {}, {}
    for rel in _product_files():
        p = ENGINE / rel
        if not p.exists():
            continue
        src = p.read_text(encoding="utf-8")
        lines = src.count("\n") + (0 if src.endswith("\n") else 1)
        if lines > FILE_MAX:
            files[rel] = lines
        try:
            tree = ast.parse(src)
        except SyntaxError:
            continue

        def visit(node, prefix):
            for ch in ast.iter_child_nodes(node):
                if isinstance(ch, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    q = f"{prefix}{ch.name}"
                    ln = ch.end_lineno - ch.lineno + 1
                    if ln > FUNC_MAX:
                        funcs[f"{rel}::{q}"] = ln
                    b = _branches(ch)
                    if b > BRANCH_MAX:
                        branches[f"{rel}::{q}"] = b
                    visit(ch, q + ".")
                elif isinstance(ch, ast.ClassDef):
                    visit(ch, f"{prefix}{ch.name}.")
                else:
                    visit(ch, prefix)
        visit(tree, "")
    return files, funcs, branches


def _grown(now: dict, base: dict) -> list[str]:
    return [f"{k}: {v} (baseline {base.get(k, 'none — new offender')})" for k, v in sorted(now.items())
            if v > base.get(k, 0)]


def test_no_file_grows_past_the_ceiling():
    files, _, _ = _measure()
    assert not _grown(files, FILES), f"a product file over {FILE_MAX} lines grew or is new: {_grown(files, FILES)}"


def test_no_function_grows_past_the_ceiling():
    _, funcs, _ = _measure()
    assert not _grown(funcs, FUNCTIONS), \
        f"a function over {FUNC_MAX} lines grew or is new: {_grown(funcs, FUNCTIONS)}"


def test_no_function_grows_more_branches():
    _, _, branches = _measure()
    assert not _grown(branches, BRANCHES), \
        f"a function over {BRANCH_MAX} branches grew or is new: {_grown(branches, BRANCHES)}"


def test_the_provider_and_the_probe_are_named():
    assert "voice/engine/llm/providers/nucleo.py" in FILES and "nucleo/flash/probe.py" in FILES
    assert "voice/engine/llm/providers/nucleo.py::NucleoLLMStream._run_inner" in FUNCTIONS
    assert "nucleo/flash/probe.py::run_turn" in FUNCTIONS
