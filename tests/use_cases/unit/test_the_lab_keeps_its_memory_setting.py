"""The lab's memory setting lives in the ENV, because the agent rewrites its own config file.

MEASURED, twice, 2026-08-22 → 2026-08-23. `memory.rerank_provider` was pinned to `"off"` inside each lab
agent's `config/v2.json`. The next morning the ES agent's `memory` block was `{}` — a running engine
rewrites that file and does not preserve keys it holds to be defaults. The US agent, which had been
stopped, still had its key: the same pin, two outcomes, decided only by whether the engine had been
alive to overwrite it.

WHY THAT ONE MISSING KEY IS NOT A SMALL ONE. With the key gone, `config.v2.get("memory")` falls through
to the CODE default (`config/v2.py`: `"local"`), which pulls a 1.1 GB cross-encoder ONNX blob on first
recall. The probe path still composes its prompt SYNCHRONOUSLY on the event loop
(`nucleo/flash/probe.py:251`), so that download does not slow memory down — it takes the whole engine
with it. Every endpoint times out and the round dies reporting `INFRA: timed out`, naming neither memory
nor the download. That is the most expensive shape of failure this harness has: it looks like the tester.

WHY THE ENV IS THE RIGHT HOME. `config.v2.get()` reads stored > env > default, so a key present in the
agent's own file still wins — the env pin is not a way to override the agent, it is a way to survive the
agent DELETING its own entry. It is the one layer the process under test cannot rewrite from underneath
us. It also matches what the operator's engine runs, so the lab is not measuring a memory path the
product does not use.
"""
from __future__ import annotations

from tests.use_cases.lab import profiles as P
from tests.use_cases.lab import stage


def test_every_lab_agent_boots_with_the_reranker_pinned_off():
    for prof in P.PROFILES.values():
        for voice in (True, False):
            env = stage.env_for(prof, voice=voice)
            assert env.get("MEMORY_RERANK") == "off", f"{prof.key} (voz={voice}): sin el pin del reranker"


def test_the_stage_never_writes_the_setting_into_the_agents_own_config():
    """The distinction the incident turned on, stated as the thing that must NOT happen.

    A FORWARD guard, and it does not disarm: reverting the env pin leaves it green, because what it
    forbids is the OLD fix coming back. Writing `rerank_provider` into the sandbox's `config/v2.json` is
    what was tried first, and it survived exactly as long as the agent stayed stopped. If someone puts it
    back there, this is the test they have to argue with.
    """
    import inspect
    src = inspect.getsource(stage)
    assert "rerank_provider" not in src, (
        "el plató vuelve a escribir el ajuste en el config del agente — el agente lo reescribe y lo borra; "
        "el pin va en el ENV (`env_for`)")


def test_the_env_pin_actually_reaches_the_effective_config():
    """End to end through the real resolver, against an EMPTY store — which is exactly the state the ES
    agent left behind. Asserting only that the var is set would pass even if `_ENV_FALLBACK` dropped the
    mapping, and the engine would go right back to downloading."""
    import os
    from unittest import mock
    from config import v2 as cfg

    env = stage.env_for(next(iter(P.PROFILES.values())), voice=True)
    with mock.patch.object(cfg, "_read", lambda: {"memory": {}}), \
         mock.patch.dict(os.environ, {"MEMORY_RERANK": env["MEMORY_RERANK"]}, clear=False):
        assert cfg.get("memory")["rerank_provider"] == "off"


def test_a_key_the_agent_still_owns_beats_the_env():
    """The other half, and it is deliberate: the env is a FLOOR, not a gag. An operator who sets the
    provider in the sandbox's own config still gets what they asked for — the pin only covers the case
    where nobody asked for anything."""
    import os
    from unittest import mock
    from config import v2 as cfg

    with mock.patch.object(cfg, "_read", lambda: {"memory": {"rerank_provider": "local"}}), \
         mock.patch.dict(os.environ, {"MEMORY_RERANK": "off"}, clear=False):
        assert cfg.get("memory")["rerank_provider"] == "local"
