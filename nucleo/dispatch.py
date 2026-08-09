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
import secrets
import time
import unicodedata
from dataclasses import dataclass, field
from typing import Any

from loguru import logger

from nucleo import dev_worker_guard, research
from nucleo.workers import WorkerSpec, get_backend
from nucleo.workers.session import SessionRecord, WorkerSession

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
_ARCHITECT_RE = re.compile(r"\barchitect\b|\bproyecto\b", re.I)
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


def _goal_key(req: str) -> str:
    """Firma estable de una gestión para casar reanudaciones (palabras de contenido, ordenadas)."""
    return " ".join(sorted(_content_words(req)))


def _find_resume(req: str) -> dict | None:
    """Entrada de reanudación reciente que casa esta petición ('' → None): solape de palabras ≥0.5 con una gestión
    web INCOMPLETA dentro del TTL. Poda de paso las caducadas."""
    now = time.time()
    req_w = _content_words(req)
    if not req_w:
        return None
    best, best_score = None, 0.0
    for key, ent in list(_WEB_RESUME.items()):
        if now - ent.get("ts", 0) > _RESUME_TTL:
            _WEB_RESUME.pop(key, None)
            continue
        o = set(key.split())
        union = len(req_w | o)
        score = (len(req_w & o) / union) if union else 0.0
        if score >= 0.5 and score > best_score:
            best, best_score = ent, score
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


# ── DEV WORKER ACOTADO (V2-076) — escalada ORIGINADA en un cluster con permiso de código ─────────────────────────
# Una escalada de una charla agente-agente llega con trusted=False (nunca hereda la confianza del operador) PERO,
# si el operador concedió `code` al cluster, debe poder ESCRIBIR código y SUBIRLO al repo autorizado — sin tocar
# nada más. No usamos el `_tools_for(trusted)` binario: montamos un worker con alcance JUSTO:
#   · Read/Write/Edit acotados a un DIRECTORIO TEMPORAL (cwd), nunca el proyecto (aislamiento de escritura).
#   · git SOLO por el PUENTE `nucleo.git_cli` (nunca Bash git pelado) y SOLO al repo autorizado (ZAELAR_ALLOWED_REPO).
#   · SIN puentes de memoria (ZAELAR_NO_BRIDGE_TOOLS) → un dev de cluster no lee/escribe la memoria del operador.
#   · PYTHONPATH al engine para que el puente sea importable desde el cwd temporal.
_ENGINE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
def _git_tools() -> list[str]:
    """Mismo criterio que los puentes de `claude_session._BRIDGE_TOOLS`: TODAS las formas de escribir el intérprete,
    para que el dev worker no se quede pidiendo una aprobación que en headless nadie va a dar."""
    try:
        from nucleo.workers.claude_session import _INTERPRETERS
        return [f"Bash({py} -m nucleo.git_cli:*)" for py in _INTERPRETERS]
    except Exception:
        return ["Bash(python -m nucleo.git_cli:*)", "Bash(.venv/bin/python -m nucleo.git_cli:*)"]


_DEV_TOOLS = ["Read", "Write", "Edit", *_git_tools()]


def _dev_worker_params(context: dict) -> dict | None:
    """Si el contexto de escalada pide un dev worker (V2-076: `dev` + `repo` autorizado), devuelve sus parámetros
    ACOTADOS; si no, None (worker normal). Puro/testeable."""
    ctx = context or {}
    if not (ctx.get("dev") and ctx.get("repo")):
        return None
    repo = str(ctx.get("repo"))
    return {
        "tools": list(_DEV_TOOLS),
        "repo": repo,
        "env": {"ZAELAR_NO_BRIDGE_TOOLS": "1", "ZAELAR_ALLOWED_REPO": repo, "PYTHONPATH": _ENGINE_ROOT},
    }


def _dev_prompt(req: str, repo: str) -> str:
    return (
        "Eres un worker de DESARROLLO en una colaboración de código AUTORIZADA por el operador. Trabajas en el "
        "DIRECTORIO ACTUAL (una carpeta temporal AISLADA) — NO escribas ni leas fuera de ella.\n"
        f"Repo autorizado: {repo} (es el ÚNICO que puedes tocar).\n"
        "Flujo:\n"
        "1. Clónalo:  python -m nucleo.git_cli clone repo   (queda en ./repo)\n"
        "2. Escribe/edita el código dentro de ./repo con Read/Write/Edit.\n"
        "3. Commit + push:  python -m nucleo.git_cli commit repo -m \"<mensaje>\"  y luego  python -m nucleo.git_cli push repo\n"
        "NO tienes acceso a la memoria del operador, a otros repos, ni a Bash abierto (solo el puente git_cli). "
        "Si algo requiere más permisos, dilo y termina — no lo fuerces.\n\n"
        f"TAREA: {req}")


