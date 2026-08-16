"""nucleo/mem_processor.py — el PROCESADOR LLM del CORAZÓN de escritura (V2-013 · T123).

Por cada turno del operador, DESTILA el texto crudo en **píldoras** curadas y decide, por cada una, si se guarda,
DÓNDE (ESTADO/CORTO/LARGO/DESCARTAR), con qué importancia, TTL y bajo qué `slot` canónico. Es la pieza que hace
que la memoria APRENDA en vez de acumular chat crudo.

Reglas de diseño (invariantes del operador, 2026-07-10):

  - **LLM al ESCRIBIR, nunca al LEER.** Este módulo vive SOLO en el camino de escritura, que es async/off-hot-path
    (lo llama `nucleo/memory_agent.ingest_utterance`, disparado fire-and-forget en `providers/nucleo.py`). El turno
    de voz NUNCA espera aquí. La LECTURA es siempre queries directas (retriever/state/recent_short), sin LLM.
  - **Proveedor configurable**: por defecto usa `gpt-4.1-mini` vía OpenAI según `config/v2.py`; puede apuntarse al
    endpoint OpenAI-compatible de Ollama para ejecución local. Configurable por `memory.mem_processor_*` o env,
    con modelo por invocación (no fija ninguna env global de cerebro).
  - **Fail-open**: si el modelo no está / falla / devuelve basura, `process()` devuelve `None` y el llamador
    cae a la heurística regex barata (`memory_agent.classify`) — la memoria nunca se queda sin escribir.

Salida por átomo (`process()` devuelve `list[dict]`)::

    {
      "text":        str,                       # enunciado CANÓNICO (no la frase cruda) — lo que se embebe/indexa
      "dest":        "state"|"short"|"long"|"discard",
      "kind":        "profile"|"pref"|"fact"|"event"|"result"|"intent",  # intent = deseo/intención a futuro
      "importance":  float,                     # 0..1 (relevancia CON contexto de la situación del operador)
      "ttl_days":    float | None,              # None = no caduca
      "slot":        str | None,                # clave canónica del hecho singular (operator.name, goal.current…)
      "concepts":    list[str],                 # 1-3 categorías LIGERAS (salud/finanzas/trabajo/familia…) → grafo
      "state_patch": dict,                      # merge en la tabla `state` (solo si dest=='state')
    }
"""
from __future__ import annotations

import asyncio
import json
import os
import time

from loguru import logger

_MAX_INPUT = 600            # chars del turno que ve el procesador (destila, no necesita el turno entero)
_TIMEOUT = float(os.getenv("MEM_PROCESSOR_TIMEOUT", "30"))   # s por INTENTO; off-hot-path pero acotado (release del slot)
# UA de navegador para el POST del CORAZÓN — AIMLAPI (tras Cloudflare) 403ea el UA por defecto de aiohttp; ver el uso.
_BROWSER_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
# REINTENTO ante fallo TRANSITORIO (auditoría 2026-07-29): un timeout/conexión/429/5xx de la API remota devolvía
# None → fail-open a la heurística lossy → PÉRDIDA DURABLE de ese turno (un hecho que el modelo SÍ destila bien se
# tiraba por un blip de red). Era la causa nº1 de los fallos "esperaba long, está []" del bot de memoria (medido:
# ~25% de timeouts intermitentes en una tanda). Escribir es off-hot-path y la doctrina lo permite LENTO → reintentar
# un blip antes de rendirse es correcto. Los 4xx de auth/bad-request NO se reintentan (fallan rápido, alertan).
_RETRIES = max(0, int(os.getenv("MEM_PROCESSOR_RETRIES", "2")))           # reintentos (=> _RETRIES+1 intentos)
_RETRY_BACKOFF = float(os.getenv("MEM_PROCESSOR_RETRY_BACKOFF", "1.5"))   # s base, escalado por intento


class _PermanentError(RuntimeError):
    """Error NO reintentable (4xx auth/bad-request): reintentar no ayuda → fail-open inmediato."""

# CAP DE CONCURRENCIA (2026-07-14, fix del corte de voz): el CORAZÓN es un LLM LOCAL PESADO (GPU). En la sesión
# manual 12:07-12:14 se disparaba en CADA turno sin límite → se APILABAN 15-29s en la GPU Metal (medido) →
# asfixiaban STT/TTS → la voz se cortaba a media frase. Cap a 1 distilación a la vez.
# NUNCA pilear en la GPU es más importante que destilar cada turno. Configurable (MEM_PROCESSOR_CONCURRENCY, def 1).
_CONCURRENCY = max(1, int(os.getenv("MEM_PROCESSOR_CONCURRENCY", "1")))
_sem = asyncio.Semaphore(_CONCURRENCY)
# COLA DIFERIDA corta (auditoría 2026-07-14): el SKIP-si-ocupado tiraba turnos enteros de destilación en
# conversación rápida — pérdida directa de write-completeness (la palanca nº1 del recall, V2-031). Ahora un
# turno que pilla la GPU ocupada ESPERA su turno (serial: sigue sin haber JAMÁS dos distilaciones a la vez en
# la GPU) con espera acotada; solo si ya hay _QUEUE_MAX esperando o se agota _QUEUE_WAIT cae a la heurística.
# Destilar tarde > no destilar (va off-hot-path, a nadie le corre prisa).
_QUEUE_MAX = max(0, int(os.getenv("MEM_PROCESSOR_QUEUE_MAX", "2")))
_QUEUE_WAIT = float(os.getenv("MEM_PROCESSOR_QUEUE_WAIT", "15"))   # s de espera máx. por el slot
_waiters = 0


