#
# ARRIENDO DE ENERGÍA — el techo que la propia máquina se vigila (2026-08-13).
#
# EL PROBLEMA. `energy_meter` reporta cada gasto y lee el saldo que le devuelve la respuesta; si llega a
# cero, cierra la sesión. Eso funciona MIENTRAS el enlace con la nube esté vivo. Cuando no lo está —y
# alguna vez no lo estará— `balance` viene a `None`, `account_limits.should_close(None)` dice que no (y
# hace bien: un timeout no es una autorización), y esta máquina **sigue gastando sin techo** hasta que
# alguien lo note. El radio de daño no está acotado por nada.
#
# LO QUE NO SE HACE, Y POR QUÉ. Lo obvio sería pedir permiso antes de cada operación. Se descartó: mete
# una ida y vuelta de red en el camino crítico de CADA frase de voz para ganar una precisión que, con el
# margen de este negocio, no vale nada. Una frase cuesta céntimos; pasarse un poco es barato, esperar es
# caro.
#
# LO QUE SE HACE. La nube concede un ARRIENDO —una cantidad de Energy y una fecha— y mientras quede,
# esta máquina **gasta sin preguntar a nadie**: cada operación es una resta en un contador en proceso.
# Cero red en régimen. La renovación se pide de fondo al llegar a la mitad, así que nunca se espera por
# ella. Y si el arriendo se agota sin que llegue el siguiente, la máquina **se para a sí misma**.
#
# Eso último es lo que convierte «reactivo» de una renuncia en un diseño: el fail-closed vive DENTRO del
# inquilino, no en el gateway. Si la nube se cae, el usuario sigue trabajando con lo que le quede y luego
# corta — no gasta sin techo hasta que nos enteremos. Pérdida máxima en el peor caso = un arriendo, que
# es un número que se decide, no una esperanza.
#
# EL MARGEN NO ESTÁ AQUÍ. La nube corta la suma de arriendos un poco antes del saldo real, para que el
# exceso inevitable caiga DENTRO de la ventana autorizada. Este lado no conoce ese margen a propósito: si
# lo conociera, un motor comprometido podría gastárselo.
#
# SE REUTILIZA EL INTERRUPTOR QUE YA EXISTE. Agotarse no inventa una forma nueva de parar: llama a
# `nucleo/runstate.stop()`, la misma que el ⏻ del operador (V2-092), que ya congela workers y suspende
# los widgets que producen. Con una asimetría deliberada: si paramos NOSOTROS por energía, al renovar
# arrancamos solos; si paró el OPERADOR, no lo tocamos. La intención es de quien la tuvo.
#
# SELF-HOST NO EXISTE AQUÍ. `enabled()` es falso sin cuenta de nube → `allowed()` siempre True, cero
# estado, cero red. Quien se auto-hospeda paga sus propias APIs y no le arrienda energía nadie.
#
from __future__ import annotations

import asyncio
import os
import time

import httpx
from loguru import logger

# Quién nos paró. Sirve para no pisar una parada del operador al renovar (ver la asimetría de arriba).
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
_state: dict = {"lease_id": None, "granted": 0.0, "spent": 0.0, "expires_at": 0.0, "at": 0.0}
_loaded = False
_renewing = False


def enabled() -> bool:
    from nucleo import cloud_account
    return cloud_account.is_cloud_account()


def _load_once() -> None:
    global _loaded
    if _loaded:
        return
    _loaded = True
    try:
        import memory
        raw = memory.kv_get(_KV_KEY)
        if isinstance(raw, dict):
            _state.update({k: raw.get(k, _state[k]) for k in _state})
    except Exception as e:  # noqa: BLE001 — sin arriendo guardado se pide uno nuevo, no se rompe nada
        logger.debug(f"energy_lease: no se pudo leer el arriendo guardado: {e}")


def _persist() -> None:
    try:
        import memory
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


def allowed() -> bool:
    """¿Puede esta máquina empezar algo que cueste dinero?

    Sin cuenta de nube, siempre. Con cuenta de nube, **solo con arriendo vivo**: sin arriendo la
    respuesta es NO, no «adelante hasta que alguien diga lo contrario». Es la diferencia entre
    fail-closed y el `guarded-until-configured` que nos costó nueve días de nube abierta."""
    if not enabled():
        return True
    return remaining() > 0 and not expired()


