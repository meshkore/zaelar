"""A correction that continues an in-progress accumulator chain (V2-096) must not open a new flow (V2-090 addenda,
2026-08-15). Real production data showed ONE continuous utterance ("borra toda la agenda...") splitting into five
separate corr_ids, because LiveKit closes a turn per STT-final segment and `trace.begin()` fired unconditionally
per turn. `_begin_or_adopt_trace` is factored out of `_run_inner` precisely so this is testable without a live
LiveKit stream — see `voice/engine/llm/providers/nucleo.py::_begin_or_adopt_trace`.
"""
from nucleo.flash.accumulator import Accumulator
from voice import trace
from voice.engine.llm.providers.nucleo import NucleoLLM, _begin_or_adopt_trace, _flow_should_close


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
    brain._acc.offer("Pues mira, me vas a borrar")   # incomplete -> "hold", buffer now non-empty
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
    action, _merged, _why, _dropped = brain._acc.offer("busca una moto de segunda mano.")
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
