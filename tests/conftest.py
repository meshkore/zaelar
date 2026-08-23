"""conftest.py raíz de la suite — garantías de AISLAMIENTO que valen para TODOS los tests.

## El agente arranca EN MARCHA en cada test (V2-092)

Desde que existe el interruptor global (`nucleo/runstate.py`), «¿está el agente parado?» gobierna caminos reales:
los ciclos de background no hacen `tick()`, los crons no disparan, no se abre trabajo nuevo y los widgets que
producen se niegan a arrancar. Ese interruptor **está persistido en la base del operador**, así que sin este fixture
la suite dependería de un estado AMBIENTAL: correr los tests con el ⏻ apagado en la sesión real hacía fallar
`test_background.py::test_scheduler_ticks_a_passive_widget`, y el fallo no señalaba a nada del test — pasó de verdad
el 2026-08-13, mientras se construía la propia función.

Se pone la caché EN PROCESO (no se escribe nada en ninguna base), así que un test que quiera parar el agente sigue
pudiendo — llama a `runstate.stop()` y manda él (ver `tests/agent_headless/unit/test_runstate.py`, que además usa su
propia base temporal).
"""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _agente_en_marcha():
    from nucleo import runstate
    runstate._state.update({"value": runstate.RUNNING, "at": 0.0, "src": "test"})
    yield
    runstate._reset_for_tests()


@pytest.fixture(autouse=True)
def _reranker_deja_de_depender_de_la_maquina(monkeypatch):
    """El reranker LOCAL descarga su modelo de HuggingFace, y la suite decía «sin red» sin serlo (2026-08-23).

    `memory/rerank.py::_cfg()` lee `config/v2.py` PRIMERO y solo cae al entorno si no hay config. Eso es la norma
    del producto —«el store MANDA sobre `.env`»— y NO se toca aquí. El problema es que ese fichero está
    GITIGNOREADO: es la config de CADA máquina. En la del operador `rerank_provider='local'` sin el modelo en
    caché, así que `MEMORY_RERANK=off` no apagaba nada y cualquier test que llegara al reranker se ponía a
    DESCARGAR. Medido: la suite de memoria pasó de 34 s a colgada **sin que cambiara una línea de test**, y tres
    procesos de pytest quedaron bloqueados esperándose entre ellos por el lock del fichero.

    Lo que no falla con ruido es lo caro: un test que se anuncia determinista y sale a la red no da un error, se
    cuelga — o peor, mide otra cosa. Así que DENTRO de la suite el entorno gana, y por defecto el reranker está
    apagado. Un test que quiera medirlo de verdad pone `MEMORY_RERANK` y manda él.

    La precedencia de PRODUCCIÓN queda exactamente como estaba: esto solo vive en el conftest.
    """
    import os
    monkeypatch.setenv("MEMORY_RERANK", os.environ.get("MEMORY_RERANK", "off"))
    from memory import rerank
    real_cfg = rerank._cfg

    def _el_entorno_manda_en_la_suite() -> dict:
        cfg = dict(real_cfg())
        cfg["rerank_provider"] = os.environ["MEMORY_RERANK"]
        return cfg

    monkeypatch.setattr(rerank, "_cfg", _el_entorno_manda_en_la_suite)