# ── config (OpenAI por defecto; endpoint local OpenAI-compatible opcional) ──────────────────────────────────
def _config_url() -> str:
    try:
        from config import v2 as _v2
        return (_v2.get("memory").get("mem_processor_base_url") or "").strip()
    except Exception:
        return ""


# Último recurso si `config/v2.py` no se puede importar NI hay env: tiene que ser el MISMO par que el default de
# `config §memory` (2026-08-09). Antes caía a Ollama local (`qwen2.5:7b-instruct` @ 11434), que en cualquier
# instalación sin Ollama —toda la nube, y la mayoría de self-hosts— significaba fallar en cada turno y escribir
# por la heurística lossy en silencio. Un default que solo funciona en la máquina del que lo escribió no es
# un default. Ollama sigue siendo una OPCIÓN, apuntando `mem_processor_base_url` a localhost:11434 a mano.
_FALLBACK_URL = "https://api.aimlapi.com/v1"
_FALLBACK_MODEL = "deepseek/deepseek-v4-flash"


def _url() -> str:
    # Endpoint del CORAZÓN: config §memory.mem_processor_base_url → env → el mismo default que la config.
    u = _config_url()
    if u:
        return u
    return (os.getenv("MEM_PROCESSOR_URL")
            or os.getenv("ZAELAR_LOCAL_LLM_URL")
            or _FALLBACK_URL)


def _model() -> str:
    # Modelo del CORAZÓN de escritura. Va OFF-HOT-PATH (cola async) → su latencia NO la paga el turno de voz, así
    # que el eje de elección es calidad-vs-PRECIO. **DEFAULT = `deepseek/deepseek-v4-flash` vía AIMLAPI**
    # (2026-08-09, benchmarks §12.3: iguala a gpt-4.1-mini en completeness y precisión por −55% de coste).
    # CONFIGURABLE (`config/v2.py`/`config/v2.json §memory.mem_processor_model`); env MEM_PROCESSOR_MODEL = fallback
    # power-user; el literal de abajo solo se alcanza si la config no se puede importar (ver _FALLBACK_MODEL).
    # ⚠️ Si se apunta a un modelo LOCAL (Ollama), ojo al TRADE-OFF con la voz 100% local: corre en la MISMA GPU
    # Metal que STT/TTS → uno pesado puede CORTAR la voz aunque no pile (medido 15-29s). No aplica a la config de
    # producción, que va por nube y deja la GPU libre.
    try:
        from config import v2 as _v2
        m = (_v2.get("memory").get("mem_processor_model") or "").strip()
        if m:
            return m
    except Exception:
        pass
    return os.getenv("MEM_PROCESSOR_MODEL") or _FALLBACK_MODEL


def _endpoint_key(url: str) -> str:
    # Credencial POR ENDPOINT — la key sigue a la URL, nunca al revés. Resolución ÚNICA (`nucleo/provider_keys.py`,
    # V2-098): antes reimplementada aquí y en fast_client/susurro/memllm, cada una con su propia lista y ya
    # desincronizadas entre sí.
    from nucleo.provider_keys import key_for_endpoint
    return key_for_endpoint(url, default="local")


def _key() -> str:
    # Config §memory.mem_processor_api_key (inline) → resolución POR ENDPOINT. El env genérico MEM_PROCESSOR_KEY
    # solo aplica EMPAREJADO con MEM_PROCESSOR_URL (power-user/headless): con la URL saliendo de CONFIG jamás se usa
    # una key suelta del env — auditoría 2026-07-19: la key rancia de un bloque temporal del store se enviaba a
    # api.openai.com → 401 silencioso → 2 días de fail-open heurístico llenando el largo plazo de STT crudo.
    try:
        from config import v2 as _v2
        k = (_v2.get("memory").get("mem_processor_api_key") or "").strip()
        if k:
            return k
    except Exception:
        pass
    if _config_url():
        return _endpoint_key(_url())
    env_k = os.getenv("MEM_PROCESSOR_KEY")
    if env_k:
        return env_k
    return _endpoint_key(_url())


def enabled() -> bool:
    """El procesador LLM se puede apagar (env `MEM_PROCESSOR=0`) → todo cae a la heurística barata."""
    return os.getenv("MEM_PROCESSOR", "1").strip().lower() not in ("0", "false", "no", "off")


# ── SALUD del CORAZÓN (auditoría 2026-07-19: 2 días caído en silencio — un fallo de credencial/endpoint NUNCA
# puede volver a ser logger.debug). Racha de fallos consecutivos → ALERTA observable (◉/debug/SSE) al cruzar el
# umbral, y aviso de recuperación al volver. `status()` lo expone al área de config. ─────────────────────────────
_ALERT_AFTER = max(1, int(os.getenv("MEM_PROCESSOR_ALERT_AFTER", "3")))
_fail_streak = 0
_last_error: str = ""
_last_ok_ts: float = 0.0
_alerted = False


