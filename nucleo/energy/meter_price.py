# ENERGY METERING — PRICING: usage → cost → Energy (split from `meter.py`, refactor2710-10b). Names on `meter`
# are read through `_m.` at call time, so patching `energy_meter.<name>` still governs these.
from loguru import logger



def _is_local_endpoint(base_url: str) -> bool:
    u = (base_url or "").lower()
    return "11434" in u or "localhost" in u or "127.0.0.1" in u


def _resolve_tokens(
    base_url: str, model: str | None, prompt_tokens: int | None, completion_tokens: int | None
) -> tuple[int, int, bool]:
    """`(prompt, completion, estimated)`. Both None on a PAID endpoint → the floor, warned once. 0/0 is an
    answer, `None` is a missing one."""
    if prompt_tokens is None and completion_tokens is None and not _m._is_local_endpoint(base_url):
        key = f"{(base_url or '').lower()}::{(model or '').lower()}"
        if key not in _m._warned_missing_usage:
            _m._warned_missing_usage.add(key)
            logger.warning(
                f"energy_meter: NO usage reported for base_url={base_url!r} model={model!r} — charging "
                f"the floor {_m._MISSING_USAGE_FLOOR} tokens so it is not free. FIX THE CALL SITE: ask the "
                f"provider for usage (streaming needs stream_options={{'include_usage': True}})."
            )
        return _m._MISSING_USAGE_FLOOR[0], _m._MISSING_USAGE_FLOOR[1], True
    return prompt_tokens or 0, completion_tokens or 0, False


def _broker_markup(base_url: str, model: str) -> float:
    """The reseller's (AIMLAPI) markup on the native model rate; 1.0 direct, the highest observed if unknown."""
    if "aimlapi" not in (base_url or "").lower():
        return 1.0
    for needle, mult in sorted(_m._BROKER_MARKUP_AIMLAPI.items(), key=lambda kv: -len(kv[0])):
        if needle in model:
            return mult
    return _m._BROKER_MARKUP_DEFAULT


def _rate_for(base_url: str, model: str | None) -> tuple[float, float]:
    """Never None (local endpoints are filtered earlier): model row, else base_url row, else the fallback
    (logged once). Native rates, times the broker markup when routed through one."""
    u = (base_url or "").lower()
    m = (model or "").lower()
    mk = _m._broker_markup(u, m)
    # THE MODEL DECIDES (2026-08-13); longest pattern first so the most specific wins («grok-4.5» over «grok-4»).
    if m:
        for needle in sorted(_m._MODEL_RATES, key=len, reverse=True):
            if needle in m:
                i, o = _m._MODEL_RATES[needle]
                return i * mk, o * mk
    for needle, rates in _m._RATES_PER_1M_TOKENS_USD.items():
        if needle in u:
            return rates[0] * mk, rates[1] * mk
    key = f"{u}::{m}"
    if key not in _m._warned_unmapped:
        _m._warned_unmapped.add(key)
        logger.warning(
            f"energy_meter: no rate row for base_url={base_url!r} model={model!r} — charging the "
            f"fallback rate {_m._FALLBACK_RATE_USD} $/1M tokens. Add a real rate to energy_meter.py."
        )
    # NOT marked up: the fallback is already punitive; stacking the broker margin would pad twice.
    return _m._FALLBACK_RATE_USD


def _cached_rate_for(base_url: str, model: str | None, in_rate: float) -> float:
    m = (model or "").lower()
    for needle in sorted(_m._CACHED_READ_RATES_USD, key=len, reverse=True):
        if needle in m:
            return _m._CACHED_READ_RATES_USD[needle]
    key = f"cache::{m}"
    if key not in _m._warned_unmapped:
        _m._warned_unmapped.add(key)
        logger.warning(
            f"energy_meter: no cached-read rate for model={model!r} — charging "
            f"{_m._CACHED_READ_FALLBACK_FRACTION:.0%} of the input rate. Measure it and add a real row."
        )
    return in_rate * _m._CACHED_READ_FALLBACK_FRACTION


