"""widgets/navegador/act_api: the BROWSER BRIDGE for Claude Code agents (V2-036 F3).

Exposes the owner's `TaskBrowser` primitives (navigate/click/type/scroll/snapshot/extract) as a synchronous
request/response API for the `nucleo/nav_cli.py` CLI (`hbweb`). It runs in the uvicorn loop, the same loop as the
browser owner, so it calls `TaskBrowser` directly. Loopback: same trust model as the rest of the API.
"""
import asyncio

from widgets.navegador import lazy as _lazy
from widgets.results import door_verdict as _door

from fastapi import APIRouter, Body
from fastapi.responses import JSONResponse
from nucleo.errors import brief as _brief

router = APIRouter()


def _shot_path(task_id: str) -> str:
    """Absolute PNG path of this tab's viewport (written by TaskBrowser._capture after each action), or '' when the
    file is not there: `nav_cli` turns a non-empty value into «read this file», so a missing PNG must never be
    advertised; empty sends the worker to the text snapshot (V2-205)."""
    try:
        import os
        from widgets import store
        from widgets.navegador import owner
        p = os.path.abspath(f"{store.data_dir(owner.WID)}/shot-{task_id}.png")
        return p if os.path.isfile(p) else ""
    except Exception:
        return ""


def _emit_nav(nav_tid: str, label: str, text: str) -> None:
    """Observability row for a browser action's result (page reached / what was found), which only the browser
    knows (V2-048). Its label differs from the intent `step` to dodge `navegador` flood-dedup; stamps the owning
    worker's trace/span. Never raises."""
    try:
        from voice.observer import emit
        from nucleo import dispatch
        extra = {"id": nav_tid}
        r = dispatch.record_by_nav_task(nav_tid)
        if r is not None and getattr(r, "trace_id", ""):
            extra["trace"] = r.trace_id
            extra["span"] = f"worker:{r.task_id}"
        emit("navegador", label, text=text[:200], extra=extra)
    except Exception:
        pass


# Same threshold the FlashBrain turn uses for «sin moverse» (`nucleo/flash/prompt.py`), read from the same env
# variable so the two halves of one fact can never drift apart.
_STALL_HINT_S = int(__import__("os").environ.get("ZAELAR_NAV_STALLED_S", "120") or 120)

# How long to wait before looking again at a page that returned only hollow rows (V2-294). Deliberately short:
# this is the hydration time for a listing, not a network wait — if it has not rendered by then, waiting longer
# fixes nothing, and the worker has its own exits (change the search or site).
_HYDRATE_WAIT_S = float(__import__("os").environ.get("ZAELAR_NAV_HYDRATE_S", "2") or 2)


from nucleo.workers import progress as _progress   # V2-227: la frase que lee una persona

_HANDED: dict[str, str] = {}          # V2-223: última extracción entregada por tarea (no repetir la misma)


_PHASE_TARGET = {           # de qué argumento sale el «target» que la frase enseña al operador
    "navigate": "url", "open": "url", "goto": "url", "visit": "url",
    "type": "text", "type_at": "text",
    "click": "ref", "select_option": "value",
}


# A template must be LONG (a complete navigation phrase, not a category word: «Bici » is shared by three
# legitimate bikes) and come from the PAGE, not three unrelated rows — hence the half minimum. Three
# «Ford Focus 1.5 TDCi» among seven cars are three cars, not chrome.
_TPL_MIN_CHARS = 12
_TPL_MIN_ROWS = 3

# Concern modules (`entry` registers the route on `router`) read every name of this module through the package.
from widgets.navegador.act_api.guards import (  # noqa: E402,F401 — re-export
    _with_wall, _query_of, _with_url_change, _with_stall)
from widgets.navegador.act_api.pick import (  # noqa: E402,F401 — re-export
    by_identity, _boilerplate_suffix, _boilerplate_prefix, by_amount, dedupe_by_url)
from widgets.navegador.act_api.handover import (  # noqa: E402,F401 — re-export
    _sheet_of, _hand_over, _note_body, _sheet_already_named)
from widgets.navegador.act_api.entry import (  # noqa: E402,F401 — re-export
    _say_phase, _phase_for_action, _act_extract, navegador_act)
