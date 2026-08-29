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
from nucleo.workers.providers import _reset_epoch, classify_failure, is_depleted
# Cooldown mechanics shared with the sibling module (V2-098) — the STATE stays separate on purpose (its own KV
# namespace: a MODEL tier being down says nothing about a CLI endpoint being down), only load/save/token/available.
from nucleo import provider_health as _health
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
_KV = "cluster_provider_cooldown"      # nombre histórico: el cooldown es COMPARTIDO (ver `role` abajo)

_store = CooldownStore(_KV)

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


# ── catálogo por defecto (SIN config explícita) — mismo orden/prioridad que `brain.py._resolve_endpoint` ────
def _known_chain() -> list[dict]:
    """Los escalones por defecto del cerebro de voz: **titular + UN failover**, y nada más.

    V2-500 — salen de `config/models.default.json`, la tabla única y pública. Antes esto era un catálogo
    escrito aquí, con cinco escalones (Z.AI, sus créditos, AIMLAPI, xAI, Groq) que nadie comparaba con nada:
    la norma del operador vivía solo en su `config/v2.json`, gitignorado, así que una instalación nueva —y la
    nube— arrancaban con otro reparto. Y el primero de esos cinco era Z.AI, que es como su cartera acabó
    pagando turnos de cluster que nadie había autorizado.

    **Un solo failover** es también norma (2026-08-30): una cadena de cuatro no se puede razonar ni depurar, y
    los dos últimos escalones que había aquí estaban muertos sin que nadie lo supiera — xAI sin créditos (403)
    y Groq con un modelo retirado (404 `model_not_found`).

    Un `LLM_API_KEY`/`LLM_BASE_URL` explícito —el operador pinchando un endpoint a mano— se sigue respetando y
    va el primero.
    """
    from config import models as _tabla
    explicit = bool(os.getenv("LLM_API_KEY") or os.getenv("LLM_BASE_URL"))
    override_model = (os.getenv("MESHKORE_MISSION_MODEL") or os.getenv("ASSISTANT_LLM_MODEL")
                      or os.getenv("LLM_MODEL") or "")
    escalones = _tabla.chain_for("voice_brain", names=("deepseek-directo", "aimlapi-failover"))
    if override_model:
        for e in escalones:
            e["model"] = override_model
    if explicit:
        pinchado = {"name": "endpoint-del-operador", "base_url": os.getenv("LLM_BASE_URL") or "",
                    "env": ["LLM_API_KEY"], "model": override_model or "", "provider": "aimlapi",
                    "plan": "endpoint configurado a mano"}
        return [pinchado] + escalones
    return escalones


