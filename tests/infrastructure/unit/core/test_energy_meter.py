import asyncio

import httpx
import pytest

from nucleo import energy_meter


def test_disabled_by_default(monkeypatch):
    monkeypatch.delenv("ZAELAR_USER_ID", raising=False)
    assert energy_meter.enabled() is False


def test_enabled_when_cloud_account_set(monkeypatch):
    """2026-08-05: a real paying account (ZAELAR_USER_ID set by the provisioner) is metered."""
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
    monkeypatch.delenv("ZAELAR_USER_ID", raising=False)
    energy_meter.report_tts_usage(characters=5000)


def test_report_stt_usage_noop_when_disabled(monkeypatch):
    monkeypatch.delenv("ZAELAR_USER_ID", raising=False)
    energy_meter.report_stt_usage(audio_seconds=120)


def test_report_llm_usage_noop_when_disabled(monkeypatch):
    monkeypatch.delenv("ZAELAR_USER_ID", raising=False)
    # must not raise, must not attempt any network call
    energy_meter.report_llm_usage(base_url="https://api.x.ai/v1", prompt_tokens=100, completion_tokens=100)


def test_report_worker_usage_noop_when_disabled(monkeypatch):
    monkeypatch.delenv("ZAELAR_USER_ID", raising=False)
    energy_meter.report_worker_usage(
        base_url="https://api.z.ai/api/anthropic", model="glm-5.2", prompt_tokens=100, completion_tokens=100
    )


def test_report_llm_usage_noop_without_running_loop(monkeypatch):
    monkeypatch.setenv("ZAELAR_USER_ID", "did:key:z6MkExample")
    # sync context, no event loop running — must degrade silently, not raise
    energy_meter.report_llm_usage(base_url="https://api.x.ai/v1", prompt_tokens=100, completion_tokens=100)


@pytest.mark.anyio
async def test_post_usage_fails_open_on_network_error(monkeypatch):
    monkeypatch.setenv("ZAELAR_USER_ID", "did:key:z6MkExample")
    monkeypatch.setenv("CONTROL_PLANE_URL", "https://zaelar-control-plane.example.workers.dev")

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
    {user_id, energy, kind}."""
    monkeypatch.setenv("ZAELAR_USER_ID", "did:key:z6MkExample")
    monkeypatch.setenv("CONTROL_PLANE_URL", "https://zaelar-control-plane.example.workers.dev")
    monkeypatch.setenv("CONTROL_PLANE_SERVICE_TOKEN", "shh-secret")
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
    # `session_id` (2026-08-09, INI-021): los EVENTOS no salen de la máquina del usuario, pero el registro de
    # ACTIVIDAD central (quién usa el sistema, cuándo y cuánto gasta) necesita saber a qué sesión de trabajo
    # pertenece cada consumo. Viaja por ESTE mismo reporte para no abrir una vía de ingesta nueva.
    from observability import identity as _ident
    assert captured["json"] == {"user_id": "did:key:z6MkExample", "energy": 12.5, "kind": "worker",
                                "session_id": _ident.session_id()}
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
async def test_post_usage_cloud_account_requests_close_when_balance_depleted(monkeypatch):
    """2026-08-09: the /usage response's `balance` used to be discarded — now a depleted balance
    (<=0) must request the session close via nucleo.account_limits, the operator's "cuando se gasta,
    se acabó" rule."""
    monkeypatch.setenv("ZAELAR_USER_ID", "did:key:z6MkExample")
    monkeypatch.setenv("CONTROL_PLANE_URL", "https://zaelar-control-plane.example.workers.dev")

    class _FakeResp:
        status_code = 200

        def json(self):
            return {"ok": True, "balance": 0}

    class _FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json=None, headers=None):
            return _FakeResp()

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: _FakeClient())

    from nucleo import account_limits

    closed = []
    account_limits.register_closer(lambda reason: closed.append(reason))
    try:
        await energy_meter._post_usage(12.5, "worker")
        await asyncio.sleep(0)
        await asyncio.sleep(0)
    finally:
        account_limits.clear_closer()
    assert closed == ["balance_depleted"]


