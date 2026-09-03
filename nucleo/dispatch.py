"""nucleo/dispatch.py — Manager of Brain Worker sessions (V2-038; reframes dispatcher V2-006/V2-036).

Receives escalations from FlashBrain (`bus:escalate.requested`) and converts them into live **Brain Workers**
(`nucleo/workers/`): an agnostic backend (`get_backend`) driven by a `WorkerSession`. Maintains the **SINGLE
IN-MEMORY REGISTRY** of live sessions (`_SESSIONS`), which is the **SOURCE OF TRUTH** (§v2·C) — absorbs and replaces
the three partial registries from before (`escalate._tasks`, `_INFLIGHT`, old `_SESSIONS`, §v3·G). Exposes:
  · `active_sessions()`/`has_active()`/`pending_summaries()` — projection for STATE/prompt/`/api/tasks`.
  · `inject(which, msg)` — injects into a live session (refinement; replaces V2-029's deduplicate-and-discard).
  · `cancel_session(tid)`/`cancel_all()` — terminate politely (terminate the process group through the backend).
  · `resolve_sessions(query)` — “for that process” → deterministic tid(s).

The confirmation gate for irreversible actions (V2-007) and kind classification are retained. Design:
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

from nucleo import dedup as _dedup
from nucleo import matching
from typing import Any

from loguru import logger

from nucleo import dev_worker_guard, research
from nucleo.workers import WorkerSpec, get_backend, workdir
from nucleo.workers.providers import worker_sees as _worker_sees
from nucleo import surfaces
from nucleo.workers.session import SessionRecord, WorkerSession
# Prompt composition (pure, no session-pool state) split out (V2-098) into its own module; re-exported by name
# so existing call sites (below, and tests doing dispatch._build_prompt/_web_prompt) keep working unchanged.
from nucleo.dispatch_prompts import _build_prompt, _web_prompt  # noqa: F401

# Classification heuristic (only when the escalation does not set `kind`). Conservative.
# kind="web" = the task requires ENTERING a specific site and operating it with a real browser (mode 2 of the decision
# «search web» in CLAUDE.md: marketplaces, login, automating an operation). It is NOT «the data is on the internet» —
# that is RESEARCH (mode 3), handled by a generic worker with WebSearch/WebFetch, which is much faster
# and does not fight cookie banners.
#
# Se quitan of here «in the web» and «in internet» (2026-08-02): «investiga EN INTERNET and preparame a informe»
# casaba and mandaba the task al browser. Observado in live with the narracion of the worker: 7 minutos peleandose with
# the banner of cookies of aquopolis.es, clicando by coordenadas and pidiendo analisis of imagen, for sacar a
# precio that `web_search` + `fetch` habian dado in segundos in the corrida anterior. Decir where lives a dato no es
# pedir that is abra a browser.
# V2-289 — the CLASIFICACIÓN of the errand (what clase es, how is rotula) lives in `nucleo/errand_kind.py`: son
# funciones puras sobre the texto of the request, without record ni pool detras. Se re-exportan with sus names
# privados because son the contrato that already usan the tests of higiene of escalada.
from nucleo.errand_kind import (  # noqa: E402,F401 — re-export
    _ARCHITECT_RE, _DATA_NOT_CODE_RE, _MODIFY_CODE_RE, _WEB_RE,
    classify_kind as _classify_kind, default_label as _default_label)


@dataclass
class Task:
    """An incoming FlashBrain escalation."""
    id: str
    request: str
    kind: str = "generic"
    trusted: bool = True
    context: dict[str, Any] = field(default_factory=dict)


# ── REGISTRO ÚNICO EN RAM = source of truth (§v2·C, §v3·G) ─────────────────────────────────────────────────
_SESSIONS: dict[str, SessionRecord] = {}

# ── V2-049 CONTINUIDAD web: REANUDAR in vez of re-launch of cero ─────────────────────────────────────────────
# When a worker WEB dies without COMPLETAR the operation, guardamos how REANUDARLO by CLAVE of objetivo: the same
# tab (continues in the pagina that alcanzo) + the session_id nativo a `--resume` (continua the razonamiento). La
# siguiente escalada of the MISMA operation —a nudge of the operator, su response a a dato, or the auto-resume of the
# own dispatch— CONTINÚA from there, in vez of open the tab 2ª/3ª/5ª and re-teclear todo (bug ITV 17-jul: 5
# workers, cero continuidad). Los datos reunidos already viven in memory (slots task.*), so that the worker reanudado
# no the vuelve a pedir. TTL 30 min; cap of auto-reanudaciones for no respawnear something roto in bucle.
# ── CONTINUIDAD WEB (V2-049) — extraida a `nucleo/workers/resume.py` (trinquete, 2026-08-26). Los names
# historicos quedan como ALIAS al MISMO objeto/funcion: quien mutaba `dispatch._WEB_RESUME` in site continues
# mutando the dict real, and the guardas of source miden the funciones reales esten donde esten.
from nucleo.workers import resume as _wres

_WEB_RESUME = _wres._WEB_RESUME
_RESUME_TTL = _wres._RESUME_TTL
_RESUME_CAP = _wres._RESUME_CAP
_resume_persist = _wres._resume_persist
_resume_restore = _wres._resume_restore
_goal_key = _wres._goal_key
_resume_entry = _wres._resume_entry
_leave_resume = _wres._leave_resume
_find_resume = _wres._find_resume


def _schedule_auto_resume(req: str) -> None:
    """V2-049: automatically resumes an incomplete web operation after a brief pause (without an operator nudge).
    Emits another escalation for the SAME request; the listener matches it to the newly recorded `_WEB_RESUME` entry
    and CONTINUES (same tab + `--resume`). The `_WEB_RESUME[count]` cap stops it if something is genuinely broken."""
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

# Loop DUEÑO of the sessions (uvicorn/server). El FlashBrain corre in OTRO loop (job-thread of LiveKit) → todo
# comando of session disparado from the turn of voice is MARSHALEA here (§v3·D), como browser_search.search_sync.
_LOOP: "asyncio.AbstractEventLoop | None" = None


def set_loop(loop) -> None:
    global _LOOP
    _LOOP = loop


def _model_for(kind: str) -> str:
    """Worker model — TIED TO THE PROVIDER TIER that will be used, not to the global configuration.

    `code_agent.model` (p.ej. `glm-5.2`) only exists in SU proveedor. Al relevar a another escalon there is that relevar
    also the name of the model: with the cuota of Z.AI agotada, the relevo a the licencia local seguia pidiendo
    `glm-5.2` and the CLI moria al instante with «There's an issue with the selected model (glm-5.2)» — a relevo that
    no releva. Con the licencia (or any escalon without model declarado) is returns "" and the CLI usa su default."""
    def _configured() -> str:
        try:
            from config import v2 as _v2
            key = kind if kind in ("web", "code", "memory") else "generic"
            return _v2.code_agent_model(key)
        except Exception:
            return ""

    # La cadena of relevo es of CLAUDE CODE (escalones `ANTHROPIC_BASE_URL`-compatible). Otro backend —Codex— is
    # autentica with SU own cuenta and esos escalones no significan nothing for el: leave that the cadena decidiera su
    # model TIRABA the model configurado (2026-08-12, measured). El caso real: with `base_url` apuntando aun a Z.AI of
    # when the proveedor era claude_code, and Z.AI in cooldown by cuota, `relayed()` daba True → is devolvia the
    # model of the escalon of relevo (empty) → Codex caia a su own `config.toml` (`gpt-5.6-sol`, that the API no
    # sirve) and the worker moria in 2,8 s with a 400. El `gpt-5.5` that the operator habia elegido no llegaba never.
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
    """Allowlist of worker tools by type. An untrusted turn never reaches here (deny_tools in the spec).

    NUNCA a `"Bash"` pelado (auditoria 2026-07-14): the Bash of the worker queda acotado a the CLIs bridge
    (`_BRIDGE_TOOLS` of `claude_session`, that is anaden solos) — a Bash abierto permitiria a a worker
    inducido by contenido web hostil open the SQLite in paralelo (`sqlite3 memory/_data/zaelar.db …`) and
    romper the ESCRITOR ÚNICO. Es the invariante documentado in CLAUDE.md («Bash SOLO a esos CLIs»)."""
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


# ── proyeccion for ESTADO / prompt / /api/tasks (the sincroniza the LOOP ~1 Hz, §v2·C) ───────────────────────
def active_sessions() -> list[dict]:
    """Serializable snapshot of LIVE sessions (without handles). Source of truth for STATE and /api/tasks.

    ⚠️ «VIVAS» it decia the docstring and NO it hacia the code (arreglado 2026-08-18): esto devolvia **todo**
    `_SESSIONS`, incluidas the `done`/`cancelled` that aun no is habian sacado of the record. Era the only of the
    three proyecciones without the filtro — `has_active()` and `pending_summaries()` it llevan justo debajo, and until
    `sync_state()` is it re-aplica a mano sobre `_SESSIONS` in vez of fiarse of this funcion, that es the senal mas
    clara of that was missing. Y all the consumidores the leen como if outside of live: `loop.py` the mete in a set that
    calls `live_ids`, `susurro/apply.py` dedupe contra ella (a task TERMINADA suprimiendo a re-ejecucion
    legitima) and `/api/tasks` alimenta the chips of the tab «Procesos» of the operator, that pinta each fila como
    «in curso» — or sea that a task acabada could verse trabajando. Es the desalineacion PROCESOS↔FLUJOS that
    reporto the operator: the tablero of flujos decia «ningun flujo activo» and Procesos seguia diciendo «creando a
    widget… in curso». Lo TERMINADO is reads of the ledger (`nucleo/workers/ledger.py`), that es su site."""
    now = time.time()
    out = []
    for r in _SESSIONS.values():
        if r.status not in LIVE_SESSION_STATES:
            continue
        out.append({
            "id": r.task_id, "kind": r.kind, "backend": r.backend, "goal": r.goal[:120],
            # V2-530 — the NAME, beside the brief and never instead of it: `goal` still carries the
            # operator's own words (dedup compares them, the Master audits them) and `title` is what a
            # human reads or hears. Falls back to the brief, so a consumer can use it unconditionally.
            "title": _sheets.title_of(r),
            "phase": r.phase, "status": r.status, "age_s": int(now - r.started), "paused": r.paused,
            # V2-227: where mira the operator. El frontend opens the sheet with esto ANTES of that haya a result,
            # so that viaja in the proyeccion live and no in the entrega.
            "surface": r.surface,
            # SILENCIO real from the ultimo evento of the worker. Es it that of truth says if esta stalled — `age_s`
            # only says if lleva rato trabajando, that no es it same (ver the detector in nucleo/loop.py).
            "silent_s": int(now - (r.last_event_at or r.started)),
            "waiting_on": r.waiting_on, "ask": r.ask[:160] if r.ask else "",
            # V2-059: observabilidad estructurada — plan + progreso + ultimos pasos reales.
            "plan": list(r.plan), "done": r.done, "total": len(r.plan), "pct": _progress_pct(r),
            "note": r.note, "steps": list(r.steps)[-6:],
            "considered": r.considered, "kept": r.kept,     # amplitud de una investigación (-1 = no aplica)
        })
    return out


def has_active() -> bool:
    return any(r.status in LIVE_SESSION_STATES for r in _SESSIONS.values())


# V2-354 — the RELOJES viven in `dispatch_thresholds` (trinquete); is re-exportan: `dispatch` es the contrato.
from nucleo.dispatch_thresholds import NO_STEP_SECS, STUCK_SECS  # noqa: F401,E402


# ── An ENDING is a FACT (V2-198/199/222/224/238) — extracted to `nucleo/workers/ended.py` (ratchet,
# 2026-09-03, V2-566). The historical names stay as ALIASES to the SAME objects/functions: whoever mutated
# `dispatch._ENDED_SESSIONS` in place keeps mutating the real dict, and the source guards measure the real
# functions wherever they live.
from nucleo.workers import ended as _ended
from nucleo import errand_continuity as _continuity

LIVE_SESSION_STATES = _ended.LIVE_SESSION_STATES
ENDED_SESSION_STATES = _ended.ENDED_SESSION_STATES
JUST_ENDED_S = _ended.JUST_ENDED_S
_ENDED_SESSIONS = _ended._ENDED_SESSIONS
_live_goals = _ended._live_goals
_remember_ended = _ended._remember_ended
recently_ended_sessions = _ended.recently_ended_sessions
mark_death_reported = _ended.mark_death_reported

def pending_summaries() -> list[dict]:
    """Reemplaza `escalate.pending()` (§v3·G): tasks EN CURSO for the filler of the provider + the bloque of the prompt."""
    now = time.time()
    return [{"id": r.task_id, "request": r.goal, "secs": int(now - r.started),
             "phase": r.phase, "waiting_on": r.waiting_on,
             # V2-131: SILENCE since the worker's last event. `active_sessions()` has carried it for the loop's
             # stall detector all along; the PROMPT never got it, so the brain answering "¿how va?" could only
             # see "it started N seconds ago" and had to guess what counts as too long. It guessed "sigo in
             # marcha" six turns running over a task that had emitted nothing at all.
             "silent_s": int(now - (r.last_event_at or r.started)),
             # V2-059: the FlashBrain can say the PASO real + progreso if the operator question "¿how va?".
             "pct": _progress_pct(r), "done": r.done, "total": len(r.plan), "note": r.note,
             # V2-354 — segundos without COMPLETAR a step of the plan (≠ `silent_s`); the porque, in `NO_STEP_SECS`.
             "no_step_s": int(now - (getattr(r, "last_step_at", 0) or r.started)),
             # Amplitud in curso: leaves al cerebro contestar «va by 30 candidatos» and, al acabar, ofrecer continue.
             "considered": r.considered, "kept": r.kept,
             "sheet": sheet_of(r)}     # V2-451: la hoja es del ENCARGO, y sin esto solo viajaba con navegador
            for r in _SESSIONS.values() if r.status in LIVE_SESSION_STATES]


def get_record(tid) -> "SessionRecord | None":
    return _SESSIONS.get(str(tid))


def record_by_nav_task(nav_tid) -> "SessionRecord | None":
    """El worker that conduce the tab of browser `nav_tid` (for sellar trace/span from the bridge hbweb,
    that corre in the loop of the server without contexto of trace). V2-048."""
    nav_tid = str(nav_tid)
    for r in _SESSIONS.values():
        if getattr(r, "nav_task", "") == nav_tid:
            return r
    return None




# ── the HOJA of results como superficie of the progreso (V2-227 ambito C · extraida a `nucleo/sheets.py` the
# 2026-08-24, V2-276) ─────────────────────────────────────────────────────────────────────────────────────────
# La seccion lives ahora in su own module HOJA, that no importa this file: the three funciones that recorren
# the record live it reciben, and these envolturas is it pasan. Se re-exporta todo because there is produccion and tests
# that it importan by name from here — es a mudanza, no a cambio of interfaz.
from nucleo.turn_marks import mark_stall_offered, stall_offered  # noqa: F401 — re-export
from nucleo.sheets import (  # noqa: F401 — re-export
    PHASES_KEPT, _phrases, _sheet_close, _sheet_open, retitle as _sheet_retitle, sheet_id_for, sheet_of,
)
from nucleo import sheets as _sheets


def _sheet_sessions() -> list:
    return _sheets.sheet_sessions(_SESSIONS.values(), LIVE_SESSION_STATES)


def sheet_for_nav_task(nav_task: str) -> str:
    """La sheet donde entregar it that ESTA tab encuentre, abriendola if su errand aun no has (V2-290)."""
    return _sheets.sheet_for_delivery(nav_task, _SESSIONS.values(), LIVE_SESSION_STATES)


def sheet_progress(sheet: str = "") -> dict:
    return _sheets.sheet_progress(sheet, _SESSIONS.values(), LIVE_SESSION_STATES)


def sheet_harvest(sheet: str = "") -> dict:
    """Los NÚMEROS of the sheet (V2-296). Cuerpo in `nucleo/sheets.py`; here only is le pasa the record live."""
    return _sheets.sheet_harvest(sheet, _SESSIONS.values(), LIVE_SESSION_STATES)


def record_phase(tid, phase: str) -> bool:
    """Apunta a linea in the diario of PROCESO of `tid`. El body lives in `nucleo/sheets.py` (V2-281):
    here only is resuelve the record, that es it only that this module has and aquel no."""
    return _sheets.record_phase(_SESSIONS.get(str(tid)), phase, PHASES_KEPT)

def session_phase(tid, phase: str) -> None:
    """Compat V2-036: reporte of fase EXPLÍCITO of the worker (hbnote). Actualiza the record RAM."""
    r = _SESSIONS.get(str(tid))
    if r is not None:
        _p = (phase or "").strip()
        r.phase = _p or r.phase
        r.last_event_at = time.time()
        record_phase(tid, _p)   # V2-358: `sheets.record_phase` marca la afirmación sin respaldo
    try:
        from voice.observer import emit
        extra = {"id": str(tid)}
        # V2-044: the handler HTTP of the CLI (hbnote) no has contexto of trace → sellar the of the session.
        if r is not None and r.trace_id:
            extra["trace"] = r.trace_id
            extra["span"] = f"worker:{tid}"
        emit("task", "phase", text=(phase or "").strip(), extra=extra)
    except Exception:
        pass


def session_alive(tid) -> str:
    """A LATIDO: the same fase, diciendo how much lleva. No touches the record (V2-227 ambito B2).

    Una tarjeta congelada in «recorriendo the pagina» durante noventa segundos es indistinguible of a worker
    dead, and esa ambiguedad es justo it that the operator pidio quitar: the silencio is reads como averia. Pero the
    remedio no can ser reescribir `r.phase` with the texto decorado — the latido siguiente decoraria the
    decoracion («… lleva 1 min — lleva 2 min»). Asi that is EMITE and no is guarda: the record preserves the fase
    limpia and the carril lleva the version with the time.

    Devuelve it emitido (or "" if no habia nothing that latir), that es it that does esto comprobable without a bus.
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
    """V2-059: the worker DECLARA su lista of tasks al empezar (`hbnote plan "a|b|c"`). Observabilidad estructurada:
    is ve the plan + cuantos pasos lleva → progreso real (no only a fase coarse)."""
    r = _SESSIONS.get(str(tid))
    if r is None:
        return
    if isinstance(steps, str):
        steps = [s.strip() for s in re.split(r"[|\n]", steps) if s.strip()]
    r.plan = [str(s)[:80] for s in (steps or [])][:12]
    r.done = 0
    r.last_event_at = time.time()
    r.last_step_at = r.last_event_at      # V2-354: el reloj del avance arranca AL DECLARAR el plan
    try:
        from voice.observer import emit
        extra = {"id": str(tid), "plan": r.plan}
        if r.trace_id:
            extra.update(trace=r.trace_id, span=f"worker:{tid}")
        emit("task", "plan", text=f"{len(r.plan)} pasos: " + " · ".join(r.plan)[:160], extra=extra)
    except Exception:
        pass


