"""server/tasks_api.py — the operator's TASK BOARD over HTTP (V2-728).

Two routes and nothing else: READ the board, and REOPEN one finished task's report.

WHY ITS OWN MODULE. It was born inside `server/voice_api.py`, which the architecture ratchet caps at 900
lines for files not in its god-file table — and the reopen route pushed it past. The house rule is to
EXTRACT, never to raise the number, and this is the cut the file was asking for anyway: everything else in
`voice_api.py` is about a voice session (its transport, its state, its ⏻), while a task board outlives every
session there is. That is the whole point of V2-728.

NEITHER ROUTE DECIDES ANYTHING. `nucleo.tasks.board()` owns the read (the durable rows with the live detail
merged on top) and `widgets/results/rehydrate.py` owns the rebuild; an HTTP surface that reached into
`memory/` directly would also break the memory boundary ratchet, which counts exactly that.
"""
import asyncio

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from loguru import logger

from voice.observer import emit

router = APIRouter()


@router.get("/api/tasks")
async def tasks(scope: str = "live", all: str = ""):
    """The operator's TASK BOARD — one query over the durable `tasks` table (V2-728).

    This used to be two things stitched together at this route: `dispatch.active_sessions()` (a RAM dict, so a
    restart emptied it) plus `errands.board_rows()` (a second row shape, synthesised per request). They had
    different ids, different lifetimes and different notions of «finished», which is how the Processes tab and
    the Flows board came to disagree about the same work. Both now write the same table, and the read —rows
    plus the live detail merged on top— belongs to `nucleo.tasks.board()`, not to this route.

    `scope` picks the sub-tab: `live` (En curso) · `done` (Hechas) · `recurring` (Periódicas) · `scheduled`
    (Programadas). `all=1` is the `⚙ todo` switch — it adds the engine's own internal escalations, which the
    operator needs during a manual test and nowhere else. Read-only, no-cache.
    """
    try:
        from nucleo import tasks as _tasks
        show_all = str(all or "").strip().lower() in ("1", "true", "yes", "si", "sí")
        rows = _tasks.board(scope, show_all=show_all)
    except Exception:  # noqa: BLE001
        return JSONResponse({"tasks": [], "scope": scope}, headers={"Cache-Control": "no-cache"})
    return JSONResponse({"tasks": rows, "scope": scope}, headers={"Cache-Control": "no-cache"})


@router.post("/api/tasks/reopen")
async def tasks_reopen(payload: dict | None = None):
    """«Ver resultados» on a finished row — put that task's report back on the canvas (V2-728).

    Operator, 2026-09-20: *«si el usuario quiere ver cómo ha terminado, se va a esa lista, le da el botón y
    ve los datos derivados»*. The button had nowhere to call. The voice path could already do this
    (`reopen_task` → `nucleo/flash/task_recall.py`), but a voice tool is not reachable from a click, and the
    click is the gesture the operator described.

    The sheet may be long gone — eight is the cap and a busy week passes it — so this REBUILDS it from
    `task_artifacts` when it has to (`widgets/results/rehydrate.py`, idempotent: a sheet still on disk is left
    exactly as it is, with anything added since). Then it emits the same `widget/show` the brain emits, rather
    than answering with an id for the caller to open: that one event reaches the desktop AND the mobile shell,
    and it puts the opening on the observability timeline like every other card that appears on screen.
    """
    tid = str((payload or {}).get("id") or "").strip()
    if not tid:
        return JSONResponse({"ok": False, "error": "sin tarea"}, status_code=400)
    try:
        from widgets.results import rehydrate as _rehy
        out = await asyncio.to_thread(_rehy.sheet_from_task, tid)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"tasks_reopen({tid}) failed: {e}")
        return JSONResponse({"ok": False, "error": "no se pudo reabrir"}, status_code=500)
    if out.get("ok") and out.get("instance"):
        # `src` is neither «user» (the SSE client drops those as its own echo) nor `worker:…` (which opens
        # the card in the background, deliberately, so unattended work never steals focus). This one IS the
        # operator asking, so it comes to the front.
        emit("widget", "show", extra={"id": out["instance"], "src": "tasks"})
    return JSONResponse(out, headers={"Cache-Control": "no-cache"})


