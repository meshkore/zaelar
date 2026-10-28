#
# ENERGY METERING — real usage → real cost → "Energy" units.
#
# Converts ACTUAL provider usage (LLM tokens, TTS characters, STT audio-seconds, Brain Worker tokens,
# transport participant-seconds) into a cost estimate, then into Energy units, and reports it
# fire-and-forget to a usage ledger endpoint (see _post_usage_cloud_account).
#
# SCOPE: only active when `ZAELAR_USER_ID` is set (nucleo/cloud_account.py). A self-host install
# doesn't set it → enabled() False → zero cost, zero network calls.
#
# Rates are resolved per MODEL first (a single broker base_url can serve dozens of differently-priced
# models), then per base_url, then a non-None FALLBACK rate for any (base_url, model) this table doesn't
# know — so an unlisted provider degrades to "probably over-meters a little" instead of "silently free".
# Brain Workers (nucleo/workers/, Claude Code CLI) are metered too (report_worker_usage), from the
# stream-json "result" usage.
#
# NUMBERS BELOW ARE DEFAULTS:
#   - Per-provider/per-model $/token rates: public provider pricing at the time of writing — re-verify
#     against each provider's pricing page periodically.
#   - EUR_PER_ENERGY_UNIT and MARGIN_MULTIPLIER are defaults; a deployment overrides them via
#     ENERGY_EUR_PER_UNIT / ENERGY_MARGIN_MULTIPLIER.
#   - The FALLBACK rate for an unmapped (base_url, model) deliberately over-meters (and is logged
#     loudly so a real rate gets added) rather than ever metering as free.
#
import functools
import os
import time

import httpx
from loguru import logger

from nucleo import energy_tariffs

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
    # ── DeepSeek DIRECT (the table's titular for everything that is not the Brain Worker) ──────────
    # Prices read from api-docs.deepseek.com/quick_start/pricing on 2026-09-25, PEAK tier.
    #
    # PEAK, always, on purpose: DeepSeek bills peak/off-peak with off-peak at HALF price. This table is
    # static, so billing the peak rate over-charges by at most 2x during the cheap window and never
    # under-charges — the same stance as `_FALLBACK_RATE_USD`. (This closes the ⚠️ left open in
    # `_CACHED_READ_RATES_USD` below: the pricing page now publishes both tiers.)
    #
    # `deepseek-flash` IS DeepSeek-V4.1-Flash — the model `config/models.default.json` names as titular of
    # voice_brain, memory_writer, memory_rem, triage and susurro, i.e. the hottest path in the product.
    # It had NO row (the table only knew the older broker name `deepseek-v4-flash`), so every voice turn
    # on a cloud account metered at the punitive catch-all (1.00, 5.00) — 3.3x input and 4.2x output of
    # its real price. Measured 2026-09-25 by calling `_rate_for()` with the model the table actually names.
    "deepseek-flash": (0.30, 1.20),
    # brief_composer's titular. It DID have a row and the row was too CHEAP — (0.28, 0.42) against a real
    # (1.32, 3.96), so this one was under-metering by 4.7x input / 9.4x output, which loses real money
    # instead of over-charging. Both errors come from the same cause: a price written once and never
    # re-read against the provider's page.
    "deepseek-v4-pro": (1.32, 3.96),
    # The broker route (AIMLAPI `deepseek/deepseek-v4-flash`), kept because older configs may still use
    # it. Its price is the broker's, not DeepSeek's, so it does NOT move with the rows above.
    "deepseek-v4-flash": (0.14, 0.28),
    # The memory's EMBEDDINGS (V2-501, 2026-08-30). They have no output tokens at all — an embedding is not
    # generated text — so the output rate is a real zero and not a placeholder. A row is needed even though the
    # amounts are tiny: without one they fall to the punitive catch-all, which for the cheapest model on the
    # whole list means over-charging by ~100x. And they are NOT rare: this runs on every insert AND every
    # query, so a wrong rate here is a wrong rate on the hottest path the memory has.
    "text-embedding-3-small": (0.02, 0.0),
    "text-embedding-3-large": (0.13, 0.0),
    "mistral-embed": (0.10, 0.0),
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
    # tarifa pública de xAI. El input CACHEADO sí se modela (ver `_CACHED_READ_RATES_USD`, medido a
    # $0.30/1M). Lo que NO se modela todavía es el tramo LARGO de grok-4.5 ($4/$12 por encima de 200K de
    # prompt): con 500K de contexto una sesión larga puede cruzarlo y ahí volveríamos a cobrar de menos.
    "grok-4.5": (2.00, 6.00),
    "grok-4.6": (2.00, 6.00),
    "grok-4.3": (3.00, 15.00),
    # Los del relay de los workers, también por modelo (la fila por base_url se queda de respaldo).
    # `glm-5.3` es HOY el titular del Brain Worker en la tabla. Acertaba de rebote por la fila de
    # `api.z.ai`, no por su nombre: un worker servido por otro endpoint (o un relevo) habría caído al
    # catch-all. Precio verificado en docs.z.ai/guides/overview/pricing el 2026-09-25 — idéntico al de
    # 5.2. This is Z.AI's pay-per-token price.
    "glm-5.3": (1.40, 4.40),
    "glm-5.2": (1.40, 4.40),
    "kimi-k2.6": (0.95, 4.00),
    # (`deepseek-v4-pro` vivía aquí con (0.28, 0.42) y AQUÍ GANABA: una clave repetida en un literal de
    # dict se queda con el ÚLTIMO valor, así que la fila de arriba —la buena— era letra muerta. El precio
    # correcto, verificado, está en el bloque de DeepSeek al principio de la tabla.)
}

