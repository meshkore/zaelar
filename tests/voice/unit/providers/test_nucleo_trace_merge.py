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
    NucleoLLM, _begin_or_adopt_trace, _flow_should_close, _release_acc_trace_if_fresh,
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


# ── Cierre EXPLÍCITO de un flujo conversacional (V2-090 addenda, 2026-08-15) ─────────────────────────────────────
# Real: el operador reinició el sistema y el master seguía mostrando "7 activos" — un turno normal (o el kickoff)
# no tenía NINGUNA forma de decir "ya terminé", así que el master solo podía ADIVINAR por RECENCIA (< 60s), y
# adivinaba mal en cuanto el turno acababa de completarse. `_flow_should_close` es la decisión pura; la envoltura
# real (`_maybe_close_flow`) la llama `_run` solo en el camino LIMPIO (nunca tras una cancelación por barge-in).
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
# "Necesito que cierres todos los widgets..." sat "EN CURSO" in the master forever despite doing its job (closing
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


# ── Cierre APLAZADO mientras el bot sigue hablando (2026-08-16, real: el turno desapareció del master mientras
# zaelar todavía narraba la respuesta) — `_maybe_close_flow` ahora encola en vez de cerrar si `proactive.
# bot_speaking()` es True; `drain_pending_flow_closes` (llamado por agent.py al volver a idle) resuelve la cola.
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


# ── CASO DE USO REAL: una frase titubeante = UN flujo (V2-116, sesión b403c979) ────────────────────────────────
# Los cinco finales de STT que LiveKit entregó, verbatim y en orden, de una sola frase hablada sin parar:
# «Mira, lo que quiero es que me digas cuál es el último Ferrari que ha salido al mercado, entonces quiero que me
# muestres…». En producción salieron CUATRO corr_ids (T2·73cc, T3·0a2e, T4·075a, T5·ae59), cada uno cancelando al
# anterior por barge-in, con dos prompts completos de ~5.800 tokens tirados a la basura.
_REAL_FRAGMENTS = [
    "Mira, lo que quiero es",
    "que me digas cuál es el",
    "último Ferrari",
    "que ha salido al mercado,",
    "entonces quiero que me muestres",
]


def _simulate_utterance(fragments, *, brain=None):
    """Simula los turnos de voz que LiveKit dispararía para estos fragmentos, sobre una instancia de agente
    LIMPIA, ejercitando EL MISMO código que corre en producción (`_begin_or_adopt_trace` + `Accumulator.offer` +
    `_resolve_acc_chain`). Devuelve la lista de (fragmento, trace, acción) por turno."""
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
    """EL CASO DEL OPERADOR, reproducido desde una instancia vacía: «en mitad de una frase se abren varios flujos».

    Los flujos son el esqueleto del sistema — toda acción continua que dure minutos se asocia a su corr_id—, así
    que partir una frase en cuatro rompe la garantía entera. La causa medida NO es el merge de V2-096 (que
    funciona) sino que la continuidad del flujo COLGABA de acertar la completitud léxica: `looks_incomplete("Mira,
    lo que quiero es")` devuelve False —cláusula colgada de la cópula «es»— así que el acumulador suelta la
    cadena, se limpia `_acc_trace_id` y el trozo siguiente abre flujo nuevo. Verificado que este test falla sin
    la ventana de gracia de `_begin_or_adopt_trace`."""
    turns = _simulate_utterance(_REAL_FRAGMENTS)
    tids = {tid for _, tid, _ in turns}
    assert len(tids) == 1, (
        "una sola frase tiene que ser UN solo flujo; salieron "
        f"{len(tids)}: " + " · ".join(f"{f!r}→{t}" for f, t, _ in turns))
    # …y la premisa que hace falso-negativo el arreglo: el primer trozo SIGUE juzgándose «completo» por el léxico.
    # Si algún día deja de serlo, este caso ya no probaría lo que cree probar.
    assert turns[0][2] == "act", "la premisa del caso (falso «completo» en el 1er trozo) ha cambiado"
    trace.adopt("")


def test_use_case_dos_peticiones_separadas_en_el_tiempo_siguen_siendo_dos_flujos():
    """El contrapeso: la ventana de gracia no puede pegar TODO. Pasados los segundos de gracia, un tema nuevo abre
    su propio flujo — si no, el arreglo cambiaría partir frases por fundir tareas distintas, que es igual de malo
    para un esqueleto que existe para separar trabajos."""
    import voice.engine.llm.providers.nucleo as _nuc
    brain = _fresh_brain()
    brain._acc = Accumulator()
    first = _simulate_utterance(["¿Qué hora es?"], brain=brain)
    assert first[0][2] == "act", "premisa: una frase completa se resuelve en el acto"
    # el reloj avanza más allá de la gracia (sin dormir: se envejece la marca a mano)
    tid_grace, _ts = brain._chain_grace
    brain._chain_grace = (tid_grace, 0.0)
    second = _simulate_utterance(["Ponme música"], brain=brain)
    assert second[0][1] != first[0][1], "dos peticiones sin relación no pueden compartir flujo"
    trace.adopt("")