def status() -> dict:
    """Salud del CORAZÓN para el área de config / diagnóstico."""
    return {"model": _model(), "url": _url(), "fail_streak": _fail_streak,
            "last_error": _last_error, "last_ok_ts": _last_ok_ts, "degraded": _alerted}


def _mark_ok() -> None:
    global _fail_streak, _last_ok_ts, _alerted
    _last_ok_ts = time.time()
    if _alerted:
        # V2-066 (2026-07-24, petición del operador): NADA de banner superior para esto — el ◉ de estado YA
        # existe para "algo va mal, ábrelo y mira qué pasa"; un `health_state` (mismo sustrato que LLM/STT/TTS)
        # es lo que /api/status lee para pintar el icono en verde/ámbar/rojo. `emit("alert", …)` disparaba
        # `store.showAlert()` en el frontend — un banner — que el operador pidió explícitamente quitar.
        try:
            from voice import health_state
            health_state.clear("memory")
        except Exception:
            pass
        logger.warning(f"mem_processor: RECUPERADO ({_model()}) tras {_fail_streak} fallos")
    _fail_streak = 0
    _alerted = False


def _mark_fail(err: str) -> None:
    global _fail_streak, _last_error, _alerted
    _fail_streak += 1
    _last_error = err
    logger.warning(f"mem_processor: fallo {_fail_streak}/{_ALERT_AFTER} ({_model()} @ {_url()}): {err[:160]} → heurística")
    if _fail_streak >= _ALERT_AFTER and not _alerted:
        _alerted = True
        try:
            from voice import health_state
            health_state.record("memory", "outage",
                                f"{_fail_streak} fallos ({_model()} @ {_url()}): {err[:160]} — heurística")
        except Exception:
            pass


# ── CONSUMO REAL (2026-08-09) — el CORAZÓN es una llamada LLM de nube como cualquier otra, y hasta hoy era la
# ÚNICA que no reportaba a Energy: `report_llm_usage` solo se llamaba desde `flash/fast_client.py`, los Brain
# Workers y el generador de widgets. En una cuenta cloud eso significaba destilar cada turno GRATIS en el
# contador — exactamente el agujero que la addenda de INI-019 cerró para la voz. Mismo contrato que el resto:
# fire-and-forget, fail-open, no-op fuera de demo/cuenta cloud. `last_usage()` además expone los tokens reales
# al bench de destilación (§12.3), que calcula el $/1k turnos con números medidos, no estimados.
_last_usage: dict = {}


def last_usage() -> dict:
    """Tokens de la ÚLTIMA destilación (`{prompt_tokens, completion_tokens, total_tokens}`), `{}` si el proveedor
    no los devolvió. Solo diagnóstico/bench — el camino de escritura no lo consume."""
    return dict(_last_usage)


def _record_usage(usage: dict | None) -> None:
    global _last_usage
    if not isinstance(usage, dict):
        _last_usage = {}
        return
    _last_usage = {k: usage.get(k) for k in ("prompt_tokens", "completion_tokens", "total_tokens")}
    from nucleo import energy_meter as _energy
    _energy.meter_openai_response({"usage": usage}, base_url=_url(), model=_model())


