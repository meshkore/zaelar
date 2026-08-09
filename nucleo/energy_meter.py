#
# ENERGY METERING (INI-018, added 2026-07-24; extended 2026-08-05 — INI-019 addenda) — real usage →
# real cost → "Energy" units.
#
# Zaelar's product concept of "Energy" (web/src/components/Pricing.astro/Energy.astro,
# project/concept/docs/product/energy-model.md) had NO real conversion rate or ledger anywhere —
# confirmed by a full repo search before writing this. This module converts ACTUAL provider usage
# (LLM tokens, TTS characters, STT audio-seconds, Brain Worker tokens) into a real €-cost estimate,
# then into Energy units, and reports it fire-and-forget to the right ledger (demo Worker's ephemeral
# KV, or the control-plane's persistent per-account ledger — see _post_usage).
#
# SCOPE: fires for demo Machines (`ZAELAR_DEMO_SESSION`/pool/router — nucleo/demo_routing.py) AND for
# real cloud accounts (`ZAELAR_USER_ID` — nucleo/cloud_account.py, wired 2026-08-05). The operator's
# own local install and every self-host install have NEITHER set → enabled() False → zero cost, zero
# network calls, exactly like demo_limits.py's own no-op pattern.
#
# 2026-08-05 FINDING (see INI-019 addenda for the full incident writeup): report_llm_usage() was only
# ever called from the FlashBrain's voice turn (nucleo/flash/fast_client.py), and the rate table only
# covered "x.ai"/"api.openai.com" — but the FlashBrain's actual production model runs on AIMLAPI
# (a multi-model broker, config/v2.json §fast), which matched NEITHER row. Every real voice turn was
# metering silently to zero cost. Fixed by: (a) per-MODEL rates for the AIMLAPI broker (a single
# base_url covers dozens of differently-priced models — a base_url-only table cannot express that),
# (b) a non-None FALLBACK rate for any (base_url, model) this table doesn't yet know about, so a
# future unlisted provider degrades to "probably overcharges a little" instead of "silently free" —
# under-metering loses real money, over-metering by a small margin on a rare/unknown provider does not.
# Brain Workers (nucleo/workers/, Claude Code CLI relayed to Z.AI/Moonshot/local license) are metered
# too (report_worker_usage) — they were computing real usage/cost already (claude_session.py's stream-
# json "result" message) but discarding it into a UI chip, never into Energy.
#
# NUMBERS BELOW ARE DEFAULTS, NOT FINAL PRICING — flagged explicitly wherever they are business
# decisions, not technical facts:
#   - Per-provider/per-model $/token rates: real published pricing as of 2026-08-05 (web search) —
#     re-verify against the provider's own pricing page periodically, don't treat as permanently
#     accurate. Same norm as the rest of the repo (see V2-035's "never assume, verify" note).
#   - EUR_PER_ENERGY_UNIT (1 Energy = €0.01) and MARGIN_MULTIPLIER (4x raw cost) are OPERATOR
#     business decisions defaulted here for a working system — confirm/adjust, don't treat as final.
#   - The FALLBACK rate for an unmapped (base_url, model) is a deliberate business choice: better to
#     mildly over-meter an unknown provider (logged loudly so it gets a real rate added) than to ever
#     silently meter it as free.
#
import os
import time

import httpx
from loguru import logger

# $ per 1M tokens, (input, output), matched by substring against `base_url`. Covers providers that
# serve a single (or effectively single-priced) model directly — NOT brokers like AIMLAPI, which
# serve dozens of models at very different prices (see _AIMLAPI_MODEL_RATES below).
# Source: public provider pricing, 2026-08-05 — RE-VERIFY periodically, provider pricing changes.
_RATES_PER_1M_TOKENS_USD: dict[str, tuple[float, float]] = {
    "x.ai": (0.20, 0.50),               # Grok 4.1 Fast tier
    "api.openai.com": (0.40, 1.60),     # gpt-4.1-mini tier (OpenAI direct is no longer a default anywhere)
    "api.z.ai": (1.40, 4.40),           # GLM-5.2 — the Brain Workers' primary relay tier (code_agent)
    "moonshot.ai": (0.95, 4.00),        # Kimi K2.6 — the Brain Workers' secondary relay tier
}

