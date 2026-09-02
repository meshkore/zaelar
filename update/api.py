"""The one route this module adds: `GET /api/update`.

DELIBERATELY NOT ON THE SSE STREAM, and it is worth writing down why, because the stream looks like the
obvious home for a push. A version can only change when the process changes, and a new process always
breaks every open SSE connection — so «the stream reconnected» already carries the news. The reason it is
still a poll is the other half of the operator's ask: the number has to keep climbing in a browser left
open for three days, including in the mobile PWA whose tab has been in the background for hours, and a
poll on a visible tab is the only thing that keeps being true in all of those cases. It costs one request
of ~200 bytes against a fully cached dict, which is less than the `/api/status` poll already running.

NOT in `server/ingress.py`'s public allowlist, on purpose: it is a normal `/api/*` route, so on a Machine
that takes part in session routing it needs the same session cookie as everything else. The browser asking
it always has one — it just loaded the app from this very process. Nothing here needs to be readable by a
stranger, and the allowlist is meant to grow only when something must be.
"""
from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from . import state

router = APIRouter()


@router.get("/api/update")
async def update_state() -> JSONResponse:
    # `no-store`, same reason as the app shell: an answer about staleness that is itself served from a
    # cache is the one answer that can never be trusted.
    return JSONResponse(state(), headers={"Cache-Control": "no-store, max-age=0"})
