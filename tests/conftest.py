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
def _reranker_deja_de_depender_de_la_maquina():
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

    ⚠️ NO usa `monkeypatch`, y no es preferencia de estilo: pedirlo aquí instancia ese fixture en el nivel MÁS
    EXTERNO de toda la suite, así que sus parches se deshacen DESPUÉS del teardown de cualquier fixture de
    módulo. Medido al introducirlo: `test_session_rotation.py` se puso en ERROR porque su propio `_clean`
    llamaba, al salir, a la función que el test había parcheado para que reventara — un fixture del conftest
    raíz no puede reordenar el ciclo de vida de los demás. Guardar y restaurar a mano no toca ese orden.
    """
    import os
    from memory import rerank

    previo_env = os.environ.get("MEMORY_RERANK")
    os.environ["MEMORY_RERANK"] = previo_env if previo_env is not None else "off"
    real_cfg = rerank._cfg

    def _el_entorno_manda_en_la_suite() -> dict:
        return {**real_cfg(), "rerank_provider": os.environ["MEMORY_RERANK"]}

    rerank._cfg = _el_entorno_manda_en_la_suite
    try:
        yield
    finally:
        rerank._cfg = real_cfg
        if previo_env is None:
            os.environ.pop("MEMORY_RERANK", None)
        else:
            os.environ["MEMORY_RERANK"] = previo_env


@pytest.fixture(autouse=True)
def _cloud_embeddings_never_reach_the_network():
    """The embeddings titular became a PAID provider (V2-501) — and that turned half the suite into its
    customer without anyone deciding so.

    Measured 2026-08-30, the moment the table changed: three autodetection tests in `test_embeddings.py`
    started failing with `assert 'cloud' == 'fastembed'`. They were not broken: they probed the new rung, and
    since the operator's machine DOES have `OPENAI_API_KEY` in its environment, the probe went out to the
    internet and came back with a real vector. That is the worst shape of this failure: the tests neither hang
    nor complain, they simply measure the network of whoever runs them — green on a laptop with a key, red in
    CI without one, and a bill nobody asked for.

    So INSIDE the suite the cloud backend behaves like an unavailable provider, a path the module already knows
    how to walk (returning `None` = "did not answer" → defer the vector, never change the space). A test that
    genuinely wants to measure it patches `_cloud_embed` itself, or sets `ZAELAR_TEST_EMBED_CLOUD=1` to let the
    real call through.

    No `monkeypatch`, for the same reason as the reranker fixture above: requesting it here instantiates it at
    the outermost level and its patches are undone AFTER any module fixture's teardown.
    """
    import os
    from memory import embeddings as emb

    if os.environ.get("ZAELAR_TEST_EMBED_CLOUD") == "1":
        yield
        return
    real = emb._cloud_embed
    # Kept reachable by hand for the one test that DOES have to measure the real function (with `urlopen`
    # patched, no network): without this the original is unreachable while the fixture is installed.
    emb._REAL_CLOUD_EMBED = real
    emb._cloud_embed = lambda texts, *, timeout=None: None
    try:
        yield
    finally:
        emb._cloud_embed = real
