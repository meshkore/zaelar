# ENERGY LEASE — a local spending ceiling the instance enforces on itself.
# The endpoint (CONTROL_PLANE_URL + ZAELAR_USER_ID) grants Energy with an expiry; each metered op is an in-process
# subtraction (no network), renewal is asked in the background at ENERGY_LEASE_RENEW_AT. No renewal → the instance
# STOPS ITSELF (`runstate.stop()`, same switch as ⏻) and a later lease restarts only a stop it caused itself.
# A SPENT LEASE IS NOT AN EMPTY ACCOUNT (V2-801): running out asks again at once, with a short bounded backoff, and
# stops only on a persisted cause — `energy_denied` (the endpoint ANSWERED `"ok": false`, any reason) or
# `lease_unrenewed` (no answer: network, timeout, 5xx, no `ok`). While a request is in flight the fuse never blows.
# Self-host (no ZAELAR_USER_ID): `allowed()` is always True, no state, no network.
from __future__ import annotations

import asyncio
import os
import time

from loguru import logger

STOP_SRC = "energy_lease"   # who stopped us: a renewal never undoes the operator's own stop
_RENEW_AT = float(os.getenv("ENERGY_LEASE_RENEW_AT", "0.5"))   # half: room for a slow round trip, off the hot path
# Renew this long before expiry even with balance left.
_EXPIRY_MARGIN_S = float(os.getenv("ENERGY_LEASE_EXPIRY_MARGIN_S", "120"))

_KV_KEY = "energy:lease"
_PATH = "/lease"

# In process (a debit is a subtraction) AND in `sys_kv` (a restart loop must not reset the spend). NEVER the root
# state: `compose_state` dumps every scalar into each turn's prompt.
_state: dict = {"lease_id": None, "granted": 0.0, "spent": 0.0, "expires_at": 0.0, "at": 0.0, "cause": None}
_loaded = False
_renewing = False
_recovering = False       # a recovery (`_renew_or_blow`) is between attempts: still no stop decision

# A stop's two causes, shown via `account_limits.request_close(cause)`.
CAUSE_DENIED = "energy_denied"          # the endpoint answered no
CAUSE_UNRENEWED = "lease_unrenewed"     # no answer could be had

# Recovery backoff (s before each attempt): short and bounded — the overspend it allows is one in-flight op's.
_RECOVER_DELAYS = tuple(float(x) for x in os.getenv("ENERGY_LEASE_RECOVER_DELAYS", "0,1,3").split(",") if x.strip())


def enabled() -> bool:
    from nucleo.energy import account as cloud_account
    return cloud_account.is_cloud_account()


def _load_once() -> None:
    global _loaded
    if _loaded:
        return
    _loaded = True
    try:
        # `from memory import api`, NOT bare `import memory` (re-exports nothing → silent no-persist). 2026-08-14:
        # seven leases in a row with `reported_spent = 0`, each restart asking for a fresh 50.
        from memory import api as memory
        raw = memory.kv_get(_KV_KEY)
        if isinstance(raw, dict):
            _state.update({k: raw.get(k, _state[k]) for k in _state})
    except Exception as e:  # noqa: BLE001 — no stored lease: a new one is asked for, nothing breaks
        logger.debug(f"energy_lease: no se pudo leer el arriendo guardado: {e}")


def _persist() -> None:
    try:
        from memory import api as memory   # see the note in `_load_once`: the bare import is a no-op
        memory.kv_set(_KV_KEY, dict(_state))
    except Exception as e:  # noqa: BLE001
        logger.debug(f"energy_lease: no se pudo guardar el arriendo: {e}")


def remaining() -> float:
    """Energy left in the lease, never negative (an in-flight op may overshoot; nothing new starts after)."""
    _load_once()
    return max(0.0, float(_state["granted"]) - float(_state["spent"]))


def expired() -> bool:
    _load_once()
    exp = float(_state["expires_at"] or 0.0)
    return exp > 0 and time.time() >= exp


def _near_expiry() -> bool:
    """Is the lease running out by CLOCK? Without it a machine that spends little expired with energy left."""
    _load_once()
    exp = float(_state["expires_at"] or 0.0)
    return exp > 0 and time.time() >= exp - _EXPIRY_MARGIN_S


def _in_flight() -> bool:
    """Is a lease request pending (boot, renewal, recovery)? Then no stop decision: the answer is seconds away."""
    return _renewing or _recovering or _booting


_booting = False          # the boot lease request is scheduled and has not answered yet


