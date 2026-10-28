# ENERGY LEASE — a local spending ceiling the instance enforces on itself.
#
# When a usage lease endpoint is configured (CONTROL_PLANE_URL + ZAELAR_USER_ID), it grants a LEASE: an
# amount of Energy and an expiry. While the lease lasts, every metered operation is a subtraction on an
# in-process counter — zero network on the hot path. Renewal is requested in the background once a
# fraction of the lease is spent (ENERGY_LEASE_RENEW_AT). If the lease runs out with no renewal, the
# instance STOPS ITSELF via `nucleo/runstate.stop()` — the same switch as the user's ⏻ — so an
# unreachable endpoint caps spend at one lease instead of leaving it unbounded. If the lease stopped the
# instance, a renewal restarts it; a stop by the user is never undone here.
#
# A SPENT LEASE IS NOT AN EMPTY ACCOUNT (V2-801). The lease is a small slice of the account's balance, and one
# charge can be bigger than the whole slice (a Brain Worker bills its whole run when it ends). Running the slice
# out therefore ASKS for another one at once, with a short bounded backoff, and stops only on what actually
# happened, recorded as the stop's cause and shown as such:
#   · `energy_denied`   — the endpoint ANSWERED no (a 2xx/4xx body carrying `"ok": false`): the account cannot
#                         spend. Any reason means the same thing; the engine never branches on it.
#   · `lease_unrenewed` — no answer could be had (network error, timeout, 5xx, a body without `ok`): the account
#                         may be full, the engine just cannot confirm it. Fail-closed all the same, but this one
#                         never claims the account is empty.
# The cause is persisted with the lease, so a restart loop against an unreachable endpoint does not hand each new
# process a fresh allowance. At boot the lease is asked for again (`ensure(force=True)`) before any stop decision:
# while a lease request is in flight the fuse does not blow.
#
# Without ZAELAR_USER_ID (self-host) `enabled()` is False → `allowed()` is always True, no state, no network.
#
from __future__ import annotations

import asyncio
import os
import time

import httpx
from loguru import logger

from nucleo.energy import tariffs as energy_tariffs

# Quién nos paró. Sirve para no pisar una parada del operador al renovar (the lease only restarts a stop it caused itself).
STOP_SRC = "energy_lease"

# Se pide renovación al consumir esta fracción. La mitad da margen de sobra para una ida y vuelta lenta
# sin que el arriendo llegue a agotarse — la renovación NUNCA debe estar en el camino crítico.
_RENEW_AT = float(os.getenv("ENERGY_LEASE_RENEW_AT", "0.5"))

# Colchón antes de que caduque: un arriendo a punto de expirar se renueva aunque quede saldo.
_EXPIRY_MARGIN_S = float(os.getenv("ENERGY_LEASE_EXPIRY_MARGIN_S", "120"))

_KV_KEY = "energy:lease"
_PATH = "/lease"

# El contador vive en proceso Y en `sys_kv`. En proceso porque descontar tiene que costar una resta; en
# `sys_kv` porque si no, reiniciar pondría el gastado a cero y un bucle de reinicios sería gasto sin
# techo — justo el agujero que esto cierra. NUNCA en el estado raíz: `compose_state` vuelca cada escalar
# del estado al prompt de cada turno (misma razón que en `rehydrate.py` y en el saldo de `energy_meter`).
_state: dict = {"lease_id": None, "granted": 0.0, "spent": 0.0, "expires_at": 0.0, "at": 0.0, "cause": None}
_loaded = False
_renewing = False
_recovering = False       # a recovery (`_renew_or_blow`) is between attempts: still no stop decision

# The two causes a stop can have. They travel to the screen through `account_limits.request_close(cause)`.
CAUSE_DENIED = "energy_denied"          # the endpoint answered no
CAUSE_UNRENEWED = "lease_unrenewed"     # no answer could be had

