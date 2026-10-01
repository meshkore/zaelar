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

from nucleo import dev_worker_guard, protected_core, research
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


def _tools_for(kind: str, trusted: bool, may_write: bool = False) -> list[str] | None:
    """Allowlist of worker tools by type. An untrusted turn never reaches here (deny_tools in the spec).

    NUNCA a `"Bash"` pelado (auditoria 2026-07-14): the Bash of the worker queda acotado a the CLIs bridge
    (`_BRIDGE_TOOLS` of `claude_session`, that is anaden solos) — a Bash abierto permitiria a a worker
    inducido by contenido web hostil open the SQLite in paralelo (`sqlite3 memory/_data/zaelar.db …`) and
    romper the ESCRITOR ÚNICO. Es the invariante documentado in CLAUDE.md («Bash SOLO a esos CLIs»)."""
    if not trusted:
        return []
    # V2-655: `Write`/`Edit` los da `may_write`, no el kind. Un `code` que no es el generador de widgets
    # —la rama `architect`— pedía escritura sobre el motor y la recibía por llamarse igual.
    if kind == "code" and may_write:
        return ["Read", "Write", "Edit", "WebSearch", "WebFetch"]
    if kind == "code":                      # V2-655 — a `code` errand that is not the widget generator
        return ["Read", "WebSearch", "WebFetch"]   # works on the ENGINE: it never writes
    # `Write` for every other trusted errand: the prompt hands every bridge payload through a relative file it
    # writes itself (see `claude_session._DEFAULT_TOOLS`, 2026-08-28). This list REPLACES that default, and it
    # never had it — demo pass 2026-09-28: «No such tool available: Write», a `printf` blocked over «$400», and a
    # monitor errand whose verified results never reached the sheet.
    return ["Read", "Write", "WebSearch", "WebFetch"]


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
        return max(1, int(_v2.get("code_agent").get("max_parallel", 2)))
    except Exception:
        return 2          # V2-771 — two at a time, the rest queued (see config/v2.py §code_agent)


_sem: "asyncio.Semaphore | None" = None


def _pool():
    global _sem
    if _sem is None:
        _sem = asyncio.Semaphore(_max_parallel())
    return _sem


# ── proyeccion for ESTADO / prompt / /api/tasks (the sincroniza the LOOP ~1 Hz, §v2·C) ───────────────────────
def unclosed_uids() -> set[str]:
    """The durable ids of every session whose run has not reached `tasks.closed()` yet — LIVE or not.

    A session is `done` the moment its result exists, but it stays in `_SESSIONS` while `_finish` waits for a
    moment to SPEAK the delivery, and only its `finally` closes the row. The reconciler read `active_sessions()`
    (live states only) and settled that row as «failed — nobody was carrying it» in the gap; the FlashBrain then
    told the operator the finished search had failed and ran it again (demo pass 2026-09-28, S1)."""
    return {str(getattr(r, "uid", "") or "") for r in list(_SESSIONS.values())} - {""}


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
    widget… in curso». Lo TERMINADO is read from the `tasks` table (`nucleo/tasks.py::board`), that es su site."""
    now = time.time()
    out = []
    for r in _SESSIONS.values():
        if r.status not in LIVE_SESSION_STATES:
            continue
        out.append({
            "id": r.task_id, "kind": r.kind, "backend": r.backend, "goal": r.goal[:120],
            # V2-728 — the DURABLE id of the commission this session serves. `id` above is the per-process
            # session counter and is what every existing consumer keys on, so it stays; this is what joins
            # the hot detail to the row in `tasks`, and a relay carries the same one as its parent.
            "uid": str(getattr(r, "uid", "") or ""),
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
            # V2-776 D1 — how long since the worker last reported ITSELF (`hbnote`), and when it last showed any
            # sign of life. The pulse writes both into the durable row and enforces the first.
            "unreported_s": int(now - (getattr(r, "reported_at", 0.0) or r.started)),
            "reported": bool(getattr(r, "reported_at", 0.0)),
            "heartbeat_at": int(r.last_event_at or r.started),
            "reported_at": int(getattr(r, "reported_at", 0.0) or 0),
        })
    return out


def has_active() -> bool:
    return any(r.status in LIVE_SESSION_STATES for r in _SESSIONS.values())


def sheets_have_live_work(card_ids) -> bool:
    """Is a LIVE errand delivering into one of these results cards (`results` or `results::<sheet>`)?

    Closing a sheet orphans only the errand that writes INTO it. `has_active()` answered for every worker, so
    an unrelated live errand (a Telegram follow-up watching for a reply) made «Close the results» fall through
    to the model, which then did something else (demo pass 2026-09-27, S4)."""
    live = [r for r in _SESSIONS.values() if r.status in LIVE_SESSION_STATES]
    for cid in card_ids or ():
        sheet = str(cid or "").split("::", 1)[1] if "::" in str(cid or "") else ""
        for r in live:
            own = sheet_of(r)
            if sheet and own == sheet:
                return True
            if not sheet and not own and surfaces.opens_sheet(getattr(r, "surface", "")):
                return True
    return False


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
from nucleo import docsheet as _docsheet, sheets as _sheets


def _sheet_sessions() -> list:
    return _sheets.sheet_sessions(_SESSIONS.values(), LIVE_SESSION_STATES)


def sheet_for_nav_task(nav_task: str) -> str:
    """La sheet donde entregar it that ESTA tab encuentre, abriendola if su errand aun no has (V2-290)."""
    return _sheets.sheet_for_delivery(nav_task, _SESSIONS.values(), LIVE_SESSION_STATES)


def sheet_progress(sheet: str = "") -> dict:
    return _sheets.sheet_progress(sheet, _SESSIONS.values(), LIVE_SESSION_STATES)


def task_progress(task: str = "") -> dict:
    """The live narrative of ONE errand by task_id — the documento sheet's process view (V2-644)."""
    return _sheets.task_progress(task, _SESSIONS.values(), LIVE_SESSION_STATES)