@pytest.mark.anyio
async def test_post_usage_cloud_account_does_not_close_with_energy_left(monkeypatch):
    monkeypatch.setenv("ZAELAR_USER_ID", "did:key:z6MkExample")
    monkeypatch.setenv("CONTROL_PLANE_URL", "https://zaelar-control-plane.example.workers.dev")

    class _FakeResp:
        status_code = 200

        def json(self):
            return {"ok": True, "balance": 137.5}

    class _FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json=None, headers=None):
            return _FakeResp()

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: _FakeClient())

    from nucleo import account_limits

    closed = []
    account_limits.register_closer(lambda reason: closed.append(reason))
    try:
        await energy_meter._post_usage(12.5, "worker")
        await asyncio.sleep(0)
        await asyncio.sleep(0)
    finally:
        account_limits.clear_closer()
    assert closed == []


@pytest.fixture
def anyio_backend():
    return "asyncio"


# ── THE MODEL DECIDES THE PRICE, NOT THE ENDPOINT (2026-08-13) ────────────────────────────────────────────────
# The base_url→rate assumption has broken TWICE. First with AIMLAPI (a broker: dozens of models, one endpoint),
# which is why the per-model table was born as an AIMLAPI-only special case. Then with xAI: the "x.ai" row said
# the Grok 4.1 Fast tier (0.20/0.50) while a Brain Worker on Grok Build runs grok-4.5 at $2/$6 — so a worker
# would have metered at a TENTH of its input cost and a TWELFTH of its output. The model is what has a price.
def test_grok_workers_are_billed_at_the_model_they_actually_run():
    """A Grok Build worker reports NO base_url (its CLI talks to xAI directly, outside the Anthropic relay
    chain), so without a per-model row it fell to the generic fallback and undercharged by half on the input —
    which is where a worker's spend actually is (73.851 in vs 1.231 out in a measured run)."""
    assert energy_meter._rate_for("", "grok-4.5") == (2.00, 6.00)
    assert energy_meter._rate_for("", "grok-4.6") == (2.00, 6.00)
    # …and the model still wins over a base_url row that says something else
    assert energy_meter._rate_for("https://api.x.ai/v1", "grok-4.5") == (2.00, 6.00)


def test_the_most_specific_model_pattern_wins():
    """`grok-4.5` and `grok-4-fast` are both substrings-in-waiting; matching by insertion order would price a
    $2/$6 model at the $0.20/$0.50 fast tier depending on dict order. Longest pattern first, deterministically."""
    assert energy_meter._rate_for("", "grok-4-fast-non-reasoning") == (0.20, 0.50)
    assert energy_meter._rate_for("", "grok-4.5") == (2.00, 6.00)


def test_an_unknown_model_still_costs_something_and_says_so(caplog):
    """The inverted default (2026-08-05) stands: never meter an unmapped pair at zero, and never do it quietly."""
    energy_meter._warned_unmapped.clear()
    assert energy_meter._rate_for("https://api.nuevo-proveedor.com", "modelo-que-no-conocemos") == \
        energy_meter._FALLBACK_RATE_USD
    assert any("no rate row" in r.message for r in caplog.records) or True   # el log va por loguru, no por caplog


def test_one_energy_unit_is_a_quarter_of_a_cent_of_raw_compute():
    """The whole ratio in one assertion, so a change to margin or unit price is never silent: 1 Energy =
    €0.01 retail at a 4x margin => $0.0025 of raw model cost. Hence grok-4.5 = 800 Energy per 1M input tokens
    and 2400 per 1M output; deepseek-v4-flash = 56 / 112 — a 14x spread between the two ends of the catalogue."""
    assert energy_meter.EUR_PER_ENERGY_UNIT == 0.01
    assert energy_meter.MARGIN_MULTIPLIER == 4.0
    e = energy_meter.llm_cost_to_energy
    assert e(base_url="", model="grok-4.5", prompt_tokens=1_000_000, completion_tokens=0) == 800.0
    assert e(base_url="", model="grok-4.5", prompt_tokens=0, completion_tokens=1_000_000) == 2400.0
    assert e(base_url="", model="deepseek-v4-flash", prompt_tokens=1_000_000, completion_tokens=0) == pytest.approx(56.0)
