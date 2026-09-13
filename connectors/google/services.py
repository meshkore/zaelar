"""services.py — which Google services this build can reach, who fronts each one, and what it costs in
consent (V2-685).

## Why a table and not five READMEs

The operator's question was «use it for Gmail, Calendar and Meet — I guess we have no more widgets
where it would apply». Answering that required reading five connector packages to find out which Google
doors exist, which have a surface the operator can actually see, and which ask for a scope Google
classes as sensitive. That answer is worth writing down once.

## What this table does NOT own: the scopes of an existing connector

Each connector already declares its own scopes next to the client that requests them
(`email/providers.py::_GOOGLE_OAUTH`, `calendar/providers.py::_GOOGLE_TIERS`, and the tier tables in
video/photos/files). Copying them here would make two truths that drift, and this package sits BELOW
those connectors in the dependency order — it cannot import them to check. So a service names its
owner and the caller asks the owner. `scopes` here is filled in only for a service that has no
connector of its own, which today means Meet.

## Meet, and why it asks for nothing extra

A Google Meet link is not a separate product to connect: it is `conferenceData` on a Calendar event, so
it rides the calendar scope that the calendar connector already holds. There IS a standalone Meet REST
API (v2, spaces and recordings) behind `.../auth/meetings.space.created`, and it is deliberately NOT
requested — an unused sensitive scope buys nothing today and costs a harder Google verification for
every user of the app. It is named in `FUTURE_SCOPES` so the decision is visible rather than forgotten.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class GoogleService:
    id: str
    label: str
    #: The connector package that owns the flow and the tokens, or "" when this package is the owner.
    owner: str
    #: The widget the operator sees it through, or "" when it has no surface of its own.
    widget: str
    #: Set ONLY for a service with no connector of its own. Otherwise the owner's registry is the truth.
    scopes: tuple[str, ...] = ()
    note: str = ""
    #: A service Google classes as SENSITIVE or RESTRICTED — it needs app verification before anyone
    #: outside the test users can consent. Worth surfacing: it is the difference between "connect it"
    #: and "connect it after Google reviews us".
    sensitive: bool = False


SERVICES: dict[str, GoogleService] = {
    "gmail": GoogleService(
        id="gmail", label="Gmail", owner="connectors.email", widget="mensajeria",
        sensitive=True,
        note="Correo por IMAP/SMTP con XOAUTH2 — el token sustituye a la contraseña. El scope es "
             "«toda la cuenta de correo», que Google clasifica como RESTRINGIDO."),
    "calendar": GoogleService(
        id="calendar", label="Google Calendar", owner="connectors.calendar", widget="agenda",
        sensitive=True,
        note="Lee y escribe tus calendarios: la agenda se sincroniza y una cita dictada por voz "
             "aparece en el Google Calendar real."),
    "meet": GoogleService(
        id="meet", label="Google Meet", owner="", widget="agenda",
        # Nothing of its own: a Meet link is created WITH the calendar event that carries it.
        scopes=(),
        note="Una cita puede nacer con enlace de Meet. No es una conexión aparte: va con el calendario, "
             "y por eso no pide ni un permiso más."),
    "drive": GoogleService(
        id="drive", label="Google Drive", owner="connectors.files", widget="archivos",
        sensitive=True,
        note="Ficheros de Drive dentro del gestor de archivos."),
    "photos": GoogleService(
        id="photos", label="Google Photos", owner="connectors.photos", widget="fotos",
        note="Tu biblioteca de fotos en el visor."),
    "youtube": GoogleService(
        id="youtube", label="YouTube", owner="connectors.video", widget="youtube",
        note="Tus suscripciones alimentan el inicio del reproductor. Solo lectura."),
}

#: Named, not requested. See the module docstring: an unused sensitive scope costs verification and
#: buys nothing until something on screen needs it.
FUTURE_SCOPES: dict[str, tuple[str, ...]] = {
    "meet": ("https://www.googleapis.com/auth/meetings.space.created",),
}


def get(service_id: str) -> GoogleService | None:
    return SERVICES.get((service_id or "").strip().lower())


def ids() -> list[str]:
    return list(SERVICES.keys())


def with_widget() -> list[GoogleService]:
    """The services the operator can actually SEE. His own scoping question — «for now I guess we do not
    have more widgets where applicable» — is this list, and it is derived rather than asserted."""
    return [s for s in SERVICES.values() if s.widget]


def public_list() -> list[dict]:
    """Redacted list for the Connectors tab. No endpoints, no credentials, no scopes of other owners."""
    return [{"id": s.id, "label": s.label, "widget": s.widget, "note": s.note,
             "sensitive": s.sensitive, "own_flow": not s.owner}
            for s in SERVICES.values()]
