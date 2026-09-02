"""Which use cases can be carried out END TO END today, and what blocks the rest.

Asked for by the operator on 2026-08-19: *“separate from the group the cases we cannot test now because they need
specific user credentials, sites that must be accessed, or operations that must be performed […] and leave in a
list only the use cases that can actually be carried out from start to finish”*.

Before this module the catalog had a GRADING adjustment (`derived.NO_ACCOUNT` / `derived.NO_BOOKING`) but no
segmentation, and the two are not the same question:

  · grading asks «what can this run honestly be scored on?»
  · segmentation asks «is this case runnable end to end at all, and if not, WHO unblocks it?»

Keeping only the first produced two measured defects that this module exists to prevent:

1. **The US twin escaped.** `data_scope()` is keyed by the BARE case id, and `restaurant-tonight-madrid`'s twin
   is `restaurant-tonight-nyc` — a DIFFERENT bare id — so the ES case carried the real-data limit and the US
   one was graded as if a table could be booked. A pair that differs only in market must never differ in what
   it can honestly be asked to do.
2. **A note contradicting its own case.** `search-buy-guitar` asks “Find me a second-hand acoustic guitar for
   less than €150” — a search, nothing else — and carried “the only thing that cannot be done is complete the
   purchase […] stopping at the wall and SAYING SO is the correct behavior, a 5”. That REWARDS asking for a card the
   user never mentioned instead of delivering the list. The blocker was in the case id (`search-buy-*`) and in
   the catalog's `expected`, not in the request.

So the segment is decided by ONE question, asked of the OPENING LINE and nothing else: **does what the user
actually asked for require a credential, a payment method, a phone call, or a real object that does not
   exist?** “Find me a second-hand monitor” does not. “Find me the book and buy it for me” does.

THREE groups, not two — and the split between the last two is the operator's next decision, which is why it is
worth the extra name:

  · `completable` — runnable start to finish today. Nothing is missing. This is the list to test.
  · `credentials` — the OPERATOR unblocks it, by providing an account, a card, a phone, or a real bill /
    subscription / prescription / flight to act on.
  · `capability`  — WE unblock it, by building something: resolving a contact (V2-523, written and not
    built), placing a phone call, a second agent to negotiate with, or a signal nobody measures. No
    credential the operator could hand over would help. (Sending on WhatsApp/Telegram was on this list
    until 2026-08-31 and came off it: V2-521 built it.)

Closed inventory ON PURPOSE, and hand-edited: `tests/use_cases/unit/test_segments.py` fails if a scenario in
`scenarios.all_scenarios()` is not classified here, so a case added tomorrow cannot silently land in no group
(same reason `test_observer_categories.py` exists for observability kinds). Deriving the group from a heuristic
over the wording was considered and rejected: “reserve it for me” vs “find it for me” is a one-word difference that decides
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
    # ROADMAP TASKS that, once completed, make it possible to test this case. Operator request (2026-08-21):
    # “can you link the use case to the roadmap tasks […] so that right now you would never run it, because
    # you would know those tasks are pending”.
    #
    # `missing` already said in prose what is missing; this makes it ACTIONABLE in two directions: the harness
    # REFUSES to run the case (running it would spend an entire conversation producing a failure that is already
    # written, and then archive a duplicate initiative explaining it), and whoever closes those tasks has the
    # case that tests them in front of them. It is the operator’s rule that use cases are the tip of the pyramid:
    # first write what is expected, and development follows.
    #
    # Deliberately NARROWER than the entire `capability` group: some cases in that group have already been
    # measured and are on the scoreboard, and gating them by group would silently shrink the run and invalidate
    # existing measurements. Only cases that declare it are gated.
    blocked_by: tuple[str, ...] = ()


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


def _future(missing: str, *refs: str) -> Segment:
    """A case WRITTEN BEFORE the mechanism that makes it possible, with the tasks that unblock it.

    `grade` stays EMPTY —not `no_account`— because once these tasks are done the case is judged in FULL:
    it is not missing an operator credential; it is missing our code. Putting a downgrade note here would leave
    the case permanently judged down on the day it finally works.
    """
    return Segment(CAPABILITY, "", missing, tuple(refs))


SEGMENTS: dict[str, Segment] = {
    # ── COMPLETABLE ────────────────────────────────────────────────────────────────────────────────────────
    # Information, a comparison, a plan, a widget, a reminder: the deliverable IS the answer, so there is no
    # wall to stop at. These are graded on the FULL outcome and carry no real-data note.
    "quick-fact-opening-hours": _done(),
    # Showing a photo is completed in FULL: there is no wall, account, or anything to reserve — the deliverable IS
    # the result. That is why it is the clean case for measuring WHERE it appears and WHEN (V2-457).
    "show-real-photo-of-a-new-car": _done(),
    "remember-and-remind-deadline": _done(),
    # INI-026 B1 (2026-08-29): calendar + default alert + voice manipulation — all within the engine,
    # with no login, payment, or third party: completable end to end.
    "dentist-appointment-into-agenda": _done(),
    # INI-026 A8bis-A (2026-08-29): look up a FUTURE FACT externally (release date), state it with its source,
    # and set up the alert. Completable: the search is public; there is no credential, payment, or third party.
    "find-a-future-release-and-remind-me": _done(),
    # INI-026, the center of v1 after the 2026-08-29 directive: the agent should remember who you are. Everything
    # is within the engine (seeding + recall + one response), with no credential, payment, or third party.
    "knows-who-i-am-without-being-told-again": _done(),
    "build-workout-tracker-widget": _done(),
    "three-tasks-at-once": _done(),
    # Music and video (2026-08-26). `completable` according to this module’s SINGLE question, asked of the opening
    # line: “play me music” and “play video X” do NOT request a credential, card, call, or nonexistent real object.
    # The fact that the studio has no Spotify connection does not move them to `credentials`; that is the
    # distinction this file exists to preserve: the account-free path (hidden YouTube audio) is a PRODUCT path,
    # not a degraded version waiting for the operator to unblock something. If someone connects Spotify tomorrow,
    # the case measures the other branch; its segment does not change.
    "play-music-and-build-playlist": _done(),
    "watch-a-video-not-listen-to-it": _done(),
    # Second batch (2026-08-27). Same question asked of the opening line and same answer: pasting two links
    # and requesting videos about a topic do not require a credential, card, call, or nonexistent real object.
    # `build-a-video-playlist-from-links` is NOT a “future case” — its mechanism arrived with V2-366 (add /
    # play_item / next / previous), so it is run now; writing a case BEFORE its mechanism is the house rule,
    # but gating it when the mechanism is ALREADY there would under-measure.
    "build-a-video-playlist-from-links": _done(),
    "find-videos-on-a-topic-no-ai-slop": _done(),
    # Messaging as the primary widget + calendar lifecycle (V2-521/V2-473, 2026-08-31). All five are
    # `completable` under this module’s SINGLE question, asked of the opening line: none requests a credential
    # missing to JUDGE IT — precisely because their checks judge behavior against the studio’s real state
    # (unlinked WhatsApp → the truthful outcome; email → the panel SETUP, never the connection). It is the same
    # distinction that left `play-music-and-build-playlist` completable: the account-free path is a PRODUCT path,
    # not a degraded version waiting for an unblock.
    "show-my-messages": _done(),
    "connect-email-by-voice": _done(),
    "dictate-a-reply-honestly": _done(),
    "agenda-appointment-lifecycle": _done(),
    "what-does-my-week-look-like": _done(),
    # ── FUTURE CASES: written before their mechanism, and GATED by it ────────────────────────────
    # This is not `capability` in the old sense (a capability nobody has planned): it is a capability with
    # an open initiative and a concrete phase. That is why these have `blocked_by` and the harness refuses to
    # run them — the verdict is already written in the initiative, and spending the conversation would only add
    # a duplicate round to the umbrella.
    # UNGATED 2026-08-21: V2-259 complete (F1+F2+F3+F4, `b8a1415` + `f3052f9`). The case is no longer future
    # work and is run on every pass like any other — the whole point of writing it before the mechanism is that
    # the bar was set when nobody yet knew what the code would do.
    "two-searches-two-sheets": _done(),
    "repeat-a-finished-search": _future(
        "los candidatos de una búsqueda terminada no sobreviven al encargo siguiente: la hoja se ESTRENA "
        "y nada los guarda, así que repetir la misma petición no puede resolverse con lo que ya se tenía",
        "V2-260 F1", "V2-260 F2"),
    "candidates-already-known": _future(
        "no existe catálogo de candidatos por categoría: lo único que sobrevive a una investigación es su "
        "BRIEF (`research.remember_round`, TTL 6 h) y no sus resultados",
        "V2-260 F2", "V2-260 F3"),
    "change-the-criteria-not-the-search": _future(
        "sin catálogo no hay nada que enseñar ante una petición genérica, ni forma de distinguir «enséñame "
        "lo que tienes» de «búscame otra cosa», ni de que lo nuevo se sume a lo viejo",
        "V2-260 F2", "V2-260 F3", "V2-260 F4"),
    # searches — the user asked to FIND, never to buy
    "search-buy-used-car": _done(),
    "search-buy-motorcycle": _done(),
    "search-buy-bicycle": _done(),
    "search-buy-camera": _done(),
    "search-buy-guitar": _done(),
    "search-secondhand-monitor": _done(),
    "cheapest-monitor": _done(),
    # DEEP_SEARCH_SET additions (V2-556, operator 2026-09-02) — every one asks to FIND on a real
    # marketplace with its own filters and pagination; nothing to reserve, pay or sign into, so the
    # FULL outcome is graded. Same doctrine as search-buy-guitar above: the blocker must never be
    # smuggled in by the id or the expected text.
    "search-buy-boat-multicountry": _done(),
    "search-buy-surfboard": _done(),
    "search-rent-apartment": _done(),
    "search-buy-apartment": _done(),
    "search-buy-laptop": _done(),
    "search-buy-phone": _done(),
    "search-buy-tv": _done(),
    "search-buy-sofa": _done(),
    "search-buy-washing-machine": _done(),
    "search-buy-watch": _done(),
    "search-buy-sneakers": _done(),
    "search-buy-ski-gear": _done(),
    "search-buy-camper": _done(),
    "search-restaurant-occasion": _done(),
    "search-buy-vinyl": _done(),
    "search-buy-stroller": _done(),
    "search-buy-ebike": _done(),
    "search-holiday-rental": _done(),
    # A sourced fact about the world: the deliverable IS the answer (real time and distance, with traffic), so
    # there is no wall to stop it — no account, card, or missing capability. The FULL result is scored, and that
    # is the point: if the agent answers “about 2 hours” from memory and the sheet is empty, the case FAILS.
    "driving-time-with-traffic": _done(),
    "find-best-hotel-city": _done(),
    "hotel-under-15-days": _done(),
    # maximum complexity, kept for last: several filters that must ALL hold at once, some of them
    # behind the site's own controls rather than in the text of a query
    "hotel-many-filters-at-once": _done(),
    "used-car-search-wallapop": _done(),
    "house-search-los-angeles": _done(),
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
    # The sending channel is NO LONGER missing (V2-521, 2026-08-31); what is missing is who to send it to.
    "split-dinner-bill-friends": _cap("resolución de contactos: a quién se le manda (V2-523, sin construir)"),
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
    # tier 7 — WhatsApp/Telegram. Until 2026-08-31 what was missing here was SENDING, and no longer is: V2-521
    # made both connectors drain `msg.reply` and deliver it. What is still missing is the NEXT step, and it must
    # be stated precisely or whoever picks this up will build what already exists: we know how to send a message
    # over WhatsApp, but not to WHOM — “Pedro’s agent” does not resolve to any handle because the contact book
    # does not exist (V2-523). `missing` is quoted literally in the judge’s note, so an outdated sentence there
    # is not cosmetic: it downgrades the case for the wrong reason.
    "coordinate-lunch-whatsapp": _cap("resolver «el agente de Pedro» a un contacto real (V2-523, sin construir)"),
    "coordinate-dinner-whatsapp": _cap("resolver «el agente de Alex» a un contacto real (V2-523, sin construir)"),
    "group-plan-three-friends": _cap("resolver tres contactos y sus canales (V2-523, sin construir)"),
    "realtime-eta-share": _cap("resolver el contacto y una señal de «he salido de casa» que nadie mide"),
    "split-trip-telegram": _cap("resolver el contacto en Telegram (V2-523, sin construir)"),
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


def blocked_by(scenario_id: str) -> tuple[str, ...]:
    """The pending roadmap tasks that gate this case. Empty = it can be run today."""
    seg = segment_of(scenario_id)
    return seg.blocked_by if seg else ()


# A `completable` case whose deliverable is NOT findings-on-screen. Everything else in that segment ends in a
# shortlist the operator can look at, and gets the findings contract (`derived._DELIVERABLE_FINDINGS`).
#   · quick-fact-opening-hours    → a fact answered IN the turn by `web_search`; escalating is itself the
#                                   failure (V2-022), so demanding a results sheet would invert the case.
#   · remember-and-remind-deadline → lands in memory + the scheduler, verified through `scheduled_jobs`.
#   · build-workout-tracker-widget → the deliverable IS a new widget; here creating one is the point, not a bug.
#   · three-tasks-at-once          → judged on COORDINATION, not on any one task finishing.
#   · play-music-and-build-playlist → what is delivered is SOUND and a list in the widget store; requesting a
#                                     results sheet would reward showing candidates instead of playing music.
#   · watch-a-video-not-listen-to-it → what is delivered is a video ON SCREEN; the `youtube` widget IS the
#                                     surface, so a separate sheet would be an unnecessary second screen.
FINDINGS_EXEMPT = {
    "quick-fact-opening-hours",
    "remember-and-remind-deadline",
    # · dentist-appointment-into-agenda → what is delivered is an APPOINTMENT in the calendar with its alert,
    #   not a list of options: the surface is the calendar widget + scheduled_jobs, not the results sheet.
    "dentist-appointment-into-agenda",
    # · find-a-future-release-and-remind-me → what is delivered is ONE fact (a date) and its alert, not a list
    #   of candidates: the findings budget does not apply.
    "find-a-future-release-and-remind-me",
    # · knows-who-i-am-without-being-told-again → what is delivered is a CONVERSATION that applies what it already
    #   knew; there are no findings to budget.
    "knows-who-i-am-without-being-told-again",
    "build-workout-tracker-widget",
    "three-tasks-at-once",
    "play-music-and-build-playlist",
    "watch-a-video-not-listen-to-it",
    # · build-a-video-playlist-from-links → what is delivered is a LIST WITHIN the video widget, which is already
    #   the surface; a results sheet beside it would be a second screen counting the same thing.
    "build-a-video-playlist-from-links",
    # · show-real-photo-of-a-new-car → what is delivered is the PHOTO, and its surface is the `imagenes` viewer.
    #   It is the same boundary as the line above, one medium further (V2-402 set it for video, V2-457 for the
    #   image): what you SEE has its widget, while the sheet is for INFORMATION. Giving it the findings contract
    #   would tell the judge to expect a list in the sheet — asking the agent for exactly the defect this case
    #   exists to measure.
    "show-real-photo-of-a-new-car",
    # · show-my-messages / connect-email-by-voice / dictate-a-reply-honestly → the surface is the messaging
    #   widget (its list, channel panel, and reply confirmation); a results sheet beside it would be the same
    #   second screen already rejected for music and video.
    "show-my-messages",
    "connect-email-by-voice",
    "dictate-a-reply-honestly",
    # · agenda-appointment-lifecycle / what-does-my-week-look-like → what is delivered is APPOINTMENTS in the
    #   calendar (and an honest reading of them), the same boundary as dentist-appointment-into-agenda.
    "agenda-appointment-lifecycle",
    "what-does-my-week-look-like",
}
# And the one that DOES deliver findings, stated so it is not dragged along by thematic similarity: in
# `find-videos-on-a-topic-no-ai-slop` the operator asked to CHOOSE among 3 or 4 named options. That is exactly
# a shortlist to inspect, so it gets the findings contract like any search — being multimedia does not exempt it.
# Playing a video there would answer a different question.


def delivers_findings(scenario_id: str) -> bool:
    """True when a good answer to this case is a shortlist of real options ON SCREEN."""
    return is_completable(scenario_id) and bare(scenario_id) not in FINDINGS_EXEMPT
