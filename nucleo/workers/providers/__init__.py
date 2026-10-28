"""nucleo/workers/providers/ — CADENA de proveedores del Brain Worker, con relevo automático (2026-08-02).

**Quién conduce siempre es Claude Code** (el CLI `claude`); lo que cambia por debajo es a QUÉ endpoint
Anthropic-compatible apunta (`ANTHROPIC_BASE_URL` + `ANTHROPIC_AUTH_TOKEN`). Eso ya existía para UN proveedor
(Z.AI GLM, `v2.external_worker_env()`); lo que faltaba —y costó una sesión— es que hubiera MÁS DE UNO y que el
relevo fuera solo.

Incidente que lo motiva: el plan de Z.AI agotó su cuota semanal («[1310] Weekly/Monthly Limit Exhausted. Your
limit will reset at 2026-08-04») EN MITAD de una tarea. El worker murió, el operador se quedó sin resultado, y el
panel de alertas —que existe justo para esto— no dijo ni una palabra: `balances._REACTIVE_MAP` no tenía entrada
para el proveedor de los workers, así que su 429 no llegaba a ninguna parte. Un único proveedor de suscripción es
un punto único de fallo con fecha de caducidad semanal.

DISEÑO
------
- **Cadena ordenada de escalones.** Se prueba el primero SANO. Un escalón solo existe si su credencial está
  presente — no se ofrece nunca un proveedor sin token.
- **Agotado ≠ roto.** Un 429/cuota marca ESE escalón en cooldown (hasta la fecha de reset que da el propio
  proveedor, si la dice) y pasa al siguiente. Un error de credencial marca más corto: puede ser un despiste.
- **Suscripción, no pago por token** (regla del operador): los escalones son planes de coding con forfait
  (Z.AI, Kimi/Moonshot…), no APIs facturadas por token. Dos suscripciones baratas cubren el hueco de una.
- **La licencia local es el ÚLTIMO escalón y solo en local**: `claude` logueado en el navegador no corre en un
  contenedor, así que en cloud ese escalón no se ofrece — ahí la cobertura la dan dos tokens de suscripción.
- **Fail-open**: sin config ni credenciales, `env_for_worker()` devuelve {} y todo se comporta como antes.
"""
from __future__ import annotations

import os
import re
import time

from loguru import logger

# KNOWN Anthropic-compatible endpoints (drive Claude Code via `ANTHROPIC_BASE_URL`). A tier joins the chain only if
# its env var has a value, so listing it activates nothing. Adding one = one line.
KNOWN: list[dict] = [
    # ⚠️ `vision: False` — MEASURED 2026-08-27, against the provider's claim: the gateway passes an image URL the
    # model cannot fetch; `glm-5.3` says so, `glm-4.6`/`4.5v`/`4.6v` confabulate (pure red → "Orange", blue →
    # "Teal"). Z.ai's native `paas/v4` vision answers `1113 Insufficient balance` (a different wallet). The
    # browser's vision path (V2-049) sends a screenshot per action, so `vision_env()` sets `ZAELAR_NAV_VISION=0`
    # and the worker goes DOM. V2-500: `config/models.default.json` decides who and which model; one holder + ONE
    # failover (Z.AI coding plan, DeepSeek Anthropic endpoint); both `vision: False`, measured.
]


def _known_from_table() -> list[dict]:
    from config import models as _tabla
    return _tabla.chain_for("brain_worker", names=("z.ai", "deepseek"))


KNOWN = _known_from_table()

# Escalón final SOLO LOCAL: sin base_url el CLI usa la licencia con la que el operador ya está logueado. No
# necesita credencial y por eso no puede fallar por cuota de API — pero consume su licencia, así que va el último.
LICENSE_TIER = {"name": "licencia-claude", "base_url": "", "env": [], "plan": "licencia local de Claude Code",
                "local_only": True}

# Cooldown mechanics shared with the voice/cluster sibling module (V2-098) — the STATE stays separate on purpose
# (its own KV namespace: a CLI endpoint being down says nothing about a MODEL tier being down), only
# load/save/token/available.
from nucleo.provider_health import CooldownStore, token_for as _token_for

_DEFAULT_COOLDOWN_S = 30 * 60          # sin fecha de reset explícita: media hora y se reintenta
_DEPLETED_COOLDOWN_S = 20 * 60         # V2-243 lo puso en 6 h («un saldo no se repone solo»). Cierto salvo en
                                       # one case that matters: the operator TOPS UP. Measured 2026-08-27: a
                                       # 402 at 18:55 parked the holder past midnight despite a 19:40 top-up,
                                       # and the brain went MUTE when the relay fell. Parole costs ~3 failed
                                       # calls/h; not having it cost six hours of silence.
_BROKEN_COOLDOWN_S = 15 * 60           # V2-682: a rejected REQUEST is our config or their deploy — both get
                                       # fixed in minutes, so the tier is retried soon rather than parked.