def _VOICE_RELAYS() -> list[dict]:
    """Los escalones de relevo de la cadena de voz, aparte para poder NOMBRARLOS cuando la regla de
    self-host los calla (V2-244). La lista y sus razones no cambian: ver `_voice_chain`."""
    return [
    # PRIMER escalón desde 2026-08-14, y es el MISMO MODELO que el titular por OTRO endpoint — que suena raro
    # hasta que se ve el número. El titular va por el broker AIMLAPI, que ACEPTA `thinking:{"type":"disabled"}`
    # y razona igual; `api.deepseek.com` lo OBEDECE. Medido con el prompt real de voz, 6 turnos por brazo:
    #
    #   AIMLAPI → TTFT p50 4,24 s · peor 14,71 s · 2.138 tokens de razonamiento
    #   DIRECTO → TTFT p50 1,01 s · peor  1,30 s ·     0
    #
    # O sea que el relevo por LATENCIA ideal no es un modelo distinto: es el mismo sin el razonamiento oculto
    # que el broker no deja apagar. Y encaja con el criterio de esta cadena mejor que nada: **no encarece** (es
    # la misma tarifa por token, sin el ×1,4 de Grok Fast ni el ×4,2 de Groq) y es el más rápido al primer token.
    #
    # **El modelo del escalón es V4 PRO, no Flash, y eso se decidió MIDIENDO** (2026-08-15, nodo 2.13 a 3
    # rondas × 14 casos = 42 turnos por brazo, que es lo que hacía falta para distinguir defecto de ruido):
    #
    #   brazo                        enrutado  graves   TTFT p50   peor turno
    #   AIMLAPI deepseek-v4-flash      41/42       0     8.659 ms   12.025 ms   ← titular
    #   DIRECTO deepseek-v4-PRO        41/42       1     1.158 ms    5.582 ms   ← este escalón
    #   DIRECTO deepseek-v4-flash      38/42       1       934 ms    2.344 ms   ← lo que había aquí
    #   AIMLAPI (titular anterior)     31/42       0     1.297 ms    2.352 ms
    #
    # Flash DIRECTO fallaba `mostrar widget` **3 de 3** — o sea un defecto de enrutado reproducible, no mala
    # suerte. Pro iguala el enrutado del titular (41/42) por 224 ms más de TTFT, así que el relevo deja de
    # costar precisión: el intercambio que este comentario declaraba antes («enrutado algo peor a cambio de
    # que el turno llegue») ya no hay que pagarlo. Cuesta ×2 el input, y por eso es RELEVO y no titular — un
    # relevo tiene techo de turnos y solo actúa tras dos turnos lentos seguidos.
    #
    # Sigue sin ser TITULAR: el broker marca 0 graves en 42 turnos y los dos brazos directos marcan 1. El
    # grave es `pregunta memoria → widget_data`, exactamente el fallo que baneó a grok del FlashBrain, y con
    # el razonamiento apagado se pierde justo esa discriminación pregunta/orden. Promoverlo es decisión del
    # operador porque además dobla el coste de CADA turno de voz (V2-097 §1).
    {"name": "deepseek-directo", "base_url": "https://api.deepseek.com", "env": ["DEEPSEEK_API_KEY"],
     "model": os.getenv("ZAELAR_VOICE_RELAY_DEEPSEEK_MODEL", "deepseek-v4-pro"), "provider": "aimlapi",
     "plan": "DeepSeek directo V4 Pro (enrutado del titular, TTFT ×7,5 mejor)"},
    {"name": "xai-fast", "base_url": "https://api.x.ai/v1", "env": ["XAI_API_KEY"],
     "model": os.getenv("ZAELAR_VOICE_RELAY_XAI_MODEL", "grok-4-fast"), "provider": "aimlapi",
     "plan": "xAI Grok Fast (1,4× el titular)"},
    {"name": "groq", "base_url": "https://api.groq.com/openai/v1", "env": ["GROQ_API_KEY"],
     "model": os.getenv("ZAELAR_VOICE_RELAY_GROQ_MODEL", "llama-3.3-70b-versatile"), "provider": "aimlapi",
     "plan": "Groq LPU (TTFT sub-segundo, 4,2× el titular)"},
]


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

    relevos = _VOICE_RELAYS()
    # SOLO EN LA NUBE hay relevo por defecto (ver el docstring). `is_cloud_account` es el mismo gate de siempre.
    if _relays_suppressed():
        relevos = []
    return ([titular] if titular else []) + relevos


def _relays_suppressed() -> bool:
    """True en self-host, donde la cadena de voz es SOLO el titular (regla del operador, ver `_voice_chain`)."""
    try:
        from nucleo import cloud_account
        return not cloud_account.is_cloud_account()
    except Exception:
        return True


