"""server_api.py — control plane for the calendar connectors (V2-679), at `/api/calendar/*`.

Prefix checked free before choosing it (`grep -rn '"/api/calendar' server/ connectors/` → nothing).

The four routes (status · connect · callback · disconnect) are the shared account flow,
`connectors/oauth_routes.py`. What is this door's own: the provider defaults to `google`, and a successful
callback runs an initial sync + local-meeting migration. Disconnecting forgets the tokens only — the local
agenda store is untouched: what was already mirrored stays as plain local meetings, per the operator's
"no perder nada" rule.
"""
from fastapi import APIRouter

from connectors.calendar import oauth, providers, service
from connectors.oauth_routes import Door, register

router = APIRouter()


def _kick_agenda_sync(_provider_id: str = "") -> None:
    """First contact after consent: an immediate sync (so the operator sees their existing appointments right
    away, not after the next background tick) plus a one-time migration of pre-existing LOCAL meetings up to
    Google — the operator's explicit "no quiero divergencias" requirement. Both steps live in the WIDGET
    (`widgets/agenda/data.py::on_calendar_connected`), which already owns the dedup/twin-settlement rules this
    needs; this connector stays agenda-agnostic. Best-effort: a refresh failure must never turn a successful
    OAuth consent into a reported failure."""
    try:
        from widgets.agenda import data as adata
        adata.on_calendar_connected()
    except Exception:
        pass


DOOR = Door(prefix="/api/calendar", family="agenda", oauth=oauth, providers=providers,
            status=lambda: service.status(), label="your Google Calendar", label_key="oauth.calendar.account",
            done="Your agenda is now syncing with Google Calendar.", done_key="oauth.calendar.done",
            default_provider="google", on_connected=_kick_agenda_sync)
status, connect, callback, disconnect = register(router, DOOR)
_page = DOOR.page
