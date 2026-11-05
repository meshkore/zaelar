"""Durable recall is composed OUTSIDE the event loop and bounded — in BOTH channels (F1, 2026-08-23).

The harness reported it with the measured cost: with slow memory (a 1.1 GB download), `probe.py` blocked the
ENTIRE engine — every endpoint timed out and the batch died as «INFRA: timed out», without mentioning
memory anywhere. The VOICE path already survived.

And the defect is stated by the docstring of `prompt.build_flash_system`: the real parameter is `recall_block` (the
caller composes it outside the loop, on demand), and **`recall_query` is the TEST COMPATIBILITY path**,
which composes inline. The text channel used the test path in production.

What these cases pin down is the entire class, not the instance: a PROTECTION that exists in one channel and not in
the other is indistinguishable from having none — the failure emerges through the channel nobody remembered, at the worst moment.
"""
import asyncio

from nucleo.turn import recall_budget


def test_nothing_to_ask_costs_nothing():
    assert asyncio.run(recall_budget.compose("")) == ("", [])
    assert asyncio.run(recall_budget.compose("   ")) == ("", [])


def test_a_slow_retriever_does_NOT_take_the_turn_down(monkeypatch):
    """The measured case. Degrading is the POINT, not a workaround: a turn with less memory is a worse response; a
    turn that never arrives is a dead agent.

    It is timed deliberately INSIDE the loop. `wait_for` cancels the wait, not the THREAD — `to_thread` runs in
    the executor and nobody can interrupt it from outside — so an enclosing `asyncio.run()` blocks while closing,
    waiting for that thread, and would measure 2 s with the guard working perfectly. What this case asserts is what
    actually matters on a live server: that the TURN remains free within its budget. The slow thread finishes alone,
    at its own pace, with nobody waiting for it."""
    import time as _t
    from nucleo.turn.prompt import recall as prompt_mod
    monkeypatch.setenv("ZAELAR_RECALL_BUDGET_MS", "50")
    monkeypatch.setattr(prompt_mod, "compose_recall", lambda q, t=None: (_t.sleep(2), ("bloque", [1]))[1])

    async def _medir():
        timings: dict = {}
        t0 = _t.perf_counter()
        got = await recall_budget.compose("qué sabes de mí", timings)
        return got, timings, _t.perf_counter() - t0

    got, timings, elapsed = asyncio.run(_medir())
    assert got == ("", []), "el turno se quedó esperando a la memoria"
    assert timings.get("recall_timeout") is True, "y encima no dejó rastro de por qué faltó el recall"
    assert elapsed < 1.0, f"el turno tardó {elapsed:.2f}s: no cortó en su presupuesto"


def test_a_broken_retriever_degrades_instead_of_raising(monkeypatch):
    from nucleo.turn.prompt import recall as prompt_mod

    def _boom(q, t=None):
        raise RuntimeError("simulado")
    monkeypatch.setattr(prompt_mod, "compose_recall", _boom)
    assert asyncio.run(recall_budget.compose("algo")) == ("", [])


def test_a_recall_within_budget_arrives_whole(monkeypatch):
    """The counterpart, without which «does not hang» could be satisfied by never remembering anything."""
    from nucleo.turn.prompt import recall as prompt_mod
    monkeypatch.setattr(prompt_mod, "compose_recall", lambda q, t=None: (f"RECUERDO: {q}", [7]))
    assert asyncio.run(recall_budget.compose("los hijos")) == ("RECUERDO: los hijos", [7])


def test_one_knob_moves_both_channels(monkeypatch):
    """Two diverging budgets are how «voice works» and «text hangs» become two distinct failure reports for a single cause."""
    monkeypatch.setenv("ZAELAR_RECALL_BUDGET_MS", "1500")
    assert abs(recall_budget.budget_s() - 1.5) < 1e-9
    monkeypatch.setenv("ZAELAR_RECALL_BUDGET_MS", "no-es-un-numero")
    assert recall_budget.budget_s() > 0, "un valor ilegible no puede dejar el presupuesto en cero"


# ── A recall the turn gave up on has to be VISIBLE (2026-08-25) ───────────────────────────────────────────────
#
# The flag above (`recall_timeout`) existed and this very node asserted it — and NOTHING read it. Measured over
# the 223 live session timelines in `.meshkore/logs/sessions/`: of the 27 turns that asked for durable recall,
# 21 came back with `mem_ms: null` and «→ 0 tarjetas del largo plazo», which is exactly what a turn whose memory
# genuinely held nothing looks like. The six that finished took 556-797 ms against an 800 ms budget.
#
# That is the failure class this file already names, one layer up: a protection that fires without telling
# anybody is indistinguishable from a system that had nothing to say. Cheap to write, and its answer is the
# reassuring one — which is what makes it expensive.

def _capture(monkeypatch):
    """Intercept both outward channels. They are imported lazily inside `_publish`, so patching the modules is
    what a real turn would go through — no seam invented for the test."""
    from voice import health_state, observer
    filas: list = []
    monkeypatch.setattr(observer, "emit",
                        lambda kind, label, text="", role="", extra=None:
                        filas.append({"kind": kind, "label": label, "text": text, "extra": extra or {}}))
    health_state.clear("memory")
    return filas


