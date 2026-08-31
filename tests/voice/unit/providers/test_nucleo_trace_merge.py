"""A correction that continues an in-progress accumulator chain (V2-096) must not open a new flow (V2-090 addenda,
2026-08-15). Real production data showed ONE continuous utterance ("borra toda la agenda...") splitting into five
separate corr_ids, because LiveKit closes a turn per STT-final segment and `trace.begin()` fired unconditionally
per turn. `_begin_or_adopt_trace` is factored out of `_run_inner` precisely so this is testable without a live
LiveKit stream — see `voice/engine/llm/providers/nucleo.py::_begin_or_adopt_trace`.
"""
import asyncio

import pytest

from nucleo.flash import accumulator as acc_mod
from nucleo.flash.accumulator import Accumulator
from voice import trace
from voice.engine.llm.providers.nucleo import (
    NucleoLLM, _begin_or_adopt_trace, _close_flow_now, _flow_should_close, _merge_target,
    _release_acc_trace_if_fresh,
)


async def _stub_incomplete(text: str) -> tuple[str, str]:
    return "incomplete", ""


@pytest.fixture(autouse=True)
def _no_real_judge_calls():
    """Fast, network-free layer-2 stub for every test here — several fixtures below offer lexically-incomplete
    fragments ("Pues mira, me vas a borrar" starts with the dangling «pues»), which since V2-102 fall through to
    `Accumulator.offer()`'s judge call. Without this, they'd hit the real model over the network."""
    acc_mod.set_judge(_stub_incomplete)
    yield
    acc_mod.set_judge(None)


def _offer(acc: Accumulator, *args, **kwargs):
    """`Accumulator.offer()` is async since V2-102 — same `asyncio.run(...)`-per-call convention used elsewhere
    in this suite for a sync test that needs one async result."""
    return asyncio.run(acc.offer(*args, **kwargs))


def _fresh_brain() -> NucleoLLM:
    trace.adopt("")
    return NucleoLLM()


def test_kickoff_always_opens_its_own_trace():
    brain = _fresh_brain()
    _begin_or_adopt_trace(brain, "I just connected", True)
    tid = trace.current()
    assert tid
    trace.adopt("")


def test_first_fragment_of_a_new_chain_opens_a_fresh_trace():
    brain = _fresh_brain()
    brain._acc = Accumulator()
    _begin_or_adopt_trace(brain, "Pues mira, me vas a borrar", False)
    tid = trace.current()
    assert tid
    assert brain._acc_trace_id == tid
    trace.adopt("")


def test_turn_offered_while_the_chain_is_pending_adopts_the_chains_trace():
    brain = _fresh_brain()
    brain._acc = Accumulator()
    _begin_or_adopt_trace(brain, "Pues mira, me vas a borrar", False)
    first_tid = trace.current()
    _offer(brain._acc, "Pues mira, me vas a borrar")   # incomplete -> "hold", buffer now non-empty
    assert brain._acc.pending()

    trace.adopt("")   # simulate a fresh turn's context, as a new NucleoLLMStream would start with
    _begin_or_adopt_trace(brain, "Pues mira, me vas a borrar toda la agenda.", False)
    assert trace.current() == first_tid
    assert brain._acc_trace_id == first_tid
    trace.adopt("")


def test_unrelated_new_utterance_after_the_chain_resolves_gets_its_own_trace():
    brain = _fresh_brain()
    brain._acc = Accumulator()
    _begin_or_adopt_trace(brain, "busca una moto de segunda mano", False)
    first_tid = trace.current()
    action, _merged, _why, _dropped = _offer(brain._acc, "busca una moto de segunda mano.")
    assert action == "act"                 # closes the chain in one shot (already looks complete)
    brain._acc_trace_id = ""               # this is what the real call site does right after "act"

    trace.adopt("")
    _begin_or_adopt_trace(brain, "qué tiempo hace en Tarragona", False)
    assert trace.current() != first_tid
    trace.adopt("")


# ── EXPLICIT closing of a conversational flow (V2-090 addendum, 2026-08-15) ─────────────────────────────────────
# Real case: the operator restarted the system and the master still showed "7 active" — a normal turn (or kickoff)
# had NO way to say "I'm done", so the master could only GUESS from RECENCY (< 60s), and
# guessed wrong as soon as the turn had just completed. `_flow_should_close` is the pure decision; the real wrapper
# (`_maybe_close_flow`) calls it from `_run` only on the CLEAN path (never after a barge-in cancellation).
def test_flow_should_close_a_plain_finished_turn():
    assert _flow_should_close("T1·aaaa", "", set(), False) is True