# Backoff (seconds before each attempt) of the recovery that runs when the lease is spent or expired. Short and
# bounded: it is the window during which a machine whose lease just ran out keeps working while it asks — the
# overspend it allows is that window's, the same order as one in-flight operation.
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
        # `from memory import api` — NOT a bare `import memory`. The `memory/__init__.py` facade is a
        # docstring and re-exports nothing, so `memory.kv_get` raises AttributeError, the except below
        # swallows it into a debug line, and the lease silently stops persisting. Found in production
        # on 2026-08-14: seven leases in a row, every one `reported_spent = 0`, because each restart
        # forgot the counter and asked for a fresh 50 Energy — the restart loop with uncapped spend
        # that this very persistence exists to close. `nucleo/runstate.py` already imported it right.
        from memory import api as memory
        raw = memory.kv_get(_KV_KEY)
        if isinstance(raw, dict):
            _state.update({k: raw.get(k, _state[k]) for k in _state})
    except Exception as e:  # noqa: BLE001 — sin arriendo guardado se pide uno nuevo, no se rompe nada
        logger.debug(f"energy_lease: no se pudo leer el arriendo guardado: {e}")


def _persist() -> None:
    try:
        from memory import api as memory   # see the note in `_load_once`: the bare import is a no-op
        memory.kv_set(_KV_KEY, dict(_state))
    except Exception as e:  # noqa: BLE001
        logger.debug(f"energy_lease: no se pudo guardar el arriendo: {e}")


def remaining() -> float:
    """Energy que queda del arriendo. Nunca negativa: pasarse es normal (una operación en vuelo puede
    cruzar el límite) y lo que importa es que a partir de ahí no se empieza nada nuevo."""
    _load_once()
    return max(0.0, float(_state["granted"]) - float(_state["spent"]))


def expired() -> bool:
    _load_once()
    exp = float(_state["expires_at"] or 0.0)
    return exp > 0 and time.time() >= exp


def _near_expiry() -> bool:
    """Is the lease running out by CLOCK (not by balance)?

    Renewal only ever fired at the half-spent mark, so a machine that spends little watched its lease
    expire with plenty of energy left without ever asking for another. `_EXPIRY_MARGIN_S` existed from
    day one for exactly this and **nobody read it**: the intent was written, the wire was never run."""
    _load_once()
    exp = float(_state["expires_at"] or 0.0)
    return exp > 0 and time.time() >= exp - _EXPIRY_MARGIN_S


def _in_flight() -> bool:
    """Is a lease request pending (boot, renewal, or a recovery between attempts)? While it is, there is no stop
    decision to take: the answer is seconds away."""
    return _renewing or _recovering or _booting


_booting = False          # the boot lease request is scheduled and has not answered yet


async def _boot_lease() -> bool:
    global _booting
    try:
        return await ensure(reason="boot", force=True)
    finally:
        _booting = False


def start_at_boot():
    """Asks for a FRESH lease at boot and returns the task. The lease persisted by the previous process is not
    trusted as the answer: it may be spent, it carries no fresh balance for the gauge, and a stop decided on it
    before the endpoint is asked is a stop decided on stale facts. The in-flight mark is set HERE, synchronously,
    so nothing that runs before the task's first step can take a stop decision either (V2-801)."""
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
    """¿Puede esta máquina empezar algo que cueste dinero?

    Sin cuenta de nube, siempre. Con cuenta de nube, **solo con arriendo vivo**: sin arriendo la
    respuesta es NO, no «adelante hasta que alguien diga lo contrario». Es la diferencia entre
    fail-closed y `guarded-until-configured`."""
    if not enabled():
        return True
    return remaining() > 0 and not expired()


