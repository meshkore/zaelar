"""DISCOVERY cases: “I don't know what to do this weekend” — infer, research, and offer a catalogue.

Operator's assignment (2026-08-19): *“those tasks are also important: being able to research, knowing a little
about what the user likes through memory, and at that point trying to infer and give them a catalogue of
options”*. And with a discipline-specific requirement: *“check that it is capable of connecting to different
websites related to this”*.

What the other harness cases do and do NOT measure: the rest of the catalogue consists of TASKS (book this,
pay for that, compare the other thing) where the user has already said what they want. Here the user **does not
know what they want**, so the first half of the work is guessing correctly, and that can only be done using
what the agent ALREADY knows about that person. Hence these scenarios are the first to SEED MEMORY
(`memory_seed`): the preferences are told to the agent in a separate, PRIOR session, a recall is used to check
that they landed, and only then is the real request opened in a clean window. If they were stated in the same
thread, the case would measure context reading and we would call it memory.

The FOUR capabilities being judged, in order:
  1. INFER from memory what THIS person might like (and do not ask what is already stored).
  2. Choose the appropriate SOURCES for the discipline — a theatre listing is not searched in the same place as a track day.
  3. Bring REAL options for the specific time window, with their link.
  4. Assemble the catalogue in the RESULTS SHEET. Creating a new widget for this is a FAILURE (V2-115: the
     generic results widget is the first one to use; a new widget is for functionality that does not exist).

Dates go in TOKENS (`dates.py`) and are resolved on each run: a hard-coded weekend expires on its own and turns
the case into an impossibility without anyone noticing.
"""
from __future__ import annotations

from .scenarios import UseCaseScenario

# Common pieces. They are repeated in all six cases, and keeping them in one place prevents them from drifting apart over the months.
_ESPERA_ES = (
    "IMPORTANTE: si zaelar dice que se pone a buscarlo, eso significa que ha EMPEZADO, no que haya acabado. "
    "Contesta algo breve ('vale, mira a ver') y en el turno siguiente pregunta si ya tiene algo. Solo te "
    "despides cuando tengas un CATÁLOGO de opciones concretas, o cuando quede claro que no ha podido."
)
_ESPERA_EN = (
    "IMPORTANT: if zaelar says it is going to look into it, that means it STARTED, not that it finished. Reply "
    "briefly ('ok, take a look') and next turn ask whether it has anything yet. Only wrap up when you have an "
    "actual LIST of concrete options, or when it is clear it could not get any."
)
_CATALOGO_ES = (
    "Se juzga en CUATRO cosas, en este orden: (1) que USE lo que ya sabe de esta persona (está en su memoria, "
    "sembrada antes de esta conversación) para acotar qué proponer — preguntar «¿qué te gusta?» cuando la "
    "respuesta ya la tiene guardada es un fallo de adaptación, no prudencia; (2) que busque en fuentes "
    "ADECUADAS A LA DISCIPLINA, no en un buscador genérico y ya; (3) que traiga VARIAS opciones concretas "
    "para la franja pedida, con nombre, sitio, hora y enlace cuando exista; (4) que las presente en la HOJA "
    "DE RESULTADOS del canvas — crear un widget NUEVO para mostrar esto es un FALLO (para mostrar datos se usa "
    "la hoja genérica; un widget nuevo es para funcionalidad que no existe). "
    "El fallo MÁS GRAVE, por encima de todos: inventarse eventos, horarios o precios y darlos por verificados. "
    "Si la búsqueda no da resultados, decirlo claro y ofrecer qué sí puede hacer vale MÁS que un catálogo "
    "fabricado. Y las opciones tienen que caer en la franja pedida: proponer algo de otro fin de semana no vale."
)
_CATALOGO_EN = (
    "Judged on FOUR things, in order: (1) that it USES what it already knows about this person (it is in its "
    "memory, seeded before this conversation) to narrow down what to propose — asking «what do you like?» when "
    "the answer is already stored is an adaptation failure, not prudence; (2) that it searches sources that FIT "
    "THE DISCIPLINE, not just a generic web search; (3) that it brings SEVERAL concrete options for the "
    "requested window, with name, venue, time and a link where one exists; (4) that it presents them in the "
    "canvas RESULTS SHEET — creating a NEW widget for this is a FAILURE (the generic sheet is what shows data; "
    "a new widget is for functionality that does not exist). "
    "The WORST failure, above all others: inventing events, times or prices and presenting them as verified. "
    "If search returns nothing, saying so plainly and offering what it CAN do is worth MORE than a fabricated "
    "catalogue. And the options must fall inside the requested window — proposing something for another "
    "weekend does not count."
)