# ── prompt (afinable; se destila sobre turnos reales) ───────────────────────────────────────────────────────
_SYSTEM = """Eres el PROCESADOR DE MEMORIA de un asistente personal por voz. Recibes UN turno del operador (lo que
dijo) y el ESTADO actual que el asistente ya conoce. Tu trabajo: DESTILAR ese turno en 0..N "píldoras" de memoria
—hechos/preferencias CANÓNICOS, no la frase literal— y decidir para cada una DÓNDE va y cuánto importa.

Por CADA píldora decides:
- text: el hecho en forma CANÓNICA, breve y autocontenida, en tercera persona o como dato ("El operador se llama
  Marta", "Prefiere trato directo, sin rodeos", "Trabaja en su tienda online"). NO copies la frase cruda.
- dest: uno de:
  · "state"  = identidad/situación ESENCIAL que sitúa al asistente (nombre del operador, su objetivo actual, su
    proyecto de trabajo, dónde vive/trabaja, trato preferido). Poquísimas cosas. Va SIEMPRE en el prompt.
  · "long"   = DURADERO y digno de recordar: gustos, datos personales, decisiones, resultados, y **experiencias
    o eventos VIVIDOS aunque sean del pasado** (un viaje, una compra, una búsqueda, una reunión importante,
    "el mes pasado…", "la semana pasada…"). Si un humano lo recordaría semanas o meses después → long.
  · "short"  = SOLO contexto EFÍMERO de HOY sin valor duradero (estado de ánimo del momento, el tiempo que hace,
    "tengo hambre ahora"). Si mañana ya no importa → short. En la duda entre short y long, elige long.
  IMPORTANTE: "evento vivido" NO convierte toda actividad cotidiana en long. Café, comida, trayecto, compra menor,
  recado rutinario o cansancio del día → short con TTL 1-20 días, salvo que el turno explique por qué fue
  excepcional. En cambio un accidente, incendio, operación, logro o incidente laboral significativo → long.
  NO inventes intenciones a partir de una predicción banal ("mañana estaré mejor" no es un objetivo ni un deseo).
  NUNCA descartes PETICIONES, TAREAS, COMPROMISOS, CITAS o RECADOS, aunque vengan de otra persona ("X me pidió Y
  para el día Z", "tengo cita el jueves", "me han encargado…"): guárdalos (long si son relevantes/importan más de
  un día; short si son solo de hoy). Tampoco descartes datos concretos con NÚMEROS/fechas/importes/direcciones.
  · "discard"= sin valor para recordar (saludos, charla vacía, órdenes al asistente, ruido de transcripción).
  ⚠️ Un dato SENSIBLE que el operador te da PIDIÉNDOTE recordarlo (una contraseña suya, un PIN, un código) SÍ se
  guarda — eres SU memoria personal y local, negarte es fallarle ("¿cuál era mi contraseña?" debe funcionar).
  Guárdalo como long/fact con importance alta; NUNCA lo descartes por parecer "sensible".

  ★ NO TE QUEDES EN EL DATO LITERAL — INFIERE INTERESES E INTENCIONES (clave, genera píldoras EXTRA):
  De lo que dice el operador, además del hecho, EXTRAE (como píldoras separadas, dest=long):
    (a) INTERESES latentes (kind="pref"): lo que le atrae/gusta, aunque no lo diga con esas palabras. Ej: "hagamos
        un estudio para un viaje de buceo" → interés por el BUCEO y por los viajes de mar. "me he leído tres libros
        de Nolan" → le interesa el cine de Nolan.
    (b) INTENCIONES / DESEOS a futuro (kind="intent"): lo que QUIERE hacer/probar/conseguir, aunque no sepamos si
        se hará. Ej: "hagamos un estudio para un viaje de buceo" → INTENCIÓN de hacer un viaje (de buceo). "algún día
        me gustaría aprender a navegar" → intención de aprender a navegar. Son DESEOS ABIERTOS: persisten (nunca
        sabemos si se cumplieron) hasta que el operador diga lo contrario; NO son tareas que te delega a TI.
  Estas píldoras inferidas sirven para que, en el futuro, ante "me apetecería un viaje", el asistente SEPA que le
  gusta el buceo y que quería un viaje de mar — para tenerlo en cuenta y PREGUNTAR, sin encasillarse. Escribe el
  interés/intención en 3ª persona y canónico ("Le interesa el buceo." / "Quiere hacer un viaje de buceo.").
- kind: "profile" (identidad) | "pref" (preferencia/deseo) | "fact" (hecho) | "event" (algo que pasó) | "result".
- importance: 0.0-1.0. Súbela si es RELEVANTE A LA SITUACIÓN del operador según el ESTADO (si estudia Derecho, algo
  de Derecho importa más; si su proyecto es zaelar, algo de zaelar importa más). Identidad→0.9. Charla efímera→0.2.
- ttl_days: null si no caduca (identidad, hechos duraderos); un número pequeño (p.ej. 1-7) para lo efímero.
- slot: SOLO para ATRIBUTOS SINGULARES del operador — los que tienen UN ÚNICO valor vigente, de modo que una
  corrección/repetición SOBRESCRIBE (invalida) el anterior. SIEMPRE asígnalo cuando aplique — permite deduplicar y
  corregir de forma determinista (sin depender del fraseo). USA EXACTAMENTE una clave de este catálogo:
  {SLOT_CATALOG}.
  ⚠️ goal.current = el objetivo VITAL/profesional del OPERADOR (lo que ÉL quiere lograr: "lanzar mi empresa",
  "cerrar la ronda"). NUNCA una TAREA que te delega a TI ("ayúdame a escribir un podcast", "búscame vuelos") →
  eso es una tarea/encargo, va a dest=long kind=result, jamás a goal.current ni al state.objetivo.
  ⚠️ MUY IMPORTANTE: un `slot` INVALIDA todo lo anterior con ese mismo slot. NO lo uses para hechos ADITIVOS de los
  que puede haber VARIOS a la vez: ALERGIAS (se puede ser alérgico a varias cosas), idiomas, aficiones/gustos,
  personas del entorno, eventos, mensajes, transacciones, habilidades → slot=null SIEMPRE. Ejemplo del error a
  evitar: "alérgico a los frutos secos" NO es dieta → slot=null (si lo pusieras en operator.diet, un cambio de
  dieta borraría la alergia). En la duda entre singular y aditivo → null (aditivo no destruye nada).
- value: SOLO si hay slot — el VALOR escueto y limpio del hecho singular ("Valencia", "Marta", "vegetariana").
  Con slot+value el sistema actualiza el estado él solo; sin value el hecho puede no llegar al estado.
- change: la SEÑAL DE CAMBIO del hecho (tú entiendes CUALQUIER idioma; esta señal NO depende del fraseo):
  · "update"     = el operador DECLARA que un hecho singular suyo HA CAMBIADO (una mudanza, cambio de trabajo/
    coche/objetivo: "me acabo de mudar a X", "ya no trabajo en Y", "I've moved to X", "ara visc a X"…).
  · "correction" = CORRIGE un dato que quedó mal guardado ("no me llamo X, sino Y", "en realidad es Z").
  · "none"       = todo lo demás (primer dato, refuerzo, hecho suelto).
- state_patch: SOLO si dest=="state". Objeto con las claves del estado a fijar. Claves: operator_name, location,
  treatment, objetivo, proyecto (o una clave libre en minúsculas para otros datos de identidad: hardware, car,
  empresa…). Ej: {"operator_name":"Marta"}.
- concepts: 1-3 CATEGORÍAS ligeras (una palabra, minúsculas) que ORGANIZAN el dato conceptualmente, para agrupar
  hechos afines. Vocabulario abierto pero CORTO y reutilizable: salud, finanzas, trabajo, familia, ocio, vivienda,
  estudios, viajes, tecnología, deporte, comida, relaciones, agenda… Ej: "alérgico a frutos secos"→["salud"];
  "hipoteca de 250.000€"→["finanzas","vivienda"]; "juega al pádel"→["deporte","ocio"]. Píldora trivial/efímera → [].

Responde SOLO con un array JSON de píldoras (posiblemente vacío []). Sin texto fuera del JSON. Si el turno no
aporta nada memorable, devuelve []."""

