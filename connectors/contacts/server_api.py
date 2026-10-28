"""server_api.py — control plane for the contacts connector (V2-699), at `/api/contacts/*`.

Checked free first (`grep -rn '"/api/contacts' server/ connectors/ widgets/`) — nothing else in this repo
answers that prefix. Its four routes (status · `POST /api/contacts/connect` · callback · disconnect) are the
shared account flow, `connectors/oauth_routes.py`, with one fixed provider.

The IMPORT itself is deliberately NOT here. It is the widget's own declared action
(`widgets/contactos` → `import_google`), because the merge belongs to whoever owns the store, and because
an action is the thing the voice can reach — an HTTP endpoint is not.
"""
from fastapi import APIRouter

from connectors.contacts import oauth, providers
from connectors.oauth_routes import Door, register

router = APIRouter()

DOOR = Door(prefix="/api/contacts", family="contactos", oauth=oauth, providers=providers,
            status=lambda: {"ok": True, "providers": oauth.status()},
            label="Google Contacts", provider="google-contacts",
            done="Go back to the Contacts card and press «Sync contacts».", done_key="oauth.contacts.done",
            error_key="oauth.err.google", error_default="Google returned an error: {error}", error_status=400)
status, connect, callback, disconnect = register(router, DOOR)
_page = DOOR.page
