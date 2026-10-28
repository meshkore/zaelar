# ENERGY METERING — the REPORTING DOORS (split from `meter.py`, refactor2710-10b) and their shared tail
# (`_fire_and_forget`). Names on `meter` are read through `_m.` at call time, so patches still govern them.
import functools

from loguru import logger



def _fire_and_forget(energy: float, kind: str, meta: dict | None = None) -> None:
    """Shared tail of every report_*_usage(): schedule the POST, never blocking or raising. No loop → drop."""
    import asyncio

    # The LEASE is debited HERE, first and with no network (2026-08-13, ADR-0005): even if the POST is dropped,
    # the spend happened. A ceiling that only counts when the network works is no ceiling.
    try:
        from nucleo.energy import lease as energy_lease
        energy_lease.note_spend(energy)
    except Exception:  # noqa: BLE001
        pass

    _m._observe_charge(energy, kind, meta)

    try:
        asyncio.get_running_loop()
        asyncio.create_task(_m._post_usage(energy, kind, meta))
        return
    except RuntimeError:
        pass
    # No loop in THIS thread (`asyncio.to_thread`, V2-102: `memllm.chat_sync` callers lost their ledger POST) →
    # bridge to the captured server loop; none captured (`set_loop` not called) → drop.
    if _m._loop is not None:
        try:
            asyncio.run_coroutine_threadsafe(_m._post_usage(energy, kind, meta), _m._loop)
        except Exception:  # noqa: BLE001
            pass


def _observe_charge(energy: float, kind: str, meta: dict | None) -> None:
    """One observability event per charge: the raw units, the price applied (raw USD, margin) and `billed_by`
    (engine or upstream egress) — prices are corrected against these rows. Never raises."""
    try:
        from voice.observer import emit
        e = float(energy)
        extra = {"charge": kind, "energy": round(e, 4),
                 "raw_usd": round(e * _m.EUR_PER_ENERGY_UNIT / _m.MARGIN_MULTIPLIER, 8), "margin": _m.MARGIN_MULTIPLIER}
        upstream = False
        if kind in ("llm", "worker", "search"):
            from nucleo.energy import egress as llm_egress
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
    """Every public door swallows its own exceptions: metering never breaks the call it meters (2026-08-15 —
    it used to be a try/except copied into eleven callers). Logged at DEBUG, never silent."""
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
    """Call once usage is resolved. Fire-and-forget, no latency; no-op without a metered account."""
    if not _m.enabled():
        return
    pt, ct, estimated = _m._resolve_tokens(base_url, model, prompt_tokens, completion_tokens)
    # The cache hit is discounted only from REAL provider tokens, never from an estimate.
    energy = _m.llm_cost_to_energy(base_url=base_url, model=model, prompt_tokens=pt, completion_tokens=ct,
                                cache_hit_tokens=None if estimated else cache_hit_tokens)
    if energy is None:
        return
    meta = {"model": model, "base_url": base_url, "prompt_tokens": pt, "completion_tokens": ct}
    if cache_hit_tokens and not estimated:
        meta["cache_hit_tokens"] = int(cache_hit_tokens)
    if estimated:
        meta["estimated"] = True
    _m._fire_and_forget(energy, "llm", meta)


@_never_raises
def meter_openai_response(payload, *, base_url: str, model: str | None = None) -> None:
    """**THE DOOR.** Hand it the provider's raw response (dict, or anything with `.usage`, OpenAI field names)
    and forget about billing (operator, 2026-08-15). Eleven callers once copied an eight-line block and only
    one read `prompt_cache_hit_tokens`: which fields a response carries belongs to the meter. Never raises."""
    usage = payload.get("usage") if isinstance(payload, dict) else getattr(payload, "usage", None)
    if usage is not None and not isinstance(usage, dict):
        # SDKs return an object (OpenAI `resp.usage`), not a dict: normalised here.
        usage = getattr(usage, "model_dump", getattr(usage, "dict", dict))() or {}
    usage = usage or {}
    _m.report_llm_usage(
        base_url=base_url, model=model,
        prompt_tokens=usage.get("prompt_tokens"),
        completion_tokens=usage.get("completion_tokens"),
        # INSIDE prompt_tokens (pt = hit + miss) → DISCOUNTED; see `llm_cost_to_energy`.
        cache_hit_tokens=usage.get("prompt_cache_hit_tokens"),
    )