def session_progress(tid, note: str = "", done: int | None = None, pct: int | None = None) -> None:
    """V2-059: the worker reporta PROGRESO (`hbnote progress "..." --done N` / `--pct P`). Actualiza done/pct/note
    of the record → ESTADO/prompt of the FlashBrain + /api/tasks + observabilidad. Fail-soft."""
    r = _SESSIONS.get(str(tid))
    if r is None:
        return
    if note.strip():
        r.note = note.strip()[:200]
    if done is not None:
        try:
            _nuevo = max(0, int(done))
            if _nuevo != r.done:
                r.last_step_at = time.time()    # V2-354: el reloj del AVANCE, no el de la señal
            r.done = _nuevo
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
    """AMPLITUD reportada by the worker (`hbnote considered N --kept M`): cuantos candidatos ha evaluado of truth.

    Existe for that the SELECCIÓN sea auditable. Sin this dato, «te he encontrado the 3 mejores» es indistinguible
    of «te he copiado the 3 primeras that salieron», and ni the operator ni the cerebro can juzgar if conviene continue
    buscando. Con el, the cerebro can ofrecer the continuacion with a number concreto delante."""
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
    """% of progreso: the explicito if it there is; if no, done/len(plan); -1 if desconocido."""
    if getattr(r, "pct", -1) >= 0:
        return r.pct
    if r.plan:
        return int(100 * min(r.done, len(r.plan)) / len(r.plan))
    return -1


