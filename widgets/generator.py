#
# Widget generator — zaelar's ONE local code agent. The brain (Hermes) asks for a NEW widget (or a change to an
# existing one) by voice; zaelar delegates an ATOMIC task to a HEADLESS Claude Code instance (`claude -p`) that
# is born, does exactly that task, deploys into widgets/<id>/, and exits. No external context, no task queue, no
# history — one agent, one atomic task. (Pattern learned from MeshKore's daemon runner; we depend on NONE of it.)
#
# ISOLATION: this module + its two endpoints are the only place that spawns an agent. It lives entirely inside the
# widget circuit and never touches the voice core. Safety: file tools only (Write/Edit/Read — NO Bash), scoped to
# the zaelar dir, hard timeout, single-agent lock, and the result is VALIDATED before it's trusted in the catalog.
#
import glob
import json
import os
import re
import shutil
import subprocess
import threading

from loguru import logger

from nucleo import workspace as _workspace

HERE = os.path.dirname(os.path.abspath(__file__))          # …/zaelar/widgets
ZAELAR = os.path.dirname(HERE)                             # …/zaelar  (the agent's cwd — widget CODE
                                                             # generation stays repo-relative; see the
                                                             # Fase 3 plan's M10, deliberately out of
                                                             # scope for the M0 workspace-root refactor)
GEN_TIMEOUT = float(os.getenv("WIDGET_GEN_TIMEOUT", "240"))
GEN_MODEL = os.getenv("WIDGET_GEN_MODEL", "")              # optional override, e.g. "sonnet"

_RESERVED = {"generator", "server_api", "runtime", "store", "brief", "_data", "__pycache__"}
_lock = threading.Lock()                                   # ONE agent at a time (the "solo 1 agente" rule)

# In-flight generation journal — a server restart kills the headless agent mid-build with no trace. Each job is
# recorded here when it starts and removed when it ends, so on boot resume_interrupted_generations() (server_api)
# can relaunch creates / report broken modifies instead of leaving the operator with a silent "hecho" that never
# landed. NOT a widget store: it's the generator's own journal, hence the underscore name no safe_id() can take.
# Same `<workspace>/widgets/_data` root as `store.DATA_DIR` — unset ZAELAR_WORKSPACE = byte-identical
# to the old `HERE/_data` path (workspace.root() falls back to the engine repo root).
JOBS_FILE = os.path.join(str(_workspace.root()), "widgets", "_data", "_jobs.json")
_jobs_lock = threading.Lock()


def _jobs_read() -> dict:
    try:
        return json.load(open(JOBS_FILE, encoding="utf-8"))
    except Exception:
        return {}