# El catálogo de slots del prompt se GENERA del registro único `memory/slots.py` (auditoría 2026-07-14): el
# vocabulario que ve el modelo y el que normaliza/protege el host son EL MISMO por construcción.
from memory import slots as _memslots  # noqa: E402  (stdlib puro, sin ciclos)

_SYSTEM = _SYSTEM.replace("{SLOT_CATALOG}", _memslots.prompt_catalog())

# Fewshots NEUTROS (auditoría 2026-07-14): antes protagonizaba el OPERADOR REAL ("Ricard", proyecto "zaelar")
# — dato de fábrica en el camino de escritura que sesgaba al modelo pequeño (podía ecoar ese nombre ante un
# garble). Los ejemplos usan una persona ficticia cualquiera; el sistema se sirve EN BLANCO.
_FEWSHOT_USER = """ESTADO actual: (vacío)
Turno del operador: "Hola, mira, me llamo Marta y estoy montando una tienda online de cerámica. Ah, y prefiero que me hables directo, sin tanto rodeo." """

_FEWSHOT_ASSISTANT = """[{"text":"La operadora se llama Marta.","dest":"state","kind":"profile","importance":0.95,"ttl_days":null,"slot":"operator.name","value":"Marta","change":"none","state_patch":{"operator_name":"Marta"}},
{"text":"Su proyecto de trabajo actual es una tienda online de cerámica.","dest":"state","kind":"profile","importance":0.85,"ttl_days":null,"slot":"project.current","value":"tienda online de cerámica","change":"none","state_patch":{"proyecto":"tienda online de cerámica"}},
{"text":"Prefiere trato directo, sin rodeos.","dest":"state","kind":"pref","importance":0.8,"ttl_days":null,"slot":"operator.treatment","value":"directo, sin rodeos","change":"none","state_patch":{"treatment":"directo, sin rodeos"}}]"""

_FEWSHOT_USER_2 = """ESTADO actual: operator_name=Marta
Turno del operador: "vale, gracias, cierra eso" """

_FEWSHOT_ASSISTANT_2 = "[]"

# Tercer shot: gustos/aficiones y posesiones/hechos personales DURADEROS → LARGO PLAZO (no estado, no descarte).
# Es el fallo típico del modelo pequeño: infravalora "me encanta X" / "tengo un Y" y no lo guarda.
_FEWSHOT_USER_3 = """ESTADO actual: operator_name=Marta
Turno del operador: "Me encanta el pádel, juego cada martes. Ah, y tengo un perro que se llama Simba." """

_FEWSHOT_ASSISTANT_3 = """[{"text":"Le encanta el pádel; juega cada martes.","dest":"long","kind":"pref","importance":0.75,"ttl_days":null,"slot":null,"change":"none","concepts":["deporte","ocio"],"state_patch":{}},
{"text":"Tiene un perro llamado Simba.","dest":"long","kind":"fact","importance":0.7,"ttl_days":null,"slot":null,"change":"none","concepts":["familia"],"state_patch":{}}]"""

# Cuarto shot: EXPERIENCIAS/EVENTOS del pasado → LARGO (no efímeros). El modelo tiende a mandarlos a short por
# la marca temporal ("el mes pasado"); un viaje o una búsqueda se recuerdan meses después → durable.
_FEWSHOT_USER_4 = """ESTADO actual: operator_name=Marta, location=Zaragoza
Turno del operador: "El mes pasado hice un viaje a Oporto y me encantó, y la semana pasada estuve mirando coches de segunda mano." """

_FEWSHOT_ASSISTANT_4 = """[{"text":"El mes pasado viajó a Oporto y le encantó.","dest":"long","kind":"event","importance":0.65,"ttl_days":null,"slot":null,"change":"none","state_patch":{}},
{"text":"La semana pasada estuvo mirando coches de segunda mano.","dest":"long","kind":"event","importance":0.6,"ttl_days":null,"slot":null,"change":"none","state_patch":{}}]"""

# Quinto shot: INFERIR interés + intención a futuro del dato literal (lo pidió el operador). De "estudio para un
# viaje de buceo" → interés por el buceo (pref) + intención de un viaje de buceo (intent). Deseos ABIERTOS.
_FEWSHOT_USER_5 = """ESTADO actual: operator_name=Marta
Turno del operador: "Oye, hagamos un estudio para organizar un viaje de buceo el año que viene." """

