# ENERGY LEASE — THE GATE: the question asked BEFORE starting paid work (`check`/`admit`), and how a
# refusal is recognised (`is_refusal`). State and the public face stay in `nucleo/energy/lease.py`.
from __future__ import annotations

import time

from loguru import logger

from nucleo.energy import lease as _m


def is_refusal(err) -> bool:
    """Is this exception (or its text) the lease gate saying no, rather than a provider failing?"""
    return isinstance(err, _m.OutOfEnergy) or _m.REFUSAL_MARK in str(err or "")


def check(kind: str = "") -> bool:
    """May this machine START a paid operation of `kind` now? Never raises; True without a cloud account.

    Beyond `allowed()`: a request IN FLIGHT → a healthy lease keeps going, none/failed waits (no stop decision);
    ran out (clock or amount) with no failure on record → yes, and recover now; otherwise → no, and the fuse
    blows with its cause, so the operator sees what happened rather than a pile of failed calls."""
    try:
        if _m.allowed():
            return True
        healthy = float(_m._state["granted"]) > 0 and not _m._state.get("cause")
        if _m._in_flight():
            return healthy
        if healthy:
            _m._schedule(_m._renew_or_blow(reason="expired" if _m.remaining() > 0 else "exhausted"))
            return True
        now = time.time()
        if now - _m._refused_log_at.get(kind, 0.0) > 60:
            _m._refused_log_at[kind] = now
            logger.warning(f"energy_lease: no usable lease — refusing paid work ({kind or 'unspecified'})")
        _m._blow_fuse()
        return False
    except Exception as e:  # noqa: BLE001 — a broken gate fails CLOSED where there is a lease to obey
        logger.warning(f"energy_lease.check failed ({e!r}) — refusing paid work")
        return not _m.enabled()


def admit(kind: str = "") -> None:
    """`check()` for a caller that must not proceed on a no: raises `OutOfEnergy`."""
    if not _m.check(kind):
        raise _m.OutOfEnergy(f"{_m.REFUSAL_MARK} for {kind or 'paid work'}")