def suppressed_relays() -> list[str]:
    """Escalones de voz que la regla de self-host está callando **y para los que SÍ hay credencial**.

    V2-244 — la regla es del operador y no se toca: quien se autohospeda paga sus APIs y no puede llevarse la
    sorpresa de que el agente se pase solo a un proveedor que él no eligió. Pero esa regla se escribió sobre el
    relevo por LATENCIA (todo el docstring de `_voice_chain` habla de TTFT y de coste), y lo que se midió el
    2026-08-21 es otra cosa: el titular MUERTO (402) deja el producto entero mudo **con una clave viva sin usar**.
    El arnés lo aisló en dos líneas seguidas del log — `memllm[i18n]` relevó a AIMLAPI y siguió; el cerebro de voz
    dijo «SIN RELEVO disponible» en el mismo segundo.
    Callar un escalón es legítimo; callar QUE LO ESTÁS CALLANDO deja al operador sin la única frase que le habría
    dicho qué hacer. Esto no releva: solo permite NOMBRARLO.
    """
    if not _relays_suppressed():
        return []
    try:
        from config import v2
        if (v2.get("fast") or {}).get("providers"):
            return []                      # el operador ya puso su lista explícita: no hay nada callado
    except Exception:
        pass
    out = []
    for t in _VOICE_RELAYS():
        name = str(t.get("name") or "")
        if not name:
            continue
        if not ((t.get("api_key") or "").strip() or _token_for(t)):
            continue                       # sin credencial no es un escalón callado, es un escalón inexistente
        if not _store.available(name):
            continue                       # y uno YA en cooldown no es una salida: nombrarlo mandaría al
            #                                operador a mirar un proveedor que también está caído. El caso real
            #                                del 2026-08-21: `deepseek-directo` usa la MISMA cuenta que se quedó
            #                                sin saldo, así que ofrecerlo como remedio sería mentirle.
        out.append(name)
    return out


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


def pick(role: str = ROLE_CLUSTER) -> dict | None:
    """El primer escalón SANO de la cadena. None si no hay ninguno con credencial (→ el llamador decide).

    Además AGOTA el techo de turnos de un relevo por latencia: si el escalón que toca ya sirvió su presupuesto
    como relevo, se levanta su cooldown de latencia y se vuelve al titular. Sin esto, dos turnos lentos podían
    dejarnos indefinidamente en un escalón más caro."""
    ch = chain(role)
    for i, t in enumerate(ch):
        if _store.available(t["name"]):
            # ¿Es un relevo (no el primero) al que se le acabó el presupuesto?
            if i > 0 and _relay_turns.get(t["name"], 0) >= _RELAY_TURN_BUDGET:
                _relay_turns.pop(t["name"], None)
                titular = ch[0]["name"]
                if _store.until(titular) > time.time():
                    # …AUNQUE SIGA LENTO, que es lo que dice la línea de al lado — y solo eso. Medido en
                    # `search-secondhand-monitor__es` (2026-08-24 00:56): este mismo proceso puso a «z.ai» en
                    # cooldown hasta el 25 Aug 01:39 por quedarse sin cuota SEMANAL, y 260 s después este
                    # `lift` se lo quitó porque el presupuesto del relevo se había agotado — devolviéndole el
                    # turno a un proveedor que sabíamos que iba a contestar 429. La intención de esta línea
                    # siempre fue la latencia; lo que faltaba era poder decirlo.
                    _store.lift(titular, only=_health.REASON_LATENCY)
                    if not _store.available(titular):
                        # Sigue castigado por SALUD: el techo del relevo no tiene nada que decir ahí. Se
                        # queda donde está y se recuerda que este escalón acaba de renovar su turno, o el
                        # siguiente `pick` vuelve a entrar aquí y a emitir el mismo aviso en bucle.
                        _relay_turns[t["name"]] = 1
                        return t
                    logger.info(f"provider_chain({role}): agotado el techo de relevo de «{t['name']}» "
                                f"({_RELAY_TURN_BUDGET} turnos) → vuelve «{titular}»")
                    try:
                        from voice.observer import emit
                        emit("perf", f"🔌 fin del relevo por latencia: vuelve «{titular}» "
                                     f"(techo de {_RELAY_TURN_BUDGET} turnos en «{t['name']}»)", role="system",
                             extra={"provider": titular, "relay": t["name"], "reason": "relay_budget"})
                    except Exception:
                        pass
                    return ch[0] if _store.available(ch[0]["name"]) else t
            if i > 0:
                _relay_turns[t["name"]] = _relay_turns.get(t["name"], 0) + 1
            return t
    return None


