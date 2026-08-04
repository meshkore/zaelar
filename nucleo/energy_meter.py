#
# ENERGY METERING (INI-018, added 2026-07-24) — real usage → real cost → "Energy" units, DEMO ONLY.
#
# Zaelar's product concept of "Energy" (web/src/components/Pricing.astro/Energy.astro,
# project/concept/docs/product/energy-model.md) had NO real conversion rate or ledger anywhere —
# confirmed by a full repo search before writing this. This module is the first real piece: it
# converts ACTUAL provider usage (LLM tokens, TTS characters, STT audio-seconds) into a real
# €-cost estimate, then into Energy units, and reports it fire-and-forget to the demo ledger
# (cloud/infra/demo-session-worker/'s /usage endpoint).
#
# SCOPE: this only ever fires for demo Machines (`ZAELAR_DEMO_SESSION` set — see
# nucleo/demo_limits.py, the same gate). The operator's own account and every self-host install
# have NO Energy system at all (energy-model.md is explicit about this) — `enabled()` being False
# there means zero cost, zero network calls, exactly like demo_limits.py's own no-op pattern.
#
# NUMBERS BELOW ARE DEFAULTS, NOT FINAL PRICING — flagged explicitly wherever they are business
# decisions, not technical facts:
#   - Per-provider $/token rates: real published pricing as of 2026-07-24 (web search), but
#     provider pricing changes — re-verify against the provider's own pricing page periodically,
#     don't treat these as permanently accurate.
#   - EUR_PER_ENERGY_UNIT (1 Energy = €0.01) and MARGIN_MULTIPLIER (4x raw cost) are OPERATOR
#     business decisions defaulted here for a working system — confirm/adjust, don't treat as final.
#
import os
import time

import httpx
from loguru import logger

# $ per 1M tokens, (input, output). Source: public provider pricing, 2026-07-24 — RE-VERIFY
# periodically, provider pricing changes without notice.
_RATES_PER_1M_TOKENS_USD: dict[str, tuple[float, float]] = {
    "x.ai": (0.20, 0.50),              # Grok 4.1 Fast tier — matches FAST_MODEL=grok-4.20-0309-non-reasoning
    "api.openai.com": (0.40, 1.60),    # gpt-4.1-mini — the memory CORAZÓN (mem_processor) model
    # Add a row here for every provider actually reachable from a demo Machine before relying on
    # this for anything beyond the FlashBrain (xai) call this module currently meters.
}

# Business decisions (see module docstring) — single constants, easy to tune without touching the
# calculation logic below.
EUR_PER_ENERGY_UNIT = float(os.getenv("ENERGY_EUR_PER_UNIT", "0.01"))   # 1 Energy = €0.01 (default)
MARGIN_MULTIPLIER = float(os.getenv("ENERGY_MARGIN_MULTIPLIER", "4.0"))  # retail vs raw compute cost


def enabled() -> bool:
    """Energy metering only exists for demo Machines (per-session OR warm-pool). Routes through the
    single 'am I a demo machine' accessor so pool machines (session learned at first touch) meter too."""
    from nucleo import demo_routing
    return demo_routing.is_demo_machine()


def _rate_for_base_url(base_url: str) -> tuple[float, float] | None:
    u = (base_url or "").lower()
    for needle, rates in _RATES_PER_1M_TOKENS_USD.items():
        if needle in u:
            return rates
    return None


def llm_cost_to_energy(
    *, base_url: str, prompt_tokens: int | None, completion_tokens: int | None
) -> float | None:
    """Pure. Returns Energy units for one LLM call, or None if this provider has no rate row (fails
    open — better to under-meter an unlisted provider than crash the turn over a billing detail)."""
    rates = _rate_for_base_url(base_url)
    if rates is None:
        return None
    in_rate, out_rate = rates
    pt = prompt_tokens or 0
    ct = completion_tokens or 0
    raw_usd = (pt / 1_000_000) * in_rate + (ct / 1_000_000) * out_rate
    retail_eur = raw_usd * MARGIN_MULTIPLIER  # treats USD≈EUR for simplicity — fine at these magnitudes
    return retail_eur / EUR_PER_ENERGY_UNIT


