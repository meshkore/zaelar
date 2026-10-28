# ENERGY LEASE — RENEWAL AND THE FUSE: ask, recover a spent lease, stop when none can be had, retry while
# stopped. State and the public face stay in `nucleo/energy/lease.py`.
from __future__ import annotations

import asyncio
import os
import time

from loguru import logger
import httpx

from nucleo.energy import tariffs as energy_tariffs


async def _renew_or_blow(reason: str = "expired") -> None:
    """The lease ran out (clock or amount): retry along `_RECOVER_DELAYS`, then judge by `allowed()` — not by
    `ensure`'s return, which on a network failure still says «balance left». An ANSWERED no ends at once
    (`CAUSE_DENIED`); out of attempts → `CAUSE_UNRENEWED`. Single-flight."""
    if _m._recovering:
        return
    _m._recovering = True
    try:
        for delay in _m._RECOVER_DELAYS or (0.0,):
            if delay:
                await asyncio.sleep(delay)
            for _ in range(200):                      # a request already in flight answers for us: wait for it
                if not _m._renewing:
                    break
                await asyncio.sleep(0.05)
            try:
                await _m.ensure(reason=reason, force=True)
            except Exception as e:  # noqa: BLE001
                logger.warning(f"energy_lease: renewal ({reason}) failed: {e}")
            if _m.allowed() or _m._state.get("cause") == _m.CAUSE_DENIED:
                return
    finally:
        _m._recovering = False
    if not _m.allowed():
        if _m._state.get("cause") != _m.CAUSE_DENIED:
            _m._state["cause"] = _m.CAUSE_UNRENEWED
            _m._persist()
        logger.warning(f"energy_lease: lease not renewed after {len(_m._RECOVER_DELAYS) or 1} attempt(s) ({reason})")
        _m._blow_fuse()


def _server_loop():
    """The loop for lease work when the spend happens in a thread (`asyncio.to_thread`): dropping the renewal
    there once stopped an account with 200 Energy left."""
    try:
        from nucleo.energy import meter as energy_meter
        return energy_meter._loop
    except Exception:  # noqa: BLE001
        return None


def _schedule(coro) -> None:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        loop = _m._server_loop()
        if loop is None or loop.is_closed():
            coro.close()
            return
        asyncio.run_coroutine_threadsafe(coro, loop)
        return
    asyncio.create_task(coro)


def _blow_fuse(*, verdict: bool = False) -> None:
    """No lease and none coming: stop for real, and VISIBLY. Never while a request is IN FLIGHT (booting is not
    exhausted; a stop-then-resume flicker protects nothing). `verdict` = the cloud ANSWERED no, which runs inside
    the request itself — without it a denied boot lease never stopped anything (2026-10-22)."""
    if _m._in_flight() and not verdict:
        logger.debug("energy_lease: a lease request is in flight — no stop decision yet")
        return
    cause = _m.CAUSE_DENIED if verdict else (_m._state.get("cause") or _m.CAUSE_UNRENEWED)
    try:
        from nucleo import runstate
        if not runstate.stopped():     # already stopped: the notice and the retry below still have to happen
            logger.warning("energy_lease: arriendo agotado — PARANDO las operaciones de pago")
            _m._schedule(runstate.stop(src=_m.STOP_SRC))
    except Exception as e:  # noqa: BLE001
        logger.warning(f"energy_lease: no se pudo parar por arriendo agotado: {e}")
    try:
        from nucleo.energy import limits as account_limits
        account_limits.request_close(cause)
    except Exception:  # noqa: BLE001
        pass
    _m._start_retry()


def _start_retry() -> None:
    if _m._retry_task is not None and not _m._retry_task.done():
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = _m._server_loop()
        if loop is None or loop.is_closed():
            return
        _m._retry_task = asyncio.run_coroutine_threadsafe(_m._retry_loop(), loop)
        return
    _m._retry_task = loop.create_task(_m._retry_loop())


async def _retry_loop() -> None:
    """Asks until a lease arrives (or attempts run out), forced since local state says «nothing left». The wait
    grows from a few seconds to `_RETRY_S`: a full first minute kept agents stopped for nothing (V2-801)."""
    intentos = 0
    while intentos < int(os.getenv("ENERGY_LEASE_RETRY_MAX", "2880")):   # ~48 h at one attempt/minute
        intentos += 1
        await asyncio.sleep(min(_m._RETRY_S, 5.0 * (2 ** (intentos - 1))))
        try:
            if await _m.ensure(reason="retry_after_exhaustion", force=True):
                logger.info(f"energy_lease: arriendo recuperado tras {intentos} intento(s)")
                return
        except Exception as e:  # noqa: BLE001
            logger.debug(f"energy_lease: reintento {intentos} falló: {e}")
    logger.warning("energy_lease: se agotaron los reintentos de arriendo; hace falta intervención")