_FEWSHOT_ASSISTANT_5 = """[{"text":"Le interesa el buceo.","dest":"long","kind":"pref","importance":0.7,"ttl_days":null,"slot":null,"change":"none","concepts":["deporte","ocio","viajes"],"state_patch":{}},
{"text":"Quiere hacer un viaje de buceo el año que viene.","dest":"long","kind":"intent","importance":0.7,"ttl_days":null,"slot":null,"change":"none","concepts":["viajes","ocio"],"state_patch":{}}]"""

# Sexto shot (auditoría 2026-07-14, cierre del retest V2-038): CAMBIO DECLARADO de un hecho singular — la señal
# `change:"update"` la emite EL MODELO (que entiende cualquier fraseo/idioma), no una regex del host. Con
# slot+value+change el estado se actualiza y la píldora vieja queda superseded, diga como lo diga el operador.
_FEWSHOT_USER_6 = """ESTADO actual: operator_name=Marta, location=Zaragoza
Turno del operador: "Ah, por cierto, me acabo de mudar a Valencia." """

_FEWSHOT_ASSISTANT_6 = """[{"text":"Vive en Valencia.","dest":"state","kind":"profile","importance":0.95,"ttl_days":null,"slot":"operator.location","value":"Valencia","change":"update","concepts":["vivienda"],"state_patch":{"location":"Valencia"}}]"""

# Séptimo shot: conversación con VARIOS hechos mezclados. Obliga a no quedarse solo con el perfil evidente.
_FEWSHOT_USER_7 = """ESTADO actual: (vacío)
Turno del operador: "Hoy en el hospital atendimos una emergencia bastante seria. Soy enfermera. Antes vivía en Granada, pero ahora vivo en Málaga; quizá algún día me vaya a Cádiz, todavía no lo sé." """

_FEWSHOT_ASSISTANT_7 = """[{"text":"Trabaja como enfermera.","dest":"state","kind":"profile","importance":0.9,"ttl_days":null,"slot":"operator.job","value":"enfermera","change":"none","concepts":["trabajo"],"state_patch":{"job":"enfermera"}},
{"text":"Hoy atendió una emergencia seria en el hospital.","dest":"long","kind":"event","importance":0.75,"ttl_days":null,"slot":null,"change":"none","concepts":["trabajo","salud"],"state_patch":{}},
{"text":"Vivía anteriormente en Granada.","dest":"long","kind":"event","importance":0.55,"ttl_days":null,"slot":null,"change":"none","concepts":["vivienda"],"state_patch":{}},
{"text":"Vive en Málaga.","dest":"state","kind":"profile","importance":0.95,"ttl_days":null,"slot":"operator.location","value":"Málaga","change":"none","concepts":["vivienda"],"state_patch":{"location":"Málaga"}},
{"text":"Considera mudarse a Cádiz en el futuro, sin una decisión tomada.","dest":"long","kind":"intent","importance":0.5,"ttl_days":null,"slot":null,"change":"none","concepts":["vivienda"],"state_patch":{}}]"""

# Octavo shot: cotidianeidad efímera. No promocionar café ni fabricar objetivos a partir de "mañana estaré bien".
_FEWSHOT_USER_8 = """ESTADO actual: operator_name=Marta
Turno del operador: "Esta mañana tomé un café al volver del trabajo y ahora estoy cansada, pero mañana ya estaré bien." """

_FEWSHOT_ASSISTANT_8 = """[{"text":"Esta mañana tomó un café al volver del trabajo.","dest":"short","kind":"event","importance":0.2,"ttl_days":7,"slot":null,"change":"none","concepts":[],"state_patch":{}},
{"text":"Ahora está cansada.","dest":"short","kind":"fact","importance":0.3,"ttl_days":1,"slot":null,"change":"none","concepts":[],"state_patch":{}}]"""


_LANG_NAME = {"es": "castellano", "en": "English", "de": "Deutsch", "fr": "français", "it": "italiano",
              "pt": "português", "ca": "català"}


def _default_code() -> str:
    try:
        from voice.engine.core import langs
        return langs.current_code()
    except Exception:
        return "en"


def _render(text: str, state: dict | None) -> str:
    st = state or {}
    keep = {k: st.get(k) for k in ("operator_name", "location", "treatment", "objetivo", "proyecto")
            if st.get(k)}
    snap = ", ".join(f"{k}={v}" for k, v in keep.items()) or "(vacío)"
    # IDIOMA CANÓNICO de la memoria = el del operador (decisión 2026-07-10: la memoria es MONOLINGÜE, en el idioma
    # de la persona; el sistema entero se adapta a ese idioma). Si el operador suelta algo en otro idioma, se DESTILA
    # igualmente traduciendo la píldora al idioma canónico — NUNCA se descarta un dato durable por venir en otro idioma.
    # Same fix as memllm: no hardcoded language. An unseeded state must not silently mean Spanish — that is
    # what committed a brand-new account's memory to a language its owner had not chosen.
    code = st.get("language") or _default_code()
    lang = _LANG_NAME.get(code, _LANG_NAME["en"])
    return (f"ESTADO actual: {snap}\n"
            f"IDIOMA DE LA MEMORIA: {lang}. Escribe SIEMPRE las píldoras en {lang}, aunque el operador hable en "
            f"otro idioma (tradúcelo). Un dato memorable dicho en otro idioma NO se descarta: se guarda en {lang}.\n"
            f"Turno del operador: \"{(text or '').strip()[:_MAX_INPUT]}\"")