def sheet_harvest(sheet: str = "") -> dict:
    """Los NÚMEROS of the sheet (V2-296). Cuerpo in `nucleo/sheets.py`; here only is le pasa the record live."""
    return _sheets.sheet_harvest(sheet, _SESSIONS.values(), LIVE_SESSION_STATES)


def sheet_browser(sheet: str = "") -> dict:
    """El NAVEGADOR del encargo de esta hoja (V2-571). Cuerpo en `nucleo/sheets.py`; aquí solo el registro vivo."""
    return _sheets.sheet_browser(sheet, _SESSIONS.values(), LIVE_SESSION_STATES)


def record_phase(tid, phase: str) -> bool:
    """Apunta a linea in the diario of PROCESO of `tid`. El body lives in `nucleo/sheets.py` (V2-281):
    here only is resuelve the record, that es it only that this module has and aquel no."""
    return _sheets.record_phase(_SESSIONS.get(str(tid)), phase, PHASES_KEPT)

# V2-059 — lo que el worker REPORTA de sí mismo (fase, plan, progreso, amplitud) vive junto en
# `workers/reports.py`. Re-exportado: `agent_api`, `agentes/worker` y 4 tests llaman por aquí.
from nucleo.workers.reports import (  # noqa: E402,F401 — re-export
    _progress_pct, session_alive, session_considered, session_phase, session_plan, session_progress,
    session_reported)


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


_seed_research_criteria = research.seed_criteria   # V2-644: body moved to research.py (ratchet)


# La address of this motor lives in `nucleo/engine_url.py` (V2-296): funcion pura of two env vars, without state
# of the gestor of sessions. Se re-exporta because es a mudanza, no a cambio of interfaz.
from nucleo.engine_url import _own_base_url  # noqa: E402,F401 — re-export


def _task_row(how: str, rec, **kw) -> None:
    """V2-776 D1 — the durable row of an errand that ended BEFORE its worker ran. Each early return of
    `_run_session` used to skip `tasks.closed()` (only the `finally` below reaches it), so the row stayed
    `pending` forever. Best-effort: a store that failed must not change how the errand ended."""
    try:
        from nucleo import tasks as _tasks
        getattr(_tasks, how)(rec, **kw)
    except Exception:  # noqa: BLE001
        logger.debug(f"dispatch: task row {how} failed", exc_info=True)


async def _run_session(task: 'Task'):
    """V2-778 F1 — the body lives in `nucleo/dispatch_session.py`; this delegate keeps the name (and its patches)."""
    return await _dispatch_session._run_session(task)


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
    absorb_refinement,
    confirm_line,
    parked_errands,
    pending_confirm,
    remember_code_change,
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


# V2-778 F1-11 — the escalation listener lives in `nucleo/dispatch_listener.py`; this name delegates to it, so
# `dispatch.start()`, every caller and every test keep calling `dispatch.run_listener`. A module import (not a
# `from … import`) keeps the two-way reference safe whichever module is imported first.
from nucleo import dispatch_listener as _listener  # noqa: E402


def run_listener(*args, **kwargs):
    return _listener.run_listener(*args, **kwargs)
from nucleo import dispatch_session as _dispatch_session  # noqa: E402 — V2-778 F1, reads this module back


# V2-778 F1 — moved to `dispatch_prepare.py`, imported back under their names (that module reads this one).
from .dispatch_prepare import (  # noqa: E402,F401
    _compose_brief, _TITLE_BG_TASKS, _name_errand, _BRIEF_BG_TASKS, _attach_brief_followup, _FORCE_NEW_RE,
    _COEXIST_RE, _prepare_web, _finalize_web, _compose_context)
