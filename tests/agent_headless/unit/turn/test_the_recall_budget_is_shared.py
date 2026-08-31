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
import inspect

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
    from nucleo.flash import prompt as prompt_mod
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
    from nucleo.flash import prompt as prompt_mod

    def _boom(q, t=None):
        raise RuntimeError("simulado")
    monkeypatch.setattr(prompt_mod, "compose_recall", _boom)
    assert asyncio.run(recall_budget.compose("algo")) == ("", [])


def test_a_recall_within_budget_arrives_whole(monkeypatch):
    """The counterpart, without which «does not hang» could be satisfied by never remembering anything."""
    from nucleo.flash import prompt as prompt_mod
    monkeypatch.setattr(prompt_mod, "compose_recall", lambda q, t=None: (f"RECUERDO: {q}", [7]))
    assert asyncio.run(recall_budget.compose("los hijos")) == ("RECUERDO: los hijos", [7])


def test_one_knob_moves_both_channels(monkeypatch):
    """Two diverging budgets are how «voice works» and «text hangs» become two distinct failure reports for a single cause."""
    monkeypatch.setenv("ZAELAR_RECALL_BUDGET_MS", "1500")
    assert abs(recall_budget.budget_s() - 1.5) < 1e-9
    monkeypatch.setenv("ZAELAR_RECALL_BUDGET_MS", "no-es-un-numero")
    assert recall_budget.budget_s() > 0, "un valor ilegible no puede dejar el presupuesto en cero"


def test_no_channel_composes_the_recall_inside_the_loop():
    """The class guard. `recall_query=` is the test path: in production it composes INLINE, and using it is
    exactly the failure that brought down the engine. All three turn entry points pass through the guard."""
    from nucleo.flash import probe, probe_api
    from voice.engine.llm.providers import nucleo as voice_provider

    import ast

    for mod, name in ((probe, "probe.run_turn"), (probe_api, "probe_api"),
                      (voice_provider, "el provider de voz")):
        src = inspect.getsource(mod)
        assert "recall_budget" in src, f"{name} no pasa por la guarda con presupuesto"
        # Inspect the CODE, not the text. Searching for the string `recall_query=` also finds it in a
        # comment that EXPLAINS why it is not used — this happened while writing this very guard, and it is the second time
        # today that prose about a pattern has brought down a string-matching guard.
        usados = [k.arg for n in ast.walk(ast.parse(src)) if isinstance(n, ast.Call) for k in n.keywords]
        assert "recall_query" not in usados, \
            f"{name} volvió a la ruta de compatibilidad (compone el recall dentro del loop)"


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
    from nucleo.flash import prompt as prompt_mod
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
    from nucleo.flash import prompt as prompt_mod
    from voice import health_state
    _capture(monkeypatch)
    monkeypatch.setenv("ZAELAR_RECALL_BUDGET_MS", "50")
    monkeypatch.setattr(prompt_mod, "compose_recall", _slow())

    asyncio.run(recall_budget.compose("qué sabes de mí", {}))

    rec = health_state.get("memory")
    assert rec is not None and rec["kind"] == "degraded", "la memoria degradada no enciende el ámbar"


def test_a_recall_INSIDE_budget_says_nothing(monkeypatch):
    """The counterpart. A warning that always appears is not a warning: it is noise, and people learn to ignore it."""
    from nucleo.flash import prompt as prompt_mod
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
    from nucleo.flash import prompt as prompt_mod
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
    from nucleo.flash import prompt as prompt_mod
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
    from nucleo.flash import prompt as prompt_mod
    _capture(monkeypatch)

    def _a_tiempo(q, t=None):
        if t is not None:
            t["mem_query_ms"] = 42.0
        return "RECUERDO", [7]
    monkeypatch.setattr(prompt_mod, "compose_recall", _a_tiempo)

    timings: dict = {}
    assert asyncio.run(recall_budget.compose("los hijos", timings)) == ("RECUERDO", [7])
    assert timings.get("mem_query_ms") == 42.0, "se perdió el coste de un recall que SÍ llegó"


# ── V2-311 step 2: a recall that arrives LATE is the next turn's memory — or nobody's ─────────────────
#
# 77% of live recalls (21/27, measured by memory-dev across 223 sessions) were abandoned when the budget expired
# — and ALL still finished: the thread ran to completion and the composed block died in a future nobody inspected.
# The turn paid the full cost 100% of the time and received the result 22% of the time.
#
# The production queue (2.1 s / 3.5 s / 21 s) is why there is a freshness cutoff, and the cutoff is NOT a clock:
# it is «no turn has asked since then». If generation advanced, the conversation advanced — and V2-254
# measured what stale memory does to a conversation that has already moved (weather in Soria → plumber in
# Soria). Seconds would be a proxy for that; turns ARE that.

def _con_notas(monkeypatch):
    """The real mailbox, isolated: what is measured is that the note REACHES the mailbox drained by the next turn."""
    from voice import brain_notes
    monkeypatch.setattr(brain_notes, "_pending", [])
    return brain_notes