# $ per 1M tokens, (input, output), matched by substring against the MODEL name — only consulted when
# `base_url` resolves to the AIMLAPI broker (api.aimlapi.com), which serves many models at different
# prices; a single base_url→rate row (as used above) cannot express that. Source: public AIMLAPI/
# DeepSeek/Anthropic pricing, 2026-08-05 — RE-VERIFY periodically.
_AIMLAPI_MODEL_RATES: dict[str, tuple[float, float]] = {
    # Serves TWO pieces since 2026-08-09: the FlashBrain (config §fast) and the memory CORAZÓN
    # (config §memory.mem_processor_model — see zaelar-model-benchmarks.md §12.3). Measured cost of
    # one distilled turn: ~4076 in + ~389 out tokens => ~$0.00068, i.e. $0.68 per 1000 turns.
    "deepseek-v4-flash": (0.14, 0.28),
    "claude-haiku-4.5": (1.00, 5.00),          # FlashBrain's _FALLBACK_MODEL
    # CORAZÓN fallback chain (§12.3), rated so a failover never meters as the generic fallback rate.
    "gemini-2.5-flash-lite": (0.10, 0.40),
    "gemini-2.5-flash": (0.30, 2.50),
    "gpt-4.1-mini": (0.40, 1.60),              # previous CORAZÓN titular; last link of the chain
    "gpt-4.1-nano": (0.10, 0.40),
    "gpt-4o-mini": (0.15, 0.60),
    "grok-4-fast": (0.20, 0.50),
    "kimi-k2": (0.95, 4.00),
    "glm-4.7": (0.40, 1.75),
    "ministral-8b": (0.10, 0.10),
    "llama-3.3-70b": (0.59, 0.79),
}

# Applied when neither table above has a row for the (base_url, model) actually used. Deliberately NOT
# the cheapest rate seen (that would risk under-charging real usage on an unlisted provider) — see
# module docstring. Logged loudly (once per distinct unmapped key) so an operator notices and adds a
# real rate instead of this staying the permanent answer.
_FALLBACK_RATE_USD: tuple[float, float] = (1.00, 5.00)
_warned_unmapped: set[str] = set()

# Business decisions (see module docstring) — single constants, easy to tune without touching the
# calculation logic below.
EUR_PER_ENERGY_UNIT = float(os.getenv("ENERGY_EUR_PER_UNIT", "0.01"))   # 1 Energy = €0.01 (default)
MARGIN_MULTIPLIER = float(os.getenv("ENERGY_MARGIN_MULTIPLIER", "4.0"))  # retail vs raw compute cost


def enabled() -> bool:
    """Energy metering exists for demo Machines (per-session OR warm-pool) AND for real cloud accounts
    (ZAELAR_USER_ID set, 2026-08-05). Routes through the two single-purpose accessors so neither this
    module nor its callers need to know the shape of either gate."""
    from nucleo import cloud_account, demo_routing
    return demo_routing.is_demo_machine() or cloud_account.is_cloud_account()


def _is_local_endpoint(base_url: str) -> bool:
    u = (base_url or "").lower()
    return "11434" in u or "localhost" in u or "127.0.0.1" in u


