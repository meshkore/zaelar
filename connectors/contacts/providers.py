"""providers.py — where a contact can be imported FROM (V2-699).

Same shape as `connectors/photos/providers.py` and `connectors/files/providers.py`: one registry, scope
tiers next to the client that requests them, nothing about credentials.

## Three tiers: read-only, read-only + «others», and the two-way sync

This started as an import and nothing else, on the reasoning that a two-way sync has to answer «who wins»
on every field and that the answer for a local-first assistant is always «he does». **The operator
overruled it the same day, and his reason is better than the objection was:**

> «Si se modifica algo en nuestro agente, un nombre, un teléfono, también se modifica en Google. Eso sería
> lo más interesante, lo más simple a nivel gráfico y lo más fácil de comprender por parte de los
> usuarios. Además estaría unificado como por ejemplo en la agenda, Google Calendar.»

The point about the agenda is the one that settles it: Google Calendar is already two-way there — a
meeting dictated by voice appears in his real calendar. A contacts connector that was one-way would be
the odd one out in his own product, and «who wins» is answerable after all: **whoever touched the row
last**, which is what `updated` has always recorded.

⚠️ **The `sync` tier does not work until its scope is declared on the OAuth app.** As of 2026-09-15 the
consent screen carries `contacts.readonly` and `contacts.other.readonly` only. `.../auth/contacts` has to
be added in the Google Cloud console before anyone can consent to this tier — Google rejects what it was
never told about. Everything below is built and tested; that one console line is the gate.

## Why «Otros contactos» is opt-in

`contacts.readonly` is the address book he actually curated. `contacts.other.readonly` is Google's
«Other contacts» — every address he has ever mailed, auto-collected, usually hundreds of rows with no
name. Importing those by default would bury the twelve people he cares about, so the wider tier exists
and is NOT the default.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ScopeTier:
    id: str
    label: str
    scopes: tuple[str, ...]
    #: True when this tier can WRITE back to the provider. Read off the tier rather than re-derived from
    #: the scope strings by each caller: the widget has to be able to say «solo puedo traer» honestly, and
    #: a surface that guessed would eventually guess wrong in the direction that loses data.
    writes: bool = False
    note: str = ""


@dataclass(frozen=True)
class ContactsProvider:
    id: str
    label: str
    authorize_url: str
    token_url: str
    api_base: str
    tiers: tuple[ScopeTier, ...]
    default_tier: str
    needs_client_secret: bool = False
    extra_auth_params: dict = field(default_factory=dict)
    note: str = ""

    def tier(self, tier_id: str = "") -> ScopeTier:
        wanted = (tier_id or "").strip() or self.default_tier
        for t in self.tiers:
            if t.id == wanted:
                return t
        for t in self.tiers:
            if t.id == self.default_tier:
                return t
        return self.tiers[0]


_GOOGLE_TIERS = (
    ScopeTier(
        id="saved", label="Mis contactos guardados",
        scopes=("https://www.googleapis.com/auth/contacts.readonly",),
        note="La agenda de Google que tú has ido guardando. Solo lectura: zaelar copia los contactos a su "
             "directorio y nunca escribe de vuelta en Google."),
    ScopeTier(
        id="saved+other", label="Guardados y «otros contactos»",
        scopes=("https://www.googleapis.com/auth/contacts.readonly",
                "https://www.googleapis.com/auth/contacts.other.readonly"),
        note="Añade las direcciones que Google recopila solo porque les has escrito alguna vez. Son muchas "
             "y casi siempre sin nombre: elígelo solo si echas en falta a alguien."),
    ScopeTier(
        id="sync", label="Sincronización en los dos sentidos",
        scopes=("https://www.googleapis.com/auth/contacts",),
        writes=True,
        note="Lo que cambies aquí también se cambia en Google. Requiere el permiso de ESCRITURA de "
             "contactos, que hay que declarar una vez en la app de Google Cloud."),
)

PROVIDERS: dict[str, ContactsProvider] = {
    # id "google-contacts", NOT "google" — the same shape `connectors/photos` already uses for
    # "google-photos". ⚠️ `connectors/registry.py::descriptors()` is a FLAT, globally-unique id space and
    # `_calendar()` already owns "google": two rows under one id is a collision the Connectors tab
    # resolves by showing whichever it saw last, so a contacts row called "google" would have EATEN the
    # calendar card. Caught by `test_the_account_row_does_not_collide_with_the_calendar_row`, which the
    # Google account row (V2-685) had already paid for once.
    "google-contacts": ContactsProvider(
        id="google-contacts", label="Google Contacts",
        authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
        token_url="https://oauth2.googleapis.com/token",
        api_base="https://people.googleapis.com/v1",
        tiers=_GOOGLE_TIERS, default_tier="saved",
        needs_client_secret=False,
        # Without access_type=offline + prompt=consent Google returns NO refresh_token at all (measured on
        # Drive, V2-557, paid again on video/photos) — the connection would silently die within the hour.
        extra_auth_params={"access_type": "offline", "prompt": "consent"},
        note="Copia tus contactos de Google al directorio de zaelar. Es una importación, no una "
             "sincronización: lo que edites aquí es tuyo y no vuelve a Google."),
}

#: Named, not requested — the same discipline as `connectors/google/services.py::FUTURE_SCOPES`.
#: `.../auth/contacts` is NOT here any more: it is a real tier now (`sync`), it is requested when the
#: operator chooses it, and pretending otherwise would be the drift this dict exists to prevent.
FUTURE_SCOPES: dict[str, tuple[str, ...]] = {
    # Domain directory lookup. Useless on a personal account, so it stays named and unrequested.
    "google-contacts": ("https://www.googleapis.com/auth/directory.readonly",),
}


def writes(provider_id: str, tier_id: str) -> bool:
    """Can this granted tier push changes BACK? The widget asks before it promises a two-way sync."""
    p = get(provider_id)
    return bool(p and p.tier(tier_id).writes)


def get(provider_id: str) -> ContactsProvider | None:
    return PROVIDERS.get((provider_id or "").strip().lower())


def ids() -> list[str]:
    return list(PROVIDERS.keys())


def public_list() -> list[dict]:
    """Redacted list for the frontend connect form. No endpoints, no credentials."""
    return [{"id": p.id, "label": p.label, "note": p.note, "default_tier": p.default_tier,
             "tiers": [{"id": t.id, "label": t.label, "note": t.note, "writes": t.writes}
                       for t in p.tiers]}
            for p in PROVIDERS.values()]
