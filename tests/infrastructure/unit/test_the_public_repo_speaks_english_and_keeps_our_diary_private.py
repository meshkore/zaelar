"""Two rules of the public repo, made red-able (V2-778 F6-45, 2026-10-01).

CRIT-W2 — English everywhere inside `engine/`. Measured 2026-08-29: hundreds of product files still carried
Castilian comments, with the rule written in five places and no test; reading that backlog as the house register
is how it kept losing. This freezes today's count of Castilian COMMENT lines per file: no file may gain one and the
total only falls. Quotes are skipped — «…» and "…" inside an English comment are the operator's own words, which
is product data, not prose.

CRIT-W8 — neither our past nor our future is published: the roadmap, the module logs and the test reports stay
local. Nothing under those paths may be tracked.
"""
from __future__ import annotations

import io
import re
import subprocess
import tokenize
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[3]

_QUOTED = re.compile(r"«[^»]*»|\"[^\"]*\"|'[^']*'|`[^`]*`")
_MARKS = re.compile(r"[ñ¿¡áéíóú]", re.I)
_STOP = {"que", "los", "las", "del", "para", "una", "por", "con", "cuando", "porque", "pero", "esto", "está",
         "como", "sin", "sobre", "también", "aquí", "eso", "hay", "ya", "solo", "sólo", "muy", "más", "el", "la",
         "es", "se", "lo", "su", "sus", "si", "no", "en", "y", "o", "un", "al"}


def _castilian(comment: str) -> bool:
    text = _QUOTED.sub(" ", comment.lstrip("#"))
    words = re.findall(r"[a-záéíóúñü]+", text.lower())
    if len(words) < 4:
        return False
    hits = sum(1 for w in words if w in _STOP)
    return hits / len(words) >= 0.25 or (bool(_MARKS.search(text)) and hits >= 2)


def _tracked_py() -> list[str]:
    out = subprocess.run(["git", "ls-files", "*.py"], cwd=ENGINE, capture_output=True, text=True).stdout.split()
    return [p for p in out if not p.startswith("tests/") and "/tests/" not in p]


def _counts() -> dict[str, int]:
    counts: dict[str, int] = {}
    for rel in _tracked_py():
        p = ENGINE / rel
        if not p.exists():
            continue
        try:
            toks = tokenize.generate_tokens(io.StringIO(p.read_text(encoding="utf-8")).readline)
            n = sum(1 for t in toks if t.type == tokenize.COMMENT and _castilian(t.string))
        except (tokenize.TokenError, SyntaxError, UnicodeDecodeError, IndentationError):
            continue
        if n:
            counts[rel] = n
    return counts


