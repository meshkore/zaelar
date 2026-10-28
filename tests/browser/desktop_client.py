"""Mount the canvas (`frontend/app/widgets/desktop.js`) in a Playwright page with its REAL imports (V2-831 T-14).

Six render tests used to paste desktop.js into a classic script tag with its imports replaced by hand-written stubs.
Every import desktop.js gained after that went unstubbed, the tests failed at the stub check, and nobody saw it for a
month (c9553455b added `footprint.js` and `placement.js`). Here the page asks for the module the way the app does,
`import("/app/widgets/desktop.js")`, and every request under `/app/` is answered with the engine's own file. So the
canvas runs with the modules it really imports, and a new import needs nothing from the tests. A file that does not
exist answers 404, and the failure names it. Call it after `pg.goto(<origin>)`; it leaves
`window.__Desktop` set, which is what these tests already read.
"""
from __future__ import annotations

from pathlib import Path
from urllib.parse import urlsplit

_APP = Path(__file__).resolve().parents[2] / "frontend" / "app"


def served(url: str) -> dict:
    """What `/app/<path>` answers: the engine's file (any `?v=` ignored, as the static route does), else 404."""
    rel = urlsplit(url).path.split("/app/", 1)[-1]
    p = (_APP / rel).resolve()
    if _APP not in p.parents or not p.is_file():
        return {"status": 404, "body": f"not in frontend/app: {rel}", "headers": {"content-type": "text/plain"}}
    kind = "text/javascript" if p.suffix in (".js", ".mjs") else "text/css" if p.suffix == ".css" else "text/plain"
    return {"status": 200, "body": p.read_bytes(), "headers": {"content-type": kind}}


async def mount(pg, origin: str = "http://zaelar.test") -> None:
    """Load the real desktop.js as a module in `pg` and expose its `Desktop` as `window.__Desktop`."""
    missing: list[str] = []

    async def _serve(route):
        answer = served(route.request.url)
        if answer["status"] == 404:
            missing.append(urlsplit(route.request.url).path)
        await route.fulfill(**answer)

    await pg.route(f"{origin}/app/**", _serve)
    try:
        await pg.evaluate("async () => { window.__Desktop = (await import('/app/widgets/desktop.js')).Desktop; }")
    except Exception as e:
        raise AssertionError(f"desktop.js did not load; files it imports that do not exist: {missing or 'none'} "
                             f"({e})") from e
