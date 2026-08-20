"""Backlog data for the ``use_cases`` suite: real-world ES/US task scenarios.

This module is the single source of truth for the catalog. It is intentionally
plain data (no pytest, no runner) — see ``tests/use_cases/CASES.md`` for the
tier definitions and the human-readable rendering of this same list, and
``tests/use_cases/catalog.py`` for how it is exposed to the Observatory.

Every entry is a backlog case: none is wired to a runner yet. They get
promoted to executable cases one at a time in future changes, each picking
the runner shape (browser automation, an agent-headless live scenario, an
email-based multi-agent exchange, …) that fits that specific task.

Tiers (easy -> hard):
  1 = bounded single-site action (target already named, no comparison)
  2 = search + compare + choose (no fixed target)
  3 = multi-step single-domain task with a real deadline/follow-up
  4 = cross-domain orchestration (multiple providers/domains in one ask)
  5 = standing/reactive task (proactive, memory-triggered, no single turn completes it)
  6 = multi-agent coordination over email (the only connector that can send today)
  7 = multi-agent coordination over WhatsApp/Telegram (BLOCKED: neither
      connector can send yet, and contact resolution is only designed, not
      built — see V2-052-contactos-red-canales.md)
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class UseCase:
    id: str
    locale: str  # "es" | "us"
    tier: int
    title: str
    utterance: str
    expected: str
    status: str = "backlog"  # "backlog" | "blocked" | "promoted" (has a real dynamic-harness runner)
    depends_on: tuple[str, ...] = field(default_factory=tuple)
    notes: str = ""


_BLOCKED_DEPENDENCIES = (
    "connectors/whatsapp and connectors/telegram send capability (both are read-only today)",
    "V2-052 contact resolution (.meshkore/roadmap/initiatives/V2-052-contactos-red-canales.md, "
    "design closed, not built)",
    "Z∴ agent-message tagging convention (recorded in CASES.md, not implemented)",
)

CASES: list[UseCase] = [
    # --- ES / tier 1: bounded single-site action -----------------------------------------
    UseCase("restaurant-tonight-madrid", "es", 1, "Book a known restaurant tonight",
            "Resérvame mesa para 2 esta noche a las 21:30 en Casa Lucio.",
            "A table for 2 is booked at Casa Lucio for 21:30 tonight — verified against real system state "
            "(worker signal), not just the agent's claim — see tests/use_cases/e2e/agent/scenarios.py.",
            status="promoted"),
    UseCase("cancel-subscription-before-charge", "es", 1, "Cancel a subscription before renewal",
            "Cancela mi suscripción a Netflix antes de que me cobren el día 15.",
            "The Netflix subscription is cancelled before the next billing date."),
    UseCase("reorder-prescription", "es", 1, "Reorder a known prescription",
            "Pide la reposición de mi receta de la farmacia de siempre.",
            "The usual prescription is reordered from the operator's regular pharmacy."),
    UseCase("pay-known-bill", "es", 1, "Pay a known bill",
            "Paga la factura de la luz de este mes antes del día 5.",
            "This month's electricity bill is paid before the 5th."),
    UseCase("renew-gym-membership", "es", 1, "Renew a known gym membership",
            "Renueva mi cuota del gimnasio de este mes.",
            "This month's gym membership fee is renewed."),
    UseCase("book-barber-slot", "es", 1, "Book the usual barber",
            "Resérvame hora en la peluquería de siempre para el sábado por la mañana.",
            "A Saturday-morning slot is booked at the operator's usual barber."),
    UseCase("book-hotel-night-known", "es", 1, "Book a specific hotel night",
            "Resérvame una noche en el Hotel Palacio de la Merced para el {FECHA_FUTURA_CERCANA}.",
            "One night is booked at the named hotel for {NEAR_FUTURE_DATE}."),
    UseCase("buy-known-product", "es", 1, "Buy a specific listed product",
            "Cómprame el libro que tengo en la lista de deseos de Casa del Libro.",
            "The wishlisted book is purchased from the named store."),
    UseCase("find-theatre-tickets", "es", 1, "Buy tickets to a specific known show",
            "Consígueme dos entradas para el musical de El Rey León en Madrid para el sábado.",
            "Two tickets for the named show on Saturday are purchased."),
    # The three below were added 2026-08-18 to fix a REPRESENTATION gap, not to pad the count: every case
    # promoted until then was a slow browser search on a third-party site, so the scoreboard could only ever
    # show shades of red and we learned nothing about the parts of the product that DO work. These are real
    # user needs that are also achievable end-to-end today — a fast in-turn answer, a widget the engine
    # builds itself, and a memory+agenda commitment — none of which need a login, a payment or a phone call.
    UseCase("quick-fact-opening-hours", "es", 1, "Answer a real-world fact in the same turn",
            "¿A qué hora abre mañana el Museo del Prado y cuánto cuesta la entrada general?",
            "Both facts (opening time + general admission price) are answered correctly IN THE SAME TURN via "
            "web_search, without spawning a browser task or making the operator wait — this is the "
            "'dato directo + síntesis' path (V2-022), and escalating it to a worker is itself the failure.",
            status="promoted"),
    UseCase("build-workout-tracker-widget", "es", 1, "Build a small widget on request",
            "Móntame un widget para ir apuntando mis entrenamientos, con el día y qué hice.",
            "A real widget is generated, passes the generator's own validation gate and appears on the canvas "
            "with usable actions — verified against the widget catalog and the live task registry, not just "
            "the agent's claim. No third-party site, login or payment involved, which is why this is a fair "
            "test of the generation path itself.",
            status="promoted"),
    UseCase("remember-and-remind-deadline", "es", 1, "Record a commitment and set its reminder",
            "Apúntame que el jueves tengo que renovar el seguro del coche, y recuérdamelo el miércoles.",
            "The commitment is stored durably AND a reminder exists for the day before — the two halves are "
            "different subsystems (memory vs agenda/cron) and a pass requires BOTH, since 'I'll remind you' "
            "with nothing scheduled is the exact failure this case is for.",
            status="promoted"),

    # --- ES / tier 2: search + compare + choose -------------------------------------------
    UseCase("best-pediatric-dentists", "es", 2, "Find and book the best pediatric dentist",
            "Encuéntrame los 3 mejores dentistas infantiles cerca de mi casa en Madrid y resérvame "
            "con el mejor valorado.",
            "3 candidates are found and an appointment is booked with the top-rated one."),
    UseCase("compare-flights-madrid-lisboa", "es", 2, "Compare and book the cheapest flight",
            "Compárame vuelos Madrid–Lisboa para un fin de semana largo {EN_UNAS_SEMANAS} y coge el más barato con "
            "equipaje incluido.",
            "Flights are compared and the cheapest option with checked baggage is booked — verified "
            "against real system state (worker + browser signals), not just the agent's claim — see "
            "tests/use_cases/e2e/agent/scenarios.py.",
            status="promoted"),
    UseCase("best-plumber-same-day", "es", 2, "Find a same-day plumber",
            "Búscame un fontanero que pueda venir hoy mismo y el mejor valorado.",
            "Real plumbers who can come TODAY are found, each with its rating and a way to reach it (phone or "
            "booking page), and the best-rated one is named. The operator asked to FIND one, not to hire "
            "one — the shortlist with real data IS the deliverable."),
    UseCase("compare-insurance-quotes", "es", 2, "Compare insurance quotes",
            "Compárame tres seguros de coche y dime cuál me conviene.",
            "Three car-insurance quotes are compared with a clear recommendation."),
    UseCase("cheapest-monitor", "es", 2, "Find the cheapest well-reviewed monitor",
            "Encuéntrame el monitor más barato de 27 pulgadas 4K que tenga buenas reseñas.",
            "The cheapest well-reviewed 27-inch 4K monitor is identified — verified against real system "
            "state (worker + browser signals), not just the agent's claim — see "
            "tests/use_cases/e2e/agent/scenarios.py.",
            status="promoted"),
    UseCase("best-rated-rental-car", "es", 2, "Find the best-rated rental car",
            "Búscame el coche de alquiler mejor valorado en Málaga para el fin de semana.",
            "Real rental-car offers in Málaga for that weekend are found with price and rating, and the "
            "best-rated one is named. The operator asked to FIND it, not to rent it."),
    UseCase("compare-broadband-plans", "es", 2, "Compare broadband/mobile plans",
            "Compárame las tarifas de fibra+móvil de los operadores y dime cuál me ahorra más.",
            "Broadband+mobile bundles are compared and the cheapest is recommended."),
    UseCase("weekend-barber-availability", "es", 2, "Find weekend barber availability",
            "Encuéntrame una peluquería con hueco este fin de semana cerca de mi casa.",
            "A nearby barber with a genuinely FREE slot this weekend is found, naming the day and time seen on "
            "the real page — availability read, never assumed. The operator asked to FIND one with an "
            "opening, not to book the appointment."),
    UseCase("search-buy-used-car", "es", 2, "Search classifieds for a used car",
            "Búscame un coche de segunda mano, diésel, menos de 100.000 km y por debajo de "
            "12.000€, y dime los 3 mejores.",
            "Listings matching the criteria are found on classifieds sites and the top 3 are presented — "
            "verified against real system state (worker + browser signals), not just the agent's claim — "
            "see tests/use_cases/e2e/agent/scenarios.py.",
            status="promoted"),
    UseCase("search-buy-motorcycle", "es", 2, "Search classifieds for a used motorcycle",
            "Búscame una moto de segunda mano de 125cc en buen estado por menos de 2.500€.",
            "Matching motorcycle listings are found and the best candidate is identified."),
    UseCase("search-buy-bicycle", "es", 2, "Search classifieds for a used bicycle",
            "Encuéntrame una bici de montaña de segunda mano en buen estado, talla M, por menos "
            "de 300€.",
            "Matching bicycle listings are found and the best candidate is identified."),
    UseCase("search-secondhand-monitor", "es", 2, "Search classifieds for a secondhand monitor",
            "Búscame un monitor de segunda mano de al menos 27 pulgadas por menos de 150€.",
            "Matching secondhand monitor listings are found and the best candidate is identified."),
    UseCase("search-buy-book", "es", 2, "Find and buy a book at the cheapest store",
            "Búscame el último libro de Fernando Aramburu y cómpramelo en la librería que sea "
            "más barata.",
            "The book's price is compared across stores and it's bought from the cheapest one."),
    UseCase("search-buy-camera", "es", 2, "Search classifieds for a used camera",
            "Búscame una cámara réflex de segunda mano con pocos disparos, por menos de 400€.",
            "Matching camera listings are found and the best candidate is identified."),
    UseCase("search-buy-guitar", "es", 2, "Search classifieds for a used guitar",
            "Encuéntrame una guitarra acústica de segunda mano para empezar, por menos de 150€.",
            "Matching guitar listings are found and the best candidate is identified."),
    UseCase("find-best-hotel-city", "es", 2, "Find the best-rated hotel in a city",
            "Búscame el mejor hotel en Sevilla para el fin de semana del 20, con buena "
            "valoración y menos de 120€ la noche.",
            "Real hotels in the city for that weekend are compared and the best-rated one UNDER the price cap "
            "is named with its real price and rating. The operator asked to FIND it, not to book it."),
    UseCase("find-direct-flight-budget", "es", 2, "Find the cheapest direct flight",
            "Búscame un vuelo directo Madrid–Roma {DENTRO_DE_UN_MES}, lo más barato posible.",
            "Direct flights are compared and the cheapest one is identified."),
    UseCase("rental-car-automatic-airport", "es", 2, "Find an automatic rental car at an airport",
            "Búscame un coche de alquiler automático en el aeropuerto de Málaga para la semana "
            "que viene.",
            "Automatic rental cars at the named airport are compared and the best one is found."),
    UseCase("find-concert-tickets", "es", 2, "Find the cheapest tickets to a concert",
            "Búscame entradas para un concierto de Rosalía en Madrid este mes, lo más baratas "
            "posible.",
            "Ticket options for the concert are compared and the cheapest is identified."),
    UseCase("things-to-do-nearby-weekend", "es", 2, "Find things to do nearby this weekend",
            "Busca planes para este fin de semana cerca de mi casa.",
            "A short list of nearby weekend plans/activities is found and presented."),
    UseCase("kid-friendly-activity-nearby", "es", 2, "Find a kid-friendly activity nearby",
            "Encuéntrame un plan con niños para este domingo cerca de casa.",
            "A kid-friendly activity near the operator's home is found for the given day."),
    UseCase("hotel-under-15-days", "es", 2, "Find/book a hotel within 15 days (dynamic scenario)",
            "Búscame un hotel para dentro de menos de 15 días, para dos personas, cuatro estrellas, "
            "cuatro noches.",
            "A real 4-star hotel candidate (or booking) for ~4 nights within 15 days is reached, verified "
            "against real system state (worker + browser signals), not just the agent's claim — see "
            "tests/use_cases/e2e/agent/scenarios.py for the full dynamic, non-deterministic harness.",
            status="promoted"),

    # --- ES / tier 3: multi-step single-domain task with a deadline -----------------------
    UseCase("itv-before-deadline", "es", 3, "Book vehicle inspection before deadline",
            "Tengo que pasar la ITV antes del día 30 — búscame cita y avísame el día antes.",
            "An ITV appointment before the 30th is booked and a reminder fires the day before."),
    UseCase("renew-passport-before-expiry", "es", 3, "Renew a soon-to-expire passport",
            "Mi pasaporte caduca en dos meses — pide cita para renovarlo y recuérdamelo.",
            "A passport-renewal appointment is booked and a reminder is set."),
    UseCase("track-package-reschedule", "es", 3, "Track a package and reschedule delivery",
            "Sigue el paquete que estoy esperando y, si no voy a estar, reprograma la entrega.",
            "The package is tracked and delivery is rescheduled if the operator will be out."),
    UseCase("negotiate-lower-phone-bill", "es", 3, "Negotiate a lower phone bill",
            "Llama a mi operador y consigue que me bajen la tarifa del móvil.",
            "The phone carrier is contacted and a lower rate is negotiated."),
    UseCase("file-expense-report", "es", 3, "File a trip expense report",
            "Prepárame el informe de gastos del viaje de la semana pasada y envíalo a administración.",
            "An expense report is compiled from last week's trip and sent to accounting."),
    UseCase("split-dinner-bill-friends", "es", 3, "Split a dinner bill with friends",
            "Divide la cuenta de la cena de anoche entre los cuatro y mándales el importe.",
            "Last night's bill is split four ways and each share is sent to the right person."),

    # --- ES / tier 4: cross-domain orchestration -------------------------------------------
    UseCase("weekend-trip-san-sebastian", "es", 4, "Plan a weekend trip door-to-door",
            "Organízame un fin de semana en San Sebastián: tren, hotel con desayuno y mesa el "
            "sábado noche.",
            "Train, breakfast-included hotel and a Saturday dinner reservation are all booked."),
    UseCase("clean-and-reply-inbox", "es", 4, "Clean up and triage the inbox",
            "Limpia mi bandeja de entrada de las últimas dos semanas y responde solo lo urgente.",
            "The last two weeks of email are triaged; only genuinely urgent items get a reply."),
    UseCase("archive-newsletters", "es", 4, "Archive a newsletter backlog",
            "Archívame las newsletters acumuladas y déjame solo lo que importa.",
            "Accumulated newsletters are archived, leaving only what matters in the inbox."),
    UseCase("rebook-delayed-flight-now", "es", 4, "Rebook a flight that just got delayed",
            "Mi vuelo se ha retrasado más de una hora — búscame otro y avísame.",
            "An alternative flight is found and booked; the operator is notified."),
    UseCase("found-next-apartment", "es", 4, "Find an apartment and schedule viewings",
            "Búscame piso de alquiler en Chamberí, máximo 1200€, y agenda las visitas que encajen "
            "con mi agenda.",
            "Matching listings are found and viewings are scheduled around the operator's calendar."),
    UseCase("moms-birthday-flowers-onetime", "es", 4, "Order flowers for a birthday",
            "Es el cumpleaños de mi madre pasado mañana — pide flores y que lleguen a su casa por "
            "la mañana.",
            "Flowers are ordered for morning delivery two days from now."),
    UseCase("three-tasks-at-once", "es", 4, "Three concurrent tasks, interleaved conversation",
            "Hazme un informe de coches eléctricos, búscame un monitor barato, y móntame un widget "
            "de un juego de plataformas tipo Super Mario.",
            "Three DIFFERENT tasks run CONCURRENTLY (a research report, a marketplace search and a "
            "widget-code generation — three distinct worker kinds), and the operator then talks about "
            "them out of order, referring to each only obliquely ('¿y el del coche?', 'ese ponle que "
            "salte más alto'). Success = every message is ATTRIBUTED to the right running task (never "
            "answered against the wrong one, never silently dropped), the tasks stay independent "
            "(one failing/slow does not stall the others), and the replies read as one linked "
            "conversation that carries state ('el informe ya está, la búsqueda sigue, el juego lo "
            "tengo a medias') rather than three robotic status dumps. Verified against the real live "
            "task registry (/api/tasks) for genuine concurrency, not just the transcript — see "
            "tests/use_cases/e2e/agent/scenarios.py.",
            status="promoted"),

    # --- ES / tier 5: standing / reactive over time -----------------------------------------
    UseCase("watch-flight-rebook-automatically", "es", 5, "Watch a flight and auto-rebook",
            "Vigila mi vuelo a Barcelona; si se retrasa más de una hora, búscame otro sin "
            "preguntar y avísame.",
            "The flight is monitored; a delay over an hour triggers an automatic rebook + notice."),
    UseCase("track-price-drop-buy", "es", 5, "Buy automatically on a price drop",
            "Vigila el precio de este monitor y cómpralo en cuanto baje de 250€.",
            "The price is tracked continuously and the purchase fires the moment it drops below €250."),
    UseCase("cancel-trial-before-it-charges", "es", 5, "Auto-cancel an unused trial",
            "Tengo una prueba gratuita que se convierte en pago el viernes — cancélala tú antes "
            "si no he vuelto a usarla.",
            "The trial is cancelled before Friday's charge, conditional on no further use."),
    UseCase("gym-membership-no-silent-renew", "es", 5, "Never auto-renew without asking",
            "No dejes que la cuota del gimnasio se renueve sola sin decírmelo antes.",
            "The membership renewal is intercepted and confirmed with the operator before charging."),
    UseCase("moms-birthday-flowers-recurring", "es", 5, "Recurring yearly birthday reminder + order",
            "No olvides el cumpleaños de mi madre — pide flores el día antes, cada año.",
            "Flowers are ordered automatically the day before, every year, without being asked again."),
    UseCase("grocery-restock-reactive", "es", 5, "Reactive grocery restock",
            "Cuando vea que se acaba la leche o el café, pídelos otra vez sin que tenga que "
            "decírtelo.",
            "Milk/coffee are reordered automatically when consumption patterns say they're running low."),

    # --- ES / tier 6: multi-agent coordination over email -----------------------------------
    UseCase("coordinate-lunch-with-pedro", "es", 6, "Coordinate lunch via a friend's agent",
            "Dile al agente de Pedro que quedamos el jueves a comer — que proponga sitio y hora "
            "y me lo confirmes.",
            "Pedro's agent proposes a place/time by email; the operator gets a confirmed plan."),
    UseCase("split-airbnb-with-marta", "es", 6, "Split a shared stay via a friend's agent",
            "Coordina con el agente de Marta un apartamento compartido para el finde en Lisboa "
            "y divide la cuenta.",
            "A shared listing is agreed with Marta's agent by email and the cost is split."),
    UseCase("reschedule-meetup-conflict", "es", 6, "Resolve a scheduling conflict between agents",
            "El agente de Javi te va a proponer quedar el sábado — mira mi agenda y negocia una "
            "hora que me valga.",
            "An incoming proposal is checked against the operator's calendar and renegotiated by email."),
    UseCase("confirm-restaurant-reservation-together", "es", 6, "Avoid a double-booking with another agent",
            "Ponte de acuerdo con el agente de Ana para reservar mesa esta noche — que ninguno "
            "reserve dos veces.",
            "Only one reservation is made; the other agent's attempt is avoided/cancelled by email."),
    UseCase("plan-joint-trip-with-friend", "es", 6, "Align a joint itinerary with a friend's agent",
            "Habla con el agente de Laura y cuadrad un itinerario común para el viaje de "
            "septiembre.",
            "A shared itinerary is negotiated and agreed with Laura's agent by email."),

    # --- ES / tier 7: multi-agent coordination over WhatsApp/Telegram (BLOCKED) -------------
    UseCase("coordinate-lunch-whatsapp", "es", 7, "Coordinate lunch over WhatsApp",
            "Escríbele por WhatsApp al agente de Pedro y quedad para comer el jueves.",
            "Pedro's agent is reached over WhatsApp and a lunch plan is confirmed.",
            status="blocked", depends_on=_BLOCKED_DEPENDENCIES),
    UseCase("split-trip-telegram", "es", 7, "Split a trip itinerary over Telegram",
            "Habla por Telegram con el agente de Marta y repartid el itinerario del viaje.",
            "Marta's agent is reached over Telegram and the itinerary is split and agreed.",
            status="blocked", depends_on=_BLOCKED_DEPENDENCIES),
    UseCase("group-plan-three-friends", "es", 7, "Coordinate a group plan across three agents",
            "Coordínate con los agentes de Pedro, Marta y Javi por WhatsApp para quedar todos "
            "el sábado.",
            "Three agents are reached over WhatsApp and a single Saturday plan is agreed.",
            status="blocked", depends_on=_BLOCKED_DEPENDENCIES),
    UseCase("realtime-eta-share", "es", 7, "Share a live ETA with a friend's agent",
            "Avisa por WhatsApp al agente de Ana en cuanto salga de casa, para que sepa a qué "
            "hora llego.",
            "Ana's agent is notified over WhatsApp the moment the operator leaves.",
            status="blocked", depends_on=_BLOCKED_DEPENDENCIES),

    # --- US / tier 1: bounded single-site action --------------------------------------------
    UseCase("restaurant-tonight-nyc", "us", 1, "Book a known restaurant tonight",
            "Book a table for 2 tonight at 7pm at Katz's Delicatessen.",
            "A table for 2 is booked at Katz's for 7pm tonight."),
    UseCase("cancel-subscription-before-charge", "us", 1, "Cancel a subscription before renewal",
            "Cancel my Hulu trial before it charges me on the 15th.",
            "The Hulu trial is cancelled before the next billing date."),
    UseCase("reorder-prescription", "us", 1, "Reorder a known prescription",
            "Reorder my blood-pressure prescription from CVS.",
            "The prescription is reordered from the named CVS pharmacy."),
    UseCase("pay-known-bill", "us", 1, "Pay a known bill",
            "Pay this month's electric bill before it's due on the 5th.",
            "This month's electric bill is paid before the 5th."),
    UseCase("renew-gym-membership", "us", 1, "Renew a known gym membership",
            "Renew this month's gym membership at Equinox.",
            "This month's Equinox membership fee is renewed."),
    UseCase("book-barber-slot", "us", 1, "Book the usual barber",
            "Book my usual barber for Saturday morning.",
            "A Saturday-morning slot is booked at the operator's usual barber."),
    UseCase("book-hotel-night-known", "us", 1, "Book a specific hotel night",
            "Book one night at the Ace Hotel downtown for {NEAR_FUTURE_DATE}.",
            "One night is booked at the named hotel for {NEAR_FUTURE_DATE}."),
    UseCase("buy-known-product", "us", 1, "Buy a specific listed product",
            "Buy the book on my Amazon wishlist.",
            "The wishlisted book is purchased."),
    UseCase("find-theatre-tickets", "us", 1, "Buy tickets to a specific known show",
            "Get me two tickets to The Lion King musical in New York for Saturday.",
            "Two tickets for the named show on Saturday are purchased."),

    # --- US / tier 2: search + compare + choose -----------------------------------------------
    UseCase("best-pediatric-dentists", "us", 2, "Find and book the best pediatric dentist",
            "Find the 3 best-rated pediatric dentists near me and book the top one.",
            "3 candidates are found and an appointment is booked with the top-rated one."),
    UseCase("compare-flights-sf-austin", "us", 2, "Compare and book the cheapest flight",
            "Compare flights SF-Austin for next long weekend and book the cheapest with a "
            "carry-on included.",
            "Flights are compared and the cheapest option with a carry-on is booked."),
    UseCase("best-plumber-same-day", "us", 2, "Find a same-day plumber",
            "Find a plumber who can come today, top-rated near me.",
            "Real plumbers who can come TODAY are found, each with its rating and a way to reach it (phone or "
            "booking page), and the best-rated one is named. The operator asked to FIND one, not to hire "
            "one — the shortlist with real data IS the deliverable."),
    UseCase("compare-insurance-quotes", "us", 2, "Compare insurance quotes",
            "Compare three car insurance quotes and tell me which one's the best deal.",
            "Three car-insurance quotes are compared with a clear recommendation."),
    UseCase("cheapest-monitor", "us", 2, "Find the cheapest well-reviewed monitor",
            "Find the cheapest 27-inch 4K monitor with good reviews.",
            "The cheapest well-reviewed 27-inch 4K monitor is identified."),
    UseCase("best-rated-rental-car", "us", 2, "Find the best-rated rental car",
            "Find the best-rated rental car in Austin for the weekend.",
            "Real rental-car offers in Austin for that weekend are found with price and rating, and the "
            "best-rated one is named. The operator asked to FIND it, not to rent it."),
    UseCase("compare-phone-plans", "us", 2, "Compare cell phone plans",
            "Compare cell phone plans and tell me which one saves me the most.",
            "Phone plans are compared and the cheapest fit is recommended."),
    UseCase("weekend-barber-availability", "us", 2, "Find weekend barber availability",
            "Find a barber with an opening this weekend near me.",
            "A nearby barber with a genuinely FREE slot this weekend is found, naming the day and time seen on "
            "the real page — availability read, never assumed. The operator asked to FIND one with an "
            "opening, not to book the appointment."),
    UseCase("search-buy-used-car", "us", 2, "Search classifieds for a used car",
            "Find me a used car, diesel or hybrid, under 60k miles and under $14,000, and give "
            "me the top 3.",
            "Listings matching the criteria are found on classifieds sites and the top 3 are presented."),
    UseCase("search-buy-motorcycle", "us", 2, "Search classifieds for a used motorcycle",
            "Find me a used 300cc motorcycle in good condition for under $3,000.",
            "Matching motorcycle listings are found and the best candidate is identified."),
    UseCase("search-buy-bicycle", "us", 2, "Search classifieds for a used bicycle",
            "Find me a used mountain bike in good condition, size M, for under $350.",
            "Matching bicycle listings are found and the best candidate is identified."),
    UseCase("search-secondhand-monitor", "us", 2, "Search classifieds for a secondhand monitor",
            "Find me a used 27-inch+ monitor for under $150.",
            "Matching secondhand monitor listings are found and the best candidate is identified."),
    UseCase("search-buy-book", "us", 2, "Find and buy a book at the cheapest store",
            "Find the latest book by Colleen Hoover and buy it from whichever store has it "
            "cheapest.",
            "The book's price is compared across stores and it's bought from the cheapest one."),
    UseCase("search-buy-camera", "us", 2, "Search classifieds for a used camera",
            "Find me a used DSLR camera with a low shutter count for under $400.",
            "Matching camera listings are found and the best candidate is identified."),
    UseCase("search-buy-guitar", "us", 2, "Search classifieds for a used guitar",
            "Find me a used acoustic guitar for beginners under $150.",
            "Matching guitar listings are found and the best candidate is identified."),
    UseCase("find-best-hotel-city", "us", 2, "Find the best-rated hotel in a city",
            "Find me the best hotel in New Orleans for the weekend of the 20th, well-rated and "
            "under $150 a night.",
            "Real hotels in the city for that weekend are compared and the best-rated one UNDER the price cap "
            "is named with its real price and rating. The operator asked to FIND it, not to book it."),
    UseCase("find-direct-flight-budget", "us", 2, "Find the cheapest direct flight",
            "Find me a direct flight NYC-Rome in October, as cheap as possible.",
            "Direct flights are compared and the cheapest one is identified."),
    UseCase("rental-car-automatic-airport", "us", 2, "Find an automatic rental car at an airport",
            "Find me an automatic rental car at Denver airport for next week.",
            "Automatic rental cars at the named airport are compared and the best one is found."),
    UseCase("find-concert-tickets", "us", 2, "Find the cheapest tickets to a concert",
            "Find me tickets to a Beyoncé concert in LA this month, as cheap as possible.",
            "Ticket options for the concert are compared and the cheapest is identified."),
    UseCase("things-to-do-nearby-weekend", "us", 2, "Find things to do nearby this weekend",
            "Find things to do this weekend near me.",
            "A short list of nearby weekend plans/activities is found and presented."),
    UseCase("kid-friendly-activity-nearby", "us", 2, "Find a kid-friendly activity nearby",
            "Find a kid-friendly activity near me for Sunday.",
            "A kid-friendly activity near the operator's home is found for the given day."),

    # --- US / tier 3: multi-step single-domain task with a deadline ---------------------------
    UseCase("smog-check-before-deadline", "us", 3, "Book vehicle inspection before deadline",
            "My car's smog check is due before the 30th - find an appointment and remind me the "
            "day before.",
            "A smog-check appointment before the 30th is booked and a reminder fires the day before."),
    UseCase("renew-passport-before-expiry", "us", 3, "Renew a soon-to-expire passport",
            "My passport expires in two months - book a renewal appointment and remind me.",
            "A passport-renewal appointment is booked and a reminder is set."),
    UseCase("track-package-reschedule", "us", 3, "Track a package and reschedule delivery",
            "Track the package I'm expecting and reschedule delivery if I won't be home.",
            "The package is tracked and delivery is rescheduled if the operator will be out."),
    UseCase("negotiate-lower-phone-bill", "us", 3, "Negotiate a lower phone bill",
            "Call my carrier and get my phone bill lowered.",
            "The phone carrier is contacted and a lower rate is negotiated."),
    UseCase("file-expense-report", "us", 3, "File a trip expense report",
            "Put together last week's trip expense report and send it to accounting.",
            "An expense report is compiled from last week's trip and sent to accounting."),
    UseCase("split-dinner-bill-friends", "us", 3, "Split a dinner bill with friends",
            "Split last night's dinner bill four ways and send everyone their share.",
            "Last night's bill is split four ways and each share is sent to the right person."),

    # --- US / tier 4: cross-domain orchestration ------------------------------------------------
    UseCase("weekend-trip-austin", "us", 4, "Plan a weekend trip door-to-door",
            "Plan a weekend in Austin: flight, hotel with breakfast, dinner reservation Saturday.",
            "Flight, breakfast-included hotel and a Saturday dinner reservation are all booked."),
    UseCase("clean-and-reply-inbox", "us", 4, "Clean up and triage the inbox",
            "Clean up my inbox from the last two weeks and reply to what's actually urgent.",
            "The last two weeks of email are triaged; only genuinely urgent items get a reply."),
    UseCase("archive-newsletters", "us", 4, "Archive a newsletter backlog",
            "Archive my backlog of newsletters and leave only what matters.",
            "Accumulated newsletters are archived, leaving only what matters in the inbox."),
    UseCase("rebook-delayed-flight-now", "us", 4, "Rebook a flight that just got delayed",
            "My flight just got delayed over an hour - find another one and let me know.",
            "An alternative flight is found and booked; the operator is notified."),
    UseCase("found-next-apartment", "us", 4, "Find an apartment and schedule viewings",
            "Find me a 1-bedroom in Brooklyn under $2800 and schedule the tours that fit my "
            "calendar.",
            "Matching listings are found and tours are scheduled around the operator's calendar."),
    UseCase("moms-birthday-flowers-onetime", "us", 4, "Order flowers for a birthday",
            "It's my mom's birthday the day after tomorrow - order flowers for morning delivery.",
            "Flowers are ordered for morning delivery two days from now."),

    # --- US / tier 5: standing / reactive over time ----------------------------------------------
    UseCase("watch-flight-rebook-automatically", "us", 5, "Watch a flight and auto-rebook",
            "Watch my flight to Chicago; if it's delayed more than an hour, rebook me "
            "automatically and let me know.",
            "The flight is monitored; a delay over an hour triggers an automatic rebook + notice."),
    UseCase("track-price-drop-buy", "us", 5, "Buy automatically on a price drop",
            "Track this monitor's price and buy it the moment it drops below $250.",
            "The price is tracked continuously and the purchase fires the moment it drops below $250."),
    UseCase("cancel-trial-before-it-charges", "us", 5, "Auto-cancel an unused trial",
            "I've got a free trial that converts to paid Friday - cancel it yourself if I "
            "haven't used it again.",
            "The trial is cancelled before Friday's charge, conditional on no further use."),
    UseCase("gym-membership-no-silent-renew", "us", 5, "Never auto-renew without asking",
            "Don't let my gym membership auto-renew without checking with me first.",
            "The membership renewal is intercepted and confirmed with the operator before charging."),
    UseCase("moms-birthday-flowers-recurring", "us", 5, "Recurring yearly birthday reminder + order",
            "Never let me forget my mom's birthday - order flowers the day before, every year.",
            "Flowers are ordered automatically the day before, every year, without being asked again."),
    UseCase("grocery-restock-reactive", "us", 5, "Reactive grocery restock",
            "When you notice we're low on milk or coffee, reorder it without me having to ask.",
            "Milk/coffee are reordered automatically when consumption patterns say they're running low."),

    # --- US / tier 6: multi-agent coordination over email -----------------------------------------
    UseCase("coordinate-dinner-with-alex", "us", 6, "Coordinate dinner via a friend's agent",
            "Ask Alex's agent to lock in Friday dinner - let them pick the place, just confirm "
            "the time with me.",
            "Alex's agent proposes a place/time by email; the operator gets a confirmed plan."),
    UseCase("split-airbnb-with-jordan", "us", 6, "Split a shared stay via a friend's agent",
            "Coordinate with Jordan's agent on a shared Airbnb for the weekend in Miami and "
            "split the bill.",
            "A shared listing is agreed with Jordan's agent by email and the cost is split."),
    UseCase("resolve-meetup-conflict", "us", 6, "Resolve a scheduling conflict between agents",
            "Sam's agent is going to propose meeting Saturday - check my calendar and negotiate "
            "a time that works.",
            "An incoming proposal is checked against the operator's calendar and renegotiated by email."),
    UseCase("confirm-restaurant-together", "us", 6, "Avoid a double-booking with another agent",
            "Sync up with Taylor's agent on tonight's reservation - make sure neither of us "
            "double-books.",
            "Only one reservation is made; the other agent's attempt is avoided/cancelled by email."),
    UseCase("plan-joint-trip-with-friend", "us", 6, "Align a joint itinerary with a friend's agent",
            "Talk to Morgan's agent and align on a shared itinerary for the September trip.",
            "A shared itinerary is negotiated and agreed with Morgan's agent by email."),

    # --- US / tier 7: multi-agent coordination over WhatsApp/Telegram (BLOCKED) --------------------
    UseCase("coordinate-dinner-whatsapp", "us", 7, "Coordinate dinner over WhatsApp",
            "Text Alex's agent on WhatsApp and lock in Thursday dinner.",
            "Alex's agent is reached over WhatsApp and a dinner plan is confirmed.",
            status="blocked", depends_on=_BLOCKED_DEPENDENCIES),
    UseCase("split-trip-telegram", "us", 7, "Split a trip itinerary over Telegram",
            "Message Jordan's agent on Telegram and split up the trip itinerary.",
            "Jordan's agent is reached over Telegram and the itinerary is split and agreed.",
            status="blocked", depends_on=_BLOCKED_DEPENDENCIES),
    UseCase("group-plan-three-friends", "us", 7, "Coordinate a group plan across three agents",
            "Coordinate with Alex, Jordan and Sam's agents over WhatsApp to get everyone "
            "together Saturday.",
            "Three agents are reached over WhatsApp and a single Saturday plan is agreed.",
            status="blocked", depends_on=_BLOCKED_DEPENDENCIES),
    UseCase("realtime-eta-share", "us", 7, "Share a live ETA with a friend's agent",
            "Ping Taylor's agent on WhatsApp the moment I leave, so they know when I'll arrive.",
            "Taylor's agent is notified over WhatsApp the moment the operator leaves.",
            status="blocked", depends_on=_BLOCKED_DEPENDENCIES),
    # ── Hard searches: many constraints at once, kept for LAST on purpose (operator, 2026-08-20) ──────
    # A one-constraint search is the minimum case; these are the maximum. They are here so the ceiling is
    # written down, not so they get promoted early: the order of work is least complexity first, by tier.
    # What makes them hard is not the subject but the SHAPE — several filters that must all hold at once,
    # some of which live behind a site's own controls rather than in the text of a query, and a result that
    # has to be checked against every one of them before it is offered.
    UseCase("hotel-many-filters-at-once", "es", 7, "Hotel search where every filter has to hold at once",
            "Búscame hotel en la costa para el puente, que tenga piscina, parking gratis, wifi decente "
            "y que acepten perro. Nada de interior.",
            "Candidates are offered only when ALL constraints hold, each one checked against the page "
            "rather than assumed, and any constraint that could not be verified is named as such."),
    UseCase("used-car-search-wallapop", "es", 7, "Second-hand search on a marketplace with its own filters",
            "Mírame coches de segunda mano en Wallapop, diésel, menos de 120.000 km, cambio manual y "
            "por debajo de 9.000 €, cerca de casa.",
            "Real listings are read from the marketplace with every filter applied, and price/mileage "
            "come from the listing rather than from the model."),
    UseCase("house-search-los-angeles", "us", 7, "House search on whichever site is popular in that market",
            "Find me houses to rent in Los Angeles, two bedrooms, under $3,500, pets allowed, and not "
            "on a main road.",
            "The agent picks a site people actually use in that market, applies the filters there, and "
            "reports which constraint each candidate meets."),
]
