import httpx
import pytest

from nucleo import energy_meter


def test_disabled_by_default(monkeypatch):
    monkeypatch.delenv("ZAELAR_DEMO_SESSION", raising=False)
    monkeypatch.delenv("ZAELAR_DEMO_POOL", raising=False)
    monkeypatch.delenv("ZAELAR_DEMO_ROUTER", raising=False)
    monkeypatch.delenv("ZAELAR_USER_ID", raising=False)
    assert energy_meter.enabled() is False


def test_enabled_when_demo_session_set(monkeypatch):
    monkeypatch.delenv("ZAELAR_USER_ID", raising=False)
    monkeypatch.setenv("ZAELAR_DEMO_SESSION", "abc-123")
    assert energy_meter.enabled() is True


def test_enabled_when_cloud_account_set(monkeypatch):
    """2026-08-05: a real paying account (ZAELAR_USER_ID set by the provisioner) is metered too —
    not just the demo. No ZAELAR_DEMO_* env at all, purely the cloud-account gate."""
    monkeypatch.delenv("ZAELAR_DEMO_SESSION", raising=False)
    monkeypatch.delenv("ZAELAR_DEMO_POOL", raising=False)
    monkeypatch.delenv("ZAELAR_DEMO_ROUTER", raising=False)
    monkeypatch.setenv("ZAELAR_USER_ID", "did:key:z6MkExample")
    assert energy_meter.enabled() is True


def test_llm_cost_to_energy_xai(monkeypatch):
    monkeypatch.setenv("ENERGY_EUR_PER_UNIT", "0.01")
    monkeypatch.setenv("ENERGY_MARGIN_MULTIPLIER", "4.0")
    # 1M prompt + 1M completion tokens on x.ai: $0.20 + $0.50 = $0.70 raw, *4 margin = €2.80 retail
    # (treating USD≈EUR) / €0.01 per unit = 280 Energy.
    energy = energy_meter.llm_cost_to_energy(
        base_url="https://api.x.ai/v1", prompt_tokens=1_000_000, completion_tokens=1_000_000
    )
    assert energy == pytest.approx(280.0)


def test_llm_cost_to_energy_aimlapi_uses_per_model_rate(monkeypatch):
    """2026-08-05 fix: AIMLAPI is a multi-model broker — a bare base_url match would be wrong for it
    (dozens of models at very different prices). This is the exact call shape the FlashBrain makes in
    production (config/v2.json §fast: provider=aimlapi, model=deepseek/deepseek-v4-flash) — before the
    fix this silently returned None (zero Energy) because "aimlapi" wasn't in the old base_url table."""
    monkeypatch.setenv("ENERGY_EUR_PER_UNIT", "0.01")
    monkeypatch.setenv("ENERGY_MARGIN_MULTIPLIER", "4.0")
    energy = energy_meter.llm_cost_to_energy(
        base_url="https://api.aimlapi.com/v1",
        model="deepseek/deepseek-v4-flash",
        prompt_tokens=1_000_000,
        completion_tokens=1_000_000,
    )
    # $0.14 + $0.28 = $0.42 raw * 4 margin = €1.68 / €0.01 = 168 Energy — NOT None, NOT zero.
    assert energy == pytest.approx(168.0)


def test_llm_cost_to_energy_aimlapi_unknown_model_uses_fallback_not_none(monkeypatch):
    monkeypatch.setenv("ENERGY_EUR_PER_UNIT", "0.01")
    monkeypatch.setenv("ENERGY_MARGIN_MULTIPLIER", "4.0")
    energy = energy_meter.llm_cost_to_energy(
        base_url="https://api.aimlapi.com/v1",
        model="some/brand-new-model-not-in-the-table",
        prompt_tokens=1_000_000,
        completion_tokens=1_000_000,
    )
    assert energy is not None
    assert energy > 0


def test_llm_cost_to_energy_unlisted_provider_never_silently_free(monkeypatch):
    """The core 2026-08-05 fix: an unmapped (base_url, model) must NEVER meter as zero cost — that is
    exactly how real FlashBrain usage went unbilled. It must return the fallback rate, not None."""
    monkeypatch.setenv("ENERGY_EUR_PER_UNIT", "0.01")
    monkeypatch.setenv("ENERGY_MARGIN_MULTIPLIER", "4.0")
    energy = energy_meter.llm_cost_to_energy(
        base_url="https://some-unlisted-provider.example/v1", prompt_tokens=1_000_000, completion_tokens=1_000_000
    )
    assert energy is not None
    assert energy > 0


