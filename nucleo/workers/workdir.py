"""nucleo/workers/workdir.py — a private scratch working directory per worker task.

Why this exists (incident 2026-08-18, voice session `08f54c0c`, flow `T15·bcf7`): a research worker was spawned
with `cwd` = the engine repository root, so the headless agent auto-loaded that repository's DEVELOPER context
into every single request. Measured on the dying session, the FIRST API call already carried **122,833 input
tokens before the worker had done any work** — roughly 76k of them `engine/CLAUDE.md` (304,893 bytes) plus the
parent `CLAUDE.md`, none of which a worker shopping for a children's guitar can use. That left ~62k of usable
headroom; fourteen browser steps ate it, and the provider then rejected the next call with `max_output_tokens`
(the accumulated input plus the requested output reservation no longer fit its window). Cost: $2.27 for zero
results, and the operator got a raw `API Error: …` where the report should have been.

Three separate problems collapse into that one `cwd`, and one scratch directory per task removes all three:

  - **Context.** A scratch directory has no `CLAUDE.md` above it, so the worker pays for its own task and nothing
    else. This is the cheap 85% of the incident: the browsing was never the expensive part.
  - **Collision.** The delivery recipe tells every worker to write its report to a RELATIVE path in its working
    directory (`informe.json`, plain). Sharing the repo root means every worker shares that one file — the guitar
    worker started with the PREVIOUS day's report auto-attached to its prompt. One directory per task makes the
    relative path private again, with no change to the recipe. ⚠️ **One directory per task id was NOT enough and
    this bullet claimed the fix for six days**: ids restart at 0 in every process, so the collision came straight
    back through the restart door and served a stale report as fresh work — see `for_task` for the measurement and
    the boot stamp that closes it.
  - **Privacy.** Walking up from `engine/` also picks up the ROOT `CLAUDE.md`, which is the PRIVATE business/cloud
    one, and ships it to whichever provider serves the worker. Confining the cwd is what stops that at the source.

The bridges keep working from the scratch cwd because `env_for_task()` puts the engine root on `PYTHONPATH` — the
same pattern the confined dev worker already uses (`dispatch_devworker`). Bridge invocations are already
`-m nucleo.<mod>` with an ABSOLUTE interpreter, so only module RESOLUTION ever depended on the cwd.

About `extra_dirs()`, stated precisely because the first version of this docstring overclaimed: the browser hands
the worker its screenshot as an ABSOLUTE path under `widgets/_data/` and tells it to open that with `Read` (the
V2-049 vision path). **Measured against the real CLI with production flags** (`--print --permission-mode acceptEdits
--allowedTools Read`, from a scratch cwd): reading an absolute path outside the cwd IS currently allowed, so
`--add-dir` is NOT what keeps that path working. It is declared anyway, as defence in depth — the read scope this
worker actually depends on becomes explicit instead of resting on a permission default that could tighten without
notice, and a tightening would show up as a blind worker, which is the hardest failure to attribute.
"""
from __future__ import annotations

import os
import shutil
import tempfile
import time

from loguru import logger

from nucleo.runtime_ids import boot_id

# THREE levels, not two: this module lives in `nucleo/workers/`, one level deeper than `dispatch_devworker.py`
# (`nucleo/`), whose pattern it copied. With two, `PYTHONPATH` pointed at `nucleo/` and `-m nucleo.nav_cli` stopped
# resolving — a worker with NO bridges at all, which is the very fault this module exists to prevent.
_ENGINE_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_ROOT = os.path.join(tempfile.gettempdir(), "zaelar-workers")
# Kept on disk after the task ends ON PURPOSE: `informe.json` is the evidence of what the worker actually
# delivered, and it is the first thing to look at when a delivery goes wrong. Bounded by AGE instead of by
# lifetime, so the disk cannot grow forever and a post-mortem still has something to read.
_TTL_S = float(os.getenv("ZAELAR_WORKDIR_TTL_H", "48")) * 3600


def needs_repo(kind: str) -> bool:
    """True for the worker kinds whose JOB is the repository itself — confining those would break them.

    `code` is an architect/source task (the WIDGET path never gets here: it goes to `GeneratorBackend`, an
    in-process generator that spawns no agent). `dev` is the cluster dev worker, which already builds its own
    isolated cwd plus a confinement guard in `dispatch`. Everything else — research, web, generic, memory — only
    ever touches its own deliverable, and has no business reading the engine's source or its developer notes."""
    return (kind or "") in ("code", "dev")