def test_flow_should_not_close_without_a_trace():
    assert _flow_should_close("", "", set(), False) is False


def test_flow_should_not_close_while_the_accumulator_still_expects_more():
    assert _flow_should_close("T1·aaaa", "T1·aaaa", set(), False) is False


def test_flow_should_not_close_with_a_confirmation_still_pending_on_it():
    assert _flow_should_close("T1·aaaa", "", {"T1·aaaa"}, False) is False


def test_flow_should_not_close_while_its_worker_is_still_running():
    assert _flow_should_close("T1·aaaa", "", set(), True) is False


# ── just_escalated — a structural race, not an occasional one (V2-113, 2026-08-17) ───────────────────────────────
# Real trace evidence (session dd64a1a7-..., trace T5·d232): `escalate.requested` published at 722148.675ms, the
# flow's "end" fired at 722148.859ms — 184ms later, still inside the SAME synchronous turn — while the worker
# dispatch.run_listener spawns didn't start until 741431.474ms, ~19s later. `has_live_worker` was reliably still
# False at close-time because dispatch.run_listener never got a scheduler turn to register the SessionRecord.
def test_flow_should_not_close_right_after_publishing_an_escalation():
    assert _flow_should_close("T1·aaaa", "", set(), False, just_escalated=True) is False


def test_flow_should_close_normally_once_a_worker_is_actually_registered():
    # has_live_worker=True wins regardless of just_escalated (dispatch.run_listener finished registering).
    assert _flow_should_close("T1·aaaa", "", set(), True, just_escalated=True) is False


def test_flow_closes_normally_when_nothing_was_escalated_this_turn():
    # just_escalated defaults False — a plain conversational turn is unaffected by this guard.
    assert _flow_should_close("T1·aaaa", "", set(), False) is True


# ── _close_flow_now reads brain._escalated_trace_id (V2-113) ──────────────────────────────────────────────────────
def test_close_flow_now_defers_while_this_traces_escalation_is_unresolved(monkeypatch):
    from voice.engine.llm.providers import nucleo as nmod

    brain = _fresh_brain()
    _begin_or_adopt_trace(brain, "búscame vuelos a Ibiza", True)
    tid = trace.current()
    brain._escalated_trace_id = tid

    closed = {"v": False}

    def _fake_emit(*a, **k):
        closed["v"] = True

    monkeypatch.setattr("nucleo.dispatch.has_live_trace", lambda t: False)
    monkeypatch.setattr("widgets.confirm.pending", lambda: {})
    monkeypatch.setattr("voice.observer.emit", _fake_emit)
    nmod._close_flow_now(tid, brain)
    assert closed["v"] is False, "must NOT close while the escalation's own outcome is still unknown"


def test_close_flow_now_closes_once_a_different_traces_escalation_is_pending():
    from voice.engine.llm.providers import nucleo as nmod

    brain = _fresh_brain()
    _begin_or_adopt_trace(brain, "búscame vuelos a Ibiza", True)
    tid = trace.current()
    brain._escalated_trace_id = "T9·other"   # a DIFFERENT trace's escalation is pending, not this one
    trace.adopt("")
    # a real close attempt for `tid` should proceed to `_flow_should_close`'s normal plain-turn verdict (True) —
    # verified indirectly via `_flow_should_close` itself, since it's the pure decision under test here.
    assert _flow_should_close(tid, "", set(), False, just_escalated=(brain._escalated_trace_id == tid)) is True


# ── _release_acc_trace_if_fresh (2026-08-16) — the real bug diagnosed live ──────────────────────────────────────
# "Necesito que cierres todos los widgets..." remained "EN CURSO" in the master forever despite doing its job (closing
# the widgets) correctly: `_begin_or_adopt_trace` sets `_acc_trace_id` for a fresh turn on the assumption that
# the accumulator's `offer()` a few lines below will clear it once resolved — but the hard-interrupt/echo/ambient
# early-return branches `return` BEFORE ever reaching `offer()`, so `_acc_trace_id` stays pinned to that trace
# and `_flow_should_close`'s "a chain still expects a continuation" guard blocks it from EVER closing.
def test_a_fresh_hard_interrupt_turn_releases_its_own_acc_trace():
    brain = _fresh_brain()
    brain._acc = Accumulator()
    _begin_or_adopt_trace(brain, "cierra todos los widgets", False)
    tid = trace.current()
    assert brain._acc_trace_id == tid           # the bug's precondition: freshly pinned by _begin_or_adopt_trace

    _release_acc_trace_if_fresh(brain)

    assert brain._acc_trace_id == ""
    assert _flow_should_close(tid, brain._acc_trace_id, set(), False) is True
    trace.adopt("")