# Applied when neither table above has a row for the (base_url, model) actually used. Deliberately NOT
# the cheapest rate seen (that would risk under-charging real usage on an unlisted provider) — see
# module docstring. Logged loudly (once per distinct unmapped key) so an operator notices and adds a
# real rate instead of this staying the permanent answer.
_FALLBACK_RATE_USD: tuple[float, float] = (1.00, 5.00)
_warned_unmapped: set[str] = set()

# Defaults; a deployment overrides them via the env vars — single constants, easy to tune without
# touching the calculation logic below.
EUR_PER_ENERGY_UNIT = float(os.getenv("ENERGY_EUR_PER_UNIT", "0.01"))   # default; ENERGY_EUR_PER_UNIT overrides
MARGIN_MULTIPLIER = float(os.getenv("ENERGY_MARGIN_MULTIPLIER", "4.0"))  # default; ENERGY_MARGIN_MULTIPLIER overrides


def enabled() -> bool:
    """Energy metering is active only when ZAELAR_USER_ID is set. Routes
    through the single-purpose accessor so neither this module nor its callers need to know the
    shape of the gate."""
    from nucleo import cloud_account
    return cloud_account.is_cloud_account()


def _is_local_endpoint(base_url: str) -> bool:
    u = (base_url or "").lower()
    return "11434" in u or "localhost" in u or "127.0.0.1" in u


# Token assumption for a PAID call whose provider reported no usage at all. 2026-08-13: the fallback
# RATE (above) covered "we don't know the price"; nothing covered "we don't know the volume", and that
# second hole was worse — a rate is a number that gets looked up, a missing volume multiplies to
# exactly zero and reports success. Every provider that streams without `stream_options:
# {include_usage: true}`, and every SDK response read for its text only, landed there.
#
# So: same never-silently-free stance as _FALLBACK_RATE_USD, one level up. A call with no usage is
# charged this floor and logged loudly, which is deliberately the WRONG number — it exists to be
# noticed and fixed at the call site (ask the provider for usage), not to be a permanent estimate.
# Marked `estimated` in the report so reconciliation can find every one of them later.
_MISSING_USAGE_FLOOR = (
    int(os.getenv("ENERGY_MISSING_USAGE_IN_TOKENS", "2000")),
    int(os.getenv("ENERGY_MISSING_USAGE_OUT_TOKENS", "500")),
)
_warned_missing_usage: set[str] = set()


def _resolve_tokens(
    base_url: str, model: str | None, prompt_tokens: int | None, completion_tokens: int | None
) -> tuple[int, int, bool]:
    """`(prompt, completion, estimated)`. Both counters absent on a PAID endpoint → the floor, warned
    once per (endpoint, model). A call that reports 0/0 explicitly is NOT this case: zero is an
    answer, `None` is a missing answer, and conflating them is what made this hole invisible."""
    if prompt_tokens is None and completion_tokens is None and not _is_local_endpoint(base_url):
        key = f"{(base_url or '').lower()}::{(model or '').lower()}"
        if key not in _warned_missing_usage:
            _warned_missing_usage.add(key)
            logger.warning(
                f"energy_meter: NO usage reported for base_url={base_url!r} model={model!r} — charging "
                f"the floor {_MISSING_USAGE_FLOOR} tokens so it is not free. FIX THE CALL SITE: ask the "
                f"provider for usage (streaming needs stream_options={{'include_usage': True}})."
            )
        return _MISSING_USAGE_FLOOR[0], _MISSING_USAGE_FLOOR[1], True
    return prompt_tokens or 0, completion_tokens or 0, False


def _broker_markup(base_url: str, model: str) -> float:
    """The BROKER's cut, as a multiplier on the native model rate.

    Every row in the tables above is the price the MODEL'S OWN provider charges. A call routed through a
    reseller (AIMLAPI) pays that reseller's markup on top, which depends on the model; this returns that
    multiplier (1.0 for a direct endpoint). An unknown model on the broker takes the highest observed markup,
    for the same never-silently-cheap reason as `_FALLBACK_RATE_USD`.
    """
    if "aimlapi" not in (base_url or "").lower():
        return 1.0
    for needle, mult in sorted(_BROKER_MARKUP_AIMLAPI.items(), key=lambda kv: -len(kv[0])):
        if needle in model:
            return mult
    return _BROKER_MARKUP_DEFAULT


_BROKER_MARKUP_AIMLAPI: dict[str, float] = {
    "deepseek-v4-flash": 1.30,      # 0.14 nativo → 0.182 por el broker
    "grok-4-fast": 1.05,            # 0.20 → 0.21
    "gemini-2.5-flash": 1.00,       # 0.30 → 0.30 (sin margen)
}
_BROKER_MARKUP_DEFAULT = 1.30       # el peor margen observado; over-charge antes que under-charge