def test_llm_cost_to_energy_local_endpoint_is_free(monkeypatch):
    """Ollama/local endpoints stay genuinely free — the ONLY case that returns None."""
    for url in ("http://localhost:11434/v1", "http://127.0.0.1:11434/v1"):
        assert (
            energy_meter.llm_cost_to_energy(base_url=url, prompt_tokens=1_000_000, completion_tokens=1_000_000)
            is None
        )


def test_llm_cost_to_energy_handles_none_tokens():
    # None token counts (e.g. provider never sent usage AND estimate also failed) shouldn't crash —
    # treated as 0 usage, not an error.
    energy = energy_meter.llm_cost_to_energy(base_url="https://api.x.ai/v1", prompt_tokens=None, completion_tokens=None)
    assert energy == 0.0


def test_tts_cost_to_energy(monkeypatch):
    monkeypatch.setenv("ENERGY_EUR_PER_UNIT", "0.01")
    monkeypatch.setenv("ENERGY_MARGIN_MULTIPLIER", "4.0")
    monkeypatch.setenv("ENERGY_TTS_USD_PER_1K_CHARS", "0.05")
    # 2000 chars @ $0.05/1k = $0.10 raw, *4 margin = €0.40 (USD≈EUR) / €0.01 per unit = 40 Energy.
    energy = energy_meter.tts_cost_to_energy(characters=2000)
    assert energy == pytest.approx(40.0)


def test_tts_cost_to_energy_handles_none_characters():
    assert energy_meter.tts_cost_to_energy(characters=None) == 0.0


def test_stt_cost_to_energy(monkeypatch):
    monkeypatch.setenv("ENERGY_EUR_PER_UNIT", "0.01")
    monkeypatch.setenv("ENERGY_MARGIN_MULTIPLIER", "4.0")
    monkeypatch.setenv("ENERGY_STT_USD_PER_MIN", "0.0048")
    # 60 min @ $0.0048/min = $0.288 raw, *4 margin = €1.152 / €0.01 per unit = 115.2 Energy.
    energy = energy_meter.stt_cost_to_energy(audio_seconds=3600)
    assert energy == pytest.approx(115.2)


def test_stt_cost_to_energy_handles_none_seconds():
    assert energy_meter.stt_cost_to_energy(audio_seconds=None) == 0.0


def test_report_tts_usage_noop_when_disabled(monkeypatch):
    monkeypatch.delenv("ZAELAR_DEMO_SESSION", raising=False)
    monkeypatch.delenv("ZAELAR_USER_ID", raising=False)
    energy_meter.report_tts_usage(characters=5000)


def test_report_stt_usage_noop_when_disabled(monkeypatch):
    monkeypatch.delenv("ZAELAR_DEMO_SESSION", raising=False)
    monkeypatch.delenv("ZAELAR_USER_ID", raising=False)
    energy_meter.report_stt_usage(audio_seconds=120)


def test_report_llm_usage_noop_when_disabled(monkeypatch):
    monkeypatch.delenv("ZAELAR_DEMO_SESSION", raising=False)
    monkeypatch.delenv("ZAELAR_USER_ID", raising=False)
    # must not raise, must not attempt any network call
    energy_meter.report_llm_usage(base_url="https://api.x.ai/v1", prompt_tokens=100, completion_tokens=100)


def test_report_worker_usage_noop_when_disabled(monkeypatch):
    monkeypatch.delenv("ZAELAR_DEMO_SESSION", raising=False)
    monkeypatch.delenv("ZAELAR_USER_ID", raising=False)
    energy_meter.report_worker_usage(
        base_url="https://api.z.ai/api/anthropic", model="glm-5.2", prompt_tokens=100, completion_tokens=100
    )


def test_report_llm_usage_noop_without_running_loop(monkeypatch):
    monkeypatch.setenv("ZAELAR_DEMO_SESSION", "abc-123")
    monkeypatch.setenv("DEMO_SESSION_WORKER_URL", "https://example.invalid")
    # sync context, no event loop running — must degrade silently, not raise
    energy_meter.report_llm_usage(base_url="https://api.x.ai/v1", prompt_tokens=100, completion_tokens=100)