def test_release_does_not_end_a_genuinely_pending_chain_it_only_adopted():
    """If a hard interrupt ("para") lands MID a real fragment chain from a PRIOR turn, `_begin_or_adopt_trace`
    ADOPTS that chain's trace rather than opening a fresh one — releasing it here would end an unrelated,
    still-unresolved chain's protection early, not just this turn's own bookkeeping."""
    brain = _fresh_brain()
    brain._acc = Accumulator()
    _begin_or_adopt_trace(brain, "Pues mira, me vas a borrar", False)
    chain_tid = trace.current()
    _offer(brain._acc, "Pues mira, me vas a borrar")   # incomplete -> "hold": a real chain is now pending
    assert brain._acc.pending()

    trace.adopt("")
    _begin_or_adopt_trace(brain, "para", False)         # adopts chain_tid, does NOT open a fresh trace
    assert trace.current() == chain_tid

    _release_acc_trace_if_fresh(brain)

    assert brain._acc_trace_id == chain_tid, "an in-flight chain from a PRIOR turn must survive"
    trace.adopt("")


# ── DEFERRED closing while the bot is still speaking (2026-08-16, real case: the turn disappeared from the master
# while zaelar was still narrating the response) — `_maybe_close_flow` now queues instead of closing when `proactive.
# bot_speaking()` is True; `drain_pending_flow_closes` (called by agent.py on returning to idle) drains the queue.
def test_maybe_close_flow_queues_instead_of_closing_while_the_bot_is_still_speaking(monkeypatch):
    from voice import proactive
    from voice.engine.llm.providers import nucleo as nucleo_mod

    closes = []
    monkeypatch.setattr("voice.observer.emit",
                         lambda kind, label, **kw: closes.append((kind, label)) if kind == "flow" else None)
    trace.adopt("")
    trace.begin("hola", origin="turno")
    tid = trace.current()
    brain = NucleoLLM()

    proactive.register_bot_probe(lambda: True)
    try:
        nucleo_mod._maybe_close_flow(brain)
        assert closes == [], "must not close while its own TTS is still narrating the answer"
        assert tid in nucleo_mod._PENDING_FLOW_CLOSES
    finally:
        proactive.clear_speaker()
        nucleo_mod._PENDING_FLOW_CLOSES.clear()
    trace.adopt("")


def test_maybe_close_flow_closes_immediately_when_the_bot_is_not_speaking(monkeypatch):
    from voice.engine.llm.providers import nucleo as nucleo_mod

    closes = []
    monkeypatch.setattr("voice.observer.emit",
                         lambda kind, label, **kw: closes.append((kind, label)) if kind == "flow" else None)
    trace.adopt("")
    trace.begin("hola", origin="turno")
    brain = NucleoLLM()

    nucleo_mod._maybe_close_flow(brain)   # no bot-probe registered — same as an uninstrumented test env

    assert ("flow", "end") in closes
    trace.adopt("")


def test_drain_closes_a_queued_flow_once_speech_goes_idle(monkeypatch):
    from voice.engine.llm.providers import nucleo as nucleo_mod

    closes = []
    monkeypatch.setattr("voice.observer.emit",
                         lambda kind, label, **kw: closes.append((kind, label)) if kind == "flow" else None)
    trace.adopt("")
    trace.begin("hola", origin="turno")
    tid = trace.current()
    brain = NucleoLLM()
    nucleo_mod._PENDING_FLOW_CLOSES[tid] = brain

    nucleo_mod.drain_pending_flow_closes()

    assert ("flow", "end") in closes
    assert nucleo_mod._PENDING_FLOW_CLOSES == {}
    trace.adopt("")


def test_drain_still_respects_flow_should_close_conditions(monkeypatch):
    """Re-checked at drain time, not just trusted from when it was queued — a worker could have started on this
    trace while the audio was still playing out."""
    from voice.engine.llm.providers import nucleo as nucleo_mod

    closes = []
    monkeypatch.setattr("voice.observer.emit",
                         lambda kind, label, **kw: closes.append((kind, label)) if kind == "flow" else None)
    monkeypatch.setattr("nucleo.dispatch.has_live_trace", lambda tid: True)
    trace.adopt("")
    trace.begin("hola", origin="turno")
    tid = trace.current()
    brain = NucleoLLM()
    nucleo_mod._PENDING_FLOW_CLOSES[tid] = brain

    nucleo_mod.drain_pending_flow_closes()

    assert closes == [], "a live worker spawned on this trace owns the close now"
    trace.adopt("")


