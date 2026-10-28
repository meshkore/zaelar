# ENERGY LEASE — THE GAUGE: the balance the lease answer carries, and telling the Energy gauge as the
# agent spends. State and the public face stay in `nucleo/energy/lease.py`.
from __future__ import annotations

import time

from loguru import logger

from nucleo.energy import lease as _m


def _gauge_from_lease(data: dict) -> None:
    """Under a lease the balance arrives only in the lease answer (no per-charge report), optionally with the
    plan's gauge facts (`cycle_energy`, `scale`, `tier`) instead of a guess. Never raises: presentation."""
    try:
        if not isinstance(data, dict) or data.get("balance") is None:
            return
        b = float(data["balance"])
        plan = data.get("plan") if isinstance(data.get("plan"), dict) else {}
    except (TypeError, ValueError) as e:
        logger.debug(f"energy_lease: unreadable balance in the lease answer: {e!r}")
        return
    from nucleo.energy import meter as _em
    _em._load_once()
    _st = _em._state
    cap = _st.get("capacity")
    cycle = plan.get("cycle_energy")
    if isinstance(cycle, (int, float)) and cycle > 0:
        cap = float(cycle)
    elif cap is None or _st.get("balance") is None or b > float(_st["balance"]):
        cap = b
    gauge = {k: plan.get(k) for k in ("key", "name", "tier", "scale") if plan.get(k) is not None}
    _st.update({"balance": b, "capacity": cap, "at": time.time(), "src": "lease", "plan": gauge or None})
    try:
        from memory import api as memory
        # kv_set encodes JSON itself: a string here came back as a string and was never restored.
        memory.kv_set(_em._KV_KEY, {k: _st[k] for k in ("balance", "capacity", "at", "src", "plan")})
    except Exception as e:  # noqa: BLE001
        logger.debug(f"energy_lease: gauge balance not persisted: {e!r}")
    try:
        from voice.observer import emit
        # The fresh balance as granted: the spend counter resets right after, so no phantom dip.
        emit("energy", "saldo", extra={**_em.snapshot(), "balance": b})
    except Exception as e:  # noqa: BLE001
        logger.debug(f"energy_lease: gauge event not emitted: {e!r}")


def _tell_gauge() -> None:
    """The gauge goes down as the agent works: one `energy` event every few seconds at most (a spend is local)."""
    now = time.time()
    if now - _m._gauge_told["at"] < _m._GAUGE_EVERY_S:
        return
    _m._gauge_told["at"] = now
    try:
        from nucleo.energy import meter as energy_meter
        from voice.observer import emit
        snap = energy_meter.snapshot()
        if snap.get("known"):
            emit("energy", "saldo", extra={"balance": snap["balance"], "capacity": snap["capacity"]})
    except Exception as e:  # noqa: BLE001 — the gauge is presentation; a spend never fails for it
        logger.debug(f"energy_lease: gauge not told: {e!r}")


def _gauge_knows() -> bool:
    """Does the gauge know the balance? Only a lease ANSWER tells it, so not knowing is a reason to ask."""
    try:
        from nucleo.energy import meter as energy_meter
        return bool(energy_meter.snapshot().get("known"))
    except Exception as e:  # noqa: BLE001 — unreadable means «ask», the safe side for a display
        logger.debug(f"energy_lease: gauge state unreadable: {e!r}")
        return False
