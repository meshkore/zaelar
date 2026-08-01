"""conftest de tests de memoria — el reranker (default `local` en producción, V2-030) se APAGA en los tests
unitarios: aquí medimos la lógica del retriever (fusión/score/grafo), no el cross-encoder (que tiene sus propios
tests en test_rerank.py y su medición a escala en tests/memory/e2e/bot/scale_eval.py). Además evita cargar un
modelo ONNX de ~1 GB en CI. Los tests que quieran el reranker lo activan explícitamente."""
import pytest


@pytest.fixture(autouse=True)
def _rerank_off(monkeypatch):
    monkeypatch.setenv("MEMORY_RERANK", "off")
    yield
