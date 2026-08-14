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
import time

from loguru import logger

# Clasificación y lectura de la hora de reset REUSADAS del hermano (puras, sin estado). No se copian a propósito:
# este módulo tenía su propio `_RESET_RE` que solo leía la FECHA, así que un reset del mismo día («reset at
# 23:15:37») se resolvía a medianoche pasada y el cooldown nacía vencido — el bug que el hermano ya arregló y que
# aquí seguía vivo. Dos copias de la misma lectura garantizan que una de ellas se quede atrás.
from nucleo.workers.providers import _reset_epoch, classify_failure


_DEFAULT_COOLDOWN_S = 30 * 60          # sin fecha de reset explícita: media hora y se reintenta
_AUTH_COOLDOWN_S = 5 * 60              # credencial mal: puede ser un despiste, no castigues una semana
_KV = "cluster_provider_cooldown"      # nombre histórico: el cooldown es COMPARTIDO (ver `role` abajo)

_cooldown: dict[str, float] = {}       # name -> epoch en el que vuelve a estar disponible
_loaded = False

# ── DOS CONSUMIDORES, UNA MECÁNICA (V2-094, 2026-08-14) ───────────────────────────────────────────────────────
# Este módulo nació para el cerebro de CLUSTER. El de VOZ tenía el mismo problema y ningún relevo: un turno lento
# o un proveedor sin cuota se repetía igual contra el mismo tier. Así que la mecánica se comparte y lo único que
# cambia por consumidor es la CADENA:
#   · `cluster` → arranca en Z.AI (su titular histórico);
#   · `voice`   → arranca en lo que diga `config §fast` (el titular del FlashBrain, hoy DeepSeek V4 Flash vía
#                 AIMLAPI) y sigue por los escalones RÁPIDOS Y BARATOS que tengan credencial.
# El COOLDOWN sí es compartido a propósito: si a Z.AI se le acabó la cuota, se le acabó para todo el mundo — y
# marcarlo dos veces sería tener dos verdades sobre el mismo proveedor.
ROLE_CLUSTER = "cluster"
ROLE_VOICE = "voice"

# ── RELEVO POR LATENCIA (lo que no existía) ───────────────────────────────────────────────────────────────────
# `note_failure` cubre el proveedor ROTO (429/cuota/credencial). No cubría el proveedor LENTO, que es el fallo que
# el operador vive de verdad: turnos de 20-25 s en los que «parece que se ha quedado tonto». Medido en la sesión
# b70a45d0: TTFT p50 de 8.370 ms y máximo de 25.703 ms, con el prompt CONSTANTE (±9%) y 120 tok/s de generación —
# o sea, todo el tiempo antes del primer token.
#
# Tres decisiones que importan:
# 1. **No se releva al primer turno lento.** Un pico aislado es ruido; hacen falta `_SLOW_STREAK` seguidos. Relevar
#    por un pico cambiaría de modelo (y de precio) continuamente.
# 2. **El cooldown de latencia es CORTO.** Lentitud es transitoria; quedarse media hora en un escalón más caro por
#    dos turnos malos sale carísimo. 5 minutos y se vuelve a probar el titular.
# 3. **TECHO DE TURNOS en el relevo.** Un relevo por latencia salta justo en los turnos DIFÍCILES, que son los que
#    más tokens gastan — el peor perfil de coste posible. Pasados `_RELAY_TURN_BUDGET` turnos se vuelve al titular
#    aunque siga lento: preferimos un turno lento a una factura sorpresa. (En la nube el salto de DeepSeek a un
#    escalón grande puede ser de 14× el input; ver `.meshkore/docs/ops/zaelar-energy-accounting.md` en la raíz.)
_SLOW_COOLDOWN_S = 5 * 60
_SLOW_STREAK = 2
_RELAY_TURN_BUDGET = 40

_slow_streak: dict[str, int] = {}      # name -> turnos lentos consecutivos de ESE escalón
_relay_turns: dict[str, int] = {}      # name -> turnos ya servidos por ese escalón como RELEVO de latencia


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