def _rate_for(base_url: str, model: str | None) -> tuple[float, float]:
    """Never returns None — local endpoints are filtered by the caller BEFORE this is reached
    (llm_cost_to_energy). Every real cloud endpoint gets a rate: exact if we have one, a per-model
    AIMLAPI rate if the broker is AIMLAPI, else the fallback (logged once). The rate is the NATIVE
    provider's; if the call went through a broker, its margin is applied on top (`_broker_markup`)."""
    u = (base_url or "").lower()
    m = (model or "").lower()
    mk = _broker_markup(u, m)
    # EL MODELO MANDA (2026-08-13). Antes esta tabla solo se consultaba si el endpoint era AIMLAPI, y por
    # eso un worker de Grok Build —que no reporta base_url, porque su CLI habla con xAI directamente— caía
    # al fallback y se cobraba a la mitad. El precio es del MODELO; el endpoint solo es dónde se sirve.
    # Se ordena por longitud del patrón para que el más específico gane («grok-4.5» antes que «grok-4»).
    if m:
        for needle in sorted(_MODEL_RATES, key=len, reverse=True):
            if needle in m:
                i, o = _MODEL_RATES[needle]
                return i * mk, o * mk
    for needle, rates in _RATES_PER_1M_TOKENS_USD.items():
        if needle in u:
            return rates[0] * mk, rates[1] * mk
    key = f"{u}::{m}"
    if key not in _warned_unmapped:
        _warned_unmapped.add(key)
        logger.warning(
            f"energy_meter: no rate row for base_url={base_url!r} model={model!r} — charging the "
            f"fallback rate {_FALLBACK_RATE_USD} $/1M tokens. Add a real rate to energy_meter.py."
        )
    # Deliberately NOT marked up: the fallback is already a punitive catch-all, and stacking the broker's
    # margin on top would compound two paddings that each exist for the same "never under-charge" reason.
    return _FALLBACK_RATE_USD


# $ per 1M CACHED-READ input tokens, by model. A cached read is a real billed line and it is NOT
# included in `input_tokens` (Anthropic-shaped usage reports the three counters separately), so ignoring
# it undercharges — badly, because in a long agentic session the same prompt prefix is re-read on every
# turn and cached reads end up SEVERAL TIMES the fresh input. Measured on a real worker run: 211k cached
# reads against 74k fresh input, i.e. 29% of the bill missing.
#
# The grok rate is DERIVED FROM MEASUREMENT, not from a pricing page: two independent calls of very
# different sizes (384 and 62.720 cached tokens) both solve to exactly $0.30/1M against the cost xAI's own
# CLI reports, while the figure blogs quote ($0.50) does not fit either. GLM's is Z.AI's published
# cached-input price. Anything unmapped falls to a fraction of the input rate — the same
# never-silently-free stance as _FALLBACK_RATE_USD, logged once.
_CACHED_READ_RATES_USD: dict[str, float] = {
    "grok-4.5": 0.30,          # medido (ver arriba), no publicado
    "grok-4.6": 0.30,
    "glm-5.2": 0.26,           # precio público de Z.AI para input cacheado
    "glm-5.3": 0.26,           # 2026-08-14: se hereda el de 5.2 hasta que Z.AI publique el suyo (ver ⚠️ abajo)
    # DeepSeek, CONFIRMADO el 2026-09-25 en su página de precios (cierra el ⚠️ que esta tabla llevaba
    # abierto desde el 2026-08-14, cuando el precio de cache-hit de la familia V4 no era público). Tarifa
    # PICO, como las filas de input/output: el valle es la mitad y facturar el caro nunca cobra de menos.
    # El descuento real es ENORME —50× frente al input fresco—, así que la fracción del 25% que se venía
    # aplicando sobre-cobraba el hit unas 12×, y el hit es justo lo que más crece en una sesión larga.
    "deepseek-flash": 0.006,
    "deepseek-v4-pro": 0.044,
}
_CACHED_READ_FALLBACK_FRACTION = 0.25      # del rate de input, cuando no hay fila propia


def _cached_rate_for(base_url: str, model: str | None, in_rate: float) -> float:
    m = (model or "").lower()
    for needle in sorted(_CACHED_READ_RATES_USD, key=len, reverse=True):
        if needle in m:
            return _CACHED_READ_RATES_USD[needle]
    key = f"cache::{m}"
    if key not in _warned_unmapped:
        _warned_unmapped.add(key)
        logger.warning(
            f"energy_meter: no cached-read rate for model={model!r} — charging "
            f"{_CACHED_READ_FALLBACK_FRACTION:.0%} of the input rate. Measure it and add a real row."
        )
    return in_rate * _CACHED_READ_FALLBACK_FRACTION


