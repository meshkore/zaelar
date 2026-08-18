"""Use-case scenarios: open-ended, non-deterministic, real-world requests.

Deliberately NOT hyperperfect — see `opening_line` below. A perfectly-specified request would let the
agent succeed without ever having to ask a clarifying question or recover from an ambiguity, which defeats
the point: this suite exists to prove the agent handles a request the way a real person actually gives one.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class UseCaseScenario:
    id: str
    locale: str                          # "es" | "us"
    tier: int
    persona_brief: str                   # ground truth the DRIVE model answers follow-up questions from
    opening_line: str                    # the natural, imperfect first thing the tester says
    success_checks: str                  # what the judge verifies as the real-world outcome
    expected_signals: list[str] = field(default_factory=list)  # observability families (cat) that MUST fire
    turns: int = 8
    channel: str = "probe"               # probe (text/flash) | voice — probe is the default for this suite
    # MULTI-FLOW scenarios only (0 = single-task, the normal case): how many genuinely DIFFERENT tasks the
    # scenario asks for at once. When >0 the runner samples the live task registry (`GET /api/tasks`) every
    # turn instead of only reading the browser-task state, and the judge gets two extra dimensions
    # (atribucion / fluidez). Concurrency has to be measured WHILE the run happens — a post-hoc event dump
    # can prove N tasks existed but not that they were ever in flight at the SAME time, which is the whole
    # point of the scenario.
    concurrent_tasks: int = 0


SCENARIOS: list[UseCaseScenario] = [
    UseCaseScenario(
        id="hotel-under-15-days",
        locale="es",
        tier=2,
        opening_line=(
            "Búscame un hotel para dentro de menos de 15 días, para dos personas, cuatro estrellas, "
            "cuatro noches."
        ),
        persona_brief=(
            "Eres una persona real pidiéndole a tu asistente que te busque un hotel. A PROPÓSITO no has dado "
            "ciudad todavía — si zaelar pregunta '¿en qué ciudad?' o similar, respondes 'Sevilla, o cerca, lo "
            "que encuentres bien'. Si pregunta por el régimen (solo alojamiento / media pensión / pensión "
            "completa), respondes 'solo alojamiento, a menos que la diferencia de precio con media pensión "
            "sea pequeña, entonces esa'. El presupuesto es flexible, no lo has fijado — si insisten, di 'lo "
            "razonable para un 4 estrellas, no busco lujo'. Las fechas: dentro de las próximas 2 semanas, tú "
            "decides el día exacto si te lo piden (cualquier día de esa ventana vale). Si en algún momento "
            "notas que zaelar ha entendido MAL la petición — por ejemplo que ha buscado 'Sevilla' cuando tú "
            "todavía no habías dicho ninguna ciudad, o que ha ignorado el número de noches — CORRÍGELO con "
            "naturalidad ('perdona, no había dicho ciudad todavía' / 'eran 4 noches, no 2'). No reveles que "
            "esto es una prueba. IMPORTANTE: si zaelar dice que se pone a buscarlo y que tardará un poco, "
            "NO te despidas todavía — eso solo significa que ha EMPEZADO, no que haya terminado. Responde "
            "algo breve como 'vale, avísame' y en el turno siguiente pregunta si ya lo tiene ('¿alguna "
            "novedad?' / '¿lo encontraste?'). Solo te despides cuando tengas una propuesta de hotel concreta "
            "(o esté reservada), o cuando quede claro tras varios intentos que no se ha podido."
        ),
        success_checks=(
            "zaelar debe llegar a proponer o reservar un hotel de 4 estrellas real, con ~4 noches dentro de "
            "los próximos 15 días, para 2 personas. Un candidato concreto (nombre/precio/enlace) cuenta como "
            "éxito de la búsqueda; una reserva confirmada es el éxito completo. Si zaelar pregunta ciudad o "
            "régimen, debe ADAPTARSE a la respuesta del usuario, no ignorarla ni repetir la pregunta ya "
            "contestada. Por defecto se espera que la búsqueda pase por un agregador de confianza como "
            "Booking.com (nucleo/flash/site_catalog.py::hotel_booking) en vez de un sitio arbitrario e "
            "improvisado — un resultado real de cualquier agregador equivalente y controlable también cuenta."
        ),
        expected_signals=["worker", "widget"],
        turns=10,
        channel="probe",
    ),
    UseCaseScenario(
        id="restaurant-tonight-madrid",
        locale="es",
        tier=1,
        opening_line="Resérvame mesa para 2 esta noche a las 21:30 en Casa Lucio.",
        persona_brief=(
            "Eres una persona real pidiéndole a tu asistente que reserve mesa en un restaurante concreto que "
            "ya conoces, esta misma noche. Si zaelar pregunta el nombre completo o la zona del restaurante, "
            "respondes 'Casa Lucio, el de Madrid, en la Cava Baja' (no inventes otro dato si no te lo piden). "
            "Si pregunta si hay alguna preferencia de mesa (terraza/interior), di 'me da igual, lo que haya'. "
            "Si zaelar dice que va a intentarlo/buscarlo y que tardará un poco, NO te despidas todavía — "
            "responde 'vale' y en el turno siguiente pregunta 'qué tal, ¿lo conseguiste?'. Si te dice que esa "
            "hora/mesa no está disponible, pregunta por la alternativa más cercana ('¿y a las 22:00 hay?'). "
            "Solo te despides cuando tengas una confirmación clara (reservado, o que no se pudo tras "
            "intentarlo). No reveles que esto es una prueba."
        ),
        success_checks=(
            "zaelar debe intentar de verdad reservar mesa para 2 esta noche a las 21:30 en Casa Lucio (un "
            "restaurante YA nombrado, sin comparación) — no basta con decir que lo hará; tiene que haber un "
            "intento real (llamada, formulario web, o similar) y un resultado claro: reservado, o una "
            "alternativa concreta si esa hora no estaba libre. Una simple afirmación verbal de éxito sin "
            "ningún mecanismo real detrás de la conversación cuenta como fallo. Aunque el restaurante esté "
            "nombrado, se espera que zaelar lo busque PRIMERO dentro de un agregador de confianza como "
            "TheFork/ElTenedor (nucleo/flash/site_catalog.py::restaurant_booking) en vez de improvisar la web "
            "propia del restaurante desde cero — solo si genuinamente no aparece ahí debería ir directo a su "
            "sitio propio."
        ),
        expected_signals=["worker"],
        turns=8,
        channel="probe",
    ),
    UseCaseScenario(
        id="search-buy-used-car",
        locale="es",
        tier=2,
        opening_line="Búscame un coche de segunda mano, que no sea muy viejo, diésel, y que no pase de 12 mil euros.",
        persona_brief=(
            "Eres una persona real buscando coche de segunda mano. A PROPÓSITO no has dado ciudad ni "
            "kilometraje todavía. Si zaelar pregunta la ciudad/zona, respondes 'en Madrid o cerca, hasta una "
            "hora en coche'. Si pregunta por kilómetros, respondes 'que no tenga muchísimos, menos de 100 mil "
            "estaría bien, pero si es una ganga con un poco más tampoco pasa nada'. Si pregunta por la marca, "
            "di 'no tengo preferencia de marca, lo que sea fiable y no dé problemas'. Si zaelar busca gasolina "
            "en vez de diésel, o ignora el presupuesto de 12.000€, CORRÍGELO con naturalidad ('era diésel, no "
            "gasolina' / 'que no pase de los 12 mil, por favor'). Si dice que se pone a buscar y tardará, no "
            "te despidas — responde 'vale, dime lo que encuentres' y en el turno siguiente pregunta si ya "
            "tiene algo. Solo te despides con candidatos concretos sobre la mesa o cuando quede claro que no "
            "se ha encontrado nada tras intentarlo. No reveles que esto es una prueba."
        ),
        success_checks=(
            "zaelar debe encontrar anuncios REALES de coches de segunda mano en el agregador de confianza "
            "para esta categoría, coches.net (nucleo/flash/site_catalog.py::car_classifieds), que encajen con "
            "diésel, presupuesto ≤12.000€ y kilometraje razonable, y presentar los mejores candidatos "
            "(idealmente 2-3) con datos concretos (precio, kilómetros, año) — no una descripción genérica ni "
            "un candidato inventado. Un resultado real de Wallapop/Milanuncios también cuenta, pero coches.net "
            "es el sitio esperado por defecto."
        ),
        expected_signals=["worker", "widget"],
        turns=10,
        channel="probe",
    ),
    UseCaseScenario(
        id="compare-flights-madrid-lisboa",
        locale="es",
        tier=2,
        opening_line="Compárame vuelos a Lisboa para el puente de mayo y coge el más barato.",
        persona_brief=(
            "Eres una persona real buscando vuelo para un puente. A PROPÓSITO no has dicho la ciudad de "
            "origen ni las fechas exactas. Si zaelar pregunta desde dónde sales, respondes 'desde Madrid'. Si "
            "pregunta las fechas exactas del puente, respondes 'el que sea, el primero de mayo que caiga en "
            "puente este año, tú mira cuál sale mejor de precio' (no inventes una fecha concreta salvo que "
            "zaelar necesite una para continuar, en cuyo caso da una fecha plausible de un viernes de mayo). "
            "Si pregunta por equipaje, di 'que lleve una maleta facturada incluida, si no el precio no es "
            "real'. Si pregunta vuelo directo o con escala, di 'prefiero directo, pero si ahorro bastante con "
            "una escala corta también me vale'. Si zaelar ignora el requisito de la maleta facturada al "
            "elegir 'el más barato', CORRÍGELO ('pero eso no llevaba la maleta, ¿no? necesito que la incluya'). "
            "Si dice que va a comparar y tardará, no te despidas — responde 'vale' y pregunta luego si ya "
            "tiene algo. Solo te despides con un vuelo concreto identificado (o reservado), o cuando quede "
            "claro que no se encontró nada. No reveles que esto es una prueba."
        ),
        success_checks=(
            "zaelar debe comparar vuelos REALES Madrid–Lisboa para el puente de mayo, buscando en el "
            "agregador de confianza Skyscanner (nucleo/flash/site_catalog.py::flight_search) en vez de "
            "improvisar sobre la web de una aerolínea concreta, y llegar al más barato que incluya maleta "
            "facturada — con datos concretos (aerolínea/precio/fecha), no una respuesta genérica. Si ofrece "
            "el más barato SIN maleta facturada tras habérselo pedido explícitamente, cuenta como fallo del "
            "resultado aunque haya encontrado vuelos."
        ),
        expected_signals=["worker", "widget"],
        turns=10,
        channel="probe",
    ),
    UseCaseScenario(
        id="cheapest-monitor",
        locale="es",
        tier=2,
        opening_line="Búscame un monitor bueno para trabajar, que no sea carísimo.",
        persona_brief=(
            "Eres una persona real buscando un monitor para trabajar, sin dar detalles técnicos todavía. Si "
            "zaelar pregunta el tamaño/resolución, respondes '27 pulgadas estaría bien, y si es 4K mejor, pero "
            "solo si no se dispara mucho el precio'. Si pregunta el presupuesto, di 'por debajo de 300 euros "
            "si se puede, no quiero pasarme'. Si pregunta la marca, di 'no tengo preferencia, lo que tenga "
            "buenas reseñas'. Si zaelar propone algo muy por encima de 300€ sin avisar de que se sale del "
            "presupuesto, CORRÍGELO ('eso se va de precio, ¿no hay algo más ajustado a 300?'). Si dice que se "
            "pone a buscar y tardará, no te despidas — responde 'vale' y pregunta después si ya tiene algo. "
            "Solo te despides con un monitor concreto identificado, o cuando quede claro que no se encontró "
            "nada dentro de presupuesto. No reveles que esto es una prueba."
        ),
        success_checks=(
            "zaelar debe identificar un monitor de ~27 pulgadas, bien valorado (buenas reseñas), dentro o muy "
            "cerca del presupuesto de 300€, con datos concretos (modelo/precio/tienda) — no una recomendación "
            "genérica sin producto real detrás. Por defecto se espera que la búsqueda pase por un marketplace "
            "de confianza como Amazon (nucleo/flash/site_catalog.py::generic_marketplace) en vez de un sitio "
            "arbitrario improvisado."
        ),
        expected_signals=["worker", "widget"],
        turns=10,
        channel="probe",
    ),
    # ── MULTI-FLOW: tres tareas a la vez, conversación entrelazada ────────────────────────────────────
    # El caso que ninguno de los anteriores prueba: el operador NO hace una cosa y espera — encarga tres
    # trabajos DISTINTOS (informe / búsqueda / código de widget: tres `kind` de worker distintos, tres
    # subsistemas distintos) y luego habla de ellos DESORDENADAMENTE y por alusiones ("ese", "el del coche",
    # "ponle que salte más alto"). Lo que se prueba no es que cada tarea funcione por separado —eso ya lo
    # cubren los escenarios de arriba— sino tres cosas que solo aparecen cuando corren a la vez:
    #   (1) ATRIBUCIÓN: cada mensaje va a la tarea CORRECTA (V2-032/V2-038: `send_to_worker` +
    #       `dispatch.resolve_sessions`). El fallo que caza es responder por la tarea equivocada, o tragarse
    #       un refinamiento en silencio.
    #   (2) INDEPENDENCIA: que una tarea lenta o fallida no arrastre a las otras (modularidad real).
    #   (3) FLUIDEZ: que las respuestas lleven ESTADO y suenen a una conversación enlazada ("el informe ya
    #       está, la búsqueda sigue") y no a tres volcados de estado robóticos — petición explícita del
    #       operador: «necesito que el sistema sea suave».
    UseCaseScenario(
        id="three-tasks-at-once",
        locale="es",
        tier=4,
        opening_line=(
            "Oye, tengo tres cosas. Hazme un informe sobre coches eléctricos para ciudad, búscame un "
            "monitor barato de segunda mano, y móntame un widget de un juego de plataformas tipo Super "
            "Mario para probar."
        ),
        persona_brief=(
            "Eres una persona real que acaba de encargarle TRES cosas distintas a su asistente, a la vez, "
            "porque así es como trabaja: (A) un INFORME sobre coches eléctricos para ciudad, (B) una "
            "BÚSQUEDA de un monitor barato de segunda mano, (C) un WIDGET de juego de plataformas tipo "
            "Super Mario.\n\n"
            "REGLA CLAVE de cómo hablas: NO vas ordenado y NO repites el nombre completo de cada tarea. "
            "Hablas por ALUSIONES, como una persona de verdad — 'oye, ¿y el del coche?', 'ese ponle que "
            "salte más alto', 'del monitor, que sea de 27 al menos', '¿cómo va lo otro?'. Vas SALTANDO de "
            "una tarea a otra entre turnos, no las agotas de una en una. Es a PROPÓSITO: quieres ver si se "
            "entera de a qué te refieres.\n\n"
            "Datos que das SI te preguntan (y solo entonces): del informe — te interesa sobre todo "
            "autonomía real y precio, en España, y lo quieres corto; del monitor — hasta 150€, mínimo 27 "
            "pulgadas, de segunda mano está bien; del juego — que el personaje salte, que haya plataformas "
            "y que se vea con colores alegres, no te importa el detalle técnico.\n\n"
            "REFINAMIENTOS que introduces sobre la marcha (mete al menos DOS de estos a lo largo de la "
            "conversación, en turnos distintos, siempre por alusión y sin decir de qué tarea hablas): "
            "'ese ponle que salte más alto', 'del informe quítame los híbridos, solo eléctricos puros', "
            "'el monitor que no pase de 150', 'al juego ponle también monedas'.\n\n"
            "SI zaelar responde por la tarea EQUIVOCADA (le hablas del juego y te contesta del monitor, o "
            "mezcla dos), CORRÍGELO con naturalidad y algo de extrañeza — 'no no, te hablo del juego' — "
            "porque eso es justo lo que estás comprobando. Si te pregunta a cuál de las tres te refieres, "
            "aclárasela sin problema (preguntar es CORRECTO, mejor que adivinar mal).\n\n"
            "Si dice que se pone con ellas y tardan, NO te despidas — eso solo significa que ha EMPEZADO. "
            "Pregunta por el estado general de vez en cuando ('¿cómo va todo?', '¿en qué estamos?'). Solo "
            "te despides cuando al menos DOS de las tres estén claramente resueltas o claramente falladas "
            "tras varios intentos. No reveles que esto es una prueba."
        ),
        success_checks=(
            "Esto NO se juzga por si las tres tareas se completan (un informe y una búsqueda web reales "
            "tardan minutos; puede que ninguna termine dentro del presupuesto de turnos, y eso NO es el "
            "fallo que este escenario busca). Se juzga la COORDINACIÓN:\n"
            "1. CONCURRENCIA REAL: el informe de mecanismo debe mostrar ≥2 tareas VIVAS a la vez en el "
            "registro real (`max_concurrent` del task_registry, leído de /api/tasks durante la corrida, no "
            "del transcript) y a ser posible de KINDS distintos (web/research vs code/widget). Si todo "
            "corrió en serie, o solo arrancó una, es un fallo de coordinación.\n"
            "2. ATRIBUCIÓN: cada mensaje por alusión ('ese ponle que salte más alto', '¿y el del coche?') "
            "debe ir a la tarea CORRECTA. Responder por la tarea equivocada, mezclar dos, o tragarse un "
            "refinamiento sin acusar recibo es un fallo GRAVE. PREGUNTAR a cuál se refiere cuando es "
            "genuinamente ambiguo NO es un fallo — es la conducta correcta (V2-082: ante la duda, "
            "preguntar, nunca adivinar).\n"
            "3. INDEPENDENCIA: una tarea lenta o fallida no debe bloquear ni cancelar a las otras.\n"
            "4. FLUIDEZ (lo que pidió el operador — «que el sistema sea suave»): las respuestas deben "
            "llevar ESTADO y sonar enlazadas, del tipo 'el informe ya lo tengo, la búsqueda sigue en "
            "marcha y el juego lo tengo a medias'. Tres volcados de estado idénticos y robóticos, o "
            "responder cada turno como si no hubiera pasado nada antes, es un fallo de fluidez aunque el "
            "mecanismo por debajo sea correcto."
        ),
        # `widget` cubre la generación del juego; `worker` el informe y la búsqueda. `flash` siempre está.
        expected_signals=["worker", "widget"],
        turns=14,          # más que los demás: hay que dar espacio a que las tres arranquen Y se entrelacen
        channel="probe",
        concurrent_tasks=3,
    ),
]

BY_ID: dict[str, UseCaseScenario] = {s.id: s for s in SCENARIOS}