# ── THE GATE IN FRONT OF PAID WORK ───────────────────────────────────────────────────────────────────────────
# `allowed()` existed from day one and nothing in production asked it: every paid call started first and was
# subtracted afterwards, so a machine with no lease at all — a brand-new account with nothing to lease — spent
# freely until the first report came back. `check()` is the question asked BEFORE starting something that costs
# money, and `admit()` is the same question for a caller that must not proceed on a no. The doors are the
# places paid work already passes on its way out: the model egress (`llm_egress.route`), the hot model client
# (`FastClient.stream/complete`, asked before its relay loop), the paid search keys (`search/providers/keys.key`),
# the one answer for opening a worker (`runstate.blocks_new_work`), and the few metered callers that do not route
# (decision model, cloud embeddings, browser agent, remote triage/distiller). `test_paid_work_passes_the_lease_gate`
# pins that every file that METERS paid spend also passes a door.

# The refusal's own words. Error handlers that only receive the TEXT of an exception (the provider ladder)
# recognise it by this mark, so a refusal never opens a cooldown on a healthy tier.
REFUSAL_MARK = "no energy lease"


class OutOfEnergy(RuntimeError):
    """A paid call was refused BEFORE it started because this machine holds no usable lease. It is nobody's
    failure — not the provider's, not ours — and callers must not treat it as an outage (no relay, no light)."""


def is_refusal(err) -> bool:
    """Is this exception (or its text) the lease gate saying no, rather than a provider failing?"""
    return isinstance(err, OutOfEnergy) or REFUSAL_MARK in str(err or "")


_refused_log_at: dict = {}


def check(kind: str = "") -> bool:
    """May this machine START a paid operation of `kind` now? Never raises; True without a cloud account.

    Cases beyond the plain `allowed()`:
      · a lease request is IN FLIGHT → no stop decision. A machine that held a lease and has no recorded failure
        keeps going for that short, bounded window; one that never held one (boot) or whose last recovery failed
        waits quietly. Stopping for an answer seconds away is the flicker `_blow_fuse` refuses;
      · the lease ran out — by CLOCK with energy left, or by AMOUNT — and nothing has failed since it was granted
        → yes, and recover now (`_renew_or_blow`); whatever the recovery hears decides the next call, so the old
        lease covers at most the recovery window;
      · otherwise (no lease, or a denial / failed recovery on record) → no, and the fuse blows with the cause on
        record, so the refusal reaches the operator as what happened rather than as a pile of failed calls."""
    try:
        if allowed():
            return True
        healthy = float(_state["granted"]) > 0 and not _state.get("cause")
        if _in_flight():
            return healthy
        if healthy:
            _schedule(_renew_or_blow(reason="expired" if remaining() > 0 else "exhausted"))
            return True
        now = time.time()
        if now - _refused_log_at.get(kind, 0.0) > 60:
            _refused_log_at[kind] = now
            logger.warning(f"energy_lease: no usable lease — refusing paid work ({kind or 'unspecified'})")
        _blow_fuse()
        return False
    except Exception as e:  # noqa: BLE001 — a broken gate fails CLOSED where there is a lease to obey
        logger.warning(f"energy_lease.check failed ({e!r}) — refusing paid work")
        return not enabled()


def admit(kind: str = "") -> None:
    """`check()` for a caller that must not proceed on a no: raises `OutOfEnergy`."""
    if not check(kind):
        raise OutOfEnergy(f"{REFUSAL_MARK} for {kind or 'paid work'}")


def _gauge_from_lease(data: dict) -> None:
    """The lease answer is where the balance arrives now: with the lease a Machine no longer reports each charge,
    so the usage-report response that used to carry it never comes, and an account with Energy saw an unlit
    gauge. The answer may also carry the plan's gauge facts — `cycle_energy` (what this cycle made available),
    `scale` (the gauge's full scale) and `tier` — which make the gauge «the plan's Energy minus what was spent»
    instead of a guess from the highest balance ever seen. Never raises: presentation bookkeeping."""
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
        # The fresh balance as granted: the lease's spend counter is reset right after this, so subtracting the
        # previous lease's spend here would show a dip that never happened.
        emit("energy", "saldo", extra={**_em.snapshot(), "balance": b})
    except Exception as e:  # noqa: BLE001
        logger.debug(f"energy_lease: gauge event not emitted: {e!r}")