@_never_raises
def report_worker_usage(
    *, base_url: str, model: str | None = None, prompt_tokens: int | None, completion_tokens: int | None,
    cached_tokens: int | None = None,
) -> None:
    """Call when a Brain Worker session ends (`workers/session.py::_finish`). Priced by the model table, NOT
    the CLI's `total_cost_usd` (Anthropic list prices, meaningless once relayed to Z.AI/Moonshot)."""
    if not _m.enabled():
        return
    pt, ct, estimated = _m._resolve_tokens(base_url, model, prompt_tokens, completion_tokens)
    energy = _m.llm_cost_to_energy(
        base_url=base_url, model=model, prompt_tokens=pt, completion_tokens=ct, cached_tokens=cached_tokens,
    )
    if energy is None:
        return
    meta = {"model": model, "base_url": base_url, "prompt_tokens": pt, "completion_tokens": ct}
    if cached_tokens:
        meta["cached_tokens"] = int(cached_tokens)
    if estimated:
        meta["estimated"] = True
    _m._fire_and_forget(energy, "worker", meta)


@_never_raises
def report_tts_usage(*, characters: int | None, provider: str) -> None:
    """Call from agent.py's TTSMetrics hook (local backends already excluded). The RAW UNITS travel in `meta`
    so a wrong price can be corrected backwards — a character COUNT, never the text."""
    if not _m.enabled():
        return
    energy = _m.tts_cost_to_energy(characters=characters, provider=provider)
    if energy <= 0:
        return
    _m._fire_and_forget(energy, "tts", {"provider": provider, "characters": int(characters or 0)})


@_never_raises
def report_stt_usage(*, audio_seconds: float | None, provider: str) -> None:
    """Call from agent.py's STTMetrics hook (local backends excluded). Same contract as report_tts_usage."""
    if not _m.enabled():
        return
    energy = _m.stt_cost_to_energy(audio_seconds=audio_seconds, provider=provider)
    if energy <= 0:
        return
    _m._fire_and_forget(energy, "stt",
                     {"provider": provider, "audio_seconds": round(float(audio_seconds or 0.0), 3)})


@_never_raises
def report_transport_usage(*, participant_seconds: float | None, provider: str = "livekit") -> None:
    """Call when a voice SESSION closes: transport bills the whole time the room is up, silences included."""
    if not _m.enabled():
        return
    energy = _m.transport_cost_to_energy(participant_seconds=participant_seconds, provider=provider)
    if energy <= 0:
        return
    _m._fire_and_forget(energy, "transport",
                     {"provider": provider,
                      "participant_seconds": round(float(participant_seconds or 0.0), 1)})


@_never_raises
def report_decision_usage(*, provider: str = "typesafe", questions: int = 1) -> None:
    """Call after a Jev round trip answered (~1.4 per voice turn). `questions` is detail; the price is the trip."""
    if not _m.enabled():
        return
    _m._fire_and_forget(_m.decision_cost_to_energy(provider=provider), "decision",
                     {"provider": provider, "questions": int(questions)})


@_never_raises
def report_search_usage(*, provider: str) -> None:
    """Call after a PAID search provider answered; never for a free one — "free" is not a rate to look up."""
    if not _m.enabled():
        return
    _m._fire_and_forget(_m.search_cost_to_energy(provider=provider), "search", {"provider": provider})


# Last, so either import order works: `_m` is only read at call time.
from nucleo.energy import meter as _m  # noqa: E402