def _classify_kind(request: str) -> str:
    r = request or ""
    if _WEB_RE.search(r):
        return "web"
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
    """Snapshot serializable de las sesiones vivas (sin handles). Fuente de verdad para ESTADO y /api/tasks."""
    now = time.time()
    out = []
    for r in _SESSIONS.values():
        out.append({
            "id": r.task_id, "kind": r.kind, "backend": r.backend, "goal": r.goal[:120],
            "phase": r.phase, "status": r.status, "age_s": int(now - r.started), "paused": r.paused,
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
    return any(r.status in ("queued", "running") for r in _SESSIONS.values())


def pending_summaries() -> list[dict]:
    """Reemplaza `escalate.pending()` (§v3·G): tareas EN CURSO para el filler del provider + el bloque del prompt."""
    now = time.time()
    return [{"id": r.task_id, "request": r.goal, "secs": int(now - r.started),
             "phase": r.phase, "waiting_on": r.waiting_on,
             # V2-059: el FlashBrain puede decir el PASO real + progreso si el operador pregunta "¿cómo va?".
             "pct": _progress_pct(r), "done": r.done, "total": len(r.plan), "note": r.note,
             # Amplitud en curso: deja al cerebro contestar «va por 30 candidatos» y, al acabar, ofrecer seguir.
             "considered": r.considered, "kept": r.kept}
            for r in _SESSIONS.values() if r.status in ("queued", "running")]


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


def session_phase(tid, phase: str) -> None:
    """Compat V2-036: reporte de fase EXPLÍCITO del worker (hbnote). Actualiza el registro RAM."""
    r = _SESSIONS.get(str(tid))
    if r is not None:
        r.phase = (phase or "").strip() or r.phase
        r.last_event_at = time.time()
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
                  if r.status in ("queued", "running")]
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
    return [k for k, r in _SESSIONS.items() if r.status in ("queued", "running")]


def _content_words(text: str) -> set:
    return {w for w in _norm(text).split() if len(w) >= 4}


def _target_widget(request: str) -> str:
    """Widget EXISTENTE que la petición referencia ('' si ninguno) — clave de dedup para tareas de widget."""
    try:
        from nucleo.agentes import code as _code
        return _code._referenced_widget(request) or ""
    except Exception:
        return ""


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
        if r.status not in ("queued", "running"):
            continue
        if tgt and _target_widget(r.goal) == tgt:
            return k
        o = _content_words(r.goal)
        union = len(req_w | o)
        if union and len(req_w & o) / union >= 0.6:
            return k
    return None


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
    q_words = {w for w in q.split() if len(w) > 3}
    scored = []
    for k in keys:
        r = _SESSIONS[k]
        hay = _norm(f"{r.label} {r.goal}")
        hay_words = {w for w in hay.split() if len(w) > 3}
        scored.append((len(q_words & hay_words), k))
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
        if r.status not in ("queued", "running") or not r.session:
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
def _recent_conversation_block(limit: int = 8) -> str:
    """CONVERSACIÓN RECIENTE verbatim para el prompt del worker (sesión 22:40 2026-07-16): una escalada llegaba
    con la frase CRUDA («¿Por qué crees que puede ser?») y CERO contexto conversacional → el worker investigó la
    voz TTS cuando el operador llevaba tres turnos quejándose de que la MÚSICA no sonaba. El modelo rápido ya
    tenía la instrucción de reformular «con el contexto necesario», pero es no-razonador y no es fiable en eso →
    el contexto de los últimos turnos se adjunta DETERMINISTA aquí (lectura µs de `memory.recent_window`, el
    buffer conversacional persistente), no se delega. Best-effort, nunca lanza."""
    try:
        from memory import api as memory
        win = memory.recent_window(limit=limit) or []
        lines = []
        for m in win:
            who = "OPERADOR" if (m.get("role") == "user") else "zaelar"
            txt = (m.get("content") or "").strip().replace("\n", " ")[:220]
            if txt:
                lines.append(f"{who}: {txt}")
        return "\n".join(lines[-limit:])
    except Exception:
        return ""


def _today_block() -> str:
    """La fecha/hora REAL de hoy, para anclar toda restricción temporal (V2-057): «el último», «el de hoy»,
    «el tiempo actual» solo tienen sentido contra la fecha real — sin esto el worker no puede certificar que un
    resultado sea el vigente. El FlashBrain ya la lleva (live_state); el worker NO la recibía."""
    import time as _t
    return (f"FECHA/HORA REAL DE HOY: {_t.strftime('%A %d %b %Y')} ({_t.strftime('%Y-%m-%d')}), "
            f"{_t.strftime('%H:%M')} hora local. Ancla a esto cualquier restricción temporal de la petición "
            f"(«el último» = el más reciente respecto a HOY; «de hoy»/«ahora» = esta fecha y de aquí en adelante; "
            f"«el de tal día» = esa fecha exacta). NUNCA des un dato caducado como si fuera vigente.")


# V2-057/V2-061 — método OBLIGATORIO: entender → planificar → ejecutar → REFLEJAR en los espejos → VERIFICAR → ITERAR.
# El worker no ejecuta a ciegas por deducción del texto; muchas órdenes son acciones ENCADENADAS (realidad ↔ widgets
# ↔ memoria) y hay que actualizar TODOS los planos y certificar que quedan coherentes antes de entregar.
_METHOD_BLOCK = (
    "MÉTODO (síguelo SIEMPRE, en este orden; no ejecutes a ciegas):\n"
    "1) ENTIENDE exactamente qué se pide, incluidas las restricciones IMPLÍCITAS: «el último/más reciente» = el "
    "más nuevo por fecha (no el primero por relevancia); «hoy/ahora/actual» = anclado a la fecha real de hoy y de "
    "aquí en adelante; «el de tal día» = esa fecha exacta; una cifra/precio/resultado = el VIGENTE. Distingue el "
    "PLANO: si es una acción del MUNDO REAL (cancelar/reservar una cita, dar de baja una suscripción, hacer/anular "
    "un pedido, pagar), la acción PRINCIPAL es en la realidad (la web/servicio donde se hizo) — la agenda y los "
    "widgets son solo ESPEJOS locales que reflejan esa realidad, NUNCA el objetivo en sí.\n"
    "2) PLANIFICA los pasos y LOCALIZA en memoria lo que necesites (dónde se reservó/contrató, la cita concreta, la "
    "cuenta) con python -m nucleo.mem_cli recall \"<qué buscas>\".\n"
    "3) EJECUTA la acción en la realidad con tus herramientas (navegador, etc.).\n"
    "4) REFLEJA el cambio en los ESPEJOS locales, encadenado: si afecta a un widget (borrar la cita ya cancelada de "
    "la agenda, actualizar una lista), hazlo con python -m nucleo.widget_cli (LEE el widget primero con `read` y usa "
    "los ids REALES que te devuelve, nunca inventes ids); si afecta a un hecho que zaelar recuerda, actualízalo con "
    "python -m nucleo.mem_cli remember. Un ESPEJO desactualizado (la cita sigue en la agenda tras cancelarla) es un "
    "fallo, no un detalle.\n"
    "4b) ENSÉÑALO EN PANTALLA si la tarea produce un CONJUNTO DE RESULTADOS para el operador — una lista de "
    "cualquier cosa (sitios, alojamientos, productos, anuncios, artículos, proyectos, ficheros, opciones, "
    "candidatos…). El operador mira una pantalla: un listado que solo se DICE por voz es una entrega a medias y se "
    "pierde en cuanto acaba la frase. Hazlo con la superficie genérica de presentación: "
    "`python -m nucleo.widget_cli read results` (te devuelve su contrato y la forma EXACTA del payload) → "
    "entrégalo en DOS pasos, que es la ÚNICA forma probada que pasa los guardas:\n"
    "     (i)  escribe el JSON con tu tool Write a un fichero de RUTA RELATIVA en tu directorio de trabajo — "
    "`informe.json` a secas. NUNCA `/tmp/…` ni una ruta absoluta ni `TMP/`: fuera de tu directorio la escritura "
    "pide una aprobación que nadie te va a dar.\n"
    "     (ii) `python -m nucleo.widget_cli data results present @informe.json`\n"
    "   …y después `python -m nucleo.widget_cli show results`. **Nunca pegues el JSON en la línea de comandos ni "
    "uses un heredoc**: las comillas y las llaves los bloquea el guarda del shell. Y no te inventes un script "
    "propio para llamar a la API: el puente ya está permitido, úsalo tal cual. "
    "Ponlo en cuanto tengas resultados sólidos, y ve añadiendo con `data results append` según encuentres más: es "
    "mejor que el operador vea llenarse el informe que esperar callado al final. Cada item con su enlace REAL y, si "
    "el operador pidió verlo con fotos, su `image`. La voz final entonces es CORTA (2-3 frases: qué has encontrado "
    "y que está en pantalla) — el detalle ya lo está leyendo.\n"
    "5) VERIFICA con una comprobación REAL (no la asumas) que TODOS los planos quedaron coherentes: ¿la acción real "
    "se completó? ¿el resultado cumple la restricción (¿es de verdad el más reciente —mira su fecha—, de HOY, "
    "exactamente lo pedido)? ¿los espejos (widget/memoria) reflejan ya la realidad? Si algo no se puede certificar, "
    "dilo con honestidad — no des por bueno un resultado sin confirmarlo.\n"
    "6) ITERA si la verificación falla (afina la búsqueda, ordena por fecha, prueba otra fuente, corrige el espejo) "
    "hasta cumplirlo. Solo entrega cuando está CERTIFICADO en todos los planos. Nunca digas «hecho» sin verificar.")


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


def _build_prompt(request: str, context: str, trusted: bool, brief: dict | None = None) -> str:
    header = ("Eres un Brain Worker del asistente personal zaelar: una sesión de trabajo que CONDUCE una tarea del "
              "operador con tus herramientas (memoria, navegador, código, búsqueda). Resuelve la PETICIÓN de forma "
              "concreta y devuelve SOLO el resultado útil, natural y humano, SIN jerga técnica ni interna (nunca "
              "'píldora', 'memoria de corto/largo plazo', 'base de datos', ids ni mecanismos). El RESULTADO FINAL "
              "que entregas (lo que zaelar dice/muestra al operador) debe ser CONCISO — sin relleno, sin repetir el "
              "trabajo paso a paso ya reportado por el progreso, sin inflar la respuesta; al grano. (Esto es del "
              "resultado final, NO de tu proceso de trabajo — sigue investigando/ejecutando todo lo que haga falta "
              "y reportando el progreso como se indica abajo.)\n"
              "REPORTA TU PROGRESO de forma ESTRUCTURADA (zaelar lo enseña al operador y lo usa para responder "
              "'¿cómo va?'):\n"
              "  1) AL EMPEZAR declara tu plan: python -m nucleo.agent_report plan \"paso1|paso2|paso3|…\" "
              "(3-6 pasos concretos).\n"
              "  2) AL COMPLETAR cada paso: python -m nucleo.agent_report progress \"<qué acabas de terminar>\" "
              "--done <nº de pasos hechos>.\n"
              "  3) Para una fase legible puntual: python -m nucleo.agent_report phase \"<qué haces ahora>\".\n"
              "Reporta de verdad (no lo olvides): sin reporte, el operador no ve avanzar la tarea. Si necesitas un "
              "dato del usuario para seguir, pregúntaselo con 'python -m nucleo.worker_bridge ask \"<pregunta>\"' y "
              "ESPERA su respuesta. Si necesitas que zaelar haga algo por ti (buscar en la web), usa "
              "'python -m nucleo.worker_bridge act <accion> <json>'. Para LEER u OPERAR un widget del canvas "
              "(reflejar en la agenda/lista lo que has hecho en la realidad, o ENSEÑAR en pantalla un conjunto de "
              "resultados): 'python -m nucleo.widget_cli read|data|show|close <widget>' (lee primero, usa ids "
              "reales). NUNCA reescribas el CÓDIGO de un widget para meterle datos: los datos entran por sus "
              "acciones declaradas, que ves con `read`.")
    if not trusted:
        header = ("Eres un asistente que SOLO razona sobre el texto (fuente NO confiable): no ejecutes acciones ni "
                  "uses herramientas.")
    parts = [header]
    if trusted:
        parts.append(_today_block())
        parts.append(_METHOD_BLOCK)
    if context:
        parts.append("CONTEXTO DE MEMORIA (lo que zaelar ya sabe; úsalo si viene a cuento):\n" + context)
    if trusted:
        recent = _recent_conversation_block()
        if recent:
            parts.append("CONVERSACIÓN RECIENTE (los últimos turnos, para SITUAR la petición — los pronombres y "
                         "quejas del operador ('no se oye', 'ciérralo', 'eso') se refieren a lo que sale AQUÍ):\n"
                         + recent)
    parts.append("PETICIÓN:\n" + request)
    # El BRIEF va DESPUÉS de la petición literal, no antes: es la dirección de CÓMO hacerlo bien, y se lee mejor
    # sabiendo ya qué se pide. Sin brief (no es una investigación, o el compositor no estaba) esto no aparece y el
    # worker sale exactamente como salía antes.
    if brief:
        block = research.to_prompt_block(brief)
        if block:
            parts.append(block)
    return _with_interpreter("\n\n".join(parts))


# El prompt se ESCRIBE con `python -m nucleo.…` porque así se lee; lo que le LLEGA al worker es el intérprete REAL
# y absoluto. En esta máquina `python` a secas no existe (solo `python3` y el venv) — y el worker obedecía la
# instrucción al pie de la letra, fallaba, y se ponía a probar variantes hasta topar con el allowlist. Con la
# narración del worker visible (2026-08-02) se le vio decirlo con todas las letras: «`python` (bare) pasó el
# permiso pero no existe el binario; `.venv/bin/python` existe pero pide aprobación». Sustituir aquí es un solo
# punto de verdad: el texto sigue legible y el comando sale siempre ejecutable y ya permitido.
def _with_interpreter(prompt: str) -> str:
    # Solo si el prompt REALMENTE trae puentes. El perfil UNTRUSTED (texto de un peer) va sin tools por
    # construcción: colarle la cabecera le daría la ruta absoluta del engine sin ninguna necesidad.
    if "python -m nucleo." not in prompt:
        return prompt
    try:
        from nucleo.workers.claude_session import bridge_python
        py = bridge_python()
    except Exception:
        return prompt
    if not py or py == "python":
        return prompt
    out = prompt.replace("python -m nucleo.", f"{py} -m nucleo.")
    return (f"INTÉRPRETE: para CUALQUIER puente (`-m nucleo.…`) usa EXACTAMENTE `{py}`, tal cual, siempre. Está "
            f"permitido y funciona. NO uses `python` a secas ni `python3` ni rutas relativas: si un comando te pide "
            f"aprobación es que lo escribiste distinto — corrige el intérprete, no busques otra vía ni escribas un "
            f"script propio para llamar a la API.\n\n") + out


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
        if cont:
            tid = str(cont[0])
            try:
                navtasks.set_goal(tid, req)
            except Exception:
                pass
        else:
            tid = str(navtasks.create(req))
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
    except Exception:
        pass


# Guía de COMPORTAMIENTO HUMANO en la web (regla del operador 2026-07-21: "que parezcan humanos, orientar el uso
# de las páginas; genérico, para medio mundo, ES o EN — no scrapear, un asistente, nada raro"). GENÉRICA a
# propósito: no nombra sitios; describe cómo se mueve una PERSONA por casi cualquier web. Se antepone al manual de
# comandos del worker web. El sigilo TÉCNICO (Chrome real + fingerprint humano) vive en widgets/navegador/owner.py;
# esto es el COMPORTAMIENTO (ritmo, orden, gestos) que el modelo controla turno a turno.
_HUMAN_NAV_GUIDE = (
    "NAVEGA COMO UNA PERSONA, no como un robot (vale para casi cualquier web, en español o inglés; eres un "
    "asistente navegando POR el operador, no un extractor masivo):\n"
    "• RITMO humano: una acción cada vez, deja que la página cargue y 'léela' con `look` antes de seguir. No "
    "dispares comandos a ráfagas ni recargues la misma página en bucle.\n"
    "• Usa la PROPIA web como un usuario: su buscador y sus FILTROS (precio, ubicación, categoría, orden por "
    "fecha/precio) en vez de forzar URLs raras o parámetros a mano. Escribe en su caja de búsqueda y pulsa buscar.\n"
    "• COOKIES/consentimiento: acéptalos con naturalidad (un humano lo hace) para poder ver el contenido; si el "
    "banner reaparece, ciérralo y sigue.\n"
    "• Desplázate GRADUALMENTE (scroll de a poco, como quien ojea) para que carguen los resultados; abre una "
    "ficha/anuncio concreto para leer el detalle, como una persona interesada de verdad.\n"
    "• Si aparece una VERIFICACIÓN anti-robot, un captcha o un aviso de 'demasiadas peticiones': NO insistas a lo "
    "bruto (eso confirma que eres un bot). Para, espera unos segundos y reintenta UNA vez despacio; si sigue "
    "bloqueado, prueba OTRA web equivalente que tenga el mismo dato, o dilo con honestidad. Nunca machaques ni "
    "recargues en bucle.\n"
    "• No hagas nada 'raro': no toques login/pagos salvo que el objetivo lo pida y tengas permiso; no aceptes "
    "promos ni suscripciones; céntrate en el objetivo como lo haría una persona con prisa pero educada.\n\n"
)


def _web_prompt(goal: str, context: str, brief: dict | None = None) -> str:
    """Prompt del worker WEB (portado de web_cc/V2-036 al sustrato V2-038): conduce el navegador por hbweb con
    criterio de CIERRE (extraer → concluir → entregar) e hitos visibles. Sin él, el worker deambula.

    Con `brief` (nucleo/research.py) la BÚSQUEDA deja de ser «filtra y coge los 2-3 primeros»: el atajo de cierre
    rápido que este prompto lleva de serie —correcto para «tráeme el precio de X», ruinoso para «elige lo mejor»—
    se sustituye por el embudo del brief (reunir ancho → filtrar → puntuar → verificar finalistas)."""
    try:
        from nucleo.workers.claude_session import bridge_python
        py = bridge_python()          # absoluto y permitido; `.venv/bin/python` relativo pedía aprobación
    except Exception:
        py = ".venv/bin/python"
    try:
        from voice.engine.core import langs
        native = langs.current_language().native
    except Exception:
        native = "español"
    # V2-044 sesión 22:40: el objetivo escalado puede venir TERSO — la conversación reciente sitúa los pronombres
    # y restricciones que el modelo rápido no reformuló ("no se oye", "esa", "la de antes").
    recent = _recent_conversation_block()
    recent_block = (f"CONVERSACIÓN RECIENTE (sitúa el objetivo; lo que el operador mencione se refiere a esto):\n"
                    f"{recent}\n\n") if recent else ""
    p = (
        "Eres un Brain Worker de zaelar que CONDUCE un navegador web REAL para cumplir un OBJETIVO del operador, "
        f"paso a paso y con criterio. OBJETIVO (respétalo al pie de la letra):\n«{goal}»\n\n"
        + _today_block() + "\n\n"
        + recent_block +
        _HUMAN_NAV_GUIDE +
        "CÓMO CONDUCIR (desde la raíz del repo; el navegador ya tiene su pestaña asignada):\n"
        f"• VER la página como un humano (VISIÓN): {py} -m nucleo.nav_cli look\n"
        "     → imprime la ruta de un PNG; ÁBRELO con tu tool Read para VER la página, y actúa por coordenadas:\n"
        f"• Click por coordenadas (visión):  {py} -m nucleo.nav_cli click_at <x> <y>\n"
        f"• Escribir por coordenadas:        {py} -m nucleo.nav_cli type_at <x> <y> \"<texto>\" --submit\n"
        f"• (alternativa DOM) elementos:     {py} -m nucleo.nav_cli snapshot   → luego click <ref> / type <ref> \"<txt>\"\n"
        f"• Ir a una URL:                    {py} -m nucleo.nav_cli navigate \"<url>\"\n"
        f"• Desplazar / extraer:             {py} -m nucleo.nav_cli scroll 800   ·   {py} -m nucleo.nav_cli extract\n"
        f"• Progreso ESTRUCTURADO (el operador lo VE y zaelar responde '¿cómo va?'): al empezar "
        f"{py} -m nucleo.agent_report plan \"paso1|paso2|paso3\"  y al terminar cada paso "
        f"{py} -m nucleo.agent_report progress \"<hecho>\" --done <n>\n"
        f"• Fase legible puntual (tarjeta): {py} -m nucleo.agent_report phase \"<qué haces>\"\n"
        f"• Preguntar al operador y ESPERAR su respuesta: {py} -m nucleo.worker_bridge ask \"<pregunta>\"\n"
        f"• Leer un dato que zaelar ya sepa:  {py} -m nucleo.mem_cli recall \"<consulta>\"\n"
        f"• GUARDAR un dato que reúnas (para no volver a pedirlo): {py} -m nucleo.mem_cli remember \"<dato>\" --slot task.<algo>\n\n"
        "MÉTODO — como lo haría una persona competente; entiende la página y AVANZA (no des vueltas):\n"
        "1) MIRA con `look` (VISIÓN) antes de actuar: abre el PNG con Read y ubica los campos/botones por su posición "
        "en píxeles. La visión es tu camino PRINCIPAL para rellenar formularios, elegir en un calendario/desplegable "
        "o pulsar el botón correcto — el snapshot de texto es solo apoyo cuando los nombres son claros. Tras CADA "
        "acción importante vuelve a `look` para confirmar qué cambió (las coordenadas cambian al hacer scroll/navegar).\n"
        "2) DESBLOQUEA lo que tape la página: banner de cookies/consentimiento o aviso modal → ACÉPTALO/ciérralo "
        "(«Aceptar», «Acepto», «Entendido», «Continuar»…) para poder seguir. Si reaparece un par de veces, sigue igual.\n"
        "3) RECONOCE primero, pregunta UNA vez, ejecuta después (para una GESTIÓN: reservar/pedir cita, rellenar y "
        "enviar un formulario, tramitar, contratar):\n"
        "   a. RECON: recorre el flujo hasta VER el formulario real y ENUMERA todos los datos que pedirá (matrícula, "
        "fecha de matriculación, DNI, nombre, email, teléfono, estación, día/hora…). Consulta `mem_cli recall` lo que "
        "zaelar ya sepa.\n"
        "   b. PIDE DE GOLPE lo que falte: una SOLA `worker_bridge ask` con TODOS los datos que te faltan a la vez "
        "(no de uno en uno, no vayas y vengas). Espera la respuesta. NUNCA inventes valores.\n"
        "   c. GUARDA cada dato que reúnas con `mem_cli remember \"...\" --slot task.<campo>` EN CUANTO lo tengas — así "
        "no se pierde y no lo vuelves a pedir aunque el flujo se reinicie.\n"
        "   d. EJECUTA hasta el FINAL: rellena TODOS los campos con visión, elige opciones, avanza el calendario, "
        "acepta condiciones y ENVÍA/CONFIRMA. Es una acción a TERMINAR, no algo que se le explique al operador.\n"
        + ("   (Si el objetivo es BUSCAR/COMPARAR: llega a la página de RESULTADOS con los filtros exactos "
           "—categoría excluyente, ubicación/orden— y `extract`. NO cierres con los primeros que salgan: esta tarea "
           "trae un BRIEF DE INVESTIGACIÓN al final del prompt que fija cuántos candidatos hay que reunir ANTES de "
           "descartar y con qué baremo verificar a los finalistas. Manda el brief.)\n"
           if brief else
           "   (Si el objetivo es BUSCAR/COMPARAR productos: llega a la página de RESULTADOS con los filtros exactos "
           "—categoría excluyente, ubicación/orden—, `extract`, y concluye con los 2-3 que mejor encajan.)\n")
        +
        "4) SOLO te detienen dos cosas: un CAPTCHA o un LOGIN/pago que exija credenciales que no tienes. Todo lo demás "
        "(entender la página, aceptar cookies, elegir en un desplegable/calendario, rellenar y enviar) lo resuelves TÚ "
        "con visión — no es excusa para parar. Si de verdad hay un captcha/login, repórtalo y pregunta cómo seguir.\n"
        "5) NO TE ATASQUES: si repites la misma acción sin avanzar 2-3 veces, cambia de estrategia (otra entrada, otro "
        "botón, `look` de nuevo por si la coordenada cambió). Nunca gires en bucle en silencio. Reporta tu fase en "
        "CADA cambio de etapa. Si te REANUDAN una tarea ya empezada, haz `look` primero para ver dónde te quedaste y "
        "continúa desde ahí — NO reinicies desde cero.\n"
        "6) Si una respuesta de un puente trae ⟦NUEVAS INSTRUCCIONES DEL OPERADOR⟧, incorpóralas al objetivo.\n"
        "7) VERIFICA antes de cerrar (V2-057): comprueba de VERDAD que lo que vas a entregar cumple la restricción del "
        "objetivo — si pedía «el último/más reciente», confirma su FECHA (que sea el más nuevo, no uno cualquiera); "
        "si pedía algo «de hoy/actual», que el dato sea de la fecha real de hoy y de aquí en adelante; que sea "
        "EXACTAMENTE lo pedido, no algo parecido. Si no cumple, ITERA (ordena por fecha, afina el filtro, otra "
        "fuente) hasta que cumpla; si no se puede certificar, dilo con honestidad. No des por bueno un resultado sin "
        "confirmarlo.\n"
        "8) CIERRE: cuando la gestión esté HECHA y VERIFICADA (cita confirmada, formulario enviado, dato certificado) "
        "o de verdad necesites algo del operador, ESCRIBE tu conclusión/estado final en " + native + ", natural y "
        "humana, SIN jerga interna (nada de refs, comandos, coordenadas ni ids). Tu ÚLTIMA salida de texto es lo que "
        "se le dirá por voz. No inventes: básate en lo que VISTE. Si confirmaste una cita, di el día/hora/estación "
        "exactos."
    )
    if context:
        p += "\n\nCONTEXTO DE MEMORIA (lo que zaelar ya sabe; úsalo si viene a cuento):\n" + context
    if brief:
        block = research.to_prompt_block(brief)
        if block:
            p += "\n\n" + block
    return p


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
        env = {"ZAELAR_TASK_REQUEST": req}       # req crudo → registry (elige generador) + backend
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
            spec = WorkerSpec(kind=kind, model=_model_for(kind), tools=_tools_for(kind, trusted),
                              deny_tools=(not trusted), trusted=trusted, task_id=key,
                              token=rec_token(rec), parent_task_id=rec.parent_task_id, depth=rec.depth,
                              env=env, resume_sid=resume_sid)
        backend = get_backend(spec)
        session = WorkerSession(backend, spec, rec)
        rec.session = session
        # PRE-VUELO: ¿esto es una investigación/selección? Entonces se dirige con un brief (amplitud + baremo +
        # forma del entregable) en vez de dejar que el worker se autoimponga el criterio mínimo. Un dev-worker de
        # código no pasa por aquí: su dirección es el repo, no un espacio de candidatos.
        brief = None
        if not _dev:
            brief = await _compose_brief(req, ctx, trusted, resume)
            if brief:
                research.save(key, brief)
                research.remember_round(_goal_key(req), brief)   # para que una 2ª petición continúe, no reempiece
                rec.phase = "preparando la investigación"
                logger.info(f"dispatch: tarea {key} dirigida por BRIEF (ronda {brief.get('round')}, "
                            f"≥{(brief.get('breadth') or {}).get('min_candidates')} candidatos)")
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
                elif nav_tid or rec.native_sid:
                    _WEB_RESUME[gk] = {"nav_task": nav_tid or str((resume or {}).get("nav_task") or ""),
                                       "native_sid": rec.native_sid or str((resume or {}).get("native_sid") or ""),
                                       "ts": time.time(), "count": _prev_count + 1, "goal": req[:200],
                                       # los criterios ya acordados viajan a la reanudación: recomponerlos a mitad
                                       # de una búsqueda la convertiría en otra búsqueda distinta sin avisar
                                       "brief_task": key if brief else str((resume or {}).get("brief_task") or "")}
            try:
                if key.isdigit():
                    escalate.finish(int(key), rec.result_summary if rec.ok else "")
            except Exception:
                pass
            _waiting_user = (rec.waiting_on == "user") or bool(rec.ask)
            # V2-079: rastro DURABLE de la ejecución que se va (el registro vivo se purga aquí y desaparecía). El
            # ledger conserva el histórico para la pestaña «Procesos» del ChatWall. Best-effort, fuera del hot-path.
            try:
                from nucleo.workers import ledger as _ledger
                _ledger.record_finish(id=str(key), kind=str(kind or ""), goal=str(req or "")[:160],
                                      status=str(rec.status or "done"), started_at=getattr(rec, "started", None),
                                      trace_id=str(getattr(rec, "trace_id", "") or ""), ok=bool(rec.ok))
            except Exception:
                pass
            _SESSIONS.pop(key, None)
            try:
                from nucleo import worker_api
                worker_api.purge_task(key)   # §v3·L: sin asks pendientes de una sesión terminada
            except Exception:
                pass
            sync_state()
            # V2-049 AUTO-RESUME: gestión web incompleta, SIN pregunta pendiente, bajo el cap → CONTINÚA sola (el
            # FlashBrain no cesa la tarea ni espera un empujón del operador). Con pregunta pendiente NO: espera la
            # respuesta (que, al llegar como turno, reanuda por la misma vía). Con `ask` la purga de arriba ya la
            # quitó, por eso leímos _waiting_user ANTES.
            if _resumable and not _waiting_user and (_prev_count + 1) < _RESUME_CAP:
                _schedule_auto_resume(req)


def rec_token(rec: "SessionRecord") -> str:
    """Token de auth por-tarea para los bridges (§v2·D). Se guarda en el propio registro (atributo dinámico)."""
    tok = getattr(rec, "_token", "")
    if not tok:
        tok = secrets.token_urlsafe(18)
        setattr(rec, "_token", tok)
    return tok


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
                continue
            # V2-049 CONTINUIDAD: sin sesión viva que casar, ¿hay una gestión web INCOMPLETA reciente que ESTA
            # petición reanuda? (nudge «sigue con la ITV», o el operador aportando el dato que faltaba). Reanuda esa
            # misma pestaña + razonamiento en vez de arrancar de cero.
            _k = kind if kind != "generic" else _classify_kind(request)
            if _k == "web":
                _res = _find_resume(request)
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
