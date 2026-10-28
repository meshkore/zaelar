# ENERGY METERING — real provider usage (LLM/worker tokens, TTS chars, STT seconds, transport
# participant-seconds) → cost → Energy units, reported fire-and-forget to a usage ledger.
# Active only with `ZAELAR_USER_ID` set (nucleo/energy/account.py); self-host → zero cost, zero network.
# Rates: per MODEL first, then per base_url, then a punitive FALLBACK logged once — never silently free.
# All numbers are defaults (re-verify provider pricing; ENERGY_EUR_PER_UNIT / ENERGY_MARGIN_MULTIPLIER override).
# Split by concern (refactor2710-10b): this face keeps the STATE and the ledger POST; tables in `meter_rates.py`,
# pricing in `meter_price.py`, reporting doors in `meter_report.py` — all re-exported here.
import os
import time

import httpx
from loguru import logger

from nucleo.energy import tariffs as energy_tariffs  # noqa: F401 — read by meter_price as `_m.energy_tariffs`
from nucleo.energy.meter_rates import (  # noqa: F401 — the price tables, moved by concern (refactor2710-10b)
    _BROKER_MARKUP_AIMLAPI, _BROKER_MARKUP_DEFAULT, _CACHED_READ_FALLBACK_FRACTION, _CACHED_READ_RATES_USD,
    _DECISION_USD_PER_REQUEST, _FALLBACK_RATE_USD, _MODEL_RATES, _RATES_PER_1M_TOKENS_USD, _SEARCH_USD_PER_REQUEST,
)

# Logged loudly once per distinct unmapped key (see `_FALLBACK_RATE_USD` in `meter_rates.py`).
_warned_unmapped: set[str] = set()

EUR_PER_ENERGY_UNIT = float(os.getenv("ENERGY_EUR_PER_UNIT", "0.01"))   # default; ENERGY_EUR_PER_UNIT overrides
MARGIN_MULTIPLIER = float(os.getenv("ENERGY_MARGIN_MULTIPLIER", "4.0"))  # default; ENERGY_MARGIN_MULTIPLIER overrides


def enabled() -> bool:
    """Metering is active only when ZAELAR_USER_ID is set (asked through the single-purpose accessor)."""
    from nucleo.energy import account as cloud_account
    return cloud_account.is_cloud_account()


# Tokens charged for a PAID call that reported no usage (2026-08-13): a missing volume multiplied to zero and
# reported success. Deliberately the WRONG number, logged loudly and marked `estimated` — fix the call site.
_MISSING_USAGE_FLOOR = (
    int(os.getenv("ENERGY_MISSING_USAGE_IN_TOKENS", "2000")),
    int(os.getenv("ENERGY_MISSING_USAGE_OUT_TOKENS", "500")),
)
_warned_missing_usage: set[str] = set()
_warned_search = set()        # once per unmapped search provider (see `_SEARCH_USD_PER_REQUEST` in `meter_rates.py`)


# --- reporting: fire-and-forget POST to the right ledger, never blocks the turn/worker ---

_USAGE_ENDPOINT_PATH = "/usage"


async def _post_usage(energy: float, kind: str, meta: dict | None = None) -> None:
    await _post_usage_cloud_account(energy, kind, meta)


async def _post_usage_cloud_account(energy: float, kind: str, meta: dict | None = None) -> None:
    """POST /usage to CONTROL_PLANE_URL (`meta`: units/model only, never content); no URL or user id → no-op.
    The answer's `balance` feeds the gauge and `limits.on_balance` (depleted → close). Never raises."""
    from nucleo.energy import limits as account_limits, account as cloud_account

    control_plane_url = (os.getenv("CONTROL_PLANE_URL") or "").strip()
    user_id = cloud_account.my_user_id()
    if not control_plane_url or not user_id or energy <= 0:
        return
    # DOUBLE BILLING (2026-08-13, T303): with mediated egress the upstream already booked what it saw. The lease
    # deduction happens earlier (`_fire_and_forget`). Search joined 2026-10-23, decision 2026-10-24; voice stays here.
    from nucleo.energy import egress as llm_egress
    if kind in ("llm", "worker", "search", "decision") and llm_egress.bills_upstream():
        return
    service_token = (os.getenv("CONTROL_PLANE_SERVICE_TOKEN") or "").strip()
    headers = {"X-Service-Token": service_token} if service_token else {}
    payload = {"user_id": user_id, "energy": energy, "kind": kind}
    # The session id lets the ledger group usage (2026-08-09); no content, and events never leave this machine.
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


