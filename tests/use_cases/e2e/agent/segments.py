"""Which use cases can be carried out END TO END today, and what blocks the rest.

Asked for by the operator on 2026-08-19: *«separar del grupo las que no podamos probar ahora porque necesitan
credenciales específicas del usuario, de los sites a los que hay que entrar o de las operaciones que hay que
hacer […] y dejar en una lista solo los use cases que sí van a poder llevarse a cabo de inicio a fin»*.

Before this module the catalog had a GRADING adjustment (`derived.NO_ACCOUNT` / `derived.NO_BOOKING`) but no
segmentation, and the two are not the same question:

  · grading asks «what can this run honestly be scored on?»
  · segmentation asks «is this case runnable end to end at all, and if not, WHO unblocks it?»

Keeping only the first produced two measured defects that this module exists to prevent:

1. **The US twin escaped.** `data_scope()` is keyed by the BARE case id, and `restaurant-tonight-madrid`'s twin
   is `restaurant-tonight-nyc` — a DIFFERENT bare id — so the ES case carried the real-data limit and the US
   one was graded as if a table could be booked. A pair that differs only in market must never differ in what
   it can honestly be asked to do.
2. **A note contradicting its own case.** `search-buy-guitar` asks «Encuéntrame una guitarra acústica de
   segunda mano por menos de 150€» — a search, nothing else — and carried «lo que no se puede es cerrar la
   compra […] pararse en el muro DICIÉNDOLO es la conducta correcta, un 5». That REWARDS asking for a card the
   user never mentioned instead of delivering the list. The blocker was in the case id (`search-buy-*`) and in
   the catalog's `expected`, not in the request.

So the segment is decided by ONE question, asked of the OPENING LINE and nothing else: **does what the user
actually asked for require a credential, a payment method, a phone call, or a real object that does not
exist?** «Búscame un monitor de segunda mano» does not. «Búscame el libro y cómpramelo» does.

THREE groups, not two — and the split between the last two is the operator's next decision, which is why it is
worth the extra name:

  · `completable` — runnable start to finish today. Nothing is missing. This is the list to test.
  · `credentials` — the OPERATOR unblocks it, by providing an account, a card, a phone, or a real bill /
    subscription / prescription / flight to act on.
  · `capability`  — WE unblock it, by building something: sending on WhatsApp/Telegram, resolving a contact
    (V2-052, designed and not built), placing a phone call, a second agent to negotiate with, or a signal
    nobody measures. No credential the operator could hand over would help.

Closed inventory ON PURPOSE, and hand-edited: `tests/use_cases/unit/test_segments.py` fails if a scenario in
`scenarios.all_scenarios()` is not classified here, so a case added tomorrow cannot silently land in no group
(same reason `test_observer_categories.py` exists for observability kinds). Deriving the group from a heuristic
over the wording was considered and rejected: «resérvame» vs «búscame» is a one-word difference that decides
whether a case is testable, and a regex getting it wrong is invisible until a whole batch is graded against the
wrong bar.
"""
from __future__ import annotations

from dataclasses import dataclass

COMPLETABLE = "completable"
CREDENTIALS = "credentials"
CAPABILITY = "capability"


@dataclass(frozen=True)
class Segment:
    group: str      # completable | credentials | capability
    grade: str      # "" = grade the whole outcome · "no_account" · "no_booking" (see derived.py for the notes)
    missing: str    # what is missing, concretely — it is quoted verbatim into the judge's note


def _done() -> Segment:
    return Segment(COMPLETABLE, "", "")


def _cred_search(missing: str) -> Segment:
    """The search half is real and graded whole; only closing the deal needs the operator."""
    return Segment(CREDENTIALS, "no_booking", missing)


def _cred_none(missing: str) -> Segment:
    """There is nothing to act on at all — the honest maximum is saying precisely what is missing."""
    return Segment(CREDENTIALS, "no_account", missing)


def _cap(missing: str) -> Segment:
    return Segment(CAPABILITY, "no_account", missing)