_GAUGE_EVERY_S = 3.0
_gauge_told = {"at": 0.0}


def _tell_gauge() -> None:
    """The gauge goes down as the agent works: one `energy` event at most every few seconds, carrying the balance
    the gauge would read now (`energy_meter.snapshot`). A spend is local under a lease, so nothing else tells it."""
    now = time.time()
    if now - _gauge_told["at"] < _GAUGE_EVERY_S:
        return
    _gauge_told["at"] = now
    try:
        from nucleo.energy import meter as energy_meter
        from voice.observer import emit
        snap = energy_meter.snapshot()
        if snap.get("known"):
            emit("energy", "saldo", extra={"balance": snap["balance"], "capacity": snap["capacity"]})
    except Exception as e:  # noqa: BLE001 — the gauge is presentation; a spend never fails for it
        logger.debug(f"energy_lease: gauge not told: {e!r}")


def note_spend(energy: float) -> None:
    """Descuenta del contador local. Se llama en el MISMO gesto que reportar el consumo a la nube, pero
    sin esperar a la respuesta: es una resta, no una consulta. Nunca lanza."""
    if not enabled() or not energy or energy <= 0:
        return
    try:
        _load_once()
        _state["spent"] = float(_state["spent"]) + float(energy)
        _persist()
        _tell_gauge()
        if remaining() <= 0:
            # THE SLICE IS SPENT, NOT THE ACCOUNT. One charge can exceed the whole lease (a worker bills its run
            # when it ends), and stopping here told someone with most of his balance left that it was gone. Ask
            # for another lease now; stop only if the endpoint says no or cannot be reached (V2-801).
            _schedule(_renew_or_blow(reason="exhausted"))
        elif expired():
            # EXPIRED IS NOT EXHAUSTED, and conflating them cost a daily outage. A machine left on
            # overnight without spending wakes up with a stale lease and an untouched balance; stopping
            # there shuts down the agent of someone whose account is full, and the retry loop sleeps a
            # whole minute before its first attempt. Ask for another lease, and stop ONLY if the cloud
            # says no or does not answer — which is what the fuse exists to cover.
            _schedule(_renew_or_blow())
        elif float(_state["spent"]) >= float(_state["granted"]) * _RENEW_AT or _near_expiry():
            _schedule(ensure(reason="half_spent"))
    except Exception as e:  # noqa: BLE001 — contar jamás puede tumbar el turno que lo disparó
        logger.warning(f"energy_lease.note_spend falló (no fatal): {e}")


async def _renew_or_blow(reason: str = "expired") -> None:
    """The lease ran out — by CLOCK or by AMOUNT. Ask for another, a few times, then ask the question that matters.

    We do not check whether `ensure` returned True, we check `allowed()`. The difference matters: on a
    NETWORK failure `ensure` answers "there is still leased balance" — correct while the lease is alive,
    useless once it has run out. `allowed()` is the predicate every caller obeys, so an outage against
    the cloud still ends in a stop. Fail-closed without giving up the normal case.

    The attempts follow `_RECOVER_DELAYS`: a redeploy or a dropped connection is seconds long, and one failed
    request is not a reason to stop an agent. An ANSWERED no ends the attempts at once (the request already
    stopped, with `CAUSE_DENIED`); running out of attempts stops with `CAUSE_UNRENEWED`. Single-flight."""
    global _recovering
    if _recovering:
        return
    _recovering = True
    try:
        for delay in _RECOVER_DELAYS or (0.0,):
            if delay:
                await asyncio.sleep(delay)
            for _ in range(200):                      # a request already in flight answers for us: wait for it
                if not _renewing:
                    break
                await asyncio.sleep(0.05)
            try:
                await ensure(reason=reason, force=True)
            except Exception as e:  # noqa: BLE001
                logger.warning(f"energy_lease: renewal ({reason}) failed: {e}")
            if allowed() or _state.get("cause") == CAUSE_DENIED:
                return
    finally:
        _recovering = False
    if not allowed():
        if _state.get("cause") != CAUSE_DENIED:
            _state["cause"] = CAUSE_UNRENEWED
            _persist()
        logger.warning(f"energy_lease: lease not renewed after {len(_RECOVER_DELAYS) or 1} attempt(s) ({reason})")
        _blow_fuse()