# --- THE BALANCE THE OPERATOR SEES (2026-08-13): a state that can strand you must be VISIBLE first. ---
# `capacity` = what the gauge started from; a balance that RISES (a top-up) sets it, spending does not.
# Lives in `sys_kv`, NEVER the root state: `compose_state` dumps every scalar into each voice prompt.
_KV_KEY = "energy:balance"
_state: dict = {"balance": None, "capacity": None, "at": 0.0, "src": "", "plan": None}
_loaded = False

_loop = None   # the server's loop (V2-102), captured once from the lifespan, as `search/browser.py::set_loop`


def set_loop(loop) -> None:
    """Lets `_fire_and_forget` schedule its POST from a thread with no loop (`asyncio.to_thread`)."""
    global _loop
    _loop = loop


def _load_once() -> None:
    global _loaded
    if _loaded:
        return
    _loaded = True
    try:
        from memory import api as memory
        d = memory.kv_get(_KV_KEY)          # kv_get/kv_set encode JSON themselves: store the dict as is
        if isinstance(d, dict):
            _state.update({"balance": d.get("balance"), "capacity": d.get("capacity"),
                           "at": float(d.get("at") or 0.0), "src": d.get("src") or "", "plan": d.get("plan")})
    except Exception:
        pass


def note_balance(balance) -> None:
    """Records the balance the ledger just reported. Presentation bookkeeping: never raises."""
    try:
        if balance is None:
            return
        b = float(balance)
    except (TypeError, ValueError):
        return
    _load_once()
    prev = _state.get("balance")
    cap = _state.get("capacity")
    # A TOP-UP is a rising balance (or the first one seen); spending never moves the capacity.
    if cap is None or prev is None or b > float(prev):
        cap = b
    _state.update({"balance": b, "capacity": cap, "at": time.time(), "src": "report"})
    try:
        from memory import api as memory
        memory.kv_set(_KV_KEY, {"balance": b, "capacity": cap, "at": _state["at"], "src": "report"})
    except Exception:
        pass
    # LIVE: the gauge drops while the agent works, without the frontend asking. `emit` never blocks.
    try:
        from voice.observer import emit
        emit("energy", "saldo", extra={"balance": b, "capacity": cap})
    except Exception:
        pass


def snapshot() -> dict:
    """The gauge's data. `known=False` = no balance seen yet: drawn unlit, not at zero («don't know» ≠ «ran out»)."""
    _load_once()
    b, cap = _state.get("balance"), _state.get("capacity")
    if b is not None and _state.get("src") == "lease":
        # Balance at grant minus this Machine's spend of the lease since: goes down live, with no network.
        try:
            from nucleo.energy import lease as energy_lease
            b = max(0.0, float(b) - float(energy_lease._state.get("spent") or 0.0))
        except Exception as e:  # noqa: BLE001
            logger.debug(f"energy_meter: lease spend unreadable: {e!r}")
    return {"cloud": enabled(), "known": b is not None, "balance": b, "capacity": cap,
            "plan": _state.get("plan"), "at": _state.get("at") or 0.0}


def _reset_for_tests() -> None:
    global _loaded
    _state.update({"balance": None, "capacity": None, "at": 0.0, "src": "", "plan": None})
    _loaded = False


from nucleo.energy.meter_price import (  # noqa: E402,F401 — moved by concern (refactor2710-10b)
    _broker_markup, _cached_rate_for, _is_local_endpoint, _rate_for, _resolve_tokens, decision_cost_to_energy,
    llm_cost_to_energy, search_cost_to_energy, stt_cost_to_energy, transport_cost_to_energy, tts_cost_to_energy,
)
from nucleo.energy.meter_report import (  # noqa: E402,F401 — moved by concern (refactor2710-10b)
    _fire_and_forget, _never_raises, _observe_charge, meter_openai_response, report_decision_usage,
    report_llm_usage, report_search_usage, report_stt_usage, report_transport_usage, report_tts_usage,
    report_worker_usage,
)
