"""nucleo/dispatch.py — GESTOR de sesiones de Brain Workers (V2-038; reencuadra el dispatcher V2-006/V2-036).

Recibe las escaladas del FlashBrain (`bus:escalate.requested`) y las convierte en **Brain Workers** vivos
(`nucleo/workers/`): backend agnóstico (`get_backend`) conducido por una `WorkerSession`. Mantiene el **ÚNICO
REGISTRO EN RAM** de sesiones vivas (`_SESSIONS`), que es la **FUENTE DE VERDAD** (§v2·C) — absorbe y reemplaza los
tres registros parciales de antes (`escalate._tasks`, `_INFLIGHT`, `_SESSIONS` viejos, §v3·G). Expone:
  · `active_sessions()`/`has_active()`/`pending_summaries()` — proyección para ESTADO/prompt/`/api/tasks`.
  · `inject(which, msg)` — inyecta a una sesión viva (↓, refinamiento; reemplaza el dedup-descartar de V2-029).
  · `cancel_session(tid)`/`cancel_all()` — MATAR con cortesía (kill de grupo vía el backend).
  · `resolve_sessions(query)` — "para ese proceso" → tid(s) deterministas.

Confirm-gate de irreversibles (V2-007) y clasificación de kind se conservan. Diseño:
initiatives/V2-038-brain-workers-interactivos.md.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import secrets as _secrets
import secrets
import time
import unicodedata
from dataclasses import dataclass, field
from typing import Any

from loguru import logger

from nucleo import dev_worker_guard, research
from nucleo.workers import WorkerSpec, get_backend, workdir
from nucleo import surfaces
from nucleo.workers.session import SessionRecord, WorkerSession
# Prompt composition (pure, no session-pool state) split out (V2-098) into its own module; re-exported by name
# so existing call sites (below, and tests doing dispatch._build_prompt/_web_prompt) keep working unchanged.
from nucleo.dispatch_prompts import _build_prompt, _web_prompt  # noqa: F401

# Heurística de clasificación (solo cuando el escalado no fija `kind`). Conservadora.
# kind="web" = hay que ENTRAR a un sitio concreto y operarlo con un navegador real (modalidad 2 de la decisión
# «búsqueda web» de CLAUDE.md: marketplaces, login, automatizar una gestión). NO es «el dato está en internet» —
# eso es INVESTIGACIÓN (modalidad 3) y la hace un worker genérico con WebSearch/WebFetch, que es muchísimo más
# rápido y no se pelea con banners de cookies.
#
# Se quitan de aquí «en la web» y «en internet» (2026-08-02): «investiga EN INTERNET y prepárame un informe»
# casaba y mandaba la tarea al navegador. Observado en vivo con la narración del worker: 7 minutos peleándose con
# el banner de cookies de aquopolis.es, clicando por coordenadas y pidiendo análisis de imagen, para sacar un
# precio que `web_search` + `fetch` habían dado en segundos en la corrida anterior. Decir dónde vive un dato no es
# pedir que se abra un navegador.
_WEB_RE = re.compile(
    r"\b(en\s+wallapop|wallapop|en\s+amazon|amazon|navegador|abre\s+la\s+web|abre\s+la\s+p[áa]gina|"
    r"en\s+linkedin|linkedin|en\s+el\s+sitio|en\s+la\s+p[áa]gina|automatiza|"
    r"in[ií]ciame?\s+sesi[óo]n|log[ui]n)\b", re.I)
# El generador (kind="code") SOLO construye/modifica el CÓDIGO de un widget. Antes `_CODE_RE` matcheaba la palabra
# «widget/tarjeta/panel» A SECAS → CUALQUIER tarea que la mencionara (p.ej. «abre y muestra el mensaje… se refleja
# en el widget de mensajería») caía en el generador y CONSTRUÍA un widget basura (incidente 2026-08-01, clase del
# 25/07). Fix V2-081: exige un VERBO de crear/modificar CÓDIGO junto al nombre — coherente con el guard del router
# (`looks_like_create_widget`, que también usa verbo+nombre); create se reutiliza de ahí (fuente única), aquí solo
# se añade el lado MODIFICAR-código. Mostrar/abrir/leer/gestionar un widget existente NO es código → kind="generic"
# (un worker general que, si hace falta, OPERA el widget vía hbwidget — nunca lo regenera).
_MODIFY_CODE_RE = re.compile(
    r"\b(modific\w*|cambi\w*|edit\w*|reescrib\w*|refactor\w*|redise[nñ]\w*|actualiz\w+ el c[oó]digo|"
    r"a[ñn]ad\w*\s+(?:una?\s+)?columna|modify|redesign|rewrite)\b[^.!?]{0,45}\b(widget|tarjeta|panel|componente)\b",
    re.I)
# …y lo MISMO con «proyecto», que estaba A SECAS una línea debajo del comentario que lo prohíbe (incidente
# 2026-08-12, auditando una búsqueda de veleros de punta a punta). El criterio que dio el propio operador era
# «listo para navegar, no un PROYECTO para restaurar» — en la compraventa de barcos «un proyecto» es el término
# corriente para un barco a medio reformar. Esa palabra sola mandó su BÚSQUEDA al `kind="code"`, o sea al backend
# del GENERADOR de widgets (`registry.get_backend` elige por `spec.kind`): un buscador despachado al sitio que
# escribe código. Es la misma clase exacta que V2-081, sin arreglar en esta rama.
# `architect` se queda A SECAS a propósito: es el nombre de nuestro conector, nadie lo dice de pasada. «Proyecto»
# es una palabra del castellano de todos los días, así que exige —como el lado MODIFICAR-código— un VERBO de
# trabajo de proyecto delante, o una palabra de repositorio detrás.
_ARCHITECT_RE = re.compile(
    r"\barchitect\b"
    r"|\b(crea\w*|monta\w*|arranca\w*|planifica\w*|retoma\w*|abre|cierra|a[ñn]ad\w*|actualiz\w*|"
    r"create|start|plan)\b[^.!?]{0,45}\bproyecto\b"
    r"|\bproyecto\b[^.!?]{0,45}\b(repo\w*|rama\w*|commit\w*|c[oó]digo|tarea\w*|meshkore|daemon)\b",
    re.I)
# …y el contrapeso: LLENAR un widget con datos NO es tocar su código (incidente 2026-08-02). El brief «finaliza y
# muestra el informe … REFLEJANDO EL CAMBIO en el widget de informes» casaba `cambi\w*` + `widget` dentro de la
# ventana de 45 chars → se despachó al GENERADOR, que se pasó 3,5 min REESCRIBIENDO widget.js para un caso que solo
# necesitaba una data-op, y el operador siguió sin ver nada. Un verbo de DATOS/PRESENTACIÓN en la misma frase gana:
# la petición es «pon estos datos ahí», no «cámbiame el componente». (Crear un widget nuevo sigue mandando: eso lo
# decide `looks_like_create_widget` con verbo+nombre y no pasa por aquí.)
_DATA_NOT_CODE_RE = re.compile(
    r"\b(refleja\w*|rellena\w*|llena\w*|puebla\w*|presenta\w*|muestra\w*|mostrar|ense[nñ]a\w*|pinta\w*|vuelca\w*|"
    r"pon(?:er|ga|gas)?\b[^.!?]{0,30}\b(?:datos|resultados|informe|lista|items)|fill|populate|render|display)\b",
    re.I)


@dataclass
class Task:
    """Una escalada entrante del FlashBrain."""
    id: str
    request: str
    kind: str = "generic"
    trusted: bool = True
    context: dict[str, Any] = field(default_factory=dict)


# ── REGISTRO ÚNICO EN RAM = fuente de verdad (§v2·C, §v3·G) ─────────────────────────────────────────────────
_SESSIONS: dict[str, SessionRecord] = {}

# ── V2-049 CONTINUIDAD web: REANUDAR en vez de re-lanzar de cero ─────────────────────────────────────────────
# Cuando un worker WEB muere sin COMPLETAR la gestión, guardamos cómo REANUDARLO por CLAVE de objetivo: la misma
# pestaña (sigue en la página que alcanzó) + el session_id nativo a `--resume` (continúa el razonamiento). La
# siguiente escalada de la MISMA gestión —un nudge del operador, su respuesta a un dato, o el auto-resume del
# propio dispatch— CONTINÚA desde ahí, en vez de abrir la pestaña 2ª/3ª/5ª y re-teclear todo (bug ITV 17-jul: 5
# workers, cero continuidad). Los datos reunidos ya viven en memoria (slots task.*), así que el worker reanudado
# no los vuelve a pedir. TTL 30 min; cap de auto-reanudaciones para no respawnear algo roto en bucle.
_WEB_RESUME: dict[str, dict] = {}
_RESUME_TTL = 1800.0
_RESUME_CAP = 3
# …y como el registro de sesiones, esto vivía SOLO en RAM: un reinicio en mitad de una gestión web se llevaba por
# delante la única forma de CONTINUARLA (el `native_sid` que hace que el worker retome su razonamiento en vez de
# empezar de cero). Espejo en `sys_kv` — estado de proceso, no del operador, igual que el ledger de workers. El TTL
# se aplica igual al cargar, así que una entrada rancia no revive nada.
_RESUME_KEY = "web_resume"


def _resume_persist() -> None:
    """Espeja `_WEB_RESUME` a `sys_kv`. Best-effort y fuera del hot-path (solo al cerrar una sesión web)."""
    try:
        from memory import api as _mem
        if _WEB_RESUME:
            _mem.kv_set(_RESUME_KEY, _WEB_RESUME)
        else:
            _mem.kv_del(_RESUME_KEY)
    except Exception:
        pass


def _resume_restore() -> int:
    """Recarga las entradas de continuidad web que no han caducado. Devuelve cuántas. La llama `start()`."""
    try:
        from memory import api as _mem
        raw = _mem.kv_get(_RESUME_KEY)
        if not isinstance(raw, dict):
            return 0
        now = time.time()
        n = 0
        for k, ent in raw.items():
            if isinstance(ent, dict) and (now - float(ent.get("ts") or 0)) <= _RESUME_TTL:
                _WEB_RESUME[str(k)] = ent
                n += 1
        if n:
            logger.info(f"dispatch: {n} gestión(es) web reanudables recuperadas del proceso anterior")
        return n
    except Exception:
        return 0


def _goal_key(req: str) -> str:
    """Firma estable de una gestión para casar reanudaciones (palabras de contenido, ordenadas)."""
    return " ".join(sorted(_content_words(req)))


def _resume_entry(rec, *, nav_tid: str, resume: dict | None, req: str, key: str,
                  brief: bool, prev_count: int) -> dict:
    """La entrada de reanudación que deja una gestión web INCOMPLETA. Fuera de `_run_session` para poder probarla.

    V2-239 — UN `native_sid` QUE MATÓ A UN WORKER NO SE VUELVE A ARMAR. Aquí había un
    `rec.native_sid or (resume or {}).get("native_sid")` que RECICLABA el id heredado cuando el worker no llegaba
    a tener el suyo. Y no llegar a tenerlo significa exactamente una cosa: el CLI nunca anunció su sesión
    (`rec.native_sid` lo pone el evento `spawned`, que nace del `system/init` de Claude Code — y ese init llega
    igual en un arranque limpio que en un `--resume`, así que una reanudación que PRENDE sí deja su id). O sea que
    el id volvía a la entrada, el siguiente worker se lo llevaba, y volvía a morir en el arranque.

    Medido por el arnés SOBRE el arreglo de V2-237 (05dd79f, worktree limpio, `n_dirty=0`): el `take=True`
    consumía bien y aun así la sesión `0364d544-505` se llevó por delante a los workers 3 y 4, muertos 2/2 a los
    380 y 420 ms. **Consumir la entrada no basta si el camino de la muerte la vuelve a armar con el mismo id.**

    `nav_task` SÍ conserva su respaldo: la pestaña del navegador es otro recurso, sobrevive al worker que la
    abrió y no es lo que estaba matando a nadie.
    """
    return {"nav_task": nav_tid or str((resume or {}).get("nav_task") or ""),
            "native_sid": rec.native_sid,
            "ts": time.time(), "count": int(prev_count) + 1, "goal": req[:200],
            # los criterios ya acordados viajan a la reanudación: recomponerlos a mitad de una búsqueda la
            # convertiría en otra búsqueda distinta sin avisar
            "brief_task": key if brief else str((resume or {}).get("brief_task") or "")}


def _find_resume(req: str, *, take: bool = False) -> dict | None:
    """Entrada de reanudación reciente que casa esta petición ('' → None): solape de palabras ≥0.5 con una gestión
    web INCOMPLETA dentro del TTL. Poda de paso las caducadas.

    `take=True` la CONSUME, y eso es lo que impide que varios workers reanuden la misma sesión del CLI.

    Medido por el arnés el 2026-08-21 en `best-plumber-same-day` (1/5, cero filas extraídas), con la correlación
    perfecta: tres workers distintos arrancaron con «REANUDA sesión nativa c5ad1d9e-ad0…» —**la misma**— y los
    tres murieron a los 371, 401 y 374 ms; los dos que abrieron sesión propia sobrevivieron. **3 de 3 contra 0 de
    3.** Una sesión del CLI no se puede reanudar dos veces a la vez: el segundo `--resume` del mismo id muere en
    el arranque, antes de hacer nada. Y como esto se leía sin consumirse, cada escalada de la misma petición
    —incluidas las que dispara el auto-resume— se llevaba el MISMO `native_sid`.

    Consumirla es seguro porque el ciclo de vida ya la devuelve: al cerrar una gestión web incompleta,
    `_run_session` reescribe la entrada con el `native_sid` ACTUAL. Y si el worker muere antes de llegar ahí, la
    reanudación se pierde y el siguiente encargo empieza de cero — que es estrictamente mejor que morir en 400 ms.
    """
    now = time.time()
    req_w = _content_words(req)
    if not req_w:
        return None
    best, best_key, best_score = None, "", 0.0
    for key, ent in list(_WEB_RESUME.items()):
        if now - ent.get("ts", 0) > _RESUME_TTL:
            _WEB_RESUME.pop(key, None)
            continue
        o = set(key.split())
        union = len(req_w | o)
        score = (len(req_w & o) / union) if union else 0.0
        if score >= 0.5 and score > best_score:
            best, best_key, best_score = ent, key, score
    if best is not None and take:
        _WEB_RESUME.pop(best_key, None)
        _resume_persist()          # …y que el rastro durable no se la sirva otra vez tras un reinicio
    return best


def _schedule_auto_resume(req: str) -> None:
    """V2-049: reanuda SOLA una gestión web incompleta tras una breve pausa (sin empujón del operador). Emite otra
    escalada de la MISMA petición; el listener la casará con la entrada de `_WEB_RESUME` recién grabada y CONTINUARÁ
    (misma pestaña + `--resume`). El cap de `_WEB_RESUME[count]` la corta si algo está roto de verdad."""
    async def _later() -> None:
        try:
            await asyncio.sleep(5.0)
            from nucleo.flash import escalate
            escalate.escalate_to_slowbrain(req, context={"kind": "web", "auto_resume": True})
            logger.info(f"dispatch: AUTO-RESUME de gestión web incompleta: {req[:80]}")
        except Exception as e:  # noqa: BLE001
            logger.warning(f"dispatch: auto-resume falló: {e}")
    try:
        asyncio.create_task(_later())
    except Exception:
        pass

# Loop DUEÑO de las sesiones (uvicorn/server). El FlashBrain corre en OTRO loop (job-thread de LiveKit) → todo
# comando de sesión disparado desde el turno de voz se MARSHALEA aquí (§v3·D), como browser_search.search_sync.
_LOOP: "asyncio.AbstractEventLoop | None" = None


def set_loop(loop) -> None:
    global _LOOP
    _LOOP = loop


def _model_for(kind: str) -> str:
    """Modelo del worker — PEGADO AL ESCALÓN DE PROVEEDOR que se vaya a usar, no al config global.

    `code_agent.model` (p.ej. `glm-5.2`) solo existe en SU proveedor. Al relevar a otro escalón hay que relevar
    también el nombre del modelo: con la cuota de Z.AI agotada, el relevo a la licencia local seguía pidiendo
    `glm-5.2` y el CLI moría al instante con «There's an issue with the selected model (glm-5.2)» — un relevo que
    no releva. Con la licencia (o cualquier escalón sin modelo declarado) se devuelve "" y el CLI usa su default."""
    def _configured() -> str:
        try:
            from config import v2 as _v2
            key = kind if kind in ("web", "code", "memory") else "generic"
            return _v2.code_agent_model(key)
        except Exception:
            return ""

    # La cadena de relevo es de CLAUDE CODE (escalones `ANTHROPIC_BASE_URL`-compatible). Otro backend —Codex— se
    # autentica con SU propia cuenta y esos escalones no significan nada para él: dejar que la cadena decidiera su
    # modelo TIRABA el modelo configurado (2026-08-12, medido). El caso real: con `base_url` apuntando aún a Z.AI de
    # cuando el proveedor era claude_code, y Z.AI en cooldown por cuota, `relayed()` daba True → se devolvía el
    # modelo del escalón de relevo (vacío) → Codex caía a su propio `config.toml` (`gpt-5.6-sol`, que la API no
    # sirve) y el worker moría en 2,8 s con un 400. El `gpt-5.5` que el operador había elegido no llegaba nunca.
    try:
        from nucleo.workers import registry as _reg
        if _reg._provider_for(kind) != "claude_code":
            return _configured()
    except Exception:
        pass
    try:
        from nucleo.workers import providers as _prov
        if not _prov.relayed():
            return _configured()                    # sin relevo, manda el modelo por invocación de siempre
        tier = _prov.pick() or {}
    except Exception:
        return _configured()
    return str(tier.get("model") or "")              # relevado: el modelo del escalón, o el default del proveedor


def _tools_for(kind: str, trusted: bool) -> list[str] | None:
    """Allowlist de tools del worker por tipo. Un turno no confiable no llega aquí (deny_tools en el spec).

    NUNCA un `"Bash"` pelado (auditoría 2026-07-14): el Bash del worker queda acotado a los CLIs puente
    (`_BRIDGE_TOOLS` de `claude_session`, que se añaden solos) — un Bash abierto permitiría a un worker
    inducido por contenido web hostil abrir la SQLite en paralelo (`sqlite3 memory/_data/zaelar.db …`) y
    romper el ESCRITOR ÚNICO. Es el invariante documentado en CLAUDE.md («Bash SOLO a esos CLIs»)."""
    if not trusted:
        return []
    if kind == "code":
        return ["Read", "Write", "Edit", "WebSearch", "WebFetch"]
    if kind == "web":
        return ["Read", "WebSearch", "WebFetch"]
    return ["Read", "WebSearch", "WebFetch"]


# ── DEV WORKER ACOTADO (V2-076) ── moved to dispatch_devworker.py (2026-08-17 modularization pass) — no
# session/pool state touched, re-exported here since callers use both module-qualified access
# (dispatch._dev_worker_params(...)) and direct-name imports (`from nucleo.dispatch import _DEV_TOOLS`).
from nucleo.dispatch_devworker import (  # noqa: F401 — re-export
    _git_tools, _DEV_TOOLS, _dev_worker_params, _dev_prompt,
)


def _classify_kind(request: str) -> str:
    r = request or ""
    if _WEB_RE.search(r):
        return "web"
    # …y también cuando el operador NO nombra el sitio pero la tarea es una GESTIÓN que solo existe dentro de uno
    # (V2-119, 2026-08-18). `_WEB_RE` es una lista de sitios nombrados: sirve para «búscalo en Wallapop» y dejaba
    # fuera «resérvame mesa para 2 en Casa Lucio», que caía en `generic` — un worker sin el catálogo de sitios de
    # confianza y sin la ruta del navegador. El caso de uso `restaurant-tonight-madrid` lo midió: la corrida
    # terminó sin UN SOLO intento de reserva, con el modelo inventándose la política del restaurante.
    # Solo las categorías TRANSACCIONALES (reservar mesa/habitación/vuelo) promocionan: los clasificados de
    # segunda mano NO, porque comparten fraseo con una investigación y esa tiene su propio embudo desde
    # `generic`. El porqué completo, y la taxonomía, en `site_catalog.TRANSACTIONAL_CATEGORIES`.
    try:
        from nucleo.flash import site_catalog as _sc
        if _sc.category_of(r) in _sc.TRANSACTIONAL_CATEGORIES:
            return "web"
    except Exception:
        pass
    # …y cuando el operador SÍ nombra un sitio, pero uno que `_WEB_RE` no conoce (V2-126, 2026-08-18).
    #
    # Había DOS inventarios de sitios conocidos y llevaban tiempo desincronizados: `_WEB_RE` (aquí: wallapop,
    # amazon, linkedin, «abre la web»…) y `router_guards._KNOWN_SITES` (quince, los que el motor sabe abrir para
    # un login). DOCE estaban solo en el segundo — netflix, spotify, gmail, google, ebay, twitter, instagram,
    # facebook, outlook, github, idealista, milanuncios. Medido en el caso `cancel-subscription-before-charge`:
    # «Cancela mi suscripción a Netflix» → `generic`, o sea un worker SIN navegador. Y ese es el daño real, no la
    # falta de una cuenta de Netflix: sin navegador la tarea no puede llegar al muro de login, así que no puede
    # PEDIRLE al operador que entre ni decir «no puedo acceder a tu cuenta» — el sistema se queda sin la única
    # respuesta honesta que tenía, y el turno rellena el hueco narrando.
    #
    # Se exige NOMBRE DE SITIO + VERBO DE TAREA, nunca el verbo suelto: `looks_like_web_task` por sí solo es
    # ancho (`lee|mira|revis|compr`) y su propio docstring dice que existe como DISPARADOR, no como clasificador
    # — enrutar de más ya costó una vez dos tarjetas de navegador que nadie pidió (ver `_MODIFY_CODE_RE` arriba).
    # Música y mensajería quedan FUERA aunque nombren su sitio: esas cuentas se vinculan DENTRO de su widget
    # (OAuth/QR), nunca por el Chromium, y sus dos guards existen justo para sostener ese invariante.
    try:
        from nucleo.flash import router_guards as _rg
        _site = _rg.login_site(r)
        # V2-138: those two guards exist because CONNECTING one of those accounts happens inside its own widget
        # (OAuth/QR), never through the Chromium — a real invariant. But they were excluding the site for ANY
        # request, and ending a PAID commitment with that provider has nothing to do with linking it: «anula la
        # suscripción de Spotify» happens on spotify.com like any other cancellation. Measured: it classified as
        # `generic`, i.e. a worker with NO browser, so it could not even reach the login wall to tell the
        # operator what it needed. The carve-out is narrow on purpose — `ends_a_commitment` is False for «quita
        # la música de Spotify» and for «conecta mi Spotify».
        from nucleo import danger as _danger_cls
        _linking_guard = (_rg.is_music_service(_site, r) or _rg.is_messaging_service(_site, r))
        if _site and _rg.looks_like_web_task(r) and (not _linking_guard or _danger_cls.ends_a_commitment(r)):
            return "web"
    except Exception:
        pass
    # …y una gestión de DINERO o de COMPROMISO ocurre en una WEB, aunque el proveedor no esté en ninguna lista
    # (V2-148, 2026-08-19). Medido sobre las frases del propio caso: «paga la factura de la luz», «paga la
    # factura de Endesa», «paga la factura de la luz en la web de Endesa» — las tres a `generic`, o sea un
    # worker SIN navegador, incluso después de que el operador nombrara el proveedor y dijera dónde la paga.
    #
    # Lo había dejado abierto DOS veces (V2-141, V2-144) anotando que «el destino de un pago es la web del
    # proveedor CONCRETO, no un sitio de confianza común, así que no es la misma solución que una categoría del
    # catálogo». Era cierto y era la conclusión equivocada: no necesita entrada de catálogo NINGUNA, necesita
    # NAVEGADOR — el destino es el proveedor que nombre el operador, y encontrarlo es trabajo del worker.
    #
    # Va DESPUÉS de las ramas anteriores para no pisarlas (un sitio nombrado o una categoría transaccional ya
    # resolvieron), y el daño que repara no es «no paga» —imposible sin cuenta real, y el caso no lo penaliza—
    # sino que sin navegador la tarea no puede llegar al muro de login: el sistema pierde la única respuesta
    # honesta que tenía y el turno rellena el hueco narrando (el argumento de V2-126 para Netflix, otra vez).
    try:
        from nucleo.flash import router_guards as _rg_money
        if _rg_money.money_work_needs_a_browser(r):
            return "web"
    except Exception:
        pass
    # CÓDIGO de widget = CREAR (reusa la detección del router, verbo+nombre) o MODIFICAR-código, o architect.
    # NUNCA por mencionar «widget» a secas (V2-081): abrir/mostrar/gestionar uno existente NO es código.
    try:
        from nucleo.flash import router as _router
        _create = _router.looks_like_create_widget(r)
    except Exception:
        _create = False
    _modify_code = bool(_MODIFY_CODE_RE.search(r)) and not _DATA_NOT_CODE_RE.search(r)
    if _create or _modify_code or _ARCHITECT_RE.search(r):
        return "code"
    return "generic"


def _default_label(kind: str, request: str = "") -> str:
    return {"web": "Buscando en la web…", "code": "Trabajando en un widget…",
            "memory": "Actualizando la memoria…", "research": "Investigando…"}.get(kind, "Pensando…")


def _max_parallel() -> int:
    try:
        v = os.getenv("CODE_AGENT_MAX_PARALLEL")
        if v:
            return max(1, int(v))
    except Exception:
        pass
    try:
        from config import v2 as _v2
        return max(1, int(_v2.get("code_agent").get("max_parallel", 3)))
    except Exception:
        return 3


_sem: "asyncio.Semaphore | None" = None


def _pool():
    global _sem
    if _sem is None:
        _sem = asyncio.Semaphore(_max_parallel())
    return _sem


# ── proyección para ESTADO / prompt / /api/tasks (la sincroniza el LOOP ~1 Hz, §v2·C) ───────────────────────
def active_sessions() -> list[dict]:
    """Snapshot serializable de las sesiones VIVAS (sin handles). Fuente de verdad para ESTADO y /api/tasks.

    ⚠️ «VIVAS» lo decía el docstring y NO lo hacía el código (arreglado 2026-08-18): esto devolvía **todo**
    `_SESSIONS`, incluidas las `done`/`cancelled` que aún no se habían sacado del registro. Era la única de las
    tres proyecciones sin el filtro — `has_active()` y `pending_summaries()` lo llevan justo debajo, y hasta
    `sync_state()` se lo re-aplica a mano sobre `_SESSIONS` en vez de fiarse de esta función, que es la señal más
    clara de que faltaba. Y todos los consumidores la leen como si fuera de vivas: `loop.py` la mete en un set que
    llama `live_ids`, `susurro/apply.py` dedupe contra ella (una tarea TERMINADA suprimiendo una re-ejecución
    legítima) y `/api/tasks` alimenta los chips de la pestaña «Procesos» del operador, que pinta cada fila como
    «en curso» — o sea que una tarea acabada podía verse trabajando. Es la desalineación PROCESOS↔FLUJOS que
    reportó el operador: el tablero de flujos decía «ningún flujo activo» y Procesos seguía diciendo «creando un
    widget… en curso». Lo TERMINADO se lee del ledger (`nucleo/workers/ledger.py`), que es su sitio."""
    now = time.time()
    out = []
    for r in _SESSIONS.values():
        if r.status not in LIVE_SESSION_STATES:
            continue
        out.append({
            "id": r.task_id, "kind": r.kind, "backend": r.backend, "goal": r.goal[:120],
            "phase": r.phase, "status": r.status, "age_s": int(now - r.started), "paused": r.paused,
            # V2-227: dónde mira el operador. El frontend abre la hoja con esto ANTES de que haya un resultado,
            # así que viaja en la proyección viva y no en la entrega.
            "surface": r.surface,
            # SILENCIO real desde el último evento del worker. Es lo que de verdad dice si está encallado — `age_s`
            # solo dice si lleva rato trabajando, que no es lo mismo (ver el detector en nucleo/loop.py).
            "silent_s": int(now - (r.last_event_at or r.started)),
            "waiting_on": r.waiting_on, "ask": r.ask[:160] if r.ask else "",
            # V2-059: observabilidad estructurada — plan + progreso + últimos pasos reales.
            "plan": list(r.plan), "done": r.done, "total": len(r.plan), "pct": _progress_pct(r),
            "note": r.note, "steps": list(r.steps)[-6:],
            "considered": r.considered, "kept": r.kept,     # amplitud de una investigación (-1 = no aplica)
        })
    return out


def has_active() -> bool:
    return any(r.status in LIVE_SESSION_STATES for r in _SESSIONS.values())


# How long a live worker may go WITHOUT emitting anything before we call it stalled. One definition, read by
# both consumers: `nucleo/loop.py`'s supervisor (which speaks up on its own) and `pending_summaries()` below
# (which puts it in front of the brain). Two copies of this number is how the operator gets told one thing by
# the proactive notice and another by the agent he just asked.
STUCK_SECS = float(os.getenv("WORKER_STUCK_SECS", "180"))


# V2-198 — los estados de una SESIÓN de worker, enumerados UNA vez. Había CUATRO filtros escribiendo
# `("queued", "running")` a mano y ninguno para el otro lado: una sesión que termina, se cancela o falla
# desaparecía del registro sin dejar NINGÚN hecho en el estado vivo. Es el mismo hueco que V2-150 cerró para
# las tareas de navegador y V2-196/197 para sus estados… un nivel por encima, y peor: una tarea de navegador
# solo existe con `kind=web`, mientras que **toda** escalada abre una sesión de worker. Los casos que se
# resuelven por búsqueda (`cheapest-monitor`) o por memoria (`remember-and-remind-deadline`) no tienen tarea de
# navegador en absoluto, así que para ellos el arreglo de V2-150 nunca se aplicó.
LIVE_SESSION_STATES = frozenset({"queued", "running"})
# V2-238 — «relevada» es un final propio: la sesión se fue, pero el ENCARGO no. Vivía como `error`, y con eso
# el motor le anunciaba al operador una muerte que no había ocurrido mientras el relevo trabajaba.
ENDED_SESSION_STATES = frozenset({"done", "error", "cancelled", "relevada"})
JUST_ENDED_S = 300.0     # cinco minutos: lo que dura la conversación en la que el operador todavía pregunta


_ENDED_SESSIONS: dict[str, dict] = {}


def _live_goals() -> set[str]:
    """Goals of the sessions that are RUNNING right now, normalised for comparison (V2-222)."""
    out = set()
    for r in list(_SESSIONS.values()):
        try:
            if str(getattr(r, "status", "") or "") in LIVE_SESSION_STATES:
                g = (getattr(r, "goal", "") or "").strip().lower()
                if g:
                    out.add(g)
        except Exception:  # noqa: BLE001
            continue
    return out


def _remember_ended(rec, resuming: bool = False) -> None:
    """Snapshot of a session that just ENDED, kept for `JUST_ENDED_S`.

    `resuming` means the caller is about to relaunch this very errand (V2-049 auto-resume), so it did NOT end —
    and recording it as ended is what put two contradictory statements about the SAME errand in one prompt. See
    V2-222 and the measurement in `recently_ended_sessions`.

    V2-199 — V2-198 read `_SESSIONS` for the ended ones and **`_run_session` pops the record in its `finally`**,
    so in a real dispatch there was never anything left to find. Its unit tests placed records by hand and
    never popped, which is why they passed while the production path did nothing: **a test that never walks the
    real path proves the code compiles, not that it works.** Caught by running one real escalation end to end —
    the worker answered, the brain-note went out, and `recently_ended_sessions()` returned zero.

    A light dict on purpose, not the record: `SessionRecord` holds the worker handles, and keeping it alive
    five minutes past the end would keep those alive too.
    """
    if resuming:
        return
    try:
        _ENDED_SESSIONS[str(rec.task_id)] = {
            "id": str(rec.task_id), "goal": (rec.goal or "").strip(), "status": str(rec.status or "done"),
            "ok": bool(rec.ok), "summary": (rec.result_summary or "").strip(), "at": time.time(),
            # V2-224 — cuántos turnos han LLEVADO ya este final delante. Ver `mark_death_reported`.
            "told": 0}
        for k in [k for k, v in _ENDED_SESSIONS.items()
                  if time.time() - float(v.get("at") or 0) > JUST_ENDED_S]:
            _ENDED_SESSIONS.pop(k, None)
    except Exception:  # noqa: BLE001
        pass
    # V2-222 — y si de verdad MURIÓ, se EMPUJA. Medido por el arnés sobre `hotel-under-15-days` con el contador
    # de las dos vías: lo que se empuja como nota de sistema se dice en el turno siguiente 3 de 3 veces (3 s la
    # pregunta del worker, 7 s el muro); lo que solo se RENDERIZA como línea de estado del prompt, 0 de 13, y con
    # la redacción imperativa de V2-221 delante las trece veces. La línea de estado se queda (es el contexto de
    # los cinco minutos siguientes); la orden viaja por el camino que sí llega.
    try:
        if (str(rec.status or "") != "cancelled" and not bool(rec.ok)
                and not str(getattr(rec, "handoff", "") or "")):     # V2-238: un relevo no ha muerto
            from voice import brain_notes
            _g = (rec.goal or "la tarea de fondo").strip()[:70]
            brain_notes.push(
                f"[SISTEMA] La tarea de fondo «{_g}» ha MUERTO sin resultado y no se va a reintentar sola. El "
                f"operador no lo sabe: está esperando algo que ya no va a llegar. Díselo EN ESTE TURNO con tus "
                f"palabras y ofrécele una salida concreta —reintentarlo, probar otra vía o dejarlo—; no digas "
                f"«sigo con ello» ni «te aviso en cuanto lo tenga».")
    except Exception:  # noqa: BLE001
        pass


def recently_ended_sessions(now: float | None = None, limit: int = 3) -> list[dict]:
    """Sesiones de worker que ACABARON hace poco, y CÓMO acabaron.

    Espejo de `widgets/navegador/tasks.recently_finished()` (V2-150), cuya lección era: un final es un HECHO, y
    una tarea que desaparece del estado al terminar deja al turno con su propia memoria de haberla arrancado.
    Aquí faltaba entero.

    V2-222 — y una gestión que está CORRIENDO no es una gestión que acabó, diga lo que diga el registro. Medido
    por el arnés sobre `hotel-under-15-days` (sandbox `20260820-194231`), leyendo el system prompt de los ocho
    turnos: siete llevaban la MISMA cadena de objetivo dos veces, en el mismo prompt —

        TAREAS DE FONDO EN CURSO (… NO reinicies ni digas que ya está): «Busca hoteles de 4 estrellas…»
            — abriendo una página… [paso 2/5, 40%] (llevas 64s)
        TAREAS DE FONDO — YA ACABADAS: «Busca hoteles de 4 estrellas…» FALLÓ … DÍSELO EN ESTE TURNO

    — porque el primer intento falló, `_remember_ended` lo archivó, y V2-049 relanzó el MISMO encargo con otro id.
    Los dos bloques decían la verdad sobre sesiones distintas; el operador solo tenía UN encargo. El turno
    contestó «sigo esperando resultados», que es la mitad CIERTA: no estaba desobedeciendo el imperativo, estaba
    resolviendo una contradicción, y ninguna redacción de ninguna de las dos mitades podía arreglar eso.

    `_remember_ended(resuming=True)` lo cierra en el origen. Este filtro es el cinturón: la reanudación
    automática no es la única forma de que dos sesiones lleven un mismo objetivo (una escalada repetida también
    lo hace), y el modo de fallo es un prompt que se discute a sí mismo — invisible salvo que se lea entero,
    como se leyó este.
    """
    now = time.time() if now is None else now
    _live = _live_goals()
    rows = [{**v, "ago_s": int(now - float(v.get("at") or now))}
            for v in _ENDED_SESSIONS.values()
            if (now - float(v.get("at") or 0)) <= JUST_ENDED_S
            and (v.get("goal") or "").strip().lower() not in _live]
    rows.sort(key=lambda r: r["ago_s"])
    return rows[:max(1, limit)]


def mark_death_reported(task_ids) -> None:
    """Un turno ya ha llevado delante el final de estas tareas (V2-224).

    El arnés midió la cláusula anti-repetición de V2-221 en dos rondas del MISMO commit y falló en las dos
    direcciones opuestas: en una lo dijo en el turno 2 y lo repitió en el 5, 6, 7, 8 y 9 —el disco rayado de
    V2-189—, y en la otra lo dijo en el turno 2 y luego lo NEGÓ siete turnos («sigo con ello», «dame un
    momento»). Misma cláusula, mismo commit, resultados opuestos: eso no es un umbral mal puesto, es que
    «¿ya se lo dije?» no era un HECHO que el prompt tuviera, sino algo que el modelo deducía de la ventana.

    Nosotros SÍ lo sabemos: contamos los turnos que se lo llevaron delante. Y la lección que dejó el arnés al
    diagnosticarlo gobierna la redacción de la cara nueva — **callar la repetición no es callar el estado**: el
    aviso deja de darse, la prohibición de «sigo con ello» se queda.
    """
    for tid in (task_ids or []):
        row = _ENDED_SESSIONS.get(str(tid))
        if row is not None:
            row["told"] = int(row.get("told") or 0) + 1


def pending_summaries() -> list[dict]:
    """Reemplaza `escalate.pending()` (§v3·G): tareas EN CURSO para el filler del provider + el bloque del prompt."""
    now = time.time()
    return [{"id": r.task_id, "request": r.goal, "secs": int(now - r.started),
             "phase": r.phase, "waiting_on": r.waiting_on,
             # V2-131: SILENCE since the worker's last event. `active_sessions()` has carried it for the loop's
             # stall detector all along; the PROMPT never got it, so the brain answering "¿cómo va?" could only
             # see "it started N seconds ago" and had to guess what counts as too long. It guessed "sigo en
             # marcha" six turns running over a task that had emitted nothing at all.
             "silent_s": int(now - (r.last_event_at or r.started)),
             # V2-059: el FlashBrain puede decir el PASO real + progreso si el operador pregunta "¿cómo va?".
             "pct": _progress_pct(r), "done": r.done, "total": len(r.plan), "note": r.note,
             # Amplitud en curso: deja al cerebro contestar «va por 30 candidatos» y, al acabar, ofrecer seguir.
             "considered": r.considered, "kept": r.kept}
            for r in _SESSIONS.values() if r.status in LIVE_SESSION_STATES]


def get_record(tid) -> "SessionRecord | None":
    return _SESSIONS.get(str(tid))


def record_by_nav_task(nav_tid) -> "SessionRecord | None":
    """El worker que conduce la pestaña de navegador `nav_tid` (para sellar trace/span desde el puente hbweb,
    que corre en el loop del server sin contexto de trace). V2-048."""
    nav_tid = str(nav_tid)
    for r in _SESSIONS.values():
        if getattr(r, "nav_task", "") == nav_tid:
            return r
    return None


PHASES_KEPT = 40          # lo que cabe en una pestaña sin convertirse en un log


# ── la HOJA de resultados como superficie del progreso (V2-227 ámbito C) ──────────────────────────────────────
# El registro vivo es el ÚNICO dueño de «qué está pasando». La hoja no lo guarda: lo LEE en cada `view_data`,
# igual que `counts`. Guardarlo sería reproducir el estado en dos sitios y quedarse con la copia rancia en
# pantalla — que es exactamente el fallo que este ámbito existe para quitar.
def _sheet_sessions() -> list:
    """Las sesiones VIVAS cuya superficie es la hoja (`lista`/`item`). El resto de encargos no pintan aquí."""
    return [r for r in list(_SESSIONS.values())
            if r.status in LIVE_SESSION_STATES and surfaces.opens_sheet(getattr(r, "surface", ""))]


def _phrases(rec) -> list:
    """Las fases de un registro, ya legibles y en orden, sin el andamio `{t, s}`."""
    out = []
    for p in list(getattr(rec, "phases", None) or []):
        s = str((p.get("s") if isinstance(p, dict) else p) or "").strip()
        if s:
            out.append(s)
    return out


#: Sello de ESTE proceso. `escalate._seq` vuelve a 0 en cada arranque, así que un `task_id` no identifica un
#: encargo más allá de la vida del motor; un id de hoja SÍ tiene que hacerlo, porque la hoja se guarda en disco y
#: sobrevive al reinicio (V2-233). Aleatorio y corto: no hace falta que sea legible, hace falta que no choque.
_BOOT = _secrets.token_hex(3)


def sheet_id_for(task_id) -> str:
    """El id de la HOJA de un encargo. UNA definición: la usan el sellado del record y cualquiera que necesite
    reconstruirlo, para que no haya dos formas de nombrar la misma caja."""
    return f"{_BOOT}-{str(task_id or '').strip()}"


def sheet_of(rec) -> str:
    """La hoja de un encargo, sellada UNA vez (mismo criterio que `surfaces.set_once`: cambiarla a mitad mueve lo
    que el operador ya está mirando). Devuelve "" si este encargo no tiene hoja — entonces se escribe la de
    siempre, que es lo correcto para un navegador sin encargo detrás."""
    return str(getattr(rec, "sheet", "") or "")


def sheet_for_nav_task(nav_task: str) -> str:
    """La hoja del ENCARGO al que pertenece esta tarea de navegador ("" si no cuelga de ninguno).

    V2-259 — el navegador encuentra cosas y las entrega a la hoja (V2-257), pero la hoja es del ENCARGO y la tarea
    del navegador tiene su propio id: dos navegadores de la misma búsqueda entregan en la MISMA hoja. `_prepare_web`
    ya guarda `rec.nav_task`, así que la vuelta existe; lo que faltaba era pedirla. Sin encargo detrás —el operador
    conduciendo el navegador a mano— devuelve "", que es la hoja de siempre y es lo correcto.
    """
    tid = str(nav_task or "").strip()
    if not tid:
        return ""
    for r in list(_SESSIONS.values()):
        if str(getattr(r, "nav_task", "") or "") == tid:
            return sheet_of(r)
    return ""


def sheet_progress(sheet: str = "") -> dict:
    """`{alive, phases}` — lo que la pestaña de PROCESO de la hoja tiene que pintar AHORA MISMO.

    `alive` es «hay un encargo en marcha», no «ha dicho algo»: la hoja se abre antes de la primera fase, y ese
    hueco de unos segundos es justo cuando el operador está mirando la pantalla en blanco que pidió quitar.

    `sheet` acota a UN encargo (V2-259: una hoja por encargo, y su clave es el `task_id`). Sin él se mantiene el
    comportamiento viejo —las fases de todos los encargos vivos, entrelazadas EN ORDEN DE TIEMPO—, que era la
    respuesta honesta cuando la hoja era única: quedarse con un encargo escondía en silencio que había otro
    trabajando. Con hojas separadas eso deja de hacer falta, pero la hoja SIN instancia sigue existiendo y sigue
    mereciendo el relato completo.
    """
    rows = _sheet_sessions()
    # V2-259 — con UNA hoja por encargo, el relato de una caja es el de SU encargo. El entrelazado de abajo era
    # la respuesta honesta mientras la hoja era única (quedarse con un encargo escondía que había otro); ahora
    # cada uno tiene dónde contarse, y mezclarlos sería contar dos veces lo mismo en dos sitios.
    want = str(sheet or "").strip()
    if want:
        rows = [r for r in rows if sheet_of(r) == want]
    if not rows:
        return {"alive": False, "phases": []}
    seq = []
    for r in rows:
        for p in list(getattr(r, "phases", None) or []):
            s = str((p.get("s") if isinstance(p, dict) else p) or "").strip()
            if s:
                seq.append((float(p.get("t") or 0.0) if isinstance(p, dict) else 0.0, s))
    seq.sort(key=lambda x: x[0])
    return {"alive": True, "phases": [s for _, s in seq][-PHASES_KEPT:]}


def _sheet_open(rec) -> None:
    """ABRIR la hoja al ENCARGAR, que es el gesto entero del ámbito C: sin esto el operador no ve nada hasta que
    hay respuesta, y el contrato de pantalla se queda cumplido en un test y ausente en el producto.

    UNA HOJA POR ENCARGO (V2-259), y su clave es el `task_id`. Antes era única, así que había que elegir entre
    estrenarla —borrándole lo entregado a otro encargo que siguiera escribiendo— y reutilizarla, que enseñaba los
    resultados de la búsqueda anterior como si fueran los de ésta. Ninguna de las dos era buena, y la primera es
    literalmente el «error de borrar búsquedas» que el operador pidió quitar. Con una clave por encargo la
    disyuntiva desaparece: cada uno estrena la suya y nadie pisa a nadie.

    Todo fail-soft: un fallo aquí no puede tumbar una escalada.
    """
    # El SELLO, una vez y antes de nada: todo lo que escriba en esta hoja tiene que nombrarla igual.
    if not getattr(rec, "sheet", ""):
        try:
            rec.sheet = sheet_id_for(rec.task_id)
        except Exception:  # noqa: BLE001
            pass
    _sid = sheet_of(rec)
    try:
        from widgets.results import data as _sheet
        # V2-259 — SU hoja. `fresh` deja de ser una decisión difícil: una hoja nueva es una CLAVE nueva, así que
        # estrenar ya no puede borrarle a nadie lo suyo (que es literalmente lo que el operador pidió evitar).
        _sheet.begin_task((rec.goal or "").strip(), fresh=True, sheet=_sid)
        _sheet.prune_sheets()          # la hoja persiste a propósito; N instancias no pueden crecer sin techo
    except Exception:  # noqa: BLE001
        pass
    try:
        from voice.observer import emit
        from widgets.results import data as _sheet2
        emit("widget", "show",
             extra={"id": _sheet2.instance_id(_sid), "src": f"worker:{rec.task_id}"})
    except Exception:
        pass


def _sheet_close(rec) -> None:
    """El encargo ACABÓ: se para el loader y la historia se queda con el informe.

    Dos cosas que solo se pueden hacer aquí. (1) Nadie más avisa del final: el emisor de fases solo dispara al
    CAMBIAR una fase, así que sin esta escritura la tarjeta seguiría diciendo «Trabajando…» sobre un worker que
    ya no existe. (2) El registro vivo se tira al terminar, y con él las frases; la hoja SÍ es persistente —un
    informe que sobrevive a un reinicio con la explicación de cómo se llegó a él borrada cuenta la mitad.
    """
    try:
        from widgets.results import data as _sheet
        _sheet.end_task(_phrases(rec), sheet=sheet_of(rec))
    except Exception:  # noqa: BLE001
        pass



def session_phase(tid, phase: str) -> None:
    """Compat V2-036: reporte de fase EXPLÍCITO del worker (hbnote). Actualiza el registro RAM."""
    r = _SESSIONS.get(str(tid))
    if r is not None:
        _p = (phase or "").strip()
        r.phase = _p or r.phase
        r.last_event_at = time.time()
        # V2-227 ámbito C — el historial que lee la pestaña de PROCESO. Se DEDUPLICA contra la última: un worker
        # que hace tres `scroll` seguidos produce tres veces «recorriendo la página», y tres líneas idénticas no
        # informan de nada — parecen progreso sin serlo, que es la mentira que este área lleva todo el día
        # quitando. El anillo es corto a propósito: esto es lo que el operador MIRA, no la auditoría (que ya vive
        # en observabilidad, entera y con su evidencia).
        if _p and (not r.phases or r.phases[-1].get("s") != _p):
            r.phases.append({"t": time.time(), "s": _p})
            del r.phases[:-PHASES_KEPT]
            # …y que la tarjeta abierta se entere. `widgets/store.py` emite esto al GUARDAR, y aquí no hay nada
            # que guardar: el proceso es una vista del registro vivo, no un dato de la hoja. Sin este aviso la
            # pestaña se quedaría quieta hasta el siguiente cambio de datos — un panel de progreso que no avanza.
            if surfaces.opens_sheet(getattr(r, "surface", "")):
                try:
                    from voice.observer import emit as _emit_w
                    from widgets.results import data as _sheet3
                    _emit_w("widget", "data",
                            extra={"id": _sheet3.instance_id(sheet_of(r)), "src": "worker"})
                except Exception:
                    pass
    try:
        from voice.observer import emit
        extra = {"id": str(tid)}
        # V2-044: el handler HTTP del CLI (hbnote) no tiene contexto de trace → sellar el de la sesión.
        if r is not None and r.trace_id:
            extra["trace"] = r.trace_id
            extra["span"] = f"worker:{tid}"
        emit("task", "phase", text=(phase or "").strip(), extra=extra)
    except Exception:
        pass


def session_alive(tid) -> str:
    """A LATIDO: la misma fase, diciendo cuánto lleva. No toca el registro (V2-227 ámbito B2).

    Una tarjeta congelada en «recorriendo la página» durante noventa segundos es indistinguible de un worker
    muerto, y esa ambigüedad es justo lo que el operador pidió quitar: el silencio se lee como avería. Pero el
    remedio no puede ser reescribir `r.phase` con el texto decorado — el latido siguiente decoraría la
    decoración («… lleva 1 min — lleva 2 min»). Así que se EMITE y no se guarda: el registro conserva la fase
    limpia y el carril lleva la versión con el tiempo.

    Devuelve lo emitido (o "" si no había nada que latir), que es lo que hace esto comprobable sin un bus.
    """
    r = _SESSIONS.get(str(tid))
    if r is None or r.status not in LIVE_SESSION_STATES or r.paused:
        return ""
    try:
        from nucleo.workers import progress as _prog
        said = _prog.still_alive(r.phase or _default_label(r.kind), int(time.time() - (r.last_event_at or r.started)))
    except Exception:  # noqa: BLE001
        return ""
    try:
        from voice.observer import emit
        extra = {"id": str(tid)}
        if r.trace_id:
            extra["trace"] = r.trace_id
            extra["span"] = f"worker:{tid}"
        emit("task", "alive", text=said, extra=extra)
    except Exception:
        pass
    return said


def session_plan(tid, steps) -> None:
    """V2-059: el worker DECLARA su lista de tareas al empezar (`hbnote plan "a|b|c"`). Observabilidad estructurada:
    se ve el plan + cuántos pasos lleva → progreso real (no solo una fase coarse)."""
    r = _SESSIONS.get(str(tid))
    if r is None:
        return
    if isinstance(steps, str):
        steps = [s.strip() for s in re.split(r"[|\n]", steps) if s.strip()]
    r.plan = [str(s)[:80] for s in (steps or [])][:12]
    r.done = 0
    r.last_event_at = time.time()
    try:
        from voice.observer import emit
        extra = {"id": str(tid), "plan": r.plan}
        if r.trace_id:
            extra.update(trace=r.trace_id, span=f"worker:{tid}")
        emit("task", "plan", text=f"{len(r.plan)} pasos: " + " · ".join(r.plan)[:160], extra=extra)
    except Exception:
        pass


def session_progress(tid, note: str = "", done: int | None = None, pct: int | None = None) -> None:
    """V2-059: el worker reporta PROGRESO (`hbnote progress "..." --done N` / `--pct P`). Actualiza done/pct/note
    del registro → ESTADO/prompt del FlashBrain + /api/tasks + observabilidad. Fail-soft."""
    r = _SESSIONS.get(str(tid))
    if r is None:
        return
    if note.strip():
        r.note = note.strip()[:200]
    if done is not None:
        try:
            r.done = max(0, int(done))
        except (TypeError, ValueError):
            pass
    if pct is not None:
        try:
            r.pct = max(0, min(100, int(pct)))
        except (TypeError, ValueError):
            pass
    r.last_event_at = time.time()
    try:
        from voice.observer import emit
        extra = {"id": str(tid), "done": r.done, "total": len(r.plan), "pct": _progress_pct(r)}
        if r.trace_id:
            extra.update(trace=r.trace_id, span=f"worker:{tid}")
        emit("task", "progress", text=(r.note or f"{r.done}/{len(r.plan)}")[:160], extra=extra)
    except Exception:
        pass


def session_considered(tid, considered: int | None = None, kept: int | None = None) -> None:
    """AMPLITUD reportada por el worker (`hbnote considered N --kept M`): cuántos candidatos ha evaluado de verdad.

    Existe para que la SELECCIÓN sea auditable. Sin este dato, «te he encontrado las 3 mejores» es indistinguible
    de «te he copiado las 3 primeras que salieron», y ni el operador ni el cerebro pueden juzgar si conviene seguir
    buscando. Con él, el cerebro puede ofrecer la continuación con un número concreto delante."""
    r = _SESSIONS.get(str(tid))
    if r is None:
        return
    for attr, val in (("considered", considered), ("kept", kept)):
        if val is None:
            continue
        try:
            setattr(r, attr, max(0, int(val)))
        except (TypeError, ValueError):
            pass
    r.last_event_at = time.time()
    try:
        from voice.observer import emit
        extra = {"id": str(tid), "considered": r.considered, "kept": r.kept}
        if r.trace_id:
            extra.update(trace=r.trace_id, span=f"worker:{tid}")
        emit("task", "considered", text=f"{r.considered} candidatos evaluados"
                                       + (f" · {r.kept} finalistas" if r.kept >= 0 else ""), extra=extra)
    except Exception:
        pass


def _progress_pct(r: "SessionRecord") -> int:
    """% de progreso: el explícito si lo hay; si no, done/len(plan); -1 si desconocido."""
    if getattr(r, "pct", -1) >= 0:
        return r.pct
    if r.plan:
        return int(100 * min(r.done, len(r.plan)) / len(r.plan))
    return -1


_last_sync: tuple | None = None


def sync_state() -> None:
    """Proyecta el registro RAM al ESTADO de memoria (`activity` + `sessions`). La llama el LOOP (~1 Hz) y los
    puntos de cambio grueso (start/end/cancel) — coalescada, nunca por-evento (§v2·C: no floodear SQLite).
    SKIP-IF-UNCHANGED (2026-07-16): el loop la llama cada tick; si no hay workers vivos, escribía el estado —y
    disparaba `memory.updated`→SSE— CADA SEGUNDO sin cambio, floodeando el visor/log y churneando SQLite. Ahora
    solo escribe cuando la proyección REALMENTE cambia."""
    global _last_sync
    try:
        from memory import api as memory
        sess = active_sessions()
        labels = [(r.phase or _default_label(r.kind)) for r in _SESSIONS.values()
                  if r.status in LIVE_SESSION_STATES]
        # Detección de cambio SIN campos volátiles: `age_s` (y cualquier tiempo transcurrido) SUBE cada segundo →
        # si se incluye, con una sesión viva el snapshot difiere SIEMPRE y se reescribe el estado cada tick
        # (flood de MEMORY·state, el bug 2026-07-16). Comparo solo los campos ESTABLES; el estado escrito sí
        # conserva age_s (lo usa el prompt), pero no dispara memory.updated si nada relevante cambió.
        stable = [{k: v for k, v in s.items() if k not in ("age_s", "silent_s", "secs", "updated", "ts")}
                  for s in sess]
        snap = (tuple(labels), json.dumps(stable, sort_keys=True, default=str))
        if snap == _last_sync:
            return                      # nada relevante cambió → no reescribir ni emitir memory.updated (~1 Hz)
        _last_sync = snap
        memory.set_state({"activity": labels, "sessions": sess})
        # REHIDRATACIÓN (2026-08-12): el mismo cambio deja un rastro DURABLE en `sys_kv` con marca de tiempo. Es lo
        # que permite que el arranque siguiente sepa qué había en vuelo si este proceso muere (un reinicio mató una
        # búsqueda del operador SIN dejar constancia). Va aquí porque este es el único punto que ya sabe que la
        # proyección cambió — no añade ni una escritura extra en reposo. Ver `nucleo/rehydrate.py`.
        try:
            from nucleo import rehydrate as _rehydrate
            _rehydrate.remember(sess)
        except Exception:
            pass
    except Exception:
        pass


# ── resolución de "cuál" para inject / stop (determinista, §v2·B/§v3·M) ──────────────────────────────────────
def _norm(text: str) -> str:
    n = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in n if not unicodedata.combining(c)).lower()


_ALL_RE = re.compile(r"\b(todo|todos|todas|all|everything|cualquier|lo que estas haciendo|lo que haces)\b")
_KIND_HINTS = {
    "code": ("widget", "tarjeta", "panel", "codigo", "code", "card"),
    "web":  ("web", "navegador", "busqueda", "buscando", "wallapop", "amazon", "internet", "browser", "search"),
    "memory": ("memoria", "memory"),
    "research": ("estudio", "informe", "investiga", "research"),
}


def _live_keys() -> list[str]:
    return [k for k, r in _SESSIONS.items() if r.status in LIVE_SESSION_STATES]


def live_traces() -> list[str]:
    """Distinct `trace_id`s of the sessions that are still LIVE. The set form of `has_live_trace`, for the caller
    that needs to know WHICH task is running rather than whether a given trace is one (`nucleo.py::_merge_target`,
    V2-123). Same liveness filter as `_live_keys` — a `done` session is not a task the conversation can still be
    about, and reading unfiltered `_SESSIONS` is the exact bug `active_sessions()` carried until 2026-08-18."""
    out = []
    for k in _live_keys():
        t = str(getattr(_SESSIONS[k], "trace_id", "") or "")
        if t and t not in out:
            out.append(t)
    return out


# Tokens for the dedup matcher. `.split()` was leaving PUNCTUATION stuck to the word, so `zurdo` and `zurdo,` —
# and `guitarra` and `(guitarra` — counted as different words. Found live (2026-08-18): two escalations of the same
# search scored Jaccard 0.556 against `find_duplicate`'s 0.60 threshold and BOTH workers ran, doing the same job
# twice on real money. Punctuation only ever moves that ratio DOWN (it shrinks the intersection and grows the
# union), so the bias was one-directional: miss duplicates, never over-merge. `\w+` rather than `[a-z0-9]+` on
# purpose — `_norm` strips accents but a goal in another alphabet would tokenize to NOTHING under a latin-only
# class, which would silently turn dedup off for that language instead of fixing it. CJK is a separate matter and
# unchanged either way: its tokens are 2-3 characters, so the `len(w) >= 4` filter below already dropped them —
# a pre-existing limit of this matcher, not something introduced here.
_WORD_RE = re.compile(r"\w+", re.UNICODE)


def _content_words(text: str) -> set:
    return {w for w in _WORD_RE.findall(_norm(text)) if len(w) >= 4}


def _target_widget(request: str) -> str:
    """Widget EXISTENTE que la petición referencia ('' si ninguno) — clave de dedup para tareas de widget."""
    try:
        from nucleo.agentes import code as _code
        return _code._referenced_widget(request) or ""
    except Exception:
        return ""


def trace_of(tid: str) -> str:
    """`trace_id` of a live session by its tid ('' if it doesn't exist or has none yet). The single cross-module
    accessor to `_SESSIONS` for this field — keeps the caller (the voice provider) from reaching into the private
    dict directly."""
    r = _SESSIONS.get(str(tid))
    return str(getattr(r, "trace_id", "") or "") if r else ""


def has_live_trace(trace_id: str) -> bool:
    """Is there a LIVE worker session carrying this trace_id? The reverse of `trace_of` — a plain conversational
    turn that finishes cleanly can close its own flow (V2-090 addenda, `nucleo.py::_maybe_close_flow`), but only
    once nothing spawned on this trace is still working; the worker's OWN end (`_run_session`'s finally block)
    already emits the explicit close, and closing the flow again from here would be a stale, contradictory
    second "end" while the session is still running."""
    tid = (trace_id or "").strip()
    if not tid:
        return False
    return any(getattr(r, "trace_id", "") == tid for r in _SESSIONS.values())


def find_duplicate(request: str, kind: str) -> str | None:
    """tid de una sesión VIVA que ya está atendiendo ESTA misma petición ('' → None). El dedup vive AQUÍ, en la
    fuente de verdad (registro RAM), NO en el snapshot de inicio de turno del provider de voz (que falló la
    sesión 2026-07-15: la re-escalada llegó en un turno ambiente por contaminación de ventana y `_similar_pending`
    no la vio). Dos señales: (1) MISMO widget destino (tareas de código sobre el mismo widget) → dedup fuerte;
    (2) solape de palabras de contenido ≥0.6 con el goal de una sesión viva (re-escalada casi idéntica)."""
    req_w = _content_words(request)
    if not req_w:
        return None
    tgt = _target_widget(request) if kind in ("code", "generic") else ""
    for k, r in _SESSIONS.items():
        if r.status not in LIVE_SESSION_STATES:
            continue
        if tgt and _target_widget(r.goal) == tgt:
            return k
        o = _content_words(r.goal)
        union = len(req_w | o)
        if union and len(req_w & o) / union >= 0.6:
            return k
    return None


# ATRIBUCIÓN: qué palabras de una alusión sirven para reconocer una tarea, y cuándo dos son LA MISMA cosa.
#
# V2-140 — criterio 2 del caso `three-tasks-at-once` («cada mensaje por alusión debe ir a la tarea CORRECTA»).
# Medido con tres tareas vivas y las frases reales del caso, antes de tocar nada:
#
#     «¿y el del coche?»                        → ['t1','t2','t3']   (t1 = «informe sobre COCHES eléctricos»)
#     «el del monitor, que sea de 27 pulgadas»  → ['t1','t2','t3']   (t2 = «un MONITOR barato de segunda mano»)
#
# Dos causas mecánicas, ninguna del modelo. La primera es la MISMA que costó dinero en V2-123 (`find_duplicate`
# comparando «guitarra» con «(guitarra»): se troceaba por espacios sobre un `_norm` que solo quita acentos y
# minusculiza, así que **la puntuación se quedaba pegada** — `coche?` y `monitor,`. Es la función hermana, en el
# mismo fichero, y no se revisó entonces. La segunda es que el cruce era por igualdad exacta, así que `coche` no
# reconocía `coches`: la persona alude en singular a algo que pidió en plural, que es lo normal al hablar.
#
# El emparejamiento por prefijo va ACOTADO a propósito — la atribución que se equivoca manda el refinamiento a
# la tarea que no es, y eso es peor que no resolver: mínimo 4 caracteres de raíz y como mucho 3 de diferencia,
# de modo que `coche`/`coches` e `informe`/`informes` casan y `coche`/`cocina` no.
_REF_WORD_RE = re.compile(r"\w+", re.UNICODE)


def _ref_words(text: str) -> set[str]:
    return {w for w in _REF_WORD_RE.findall(text or "") if len(w) > 3}


def _same_thing(a: str, b: str) -> bool:
    if a == b:
        return True
    short, long_ = (a, b) if len(a) <= len(b) else (b, a)
    return len(short) >= 4 and len(long_) - len(short) <= 3 and long_.startswith(short)


def resolve_sessions(query: str) -> list[str]:
    """Referencia del operador → tid(s) vivos. '' / 'todo' → todas; una sola viva → esa; varias → por kind o
    solape de palabras con el goal; nada casa → todas (mejor parar de más que dejar zombies)."""
    keys = _live_keys()
    if not keys:
        return []
    q = _norm(query)
    if not q or _ALL_RE.search(q):
        return list(keys)
    if len(keys) == 1:
        return list(keys)
    want = {k for k, hints in _KIND_HINTS.items() if any(h in q for h in hints)}
    if want:
        by_kind = [k for k in keys if (_SESSIONS[k].kind or "") in want]
        if by_kind:
            return by_kind
    q_words = _ref_words(q)
    scored = []
    for k in keys:
        r = _SESSIONS[k]
        hay_words = _ref_words(_norm(f"{r.label} {r.goal}"))
        scored.append((sum(1 for w in q_words if any(_same_thing(w, h) for h in hay_words)), k))
    scored.sort(reverse=True)
    if scored and scored[0][0] > 0:
        top = scored[0][0]
        return [k for s, k in scored if s == top]
    return list(keys)


# ── inyección (↓) ────────────────────────────────────────────────────────────────────────────────────────
async def inject(which: str, message: str) -> list[str]:
    """Inyecta `message` a la(s) sesión(es) que resuelva `which`. Devuelve los tid inyectados. Reemplaza el
    dedup-descartar de V2-029: un refinamiento se INYECTA, no se tira (§v3·G)."""
    tids = resolve_sessions(which)
    done = []
    for tid in tids:
        r = _SESSIONS.get(tid)
        if not r:
            continue
        try:
            if r.session:
                await r.session.inject(message)
            else:
                # aún EN COLA del pool (sin proceso): la instrucción queda `pending` en el record y se entrega
                # por piggyback en el primer contacto del worker (§v3·H) — nunca se pierde en silencio.
                from nucleo.workers.session import Inject
                r.injects.append(Inject(text=message, ts=time.time()))
            done.append(tid)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"dispatch: inject a {tid} falló: {e}")
    return done


def take_pending_injects(tid) -> list[str]:
    """Piggyback: worker_api la llama al responder a un bridge → entrega las inyecciones pendientes (§v3·H).
    Lee el RECORD (no la sesión): también entrega lo inyectado mientras la tarea esperaba en la cola del pool."""
    r = _SESSIONS.get(str(tid))
    if not r:
        return []
    out = []
    for inj in r.injects:
        if inj.state == "pending":
            inj.state = "delivered"
            out.append(inj.text)
    return out


# ── entradas SÍNCRONAS marshaladas al loop del server (las llama el FlashBrain desde el job-thread, §v3·D/O) ──
def inject_soon(which: str, message: str) -> None:
    """Fire-and-forget: inyecta a la(s) sesión(es) de `which`, en el loop dueño. NUNCA se await-ea en el turno."""
    if _LOOP is None:
        return
    try:
        asyncio.run_coroutine_threadsafe(inject(which, message), _LOOP)
    except Exception:
        pass


def cancel_soon(which: str) -> list[str]:
    """Fire-and-forget: resuelve `which` y MATA en el loop dueño. Devuelve los tid que VA a matar (para la voz)."""
    tids = resolve_sessions(which)   # lectura de dict (barata); la cancelación real va al loop dueño
    if _LOOP is not None and tids:
        def _do():
            for t in tids:
                cancel_session(t)
        try:
            _LOOP.call_soon_threadsafe(_do)
        except Exception:
            pass
    return tids


# ── MATAR (con cortesía) ─────────────────────────────────────────────────────────────────────────────────
def cancel_session(tid, *, reason: str = "operator") -> bool:
    """Mata una sesión: cancela su asyncio.Task (→ el backend mata el grupo de procesos) y purga registro +
    chip + estado de inmediato (reflejo instantáneo). Idempotente."""
    key = str(tid)
    r = _SESSIONS.get(key)
    if not r:
        return False
    if r.session:
        try:
            asyncio.ensure_future(r.session.stop(reason=reason))
        except Exception:
            pass
    if r.task and not r.task.done():
        try:
            r.task.cancel()
        except Exception:
            pass
    _SESSIONS.pop(key, None)
    try:
        from nucleo import worker_api
        worker_api.purge_task(key)   # §v3·L: el loop no debe relatar la pregunta de un muerto
    except Exception:
        pass
    try:
        from voice.observer import emit
        _tx = {"trace": r.trace_id, "span": f"worker:{key}"} if r.trace_id else {}   # V2-044
        emit("task", "cancel", text=(r.label or r.goal or "")[:120], role="system",
             extra={"id": key, "goal": (r.goal or "")[:120], **_tx})
        emit("task", "end", extra={"id": key, "ok": False, **_tx})
    except Exception:
        pass
    sync_state()
    return True


def cancel_all(*, reason: str = "reset") -> int:
    n = 0
    for k in list(_SESSIONS.keys()):
        if cancel_session(k, reason=reason):
            n += 1
    return n


# ── V2-065 (2026-07-23): PAUSAR ≠ matar — el botón ⏻ del operador. A diferencia de `cancel_all` (mata de verdad,
# irreversible, usado por Reset), esto congela los workers VIVOS en el sitio (SIGSTOP al backend, ver
# `workers/base.py::pause`) y los deja en el registro tal cual — `resume_all()` los continúa exactamente donde
# estaban. Un backend que no soporta pausar de verdad (Codex stub, generator_session) simplemente no hace nada
# (`pause()` devuelve False) — nunca rompe. Best-effort, síncrono (SIGSTOP/SIGCONT no son I/O).
def pause_all() -> int:
    n = 0
    for r in _SESSIONS.values():
        if r.status not in LIVE_SESSION_STATES or not r.session:
            continue
        try:
            if r.session.pause():
                n += 1
        except Exception as e:  # noqa: BLE001
            logger.warning(f"pause_all: worker {r.task_id} falló al pausar: {e}")
    if n:
        sync_state()
    return n


def resume_all() -> int:
    n = 0
    for r in _SESSIONS.values():
        if not r.paused or not r.session:
            continue
        try:
            if r.session.resume():
                n += 1
        except Exception as e:  # noqa: BLE001
            logger.warning(f"resume_all: worker {r.task_id} falló al reanudar: {e}")
    if n:
        sync_state()
    return n


async def stop_all_async(*, grace: float = 2.0) -> int:
    """Apagado ORDENADO del lifespan (§v3·L): para los backends esperando su cierre (killpg) ANTES de tumbar el
    loop. Devuelve cuántas sesiones había."""
    recs = list(_SESSIONS.values())
    for r in recs:
        if r.session:
            try:
                await r.session.stop(grace=grace, reason="shutdown")
            except Exception:
                pass
        if r.task and not r.task.done():
            r.task.cancel()
    n = len(recs)
    _SESSIONS.clear()
    return n


# ── arranque de una sesión desde una escalada ────────────────────────────────────────────────────────────


async def _seed_research_criteria(brief: dict) -> None:
    """Vuelca el brief recién compuesto a la pestaña CRITERIOS de la hoja de resultados.

    Se hace AQUÍ, en el pre-vuelo, y no dentro del worker: si dependiera de que el ejecutor se acuerde de
    escribirlo, faltaría justo en las búsquedas que peor van. Efecto de paso —y buscado—: el `goal` es la firma
    del encargo, así que arrancar una investigación DISTINTA vacía la hoja de la anterior. El operador ya se comió
    una vez quedarse mirando los resultados de la búsqueda de antes creyendo que eran los suyos. Una ronda 2
    conserva el objetivo, así que «sigue buscando» no borra nada.

    Best-effort duro: esto es la pantalla, no el trabajo. Si el widget falla, la investigación sigue igual."""
    try:
        payload = research.to_criteria(brief)
        if not payload:
            return
        from widgets.server_api import brain_action
        await brain_action("results", "criteria", payload)
    except Exception as exc:                                # noqa: BLE001 — nunca frenar una tarea por la vista
        logger.debug(f"dispatch: no pude sembrar los criterios en la hoja de resultados ({exc})")


async def _compose_brief(request: str, context: str, trusted: bool, resume: dict | None = None) -> dict | None:
    """PRE-VUELO de una investigación: convierte la petición cruda en un BRIEF dirigido (nucleo/research.py).

    Por qué está AQUÍ y no en el turno de voz: dirigir bien una búsqueda —separar criterios duros de blandos,
    añadir lo que un experto sabe que hará falta, fijar cuán ancho hay que buscar y con qué baremo juzgar— es un
    trabajo de razonamiento, y el FlashBrain de voz tiene que contestar en milisegundos. Aquí ya estamos fuera de
    ese reloj: la escalada es asíncrona, el operador ya sabe que esto tarda, así que este es el único punto del
    sistema donde se puede pensar antes de empezar a trabajar.

    Si es una REANUDACIÓN, el brief de la ronda anterior se reutiliza tal cual: los criterios ya estaban acordados
    y recomponerlos podría cambiarlos a mitad de una búsqueda que el operador cree que sigue el mismo guion."""
    if not trusted:
        return None                       # perfil sin tools: no hay investigación que dirigir
    prev_tid = str((resume or {}).get("brief_task") or "")
    if prev_tid:
        prev = research.load(prev_tid)
        if prev:
            return prev
    # ¿Ya investigamos esto y el operador vuelve a la carga? Entonces es la RONDA SIGUIENTE de la misma búsqueda:
    # hereda los criterios acordados y sube la amplitud, con su frase de ahora como motivo del rechazo. Sin esto,
    # «esos no me valen, busca más» recomponía el brief desde cero y repetía la misma búsqueda con la misma
    # amplitud — el operador habría visto llegar los mismos resultados y concluido, con razón, que no le escuchamos.
    gk = _goal_key(request)
    prev = research.previous_round(gk)
    if prev:
        nxt = research.expand(prev, note=request)
        logger.info(f"dispatch: RONDA {nxt.get('round')} de una investigación ya conocida "
                    f"(≥{(nxt.get('breadth') or {}).get('min_candidates')} candidatos): {request[:60]}")
        return nxt
    return await research.compose(request, context)


# ── contrato WEB restaurado (demo 2026-07-14: la búsqueda corrió INVISIBLE) ────────────────────────────────
# En el refactor V2-038 (P2) el flujo `kind=web` se unificó bajo el WorkerSession genérico y se PERDIÓ el paso
# de `web_cc` que creaba la tarea+TARJETA del navegador y daba al worker el contrato de cierre → el worker de la
# demo navegó 12+ min sin superficie visible ni entrega. Se restaura AQUÍ, dentro del sustrato nuevo:
# una tarea = una pestaña = una tarjeta (continuidad V2-032 incluida) + prompt web con criterio de CIERRE.
_FORCE_NEW_RE = re.compile(
    r"\b(otro|otra|segundo|segunda|nuevo|nueva|aparte|adem[aá]s|en paralelo|a la vez)\b[^.]*"
    r"\b(navegador|pesta[ñn]a|ventana|b[uú]squeda|tarea)\b", re.I)
_COEXIST_RE = re.compile(r"\bsin (parar|detener|cerrar|tocar)\b", re.I)


async def _prepare_web(rec: "SessionRecord", req: str, reuse_tid: str = "") -> str:
    """kind=web: crea (o RE-USA, continuidad V2-032/V2-049) la tarea del navegador y ABRE su tarjeta ANTES de
    arrancar el worker. Devuelve el id de navtask ('' si el subsistema no está). El id viaja al worker por
    ZAELAR_NAV_TASK → sus capturas/acciones casan con ESTA tarjeta (y su pestaña, que persiste en el owner)."""
    try:
        from widgets.navegador import tasks as navtasks
    except Exception:
        return ""
    try:
        # V2-049: reanudación EXPLÍCITA → misma pestaña que alcanzó el worker anterior (sigue en su página).
        cont = None
        if reuse_tid and navtasks.get(reuse_tid):
            cont = (reuse_tid,)
        force_new = bool(_FORCE_NEW_RE.search(req)) or bool(_COEXIST_RE.search(req))
        if cont is None and not force_new:
            try:
                cont = navtasks.find_continuation(req)
            except Exception:
                cont = None
        # ONE TAB, ONE DRIVER (measured live 2026-08-21, `search-secondhand-monitor`). Three workers on the same
        # errand were each handed nav task `t6`, and they drove it at once: 46, 27 and 7 actions interleaved on one
        # page. The damage is not cosmetic — element refs are HANDED OUT PER LOOK (V2-248), so `click [29]` from the
        # second worker landed on whatever the first had just turned the page into. On a checkout page that is not a
        # dirty result, it is the wrong ACTION.
        #
        # The cause is two similarity judgements about the SAME pair of texts disagreeing: `find_duplicate` (Jaccard
        # >= 0.60 on content words) said "different errands" and spawned three workers, while `find_continuation`
        # (>= 2 shared stemmed subjects OR Jaccard >= 0.40) said "same browsing session" and gave them one tab. Both
        # predicates are defensible on their own; what is never defensible is the combination, so the contradiction
        # is resolved HERE, where it becomes physical. Continuation stays available for the case it was written for
        # — the operator refining a task whose worker is gone — and stops being a way to share a live tab.
        if cont:
            _held = record_by_nav_task(str(cont[0]))
            if _held is not None and _held is not rec and _held.status in LIVE_SESSION_STATES:
                logger.warning(f"dispatch: la pestaña {cont[0]} ya la conduce {_held.task_id} → pestaña nueva")
                cont = None
        if cont:
            tid = str(cont[0])
            try:
                navtasks.set_goal(tid, req)
            except Exception:
                pass
        else:
            tid = str(navtasks.create(req, trace=str(getattr(rec, "trace_id", "") or "")))
        try:
            from voice.observer import emit
            emit("widget", "show", extra={"id": navtasks.inst_id(tid), "src": f"worker:{tid}"})
        except Exception:
            pass
        try:
            navtasks.set_status(tid, "working")
            navtasks.set_phase(tid, "conduciendo el navegador", True)
        except Exception:
            pass
        try:  # esencia del objetivo en la cabecera de la tarjeta (sintetizador existente; best-effort)
            from nucleo.agentes.web import _synthesize_goal
            s = await _synthesize_goal(req)
            if s:
                navtasks.set_goal_summary(tid, s)
        except Exception:
            pass
        rec.nav_task = tid
        return tid
    except Exception as e:  # noqa: BLE001
        logger.warning(f"dispatch: _prepare_web falló (la tarea corre sin tarjeta): {e}")
        return ""


async def _finalize_web(rec: "SessionRecord", keep_open: bool = False) -> None:
    """Cierra la TARJETA del navegador con lo encontrado: extrae los anuncios que quedaron en pantalla (la
    pestaña del owner sigue viva aunque el worker haya muerto/sido matado) y fija el estado final. Best-effort.
    V2-049: si `keep_open` (gestión web incompleta que se va a REANUDAR), NO la marca «failed» — la deja en PAUSA
    (working) para que la pestaña y su página se conserven y el worker reanudado continúe donde estaba."""
    tid = getattr(rec, "nav_task", "")
    if not tid:
        return
    items: list = []
    try:
        from widgets.navegador import tasks as navtasks
        try:
            from widgets.navegador import owner
            tb = owner._task_browsers.get(str(tid))
            if tb is not None:
                items = await tb.extract_listings()
                if items:
                    navtasks.set_results(tid, {"conclusion": (rec.result_summary or "").strip()[:300],
                                               "items": items[:5]})
        except Exception:
            pass
        if rec.status == "cancelled":
            navtasks.cancel(tid)
        elif keep_open:
            navtasks.set_phase(tid, "en pausa — reanudando la gestión", True)     # pestaña VIVA para el resume
        else:
            navtasks.finish(tid, "done" if rec.ok else "failed",
                            ("✅ " if rec.ok else "") + ((rec.result_summary or "").strip()[:200]
                                                        or "sin resultado"))
        # V2-257 — tercer y último camino por el que el navegador encuentra algo; los tres pasan ya por la misma
        # puerta (`widgets/results/intake`). Va DESPUÉS del cierre por dos razones: mantiene pegados el
        # `set_results` y el final que exige el invariante de V2-192 (una tarea VIVA no puede tener resultados),
        # y deja fuera el caso `cancelled` — el operador dijo que parásemos, así que no le llenamos la hoja.
        if items and rec.status != "cancelled":
            try:
                from widgets.results import intake as _intake
                _intake.push(items, sheet=sheet_of(rec),
                             source_url=str((navtasks.get(tid) or {}).get("url") or ""))
            except Exception:  # noqa: BLE001
                pass
    except Exception:
        pass


async def _compose_context(request: str, kind: str) -> str:
    """Contexto mínimo de memoria para el worker (best-effort, off-voz). Fail-open a vacío, pero AVISANDO:
    el fail-open silencioso escondió durante todo V2-038 un typo (`compose_task_context`, función inexistente)
    que dejaba a TODOS los workers sin el bloque «CONTEXTO DE MEMORIA» (auditoría 2026-07-14)."""
    try:
        from nucleo import memory_agent
        return await memory_agent.compose_context(request, budget=2000)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"dispatch: compose_context falló ({e}); el worker {kind} sale SIN contexto de memoria")
        return ""


def _own_base_url() -> str:
    """The URL of THIS engine, for the bridges a worker uses to talk back to it.

    Reads the same `HOST`/`PORT` the server binds with, so a sandbox on a free port and the operator's engine on
    43917 each hand their workers their OWN address instead of a shared constant. `127.0.0.1` rather than the
    bind host when that is `0.0.0.0`: a worker is a local subprocess, and the wildcard is not a dialable address.
    """
    port = (os.getenv("PORT") or "43917").strip() or "43917"
    host = (os.getenv("HOST") or "127.0.0.1").strip() or "127.0.0.1"
    if host in ("0.0.0.0", "::", "*", ""):
        host = "127.0.0.1"
    return f"http://{host}:{port}"


async def _run_session(task: "Task") -> None:
    """Crea y conduce UNA sesión bajo el pool. Nunca lanza (corre como task suelta)."""
    from nucleo import danger
    from nucleo.flash import escalate

    key = str(task.id)
    req = (task.request or "").strip()

    # TRAZABILIDAD (V2-044): adopta el trace de la frase que originó la escalada (viajó en task.context porque el
    # bus no copia contexto). span=worker:<id> → TODOS los emits del ciclo (fases, chips, entrega, notify) quedan
    # encadenados a esa frase en el árbol de Trazas.
    try:
        from voice import trace as _trace
        _rec0 = _SESSIONS.get(key)
        _tid0 = (task.context or {}).get("trace") or (getattr(_rec0, "trace_id", "") if _rec0 else "")
        if _tid0:
            _trace.adopt(str(_tid0), span=f"worker:{key}")
            if _rec0 is not None and not _rec0.trace_id:
                _rec0.trace_id = str(_tid0)
    except Exception:
        pass
    kind = (task.kind or "generic").strip() or "generic"
    if kind == "generic":
        kind = _classify_kind(req)
    trusted = bool(task.trusted)

    # CONFIRM-GATE de irreversibles (V2-007) — antes de arrancar nada.
    if trusted and danger.is_dangerous(req) and not bool(task.context.get("confirmed")):
        logger.info(f"dispatch: tarea {key} PARA por confirm-gate: {req[:80]}")
        rec = _SESSIONS.get(key)
        if rec:
            rec.status = "done"
            rec.result_summary = danger.confirm_question(req)
            await _deliver_confirm(rec)
            _SESSIONS.pop(key, None)
            # La pregunta se RECUERDA (V2-126). Hasta aquí el gate era un callejón sin salida: hablaba la
            # pregunta por el raíl proactivo, tiraba el registro, y nadie ponía nunca `context["confirmed"]`
            # — un `sí` del operador no tenía a qué volver. Peor: la tarea desaparecía de `pending_summaries`,
            # así que el turno siguiente NO veía nada pendiente y volvía a narrar trabajo que no existía.
            # Medido en `cancel-subscription-before-charge` y en `pay-known-bill` (tres tareas, las tres
            # paradas por el gate, ninguna contada al operador).
            remember_confirm(key, req, task)
            sync_state()
        return

    rec = _SESSIONS.get(key)
    if rec is None:
        return
    rec.kind = kind
    rec.label = _default_label(kind, req)
    sync_state()

    async with _pool():
        if rec.status == "cancelled":         # cancelada mientras esperaba el pool
            _SESSIONS.pop(key, None)
            return
        ctx = await _compose_context(req, kind)
        env = {"ZAELAR_TASK_REQUEST": req,       # req crudo → registry (elige generador) + backend
               # V2-152: a worker must talk to the engine that SPAWNED it, and until now nothing told it which
               # one that was. All six bridges (`nav_cli`, `mem_cli`, `worker_bridge`, `agent_report`,
               # `widget_cli`, plus `hbsay`) resolve `ZAELAR_BASE` with a hardcoded `localhost:43917` default,
               # and NOBODY set that variable — so an engine on any other port spawned workers that drove a
               # DIFFERENT engine's browser, memory and task cards. Measured on `book-hotel-night-known__es`:
               # the sandbox's own task record stayed empty (`url=""`, `shot_rev=0`) and not one of the owner's
               # browser events reached its timeline, while the worker was really navigating Booking.com — on
               # the operator's live engine. The brain then told the operator, truthfully about ITS record and
               # falsely about the world, that nothing had been opened, and he stopped a task that was working.
               "ZAELAR_BASE": _own_base_url()}
        nav_tid = ""
        resume = task.context.get("resume") or {}     # V2-049: {nav_task, native_sid, count} si REANUDA una gestión
        resume_sid = str(resume.get("native_sid") or "") if kind == "web" and trusted else ""
        if kind == "web" and trusted:
            nav_tid = await _prepare_web(rec, req, reuse_tid=str(resume.get("nav_task") or ""))
            if nav_tid:
                env["ZAELAR_NAV_TASK"] = nav_tid       # las capturas/acciones de hbweb casan con ESTA tarjeta
        _dev = _dev_worker_params(task.context)     # V2-076: escalada de cluster con permiso de código
        _dev_settings_path = ""
        if _dev:
            import tempfile as _tf
            _wd = _tf.mkdtemp(prefix="zaelar-dev-")   # cwd AISLADO para Read/Write/Edit (nunca el proyecto)
            env.update(_dev["env"])
            # GUARD DE CONFINAMIENTO REAL (auditoría 2026-07-26, cierra el hallazgo "solo convención de prompt"):
            # hook PreToolUse que deniega Read/Write/Edit/Glob/Grep fuera de `_wd` — fuera del propio workdir (no
            # dentro: así el worker no puede tocar el fichero de settings que lo confina).
            env["ZAELAR_DEV_WORKER_ROOT"] = _wd
            _dev_settings_path = os.path.join(_tf.gettempdir(), f"zaelar-dev-settings-{key}.json")
            try:
                dev_worker_guard.write_settings_file(_dev_settings_path)
            except Exception:
                logger.warning(f"dispatch: no pude escribir el settings del guard de confinamiento para {key} "
                               "(dev-worker seguirá sin ese jail; git_cli sigue acotado al repo autorizado)")
                _dev_settings_path = ""
            spec = WorkerSpec(kind="dev", model=_model_for("code"), tools=_dev["tools"],
                              deny_tools=False, trusted=False, task_id=key,
                              token=rec_token(rec), parent_task_id=rec.parent_task_id, depth=rec.depth,
                              env=env, cwd=_wd,
                              extra_args=(["--settings", _dev_settings_path] if _dev_settings_path else []))
        else:
            # OWN CWD (incident 2026-08-18): until today this spec carried no `cwd`, so the backend fell back to
            # the ENGINE ROOT and the headless agent loaded `engine/CLAUDE.md` (76k tokens) plus the parent
            # CLAUDE.md on EVERY request. Measured on the worker that died: 122,833 input tokens BEFORE doing any
            # work, ~62k of headroom, and the provider rejected the call 14 steps later. Measured again head-to-head
            # afterwards: 167,242 tokens in the repo root vs 25,352 in a scratch dir (-84.8%). See
            # `workers/workdir.py` for the three faults one directory per task fixes (context, `informe.json`
            # collision, private CLAUDE.md). `read_dirs` declara la dependencia de lectura de la VISIÓN del
            # navegador (la captura llega por ruta absoluta fuera del cwd, V2-049) — medido que el CLI ya la permite
            # sin decírselo, así que es defensa en profundidad, no un requisito.
            _wd = None
            if not workdir.needs_repo(kind):
                _wd = workdir.for_task(key)
                env.update(workdir.env_for_task(env))
            spec = WorkerSpec(kind=kind, model=_model_for(kind), tools=_tools_for(kind, trusted),
                              deny_tools=(not trusted), trusted=trusted, task_id=key,
                              token=rec_token(rec), parent_task_id=rec.parent_task_id, depth=rec.depth,
                              env=env, cwd=_wd, resume_sid=resume_sid,
                              read_dirs=(workdir.extra_dirs() if _wd else []))
        backend = get_backend(spec)
        session = WorkerSession(backend, spec, rec)
        rec.session = session
        # PRE-VUELO: ¿esto es una investigación/selección? Entonces se dirige con un brief (amplitud + baremo +
        # forma del entregable) en vez de dejar que el worker se autoimponga el criterio mínimo. Un dev-worker de
        # código no pasa por aquí: su dirección es el repo, no un espacio de candidatos.
        brief = None
        if not _dev:
            try:
                brief = await _compose_brief(req, ctx, trusted, resume)
            except research.ComposerUnavailable:
                # El compositor no pudo contestar. El fail-open (arrancar sin dirigir) es correcto, pero NO puede
                # arrastrar consigo la mitad del presupuesto: que esto sea una investigación no depende de que el
                # compositor esté vivo. Se promociona el kind IGUAL — cuesta DIRECCIÓN, no TIEMPO. Medido en el
                # banco del 2026-08-13: el compositor tardó >30 s, la tarea se quedó en `generic` (600 s) y el
                # worker murió a los 704 s con el navegador a medias, el mismo «agotó su tiempo» que la promoción
                # de abajo existe para cerrar.
                brief = None
                if kind == "generic":
                    rec.kind = "research"
                    rec.label = _default_label("research", req)
                    logger.info(f"dispatch: tarea {key} SIN brief (compositor caído) pero con presupuesto de "
                                f"investigación · kind={rec.kind}")
                    sync_state()
            if brief:
                research.save(key, brief)
                research.remember_round(_goal_key(req), brief)   # para que una 2ª petición continúe, no reempiece
                await _seed_research_criteria(brief)
                rec.phase = "preparando la investigación"
                # EL BRIEF ES LA PRUEBA de que esto es una INVESTIGACIÓN, y con ella se cobra el presupuesto que le
                # corresponde. `loop._kind_budget_default` ya reservaba 1200s para `research`… pero NADIE asignaba
                # nunca ese kind: `_classify_kind` solo devuelve web/code/generic, así que toda investigación que no
                # nombrara Wallapop/Amazon caía en `generic` = 600s. Y ese medio presupuesto CONTRADICE el propio
                # brief, que exige reunir ≥40 candidatos y ENTRAR en la ficha de cada finalista: 10 minutos no dan
                # para eso, así que el worker moría conminado a «entrega ya» con la hoja a medias — es lo que le pasó
                # al operador el 2026-08-12 dos veces («agotó su tiempo»). Solo se promociona `generic`: `web`
                # (1200s, y con su reanudación por `native_sid`) y `code` conservan su ruta intacta. Y el `spec` del
                # worker YA está construido con el kind viejo a propósito — aquí solo cambia lo que MIDE el
                # supervisor y lo que LEE el operador en la tarjeta («Investigando…», no «Pensando…»).
                if kind == "generic":
                    rec.kind = "research"
                    rec.label = _default_label("research", req)
                logger.info(f"dispatch: tarea {key} dirigida por BRIEF (ronda {brief.get('round')}, "
                            f"≥{(brief.get('breadth') or {}).get('min_candidates')} candidatos) · "
                            f"kind={rec.kind}")
                sync_state()
        if _dev:
            prompt = _dev_prompt(req, _dev["repo"])
        elif kind == "web" and trusted:
            prompt = _web_prompt(req, ctx, brief)
        else:
            prompt = _build_prompt(req, ctx, trusted, brief)
        if resume and (kind == "web" and trusted):
            prompt = ("REANUDAS una gestión que YA empezaste (no arranques de cero): la pestaña sigue donde la "
                      "dejaste y los datos que ya reuniste están en memoria (consúltalos con mem_cli recall). Haz "
                      "`look` PRIMERO para ver dónde te quedaste y CONTINÚA desde ahí hasta terminar.\n\n") + prompt
        try:
            await session.run(prompt)
        except asyncio.CancelledError:
            pass
        except Exception as e:  # noqa: BLE001
            logger.warning(f"dispatch: sesión {key} falló: {e}")
        finally:
            # V2-049 CONTINUIDAD: ¿gestión web que quedó SIN completar? → reanudable (mantén la pestaña viva).
            _resumable = (kind == "web" and trusted and rec.status != "cancelled" and not rec.ok)
            _prev_count = int((resume or {}).get("count", 0))
            if nav_tid:
                try:
                    await _finalize_web(rec, keep_open=_resumable)
                except Exception:
                    pass
            if _dev:
                # limpieza del workdir temporal + el settings del guard (auditoría 2026-07-26, T-07: antes no se
                # borraban nunca — fuga de disco acumulativa con escaladas de código de cluster repetidas).
                try:
                    import shutil as _sh
                    _sh.rmtree(_wd, ignore_errors=True)
                except Exception:
                    pass
                if _dev_settings_path:
                    try:
                        os.remove(_dev_settings_path)
                    except Exception:
                        pass
            if kind == "web" and trusted:
                gk = _goal_key(req)
                if rec.ok or rec.status == "cancelled":
                    _WEB_RESUME.pop(gk, None)                       # completada o parada → nada que reanudar
                    _resume_persist()                               # …y que no quede rastro durable de algo cerrado
                elif nav_tid or rec.native_sid:
                    _WEB_RESUME[gk] = _resume_entry(rec, nav_tid=nav_tid, resume=resume, req=req, key=key,
                                                    brief=bool(brief), prev_count=_prev_count)
                _resume_persist()       # sobrevive al reinicio → la reanudación CONTINÚA en vez de empezar de cero
            try:
                if key.isdigit():
                    escalate.finish(int(key), rec.result_summary if rec.ok else "")
            except Exception:
                pass
            _waiting_user = (rec.waiting_on == "user") or bool(rec.ask)
            # V2-222 — ¿va a CONTINUAR sola? Se calcula aquí, ANTES de anotar el final, porque una sesión que se
            # reanuda sola no ha terminado y anotarla como terminada es lo que partía el prompt en dos.
            # V2-238 — DOS ESCALADAS PARA UNA MUERTE. `_finish` ya relanza el encargo cuando releva de proveedor
            # o compacta el contexto (`escalate_to_slowbrain`), y deja `ok=False` a propósito para que no haya dos
            # entregas. Pero `_resumable` lee exactamente ese `ok=False` y disparaba ADEMÁS el auto-resume de
            # V2-049: dos workers sobre el mismo encargo, y —hasta V2-237— los dos reanudando la MISMA sesión del
            # CLI, que es como morían a los 400 ms. El testigo ya está pasado: aquí no se pasa otra vez.
            _handoff = str(getattr(rec, "handoff", "") or "")
            _will_resume = bool(_resumable and not _waiting_user
                                and (_prev_count + 1) < _RESUME_CAP and not _handoff)
            # …pero el ENCARGO continúa en las dos formas, así que lo que mira «¿esto se ha acabado?» mira esto.
            _continues = bool(_will_resume or _handoff)
            # V2-079: rastro DURABLE de la ejecución que se va (el registro vivo se purga aquí y desaparecía). El
            # ledger conserva el histórico para la pestaña «Procesos» del ChatWall. Best-effort, fuera del hot-path.
            try:
                from nucleo.workers import ledger as _ledger
                _ledger.record_finish(id=str(key), kind=str(kind or ""), goal=str(req or "")[:160],
                                      status=str(rec.status or "done"), started_at=getattr(rec, "started", None),
                                      trace_id=str(getattr(rec, "trace_id", "") or ""), ok=bool(rec.ok))
            except Exception:
                pass
            # EXPLICIT flow-close signal (observability, V2-090): without this a flow only ever looks "closed" by
            # the ABSENCE of new events — an inference from silence, never a fact. The ledger above already records
            # this worker session's own end; this event is for the FLOW (`corr_id`) that spawned it, so the
            # master's board can mark the column closed for real instead of guessing from recency.
            if getattr(rec, "trace_id", ""):
                try:
                    from voice import trace as _trace2
                    from voice.observer import emit as _emit_flow_end
                    # `trace.scope()` FORCES this event's corr_id to `rec.trace_id`, rather than trusting whatever
                    # trace happens to be ambient in this task's context at finally-time — `emit()` always reads
                    # `trace.current()` for the indexed `corr_id` column, never an `extra` field.
                    with _trace2.scope(rec.trace_id):
                        _emit_flow_end("flow", "end", role="system",
                                        extra={"ok": bool(rec.ok), "status": str(rec.status or "")})
                except Exception:
                    pass
            _remember_ended(rec, resuming=_continues)     # V2-199: el final es un HECHO — antes de tirar el registro
            _SESSIONS.pop(key, None)
            # V2-227 ámbito C — DESPUÉS del pop, nunca antes: la hoja lee el registro vivo, así que mientras esta
            # sesión siguiera dentro `alive` seguiría diciendo que sí. Y no al reanudar: el encargo continúa.
            if not _continues and surfaces.opens_sheet(getattr(rec, "surface", "")):
                _sheet_close(rec)
            try:
                from nucleo import worker_api
                worker_api.purge_task(key)   # §v3·L: sin asks pendientes de una sesión terminada
            except Exception:
                pass
            try:
                from nucleo.workers import findings
                findings.forget(key)         # V2-236: la memoria de hallazgos se va con su sesión
            except Exception:
                pass
            sync_state()
            # V2-049 AUTO-RESUME: gestión web incompleta, SIN pregunta pendiente, bajo el cap → CONTINÚA sola (el
            # FlashBrain no cesa la tarea ni espera un empujón del operador). Con pregunta pendiente NO: espera la
            # respuesta (que, al llegar como turno, reanuda por la misma vía). Con `ask` la purga de arriba ya la
            # quitó, por eso leímos _waiting_user ANTES.
            if _will_resume:
                _schedule_auto_resume(req)


def rec_token(rec: "SessionRecord") -> str:
    """Token de auth por-tarea para los bridges (§v2·D). Se guarda en el propio registro (atributo dinámico)."""
    tok = getattr(rec, "_token", "")
    if not tok:
        tok = secrets.token_urlsafe(18)
        setattr(rec, "_token", tok)
    return tok


# ── CONFIRMACIÓN PENDIENTE de una tarea irreversible (V2-126) ─────────────────────────────────────────────
# Same contract as `widgets/confirm.py` (the sibling gate for irreversible WIDGET actions): remember the ask,
# expire it rather than let it hang forever, and expose a line the FlashBrain can read in its live state. It is
# a separate registry on purpose — that one is keyed by widget id and executes through `apply_action`, this one
# re-dispatches a worker task; fusing them would couple two unrelated execution paths for a shared TTL.
_PENDING_CONFIRM: dict[str, dict] = {}
_CONFIRM_TTL = 300.0     # 5 min. Longer than the widget gate's 90 s: this question ("shall I really pay?")
                         # arrives mid-conversation and the operator may reasonably think about it.


# V2-190 — an expired confirmation is a FACT, and losing it is how a gated task turns into narrated work.
# Measured on `renew-gym-membership__es` (2026-08-20 01:01): the gate parked the renewal, the operator was
# asked, five minutes went by inside a normal conversation, `_sweep_confirm` dropped the entry, `confirm_line()`
# went empty — and from that turn on the state said NOTHING about it. The model fell back on the only thing it
# still had, its own earlier «empiezo ya con la renovación», and answered «sigo sin novedades de la web de
# Basic-Fit» about a task whose record read `status=done url= shot_rev=0`: it never opened a single page.
#
# The TTL itself is NOT the bug and is not raised: a «shall I really pay?» answered «sí» forty minutes later is
# exactly what it protects against. What was wrong is that expiring the GATE also erased the MEMORY of it. So
# the gate still expires — `resolve_confirm` reads `_PENDING_CONFIRM` and an expired ask can no longer be armed
# by a late yes — and the fact moves here, where the turn can still say it. Same remedy as
# `widgets/navegador/tasks.recently_finished()` (V2-150): an ending is a fact.
_EXPIRED_CONFIRM: dict[str, dict] = {}
_EXPIRED_MEMORY_S = 900.0     # 15 min: long enough to outlive the conversation that asked


def _sweep_confirm(now: float | None = None) -> None:
    now = time.time() if now is None else now
    for k in [k for k, v in _PENDING_CONFIRM.items() if now - v["ts"] > _CONFIRM_TTL]:
        _EXPIRED_CONFIRM[k] = {**_PENDING_CONFIRM.pop(k), "expired_at": now}
    for k in [k for k, v in _EXPIRED_CONFIRM.items() if now - float(v.get("expired_at") or 0) > _EXPIRED_MEMORY_S]:
        _EXPIRED_CONFIRM.pop(k, None)


def remember_confirm(task_id: str, request: str, task: "Task") -> None:
    """Keep the question the gate just asked, so a later «sí» has somewhere to go."""
    from nucleo import danger as _danger
    _sweep_confirm()
    _EXPIRED_CONFIRM.pop(str(task_id), None)      # se vuelve a preguntar: ya no es un caducado sin respuesta
    _PENDING_CONFIRM[str(task_id)] = {
        "request": request, "kind": (task.kind or "generic"), "trusted": bool(task.trusted),
        "context": dict(task.context or {}), "question": _danger.confirm_question(request),
        "ts": time.time()}


def pending_confirm() -> dict | None:
    """The confirmation still waiting for a yes/no, or None. Most recent wins — a second irreversible ask
    supersedes the first, exactly like the widget gate."""
    _sweep_confirm()
    if not _PENDING_CONFIRM:
        return None
    tid = max(_PENDING_CONFIRM, key=lambda k: _PENDING_CONFIRM[k]["ts"])
    return {"task_id": tid, **_PENDING_CONFIRM[tid]}


def confirm_line() -> str:
    """Line for the FlashBrain's live state. Without it the brain has NO idea a task is parked waiting on the
    operator — which is precisely how a gated task turned into narrated progress."""
    p = pending_confirm()
    if not p:
        # V2-190: nothing waiting — but maybe something EXPIRED waiting, and that is not the same as nothing.
        _sweep_confirm()
        if not _EXPIRED_CONFIRM:
            return ""
        _e = max(_EXPIRED_CONFIRM.values(), key=lambda v: float(v.get("expired_at") or 0))
        return (f"UNA CONFIRMACIÓN QUE LE PEDISTE CADUCÓ SIN RESPUESTA: «{str(_e.get('request') or '')[:120]}». "
                f"Esa tarea NUNCA EMPEZÓ y no va a empezar sola — no digas que sigue en marcha ni que esperas "
                f"novedades suyas. Si sale a colación, dilo y ofrece retomarla desde cero.")
    from nucleo import danger as _danger_line
    # Si mueve DINERO se dice aquí también (V2-129): el operador ya oyó «no hago ningún cargo sin decirte el
    # importe», y el turno siguiente no puede contradecir esa promesa.
    money = (" MUEVE DINERO: le prometiste decirle el importe exacto ANTES de cobrar nada, así que ni lo pagues"
             " ni digas que está pagado hasta haber mirado la cifra y habértela confirmado él."
             if _danger_line.moves_money(p["request"]) else "")
    return (f"CONFIRMACIÓN PENDIENTE de una acción IRREVERSIBLE: «{p['request'][:120]}».{money} Le preguntaste al "
            f"operador y AÚN NO ha contestado, así que la tarea está PARADA y no ha empezado nada — no digas "
            f"que está en marcha. Si dice que SÍ, arranca; si dice que NO, olvídalo y confírmaselo.")


def resolve_confirm(ok: bool) -> dict | None:
    """Answer the pending confirmation. `True` re-dispatches the SAME request with `confirmed` set (the gate
    lets it through this time); `False` drops it. Returns what was resolved, or None if nothing was pending."""
    p = pending_confirm()
    if not p:
        return None
    _PENDING_CONFIRM.pop(p["task_id"], None)
    if not ok:
        return {**p, "ok": False}
    # Se re-lanza por la MISMA puerta que cualquier escalada (`escalate.requested` → `run_listener`), no por un
    # atajo: así conserva el trace, el dedup y el registro de tareas. Lo único distinto es `confirmed`, que es
    # lo que el gate mira para dejarla pasar esta vez.
    ctx = {**p["context"], "confirmed": True, "kind": p["kind"]}
    try:
        from nucleo.flash import escalate as _esc
        _esc.escalate_to_slowbrain(p["request"], context=ctx)
    except Exception:
        logger.warning("resolve_confirm: no se pudo re-lanzar la tarea confirmada")
    return {**p, "ok": True}


async def _deliver_confirm(rec: "SessionRecord") -> None:
    try:
        from voice import proactive
        await proactive.notify("zaelar", rec.result_summary, speak=True)
    except Exception:
        pass


# ── compat: llamada directa (tester) ───────────────────────────────────────────────────────────────────────
async def dispatch(task: "Task") -> str:
    """Compat: arranca una sesión y espera su resultado (para tests/voice/e2e/agent/llamadas directas)."""
    if not (task.request or "").strip():        # una petición vacía es un no-op, no una sesión
        return ""
    key = str(task.id)
    _SESSIONS[key] = SessionRecord(task_id=key, goal=(task.request or "").strip()[:200],
                                   kind=(task.kind or "generic"))
    await _run_session(task)
    return "(tarea despachada)"


# ── consumo de escalados del bus (FlashBrain → workers) ────────────────────────────────────────────────────
def _merge_dedup_flow(ctx: dict, dup: str) -> bool:
    """An escalation was just absorbed as a refinement of the live session `dup` — which is PROOF, not a guess,
    that the two are the same task (`find_duplicate` demands 60% content-word overlap with its goal). Fuse this
    turn's flow into the live task's so the master paints ONE chronological thread (V2-123). Returns True when the
    caller must NOT emit its own `flow/end`.

    Why the close is skipped once merged: the reader folds an absorbed flow into its titular and a close counts for
    the COMBINED row (`cloud/backoffice/src/flowAttribution.js::_absorb` sums `ended_events` — "closed if EITHER
    closed", correct when both halves are turns of one sentence). Closing here would therefore mark a task that is
    still working as finished and drop it off the board — losing sight of live work, which is worse than the stray
    open flow this close exists to prevent. The live session's own end (`_run_session`'s finally block) owns it,
    the same rule as everywhere else: the flow belongs to whoever is still working.

    This is the trigger half that V2-105 left unbuilt on purpose. It merges on EVIDENCE ALREADY HELD rather than on
    a similarity guess: the dedup matcher had to be convinced first, and it is the strict one of the two resolvers
    in this module (`resolve_sessions` is deliberately loose — "better to stop too much than leave zombies" — a
    bias that suits cancelling and would be wrong for attribution)."""
    src = str((ctx or {}).get("trace") or "")
    if not src:
        return False
    dst = trace_of(dup)
    if not dst:
        return False
    if dst == src:
        return True             # already the same flow: nothing to fuse, and its worker still owns the close
    try:
        from voice import trace as _trace_merge
        _trace_merge.merge(dst, src)
    except Exception:
        return False
    return True


def _close_escalated_flow(ctx: dict, *, ok: bool, status: str) -> None:
    """Explicit flow-close for an `escalate.requested` outcome that never spawns its own `SessionRecord` —
    rejected while the agent is halted, or absorbed as a refinement into an already-live session (V2-113). Both
    paths leave `has_live_trace(trace_id)` False forever for THIS trace, so without an explicit close here the
    voice provider's `just_escalated` guard (`nucleo.py::_flow_should_close`) would block the flow from EVER
    closing — mirrors the close `_run_session`'s finally block emits for a real spawn."""
    trace_id = str((ctx or {}).get("trace") or "")
    if not trace_id:
        return
    try:
        from voice import trace as _trace3
        from voice.observer import emit as _emit_close2
        with _trace3.scope(trace_id):
            _emit_close2("flow", "end", role="system", extra={"ok": ok, "status": status})
    except Exception:
        pass