def llm_cost_to_energy(
    *, base_url: str, model: str | None = None, prompt_tokens: int | None, completion_tokens: int | None,
    cached_tokens: int | None = None, cache_hit_tokens: int | None = None,
) -> float | None:
    """Pure. Returns Energy units for one LLM call, or None only for a local/free endpoint (Ollama —
    11434/localhost/127.0.0.1). Every real cloud endpoint always returns a value (exact rate if known,
    fallback otherwise) — see module docstring for why this changed from the original fail-open design.

    **The two cache counters have OPPOSITE arithmetic, and mixing them up bills twice.** They are separate
    parameters on purpose — a single `cached_tokens` would silently mean whichever the caller assumed:

      * `cached_tokens` — **Anthropic** shape (`cache_read_input_tokens`). A counter that sits OUTSIDE
        `prompt_tokens`, so its cost is ADDED.
      * `cache_hit_tokens` — **OpenAI/DeepSeek** shape (`prompt_cache_hit_tokens`). Already INSIDE
        `prompt_tokens` (verified against the live API: `prompt_tokens = hit + miss`), so it must be
        DISCOUNTED — re-priced down from the input rate, never added on top.

    Feeding DeepSeek's counter into `cached_tokens` would charge those tokens at the full input rate (inside
    `prompt_tokens`) AND again at the cache rate. Getting this wrong matters more here than anywhere else: the
    voice system prompt is ~10k CONSTANT tokens, so in a real conversation most of the input is a cache hit, and
    input dominates output 14:1 in this brain.

    Both default to 0, so a caller with no cache figure behaves exactly as before.
    """
    if _is_local_endpoint(base_url):
        return None
    in_rate, out_rate = _rate_for(base_url, model)
    pt = prompt_tokens or 0
    ct = completion_tokens or 0
    cached = cached_tokens or 0
    # Acotado a `pt`: un contador raro de un proveedor no puede producir un número de tokens frescos NEGATIVO
    # (que restaría de la factura — el sentido peligroso).
    hit = max(0, min(cache_hit_tokens or 0, pt))
    fresh = pt - hit
    raw_usd = (fresh / 1_000_000) * in_rate + (ct / 1_000_000) * out_rate
    if hit:
        raw_usd += (hit / 1_000_000) * _cached_rate_for(base_url, model, in_rate)
    if cached:
        raw_usd += (cached / 1_000_000) * _cached_rate_for(base_url, model, in_rate)
    retail_eur = raw_usd * MARGIN_MULTIPLIER  # treats USD≈EUR for simplicity — fine at these magnitudes
    return retail_eur / EUR_PER_ENERGY_UNIT


# VOICE RATES live in `nucleo/energy_tariffs.py`, resolved PER PROVIDER from a tariff table that can be
# delivered with the usage lease. A flat constant here could not follow the provider actually running.


def tts_cost_to_energy(*, characters: int | None, provider: str) -> float:
    """Pure given the tariff table. Energy units for one TTS synthesis call.

    `provider` is REQUIRED and has no default on purpose: a default here would be a second place where
    a price silently stops matching what runs. Local backends never reach this (the caller filters
    them — see the metrics_collected hook in agent.py); one that did would hit the never-free catch-all.
    """
    chars = characters or 0
    raw_usd = (chars / 1000.0) * energy_tariffs.rate_for("tts", provider)
    retail_eur = raw_usd * MARGIN_MULTIPLIER
    return retail_eur / EUR_PER_ENERGY_UNIT


def stt_cost_to_energy(*, audio_seconds: float | None, provider: str) -> float:
    """Pure given the tariff table. Energy units for one STT transcription call (`audio_duration`
    from LiveKit's STTMetrics). Same required-`provider` contract as `tts_cost_to_energy`."""
    secs = audio_seconds or 0.0
    raw_usd = (secs / 60.0) * energy_tariffs.rate_for("stt", provider)
    retail_eur = raw_usd * MARGIN_MULTIPLIER
    return retail_eur / EUR_PER_ENERGY_UNIT


def transport_cost_to_energy(*, participant_seconds: float | None, provider: str = "livekit") -> float:
    """Pure given the tariff table. Energy for real-time transport, billed per PARTICIPANT-minute.

    A voice session has two participants (user + agent), so the caller passes the summed
    participant-seconds — putting that multiplication here would hide it from whoever later reads a
    bill and wonders why it is double the wall-clock."""
    secs = participant_seconds or 0.0
    raw_usd = (secs / 60.0) * energy_tariffs.rate_for("transport", provider)
    retail_eur = raw_usd * MARGIN_MULTIPLIER
    return retail_eur / EUR_PER_ENERGY_UNIT


# $ per SEARCH REQUEST — this family is priced per call, not per token, so it needs its own table
# rather than a row in the LLM one. Added 2026-08-13: web search had no rate at all, which meant a
# paid search key would have billed at zero the way the FlashBrain did before 2026-08-05.
#
# `""` is the deliberate catch-all (same never-silently-free stance as _FALLBACK_RATE_USD). Free
# providers are NOT in this table and are NOT charged — they are filtered by the caller, because
# "free" is a fact about the provider, not a rate of zero to be looked up. Source: public pricing,
# 2026-08-13 — RE-VERIFY, and note these are entry-tier rates that volume discounts move.
# The rates live BESIDE the providers they price (V2-782): `search/providers/__init__.py::USD_PER_REQUEST`, each with
# its source and date. Only the catch-all row is this module's: an unmapped paid provider bills at the most expensive
# known rate, and is logged once.
from search.providers import USD_PER_REQUEST as _SEARCH_RATES  # noqa: E402 — a declaration table, no engine imports
_SEARCH_USD_PER_REQUEST: dict[str, float] = {**_SEARCH_RATES, "": 0.008}
_warned_search = set()


def search_cost_to_energy(*, provider: str) -> float:
    """Pure. Energy units for ONE paid search request. The caller decides what is paid: a free
    provider must never reach here (see `websearch`)."""
    p = (provider or "").lower()
    if p not in _SEARCH_USD_PER_REQUEST and p not in _warned_search:
        _warned_search.add(p)
        logger.warning(
            f"energy_meter: no search rate for provider={provider!r} — charging the catch-all "
            f"{_SEARCH_USD_PER_REQUEST['']} $/request. Add a real rate to energy_meter.py."
        )
    raw_usd = _SEARCH_USD_PER_REQUEST.get(p, _SEARCH_USD_PER_REQUEST[""])
    return (raw_usd * MARGIN_MULTIPLIER) / EUR_PER_ENERGY_UNIT