# ── REAL USE CASE: a hesitant sentence = ONE flow (V2-116, session b403c979) ────────────────────────────────
# The five STT finals that LiveKit delivered, verbatim and in order, from one uninterrupted spoken sentence:
# «Mira, lo que quiero es que me digas cuál es el último Ferrari que ha salido al mercado, entonces quiero que me
# muestres…». In production, FOUR corr_ids appeared (T2·73cc, T3·0a2e, T4·075a, T5·ae59), each cancelling the
# previous one due to barge-in, with two complete prompts of ~5,800 tokens thrown away.
_REAL_FRAGMENTS = [
    "Mira, lo que quiero es",
    "que me digas cuál es el",
    "último Ferrari",
    "que ha salido al mercado,",
    "entonces quiero que me muestres",
]


def _simulate_utterance(fragments, *, brain=None):
    """Simulate the voice turns that LiveKit would trigger for these fragments on a CLEAN agent instance,
    exercising THE SAME code that runs in production (`_begin_or_adopt_trace` + `Accumulator.offer` +
    `_resolve_acc_chain`). Return the list of (fragment, trace, action) tuples for each turn."""
    from voice.engine.llm.providers.nucleo import _resolve_acc_chain
    b = brain if brain is not None else _fresh_brain()
    if getattr(b, "_acc", None) is None:
        b._acc = Accumulator()
    out = []
    for frag in fragments:
        _begin_or_adopt_trace(b, frag, False)          # ← lo que hace `_run_inner` al empezar el turno
        tid = trace.current()
        action, _merged, _why, _dropped = _offer(b._acc, frag)
        if action == "act":
            _resolve_acc_chain(b)                       # ← y lo que hace al resolverse la cadena
        out.append((frag, tid, action))
    return out


def test_use_case_una_frase_titubeante_es_UN_solo_flujo():
    """THE OPERATOR'S CASE, reproduced from an empty instance: "several flows open in the middle of a sentence."

    Flows are the system's skeleton — every continuous action lasting minutes is associated with its corr_id—, so
    splitting a sentence into four breaks the entire guarantee. The measured cause is NOT the V2-096 merge (which
    works), but that flow continuity DEPENDED on correctly identifying lexical completeness: `looks_incomplete("Mira,
    lo que quiero es")` returns False — a clause dangling from the copula «es»— so the accumulator releases the
    chain, `_acc_trace_id` is cleared, and the next fragment opens a new flow. Verified that this test fails without
    `_begin_or_adopt_trace`'s grace window."""
    turns = _simulate_utterance(_REAL_FRAGMENTS)
    tids = {tid for _, tid, _ in turns}
    assert len(tids) == 1, (
        "una sola frase tiene que ser UN solo flujo; salieron "
        f"{len(tids)}: " + " · ".join(f"{f!r}→{t}" for f, t, _ in turns))
    # …and the premise that makes the fix a false negative: the first fragment is STILL judged "complete" lexically.
    # If that ever changes, this case will no longer test what it claims to test.
    assert turns[0][2] == "act", "case premise (false 'complete' on the 1st fragment) has changed"
    trace.adopt("")


def test_use_case_dos_peticiones_separadas_en_el_tiempo_siguen_siendo_dos_flujos():
    """The counterbalance: the grace window cannot glue EVERYTHING together. Once the grace seconds have passed, a new
    topic opens its own flow — otherwise the fix would turn splitting sentences into merging different tasks, which is
    just as bad for a skeleton whose purpose is to separate jobs."""
    import voice.engine.llm.providers.nucleo as _nuc
    brain = _fresh_brain()
    brain._acc = Accumulator()
    first = _simulate_utterance(["¿Qué hora es?"], brain=brain)
    assert first[0][2] == "act", "premisa: una frase completa se resuelve en el acto"
    # Advance the clock beyond the grace period (without sleeping: age the marker manually).
    tid_grace, _ts = brain._chain_grace
    brain._chain_grace = (tid_grace, 0.0)
    second = _simulate_utterance(["Ponme música"], brain=brain)
    assert second[0][1] != first[0][1], "dos peticiones sin relación no pueden compartir flujo"
    trace.adopt("")


# ── V2-123: a turn ABOUT a live task merges into its flow; it does not open a separate column ────────────────────────────
# The gap it closes, reported with a screenshot: while a worker was searching for a guitar, "yes, show me everything in
# real time" and the agent's response opened a SEPARATE flow — the V2-090 merge only kicks in if the model
# calls `send_to_worker`, and a follow-up that the model answers conversationally matches nothing.