async def ensure(*, reason: str = "boot", force: bool = False) -> bool:
    """Asks for a lease if needed; returns whether a usable one is held. Single-flight: N crossings, ONE request."""
    if not _m.enabled():
        return True
    _m._load_once()
    if not force and _m.remaining() > 0 and not _m._near_expiry() and \
            float(_m._state["spent"]) < float(_m._state["granted"]) * _m._RENEW_AT and _m._gauge_knows():
        return True
    if _m._renewing:
        return _m.remaining() > 0
    _m._renewing = True
    try:
        return await _m._request(reason)
    finally:
        _m._renewing = False


async def _request(reason: str) -> bool:
    from nucleo.energy import account as cloud_account

    url = (os.getenv("CONTROL_PLANE_URL") or "").strip()
    if not url:
        # No endpoint on a cloud account is a fault, not a licence: `allowed()` stays no and the fuse blows.
        logger.warning("energy_lease: CONTROL_PLANE_URL sin configurar — no se puede arrendar energía")
        return False
    token = (os.getenv("CONTROL_PLANE_SERVICE_TOKEN") or "").strip()
    payload = {"machine_id": (os.getenv("FLY_MACHINE_ID") or "").strip() or None,
               "spent": round(float(_m._state["spent"]), 6), "reason": reason}
    try:
        async with httpx.AsyncClient(timeout=5.0) as c:
            r = await c.post(url.rstrip("/") + _m._PATH, json=payload,
                             headers={"X-Service-Token": token} if token else {})
        data = r.json() if r.status_code < 500 else None
    except Exception as e:  # noqa: BLE001
        # Renewal failed: the current lease is untouched; if it runs out first, the fuse does its job.
        logger.warning(f"energy_lease: renovación fallida ({reason}), se sigue con lo que quede: {e}")
        return _m.remaining() > 0
    if not isinstance(data, dict) or "ok" not in data:
        # NOT AN ANSWER (5xx, no `ok`): a failed renewal like a timeout, never a verdict that zeroes the lease (V2-801).
        logger.warning(f"energy_lease: no lease answer ({reason}, HTTP {r.status_code}), se sigue con lo que quede")
        return _m.remaining() > 0

    # TARIFFS ON THE FLY: adopted BEFORE the verdict (valid even on a denial), riding the one periodic call the
    # engine already makes. `update()` rejects an empty/corrupt payload — absence is not an instruction.
    try:
        energy_tariffs.update(data.get("tariffs"), source="lease")
    except Exception as e:  # noqa: BLE001
        logger.warning(f"energy_lease: no se pudieron aplicar las tarifas centrales: {e}")
    # …and the balance (with the plan's gauge facts), which the gauge has no other way to learn under a lease.
    _m._gauge_from_lease(data)

    granted = float(data.get("energy") or 0.0)
    if not data.get("ok") or granted <= 0:
        # ANY answered no is a VERDICT meaning «don't spend»; the reason is logged, never branched on (a new
        # reason must not be silently ignored). A network FAULT returned earlier, leaving the lease alive.
        motivo = data.get("error") or data.get("reason") or "sin_motivo"
        logger.warning(f"energy_lease: la nube NIEGA el arriendo ({motivo}) — se paran las operaciones de pago")
        _m._state.update({"granted": 0.0, "spent": 0.0, "expires_at": 0.0, "at": time.time(), "cause": _m.CAUSE_DENIED})
        _m._persist()
        _m._blow_fuse(verdict=True)
        return False

    ttl = float(data.get("ttl_s") or 1800)
    _m._state.update({"lease_id": data.get("lease_id"), "granted": granted, "spent": 0.0,
                   "expires_at": time.time() + ttl, "at": time.time(), "cause": None})
    _m._persist()
    logger.info(f"energy_lease: arriendo de {granted:.2f} Energy por {ttl:.0f}s ({reason}), "
                f"user={cloud_account.my_user_id()}")
    _m._maybe_resume()
    try:
        from nucleo.energy import limits as account_limits
        account_limits.clear_exhausted()            # a lease is the end of "out of energy", whatever caused it
    except Exception as e:  # noqa: BLE001
        logger.debug(f"energy_lease: could not clear the out-of-energy state: {e!r}")
    return True


def _maybe_resume() -> None:
    """A new lease arrived: restart only a stop WE caused, never one the operator made by hand."""
    try:
        from nucleo import runstate
        if runstate.stopped() and runstate.snapshot().get("src") == _m.STOP_SRC:
            logger.info("energy_lease: arriendo repuesto — se reanuda lo que paramos por energía")
            _m._schedule(runstate.start(src=_m.STOP_SRC))
    except Exception as e:  # noqa: BLE001
        logger.warning(f"energy_lease: no se pudo reanudar tras renovar: {e}")


# Last, so either import order works: `_m` is only read at call time.
from nucleo.energy import lease as _m  # noqa: E402