# --- reporting: fire-and-forget POST to the right ledger, never blocks the turn/worker ---

_USAGE_ENDPOINT_PATH = "/usage"


async def _post_usage(energy: float, kind: str, meta: dict | None = None) -> None:
    await _post_usage_cloud_account(energy, kind, meta)


async def _post_usage_cloud_account(energy: float, kind: str, meta: dict | None = None) -> None:
    """Reports usage to the ledger at CONTROL_PLANE_URL (POST /usage). `meta` carries model/base_url
    only — never content. Missing CONTROL_PLANE_URL or a user id → no-op, never raises.

    The response carries the account's new `balance`; a depleted balance
    (nucleo/account_limits.should_close) requests the session close, fire-and-forget — a failed close
    request never breaks the turn that triggered it."""
    from nucleo import account_limits, cloud_account

    control_plane_url = (os.getenv("CONTROL_PLANE_URL") or "").strip()
    user_id = cloud_account.my_user_id()
    if not control_plane_url or not user_id or energy <= 0:
        return
    # DOBLE COBRO (2026-08-13, T303). Con egress mediado, quien hizo la llamada de verdad ya la apuntó
    # en el ledger con los tokens que VIO ÉL — mejor dato que esta estimación. Reportarla otra vez
    # desde aquí cobraría dos veces el mismo turno. El descuento del arriendo local NO pasa por aquí
    # (va en `_fire_and_forget`, antes), así que el techo de seguridad sigue funcionando igual.
    from nucleo import llm_egress
    # Paid search joined on 2026-10-23, when its three indexes started going out through egress too. Voice (`tts`,
    # `stt`, `transport`) is still metered here: it does not go through egress. The decision model joined on
    # 2026-10-24, when its trips started going out through egress (billed there per trip).
    if kind in ("llm", "worker", "search", "decision") and llm_egress.bills_upstream():
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
        note_balance(balance)
        account_limits.on_balance(balance)        # depleted → close the session; back above zero → end the notice
    except Exception as e:  # noqa: BLE001
        logger.warning(f"energy_meter: cloud-account usage report failed (non-fatal): {e}")


# --- EL SALDO QUE EL OPERADOR VE (2026-08-13) --------------------------------------------------------------
#
# El saldo YA llegaba en la respuesta de cada reporte y solo se usaba para decidir el corte. Aquí se conserva,
# porque un saldo que solo sirve para apagarte es la peor forma de contarlo: el operador se enteró de que se le
# había agotado la energía por un cartel, sin haber visto nunca cuánta le quedaba. Es el mismo criterio que
# [[feedback_visible_state_over_silent_state]] — un estado que puede dejarte tirado tiene que VERSE antes.
#
# `capacity` = de cuánto se partía, para poder dibujar una PILA (cuánto queda de cuánto había) y no un número
# suelto. No se puede preguntar «cuánto compró»: solo se ve el saldo. Pero una recarga es, por definición, un
# saldo que SUBE — así que un salto hacia arriba fija la capacidad nueva y un descenso no la toca.
#
# Vive en `sys_kv`, NUNCA en el estado raíz: `memory.api.compose_state` vuelca cada escalar del estado al prompt
# como «Clave: valor.», así que un saldo ahí viajaría en todos los turnos de voz (misma razón que en
# `nucleo/rehydrate.py`).
_KV_KEY = "energy:balance"
_state: dict = {"balance": None, "capacity": None, "at": 0.0, "src": "", "plan": None}
_loaded = False

# The server's event loop (V2-102), for the SAME cross-thread bridge problem `search/browser.py::set_loop`
# already solves — captured once, sync, from the lifespan.
_loop = None


def set_loop(loop) -> None:
    """Captures the server's loop so `_fire_and_forget` can still schedule its POST when called from a thread
    that has none of its own (`asyncio.to_thread`) — see `_fire_and_forget` for why this exists."""
    global _loop
    _loop = loop


def _load_once() -> None:
    global _loaded
    if _loaded:
        return
    _loaded = True
    try:
        from memory import api as memory
        d = memory.kv_get(_KV_KEY)          # kv_get/kv_set ya hacen el JSON: se guarda el dict tal cual
        if isinstance(d, dict):
            _state.update({"balance": d.get("balance"), "capacity": d.get("capacity"),
                           "at": float(d.get("at") or 0.0), "src": d.get("src") or "", "plan": d.get("plan")})
    except Exception:
        pass