_last_sync: tuple | None = None


def sync_state() -> None:
    """Proyecta the record RAM al ESTADO of memory (`activity` + `sessions`). La calls the LOOP (~1 Hz) and the
    points of cambio grueso (start/end/cancel) — coalescada, never by-evento (§v2·C: no floodear SQLite).
    SKIP-IF-UNCHANGED (2026-07-16): the loop the calls each tick; if no there is workers live, escribia the state —and
    disparaba `memory.updated`→SSE— CADA SEGUNDO without cambio, floodeando the visor/log and churneando SQLite. Ahora
    only writes when the proyeccion REALMENTE cambia."""
    global _last_sync
    try:
        from memory import api as memory
        sess = active_sessions()
        labels = [(r.phase or _default_label(r.kind)) for r in _SESSIONS.values()
                  if r.status in LIVE_SESSION_STATES]
        # Deteccion of cambio SIN fields volatiles: `age_s` (and any time transcurrido) SUBE each second →
        # if is incluye, with a session live the snapshot difiere SIEMPRE and is reescribe the state each tick
        # (flood of MEMORY·state, the bug 2026-07-16). Comparo only the fields ESTABLES; the state escrito si
        # preserves age_s (it usa the prompt), but no dispara memory.updated if nothing relevante cambio.
        stable = [{k: v for k, v in s.items() if k not in ("age_s", "silent_s", "secs", "updated", "ts")}
                  for s in sess]
        snap = (tuple(labels), json.dumps(stable, sort_keys=True, default=str))
        if snap == _last_sync:
            return                      # nada relevante cambió → no reescribir ni emitir memory.updated (~1 Hz)
        _last_sync = snap
        memory.set_state({"activity": labels, "sessions": sess})
        # REHIDRATACIÓN (2026-08-12): the same cambio leaves a rastro DURABLE in `sys_kv` with marca of time. Es it
        # that allows that the arranque siguiente sepa what habia in vuelo if this proceso dies (a reinicio mato a
        # search of the operator SIN leave constancia). Va here because this es the only point that already sabe that the
        # proyeccion cambio — no adds ni a escritura extra in reposo. Ver `nucleo/rehydrate.py`.
        try:
            from nucleo import rehydrate as _rehydrate
            _rehydrate.remember(sess)
        except Exception:
            pass
    except Exception:
        pass


# ── resolucion of "which" for inject / stop (determinista, §v2·B/§v3·M) ──────────────────────────────────────
def _norm(text: str) -> str:
    return matching.norm_text(text)


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


# The tokenizer moved to `nucleo/matching.py` (F4, 2026-08-23) with its history — the punctuation lesson of
# V2-123, the non-latin-alphabet note — because it stopped being this module's private business the day it turned
# out `widgets/browser/tasks._similar` was judging the SAME question with its own copy and the two disagreed
# about the same pair of texts. One yardstick, imported; the local names survive for the callers.
def _content_words(text: str) -> set:
    return matching.content_words(text)