async def _boot_lease() -> bool:
    global _booting
    try:
        return await ensure(reason="boot", force=True)
    finally:
        _booting = False


def start_at_boot():
    """Asks for a FRESH lease at boot (the persisted one is stale facts) and returns the task. The in-flight mark
    is set HERE, synchronously, so nothing before the task's first step can decide a stop (V2-801)."""
    global _booting
    if not enabled():
        return None
    _booting = True
    return asyncio.get_running_loop().create_task(_boot_lease())


def stop_cause() -> str | None:
    """Why the last stop happened (`CAUSE_DENIED` / `CAUSE_UNRENEWED`), or None while the lease is healthy."""
    _load_once()
    return _state.get("cause")


def allowed() -> bool:
    """May this machine start something that costs money? Self-host: always. Cloud: **only with a live lease**
    — no lease is NO (fail-closed), not «go ahead until told otherwise»."""
    if not enabled():
        return True
    return remaining() > 0 and not expired()


# ── THE GATE IN FRONT OF PAID WORK (`lease_gate.py`) ─────────────────────────────────────────────────────────
# Nothing used to ask `allowed()`: a machine with no lease spent until the first report. `check()`/`admit()` are
# asked BEFORE paid work, at the doors it already passes (egress, FastClient, search keys, runstate, a few direct
# callers); `test_paid_work_passes_the_lease_gate` pins that every metering file passes one.

# The refusal's words: text-only error handlers (the provider ladder) recognise it, so no cooldown opens.
REFUSAL_MARK = "no energy lease"


class OutOfEnergy(RuntimeError):
    """A paid call refused BEFORE it started (no usable lease). Nobody's failure: never an outage, no relay."""


_refused_log_at: dict = {}


_GAUGE_EVERY_S = 3.0
_gauge_told = {"at": 0.0}


def note_spend(energy: float) -> None:
    """Debits the local counter, in the same gesture as the usage report but never waiting. Never raises."""
    if not enabled() or not energy or energy <= 0:
        return
    try:
        _load_once()
        _state["spent"] = float(_state["spent"]) + float(energy)
        _persist()
        _tell_gauge()
        if remaining() <= 0:
            # THE SLICE IS SPENT, NOT THE ACCOUNT (V2-801): one worker charge can exceed it. Ask again now.
            _schedule(_renew_or_blow(reason="exhausted"))
        elif expired():
            # EXPIRED IS NOT EXHAUSTED (it cost a daily outage after idle nights): ask again, stop only on no/silence.
            _schedule(_renew_or_blow())
        elif float(_state["spent"]) >= float(_state["granted"]) * _RENEW_AT or _near_expiry():
            _schedule(ensure(reason="half_spent"))
    except Exception as e:  # noqa: BLE001 — counting never breaks the turn that triggered it
        logger.warning(f"energy_lease.note_spend falló (no fatal): {e}")


# Retry while stopped for energy: renewal fires on SPEND and a stopped machine spends nothing, so without this
# a top-up would never wake it (found deploying, not reasoning).
_RETRY_S = float(os.getenv("ENERGY_LEASE_RETRY_S", "60"))
_retry_task = None


def snapshot() -> dict:
    """For `/api/energy` and the viewer. `leased=False` on self-host: no lease to show."""
    if not enabled():
        return {"leased": False}
    _load_once()
    return {"leased": True, "lease_id": _state["lease_id"], "granted": float(_state["granted"]),
            "spent": float(_state["spent"]), "remaining": remaining(),
            "expires_at": float(_state["expires_at"] or 0.0), "allowed": allowed(), "stop_cause": _state.get("cause")}


def _reset_for_tests() -> None:
    global _loaded, _renewing, _recovering, _booting
    _state.update({"lease_id": None, "granted": 0.0, "spent": 0.0, "expires_at": 0.0, "at": 0.0, "cause": None})
    _loaded = False
    _renewing = False
    _recovering = False
    _booting = False
    _refused_log_at.clear()


from nucleo.energy.lease_gate import (  # noqa: E402,F401 — moved by concern (refactor2710-10b)
    is_refusal, check, admit,
)
from nucleo.energy.lease_gauge import (  # noqa: E402,F401 — moved by concern (refactor2710-10b)
    _gauge_from_lease, _tell_gauge, _gauge_knows,
)
from nucleo.energy.lease_renewal import (  # noqa: E402,F401 — moved by concern (refactor2710-10b)
    _renew_or_blow, _server_loop, _schedule, _blow_fuse, _start_retry, _retry_loop, ensure, _request, _maybe_resume,
)
