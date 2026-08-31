"""Memory-test conftest — the reranker (default `local` in production, V2-030) is TURNED OFF in unit tests:
here we measure the retriever's logic (fusion/score/graph), not the cross-encoder (which has its own tests in
test_rerank.py and its scale evaluation in tests/memory/e2e/bot/scale_eval.py). It also avoids loading an
~1 GB ONNX model in CI. Tests that want the reranker enable it explicitly."""
import pytest


@pytest.fixture(autouse=True)
def _rerank_off(monkeypatch):
    monkeypatch.setenv("MEMORY_RERANK", "off")
    yield