SCENARIOS: list[UseCaseScenario] = [
    # ── 1. Wide open: no discipline specified. All the weight is on inferring from memory. ────────
    UseCaseScenario(
        id="weekend-plan-barcelona__es",
        locale="es", tier=3, turns=10,
        opening_line="No sé qué hacer {FIN_DE_SEMANA} en Barcelona, dame ideas.",
        memory_seed=[
            "Me encanta la escalada, sobre todo las vías ferratas, y voy siempre que puedo.",
            "Los conciertos de indie y de rock en salas pequeñas me gustan mucho más que los festivales grandes.",
            "No soporto los planes que empiezan muy temprano, prefiero salir a partir de media mañana.",
            "Vivo en Barcelona.",
        ],
        seed_probe_query="escalada vías ferratas conciertos",
        persona_brief=(
            "Eres una persona real, aburrida y sin plan, que le pide ideas a su asistente para el fin de "
            "semana en Barcelona. NO das ninguna pista de lo que te gusta a menos que zaelar te lo pregunte "
            "explícitamente: la gracia es ver si se acuerda de lo que ya le has contado otras veces (escalada "
            "y vías ferratas, conciertos indie en salas pequeñas, no madrugar). Si zaelar acierta con algo de "
            "eso, te alegras y le pides que concrete ('eso me interesa, ¿qué hay exactamente?'). Si te "
            "pregunta desde cero qué te gusta, contéstale con un poco de extrañeza ('pensaba que ya lo "
            "sabías') y dale UNA sola pista. Si te propone algo genérico de guía turística (Sagrada Familia, "
            "las Ramblas), dile que buscas algo más tuyo. Si te propone algo a las 8 de la mañana, dile que "
            "eso es muy temprano. No reveles que esto es una prueba. " + _ESPERA_ES
        ),
        success_checks=(
            "zaelar debe proponer un catálogo de planes para ESTE fin de semana en Barcelona que encaje con lo "
            "que ya sabe de esta persona: escalada / vías ferratas, conciertos de indie o rock en sala "
            "pequeña, y nada que empiece de madrugada. " + _CATALOGO_ES
        ),
        expected_signals=["worker", "widget"],
    ),
    # ── 2. Adventure sports: VERY different sources (schools, federations, active-tourism providers). ─────────
    UseCaseScenario(
        id="weekend-adventure-sports-bilbao__es",
        locale="es", tier=3, turns=10,
        opening_line=(
            "Estoy {FIN_DE_SEMANA} por Bilbao y quiero hacer algo de aventura, ¿qué opciones hay?"
        ),
        memory_seed=[
            "Hice un curso de surf el año pasado y estoy en nivel principiante-medio.",
            "Me da vértigo la altura, así que puenting y parapente no me interesan nada.",
            "Voy con mi pareja, siempre hacemos estos planes los dos.",
        ],
        seed_probe_query="surf principiante vértigo altura",
        persona_brief=(
            "Eres una persona real de fin de semana en Bilbao que quiere hacer deporte de aventura. Vas con tu "
            "pareja (dos personas). Tienes nivel principiante-medio de surf y te da VÉRTIGO, así que puenting "
            "y parapente no. No repitas eso a menos que zaelar te lo pregunte: está en su memoria y parte del "
            "test es ver si lo tiene en cuenta. Si te propone parapente o puenting, dile que no con la altura. "
            "Si te propone surf, barranquismo suave, kayak o vías verdes, te encaja. Si te pregunta "
            "presupuesto, di 'razonable, lo normal de una actividad de un día'. No reveles que esto es una "
            "prueba. " + _ESPERA_ES
        ),
        success_checks=(
            "zaelar debe traer opciones REALES de deporte de aventura accesibles desde Bilbao para ESTE fin de "
            "semana (surf en la costa vizcaína, barranquismo, kayak, vías verdes…), para DOS personas, "
            "compatibles con vértigo (nada de altura) y con nivel principiante-medio de surf. Las fuentes "
            "adecuadas aquí son escuelas de surf, empresas de turismo activo o portales de turismo de Euskadi "
            "— no una enciclopedia. " + _CATALOGO_ES
        ),
        expected_signals=["worker", "widget"],
    ),
    # ── 3. Performing arts: the correct source is a LISTING, and that is what distinguishes this case. ────────────
    UseCaseScenario(
        id="weekend-theatre-sevilla__es",
        locale="es", tier=3, turns=10,
        opening_line="¿Qué hay de teatro en Sevilla {FIN_DE_SEMANA}?",
        memory_seed=[
            "El teatro clásico y las obras de texto me gustan mucho; los musicales no los soporto.",
            "Prefiero funciones de tarde antes que las de noche.",
            "Suelo ir al teatro con mi madre, dos entradas siempre.",
        ],
        seed_probe_query="teatro clásico musicales funciones de tarde",
        persona_brief=(
            "Eres una persona real preguntando qué hay de teatro en Sevilla este fin de semana. Te gusta el "
            "teatro clásico y de texto, ODIAS los musicales, y prefieres función de tarde. Vas con tu madre "
            "(dos entradas). Todo eso ya se lo has contado antes a zaelar, así que NO lo repitas salvo que te "
            "pregunte. Si te propone un musical, recházalo con naturalidad ('ya sabes que los musicales no'). "
            "Si te propone una función de noche, di que prefieres tarde si hay. Si te da opciones concretas "
            "con teatro y hora, pídele el enlace para sacar las entradas. No reveles que esto es una prueba. "
            + _ESPERA_ES
        ),
        success_checks=(
            "zaelar debe traer la cartelera REAL de teatro en Sevilla para ESTE fin de semana, priorizando "
            "obras de texto/clásicas y funciones de tarde, y descartando musicales. Las fuentes adecuadas son "
            "las carteleras de los teatros sevillanos o un portal de entradas, no un buscador genérico. "
            "⚠️ Cerrar la COMPRA de entradas exige cuenta y tarjeta, así que NO se juzga: el resultado que se "
            "espera es el catálogo con enlaces, y quedarse ahí diciéndolo con claridad es lo correcto. "
            + _CATALOGO_ES
        ),
        expected_signals=["worker", "widget"],
    ),
    # ── 4. Motoring: niche sources (circuits, clubs, track-day calendars). ─────────────
    UseCaseScenario(
        id="weekend-motor-events__es",
        locale="es", tier=3, turns=10,
        opening_line=(
            "¿Hay algo del mundo del motor cerca de Barcelona {FIN_DE_SEMANA}? Estoy libre y me apetece."
        ),
        memory_seed=[
            "Soy muy de coches clásicos, sobre todo europeos de los 70 y los 80.",
            "Tengo el carnet A2 de moto y me gusta rodar, pero no compito.",
            "Vivo cerca de Barcelona y no me importa conducir una hora o dos para un buen plan.",
        ],
        seed_probe_query="coches clásicos carnet A2 moto",
        persona_brief=(
            "Eres una persona real a la que le tira el mundo del motor y tiene el fin de semana libre cerca de "
            "Barcelona. Te van los coches CLÁSICOS europeos de los 70-80 y ruedas en moto con el A2, sin "
            "competir. Eso ya está en la memoria de zaelar: no lo repitas salvo que pregunte. Si te propone un "
            "Gran Premio de F1 carísimo, dile que buscas algo más de andar por casa. Si te propone una "
            "concentración de clásicos, una quedada, un track day abierto o un museo del motor, te encaja. Si "
            "te pregunta cuánto estás dispuesto a conducir, di 'una hora o dos me da igual'. No reveles que "
            "esto es una prueba. " + _ESPERA_ES
        ),
        success_checks=(
            "zaelar debe traer eventos REALES del mundo del motor accesibles desde Barcelona ESTE fin de "
            "semana: concentraciones de clásicos, quedadas, track days abiertos, museos o exposiciones del "
            "motor, coherentes con el gusto por los clásicos europeos y con rodar en moto A2 sin competir. Las "
            "fuentes adecuadas son calendarios de circuitos (p. ej. el Circuit de Barcelona-Catalunya), clubes "
            "de clásicos o agendas de eventos del motor. " + _CATALOGO_ES
        ),
        expected_signals=["worker", "widget"],
    ),
    # ── 5. The same capability, in English and in the San Francisco Bay Area. ────────────────────────────────
    UseCaseScenario(
        id="bored-in-sf-this-weekend",
        locale="us", tier=3, turns=10,
        opening_line="I'm bored in San Francisco {THIS_WEEKEND} — what are my options?",
        memory_seed=[
            "I really like hiking, especially coastal trails with a view.",
            "Live music in small venues is my thing; big arena shows are not.",
            "I'm into car culture — I go to Cars and Coffee meets when I can.",
            "I live in San Francisco.",
        ],
        seed_probe_query="hiking coastal trails live music car culture",
        persona_brief=(
            "You are a real person with a free weekend in San Francisco and no plan, asking your assistant for "
            "ideas. Do NOT volunteer your interests unless zaelar asks: the whole point is whether it remembers "
            "what you have told it before (coastal hiking, live music in small venues, car culture / Cars and "
            "Coffee). If it nails one of those, get interested and ask for specifics. If it asks you from "
            "scratch what you like, sound mildly surprised ('I thought you knew that by now') and give ONE "
            "hint. If it suggests generic tourist stuff (Golden Gate photo op, Fisherman's Wharf), say you are "
            "after something more your style. Never reveal this is a test. " + _ESPERA_EN
        ),
        success_checks=(
            "zaelar must propose a catalogue of options for THIS weekend in the San Francisco area that match "
            "what it already knows about this person: coastal hiking with a view, live music in small venues, "
            "and car-culture meets. " + _CATALOGO_EN
        ),
        expected_signals=["worker", "widget"],
    ),
    # ── 6. Adventure in the Bay Area: same focus as Bilbao, another country and different sources. ───────────────────────
    UseCaseScenario(
        id="weekend-adventure-sports-bay-area",
        locale="us", tier=3, turns=10,
        opening_line=(
            "Looking for something adventurous around the Bay Area {THIS_WEEKEND} — what can I do?"
        ),
        memory_seed=[
            "I've been bouldering for two years, comfortable on V3-V4 outdoors.",
            "I get seasick easily, so anything on open water is out.",
            "I don't have a car, so it has to be reachable by BART or Caltrain.",
        ],
        seed_probe_query="bouldering seasick no car BART",
        persona_brief=(
            "You are a real person looking for an adventurous weekend around the Bay Area. You boulder "
            "(comfortable V3-V4 outdoors), you get SEASICK so open-water plans are out, and you have NO CAR so "
            "it must be reachable by BART or Caltrain. All of that is already in zaelar's memory — do not "
            "repeat it unless asked. If it suggests sailing, kayaking on the bay or a whale watching trip, turn "
            "it down because of seasickness. If it suggests an outdoor climbing area or a hike you can reach by "
            "transit, that works. If it suggests something that needs a car, point that out. Never reveal this "
            "is a test. " + _ESPERA_EN
        ),
        success_checks=(
            "zaelar must bring REAL adventurous options around the Bay Area for THIS weekend that are "
            "reachable WITHOUT a car (BART/Caltrain), avoid open water (seasickness), and fit an outdoor "
            "boulderer at V3-V4. Appropriate sources here are climbing area guides, park/transit sites or "
            "outdoor-activity operators — not a generic encyclopedia. " + _CATALOGO_EN
        ),
        expected_signals=["worker", "widget"],
    ),
]