def _target_widget(request: str) -> str:
    return _dedup.target_widget(request)


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
    """tid of a session VIVA that already atiende ESTA request ('' → None). La REGLA lives in `nucleo/dedup.py`;
    here only is resuelve QUIÉN esta live, that es it only that this module sabe."""
    return dedup_scan(request, kind)[0]


def _live_errands() -> list[tuple[str, str]]:
    """(tid, goal) of each session VIVA — the only point that traduce the record RAM for the two jueces."""
    return [(k, r.goal) for k, r in _SESSIONS.items() if r.status in LIVE_SESSION_STATES]


def dedup_scan(request: str, kind: str) -> tuple[str | None, dict]:
    """El veredicto of the dedup Y the evidencia sobre the that it tomo (`nucleo/dedup.scan`)."""
    return _dedup.scan(request, kind, _live_errands())


#: Re-exportado for that `run_listener` it resuelva como global of the module — so a test can sustituirlo
#: and the cableado real continues siendo the that is prueba.
about_a_live_errand = _dedup.about_a_live_errand


# ATRIBUCIÓN: what palabras of a alusion sirven for reconocer a task, and cuando two son LA MISMA cosa.
#
# V2-140 — criterion 2 of the caso `three-tasks-at-once` («each mensaje by alusion must ir a the task CORRECTA»).
# Medido with three tasks live and the frases reales of the caso, before of touch nothing:
#
#     «¿and the of the coche?»                        → ['t1','t2','t3']   (t1 = «informe sobre COCHES electricos»)
#     «the of the monitor, that sea of 27 pulgadas»  → ['t1','t2','t3']   (t2 = «a MONITOR barato of second mano»)
#
# Dos causas mecanicas, ninguna of the model. La first es the MISMA that costo money in V2-123 (`find_duplicate`
# comparando «guitarra» with «(guitarra»): is troceaba by espacios sobre a `_norm` that only quita acentos and
# minusculiza, so that **the puntuacion is quedaba pegada** — `coche?` and `monitor,`. Es the funcion hermana, in the
# same file, and no is reviso entonces. La second es that the cruce era by igualdad exacta, so that `coche` no
# reconocia `coches`: the persona alude in singular a something that pidio in plural, that es it normal al hablar.
#
# El emparejamiento by prefijo va ACOTADO a purpose — the atribucion that is equivoca manda the refinamiento a
# the task that no es, and eso es peor that no resolver: minimo 4 caracteres of raiz and como mucho 3 of diferencia,
# of modo that `coche`/`coches` e `informe`/`informes` casan and `coche`/`cocina` no.
_REF_WORD_RE = re.compile(r"\w+", re.UNICODE)


def _ref_words(text: str) -> set[str]:
    return {w for w in _REF_WORD_RE.findall(text or "") if len(w) > 3}


def _same_thing(a: str, b: str) -> bool:
    if a == b:
        return True
    short, long_ = (a, b) if len(a) <= len(b) else (b, a)
    return len(short) >= 4 and len(long_) - len(short) <= 3 and long_.startswith(short)


def resolve_sessions(query: str) -> list[str]:
    """Referencia of the operator → tid(s) live. '' / 'todo' → all; a sola live → esa; varias → by kind or
    solape of palabras with the goal; nothing casa → all (mejor parar of mas that leave zombies)."""
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


# ── inyeccion (↓) ────────────────────────────────────────────────────────────────────────────────────────
async def inject(which: str, message: str) -> list[str]:
    """Inyecta `message` a the(s) session(es) that resuelva `which`. Devuelve the tid inyectados. Reemplaza the
    dedup-descartar of V2-029: a refinamiento is INYECTA, no is tira (§v3·G)."""
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
                # aun EN COLA of the pool (without proceso): the instruccion queda `pending` in the record and is entrega
                # by piggyback in the first contacto of the worker (§v3·H) — never is pierde in silencio.
                from nucleo.workers.session import Inject
                r.injects.append(Inject(text=message, ts=time.time()))
            done.append(tid)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"dispatch: inject a {tid} falló: {e}")
    return done


def take_pending_injects(tid) -> list[str]:
    """Piggyback: worker_api the calls al responder a a bridge → entrega the inyecciones pending (§v3·H).
    Lee the RECORD (no the session): also entrega it inyectado mientras the task esperaba in the cola of the pool."""
    r = _SESSIONS.get(str(tid))
    if not r:
        return []
    out = []
    for inj in r.injects:
        if inj.state == "pending":
            inj.state = "delivered"
            out.append(inj.text)
    return out


# ── entradas SÍNCRONAS marshaladas al loop of the server (the calls the FlashBrain from the job-thread, §v3·D/O) ──
def inject_soon(which: str, message: str) -> None:
    """Fire-and-forget: inyecta a the(s) session(es) of `which`, in the loop dueno. NUNCA is await-ea in the turn."""
    if _LOOP is None:
        return
    try:
        asyncio.run_coroutine_threadsafe(inject(which, message), _LOOP)
    except Exception:
        pass


def cancel_soon(which: str) -> list[str]:
    """Fire-and-forget: resuelve `which` and MATA in the loop dueno. Devuelve the tid that VA a kill (for the voice)."""
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


# ── MATAR (with cortesia) ─────────────────────────────────────────────────────────────────────────────────
def cancel_session(tid, *, reason: str = "operator") -> bool:
    """Mata a session: cancela su asyncio.Task (→ the backend mata the grupo of procesos) and purge record +
    chip + state of inmediato (reflejo instantaneo). Idempotente."""
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


# ── V2-065 (2026-07-23): PAUSAR ≠ kill — the boton ⏻ of the operator. A diferencia of `cancel_all` (mata of truth,
# irreversible, usado by Reset), esto congela the workers VIVOS in the site (SIGSTOP al backend, ver
# `workers/base.py::pause`) and the leaves in the record tal cual — `resume_all()` the continua exactamente donde
# estaban. Un backend that no soporta pausar of truth (Codex stub, generator_session) simplemente no does nothing
# (`pause()` returns False) — never rompe. Best-effort, sincrono (SIGSTOP/SIGCONT no son I/O).
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
    """Apagado ORDENADO of the lifespan (§v3·L): for the backends waiting su cierre (killpg) ANTES of tumbar the
    loop. Devuelve how many sessions habia."""
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


# ── arranque of a session from a escalada ────────────────────────────────────────────────────────────


async def _seed_research_criteria(brief: dict) -> None:
    """Vuelca the brief recien compuesto a the tab CRITERIOS of the sheet of results.

    Se does AQUÍ, in the pre-vuelo, and no inside of the worker: if dependiera of that the ejecutor is acuerde of
    escribirlo, faltaria justo in the busquedas that peor van. Efecto of step —and buscado—: the `goal` es the firma
    of the errand, so that start a research DISTINTA empty the sheet of the anterior. El operator already is comio
    a vez quedarse mirando the results of the search of before creyendo that eran the suyos. Una ronda 2
    preserves the objetivo, so that «continues buscando» no borra nothing.

    Best-effort duro: esto es the pantalla, no the work. If the widget falla, the research continues igual."""
    try:
        payload = research.to_criteria(brief)
        if not payload:
            return
        from widgets.server_api import brain_action
        await brain_action("results", "criteria", payload)
    except Exception as exc:                                # noqa: BLE001 — nunca frenar una tarea por la vista
        logger.debug(f"dispatch: no pude sembrar los criterios en la hoja de resultados ({exc})")