def _rate_for(base_url: str, model: str | None) -> tuple[float, float]:
    """Never returns None — local endpoints are filtered by the caller BEFORE this is reached
    (llm_cost_to_energy). Every real cloud endpoint gets a rate: exact if we have one, a per-model
    AIMLAPI rate if the broker is AIMLAPI, else the fallback (logged once)."""
    u = (base_url or "").lower()
    m = (model or "").lower()
    if "aimlapi" in u and m:
        for needle, rates in _AIMLAPI_MODEL_RATES.items():
            if needle in m:
                return rates
    for needle, rates in _RATES_PER_1M_TOKENS_USD.items():
        if needle in u:
            return rates
    key = f"{u}::{m}"
    if key not in _warned_unmapped:
        _warned_unmapped.add(key)
        logger.warning(
            f"energy_meter: no rate row for base_url={base_url!r} model={model!r} — charging the "
            f"fallback rate {_FALLBACK_RATE_USD} $/1M tokens. Add a real rate to energy_meter.py."
        )
    return _FALLBACK_RATE_USD


def llm_cost_to_energy(
    *, base_url: str, model: str | None = None, prompt_tokens: int | None, completion_tokens: int | None
) -> float | None:
    """Pure. Returns Energy units for one LLM call, or None only for a local/free endpoint (Ollama —
    11434/localhost/127.0.0.1). Every real cloud endpoint always returns a value (exact rate if known,
    fallback otherwise) — see module docstring for why this changed from the original fail-open design."""
    if _is_local_endpoint(base_url):
        return None
    in_rate, out_rate = _rate_for(base_url, model)
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


# --- reporting: fire-and-forget POST to the right ledger, never blocks the turn/worker ---

_USAGE_ENDPOINT_PATH = "/usage"


async def _post_usage(energy: float, kind: str, meta: dict | None = None) -> None:
    from nucleo import cloud_account

    if cloud_account.is_cloud_account():
        await _post_usage_cloud_account(energy, kind, meta)
        return
    from nucleo import demo_routing

    session_id = demo_routing.my_session_id() or ""   # fixed env OR warm-pool pinned session
    worker_url = (os.getenv("DEMO_SESSION_WORKER_URL") or "").strip()
    if worker_url and session_id and energy > 0:
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                await client.post(
                    worker_url.rstrip("/") + _USAGE_ENDPOINT_PATH,
                    json={"session_id": session_id, "energy": energy, "kind": kind},
                )
        except Exception as e:  # noqa: BLE001
            logger.warning(f"energy_meter: usage report failed (non-fatal, turn unaffected): {e}")
    # 2026-08-08: ALSO report to the control-plane (zaelar_user_events, keyed by session_id — no
    # account exists yet) — "everything goes through zaelar_user_events" (operator ask). The demo
    # Worker's KV above stays the actual budget cap; this call is purely for centralized
    # observability, so its own failure must never affect (or be affected by) the call above.
    await _post_usage_demo_to_control_plane(session_id, energy, kind, meta)


async def _post_usage_demo_to_control_plane(session_id: str, energy: float, kind: str, meta: dict | None) -> None:
    """Demo-session counterpart of _post_usage_cloud_account: same /usage call, session_id instead of
    user_id, no Energy ledger involved (a demo session has no account to bill — energy.consume is
    skipped control-plane-side when there's no user_id). CONTROL_PLANE_URL is injected by the
    provisioner at Machine creation (machineConfig.js::demoMachineConfig/demoPoolMachineConfig,
    2026-08-08) — guarded-until-configured, same as everywhere else: missing it → no-op, never raises."""
    control_plane_url = (os.getenv("CONTROL_PLANE_URL") or "").strip()
    if not control_plane_url or not session_id or energy <= 0:
        return
    service_token = (os.getenv("CONTROL_PLANE_SERVICE_TOKEN") or "").strip()
    headers = {"X-Service-Token": service_token} if service_token else {}
    payload = {"session_id": session_id, "energy": energy, "kind": kind}
    if meta:
        payload["meta"] = meta
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            await client.post(
                control_plane_url.rstrip("/") + _USAGE_ENDPOINT_PATH,
                json=payload,
                headers=headers,
            )
    except Exception as e:  # noqa: BLE001
        logger.warning(f"energy_meter: demo-session control-plane report failed (non-fatal): {e}")


