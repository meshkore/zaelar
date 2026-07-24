import httpx
import pytest

from nucleo import energy_meter


def test_disabled_by_default(monkeypatch):
    monkeypatch.delenv("ZAELAR_DEMO_SESSION", raising=False)
    assert energy_meter.enabled() is False


def test_enabled_when_demo_session_set(monkeypatch):
    monkeypatch.setenv("ZAELAR_DEMO_SESSION", "abc-123")
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


def test_llm_cost_to_energy_unknown_provider_returns_none():
    assert (
        energy_meter.llm_cost_to_energy(
            base_url="https://some-unlisted-provider.example/v1", prompt_tokens=1000, completion_tokens=1000
        )
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
    energy_meter.report_tts_usage(characters=5000)


def test_report_stt_usage_noop_when_disabled(monkeypatch):
    monkeypatch.delenv("ZAELAR_DEMO_SESSION", raising=False)
    energy_meter.report_stt_usage(audio_seconds=120)


def test_report_llm_usage_noop_when_disabled(monkeypatch):
    monkeypatch.delenv("ZAELAR_DEMO_SESSION", raising=False)
    # must not raise, must not attempt any network call
    energy_meter.report_llm_usage(base_url="https://api.x.ai/v1", prompt_tokens=100, completion_tokens=100)


def test_report_llm_usage_noop_without_running_loop(monkeypatch):
    monkeypatch.setenv("ZAELAR_DEMO_SESSION", "abc-123")
    monkeypatch.setenv("DEMO_SESSION_WORKER_URL", "https://example.invalid")
    # sync context, no event loop running — must degrade silently, not raise
    energy_meter.report_llm_usage(base_url="https://api.x.ai/v1", prompt_tokens=100, completion_tokens=100)


@pytest.mark.anyio
async def test_post_usage_fails_open_on_network_error(monkeypatch):
    monkeypatch.setenv("ZAELAR_DEMO_SESSION", "abc-123")
    monkeypatch.setenv("DEMO_SESSION_WORKER_URL", "https://example.invalid")

    class _FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json=None):
            raise RuntimeError("network down")

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: _FakeClient())
    # must not raise — fails open
    await energy_meter._post_usage(42.0, "llm")


@pytest.fixture
def anyio_backend():
    return "asyncio"
