"""The suite declares its environment, and that takes precedence INSIDE the suite (architecture audit 2026-08-23, H4).

Measured with real cost: `memory/rerank.py::_cfg()` reads `config/v2.py` before the environment — product rule,
“the store OVERRIDES `.env`,” and that is not touched here—but that file is GITIGNORED, meaning it is the config of
EACH machine. With `rerank_provider='local'` and the model outside the cache, `MEMORY_RERANK=off` did not turn
anything off: any test that reached the reranker would start DOWNLOADING from HuggingFace. The memory suite went
from 34 s to HUNG without a single line of test code changing, and three pytest processes became blocked on the
file lock, waiting for one another.

What makes this dangerous is not that it fails, but HOW it fails: a test advertised as “deterministic, no network”
does not raise an error when it reaches the network—it hangs, or measures something else. Same family as an absolute
floor calibrated against a live corpus or a test asleep beneath its own skip: green, while not covering what it says
it covers.

The guard lives here rather than in conftest because it checks the EFFECT of the fixture, not its code: it patches
the config source beneath the wrapper, so it keeps measuring even if the fixture is rewritten.
"""
from __future__ import annotations

import pytest

from memory import rerank


@pytest.fixture
def config_pidiendo_el_reranker_local(monkeypatch):
    """The operator's config on the day the suite hung. `config.v2.get`, which is what `_cfg()` queries, is patched
    —patching `_cfg` would overwrite the conftest wrapper and the test would stop testing it."""
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
    """The other half; without it, the fix would be “the reranker can never be measured again.” Anyone who wants to
    exercise it for real requests it explicitly and takes precedence—which is what `scale_eval` does when comparing
    rerankers."""
    monkeypatch.setenv("MEMORY_RERANK", "local")
    assert rerank.provider() == "local"