# ── API ─────────────────────────────────────────────────────────────────────────────────────────────────────
async def process(text: str, *, state: dict | None = None) -> list[dict] | None:
    """DESTILA `text` en píldoras de memoria (ver módulo). NUNCA lanza. Semántica del retorno (importa para el
    llamador):
      - **`None`** = el modelo NO está disponible / desactivado / falló → el llamador debe caer a la heurística.
      - **`[]`**   = el modelo CORRIÓ y decidió que no hay nada memorable → DESCARTE legítimo (no caer a heurística).
      - `[átomos]` = píldoras curadas a guardar."""
    global _waiters
    t = (text or "").strip()
    if not t or not enabled():
        return None
    # COLA DIFERIDA (auditoría 2026-07-14, antes SKIP-si-ocupado): con la GPU ocupada, el turno ESPERA su slot
    # (serial — jamás dos distilaciones a la vez en la GPU, el anti-pileup se conserva) en vez de perderse.
    # Solo cae a la heurística (None) si la cola está llena o la espera se agota — pérdida de write-completeness
    # acotada y OBSERVABLE (evento perf), ya no silenciosa por defecto.
    if _sem.locked() and _waiters >= _QUEUE_MAX:
        try:
            from voice.observer import perf
            perf(f"CORAZÓN mem_processor SKIP (GPU ocupada, cola llena {_waiters}/{_QUEUE_MAX})",
                 module="memory", func="mem_processor.process")
        except Exception:
            pass
        return None
    import aiohttp
    payload = {
        "model": _model(),
        "temperature": 0,
        "messages": [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": _FEWSHOT_USER},
            {"role": "assistant", "content": _FEWSHOT_ASSISTANT},
            {"role": "user", "content": _FEWSHOT_USER_2},
            {"role": "assistant", "content": _FEWSHOT_ASSISTANT_2},
            {"role": "user", "content": _FEWSHOT_USER_3},
            {"role": "assistant", "content": _FEWSHOT_ASSISTANT_3},
            {"role": "user", "content": _FEWSHOT_USER_4},
            {"role": "assistant", "content": _FEWSHOT_ASSISTANT_4},
            {"role": "user", "content": _FEWSHOT_USER_5},
            {"role": "assistant", "content": _FEWSHOT_ASSISTANT_5},
            {"role": "user", "content": _FEWSHOT_USER_6},
            {"role": "assistant", "content": _FEWSHOT_ASSISTANT_6},
            {"role": "user", "content": _FEWSHOT_USER_7},
            {"role": "assistant", "content": _FEWSHOT_ASSISTANT_7},
            {"role": "user", "content": _FEWSHOT_USER_8},
            {"role": "assistant", "content": _FEWSHOT_ASSISTANT_8},
            {"role": "user", "content": _render(t, state)},
        ],
    }
    url = _url().rstrip("/") + "/chat/completions"
    local = any(h in url for h in ("11434", "localhost", "127.0.0.1"))
    t0 = time.time()
    # FASE 3: marca CONTENCIÓN mientras el CORAZÓN destila (LLM LOCAL qwen, GPU) → el turno correlaciona su TTFT
    # con esto. Solo si es LOCAL (el remoto no contende con la GPU del STT/TTS).
    try:
        from voice.observer import mark_busy as _mb
    except Exception:
        _mb = None
    # ADQUIERE EL SLOT (cap de concurrencia, espera ACOTADA — la cola diferida): mientras dure una distilación,
    # los demás turnos esperan en fila (serial en la GPU, sin pileup) hasta _QUEUE_WAIT; si se agota, heurística.
    _waiters += 1
    try:
        await asyncio.wait_for(_sem.acquire(), timeout=_QUEUE_WAIT)
    except (asyncio.TimeoutError, TimeoutError):
        try:
            from voice.observer import perf
            perf(f"CORAZÓN mem_processor SKIP (espera de slot > {_QUEUE_WAIT:g}s)",
                 module="memory", func="mem_processor.process")
        except Exception:
            pass
        return None
    finally:
        _waiters -= 1
    try:
        if _mb and local:
            _mb("corazon", True)
        try:
            atoms = None
            for _attempt in range(_RETRIES + 1):
                try:
                    to = aiohttp.ClientTimeout(total=_TIMEOUT)
                    async with aiohttp.ClientSession(timeout=to) as s:
                        # UA de navegador: AIMLAPI va tras Cloudflare y 403ea el User-Agent por defecto de aiohttp
                        # (igual que fast_client con el SDK OpenAI — ver su _BROWSER_UA). Sin esto, apuntar el CORAZÓN
                        # a AIMLAPI (config §memory.mem_processor_base_url) 403ea SIEMPRE → todo escribe por heurística.
                        # Inocuo para OpenAI/Ollama/otros endpoints; el header sobra pero no molesta.
                        # EGRESS (T304): con salida mediada, ni el destino ni la credencial son del
                        # proveedor. `url` ya trae `/chat/completions`, así que se reenruta la BASE.
                        from nucleo import llm_egress
                        _base, _tok, _extra = llm_egress.route(_url(), _key())
                        _dest = _base.rstrip("/") + "/chat/completions" if _extra else url
                        _headers = {"Authorization": f"Bearer {_tok}", **(_extra or {})}
                        if not _extra:
                            _headers["User-Agent"] = _BROWSER_UA
                        async with s.post(_dest, headers=_headers, json=payload) as r:
                            # CUALQUIER 2xx es una respuesta buena (2026-08-09): AIMLAPI devuelve **HTTP 201** con
                            # un cuerpo de completion perfectamente válido para algunos modelos (visto con
                            # `zhipu/glm-4.7`). Exigir `== 200` convertía eso en un fallo → fail-open a la heurística
                            # lossy en CADA turno, en silencio, para quien configurase uno de esos modelos.
                            if not (200 <= r.status < 300):
                                body = (await r.text())[:200]
                                # 4xx (salvo 429) = auth/bad-request: PERMANENTE, reintentar no ayuda → fail-open ya.
                                if 400 <= r.status < 500 and r.status != 429:
                                    raise _PermanentError(f"HTTP {r.status} de {url}: {body}")
                                raise RuntimeError(f"HTTP {r.status} de {url}: {body}")
                            data = await r.json()
                    content = data["choices"][0]["message"]["content"]
                    atoms = _parse(content)
                    _record_usage(data.get("usage"))
                    _mark_ok()
                    break
                except _PermanentError as e:
                    _mark_fail(f"{e}")
                    return None
                except Exception as e:  # noqa: BLE001  (timeout / conexión / 429 / 5xx = TRANSITORIO → reintenta)
                    if _attempt < _RETRIES:
                        await asyncio.sleep(_RETRY_BACKOFF * (_attempt + 1))
                        continue
                    _mark_fail(f"{type(e).__name__}: {e}")
                    return None
        finally:
            if _mb and local:
                _mb("corazon", False)
    finally:
        _sem.release()
    _ms = round((time.time() - t0) * 1000)
    try:
        from voice.observer import emit, perf
        emit("memory", "procesador", role="system",
             text=f"«{t[:50]}» → {len(atoms)} píldora(s)",
             extra={"layer": "write", "model": _model(), "engine": "local" if local else "remote",
                    "proc_ms": _ms})
        # PERF (V2-037): el CORAZÓN es un LLM LOCAL (GPU) que puede contender con STT/voz — visible en System Events.
        perf(f"CORAZÓN mem_processor {_model()} {_ms}ms" + (" ⚠️LOCAL/GPU" if local else ""),
             module="memory", func="mem_processor.process", ms=_ms)
    except Exception:
        pass
    return atoms


