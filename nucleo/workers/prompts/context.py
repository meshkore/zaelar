"""What a worker is told about its moment: the conversation, today, the method, the network first, the known route.

Moved from `nucleo/dispatch_prompts.py` (refactor2710-08 T-04): the worker briefs live with the workers, and the voice
turn's prompt never imports them.
"""
from __future__ import annotations

from nucleo.workers.source_outcomes import worker_line as _sources_line   # V2-798: what each source did lately

def _recent_conversation_block(limit: int = 8) -> str:
    """CONVERSACIÓN RECIENTE verbatim para el prompt del worker (sesión 22:40 2026-07-16): una escalada llegaba
    con la frase CRUDA («¿Por qué crees que puede ser?») y CERO contexto conversacional → el worker investigó la
    voz TTS cuando el operador llevaba tres turnos quejándose de que la MÚSICA no sonaba. El modelo rápido ya
    tenía la instrucción de reformular «con el contexto necesario», pero es no-razonador y no es fiable en eso →
    el contexto de los últimos turnos se adjunta DETERMINISTA aquí (lectura µs de `memory.recent_window`, el
    buffer conversacional persistente), no se delega. Best-effort, nunca lanza."""
    try:
        from memory import api as memory
        win = memory.recent_window(limit=limit) or []
        lines = []
        for m in win:
            who = "OPERADOR" if (m.get("role") == "user") else "zaelar"
            txt = (m.get("content") or "").strip().replace("\n", " ")[:220]
            if txt:
                lines.append(f"{who}: {txt}")
        return "\n".join(lines[-limit:])
    except Exception:
        return ""


def _today_block() -> str:
    """La fecha/hora REAL de hoy, para anclar toda restricción temporal (V2-057): «el último», «el de hoy»,
    «el tiempo actual» solo tienen sentido contra la fecha real — sin esto el worker no puede certificar que un
    resultado sea el vigente. El FlashBrain ya la lleva (live_state); el worker NO la recibía."""
    # V2-250 — UN SOLO RELOJ, el mismo que el resto del razonamiento con fechas. Todo lo que resuelve un momento
    # en este motor pasa por `scheduler.time.time()` (`parse_when`, `next_cron`, y por eso `router_guards` lo lee
    # explícitamente: «ONE clock»). Este bloque —que es justo el que le DICE al worker qué día es— leía el reloj
    # de PARED, así que con el reloj fijado se quedaba en la fecha real mientras las fechas que él mismo manda
    # anclar venían de la otra. Invisible en producción, donde los dos coinciden, y letal al medir: memoria-dev
    # midió la forma gemela en el dosier (`75f2a34`) — replay a 2026-03-10, cita a 6 días por delante, agenda
    # VACÍA porque `date.today()` decía 2026-08-21 y toda fecha futura se leía como pasada.
    import time as _t
    try:
        from nucleo.pulse import scheduler as _sched
        _ahora = _t.localtime(_sched.time.time())
    except Exception:  # noqa: BLE001
        _ahora = _t.localtime()
    return (f"FECHA/HORA REAL DE HOY: {_t.strftime('%A %d %b %Y', _ahora)} ({_t.strftime('%Y-%m-%d', _ahora)}), "
            f"{_t.strftime('%H:%M', _ahora)} hora local. Ancla a esto cualquier restricción temporal de la petición "
            f"(«el último» = el más reciente respecto a HOY; «de hoy»/«ahora» = esta fecha y de aquí en adelante; "
            f"«el de tal día» = esa fecha exacta). NUNCA des un dato caducado como si fuera vigente.")


