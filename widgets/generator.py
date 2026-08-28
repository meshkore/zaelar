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
# Static + runtime contract validation lives in its own module (V2-098): no shared mutable state with the
# orchestration below it. Re-exported by name so existing callers (widgets/harness.py, server_api.py, tests)
# keep working unchanged against `generator._validate`/`generator._validate_background`/etc.
from .validator import (_validate, _validate_actions_sync, _validate_background,  # noqa: F401
                         _apply_action_names, _defines_function, _keyword_collisions,
                         _scan_data_py, _scan_widget_js)

from widgets import paths

HERE = paths.BUILTIN_ROOT                                  # …/zaelar/widgets
ZAELAR = os.path.dirname(HERE)                             # …/zaelar  (the agent's cwd — widget CODE
                                                             # generation stays repo-relative; see the
                                                             # Phase 3 plan's M10, deliberately out of
                                                             # scope for the M0 workspace-root refactor)
GEN_TIMEOUT = float(os.getenv("WIDGET_GEN_TIMEOUT", "240"))
GEN_MODEL = os.getenv("WIDGET_GEN_MODEL", "")              # optional override, e.g. "sonnet"

_RESERVED = {"generator", "server_api", "runtime", "store", "brief", "_data", "__pycache__"}
_lock = threading.Lock()                                   # one agent at a time

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


# Filler words that must NOT enter a new widget id. Without this, deriving the id from the whole request produced
# junk ids from the instruction text itself (2026-07-15 session). Bilingual es/en. Keep the first 3 content words.
_ID_FILLER = {
    "crea", "crear", "cree", "creame", "haz", "hazme", "hacer", "genera", "generar", "generame", "monta", "montame",
    "construye", "disena", "nuevo", "nueva", "widget", "tarjeta", "panel", "cuadro", "implementar", "implementa",
    "quiero", "necesito", "ponme", "dame", "un", "una", "el", "la", "los", "las", "de", "del", "que", "para", "por",
    "con", "en", "y", "o", "a", "al", "me", "mi", "su", "lo", "capacidad", "capaz", "poder", "pueda",
    "make", "create", "build", "new", "a", "an", "the", "of", "to", "for", "with", "that", "widget", "card",
}


def _concise_id(spec: str) -> str:
    """Derive a short meaningful id from the request: normalize accents, remove filler, and keep the first 3
    content words. Fall back to the raw slug if nothing remains. Avoid junk ids derived from the whole instruction."""
    import unicodedata
    n = "".join(c for c in unicodedata.normalize("NFKD", (spec or "")) if not unicodedata.combining(c)).lower()
    toks = [t for t in re.split(r"[^a-z0-9]+", n) if t and t not in _ID_FILLER and len(t) > 1]
    return safe_id("-".join(toks[:3])) or safe_id(spec)


def exists(wid: str) -> bool:
    return bool(wid) and paths.dir_for(wid) is not None


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


# V2-038: generation processes are killable by token (= Brain Worker task_id). A `stop_worker`/`cancel_session` on
# a `code` task kills the generator's `claude` subprocess, which runs inside a non-cancellable `to_thread` thread.
_PROCS: dict = {}          # token -> subprocess.Popen
_PROCS_LOCK = threading.Lock()


def kill(token: str) -> bool:
    """Kill the generation subprocess associated with `token`, politely via terminate then kill. Idempotent."""
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
    prompts; MeshKore hit this). File tools only, cwd = zaelar, hard timeout. Killable by `token` (V2-038):
    Popen + communicate registered in _PROCS, so `kill(token)` can terminate it from another thread. Returns
    (ran, error)."""
    claude = _find_claude()
    if not claude:
        return False, "Claude Code CLI not found (set CLAUDE_BIN)"
    cmd = [claude, "-p", "--allowedTools", "Write Edit Read",
           "--permission-mode", "acceptEdits", "--output-format", "json"]
    env = dict(os.environ)
    env["PATH"] = os.path.dirname(claude) + os.pathsep + env.get("PATH", "")
    # Route widget generation through the external §code_agent endpoint (Z.AI GLM) when configured, so this
    # headless agent also avoids consuming Claude Teams license tokens (operator, 2026-07-31). Shared helper with
    # brain workers. If routed and there is no explicit override, use the §code_agent model.
    model = GEN_MODEL
    base_url = ""       # actual endpoint used for Energy metering below; "" means local license
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
        # A killed process (terminate/kill) returns rc!=0, so treat it as incomplete and let _discard clean up.
        if p.returncode and p.returncode < 0:
            return False, "generation cancelled"
    # Energy metering (2026-08-05, closes the gap noted in INI-019 addenda): `--output-format json` already includes
    # `usage`/`model`, with the same shape as the stream-json "result" metered for interactive Brain Workers (see
    # nucleo/workers/session.py). Previously stdout was discarded unread, so widget generation/modification never
    # charged Energy despite costing real tokens. Best-effort: non-JSON stdout or missing `usage` must not break a
    # generation that already completed successfully.
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
        ok, verr = _validate(wid, stamp_origin=True)
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
        # The folder the CREATE path wrote, which is always the generated root — never a built-in that happens
        # to share the id. A rollback must not be able to delete engine source.
        shutil.rmtree(paths.new_dir(wid), ignore_errors=True)
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
    d = paths.dir_for(wid) or paths.new_dir(wid)
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
        ok, verr = (_validate(wid, stamp_origin=True) if ran else (False, err))
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
