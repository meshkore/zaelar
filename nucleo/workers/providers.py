"""nucleo/workers/providers.py — CADENA de proveedores del Brain Worker, con relevo automático (2026-08-02).

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

# Endpoints Anthropic-compatible CONOCIDOS (verificados: conducen Claude Code por `ANTHROPIC_BASE_URL`). Un
# escalón solo entra en la cadena si su variable de entorno tiene valor, así que tener esto aquí no activa nada:
# el operador contrata el plan, pone la key en el store, y el escalón aparece solo. Añadir uno nuevo = una línea.
KNOWN: list[dict] = [
    # ⚠️ `vision: False` — MEASURED 2026-08-27, and it contradicts what the provider advertises. The image
    # never reaches the model: this gateway uploads it and passes a URL the model cannot fetch. `glm-5.3`
    # says so plainly ("I can't access the image from that URL"); `glm-4.6`, `glm-4.5v` and `glm-4.6v` do NOT
    # — they answer confidently about an image they never saw. Probed with flat solid colours, which leave no
    # room for interpretation: a pure red 400×400 came back "Orange", a pure blue one "Teal", and a white PNG
    # with "ZAELAR 4271" written on it was described as a nine-tile CAPTCHA grid asking to pick crosswalks.
    # Z.ai's own vision path is the native `paas/v4` endpoint, which this plan does not serve at all: it
    # answers `1113 Insufficient balance` — a different wallet from the coding plan.
    #
    # So the honest half of the chain is only as safe as the model that happens to be serving. The browser's
    # vision path (V2-049) feeds a screenshot on EVERY action, and a confabulated screenshot has the SHAPE of
    # an observation — worse than DeepSeek's honest "I cannot read the screenshot" (measured 2026-08-24).
    # Declaring the trait here is what makes `vision_env()` set `ZAELAR_NAV_VISION=0` and send the worker
    # down the DOM route instead, whichever GLM is on the other end.
    # V2-500 — la tabla única (`config/models.default.json`) decide QUIÉN y CON QUÉ MODELO; aquí solo se
    # traduce. **Titular + UN failover**, norma del operador: Z.AI (plan de código, protocolo Anthropic) y
    # DeepSeek por su endpoint Anthropic. Moonshot salió de aquí al aplicarla — no estaba medido ni tenía
    # credencial, así que era un escalón que solo alargaba la cadena.
    #
    # Los DOS llevan `vision: False`, y eso está MEDIDO, no supuesto: los GLM contestan con seguridad sobre
    # imágenes que no han visto (un rojo plano volvió «Orange», un azul «Teal») y DeepSeek V4 al menos lo dice
    # («no se pudo leer, sigo por DOM»). El camino de visión del navegador manda una captura en CADA acción,
    # y una captura confabulada tiene la FORMA de una observación. Por eso `vision_env()` apaga la visión y el
    # worker va por DOM.
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
                                       # el ÚNICO caso que importa: que el operador RECARGUE — que es justo lo que
                                       # la alerta existe para provocar. Medido el 2026-08-27: el 402 de las 18:55
                                       # castigó al titular hasta pasada la medianoche, el operador recargó a las
                                       # 19:40, y el motor siguió mandándolo todo al relevo. Cuando ese relevo se
                                       # cayó a su vez, el cerebro se quedó MUDO con el titular sano al lado, y no
                                       # había forma de decirle que ya había saldo. Una recarga es invisible desde
                                       # aquí: la única manera de enterarse es volver a probar. El coste de la
                                       # libertad condicional son ~3 llamadas fallidas por hora mientras de verdad
                                       # no hay saldo; el coste de no tenerla fueron seis horas de silencio.
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
        # El modelo va PEGADO al escalón: `code_agent.model` (p.ej. `glm-5.2`) solo vale en SU proveedor.
        # Heredarlo en los demás fue el fallo del primer relevo: la licencia recibió `glm-5.2` y murió al
        # instante. Sin modelo declarado → "" y que cada proveedor use su default.
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


def env_for_worker() -> dict:
    """Las env vars con las que lanzar `claude` AHORA. {} = sin redirect (licencia local o nada configurado).

    Sustituye a `v2.external_worker_env()` como fuente única: mismo contrato, pero eligiendo escalón sano."""
    t = pick()
    if not t or not t.get("base_url"):
        return {}
    tok = (t.get("api_key") or "").strip() or _token_for(t)
    if not tok:
        return {}
    out = {"ANTHROPIC_BASE_URL": t["base_url"], "ANTHROPIC_AUTH_TOKEN": tok}
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


# ── detección de agotamiento y relevo ─────────────────────────────────────────────────────────────────────
# El proveedor ANUNCIA cuándo vuelve, y lo dice de tres formas distintas. Solo se leía la primera:
#   · fecha            «will reset at 2026-08-30»          → límite semanal/mensual
#   · fecha + hora     «reset at 2026-08-12 23:15:37»
#   · SOLO la hora     «Usage limit reached for 5 hour … reset at 23:15:37»  → límite de VENTANA, del mismo día
# Leer solo la fecha convertía el tercer caso en «medianoche pasada» → epoch en el pasado → caía al suelo de media
# hora, y a partir de ahí cada worker volvía a elegir ese proveedor y a comerse un 429. Con el reset a las 23:15,
# eso son SIETE HORAS de reintentos quemados de uno en uno (hallazgo de un e2e real, 2026-08-10).
# V2-309 — la hora viene como el proveedor quiera escribirla, y `6:10am` (un dígito + sufijo) no casaba: el
# cooldown caía al suelo por defecto (30 min) en vez de a las 6:10, así que a los 30 minutos otro worker iba
# a morir contra el mismo límite. Se acepta 1-2 dígitos y el am/pm opcional, que es como lo escribe el CLI.
_RESET_RE = re.compile(
    r"reset(?:s|ting)?(?:\s+(?:at|on|in))?\s*[:\s]\s*"
    r"(\d{4}-\d{2}-\d{2}(?:[ T]\d{2}:\d{2}(?::\d{2})?)?|\d{1,2}:\d{2}(?::\d{2})?\s*(?:am|pm)?)", re.I)
# Un límite de VENTANA (5 h, diario) no es un rate-limit pasajero: no se arregla reintentando en dos segundos, se
# arregla esperando a la hora que el propio proveedor dice. Tratarlo como `rate` era no ponerle cooldown NI relevar.
# V2-309 — «session limit» es la MISMA clase y no casaba con ninguna: medido el 2026-08-25 04:36, el worker
# murió al instante con «You've hit your session limit · resets 6:10am (Europe/Madrid)», `classify_failure`
# devolvió "" (no es fallo de proveedor) → sin cooldown y sin relevo, así que CADA worker nuevo iba al mismo
# escalón muerto y moría igual. Es literalmente lo que este patrón existe para cerrar, con otra redacción del
# proveedor. Y el «resets 6:10am» es su hora: se respeta como en cualquier ventana.
_WINDOW_RE = re.compile(
    r"usage limit reached|limit reached for\s+\d+\s*(?:hour|hr|minute|min|day)|"
    r"(?:hit|reached|exceeded)\s+(?:your|the)\s+session limit|session limit\b[^.]{0,40}\breset|"
    r"limit will reset|quota (?:will )?reset", re.I)
# Señales de CUOTA/PLAN agotado, más específicas que el `credit` genérico de `llm_health` (que también pilla un
# rate-limit pasajero). Aquí importa distinguir «espera 20s» de «hasta el jueves».
_EXHAUSTED_RE = re.compile(
    r"limit exhausted|quota exceeded|insufficient (?:balance|credit|quota)|out of credit|"
    r"monthly limit|weekly limit|plan limit|saldo insuficiente", re.I)


# ── A BLOWN CONTEXT IS NOT A SICK PROVIDER (incident 2026-08-18) ─────────────────────────────────────────────
# The worker of session `08f54c0c` died with "API Error: The model has reached its context window limit." and that
# text was handed to the operator as if it were their report. `classify_failure` did not recognize it (returned
# ""), so there was no relay and no alert: the very hole closed for quota on 2026-08-10, still open for this.
#
# This gets its OWN family rather than living inside `classify_failure`, for a substantive reason: a blown context
# is not an unhealthy provider. Folding it into `exhausted` would put a perfectly working tier on cooldown and
# migrate the fault to the next one — which would blow up identically, because the cause is the SIZE of the
# context, not who serves it. The correct answer is COMPACT AND CONTINUE (`session._context_handoff`), not relay.
#
# Two ways of saying the same thing, and both must be caught: the CLI's SYNTHETIC message talks about a "context
# window", but the real `apiError` in the incident was `max_output_tokens` — the provider rejects the call once the
# accumulated input PLUS the requested output reservation no longer fit its window. That is why it died at 138k
# and not at 200k.
_CONTEXT_RE = re.compile(
    r"context window|context[_ ]length|max_output_tokens|maximum context|"
    r"too many tokens|prompt is too long|input length and `max_tokens`", re.I)


def is_context_overflow(text: str) -> bool:
    """True if the error says the CONTEXT (input + output reservation) no longer fits the model's window.

    It must ALSO not be a quota problem: a 429 that happens to mention tokens is the other thing, and confusing
    the two would send us compacting when the right move is to relay to another provider."""
    t = text or ""
    if not _CONTEXT_RE.search(t):
        return False
    return classify_failure(t) == ""


# V2-243 — UN SALDO AGOTADO NO ES UNA CUOTA, y decirlo mal es el defecto, no un matiz de redacción. Una CUOTA
# anuncia cuándo vuelve y vuelve sola; un SALDO no vuelve hasta que el operador recargue. Los dos caen hoy en
# `exhausted`, así que el saldo heredaba el suelo de media hora y el panel escribía «sin cuota hasta las 03:02»
# — una fecha en la que no va a pasar nada. Medido en producción el 2026-08-21: `Insufficient Balance` de
# DeepSeek (HTTP 402) dos veces, con «sin cuota hasta el 21 Aug 03:02 · SIN RELEVO disponible», y el arnés paró
# de medir porque el cerebro se quedó sin proveedor.
#
# Predicado APARTE y no un valor nuevo de `classify_failure` a propósito: esa función la comparte
# `nucleo/flash/provider_chain.py`, que ramifica sobre sus tres valores y devolvería None (ni cooldown ni relevo)
# ante uno desconocido. Misma razón por la que `is_context_overflow` vive aparte, escrita ahí arriba.
_DEPLETED_RE = re.compile(
    r"insufficient (?:balance|credit|funds)|out of credit|no credit|balance is insufficient|"
    r"saldo insuficiente|sin saldo|recharge|top ?[- ]?up", re.I)


def is_depleted(text: str) -> bool:
    """True si el proveedor dice que se quedó SIN SALDO y NO anuncia cuándo vuelve.

    La ausencia de fecha es parte del predicado: un plan con forfait que dice «reset at …» sí vuelve solo, y
    tratarlo como saldo lo apagaría durante horas de más."""
    t = str(text or "")
    if not _DEPLETED_RE.search(t):
        return False
    return not _RESET_RE.search(t)


def classify_failure(text: str) -> str:
    """'exhausted' (plan/cuota agotada, hay que relevar) · 'auth' · 'rate' (pasajero) · '' (no es de proveedor)."""
    t = (text or "")
    if _EXHAUSTED_RE.search(t):
        return "exhausted"
    low = t.lower()
    if any(x in low for x in ("401", "403", "invalid api key", "unauthorized", "authentication")):
        return "auth"
    # VENTANA AGOTADA ≠ RATE-LIMIT (2026-08-10). Un «Usage limit reached for 5 hour» o cualquier 429 que ANUNCIE su
    # hora de reset no se arregla reintentando: hay que esperar a esa hora y, mientras, usar otro escalón. Caía en
    # `rate`, y `rate` no pone cooldown ni releva — así que el proveedor seguía siendo el elegido durante horas y
    # cada worker nuevo quemaba su reintento contra él.
    if _WINDOW_RE.search(t) or ("429" in low and _RESET_RE.search(t)):
        return "exhausted"
    if "429" in low or "too many requests" in low or "rate limit" in low:
        return "rate"
    return ""


# ── UN WORKER CIEGO NO ES UN WORKER CAÍDO (2026-08-10) ────────────────────────────────────────────────────────
# Hallazgo de una prueba e2e real: el plan de un proveedor se agota por DOS vías que no son la misma cosa.
#
#   · el MODELO se agota → la llamada falla → `note_failure` releva de escalón y el worker sigue en otro sitio.
#     Esto ya funcionaba (y se vio funcionar: relevó a la licencia local y entregó).
#   · las TOOLS INTEGRADAS del proveedor se agotan (búsqueda web y lector de páginas servidos por él) → la llamada
#     al modelo NO falla. El worker sigue razonando perfectamente… pero **CIEGO**: no puede buscar ni leer una
#     página. El error viaja dentro de un `tool_result`, que hasta ayer se descartaba como ruido interno, así que
#     no había alerta, ni relevo, ni una línea en el registro. El worker parecía sano y entregaba conclusiones
#     sin material.
#
# Es exactamente el modo de fallo que más caro sale aquí: un estado que ENGAÑA. Lo que hace esta función es
# separar las dos cosas para poder DECIRLO. Deliberadamente NO pone el escalón en cooldown: sus tools están
# agotadas, su modelo no, y castigar al modelo por eso apagaría un proveedor que funciona para todo lo demás.
# Qué hacer con esa política (¿relevar igualmente? ¿solo para tareas de investigación?) es decisión del operador,
# no un efecto colateral de instrumentar.
_TOOL_LIMIT_RE = re.compile(
    r"web_search|websearch_prime|web_search_prime|webreader|web_reader|"          # las tools integradas por nombre
    r"search.{0,20}(?:quota|limit)|(?:quota|limit).{0,20}search", re.I)


def classify_tool_failure(text: str) -> str:
    """'blind' si el error de un `tool_result` es una cuota agotada de las TOOLS del proveedor · '' si no lo es.

    Se exige que sea (a) un problema de cuota/límite Y (b) que hable de las tools: un 429 pelado del modelo no es
    ceguera, es el caso que ya cubre `note_failure`, y confundirlos daría una alerta equivocada."""
    t = text or ""
    if not _TOOL_LIMIT_RE.search(t):
        return ""
    return "blind" if (classify_failure(t) in ("exhausted", "rate")) else ""


def note_tool_blindness(text: str, tool: str = "", provider: str = "") -> str:
    """Registra que el worker se ha quedado CIEGO y devuelve el detalle legible (o "" si no era eso).

    Alerta + timeline, sin tocar el relevo. Fila propia en el panel (`worker:tools`) para que no se confunda con
    «el proveedor de los workers está caído», que es otro problema con otra solución."""
    if not classify_tool_failure(text):
        return ""
    # El culpable es el escalón con el que corría ESA sesión, no el primero de la cadena ahora: tras un relevo
    # son distintos, y nombrar al equivocado manda al operador a mirar el proveedor que sí funciona.
    name = provider or (pick() or {}).get("name", "") or "el proveedor"
    when = _RESET_RE.search(text or "")
    detail = (f"las herramientas de búsqueda de «{name}» están sin cuota"
              + (f" (reset {when.group(1)})" if when else "")
              + " — el worker sigue razonando pero NO puede buscar ni leer páginas")
    logger.warning(f"brain worker CIEGO: {detail}")
    try:
        from voice import health_state
        health_state.record("worker_tools", "credit", detail)
    except Exception:
        pass
    try:
        from voice.observer import emit
        emit("alert", "🕶️ worker CIEGO — sin herramientas de búsqueda", text=detail, role="system",
             extra={"provider": name, "tool": tool, "reason": "tool_quota",
                    "raw": (text or "")[:300]})
    except Exception:
        pass
    return detail


def _reset_epoch(text: str) -> float:
    """Cuándo dice el proveedor que vuelve, en epoch local. 0.0 = no lo dice (el llamador aplica su suelo).

    Una hora SUELTA se resuelve sobre HOY; si ya pasó, es de mañana (a las 23:50 un «reset at 00:30» no es de hace
    23 horas). Sin esto, una hora del mismo día se leía como medianoche pasada y el cooldown nacía vencido."""
    m = _RESET_RE.search(text or "")
    if not m:
        return 0.0
    raw = m.group(1).strip().replace("T", " ")
    # `6:10am` → `6:10 AM`: strptime con %p exige el separador y no admite minúsculas pegadas.
    _mp = re.match(r"^(\d{1,2}:\d{2}(?::\d{2})?)\s*(am|pm)$", raw, re.I)
    if _mp:
        raw = f"{_mp.group(1)} {_mp.group(2).upper()}"
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return time.mktime(time.strptime(raw, fmt))
        except Exception:
            pass
    for fmt in ("%I:%M:%S %p", "%I:%M %p", "%H:%M:%S", "%H:%M"):   # solo la hora → sobre el día de hoy
        try:
            hm = time.strptime(raw, fmt)
        except Exception:
            continue
        now = time.localtime()
        stamp = time.mktime((now.tm_year, now.tm_mon, now.tm_mday,
                             hm.tm_hour, hm.tm_min, hm.tm_sec, 0, 0, -1))
        return stamp if stamp > time.time() else stamp + 86400.0
    return 0.0


def note_failure(text: str, tier: dict | None = None) -> dict | None:
    """Un worker murió por el PROVEEDOR: marca el escalón, avisa, y devuelve el escalón de RELEVO (o None).

    Es el punto que faltaba: hasta hoy este 429 se entregaba al operador como texto de resultado («API Error…»)
    y moría ahí — ni alerta en el panel, ni cambio de proveedor, ni registro."""
    kind = classify_failure(text)
    if not kind:
        return None
    t = tier or pick()
    if not t or not t.get("base_url"):
        return None                                  # la licencia local no se pone en cooldown por esto

    dry = is_depleted(text)
    if kind == "exhausted":
        # Mismo suelo que en el hermano `nucleo/flash/provider_chain.py` (2026-08-09): una fecha de reset ya
        # VENCIDA en el texto del error dejaba el escalón disponible en el acto → relevo a sí mismo → bucle.
        # V2-243: si es SALDO y no cuota, no hay nada que esperar — reintentar cada media hora es quemar un
        # worker por ronda contra una cuenta vacía.
        until = (time.time() + _DEPLETED_COOLDOWN_S) if dry \
            else max(_reset_epoch(text), time.time() + _DEFAULT_COOLDOWN_S)
    elif kind == "auth":
        until = time.time() + _AUTH_COOLDOWN_S
    else:
        return None                                  # rate-limit pasajero: no releves, se reintenta solo

    _store.set(t["name"], until)

    nxt = pick()
    when = time.strftime("%d %b %H:%M", time.localtime(until))
    # V2-243: lo que se escribe aquí es lo que el operador lee en el panel, y de ello depende lo que HAGA. Una
    # cuota le dice «espera»; un saldo le dice «recarga». Poner una hora donde no va a pasar nada es peor que no
    # poner ninguna.
    estado = (f"SIN SALDO — no vuelve solo, hay que recargar" if dry
              else f"sin cuota hasta el {when}")
    detail = (f"«{t['name']}» ({t.get('plan', '')}) {estado}"
              + (f" → relevo a «{nxt['name']}»" if nxt else " · SIN RELEVO disponible"))
    logger.warning(f"brain worker: {detail}")

    # (1) al panel de ALERTAS, por el mismo canal reactivo que usan los demás proveedores
    try:
        from voice import health_state
        health_state.record("code_agent", "credit" if kind == "exhausted" else "auth", detail)
    except Exception:
        pass
    # (2) al timeline, con el mismo peso que una degradación del motor
    try:
        from voice.observer import emit
        emit("perf", f"🔌 proveedor de workers: {detail}", role="system",
             extra={"provider": t["name"], "kind": kind, "until": until,
                    "next": (nxt or {}).get("name", ""), "text": (text or "")[:300]})
    except Exception:
        pass
    return nxt


def _serving() -> set[str]:
    """Qué escalones están sirviendo AHORA MISMO a una sesión viva.

    «EN USO» y «el que se elegiría» son preguntas DISTINTAS, y confundirlas hacía mentir al panel: tras un relevo,
    el que trabaja es el de relevo y el que se elegiría vuelve a ser el primero de la cadena en cuanto su cooldown
    expira. La fila decía «EN USO · disponible» de un proveedor que no estaba haciendo nada (hallazgo de un e2e
    real, 2026-08-10). Best-effort: si el registro de sesiones no está disponible, se cae al comportamiento de antes.
    """
    try:
        from nucleo import dispatch
        by_url = {t.get("base_url", ""): t["name"] for t in chain()}
        out = set()
        for r in dispatch._SESSIONS.values():
            if r.status not in ("queued", "running"):
                continue
            s = getattr(r, "session", None)
            url = getattr(s, "_base_url", "") if s else ""
            name = by_url.get(url or "")
            if name:
                out.add(name)
        return out
    except Exception:
        return set()


def status() -> list[dict]:
    """Estado de cada escalón para el panel: `[{name, plan, state, detail, active, serving}]`."""
    now = time.time()
    active = pick()
    serving = _serving()
    out = []
    for t in chain():
        until = _store.until(t["name"])
        if until > now:
            state = "error"
            detail = f"sin cuota hasta el {time.strftime('%d %b %H:%M', time.localtime(until))}"
        else:
            state = "ok"
            detail = "disponible"
        # `serving` = está trabajando de verdad · `active` = es el que se elegiría para el próximo worker. Con un
        # relevo en marcha no son el mismo, y el panel tiene que poder decir cuál es cuál.
        out.append({"name": t["name"], "plan": t.get("plan", ""), "state": state, "detail": detail,
                    "serving": t["name"] in serving,
                    "active": bool(active and active["name"] == t["name"])})
    return out


def clear(name: str = "") -> None:
    """Levanta el cooldown (el operador recargó el plan y no quiere esperar al reset)."""
    _store.clear(name)


def exhausted_until() -> float:
    """Epoch at which the chain gets its first healthy tier back — `0.0` when one is available RIGHT NOW.

    `pick() is None` means TWO different worlds and no caller can tell them apart:

      · an EMPTY chain — self-host with no keys — where `env_for_worker()` returning `{}` is the fail-open this
        module promises: run the local Claude license exactly as before;
      · a chain whose every tier is in COOLDOWN, where `{}` means «run the local license» too — except the
        license is itself one of those tiers, and we put it there ourselves because it just answered
        «You've hit your session limit».

    So the cooldown we record for the LICENSE tier could never bite: measured in `find-concert-tickets__es`
    (2026-08-25 10:53-10:56), the license was marked out-of-quota until 14:20 and then spawned into TWICE more
    inside three minutes — 1.8 s, 3.9 s, 1.9 s of life, three dead workers, four minutes of the round, and a
    person told three times that a search was starting. Eleven of the twenty-eight empty-sheet rounds have this
    shape.

    The distinction lives here, next to `chain()`, because that is the only place that knows whether the chain is
    empty or merely asleep. Reading it anywhere else means recomputing the chain, and two readings derive.
    """
    ch = chain()
    if not ch:
        return 0.0                                  # nothing configured: the license path, as always
    now = time.time()
    untils = [_store.until(t["name"]) for t in ch]
    if any(u <= now for u in untils):
        return 0.0                                  # at least one tier is healthy → spawn away
    return min(untils)                              # the earliest one back is when work becomes possible again


def exhausted_reason() -> str:
    """One operator-facing sentence for `exhausted_until()`, or `""` when work is possible.

    Carries the HOUR because that is the only actionable part: «no quota» invites a retry in ten seconds,
    «back at 14:20» does not."""
    until = exhausted_until()
    if not until:
        return ""
    return ("Me he quedado sin cuota en el proveedor que mueve mis procesos de fondo; vuelve a las "
            f"{time.strftime('%H:%M', time.localtime(until))}. Hasta entonces no puedo lanzar una búsqueda.")