#: Measured on 2026-10-01. Translating a file lowers its number; delete its line when it reaches zero.
TOTAL = 3658
PER_FILE: dict[str, int] = {
    'config/settings.py': 2,
    'config/v2.py': 4,
    'conftest.py': 1,
    'connectors/calendar/google_calendar.py': 1,
    'connectors/contacts/google_people.py': 2,
    'connectors/meshkore/bridge.py': 1,
    'connectors/meshkore/capsule.py': 1,
    'connectors/music/base.py': 1,
    'connectors/registry.py': 1,
    'connectors/torrent/session.py': 1,
    'frontend/mobile/icons/generate.py': 1,
    'i18n/init/detect.py': 1,
    'i18n/langspec.py': 10,
    'memory/_prompt.py': 75,
    'memory/api.py': 38,
    'memory/consolidator.py': 33,
    'memory/embeddings.py': 66,
    'memory/episodic.py': 1,
    'memory/graph_ppr.py': 2,
    'memory/reembed.py': 3,
    'memory/rem.py': 39,
    'memory/rerank.py': 15,
    'memory/rerank_local.py': 3,
    'memory/retriever.py': 28,
    'memory/schema.py': 42,
    'memory/secrets.py': 18,
    'memory/slots.py': 15,
    'memory/state.py': 41,
    'memory/vault.py': 8,
    'memory/vault_api.py': 1,
    'memory/writer.py': 95,
    'nucleo/agent_report.py': 3,
    'nucleo/agentes/claude_code.py': 11,
    'nucleo/agentes/code.py': 15,
    'nucleo/agentes/codex.py': 2,
    'nucleo/agentes/web.py': 14,
    'nucleo/batch/runner.py': 1,
    'nucleo/bridge_usage.py': 2,
    'nucleo/browser_search.py': 10,
    'nucleo/consent.py': 1,
    'nucleo/context_packs/introduction.py': 5,
    'nucleo/danger.py': 1,
    'nucleo/dev_worker_guard.py': 1,
    'nucleo/dispatch.py': 14,
    'nucleo/dispatch_confirm.py': 4,
    'nucleo/dispatch_listener.py': 3,
    'nucleo/dispatch_prepare.py': 6,
    'nucleo/dispatch_prompts.py': 110,
    'nucleo/dispatch_session.py': 19,
    'nucleo/energy_lease.py': 57,
    'nucleo/energy_meter.py': 60,
    'nucleo/errand_kind.py': 9,
    'nucleo/errands/party.py': 4,
    'nucleo/errands/verify.py': 1,
    'nucleo/errands/wake.py': 2,
    'nucleo/flash/accumulator.py': 37,
    'nucleo/flash/answer_guards.py': 12,
    'nucleo/flash/canvas_license.py': 1,
    'nucleo/flash/canvas_visibility.py': 1,
    'nucleo/flash/clarifying.py': 2,
    'nucleo/flash/close_guards.py': 1,
    'nucleo/flash/data_ops.py': 1,
    'nucleo/flash/delivery.py': 91,
    'nucleo/flash/dialog.py': 10,
    'nucleo/flash/direct_action.py': 1,
    'nucleo/flash/errand_sheet.py': 10,
    'nucleo/flash/escalate.py': 16,
    'nucleo/flash/fast_client.py': 55,
    'nucleo/flash/frontend.py': 3,
    'nucleo/flash/hard_turn.py': 1,
    'nucleo/flash/listing_turn.py': 1,
    'nucleo/flash/live_blocks.py': 188,
    'nucleo/flash/model_spec.py': 7,
    'nucleo/flash/post_stream.py': 179,
    'nucleo/flash/presence.py': 1,
    'nucleo/flash/prewarm.py': 11,
    'nucleo/flash/probe.py': 130,
    'nucleo/flash/probe_after.py': 91,
    'nucleo/flash/probe_decide.py': 25,
    'nucleo/flash/probe_scheduling.py': 37,
    'nucleo/flash/prompt.py': 119,
    'nucleo/flash/provider_chain.py': 43,
    'nucleo/flash/recall_heuristics.py': 30,
    'nucleo/flash/reminder_guards.py': 7,
    'nucleo/flash/router.py': 2,
    'nucleo/flash/router_catalog.py': 6,
    'nucleo/flash/router_guards.py': 11,
    'nucleo/flash/segmenter.py': 51,
    'nucleo/flash/show_guard.py': 1,
    'nucleo/flash/show_target.py': 3,
    'nucleo/flash/site_catalog.py': 10,
    'nucleo/flash/style_directive.py': 1,
    'nucleo/flash/task_block.py': 43,
    'nucleo/flash/tool_executor.py': 129,
    'nucleo/flash/tool_executor_widget.py': 68,
    'nucleo/flash/tool_selection.py': 2,
    'nucleo/flash/tools_media.py': 9,
    'nucleo/flash/turn_brief.py': 3,
    'nucleo/flash/video_turn.py': 7,
    'nucleo/homeostasis.py': 38,
    'nucleo/jev.py': 2,
    'nucleo/mem_processor.py': 103,
    'nucleo/memllm.py': 6,
    'nucleo/memory_agent/external.py': 1,
    'nucleo/memory_agent/gates.py': 2,
    'nucleo/memory_agent/ingest.py': 36,
    'nucleo/memory_agent/lang_marks.py': 108,
    'nucleo/mesh_agents.py': 1,
    'nucleo/mesh_cli.py': 5,
    'nucleo/protected_core.py': 20,
    'nucleo/rehydrate.py': 44,
    'nucleo/research.py': 37,
    'nucleo/runstate.py': 4,
    'nucleo/style_policy.py': 2,
    'nucleo/susurro/apply.py': 2,
    'nucleo/susurro/catalog.py': 1,
    'nucleo/susurro/engine.py': 1,
    'nucleo/turn/vault_gate.py': 1,
    'nucleo/websearch.py': 1,
    'nucleo/worker_api.py': 2,
    'nucleo/worker_policy.py': 2,
    'nucleo/workers/base.py': 16,
    'nucleo/workers/claude_session.py': 91,
    'nucleo/workers/codex_session.py': 43,
    'nucleo/workers/generator_session.py': 18,
    'nucleo/workers/goal.py': 2,
    'nucleo/workers/grok_session.py': 62,
    'nucleo/workers/handoff.py': 2,
    'nucleo/workers/providers.py': 87,
    'nucleo/workers/relay.py': 3,
    'nucleo/workers/reports.py': 3,
    'nucleo/workers/session.py': 3,
    'nucleo/workers/tool_steps.py': 6,
    'observability/flows.py': 5,
    'observability/identity.py': 1,
    'server/feedback_api.py': 4,
    'server/ingress.py': 1,
    'server/voice_api.py': 6,
    'server/wizard_api.py': 2,
    'version.py': 1,
    'voice/attention.py': 2,
    'voice/endpointing.py': 3,
    'voice/engine/llm/providers/confirm_gate.py': 13,
    'voice/engine/llm/providers/nucleo.py': 158,
    'voice/engine/llm/providers/pending_confirm.py': 2,
    'voice/engine/llm/providers/promise_backstop.py': 1,
    'voice/engine/llm/providers/turn_admit.py': 14,
    'voice/engine/llm/providers/turn_after.py': 69,
    'voice/engine/llm/providers/turn_failure.py': 23,
    'voice/engine/llm/providers/turn_fragment.py': 9,
    'voice/engine/llm/providers/turn_prompt.py': 35,
    'voice/engine/llm/providers/turn_tools.py': 20,
    'voice/engine/llm/providers/widget_intent.py': 6,
    'voice/engine/pipeline/agent.py': 1,
    'voice/engine/pipeline/first_air.py': 2,
    'voice/engine/speech/elevenlabs_voices.py': 6,
    'voice/engine/speech/filler_audio.py': 5,
    'voice/interrupt_grammar.py': 2,
    'voice/mic_input.py': 2,
    'voice/proactive.py': 2,
    'voice/trace.py': 18,
    'widgets/agenda/data.py': 4,
    'widgets/agenda/gcal.py': 1,
    'widgets/agenda/index.py': 1,
    'widgets/agenda/tasklists.py': 2,
    'widgets/brief.py': 4,
    'widgets/contactos/data.py': 3,
    'widgets/contactos/gcontacts.py': 1,
    'widgets/mensajeria/data.py': 3,
    'widgets/mensajeria/owner.py': 2,
    'widgets/mensajeria/thread.py': 1,
    'widgets/navegador/act_api.py': 79,
    'widgets/navegador/click_gate.py': 2,
    'widgets/navegador/data.py': 1,
    'widgets/navegador/dom.py': 6,
    'widgets/navegador/tasks.py': 1,
    'widgets/presentation.py': 4,
    'widgets/results/data.py': 2,
    'widgets/results/digest.py': 1,
    'widgets/results/sheet_names.py': 3,
    'widgets/server_api.py': 5,
    'widgets/youtube/account.py': 1,
    'widgets/youtube/data.py': 1,
}


def test_no_file_gains_castilian_comments():
    now = _counts()
    grown = sorted(f"{f}: {n} (was {PER_FILE.get(f, 0)})" for f, n in now.items() if n > PER_FILE.get(f, 0))
    assert not grown, f"new Castilian comment lines in a public file — write them in English (CRIT-W2): {grown[:12]}"


def test_the_castilian_backlog_only_shrinks():
    assert sum(_counts().values()) <= TOTAL


def test_our_diary_is_not_tracked():
    """CRIT-W8. These paths exist in the operator's checkout and are gitignored on purpose."""
    paths = [".meshkore/roadmap", "tests/voice/e2e/agent/reports", "tests/runs"]
    out = subprocess.run(["git", "ls-files", "--", *paths], cwd=ENGINE, capture_output=True, text=True).stdout
    mods = subprocess.run(["git", "ls-files", "--", ".meshkore/modules"], cwd=ENGINE, capture_output=True,
                          text=True).stdout.splitlines()
    leaked = [p for p in out.splitlines() if p.strip()] + [p for p in mods if "/tasks/" in p or "/logs/" in p]
    assert not leaked, f"the roadmap, module logs or test reports are tracked in the PUBLIC repo: {leaked[:10]}"
