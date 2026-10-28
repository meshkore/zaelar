"""widgets/generator_folders.py — a generated widget's FOLDER and its JOB: ids, the pending-jobs ledger, forking a
shipped widget, discarding a failed build (split from `generator.py`)."""
from __future__ import annotations

import glob
import json
import os
import re
import shutil
import threading

from loguru import logger

from nucleo import workspace as _workspace
from widgets import paths


_RESERVED = {"generator", "server_api", "runtime", "store", "brief", "_data", "__pycache__"}


# In-flight generation journal — a server restart kills the headless agent mid-build with no trace. Each job is
# recorded here when it starts and removed when it ends, so on boot resume_interrupted_generations() (server_api)
# can relaunch creates / report broken modifies instead of leaving the operator with a silent "done" that never
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


def _folder_ref(d: str) -> str:
    """The target folder as the headless agent must address it: ABSOLUTE, always. The agent's cwd is a private
    scratch directory since V2-601 T-04 (it used to be the repo root — see `_run_agent`), so a relative path
    would resolve against a folder that holds nothing. Before V2-515 the prompts hardcoded `widgets/<id>/`,
    which silently pointed the agent at ENGINE SOURCE whenever the real target was the generated root — with a
    mounted workspace that meant every generated widget landed in the ephemeral checkout instead of the volume."""
    return os.path.realpath(d)


def _fork_shipped(wid: str, src: str) -> str:
    """A SHIPPED widget is never edited in place (V2-515): copy it into the generated root and hand the
    edit THAT folder. The copy shadows the original everywhere (catalog, identify, widget.js serving,
    python imports), so from here on "the user's musica" IS this fork — while the shipped folder keeps
    receiving engine updates untouched underneath, which is exactly what makes `restore` meaningful."""
    import time
    dst = paths.new_dir(wid)
    shutil.rmtree(dst, ignore_errors=True)                 # debris of a half-built fork never survives
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__"))
    man_p = os.path.join(dst, "manifest.json")
    try:
        man = json.load(open(man_p, encoding="utf-8"))
    except Exception:
        man = {"id": wid}
    man["origin"] = "user"
    try:
        import version as _v
        engine = str(getattr(_v, "VERSION", "") or "")
    except Exception:
        engine = ""
    man["forked_from"] = {"origin": "builtin", "engine": engine, "date": time.strftime("%Y-%m-%d")}
    json.dump(man, open(man_p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    # The import shadow needs a REGULAR package: a namespace portion loses to a regular one later in the
    # search path, and the shipped folder always has __init__.py.
    open(os.path.join(dst, "__init__.py"), "a").close()
    paths.forget_modules(wid)
    from . import runtime as _runtime
    _runtime.invalidate()
    logger.info(f"widget-agent: '{wid}' FORKED from shipped source → {dst}")
    return dst


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
