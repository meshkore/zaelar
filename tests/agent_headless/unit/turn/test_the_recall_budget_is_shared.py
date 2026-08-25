"""El recall durable se compone FUERA del event loop y acotado — en LOS DOS canales (F1, 2026-08-23).

Lo reportó el arnés con el coste medido: con la memoria lenta (una descarga de 1,1 GB) `probe.py` bloqueaba el
motor ENTERO — todos los endpoints en timeout y la tanda muerta como «INFRA: timed out», sin nombrar a la
memoria por ningún lado. El camino de VOZ ya sobrevivía.

Y el defecto lo dice el docstring de `prompt.build_flash_system`: el parámetro de verdad es `recall_block` (el
llamante lo compone fuera del loop, bajo demanda) y **`recall_query` es la ruta de COMPATIBILIDAD PARA TESTS**,
que compone en línea. El canal de texto usaba la ruta de tests en producción.

Lo que estos casos fijan es la clase entera, no la instancia: una PROTECCIÓN que existe en un canal y no en el
otro no se distingue de no tenerla — el fallo sale por el canal que nadie recordó, en el peor momento.
"""
import asyncio
import inspect

from nucleo.turn import recall_budget


def test_nothing_to_ask_costs_nothing():
    assert asyncio.run(recall_budget.compose("")) == ("", [])
    assert asyncio.run(recall_budget.compose("   ")) == ("", [])


def test_a_slow_retriever_does_NOT_take_the_turn_down(monkeypatch):
    """El caso medido. Degradar es el PUNTO, no un apaño: un turno con menos memoria es peor respuesta; un
    turno que no llega es un agente muerto.

    Se cronometra DENTRO del loop a propósito. `wait_for` cancela la espera, no el HILO — `to_thread` corre en
    el executor y nadie puede interrumpirlo desde fuera — así que un `asyncio.run()` alrededor se bloquea al
    cerrar esperando a ese hilo y mediría 2 s con la guarda funcionando perfectamente. Lo que este caso afirma
    es lo que de verdad importa en un servidor vivo: que el TURNO queda libre en su presupuesto. El hilo lento
    termina solo, a su ritmo, sin nadie esperándole."""
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
    """La contrapartida, sin la cual «no se cuelga» se satisface no recordando nunca."""
    from nucleo.flash import prompt as prompt_mod
    monkeypatch.setattr(prompt_mod, "compose_recall", lambda q, t=None: (f"RECUERDO: {q}", [7]))
    assert asyncio.run(recall_budget.compose("los hijos")) == ("RECUERDO: los hijos", [7])


def test_one_knob_moves_both_channels(monkeypatch):
    """Dos presupuestos que derivan es cómo «en voz va» y «en texto se cuelga» se convierten en dos informes de
    fallo distintos para una sola causa."""
    monkeypatch.setenv("ZAELAR_RECALL_BUDGET_MS", "1500")
    assert abs(recall_budget.budget_s() - 1.5) < 1e-9
    monkeypatch.setenv("ZAELAR_RECALL_BUDGET_MS", "no-es-un-numero")
    assert recall_budget.budget_s() > 0, "un valor ilegible no puede dejar el presupuesto en cero"


def test_no_channel_composes_the_recall_inside_the_loop():
    """El guarda de la clase. `recall_query=` es la ruta de tests: en producción compone EN LÍNEA, y usarla es
    exactamente el fallo que tumbó el motor. Los tres puntos de entrada del turno pasan por la guarda."""
    from nucleo.flash import probe, probe_api
    from voice.engine.llm.providers import nucleo as voice_provider

    import ast

    for mod, name in ((probe, "probe.run_turn"), (probe_api, "probe_api"),
                      (voice_provider, "el provider de voz")):
        src = inspect.getsource(mod)
        assert "recall_budget" in src, f"{name} no pasa por la guarda con presupuesto"
        # Se mira el CÓDIGO, no el texto. Buscar la cadena `recall_query=` la encuentra también en un
        # comentario que EXPLICA por qué no se usa — pasó al escribir este mismo guarda, y es la segunda vez
        # en el día que la prosa sobre un patrón derriba un guarda que casa por cadena.
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
    """La fila cuenta lo que pasó DESPUÉS; la luz es lo único que se ve MIENTRAS pasa."""
    from nucleo.flash import prompt as prompt_mod
    from voice import health_state
    _capture(monkeypatch)
    monkeypatch.setenv("ZAELAR_RECALL_BUDGET_MS", "50")
    monkeypatch.setattr(prompt_mod, "compose_recall", _slow())

    asyncio.run(recall_budget.compose("qué sabes de mí", {}))

    rec = health_state.get("memory")
    assert rec is not None and rec["kind"] == "degraded", "la memoria degradada no enciende el ámbar"