# V2-057/061 — the MANDATORY method: understand → plan → act → REFLECT on the cards → VERIFY → ITERATE, every plane
# (world ↔ cards ↔ memory) left coherent. V2-705: a card with a connector IS the source; «espejo» names what is done outside.
_METHOD_BLOCK = (
    "MÉTODO (síguelo SIEMPRE, en este orden; no ejecutes a ciegas):\n"
    "1) ENTIENDE exactamente qué se pide, incluidas las restricciones IMPLÍCITAS: «el último/más reciente» = el "
    "más nuevo por fecha (no el primero por relevancia); «hoy/ahora/actual» = anclado a la fecha real de hoy y de "
    "aquí en adelante; «el de tal día» = esa fecha exacta; una cifra/precio/resultado = el VIGENTE. Distingue el "
    "PLANO: un widget con conector ES la fuente (la agenda ES el calendario de Google, mensajería ES el buzón, "
    "contactos ES el directorio): una cita se crea/cancela y un mensaje se manda CON el widget "
    "(python -m nucleo.cli.widget), nunca conduciendo su web. Solo lo hecho en un SITIO sin conector (una reserva "
    "en una web, una suscripción, un pedido, un pago) se hace o deshace ALLÍ; después se refleja en el widget.\n"
    "2) PLANIFICA los pasos y LOCALIZA en memoria lo que necesites (dónde se reservó/contrató, la cita concreta, la "
    "cuenta) con python -m nucleo.cli.mem recall \"<qué buscas>\".\n"
    "3) EJECUTA la acción en la realidad con tus herramientas (navegador, etc.).\n"
    "4) REFLEJA en los widgets lo hecho FUERA, encadenado: si una gestión en un sitio externo afecta a un widget "
    "(la reserva cancelada allí sale de la agenda, una lista se actualiza), hazlo con python -m nucleo.cli.widget "
    "(LEE el widget primero con `read` y usa los ids REALES que te devuelve, nunca inventes ids); si afecta a un "
    "hecho que zaelar recuerda, actualízalo con python -m nucleo.cli.mem remember. Un widget desactualizado (la "
    "cita sigue en la agenda tras cancelarla fuera) es un fallo, no un detalle.\n"
    "4a) EN SU PANTALLA SOLO SE ABRE EL ENTREGABLE de este encargo (la hoja de resultados si pidió una lista, el "
    "documento si pidió un escrito, nada si la respuesta se dice): tus pasos intermedios —leer, extraer, buscar o "
    "listar para ti— no abren nada; el sistema los cuenta en el panel de procesos.\n"
    "4b) ENSÉÑALO EN PANTALLA siempre que la tarea produzca algo que se MIRA. Da igual el volumen: una LISTA de "
    "cualquier cosa (sitios, alojamientos, productos, anuncios, artículos, proyectos, ficheros, opciones, "
    "candidatos…) o UNA SOLA cosa (la ficha técnica de un producto, un informe, un resumen) — las dos van "
    "al MISMO sitio. Para una sola, entrégala como un único item con sus `facts`, su `image`/`images` y sus "
    "`blocks`, y ábrela con `data results detail`: eso es la hoja en blanco con título, foto, precio, "
    "características y enlaces. El operador mira una pantalla: algo que solo se DICE por voz es una entrega a "
    "medias y se pierde en cuanto acaba la frase. **NUNCA escribas un widget nuevo para PRESENTAR datos** — esta "
    "hoja ya existe y sirve para cualquier tema; programar un componente solo se justifica si el operador pidió "
    "FUNCIONALIDAD que no existe y que él maneja (un juego, un contador, una mini-app). Hazlo con la superficie "
    "genérica de presentación: "
    "`python -m nucleo.cli.widget read results` (te devuelve su contrato y la forma EXACTA del payload) → "
    "entrégalo en DOS pasos, que es la ÚNICA forma probada que pasa los guardas:\n"
    "     (i)  escribe el JSON con tu tool Write a un fichero de RUTA RELATIVA en tu directorio de trabajo — "
    "`informe.json` a secas. NUNCA `/tmp/…` ni una ruta absoluta ni `TMP/`: fuera de tu directorio la escritura "
    "pide una aprobación que nadie te va a dar.\n"
    "     (ii) `python -m nucleo.cli.widget data results present @informe.json`\n"
    "   …y después `python -m nucleo.cli.widget show results`. **Nunca pegues el JSON en la línea de comandos ni "
    "uses un heredoc**: las comillas y las llaves los bloquea el guarda del shell. Y no te inventes un script "
    "propio para llamar a la API: el puente ya está permitido, úsalo tal cual. "
    "Ponlo en cuanto tengas resultados sólidos, y ve añadiendo con `data results append` según encuentres más: es "
    "mejor que el operador vea llenarse el informe que esperar callado al final. Cada item con su enlace REAL y, si "
    "el operador pidió verlo con fotos, su `image`. La voz final entonces es CORTA (2-3 frases: qué has encontrado "
    "y que está en pantalla) — el detalle ya lo está leyendo.\n"
    "4c) SI LO QUE PIDIÓ SON LAS FOTOS, van al VISOR `imagenes`, no a la hoja (V2-457). La frontera es de QUÉ es la respuesta, no de si hay imágenes por medio: «enséñame fotos de X» se responde con las fotos, así que su sitio es el visor —una grande, miniaturas, y la FUENTE de cada una a la vista—; «búscame un hotel» se responde con hoteles, y ahí la foto es una columna de la ficha y se queda en la hoja. Mismos dos pasos y mismo puente: escribe el JSON a `fotos.json` y `python -m nucleo.cli.widget data imagenes show @fotos.json` (cada foto `{url, thumb, title, site, page, w, h}`), luego `show imagenes`. NUNCA vuelques un álbum en la hoja: es una tabla y se lee como una lista de enlaces, que es justo lo que el operador dijo que no quería ver.\n"
    "4d) SI LO QUE PIDIÓ ES UNA SOLA COSA PARA LEER —una receta, un informe o resumen que escribes tú, unas instrucciones, un texto largo, un PDF— su sitio es la HOJA EN BLANCO `documento`, no la de resultados (V2-549). La frontera es la misma de siempre, de QUÉ es la respuesta: varias opciones que se comparan van a `results`; UNA cosa que se lee entera va a `documento`. Si te pidió UNA (una receta, no recetas), elige tú la mejor con tu criterio y ponla completa — devolverle la lista de candidatos es hacerle a él el trabajo que te encargó. Mismos dos pasos y mismo puente: escribe el JSON a `doc.json` y `python -m nucleo.cli.widget data documento show @doc.json` ({\"kind\":\"markdown\",\"title\":\"…\",\"source\":\"de dónde sale\",\"body\":\"# Título\\n\\ntexto markdown…\"}), luego `show documento`. Si es largo, primer `show` con la estructura y `data documento append @parte.json` por cada sección: mejor que lo vea crecer a que espere callado. El contrato entero lo tienes con `python -m nucleo.cli.widget read documento`.\n"
    "5) VERIFICA con una comprobación REAL (no la asumas) que TODOS los planos quedaron coherentes: ¿la acción real "
    "se completó? ¿el resultado cumple la restricción (¿es de verdad el más reciente —mira su fecha—, de HOY, "
    "exactamente lo pedido)? ¿los widgets y la memoria reflejan ya lo hecho? Si algo no se puede certificar, "
    "dilo con honestidad — no des por bueno un resultado sin confirmarlo.\n"
    "6) ITERA si la verificación falla (afina la búsqueda, ordena por fecha, prueba otra fuente, corrige el widget) "
    "hasta cumplirlo. Solo entrega cuando está CERTIFICADO en todos los planos. Nunca digas «hecho» sin verificar.\n"
    "1b) EL OBJETIVO MEDIBLE nace con el encargo (te llega como primer mensaje inyectado, «OBJETIVO MEDIBLE: …»): "
    "el motor lo comprueba solo contra la verdad del producto cuando termines, y si no se cumple te relanza "
    "diciéndote qué falta en vez de entregar algo a medias. Si al entender el encargo ves que la condición es "
    "OTRA o más precisa, afínala con 'python -m nucleo.cli.report goal @objetivo.json'; nunca la retires. "
    "Forma: {\"all\":[{\"widget\":\"agenda\",\"collection\":\"meetings\",\"where\":{\"title~\":\"X\"},"
    "\"expect\":\"present|absent\"}]} o {\"widget\":W,\"field\":\"campo\",\"is\"|\"has\":\"x\"} o "
    "{\"desktop\":\"wallpaper\",\"expect\":\"changed\"} — «where» es la misma expresión que `hbwidget rows`, "
    "y las colecciones y sus campos te los da `hbwidget read <widget>`. Si el objetivo nombra una TARJETA, lo entregas EN esa tarjeta con sus acciones declaradas (`hbwidget read <widget>` te da su contrato) y, si son varios elementos, a tandas a medida que los tienes, para que él lo vea crecer.")


