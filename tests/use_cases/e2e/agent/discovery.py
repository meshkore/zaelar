"""Casos de DESCUBRIMIENTO: «no sé qué hacer este fin de semana» — inferir, investigar y ofrecer catálogo.

Encargo del operador (2026-08-19): *«esas tareas también son importantes: el ser capaz de investigar, saber un
poquito qué le gusta al usuario a través de la memoria, y en ese momento intentar inferir y darle un catálogo
de opciones»*. Y con una exigencia por disciplina: *«comprobar que es capaz de conectarse a diferentes páginas
web relacionadas con esto»*.

Lo que miden y NO miden los otros casos del arnés: el resto del catálogo son ENCARGOS (reserva esto, paga
aquello, compárame lo otro) donde el usuario ya dijo lo que quiere. Aquí el usuario **no sabe lo que quiere**,
así que la primera mitad del trabajo es adivinarlo bien, y eso solo se puede hacer con lo que el agente YA
sabe de esa persona. De ahí que estos escenarios sean los primeros que SIEMBRAN MEMORIA
(`memory_seed`): las preferencias se le cuentan al agente en una sesión ANTERIOR y distinta, se comprueba con
un recall que aterrizaron, y solo entonces se abre la petición real en una ventana limpia. Si se dijeran en el
mismo hilo, el caso mediría lectura de contexto y lo llamaríamos memoria.

Las CUATRO capacidades que se juzgan, en orden:
  1. INFERIR de la memoria qué le puede gustar a ESTA persona (y no preguntar lo que ya tiene guardado).
  2. Elegir las FUENTES adecuadas a la disciplina — una cartelera de teatro no se busca donde un track day.
  3. Traer opciones REALES para la franja concreta, con su enlace.
  4. Montar el catálogo en la HOJA DE RESULTADOS. Crear un widget nuevo para esto es un FALLO (V2-115: el
     widget genérico de resultados es el primero a usar; un widget nuevo es para funcionalidad que no existe).

Las fechas van en TOKENS (`dates.py`) y se resuelven en cada corrida: un fin de semana escrito a mano caduca
solo y convierte el caso en imposible sin que nadie se dé cuenta.
"""
from __future__ import annotations

from .scenarios import UseCaseScenario

# Trozos comunes. Se repiten en los seis casos y tenerlos una vez evita que se vayan separando con los meses.
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
    # ── 1. Abierto de par en par: ninguna disciplina dicha. Todo el peso en inferir de la memoria. ────────
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
        expected_signals=["Brain Workers", "Widgets"],
    ),
    # ── 2. Deportes de aventura: fuentes MUY distintas (escuelas, federaciones, turismo activo). ─────────
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
        expected_signals=["Brain Workers", "Widgets"],
    ),
    # ── 3. Artes escénicas: la fuente correcta es una CARTELERA, y eso es lo que discrimina. ────────────
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
        expected_signals=["Brain Workers", "Widgets"],
    ),
    # ── 4. Mundo del motor: fuentes de nicho (circuitos, clubes, calendarios de track day). ─────────────
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
        expected_signals=["Brain Workers", "Widgets"],
    ),
    # ── 5. La misma capacidad, en inglés y en la bahía de San Francisco. ────────────────────────────────
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
        expected_signals=["Brain Workers", "Widgets"],
    ),
    # ── 6. Aventura en la bahía: mismo eje que Bilbao, otro país y otras fuentes. ───────────────────────
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
        expected_signals=["Brain Workers", "Widgets"],
    ),
]