def _voice_chain() -> list[dict]:
    """Cadena por defecto del cerebro de VOZ. Empieza SIEMPRE por el titular configurado (`config §fast`) — la
    verdad del FlashBrain no la decide este módulo — y sigue por escalones elegidos por dos criterios, en este
    orden: que sean RÁPIDOS AL PRIMER TOKEN y que no disparen el coste.

    Por qué estos y no un modelo grande: el relevo por latencia salta en los turnos difíciles, que son los que más
    tokens gastan, así que un escalón caro es justo el que no quieres ahí. Con el input dominando 14:1 en este
    cerebro, lo único que cuenta es el precio de entrada. `grok-4-fast` está a 1,4× el titular; un `grok-4.5`
    estaría a 14×, y por eso NO está en la cadena por defecto (el operador puede ponerlo a mano si quiere).
    Groq va último porque es más caro que Grok Fast, pero es el que de verdad arregla un TTFT malo: LPU + modelo
    sin razonamiento = primer token en cientos de milisegundos.

    **En self-host esta cadena está VACÍA por defecto** (solo el titular, sin relevo): quien se autohospeda paga
    sus propias APIs y no puede llevarse la sorpresa de que el agente se pase solo a un proveedor que él no eligió.
    Lo activa poniendo `fast.providers` en su config."""
    titular = None
    try:
        from nucleo.flash.fast_client import spec_from_config
        sp = spec_from_config()
        if sp.resolved_api_key():
            titular = {"name": "titular", "base_url": sp.resolved_base_url(), "model": sp.model,
                       "api_key": sp.resolved_api_key(), "provider": sp.provider or "aimlapi",
                       "plan": f"titular de voz ({sp.model})"}
    except Exception as e:  # noqa: BLE001
        logger.warning(f"provider_chain(voice): no pude resolver el titular: {e!r}")

    relevos = [
        {"name": "xai-fast", "base_url": "https://api.x.ai/v1", "env": ["XAI_API_KEY"],
         "model": os.getenv("ZAELAR_VOICE_RELAY_XAI_MODEL", "grok-4-fast"), "provider": "aimlapi",
         "plan": "xAI Grok Fast (1,4× el titular)"},
        {"name": "groq", "base_url": "https://api.groq.com/openai/v1", "env": ["GROQ_API_KEY"],
         "model": os.getenv("ZAELAR_VOICE_RELAY_GROQ_MODEL", "llama-3.3-70b-versatile"), "provider": "aimlapi",
         "plan": "Groq LPU (TTFT sub-segundo, 4,2× el titular)"},
    ]
    # SOLO EN LA NUBE hay relevo por defecto (ver el docstring). `is_cloud_account` es el mismo gate de siempre.
    try:
        from nucleo import cloud_account
        if not cloud_account.is_cloud_account():
            relevos = []
    except Exception:
        relevos = []
    return ([titular] if titular else []) + relevos


def _config_key(role: str) -> str:
    return "fast" if role == ROLE_VOICE else "cluster"


def chain(role: str = ROLE_CLUSTER) -> list[dict]:
    """Escalones ordenados y DISPONIBLES (con credencial resoluble). El primero es el preferido.

    `role` decide la cadena por defecto y qué clave de config la sobreescribe (`fast.providers` para voz,
    `cluster.providers` para el cerebro de cluster). Una lista explícita del operador manda siempre."""
    try:
        from config import v2
        cfg = v2.get(_config_key(role)) or {}
    except Exception:
        cfg = {}

    explicit_cfg = cfg.get("providers")
    if isinstance(explicit_cfg, list) and explicit_cfg:
        tiers = [dict(t) for t in explicit_cfg if isinstance(t, dict) and t.get("name")]
    else:
        tiers = _voice_chain() if role == ROLE_VOICE else _known_chain()

    out = []
    for t in tiers:
        if not ((t.get("api_key") or "").strip() or _token_for(t)):
            continue                                # sin credencial no es un escalón, es un espejismo
        out.append(t)
    return out


def _available(t: dict) -> bool:
    _load()
    return _cooldown.get(t["name"], 0) <= time.time()


def pick(role: str = ROLE_CLUSTER) -> dict | None:
    """El primer escalón SANO de la cadena. None si no hay ninguno con credencial (→ el llamador decide).

    Además AGOTA el techo de turnos de un relevo por latencia: si el escalón que toca ya sirvió su presupuesto
    como relevo, se levanta su cooldown de latencia y se vuelve al titular. Sin esto, dos turnos lentos podían
    dejarnos indefinidamente en un escalón más caro."""
    ch = chain(role)
    for i, t in enumerate(ch):
        if _available(t):
            # ¿Es un relevo (no el primero) al que se le acabó el presupuesto?
            if i > 0 and _relay_turns.get(t["name"], 0) >= _RELAY_TURN_BUDGET:
                _relay_turns.pop(t["name"], None)
                titular = ch[0]["name"]
                if _cooldown.get(titular, 0) > time.time():
                    _cooldown.pop(titular, None)     # devuélvele el turno al titular aunque siga lento
                    _save()
                    logger.info(f"provider_chain({role}): agotado el techo de relevo de «{t['name']}» "
                                f"({_RELAY_TURN_BUDGET} turnos) → vuelve «{titular}»")
                    try:
                        from voice.observer import emit
                        emit("perf", f"🔌 fin del relevo por latencia: vuelve «{titular}» "
                                     f"(techo de {_RELAY_TURN_BUDGET} turnos en «{t['name']}»)", role="system",
                             extra={"provider": titular, "relay": t["name"], "reason": "relay_budget"})
                    except Exception:
                        pass
                    return ch[0] if _available(ch[0]) else t
            if i > 0:
                _relay_turns[t["name"]] = _relay_turns.get(t["name"], 0) + 1
            return t
    return None