async def _compose_brief(request: str, context: str, trusted: bool, resume: dict | None = None) -> dict | None:
    """PRE-VUELO of a research: convierte the request cruda in a BRIEF dirigido (nucleo/research.py).

    Por what esta AQUÍ and no in the turn of voice: dirigir bien a search —separar criterios duros of blandos,
    add it that a experto sabe that hara missing, fijar cuan wide there is that buscar and with what baremo juzgar— es a
    work of razonamiento, and the FlashBrain of voice has that contestar in milisegundos. Aqui already estamos outside of
    ese reloj: the escalada es asincrona, the operator already sabe that esto tarda, so that this es the only point of the
    sistema donde is can pensar before of empezar a trabajar.

    If es a REANUDACIÓN, the brief of the ronda anterior is reuses tal cual: the criterios already estaban acordados
    and recomponerlos podria cambiarlos a mitad of a search that the operator cree that continues the same guion."""
    if not trusted:
        return None                       # perfil sin tools: no hay investigación que dirigir
    prev_tid = str((resume or {}).get("brief_task") or "")
    if prev_tid:
        prev = research.load(prev_tid)
        if prev:
            return prev
    # ¿Ya investigamos esto and the operator vuelve a the load? Entonces es the RONDA SIGUIENTE of the same search:
    # hereda the criterios acordados and sube the amplitud, with su frase of ahora como reason of the rechazo. Sin esto,
    # «esos no me valen, busca mas» recomponia the brief from cero and repetia the same search with the same
    # amplitud — the operator habria visto arrive the same results and concluido, with razon, that no le escuchamos.
    gk = _goal_key(request)
    prev = research.previous_round(gk)
    if prev:
        nxt = research.expand(prev, note=request)
        logger.info(f"dispatch: RONDA {nxt.get('round')} de una investigación ya conocida "
                    f"(≥{(nxt.get('breadth') or {}).get('min_candidates')} candidatos): {request[:60]}")
        return nxt
    return await research.compose(request, context)


#: Live references to the errand NAMERS (V2-530), for the same reason the brief composers below need one: a
#: bare `Task` can be garbage-collected mid-flight and die in silence.
_TITLE_BG_TASKS: set = set()


def _name_errand(rec) -> None:
    """Give this errand its NAME, without anybody waiting for it (V2-530).

    Fire-and-forget on purpose. The sheet is already on screen under the brief, the worker is already spawning,
    and the voice already answered — so the only thing a slow or dead provider can cost here is a box that
    keeps the name it already had. That is why nothing upstream checks the result.
    """
    try:
        from nucleo import errand_title as _et
        if not _et.enabled() or not (rec.goal or "").strip():
            return

        async def _go():
            try:
                t = await _et.compose(rec.goal)
            except Exception:  # noqa: BLE001
                return
            if not t or t == (getattr(rec, "title", "") or ""):
                return
            rec.title = t
            try:
                from voice.observer import emit
                emit("task", "🏷️ encargo nombrado", text=t, role="system",
                     extra={"id": rec.task_id, "goal": (rec.goal or "")[:120]})
            except Exception:
                pass
            if surfaces.opens_sheet(getattr(rec, "surface", "")):
                _sheet_retitle(rec)
            sync_state()

        _t = asyncio.ensure_future(_go())
        _TITLE_BG_TASKS.add(_t)
        _t.add_done_callback(_TITLE_BG_TASKS.discard)
    except Exception:  # noqa: BLE001
        pass


#: Referencias live a compositores in second plano (V2-301): a Task without referencia can ser recolectado a
#: mitad, and this dies in silencio — the clase of failure that leaves al worker without address without that nothing avise.
_BRIEF_BG_TASKS: set = set()


def _attach_brief_followup(task: "asyncio.Task", *, key: str, rec: "SessionRecord", req: str,
                           kind0: str) -> None:
    """V2-301 — the second half of the parallel brief. When the composer finishes AFTER the worker already
    spawned, its direction still has to do everything the serial path did: persist/seed the brief, promote a
    `generic` task to the research budget (direction proves it IS an investigation), and reach the RUNNING
    worker — as an injected turn, through the same channel every mid-task refinement already uses (V2-038).

    The callback runs in the owner loop (the composer task was created there), so `ensure_future` is safe.
    A composer that dies here changes nothing for the worker — it is already running, which is exactly the
    fail-open the serial path promised («the worker starts SIN brief»); only the budget promotion is still
    honoured, same as the serial ComposerUnavailable branch.
    """
    _BRIEF_BG_TASKS.add(task)

    def _done(t: "asyncio.Task") -> None:
        _BRIEF_BG_TASKS.discard(t)
        b, unavailable = None, False
        try:
            b = t.result()
        except (research.ComposerUnavailable, asyncio.CancelledError):
            unavailable = True
        except Exception:  # noqa: BLE001
            unavailable = True
        try:
            if b:
                research.save(key, b)
                research.remember_round(_goal_key(req), b)
                asyncio.ensure_future(_seed_research_criteria(b))
                block = research.to_prompt_block(b)
                if block and rec.status in LIVE_SESSION_STATES:
                    inject_soon(key, ("Ya está compuesta la DIRECCIÓN de tu investigación — aplícala DESDE "
                                      "AHORA a lo que estás haciendo, sin reempezar lo ya andado:\n\n" + block))
            # La promocion of budget va with brief O with compositor caido (same two ramas that the camino
            # serial); a compose that returns None a secas said «esto no es a research» and no promociona.
            if (b or unavailable) and kind0 == "generic" and rec.kind == "generic":
                rec.kind = "research"
                rec.label = _default_label("research", req)
                logger.info(f"dispatch: tarea {key} promocionada a research por el brief tardío")
                sync_state()
        except Exception:  # noqa: BLE001
            pass

    task.add_done_callback(_done)


# ── contrato WEB restaurado (demo 2026-07-14: the search corrio INVISIBLE) ────────────────────────────────
# En the refactor V2-038 (P2) the flujo `kind=web` is unifico bajo the WorkerSession generico and is PERDIÓ the step
# of `web_cc` that creaba the task+TARJETA of the browser and daba al worker the contrato of cierre → the worker of the
# demo navego 12+ min without superficie visible ni entrega. Se restaura AQUÍ, inside of the sustrato new:
# a task = a tab = a tarjeta (continuidad V2-032 incluida) + prompt web with criterion of CIERRE.
_FORCE_NEW_RE = re.compile(
    r"\b(otro|otra|segundo|segunda|nuevo|nueva|aparte|adem[aá]s|en paralelo|a la vez)\b[^.]*"
    r"\b(navegador|pesta[ñn]a|ventana|b[uú]squeda|tarea)\b", re.I)
_COEXIST_RE = re.compile(r"\bsin (parar|detener|cerrar|tocar)\b", re.I)


async def _prepare_web(rec: "SessionRecord", req: str, reuse_tid: str = "") -> str:
    """kind=web: crea (or RE-USA, continuidad V2-032/V2-049) the task of the browser and ABRE su tarjeta ANTES of
    start the worker. Devuelve the id of navtask ('' if the subsistema no esta). El id viaja al worker by
    ZAELAR_NAV_TASK → sus capturas/actions casan with ESTA tarjeta (and su tab, that persiste in the owner)."""
    try:
        from widgets.navegador import tasks as navtasks
    except Exception:
        return ""
    try:
        # V2-049: reanudacion EXPLÍCITA → same tab that alcanzo the worker anterior (continues in su pagina).
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
            _tr = str(getattr(rec, "trace_id", "") or "")   # V2-281: la HOJA viaja con la pestaña, como el trace
            tid = str(navtasks.create(req, trace=_tr, sheet=sheet_of(rec)))
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
    """Cierra the TARJETA of the browser with it encontrado: extrae the anuncios that quedaron in pantalla (the
    tab of the owner continues live although the worker haya dead/sido matado) and fija the state final. Best-effort.
    V2-049: if `keep_open` (operation web incompleta that is va a REANUDAR), NO the marca «failed» — the leaves in PAUSA
    (working) for that the tab and su pagina is conserven and the worker reanudado continue donde estaba."""
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
        # V2-257 — tercer and ultimo camino by the that the browser encuentra something; the three pasan already by the same
        # puerta (`widgets/results/intake`). Va DESPUÉS of the cierre by two razones: mantiene pegados the
        # `set_results` and the final that exige the invariante of V2-192 (a task VIVA no can tener results),
        # and leaves outside the caso `cancelled` — the operator said that parasemos, so that no le llenamos the sheet.
        if items and rec.status != "cancelled":
            try:
                from widgets.results import intake as _intake
                _intake.push(items, sheet=sheet_of(rec),
                             source_url=str((navtasks.get(tid) or {}).get("url") or ""))
            except Exception:  # noqa: BLE001
                pass
            # …and the HECHO a the conversacion. Escribir the filas and no contarlo es it that media the arnes the
            # 2026-08-24: llegaban a the sheet 42-113 s before of the ultimo turn and the agent seguia diciendo
            # «still no tengo nothing». `intake.push` no lleva nota a purpose —es the puerta shared of the
            # three caminos and the nota the empuja the caller— and of the three este era the only that no the empujaba.
            # La condicion of «only if nadie it ha contado already» lives with the resto in `workers/findings.py`.
            try:
                from nucleo.workers import findings as _find
                _find.hand_sheet_finding(tid, items, rec.goal)
            except Exception:  # noqa: BLE001
                pass
    except Exception:
        pass