def note_balance(balance) -> None:
    """Registra el saldo que acaba de decir el ledger. Nunca lanza: es contabilidad de PRESENTACIÓN,
    y un fallo aquí no puede tocar el turno ni el worker que la disparó."""
    try:
        if balance is None:
            return
        b = float(balance)
    except (TypeError, ValueError):
        return
    _load_once()
    prev = _state.get("balance")
    cap = _state.get("capacity")
    # Una RECARGA es un saldo que sube (o el primer saldo que vemos). Gastar no cambia de cuánto se partía.
    if cap is None or prev is None or b > float(prev):
        cap = b
    _state.update({"balance": b, "capacity": cap, "at": time.time(), "src": "report"})
    try:
        from memory import api as memory
        memory.kv_set(_KV_KEY, {"balance": b, "capacity": cap, "at": _state["at"], "src": "report"})
    except Exception:
        pass
    # EN VIVO: la pila baja mientras el agente trabaja, sin que el frontend pregunte. Un `emit` no bloquea.
    try:
        from voice.observer import emit
        emit("energy", "saldo", extra={"balance": b, "capacity": cap})
    except Exception:
        pass


def snapshot() -> dict:
    """Lo que el frontend necesita para pintar la pila. `known=False` = todavía no hemos visto ningún saldo (la
    cuenta no ha gastado nada desde que arrancó y nadie nos lo ha dicho): la pila se pinta apagada, no a cero —
    «no lo sé» y «se te acabó» no pueden verse igual."""
    _load_once()
    b, cap = _state.get("balance"), _state.get("capacity")
    if b is not None and _state.get("src") == "lease":
        # The account's balance when the lease was granted, minus what THIS Machine has spent of that lease since:
        # the gauge goes down live, with no network, exactly as the lease itself does.
        try:
            from nucleo import energy_lease
            b = max(0.0, float(b) - float(energy_lease._state.get("spent") or 0.0))
        except Exception as e:  # noqa: BLE001
            logger.debug(f"energy_meter: lease spend unreadable: {e!r}")
    return {"cloud": enabled(), "known": b is not None, "balance": b, "capacity": cap,
            "plan": _state.get("plan"), "at": _state.get("at") or 0.0}


def _reset_for_tests() -> None:
    global _loaded
    _state.update({"balance": None, "capacity": None, "at": 0.0, "src": "", "plan": None})
    _loaded = False


def _fire_and_forget(energy: float, kind: str, meta: dict | None = None) -> None:
    """Shared tail of every report_*_usage(): schedule the POST without ever blocking or raising
    into the caller. No running loop (e.g. a unit test calling this directly) → drop silently."""
    import asyncio

    # EL ARRIENDO SE DESCUENTA AQUÍ, ANTES y SIN RED (2026-08-13, ADR-0005). Es el mismo gesto que
    # reportar, pero no espera respuesta: el techo local es una resta en proceso. Va delante del
    # `create_task` a propósito — si no hay loop y el POST se descarta, el gasto ya ocurrió igual y el
    # contador tiene que saberlo. Un contador que solo cuenta cuando la red va bien no es un techo.
    try:
        from nucleo import energy_lease
        energy_lease.note_spend(energy)
    except Exception:  # noqa: BLE001
        pass

    _observe_charge(energy, kind, meta)

    try:
        asyncio.get_running_loop()
        asyncio.create_task(_post_usage(energy, kind, meta))
        return
    except RuntimeError:
        pass
    # No loop in THIS thread — the caller is inside `asyncio.to_thread` (V2-102: `nucleo/memllm.chat_sync` is
    # documented to run there, and every one of its callers metered through this path silently lost their
    # report — the local lease deduction above still happened, only the ledger POST vanished). Same
    # bridge `search/browser.py::set_loop`/`run_coroutine_threadsafe` already uses for the identical
    # problem. No loop captured yet (`set_loop` not called — e.g. a unit test) → drop, same as before.
    if _loop is not None:
        try:
            asyncio.run_coroutine_threadsafe(_post_usage(energy, kind, meta), _loop)
        except Exception:  # noqa: BLE001
            pass


def _observe_charge(energy: float, kind: str, meta: dict | None) -> None:
    """One observability event per charge, with everything known about it: the raw units the provider
    billed (tokens with their cache split, characters, seconds), the price applied (raw USD and margin) and
    whether the ledger takes this figure or the upstream egress meters it itself (`billed_by`). Prices get
    corrected against reality from these rows, so they carry the units, not just the result. The display
    text has no decimals; the data keeps them. Never raises."""
    try:
        from voice.observer import emit
        e = float(energy)
        extra = {"charge": kind, "energy": round(e, 4),
                 "raw_usd": round(e * EUR_PER_ENERGY_UNIT / MARGIN_MULTIPLIER, 8), "margin": MARGIN_MULTIPLIER}
        upstream = False
        if kind in ("llm", "worker", "search"):
            from nucleo import llm_egress
            upstream = llm_egress.bills_upstream()
        extra["billed_by"] = "egress" if upstream else "engine"
        for k, v in (meta or {}).items():
            extra.setdefault(k, v)
        shown = f"{round(e)}" if e >= 0.5 else "<1"
        what = (meta or {}).get("model") or (meta or {}).get("provider") or ""
        emit("energy", kind, text=f"−{shown} ⚡ {kind}{' · ' + str(what) if what else ''}", extra=extra)
    except Exception as e:  # noqa: BLE001 — observing a charge can never break the charge
        logger.debug(f"energy_meter: charge not observed ({kind}): {e!r}")


