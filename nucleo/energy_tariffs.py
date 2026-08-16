#
# ENERGY TARIFFS — the prices Energy is computed from, authored CENTRALLY and cached locally.
#
# WHY THIS MODULE EXISTS. Every rate used to be a constant compiled into the engine, so changing a
# price meant a release that had to reach every tenant Machine — and a release does NOT reach them
# automatically (a `flyctl deploy` only updates the process-group machine). The prices therefore
# drifted from reality in silence, which is the exact failure this codebase has now paid for three
# times: the LLM table that didn't cover the broker and metered 100% of voice traffic at zero, the
# master's hand-written provider map, and the STT rate that billed Deepgram while Voxtral ran.
#
# So the AUTHORITY for prices moves to the control-plane (the operator edits them in the backoffice)
# and this module is the engine's side of that: it takes whatever the cloud last told us, keeps it in
# `sys_kv`, and answers a rate lookup from it.
#
# WHAT THIS MODULE MUST NOT DO — and the constraint that shapes the whole design: it must NEVER make
# a network call to answer a price. The energy lease (ADR-0005) exists precisely so a Machine spends
# against a LOCAL counter with zero network in the steady state; if pricing needed a round trip, every
# metered call would put one back on the hot path. Hence: the tariff table arrives PIGGYBACKED on the
# lease response the engine already fetches periodically (`nucleo/energy_lease.py`), is cached in
# `sys_kv`, and lookups are pure dictionary reads against that cache.
#
# THE THREE LAYERS, most-authoritative first:
#   1. what the cloud sent (cached in sys_kv, survives restarts)
#   2. the DEFAULTS bundled below — real published pricing, used until the first lease lands, and the
#      only thing a self-host install ever sees (it never leases, and never meters either)
#   3. the never-silently-free catch-all inside each lookup
#
# Layer 2 is NOT redundant with layer 1: a brand-new Machine meters real usage during the seconds
# before its first lease arrives, and a fleet that has never leased (self-host) must still import
# this module without exploding.
#
from __future__ import annotations

import json
import time

from loguru import logger

# ── DEFAULTS ────────────────────────────────────────────────────────────────────────────────────
#
# Real published pricing. These are the FALLBACK, not the authority — the operator's values in the
# backoffice win. Keep them honest anyway: they are what a Machine bills with before its first lease.
#
# Sources verified 2026-08-16:
#   voxtral   — mistral.ai/news/voxtral-transcribe-2 ($0.006/min realtime, $0.003/min batch; the
#               cloud profile runs `voxtral-mini-transcribe-realtime-*`, so REALTIME is the rate)
#   deepgram  — deepgram.com/pricing (Nova-3, pay-as-you-go, monolingual)
#   elevenlabs— elevenlabs.io/pricing/api (Flash/Turbo v2.5)
#   cartesia  — cartesia.ai/pricing (Sonic, pay-as-you-go)
#
# LOCAL BACKENDS ARE DELIBERATELY ABSENT. `whisper_local`/`kokoro_local` are free, and free is a
# PROPERTY OF THE PROVIDER, not a rate of zero somebody can later mistake for "unpriced". The caller
# filters them out before metering (agent.py's metrics_collected hook); if one ever reached here it
# would hit the catch-all and over-bill loudly, which is the correct direction to fail.

DEFAULT_STT_USD_PER_MIN: dict[str, float] = {
    "voxtral": 0.006,
    "deepgram": 0.0048,
}

DEFAULT_TTS_USD_PER_1K_CHARS: dict[str, float] = {
    "elevenlabs": 0.05,
    "cartesia": 0.04,
}

# $ per PARTICIPANT-minute of real-time transport. Source: livekit.com/pricing, 2026-08-16 —
# $0.0004/min WebRTC, pay-as-you-go.
#
# ⚠️ THIS IS THE ONE RATE MOST LIKELY TO BE WRONG BY DESIGN, and it is why rates had to become
# editable. LiveKit's tiers bundle an INCLUDED QUOTA (the free Build tier alone carries 5,000 WebRTC
# minutes/month), so while a deployment sits inside its quota the true MARGINAL cost of one more
# minute is zero, and billing customers $0.0004 for it would be inventing a cost that isn't being
# paid. Above the quota this rate is real. Which of the two applies is a fact about the OPERATOR'S
# PLAN, not about the code — so the operator sets it in the master (0 while inside the quota) and the
# default here is the honest pay-as-you-go price rather than a zero that would look like "free".
DEFAULT_TRANSPORT_USD_PER_MIN: dict[str, float] = {
    "livekit": 0.0004,
}

# The catch-all per family: an unmapped provider bills at the MOST EXPENSIVE known rate and says so
# once. Same stance as `_FALLBACK_RATE_USD` and the `""` row of `_SEARCH_USD_PER_REQUEST` in
# `energy_meter`: under-billing loses real money silently, over-billing a rare provider is visible on
# the next invoice and gets corrected.
_FAMILIES: dict[str, dict[str, float]] = {
    "stt": DEFAULT_STT_USD_PER_MIN,
    "tts": DEFAULT_TTS_USD_PER_1K_CHARS,
    "transport": DEFAULT_TRANSPORT_USD_PER_MIN,
}