def tier_available(tier) -> bool:
    """¿Este escalón está elegible AHORA (sin cooldown)? Costura pública para quien fija su spec por config
    pero no debe ARRANCAR un turno en un escalón que acaba de fallar (V2-307) — un cooldown solo existe porque
    un fallo real se anotó. Fail-open a disponible: no poder leerlo no puede dejar al titular fuera."""
    try:
        return _store.available(str((tier or {}).get("name") or ""))
    except Exception:  # noqa: BLE001
        return True


def spec_for(tier: dict):
    """`ModelSpec` de FastClient listo para usar a partir de un escalón de la cadena."""
    from nucleo.flash.fast_client import ModelSpec
    tok = (tier.get("api_key") or "").strip() or _token_for(tier)
    return ModelSpec(model=tier.get("model") or "", base_url=tier.get("base_url") or "",
                      api_key=tok, provider=tier.get("provider") or "aimlapi")


# Per-role labelling for note_failure's log/panel/timeline output (2026-08-15 addendum): the function was
# hardcoded to the cluster brain's wording — fine while it had one caller, wrong the moment a HARD failure (not
# just a slow turn, which `note_slow` already covered per-role) needed to relay the VOICE tier too. The voice side
# reuses the "llm" health_state key on purpose: `config/balances.py`'s reactive panel already reads it (it is
# what nucleo.py's own degraded-turn branch records), so this doesn't need a new panel wired in.
_ROLE_LABEL = {ROLE_CLUSTER: "cerebro de cluster", ROLE_VOICE: "cerebro de voz"}
_ROLE_HEALTH_KEY = {ROLE_CLUSTER: "cluster_brain", ROLE_VOICE: "llm"}


def _same_account_as(tier: dict, role: str) -> list[str]:
    """Los OTROS escalones de la cadena que gastan de la MISMA cuenta que `tier`.

    Un saldo agotado es un hecho de la CUENTA, no del modelo. La cadena de voz del operador tiene dos escalones
    de DeepSeek —`deepseek-v4-flash` y `deepseek-v4-pro`— y los dos cobran de `DEEPSEEK_API_KEY`: cuando esa
    cuenta se queda a cero, los dos están muertos y solo el tercero (otro proveedor) puede contestar.

    Medido el 2026-08-28 con el motor vivo: el titular devolvió 402, el relevo fue al hermano, el hermano
    devolvió 402 —la misma cuenta— y ahí se acabó el único reintento que V2-252 concede, así que el turno salió
    con el error puesto **mientras AIMLAPI respondía 200 una fila más abajo**. Dos escalones que comparten
    cuenta no son dos escalones: son el mismo, y gastar el reintento en el hermano es gastarlo en nada.

    Hacen falta DOS señales, y exigir las dos es lo que lo hace seguro: mismo HOST y misma credencial resuelta.
    La credencial sola no basta —dos proveedores que no tienen nada que ver pueden acabar leyendo el mismo valor
    (un placeholder, una variable compartida, un stub) y emparejarlos apagaría un escalón sano—; el host solo
    tampoco, porque dos cuentas distintas del mismo proveedor son dos saldos distintos. Se comparan las
    credenciales RESUELTAS y no los nombres de las variables: dos escalones pueden nombrar la clave distinto y
    leer la misma. El valor no se registra ni se devuelve — solo se compara.

    Ante la duda NO se empareja: sin credencial o sin host no hay pareja, y una cuenta repartida entre dos hosts
    se comporta como hasta hoy (un reintento gastado). Equivocarse por defecto cuesta una vuelta; equivocarse por
    exceso apaga un proveedor que funcionaba.
    """
    mio = ((tier.get("api_key") or "").strip() or _token_for(tier) or "")
    casa = _host(tier)
    if not mio or not casa:
        return []
    fuera = []
    for t in chain(role):
        if t.get("name") == tier.get("name"):
            continue
        suyo = ((t.get("api_key") or "").strip() or _token_for(t) or "")
        if suyo and suyo == mio and _host(t) == casa:
            fuera.append(t["name"])
    return fuera