def _never_raises(fn):
    """Todas las puertas públicas del contador tragan sus propias excepciones.

    «Medir nunca puede tumbar la llamada que estaba midiendo» era ya la regla, pero vivía como un `try/except`
    COPIADO en cada llamante — once veces la misma línea, y un llamante nuevo que se olvidara convertía un fallo
    de contabilidad en una caída de producto. Es una propiedad del MÓDULO, así que se garantiza aquí y los
    llamantes se limitan a llamar (operador, 2026-08-15).

    Se registra en DEBUG, no en silencio: un contador que falla siempre y no lo dice es la forma cara de este
    fallo — medir de menos es indistinguible de funcionar bien (`test_energy_coverage.py`).
    """
    @functools.wraps(fn)
    def _wrapped(*a, **kw):
        try:
            return fn(*a, **kw)
        except Exception as e:  # noqa: BLE001
            logger.debug(f"energy_meter.{fn.__name__}: no pude medir ({type(e).__name__}: {e})")
            return None
    return _wrapped


@_never_raises
def report_llm_usage(
    *, base_url: str, model: str | None = None, prompt_tokens: int | None, completion_tokens: int | None,
    cache_hit_tokens: int | None = None,
) -> None:
    """Call from the LLM streaming call site's `finally` block, AFTER usage/estimate is resolved.
    Fire-and-forget (asyncio.create_task) — never awaited by the caller, never adds latency to the
    turn. No-op with zero cost if not a metered account (enabled() False) or no running event loop."""
    if not enabled():
        return
    pt, ct, estimated = _resolve_tokens(base_url, model, prompt_tokens, completion_tokens)
    # El hit de caché solo se descuenta si los tokens son REALES del proveedor. Con un estimado por chars no hay
    # forma de saber qué parte se cacheó, y aplicar el descuento sobre una cifra inventada sería rebajar la factura
    # con un dato que no existe — el sentido peligroso.
    energy = llm_cost_to_energy(base_url=base_url, model=model, prompt_tokens=pt, completion_tokens=ct,
                                cache_hit_tokens=None if estimated else cache_hit_tokens)
    if energy is None:
        return
    meta = {"model": model, "base_url": base_url, "prompt_tokens": pt, "completion_tokens": ct}
    if cache_hit_tokens and not estimated:
        meta["cache_hit_tokens"] = int(cache_hit_tokens)
    if estimated:
        meta["estimated"] = True
    _fire_and_forget(energy, "llm", meta)


@_never_raises
def meter_openai_response(payload, *, base_url: str, model: str | None = None) -> None:
    """**LA PUERTA.** Hand it the provider's raw response and forget about billing.

    Decisión de arquitectura del operador (2026-08-15): *«el módulo de cobro tiene que ser un módulo totalmente
    separado, a modo de gateway, y que cuando haya llamadas a servicios que consumen dinero se pase por ahí»*.
    El módulo ya estaba separado; lo que NO estaba era la puerta. Cada uno de los 11 llamantes repetía el mismo
    bloque de ocho líneas —importar el contador, sacar `usage`, desempaquetar dos campos, tragarse la
    excepción— y esa copia-pega tenía un coste medible, no solo estético:

    - **Solo `fast_client` leía `prompt_cache_hit_tokens`.** Los otros diez llamantes facturaban el input
      cacheado a precio de input fresco, o sea sobre-cobrando (el lado seguro, pero mal). El conocimiento de
      QUÉ campos trae una respuesta pertenece al contador, no a cada llamante.
    - Un llamante nuevo copiaba la versión que tuviera delante, así que los arreglos no se propagaban: es
      exactamente el mecanismo por el que la cobertura se ha tenido que arreglar tres veces (2026-08-05,
      2026-08-13, 2026-08-15).

    Con esto, medir una llamada nueva es **una línea** y no hay nada que recordar. `payload` es el JSON tal cual
    lo devolvió el proveedor (dict) o cualquier objeto con `.usage`; los nombres son los de la familia
    OpenAI, que es la que hablan todos nuestros endpoints —incluidos los brokers y DeepSeek directo—.

    **Nunca lanza** (`@_never_raises`, como todas las puertas de este módulo): medir no puede tumbar la llamada
    que estaba midiendo. Ésa era la razón del `except` que había en los once sitios, y ahora vive en uno.
    """
    usage = payload.get("usage") if isinstance(payload, dict) else getattr(payload, "usage", None)
    if usage is not None and not isinstance(usage, dict):
        # Los SDK devuelven un objeto, no un dict (`resp.usage` de OpenAI). Se normaliza aquí para que el
        # llamante no tenga que saber si le tocó cliente HTTP crudo o SDK.
        usage = getattr(usage, "model_dump", getattr(usage, "dict", dict))() or {}
    usage = usage or {}
    report_llm_usage(
        base_url=base_url, model=model,
        prompt_tokens=usage.get("prompt_tokens"),
        completion_tokens=usage.get("completion_tokens"),
        # DENTRO de prompt_tokens (verificado: pt = hit + miss) → se DESCUENTA. Ver la nota sobre la
        # aritmética opuesta de los dos contadores de caché en `llm_cost_to_energy`.
        cache_hit_tokens=usage.get("prompt_cache_hit_tokens"),
    )


