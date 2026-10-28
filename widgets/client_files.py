#
# A widget's CLIENT code, served to the browser: its `widget.js` entry and the modules in its `js/` folder
# (refactor2710-12 T-03). A large `widget.js` splits into `js/<part>.js` siblings that the entry imports with a
# relative path (`import { x } from "./js/list.js"`), so the browser resolves them under this same prefix.
#
# Both answer `no-cache`: without it the browser's ES module + HTTP cache can keep serving an OLD file after an
# edit, indefinitely, since desktop.js's dynamic import() has no cache-busting query param on the initial load.
# The host re-imports a card with `?v=<n>` to load an EDITED widget and start it with fresh state; the same `v` is
# carried onto every relative import of the module served, so the whole graph is new, not just the entry.
#
from __future__ import annotations

import os

from fastapi import APIRouter
from fastapi.responses import FileResponse, JSONResponse, Response

from widgets import paths as _paths

router = APIRouter()


def _safe(name: str) -> str:
    """Only [A-Za-z0-9_-.] of the basename — no folders, no traversal."""
    return "".join(c for c in os.path.basename(name or "") if c.isalnum() or c in "-_.")


def _folder(wid: str) -> str:
    wid = "".join(c for c in _safe(wid) if c != ".")
    return _paths.dir_for(wid) or _paths.new_dir(wid)


def _versioned(src: str, v: str) -> str:
    """Every `import … from "./x.js"` line of `src` imports `./x.js?v=<v>` instead."""
    out = []
    for line in src.split("\n"):
        if line.lstrip().startswith(("import ", "export ")) and " from " in line:
            for q in ('"', "'"):
                line = line.replace(f".js{q}", f".js?v={v}{q}")
        out.append(line)
    return "\n".join(out)


def _js(p: str, v: str = ""):
    if not os.path.isfile(p):
        return JSONResponse({"error": f"no {os.path.basename(p)}"}, status_code=404)
    headers = {"Cache-Control": "no-cache"}
    v = "".join(c for c in v if c.isalnum())[:32]
    if not v:
        return FileResponse(p, media_type="text/javascript", headers=headers)
    with open(p, encoding="utf-8") as fh:
        return Response(_versioned(fh.read(), v), media_type="text/javascript", headers=headers)


@router.get("/widgets/{wid}/widget.js")
async def widget_js(wid: str, v: str = ""):
    """The widget's client render module, lazy-loaded by the canvas host."""
    return _js(os.path.join(_folder(wid), "widget.js"), v)


@router.get("/widgets/{wid}/js/{name}")
async def widget_js_part(wid: str, name: str, v: str = ""):
    """One module of the widget's `js/` folder, imported by its `widget.js`."""
    name = _safe(name)
    if not name.endswith(".js") or name.startswith("."):
        return JSONResponse({"error": "not a module"}, status_code=404)
    return _js(os.path.join(_folder(wid), "js", name), v)




# The app-shell modules a widget may import (V2-831 T-12) — the house gate (`validator_js.py`) reads this SAME tuple.
# Each is served at its on-disk path as that one exact file: read-only, no folder, no sibling.
SHARED_CLIENT_MODULES = ("/frontend/app/lib/icons.js",)


def _shared_route(url: str):
    file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), *url.strip("/").split("/"))
    return lambda v="": _js(file, v)


for _url in SHARED_CLIENT_MODULES:
    router.add_api_route(_url, _shared_route(_url), methods=["GET"], include_in_schema=False)