@pytest.mark.anyio
async def test_post_usage_fails_open_on_network_error(monkeypatch):
    monkeypatch.delenv("ZAELAR_USER_ID", raising=False)
    monkeypatch.setenv("ZAELAR_DEMO_SESSION", "abc-123")
    monkeypatch.setenv("DEMO_SESSION_WORKER_URL", "https://example.invalid")

    class _FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json=None, headers=None):
            raise RuntimeError("network down")

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: _FakeClient())
    # must not raise — fails open
    await energy_meter._post_usage(42.0, "llm")


@pytest.mark.anyio
async def test_post_usage_routes_cloud_account_to_control_plane(monkeypatch):
    """2026-08-05: a real account (ZAELAR_USER_ID set) must post to CONTROL_PLANE_URL/usage with
    {user_id, energy, kind} — never to the demo Worker's session_id-keyed KV ledger."""
    monkeypatch.setenv("ZAELAR_USER_ID", "did:key:z6MkExample")
    monkeypatch.setenv("CONTROL_PLANE_URL", "https://zaelar-control-plane.example.workers.dev")
    monkeypatch.setenv("CONTROL_PLANE_SERVICE_TOKEN", "shh-secret")
    monkeypatch.delenv("ZAELAR_DEMO_SESSION", raising=False)
    captured = {}

    class _FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json=None, headers=None):
            captured["url"] = url
            captured["json"] = json
            captured["headers"] = headers

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: _FakeClient())
    await energy_meter._post_usage(12.5, "worker")
    assert captured["url"] == "https://zaelar-control-plane.example.workers.dev/usage"
    assert captured["json"] == {"user_id": "did:key:z6MkExample", "energy": 12.5, "kind": "worker"}
    assert captured["headers"] == {"X-Service-Token": "shh-secret"}


@pytest.mark.anyio
async def test_post_usage_cloud_account_noop_without_control_plane_url(monkeypatch):
    monkeypatch.setenv("ZAELAR_USER_ID", "did:key:z6MkExample")
    monkeypatch.delenv("CONTROL_PLANE_URL", raising=False)

    async def _boom(*a, **kw):
        raise AssertionError("must not attempt a network call without CONTROL_PLANE_URL")

    monkeypatch.setattr(httpx, "AsyncClient", _boom)
    await energy_meter._post_usage(12.5, "worker")


@pytest.mark.anyio
async def test_post_usage_demo_session_also_reports_to_control_plane(monkeypatch):
    """2026-08-08: a demo session (no account) must ALSO post to CONTROL_PLANE_URL/usage with
    {session_id, energy, kind} — for centralized observability (zaelar_user_events) — in ADDITION
    to, not instead of, the demo Worker's own session_id-keyed KV ledger call."""
    monkeypatch.delenv("ZAELAR_USER_ID", raising=False)
    monkeypatch.setenv("ZAELAR_DEMO_SESSION", "demo-sess-1")
    monkeypatch.setenv("DEMO_SESSION_WORKER_URL", "https://zaelar-demo-session.example.workers.dev")
    monkeypatch.setenv("CONTROL_PLANE_URL", "https://zaelar-control-plane.example.workers.dev")
    calls = []

    class _FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json=None, headers=None):
            calls.append({"url": url, "json": json, "headers": headers})

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: _FakeClient())
    await energy_meter._post_usage(7.0, "tts")
    assert len(calls) == 2
    assert calls[0]["url"] == "https://zaelar-demo-session.example.workers.dev/usage"
    assert calls[0]["json"] == {"session_id": "demo-sess-1", "energy": 7.0, "kind": "tts"}
    assert calls[1]["url"] == "https://zaelar-control-plane.example.workers.dev/usage"
    assert calls[1]["json"] == {"session_id": "demo-sess-1", "energy": 7.0, "kind": "tts"}


@pytest.mark.anyio
async def test_post_usage_demo_session_control_plane_noop_without_url(monkeypatch):
    monkeypatch.delenv("ZAELAR_USER_ID", raising=False)
    monkeypatch.setenv("ZAELAR_DEMO_SESSION", "demo-sess-1")
    monkeypatch.delenv("DEMO_SESSION_WORKER_URL", raising=False)
    monkeypatch.delenv("CONTROL_PLANE_URL", raising=False)

    async def _boom(*a, **kw):
        raise AssertionError("must not attempt a network call without either URL configured")

    monkeypatch.setattr(httpx, "AsyncClient", _boom)
    await energy_meter._post_usage(7.0, "tts")


@pytest.fixture
def anyio_backend():
    return "asyncio"
