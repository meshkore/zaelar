"""nucleo/flash/provider_chain.py — CADENA de proveedores del CEREBRO DE CLUSTER, con relevo automático
(2026-08-03). Hermano de `nucleo/workers/providers.py` (misma idea, mismo shape de datos) pero para el tier de
MODELO del canal off-voz (V2-069 «una sola mente») en vez del CLI `claude` de los brain workers — de ahí un
módulo separado en vez de forzar los dos casos en uno: aquí un escalón es un `ModelSpec` (base_url/api_key/model
de `FastClient`), allí es un endpoint Anthropic-compatible para `ANTHROPIC_BASE_URL`.

Incidente que lo motiva (2026-08-03): `connectors/meshkore/brain.py` resolvía el tier UNA VEZ al arrancar el
server (`_resolve_endpoint()`, prioridad fija por env) y se lo pasaba fijo a `nucleo.flash.cluster.respond`. Con
la cuota de Z.AI agotada, CADA turno de cluster (el heartbeat insistiendo en responder a un peer) repetía la
MISMA llamada rota → 429 en bucle, sin relevo, sin aviso — el operador solo veía "cluster brain turn failed: 429"
repetido. `nucleo.workers.providers` ya resolvía justo este problema para los workers; esto es el mismo mecanismo
aplicado al otro consumidor de modelo.

DISEÑO (igual que el hermano de workers)
-----------------------------------------
- **Cadena ordenada de escalones**, cada uno con su(s) env var(es) de credencial — sin token resoluble, el
  escalón ni aparece (fail-open: cero config = comportamiento de antes con UN tier).
- **Agotado ≠ roto**: cooldown hasta la fecha de reset si el proveedor la dice, si no una ventana corta.
- **Sticky**: `pick()` es una consulta O(1) contra un dict de cooldowns en memoria (persistido en `sys_kv`), NO
  vuelve a probar la cadena en cada turno — una vez relevado, el relevo se queda hasta que el cooldown expire o
  el operador lo limpie. El relevo dentro del MISMO turno que falla lo dispara `note_failure()` + un reintento
  del llamador (ver `connectors/meshkore/brain.py::_brain`).
- **Configurable**: `config/v2 cluster.providers` (lista ordenada, vacía por defecto) deja al operador fijar a
  mano principal→failover→failover; vacío = cadena por defecto desde las credenciales presentes (Z.AI directo →
  AIMLAPI/DeepSeek → xAI → Groq), el MISMO orden que tenía `brain.py._resolve_endpoint` antes de esto.
"""
from __future__ import annotations

import os
import re
import time

from loguru import logger

from nucleo.workers.providers import classify_failure  # regex de clasificación PURA, reusada tal cual (sin estado)

_RESET_RE = re.compile(r"reset(?:\s+at)?\s*[:\s]\s*(\d{4}-\d{2}-\d{2})", re.I)

_DEFAULT_COOLDOWN_S = 30 * 60          # sin fecha de reset explícita: media hora y se reintenta
_AUTH_COOLDOWN_S = 5 * 60              # credencial mal: puede ser un despiste, no castigues una semana
_KV = "cluster_provider_cooldown"

_cooldown: dict[str, float] = {}       # name -> epoch en el que vuelve a estar disponible
_loaded = False


def _load() -> None:
    global _loaded
    if _loaded:
        return
    _loaded = True
    try:
        from memory import api as memory
        saved = memory.kv_get(_KV) or {}
        if isinstance(saved, dict):
            now = time.time()
            _cooldown.update({k: float(v) for k, v in saved.items() if float(v) > now})
    except Exception:
        pass


def _save() -> None:
    try:
        from memory import api as memory
        memory.kv_set(_KV, {k: v for k, v in _cooldown.items() if v > time.time()})
    except Exception:
        pass


def _token_for(tier: dict) -> str:
    for name in tier.get("env") or []:
        v = (os.getenv(name) or "").strip()
        if v:
            return v
    return ""


# ── catálogo por defecto (SIN config explícita) — mismo orden/prioridad que `brain.py._resolve_endpoint` ────
def _known_chain() -> list[dict]:
    override_model = os.getenv("MESHKORE_MISSION_MODEL") or os.getenv("ASSISTANT_LLM_MODEL") or os.getenv("LLM_MODEL") or ""
    explicit = bool(os.getenv("LLM_API_KEY") or os.getenv("LLM_BASE_URL"))
    zai = {"name": "z.ai", "base_url": "https://api.z.ai/api/anthropic", "env": ["Z_AI_API_KEY"],
           "model": os.getenv("MESHKORE_MISSION_MODEL_ZAI", "glm-5.2"), "provider": "zai",
           "plan": "Z.AI GLM (coding plan)"}
    aimlapi = {"name": "aimlapi", "base_url": os.getenv("LLM_BASE_URL") or "https://api.aimlapi.com/v1",
               "env": ["LLM_API_KEY", "AIMLAPI_KEY"], "model": override_model or "deepseek/deepseek-v4-flash",
               "provider": "aimlapi", "plan": "AIMLAPI"}
    xai = {"name": "xai", "base_url": "https://api.x.ai/v1", "env": ["XAI_API_KEY"],
           "model": override_model or "grok-4.20-0309-non-reasoning", "provider": "aimlapi", "plan": "xAI directo"}
    groq = {"name": "groq", "base_url": "https://api.groq.com/openai/v1", "env": ["GROQ_API_KEY"],
            "model": override_model or "llama-3.3-70b-versatile", "provider": "aimlapi", "plan": "Groq directo"}
    # Un override LLM_API_KEY/LLM_BASE_URL explícito ganaba SIEMPRE a Z.AI en el código anterior (el operador
    # pinchó un endpoint a mano) — se preserva reordenando, no descartando: si Z.AI se recupera, sigue en la cadena.
    return [aimlapi, zai, xai, groq] if explicit else [zai, aimlapi, xai, groq]