_AUTH_COOLDOWN_S = 5 * 60              # credencial mal: puede ser un despiste, no castigues una semana
_KV = "worker_provider_cooldown"

_store = CooldownStore(_KV)


# ── cadena ────────────────────────────────────────────────────────────────────────────────────────────────


def _is_container() -> bool:
    """En cloud la licencia local no existe (no hay login de navegador dentro de un contenedor)."""
    try:
        from config import doctor
        return bool(doctor.hardware().get("container"))
    except Exception:
        return False


def chain() -> list[dict]:
    """Escalones ordenados y DISPONIBLES (con credencial resoluble). El primero es el preferido.

    Orden: lo que diga `code_agent.providers` (si el operador lo ordenó a mano) → si no, el `base_url` clásico de
    `code_agent` como cabeza + el resto del catálogo conocido → y la licencia local al final."""
    tiers: list[dict] = []
    try:
        from config import v2
        cfg = v2.get("code_agent") or {}
    except Exception:
        cfg = {}

    explicit = cfg.get("providers")
    if isinstance(explicit, list) and explicit:
        for t in explicit:
            if isinstance(t, dict) and t.get("name"):
                tiers.append(_with_measured_traits(dict(t)))
    else:
        head = (cfg.get("base_url") or "").strip()
        known = [dict(k) for k in KNOWN]
        if head:                                    # el configurado manda, esté o no en el catálogo
            match = next((k for k in known if k["base_url"] == head), None)
            if match:
                known.remove(match)
                tiers.append(match)
            else:
                tiers.append({"name": head.split("//")[-1].split("/")[0], "base_url": head,
                              "env": ["Z_AI_API_KEY"], "plan": "configurado a mano"})
        tiers += known
        tiers.append(dict(LICENSE_TIER))

    model = (cfg.get("model") or "").strip()
    head = (cfg.get("base_url") or "").strip()
    container = _is_container()
    out = []
    for t in tiers:
        if t.get("local_only") and container:
            continue                                # en cloud no hay licencia de navegador
        if t.get("base_url") and not _token_for(t) and not (t.get("api_key") or "").strip():
            continue                                # sin credencial no es un escalón, es un espejismo
        # The model is TIED to its tier: inheriting `glm-5.2` on the licence killed the first relay instantly.
        # No declared model → "" and each provider uses its default.
        if not t.get("model"):
            t["model"] = model if (t.get("base_url") and t["base_url"] == head) else ""
        out.append(t)
    return out


def _with_measured_traits(tier: dict) -> dict:
    """A hand-ordered tier inherits what the CATALOGUE has MEASURED about the same provider (V2-320).

    `code_agent.providers` lets the operator order the chain by hand, and that list is a COPY of catalogue
    entries made at some past moment. Ordering is a preference — his to set. Capability is not: whether a model
    can read an image is a fact about the model, measured once and true afterwards, and a copy made before the
    measurement silently drops it.

    Which is exactly what happened. `KNOWN`'s DeepSeek rung carries `vision: False` — V4 does not read images,
    measured on `search-buy-guitar__es` (2026-08-24 11:23), where the worker did a `Read` of the screenshot and
    answered «La captura no se pudo leer (formato no soportado). Sigo por DOM», twice, and narrated it to the
    operator. The hand-ordered copy in `config/v2.json` has no such key, so `vision_env()` saw nothing to
    declare, `ZAELAR_NAV_VISION` stayed unset, and the browser path kept sending a 300-530 KB PNG on EVERY
    action to a model that cannot open it.

    The rung was inert while DeepSeek had no balance, so nothing showed. The moment the account was topped up
    (2026-08-25) it became the first healthy tier again — and a top-up is the last event anybody would connect
    to a blind browser.

    What the operator WROTE always wins: only keys absent from his entry are filled in. Matching is by
    `base_url` first — the endpoint IS the identity, a renamed copy is still the same provider — and by name
    as a fallback.
    """
    known = next((k for k in KNOWN if k.get("base_url") and k["base_url"] == (tier.get("base_url") or "")), None)
    if known is None:
        known = next((k for k in KNOWN if k.get("name") == tier.get("name")), None)
    if known is None:
        return tier
    for key in _MEASURED_TRAITS:
        if key not in tier and key in known:
            tier[key] = known[key]
    return tier


#: Facts about what a provider CAN DO, as opposed to which one we prefer. These travel with the endpoint; the
#: order does not. Kept as a list rather than "copy everything missing" so that adding a catalogue key is a
#: deliberate act: silently inheriting `plan` or `model` would override what the operator chose on purpose.
_MEASURED_TRAITS = ("vision",)


