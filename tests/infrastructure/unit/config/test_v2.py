#
# test_v2.py — v2 config schema “Colmena” (V2-001, T38). Verifies: defaults, atomic persistence,
# fallback to env, and the privacy INVARIANT (the public view never reveals an API key).
# Run: .venv/bin/pytest tests/infrastructure/unit/config/test_v2.py
#
import importlib

import pytest


@pytest.fixture()
def v2(tmp_path, monkeypatch):
    # isolate the store file for each test
    import config.v2 as v2mod
    monkeypatch.setattr(v2mod, "_PATH", tmp_path / "v2.json")
    # clear any fallback env vars that could pollute the test
    for env in ("FAST_MODEL", "FAST_PROVIDER", "FAST_API_KEY", "FAST_BASE_URL",
                "CODE_AGENT_PROVIDER", "CODE_AGENT_MODEL", "CODE_AGENT_API_KEY", "BRAIN"):
        monkeypatch.delenv(env, raising=False)
    return v2mod


def test_defaults(v2):
    fast = v2.get("fast")
    # OPERATOR RULE (2026-08-19, hard rule from CLAUDE.md): DeepSeek V4 DIRECT from its provider is the primary
    # option; AIMLAPI is the first fallback, and OpenAI/Anthropic the last. The default no longer goes through the broker.
    assert fast["provider"] == "deepseek"
    # And V4 **PRO**, not Flash, through the direct endpoint: the 3-round benchmark on node 2.13 (42 turns per arm,
    # 2026-08-15) measured exactly what the default comment required to promote it — “run it for 3 rounds and if it
    # holds up, switch to it.” Pro held up (41/42, the same as the broker), and direct Flash did NOT (38/42, it failed
    # `show widget` 3 out of 3 times: that is not variance, it is a defect). The cost: a voice turn goes from ~0.5 to
    # ~1 Energy, and that was the missing PRICING decision, not another measurement.
    # Primary-model history: an Anthropic model via broker (V2-034, 2026-07-12) → deepseek-v4-flash via broker (2026-08-14) →
    # this. The previous two remain valid broker options.
    assert fast["model"] == "deepseek-v4-pro"
    assert fast["base_url"] == "https://api.deepseek.com", "the primary model goes DIRECT, not through the broker"
    # The fallback chain remains EMPTY by default and the rule does not change that: empty = primary + AUTOMATIC chain
    # (in the cloud, direct → broker; in SELF-HOST, only the primary, because whoever self-hosts pays for their APIs and
    # must not be surprised by a provider they did not choose).
    assert fast["providers"] == []
    assert v2.active_brain() == "nucleo"        # after Hermes's burial (V2-009): own brain by default
    assert v2.get("flags")["memory_enabled"] is True


def test_set_persists_and_reads_back(v2):
    v2.set("fast", {"model": "qwen2.5:14b", "provider": "ollama"})
    assert v2.get("fast")["model"] == "qwen2.5:14b"
    assert v2.get("fast")["provider"] == "ollama"
    # and persist it to disk
    assert v2._PATH.exists()


def test_set_ignores_unknown_keys(v2):
    v2.set("fast", {"model": "m", "bogus": "x"})
    assert "bogus" not in v2.get("fast")


def test_set_unknown_section_raises(v2):
    with pytest.raises(KeyError):
        v2.set("nope", {"a": 1})


def test_env_fallback_only_when_store_silent(v2, monkeypatch):
    monkeypatch.setenv("FAST_MODEL", "from-env")
    assert v2.get("fast")["model"] == "from-env"          # empty store → falls back to env
    v2.set("fast", {"model": "from-store"})
    assert v2.get("fast")["model"] == "from-store"        # store OVERRIDES env


def test_public_view_redacts_api_key(v2):
    v2.set("fast", {"api_key": "sk-supersecret"})
    pub = v2.public("fast")
    assert "api_key" not in pub                            # never in plaintext
    assert pub["api_key_set"] is True
    # and with no key configured → _set False
    assert v2.public("code_agent")["api_key_set"] is False


def test_public_all_never_leaks_a_secret(v2):
    v2.set("fast", {"api_key": "sk-abc"})
    v2.set("code_agent", {"api_key": "sk-def"})
    blob = repr(v2.public_all())
    assert "sk-abc" not in blob and "sk-def" not in blob


def test_specs_for_by_invocation(v2):
    v2.set("fast", {"model": "grok", "provider": "aimlapi"})
    spec = v2.fast_model_spec()
    assert spec["model"] == "grok" and spec["provider"] == "aimlapi"
    assert "api_key" in spec                               # internal use DOES see the secret