def test_merge_target_absorbe_un_turno_conversacional_mientras_una_tarea_corre():
    assert _merge_target("T9·bbbb", ["T5·aaaa"], set()) == "T5·aaaa"


def test_merge_target_acepta_las_tools_que_solo_CONDUCEN_la_tarea_viva():
    assert _merge_target("T9·bbbb", ["T5·aaaa"], {"send_to_worker"}) == "T5·aaaa"
    assert _merge_target("T9·bbbb", ["T5·aaaa"], {"stop_worker", "recall"}) == "T5·aaaa"


def test_merge_target_no_absorbe_un_turno_que_hizo_otra_cosa():
    """Playing music while a search is running is a turn about something else, whatever is running."""
    assert _merge_target("T9·bbbb", ["T5·aaaa"], {"play_music"}) == ""
    assert _merge_target("T9·bbbb", ["T5·aaaa"], {"send_to_worker", "show_widget"}) == ""


def test_merge_target_no_adivina_entre_varias_tareas_vivas():
    """The rule since V2-090: one extra unattached flow is better than guessing which of two a "how's it going?" belongs to."""
    assert _merge_target("T9·bbbb", ["T5·aaaa", "T7·cccc"], set()) == ""


def test_merge_target_no_toca_un_turno_que_ACABA_de_lanzar_su_propia_tarea():
    assert _merge_target("T9·bbbb", ["T5·aaaa"], set(), just_escalated=True) == ""


def test_merge_target_no_absorbe_un_trace_que_YA_es_una_tarea():
    """If this trace has its own live worker, it is not a turn looking for somewhere to attach: it is a task."""
    assert _merge_target("T5·aaaa", ["T5·aaaa"], set()) == ""
    assert _merge_target("T5·aaaa", ["T5·aaaa", "T7·cccc"], set()) == ""


def test_merge_target_sin_nada_vivo_no_funde_nada():
    assert _merge_target("T9·bbbb", [], set()) == ""
    assert _merge_target("", ["T5·aaaa"], set()) == ""


def test_merge_target_el_titular_es_el_mas_antiguo_via_trace_merge():
    """`_merge_target` chooses the DESTINATION; `trace.merge` decides which remains canonical (the lowest seq), so
    a long-running task with multiple merges always converges on the first id instead of changing canonical traces."""
    assert trace.merge(_merge_target("T9·bbbb", ["T5·aaaa"], set()), "T9·bbbb") == "T5·aaaa"


def test_use_case_seguimiento_mientras_el_worker_busca_es_UN_solo_hilo(monkeypatch):
    """USE CASE from the report, with the real events: the operator requests a search (a live worker on its trace), and
    immediately says "yes, show me everything in real time" — which the model answers conversationally, without a tool.
    There used to be TWO corr_ids; now the second merges and the marker is emitted under the NEW trace (so the reader
    can resolve it) while pointing to the canonical trace."""
    from nucleo import dispatch
    from nucleo.workers.session import SessionRecord
    monkeypatch.setattr(dispatch, "_SESSIONS", {}, raising=False)
    dispatch._SESSIONS["w1"] = SessionRecord(task_id="w1", kind="web", status="running",
                                             goal="busca una guitarra zurda para niño", trace_id="T5·aaaa")
    assert dispatch.live_traces() == ["T5·aaaa"], "premisa: la tarea de la guitarra está viva"

    seen = []
    monkeypatch.setattr(trace, "merge", lambda a, b: seen.append((a, b)) or a)
    brain = NucleoLLM.__new__(NucleoLLM)
    brain._acc_trace_id = ""
    brain._escalated_trace_id = ""
    brain._turn_tools = set()
    _close_flow_now("T9·bbbb", brain)
    assert seen == [("T5·aaaa", "T9·bbbb")], "el turno de seguimiento tiene que fundirse en la tarea viva"


def test_una_tarea_terminada_ya_no_absorbe_nada(monkeypatch):
    """`live_traces()` filters by status just like `_live_keys`. Without that filter, a completed task would keep
    absorbing subsequent conversation forever — the same kind of failure that `active_sessions()` used to carry."""
    from nucleo import dispatch
    from nucleo.workers.session import SessionRecord
    monkeypatch.setattr(dispatch, "_SESSIONS", {}, raising=False)
    dispatch._SESSIONS["w1"] = SessionRecord(task_id="w1", kind="web", status="done",
                                             goal="busca una guitarra zurda", trace_id="T5·aaaa")
    assert dispatch.live_traces() == []
    assert _merge_target("T9·bbbb", dispatch.live_traces(), set()) == ""
