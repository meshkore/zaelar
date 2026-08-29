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
    # ...and the ones that must NOT. A case can fail by doing TOO MUCH: `quick-fact-opening-hours` asks
    # for an opening time and the engine spawns a browser Brain Worker, which is the very defect that case
    # exists to catch. Until now the bar lived only in prose the judge read, so whether it counted depended
    # on the judge; a family that must be ABSENT is as measurable as one that must be present.
    forbidden_signals: list[str] = field(default_factory=list)
    turns: int = 8
    channel: str = "probe"               # probe (text/flash) | voice — probe is the default for this suite
    # MULTI-FLOW scenarios only (0 = single-task, the normal case): how many genuinely DIFFERENT tasks the
    # scenario asks for at once. When >0 the runner samples the live task registry (`GET /api/tasks`) every
    # turn instead of only reading the browser-task state, and the judge gets two extra dimensions
    # (atribucion / fluidez). Concurrency has to be measured WHILE the run happens — a post-hoc event dump
    # can prove N tasks existed but not that they were ever in flight at the SAME time, which is the whole
    # point of the scenario.
    concurrent_tasks: int = 0
    # DISCOVERY/curation scenarios only: cosas que el operador ya le había contado al agente ANTES de esta
    # conversación. Se siembran por el canal probe con `ingest=True` en una SESIÓN DISTINTA y luego se abre la
    # petición real en otra sesión limpia — así recordarlas exige MEMORIA de verdad y no la ventana
    # conversacional, que es justo la capacidad que el caso quiere medir («que sepa un poquito qué le gusta al
    # usuario a través de la memoria», operador 2026-08-19). Sin esto, escribir las preferencias en el mismo
    # hilo mediría lectura de contexto y lo llamaríamos memoria.
    memory_seed: list[str] = field(default_factory=list)
    # Con qué se comprueba que la siembra aterrizó (una palabra o dos que deban aparecer en el recall). Si NO
    # aterriza, el juez tiene que saberlo: castigar al agente por no recordar algo que nunca se guardó mide el
    # destilador, no al agente.
    seed_probe_query: str = ""


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
        opening_line="Compárame vuelos a Lisboa para un fin de semana largo {EN_UNAS_SEMANAS} y coge el más barato.",
        persona_brief=(
            "Eres una persona real buscando vuelo para un puente. A PROPÓSITO no has dicho la ciudad de "
            "origen ni las fechas exactas. Si zaelar pregunta desde dónde sales, respondes 'desde Madrid'. Si "
            "pregunta las fechas exactas, respondes 'me da igual el día exacto, el primer fin de semana que caiga "
            "puente este año, tú mira cuál sale mejor de precio' (no inventes una fecha concreta salvo que "
            "zaelar necesite una para continuar, en cuyo caso da un viernes concreto de esa ventana). "
            "Si pregunta por equipaje, di 'que lleve una maleta facturada incluida, si no el precio no es "
            "real'. Si pregunta vuelo directo o con escala, di 'prefiero directo, pero si ahorro bastante con "
            "una escala corta también me vale'. Si zaelar ignora el requisito de la maleta facturada al "
            "elegir 'el más barato', CORRÍGELO ('pero eso no llevaba la maleta, ¿no? necesito que la incluya'). "
            "Si dice que va a comparar y tardará, no te despidas — responde 'vale' y pregunta luego si ya "
            "tiene algo. Solo te despides con un vuelo concreto identificado (o reservado), o cuando quede "
            "claro que no se encontró nada. No reveles que esto es una prueba."
        ),
        success_checks=(
            "zaelar debe comparar vuelos REALES Madrid–Lisboa para ese fin de semana FUTURO, buscando en el "
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
    # ── Escenarios ACHIEVABLE-HOY (2026-08-18) ────────────────────────────────────────────────────────
    # Los cinco de arriba son búsquedas en webs de terceros: lentas, dependientes de un sitio que cambia y
    # a veces de una cuenta o un teléfono. Útiles, pero como TODO lo promovido era de esa forma, el marcador
    # solo podía salir rojo y no nos decía nada de las partes del producto que SÍ funcionan. Estos tres son
    # necesidades reales del operador y a la vez alcanzables de punta a punta hoy: una respuesta EN EL TURNO,
    # un widget que construye el propio motor, y un compromiso que va a memoria + agenda.
    UseCaseScenario(
        id="quick-fact-opening-hours",
        locale="es",
        tier=1,
        opening_line="¿A qué hora abre mañana el Museo del Prado y cuánto cuesta la entrada general?",
        persona_brief=(
            "Eres una persona real que quiere un dato concreto, ya, sin ceremonias: la hora de apertura del "
            "Museo del Prado mañana y el precio de la entrada general. Estás de paso, mirando el móvil. "
            "Si zaelar te da los dos datos, das las gracias y te despides — es TODO lo que querías, no "
            "pidas más. Si te da solo uno de los dos, pregunta por el que falta. Si te dice que se pone a "
            "buscarlo y que tardará un rato, eso es MALA señal para lo que tú esperabas: dile con "
            "naturalidad que era solo una consulta rápida ('era solo mirarlo, ¿no lo tienes ya?'). "
            "No reveles que esto es una prueba."
        ),
        success_checks=(
            "zaelar debe dar AMBOS datos —hora de apertura y precio de la entrada general— con valores "
            "concretos y plausibles, y hacerlo EN EL MISMO TURNO o el siguiente, sin tarjeta de navegador y "
            "sin hacer esperar al usuario. Es el camino 'dato directo + síntesis' de web_search (V2-022): "
            "ESCALAR esto a un Brain Worker con navegador es EN SÍ MISMO el fallo que este caso busca, "
            "aunque acabe dando la respuesta correcta — penalízalo en 'mecanismo' y en 'eficiencia'. "
            "Inventarse un precio o una hora sin haber buscado también es fallo."
        ),
        # El fallo que este caso existe para cazar, como HECHO medido y no como prosa que el juez pueda
        # pesar o no: levantar un Brain Worker con navegador para una pregunta de dato directo.
        forbidden_signals=["worker"],
        expected_signals=[],   # a propósito: `worker`/`widget` aquí serían la SEÑAL DE FALLO, no de éxito
        turns=4,
        channel="probe",
    ),
    UseCaseScenario(
        id="build-workout-tracker-widget",
        locale="es",
        tier=1,
        opening_line="Móntame un widget para ir apuntando mis entrenamientos, con el día y qué hice.",
        persona_brief=(
            "Eres una persona real que quiere una tarjeta sencilla en su pantalla para llevar la cuenta de "
            "sus entrenamientos. Si zaelar pregunta qué campos quieres, responde 'el día, qué ejercicio y "
            "cuánto tiempo, con eso me vale'. Si pregunta por el nombre, di 'llámalo entrenamientos'. No "
            "pides nada sofisticado: ni gráficas, ni objetivos, ni sincronización con nada. Si zaelar dice "
            "que se pone a construirlo y tarda un par de minutos, eso es NORMAL para un widget — responde "
            "'vale, avísame' y en turnos siguientes pregunta si ya está. Solo te despides cuando te diga "
            "que el widget está hecho y en pantalla, o cuando quede claro que falló. No reveles que esto "
            "es una prueba."
        ),
        success_checks=(
            "Debe generarse un widget REAL: el informe de mecanismo tiene que mostrar la familia `widget` y "
            "una tarea de generación en el registro, y el widget debe quedar en el catálogo con acciones "
            "usables para apuntar un entrenamiento. Que zaelar diga 'ya lo tienes' sin que el mecanismo lo "
            "respalde es FALLO. Preguntar por los campos antes de construir es BUENA conducta, no un "
            "defecto. Tardar 1-2 minutos es normal y no penaliza la eficiencia."
        ),
        expected_signals=["widget"],
        turns=8,
        channel="probe",
    ),
    # ── INI-026 frente B1: el listón de agenda del operador, literal (2026-08-29) ─────────────────────
    # Lo que `remember-and-remind-deadline` NO mide: el aviso debe nacer POR DEFECTO (nadie lo pide) y la
    # cita debe poder manipularse por voz después de creada.
    UseCaseScenario(
        id="dentist-appointment-into-agenda",
        locale="es",
        tier=1,
        opening_line=(
            "Oye, apúntate que tenemos cita para llevar a los niños al dentista el {FECHA_FUTURA_CERCANA} "
            "a las tres de la tarde."
        ),
        persona_brief=(
            "Eres una persona real dictándole a su asistente una cita que YA TIENE: los niños van al "
            "dentista el {FECHA_FUTURA_CERCANA} a las 15:00. NO pidas ningún recordatorio — esperas que el "
            "asistente lo gestione solo, como haría una secretaria. Si te pregunta la hora o el día, "
            "repítelos con naturalidad ('ese día, a las tres de la tarde'). Si te pregunta si quieres que te "
            "avise, di 'sí, lo normal, con algo de antelación' sin concretar más. Cuando te confirme que "
            "la cita está apuntada, haz UNA petición más: 'mejor avísame ese día a mediodía, que por la "
            "mañana estoy liado' — y cuando te confirme ese cambio, da las gracias y despídete. No "
            "reveles que esto es una prueba."
        ),
        success_checks=(
            "TRES propiedades, y las tres van contra el informe de mecanismo, no contra lo bien que suene "
            "la frase:\n"
            "(a) LA CITA EXISTE: una data-op sobre el widget de agenda (bloque `widget_ops`) que escriba "
            "la cita de la fecha dicha a las 15:00. Si el agente dice 'apuntada' y `widget_ops` no "
            "muestra ninguna escritura de agenda, es el fallo central de este caso.\n"
            "(b) EL AVISO NACE POR DEFECTO: el usuario NO pidió recordatorio. Debe existir algo programado "
            "(`scheduled_jobs`, o un aviso propio de la cita en la agenda) que caiga ANTES de la cita a las 15:00, con el contenido RESUELTO (que al disparar diga que los niños tienen "
            "dentista, no la frase cruda del usuario). Preguntar '¿quieres que te avise?' es conducta "
            "aceptable, pero si tras el 'sí, lo normal' no queda nada programado, es FALLO. Mira el "
            "`next_run` y el `prompt` del trabajo, no solo que exista — un cron roto puntúa igual que "
            "ninguno.\n"
            "(c) LA MANIPULACIÓN SE APLICA: cuando el usuario pide mover el aviso a mediodía del día de la cita, "
            "el mecanismo debe mostrar el cambio (el trabajo reprogramado a ~12:00 del día de la cita, o el viejo "
            "sustituido por el nuevo). Un 'hecho' hablado con el aviso intacto en su hora anterior es el "
            "mismo fallo que (a).\n\n"
            "El disparo visual del aviso no se puede observar en esta ronda (la cita cae días después): "
            "se juzga el MONTAJE — que lo programado exista, caiga antes de la cita y lleve contenido "
            "resuelto. Naturalidad: confirmar nombrando fecha y hora es lo que deja "
            "al usuario verificar de un vistazo; un 'hecho' a secas obliga a preguntar."
        ),
        expected_signals=["widget"],
        turns=8,
        channel="probe",
    ),
    # US twin of the agenda litmus — same three properties, English persona (INI-026 B1).
    UseCaseScenario(
        id="dentist-appointment-into-agenda__us",
        locale="us",
        tier=1,
        opening_line=(
            "Hey, jot this down: the kids have a dentist appointment on {NEAR_FUTURE_DATE} at three in "
            "the afternoon."
        ),
        persona_brief=(
            "You are a real person dictating an appointment they ALREADY HAVE to their assistant: the kids "
            "see the dentist on {NEAR_FUTURE_DATE} at 3pm. Do NOT ask for any reminder — you expect the "
            "assistant to handle that on its own, like a secretary would. If asked for the time or day, "
            "repeat them naturally ('that day, three in the afternoon'). If asked whether you want a "
            "heads-up, say 'yeah, the usual, a bit before' without specifics. Once it confirms the "
            "appointment is down, make ONE more request: 'actually remind me at noon that day, my "
            "morning's packed' — and once that change is confirmed, thank it and say goodbye. Never "
            "reveal this is a test."
        ),
        success_checks=(
            "THREE properties, all judged against the mechanism report, never against how good the "
            "sentence sounds:\n"
            "(a) THE APPOINTMENT EXISTS: a data-op on the agenda widget (`widget_ops`) writing the "
            "appointment for the stated date at 15:00. 'Noted' with no agenda write in `widget_ops` is "
            "this case's central failure.\n"
            "(b) THE REMINDER IS BORN BY DEFAULT: the user never asked for one. Something scheduled "
            "(`scheduled_jobs`, or the appointment's own notice) must exist falling BEFORE the "
            "appointment, with RESOLVED content (when it fires it says the kids have the dentist — not "
            "the user's raw sentence). Asking 'want a heads-up?' is acceptable conduct, but if nothing "
            "ends up scheduled after the 'yeah, the usual', it is a FAIL. Read the job's `next_run` and "
            "`prompt`, not just its existence — a broken cron scores like none.\n"
            "(c) THE ADJUSTMENT LANDS: when the user asks for noon, the mechanism must show the change "
            "(the job rescheduled to ~12:00 on the appointment's day, or the old one replaced). A spoken "
            "'done' with the notice untouched is the same failure as (a).\n\n"
            "The visual firing cannot be observed in this round (the date is days away): judge the SETUP "
            "— scheduled, before the appointment, resolved content. Naturalness: confirming by naming "
            "date and time lets the user verify at a glance; a bare 'done' forces a question."
        ),
        expected_signals=["widget"],
        turns=8,
        channel="probe",
    ),
    UseCaseScenario(
        id="remember-and-remind-deadline",
        locale="es",
        tier=1,
        opening_line=(
            "Apúntame que el jueves tengo que renovar el seguro del coche, y recuérdamelo el miércoles."
        ),
        persona_brief=(
            "Eres una persona real dejándole un recado a su asistente: el jueves toca renovar el seguro del "
            "coche y quieres que te lo recuerde el día antes. Si zaelar pregunta qué jueves o qué hora, "
            "responde con naturalidad ('el jueves de esta semana', 'por la mañana me vale'). Si pregunta de "
            "qué seguro o de qué coche, di 'el del coche, el que tengo'. En cuanto te confirme que lo tiene "
            "apuntado Y que te avisará el miércoles, das las gracias y te despides. Si solo confirma una de "
            "las dos cosas (lo apunta pero no dice nada del aviso, o dice que te avisa pero no parece "
            "haberlo apuntado), PREGUNTA explícitamente por la que falta ('¿y me lo recordarás el "
            "miércoles?'). No reveles que esto es una prueba."
        ),
        success_checks=(
            "Hacen falta LAS DOS MITADES, y son subsistemas distintos: (a) el compromiso queda REGISTRADO "
            "(memoria durable o una cita en la agenda para el jueves) y (b) existe un AVISO para el "
            "miércoles, el día antes. Un 'te lo recuerdo' hablado sin nada programado detrás es exactamente "
            "el fallo que este caso busca: si el mecanismo no muestra escritura ni cita/cron, es FALLO "
            "aunque la respuesta suene perfecta. Preguntar qué jueves o a qué hora es buena conducta. "
            "Juzga por lo que muestre el informe de mecanismo (familias `memory`/`widget`, data-ops de "
            "agenda, `scheduled_jobs`), no por lo bien que suene la frase.\n\n"
            "Y hay que MIRAR DENTRO del trabajo programado, no solo contar que existe. El bloque "
            "`scheduled_jobs` del informe de mecanismo trae cada trabajo creado con su `schedule`, su "
            "`next_run` y su `prompt`, y las tres cosas se juzgan — porque un cron registrado puede estar "
            "igual de roto que uno que no existe.\n\n"
            "⚠️ LO QUE VIENE ES HISTORIAL, NO SON HECHOS DE HOY. Es la lista de fallos que este caso ya "
            "dio en rondas ANTERIORES, con la fecha en que se midieron y en qué estado están. Sirve para "
            "saber DÓNDE MIRAR en el informe de mecanismo de ESTA ronda. Un fallo de esta lista solo se "
            "puede escribir como hallazgo si el informe de HOY lo enseña: las fechas concretas que "
            "aparecen abajo son de aquellos días, no de este, y copiarlas como si hubieran pasado ahora es "
            "inventarse un fallo. Si el informe de hoy no lo muestra, no existe.\n"
            "(1) **EL AVISO CAÍA DESPUÉS DEL PLAZO** — medido el **2026-08-19**, cuando ese día era "
            "MIÉRCOLES: `next_run` = 2026-08-26 para un jueves que entonces era el 2026-08-20. Seis días "
            "tarde. «El miércoles» se resolvió como *el próximo miércoles* sin comprobar la única "
            "restricción que un recordatorio tiene: **caer ANTES de la cosa que recuerda**. Un aviso "
            "posterior al plazo es un fallo de RESULTADO, no un detalle de fecha.\n"
            "    ⚠️ Esas dos fechas (26 y 20) son de AQUELLA ronda. Para juzgar la de hoy, compara el "
            "`next_run` real del informe de HOY con la fecha del evento que el agente dijo en ESTA "
            "conversación, y mira solo el ORDEN entre las dos.\n"
            "    ✅ ARREGLADO el 2026-08-19 (`router_guards.reminder_before`). Y con el arreglo viene una "
            "consecuencia que **NO hay que puntuar como fallo**: si el día que nombró el operador ES HOY (pidió "
            "el miércoles, estando a miércoles, para algo del jueves), el aviso se programa **PRONTO** —unos "
            "minutos— en vez de dentro de una semana. Eso es la lectura correcta de lo que pidió, no un "
            "recordatorio «inmediato y por tanto inútil»: la ronda del 20:44 lo puntuó 2/5 por esto y el juez se "
            "equivocaba. Lo que SÍ sigue siendo fallo es un aviso que caiga DESPUÉS del plazo.\n"
            "(2) ✅ ARREGLADO — **EL `prompt` ERA LA FRASE DEL USUARIO EN CRUDO** («Apúntame que el jueves tengo que "
            "renovar el seguro del coche, y recuérdamelo el miércoles»). Cuando eso dispare, al agente se le "
            "pedirá PROGRAMAR otra vez, no avisar de nada: el QUÉ del recordatorio se ha perdido. El campo "
            "tiene que llevar el contenido RESUELTO («recuérdale que hoy toca renovar el seguro del coche»), "
            "no el encargo.\n"
            "(3) ⬅️ **LO QUE SIGUE ABIERTO — SE PIDIERON DOS COSAS Y SOLO EXISTÍA UNA**: `n_after: 1` — estaba el aviso y no estaba la "
            "entrada de agenda del jueves, mientras el agente decía «Todo listo: la cita está en tu agenda "
            "para el jueves y te aviso el miércoles». La segunda mitad de esa frase era media verdad; la "
            "primera no tenía nada detrás."
        ),
        expected_signals=["memory"],
        turns=6,
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

    # UNA HOJA POR ENCARGO — y «cierra los resultados» con dos abiertas es una PREGUNTA, no una orden.
    #
    # Regla del operador (2026-08-21): dos búsquedas a la vez son dos navegadores y DOS hojas de resultados,
    # cada una con su correlation_id; y una hoja TERMINADA no se reutiliza para el encargo siguiente — se abre
    # una nueva. El motivo no es estético: reutilizar la caja BORRA una búsqueda, y una búsqueda borrada no se
    # recupera. La otra cara de la misma regla es que, con dos cajas abiertas, «cierra los resultados» deja de
    # ser inequívoco — y este repo ya tiene escrito qué se hace ante la duda (V2-082: se PREGUNTA, nunca se
    # adivina). Cerrar la que no era es exactamente el borrado que la regla existe para evitar.
    #
    # ⚠️ HOY EL MOTOR NO HACE ESTO, y el caso se escribe igual A PROPÓSITO. `dispatch._sheet_open()` emite
    # `widget/show` con el id pelado `"results"` y `widgets/results/data.py` guarda en UNA clave, así que dos
    # encargos comparten hoja y se acumulan con dedup — está dicho en la sección «Abierto» de V2-257. Lo que
    # este caso aporta HOY es la MEDIDA (`sheet_instances`: 1 caja para 2 encargos ⇒ `shared: true`), que es
    # lo que convierte una regla de producto en un hecho comprobable. El día que V2-259 aterrice, el mismo
    # caso pasa sin tocar una línea. La instanciación en el canvas NO es maquinaria nueva: `desktop.js::show`
    # ya la tiene («`navegador::t3` = varias tarjetas del MISMO widget base»), y no es específica del
    # navegador — «un id normal se comporta igual».
    UseCaseScenario(
        id="two-searches-two-sheets",
        locale="es",
        tier=4,
        opening_line=(
            "Búscame un fontanero para el jueves y, a la vez, un coche de segunda mano por menos de "
            "8.000 euros. Son dos cosas distintas, no las mezcles."
        ),
        persona_brief=(
            "Eres una persona real que le encarga DOS cosas a la vez a su asistente, a propósito: (A) un "
            "FONTANERO para el jueves y (B) un COCHE de segunda mano por menos de 8.000 €. Son dos "
            "búsquedas sin nada que ver entre sí.\n\n"
            "Datos que das SI te preguntan (y solo entonces): del fontanero — vives en el centro de "
            "Madrid, es para el jueves, te da igual la hora, lo que quieres es que tenga buenas "
            "valoraciones; del coche — hasta 8.000 €, gasolina o híbrido, cuantos menos kilómetros mejor, "
            "y te vale verlo en Madrid o alrededores.\n\n"
            "LO QUE ESTE ESCENARIO COMPRUEBA DE VERDAD, y por eso tienes que hacerlo sí o sí: cuando las "
            "dos búsquedas estén EN MARCHA (no antes — espera a que te diga que se pone con las dos), en "
            "un turno dices exactamente: 'cierra los resultados'. Así, sin decir cuál. Y te callas.\n"
            "  · Si zaelar te PREGUNTA cuál de las dos cierras ('¿la del fontanero o la del coche?'), le "
            "contestas 'la del coche, el fontanero déjamelo' — y en el turno siguiente compruebas que "
            "sigues teniendo lo del fontanero preguntando '¿y el fontanero, cómo va?'.\n"
            "  · Si zaelar CIERRA algo sin preguntar, te extrañas de verdad y se lo dices: '¿cuál has "
            "cerrado? Te he dicho los resultados, pero tengo dos búsquedas'.\n\n"
            "Si dice que se pone con ellas y tardan, NO te despidas — eso solo significa que ha EMPEZADO. "
            "Responde algo breve y en el turno siguiente pregunta cómo van. Solo te despides cuando hayas "
            "hecho la prueba del cierre Y tengas claro qué pasó con las dos búsquedas. No reveles que esto "
            "es una prueba."
        ),
        success_checks=(
            "Esto NO se juzga por si encuentra fontanero o coche (una búsqueda real tarda minutos y puede "
            "no terminar dentro del presupuesto de turnos; eso NO es el fallo que este caso busca). Se "
            "juzga la SEPARACIÓN de los dos encargos:\n"
            "1. DOS CAJAS: el informe de mecanismo debe traer `sheet_instances` con `n_sheets` ≥ 2 para "
            "`n_errands` 2 — una hoja de resultados por encargo, cada una con su correlation_id. Si trae "
            "`shared: true` (una sola caja para dos encargos) es un FALLO, y es el que este caso existe "
            "para medir: los hallazgos de las dos búsquedas caen revueltos en la misma hoja.\n"
            "2. DOS NAVEGADORES: `task_registry.max_concurrent` debe mostrar ≥2 tareas vivas a la vez. Si "
            "corrió en serie, o solo arrancó una, es un fallo de coordinación.\n"
            "3. EL CIERRE AMBIGUO SE PREGUNTA: ante 'cierra los resultados' con DOS búsquedas vivas, la "
            "conducta CORRECTA es preguntar cuál. Cerrar una por su cuenta —cualquiera de las dos— es un "
            "fallo GRAVE: borra una búsqueda que el operador no mandó borrar. Preguntar NO es dudar, es la "
            "norma de la casa ante una referencia ambigua.\n"
            "4. LO NO CERRADO SIGUE VIVO: tras cerrar la que el operador eligió, la otra búsqueda debe "
            "seguir en marcha y poder consultarse. Que el cierre se lleve las dos por delante es el mismo "
            "fallo del punto 3 con otra cara.\n"
            "5. ATRIBUCIÓN: cada respuesta debe ir al encargo correcto. Contestar del coche cuando se "
            "pregunta por el fontanero, o mezclar los dos en una misma respuesta como si fueran uno, es un "
            "fallo."
        ),
        expected_signals=["worker", "widget"],
        turns=12,
        channel="probe",
        concurrent_tasks=2,
    ),

    # ── CASOS DE FUTURO: escritos ANTES que el mecanismo, y GATEADOS por sus tareas de roadmap ─────────────
    # Regla del operador (2026-08-21): «todos los comportamientos que espero deben formar parte de un use case
    # lo más completito posible […] los use cases son el punto más alto de la pirámide, de lo que se desprende
    # todo lo demás». Así que la petición se escribe aquí PRIMERO, con su vínculo al roadmap en `segments.py`,
    # y el arnés se niega a conducirla hasta que esas tareas estén hechas — conducirla hoy gastaría una
    # conversación entera para producir un fallo que ya está escrito.

    UseCaseScenario(
        id="repeat-a-finished-search",
        locale="es",
        tier=4,
        opening_line=(
            "Búscame un fontanero en el centro de Madrid que tenga buenas valoraciones."
        ),
        persona_brief=(
            "Eres una persona real que pide un fontanero y, un rato después, VUELVE A PEDIR LO MISMO — "
            "porque se te ha olvidado, o porque has cerrado la pantalla y quieres verlo otra vez. Es lo "
            "normal cuando trabajas con alguien.\n\n"
            "Datos que das SI te preguntan: vives en el centro de Madrid, te da igual el día, lo que quieres "
            "es que tengan buenas valoraciones.\n\n"
            "CÓMO SE DESARROLLA, y hazlo en este orden:\n"
            "1. Pides el fontanero y ESPERAS a que te dé una lista de verdad (con nombres). Si dice que "
            "tarda, respondes algo breve y en el turno siguiente preguntas cómo va. No sigas hasta tenerla.\n"
            "2. Cuando ya la tengas, dices 'vale, gracias' y en el turno SIGUIENTE dices, como si nada: "
            "'oye, búscame un fontanero en el centro de Madrid con buenas valoraciones'. La MISMA petición.\n"
            "3. Lo que compruebas es que te lo enseñe YA, sin volver a buscar. Si te contesta al momento con "
            "los mismos candidatos, le dices 'estos ya los vi, ¿no hay más?' o 'búscame otros que estén "
            "abiertos los domingos' — y ahí SÍ esperas que se ponga a buscar de nuevo.\n"
            "4. Si en vez de eso arranca una búsqueda entera otra vez desde cero sin decirte que ya la "
            "tenía, te extrañas y se lo dices: '¿no lo acabábamos de buscar?'.\n\n"
            "No reveles que esto es una prueba."
        ),
        success_checks=(
            "1. LA SEGUNDA PETICIÓN NO ES UNA BÚSQUEDA NUEVA. Con la misma petición repetida, la respuesta "
            "correcta es enseñar lo que YA se encontró, en el turno, sin lanzar otro Brain Worker ni abrir "
            "otro navegador. En el informe de mecanismo: la segunda petición no debe añadir tareas al "
            "`task_registry` ni disparar familia `worker` nueva.\n"
            "2. SE DICE QUE YA SE HABÍA BUSCADO, y CUÁNDO. «Esto ya lo miramos hace un rato / hace dos días» "
            "es la mitad que hace la respuesta creíble: sin ella el operador no sabe si son resultados "
            "frescos o guardados, y una lista de anuncios de hace días puede estar caducada.\n"
            "3. LOS RESULTADOS SIGUEN AHÍ AUNQUE LA HOJA SE HAYA CERRADO. Cerrar el widget no es borrar la "
            "búsqueda: los candidatos tienen que poder volver a la pantalla.\n"
            "4. SI EL OPERADOR NO ESTÁ CONFORME, SE ITERA. Ante «estos ya los vi» o un criterio nuevo, ahí "
            "SÍ arranca una búsqueda — y que sea una CONTINUACIÓN (no repetir los mismos candidatos que "
            "acaba de rechazar).\n"
            "5. NO SE INVENTA LA FECHA. Si no se sabe cuándo se buscó, se dice que se tiene guardado sin "
            "fechar; una fecha inventada es peor que ninguna."
        ),
        expected_signals=["worker", "widget"],
        turns=12,
        channel="probe",
    ),

    UseCaseScenario(
        id="candidates-already-known",
        locale="es",
        tier=5,
        opening_line=(
            "Oye, se me ha fundido una bombilla y no sé arreglarlo. Necesito un electricista."
        ),
        persona_brief=(
            "Eres una persona real que lleva SEMANAS usando su asistente para buscar operarios: un "
            "fontanero, luego un albañil, luego un electricista, luego un carpintero. Cada búsqueda fue una "
            "conversación distinta, en días distintos. Hoy necesitas un ELECTRICISTA otra vez.\n\n"
            "Datos que das SI te preguntan: vives en el centro de Madrid, es para esta semana, y como "
            "siempre lo que te importa son las valoraciones.\n\n"
            "LO QUE COMPRUEBAS: que te diga que YA tenéis electricistas localizados de la otra vez y te los "
            "enseñe en el acto, en vez de ponerse a buscar desde cero como si fuera la primera vez.\n"
            "  · Si te los enseña, le preguntas '¿y estos de cuándo son?' — quieres ver si sabe que pueden "
            "estar viejos.\n"
            "  · Si te sirven, dices 'perfecto, con estos me apaño' y te despides.\n"
            "  · Si arranca una búsqueda entera sin mencionar que ya teníais unos cuantos, te extrañas: "
            "'pero si ya buscamos electricistas hace unas semanas, ¿no los tienes?'.\n\n"
            "No reveles que esto es una prueba."
        ),
        success_checks=(
            "1. SE RESPONDE DESDE LO QUE YA SE SABE. Habiendo buscado electricistas antes, la respuesta "
            "correcta es sacar esos candidatos a la pantalla EN EL TURNO — sin Brain Worker, sin navegador, "
            "sin proceso largo. Que la familia `worker` NO aparezca aquí es un ACIERTO, no una carencia.\n"
            "2. SE NOMBRA LA PROCEDENCIA Y LA EDAD. «Los encontramos hace tres semanas» es lo que permite al "
            "operador decidir si le valen o quiere frescos. Un anuncio de un operario envejece; una lista "
            "servida como nueva cuando es vieja es peor que no tenerla.\n"
            "3. NO SE CRUZAN LOS OFICIOS. Pedir un electricista no puede sacar los fontaneros. El catálogo "
            "guarda candidatos POR LO QUE SON, y confundir dos oficios es peor que no tener catálogo.\n"
            "4. SI NO HAY NADA GUARDADO DE ESE OFICIO, SE BUSCA — sin fingir que se tenía. Un catálogo vacío "
            "es una respuesta legítima; inventarse que ya se tenían candidatos no lo es.\n"
            "5. SI EL OPERADOR QUIERE MÁS, SE BUSCA. El catálogo es un ATAJO, nunca una valla: «no me valen» "
            "o «busca más» arranca la búsqueda de verdad."
        ),
        expected_signals=["widget"],
        forbidden_signals=["worker"],
        turns=8,
        channel="probe",
    ),

    UseCaseScenario(
        id="change-the-criteria-not-the-search",
        locale="es",
        tier=5,
        opening_line=(
            "Necesito un coche de segunda mano."
        ),
        persona_brief=(
            "Eres una persona real que HACE UN MES le pidió a su asistente coches de segunda mano, y le "
            "enseñó unos cuantos BMW. Hoy vuelves al tema.\n\n"
            "CÓMO SE DESARROLLA, en este orden:\n"
            "1. Pides un coche de segunda mano, así de suelto. Esperas que te saque lo que YA teníais "
            "guardado del mes pasado, sin ponerse a buscar.\n"
            "2. En cuanto te enseñe los BMW, CAMBIAS EL CRITERIO: 'no, no, estos eran BMW y ahora quiero un "
            "Mercedes'. Ahí SÍ esperas que se ponga a buscar de verdad, porque es otro encargo.\n"
            "3. Cuando te traiga los Mercedes, preguntas '¿y estos me los guardas también, no?' — quieres "
            "ver si entiende que los nuevos se suman a lo que ya teníais.\n"
            "4. Si te saca los BMW de hace un mes SIN decirte que son de hace un mes, se lo dices: 'estos "
            "son de hace mucho, ¿siguen a la venta?'.\n\n"
            "Datos que das SI te preguntan: hasta 20.000 €, gasolina o híbrido, cuantos menos kilómetros "
            "mejor, y te vale verlo en Madrid o alrededores. No reveles que esto es una prueba."
        ),
        success_checks=(
            "1. LA PETICIÓN GENÉRICA SE RESUELVE CON LO GUARDADO. «Necesito un coche de segunda mano» sin "
            "más, con candidatos ya en el catálogo, se contesta enseñándolos — no arrancando una búsqueda.\n"
            "2. UN CRITERIO NUEVO SÍ ES UN ENCARGO NUEVO. «Ahora quiero un Mercedes» no se resuelve "
            "filtrando lo guardado ni diciendo que no hay: arranca una búsqueda real, con el criterio "
            "nuevo. Confundir «enséñame lo que tienes» con «búscame otra cosa» en cualquiera de los dos "
            "sentidos es el fallo que este caso mide.\n"
            "3. LO NUEVO SE SUMA, NO SUSTITUYE. Los Mercedes encontrados pasan a ser candidatos guardados "
            "junto a los BMW; el catálogo crece, no se reemplaza en cada búsqueda.\n"
            "4. LA EDAD SE DICE Y SE TIENE EN CUENTA. Un anuncio de coche de hace un mes probablemente ya no "
            "existe —el coche se vendió o el anuncio caducó— y eso hay que decirlo al enseñarlo. Un "
            "candidato viejo servido como vigente es una entrega falsa.\n"
            "5. EL OLVIDO ES CORRECTO. Que un candidato de hace meses haya desaparecido del catálogo NO es "
            "un fallo de memoria: coincide con la realidad. Lo que sí es un fallo es enseñarlo como si "
            "siguiera vivo."
        ),
        expected_signals=["widget"],
        turns=12,
        channel="probe",
    ),
    # ── Música y vídeo (2026-08-26, petición del operador). Segunda instancia del hueco de REPRESENTACIÓN que
    # ya arreglaron los tres casos del 2026-08-18: los 13 escenarios promovidos eran TODOS «entra en una web
    # de terceros, busca, elige», así que dos superficies enteras del producto no se medían. El plató NO tiene
    # `connectors.json`, o sea que Spotify está sin conectar y el widget `musica` nunca se ha usado ahí — lo
    # que se mide es el camino de fallback real (`mode = spotify si conectado, si no youtube`), verificado
    # antes de escribir esto y no supuesto.
    UseCaseScenario(
        id="play-music-and-build-playlist",
        locale="es",
        tier=1,
        opening_line="Ponme algo de música tranquila para trabajar.",
        persona_brief=(
            "Eres una persona real que se pone a trabajar y quiere música de fondo. No tienes en la cabeza "
            "ningún artista concreto: si zaelar pregunta qué quieres, di 'algo instrumental, sin letra, que "
            "no distraiga'. Si te pregunta por un servicio de música o dice que no tienes cuenta conectada, "
            "contesta 'no tengo Spotify conectado, pon lo que puedas' — y eso te vale, NO te enfadas por "
            "ello. Cuando ya esté sonando algo, pídele que te lo guarde en una lista llamada 'Curro' para "
            "poder repetirla otro día, y más adelante pídele que añada también lo que esté sonando en ese "
            "momento. Si dice que ya está sonando pero tú no tienes forma de saberlo, pregúntale QUÉ ha "
            "puesto. Solo te despides cuando haya música puesta y la lista creada, o cuando quede claro que "
            "no puede. No reveles que esto es una prueba."
        ),
        success_checks=(
            "DOS mitades, y hacen falta las dos. (1) SUENA ALGO DE VERDAD: el informe de mecanismo tiene que "
            "enseñar el widget `musica` vivo — su `active_when` satisfecho, que sin cuenta de Spotify "
            "significa el bloque de audio oculto de YouTube (`yt.videoId` con `yt.paused` falso). (2) LA "
            "LISTA EXISTE **CON LA CANCIÓN DENTRO**: en el store del propio widget, no una promesa en el "
            "transcript. Se juzga por el RESULTADO y NO por qué llamada se usó — este criterio exigía "
            "`create_playlist` + `add_to_playlist`, y V2-384 unificó las dos en UNA a propósito (el modelo "
            "solo emite una llamada por petición), así que pedía un mecanismo que ya no existe. Una lista "
            "creada VACÍA no cuenta: lo que se pidió fue guardar LO QUE SUENA. "
            "Son FALLO, por muy bien que suene la conversación: escalar esto a un Brain Worker (es un RAIL, "
            "se resuelve en el turno — V2-042), y afirmar que suena una canción sin nada vivo detrás. "
            "Spotify está SIN CONECTAR a propósito: decirlo con naturalidad y tirar de YouTube es un PASE; "
            "narrar una sesión de Spotify que no existe es justo el fallo que este caso busca. Preguntar qué "
            "tipo de música antes de poner nada es BUENA conducta, no un defecto."
        ),
        expected_signals=["widget"],
        turns=8,
        channel="probe",
    ),
    UseCaseScenario(
        id="watch-a-video-not-listen-to-it",
        locale="es",
        tier=1,
        opening_line="Pon el vídeo del tráiler de la última de Dune.",
        persona_brief=(
            "Eres una persona real que quiere VER un vídeo en pantalla, no escuchar música. Si zaelar "
            "pregunta cuál en concreto, di 'el tráiler oficial, el que salga primero'. Si te pone música en "
            "vez de un vídeo, dilo con naturalidad: 'no, quiero VERLO, el vídeo'. Cuando esté puesto, pídele "
            "que le baje el volumen, y un par de turnos después que lo pare. Solo te despides cuando el "
            "vídeo esté en pantalla y hayas podido controlarlo, o cuando quede claro que no puede. No "
            "reveles que esto es una prueba."
        ),
        success_checks=(
            "Tiene que correr el camino de VÍDEO y no el de música: `play_video` (nunca `play_music`) abre "
            "el widget `youtube` con un `videoId` real cargado, y las peticiones de transporte que vienen "
            "después (bajar volumen, parar) llegan como data-ops sobre ESE widget. "
            "Agarrar `play_music` aquí es exactamente la regresión que V2-045 se construyó para impedir — la "
            "prosa de la frontera dentro de `play_music` no bastó en tres intentos y hizo falta una tool "
            "dedicada — así que se puntúa como fallo de MECANISMO por muy natural que suene la respuesta. "
            "⚠️ La nota de ASIMETRÍA que llevaba aquí CADUCÓ el 2026-08-27 y se conserva dicha para que "
            "nadie la reintroduzca de memoria: decía que el widget de vídeo no tiene acciones de lista y que "
            "encolar varios vídeos «no tiene mecanismo hoy, es un hallazgo». Ya lo tiene (V2-366: "
            "`add`/`play_item`/`next`/`previous`, y se reproducen uno detrás de otro solos). Puntuar hoy una "
            "cola de vídeos como hallazgo sería el instrumento acusando al producto de una capacidad que "
            "SÍ existe. Este caso sigue midiendo UN vídeo y su transporte; la lista tiene su propio caso "
            "(`build-a-video-playlist-from-links`)."
        ),
        expected_signals=["widget"],
        turns=8,
        channel="probe",
    ),

    # ── Multimedia, segunda tanda (2026-08-27, encargo del operador). Su encuadre, y ordena lo que se mide:
    # el de música se juzga contra SPOTIFY y el de vídeo contra YOUTUBE, pero el de vídeo «muy limpio en
    # diseño, no lo quiero sucio con vídeos por todos lados — listas lineales de texto, título, click». Los
    # dos se conducen POR VOZ (aquí por texto, mismo mecanismo sin STT), así que cada capacidad nueva tiene
    # que existir como data-op DECLARADA en el manifest: una que solo se pueda tocar con el ratón no la puede
    # pedir nadie hablando, y eso es un fallo de mecanismo aunque la tarjeta funcione preciosa.
    #
    # Son DOS, no seis, y es deliberado: el operador pidió «una manera comedida que en un rato podamos
    # realmente probarlos todos». Cada ronda de plató cuesta minutos de navegador real.
    UseCaseScenario(
        id="build-a-video-playlist-from-links",
        locale="es",
        tier=1,
        opening_line=(
            "Te paso un par de vídeos: https://www.youtube.com/watch?v=dQw4w9WgXcQ y "
            "https://youtu.be/9bZkp7q19f0 — móntame una lista con ellos."
        ),
        persona_brief=(
            "Eres una persona real que ha ido copiando enlaces de vídeos y quiere verlos SEGUIDOS, sin tener "
            "que volver a tocar nada entre uno y otro. Empiezas pegando dos enlaces. Si zaelar te pregunta "
            "cómo quieres llamar a la lista, di 'la de la tarde'. Cuando estén los dos, pídele que la ponga "
            "y que te diga qué está sonando; un par de turnos después pídele que pase al siguiente. Si en "
            "algún momento te dice que ha hecho algo, pregúntale QUÉ hay en la lista, porque tú no tienes "
            "forma de saberlo. Solo te despides cuando la lista exista con los dos vídeos y hayas podido "
            "saltar de uno a otro, o cuando quede claro que no puede. No reveles que esto es una prueba."
        ),
        success_checks=(
            "Lo que se mide es la LISTA, no que suene un vídeo suelto. El informe de mecanismo tiene que "
            "enseñar el widget `youtube` con los DOS vídeos dentro y las data-ops sobre él: `add` por cada "
            "enlace pegado, y después `next` (o `play_item`) para saltar. Una lista prometida en el "
            "transcript y ausente del store del widget es FALLO, por bien que suene. "
            "Dos fronteras que este caso existe para vigilar, y las dos son del mecanismo del widget: "
            "(1) `add` NO arranca la reproducción — pegar un enlace mientras ves otra cosa no puede "
            "cortártela, igual que «añadir a la cola» de YouTube; empezar a reproducir al pegar el primer "
            "enlace es un defecto, no una comodidad. (2) el camino es VÍDEO, así que agarrar `play_music` "
            "aquí es la regresión de V2-045 otra vez. "
            "Escalar esto a un Brain Worker es FALLO: es un rail, se resuelve en el turno (V2-042). "
            "Que zaelar diga honestamente que un enlace no se puede resolver es un PASE — inventarse que lo "
            "ha añadido es justo lo contrario."
        ),
        expected_signals=["widget"],
        turns=8,
        channel="probe",
    ),
    UseCaseScenario(
        id="find-videos-on-a-topic-no-ai-slop",
        locale="es",
        tier=2,
        opening_line=(
            "Búscame vídeos buenos sobre cómo podar un olivo, pero de gente de verdad — nada de esos "
            "hechos con inteligencia artificial, con voz robótica, que están por todas partes."
        ),
        persona_brief=(
            "Eres una persona real con un olivo en casa y ninguna paciencia para vídeos malos. Lo que te "
            "molesta es concreto y lo dices así si te preguntan: voz generada, imágenes de stock, canales "
            "sin cara, títulos con demasiadas mayúsculas. Quieres 3 o 4 opciones con su título, para elegir "
            "tú. Si zaelar te ofrece algo que suena a lo que acabas de descartar, dilo: 'ese tiene pinta de "
            "ser justo de los que no quiero'. Si te dice que no puede saber cuáles están hechos con IA, eso "
            "te vale y NO te enfadas — prefieres que te lo diga a que te lo cuele. Solo te despides cuando "
            "tengas candidatos concretos con nombre, o cuando quede claro que no puede. No reveles que esto "
            "es una prueba."
        ),
        success_checks=(
            "Dos mitades. (1) HAY CANDIDATOS DE VERDAD: vídeos con título real entregados en el turno, no "
            "«te aviso cuando los tenga». (2) EL FILTRO SE TRATA CON HONESTIDAD, y esta es la mitad que el "
            "caso existe para medir. "
            "«Sin vídeos hechos con IA» es un criterio que hoy NO se puede verificar desde fuera: no hay "
            "señal en la plataforma que lo diga. Las dos conductas correctas son decir con qué señales se "
            "está aproximando (canal conocido, cara a cámara, antigüedad) o decir que no puede garantizarlo "
            "y entregar igual lo que tiene. AFIRMAR que los candidatos están libres de IA sin nada detrás es "
            "el fallo que este caso busca — es la misma familia que presentar como comparables filas sin "
            "precio: un criterio que el operador dio y que se da por cumplido sin haberlo comprobado. "
            "Callarse el criterio entero y entregar la primera lista que salga también es fallo: el operador "
            "lo dijo en su primera frase. "
            "Poner un vídeo a reproducir aquí NO es lo pedido — pidió elegir él."
        ),
        expected_signals=["widget"],
        turns=10,
        channel="probe",
    ),
]

BY_ID: dict[str, UseCaseScenario] = {s.id: s for s in SCENARIOS}


def all_scenarios() -> list[UseCaseScenario]:
    from . import derived as D
    # Los de DESCUBRIMIENTO viven en su propio módulo (`discovery.py`): son una familia distinta —el usuario no
    # sabe lo que quiere, así que la mitad del trabajo es inferirlo de la memoria— y son los únicos que
    # SIEMBRAN preferencias antes de hablar. Mezclarlos aquí haría este fichero ilegible y escondería que su
    # criterio de éxito es otro.
    from . import discovery as DISC
    out = list(SCENARIOS) + list(DISC.SCENARIOS)
    have = {s.id for s in out}
    for case in D.derivable():
        if case.id in have:
            hand = BY_ID[case.id]
            if hand.locale == case.locale: continue
        scn = D.derive(case)
        if scn.id in have: continue
        out.append(scn); have.add(scn.id)
    # The REAL-DATA limit applies to hand-written scenarios too, and it has to be applied HERE rather than
    # inside `derive()`: `restaurant-tonight-madrid` and `book-hotel-night-known` are hand-written, and they
    # are exactly the cases whose completion needs a phone call or a card. Without this they would keep being
    # graded on a booking nobody can make, which the operator ruled out (2026-08-18) — and, worse, the dev
    # agent would keep receiving them as bugs.
    # Fechas SIEMPRE futuras y relativas a HOY (norma del operador, 2026-08-19; ver `dates.py` para el
    # incidente que la motivó: el catálogo pedía reservas para «el puente de mayo» con el reloj en agosto).
    # Se resuelve AQUÍ, en el único punto por el que pasan todos los escenarios —a mano y derivados—: hacerlo
    # en cada constructor garantiza que el siguiente constructor nuevo se olvide.
    from . import dates as DT
    return [_with_dates(D.apply_human_opening(D.apply_findings_contract(D.apply_data_note(s))), DT) for s in out]


def _with_dates(scn: UseCaseScenario, DT) -> UseCaseScenario:
    from dataclasses import replace
    return replace(scn,
                   opening_line=DT.resolve(scn.opening_line),
                   persona_brief=DT.resolve(scn.persona_brief),
                   success_checks=DT.resolve(scn.success_checks),
                   memory_seed=[DT.resolve(x) for x in (scn.memory_seed or [])])


def registry() -> dict[str, UseCaseScenario]:
    return {s.id: s for s in all_scenarios()}