def spec_for(tier: dict):
    """`ModelSpec` de FastClient listo para usar a partir de un escalón de la cadena."""
    from nucleo.flash.fast_client import ModelSpec
    tok = (tier.get("api_key") or "").strip() or _token_for(tier)
    return ModelSpec(model=tier.get("model") or "", base_url=tier.get("base_url") or "",
                      api_key=tok, provider=tier.get("provider") or "aimlapi")


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


def note_slow(verdict: dict, *, role: str = ROLE_VOICE, tier: dict | None = None) -> dict | None:
    """Un turno fue LENTO por el proveedor/el modelo. Devuelve el escalón de RELEVO si toca relevar, o None.

    Come el veredicto de `nucleo/flash/turn_perf.verdict()` tal cual — ahí ya está toda la decisión de si el
    tiempo se fue antes del primer token, y con qué throughput. Este módulo NO vuelve a medir nada: solo aplica la
    política de cuántos turnos lentos seguidos justifican cambiar de proveedor.

    Cuenta como lento el `pre_token` (razonamiento oculto o cola: en ambos casos el operador espera mirando una
    pantalla muda) y el `proveedor` (genera despacio). NO cuentan `frio` (la primera llamada paga handshake y
    cambiar de proveedor lo empeoraría), ni `trabajo` (hay un 2º pase legítimo), ni `prompt` (eso lo arregla el
    prompt, no otro proveedor), ni `reparto`, ni `ok` — y CUALQUIERA de ellos rompe la racha: hacen falta lentos
    SEGUIDOS, no lentos acumulados a lo largo del día."""
    cause = str((verdict or {}).get("cause") or "")
    t = tier or pick(role)
    if not t:
        return None
    name = t["name"]
    if cause not in ("pre_token", "proveedor"):
        if _slow_streak.pop(name, None):
            logger.debug(f"provider_chain({role}): racha de lentos de «{name}» rota por un turno «{cause}»")
        return None

    _slow_streak[name] = _slow_streak.get(name, 0) + 1
    streak = _slow_streak[name]
    if streak < _SLOW_STREAK:
        return None

    ch = chain(role)
    # Si ya estamos en el ÚLTIMO escalón no hay a dónde ir: castigarlo solo nos dejaría sin proveedor.
    if not ch or ch[-1]["name"] == name:
        logger.info(f"provider_chain({role}): «{name}» lento x{streak} pero es el último escalón — sin relevo")
        return None

    _load()
    until = time.time() + _SLOW_COOLDOWN_S
    _cooldown[name] = max(_cooldown.get(name, 0), until)
    _save()
    _slow_streak.pop(name, None)

    nxt = pick(role)
    ttft = int((verdict or {}).get("ttft_ms") or 0)
    detail = (f"«{name}» lento {streak} turnos seguidos (último: TTFT {ttft} ms, "
              f"{int(((verdict or {}).get('ttft_frac') or 0) * 100)}% del turno)"
              + (f" → relevo a «{nxt['name']}» durante {_SLOW_COOLDOWN_S // 60} min "
                 f"o {_RELAY_TURN_BUDGET} turnos" if nxt and nxt["name"] != name else " · SIN RELEVO disponible"))
    logger.warning(f"cerebro de {role}: {detail}")
    # VISIBLE, siempre: un cambio de proveedor a espaldas del operador es la clase de estado que engaña. Y en la
    # nube además cambia lo que cuesta cada turno.
    try:
        from voice.observer import emit
        emit("perf", f"🔌 relevo por LATENCIA: {detail}", role="system",
             extra={"provider": name, "kind": "slow", "until": until, "role": role,
                    "next": (nxt or {}).get("name", ""), "streak": streak,
                    "ttft_ms": ttft, "cause": cause})
    except Exception:
        pass
    try:
        from voice import health_state
        health_state.record(f"{role}_brain", "slow", detail)
    except Exception:
        pass
    return nxt if (nxt and nxt["name"] != name) else None


def status(role: str = ROLE_CLUSTER) -> list[dict]:
    """Estado de cada escalón para el panel: `[{name, plan, state, detail, active}]`."""
    _load()
    now = time.time()
    active = pick(role)
    out = []
    for t in chain(role):
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
