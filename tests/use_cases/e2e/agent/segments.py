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
    # LAS TAREAS DEL ROADMAP que, resueltas, permiten probar este caso. Petición del operador (2026-08-21):
    # «puedes vincular el use case a las tareas del roadmap […] y así ahora mismo jamás lo ejecutarías, porque
    # sabrías que esas tareas están pendientes».
    #
    # `missing` ya decía en prosa qué falta; esto lo hace ACCIONABLE en dos direcciones: el arnés se NIEGA a
    # conducir el caso (conducirlo sería gastar una conversación entera para producir un fallo que ya está
    # escrito, y encima archivar una iniciativa duplicada de la que lo explica), y quien cierre esas tareas
    # tiene delante el caso que las prueba. Es la regla del operador de que los use cases son la punta de la
    # pirámide: primero se escribe lo que se espera, y el desarrollo va detrás.
    #
    # Deliberadamente MÁS ESTRECHO que el grupo `capability` entero: hay casos de ese grupo que ya se han
    # medido y están en el marcador, y gatearlos por grupo encogería el paseo en silencio e invalidaría
    # medidas que existen. Solo se gatea lo que lo declara.
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
    """Un caso ESCRITO ANTES que el mecanismo que lo hace posible, con las tareas que lo desbloquean.

    `grade` se queda VACÍO —no `no_account`— porque cuando estas tareas estén hechas el caso se juzga ENTERO:
    no le falta una credencial del operador, le falta código nuestro. Poner una nota de rebaja aquí dejaría el
    caso permanentemente juzgado a la baja el día que por fin funcione.
    """
    return Segment(CAPABILITY, "", missing, tuple(refs))