async def run_listener(stop: "asyncio.Event | None" = None) -> None:
    import bus

    sub = bus.subscribe("escalate.requested")
    logger.info("dispatch: listener de escalados (Brain Workers) arrancado")
    try:
        while stop is None or not stop.is_set():
            try:
                ev = await asyncio.wait_for(sub.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            except Exception:
                break
            payload = ev if isinstance(ev, dict) else {}
            tid = payload.get("id")
            request = (payload.get("request") or "").strip()
            ctx = payload.get("context") or {}
            if not request:
                continue
            key = str(tid or "?")
            kind = str(ctx.get("kind", "generic"))
            # V2-092: con el agente PARADO (⏻) NO se abre trabajo nuevo. Los workers que ya estaban se congelan y
            # continúan al arrancar (pause_all/resume_all), pero arrancar uno DESDE CERO sobre un agente parado es
            # lo contrario de parar. Se rechaza VISIBLE (evento `task/blocked`), nunca en silencio: una escalada que
            # desaparece sin rastro es la clase de fallo que cuesta una sesión de diagnóstico.
            _halted = False
            try:
                from nucleo import runstate
                _halted = runstate.stopped()
            except Exception:
                _halted = False
            if _halted:
                try:
                    from voice.observer import emit
                    emit("task", "blocked", role="system", text=request[:120],
                         extra={"id": key, "reason": "el agente está parado (⏻): no se abre trabajo nuevo"})
                except Exception:
                    pass
                _close_escalated_flow(ctx, ok=False, status="rejected_halted")
                logger.info(f"dispatch: escalada RECHAZADA (agente parado): {request[:80]}")
                continue
            # DEDUP en la FUENTE DE VERDAD (§sesión 2026-07-15): si ya hay una sesión viva atendiendo esta misma
            # petición, NO abrimos un 2º worker (el bug de los dos «creando un widget…»). Se INYECTA como
            # refinamiento (el generador de widgets, build atómico, lo ignora con gracia; un worker vivo lo aprovecha).
            dup = find_duplicate(request, kind if kind != "generic" else _classify_kind(request))
            if dup:
                try:
                    from voice.observer import emit
                    emit("task", "dedup", role="system", text=request[:120],
                         extra={"id": dup, "dropped_id": key, "reason": "escalada duplicada de una tarea viva"})
                except Exception:
                    pass
                try:
                    await inject(dup, request)      # refinamiento a la sesión viva (no relanza)
                except Exception as e:  # noqa: BLE001
                    logger.warning(f"dispatch: inject de dedup a {dup} falló: {e}")
                # Same task, proven by the dedup match → ONE flow (V2-123). Only when the fuse didn't happen does
                # this trace still need its own explicit close, or `just_escalated` would keep it open forever.
                if not _merge_dedup_flow(ctx, dup):
                    _close_escalated_flow(ctx, ok=True, status="dedup_injected")
                continue
            # V2-049 CONTINUIDAD: sin sesión viva que casar, ¿hay una gestión web INCOMPLETA reciente que ESTA
            # petición reanuda? (nudge «sigue con la ITV», o el operador aportando el dato que faltaba). Reanuda esa
            # misma pestaña + razonamiento en vez de arrancar de cero.
            _k = kind if kind != "generic" else _classify_kind(request)
            if _k == "web":
                # take=True: la reanudación se CONSUME al entregarla. Sin eso, dos escaladas de la misma
                # petición se llevan el mismo id de sesión del CLI y la segunda muere en el arranque.
                _res = _find_resume(request, take=True)
                if _res and (_res.get("nav_task") or _res.get("native_sid")):
                    ctx = dict(ctx)
                    ctx["resume"] = _res
                    try:
                        from voice.observer import emit
                        emit("task", "resume", role="system", text=request[:120],
                             extra={"id": key, "nav_task": _res.get("nav_task", ""),
                                    "reason": "reanuda gestión web incompleta (no re-lanza de cero)"})
                    except Exception:
                        pass
            task = Task(id=key, request=request, kind=kind,
                        trusted=bool(ctx.get("trusted", True)), context=ctx)
            rec = SessionRecord(task_id=key, goal=request[:200], kind=task.kind,
                                parent_task_id=str(ctx.get("parent_task_id", "")),
                                depth=int(ctx.get("depth", 0) or 0),
                                trace_id=str(ctx.get("trace", "") or ""))   # V2-044: encadena a la frase origen
            # V2-227 — la SUPERFICIE se sella aquí, que es el único punto por el que pasan TODAS las puertas de
            # entrada al dispatcher (el cerebro con su `surface`, el auto-resume, el confirm-gate, el cluster, el
            # Susurro). Lo que declaró el cerebro manda; si no declaró nada —o dijo algo que no es del
            # vocabulario— se deriva del kind. Sellar tarde significaría abrir la hoja cuando ya hay respuesta,
            # que es exactamente lo que este cambio existe para no hacer.
            surfaces.set_once(rec, ctx.get("surface"))
            # …y si esa superficie es la hoja, se ABRE YA, vacía y con la pestaña de proceso. Aquí, y no en la
            # entrega, es donde el operador deja de mirar una pantalla en blanco.
            if surfaces.opens_sheet(getattr(rec, "surface", "")):
                _sheet_open(rec)
            _SESSIONS[key] = rec
            rec.task = asyncio.create_task(_run_session(task), name=f"worker-session-{key}")
            sync_state()
    finally:
        sub.close()
        logger.info("dispatch: listener de escalados detenido")


# ── ciclo de vida (lifespan, BRAIN=nucleo) ────────────────────────────────────────────────────────────────
_listener_task: "asyncio.Task | None" = None
_listener_stop: "asyncio.Event | None" = None


def start() -> None:
    global _listener_task, _listener_stop, _LOOP
    if _listener_task is not None and not _listener_task.done():
        return
    try:
        _LOOP = asyncio.get_running_loop()   # loop dueño de las sesiones (server) → marshaling cross-loop (§v3·D)
    except RuntimeError:
        pass
    _resume_restore()               # continuidad web del proceso anterior, ANTES de aceptar escaladas
    _listener_stop = asyncio.Event()
    _listener_task = asyncio.create_task(run_listener(_listener_stop), name="nucleo:workers-dispatch")


async def stop() -> None:
    global _listener_task, _listener_stop
    try:
        await stop_all_async()          # apagado ordenado (§v3·L): mata workers ANTES de parar el listener
    except Exception:
        pass
    if _listener_stop is not None:
        _listener_stop.set()
    if _listener_task is not None:
        _listener_task.cancel()
        try:
            await _listener_task
        except (asyncio.CancelledError, Exception):
            pass
        _listener_task = None
    _listener_stop = None


def running() -> bool:
    return _listener_task is not None and not _listener_task.done()
