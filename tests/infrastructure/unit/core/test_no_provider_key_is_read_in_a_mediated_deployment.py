"""No provider key is read in a mediated deployment — every paid call goes out through egress.

Measured 2026-10-23: chat calls already went through egress, but embeddings, the three paid search indexes, the
messaging triage model, the peer-memory distiller and the Brain Worker's Anthropic-shaped endpoint spoke to their
providers directly with a key read from the environment — the same process where the code a user asked for runs.
Since the meter skips what it believes egress records, several of those calls were neither protected nor billed.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from nucleo.energy import egress as llm_egress

GW = "https://egress.example"
TOKEN = "tok-of-this-account"


@pytest.fixture
def mediated(monkeypatch):
    monkeypatch.setattr(llm_egress, "mediated", lambda: True)
    monkeypatch.setenv("ZAELAR_GATEWAY_URL", GW + "/")
    monkeypatch.setenv("CONTROL_PLANE_SERVICE_TOKEN", TOKEN)
    for name in llm_egress._STANDS_IN_FOR:
        monkeypatch.setenv(name, f"MASTER-{name}")
    yield


def test_every_family_maps_to_its_base_and_the_longest_base_wins():
    assert llm_egress.upstream_of("https://api.deepseek.com/anthropic/v1/messages")[0] == "deepseek_anthropic"
    assert llm_egress.upstream_of("https://api.deepseek.com/chat/completions")[0] == "deepseek"
    assert llm_egress.upstream_of("https://api.z.ai/api/anthropic")[0] == "zai_anthropic"
    assert llm_egress.upstream_of("https://api.z.ai/api/paas/v4/web_search")[0] == "zai"
    assert llm_egress.upstream_of("https://generativelanguage.googleapis.com/v1beta/models/m:generateContent")[0] \
        == "gemini"
    assert llm_egress.upstream_of("https://api.openai.com/v1/embeddings")[0] == "openai"
    assert llm_egress.upstream_of("https://api.openai.com.evil.test/v1") == ("", "")


def test_self_host_gets_its_url_and_key_back_untouched(monkeypatch):
    monkeypatch.setattr(llm_egress, "mediated", lambda: False)
    assert llm_egress.route_url("https://api.openai.com/v1/embeddings", "user-key") == \
        ("https://api.openai.com/v1/embeddings", "user-key")
    assert llm_egress.stand_in_for_provider_keys() == []


def test_a_mediated_call_goes_to_egress_with_this_accounts_credential(mediated):
    assert llm_egress.route_url("https://api.openai.com/v1/responses", "MASTER") == \
        (f"{GW}/p/openai/responses", TOKEN)
    assert llm_egress.route_url("https://api.z.ai/api/anthropic", "MASTER") == (f"{GW}/p/zai_anthropic", TOKEN)
    assert llm_egress.route_url("http://localhost:11434/v1/chat/completions", "ollama")[1] == "ollama"


def test_an_unknown_provider_is_not_routed_and_keeps_only_the_stand_in(mediated):
    llm_egress.stand_in_for_provider_keys()
    url, key = llm_egress.route_url("https://api.unknown.test/v1/x", TOKEN)
    assert url == "https://api.unknown.test/v1/x" and key == TOKEN, "it fails at the provider, never with a master key"


def test_the_stand_in_replaces_every_carried_key(mediated):
    import os
    names = llm_egress.stand_in_for_provider_keys()
    assert set(names) == set(llm_egress._STANDS_IN_FOR)
    assert {"OPENAI_API_KEY", "DEEPSEEK_API_KEY", "Z_AI_API_KEY", "GEMINI_API_KEY", "DEEPGRAM_API_KEY",
            "ELEVENLABS_API_KEY", "INWORLD_API_KEY"} <= set(names), names
    assert all(os.environ[n] == TOKEN for n in names)
    from nucleo.energy.keys import key_for_endpoint
    assert key_for_endpoint("https://api.deepseek.com") == TOKEN, "the model chains still see a usable rung"


def test_the_boot_stands_in_before_the_app_is_imported():
    src = (Path(__file__).resolve().parents[4] / "server" / "__main__.py").read_text(encoding="utf-8")
    assert src.index("stand_in_for_provider_keys()") < src.index("from server import app")


# ── the call sites that used to go direct ─────────────────────────────────────────────────────────────────────

def test_embeddings_go_through_egress(mediated, monkeypatch):
    from memory import embeddings
    # the suite stubs the real call out of the network and keeps it aside (tests/conftest.py)
    monkeypatch.setattr(embeddings, "_cloud_embed", embeddings._GENUINE_CLOUD_EMBED)
    seen = {}

    def post(url, body, headers, timeout):
        seen["url"], seen["auth"] = url, headers.get("Authorization")
        return {"data": [{"index": 0, "embedding": [0.1] * 8}], "usage": {"prompt_tokens": 3}}

    monkeypatch.setattr(embeddings, "_post_json", post)
    monkeypatch.setattr(embeddings, "_cloud_base_url", lambda: "https://api.openai.com/v1")
    embeddings._cloud_embed(["hola"])
    assert seen == {"url": f"{GW}/p/openai/embeddings", "auth": f"Bearer {TOKEN}"}


@pytest.mark.parametrize("module,expect", [("openai", "/p/openai/responses"), ("zai", "/p/zai/web_search"),
                                           ("gemini", "/p/gemini/models/")])
def test_each_paid_search_index_goes_through_egress(mediated, monkeypatch, module, expect):
    import httpx
    import importlib
    prov = importlib.import_module(f"search.providers.{module}")
    seen = {}

    class Client:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def post(self, url, headers=None, json=None):
            seen["url"], seen["headers"] = url, headers
            return httpx.Response(500, text="stop here")

    monkeypatch.setattr(httpx, "Client", Client)
    llm_egress.stand_in_for_provider_keys()
    with pytest.raises(RuntimeError):
        prov.search("¿A qué hora abre el Prado?", 3)
    assert seen["url"].startswith(GW + expect), seen["url"]
    assert TOKEN in json_dumps(seen["headers"]) and "MASTER" not in json_dumps(seen["headers"])


def json_dumps(o) -> str:
    return json.dumps(o, default=str)


def test_the_triage_model_goes_through_egress(mediated, monkeypatch):
    from connectors.messaging import config as mcfg, triage
    import aiohttp
    seen = {}

    class Resp:
        status = 200
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def json(self, content_type=None): return {"choices": [{"message": {"content": "{}"}}]}

    class Session:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        def post(self, url, headers=None, json=None):
            seen["url"], seen["headers"] = url, headers
            return Resp()

    monkeypatch.setattr(aiohttp, "ClientSession", Session)
    monkeypatch.setattr(mcfg, "triage_url", lambda: "https://api.deepseek.com")
    llm_egress.stand_in_for_provider_keys()
    try:
        asyncio.run(triage.classify([{"from": "Ana", "text": "¿Quedamos mañana?"}], operator_name="Ricart"))
    except Exception:  # noqa: BLE001 — only the request matters here
        pass
    assert seen.get("url") == f"{GW}/v1/chat/completions", seen
    assert seen["headers"]["Authorization"] == f"Bearer {TOKEN}"
    assert seen["headers"].get("X-Zaelar-Provider") == "deepseek"


def test_the_brain_worker_gets_egress_and_never_a_provider_key(mediated, monkeypatch):
    from nucleo.workers import providers
    monkeypatch.setattr(providers, "pick", lambda: {"name": "z.ai", "base_url": "https://api.z.ai/api/anthropic",
                                                     "api_key": "MASTER"})
    monkeypatch.setattr(providers, "vision_env", lambda t: {})
    env = providers.env_for_worker()
    assert env["ANTHROPIC_BASE_URL"] == f"{GW}/p/zai_anthropic"
    assert env["ANTHROPIC_AUTH_TOKEN"] == TOKEN


def test_a_search_egress_records_is_not_billed_again_here(mediated, monkeypatch):
    import httpx
    from nucleo.energy import account as cloud_account, meter as energy_meter
    posted = []

    class Client:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, url, json=None, headers=None, **k):
            posted.append((json or {}).get("kind"))
            return httpx.Response(200, json={"ok": True, "balance": 100})

    monkeypatch.setenv("CONTROL_PLANE_URL", "https://cp.example")
    monkeypatch.setattr(cloud_account, "my_user_id", lambda: "u-1")
    monkeypatch.setattr(httpx, "AsyncClient", Client)
    for kind in ("search", "llm", "decision", "tts"):
        asyncio.run(energy_meter._post_usage_cloud_account(1.0, kind))
    kinds = [k for k in posted if k]                   # the balance it answers may trigger other, kindless calls
    assert kinds == ["tts"], f"egress records search, llm and decision; a second post bills twice — posted {kinds}"


def test_the_balance_panel_does_not_probe_a_wallet_this_instance_does_not_hold(mediated):
    from config import balances
    for service, (envs, probe) in balances._PROBES.items():
        if probe and any(e in llm_egress._STANDS_IN_FOR for e in envs):
            assert balances.balance(service)["state"] == "unknown"


# ── voice (2026-10-23): the streaming sockets go through egress too ────────────────────────────────────────────

@pytest.mark.parametrize("module,attr,cls,expect", [
    ("voice.engine.speech.stt.deepgram", "_deepgram", "STT", "/p/deepgram/listen"),
    ("voice.engine.speech.tts.elevenlabs", "_eleven", "TTS", "/p/elevenlabs"),
    ("voice.engine.speech.tts.inworld", "_inworld", "TTS", "/p/inworld/"),
])
def test_each_voice_provider_opens_through_egress(mediated, monkeypatch, module, attr, cls, expect):
    import importlib
    mod = importlib.import_module(module)
    llm_egress.stand_in_for_provider_keys()
    seen = {}

    class Fake:
        def __init__(self, **kw):
            seen.update(kw)

    monkeypatch.setattr(getattr(mod, attr), cls, Fake)
    import dataclasses
    fields = {f: TOKEN for f in ("deepgram_api_key", "elevenlabs_api_key", "inworld_api_key")
              if hasattr(mod.SETTINGS, f)}
    monkeypatch.setattr(mod, "SETTINGS", dataclasses.replace(mod.SETTINGS, **fields))   # SETTINGS is frozen
    mod.build()
    assert seen["base_url"].startswith(GW + expect), seen.get("base_url")
    assert seen["api_key"] == TOKEN
    if "ws_url" in seen:
        assert seen["ws_url"].startswith("wss://egress.example/"), seen["ws_url"]


# ── LiveKit (T305, 2026-10-23): the secret signs a token for ANY room, so a mediated instance does not hold it ──

def test_the_browsers_room_token_is_signed_by_egress(mediated, monkeypatch):
    import httpx
    from livekit import api
    from server import livekit_api
    from nucleo import runstate
    seen = {}

    def post(url, json=None, headers=None, timeout=None):
        seen.update(url=url, auth=headers["Authorization"], body=json)
        return httpx.Response(200, json={"token": "t", "url": "wss://lk.example", "room": "zaelar-u-1-ab"})

    def never(*a, **k):
        raise AssertionError("a mediated instance signed a LiveKit token itself")

    monkeypatch.setattr(runstate, "stopped", lambda: False)
    monkeypatch.setattr(httpx, "post", post)
    monkeypatch.setattr(api, "AccessToken", never)
    res = livekit_api.token(identity="op", name="Ricart")
    assert res.status_code == 200 and json.loads(res.body)["room"] == "zaelar-u-1-ab"
    assert seen["url"] == f"{GW}/livekit/token" and seen["auth"] == f"Bearer {TOKEN}"


def test_the_voice_worker_registers_through_egress(mediated, monkeypatch):
    from voice.engine.pipeline import agent
    seen = {}

    class Server:
        def __init__(self, **kw):
            seen.update(kw)

        def rtc_session(self, *a, **k):
            return None

    monkeypatch.setattr(agent, "AgentServer", Server)
    agent.make_server()
    assert seen["ws_url"] == "wss://egress.example/livekit"
    assert seen["api_key"] == TOKEN and seen["api_secret"] == TOKEN, "the worker holds no LiveKit secret"


def test_a_mediated_voice_session_does_not_record_to_the_provider(mediated, monkeypatch):
    """Recording uploads are signed with the LiveKit key a mediated instance does not hold: each would be a 401."""
    from nucleo.energy import egress as llm_egress
    from voice.engine.pipeline import agent
    assert agent._session_start_opts() == {"record": False}
    monkeypatch.setattr(llm_egress, "mediated", lambda: False)
    assert agent._session_start_opts() == {}, "a self-hosted instance keeps the SDK default"
