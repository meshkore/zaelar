# Real-world use cases — ES/US catalog

This is the readable catalog for the `use_cases` suite (`tests/use_cases/suite.json` +
`tests/use_cases/catalog.py` + `tests/use_cases/cases_data.py`, the source of truth). It mirrors
`tests/voice/e2e/agent/anexos/catalogo-escenarios.md`'s role for the voice suite: the catalog of
what gets tested is public and useful; per-run diaries are not (see `tests/README.md`).

**Status: mostly backlog, one promoted.** Every case below is registered and browsable
(`python -m tests list`, the Observatory at `http://127.0.0.1:8765`, `/api/catalog/use_cases`).
Cases get promoted to executable one at a time. Promotion doesn't mean "wire a simple
request/response pytest" — these are open-ended, non-deterministic real-world tasks, so a promoted
case gets a **dynamic harness** instead: `tests/use_cases/e2e/agent/` (driver + watchdog + verify +
judge, full design below), reusing the voice tester's proven DRIVE+JUDGE pattern
(`tests/voice/e2e/agent/`) rather than reinventing it.

- `hotel-under-15-days` (ES, tier 2) — **promoted**, first scenario built. Deliberately
  underspecified (no destination given) to force a real clarifying question. Live-validated
  2026-08-16, and re-investigated 2026-08-17 after it kept reporting `families_observed: [flash,
  system]` (worker/widget "never fired") on runs where a real browser search demonstrably DID run
  (launched, navigated, screenshotted for two minutes). **That was a harness bug, not a product
  bug**: `run.py` polled `/api/observability/flow/{corr_id}` per conversational turn, but a
  dispatched worker's own steps mint FRESH corr_ids as they run (V2-044 — every stimulus is born
  with its own trace) instead of inheriting the turn that triggered them, so a multi-step
  background task was invisible to per-turn polling. Compounding it, the fix's first attempt
  (session-scoped polling) also failed silently: the probe's own `session` string was never the
  right key — `events.session_id` is the engine's *live observability session* (a server-wide,
  one-at-a-time concept, `/api/observability/identity`), unrelated to the probe channel's dialogue
  window. Fixed in `probe_client.py`/`run.py`: fetch the real live session_id, pull ALL its events,
  filter to the scenario's own time window (that session spans the engine's whole uptime, not just
  one scenario). Verified: `families_observed` now correctly includes `worker`/`widget`
  (`missing_signals: []`, 191 real events) on a run where a search genuinely executed.
  **The scenario still fails (1/5)**, but now for real, accurately-diagnosed reasons: the search
  worker doesn't reliably deliver a result within the conversation's patience budget, at least once
  it exposed an internal detail it shouldn't ("hay dos procesos en marcha... lo paro y te dejo el
  otro" — a duplicate-dispatch smell worth checking next), and the FlashBrain doesn't proactively
  check in with real progress, just repeats "sigo buscando". Also separately confirmed and fixed
  2026-08-17: the engine's global run-state (⏻) was left STOPPED from earlier manual testing, which
  alone blocks 100% of worker dispatch (`nucleo/dispatch.py`'s "agente parado" gate) — always check
  `GET /api/run` before trusting a `families_observed` result that's missing `worker` entirely.
  Not yet root-caused as a fix; flagged here as an open finding for whoever picks up
  hotel/search-type cases next.

All other cases stay backlog until promoted, one at a time — picking the runner shape (browser
automation, an `agent-headless`-style scenario, an email exchange for multi-agent cases) per case
as it's picked up, not decided in bulk here.

## Two silos, one suite

`es` (Spain) and `us` (United States) are two case_groups inside a single suite rather than two
separate suites — they share the same tiers, the same multi-agent dependencies, and eventually the
same runner code; only the target locale/utterance differs. `python -m tests run use_cases` and
`/api/catalog/use_cases` return both groups together.

## Running ES vs US: one process, one language, at a time

Language is a single process-wide value today (`voice/engine/core/langs.py::current_code()` reads
`ZAELAR_LANGUAGE` live, and the probe/text channel, `nucleo/flash/probe.py`, consults the exact same
global) — there is no per-session or per-request language override anywhere in the engine. The
one-time "arranque idiomático" auto-detection only runs once, before any language has ever been
chosen for that install; after that it's a manual switch (⚙ or `ZAELAR_LANGUAGE`) that only takes
effect on the next voice reconnect.

So an `es` case and a `us` case **cannot run concurrently against one live server** — this is not a
suite-design gap, it's how the engine works today. Two ways to run both silos, already precedented by
the voice tester's multi-language wave (INI-013, wave H):
- **Sequential, one process**: set `ZAELAR_LANGUAGE=es`, reconnect, run the `es` batch; flip to `en`,
  reconnect, run the `us` batch; flip back. This is exactly what wave H did, including reverting the
  setting afterward so the live install wasn't left in the wrong language.
- **Two separately-configured processes**: one instance pinned to `es`, one to `en` — needed if both
  silos must run in parallel rather than back-to-back.

Neither of these is built into the `use_cases` runner yet (there is no runner yet). Whoever wires the
first case should pick one of the two approaches explicitly rather than assume the tester can pass a
language per case — that mechanism doesn't exist and would be new work if wanted.

## The dynamic harness (`tests/use_cases/e2e/agent/`)

A promoted case is not a scripted request/response — it's a real negotiation. Pieces, each adapted from
an existing proven pattern rather than invented from scratch:

- **`scenarios.py`** — `UseCaseScenario(id, locale, tier, persona_brief, opening_line, success_checks,
  expected_signals, turns, channel)`. `opening_line` is deliberately natural/underspecified, not
  hyperperfect — a fully-specified request never forces the agent to ask a clarifying question, which
  defeats the point.
- **`driver.py`** — the DRIVE model (reasoning-capable tier, `deepseek-v4-pro` by default) plays the
  person, adapted from the voice tester's `TesterBrain`: a running history where zaelar's replies become
  the next turn's context, so a clarifying question genuinely changes what gets said next.
- **`watchdog.py`** — mid-scenario drift detector, adapted from `connectors/meshkore/evaluator.py`
  (V2-075): closed-vocabulary verdict (`flowing/off_track/stuck` × `continue/nudge/abandon`), fail-open,
  independent read-only judge. Catches e.g. "zaelar searched Seville when the user never named a city"
  and hands the driver a natural correction to say next.
- **`verify.py`** — the genuinely new piece: polls the durable `GET /api/observability/flow/{corr_id}`
  per turn and, for browser tasks, `GET /widgets/navegador/data?q=<task_id>` for real extracted results.
  Produces a mechanism report — which subsystems *actually* fired — independent of the transcript.
- **`judge.py`** — adapted from the voice tester's judge: scores against `success_checks` using the
  mechanism report as the source of truth for any actionable claim, same principle as voice's
  VISUAL-requires-trace rule.
- **`run.py`** / **`cron_tick.sh`** — orchestrator + autonomous unattended runner, same shape as voice's.

Runs over the **text/probe channel** (`POST /api/flash/say`, `execute=true`, `ingest=false`) by default,
not voice — it exercises the identical FlashBrain/worker/browser/memory mechanism without STT/TTS
overhead, noise, or writing test conversations into the operator's real memory.

## Difficulty tiers

1. **Bounded single-site action** — the target is already named, no comparison needed. Buildable on
   today's `browser` automation.
2. **Search + compare + choose** — no fixed target; needs `agent-headless`-style reasoning plus
   `browser` to compare candidates before acting. The classifieds-marketplace cases here (car,
   motorcycle, bicycle, secondhand monitor, camera, guitar) map directly onto the engine's existing
   deep-navigation capability — Wallapop/coches.net-style browsing with real data extraction,
   with/without login (see `zaelar-testing.md`'s testing priorities and the sailboat-search audit in
   `.meshkore/roadmap/`) — making them good early candidates for the first runner wired up.
3. **Multi-step single-domain task with a real deadline** — memory (the deadline) + an action + a
   follow-up reminder.
4. **Cross-domain orchestration** — several providers/domains in one ask (e.g. transport + hotel +
   restaurant for one trip).
5. **Standing/reactive task** — proactive, memory-triggered, no single turn completes it (watch a
   flight, track a price, never auto-renew silently).
6. **Multi-agent coordination over email** — the flagship differentiator. Buildable once contact
   resolution and the agent-message tag exist; today only the email connector can send
   (`connectors/email/mailbox.py::send_reply`) — WhatsApp and Telegram are read-only.
7. **Multi-agent coordination over WhatsApp/Telegram** — same shape as tier 6, explicitly
   **BLOCKED** today (see below). Kept in the catalog rather than silently dropped, so the gap
   stays visible.

Competitor products (OpenAI Operator/ChatGPT-agent, Manus) already cover tiers 1-4 as isolated
single-agent actions well. Tier 5's memory-triggered standing tasks and tiers 6-7's person-to-person
agent coordination are where this catalog goes past both — the same promise the web already makes
(`web/src/components/Scenarios.astro`: *"Coordinated with a friend's agent to lock the reservation."*).

## Tier 6/7 dependencies — not built yet

Multi-agent cases need three things that don't exist today:

1. **Contact resolution** ("Pedro" → a real phone/handle/email address), designed but not built:
   `.meshkore/roadmap/initiatives/V2-052-contactos-red-canales.md` (status: design closed
   2026-07-17, not planned/built). Proposes contacts as memory entities
   (`slot="contact:<id>"` + per-channel slots), a `send_message(contact, text, channel?)` tool, and
   a dedicated contacts RAIL.
2. **WhatsApp/Telegram send capability** — both connectors are read-only today
   (`connectors/whatsapp/service.py`, `connectors/telegram/service.py`). Only email can send
   (`connectors/email/mailbox.py::send_reply`), which is why tier 6 is reachable sooner than tier 7.
3. **An agent-to-agent message tag** (see below) — so a human reading the thread can tell a message
   was generated by an agent, not typed by the other person.

Note: the MeshKore cluster protocol (`connectors/meshkore/`) is a real, working agent-to-agent
channel with its own live two-peer test (`tests/cluster/e2e/run_live_dialogue.py`) — but by design
an agent may never propose an objective/task on its own; the **operator manually sets
`capsule.objective`** on each side first. That's a per-side manual step, not a single voice command,
so it doesn't fit "tell Pedro's agent we're having lunch Thursday" — tiers 6/7 route through
WhatsApp/email/Telegram instead, on purpose.

## Agent-message tag: `Z∴`

Once tier 6/7 sending exists, every message one Zaelar sends to another (or to a contact's agent) is
prefixed with `Z∴` (U+2234, "therefore") — e.g. `"Z∴ We're set for Thursday, 8pm."`. Picked because
it has no easy keyboard path for most people (so it's not something a human would type by accident
or on purpose) while staying short and legible in a chat thread. This is a **design note only** —
not implemented in `connectors/` yet.

## Catalog

The full list lives in `tests/use_cases/cases_data.py` (`CASES`), grouped by locale then tier below.
Each entry: `id` — utterance — expected outcome.

### Spain (es)

**Tier 1 — bounded single-site action**
- `restaurant-tonight-madrid` — *"Resérvame mesa para 2 esta noche a las 21:30 en Casa Lucio."*
- `cancel-subscription-before-charge` — *"Cancela mi suscripción a Netflix antes de que me cobren el día 15."*
- `reorder-prescription` — *"Pide la reposición de mi receta de la farmacia de siempre."*
- `pay-known-bill` — *"Paga la factura de la luz de este mes antes del día 5."*
- `renew-gym-membership` — *"Renueva mi cuota del gimnasio de este mes."*
- `book-barber-slot` — *"Resérvame hora en la peluquería de siempre para el sábado por la mañana."*
- `book-hotel-night-known` — *"Resérvame una noche en el Hotel Palacio de la Merced para el 20 de septiembre."*
- `buy-known-product` — *"Cómprame el libro que tengo en la lista de deseos de Casa del Libro."*
- `find-theatre-tickets` — *"Consígueme dos entradas para el musical de El Rey León en Madrid para el sábado."*

**Tier 2 — search + compare + choose**
- `best-pediatric-dentists` — *"Encuéntrame los 3 mejores dentistas infantiles cerca de mi casa en Madrid y resérvame con el mejor valorado."*
- `compare-flights-madrid-lisboa` — *"Compárame vuelos Madrid–Lisboa para el puente de mayo y coge el más barato con equipaje incluido."*
- `best-plumber-same-day` — *"Búscame un fontanero que pueda venir hoy mismo y el mejor valorado."*
- `compare-insurance-quotes` — *"Compárame tres seguros de coche y dime cuál me conviene."*
- `cheapest-monitor` — *"Encuéntrame el monitor más barato de 27 pulgadas 4K que tenga buenas reseñas."*
- `best-rated-rental-car` — *"Búscame el coche de alquiler mejor valorado en Málaga para el fin de semana."*
- `compare-broadband-plans` — *"Compárame las tarifas de fibra+móvil de los operadores y dime cuál me ahorra más."*
- `weekend-barber-availability` — *"Encuéntrame una peluquería con hueco este fin de semana cerca de mi casa."*
- `search-buy-used-car` — *"Búscame un coche de segunda mano, diésel, menos de 100.000 km y por debajo de 12.000€, y dime los 3 mejores."*
- `search-buy-motorcycle` — *"Búscame una moto de segunda mano de 125cc en buen estado por menos de 2.500€."*
- `search-buy-bicycle` — *"Encuéntrame una bici de montaña de segunda mano en buen estado, talla M, por menos de 300€."*
- `search-secondhand-monitor` — *"Búscame un monitor de segunda mano de al menos 27 pulgadas por menos de 150€."*
- `search-buy-book` — *"Búscame el último libro de Fernando Aramburu y cómpramelo en la librería que sea más barata."*
- `search-buy-camera` — *"Búscame una cámara réflex de segunda mano con pocos disparos, por menos de 400€."*
- `search-buy-guitar` — *"Encuéntrame una guitarra acústica de segunda mano para empezar, por menos de 150€."*
- `find-best-hotel-city` — *"Búscame el mejor hotel en Sevilla para el fin de semana del 20, con buena valoración y menos de 120€ la noche."*
- `find-direct-flight-budget` — *"Búscame un vuelo directo Madrid–Roma en octubre, lo más barato posible."*
- `rental-car-automatic-airport` — *"Búscame un coche de alquiler automático en el aeropuerto de Málaga para la semana que viene."*
- `find-concert-tickets` — *"Búscame entradas para un concierto de Rosalía en Madrid este mes, lo más baratas posible."*
- `things-to-do-nearby-weekend` — *"Busca planes para este fin de semana cerca de mi casa."*
- `kid-friendly-activity-nearby` — *"Encuéntrame un plan con niños para este domingo cerca de casa."*

**Tier 3 — multi-step, single domain, real deadline**
- `itv-before-deadline` — *"Tengo que pasar la ITV antes del día 30 — búscame cita y avísame el día antes."*
- `renew-passport-before-expiry` — *"Mi pasaporte caduca en dos meses — pide cita para renovarlo y recuérdamelo."*
- `track-package-reschedule` — *"Sigue el paquete que estoy esperando y, si no voy a estar, reprograma la entrega."*
- `negotiate-lower-phone-bill` — *"Llama a mi operador y consigue que me bajen la tarifa del móvil."*
- `file-expense-report` — *"Prepárame el informe de gastos del viaje de la semana pasada y envíalo a administración."*
- `split-dinner-bill-friends` — *"Divide la cuenta de la cena de anoche entre los cuatro y mándales el importe."*

**Tier 4 — cross-domain orchestration**
- `weekend-trip-san-sebastian` — *"Organízame un fin de semana en San Sebastián: tren, hotel con desayuno y mesa el sábado noche."*
- `clean-and-reply-inbox` — *"Limpia mi bandeja de entrada de las últimas dos semanas y responde solo lo urgente."*
- `archive-newsletters` — *"Archívame las newsletters acumuladas y déjame solo lo que importa."*
- `rebook-delayed-flight-now` — *"Mi vuelo se ha retrasado más de una hora — búscame otro y avísame."*
- `found-next-apartment` — *"Búscame piso de alquiler en Chamberí, máximo 1200€, y agenda las visitas que encajen con mi agenda."*
- `moms-birthday-flowers-onetime` — *"Es el cumpleaños de mi madre pasado mañana — pide flores y que lleguen a su casa por la mañana."*

**Tier 5 — standing/reactive over time**
- `watch-flight-rebook-automatically` — *"Vigila mi vuelo a Barcelona; si se retrasa más de una hora, búscame otro sin preguntar y avísame."*
- `track-price-drop-buy` — *"Vigila el precio de este monitor y cómpralo en cuanto baje de 250€."*
- `cancel-trial-before-it-charges` — *"Tengo una prueba gratuita que se convierte en pago el viernes — cancélala tú antes si no he vuelto a usarla."*
- `gym-membership-no-silent-renew` — *"No dejes que la cuota del gimnasio se renueve sola sin decírmelo antes."*
- `moms-birthday-flowers-recurring` — *"No olvides el cumpleaños de mi madre — pide flores el día antes, cada año."*
- `grocery-restock-reactive` — *"Cuando veas que se acaba la leche o el café, pídelos otra vez sin que tenga que decírtelo."*

**Tier 6 — multi-agent over email**
- `coordinate-lunch-with-pedro` — *"Dile al agente de Pedro que quedamos el jueves a comer — que proponga sitio y hora y me lo confirmes."*
- `split-airbnb-with-marta` — *"Coordina con el agente de Marta un apartamento compartido para el finde en Lisboa y divide la cuenta."*
- `reschedule-meetup-conflict` — *"El agente de Javi te va a proponer quedar el sábado — mira mi agenda y negocia una hora que me valga."*
- `confirm-restaurant-reservation-together` — *"Ponte de acuerdo con el agente de Ana para reservar mesa esta noche — que ninguno reserve dos veces."*
- `plan-joint-trip-with-friend` — *"Habla con el agente de Laura y cuadrad un itinerario común para el viaje de septiembre."*

**Tier 7 — multi-agent over WhatsApp/Telegram (BLOCKED)**
- `coordinate-lunch-whatsapp` — *"Escríbele por WhatsApp al agente de Pedro y quedad para comer el jueves."*
- `split-trip-telegram` — *"Habla por Telegram con el agente de Marta y repartid el itinerario del viaje."*
- `group-plan-three-friends` — *"Coordínate con los agentes de Pedro, Marta y Javi por WhatsApp para quedar todos el sábado."*
- `realtime-eta-share` — *"Avisa por WhatsApp al agente de Ana en cuanto salga de casa, para que sepa a qué hora llego."*

### United States (us)

**Tier 1 — bounded single-site action**
- `restaurant-tonight-nyc` — *"Book a table for 2 tonight at 7pm at Katz's Delicatessen."*
- `cancel-subscription-before-charge` — *"Cancel my Hulu trial before it charges me on the 15th."*
- `reorder-prescription` — *"Reorder my blood-pressure prescription from CVS."*
- `pay-known-bill` — *"Pay this month's electric bill before it's due on the 5th."*
- `renew-gym-membership` — *"Renew this month's gym membership at Equinox."*
- `book-barber-slot` — *"Book my usual barber for Saturday morning."*
- `book-hotel-night-known` — *"Book one night at the Ace Hotel downtown for September 20th."*
- `buy-known-product` — *"Buy the book on my Amazon wishlist."*
- `find-theatre-tickets` — *"Get me two tickets to The Lion King musical in New York for Saturday."*

**Tier 2 — search + compare + choose**
- `best-pediatric-dentists` — *"Find the 3 best-rated pediatric dentists near me and book the top one."*
- `compare-flights-sf-austin` — *"Compare flights SF-Austin for next long weekend and book the cheapest with a carry-on included."*
- `best-plumber-same-day` — *"Find a plumber who can come today, top-rated near me."*
- `compare-insurance-quotes` — *"Compare three car insurance quotes and tell me which one's the best deal."*
- `cheapest-monitor` — *"Find the cheapest 27-inch 4K monitor with good reviews."*
- `best-rated-rental-car` — *"Find the best-rated rental car in Austin for the weekend."*
- `compare-phone-plans` — *"Compare cell phone plans and tell me which one saves me the most."*
- `weekend-barber-availability` — *"Find a barber with an opening this weekend near me."*
- `search-buy-used-car` — *"Find me a used car, diesel or hybrid, under 60k miles and under $14,000, and give me the top 3."*
- `search-buy-motorcycle` — *"Find me a used 300cc motorcycle in good condition for under $3,000."*
- `search-buy-bicycle` — *"Find me a used mountain bike in good condition, size M, for under $350."*
- `search-secondhand-monitor` — *"Find me a used 27-inch+ monitor for under $150."*
- `search-buy-book` — *"Find the latest book by Colleen Hoover and buy it from whichever store has it cheapest."*
- `search-buy-camera` — *"Find me a used DSLR camera with a low shutter count for under $400."*
- `search-buy-guitar` — *"Find me a used acoustic guitar for beginners under $150."*
- `find-best-hotel-city` — *"Find me the best hotel in New Orleans for the weekend of the 20th, well-rated and under $150 a night."*
- `find-direct-flight-budget` — *"Find me a direct flight NYC-Rome in October, as cheap as possible."*
- `rental-car-automatic-airport` — *"Find me an automatic rental car at Denver airport for next week."*
- `find-concert-tickets` — *"Find me tickets to a Beyoncé concert in LA this month, as cheap as possible."*
- `things-to-do-nearby-weekend` — *"Find things to do this weekend near me."*
- `kid-friendly-activity-nearby` — *"Find a kid-friendly activity near me for Sunday."*

**Tier 3 — multi-step, single domain, real deadline**
- `smog-check-before-deadline` — *"My car's smog check is due before the 30th - find an appointment and remind me the day before."*
- `renew-passport-before-expiry` — *"My passport expires in two months - book a renewal appointment and remind me."*
- `track-package-reschedule` — *"Track the package I'm expecting and reschedule delivery if I won't be home."*
- `negotiate-lower-phone-bill` — *"Call my carrier and get my phone bill lowered."*
- `file-expense-report` — *"Put together last week's trip expense report and send it to accounting."*
- `split-dinner-bill-friends` — *"Split last night's dinner bill four ways and send everyone their share."*

**Tier 4 — cross-domain orchestration**
- `weekend-trip-austin` — *"Plan a weekend in Austin: flight, hotel with breakfast, dinner reservation Saturday."*
- `clean-and-reply-inbox` — *"Clean up my inbox from the last two weeks and reply to what's actually urgent."*
- `archive-newsletters` — *"Archive my backlog of newsletters and leave only what matters."*
- `rebook-delayed-flight-now` — *"My flight just got delayed over an hour - find another one and let me know."*
- `found-next-apartment` — *"Find me a 1-bedroom in Brooklyn under $2800 and schedule the tours that fit my calendar."*
- `moms-birthday-flowers-onetime` — *"It's my mom's birthday the day after tomorrow - order flowers for morning delivery."*

**Tier 5 — standing/reactive over time**
- `watch-flight-rebook-automatically` — *"Watch my flight to Chicago; if it's delayed more than an hour, rebook me automatically and let me know."*
- `track-price-drop-buy` — *"Track this monitor's price and buy it the moment it drops below $250."*
- `cancel-trial-before-it-charges` — *"I've got a free trial that converts to paid Friday - cancel it yourself if I haven't used it again."*
- `gym-membership-no-silent-renew` — *"Don't let my gym membership auto-renew without checking with me first."*
- `moms-birthday-flowers-recurring` — *"Never let me forget my mom's birthday - order flowers the day before, every year."*
- `grocery-restock-reactive` — *"When you notice we're low on milk or coffee, reorder it without me having to ask."*

**Tier 6 — multi-agent over email**
- `coordinate-dinner-with-alex` — *"Ask Alex's agent to lock in Friday dinner - let them pick the place, just confirm the time with me."*
- `split-airbnb-with-jordan` — *"Coordinate with Jordan's agent on a shared Airbnb for the weekend in Miami and split the bill."*
- `resolve-meetup-conflict` — *"Sam's agent is going to propose meeting Saturday - check my calendar and negotiate a time that works."*
- `confirm-restaurant-together` — *"Sync up with Taylor's agent on tonight's reservation - make sure neither of us double-books."*
- `plan-joint-trip-with-friend` — *"Talk to Morgan's agent and align on a shared itinerary for the September trip."*

**Tier 7 — multi-agent over WhatsApp/Telegram (BLOCKED)**
- `coordinate-dinner-whatsapp` — *"Text Alex's agent on WhatsApp and lock in Thursday dinner."*
- `split-trip-telegram` — *"Message Jordan's agent on Telegram and split up the trip itinerary."*
- `group-plan-three-friends` — *"Coordinate with Alex, Jordan and Sam's agents over WhatsApp to get everyone together Saturday."*
- `realtime-eta-share` — *"Ping Taylor's agent on WhatsApp the moment I leave, so they know when I'll arrive."*