def chain() -> list[dict]:
    """Escalones ordenados y DISPONIBLES (con credencial resoluble). El primero es el preferido."""
    try:
        from config import v2
        cfg = v2.get("cluster") or {}
    except Exception:
        cfg = {}

    explicit_cfg = cfg.get("providers")
    if isinstance(explicit_cfg, list) and explicit_cfg:
        tiers = [dict(t) for t in explicit_cfg if isinstance(t, dict) and t.get("name")]
    else:
        tiers = _known_chain()

    out = []
    for t in tiers:
        if not ((t.get("api_key") or "").strip() or _token_for(t)):
            continue                                # sin credencial no es un escalón, es un espejismo
        out.append(t)
    return out


def _available(t: dict) -> bool:
    _load()
    return _cooldown.get(t["name"], 0) <= time.time()


def pick() -> dict | None:
    """El primer escalón SANO de la cadena. None si no hay ninguno con credencial (→ el llamador decide)."""
    for t in chain():
        if _available(t):
            return t
    return None


def spec_for(tier: dict):
    """`ModelSpec` de FastClient listo para usar a partir de un escalón de la cadena."""
    from nucleo.flash.fast_client import ModelSpec
    tok = (tier.get("api_key") or "").strip() or _token_for(tier)
    return ModelSpec(model=tier.get("model") or "", base_url=tier.get("base_url") or "",
                      api_key=tok, provider=tier.get("provider") or "aimlapi")


def _reset_epoch(text: str) -> float:
    m = _RESET_RE.search(text or "")
    if not m:
        return 0.0
    try:
        return time.mktime(time.strptime(m.group(1), "%Y-%m-%d"))
    except Exception:
        return 0.0


def note_failure(text: str, tier: dict | None = None) -> dict | None:
    """Un turno de cluster murió por el PROVEEDOR: marca el escalón, avisa, y devuelve el escalón de RELEVO (o
    None). El llamador (`connectors/meshkore/brain.py`) reintenta ESE MISMO turno con el relevo devuelto — así el
    mensaje real-time al peer no se pierde solo porque el tier de cabecera esté sin cuota."""
    kind = classify_failure(text)
    if not kind:
        return None
    t = tier or pick()
    if not t or not t.get("base_url"):
        return None

    if kind == "exhausted":
        # La fecha de reset que da el proveedor manda… salvo que ya haya PASADO. Un mensaje con una fecha vencida
        # (respuesta cacheada, reloj desfasado, texto de error reutilizado) dejaba `until` en el pasado → el
        # escalón quedaba disponible en el acto → se relevaba a SÍ MISMO y volvía a fallar: exactamente el bucle
        # de 429 que este módulo existe para cortar. Suelo de media hora: si la cuota de verdad ya se repuso, se
        # pierde media hora de tier preferido; sin suelo se pierde el turno entero, en bucle. (2026-08-09)
        until = max(_reset_epoch(text), time.time() + _DEFAULT_COOLDOWN_S)
    elif kind == "auth":
        until = time.time() + _AUTH_COOLDOWN_S
    else:
        return None                                  # rate-limit pasajero: no releves, se reintenta solo

    _load()
    _cooldown[t["name"]] = max(_cooldown.get(t["name"], 0), until)
    _save()

    nxt = pick()
    when = time.strftime("%d %b %H:%M", time.localtime(until))
    detail = (f"«{t['name']}» ({t.get('plan', '')}) sin cuota hasta el {when}"
              + (f" → relevo a «{nxt['name']}»" if nxt else " · SIN RELEVO disponible"))
    logger.warning(f"cerebro de cluster: {detail}")

    # (1) al panel de ALERTAS, mismo canal reactivo que el resto de proveedores (config/balances.py)
    try:
        from voice import health_state
        health_state.record("cluster_brain", "credit" if kind == "exhausted" else "auth", detail)
    except Exception:
        pass
    # (2) al timeline, con el mismo peso que una degradación del motor
    try:
        from voice.observer import emit
        emit("perf", f"🔌 cerebro de cluster: {detail}", role="system",
             extra={"provider": t["name"], "kind": kind, "until": until,
                    "next": (nxt or {}).get("name", ""), "text": (text or "")[:300]})
    except Exception:
        pass
    return nxt


def status() -> list[dict]:
    """Estado de cada escalón para el panel: `[{name, plan, state, detail, active}]`."""
    _load()
    now = time.time()
    active = pick()
    out = []
    for t in chain():
        until = _cooldown.get(t["name"], 0)
        if until > now:
            state = "error"
            detail = f"sin cuota hasta el {time.strftime('%d %b %H:%M', time.localtime(until))}"
        else:
            state = "ok"
            detail = "disponible"
        out.append({"name": t["name"], "plan": t.get("plan", ""), "state": state, "detail": detail,
                    "active": bool(active and active["name"] == t["name"])})
    return out


def clear(name: str = "") -> None:
    """Levanta el cooldown (el operador recargó el plan y no quiere esperar al reset)."""
    _load()
    if name:
        _cooldown.pop(name, None)
    else:
        _cooldown.clear()
    _save()