async def _post_usage_cloud_account(energy: float, kind: str, meta: dict | None = None) -> None:
    """Real-account counterpart of _post_usage: reports to the control-plane's PERSISTENT per-user
    Energy ledger (cloud/control-plane's POST /usage) instead of the demo Worker's ephemeral KV. The
    control-plane writes this SAME call into zaelar_user_events too (INI-019 addenda, "Cambio A") — so
    `meta` (model/base_url ONLY — never content) doubles as the per-user activity timeline the
    backoffice reads. CONTROL_PLANE_URL/CONTROL_PLANE_SERVICE_TOKEN are injected by the provisioner at
    Machine creation (cloud/provisioner/src/machineConfig.js::accountMachineConfig) — same
    guarded-until-configured pattern as everything else here: missing either → no-op, never raises."""
    from nucleo import cloud_account

    control_plane_url = (os.getenv("CONTROL_PLANE_URL") or "").strip()
    user_id = cloud_account.my_user_id()
    if not control_plane_url or not user_id or energy <= 0:
        return
    service_token = (os.getenv("CONTROL_PLANE_SERVICE_TOKEN") or "").strip()
    headers = {"X-Service-Token": service_token} if service_token else {}
    payload = {"user_id": user_id, "energy": energy, "kind": kind}
    if meta:
        payload["meta"] = meta
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            await client.post(
                control_plane_url.rstrip("/") + _USAGE_ENDPOINT_PATH,
                json=payload,
                headers=headers,
            )
    except Exception as e:  # noqa: BLE001
        logger.warning(f"energy_meter: cloud-account usage report failed (non-fatal): {e}")


def _fire_and_forget(energy: float, kind: str, meta: dict | None = None) -> None:
    """Shared tail of every report_*_usage(): schedule the POST without ever blocking or raising
    into the caller. No running loop (e.g. a unit test calling this directly) → drop silently."""
    import asyncio

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return
    asyncio.create_task(_post_usage(energy, kind, meta))


def report_llm_usage(
    *, base_url: str, model: str | None = None, prompt_tokens: int | None, completion_tokens: int | None
) -> None:
    """Call from the LLM streaming call site's `finally` block, AFTER usage/estimate is resolved.
    Fire-and-forget (asyncio.create_task) — never awaited by the caller, never adds latency to the
    turn. No-op with zero cost if not a metered account (enabled() False) or no running event loop."""
    if not enabled():
        return
    energy = llm_cost_to_energy(
        base_url=base_url, model=model, prompt_tokens=prompt_tokens, completion_tokens=completion_tokens
    )
    if energy is None:
        return
    _fire_and_forget(energy, "llm", {"model": model, "base_url": base_url})


def report_worker_usage(
    *, base_url: str, model: str | None = None, prompt_tokens: int | None, completion_tokens: int | None
) -> None:
    """Call from a Brain Worker session's completion (nucleo/workers/session.py::_finish), AFTER the
    stream-json "result" usage is known. Same rate table and fire-and-forget contract as
    report_llm_usage — a worker call IS an LLM call, just reached via the Claude Code CLI subprocess
    instead of an HTTP client. Deliberately does NOT use the CLI's own `total_cost_usd`: that figure is
    computed by the CLI against OFFICIAL Anthropic pricing, which is meaningless once the call was
    relayed to a flat-rate subscription tier (Z.AI/Moonshot, see nucleo/workers/providers.py) — pricing
    by our own per-model table keeps worker Energy consistent with every other metered call."""
    if not enabled():
        return
    energy = llm_cost_to_energy(
        base_url=base_url, model=model, prompt_tokens=prompt_tokens, completion_tokens=completion_tokens
    )
    if energy is None:
        return
    _fire_and_forget(energy, "worker", {"model": model, "base_url": base_url})


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