def _server_loop():
    """The event loop to run lease work on when the spend happens in a worker thread. A spend metered inside
    `asyncio.to_thread` has no running loop: dropping the renewal there let a long background job spend a lease
    to zero with the renewal never asked, and the fuse stopped an account with 200 Energy left."""
    try:
        from nucleo.energy import meter as energy_meter
        return energy_meter._loop
    except Exception:  # noqa: BLE001
        return None


def _schedule(coro) -> None:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        loop = _server_loop()
        if loop is None or loop.is_closed():
            coro.close()
            return
        asyncio.run_coroutine_threadsafe(coro, loop)
        return
    asyncio.create_task(coro)


def _blow_fuse(*, verdict: bool = False) -> None:
    """Se acabó el arriendo y no ha llegado otro. Para de verdad, y que se VEA — un corte silencioso es
    la peor versión de esto (el operador se enteró una vez por un cartel, sin haber visto nunca el
    saldo bajar).

    ARRANCANDO NO ES AGOTADO. Al arrancar se pide el arriendo como tarea, así que hay una ventana en la
    que todavía no ha llegado; una operación temprana ahí caería en «remaining()==0» y pararía el agente
    para que `_maybe_resume` lo volviera a arrancar un segundo después. Ese parpadeo no protege de nada
    y da la peor impresión posible. Mientras la petición está EN VUELO se deja pasar: el sobregasto
    posible es de una operación, que es exactamente el orden de magnitud que este diseño presupuesta."""
    # `verdict`: the cloud ANSWERED no. The in-flight exception is for a request with no answer yet; the denial
    # itself runs inside that request (`_renewing` is still True), and without this flag a denied boot lease
    # never stopped anything — measured 2026-10-22 on an account with nothing to lease.
    # In flight means ANY pending lease request — boot, renewal, or a recovery between attempts — whether or not
    # a lease was held before: the stop decision waits for the answer, which is what makes it the right one.
    if _in_flight() and not verdict:
        logger.debug("energy_lease: a lease request is in flight — no stop decision yet")
        return
    cause = CAUSE_DENIED if verdict else (_state.get("cause") or CAUSE_UNRENEWED)
    try:
        from nucleo import runstate
        if not runstate.stopped():     # already stopped: the notice and the retry below still have to happen
            logger.warning("energy_lease: arriendo agotado — PARANDO las operaciones de pago")
            _schedule(runstate.stop(src=STOP_SRC))
    except Exception as e:  # noqa: BLE001
        logger.warning(f"energy_lease: no se pudo parar por arriendo agotado: {e}")
    try:
        from nucleo.energy import limits as account_limits
        account_limits.request_close(cause)
    except Exception:  # noqa: BLE001
        pass
    _start_retry()


# Reintento mientras estamos parados por energía. SIN ESTO EL FUSIBLE ES UNA TRAMPA: la renovación se
# dispara al GASTAR, y parados no se gasta — así que recargar el saldo no despertaría nunca a la
# máquina y la única salida sería reiniciarla a mano. Encontrado desplegándolo, no razonándolo.
_RETRY_S = float(os.getenv("ENERGY_LEASE_RETRY_S", "60"))
_retry_task = None


def _start_retry() -> None:
    global _retry_task
    if _retry_task is not None and not _retry_task.done():
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = _server_loop()
        if loop is None or loop.is_closed():
            return
        _retry_task = asyncio.run_coroutine_threadsafe(_retry_loop(), loop)
        return
    _retry_task = loop.create_task(_retry_loop())


