"""La suite declara su entorno, y ese gana DENTRO de la suite (auditoría de arquitectura 2026-08-23, H4).

Medido con coste real: `memory/rerank.py::_cfg()` lee `config/v2.py` antes que el entorno —norma del producto,
«el store MANDA sobre `.env`», y aquí no se toca— pero ese fichero está GITIGNOREADO, o sea que es la config de
CADA máquina. Con `rerank_provider='local'` y el modelo fuera de la caché, `MEMORY_RERANK=off` no apagaba nada:
cualquier test que llegara al reranker se ponía a DESCARGAR de HuggingFace. La suite de memoria pasó de 34 s a
COLGADA sin que cambiara una línea de test, y tres procesos de pytest se quedaron bloqueados por el lock del
fichero, esperándose entre ellos.

Lo que hace esto peligroso no es que falle, es CÓMO falla: un test que se anuncia «determinista, sin red» no da
un error al salir a la red — se cuelga, o mide otra cosa. Misma familia que un suelo absoluto calibrado contra un
corpus vivo o un test dormido bajo su propio skip: verde, y sin cubrir lo que dice cubrir.

El guarda vive aquí y no en el conftest porque comprueba el EFECTO del fixture, no su código: parchea la fuente
de config por debajo del envoltorio, así sigue midiendo aunque el fixture se reescriba.
"""
from __future__ import annotations

import pytest

from memory import rerank


@pytest.fixture
def config_pidiendo_el_reranker_local(monkeypatch):
    """La config del operador el día que colgó la suite. Se parchea `config.v2.get`, que es lo que `_cfg()`
    consulta — parchear `_cfg` sería pisar el envoltorio del conftest y el test dejaría de probarlo."""
    from config import v2
    real_get = v2.get
    monkeypatch.setattr(
        v2, "get",
        lambda sec: ({**(real_get(sec) or {}), "rerank_provider": "local"} if sec == "memory" else real_get(sec)))


def test_una_config_local_NO_enciende_el_reranker_en_la_suite(config_pidiendo_el_reranker_local):
    assert rerank.provider() == "off", (
        "la config de la máquina pisó al entorno: la suite volvería a descargar el modelo y a colgarse, sin que "
        "ningún test haya cambiado")


def test_pero_un_test_que_lo_pida_EXPLICITAMENTE_manda_el(monkeypatch, config_pidiendo_el_reranker_local):
    """La otra mitad, y sin ella el arreglo sería «el reranker ya no se puede medir nunca». Quien quiera
    ejercitarlo de verdad lo pide y manda él — que es lo que hace `scale_eval` al comparar rerankers."""
    monkeypatch.setenv("MEMORY_RERANK", "local")
    assert rerank.provider() == "local"