async def _compose_context(request: str, kind: str) -> str:
    """Contexto minimo of memory for the worker (best-effort, off-voice). Fail-open a empty, but AVISANDO:
    the fail-open silencioso escondio durante todo V2-038 a typo (`compose_task_context`, funcion inexistente)
    that dejaba a TODOS the workers without the bloque «CONTEXTO DE MEMORIA» (auditoria 2026-07-14)."""
    try:
        from nucleo import memory_agent
        return await memory_agent.compose_context(request, budget=2000)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"dispatch: compose_context falló ({e}); el worker {kind} sale SIN contexto de memoria")
        return ""


# La address of this motor lives in `nucleo/engine_url.py` (V2-296): funcion pura of two env vars, without state
# of the gestor of sessions. Se re-exporta because es a mudanza, no a cambio of interfaz.
from nucleo.engine_url import _own_base_url  # noqa: E402,F401 — re-export


async def _run_session(task: "Task") -> None:
    """Crea and conduce UNA session bajo the pool. Never lanza (corre como task suelta)."""
    from nucleo import danger
    from nucleo.flash import escalate

    key = str(task.id)
    req = (task.request or "").strip()

    # TRAZABILIDAD (V2-044): adopta the trace of the frase that origino the escalada (viajo in task.context because the
    # bus no copia contexto). span=worker:<id> → TODOS the emits of the ciclo (fases, chips, entrega, notify) quedan
    # encadenados a esa frase in the arbol of Trazas.
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

    # CONFIRM-GATE of irreversibles (V2-007) — before of start nothing.
    if trusted and danger.is_dangerous(req) and not bool(task.context.get("confirmed")):
        logger.info(f"dispatch: tarea {key} PARA por confirm-gate: {req[:80]}")
        rec = _SESSIONS.get(key)
        if rec:
            rec.status = "done"
            rec.result_summary = danger.confirm_question(req)
            await _deliver_confirm(rec)
            _SESSIONS.pop(key, None)
            # La question is RECUERDA (V2-126). Hasta here the gate era a callejon without salida: hablaba the
            # question by the rail proactivo, tiraba the record, and nadie ponia never `context["confirmed"]`
            # — a `si` of the operator no tenia a what volver. Peor: the task desaparecia of `pending_summaries`,
            # so that the turn siguiente NO veia nothing pending and volvia a narrar work that no existia.
            # Medido in `cancel-subscription-before-charge` and in `pay-known-bill` (three tasks, the three
            # paradas by the gate, ninguna contada al operator).
            # …with su HOJA: already esta abierta in pantalla and the «si» has that volver a ELLA (V2-508).
            remember_confirm(key, req, task, sheet=sheet_of(rec))
            sync_state()
        return

    rec = _SESSIONS.get(key)
    if rec is None:
        return
    rec.kind = kind
    rec.label = _default_label(kind, req)
    sync_state()

    # LA CADENA ENTERA DORMIDA: no is lanza nothing (V2-314). Spawning here is a GUARANTEED death — every tier of
    # the worker chain is in cooldown, and the CLI would burn ~30 s in the pool to die in two. What made this
    # invisible is that `providers.pick()` returns None both when the chain is EMPTY (self-host, no keys: run
    # the local license, the promised fail-open) and when every tier is asleep — so the cooldown we record for
    # the LICENSE tier could never bite, and we spawned straight back into the provider that had just said no.
    # Measured in `find-concert-tickets__es` (2026-08-25 10:53-10:56): license marked out-of-quota until 14:20,
    # then spawned into twice more inside three minutes — 1.8 s, 3.9 s, 1.9 s of life, and a person told three
    # times that a search was starting. `exhausted_until()` is the seam that tells the two Nones apart.
    try:
        from nucleo.workers import providers as _prov
        _sleep_reason = _prov.exhausted_reason()
    except Exception:  # noqa: BLE001
        _sleep_reason = ""
    if _sleep_reason:
        logger.warning(f"dispatch: tarea {key} NO se lanza — cadena de proveedores agotada")
        try:
            from voice.observer import emit
            # `provider_asleep` and not a plain `end`: the round did not fail, it never started. The Master and
            # the harness both need to tell «we tried and it broke» from «we knew it was pointless», or an
            # exhausted quota keeps being scored as a broken product.
            emit("task", "provider_asleep", role="system", text=req[:120],
                 extra={"id": key, "ok": False, "until": _prov.exhausted_until(),
                        "reason": "todos los escalones del worker en cooldown: lanzar es morir"})
        except Exception:
            pass
        rec.status = "done"
        rec.ok = False
        rec.result_summary = _sleep_reason
        await _deliver_confirm(rec)          # same one-liner path the confirm-gate uses: speak it and be done
        _SESSIONS.pop(key, None)
        sync_state()
        return

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
            # GUARD DE CONFINAMIENTO REAL (auditoria 2026-07-26, closes the hallazgo "only convencion of prompt"):
            # hook PreToolUse that deniega Read/Write/Edit/Glob/Grep outside of `_wd` — outside of the own workdir (no
            # inside: so the worker no can touch the file of settings that it confina).
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
            # collision, private CLAUDE.md). `read_dirs` declara the dependencia of lectura of the VISIÓN of the
            # browser (the captura arrives by path absoluta outside of the cwd, V2-049) — measured that the CLI already the allows
            # without decirselo, so that es defensa in profundidad, no a requisito.
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
        # PRE-VUELO: ¿esto es a research/seleccion? Entonces is dirige with a brief (amplitud + baremo +
        # form of the entregable) in vez of leave that the worker is autoimponga the criterion minimo. Un dev-worker of
        # code no pasa by here: su address es the repo, no a espacio of candidatos.
        brief = None
        _brief_bg: asyncio.Task | None = None
        if not _dev:
            try:
                # V2-301 — the composer is a REASONING call (15-30 s) and it ran IN SERIES before the spawn:
                # measured across the guitar rounds (2026-08-24), the worker sat «in cola» 20-32 s doing
                # nothing while the composer thought, and then spent its OWN first ~20 s on preamble (mesh
                # PASO 0 + memory reads) — two stretches that overlap perfectly. A short head start keeps the
                # instant paths fully-directed (a resumed/round-2 brief returns without any LLM); past it the
                # worker spawns NOW and the brief arrives as an injected turn, through the same channel every
                # refinement already uses. Fail-open unchanged: a composer that dies just means no injection.
                _brief_bg = asyncio.ensure_future(_compose_brief(req, ctx, trusted, resume))
                _head = float(os.environ.get("ZAELAR_BRIEF_HEAD_START_S", "2.0") or 2.0)
                if _head <= 0:      # kill-switch: serial, exactly as before
                    brief = await _brief_bg
                    _brief_bg = None
                else:
                    try:
                        brief = await asyncio.wait_for(asyncio.shield(_brief_bg), timeout=_head)
                        _brief_bg = None
                    except asyncio.TimeoutError:
                        brief = None            # still thinking → spawn now, inject when ready
            except research.ComposerUnavailable:
                # El compositor no pudo contestar. El fail-open (start without dirigir) es correcto, but NO can
                # arrastrar consigo the mitad of the budget: that esto sea a research no depende of that the
                # compositor este live. Se promociona the kind IGUAL — cuesta DIRECCIÓN, no TIEMPO. Medido in the
                # banco of the 2026-08-13: the compositor tardo >30 s, the task is quedo in `generic` (600 s) and the
                # worker murio a the 704 s with the browser a medias, the same «agoto su time» that the promocion
                # of abajo exists for close.
                brief = None
                _brief_bg = None    # falló DENTRO del head start: ya está manejado aquí, nada que inyectar luego
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
                # EL BRIEF ES LA PRUEBA of that esto es a INVESTIGACIÓN, and with ella is cobra the budget that le
                # corresponde. `loop._kind_budget_default` already reservaba 1200s for `research`… but NADIE asignaba
                # never ese kind: `_classify_kind` only returns web/code/generic, so that toda research that no
                # nombrara Wallapop/Amazon caia in `generic` = 600s. Y ese medio budget CONTRADICE the own
                # brief, that exige reunir ≥40 candidatos and ENTRAR in the ficha of each finalista: 10 minutos no dan
                # for eso, so that the worker moria conminado a «entrega already» with the sheet a medias — es it that le paso
                # al operator the 2026-08-12 two veces («agoto su time»). Only is promociona `generic`: `web`
                # (1200s, and with su reanudacion by `native_sid`) and `code` conservan su path intacta. Y the `spec` of the
                # worker YA esta construido with the kind viejo a purpose — here only cambia it that MIDE the
                # supervisor and it that LEE the operator in the tarjeta («Investigando…», no «Pensando…»).
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
            # V2-289 — the step 1 of the metodo le says that the VISIÓN es su camino PRINCIPAL, and with a escalon that
            # no reads imagenes eso es a orden imposible: the descubre haciendo `Read` of a PNG of medio mega and
            # narrando the failure. Who can ver it resuelve the catalogo of escalones, that es the only that sabe
            # who sirve the session (`providers.worker_sees`, fail-open a SÍ ve).
            prompt = _web_prompt(req, ctx, brief, vision=_worker_sees())
        else:
            prompt = _build_prompt(req, ctx, trusted, brief)
        if resume and (kind == "web" and trusted):
            prompt = ("REANUDAS una gestión que YA empezaste (no arranques de cero): la pestaña sigue donde la "
                      "dejaste y los datos que ya reuniste están en memoria (consúltalos con mem_cli recall). Haz "
                      "`look` PRIMERO para ver dónde te quedaste y CONTINÚA desde ahí hasta terminar.\n\n") + prompt
        if _brief_bg is not None:
            # V2-301 — the compositor continues pensando: the worker starts YA and the address le arrives inyectada.
            prompt += ("\n\nNOTA (dirección en camino): la DIRECCIÓN detallada de esta investigación — criterios "
                       "duros y blandos, amplitud mínima y baremo — se está componiendo y te llegará como "
                       "instrucción nueva en un momento. NO la esperes parado: haz ya los primeros pasos (PASO 0, "
                       "abrir el sitio, la primera búsqueda) y aplícala en cuanto llegue.")
            _attach_brief_followup(_brief_bg, key=key, rec=rec, req=req, kind0=kind)
        try:
            await session.run(prompt)
        except asyncio.CancelledError:
            pass
        except Exception as e:  # noqa: BLE001
            logger.warning(f"dispatch: sesión {key} falló: {e}")
        finally:
            # V2-049 CONTINUIDAD: ¿operation web that quedo SIN complete? → reanudable (manten the tab live).
            _resumable = (kind == "web" and trusted and rec.status != "cancelled" and not rec.ok)
            _prev_count = int((resume or {}).get("count", 0))
            if nav_tid:
                try:
                    await _finalize_web(rec, keep_open=_resumable)
                except Exception:
                    pass
            if _dev:
                # limpieza of the workdir temporary + the settings of the guard (auditoria 2026-07-26, T-07: before no is
                # borraban never — fuga of disco acumulativa with escaladas of code of cluster repetidas).
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
                _leave_resume(rec, nav_tid=nav_tid, resume=resume, req=req, key=key,
                              brief=bool(brief), prev_count=_prev_count)
            try:
                if key.isdigit():
                    escalate.finish(int(key), rec.result_summary if rec.ok else "")
            except Exception:
                pass
            _waiting_user = (rec.waiting_on == "user") or bool(rec.ask)
            # V2-222 — ¿va a CONTINUAR sola? Se calcula here, ANTES of anotar the final, because a session that is
            # resumes sola no ha terminado and anotarla como terminada es it that partia the prompt in two.
            # V2-238 — DOS ESCALADAS PARA UNA MUERTE. `_finish` already relanza the errand when releva of proveedor
            # or compacta the contexto (`escalate_to_slowbrain`), and leaves `ok=False` a purpose for that no haya two
            # entregas. Pero `_resumable` reads exactamente ese `ok=False` and disparaba ADEMÁS the auto-resume of
            # V2-049: two workers sobre the same errand, and —until V2-237— the two reanudando the MISMA session of the
            # CLI, that es como morian a the 400 ms. El testigo already esta pasado: here no is pasa another vez.
            _handoff = str(getattr(rec, "handoff", "") or "")
            _will_resume = bool(_resumable and not _waiting_user
                                and (_prev_count + 1) < _RESUME_CAP and not _handoff)
            # …but the ENCARGO continua in the two ways, so that it that mira «¿esto is ha acabado?» mira esto.
            _continues = bool(_will_resume or _handoff)
            # V2-079: rastro DURABLE of the ejecucion that is va (the record live is purge here and desaparecia). El
            # ledger preserves the historico for the tab «Procesos» of the ChatWall. Best-effort, outside of the hot-path.
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
            # V2-227 ambito C — DESPUÉS of the pop, never before: the sheet reads the record live, so that mientras this
            # session siguiera inside `alive` seguiria diciendo that si. Y no al resume: the errand continua.
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
            # V2-049 AUTO-RESUME: operation web incompleta, SIN question pending, bajo the cap → CONTINÚA sola (the
            # FlashBrain no cesa the task ni waits a empujon of the operator). Con question pending NO: waits the
            # response (that, al arrive como turn, resumes by the same via). Con `ask` the purge of arriba already the
            # quito, by eso leimos _waiting_user ANTES.
            if _will_resume:
                _schedule_auto_resume(req)


