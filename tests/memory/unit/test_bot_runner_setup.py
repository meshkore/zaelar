"""tests/memory/e2e/bot/runner.py — dos bugs reales del arnés de `scale_eval`, cazados repoblando el corpus
(V2-031, 2026-08-17) tras cerrar la inestabilidad del backend de embedding: la medición seguía sin ser fiable
por dos motivos completamente distintos, los dos en el setup del arnés, ninguno en el retriever.

1. `_setup_env()` nunca cargaba `.meshkore/credentials/zaelar.env` (solo `.env`) — `scale_eval.py` sí lo hacía
   (código gemelo, nunca espejado). `DEEPSEEK_API_KEY` solo vive en el credential store → sin resolver →
   `nucleo/provider_keys.py::key_for_endpoint` cae a su centinela `"local"` → DeepSeek 401ea cada llamada del
   CORAZÓN → heurística silenciosa. Reproducido en vivo invocando este runner por su propia CLI documentada.
2. Una BD fresca no fijaba `state.language` — hereda el default de producto `"en"` (85b4922, arranque
   idiomático 2026-08-14) y `mem_processor._render` lo lee para decidir en qué idioma destila. El corpus está
   escrito en español; sin este seed, `--fresh` escribía la memoria entera en inglés y el harness veía
   "write miss" en case tras caso porque el `want` español nunca casaba con texto en inglés.
"""
from __future__ import annotations

import asyncio

import pytest

from memory import api as memapi
from memory import db as memdb
from tests.memory.e2e.bot import runner


def test_setup_env_loads_credential_store(monkeypatch):
    calls: list[str] = []

    def _fake_load_dotenv(path, override=False):
        calls.append(str(path))
        return True

    monkeypatch.setattr("dotenv.load_dotenv", _fake_load_dotenv)
    runner._setup_env()
    assert any("credentials" in c and "zaelar.env" in c for c in calls), \
        f"_setup_env no cargó el credential store (solo .env): {calls}"


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
    memdb.reset_db()
    memdb.get_db()
    yield
    memdb.reset_db()


def test_run_range_seeds_spanish_before_any_case(fresh_db, monkeypatch):
    monkeypatch.setattr("nucleo.mem_processor.enabled", lambda: False)  # heurística, cero red
    asyncio.run(runner.run_range(0, 1, fresh=True))
    assert memapi.state().get("language") == "es", \
        f"una BD fresca del bot debe nacer en español (corpus español), no en el default de producto: {memapi.state().get('language')!r}"