def _slow(seconds=0.4):
    import time as _t
    return lambda q, t=None: (_t.sleep(seconds), ("bloque", [1]))[1]


def test_a_recall_over_budget_leaves_a_row_in_the_timeline(monkeypatch):
    """Without this the loss is only a dict key the turn throws away and a `logging.info` with no timestamp."""
    from nucleo.turn.prompt import recall as prompt_mod
    filas = _capture(monkeypatch)
    monkeypatch.setenv("ZAELAR_RECALL_BUDGET_MS", "50")
    monkeypatch.setattr(prompt_mod, "compose_recall", _slow())

    asyncio.run(recall_budget.compose("qué sabes de mi guitarra", {}))

    memoria = [f for f in filas if f["kind"] == "memory"]
    assert memoria, "el turno perdió su memoria durable y la línea de tiempo no lo cuenta"
    fila = memoria[0]
    assert fila["extra"].get("reason") == "timeout"
    assert fila["extra"].get("budget_ms") == 50, "sin el presupuesto en la fila no se sabe si sobró poco o mucho"
    assert "guitarra" in fila["extra"].get("query", ""), "sin la pregunta la fila no se puede atar a su turno"


def test_a_recall_over_budget_turns_the_status_light_amber(monkeypatch):
    """The row records what happened AFTERWARD; the light is the only thing visible WHILE it happens."""
    from nucleo.turn.prompt import recall as prompt_mod
    from voice import health_state
    _capture(monkeypatch)
    monkeypatch.setenv("ZAELAR_RECALL_BUDGET_MS", "50")
    monkeypatch.setattr(prompt_mod, "compose_recall", _slow())

    asyncio.run(recall_budget.compose("qué sabes de mí", {}))

    rec = health_state.get("memory")
    assert rec is not None and rec["kind"] == "degraded", "la memoria degradada no enciende el ámbar"


def test_a_recall_INSIDE_budget_says_nothing(monkeypatch):
    """The counterpart. A warning that always appears is not a warning: it is noise, and people learn to ignore it."""
    from nucleo.turn.prompt import recall as prompt_mod
    from voice import health_state
    filas = _capture(monkeypatch)
    monkeypatch.setattr(prompt_mod, "compose_recall", lambda q, t=None: ("RECUERDO", [7]))

    asyncio.run(recall_budget.compose("los hijos", {}))

    assert not filas, f"un recall que llegó bien ensució la línea de tiempo: {filas}"
    assert health_state.get("memory") is None, "un recall que llegó bien encendió el ámbar"


def test_it_does_NOT_wipe_an_unrelated_memory_warning(monkeypatch):
    """The `memory` key is SHARED with `memory/` (misaligned vector space, degraded embeddings).

    Clearing it on exit — the reflexive «service healthy again» gesture — would erase a warning this module did not
    set and cannot judge. It is allowed to age out with its TTL, just as the rest of `memory/` does."""
    from nucleo.turn.prompt import recall as prompt_mod
    from voice import health_state
    _capture(monkeypatch)
    health_state.record("memory", "degraded", "espacio vectorial descuadrado")
    monkeypatch.setattr(prompt_mod, "compose_recall", lambda q, t=None: ("RECUERDO", [7]))

    asyncio.run(recall_budget.compose("los hijos", {}))

    rec = health_state.get("memory")
    assert rec is not None and "vectorial" in rec["text"], "se llevó por delante un aviso ajeno"


def test_an_abandoned_recall_does_NOT_write_its_cost_into_the_turn(monkeypatch):
    """`wait_for` cancels the WAIT, not the thread — and the thread was writing into the turn's `timings`.

    Measured 2026-08-25 on the live timelines: reply events carried `mem_query_ms` of 2.1 s, 3.5 s and 21 s
    against an 800 ms budget. Ghosts: the cost of a recall no turn ever used, published as that turn's memory
    latency — which is the very question V2-311 set out to answer. The number was not merely late, it was
    ATTRIBUTED to a turn that had already given up.

    The thread is deliberately awaited: the failure exists only AFTER it finishes, so a case that does not give it
    time to finish always passes, with or without the fix."""
    import time as _t
    from nucleo.turn.prompt import recall as prompt_mod
    _capture(monkeypatch)
    monkeypatch.setenv("ZAELAR_RECALL_BUDGET_MS", "50")

    def _tarde(q, t=None):
        _t.sleep(0.3)
        if t is not None:
            t["mem_query_ms"] = 300.0
        return "bloque", [1]
    monkeypatch.setattr(prompt_mod, "compose_recall", _tarde)

    timings: dict = {}
    asyncio.run(recall_budget.compose("qué sabes de mí", timings))
    _t.sleep(0.5)                                     # the abandoned thread finishes NOW and writes its data

    assert timings.get("recall_timeout") is True
    assert "mem_query_ms" not in timings, (
        f"un recall que el turno abandonó le metió su coste en la contabilidad: {timings}")


