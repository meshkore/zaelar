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
