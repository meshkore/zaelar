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