def llm_cost_to_energy(
    *, base_url: str, model: str | None = None, prompt_tokens: int | None, completion_tokens: int | None,
    cached_tokens: int | None = None, cache_hit_tokens: int | None = None,
) -> float | None:
    """Pure. Energy for one LLM call; None only for a local/free endpoint (11434/localhost/127.0.0.1).

    **The two cache counters have OPPOSITE arithmetic; mixing them bills twice:**
      * `cached_tokens` — Anthropic `cache_read_input_tokens`, OUTSIDE `prompt_tokens` → ADDED.
      * `cache_hit_tokens` — OpenAI/DeepSeek `prompt_cache_hit_tokens`, INSIDE `prompt_tokens` (verified live:
        `prompt_tokens = hit + miss`) → DISCOUNTED. Most voice input (~10k constant prompt) is a hit.
    """
    if _m._is_local_endpoint(base_url):
        return None
    in_rate, out_rate = _m._rate_for(base_url, model)
    pt = prompt_tokens or 0
    ct = completion_tokens or 0
    cached = cached_tokens or 0
    # Clamped to `pt`: an odd counter can never make fresh tokens NEGATIVE (that would lower the bill).
    hit = max(0, min(cache_hit_tokens or 0, pt))
    fresh = pt - hit
    raw_usd = (fresh / 1_000_000) * in_rate + (ct / 1_000_000) * out_rate
    if hit:
        raw_usd += (hit / 1_000_000) * _m._cached_rate_for(base_url, model, in_rate)
    if cached:
        raw_usd += (cached / 1_000_000) * _m._cached_rate_for(base_url, model, in_rate)
    retail_eur = raw_usd * _m.MARGIN_MULTIPLIER  # treats USD≈EUR for simplicity — fine at these magnitudes
    return retail_eur / _m.EUR_PER_ENERGY_UNIT


# VOICE RATES are per provider in `nucleo/energy/tariffs.py` (the table can arrive with the lease).


def tts_cost_to_energy(*, characters: int | None, provider: str) -> float:
    """Pure given the tariff table. Energy for one TTS call. `provider` is REQUIRED: a default would be a
    second place where a price silently stops matching what runs. Local backends are filtered by the caller."""
    chars = characters or 0
    raw_usd = (chars / 1000.0) * _m.energy_tariffs.rate_for("tts", provider)
    retail_eur = raw_usd * _m.MARGIN_MULTIPLIER
    return retail_eur / _m.EUR_PER_ENERGY_UNIT


def stt_cost_to_energy(*, audio_seconds: float | None, provider: str) -> float:
    """Pure given the tariff table. Energy units for one STT transcription call (`audio_duration`
    from LiveKit's STTMetrics). Same required-`provider` contract as `tts_cost_to_energy`."""
    secs = audio_seconds or 0.0
    raw_usd = (secs / 60.0) * _m.energy_tariffs.rate_for("stt", provider)
    retail_eur = raw_usd * _m.MARGIN_MULTIPLIER
    return retail_eur / _m.EUR_PER_ENERGY_UNIT


def transport_cost_to_energy(*, participant_seconds: float | None, provider: str = "livekit") -> float:
    """Pure given the tariff table. Transport, billed per PARTICIPANT-minute: the caller passes the summed
    participant-seconds (user + agent), so a bill at twice the wall-clock is explained where it is called."""
    secs = participant_seconds or 0.0
    raw_usd = (secs / 60.0) * _m.energy_tariffs.rate_for("transport", provider)
    retail_eur = raw_usd * _m.MARGIN_MULTIPLIER
    return retail_eur / _m.EUR_PER_ENERGY_UNIT


def search_cost_to_energy(*, provider: str) -> float:
    """Pure. Energy for ONE paid search request; a free provider never reaches here (the caller filters)."""
    p = (provider or "").lower()
    if p not in _m._SEARCH_USD_PER_REQUEST and p not in _m._warned_search:
        _m._warned_search.add(p)
        logger.warning(
            f"energy_meter: no search rate for provider={provider!r} — charging the catch-all "
            f"{_m._SEARCH_USD_PER_REQUEST['']} $/request. Add a real rate to energy_meter.py."
        )
    raw_usd = _m._SEARCH_USD_PER_REQUEST.get(p, _m._SEARCH_USD_PER_REQUEST[""])
    return (raw_usd * _m.MARGIN_MULTIPLIER) / _m.EUR_PER_ENERGY_UNIT


def decision_cost_to_energy(*, provider: str = "typesafe") -> float:
    """Pure. Energy units for ONE round trip of the decision model."""
    raw_usd = _m._DECISION_USD_PER_REQUEST.get((provider or "").lower(), _m._DECISION_USD_PER_REQUEST[""])
    return (raw_usd * _m.MARGIN_MULTIPLIER) / _m.EUR_PER_ENERGY_UNIT


# Last, so either import order works: `_m` is only read at call time.
from nucleo.energy import meter as _m  # noqa: E402