_KV_KEY = "energy:tariffs"

# In-process cache. `_loaded` is separate from `_tariffs` being empty on purpose: "never read sys_kv"
# and "read it and the cloud has sent nothing" are different states, and only the first should retry.
_tariffs: dict[str, dict[str, float]] = {}
_fetched_at: float = 0.0
_loaded = False
_warned: set[str] = set()


def _load_once() -> None:
    global _loaded, _tariffs, _fetched_at
    if _loaded:
        return
    _loaded = True
    try:
        from memory import api as memory          # NOT a bare `import memory`: the facade re-exports nothing
        raw = memory.kv_get(_KV_KEY)
        if raw:
            data = json.loads(raw) if isinstance(raw, str) else raw
            _tariffs = {k: dict(v) for k, v in (data.get("families") or {}).items()}
            _fetched_at = float(data.get("fetched_at") or 0.0)
            logger.info(f"energy_tariffs: loaded central rates from sys_kv ({_describe(_tariffs)})")
    except Exception as e:  # noqa: BLE001
        logger.warning(f"energy_tariffs: could not read cached rates, using bundled defaults: {e}")


def _describe(fams: dict[str, dict[str, float]]) -> str:
    return ", ".join(f"{fam}:{len(rows)}" for fam, rows in sorted(fams.items())) or "empty"


def update(families: dict | None, *, source: str = "lease") -> bool:
    """Store the rates the cloud just sent. Returns True if anything was stored.

    Rejects a malformed or EMPTY payload rather than adopting it: a control-plane that answers `{}`
    (misconfigured, mid-migration, or a bug) must not silently wipe the rates a Machine is billing
    with and drop it to the catch-all for everything. Absence is not an instruction.
    """
    global _tariffs, _fetched_at
    if not isinstance(families, dict) or not families:
        return False
    clean: dict[str, dict[str, float]] = {}
    for fam, rows in families.items():
        if fam not in _FAMILIES or not isinstance(rows, dict):
            continue
        vals = {}
        for provider, rate in rows.items():
            try:
                r = float(rate)
            except (TypeError, ValueError):
                continue
            if r >= 0:                      # 0 is legitimate (a provider inside an included quota)
                vals[str(provider).lower()] = r
        if vals:
            clean[fam] = vals
    if not clean:
        logger.warning(f"energy_tariffs: {source} sent rates but none were usable — keeping current")
        return False
    _load_once()
    changed = clean != _tariffs
    _tariffs = clean
    _fetched_at = time.time()
    try:
        from memory import api as memory
        memory.kv_set(_KV_KEY, json.dumps({"families": _tariffs, "fetched_at": _fetched_at}))
    except Exception as e:  # noqa: BLE001
        logger.warning(f"energy_tariffs: rates applied in memory but NOT persisted: {e}")
    if changed:
        logger.info(f"energy_tariffs: central rates updated via {source} ({_describe(_tariffs)})")
    return True


def rate_for(family: str, provider: str | None) -> float:
    """The $ rate for one provider of one family. Never raises, never returns None, never zero by
    accident — an unknown provider gets the most expensive known rate and one warning."""
    _load_once()
    fam = (family or "").lower()
    key = (provider or "").lower().strip()
    defaults = _FAMILIES.get(fam)
    if defaults is None:
        return 0.0                                   # unknown FAMILY: the caller has a bug, not a price
    table = _tariffs.get(fam) or defaults
    if key in table:
        return float(table[key])
    # Fall back to the bundled default before the catch-all: the cloud may have sent a partial table
    # (it only stores what the operator edited) and a provider it didn't mention is not unknown to US.
    if key in defaults:
        return float(defaults[key])
    warn_key = f"{fam}:{key}"
    if warn_key not in _warned:
        _warned.add(warn_key)
        logger.warning(
            f"energy_tariffs: no {fam} rate for provider={provider!r} — billing at the most expensive "
            f"known rate. Add it in the master (Tarifas) or to DEFAULT_* in energy_tariffs.py."
        )
    pool = table or defaults
    return max(pool.values()) if pool else 0.0


def snapshot() -> dict:
    """What this Machine is billing with right now — for /api/energy and the observability panel."""
    _load_once()
    return {
        "source": "central" if _tariffs else "bundled_defaults",
        "fetched_at": _fetched_at,
        "families": {fam: dict(_tariffs.get(fam) or defaults) for fam, defaults in _FAMILIES.items()},
    }


def _reset_for_tests() -> None:
    global _tariffs, _fetched_at, _loaded, _warned
    _tariffs, _fetched_at, _loaded, _warned = {}, 0.0, False, set()