SEGMENTS: dict[str, Segment] = {
    # ── COMPLETABLE ────────────────────────────────────────────────────────────────────────────────────────
    # Information, a comparison, a plan, a widget, a reminder: the deliverable IS the answer, so there is no
    # wall to stop at. These are graded on the FULL outcome and carry no real-data note.
    "quick-fact-opening-hours": _done(),
    # Enseñar una foto se completa ENTERO: no hay muro, ni cuenta, ni nada que reservar — la entrega ES
    # el resultado. Y por eso es el caso limpio para medir DÓNDE aparece y CUÁNDO (V2-457).
    "show-real-photo-of-a-new-car": _done(),
    "remember-and-remind-deadline": _done(),
    # INI-026 B1 (2026-08-29): agenda + aviso por defecto + manipulación por voz — todo dentro del motor,
    # sin login, sin pago, sin tercero: completable de punta a punta.
    "dentist-appointment-into-agenda": _done(),
    # INI-026 A8bis-A (2026-08-29): buscar un HECHO FUTURO fuera (fecha de estreno), decirlo con su fuente y
    # dejar el aviso montado. Completable: la búsqueda es pública, no hay credencial, ni pago, ni tercero.
    "find-a-future-release-and-remind-me": _done(),
    "build-workout-tracker-widget": _done(),
    "three-tasks-at-once": _done(),
    # Música y vídeo (2026-08-26). `completable` según la ÚNICA pregunta de este módulo, hecha a la frase
    # de apertura: «ponme música» y «pon el vídeo de X» NO piden credencial, tarjeta, llamada ni un objeto
    # real que no exista. Que el plató no tenga Spotify conectado no los mueve a `credentials`, y ésa es la
    # distinción que este fichero existe para no perder: el camino sin cuenta (audio oculto de YouTube) es
    # un camino de PRODUCTO, no una versión degradada esperando a que el operador desbloquee algo. Si
    # alguien conecta Spotify mañana, el caso mide la otra rama; no cambia de segmento.
    "play-music-and-build-playlist": _done(),
    "watch-a-video-not-listen-to-it": _done(),
    # Segunda tanda (2026-08-27). Misma pregunta a la frase de apertura y misma respuesta: pegar dos enlaces
    # y pedir vídeos sobre un tema no exigen credencial, tarjeta, llamada ni un objeto real que no exista.
    # `build-a-video-playlist-from-links` NO es «caso de futuro» — su mecanismo llegó con V2-366 (add /
    # play_item / next / previous), así que se conduce ya; escribir un caso ANTES que su mecanismo es la
    # norma de la casa, pero gatearlo cuando el mecanismo YA está sería medir de menos.
    "build-a-video-playlist-from-links": _done(),
    "find-videos-on-a-topic-no-ai-slop": _done(),
    # ── CASOS DE FUTURO: escritos antes que su mecanismo, y GATEADOS por él ────────────────────────────
    # No es «capability» en el sentido viejo (una capacidad que nadie ha planificado): es una capacidad con
    # su iniciativa abierta y su fase concreta. Por eso llevan `blocked_by` y el arnés se niega a
    # conducirlos — el veredicto ya está escrito en la iniciativa, y gastar la conversación solo añadiría
    # una ronda duplicada al paraguas.
    # DESGATEADO 2026-08-21: V2-259 completa (F1+F2+F3+F4, `b8a1415` + `f3052f9`). El caso deja de ser de
    # futuro y pasa a conducirse en cada paseo como cualquier otro — que es el punto entero de haberlo escrito
    # antes que el mecanismo: el listón se fijó cuando todavía no se sabía qué iba a hacer el código.
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
    # Un dato del mundo con FUENTE: la entrega ES la respuesta (tiempo y distancia reales, con tráfico), así que
    # no hay muro que la pare — ni cuenta, ni tarjeta, ni capacidad que falte. Se puntúa el resultado ENTERO, y
    # ahí está su gracia: si el agente contesta «unas 2 horas» de memoria y la hoja está vacía, el caso FALLA.
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


def blocked_by(scenario_id: str) -> tuple[str, ...]:
    """Las tareas de roadmap pendientes que gatean este caso. Vacío = se puede conducir hoy."""
    seg = segment_of(scenario_id)
    return seg.blocked_by if seg else ()


# A `completable` case whose deliverable is NOT findings-on-screen. Everything else in that segment ends in a
# shortlist the operator can look at, and gets the findings contract (`derived._DELIVERABLE_FINDINGS`).
#   · quick-fact-opening-hours    → a fact answered IN the turn by `web_search`; escalating is itself the
#                                   failure (V2-022), so demanding a results sheet would invert the case.
#   · remember-and-remind-deadline → lands in memory + the scheduler, verified through `scheduled_jobs`.
#   · build-workout-tracker-widget → the deliverable IS a new widget; here creating one is the point, not a bug.
#   · three-tasks-at-once          → judged on COORDINATION, not on any one task finishing.
#   · play-music-and-build-playlist → lo que se entrega es SONIDO y una lista en el store del widget; pedirle
#                                     una hoja de resultados premiaría enseñar candidatos en vez de poner música.
#   · watch-a-video-not-listen-to-it → lo que se entrega es un vídeo EN PANTALLA; el widget `youtube` ES la
#                                     superficie, así que una hoja aparte sería una segunda pantalla de más.
FINDINGS_EXEMPT = {
    "quick-fact-opening-hours",
    "remember-and-remind-deadline",
    # · dentist-appointment-into-agenda → lo entregado es una CITA en la agenda con su aviso, no una lista
    #   de opciones: la superficie es el widget de agenda + scheduled_jobs, no la hoja de resultados.
    "dentist-appointment-into-agenda",
    # · find-a-future-release-and-remind-me → lo entregado es UN hecho (una fecha) y su aviso, no una lista
    #   de candidatos: el presupuesto de hallazgos no aplica.
    "find-a-future-release-and-remind-me",
    "build-workout-tracker-widget",
    "three-tasks-at-once",
    "play-music-and-build-playlist",
    "watch-a-video-not-listen-to-it",
    # · build-a-video-playlist-from-links → lo entregado es una LISTA DENTRO del widget de vídeo, que ya es
    #   la superficie; una hoja de resultados al lado sería una segunda pantalla contando lo mismo.
    "build-a-video-playlist-from-links",
    # · show-real-photo-of-a-new-car → lo entregado es la FOTO, y su superficie es el visor `imagenes`. Es la
    #   misma frontera que la línea de arriba, un medio más allá (V2-402 la fijó para el vídeo, V2-457 para la
    #   imagen): lo que se VE tiene su widget, la hoja es para INFORMACIÓN. Darle el contrato de hallazgos le
    #   diría al juez que espere una lista en la hoja — o sea, le pediría al agente exactamente el defecto que
    #   este caso existe para medir.
    "show-real-photo-of-a-new-car",
}
# Y el que SÍ entrega hallazgos, dicho para que no se arrastre por parecido temático: en
# `find-videos-on-a-topic-no-ai-slop` el operador pidió ELEGIR ÉL entre 3 o 4 opciones con nombre. Eso es
# exactamente una lista corta que mirar, así que le toca el contrato de hallazgos como a cualquier búsqueda
# — que sea multimedia no lo exime. Poner un vídeo a reproducir ahí sería contestar otra pregunta.


def delivers_findings(scenario_id: str) -> bool:
    """True when a good answer to this case is a shortlist of real options ON SCREEN."""
    return is_completable(scenario_id) and bare(scenario_id) not in FINDINGS_EXEMPT