async def _retry_loop() -> None:
    """Pide arriendo hasta conseguirlo. Termina SOLO al lograrlo (o al agotar los intentos), y es
    `ensure(force=True)` porque el estado local dice «no queda nada» — sin forzar se creería al día y
    no preguntaría. The wait grows from a few seconds up to `_RETRY_S`: a stop for a lease that could not be
    renewed is usually over as soon as the endpoint is back, and a full minute before the first try kept an agent
    stopped for nothing (V2-801)."""
    intentos = 0
    while intentos < int(os.getenv("ENERGY_LEASE_RETRY_MAX", "2880")):   # ~48 h a un intento/minuto
        intentos += 1
        await asyncio.sleep(min(_RETRY_S, 5.0 * (2 ** (intentos - 1))))
        try:
            if await ensure(reason="retry_after_exhaustion", force=True):
                logger.info(f"energy_lease: arriendo recuperado tras {intentos} intento(s)")
                return
        except Exception as e:  # noqa: BLE001
            logger.debug(f"energy_lease: reintento {intentos} falló: {e}")
    logger.warning("energy_lease: se agotaron los reintentos de arriendo; hace falta intervención")


async def ensure(*, reason: str = "boot", force: bool = False) -> bool:
    """Pide un arriendo si hace falta. Devuelve si al terminar hay uno utilizable.

    Single-flight: varias operaciones cruzando el 50% a la vez piden UNA renovación, no N."""
    global _renewing
    if not enabled():
        return True
    _load_once()
    if not force and remaining() > 0 and not _near_expiry() and \
            float(_state["spent"]) < float(_state["granted"]) * _RENEW_AT and _gauge_knows():
        return True
    if _renewing:
        return remaining() > 0
    _renewing = True
    try:
        return await _request(reason)
    finally:
        _renewing = False


def _gauge_knows() -> bool:
    """Does the Energy gauge know the balance? Only a lease ANSWER tells it, so a Machine that boots on a lease it
    persisted would show an unlit gauge until the next renewal — up to half an hour. Not knowing is a reason to ask."""
    try:
        from nucleo.energy import meter as energy_meter
        return bool(energy_meter.snapshot().get("known"))
    except Exception as e:  # noqa: BLE001 — unreadable means «ask», the safe side for a display
        logger.debug(f"energy_lease: gauge state unreadable: {e!r}")
        return False


