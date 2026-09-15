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

## ⭐ The criterion: the CONSOLE declares, the CODE requests (V2-699, 2026-09-15)

Two agents flipped this rule on consecutive days — one stripped `tasks` and the Meet scopes from the
OAuth app because «nothing in the code requests them», the next put them back because «leave ready
whatever we may want». Both were arguing about one list, and there are two:

  · **the consent screen's scope list** is what Google REVIEWS. It widens the scope of a verification
    the app will need some day, and costs the operator nothing at consent time — a declared scope that
    no authorization URL asks for never appears on the blue screen and never grants anything.
  · **the scopes in an authorization URL** are what the operator actually GRANTS, one flow at a time.
    This is the list that has to stay minimal, and the one this table and every `providers.py` govern.

So: declare in the console everything non-restricted we may plausibly build; request in code only what a
shipped feature uses. `FUTURE_SCOPES` below is exactly that gap made visible — named, not requested.

⚠️ **RESTRICTED scopes are the exception and stay out of both lists until something needs them**, because
they do not merely widen a review: they trigger a third-party security assessment (CASA). As of
2026-09-15 the app carries exactly one, `drive.readonly`, and `connectors/files/providers.py` already
ships the non-sensitive alternative (`drive.file`) as its second tier.

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
    #: False when the scope this door needs is NOT configured on the OAuth app, so the flow would be
    #: rejected by Google. It is a separate axis from `sensitive`: sensitive is "costs a review",
    #: unavailable is "does not work today". A door that is listed as if it worked is worse than one
    #: that is missing — V2-699, when Gmail's scope was retired from the console and this table went on
    #: announcing it (the code did not lie about a credential, it lied about a CAPABILITY).
    available: bool = True


SERVICES: dict[str, GoogleService] = {
    "gmail": GoogleService(
        id="gmail", label="Gmail", owner="connectors.email", widget="mensajeria",
        sensitive=True, available=False,
        note="Correo por IMAP/SMTP con XOAUTH2 — el token sustituye a la contraseña. ⚠️ El scope "
             "«https://mail.google.com/» fue RETIRADO de la app OAuth el 2026-09-14, así que este camino "
             "no está disponible hoy: conecta el correo con una contraseña de aplicación. Google lo "
             "clasifica como RESTRINGIDO, y es el tramo que exige auditoría de seguridad."),
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
    "contacts": GoogleService(
        id="contacts", label="Google Contacts", owner="connectors.contacts", widget="contactos",
        sensitive=True,
        note="Copia tu agenda de Google al directorio de zaelar. Es una IMPORTACIÓN de una sola "
             "dirección: lo que edites aquí es tuyo y nunca vuelve a Google."),
}

#: Named, not requested. See the module docstring: an unused sensitive scope costs verification and
#: buys nothing until something on screen needs it.
FUTURE_SCOPES: dict[str, tuple[str, ...]] = {
    # Declared on the consent screen (2026-09-15) so building either needs no second console trip and no
    # second review — and still requested by NOTHING, which is the half that matters at consent time.
    "meet": ("https://www.googleapis.com/auth/meetings.space.created",
             "https://www.googleapis.com/auth/meetings.space.readonly"),
    "tasks": ("https://www.googleapis.com/auth/tasks",),
    "contacts": ("https://www.googleapis.com/auth/contacts.other.readonly",),   # the wider, opt-in tier
}


def available() -> list[GoogleService]:
    """The doors that actually WORK today — see `GoogleService.available`. Anything that asks «what can
    I connect» must go through here rather than iterating `SERVICES`, or it offers Gmail again."""
    return [s for s in SERVICES.values() if s.available]


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
             "sensitive": s.sensitive, "available": s.available, "own_flow": not s.owner}
            for s in SERVICES.values()]