def for_task(task_id: str) -> str:
    """This task's private scratch directory, created if needed.

    Stable per `task_id` (not a fresh `mkdtemp`) so a RESUMED worker of the same management lands back in its own
    directory and still finds what it wrote — V2-049 continuity depends on not starting from zero.

    ⚠️ AND COMPOSED WITH THE BOOT STAMP (V2-288), because `task_id` alone did NOT make the path private and the
    COLLISION this module claims to have fixed was still open — through the door `runtime_ids` exists to close.
    `escalate._seq` restarts at 0 in every process, so the first errand after a restart is `1` again, lands on the
    directory the previous run's first errand used, and inherits its `informe.json` while `_TTL_S` keeps it for
    48 hours.

    Measured on the batch of 2026-08-24 11:11, `search-buy-guitar__es`: the worker planned «3 pasos: entregar
    informe de guitarras en la hoja results» and delivered SIX guitars with real Wallapop urls **27 seconds after
    starting, with zero navigations, zero extractions and zero searches** — reading them out of
    `zaelar-workers/1/informe.json`, written by another run at 03:02. It then told the operator «Entré en Wallapop
    y revisé 14 anuncios», which is the report's own narration, not something the model made up. Cost $0.31 for a
    delivery that never happened.

    The damage is worse in production than on the bench: the operator's next search after a restart can be served
    the PREVIOUS session's report as freshly browsed, complete with prices and working links. It is not a plausible
    lie — it is a real one from another day, which is exactly the kind nobody checks.

    Same class and same remedy as V2-259's addendum on the results sheet (`dispatch.sheet_id_for`): anything that
    must not collide across a restart is composed with `boot_id()`, which also ROLLS on a reset (V2-287), so
    «empezamos de cero» gets a genuinely empty directory. Resuming inside one process is untouched — same stamp,
    same id, same directory."""
    _reap()
    raw = f"{boot_id()}-{task_id or 'task'}"
    safe = "".join(c if (c.isalnum() or c in "-_") else "-" for c in raw)[:64] or "task"
    path = os.path.join(_ROOT, safe)
    try:
        os.makedirs(path, exist_ok=True)
        return path
    except OSError as e:
        # A worker in an odd directory is still far better than one inheriting the repository's whole context, so
        # this degrades instead of failing the task.
        logger.warning(f"workdir: could not create {path} ({e}) → falling back to mkdtemp")
        try:
            return tempfile.mkdtemp(prefix="zaelar-worker-")
        except OSError:
            return _ENGINE_ROOT


def env_for_task(env: dict | None = None) -> dict:
    """The env additions a confined worker needs: the engine root on `PYTHONPATH` so `-m nucleo.<bridge>` still
    resolves from the scratch cwd. PREPENDED to whatever `PYTHONPATH` is already in play (the caller's `env` wins
    over the process env) rather than assigned, because `spec.env` REPLACES keys when the backend merges it over
    `os.environ` — assigning here would silently drop an existing entry."""
    prev = (env or {}).get("PYTHONPATH") or os.environ.get("PYTHONPATH") or ""
    return {"PYTHONPATH": (_ENGINE_ROOT + os.pathsep + prev) if prev else _ENGINE_ROOT}


def extra_dirs() -> list[str]:
    """Directories a confined worker DEPENDS on being able to read, as absolute paths.

    Only the browser's data directory today: `nav_cli` answers every action with an absolute
    `widgets/_data/navegador/shot-<task>.png` and instructs the worker to open it with `Read` (V2-049 vision).
    Verified live that the CLI already allows that read without being told (see the module docstring) — this makes
    the dependency EXPLICIT rather than incidental. Empty list if it cannot be resolved: the worker keeps the TEXT
    snapshot, which is the documented fallback."""
    try:
        from widgets import store
        from widgets.navegador import owner
        return [os.path.abspath(store.data_dir(owner.WID))]
    except Exception:
        return []


def _reap() -> None:
    """Delete scratch directories older than `_TTL_S`. Best-effort and silent: this is housekeeping, and failing to
    tidy up must never be the reason a task does not start."""
    try:
        os.makedirs(_ROOT, exist_ok=True)
        now = time.time()
        for name in os.listdir(_ROOT):
            p = os.path.join(_ROOT, name)
            try:
                if now - os.path.getmtime(p) > _TTL_S:
                    shutil.rmtree(p, ignore_errors=True)
            except OSError:
                pass
    except OSError:
        pass