async def _request(reason: str) -> bool:
    from nucleo.energy import account as cloud_account

    url = (os.getenv("CONTROL_PLANE_URL") or "").strip()
    if not url:
        # Sin control-plane configurado no hay a quién pedirle un arriendo. En una cuenta de nube eso
        # es una avería, no un permiso: `allowed()` seguirá diciendo que no y el fusible saltará.
        logger.warning("energy_lease: CONTROL_PLANE_URL sin configurar — no se puede arrendar energía")
        return False
    token = (os.getenv("CONTROL_PLANE_SERVICE_TOKEN") or "").strip()
    payload = {"machine_id": (os.getenv("FLY_MACHINE_ID") or "").strip() or None,
               "spent": round(float(_state["spent"]), 6), "reason": reason}
    try:
        async with httpx.AsyncClient(timeout=5.0) as c:
            r = await c.post(url.rstrip("/") + _PATH, json=payload,
                             headers={"X-Service-Token": token} if token else {})
        data = r.json() if r.status_code < 500 else None
    except Exception as e:  # noqa: BLE001
        # No se pudo renovar. NO se toca el arriendo actual: lo que quede sigue sirviendo, y si se agota
        # antes de que la nube vuelva, el fusible hace su trabajo. Eso es exactamente lo que se quería.
        logger.warning(f"energy_lease: renovación fallida ({reason}), se sigue con lo que quede: {e}")
        return remaining() > 0
    if not isinstance(data, dict) or "ok" not in data:
        # NOT AN ANSWER. A 5xx (a redeploy, an overloaded worker) or a body without `ok` says nothing about the
        # account. It used to fall through as `{}` → «not ok» → a VERDICT: the lease was zeroed and the agent
        # stopped as if the account were empty. It is a failed renewal, exactly like a timeout (V2-801).
        logger.warning(f"energy_lease: no lease answer ({reason}, HTTP {r.status_code}), se sigue con lo que quede")
        return remaining() > 0

    # TARIFFS ON THE FLY. The lease response may carry a tariff table, which is adopted ANTES de mirar el veredicto: son válidos igualmente si la nube niega el
    # arriendo, y perderlos por un «no gastes» dejaría a la instancia midiendo con precios viejos en
    # cuanto volviera a haber saldo. Viajan aquí, y no por un endpoint propio, porque el arriendo es la
    # única llamada periódica que el motor YA hace: un `GET /tarifas` añadiría una llamada de red, un
    # modo de fallo y un reloj nuevos para mover un puñado de números que cambian una vez al mes.
    # `update()` rechaza un payload vacío o corrupto por su cuenta — ausencia no es una instrucción.
    try:
        energy_tariffs.update(data.get("tariffs"), source="lease")
    except Exception as e:  # noqa: BLE001
        logger.warning(f"energy_lease: no se pudieron aplicar las tarifas centrales: {e}")
    # …and the balance (with the plan's gauge facts), which the gauge has no other way to learn under a lease.
    _gauge_from_lease(data)

    granted = float(data.get("energy") or 0.0)
    if not data.get("ok") or granted <= 0:
        # CUALQUIER negativa con respuesta es un VEREDICTO, y todo veredicto significa lo mismo: no
        # gastes. No se mira el motivo. Hubo una versión que solo paraba ante «insufficient_energy» y
        # eso es una trampa de mantenimiento: el día que la nube añade una razón nueva —cuenta
        # caducada, suspendida, lo que venga— el motor la ignoraría y seguiría gastando, en silencio y
        # sin que ningún test lo note. El motivo se registra para el operador; la DECISIÓN no depende
        # de él. Lo que sí se distingue es veredicto vs AVERÍA: un fallo de red sale antes (arriba) y
        # deja vivo lo que quede, que es justo lo contrario.
        motivo = data.get("error") or data.get("reason") or "sin_motivo"
        logger.warning(f"energy_lease: la nube NIEGA el arriendo ({motivo}) — se paran las operaciones de pago")
        _state.update({"granted": 0.0, "spent": 0.0, "expires_at": 0.0, "at": time.time(), "cause": CAUSE_DENIED})
        _persist()
        _blow_fuse(verdict=True)
        return False

    ttl = float(data.get("ttl_s") or 1800)
    _state.update({"lease_id": data.get("lease_id"), "granted": granted, "spent": 0.0,
                   "expires_at": time.time() + ttl, "at": time.time(), "cause": None})
    _persist()
    logger.info(f"energy_lease: arriendo de {granted:.2f} Energy por {ttl:.0f}s ({reason}), "
                f"user={cloud_account.my_user_id()}")
    _maybe_resume()
    try:
        from nucleo.energy import limits as account_limits
        account_limits.clear_exhausted()            # a lease is the end of "out of energy", whatever caused it
    except Exception as e:  # noqa: BLE001
        logger.debug(f"energy_lease: could not clear the out-of-energy state: {e!r}")
    return True


def _maybe_resume() -> None:
    """Llegó arriendo nuevo. Si el que paró fuimos NOSOTROS, arrancamos; si paró el OPERADOR, ni
    tocarlo. Encender algo que una persona apagó a mano es de las cosas que más desconfianza generan."""
    try:
        from nucleo import runstate
        if runstate.stopped() and runstate.snapshot().get("src") == STOP_SRC:
            logger.info("energy_lease: arriendo repuesto — se reanuda lo que paramos por energía")
            _schedule(runstate.start(src=STOP_SRC))
    except Exception as e:  # noqa: BLE001
        logger.warning(f"energy_lease: no se pudo reanudar tras renovar: {e}")


def snapshot() -> dict:
    """Para `/api/energy` y el visor. `leased=False` en self-host: allí no hay arriendo que enseñar."""
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