# V2-167 · the browser is the LAST resort: a booking site fights a driven Chromium (Booking's anti-bot wall, Google's
# CAPTCHA), while MeshKore agents serve the same domains over HTTP, free, in a second — asked of the Oracle at the
# moment, never a catalog. V2-486: this lived only in `_web_prompt`, so the network was asked in 0 of 399 worker
# reports — a SEARCHED hotel routes to the generic worker. Fixed in the prompt, not the router: step 0 tells the
# generic worker to ask first without changing who serves the errand (the V2-118 / V2-211 asymmetry again).
def _mesh_first_block(py: str = "python", *, browser: bool, goal: str = "") -> str:
    """El PASO 0 —preguntar a la red antes de buscar— en UN solo sitio, para los dos prompts de worker.

    `browser=True` es el worker WEB, cuyo siguiente recurso es abrir el Chromium; `browser=False` el genérico,
    que buscará por su cuenta. Solo cambia el ENCABEZADO y la salida del último punto: lo que se le manda hacer
    es idéntico, y tenerlo dos veces es exactamente como estas dos mitades se separan sin avisar.
    """
    cabeza = ("PASO 0 — ANTES DE ABRIR EL NAVEGADOR, pregunta a la red si ya hay un agente que haga esto:\n"
              if browser else
              "PASO 0 — ANTES DE PONERTE A BUSCARLO TÚ, pregunta a la red si ya hay un agente que haga esto:\n")
    cola = ("Si dice que no hay agente, o el resultado no vale, sigue con el método de abajo — es lo normal: "
            if browser else
            "Si dice que no hay agente, o el resultado no vale, sigue con tu método normal — es lo normal: ")
    return (
        cabeza
        + f"   {py} -m nucleo.cli.mesh find \"<el encargo, tal cual lo dijo el operador>\"\n"
        + f"   {py} -m nucleo.cli.mesh serve \"<el encargo>\" --prompt \"<el encargo con FECHAS ABSOLUTAS>\"\n"
        "   · EN EL IDIOMA DEL OPERADOR y con sus palabras: la red hace su propio análisis y en español encuentra "
        "igual («entradas de teatro en Madrid» devuelve un agente gratis con diez eventos reales).\n"
        "   · FECHAS ABSOLUTAS (2026-09-10), nunca «esta noche»: el agente resolvió esa expresión al año pasado "
        "y devolvió cero resultados; con la fecha explícita devolvió diez.\n"
        "   · COMPRUEBA lo que vuelve: el emparejamiento falla en los bordes (una consulta de restaurante puede "
        "contestarla un agente de hoteles). Si el dominio no encaja, es que no hay agente.\n"
        # V2-487 · el segundo intento. Medido: `roomrover` rechaza el texto libre y CONTESTA qué campos quiere;
        # con ellos devuelve diez hoteles reales de Nueva York en 0,4 s. Sin esta línea el worker leía un `ok:
        # false` y se iba al navegador con la respuesta a un campo de distancia.
        "   · Si la respuesta trae `agent_asks`, el agente NO ha dicho que no: te está diciendo qué necesita. "
        "Vuelve a pedírselo añadiendo esos campos, uno por `--field`, p. ej. "
        "`--field city=\"New York\" --field country_code=US --field checkin=2026-09-10`. Manda los campos SOLOS "
        "(sin `--prompt`): con texto libre delante, el agente lo interpreta a él y los ignora.\n"
        "   · Si `ok:true` y los datos SIRVEN, esa es tu respuesta: entrega eso y no sigas buscando. "
        + cola +
        "para lo que la red no cubra, el navegador sigue siendo el camino.\n"
        + _known_route_line(goal) + _sources_line(py)
        + "\n"
    )


# V2-594 · what we ALREADY know about this errand, in ONE line and only when there is one: from the workflow table,
# which learns from every real errand (a hand-written agent list went stale the day the mesh grew). Known to work →
# name it; known empty → say so; nothing known → write NOTHING.
def _known_route_line(goal: str) -> str:
    if not (goal or "").strip():
        return ""
    try:
        from nucleo import workflows as _wf
        plan = _wf.plan(goal)
    except Exception:
        return ""
    if not plan:
        return ""
    if plan.known_empty:
        return ("   · YA COMPROBADO para este tipo de encargo: la red NO tiene agente. No pierdas el viaje, "
                "ve directo a tu método.\n")
    best = plan.best
    if best and best.get("target"):
        return (f"   · YA COMPROBADO: para este tipo de encargo sirvió el agente «{best['target']}» de la red. "
                "Empieza por ahí.\n")
    return ""
