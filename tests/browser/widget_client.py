"""Mount a widget's client in a Playwright page through the SERVED route (refactor2710-12).

A `widget.js` may import its own `js/` modules, so a test cannot paste its text into a classic `<script>`: it loads
the module the way the canvas host does, `import("/widgets/<id>/widget.js")`, and every request under that prefix is
answered by the product's own route (`widgets/client_files.py`) — what the browser gets is what the host serves.
Call it after `pg.goto(<origin>)`; it leaves `window.render` set, which is what these tests already call.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI

from widgets import client_files

_ENGINE = Path(__file__).resolve().parents[2]



def served(url: str) -> dict:
    """What the product's client route answers for `url` (`?v=` kept), as `route.fulfill` kwargs. Built from the
    route module's own pieces, not through an HTTP client: a sync Playwright handler must not start an event loop."""
    from urllib.parse import parse_qs, urlsplit
    u = urlsplit(url)
    if u.path in client_files.SHARED_CLIENT_MODULES:      # the app-shell modules a widget may import (V2-831 T-12)
        return {"status": 200, "body": _ENGINE.joinpath(u.path.strip("/")).read_bytes(),
                "headers": {"content-type": "text/javascript"}}
    parts = u.path.strip("/").split("/")                  # widgets/<id>/widget.js  ·  widgets/<id>/js/<name>
    v = "".join(c for c in (parse_qs(u.query).get("v") or [""])[0] if c.isalnum())[:32]
    rel = ["widget.js"] if parts[2:] == ["widget.js"] else ["js", client_files._safe(parts[-1])]
    p = Path(client_files._folder(parts[1]), *rel)
    if len(parts) < 3 or not p.is_file() or not p.name.endswith(".js"):
        return {"status": 404, "body": b"", "headers": {"content-type": "text/plain"}}
    src = p.read_text(encoding="utf-8")
    return {"status": 200, "body": (client_files._versioned(src, v) if v else src).encode(),
            "headers": {"content-type": "text/javascript"}}


async def _serve(route):
    await route.fulfill(**served(route.request.url))


async def mount(pg, widget_id: str, origin: str = "http://zaelar.test") -> None:
    """Load `/widgets/<id>/widget.js` as a module in `pg` and expose its `render` as `window.render`."""
    for tail in ("widget.js*", "js/**"):            # only the client: the test's own routes (assets…) stay its own
        await pg.route(f"{origin}/widgets/{widget_id}/{tail}", _serve)
    for url in client_files.SHARED_CLIENT_MODULES:
        await pg.route(f"{origin}{url}*", _serve)
    await pg.evaluate("async id => { window.render = (await import(`/widgets/${id}/widget.js`)).render; }",
                      widget_id)


class serve:
    """A real HTTP origin for a page that loads the engine's files: widget clients through their served route (with
    `?v=` carried to their modules), everything else as static files from the engine. `with serve() as port: …`."""

    def __enter__(self) -> int:
        import socket
        import threading
        import time

        import uvicorn
        from fastapi.staticfiles import StaticFiles

        app = FastAPI()
        app.include_router(client_files.router)
        app.mount("/", StaticFiles(directory=str(_ENGINE)), name="engine")
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        s.close()
        self._srv = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
        threading.Thread(target=self._srv.run, daemon=True).start()
        deadline = time.monotonic() + 15
        while not self._srv.started and time.monotonic() < deadline:
            time.sleep(0.05)
        return port

    def __exit__(self, *exc) -> None:
        self._srv.should_exit = True