def note_spend(energy: float) -> None:
    """Descuenta del contador local. Se llama en el MISMO gesto que reportar el consumo a la nube, pero
    sin esperar a la respuesta: es una resta, no una consulta. Nunca lanza."""
    if not enabled() or not energy or energy <= 0:
        return
    try:
        _load_once()
        _state["spent"] = float(_state["spent"]) + float(energy)
        _persist()
        if remaining() <= 0 or expired():
            _blow_fuse()
        elif float(_state["spent"]) >= float(_state["granted"]) * _RENEW_AT:
            _schedule(ensure(reason="half_spent"))
    except Exception as e:  # noqa: BLE001 — contar jamás puede tumbar el turno que lo disparó
        logger.warning(f"energy_lease.note_spend falló (no fatal): {e}")


def _schedule(coro) -> None:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        coro.close()
        return
    asyncio.create_task(coro)


def _blow_fuse() -> None:
    """Se acabó el arriendo y no ha llegado otro. Para de verdad, y que se VEA — un corte silencioso es
    la peor versión de esto (el operador se enteró una vez por un cartel, sin haber visto nunca el
    saldo bajar).

    ARRANCANDO NO ES AGOTADO. Al arrancar se pide el arriendo como tarea, así que hay una ventana en la
    que todavía no ha llegado; una operación temprana ahí caería en «remaining()==0» y pararía el agente
    para que `_maybe_resume` lo volviera a arrancar un segundo después. Ese parpadeo no protege de nada
    y da la peor impresión posible. Mientras la petición está EN VUELO se deja pasar: el sobregasto
    posible es de una operación, que es exactamente el orden de magnitud que este diseño presupuesta."""
    if _renewing and not float(_state["granted"]):
        logger.debug("energy_lease: sin arriendo todavía pero se está pidiendo — no se para")
        return
    try:
        from nucleo import runstate
        if runstate.stopped():
            return
        logger.warning("energy_lease: arriendo agotado — PARANDO las operaciones de pago")
        _schedule(runstate.stop(src=STOP_SRC))
    except Exception as e:  # noqa: BLE001
        logger.warning(f"energy_lease: no se pudo parar por arriendo agotado: {e}")
    try:
        from nucleo import account_limits
        account_limits.request_close("energy_lease_exhausted")
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
        return
    _retry_task = loop.create_task(_retry_loop())


async def _retry_loop() -> None:
    """Pide arriendo hasta conseguirlo. Termina SOLO al lograrlo (o al agotar los intentos), y es
    `ensure(force=True)` porque el estado local dice «no queda nada» — sin forzar se creería al día y
    no preguntaría."""
    intentos = 0
    while intentos < int(os.getenv("ENERGY_LEASE_RETRY_MAX", "2880")):   # ~48 h a un intento/minuto
        intentos += 1
        await asyncio.sleep(_RETRY_S)
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
    if not force and remaining() > 0 and not expired() and \
            float(_state["spent"]) < float(_state["granted"]) * _RENEW_AT:
        return True
    if _renewing:
        return remaining() > 0
    _renewing = True
    try:
        return await _request(reason)
    finally:
        _renewing = False


async def _request(reason: str) -> bool:
    from nucleo import cloud_account

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
        data = r.json() if r.status_code < 500 else {}
    except Exception as e:  # noqa: BLE001
        # No se pudo renovar. NO se toca el arriendo actual: lo que quede sigue sirviendo, y si se agota
        # antes de que la nube vuelva, el fusible hace su trabajo. Eso es exactamente lo que se quería.
        logger.warning(f"energy_lease: renovación fallida ({reason}), se sigue con lo que quede: {e}")
        return remaining() > 0

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
        _state.update({"granted": 0.0, "spent": 0.0, "expires_at": 0.0, "at": time.time()})
        _persist()
        _blow_fuse()
        return False

    ttl = float(data.get("ttl_s") or 1800)
    _state.update({"lease_id": data.get("lease_id"), "granted": granted, "spent": 0.0,
                   "expires_at": time.time() + ttl, "at": time.time()})
    _persist()
    logger.info(f"energy_lease: arriendo de {granted:.2f} Energy por {ttl:.0f}s ({reason}), "
                f"user={cloud_account.my_user_id()}")
    _maybe_resume()
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
            "expires_at": float(_state["expires_at"] or 0.0), "allowed": allowed()}


def _reset_for_tests() -> None:
    global _loaded, _renewing
    _state.update({"lease_id": None, "granted": 0.0, "spent": 0.0, "expires_at": 0.0, "at": 0.0})
    _loaded = False
    _renewing = False