def test_a_recall_INSIDE_budget_says_nothing(monkeypatch):
    """La contrapartida. Un aviso que sale siempre no es un aviso: es ruido, y se aprende a ignorarlo."""
    from nucleo.flash import prompt as prompt_mod
    from voice import health_state
    filas = _capture(monkeypatch)
    monkeypatch.setattr(prompt_mod, "compose_recall", lambda q, t=None: ("RECUERDO", [7]))

    asyncio.run(recall_budget.compose("los hijos", {}))

    assert not filas, f"un recall que llegó bien ensució la línea de tiempo: {filas}"
    assert health_state.get("memory") is None, "un recall que llegó bien encendió el ámbar"


def test_it_does_NOT_wipe_an_unrelated_memory_warning(monkeypatch):
    """La clave `memory` es COMPARTIDA con `memory/` (espacio vectorial descuadrado, embeddings degradados).

    Limpiarla al salir —el gesto reflejo de «servicio sano otra vez»— borraría un aviso que este módulo no
    puso y no puede juzgar. Se deja envejecer con su TTL, igual que hace el resto de `memory/`."""
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

    Se espera al hilo a propósito: el fallo solo existe DESPUÉS de que termine, así que un caso que no le da
    tiempo a terminar pasa siempre, con arreglo y sin él."""
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
    _t.sleep(0.5)                                     # el hilo abandonado termina AHORA y escribe lo suyo

    assert timings.get("recall_timeout") is True
    assert "mem_query_ms" not in timings, (
        f"un recall que el turno abandonó le metió su coste en la contabilidad: {timings}")


def test_a_recall_within_budget_DOES_report_its_cost(monkeypatch):
    """La contrapartida: aislar al hilo abandonado no puede costarnos la métrica buena."""
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


# ── V2-311 paso 2: un recall que llega TARDE es la memoria del turno siguiente — o de nadie ─────────────────
#
# El 77% de los recalls vivos (21/27, medido por memoria-dev sobre 223 sesiones) se abandonaban al vencer el
# presupuesto — y TODOS terminaban igualmente: el hilo corre hasta el final y el bloque compuesto moría en un
# futuro que nadie miraba. El turno pagaba el coste completo el 100% de las veces y recibía el resultado el 22%.
#
# La cola de producción (2,1 s / 3,5 s / 21 s) es la razón del corte de frescura, y el corte NO es un reloj:
# es «ningún turno ha preguntado desde entonces». Si la generación avanzó, la conversación avanzó — y V2-254
# midió lo que la memoria rancia le hace a una conversación que ya se movió (meteo en Soria → fontanero en
# Soria). Los segundos serían un proxy de eso; los turnos SON eso.

def _con_notas(monkeypatch):
    """El buzón real, aislado: lo que se mide es que la nota LLEGUE al buzón que drena el turno siguiente."""
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
    assert out == ("", [])                       # ESTE turno sigue sin memoria: el contrato no cambia
    _t.sleep(0.45)                               # el hilo termina y el callback corre

    got = notas.drain()
    assert len(got) == 1, "el bloque compuesto murió en un futuro que nadie miraba — otra vez"
    nota = got[0]
    assert "Marc vive en Soria" in nota and "qué sabes de mí" in nota
    # findings.py: la nota no ORDENA anunciar — dice lo que llegó y permite ignorarlo; el juicio es del cerebro
    assert "ignóralo" in nota
    # solo TEXTO: los ids alimentan el refuerzo al usarse, y un turno que no vio el bloque no refuerza nada
    assert "7" not in nota.split("«")[0] and "[7, 9]" not in nota


def test_a_late_recall_after_another_turn_asked_is_DROPPED(monkeypatch):
    """El corte de frescura. Sin esto, el recall de 21 s aterriza cinco turnos tarde en una conversación que
    ya va por otro sitio — el secuestro de V2-254 con uniforme de mejora."""
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
        await recall_budget.compose("el encargo viejo")      # turno N: se abandona a los 50 ms
        lentitud["s"] = 0.0
        await recall_budget.compose("otro tema distinto")     # turno N+1 pregunta ANTES de que N termine
    asyncio.run(_dos_turnos())
    _t.sleep(0.5)                                             # ahora sí termina el hilo del turno N

    for nota in notas.drain():
        assert "memoria del encargo viejo" not in nota, \
            "un recall rancio aterrizó después de que la conversación avanzara"


def test_a_late_EMPTY_recall_queues_nothing(monkeypatch):
    """Un bloque vacío que llega tarde no es una nota: sería avisar de que no había nada, dos veces."""
    import time as _t

    from nucleo.flash import prompt as prompt_mod
    notas = _con_notas(monkeypatch)
    monkeypatch.setenv("ZAELAR_RECALL_BUDGET_MS", "50")
    monkeypatch.setattr(prompt_mod, "compose_recall", lambda q, t=None: (_t.sleep(0.2), ("", []))[1])

    asyncio.run(recall_budget.compose("algo"))
    _t.sleep(0.4)
    assert notas.drain() == []


# ── El refuerzo sigue a la ENTREGA, no al cálculo (V2-311 paso 3, 2026-08-25) ──────────────────────────────────
#
# `memory.query` reforzaba al COMPONER el bloque, y componer no es usar: de los 27 recalls vivos medidos, 21 se
# abandonaban al vencer el presupuesto y el hilo terminaba igualmente, así que subían el peso y reseteaban la
# caducidad (escritura durable) de píldoras por preguntas que nunca se contestaron con ellas. La señal de «esto
# se usa» la alimentaba justo el trabajo que se tiraba.
#
# Las tres salidas del módulo se reparten limpias — entregado en presupuesto, entregado tarde, descartado por
# rancio — y solo las DOS entregas refuerzan.

def _con_refuerzo(monkeypatch, ids_seleccionados=(7,)):
    """Sustituye el escritor y devuelve la lista de lo que se reforzó de verdad."""
    from memory import api as memory_api
    reforzado: list = []
    monkeypatch.setattr(memory_api, "reinforce", lambda ids: reforzado.extend(ids))

    def _compose(q, t=None):
        if t is not None:
            t["recall_reinforce_ids"] = list(ids_seleccionados)
        return "RECUERDO", [1, 2, 3, 4, 5]        # `ids` del paquete entero: NUNCA es lo que se refuerza
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
    """El defecto medido: el hilo termina igual, y hasta hoy su refuerzo se aplicaba a un turno que no lo vio."""
    import time as _t
    from nucleo.flash import prompt as prompt_mod
    _capture(monkeypatch)
    reforzado, _compose = _con_refuerzo(monkeypatch)
    monkeypatch.setenv("ZAELAR_RECALL_BUDGET_MS", "50")

    def _tarde(q, t=None):
        _t.sleep(0.3)
        return _compose(q, t)
    monkeypatch.setattr(prompt_mod, "compose_recall", _tarde)
    monkeypatch.setattr(recall_budget, "_salvage", lambda *a, **k: None)   # aislar: aquí NO se rescata

    asyncio.run(recall_budget.compose("qué sabes de mí", {}))
    _t.sleep(0.5)                                     # el hilo abandonado termina AHORA

    assert reforzado == [], f"un recall que nadie recibió subió el peso y reseteó la caducidad: {reforzado}"


def test_a_STALE_late_recall_reinforces_NOTHING(monkeypatch):
    """Si la conversación ya avanzó, el bloque se descarta — y descartar no es entregar."""
    _capture(monkeypatch)
    reforzado, _ = _con_refuerzo(monkeypatch)

    class _Fut:
        def cancelled(self): return False
        def exception(self): return None
        def result(self): return ("RECUERDO", [1, 2, 3])

    recall_budget._salvage(_Fut(), "una pregunta vieja", asked_gen=-1,   # generación que ya no es la actual
                           propias={"recall_reinforce_ids": [7]})

    assert reforzado == [], "un bloque descartado por rancio reforzó igualmente"


def test_a_SALVAGED_late_recall_DOES_reinforce(monkeypatch):
    """El matiz que puso `motor-dev-2`: si el turno siguiente SÍ se lleva el bloque, eso es un uso.

    Es la contrapartida sin la cual «no reforzar lo que no se entregó» se satisface no reforzando nunca — y el
    decay acabaría enterrando justo las píldoras que el agente usa a través del rescate."""
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
        gen_actual = recall_budget._GEN                # nadie ha preguntado desde entonces → fresco

    recall_budget._salvage(_Fut(), "la pregunta del turno anterior", asked_gen=gen_actual,
                           propias={"recall_reinforce_ids": [7]})

    assert notas, "el bloque rescatado no llegó al cerebro"
    assert reforzado == [7], f"se entregó y no se reforzó: {reforzado}"


def test_composing_the_recall_does_NOT_count_as_using_the_memory():
    """Guarda de cableado, por AST y no por texto: el defecto vuelve con UN literal.

    Los casos de arriba prueban el trigger nuevo, no impiden que alguien devuelva `reinforce_used=True` a su
    sitio — y si vuelve, todo sigue verde: la memoria se refuerza dos veces cuando llega y una vez cuando no
    llega, sin que falle nada. Se mira el CÓDIGO porque un comentario que explica el cambio contiene la cadena
    prohibida (ya derribó dos guardas por cadena en esta casa)."""
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
