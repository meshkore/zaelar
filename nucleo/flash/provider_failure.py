"""nucleo/flash/provider_failure.py — QUÉ hacer cuando el stream del modelo revienta, decidido UNA vez.

Existe porque la misma decisión estaba escrita dos veces, y esa duplicación ha mordido TRES veces:

  · 2026-08-18 (V2-118…121, `22f3674`): `probe.py` es la implementación PARALELA del provider de voz, y el arnés
    corre por ese canal. Las tags `[[cron.create]]` se CAPTURABAN allí y no se ejecutaban, así que un aviso
    programado no podía existir por esa vía — el mecanismo era INALCANZABLE para todo lo que se midiera.
  · 2026-08-15: el relevo ante un fallo DURO se añadió a la voz y no aquí.
  · 2026-08-21, y es lo que dejó al arnés **ocho horas sin poder medir**: con la cadena real sembrada
    (`deepseek-directo → aimlapi-failover`), un turno de texto devolvía
    `{"ok":false,"error":"modelo: 402 Insufficient Balance"}` **en el mismo segundo** en que el log decía
    «`deepseek-directo` SIN SALDO → relevo a `aimlapi-failover`». La voz relevaba, i18n relevaba, el texto no.

O sea: no es que faltara la política, es que **el canal de texto no la aplicaba**. Dos copias de una decisión se
separan sin avisar, y el aviso llega cuando alguien mide algo que sale mal por un motivo que no es el que mide.

Lo que se comparte es la DECISIÓN (¿atasco o fallo duro? ¿a qué escalón se releva? ¿queda alguno?). Lo que NO se
comparte —a propósito— es qué le dice cada canal al operador: la voz habla, el canal de texto devuelve un objeto.
"""
from __future__ import annotations

from loguru import logger


def tier_for(spec, role: str):
    """El escalón de la cadena con el que corrió ESTE turno, o None si no se reconoce.

    V2-252 — hay DOS fuentes de «quién es el titular» y no siempre dicen lo mismo: el turno compone su spec con
    `spec_from_config()` (que lee `fast.model` / `fast.base_url`) y la cadena se ordena por `fast.providers`.
    El arnés lo midió el 2026-08-21 al reordenar la escalera y ver que **no cambiaba nada**.

    Importa aquí porque `note_failure` sin `tier` pregunta a `pick()`, o sea «el que se elegiría AHORA» — que
    tras un reorden puede no ser el que acaba de fallar. Entonces el cooldown cae sobre un proveedor SANO y el
    roto sigue elegido: castigar al inocente y dejar suelto al culpable, en silencio. Se resuelve por el
    `base_url` con el que se hizo la llamada, que es el único dato que no puede mentir sobre quién contestó.
    """
    try:
        url = (spec.resolved_base_url() or "").strip().rstrip("/") if spec is not None else ""
    except Exception:  # noqa: BLE001
        url = ""
    if not url:
        return None
    try:
        from nucleo.flash import provider_chain as pc
        for t in pc.chain(role):
            if (t.get("base_url") or "").strip().rstrip("/") == url:
                return t
    except Exception:  # noqa: BLE001
        pass
    return None


def handle(err_text: str, *, role: str, stalled: bool = False, spec=None) -> dict:
    """Marca el escalón, registra la salud, y devuelve `{relay, dry}`.

    · `relay` = el escalón al que ir, o None si no hay a dónde (o si el error no es del proveedor).
    · `dry`   = la cadena se quedó SIN ningún escalón sano (V2-243): eso cambia lo que se le dice al operador,
                porque «¿me lo repites?» es mentira cuando no queda a quién preguntar.

    Fail-soft entero: esto corre dentro del manejador de errores de un turno y no puede añadir una excepción a la
    que ya hubo.
    """
    from nucleo.flash import provider_chain as pc

    relay = None
    culpable = tier_for(spec, role)          # el que REALMENTE corrió; None → que lo decida `pick()`, como antes
    try:
        if stalled:
            # V2-246: un atasco aislado es ruido; dos seguidos son un escalón que no sirve.
            relay = pc.note_stall(role=role, tier=culpable)
        else:
            relay = pc.note_failure(err_text, role=role, tier=culpable)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"provider_failure({role}): no pude anotar el fallo: {e!r}")
    dry = False
    try:
        dry = pc.pick(role) is None
    except Exception:  # noqa: BLE001
        pass
    try:
        from voice import health_state, llm_health
        if stalled:
            health_state.record("llm", "slow", "un turno se atascó sin respuesta y lo corté")
        else:
            health_state.record("llm", llm_health.classify(err_text) or "error",
                                (err_text or "")[:200] or "flash brain down")
    except Exception:  # noqa: BLE001
        pass
    return {"relay": relay, "dry": dry}
