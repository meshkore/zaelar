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