def pick() -> dict | None:
    """El primer escalón SANO de la cadena. None si no hay ninguno (→ el CLI se comporta como siempre)."""
    for t in chain():
        if _store.available(t["name"]):
            return t
    return None


def relayed() -> bool:
    """¿Estamos corriendo en un escalón DISTINTO del configurado? Solo entonces hay que tocar el modelo: mientras
    se use el proveedor de siempre, el modelo por invocación (`code_agent.model_*`) manda como toda la vida."""
    try:
        from config import v2
        head = ((v2.get("code_agent") or {}).get("base_url") or "").strip()
    except Exception:
        return False
    return (pick() or {}).get("base_url", "") != head


def unrouted_refusal(task_id: str = "") -> str:
    """Why a worker is not launched in a container with no routed tier (V2-778 F5-40), said as an `alert` the
    operator's view and the observability viewer read. Returns the sentence the session ends with."""
    why = ("no hay ningún proveedor de worker disponible en este contenedor (cadena agotada o sin clave): "
           "el worker no se lanza sin enrutar")
    try:
        from voice.observer import emit as _emit
        _emit("alert", "🧯 worker sin proveedor en contenedor", text=why, role="system",
              extra={"task": task_id, "cat": "worker", "is_error": True})
    except Exception:  # noqa: BLE001
        pass
    return why


def env_for_worker() -> dict:
    """Las env vars con las que lanzar `claude` AHORA. {} = sin redirect (licencia local o nada configurado).

    Sustituye a `v2.external_worker_env()` como fuente única: mismo contrato, pero eligiendo escalón sano."""
    t = pick()
    if not t or not t.get("base_url"):
        return {}
    tok = (t.get("api_key") or "").strip() or _token_for(t)
    if not tok:
        return {}
    # The CLI's own default is ten retries with backoff: against a spent quota (a `429` that will not clear for
    # hours) that is ~3 minutes before the worker gives up and the chain can relay (measured 2026-09-28, the demo's
    # monitor search). Three retries still ride out a blip; a dead tier is handed on in seconds.
    # EGRESS: a mediated deployment hands the worker egress's address and its own credential, never a provider key.
    from nucleo import llm_egress
    base, tok = llm_egress.route_url(t["base_url"], tok)
    out = {"ANTHROPIC_BASE_URL": base, "ANTHROPIC_AUTH_TOKEN": tok, "CLAUDE_CODE_MAX_RETRIES": "3"}
    out.update(vision_env(t))
    return out


def worker_sees() -> bool:
    """¿El escalón que serviría un worker AHORA lee imágenes? La otra cara de `vision_env`, para quien necesita
    la respuesta como bandera y no como entorno (el prompt del worker web). Vive aquí y no en el llamante para
    que la capacidad se resuelva en UN sitio: dos lecturas del catálogo derivan, y derivar aquí significa un
    prompt que manda mirar mientras el puente dice que no hay nada que ver."""
    try:
        return not vision_env(pick())
    except Exception:
        return True


def vision_env(tier: dict | None) -> dict:
    """`ZAELAR_NAV_VISION=0` SOLO si este escalón declara que su modelo no lee imágenes.

    Va por env porque el que necesita saberlo es `nucleo/nav_cli.py`, que corre como SUBPROCESO del worker y por
    tanto hereda su entorno — el mismo canal por el que ya viajan `ZAELAR_TASK_ID` y el token de los puentes. Y se
    resuelve AQUÍ, que es el único sitio donde ya se sabe qué escalón sirve la sesión: preguntárselo al CLI o
    deducirlo del nombre del modelo serían dos sitios más donde equivocarse.

    **Ausente = hay visión**, que es la conducta de siempre, y la dirección del fail-open no es indiferente: un
    «no ve» equivocado deja al worker CIEGO en un modelo que sí veía, y un worker ciego es el fallo más difícil de
    atribuir que tiene este módulo (lo dice `workers/workdir.py` sobre `read_dirs`). Un «sí ve» equivocado cuesta
    un `Read` fallido y el worker sigue por el DOM, que es lo que ya pasaba.

    Por eso solo se declara donde está MEDIDO. Un escalón nuevo no hereda un veredicto que nadie ha comprobado."""
    if isinstance(tier, dict) and tier.get("vision") is False:
        return {"ZAELAR_NAV_VISION": "0"}
    return {}

from nucleo.workers.providers.classify import (  # noqa: E402,F401
    _RESET_RE, _ZAI_CODE_RE, _WINDOW_RE, _EXHAUSTED_RE, _CONTEXT_RE, is_context_overflow, _DEPLETED_RE, is_depleted,
    _BROKEN_RE, is_broken_request, classify_failure, _TOOL_LIMIT_RE, classify_tool_failure)
from nucleo.workers.providers.health import (  # noqa: E402,F401
    note_tool_blindness, _reset_epoch, note_failure, _serving, status, clear, exhausted_until, exhausted_reason)