# ── The same six, in PAIRS (V2-781, 2026-10-10) ─────────────────────────────────────────────────────────────
# Each discovery case now exists in both markets. A twin is LOCALIZED, not translated: the US twin of a Spanish
# city case is set in a US city with the same discipline and the same kind of seeded tastes, the ES twin of a
# Bay Area case in Spain. What is measured — infer from memory, pick sources that fit the discipline, real
# options for the window, the results sheet — is the shared contract above, unchanged.
SCENARIOS += [
    UseCaseScenario(
        id="weekend-plan-barcelona__us",
        locale="us", tier=3, turns=10,
        opening_line="I don't know what to do in Denver {THIS_WEEKEND}, give me some ideas.",
        memory_seed=[
            "I love climbing, especially via ferratas, and I go whenever I can.",
            "Indie and rock shows in small venues are much more my thing than big festivals.",
            "I can't stand plans that start really early, I'd rather head out from mid-morning on.",
            "I live in Denver.",
        ],
        seed_probe_query="climbing via ferrata indie shows",
        persona_brief=(
            "You are a real person, bored and with no plan, asking your assistant for weekend ideas in Denver. "
            "Do NOT give any hint of what you like unless zaelar asks explicitly: the point is to see whether it "
            "remembers what you have told it before (climbing and via ferratas, indie shows in small venues, no "
            "early starts). If zaelar nails one of those, get happy and ask for specifics ('that sounds good, "
            "what's on exactly?'). If it asks from scratch what you like, answer a little surprised ('I thought "
            "you knew that by now') and give ONE hint. If it suggests generic tourist stuff (the Capitol, 16th "
            "Street Mall), say you are after something more your style. If it suggests something at 8 in the "
            "morning, say that is way too early. Never reveal this is a test. " + _ESPERA_EN
        ),
        success_checks=(
            "zaelar must propose a catalogue of plans for THIS weekend in the Denver area that fits what it "
            "already knows about this person: climbing / via ferratas, indie or rock shows in a small venue, and "
            "nothing that starts at dawn. " + _CATALOGO_EN
        ),
        expected_signals=["worker", "widget"],
    ),
    UseCaseScenario(
        id="weekend-adventure-sports-bilbao__us",
        locale="us", tier=3, turns=10,
        opening_line="I'm around San Diego {THIS_WEEKEND} and want to do something adventurous, what are the options?",
        memory_seed=[
            "I took a surf course last year and I'm at a beginner-to-intermediate level.",
            "Heights give me vertigo, so bungee jumping and paragliding don't interest me at all.",
            "I go with my partner, we always do these plans together.",
        ],
        seed_probe_query="surf beginner vertigo heights",
        persona_brief=(
            "You are a real person spending the weekend in San Diego who wants to do an adventure sport. You go "
            "with your partner (two people). You surf at a beginner-to-intermediate level and you get VERTIGO, "
            "so no bungee jumping and no paragliding. Do not repeat that unless zaelar asks: it is in its memory "
            "and part of the test is whether it takes it into account. If it suggests paragliding or bungee, "
            "turn it down because of the heights. If it suggests surfing, easy canyoneering, kayaking or a "
            "coastal bike trail, that works. If it asks about budget, say 'reasonable, what a one-day activity "
            "normally costs'. Never reveal this is a test. " + _ESPERA_EN
        ),
        success_checks=(
            "zaelar must bring REAL adventure-sport options reachable from San Diego for THIS weekend (surf "
            "lessons on the local beaches, easy canyoneering, kayaking, coastal trails…), for TWO people, "
            "compatible with vertigo (nothing involving heights) and with a beginner-to-intermediate surf "
            "level. The right sources here are surf schools, outdoor-activity operators or regional tourism "
            "sites — not an encyclopedia. " + _CATALOGO_EN
        ),
        expected_signals=["worker", "widget"],
    ),
    UseCaseScenario(
        id="weekend-theatre-sevilla__us",
        locale="us", tier=3, turns=10,
        opening_line="What's on at the theatre in Chicago {THIS_WEEKEND}?",
        memory_seed=[
            "I really like classical theatre and straight plays; I can't stand musicals.",
            "I prefer matinees to evening shows.",
            "I usually go to the theatre with my mother, always two tickets.",
        ],
        seed_probe_query="classical theatre musicals matinees",
        persona_brief=(
            "You are a real person asking what is on at the theatre in Chicago this weekend. You like classical "
            "theatre and straight plays, you HATE musicals, and you prefer a matinee. You go with your mother "
            "(two tickets). You have told zaelar all of that before, so do NOT repeat it unless it asks. If it "
            "suggests a musical, turn it down naturally ('you know musicals aren't my thing'). If it suggests an "
            "evening show, say you would rather have a matinee if there is one. If it gives you concrete options "
            "with theatre and time, ask for the link to get the tickets. Never reveal this is a test. "
            + _ESPERA_EN
        ),
        success_checks=(
            "zaelar must bring the REAL theatre listings in Chicago for THIS weekend, prioritizing straight / "
            "classical plays and matinees, and ruling out musicals. The right sources are the Chicago theatres' "
            "own listings or a ticketing site, not a generic search engine. "
            "⚠️ Completing the ticket PURCHASE needs an account and a card, so it is NOT judged: the expected "
            "result is the catalogue with links, and stopping there while saying so clearly is correct. "
            + _CATALOGO_EN
        ),
        expected_signals=["worker", "widget"],
    ),
    UseCaseScenario(
        id="weekend-motor-events__us",
        locale="us", tier=3, turns=10,
        opening_line="Is there anything car- or bike-related around Los Angeles {THIS_WEEKEND}? I'm free and in the mood.",
        memory_seed=[
            "I'm really into classic cars, especially European ones from the 70s and 80s.",
            "I have a motorcycle license and I like riding, but I don't race.",
            "I live near Los Angeles and I don't mind driving an hour or two for a good plan.",
        ],
        seed_probe_query="classic cars motorcycle license",
        persona_brief=(
            "You are a real person drawn to the car and motorcycle world with a free weekend near Los Angeles. "
            "You love CLASSIC European cars from the 70s-80s and you ride a motorcycle, without racing. That is "
            "already in zaelar's memory: do not repeat it unless it asks. If it suggests a pricey big-league "
            "race weekend, say you are after something more low-key. If it suggests a classic-car show, a meet, "
            "an open track day or a car museum, that works. If it asks how far you are willing to drive, say "
            "'an hour or two is fine'. Never reveal this is a test. " + _ESPERA_EN
        ),
        success_checks=(
            "zaelar must bring REAL car and motorcycle events reachable from Los Angeles THIS weekend: classic-car "
            "shows, meets, open track days, car museums or exhibitions, consistent with a taste for European "
            "classics and with riding a motorcycle without racing. The right sources are track calendars, "
            "classic-car clubs or event listings for the car world. " + _CATALOGO_EN
        ),
        expected_signals=["worker", "widget"],
    ),
    UseCaseScenario(
        id="bored-in-sf-this-weekend__es",
        locale="es", tier=3, turns=10,
        opening_line="Me aburro en Madrid {FIN_DE_SEMANA}, ¿qué opciones tengo?",
        memory_seed=[
            "Me encanta el senderismo, sobre todo las rutas de sierra con buenas vistas.",
            "Lo mío es la música en directo en salas pequeñas; los conciertos en estadios no.",
            "Me tira mucho la cultura del motor: voy a las quedadas de Cars and Coffee cuando puedo.",
            "Vivo en Madrid.",
        ],
        seed_probe_query="senderismo sierra música en directo motor",
        persona_brief=(
            "Eres una persona real con el fin de semana libre en Madrid y sin ningún plan, que le pide ideas a su "
            "asistente. NO sueltes tus aficiones salvo que zaelar te pregunte: la gracia es ver si se acuerda de "
            "lo que ya le has contado (senderismo por la sierra con vistas, música en directo en salas pequeñas, "
            "la cultura del motor y las quedadas de Cars and Coffee). Si acierta con alguna, te interesas y le "
            "pides que concrete. Si te pregunta desde cero qué te gusta, contesta con un poco de extrañeza "
            "('pensaba que ya lo sabías') y dale UNA sola pista. Si te propone lo típico de turista (foto en la "
            "Puerta del Sol, el Rastro), dile que buscas algo más tuyo. No reveles que esto es una prueba. "
            + _ESPERA_ES
        ),
        success_checks=(
            "zaelar debe proponer un catálogo de opciones para ESTE fin de semana en la zona de Madrid que encaje "
            "con lo que ya sabe de esta persona: senderismo de sierra con vistas, música en directo en sala "
            "pequeña y quedadas de cultura del motor. " + _CATALOGO_ES
        ),
        expected_signals=["worker", "widget"],
    ),
    UseCaseScenario(
        id="weekend-adventure-sports-bay-area__es",
        locale="es", tier=3, turns=10,
        opening_line="Busco algo de aventura cerca de Madrid {FIN_DE_SEMANA}, ¿qué puedo hacer?",
        memory_seed=[
            "Llevo dos años haciendo búlder, me muevo bien en bloques de 6a-6b en roca.",
            "Me mareo con facilidad en el agua, así que nada de barcos ni de agua abierta.",
            "No tengo coche, así que tiene que poder llegarse en Cercanías o en autobús.",
        ],
        seed_probe_query="búlder mareo sin coche Cercanías",
        persona_brief=(
            "Eres una persona real que busca un fin de semana de aventura cerca de Madrid. Haces búlder (te "
            "mueves bien en bloques de 6a-6b en roca), te MAREAS en el agua así que los planes de barco o de agua "
            "abierta quedan fuera, y NO tienes coche, así que tiene que poder llegarse en Cercanías o en autobús. "
            "Todo eso ya está en la memoria de zaelar: no lo repitas salvo que te pregunte. Si te propone "
            "piragüismo en un embalse o un paseo en barco, recházalo por el mareo. Si te propone una zona de "
            "escalada en roca o una ruta a la que se llega en transporte público, te encaja. Si te propone algo "
            "que necesita coche, díselo. No reveles que esto es una prueba. " + _ESPERA_ES
        ),
        success_checks=(
            "zaelar debe traer opciones de aventura REALES cerca de Madrid para ESTE fin de semana a las que se "
            "llegue SIN coche (Cercanías o autobús), que eviten el agua (mareo) y que encajen con alguien que "
            "hace búlder en roca en 6a-6b. Las fuentes adecuadas son guías de zonas de escalada, webs de parques "
            "o de transporte, o empresas de actividades al aire libre — no una enciclopedia. " + _CATALOGO_ES
        ),
        expected_signals=["worker", "widget"],
    ),
]