# $ per 1000 characters synthesized. Source: elevenlabs.io/pricing/api, 2026-07-24 (Flash/Turbo
# v2.5 API pay-as-you-go rate) — RE-VERIFY periodically, provider pricing changes without notice.
_TTS_USD_PER_1K_CHARS = float(os.getenv("ENERGY_TTS_USD_PER_1K_CHARS", "0.05"))

# $ per minute of audio, streaming/real-time. Source: deepgram.com/pricing, 2026-07-24 (Nova-3,
# Pay-As-You-Go tier, monolingual) — RE-VERIFY periodically.
_STT_USD_PER_MIN = float(os.getenv("ENERGY_STT_USD_PER_MIN", "0.0048"))


def tts_cost_to_energy(*, characters: int | None) -> float:
    """Pure. Energy units for one TTS synthesis call. Never None — TTS has one flat rate, no
    per-provider table (only ElevenLabs runs in the cloud profile; kokoro_local is filtered by the
    caller before this is ever invoked, same pattern as the metrics_collected hook in agent.py)."""
    chars = characters or 0
    raw_usd = (chars / 1000.0) * _TTS_USD_PER_1K_CHARS
    retail_eur = raw_usd * MARGIN_MULTIPLIER
    return retail_eur / EUR_PER_ENERGY_UNIT


def stt_cost_to_energy(*, audio_seconds: float | None) -> float:
    """Pure. Energy units for one STT transcription call (audio_duration from STTMetrics)."""
    secs = audio_seconds or 0.0
    raw_usd = (secs / 60.0) * _STT_USD_PER_MIN
    retail_eur = raw_usd * MARGIN_MULTIPLIER
    return retail_eur / EUR_PER_ENERGY_UNIT


# --- reporting: fire-and-forget POST to the demo session's own ledger, never blocks the turn ---

_USAGE_ENDPOINT_PATH = "/usage"


async def _post_usage(energy: float, kind: str) -> None:
    from nucleo import demo_routing
    worker_url = (os.getenv("DEMO_SESSION_WORKER_URL") or "").strip()
    session_id = demo_routing.my_session_id() or ""   # fixed env OR warm-pool pinned session
    if not worker_url or not session_id or energy <= 0:
        return
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            await client.post(
                worker_url.rstrip("/") + _USAGE_ENDPOINT_PATH,
                json={"session_id": session_id, "energy": energy, "kind": kind},
            )
    except Exception as e:  # noqa: BLE001
        logger.warning(f"energy_meter: usage report failed (non-fatal, turn unaffected): {e}")


def _fire_and_forget(energy: float, kind: str) -> None:
    """Shared tail of every report_*_usage(): schedule the POST without ever blocking or raising
    into the caller. No running loop (e.g. a unit test calling this directly) → drop silently."""
    import asyncio

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return
    asyncio.create_task(_post_usage(energy, kind))


def report_llm_usage(*, base_url: str, prompt_tokens: int | None, completion_tokens: int | None) -> None:
    """Call from the LLM streaming call site's `finally` block, AFTER usage/estimate is resolved.
    Fire-and-forget (asyncio.create_task) — never awaited by the caller, never adds latency to the
    turn. No-op with zero cost if not a demo Machine (enabled() False) or no running event loop."""
    if not enabled():
        return
    energy = llm_cost_to_energy(base_url=base_url, prompt_tokens=prompt_tokens, completion_tokens=completion_tokens)
    if energy is None:
        return
    _fire_and_forget(energy, "llm")


def report_tts_usage(*, characters: int | None) -> None:
    """Call from the TTSMetrics branch of agent.py's metrics_collected hook, AFTER the caller has
    already excluded local backends (kokoro_local — free, not metered). Same no-op/fire-and-forget
    contract as report_llm_usage."""
    if not enabled():
        return
    energy = tts_cost_to_energy(characters=characters)
    if energy <= 0:
        return
    _fire_and_forget(energy, "tts")


def report_stt_usage(*, audio_seconds: float | None) -> None:
    """Call from the STTMetrics branch of agent.py's metrics_collected hook, AFTER the caller has
    already excluded local backends (whisper_local — free, not metered). Same no-op/fire-and-forget
    contract as report_llm_usage."""
    if not enabled():
        return
    energy = stt_cost_to_energy(audio_seconds=audio_seconds)
    if energy <= 0:
        return
    _fire_and_forget(energy, "stt")