SEGMENTS: dict[str, Segment] = {
    # ── COMPLETABLE ────────────────────────────────────────────────────────────────────────────────────────
    # Information, a comparison, a plan, a widget, a reminder: the deliverable IS the answer, so there is no
    # wall to stop at. These are graded on the FULL outcome and carry no real-data note.
    "quick-fact-opening-hours": _done(),
    "remember-and-remind-deadline": _done(),
    "build-workout-tracker-widget": _done(),
    "three-tasks-at-once": _done(),
    # searches — the user asked to FIND, never to buy
    "search-buy-used-car": _done(),
    "search-buy-motorcycle": _done(),
    "search-buy-bicycle": _done(),
    "search-buy-camera": _done(),
    "search-buy-guitar": _done(),
    "search-secondhand-monitor": _done(),
    "cheapest-monitor": _done(),
    "find-best-hotel-city": _done(),
    "hotel-under-15-days": _done(),
    "find-direct-flight-budget": _done(),
    "find-concert-tickets": _done(),
    "best-rated-rental-car": _done(),
    "rental-car-automatic-airport": _done(),
    "best-plumber-same-day": _done(),
    "weekend-barber-availability": _done(),
    # comparisons that end in a recommendation
    "compare-insurance-quotes": _done(),
    "compare-broadband-plans": _done(),
    "compare-phone-plans": _done(),
    # discovery / curation — infer what the operator likes and bring a catalog of options
    "things-to-do-nearby-weekend": _done(),
    "kid-friendly-activity-nearby": _done(),
    "weekend-plan-barcelona": _done(),
    "weekend-theatre-sevilla": _done(),
    "weekend-adventure-sports-bilbao": _done(),
    "weekend-motor-events": _done(),
    "bored-in-sf-this-weekend": _done(),
    "weekend-adventure-sports-bay-area": _done(),

    # ── CREDENTIALS · the search is real, closing it is not ────────────────────────────────────────────────
    "restaurant-tonight-madrid": _cred_search("cerrar la mesa (teléfono o cuenta en la plataforma)"),
    "restaurant-tonight-nyc": _cred_search("cerrar la mesa (teléfono o cuenta en la plataforma)"),
    "book-hotel-night-known": _cred_search("cerrar la reserva (cuenta y tarjeta)"),
    "book-barber-slot": _cred_search("cerrar la cita (teléfono o cuenta)"),
    "best-pediatric-dentists": _cred_search("cerrar la cita (teléfono o cuenta)"),
    "find-theatre-tickets": _cred_search("comprar las entradas (cuenta y tarjeta)"),
    "search-buy-book": _cred_search("cerrar la compra (cuenta y tarjeta)"),
    "compare-flights-madrid-lisboa": _cred_search("comprar el vuelo (cuenta y tarjeta)"),
    "compare-flights-sf-austin": _cred_search("comprar el vuelo (cuenta y tarjeta)"),
    "itv-before-deadline": _cred_search("cerrar la cita de la ITV (cuenta de la estación, matrícula real)"),
    "smog-check-before-deadline": _cred_search("cerrar la cita (cuenta del taller, matrícula real)"),
    "renew-passport-before-expiry": _cred_search("cerrar la cita (cl@ve / cuenta administrativa real)"),
    "found-next-apartment": _cred_search("cerrar visitas (contacto real con las agencias)"),
    "weekend-trip-san-sebastian": _cred_search("cerrar tren/hotel/mesa (cuentas y tarjeta)"),
    "weekend-trip-austin": _cred_search("cerrar vuelo/hotel/cena (cuentas y tarjeta)"),

    # ── CREDENTIALS · nothing to act on until the operator provides it ─────────────────────────────────────
    "pay-known-bill": _cred_none("una factura real y acceso al proveedor/banco"),
    "buy-known-product": _cred_none("una cuenta con lista de deseos y un medio de pago"),
    "reorder-prescription": _cred_none("una farmacia habitual y una receta real"),
    "renew-gym-membership": _cred_none("una cuota de gimnasio real y una cuenta en su web"),
    "gym-membership-no-silent-renew": _cred_none("una cuota de gimnasio real y su fecha de renovación"),
    "cancel-subscription-before-charge": _cred_none("una suscripción real y acceso a esa cuenta"),
    "cancel-trial-before-it-charges": _cred_none("una prueba gratuita real y acceso a esa cuenta"),
    "track-package-reschedule": _cred_none("un número de seguimiento o acceso al email del transportista"),
    "rebook-delayed-flight-now": _cred_none("un vuelo real y su localizador"),
    "watch-flight-rebook-automatically": _cred_none("un vuelo real y su localizador"),
    "track-price-drop-buy": _cred_none("un medio de pago y la ficha real del producto a vigilar"),
    "moms-birthday-flowers-onetime": _cred_none("la dirección real y un medio de pago"),
    "moms-birthday-flowers-recurring": _cred_none("la dirección real y un medio de pago"),
    "file-expense-report": _cred_none("los tickets del viaje y el correo de administración"),
    "clean-and-reply-inbox": _cred_none("un conector de email configurado con la cuenta del operador"),
    "archive-newsletters": _cred_none("un conector de email configurado con la cuenta del operador"),

    # ── CAPABILITY · no credential unblocks these; we have to build something ──────────────────────────────
    "negotiate-lower-phone-bill": _cap("la capacidad de LLAMAR por teléfono, que no existe en el motor"),
    "grocery-restock-reactive": _cap("una señal de consumo (nadie mide la leche que queda) y una cuenta de compra"),
    "split-dinner-bill-friends": _cap("resolución de contactos y un canal de envío (V2-052, diseñado sin construir)"),
    # tier 6 — agent-to-agent over email: needs BOTH an email connector and a second agent to negotiate with.
    # The second agent is the harder half: the harness's DRIVE model plays the USER, and nothing in the suite
    # can stand in for a peer's agent, so these cannot be exercised even with the connector configured.
    "coordinate-lunch-with-pedro": _cap("resolución de contactos y un agente PAR con el que negociar"),
    "coordinate-dinner-with-alex": _cap("resolución de contactos y un agente PAR con el que negociar"),
    "confirm-restaurant-reservation-together": _cap("un agente PAR con el que negociar por email"),
    "confirm-restaurant-together": _cap("un agente PAR con el que negociar por email"),
    "plan-joint-trip-with-friend": _cap("un agente PAR con el que negociar por email"),
    "reschedule-meetup-conflict": _cap("un agente PAR con el que negociar por email"),
    "resolve-meetup-conflict": _cap("un agente PAR con el que negociar por email"),
    "split-airbnb-with-marta": _cap("un agente PAR con el que negociar por email"),
    "split-airbnb-with-jordan": _cap("un agente PAR con el que negociar por email"),
    # tier 7 — WhatsApp/Telegram: both connectors are READ-ONLY today (see cases_data.py's tier list), so the
    # very first step of the case is impossible, before contacts or peers even come up.
    "coordinate-lunch-whatsapp": _cap("ENVIAR por WhatsApp (el conector es de solo lectura hoy)"),
    "coordinate-dinner-whatsapp": _cap("ENVIAR por WhatsApp (el conector es de solo lectura hoy)"),
    "group-plan-three-friends": _cap("ENVIAR por WhatsApp (el conector es de solo lectura hoy)"),
    "realtime-eta-share": _cap("ENVIAR por WhatsApp (el conector es de solo lectura hoy)"),
    "split-trip-telegram": _cap("ENVIAR por Telegram (el conector es de solo lectura hoy)"),
}