def rec_token(rec: "SessionRecord") -> str:
    """Token of auth by-task for the bridges (§v2·D). Se guarda in the own record (atributo dinamico)."""
    tok = getattr(rec, "_token", "")
    if not tok:
        tok = secrets.token_urlsafe(18)
        setattr(rec, "_token", tok)
    return tok


# ── CONFIRMACIÓN PENDIENTE of a task irreversible (V2-126) ─────────────────────────────────────────────
# Moved to `nucleo/dispatch_confirm.py` (F3, 2026-08-23) — the cleanest seam in this file: own registry, own TTL,
# and zero reads of `_SESSIONS`. Re-exported so `dispatch.confirm_line()`, `dispatch.resolve_confirm(...)` and the
# tests that mutate `dispatch._PENDING_CONFIRM` keep working unchanged.
from nucleo.dispatch_confirm import (  # noqa: E402,F401
    _CONFIRM_TTL,
    _EXPIRED_CONFIRM,
    _EXPIRED_MEMORY_S,
    _PENDING_CONFIRM,
    _deliver_confirm,
    _sweep_confirm,
    confirm_line,
    pending_confirm,
    remember_confirm,
    resolve_confirm,
)


# ── compat: llamada directa (tester) ───────────────────────────────────────────────────────────────────────
async def dispatch(task: "Task") -> str:
    """Compat: starts a session and waits su result (for tests/voice/e2e/agent/llamadas directas)."""
    if not (task.request or "").strip():        # una petición vacía es un no-op, no una sesión
        return ""
    key = str(task.id)
    _SESSIONS[key] = SessionRecord(task_id=key, goal=(task.request or "").strip()[:200],
                                   kind=(task.kind or "generic"))
    await _run_session(task)
    return "(tarea despachada)"


