"""Mount a widget's client in a Playwright page through the SERVED route (refactor2710-12).

A `widget.js` may import its own `js/` modules, so a test cannot paste its text into a classic `<script>`: it loads
the module the way the canvas host does, `import("/widgets/<id>/widget.js")`, and every request under that prefix is
answered by the product's own route (`widgets/client_files.py`) — what the browser gets is what the host serves.
Call it after `pg.goto(<origin>)`; it leaves `window.render` set, which is what these tests already call.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from widgets import client_files

_ENGINE = Path(__file__).resolve().parents[2]

_app = FastAPI()
_app.include_router(client_files.router)
_served = TestClient(_app)


async def _serve(route):
    path = "/" + route.request.url.split("://", 1)[-1].split("/", 1)[-1].split("?", 1)[0]
    r = _served.get(path)
    await route.fulfill(status=r.status_code, body=r.content,
                        headers={"content-type": r.headers.get("content-type", "text/plain")})


async def mount(pg, widget_id: str, origin: str = "http://zaelar.test") -> None:
    """Load `/widgets/<id>/widget.js` as a module in `pg` and expose its `render` as `window.render`."""
    await pg.route(f"{origin}/widgets/{widget_id}/**", _serve)
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