def test_a_late_recall_becomes_the_next_turns_note(monkeypatch):
    import time as _t

    from nucleo.flash import prompt as prompt_mod
    notas = _con_notas(monkeypatch)
    monkeypatch.setenv("ZAELAR_RECALL_BUDGET_MS", "50")

    def _tarde(q, t=None):
        _t.sleep(0.25)
        return "Marc vive en Soria y busca guitarra", [7, 9]
    monkeypatch.setattr(prompt_mod, "compose_recall", _tarde)

    out = asyncio.run(recall_budget.compose("qué sabes de mí"))
    assert out == ("", [])                       # THIS turn still has no memory: the contract does not change
    _t.sleep(0.45)                               # the thread finishes and the callback runs

    got = notas.drain()
    assert len(got) == 1, "el bloque compuesto murió en un futuro que nadie miraba — otra vez"
    nota = got[0]
    assert "Marc vive en Soria" in nota and "qué sabes de mí" in nota
    # findings.py: the note does not ORDER an announcement — it states what arrived and allows it to be ignored; the brain judges
    assert "ignóralo" in nota
    # TEXT only: the ids feed reinforcement when used, and a turn that did not see the block reinforces nothing
    assert "7" not in nota.split("«")[0] and "[7, 9]" not in nota


def test_a_late_recall_after_another_turn_asked_is_DROPPED(monkeypatch):
    """The freshness cutoff. Without this, the 21-second recall lands five turns late in a conversation that
    has already moved elsewhere — V2-254's hijacking dressed up as an improvement."""
    import time as _t

    from nucleo.flash import prompt as prompt_mod
    notas = _con_notas(monkeypatch)
    monkeypatch.setenv("ZAELAR_RECALL_BUDGET_MS", "50")

    lentitud = {"s": 0.3}

    def _variable(q, t=None):
        _t.sleep(lentitud["s"])
        return "memoria del encargo viejo", [1]
    monkeypatch.setattr(prompt_mod, "compose_recall", _variable)

    async def _dos_turnos():
        await recall_budget.compose("el encargo viejo")      # turn N: abandoned after 50 ms
        lentitud["s"] = 0.0
        await recall_budget.compose("otro tema distinto")     # turn N+1 asks BEFORE N finishes
    asyncio.run(_dos_turnos())
    _t.sleep(0.5)                                             # now turn N's thread finishes

    for nota in notas.drain():
        assert "memoria del encargo viejo" not in nota, \
            "un recall rancio aterrizó después de que la conversación avanzara"


def test_a_late_EMPTY_recall_queues_nothing(monkeypatch):
    """An empty block that arrives late is not a note: it would report that there was nothing, twice."""
    import time as _t

    from nucleo.flash import prompt as prompt_mod
    notas = _con_notas(monkeypatch)
    monkeypatch.setenv("ZAELAR_RECALL_BUDGET_MS", "50")
    monkeypatch.setattr(prompt_mod, "compose_recall", lambda q, t=None: (_t.sleep(0.2), ("", []))[1])

    asyncio.run(recall_budget.compose("algo"))
    _t.sleep(0.4)
    assert notas.drain() == []


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
    from nucleo.flash import prompt as prompt_mod
    _capture(monkeypatch)
    reforzado, _compose = _con_refuerzo(monkeypatch)
    monkeypatch.setattr(prompt_mod, "compose_recall", _compose)

    asyncio.run(recall_budget.compose("qué sabes de mí", {}))

    assert reforzado == [7], (
        f"o no reforzó lo entregado, o reforzó el paquete entero en vez de la selección de memory/: {reforzado}")


def test_an_ABANDONED_recall_reinforces_NOTHING(monkeypatch):
    """The measured defect: the thread still finishes, and until now its reinforcement was applied to a turn that did not see it."""
    import time as _t
    from nucleo.flash import prompt as prompt_mod
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


def test_a_SALVAGED_late_recall_DOES_reinforce(monkeypatch):
    """The nuance added by `motor-dev-2`: if the next turn DOES take the block, that is use.

    It is the counterpart without which «do not reinforce what was not delivered» could be satisfied by never
    reinforcing anything — and decay would eventually bury exactly the pills the agent uses through salvage."""
    from voice import brain_notes
    _capture(monkeypatch)
    reforzado, _ = _con_refuerzo(monkeypatch)
    notas: list = []
    monkeypatch.setattr(brain_notes, "push", lambda t: notas.append(t))

    class _Fut:
        def cancelled(self): return False
        def exception(self): return None
        def result(self): return ("RECUERDO", [1, 2, 3])

    with recall_budget._GEN_LOCK:
        gen_actual = recall_budget._GEN                # nobody has asked since then → fresh

    recall_budget._salvage(_Fut(), "la pregunta del turno anterior", asked_gen=gen_actual,
                           propias={"recall_reinforce_ids": [7]})

    assert notas, "el bloque rescatado no llegó al cerebro"
    assert reforzado == [7], f"se entregó y no se reforzó: {reforzado}"


def test_composing_the_recall_does_NOT_count_as_using_the_memory():
    """Wiring guard, using the AST rather than text: the defect returns with ONE literal.

    The cases above test the new trigger, but do not prevent someone from returning `reinforce_used=True` to its
    place — and if it returns, everything stays green: memory is reinforced twice when it arrives and once when it
    does not, without anything failing. We inspect the CODE because a comment explaining the change contains the
    forbidden string (it has already brought down two string-based guards in this codebase)."""
    import ast
    import inspect
    from nucleo.flash import prompt as prompt_mod

    arbol = ast.parse(inspect.getsource(prompt_mod.compose_recall))
    llamadas = [n for n in ast.walk(arbol) if isinstance(n, ast.Call)
                and getattr(n.func, "attr", None) == "query"]
    assert llamadas, "compose_recall ya no llama a memory.query: este guarda mira al vacío"
    for c in llamadas:
        kw = {k.arg: k.value for k in c.keywords}
        assert "reinforce_used" in kw, "sin decirlo explícito se hereda el default, que refuerza al COMPONER"
        assert isinstance(kw["reinforce_used"], ast.Constant) and kw["reinforce_used"].value is False, \
            "componer el bloque volvió a contar como usar la memoria: refuerza aunque el turno lo abandone"