@_never_raises
def report_worker_usage(
    *, base_url: str, model: str | None = None, prompt_tokens: int | None, completion_tokens: int | None,
    cached_tokens: int | None = None,
) -> None:
    """Call from a Brain Worker session's completion (nucleo/workers/session.py::_finish), AFTER the
    stream-json "result" usage is known. Same rate table and fire-and-forget contract as
    report_llm_usage — a worker call IS an LLM call, just reached via the Claude Code CLI subprocess
    instead of an HTTP client. Deliberately does NOT use the CLI's own `total_cost_usd`: that figure is
    computed by the CLI against OFFICIAL Anthropic pricing, which is meaningless once the call was
    relayed to another provider (Z.AI/Moonshot, see nucleo/workers/providers.py) — pricing
    by the per-model table keeps worker Energy consistent with every other metered call."""
    if not enabled():
        return
    pt, ct, estimated = _resolve_tokens(base_url, model, prompt_tokens, completion_tokens)
    energy = llm_cost_to_energy(
        base_url=base_url, model=model, prompt_tokens=pt, completion_tokens=ct, cached_tokens=cached_tokens,
    )
    if energy is None:
        return
    meta = {"model": model, "base_url": base_url, "prompt_tokens": pt, "completion_tokens": ct}
    if cached_tokens:
        meta["cached_tokens"] = int(cached_tokens)
    if estimated:
        meta["estimated"] = True
    _fire_and_forget(energy, "worker", meta)


@_never_raises
def report_tts_usage(*, characters: int | None, provider: str) -> None:
    """Call from the TTSMetrics branch of agent.py's metrics_collected hook, AFTER the caller has
    already excluded local backends (kokoro_local — free, not metered). Same no-op/fire-and-forget
    contract as report_llm_usage.

    The RAW UNITS travel in `meta` alongside the Energy, deliberately: Energy is the price applied to
    them, and a price can be wrong. Without the units the ledger can only ever say what was
    charged, never what it should have been — so a tariff fixed later could not be applied backwards,
    and a bill could not be checked against the provider's own dashboard. Same reason report_llm_usage
    already sends {model, base_url}. No content, ever — a character COUNT, never the text."""
    if not enabled():
        return
    energy = tts_cost_to_energy(characters=characters, provider=provider)
    if energy <= 0:
        return
    _fire_and_forget(energy, "tts", {"provider": provider, "characters": int(characters or 0)})


@_never_raises
def report_stt_usage(*, audio_seconds: float | None, provider: str) -> None:
    """Call from the STTMetrics branch of agent.py's metrics_collected hook, AFTER the caller has
    already excluded local backends (whisper_local — free, not metered). Same no-op/fire-and-forget
    and raw-units-in-meta contract as report_tts_usage."""
    if not enabled():
        return
    energy = stt_cost_to_energy(audio_seconds=audio_seconds, provider=provider)
    if energy <= 0:
        return
    _fire_and_forget(energy, "stt",
                     {"provider": provider, "audio_seconds": round(float(audio_seconds or 0.0), 3)})


@_never_raises
def report_transport_usage(*, participant_seconds: float | None, provider: str = "livekit") -> None:
    """Call when a voice SESSION closes, with the summed participant-seconds. Per-session, not
    per-turn: transport is billed for the whole time the room is up, including the silences between
    turns, so metering it per turn would miss exactly the part nobody watches."""
    if not enabled():
        return
    energy = transport_cost_to_energy(participant_seconds=participant_seconds, provider=provider)
    if energy <= 0:
        return
    _fire_and_forget(energy, "transport",
                     {"provider": provider,
                      "participant_seconds": round(float(participant_seconds or 0.0), 1)})


# $ per ROUND TRIP for the decision model (Jev / TypeSafe System One, `nucleo/jev.py`). Priced per
# TRIP and not per question on purpose, because that is how it bills and how it is used: one call
# carries the whole turn's questions (1 question 800 ms, 100 questions 1041 ms — `nucleo/jev.py:16`).
#
# ⚠️ ESTIMATED, NOT PUBLISHED: $0.0005 is an estimate (one trip, 100 candidates, `nucleo/jev.py`), the
# same stance as grok's cached-read rate — this is the only rate here with no pricing page behind it.
_DECISION_USD_PER_REQUEST: dict[str, float] = {
    "typesafe": 0.0005,
    "": 0.0005,
}


def decision_cost_to_energy(*, provider: str = "typesafe") -> float:
    """Pure. Energy units for ONE round trip of the decision model."""
    raw_usd = _DECISION_USD_PER_REQUEST.get((provider or "").lower(), _DECISION_USD_PER_REQUEST[""])
    return (raw_usd * MARGIN_MULTIPLIER) / EUR_PER_ENERGY_UNIT


@_never_raises
def report_decision_usage(*, provider: str = "typesafe", questions: int = 1) -> None:
    """Call after a Jev round trip answered. It is the ONLY paid provider the meter did not know
    about: ~1.4 trips per voice turn. The rule of this module is that nothing paid is ever metered free.

    `questions` travels for the ledger's detail only: the price is the trip."""
    if not enabled():
        return
    _fire_and_forget(decision_cost_to_energy(provider=provider), "decision",
                     {"provider": provider, "questions": int(questions)})


@_never_raises
def report_search_usage(*, provider: str) -> None:
    """Call from a PAID web-search provider's call site, after it answered. Same no-op/fire-and-forget
    contract as report_llm_usage. The caller must not invoke this for a free provider (Google via our
    own Chromium, DuckDuckGo): what is free is a property of the provider, and passing it through a
    rate table would turn 'free' into a number somebody can get wrong later."""
    if not enabled():
        return
    _fire_and_forget(search_cost_to_energy(provider=provider), "search", {"provider": provider})
