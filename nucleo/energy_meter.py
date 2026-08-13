#
# ENERGY METERING (INI-018, added 2026-07-24; extended 2026-08-05 — INI-019 addenda) — real usage →
# real cost → "Energy" units.
#
# Zaelar's product concept of "Energy" (web/src/components/Pricing.astro/Energy.astro,
# project/concept/docs/product/energy-model.md) had NO real conversion rate or ledger anywhere —
# confirmed by a full repo search before writing this. This module converts ACTUAL provider usage
# (LLM tokens, TTS characters, STT audio-seconds, Brain Worker tokens) into a real €-cost estimate,
# then into Energy units, and reports it fire-and-forget to the control-plane's persistent
# per-account ledger (see _post_usage_cloud_account).
#
# SCOPE: fires for real cloud accounts (`ZAELAR_USER_ID` — nucleo/cloud_account.py, wired
# 2026-08-05). The operator's own local install and every self-host install don't set it →
# enabled() False → zero cost, zero network calls.
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
# serve dozens of models at very different prices (see _MODEL_RATES below, which is consulted FIRST).
# Source: public provider pricing, 2026-08-05 — RE-VERIFY periodically, provider pricing changes.
_RATES_PER_1M_TOKENS_USD: dict[str, tuple[float, float]] = {
    "x.ai": (0.20, 0.50),               # Grok 4.1 Fast tier
    "api.openai.com": (0.40, 1.60),     # gpt-4.1-mini tier (OpenAI direct is no longer a default anywhere)
    "api.z.ai": (1.40, 4.40),           # GLM-5.2 — the Brain Workers' primary relay tier (code_agent)
    "moonshot.ai": (0.95, 4.00),        # Kimi K2.6 — the Brain Workers' secondary relay tier
}

# $ per 1M tokens, (input, output), matched by substring against the MODEL name. Consulted FIRST for
# every provider, not just brokers (changed 2026-08-13 — it used to be AIMLAPI-only).
#
# Why model-first is the general case: a base_url→rate row can only be right where one endpoint serves
# one price. That assumption has now broken TWICE. First with AIMLAPI (a broker, dozens of models at
# very different prices) — which is why this table was born. Then with xAI: the "x.ai" row said
# (0.20, 0.50), the Grok 4.1 Fast tier, but a Brain Worker on Grok Build runs **grok-4.5 at $2/$6** —
# 10x the input rate. A worker on Grok would have metered at a TWELFTH of its output cost. The model
# is what has a price; the endpoint is just where it is served. So the model decides, and base_url is
# only the fallback for endpoints that really do serve a single price.
_MODEL_RATES: dict[str, tuple[float, float]] = {
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
    # Brain Workers conducidos por Grok Build (backend `grok_build`, 2026-08-13). Su CLI habla con xAI
    # DIRECTAMENTE (no por la cadena de relevo Anthropic), así que la sesión no reporta base_url y sin
    # una fila POR MODELO caería al fallback — cobrando la mitad del input, que es donde está el gasto
    # de un worker (73.851 in vs 1.231 out en una corrida medida). Precios verificados 2026-08-13 en la
    # tarifa pública de xAI. OJO: grok-4.5 tiene tramo LARGO ($4/$12 por encima de 200K de prompt) y
    # cached input a $0.50 — ninguno de los dos se modela aquí todavía, ver _rate_for.
    "grok-4.5": (2.00, 6.00),
    "grok-4.6": (2.00, 6.00),
    "grok-4.3": (3.00, 15.00),
    # Los del relay de los workers, también por modelo (la fila por base_url se queda de respaldo).
    "glm-5.2": (1.40, 4.40),
    "kimi-k2.6": (0.95, 4.00),
    "deepseek-v4-pro": (0.28, 0.42),
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
    """Energy metering exists for real cloud accounts (ZAELAR_USER_ID set, 2026-08-05). Routes
    through the single-purpose accessor so neither this module nor its callers need to know the
    shape of the gate."""
    from nucleo import cloud_account
    return cloud_account.is_cloud_account()


def _is_local_endpoint(base_url: str) -> bool:
    u = (base_url or "").lower()
    return "11434" in u or "localhost" in u or "127.0.0.1" in u


def _rate_for(base_url: str, model: str | None) -> tuple[float, float]:
    """Never returns None — local endpoints are filtered by the caller BEFORE this is reached
    (llm_cost_to_energy). Every real cloud endpoint gets a rate: exact if we have one, a per-model
    AIMLAPI rate if the broker is AIMLAPI, else the fallback (logged once)."""
    u = (base_url or "").lower()
    m = (model or "").lower()
    # EL MODELO MANDA (2026-08-13). Antes esta tabla solo se consultaba si el endpoint era AIMLAPI, y por
    # eso un worker de Grok Build —que no reporta base_url, porque su CLI habla con xAI directamente— caía
    # al fallback y se cobraba a la mitad. El precio es del MODELO; el endpoint solo es dónde se sirve.
    # Se ordena por longitud del patrón para que el más específico gane («grok-4.5» antes que «grok-4»).
    if m:
        for needle in sorted(_MODEL_RATES, key=len, reverse=True):
            if needle in m:
                return _MODEL_RATES[needle]
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
    await _post_usage_cloud_account(energy, kind, meta)


async def _post_usage_cloud_account(energy: float, kind: str, meta: dict | None = None) -> None:
    """Reports to the control-plane's PERSISTENT per-user Energy ledger (cloud/control-plane's
    POST /usage). The control-plane writes this SAME call into zaelar_user_events too (INI-019
    addenda, "Cambio A") — so `meta` (model/base_url ONLY — never content) doubles as the per-user
    activity timeline the backoffice reads. CONTROL_PLANE_URL/CONTROL_PLANE_SERVICE_TOKEN are
    injected by the provisioner at Machine creation
    (cloud/provisioner/src/machineConfig.js::accountMachineConfig) — guarded-until-configured:
    missing either → no-op, never raises.

    2026-08-09: the response already carries the account's new `balance` (control-plane's own
    /usage handler has always returned it) — this used to be discarded. Reading it here is the WHOLE
    gate: no separate balance-check endpoint was needed, just stop throwing the answer away. A
    depleted balance (nucleo/account_limits.should_close) requests the session close, fire-and-forget
    (nucleo/account_limits.py) — a failed close request never breaks the turn that triggered it."""
    from nucleo import account_limits, cloud_account

    control_plane_url = (os.getenv("CONTROL_PLANE_URL") or "").strip()
    user_id = cloud_account.my_user_id()
    if not control_plane_url or not user_id or energy <= 0:
        return
    service_token = (os.getenv("CONTROL_PLANE_SERVICE_TOKEN") or "").strip()
    headers = {"X-Service-Token": service_token} if service_token else {}
    payload = {"user_id": user_id, "energy": energy, "kind": kind}
    # SESIÓN DE TRABAJO (2026-08-09): el reporte dice a qué sesión pertenece el consumo, para que quien lo reciba
    # pueda agruparlo sin abrir otra vía. Cuesta un dict lookup y no manda NADA de contenido. Los EVENTOS no
    # viajan por aquí ni por ningún sitio: se quedan en esta máquina.
    try:
        from observability import identity as _ident
        payload["session_id"] = _ident.session_id()
    except Exception:
        pass
    if meta:
        payload["meta"] = meta
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.post(
                control_plane_url.rstrip("/") + _USAGE_ENDPOINT_PATH,
                json=payload,
                headers=headers,
            )
        balance = (resp.json() or {}).get("balance") if resp.status_code < 400 else None
        if account_limits.should_close(balance):
            account_limits.request_close("balance_depleted")
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