# ── consumo of escalados of the bus (FlashBrain → workers) ────────────────────────────────────────────────────
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
            # V2-092: with the agent PARADO (⏻) NO is opens work new. Los workers that already estaban is congelan and
            # continuan al start (pause_all/resume_all), but start uno DESDE CERO sobre a agent parado es
            # it contrario of parar. Se rechaza VISIBLE (evento `task/blocked`), never in silencio: a escalada that
            # desaparece without rastro es the clase of failure that cuesta a session of diagnostico.
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
            # DEDUP in the FUENTE DE VERDAD (§session 2026-07-15): if already there is a session live atendiendo this same
            # request, NO abrimos a 2º worker (the bug of the two «creando a widget…»). Se INYECTA como
            # refinamiento (the generador of widgets, build atomico, it ignora with gracia; a worker live it aprovecha).
            dup, _ev = dedup_scan(request, kind if kind != "generic" else _classify_kind(request))
            # `by` now comes from the deciding loop instead of being assumed here: a same-widget hit used to
            # be filed as «containment», which is a number it never computed.
            _dup_by = _ev.get("by") or ""
            _model = "skipped"          # the second half only runs with something live to compare against
            if not dup:
                # SEGUNDA MITAD DEL DEDUP, off-loop. `find_duplicate` responds «¿es a reformulacion of it
                # same?» and no can responder «¿es esto a errand siquiera?» — ver `about_a_live_errand`.
                # Only corre with something live, so that the first errand of a conversacion no it paga; and va in
                # a hilo because `chat_sync` es sincrono and this bucle es the of the servidor.
                _live = _live_errands()
                if _live:
                    try:
                        dup = await asyncio.to_thread(about_a_live_errand, request, _live)
                        _dup_by = "model" if dup else _dup_by
                        _model = "about" if dup else "separate"
                    except Exception as e:  # noqa: BLE001
                        dup = ""
                        # A model half that CRASHED used to be indistinguishable from one that answered
                        # «separate» — the same confusion as the mute miss, one layer in. Recorded, not
                        # changed: the fail-open stays, an unreachable judge must never block an errand.
                        _model = f"error:{type(e).__name__}"
            if dup:
                try:
                    from voice.observer import emit
                    # `by` separa the DOS mitades of the dedup, and without el no is can medir by separado:
                    # `containment` es a reformulacion of the same errand, `model` es a turn that no era a
                    # errand (a question by how va). Contarlas juntas esconde which of the two falla.
                    emit("task", "dedup", role="system", text=request[:120],
                         extra={"id": dup, "dropped_id": key, "by": _dup_by,
                                "reason": ("no es un encargo nuevo: va sobre una tarea viva"
                                           if _dup_by == "model" else
                                           "escalada duplicada de una tarea viva")})
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
            # THE NEGATIVE DECISION, SAID OUT LOUD (V2-507). Only the hit was emitted, so «the dedup did not
            # fire» could not be told from «there was nothing live to fire against» — opposite fixes, and the
            # round of 20260830-114302 spent a full replay of the event log without settling it. `live` is the
            # one that decides: 0 means nobody was there to match, and no yardstick can be blamed for that.
            try:
                from voice.observer import emit
                emit("task", "dedup_miss", role="system", text=request[:120],
                     extra={"id": key, "live": _ev.get("live", 0), "best": _ev.get("best", 0.0),
                            "against": _ev.get("against", ""), "bar": _ev.get("bar", 0.0), "model": _model,
                            # V2-570 — a fresh fast-pass delivery is named HERE too: «nothing live» with a
                            # just-delivered hunt on screen was how two boxes looked like a clean miss.
                            "listing_recent": [r["id"] for r in _ended.recent_listing_deliveries()][:3],
                            "reason": ("encargo NUEVO: no había ninguna tarea viva contra la que comparar"
                                       if not _ev.get("live") else
                                       "encargo NUEVO: no casa con ninguna tarea viva")})
            except Exception:
                pass
            # V2-566/V2-570 — A FOLLOW-UP IS NOT A NEW ERRAND, and a follow-up of a DELIVERED listing fast
            # pass does not spawn a parallel worker. Both decisions live in `nucleo/errand_continuity.py`
            # (extracted: dispatch sat one line under its ratchet ceiling): the escalation may come back with
            # an inherited sheet, or redirected entirely to a refined fast re-run in the same box — in which
            # case there is no session to open and the module already owns the errand's next step.
            ctx, _redirected = _continuity.inherit_and_maybe_rerun(
                request, kind if kind != "generic" else _classify_kind(request), ctx, key)
            if _redirected:
                _close_escalated_flow(ctx, ok=True, status="linear_rerun")
                continue
            # V2-049 CONTINUIDAD: without session live that casar, ¿there is a operation web INCOMPLETA reciente that ESTA
            # request resumes? (nudge «continues with the ITV», or the operator aportando the dato that was missing). Reanuda esa
            # same tab + razonamiento in vez of start of cero.
            _k = kind if kind != "generic" else _classify_kind(request)
            if _k == "web":
                # take=True: the reanudacion is CONSUME al entregarla. Sin eso, two escaladas of the same
                # request is llevan the same id of session of the CLI and the second dies in the arranque.
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
                                # La GENERACIÓN of relevo viaja with the cadena. Sin esto the cap of `_finish` no
                                # exists: each relevo estrena record and su contador vuelve a cero.
                                relay_gen=int(ctx.get("relay_gen", 0) or 0),
                                # …and the SHEET with it, for the same reason: a relay continues the errand, so
                                # it keeps writing where the operator is already looking instead of opening a
                                # second box beside it.
                                sheet=str(ctx.get("sheet", "") or ""),
                                trace_id=str(ctx.get("trace", "") or ""))   # V2-044: encadena a la frase origen
            # V2-227 — the SUPERFICIE is sella here, that es the only point by the that pasan TODAS the puertas of
            # entrada al dispatcher (the cerebro with su `surface`, the auto-resume, the confirm-gate, the cluster, the
            # Susurro). Lo that declaro the cerebro manda; if no declaro nothing —or said something that no es of the
            # vocabulario— is deriva of the kind. Sellar tarde significaria open the sheet when already there is response,
            # that es exactamente it that this cambio exists for no do.
            surfaces.set_once(rec, ctx.get("surface"))
            # …and if esa superficie es the sheet, is ABRE YA, empty and with the tab of proceso. Aqui, and no in the
            # entrega, es donde the operator leaves of mirar a pantalla in blanco.
            if surfaces.opens_sheet(getattr(rec, "surface", "")):
                _sheet_open(rec)
            _SESSIONS[key] = rec
            _name_errand(rec)          # V2-530 — asynchronous; the sheet is already open under its brief

            rec.task = asyncio.create_task(_run_session(task), name=f"worker-session-{key}")
            sync_state()
    finally:
        sub.close()
        logger.info("dispatch: listener de escalados detenido")


# ── ciclo of vida (lifespan, BRAIN=nucleo) ────────────────────────────────────────────────────────────────
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
