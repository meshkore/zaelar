#
# A widget's CLIENT code, served to the browser: its `widget.js` entry and the modules in its `js/` folder
# (refactor2710-12 T-03). A large `widget.js` splits into `js/<part>.js` siblings that the entry imports with a
# relative path (`import { x } from "./js/list.js"`), so the browser resolves them under this same prefix.
#
# Both answer `no-cache`: without it the browser's ES module + HTTP cache can keep serving an OLD file after an
# edit, indefinitely, since desktop.js's dynamic import() has no cache-busting query param on the initial load.
# A `?v=` on the entry does not reach the modules it imports — a page that already loaded a `js/` module keeps it
# until the page reloads.
#
from __future__ import annotations

import os

from fastapi import APIRouter
from fastapi.responses import FileResponse, JSONResponse

from widgets import paths as _paths

router = APIRouter()


def _safe(name: str) -> str:
    """Only [A-Za-z0-9_-.] of the basename — no folders, no traversal."""
    return "".join(c for c in os.path.basename(name or "") if c.isalnum() or c in "-_.")


def _folder(wid: str) -> str:
    wid = "".join(c for c in _safe(wid) if c != ".")
    return _paths.dir_for(wid) or _paths.new_dir(wid)


def _js(p: str):
    if not os.path.isfile(p):
        return JSONResponse({"error": f"no {os.path.basename(p)}"}, status_code=404)
    return FileResponse(p, media_type="text/javascript", headers={"Cache-Control": "no-cache"})


@router.get("/widgets/{wid}/widget.js")
async def widget_js(wid: str):
    """The widget's client render module, lazy-loaded by the canvas host."""
    return _js(os.path.join(_folder(wid), "widget.js"))


@router.get("/widgets/{wid}/js/{name}")
async def widget_js_part(wid: str, name: str):
    """One module of the widget's `js/` folder, imported by its `widget.js`."""
    name = _safe(name)
    if not name.endswith(".js") or name.startswith("."):
        return JSONResponse({"error": "not a module"}, status_code=404)
    return _js(os.path.join(_folder(wid), "js", name))
