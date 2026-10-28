"""server_api.py — control plane for the cloud-file connectors (V2-557), at `/api/cloudfiles/*`.

Deliberately NOT `/api/files/*`: that prefix is already owned by `server/memory_routes.py` (paste/drop uploads
into episodic memory, V2-003). Two routers answering one prefix is a collision that FastAPI resolves by
registration order — silently, and in favour of whichever was mounted first.

The four routes (status · connect · callback · disconnect) are the shared account flow,
`connectors/oauth_routes.py`; this door declares only what is its own.
"""
from fastapi import APIRouter

from connectors.files import oauth, providers, service
from connectors.oauth_routes import Door, register

router = APIRouter()

DOOR = Door(prefix="/api/cloudfiles", family="archivos", oauth=oauth, providers=providers,
            status=lambda: service.status(), label="your files", label_key="oauth.files.account")
status, connect, callback, disconnect = register(router, DOOR)
_page = DOOR.page
