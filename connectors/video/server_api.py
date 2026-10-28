"""server_api.py — control plane for the video-account connectors (V2-597), at `/api/video/*`.

Prefix checked free before choosing it (`grep -rn '"/api/video' server/ connectors/` → nothing): two routers
answering one prefix is a collision FastAPI resolves by mount order, silently (V2-557's T10).

The four routes (status · connect · callback · disconnect) are the shared account flow,
`connectors/oauth_routes.py`; what is this door's own is the card refresh after a connection.
"""
from fastapi import APIRouter

from connectors.oauth_routes import Door, register
from connectors.video import oauth, providers, service

router = APIRouter()


def _refresh_card(provider_id: str) -> None:
    """Push the new connection state into the youtube card so the operator does not have to press «comprobar».

    V2-603 — the wizard used to end on a button the operator had to press to discover whether the thing he had
    just done had worked, on BOTH of its last two steps. The callback lands on our OWN server and already
    knows the answer; `widgets/store.save` is the single choke point that pushes `widget/data` over SSE, so
    writing the refreshed platform rows repaints the open card by itself. Best-effort: a connection that
    succeeded must never be reported as failed because a card could not be refreshed."""
    try:
        from widgets import store
        from widgets.youtube import data as ydata
        db = store.load(ydata.WID, ydata._seed())
        ydata._sync_platforms(db)
        store.save(ydata.WID, db)
    except Exception:
        pass


DOOR = Door(prefix="/api/video", family="video", oauth=oauth, providers=providers,
            status=lambda: service.status(), label="your video account", label_key="oauth.video.account",
            on_connected=_refresh_card)
status, connect, callback, disconnect = register(router, DOOR)
_page = DOOR.page