def _jobs_write(jobs: dict) -> None:
    try:
        os.makedirs(os.path.dirname(JOBS_FILE), exist_ok=True)
        tmp = JOBS_FILE + ".tmp"
        json.dump(jobs, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        os.replace(tmp, JOBS_FILE)
    except Exception as e:
        logger.warning(f"widget-agent: could not persist jobs journal: {e}")


def _job_start(kind: str, wid: str, payload: dict) -> None:
    import time
    with _jobs_lock:
        jobs = _jobs_read()
        jobs[wid] = {"id": wid, "kind": kind, "payload": payload, "started_at": time.time()}
        _jobs_write(jobs)


def _job_end(wid: str) -> None:
    with _jobs_lock:
        jobs = _jobs_read()
        if jobs.pop(wid, None) is not None:
            _jobs_write(jobs)


def take_pending_jobs() -> list[dict]:
    """Drain the journal (boot-time): return jobs a previous process left in flight and clear the file."""
    with _jobs_lock:
        jobs = _jobs_read()
        if jobs:
            _jobs_write({})
        return list(jobs.values())


def _find_claude() -> str:
    """Locate the Claude Code CLI robustly — the server's PATH (launched from a venv) often lacks nvm's bin where
    `claude` actually lives. Env override → PATH → common install locations. (Same heuristic as MeshKore's daemon.)"""
    cand = os.getenv("CLAUDE_BIN")
    if cand and os.path.exists(os.path.expanduser(cand)):
        return os.path.expanduser(cand)
    found = shutil.which("claude")
    if found:
        return found
    for pat in ("~/.nvm/versions/node/*/bin/claude", "/opt/homebrew/bin/claude",
                "/usr/local/bin/claude", "~/.local/bin/claude"):
        hits = glob.glob(os.path.expanduser(pat))
        if hits:
            return sorted(hits)[-1]
    return ""


def safe_id(raw: str) -> str:
    """A filesystem/catalog-safe widget id: lowercase, [a-z0-9_-], trimmed."""
    s = re.sub(r"[^a-z0-9_-]+", "-", (raw or "").strip().lower()).strip("-_")
    return s[:40]


# Palabras de relleno que NO deben entrar en el id de un widget nuevo (crea/un/widget/de/que/para/el…): sin
# esto, derivar el id de la petición entera daba ids-basura tipo `implementar-en-el-widget-youtube-la-capa`
# (sesión 2026-07-15). Bilingüe es/en. El id se queda en las 3 primeras palabras de CONTENIDO.
_ID_FILLER = {
    "crea", "crear", "cree", "creame", "haz", "hazme", "hacer", "genera", "generar", "generame", "monta", "montame",
    "construye", "disena", "nuevo", "nueva", "widget", "tarjeta", "panel", "cuadro", "implementar", "implementa",
    "quiero", "necesito", "ponme", "dame", "un", "una", "el", "la", "los", "las", "de", "del", "que", "para", "por",
    "con", "en", "y", "o", "a", "al", "me", "mi", "su", "lo", "capacidad", "capaz", "poder", "pueda",
    "make", "create", "build", "new", "a", "an", "the", "of", "to", "for", "with", "that", "widget", "card",
}


def _concise_id(spec: str) -> str:
    """Deriva un id CORTO y con sentido de la petición: normaliza acentos, quita relleno y se queda con las 3
    primeras palabras de contenido (p.ej. 'crea un widget del tiempo en Soria' → 'tiempo-soria'). Fallback al
    slug crudo si no queda nada. Evita ids-basura derivados de la instrucción entera."""
    import unicodedata
    n = "".join(c for c in unicodedata.normalize("NFKD", (spec or "")) if not unicodedata.combining(c)).lower()
    toks = [t for t in re.split(r"[^a-z0-9]+", n) if t and t not in _ID_FILLER and len(t) > 1]
    return safe_id("-".join(toks[:3])) or safe_id(spec)


def exists(wid: str) -> bool:
    return bool(wid) and os.path.isfile(os.path.join(HERE, wid, "manifest.json"))


_CONTRACT = """A zaelar widget is a folder widgets/<id>/ with:
- manifest.json — {{"id","version":"0.1.0","title","description","whenToUse","keywords":[…],"entry":"widget.js"}}; add "transient":true ONLY for a momentary/process view (not for something that stays on screen). If data.py has apply_action, this is a HARD REQUIREMENT (the validation gate enforces it): (1) add "actions": {{"name": {{"desc":"one line","payload":{{"field":"type/example"}}}}, …}} with EXACTLY ONE entry per action apply_action accepts — no more, no less. This is the widget's DATA API: it's how the fast voice brain (FlashBrain) drives your widget's data via a [[widget.data:id]] tag, and it runs EVERY declared action directly and instantly (a data mutation is NEVER escalated to a code agent). An action apply_action handles but you don't declare here is INVISIBLE to the brain; an action you declare but apply_action doesn't handle is a dead entry — the gate REJECTS either mismatch. (2) Mark an action "confirm": true ONLY if it is IRREVERSIBLE (pay, send, publish, delete-all, empty) — the brain still does it itself but asks the operator for a yes/no first (never mark reversible edits like add/done/snooze/hide confirm). (3) add a "usage" one-liner at the manifest top level: a concise guide telling the brain HOW to drive this widget (which action for which intent, what each payload needs). The legacy "safe": true|false flag still parses but is deprecated — do NOT emit it in new widgets; use "confirm" for the irreversible ones and leave the rest bare.
- widget.js — an ES module exporting `export function render(el, data, ctx) {{ … }}`. SELF-CONTAINED: no external libraries, no CDN, no network from JS. Inject its own <style> once (guard by a unique id). Build DOM with textContent for ANY web/third-party/user text (never innerHTML for untrusted data — XSS). ctx = {{ action(name,payload), close(), top(), running }} (`ctx.running` is false when the operator has STOPPED the agent — see "DOES IT PRODUCE SOMETHING?" below). zaelar has BOTH a dark theme (default) and a light theme, user-toggleable live — style with the CSS variables `var(--hb-bg,#fff)`, `var(--hb-bg-soft,#fbfdff)`, `var(--hb-ink,#0d1622)`, `var(--hb-muted,#5b6b82)`, `var(--hb-muted-2,#9aa7b8)`, `var(--hb-line,#eef1f6)`, `var(--hb-accent,#3D6FE0)`, `var(--hb-accent2,#16B8A6)`, `var(--hb-risk,#e5484d)`, `var(--hb-neutral,#c2ccda)` — NEVER a hardcoded hex for anything theme-dependent, so the widget re-paints instantly when the user switches theme (see widgets/AGENTS.md §Visual style for the full contract). Rounded cards, system font, ~13-15px text. Prefer the global `hbk-*` helper classes (`hbk-card`, `hbk-hd`, `hbk-sub`, `hbk-muted`, `hbk-empty`, `hbk-chip`, `hbk-btn` — app/styles.css §WIDGET KIT) over hand-rolled CSS for these common shapes; write custom CSS for whatever is actually specific to this widget. PICK CLASS NAMES SPECIFIC TO THIS WIDGET — a short generic one (`.conn`, `.item`, `.row`, `.card`, `.icon`) may ALREADY be a BARE (unscoped) rule in the app-wide `frontend/app/styles.css`, and CSS applies both rules to any element with that class regardless of your own wrapper scoping; the validation gate rejects this, but naming it right the first time avoids a wasted round-trip.
- data.py — `def view_data(q: str = "") -> dict:` returning the widget's data. Server-side, STDLIB ONLY (urllib for any live fetch, 6s timeout, desktop User-Agent header). Never raise: on error return a dict with an "error" or a friendly empty state. Optional `def apply_action(action, payload) -> dict:` for mutations — called both by the widget's own UI (ctx.action) AND by the FlashBrain on the operator's behalf (the `widget_data` tool → same apply_action, per the "actions" declared in manifest.json above). Call `store.save(...)` at the end of any action that changes persisted data — that's what tells the canvas to re-render (no polling: see COMMUNICATION model below). If any action targets an EXISTING item by an id field (taskId/projectId/…), ALSO add `def ref_index() -> list[dict]:` returning the LIVE items as `[{{"id","label","field"[,"hint"]}}]` (field = the payload key that identifies it) so the brain can reference them by natural language and never guess an id (V2-026); and normalise any spoken relative dates/times ("mañana"/"a las cinco") inside data.py so the value lands correctly.
- BACKGROUND EXECUTION (core consideration for EVERY widget — decide this deliberately): does this widget's data change ON ITS OWN, off-screen (a feed, an inbox, a countdown, anything the operator may ask about by voice without opening the card)? If NO (most widgets — a search box, a chart computed on read), leave it foreground-only: `view_data()` runs on demand when shown, nothing else. If YES, it must keep working while hidden — declare a cycle in manifest.json: `"background": {{"every": "1m"}}` (also accepts a bare string `"1m"`/`"30s"`/`"1h"` or a number of seconds; MINIMUM 1s; a fast feed 1m, weather 1h). Then add `def tick() -> None:` to data.py: the background scheduler calls it every cycle, OFF the hot path — fetch/refresh, `store.save(...)` ONLY if data changed (idempotent saves don't re-render), and WRITE anything the operator might ask about into central memory so a voice query answers with fresh data even if the card was never opened — `from memory import api as memory; memory.write(text, kind=..., slot="<widget>:<key>")` (use a `slot` so it SUPERSEDES instead of piling up), or `memory.ingest_message(source, entity, text)` for incoming items from a source. `tick()` must be cheap, stdlib, and never raise (a failing tick is isolated, but keep it clean). NOTE: a `backed` widget (its own owner process) is already background by nature and self-schedules — it does NOT need `tick()` unless it opts into periodic `tick` commands via `background`. `widgets/background.py` is the scheduler; `mensajeria` is the reference for "off-screen → memory → voice".
- DOES IT PRODUCE SOMETHING? (also decide this deliberately, V2-092) "Produce" = it keeps doing something after the operator stops looking: playing audio/video, recording, running a live process. Most widgets do NOT (a chart, a list, a form) — skip this. If yours DOES, you MUST declare it in manifest.json, or it will keep going with the agent STOPPED (a real shipped bug: with the agent stopped a video kept playing, restarted itself on page reload, and played on top of the music player): `"runtime": {{"output":"audio", "produce":["load","play","restart","unmute"], "suspend":"pause", "active_when":{{"videoId":true,"paused":false}}}}` — `output` = the exclusive channel it takes (omit if it competes for none), `produce` = the actions that START it producing, `suspend` = the action that makes it STOP, `active_when` = how "it is producing" reads from view_data() (a LIST of conditions if it can produce more than one way — AND inside one, OR between them; dotted paths like `yt.paused` work). `suspend` and every `produce` entry MUST be real declared actions. With that, `widgets/producers.py` gives you the global stop, single-owner-of-the-speaker, and a server-side refusal of your `produce` actions while the agent is stopped, for free. In widget.js, ALSO gate on `ctx.running === false` (agent stopped): never autoplay on mount, and for an <iframe> keep `autoplay=0` out of the `src` itself (a pause sent afterwards arrives late and the first instant is audible).
- PERSISTENCE (only if the widget must keep state across restarts): use the SHARED per-widget store — `from .. import store`, then `db = store.load("{wid}", {{}})` and `store.save("{wid}", db)` (atomic JSON at widgets/_data/{wid}/state.json — YOUR OWN data directory, separate from this code folder so [[modify]]/regeneration never wipes it). Need more than one JSON (media, attachments)? `store.data_dir("{wid}")` gives you that same directory to write into — still never write anywhere else. Do NOT invent your own file writing. To READ system data the widget only observes (e.g. logs) read from .meshkore/logs/ with stdlib. Prefer computing on read; persist only what can't be derived.
- COMMUNICATION model — widgets are ISOLATED and DUMB. They do NOT talk to each other, hold no long-lived connections, run no background threads/websockets, and never poll their own data (widget.js can't fetch anyway — see below; the host re-renders you automatically the instant your data.py calls store.save(), pushed over SSE). The brain (Hermes) is the ONLY orchestrator: it reads one widget's data and hands data to another via its tag protocol, and it's the only brain allowed to mutate your data on the operator's behalf. Your data.py may do a simple stdlib fetch, nothing more. Do NOT add cross-widget calls or an event bus.
- __init__.py — empty file.
Read widgets/search/{{manifest.json,widget.js,data.py}} and widgets/agenda/widget.js FIRST to learn the exact contract + style.
ALSO read **widgets/AGENTS.md** (the house style + hard rules — palette, layout, keywords, memory) and FOLLOW it."""

_CREATE_PROMPT = (
    "You are extending the zaelar voice-assistant WIDGET CATALOG.\n" + _CONTRACT +
    "\n\nCREATE a new widget with id \"{wid}\" that does:\n{spec}\n\n"
    "Write ALL of widgets/{wid}/manifest.json, widgets/{wid}/widget.js, widgets/{wid}/data.py and "
    "widgets/{wid}/__init__.py. Small, robust, self-contained. ALSO create widgets/{wid}/notes.md with a first "
    "bullet recording what this widget should do + any style/format constraint the user stated (so future edits "
    "don't regress it). Do NOT modify any other file. Do NOT run shell commands. Reply with just: DONE {wid}."
)

_MODIFY_PROMPT = (
    "You are editing an EXISTING, WORKING zaelar widget. Read widgets/{wid}/ first (manifest.json, widget.js, "
    "data.py, AND widgets/{wid}/notes.md — the log of past decisions; NEVER undo/regress anything recorded there).\n"
    + _CONTRACT +
    "\n\nMake ONLY this change, as a SURGICAL edit:\n{change}\n\n"
    "After editing, APPEND one terse bullet to widgets/{wid}/notes.md recording this change + any constraint "
    "stated (what the user wants / rejected), so the next session keeps the same direction.\n"
    "CRITICAL: make the SMALLEST possible edit. PRESERVE everything else — the existing CSS/styling, the layout, "
    "the data handling, the polish. Do NOT rewrite the widget from scratch, do NOT drop styles or features, do "
    "NOT regress the design. The result must look as polished as before, just with the requested change applied. "
    "Keep the same id \"{wid}\" and the contract (export function render; self-contained; textContent for "
    "untrusted data). Only touch files INSIDE widgets/{wid}/. Do NOT run shell commands. Reply with just: DONE {wid}."
)


# V2-038: procesos de generación MATABLES por token (= task_id del Brain Worker). Un `stop_worker`/`cancel_session`
# sobre una tarea `code` mata el subproceso `claude` del generador (que corre en un HILO to_thread NO cancelable).
_PROCS: dict = {}          # token -> subprocess.Popen
_PROCS_LOCK = threading.Lock()


def kill(token: str) -> bool:
    """Mata el subproceso de generación asociado a `token` (con cortesía: terminate → kill). Idempotente."""
    with _PROCS_LOCK:
        p = _PROCS.get(str(token))
    if p is None:
        return False
    try:
        if p.poll() is None:
            p.terminate()
            try:
                p.wait(timeout=float(os.getenv("GEN_TERM_GRACE_S", "3")))
            except Exception:
                p.kill()
    except Exception:
        pass
    return True


def kill_all() -> int:
    with _PROCS_LOCK:
        tokens = list(_PROCS.keys())
    return sum(1 for t in tokens if kill(t))


def _run_agent(prompt: str, token: str = "") -> tuple[bool, str]:
    """Spawn ONE atomic headless Claude Code agent. Prompt via STDIN (claude 2.1.x truncates large positional
    prompts — MeshKore hit this). File tools only, cwd = zaelar, hard timeout. MATABLE por `token` (V2-038):
    Popen + communicate registrado en _PROCS → `kill(token)` lo termina desde otro hilo. Returns (ran, error)."""
    claude = _find_claude()
    if not claude:
        return False, "Claude Code CLI not found (set CLAUDE_BIN)"
    cmd = [claude, "-p", "--allowedTools", "Write Edit Read",
           "--permission-mode", "acceptEdits", "--output-format", "json"]
    env = dict(os.environ)
    env["PATH"] = os.path.dirname(claude) + os.pathsep + env.get("PATH", "")
    # Enruta la generación de widgets por el endpoint externo de §code_agent (Z.AI GLM) si está configurado, para
    # que este agente headless TAMPOCO consuma tokens de la licencia Claude Teams (operador 2026-07-31). Helper
    # ÚNICO compartido con los brain workers. Si se enruta y no hay override explícito, usa el modelo de §code_agent.
    model = GEN_MODEL
    base_url = ""       # endpoint realmente usado (para el metering de Energy más abajo — "" = licencia local)
    try:
        from config import v2 as _v2
        _ext = _v2.external_worker_env()
        if _ext:
            env.update(_ext)
            env.pop("ANTHROPIC_API_KEY", None)
            base_url = _ext.get("ANTHROPIC_BASE_URL", "")
            if not model:
                model = _v2.code_agent_model("code")
    except Exception:
        pass
    if model:
        cmd += ["--model", model]
    try:
        p = subprocess.Popen(cmd, cwd=ZAELAR, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, text=True, env=env)
    except Exception as e:
        return False, f"agent failed to start: {e}"
    if token:
        with _PROCS_LOCK:
            _PROCS[str(token)] = p
    try:
        stdout, stderr = p.communicate(input=prompt, timeout=GEN_TIMEOUT)
    except subprocess.TimeoutExpired:
        try:
            p.kill(); p.communicate()
        except Exception:
            pass
        return False, "the agent timed out"
    except Exception as e:
        return False, f"agent failed: {e}"
    finally:
        if token:
            with _PROCS_LOCK:
                _PROCS.pop(str(token), None)
    if p.returncode not in (0, None):
        logger.warning(f"widget-agent: claude exited {p.returncode}: {(stderr or '')[:300]}")
        # un proceso MATADO (terminate/kill) devuelve rc≠0 → lo tratamos como 'no completó' para que _discard limpie.
        if p.returncode and p.returncode < 0:
            return False, "generation cancelled"
    # Energy metering (2026-08-05, cierra el gap anotado en INI-019 addenda): `--output-format json` YA trae
    # `usage`/`model` (mismo shape que el "result" de stream-json que sí se metraba en los Brain Workers
    # interactivos, ver nucleo/workers/session.py) — antes se tiraba el stdout entero sin leerlo, así que la
    # generación/modificación de widgets nunca descontaba Energy pese a costar tokens reales. Best-effort: un
    # stdout no-JSON o sin `usage` no debe romper la generación, que ya terminó bien.
    if p.returncode == 0 and stdout:
        try:
            import json as _json
            obj = _json.loads(stdout)
            usage = obj.get("usage") or {}
            if usage:
                from nucleo import energy_meter as _energy
                _energy.report_worker_usage(
                    base_url=base_url,
                    model=obj.get("model") or model,
                    prompt_tokens=usage.get("input_tokens"),
                    completion_tokens=usage.get("output_tokens"),
                )
        except Exception:
            pass
    return True, ""


def generate_widget(spec: str, wid: str = "", title: str = "", token: str = "") -> dict:
    """Build a NEW widget folder with the atomic agent. Returns {ok, id, existed?, error?}. `token` (V2-038) =
    id del Brain Worker → el subproceso queda MATABLE con generator.kill(token)."""
    wid = safe_id(wid) or safe_id(title) or _concise_id(spec)
    if not wid:
        return {"ok": False, "error": "could not derive a widget id"}
    if wid in _RESERVED:
        return {"ok": False, "error": f"reserved id '{wid}'"}
    if not (spec or "").strip():
        return {"ok": False, "error": "empty spec"}
    if exists(wid):                                    # never re-create — the circuit shows the existing one
        return {"ok": True, "id": wid, "existed": True}
    logger.info(f"widget-agent: CREATE '{wid}' (atomic, headless)…")
    _job_start("create", wid, {"spec": spec.strip(), "title": title})
    try:
        with _lock:                                    # one agent at a time
            ran, err = _run_agent(_CREATE_PROMPT.format(wid=wid, spec=spec.strip()), token=token)
        if not ran:
            _discard(wid)                              # a killed/timed-out agent may leave a half-written folder
            return {"ok": False, "id": wid, "error": err}
        ok, verr = _validate(wid)
        if not ok:
            _discard(wid)                              # never leave debris in the catalog — delete the bad folder
            return {"ok": False, "id": wid, "error": verr}
        logger.info(f"widget-agent: '{wid}' created + validated ✓")
        return {"ok": True, "id": wid}
    finally:
        _job_end(wid)


def _discard(wid: str) -> None:
    """Remove a freshly-CREATED widget folder that failed to build/validate, so a partial (e.g. manifest but no
    widget.js) never lingers in the catalog. Only ever called on the create path — modify has its own rollback."""
    wid = safe_id(wid)
    if not wid or wid in _RESERVED:
        return
    try:
        shutil.rmtree(os.path.join(HERE, wid), ignore_errors=True)
    except Exception:
        pass


def modify_widget(wid: str, change: str, token: str = "") -> dict:
    """Modify an EXISTING widget with the atomic agent (e.g. 'add a column with price + seller'). BACKS UP the
    working version first and RESTORES it if the edit doesn't validate — so an iteration can't break a good widget.
    `token` (V2-038) hace el subproceso MATABLE (generator.kill(token))."""
    import shutil
    import tempfile
    wid = safe_id(wid)
    if not exists(wid):
        return {"ok": False, "id": wid, "error": "widget not found"}
    if not (change or "").strip():
        return {"ok": False, "id": wid, "error": "empty change"}
    d = os.path.join(HERE, wid)
    bak = tempfile.mkdtemp(prefix=f"wbak_{wid}_")
    try:
        shutil.copytree(d, os.path.join(bak, wid))
    except Exception:
        bak = None
    logger.info(f"widget-agent: MODIFY '{wid}' (atomic, headless)…")
    _job_start("modify", wid, {"change": change.strip()})
    try:
        with _lock:
            ran, err = _run_agent(_MODIFY_PROMPT.format(wid=wid, change=change.strip()), token=token)
        ok, verr = (_validate(wid) if ran else (False, err))
        if not ok and bak:                              # bad edit → roll back to the version that worked
            shutil.rmtree(d, ignore_errors=True)
            shutil.move(os.path.join(bak, wid), d)
            logger.warning(f"widget-agent: '{wid}' edit invalid → restaurado. ({verr})")
        if bak:
            shutil.rmtree(bak, ignore_errors=True)
        if not ok:
            return {"ok": False, "id": wid, "error": f"edición no válida (restaurado): {verr}"}
        logger.info(f"widget-agent: '{wid}' modified + validated ✓")
        return {"ok": True, "id": wid, "modified": True}
    finally:
        _job_end(wid)


def _keyword_collisions(wid: str, keywords: list) -> dict:
    """Map each of this widget's keywords to the OTHER catalog widgets already using it (case-insensitive).
    AGENTS.md asks for precise, non-overlapping keywords; this is the enforcement half."""
    from . import runtime
    mine = {str(k).strip().lower() for k in (keywords or []) if str(k).strip()}
    out: dict = {}
    for w in runtime.catalog():
        if w.get("id") == wid:
            continue
        theirs = {str(k).strip().lower() for k in (w.get("keywords") or [])}
        for k in sorted(mine & theirs):
            out.setdefault(k, []).append(w.get("id"))
    return out


# ── static house-rules scan (SEC-3 / INI-007 S-10) ──────────────────────────────────────────────────────────
# The runtime smoke-test proves view_data() RUNS; it does NOT prove the code obeys the isolation/no-network/no-XSS
# house rules (AGENTS.md). A headless agent can still emit innerHTML-with-interpolation (XSS), fetch/WebSocket
# (network from the client), dynamic import()/eval (dynamic code), or a non-stdlib import / hardcoded secret in
# data.py. These are STATIC red lines — enforce them, don't just ask for them in prose.

# widget.js: outright-banned sinks (network / dynamic code — never legitimate in a self-contained widget).
_JS_BANNED = [
    ("fetch(", re.compile(r"\bfetch\s*\(")),
    ("XMLHttpRequest", re.compile(r"\bXMLHttpRequest\b")),
    ("WebSocket", re.compile(r"\bWebSocket\b")),
    ("EventSource", re.compile(r"\bEventSource\b")),
    ("dynamic import()", re.compile(r"\bimport\s*\(")),
    ("eval()", re.compile(r"\beval\s*\(")),
    ("new Function()", re.compile(r"\bnew\s+Function\b")),
    ("external import", re.compile(r'\bimport\b[^\n;]*\bfrom\b\s*["\']')),   # self-contained: no module deps
]
# widget.js: HTML sinks are only dangerous with INTERPOLATION (a static string is fine). Flag assignment/call
# whose RHS on the same line carries a template `${…}` or a `+` string concat.
_JS_HTML_SINK = re.compile(
    r"(?:innerHTML|outerHTML)\s*=\s*(?P<rhs>.+)$|insertAdjacentHTML\s*\(|document\.write\s*\(", re.M)


def _bare_css_classes(css: str) -> set[str]:
    """Class names selected BARE (no ancestor combinator) in a CSS-ish text — i.e. a rule that applies to ANY
    element with that class, regardless of nesting (`.conn{...}`), as opposed to one scoped under another
    selector (`.mfoot .msg{...}`, which only ever matches a `.msg` INSIDE `.mfoot`). Only the bare form leaks
    properties onto an unrelated element elsewhere in the document that happens to reuse the same class name."""
    out = set()
    for sel_list, _ in re.findall(r"([^{}]+)\{([^{}]*)\}", css):
        for sel in sel_list.split(","):
            first = re.split(r"[\s>+~:]", sel.strip(), maxsplit=1)[0]
            m = re.fullmatch(r"\.([a-zA-Z][\w-]*)", first)
            if m:
                out.add(m.group(1))
    return out


def _all_css_classes(css: str) -> set[str]:
    """Every class token anywhere in a selector, nested or not (`.hb-msg .conn` → {"hb-msg","conn"}). Used on the
    WIDGET's own stylesheet: even a class it nests under its own wrapper still ends up on a real DOM element,
    which will ALSO match a bare global rule for that same name regardless of the widget's intended scoping."""
    out = set()
    for sel_list, _ in re.findall(r"([^{}]+)\{([^{}]*)\}", css):
        out.update(re.findall(r"\.([a-zA-Z][\w-]*)", sel_list))
    return out


_HOUSE_CSS_CACHE = {"mtime": None, "classes": set()}


def _house_global_classes() -> set[str]:
    """Bare classes defined in the app-wide stylesheet (frontend/app/styles.css) — the set a widget must never
    reuse verbatim, or it silently inherits whatever that global rule sets (position/display/etc.), invisibly,
    the moment the app stylesheet is loaded alongside the widget's own. This is exactly how it broke once already:
    mensajeria's own connection-card used the class "conn", which collided with the app's BARE `.conn{position:
    fixed;left:20px;bottom:14px;...}` (the mic/SSE status line) and got yanked out of the widget card entirely."""
    css_path = os.path.join(ZAELAR, "frontend", "app", "styles.css")
    try:
        mtime = os.path.getmtime(css_path)
    except OSError:
        return set()
    if _HOUSE_CSS_CACHE["mtime"] == mtime:
        return _HOUSE_CSS_CACHE["classes"]
    classes = _bare_css_classes(open(css_path, encoding="utf-8").read())
    _HOUSE_CSS_CACHE["mtime"], _HOUSE_CSS_CACHE["classes"] = mtime, classes
    return classes


_FULL_LINE_COMMENT_RE = re.compile(r"^\s*//.*$", re.M)


def _scan_widget_js(js: str) -> str | None:
    # False positive found in the marathon 2026-07-22/23: a full-line comment DESCRIBING the contract ("NADA de
    # fetch") tripped the ban on its own prose. Strip whole-line `//` comments before matching the banned sinks —
    # trailing same-line comments are left alone (lower risk, not the shape that caused this).
    banned_scan = _FULL_LINE_COMMENT_RE.sub("", js)
    for label, rx in _JS_BANNED:
        if rx.search(banned_scan):
            return f"widget.js uses banned {label} (widgets are self-contained; no network/dynamic code)"
    for m in _JS_HTML_SINK.finditer(js):
        rhs = m.groupdict().get("rhs")
        if rhs is None:                                    # insertAdjacentHTML / document.write → always flagged
            return "widget.js uses insertAdjacentHTML/document.write (use textContent + createElement)"
        if "${" in rhs or re.search(r"\+\s*[A-Za-z_$]", rhs):   # interpolated/concatenated HTML → XSS sink
            return "widget.js assigns interpolated innerHTML/outerHTML (XSS: build DOM with textContent)"
    # Class-name collision with the app-wide stylesheet: scan only the widget's OWN injected <style> (template
    # literal bodies) so JS property-access chains (e.g. `document.body`) can never produce a false positive.
    house = _house_global_classes()
    if house:
        style_text = "\n".join(re.findall(r"`([^`]*)`", js, re.S))
        used = _all_css_classes(style_text)
        bad = sorted(c for c in used if c in house and not c.startswith(("hbk-", "hb-")))
        if bad:
            names = ", ".join("." + c for c in bad)
            return (f"widget.js styles a class name also defined GLOBALLY in frontend/app/styles.css ({names}) — "
                    f"rename it to something widget-specific; the global rule's properties (position/display/etc.) "
                    f"silently apply to your element too, regardless of your own CSS")
    return None


# data.py: stdlib-only. Allow the standard library, relative imports, and the widgets package (store/planner).
_SECRET_RX = [
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bAIza[0-9A-Za-z_-]{30,}\b"),
    re.compile(r'(?i)\b(?:api[_-]?key|secret|password|passwd|token)\b\s*[:=]\s*["\'][^"\']{8,}["\']'),
]


def _apply_action_names(src: str) -> set[str] | None:
    """The action names an `apply_action(action, …)` actually HANDLES, by scanning the comparisons against its
    first parameter (`if action == "x"`, `elif action in ("a","b")`, `action.strip() == "x"`). Returns the set
    of handled literals, an EMPTY set if apply_action exists but uses a dispatch style we can't parse statically
    (e.g. a dict table — caller then fail-opens), or None if there is no apply_action at all. Stdlib AST, no
    execution. This is the enforcement half of "declared actions must match apply_action" (V2-025)."""
    import ast
    try:
        tree = ast.parse(src)
    except Exception:
        return None
    fn = next((n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "apply_action"), None)
    if fn is None:
        return None
    param = fn.args.args[0].arg if fn.args.args else "action"

    def _is_action_ref(node) -> bool:
        # `action`, or a chained call/attr on it: `action.strip()`, `action.lower().strip()`.
        while isinstance(node, ast.Call):
            node = node.func
        while isinstance(node, ast.Attribute):
            node = node.value
        return isinstance(node, ast.Name) and node.id == param

    names: set[str] = set()
    for node in ast.walk(fn):
        if not isinstance(node, ast.Compare) or not _is_action_ref(node.left):
            continue
        for op, comp in zip(node.ops, node.comparators):
            if isinstance(op, ast.Eq) and isinstance(comp, ast.Constant) and isinstance(comp.value, str):
                names.add(comp.value)
            elif isinstance(op, ast.In) and isinstance(comp, (ast.Tuple, ast.List, ast.Set)):
                names.update(e.value for e in comp.elts
                             if isinstance(e, ast.Constant) and isinstance(e.value, str))
    return names


def _defines_function(src: str, name: str) -> bool:
    """True si el módulo define `def <name>(` a nivel superior (AST, sin ejecutar)."""
    import ast
    try:
        tree = ast.parse(src)
    except Exception:
        return False
    return any(isinstance(n, ast.FunctionDef) and n.name == name for n in tree.body)


def _validate_background(man: dict, src: str) -> str | None:
    """Un widget que declara `background` (ejecución off-screen con ciclo, V2-034) debe ser válido: el ciclo
    `every` tiene que parsear a un periodo (≥1s), y un widget PASSIVE con background DEBE tener `def tick()` en su
    data.py (la función que el planificador llama cada ciclo). Un `backed` con background se atiende por su owner
    (comando `tick` en el buzón), así que no exige tick() en data.py."""
    if man.get("background") is None:
        return None
    from . import background as _bg
    period = _bg.parse_period(man.get("background"))
    if not period:
        return (f"'background' inválido ({man.get('background')!r}) — usa \"1s\"/\"5m\"/\"1h\", un nº de segundos, "
                f"o {{\"every\":\"1m\"}} (mínimo 1s)")
    if (man.get("kind") or "passive") != "backed" and not _defines_function(src, "tick"):
        return ("el manifest declara 'background' (ciclo off-screen) pero data.py no define `def tick()` — "
                "añade tick() (refresca datos + vuelca a memoria) o quita 'background'")
    return None


def _validate_actions_sync(man: dict, src: str) -> str | None:
    """Declared `actions` (the widget's DATA API the brain drives) must MATCH what `apply_action` really handles.
    A declared action with no handler is a dead entry; a handled action not declared is invisible to the brain —
    both are rejected (V2-025). Only for PASSIVE widgets: a `backed` widget routes actions through its owner's
    mailbox, not data.py:apply_action (the supervisor owns that contract), so skip it here."""
    if (man.get("kind") or "passive") == "backed":
        return None
    declared = {str(k).strip() for k in (man.get("actions") or {}) if str(k).strip()}
    if not declared:
        return None                                     # nothing declared → nothing to keep in sync
    handled = _apply_action_names(src)
    if handled is None:
        return (f"manifest declares actions {sorted(declared)} but data.py has no apply_action() to handle them "
                f"(declare them only if the widget can perform them)")
    if not handled:
        return None                                     # dispatch style we can't parse statically → fail-open
    dead = sorted(declared - handled)
    invisible = sorted(handled - declared)
    if dead:
        return (f"manifest declares action(s) {dead} that apply_action does NOT handle — remove them or add the "
                f"branch (declared actions must match apply_action)")
    if invisible:
        return (f"apply_action handles action(s) {invisible} not declared in manifest 'actions' — the brain can't "
                f"see them; declare each one (name/desc/payload) so the widget's data API is complete")
    return None


# stdlib-only is the contract for GENERATED widgets (an LLM-authored data.py must never reach into `connectors/` —
# that's the isolation invariant AGENTS.md/CLAUDE.md rely on). `musica` is the ONE hand-built, human-reviewed
# exception: real playback control has no stdlib equivalent — it has to call connectors.music/connectors.spotify
# directly (see its own data.py header). This allowlist is a hardcoded id, never a manifest field, precisely so a
# generated widget can't grant itself the exemption.
_STDLIB_EXEMPT = {"musica"}


def _scan_data_py(src: str, wid: str = "") -> str | None:
    import ast
    import sys
    try:
        tree = ast.parse(src)
    except Exception as e:
        return f"data.py does not parse: {e}"
    if wid not in _STDLIB_EXEMPT:
        stdlib = getattr(sys, "stdlib_module_names", set())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    top = a.name.split(".")[0]
                    if top not in stdlib and top != "widgets":
                        return f"data.py imports non-stdlib '{top}' (data.py must be stdlib-only)"
            elif isinstance(node, ast.ImportFrom):
                if node.level and node.level > 0:
                    continue                               # relative import (from .. import store) → allowed
                top = (node.module or "").split(".")[0]
                if top and top not in stdlib and top != "widgets":
                    return f"data.py imports non-stdlib '{top}' (data.py must be stdlib-only)"
    for rx in _SECRET_RX:
        if rx.search(src):
            return "data.py contains a hardcoded secret/credential"
    return None


def _validate(wid: str) -> tuple[bool, str]:
    """The widget must meet the contract before we trust it in the catalog."""
    d = os.path.join(HERE, wid)
    man_p, js_p = os.path.join(d, "manifest.json"), os.path.join(d, "widget.js")
    if not os.path.isfile(man_p):
        return False, "no manifest.json produced"
    try:
        man = json.load(open(man_p, encoding="utf-8"))
    except Exception as e:
        return False, f"manifest.json invalid: {e}"
    if not man.get("title") or not isinstance(man.get("keywords"), list) or not man.get("keywords"):
        return False, "manifest missing title/keywords"
    # Keyword anti-collision: if EVERY keyword is already owned by other widgets, this one is unidentifiable by
    # voice (or hijacks an existing identity) → reject. Partial overlaps are allowed but logged — identify()
    # handles them with disambiguation candidates, and stripping them here would regress older widgets' recall.
    kws = [str(k).strip() for k in man["keywords"] if str(k).strip()]
    coll = _keyword_collisions(wid, kws)
    if kws and len(coll) >= len({k.lower() for k in kws}):
        owners = sorted({o for v in coll.values() for o in v})
        return False, (f"all keywords already belong to other widgets ({', '.join(owners)}) — "
                       f"the widget would be unidentifiable; use distinctive keywords")
    if coll:
        logger.warning(f"widget-agent: '{wid}' keyword collisions (identify() will disambiguate): {coll}")
    # folder name is authoritative + este widget lo CREA el usuario (V2-083) → estampa origin:"user" para que la
    # pestaña Widgets de Config lo liste como "tuyo" (los de serie llevan la lista curada de registry._BUILTINS).
    _dirty = False
    if man.get("id") != wid:
        man["id"] = wid
        _dirty = True
    if man.get("origin") != "user":
        man["origin"] = "user"
        _dirty = True
    if _dirty:
        json.dump(man, open(man_p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    js_src = open(js_p, encoding="utf-8").read() if os.path.isfile(js_p) else ""
    if not js_src or "export function render" not in js_src:
        return False, "widget.js missing or has no `export function render`"
    js_bad = _scan_widget_js(js_src)                        # static house-rules gate (SEC-3): no XSS/network/dynamic code
    if js_bad:
        return False, js_bad
    dp = os.path.join(d, "data.py")
    data_src = ""
    if os.path.isfile(dp):
        data_src = open(dp, encoding="utf-8").read()
        data_bad = _scan_data_py(data_src, wid)          # stdlib-only + no hardcoded secrets
        if data_bad:
            return False, data_bad
        sync_bad = _validate_actions_sync(man, data_src)   # declared actions ↔ apply_action must match (V2-025)
        if sync_bad:
            return False, sync_bad
        import py_compile
        try:
            py_compile.compile(dp, doraise=True)
        except Exception as e:
            return False, f"data.py does not compile: {e}"
        # Runtime smoke-test: view_data(q="") must RUN and RETURN a dict — never raise. This is the isolation gate:
        # a widget that blows up at runtime never reaches the catalog (a friendly {"error": …} state is fine).
        try:
            import importlib
            mod = importlib.import_module(f"widgets.{wid}.data")
            mod = importlib.reload(mod)                 # test the just-written code, not a cached import (modify)
            if hasattr(mod, "view_data"):
                out = mod.view_data(q="")
                if not isinstance(out, dict):
                    return False, "view_data() must return a dict"
        except Exception as e:
            return False, f"view_data() raised at runtime: {type(e).__name__}: {e}"
    elif (man.get("kind") or "passive") != "backed" and (man.get("actions") or {}):
        return False, "manifest declares actions but the widget has no data.py to handle them"
    bg_bad = _validate_background(man, data_src)         # background cycle valid + passive needs tick() (V2-034)
    if bg_bad:
        return False, bg_bad
    init_p = os.path.join(d, "__init__.py")
    if not os.path.isfile(init_p):
        open(init_p, "w").close()
    return True, ""