def test_a_recall_within_budget_DOES_report_its_cost(monkeypatch):
    """The counterpart: isolating the abandoned thread must not cost us the valid metric."""
    from nucleo.turn.prompt import recall as prompt_mod
    _capture(monkeypatch)

    def _a_tiempo(q, t=None):
        if t is not None:
            t["mem_query_ms"] = 42.0
        return "RECUERDO", [7]
    monkeypatch.setattr(prompt_mod, "compose_recall", _a_tiempo)

    timings: dict = {}
    assert asyncio.run(recall_budget.compose("los hijos", timings)) == ("RECUERDO", [7])
    assert timings.get("mem_query_ms") == 42.0, "se perdió el coste de un recall que SÍ llegó"


# ── Reinforcement follows DELIVERY, not computation (V2-311 step 3, 2026-08-25) ──────────────────────────────────
#
# `memory.query` reinforced when COMPOSING the block, and composing is not using it: of the 27 live recalls measured, 21
# were abandoned when the budget expired and the thread still finished, so they increased the weight and reset the
# expiry (durable write) of pills for questions that were never answered with them. The «this is used» signal was
# fed by the very work that was discarded.
#
# The module's three outcomes are cleanly divided — delivered within budget, delivered late, discarded as stale —
# and only the TWO deliveries reinforce.

def _con_refuerzo(monkeypatch, ids_seleccionados=(7,)):
    """Replace the writer and return the list of what was actually reinforced."""
    from memory import api as memory_api
    reforzado: list = []
    monkeypatch.setattr(memory_api, "reinforce", lambda ids: reforzado.extend(ids))

    def _compose(q, t=None):
        if t is not None:
            t["recall_reinforce_ids"] = list(ids_seleccionados)
        return "RECUERDO", [1, 2, 3, 4, 5]        # `ids` of the entire package: NEVER what gets reinforced
    return reforzado, _compose


def test_a_delivered_recall_reinforces_and_only_the_selected_pills(monkeypatch):
    from nucleo.turn.prompt import recall as prompt_mod
    _capture(monkeypatch)
    reforzado, _compose = _con_refuerzo(monkeypatch)
    monkeypatch.setattr(prompt_mod, "compose_recall", _compose)

    asyncio.run(recall_budget.compose("qué sabes de mí", {}))

    assert reforzado == [7], (
        f"o no reforzó lo entregado, o reforzó el paquete entero en vez de la selección de memory/: {reforzado}")


def test_an_ABANDONED_recall_reinforces_NOTHING(monkeypatch):
    """The measured defect: the thread still finishes, and until now its reinforcement was applied to a turn that did not see it."""
    import time as _t
    from nucleo.turn.prompt import recall as prompt_mod
    _capture(monkeypatch)
    reforzado, _compose = _con_refuerzo(monkeypatch)
    monkeypatch.setenv("ZAELAR_RECALL_BUDGET_MS", "50")

    def _tarde(q, t=None):
        _t.sleep(0.3)
        return _compose(q, t)
    monkeypatch.setattr(prompt_mod, "compose_recall", _tarde)
    monkeypatch.setattr(recall_budget, "_salvage", lambda *a, **k: None)   # isolate: nothing is salvaged here

    asyncio.run(recall_budget.compose("qué sabes de mí", {}))
    _t.sleep(0.5)                                     # the abandoned thread finishes NOW

    assert reforzado == [], f"un recall que nadie recibió subió el peso y reseteó la caducidad: {reforzado}"


def test_a_STALE_late_recall_reinforces_NOTHING(monkeypatch):
    """If the conversation has already moved on, the block is discarded — and discarding is not delivery."""
    _capture(monkeypatch)
    reforzado, _ = _con_refuerzo(monkeypatch)

    class _Fut:
        def cancelled(self): return False
        def exception(self): return None
        def result(self): return ("RECUERDO", [1, 2, 3])

    recall_budget._salvage(_Fut(), "una pregunta vieja", asked_gen=-1,   # generation that is no longer current
                           propias={"recall_reinforce_ids": [7]})

    assert reforzado == [], "un bloque descartado por rancio reforzó igualmente"


def test_a_FRESH_late_recall_is_dropped_and_reinforces_NOTHING(monkeypatch):
    """V2-851 F5: a late block no longer rides the next turn as a note, so even a fresh one is not delivered —
    and what is not delivered is not reinforced."""
    _capture(monkeypatch)
    reforzado, _ = _con_refuerzo(monkeypatch)

    class _Fut:
        def cancelled(self): return False
        def exception(self): return None
        def result(self): return ("RECUERDO", [1, 2, 3])

    with recall_budget._GEN_LOCK:
        gen_actual = recall_budget._GEN                # nobody has asked since then → fresh

    recall_budget._salvage(_Fut(), "la pregunta del turno anterior", asked_gen=gen_actual,
                           propias={"recall_reinforce_ids": [7]})

    assert reforzado == [], f"a late block nobody received was reinforced: {reforzado}"