def _host(tier: dict) -> str:
    try:
        from urllib.parse import urlparse
        return (urlparse(str(tier.get("base_url") or "")).netloc or "").lower()
    except Exception:  # noqa: BLE001
        return ""


def note_failure(text: str, tier: dict | None = None, *, role: str = ROLE_CLUSTER) -> dict | None:
    """Un turno murió por el PROVEEDOR: marca el escalón, avisa, y devuelve el escalón de RELEVO (o None).

    `role` (default ROLE_CLUSTER, backward-compatible with the original single caller): decides which chain
    `pick()` consults when `tier` isn't given, and which label/health-state key the alert uses. The caller
    retries THIS SAME turn with the relay returned — for cluster that keeps a real-time reply to a peer from being
    lost just because the lead tier ran out of quota; for voice it lets the NEXT turn start on the relay instead
    of repeating the same broken call (2026-08-15, `voice/engine/llm/providers/nucleo.py`)."""
    kind = classify_failure(text)
    if not kind:
        return None
    t = tier or pick(role)
    if not t or not t.get("base_url"):
        return None

    dry = is_depleted(text)
    if kind == "exhausted":
        # La fecha de reset que da el proveedor manda… salvo que ya haya PASADO. Un mensaje con una fecha vencida
        # (respuesta cacheada, reloj desfasado, texto de error reutilizado) dejaba `until` en el pasado → el
        # escalón quedaba disponible en el acto → se relevaba a SÍ MISMO y volvía a fallar: exactamente el bucle
        # de 429 que este módulo existe para cortar. Suelo de media hora: si la cuota de verdad ya se repuso, se
        # pierde media hora de tier preferido; sin suelo se pierde el turno entero, en bucle. (2026-08-09)
        # V2-243: si es SALDO y no cuota, no hay nada que esperar (ver `providers.is_depleted`).
        until = (time.time() + _DEPLETED_COOLDOWN_S) if dry \
            else max(_reset_epoch(text), time.time() + _DEFAULT_COOLDOWN_S)
    elif kind == "auth":
        until = time.time() + _AUTH_COOLDOWN_S
    else:
        return None                                  # rate-limit pasajero: no releves, se reintenta solo

    _store.set(t["name"], until, _health.REASON_HEALTH)
    hermanos = _same_account_as(t, role) if dry else []  # V2-458
    for h in hermanos:
        _store.set(h, until, _health.REASON_HEALTH)

    nxt = pick(role)
    when = time.strftime("%d %b %H:%M", time.localtime(until))
    label = _ROLE_LABEL.get(role, "cerebro de cluster")
    # V2-243: una cuota le dice al operador «espera»; un saldo le dice «recarga». Escribir una hora en la que no
    # va a pasar nada es peor que no escribir ninguna — medido el 2026-08-21 con «sin cuota hasta el 21 Aug 03:02»
    # sobre un `Insufficient Balance` de DeepSeek, con el cerebro ya sin ningún proveedor.
    estado = "SIN SALDO — no vuelve solo, hay que recargar" if dry else f"sin cuota hasta el {when}"
    # V2-244 — y si NO hay relevo, decir si es que no hay ninguno o que la regla de self-host lo está callando.
    # «SIN RELEVO disponible» a secas manda al operador a buscar un proveedor que a lo mejor ya tiene puesto.
    _callados = suppressed_relays() if role == ROLE_VOICE else []
    _sin = (f" · SIN RELEVO: tengo credencial de {', '.join(_callados)} pero en self-host la cadena de voz es "
            f"solo el titular — ponlos en `fast.providers` para permitirlo") if _callados else \
        " · SIN RELEVO disponible"
    _con = f" (y {', '.join(hermanos)}: misma cuenta)" if hermanos else ""
    detail = (f"«{t['name']}» ({t.get('plan', '')}) {estado}{_con}"
              + (f" → relevo a «{nxt['name']}»" if nxt else _sin))
    logger.warning(f"{label}: {detail}")

    # (1) al panel de ALERTAS, mismo canal reactivo que el resto de proveedores (config/balances.py)
    try:
        from voice import health_state
        health_state.record(_ROLE_HEALTH_KEY.get(role, "cluster_brain"),
                             "credit" if kind == "exhausted" else "auth", detail)
    except Exception:
        pass
    # (2) al timeline, con el mismo peso que una degradación del motor
    try:
        from voice.observer import emit
        emit("perf", f"🔌 {label}: {detail}", role="system",
             extra={"provider": t["name"], "kind": kind, "until": until, "role": role,
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

    until = time.time() + _SLOW_COOLDOWN_S
    _store.set(name, until, _health.REASON_LATENCY)
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


def note_stall(*, role: str = ROLE_VOICE, tier: dict | None = None) -> dict | None:
    """Un turno se ATASCÓ (se cortó por silencio del proveedor). Devuelve el relevo si toca relevar, o None.

    V2-246 — EL AGUJERO: un escalón que se atasca SIEMPRE no se penalizaba nunca. `note_slow` vive en el camino
    de la respuesta, así que solo ve turnos que ACABARON; y `note_failure` se salta a propósito cuando el turno se
    atascó, porque un atasco suele ser pasajero. Resultado: el turno se corta, se dice «un turno se atascó y lo
    corté — sigo operativo», y el siguiente turno vuelve al MISMO escalón. Para siempre.

    Medido por el arnés el 2026-08-21 contra AIMLAPI con la clave del operador, ya con la cadena real sembrada en
    su sandbox: `deepseek/deepseek-v4-flash` —el modelo que tiene puesto el escalón de failover— **TIMEOUT a los
    75 s**, mientras `deepseek/deepseek-v4-pro` contestaba en 18,3 s. O sea que el relevo existía, entró, y se
    quedó mudo igual: el escalón de socorro apuntaba justo al modelo que ese broker no estaba sirviendo.

    La política es la MISMA que la de los lentos y por la misma razón: hacen falta `_SLOW_STREAK` atascos
    SEGUIDOS —un atasco aislado es ruido y relevar por él sería cambiar de proveedor por una hipo de red— y
    comparte la racha con `note_slow`, así que un turno bueno la rompe. Comparte también el cooldown corto y el
    techo de turnos del relevo: un proveedor atascado no puede convertirse en una factura sorpresa.
    """
    t = tier or pick(role)
    if not t:
        return None
    name = t["name"]
    _slow_streak[name] = _slow_streak.get(name, 0) + 1
    streak = _slow_streak[name]
    if streak < _SLOW_STREAK:
        return None

    ch = chain(role)
    if not ch or ch[-1]["name"] == name:
        # Sin sitio a donde ir, castigarlo nos deja sin proveedor: se avisa y se deja donde está.
        logger.info(f"provider_chain({role}): «{name}» atascado x{streak} pero es el último escalón — sin relevo")
        return None

    until = time.time() + _SLOW_COOLDOWN_S
    _store.set(name, until, _health.REASON_LATENCY)
    _slow_streak.pop(name, None)

    nxt = pick(role)
    detail = (f"«{name}» se atascó {streak} turnos seguidos (sin respuesta, cortado por silencio)"
              + (f" → relevo a «{nxt['name']}» durante {_SLOW_COOLDOWN_S // 60} min "
                 f"o {_RELAY_TURN_BUDGET} turnos" if nxt and nxt["name"] != name else " · SIN RELEVO disponible"))
    logger.warning(f"cerebro de {role}: {detail}")
    try:
        from voice.observer import emit
        emit("perf", f"🔌 relevo por ATASCO: {detail}", role="system",
             extra={"provider": name, "kind": "stall", "until": until, "role": role,
                    "next": (nxt or {}).get("name", ""), "streak": streak})
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
    now = time.time()
    active = pick(role)
    out = []
    for t in chain(role):
        until = _store.until(t["name"])
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
    _store.clear(name)