def _parse(content: str) -> list[dict]:
    """Extrae el array JSON aunque venga con texto/```json alrededor. Devuelve solo átomos bien formados."""
    txt = (content or "").strip()
    start, end = txt.find("["), txt.rfind("]")
    if start == -1 or end == -1:
        return []
    try:
        arr = json.loads(txt[start:end + 1])
    except Exception:
        return []
    out: list[dict] = []
    for a in arr:
        if not isinstance(a, dict):
            continue
        text = (a.get("text") or "").strip()
        dest = (a.get("dest") or "").strip().lower()
        if not text or dest not in ("state", "short", "long", "discard"):
            continue
        if dest == "discard":
            continue
        try:
            imp = float(a.get("importance", 0.5))
        except (TypeError, ValueError):
            imp = 0.5
        ttl = a.get("ttl_days")
        try:
            ttl = float(ttl) if ttl is not None else None
        except (TypeError, ValueError):
            ttl = None
        patch = a.get("state_patch") if isinstance(a.get("state_patch"), dict) else {}
        # concepts (T126): 1-3 etiquetas ligeras de categoría → nodos/aristas del grafo. Normaliza a lista de str
        # minúsculas, acotada a 3. Tolerante: string suelto, None, o basura → [].
        raw_c = a.get("concepts")
        if isinstance(raw_c, str):
            raw_c = [raw_c]
        concepts = [str(c).strip().lower() for c in raw_c if str(c).strip()][:3] if isinstance(raw_c, list) else []
        # CONTRATO v2 (auditoría 2026-07-14): `value` (el valor escueto del hecho singular — permite al host
        # sintetizar el state_patch MECÁNICAMENTE) + `change` (señal semántica none|update|correction que consume
        # el gate anti-garble P0b — la emite el modelo multilingüe, no una regex del host).
        change = (a.get("change") or "none").strip().lower()
        if change not in ("none", "update", "correction"):
            change = "none"
        value = (str(a.get("value")).strip()[:120] if a.get("value") is not None else "") or None
        out.append({
            "text": text[:400],
            "dest": dest,
            "kind": (a.get("kind") or "fact").strip().lower(),
            "importance": max(0.0, min(1.0, imp)),
            "ttl_days": ttl,
            "slot": (a.get("slot") or None) or None,
            "value": value,
            "change": change,
            "concepts": concepts,
            "state_patch": patch if dest == "state" else {},
        })
    return out
