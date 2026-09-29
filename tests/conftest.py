"""Suite-root conftest.py — ISOLATION guarantees that apply to ALL tests.

## The agent starts RUNNING in every test (V2-092)

Since the global switch (`nucleo/runstate.py`) exists, “is the agent stopped?” governs real paths:
background cycles do not call `tick()`, crons do not fire, no new work is opened, and the widgets they
produce refuse to start. That switch **is persisted in the operator's database**, so without this fixture
the suite would depend on an ENVIRONMENTAL state: running the tests with ⏻ off in the real session caused
`test_background.py::test_scheduler_ticks_a_passive_widget` to fail, and the failure did not point to anything in
the test — it really happened on 2026-08-13, while the feature itself was being built.

The cache is kept IN PROCESS (nothing is written to any database), so a test that wants to stop the agent still
can — call `runstate.stop()` and it takes precedence (see `tests/agent_headless/unit/test_runstate.py`, which also uses its
own temporary database).
"""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _agente_en_marcha(monkeypatch):
    """…and with a language (V2-765): a missing language also reads as STOPPED, and whether the workspace the
    suite runs against has one is exactly the kind of environmental state this fixture exists to remove. The
    gate's own tests turn it back on with `ZAELAR_LANGUAGE_GATE=1`."""
    from nucleo import runstate
    monkeypatch.setenv("ZAELAR_LANGUAGE_GATE", "0")
    runstate._state.update({"value": runstate.RUNNING, "at": 0.0, "src": "test"})
    yield
    runstate._reset_for_tests()


@pytest.fixture(autouse=True)
def _reranker_deja_de_depender_de_la_maquina():
    """The LOCAL reranker downloads its HuggingFace model, and the suite claimed to be “offline” without being so (2026-08-23).

    `memory/rerank.py::_cfg()` reads `config/v2.py` FIRST and only falls back to the environment if there is no config. That is the product
    rule —“the store OVERRIDES `.env`”— and is NOT changed here. The problem is that this file is
    GITIGNORED: it is the config for EACH machine. On the operator's machine `rerank_provider='local'` was set without the model in
    cache, so `MEMORY_RERANK=off` did not turn anything off and any test that reached the reranker started
    DOWNLOADING. Measured: the memory suite went from 34 s to hanging **without a line of test code changing**, and three
    pytest processes became blocked waiting for one another on the file lock.

    What fails silently is the expensive part: a test that claims to be deterministic and reaches the network does not report an error, it
    hangs — or worse, measures something else. So INSIDE the suite the environment wins, and by default the reranker is
    off. A test that genuinely wants to measure it sets `MEMORY_RERANK` and takes precedence.

    PRODUCTION precedence remains exactly as it was: this lives only in conftest.

    ⚠️ It does NOT use `monkeypatch`, and this is not a style preference: requesting it here instantiates that fixture at the MOST
    OUTER level of the entire suite, so its patches are undone AFTER the teardown of any module fixture.
    Measured when it was introduced: `test_session_rotation.py` became ERROR because its own `_clean`
    called, on exit, the function that the test had patched to blow up — a root-conftest fixture cannot reorder
    the lifecycle of the others. Saving and restoring by hand does not affect that order.
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


@pytest.fixture(autouse=True)
def _jev_never_reaches_the_network_and_starts_closed():
    """The decision model is a PAID remote API, and inside the suite it behaves like the embeddings above: a test
    that fires a turn brief without faking the transport used to go out to the internet with the operator's real
    key (measured 2026-09-28: six real calls in one run of `tests/voice/unit`).

    That was invisible while the provider answered fast. The day it went slow those calls timed out, three in a row
    opened the module's circuit breaker — which is process-global — and twelve Jev tests further down the run read
    «disabled» and failed, while each one passed on its own.

    So: the endpoint is a closed local port — a call that was not faked fails at once, offline and unbilled, the
    way an unreachable provider fails (every test that means to talk to Jev fakes the transport already) — and the
    breaker starts closed for every test. `ZAELAR_TEST_JEV_LIVE=1` lets the real call through. Set and restored by
    hand, without `monkeypatch`, for the ordering reason given on the reranker fixture."""
    import os
    from nucleo import jev

    saved_endpoint, saved_breaker = jev.ENDPOINT, dict(jev._breaker)
    jev._breaker.update({"fails": 0, "open_until": 0.0})
    if os.environ.get("ZAELAR_TEST_JEV_LIVE") != "1":
        jev.ENDPOINT = "http://127.0.0.1:9/v1/systemone"
    try:
        yield
    finally:
        jev.ENDPOINT = saved_endpoint
        jev._breaker.clear()
        jev._breaker.update(saved_breaker)


@pytest.fixture(autouse=True)
def _the_spec_ledger_starts_empty():
    """V2-776 L1 keeps the open end states in one in-process ledger (`nucleo.spec._OPEN`); a test that dispatched a
    data-op left its spec open, and every later brief asked an `end_state` question it never expected — measured
    2026-09-30, a wide voice run went red in files that pass alone."""
    import sys
    mod = sys.modules.get("nucleo.spec")
    if mod is not None:
        mod.reset()
    yield
    mod = sys.modules.get("nucleo.spec")
    if mod is not None:
        mod.reset()


@pytest.fixture(autouse=True)
def _composers_never_reach_the_network():
    """The two small model calls a turn can make after the fact — a finished errand's spoken line
    (`spoken_delivery.line`) and the confirmation judge (`widgets.confirm._judge`) — stay off the network inside the
    suite, for the reason on the Jev fixture above: measured 2026-09-29, `test_context_budget` passed alone and failed
    in a wide run, where an earlier test had left a model configured and the delivery was rewritten by a real call.
    Tests that exercise them turn them back on (or fake the client). `ZAELAR_TEST_LLM_LIVE=1` lets them through."""
    import os
    from nucleo.workers import spoken_delivery
    from widgets import confirm
    saved = (spoken_delivery.LIVE, confirm._JUDGE_LIVE)
    if os.environ.get("ZAELAR_TEST_LLM_LIVE") != "1":
        spoken_delivery.LIVE, confirm._JUDGE_LIVE = False, False
    try:
        yield
    finally:
        spoken_delivery.LIVE, confirm._JUDGE_LIVE = saved
