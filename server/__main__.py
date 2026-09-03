#!/usr/bin/env python3
"""
zaelar — personal voice assistant (English). Entrypoint for the whole app.
The FastAPI app + routes live in this `server/` package; run it as a module.

  Single screen / · live voice API (WebRTC offer/ice · SSE events).

Run:  ./.venv/bin/python -m server      → http://localhost:43917
   (or: make run)   ·   self-contained: zaelar/.venv + zaelar/.env
"""
import os
import sys

from loguru import logger

logger.remove()
logger.add(sys.stderr, level=os.getenv("LOG_LEVEL", "INFO"),
           format="{time:HH:mm:ss.SSS} | {level: <7} | {message}")

# repo ROOT (parent of server/) must be importable so the domain packages resolve:
# voice/ · brains/ · widgets/ · config/ · server/  (works for both `python -m server` and a direct run)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# THE PER-TENANT TREE, BEFORE ANYTHING READS A PATH (V2-562). `server/__init__` pulls in config/settings.py,
# which loads `settings.json` at import time, and everything downstream resolves its own persistent path the same
# way. On a self-host clone those directories come from git; on a cloud Machine the mounted Volume starts EMPTY,
# and every one of those writers then fails best-effort and steps over it. This one line is what makes a first
# boot on an empty disk indistinguishable from every later one — so it has to run BEFORE the import below, not
# inside a FastAPI startup hook that fires after it.
from nucleo import workspace as _workspace  # noqa: E402

_workspace.ensure()

from server import app  # noqa: E402

if __name__ == "__main__":
    import asyncio
    import uvicorn

    # zaelar's fixed local port (43917): the system always starts here unless PORT is overridden (prod sets 8080).
    host = os.getenv("HOST", "localhost"); port = int(os.getenv("PORT", "43917"))
    logger.info(f"Assistant (voice) on http://{host}:{port}")
    servers = [uvicorn.Server(uvicorn.Config(app, host=host, port=port, log_level="warning"))]

    # Optional PUBLIC HTTPS listener for local.zaelar.com — a SHARED cert (issued once, same for every
    # self-host install, à la Plex's *.plex.direct) so the browser address bar can show a real domain
    # instead of literal "localhost" while still talking directly to THIS machine (DNS: bare A record to
    # 127.0.0.1, no Cloudflare edge involved). Purely additive: internal loopback callers (nucleo/*_cli.py
    # bridges) keep using the plain HTTP port above, untouched. No-op if the cert isn't present (a fresh
    # clone without it just runs the plain HTTP port as always).
    cert_dir = os.getenv("ZAELAR_TLS_CERT_DIR", os.path.join(ROOT, "certs", "local.zaelar.com"))
    certfile, keyfile = os.path.join(cert_dir, "fullchain.pem"), os.path.join(cert_dir, "privkey.pem")
    if os.path.exists(certfile) and os.path.exists(keyfile):
        tls_port = int(os.getenv("ZAELAR_TLS_PORT", "44317"))
        logger.info(f"Assistant ALSO on https://local.zaelar.com:{tls_port} (shared cert)")
        servers.append(uvicorn.Server(uvicorn.Config(
            app, host=host, port=tls_port, log_level="warning",
            ssl_certfile=certfile, ssl_keyfile=keyfile,
        )))

    async def _serve_all():
        await asyncio.gather(*(s.serve() for s in servers))

    asyncio.run(_serve_all())
