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
    {"name": "z.ai", "base_url": "https://api.z.ai/api/anthropic",
     "env": ["Z_AI_API_KEY"], "plan": "GLM coding plan"},
    {"name": "moonshot", "base_url": "https://api.moonshot.ai/anthropic",
     "env": ["MOONSHOT_API_KEY", "KIMI_API_KEY"], "plan": "Kimi Code"},
    # DeepSeek expone un endpoint Anthropic-compatible propio (2026-08-13), y este escalón estuvo escrito y SIN
    # PROBAR hasta el 2026-08-14 porque faltaba la credencial.
    #
    # ⚠️ Al llegar la key se probó y **el `model` que declaraba era inválido**. Decía `sonnet` sobre la creencia de
    # que el gateway mapea alias de Claude (`claude-sonnet*` → v4-flash). NO los mapea: responde
    # `400 — «The supported API model names are deepseek-v4-pro or deepseek-v4-flash, but you passed sonnet»`.
    # Verificado con los tres alias de Claude (400 los tres) y con los nombres propios de DeepSeek (200 los dos).
    #
    # O sea que este escalón habría fallado con 400 en CADA petición desde el instante en que la credencial
    # entrara — y habría fallado justo cuando se le necesita, porque un escalón de relevo solo se usa cuando el
    # titular ya está caído. **Un relevo sin probar es peor que no tener relevo**: convierte una caída de proveedor
    # en una caída total, y el síntoma («el worker muere al instante») no apunta al modelo.
    #
    # Es pago por token (no suscripción), así que rompe la regla del operador de «forfait, nunca por token» — va
    # DESPUÉS de los planes y existe como red de seguridad barata.
    {"name": "deepseek", "base_url": "https://api.deepseek.com/anthropic",
     "env": ["DEEPSEEK_API_KEY"], "plan": "DeepSeek (pago por token)", "model": "deepseek-v4-flash"},
]
# Escalón final SOLO LOCAL: sin base_url el CLI usa la licencia con la que el operador ya está logueado. No
# necesita credencial y por eso no puede fallar por cuota de API — pero consume su licencia, así que va el último.
LICENSE_TIER = {"name": "licencia-claude", "base_url": "", "env": [], "plan": "licencia local de Claude Code",
                "local_only": True}

# Cooldown mechanics shared with the voice/cluster sibling module (V2-098) — the STATE stays separate on purpose
# (its own KV namespace: a CLI endpoint being down says nothing about a MODEL tier being down), only
# load/save/token/available.
from nucleo.provider_health import CooldownStore, token_for as _token_for

_DEFAULT_COOLDOWN_S = 30 * 60          # sin fecha de reset explícita: media hora y se reintenta
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
                tiers.append(dict(t))
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
    return {"ANTHROPIC_BASE_URL": t["base_url"], "ANTHROPIC_AUTH_TOKEN": tok}


# ── detección de agotamiento y relevo ─────────────────────────────────────────────────────────────────────
# El proveedor ANUNCIA cuándo vuelve, y lo dice de tres formas distintas. Solo se leía la primera:
#   · fecha            «will reset at 2026-08-30»          → límite semanal/mensual
#   · fecha + hora     «reset at 2026-08-12 23:15:37»
#   · SOLO la hora     «Usage limit reached for 5 hour … reset at 23:15:37»  → límite de VENTANA, del mismo día
# Leer solo la fecha convertía el tercer caso en «medianoche pasada» → epoch en el pasado → caía al suelo de media
# hora, y a partir de ahí cada worker volvía a elegir ese proveedor y a comerse un 429. Con el reset a las 23:15,
# eso son SIETE HORAS de reintentos quemados de uno en uno (hallazgo de un e2e real, 2026-08-10).
_RESET_RE = re.compile(
    r"reset(?:s|ting)?(?:\s+(?:at|on|in))?\s*[:\s]\s*"
    r"(\d{4}-\d{2}-\d{2}(?:[ T]\d{2}:\d{2}(?::\d{2})?)?|\d{2}:\d{2}(?::\d{2})?)", re.I)
# Un límite de VENTANA (5 h, diario) no es un rate-limit pasajero: no se arregla reintentando en dos segundos, se
# arregla esperando a la hora que el propio proveedor dice. Tratarlo como `rate` era no ponerle cooldown NI relevar.
_WINDOW_RE = re.compile(
    r"usage limit reached|limit reached for\s+\d+\s*(?:hour|hr|minute|min|day)|"
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
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return time.mktime(time.strptime(raw, fmt))
        except Exception:
            pass
    for fmt in ("%H:%M:%S", "%H:%M"):                     # solo la hora → sobre el día de hoy
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

    if kind == "exhausted":
        # Mismo suelo que en el hermano `nucleo/flash/provider_chain.py` (2026-08-09): una fecha de reset ya
        # VENCIDA en el texto del error dejaba el escalón disponible en el acto → relevo a sí mismo → bucle.
        until = max(_reset_epoch(text), time.time() + _DEFAULT_COOLDOWN_S)
    elif kind == "auth":
        until = time.time() + _AUTH_COOLDOWN_S
    else:
        return None                                  # rate-limit pasajero: no releves, se reintenta solo

    _store.set(t["name"], until)

    nxt = pick()
    when = time.strftime("%d %b %H:%M", time.localtime(until))
    detail = (f"«{t['name']}» ({t.get('plan', '')}) sin cuota hasta el {when}"
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