def bare(scenario_id: str) -> str:
    """The catalog id behind a scenario id, dropping the `__es` / `__us` locale suffix."""
    return scenario_id.split("__")[0]


def segment_of(scenario_id: str) -> Segment | None:
    """The segment for a scenario (or its bare case id). None means UNCLASSIFIED — a bug, not a state."""
    return SEGMENTS.get(bare(scenario_id))


def group_of(scenario_id: str) -> str:
    seg = segment_of(scenario_id)
    return seg.group if seg else ""


def is_completable(scenario_id: str) -> bool:
    return group_of(scenario_id) == COMPLETABLE


# A `completable` case whose deliverable is NOT findings-on-screen. Everything else in that segment ends in a
# shortlist the operator can look at, and gets the findings contract (`derived._DELIVERABLE_FINDINGS`).
#   · quick-fact-opening-hours    → a fact answered IN the turn by `web_search`; escalating is itself the
#                                   failure (V2-022), so demanding a results sheet would invert the case.
#   · remember-and-remind-deadline → lands in memory + the scheduler, verified through `scheduled_jobs`.
#   · build-workout-tracker-widget → the deliverable IS a new widget; here creating one is the point, not a bug.
#   · three-tasks-at-once          → judged on COORDINATION, not on any one task finishing.
FINDINGS_EXEMPT = {
    "quick-fact-opening-hours",
    "remember-and-remind-deadline",
    "build-workout-tracker-widget",
    "three-tasks-at-once",
}


def delivers_findings(scenario_id: str) -> bool:
    """True when a good answer to this case is a shortlist of real options ON SCREEN."""
    return is_completable(scenario_id) and bare(scenario_id) not in FINDINGS_EXEMPT
