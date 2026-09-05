"""nucleo/dispatch_prompts.py — Brain Worker prompt composition (V2-098 split from dispatch.py).

Pure prompt-string builders extracted from nucleo/dispatch.py: none of this touches SessionRecord, the session
pool, or any other dispatch.py module-level state — it only turns (request, context, brief) into the text a
worker receives. dispatch.py's session-launch code calls _build_prompt()/_web_prompt() directly (imported by
name), and re-exports them so existing test call sites (dispatch._build_prompt, dispatch._web_prompt, etc.)
keep working unchanged.
"""
from __future__ import annotations

from nucleo import research


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
        from nucleo import scheduler as _sched
        _ahora = _t.localtime(_sched.time.time())
    except Exception:  # noqa: BLE001
        _ahora = _t.localtime()
    return (f"FECHA/HORA REAL DE HOY: {_t.strftime('%A %d %b %Y', _ahora)} ({_t.strftime('%Y-%m-%d', _ahora)}), "
            f"{_t.strftime('%H:%M', _ahora)} hora local. Ancla a esto cualquier restricción temporal de la petición "
            f"(«el último» = el más reciente respecto a HOY; «de hoy»/«ahora» = esta fecha y de aquí en adelante; "
            f"«el de tal día» = esa fecha exacta). NUNCA des un dato caducado como si fuera vigente.")


# V2-057/V2-061 — método OBLIGATORIO: entender → planificar → ejecutar → REFLEJAR en los espejos → VERIFICAR → ITERAR.
# El worker no ejecuta a ciegas por deducción del texto; muchas órdenes son acciones ENCADENADAS (realidad ↔ widgets
# ↔ memoria) y hay que actualizar TODOS los planos y certificar que quedan coherentes antes de entregar.
_METHOD_BLOCK = (
    "MÉTODO (síguelo SIEMPRE, en este orden; no ejecutes a ciegas):\n"
    "1) ENTIENDE exactamente qué se pide, incluidas las restricciones IMPLÍCITAS: «el último/más reciente» = el "
    "más nuevo por fecha (no el primero por relevancia); «hoy/ahora/actual» = anclado a la fecha real de hoy y de "
    "aquí en adelante; «el de tal día» = esa fecha exacta; una cifra/precio/resultado = el VIGENTE. Distingue el "
    "PLANO: si es una acción del MUNDO REAL (cancelar/reservar una cita, dar de baja una suscripción, hacer/anular "
    "un pedido, pagar), la acción PRINCIPAL es en la realidad (la web/servicio donde se hizo) — la agenda y los "
    "widgets son solo ESPEJOS locales que reflejan esa realidad, NUNCA el objetivo en sí.\n"
    "2) PLANIFICA los pasos y LOCALIZA en memoria lo que necesites (dónde se reservó/contrató, la cita concreta, la "
    "cuenta) con python -m nucleo.mem_cli recall \"<qué buscas>\".\n"
    "3) EJECUTA la acción en la realidad con tus herramientas (navegador, etc.).\n"
    "4) REFLEJA el cambio en los ESPEJOS locales, encadenado: si afecta a un widget (borrar la cita ya cancelada de "
    "la agenda, actualizar una lista), hazlo con python -m nucleo.widget_cli (LEE el widget primero con `read` y usa "
    "los ids REALES que te devuelve, nunca inventes ids); si afecta a un hecho que zaelar recuerda, actualízalo con "
    "python -m nucleo.mem_cli remember. Un ESPEJO desactualizado (la cita sigue en la agenda tras cancelarla) es un "
    "fallo, no un detalle.\n"
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
    "`python -m nucleo.widget_cli read results` (te devuelve su contrato y la forma EXACTA del payload) → "
    "entrégalo en DOS pasos, que es la ÚNICA forma probada que pasa los guardas:\n"
    "     (i)  escribe el JSON con tu tool Write a un fichero de RUTA RELATIVA en tu directorio de trabajo — "
    "`informe.json` a secas. NUNCA `/tmp/…` ni una ruta absoluta ni `TMP/`: fuera de tu directorio la escritura "
    "pide una aprobación que nadie te va a dar.\n"
    "     (ii) `python -m nucleo.widget_cli data results present @informe.json`\n"
    "   …y después `python -m nucleo.widget_cli show results`. **Nunca pegues el JSON en la línea de comandos ni "
    "uses un heredoc**: las comillas y las llaves los bloquea el guarda del shell. Y no te inventes un script "
    "propio para llamar a la API: el puente ya está permitido, úsalo tal cual. "
    "Ponlo en cuanto tengas resultados sólidos, y ve añadiendo con `data results append` según encuentres más: es "
    "mejor que el operador vea llenarse el informe que esperar callado al final. Cada item con su enlace REAL y, si "
    "el operador pidió verlo con fotos, su `image`. La voz final entonces es CORTA (2-3 frases: qué has encontrado "
    "y que está en pantalla) — el detalle ya lo está leyendo.\n"
    "4c) SI LO QUE PIDIÓ SON LAS FOTOS, van al VISOR `imagenes`, no a la hoja (V2-457). La frontera es de QUÉ es la respuesta, no de si hay imágenes por medio: «enséñame fotos de X» se responde con las fotos, así que su sitio es el visor —una grande, miniaturas, y la FUENTE de cada una a la vista—; «búscame un hotel» se responde con hoteles, y ahí la foto es una columna de la ficha y se queda en la hoja. Mismos dos pasos y mismo puente: escribe el JSON a `fotos.json` y `python -m nucleo.widget_cli data imagenes show @fotos.json` (cada foto `{url, thumb, title, site, page, w, h}`), luego `show imagenes`. NUNCA vuelques un álbum en la hoja: es una tabla y se lee como una lista de enlaces, que es justo lo que el operador dijo que no quería ver.\n"
    "4d) SI LO QUE PIDIÓ ES UNA SOLA COSA PARA LEER —una receta, un informe o resumen que escribes tú, unas instrucciones, un texto largo, un PDF— su sitio es la HOJA EN BLANCO `documento`, no la de resultados (V2-549). La frontera es la misma de siempre, de QUÉ es la respuesta: varias opciones que se comparan van a `results`; UNA cosa que se lee entera va a `documento`. Si te pidió UNA (una receta, no recetas), elige tú la mejor con tu criterio y ponla completa — devolverle la lista de candidatos es hacerle a él el trabajo que te encargó. Mismos dos pasos y mismo puente: escribe el JSON a `doc.json` y `python -m nucleo.widget_cli data documento show @doc.json` ({\"kind\":\"markdown\",\"title\":\"…\",\"source\":\"de dónde sale\",\"body\":\"# Título\\n\\ntexto markdown…\"}), luego `show documento`. Si es largo, primer `show` con la estructura y `data documento append @parte.json` por cada sección: mejor que lo vea crecer a que espere callado. El contrato entero lo tienes con `python -m nucleo.widget_cli read documento`.\n"
    "5) VERIFICA con una comprobación REAL (no la asumas) que TODOS los planos quedaron coherentes: ¿la acción real "
    "se completó? ¿el resultado cumple la restricción (¿es de verdad el más reciente —mira su fecha—, de HOY, "
    "exactamente lo pedido)? ¿los espejos (widget/memoria) reflejan ya la realidad? Si algo no se puede certificar, "
    "dilo con honestidad — no des por bueno un resultado sin confirmarlo.\n"
    "6) ITERA si la verificación falla (afina la búsqueda, ordena por fecha, prueba otra fuente, corrige el espejo) "
    "hasta cumplirlo. Solo entrega cuando está CERTIFICADO en todos los planos. Nunca digas «hecho» sin verificar.")


# V2-167 · el navegador es el ÚLTIMO recurso, no el primero. Conducir un Chromium por una web de reservas es
# pelearse con las defensas que esas webs despliegan justo contra esto: una corrida entera se quedó en el muro
# anti-bot de Booking y otra en el CAPTCHA de Google. La red MeshKore tiene agentes que sirven esos mismos
# dominios por HTTP, gratis, en un segundo — medido: `roomrover` devuelve 10 hoteles reales con enlace de
# reserva, `aerocast` 10 vuelos con precio. No hay catálogo de agentes en ninguna parte: se le pregunta al
# oráculo EN EL MOMENTO, y lo que esté vivo y sea gratis ese día es lo que sale.
#
# V2-486 (2026-08-29) · esto vivía SOLO dentro de `_web_prompt`, y por eso la red no se consultó NI UNA vez en
# 399 informes de worker. La medición que lo cazó no es de la red, es del enrutador: `classify_kind` manda a
# `kind="web"` lo que `site_catalog.category_of` reconoce, y ese detector pide un verbo de RESERVA —
# «resérvame hotel en Nueva York» → `hotel_booking`, pero «búscame el mejor hotel de Nueva York» → `None`, o
# sea `generic`. Un hotel BUSCADO (que es como lo dice el operador) caía en el prompt genérico, que no
# nombraba `mesh_cli` en ninguna línea: la red no es que se descartara, es que el worker no sabía que existe.
#
# Se arregla por el PROMPT y no por el enrutador a propósito. Ensanchar `category_of` para que una búsqueda
# cuente como transaccional MUEVE a `kind="web"` encargos que hoy resuelve un worker genérico —y el propio
# `errand_kind` documenta por qué eso es peligroso: el fraseo de una búsqueda es el mismo que el de una
# investigación—. Dar el PASO 0 al genérico no cambia QUIÉN atiende el encargo, solo le dice que antes de
# buscar pregunte. Es la MISMA asimetría que ya se corrigió con el catálogo de sitios de confianza (V2-118) y
# con las reglas del cajón (V2-211): un bloque que solo viajaba en un prompt, y el otro worker sin él.
def _mesh_first_block(py: str = "python", *, browser: bool) -> str:
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
        + f"   {py} -m nucleo.mesh_cli find \"<el encargo, tal cual lo dijo el operador>\"\n"
        + f"   {py} -m nucleo.mesh_cli serve \"<el encargo>\" --prompt \"<el encargo con FECHAS ABSOLUTAS>\"\n"
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
        "hoy hay agentes vivos de hoteles, vuelos y entradas/eventos, y para lo demás el navegador sigue siendo "
        "el camino.\n\n"
    )


def _build_prompt(request: str, context: str, trusted: bool, brief: dict | None = None) -> str:
    header = ("Eres un Brain Worker del asistente personal zaelar: una sesión de trabajo que CONDUCE una tarea del "
              "operador con tus herramientas (memoria, navegador, código, búsqueda). Resuelve la PETICIÓN de forma "
              "concreta y devuelve SOLO el resultado útil, natural y humano, SIN jerga técnica ni interna (nunca "
              "'píldora', 'memoria de corto/largo plazo', 'base de datos', ids ni mecanismos). El RESULTADO FINAL "
              "que entregas (lo que zaelar dice/muestra al operador) debe ser CONCISO — sin relleno, sin repetir el "
              "trabajo paso a paso ya reportado por el progreso, sin inflar la respuesta; al grano. (Esto es del "
              "resultado final, NO de tu proceso de trabajo — sigue investigando/ejecutando todo lo que haga falta "
              "y reportando el progreso como se indica abajo.)\n"
              "REPORTA TU PROGRESO de forma ESTRUCTURADA (zaelar lo enseña al operador y lo usa para responder "
              "'¿cómo va?'):\n"
              "  1) AL EMPEZAR declara tu plan: python -m nucleo.agent_report plan \"paso1|paso2|paso3|…\" "
              "(3-6 pasos concretos).\n"
              "  2) AL COMPLETAR cada paso: python -m nucleo.agent_report progress \"<qué acabas de terminar>\" "
              "--done <nº de pasos hechos>.\n"
              "  3) Para una fase legible puntual: python -m nucleo.agent_report phase \"<qué haces ahora>\".\n"
              "Reporta de verdad (no lo olvides): sin reporte, el operador no ve avanzar la tarea. Si necesitas un "
              "dato del usuario para seguir, pregúntaselo con 'python -m nucleo.worker_bridge ask \"<pregunta>\"' y "
              "ESPERA su respuesta. Si necesitas que zaelar haga algo por ti (buscar en la web), usa "
              "'python -m nucleo.worker_bridge act <accion> @<fichero>.json' — el payload va SIEMPRE por "
              "fichero, en DOS pasos, igual que la hoja de resultados: (i) escribe el JSON con tu tool Write "
              "a un fichero de RUTA RELATIVA en tu directorio (`busca.json` a secas, nunca `/tmp/…` ni una "
              "ruta absoluta), (ii) pásalo con `@busca.json`. **JAMÁS pegues el JSON en la línea de "
              "comandos**: el guarda del shell bloquea las llaves con comillas dentro y el comando no llega "
              "a ejecutarse. Si lo que hace falta es que zaelar AVISE "
              "MÁS TARDE (un recordatorio, un seguimiento), prográmalo de verdad con la MISMA forma: "
              "'python -m nucleo.worker_bridge act schedule @aviso.json', con "
              "{\"when\":\"<cuándo>\",\"prompt\":\"<qué debe "
              "decir o hacer>\"} dentro del fichero — usa «mañana a las 9», «el miércoles a las 18:00», "
              "«every 30m» o un "
              "cron «0 9 * * 3», y si eso te devuelve un error, NO digas que lo has programado: dilo como "
              "está, sin programar. Para LEER u OPERAR un widget del canvas "
              "(reflejar en la agenda/lista lo que has hecho en la realidad, o ENSEÑAR en pantalla un conjunto de "
              "resultados): 'python -m nucleo.widget_cli read|data|show|close <widget>' (lee primero, usa ids "
              "reales). NUNCA reescribas el CÓDIGO de un widget para meterle datos: los datos entran por sus "
              "acciones declaradas, que ves con `read`. La MENSAJERÍA del operador (WhatsApp, Telegram y su "
              "CORREO) se consulta por esa misma vía: 'python -m nucleo.widget_cli read mensajeria' te dice qué "
              "canales están conectados y qué hay pendiente — NO existe ningún gmail_cli ni ninguna tool "
              "«gmail», y abrir el webmail en el navegador es el último recurso, nunca el primero.")
    if not trusted:
        header = ("Eres un asistente que SOLO razona sobre el texto (fuente NO confiable): no ejecutes acciones ni "
                  "uses herramientas.")
    parts = [header]
    if trusted:
        parts.append(_today_block())
        parts.append(_METHOD_BLOCK)
        # V2-486: el PASO 0 de la red también aquí — el porqué, en `_mesh_first_block`. Se escribe
        # con `python` a secas porque `_with_interpreter` sustituye el intérprete en todo el prompt.
        parts.append(_mesh_first_block(browser=False).rstrip())
        # SITIOS DE CONFIANZA también para el worker GENÉRICO (V2-118, 2026-08-18). Este catálogo solo viajaba en
        # `_web_prompt`, o sea únicamente cuando el operador NOMBRABA el sitio; el resto de las compras y
        # búsquedas de mercado —que caen aquí— salían sin él. Se midió: «búscame un monitor barato de SEGUNDA
        # MANO» volvió con monitores NUEVOS de una tienda, ignorando la única restricción que traía la petición.
        # Un worker genérico también navega (lo dice su propia cabecera), así que la carencia era del prompt, no
        # de sus capacidades. Va SIN titular de categoría a propósito: aquí caen las INVESTIGACIONES, y decirle
        # «empieza por Wallapop» a quien busca un velero de 50.000 € sería peor que no decirle nada.
        try:
            from nucleo.flash import site_catalog
            from voice.engine.core import langs as _langs
            parts.append(site_catalog.directive_block(site_catalog.resolve_locale(_langs.current_code())))
        except Exception:
            pass
    if context:
        parts.append("CONTEXTO DE MEMORIA (lo que zaelar ya sabe; úsalo si viene a cuento):\n" + context)
    if trusted:
        recent = _recent_conversation_block()
        if recent:
            parts.append("CONVERSACIÓN RECIENTE (los últimos turnos, para SITUAR la petición — los pronombres y "
                         "quejas del operador ('no se oye', 'ciérralo', 'eso') se refieren a lo que sale AQUÍ):\n"
                         + recent)
    parts.append("PETICIÓN:\n" + request)
    # El BRIEF va DESPUÉS de la petición literal, no antes: es la dirección de CÓMO hacerlo bien, y se lee mejor
    # sabiendo ya qué se pide. Sin brief (no es una investigación, o el compositor no estaba) esto no aparece y el
    # worker sale exactamente como salía antes.
    if brief:
        block = research.to_prompt_block(brief)
        if block:
            parts.append(block)
    return _with_interpreter(_with_presentation("\n\n".join(parts)))


# CONTROL DE CALIDAD DE PRESENTACIÓN (2026-08-10). El brief dirige QUÉ buscar y con qué exigencia; esto dirige CÓMO
# se ENSEÑA. Faltaba, y se vio: un worker hizo un trabajo impecable (45 candidatos, 3 propuestas verificadas) y lo
# pintó ilegible — títulos con tres ideas dentro, tarjetas descuadradas, un aviso cortado. No era culpa del modelo:
# los presupuestos de cada campo vivían solo en el CSS del widget, así que nadie se los había dicho.
def _with_presentation(prompt: str) -> str:
    """Añade las reglas de presentación de las superficies en blanco que el prompt mencione. Fail-open."""
    try:
        from widgets import presentation
        block = presentation.directive_for(prompt)
    except Exception:
        return prompt
    return prompt + "\n\n" + block if block else prompt


# El prompt se ESCRIBE con `python -m nucleo.…` porque así se lee; lo que le LLEGA al worker es el intérprete REAL
# y absoluto. En esta máquina `python` a secas no existe (solo `python3` y el venv) — y el worker obedecía la
# instrucción al pie de la letra, fallaba, y se ponía a probar variantes hasta topar con el allowlist. Con la
# narración del worker visible (2026-08-02) se le vio decirlo con todas las letras: «`python` (bare) pasó el
# permiso pero no existe el binario; `.venv/bin/python` existe pero pide aprobación». Sustituir aquí es un solo
# punto de verdad: el texto sigue legible y el comando sale siempre ejecutable y ya permitido.
def _with_interpreter(prompt: str) -> str:
    # Solo si el prompt REALMENTE trae puentes. El perfil UNTRUSTED (texto de un peer) va sin tools por
    # construcción: colarle la cabecera le daría la ruta absoluta del engine sin ninguna necesidad.
    if "python -m nucleo." not in prompt:
        return prompt
    try:
        from nucleo.workers.claude_session import bridge_python
        py = bridge_python()
    except Exception:
        return prompt
    if not py or py == "python":
        return prompt
    out = prompt.replace("python -m nucleo.", f"{py} -m nucleo.")
    # V2-211 — LAS TRES FORMAS MEDIDAS de morir en nuestra propia puerta, el mismo día y en tres casos distintos:
    #   `find-theatre-tickets__es` 15:24  cd in '…/zaelar/engine' was blocked. For security, Claude Code may only
    #                                     change directories to the allowed working directory
    #   `cheapest-monitor`         15:35  This Bash command contains multiple operations. The following part
    #                                     requires approval: curl -s "https://www.pccomponentes.com/monitores"
    #   `remember-and-remind`      15:38  …requires approval: cd /Users/…
    # En headless NADIE aprueba, así que una petición de aprobación es un callejón sin salida: el worker muere ahí,
    # callado, y el turno sigue contando que avanza. Es el confirm-gate una capa más abajo — un gate que para el
    # trabajo y no tiene camino de vuelta.
    #
    # Se ataca por delante, que es lo que ya funcionó con el intérprete el 2026-08-02 (el worker se pasaba minutos
    # probando `python`, `python3`, `.venv/bin/python`… porque el prompt no le decía cuál). Las reglas del cajón
    # donde corre no las puede deducir: o se las damos, o las descubre chocando, y chocar aquí cuesta la tarea.
    return _drawer_rules(py) + out


def _drawer_rules(py: str = "") -> str:
    """Las reglas del cajón donde corre el worker, en UN solo sitio.

    Estaban dentro de `_with_interpreter`, al que solo llama `_build_prompt` — así que el worker WEB, que es el
    que más shell compone porque conduce un navegador, era el único que NUNCA las recibía. Medido en
    `search-secondhand-monitor__es` (2026-08-24 00:56): tres `cd in '<engine>' was blocked` seguidos, a los
    42 s, en una ronda que entregó cero. Misma asimetría que V2-257 y con el mismo perjudicado.

    Sin `py` no se nombra el intérprete: la lista de fuera del cajón es la misma con o sin él, y el builder web
    ya escribe la ruta absoluta en cada línea de comando.
    """
    _py = (py or "").strip()
    cab = (f"INTÉRPRETE: para CUALQUIER puente (`-m nucleo.…`) usa EXACTAMENTE `{_py}`, tal cual, siempre. Está "
           f"permitido y funciona. NO uses `python` a secas ni `python3` ni rutas relativas.\n") if _py else ""
    _puente = f"`{_py} -m nucleo.nav_cli`" if _py else "`nucleo.nav_cli`"
    _busca = f"`{_py} -m nucleo.worker_bridge`" if _py else "`nucleo.worker_bridge`"
    _abs = f"`{_py}` es absoluto" if _py else "el intérprete es absoluto"
    return (cab +
            "TU CAJÓN (reglas del shell donde corres; romperlas NO da error, pide una aprobación que aquí no va a "
            "llegar nunca):\n"
            "  · NO SALGAS DE TU DIRECTORIO, y no es solo el `cd`: el cajón bloquea CUALQUIER comando que "
            "navegue o liste carpetas del repo del motor (`cd`, `ls`, `find`, `cat` de rutas del repo…). No "
            f"hace falta: los puentes funcionan desde donde estás — {_abs} y el resto ya viaja en "
            "el entorno (el `-m nucleo.…` PARECE pedir que te muevas a otro sitio y NO lo pide: el entorno ya lo "
            "lleva). Si lo intentas, lo que vas a leer es «cd in '…' was blocked. For security, Claude Code "
            "may only change directories to the allowed working directories», y no hay rodeo: no es una "
            "forma del comando que se pueda reescribir, es un sitio al que no se va. Lo que SÍ puedes es ABRIR con Read un fichero concreto cuya ruta absoluta te hayamos "
            "dado nosotros (la captura del navegador); eso está permitido y probado.\n"
            "  · UN comando por llamada. Nada de `&&`, `;`, `|`, `$(…)`, `${…}`, comillas invertidas ni "
            "varias cosas en la misma línea: se lee como varias operaciones, o como una expansión que el "
            "guarda no puede verificar, y se para ahí («Contains simple_expansion»).\n"
            "  · Y NI UN SOLO `&` AL FINAL para dejar algo corriendo de fondo. No es lo mismo que `&&` y por "
            "eso va aparte: el guarda lo para con otro mensaje («uses the `&` background operator, which "
            "defers execution past approval-time safety checks») y quien solo haya leído «nada de `&&`» no "
            "puede atar una cosa con la otra. Tampoco te hace falta: lo que tarda ya es asíncrono por los "
            "puentes — lanza y recoge con `wait`, que para eso está.\n"
            "  · NINGÚN argumento con llaves y comillas dentro. Un JSON pegado en la línea se bloquea "
            "(«Contains brace with quote character»): escríbelo con Write a un fichero de tu directorio y "
            "pásalo con `@fichero.json`. Todos los puentes lo aceptan.\n"
            "  · Solo los puentes. Ni `curl`, ni `wget`, ni scripts propios: para ABRIR una página usa "
            f"{_puente}, y para BUSCAR pídelo por {_busca}. Lo que traigas "
            "con `curl` además no pasa por el navegador del operador, así que ni ve las cookies ni cuenta como "
            "evidencia.\n"
            "  · Si un comando te pide aprobación, lo escribiste mal: REESCRÍBELO en la forma de arriba. No lo "
            "reintentes igual, no busques otra vía y no te calles — si de verdad no hay forma, DILO como "
            "resultado (`hbnote`/tu entrega) en vez de terminar en silencio.\n\n")


# Guía de COMPORTAMIENTO HUMANO en la web (regla del operador 2026-07-21: "que parezcan humanos, orientar el uso
# de las páginas; genérico, para medio mundo, ES o EN — no scrapear, un asistente, nada raro"). GENÉRICA a
# propósito: no nombra sitios; describe cómo se mueve una PERSONA por casi cualquier web. Se antepone al manual de
# comandos del worker web. El sigilo TÉCNICO (Chrome real + fingerprint humano) vive en widgets/navegador/owner.py;
# esto es el COMPORTAMIENTO (ritmo, orden, gestos) que el modelo controla turno a turno.
_HUMAN_NAV_GUIDE = (
    "NAVEGA COMO UNA PERSONA, no como un robot (vale para casi cualquier web, en español o inglés; eres un "
    "asistente navegando POR el operador, no un extractor masivo):\n"
    "• RITMO humano: una acción cada vez, deja que la página cargue y 'léela' con `look` antes de seguir. No "
    "dispares comandos a ráfagas ni recargues la misma página en bucle.\n"
    "• Usa la PROPIA web como un usuario: su buscador y sus FILTROS (precio, ubicación, categoría, orden por "
    "fecha/precio) en vez de forzar URLs raras o parámetros a mano. Escribe en su caja de búsqueda y pulsa buscar.\n"
    "• COOKIES/consentimiento: acéptalos con naturalidad (un humano lo hace) para poder ver el contenido; si el "
    "banner reaparece, ciérralo y sigue.\n"
    "• Desplázate GRADUALMENTE (scroll de a poco, como quien ojea) para que carguen los resultados; abre una "
    "ficha/anuncio concreto para leer el detalle, como una persona interesada de verdad.\n"
    "• Si aparece una VERIFICACIÓN anti-robot, un captcha o un aviso de 'demasiadas peticiones': NO insistas a lo "
    "bruto (eso confirma que eres un bot). Para, espera unos segundos y reintenta UNA vez despacio; si sigue "
    "bloqueado, prueba OTRA web equivalente que tenga el mismo dato, o dilo con honestidad. Nunca machaques ni "
    "recargues en bucle.\n"
    "• No hagas nada 'raro': no toques login/pagos salvo que el objetivo lo pida y tengas permiso; no aceptes "
    "promos ni suscripciones; céntrate en el objetivo como lo haría una persona con prisa pero educada.\n\n"
)


def _category_lead(goal: str, lang_code: str | None) -> str:
    """One line naming the trusted site for THIS goal's category, ahead of the whole catalog (V2-119).

    The catalog block that follows lists every category, and a worker reading six bullets still has to decide
    which one is its own — `restaurant-tonight-madrid` shows what that costs: the run never reached TheFork at
    all, and the worker ended up asserting a policy about the restaurant it had never opened. Naming the site
    the dispatcher ALREADY matched (it is the same call that routed this task to the browser in the first
    place, `dispatch._classify_kind`) removes that decision. When no category matches, this is empty and the
    catalog behaves exactly as before."""
    from nucleo.flash import site_catalog
    loc = site_catalog.resolve_locale(lang_code)
    category = site_catalog.category_of(goal, loc)
    entry = site_catalog.entry_for(category, loc) if category else None
    if entry is None:
        return ""
    return (f"ESTA TAREA es de categoría «{category}»: EMPIEZA por {entry.name} ({entry.url}) — {entry.note} "
            f"Solo si el objetivo genuinamente NO aparece ahí, ve a otro sitio, y DILO al entregar.\n\n")


def _web_prompt(goal: str, context: str, brief: dict | None = None, *, vision: bool = True) -> str:
    """Prompt del worker WEB (portado de web_cc/V2-036 al sustrato V2-038): conduce el navegador por hbweb con
    criterio de CIERRE (extraer → concluir → entregar) e hitos visibles. Sin él, el worker deambula.

    Con `brief` (nucleo/research.py) la BÚSQUEDA deja de ser «filtra y coge los 2-3 primeros»: el atajo de cierre
    rápido que este prompto lleva de serie —correcto para «tráeme el precio de X», ruinoso para «elige lo mejor»—
    se sustituye por el embudo del brief (reunir ancho → filtrar → puntuar → verificar finalistas).

    `vision=False` (V2-289) cuando el modelo que conduce NO lee imágenes. El paso 1 le decía que la VISIÓN es su
    camino PRINCIPAL, y a un modelo de texto eso es una orden que no puede cumplir — la misma clase que ordenar
    «cuéntale QUÉ has encontrado» a un turno que no sostiene nada (V2-284). Medido con el relevo a DeepSeek
    puesto: `Read` de la PNG → «formato no soportado» → «sigo por DOM», dos veces en la misma corrida. La
    alternativa (dejar el prompt igual y que lo descubra chocando) es la que estaba costando la corrida.

    Por DEFECTO hay visión, que es lo de siempre: un «no ve» equivocado deja ciego a un worker que veía."""
    try:
        from nucleo.workers.claude_session import bridge_python
        py = bridge_python()          # absoluto y permitido; `.venv/bin/python` relativo pedía aprobación
    except Exception:
        py = ".venv/bin/python"
    try:
        from voice.engine.core import langs
        native = langs.current_language().native
        lang_code = langs.current_code()
    except Exception:
        native = "español"
        lang_code = None
    # V2-044 sesión 22:40: el objetivo escalado puede venir TERSO — la conversación reciente sitúa los pronombres
    # y restricciones que el modelo rápido no reformuló ("no se oye", "esa", "la de antes").
    from nucleo.flash import site_catalog
    recent = _recent_conversation_block()
    recent_block = (f"CONVERSACIÓN RECIENTE (sitúa el objetivo; lo que el operador mencione se refiere a esto):\n"
                    f"{recent}\n\n") if recent else ""
    p = (
        "Eres un Brain Worker de zaelar que CONDUCE un navegador web REAL para cumplir un OBJETIVO del operador, "
        f"paso a paso y con criterio. OBJETIVO (respétalo al pie de la letra):\n«{goal}»\n\n"
        + _today_block() + "\n\n"
        + recent_block +
        _category_lead(goal, lang_code) +
        site_catalog.directive_block(site_catalog.resolve_locale(lang_code)) + "\n\n" +
        _HUMAN_NAV_GUIDE +
        # V2-277 — esta línea decía «desde la raíz del repo», y desde V2-117 es FALSA: el worker corre con el
        # cwd CONFINADO a su propio directorio temporal. Así que le estábamos DICIENDO dónde estaba, mal, y
        # luego bloqueando el `cd` con el que iba a llegar. Medido en `search-secondhand-monitor__es`
        # (2026-08-24 00:56): TRES `cd in '<engine>' was blocked` seguidos en el worker web, a los 42 s, y una
        # ronda que acabó entregando cero. No era el modelo cabezota: hacía lo que aquí ponía.
        "CÓMO CONDUCIR (los comandos funcionan DESDE DONDE ESTÁS —el intérprete es absoluto y el resto viaja en "
        "el entorno—; el navegador ya tiene su pestaña asignada):\n"
        f"• VER la página como un humano (VISIÓN): {py} -m nucleo.nav_cli look\n"
        "     → imprime la ruta de un PNG; ÁBRELO con tu tool Read para VER la página, y actúa por coordenadas:\n"
        f"• Click por coordenadas (visión):  {py} -m nucleo.nav_cli click_at <x> <y>\n"
        f"• Escribir por coordenadas:        {py} -m nucleo.nav_cli type_at <x> <y> \"<texto>\" --submit\n"
        f"• (alternativa DOM) elementos:     {py} -m nucleo.nav_cli snapshot   → luego click <ref> / type <ref> \"<txt>\"\n"
        f"• Ir a una URL:                    {py} -m nucleo.nav_cli navigate \"<url>\"\n"
        f"• Desplazar / extraer:             {py} -m nucleo.nav_cli scroll 800   ·   {py} -m nucleo.nav_cli extract\n"
        # VALORAR FICHA A FICHA sin perder el listado. Antes había que `navigate` a la ficha —que se lleva la
        # ÚNICA pestaña— y volver a buscar el listado: dos navegaciones por ficha, con los filtros de por
        # medio. `visit` abre la suya, la lee y la cierra. Se le dice PARA QUÉ sirve porque un verbo que el
        # prompt no explica se queda sin usar (misma lección que V2-219).
        f"• MIRAR UNA FICHA sin perder el listado: {py} -m nucleo.nav_cli visit \"<url del anuncio>\"\n"
        "  → devuelve título + descripción de ESA ficha. Es como abrirla en otra pestaña y cerrarla: el\n"
        "    listado y tus filtros siguen donde estaban. Úsalo para COMPARAR candidatos uno a uno en vez de\n"
        "    decidir con el título de la lista; `navigate` a un anuncio te deja sin listado.\n"
        f"• Progreso ESTRUCTURADO (el operador lo VE y zaelar responde '¿cómo va?'): al empezar "
        f"{py} -m nucleo.agent_report plan \"paso1|paso2|paso3\"  y al terminar cada paso "
        f"{py} -m nucleo.agent_report progress \"<hecho>\" --done <n>\n"
        f"• Fase legible puntual (tarjeta): {py} -m nucleo.agent_report phase \"<qué haces>\"\n"
        f"• Preguntar al operador y ESPERAR su respuesta: {py} -m nucleo.worker_bridge ask \"<pregunta>\"\n"
        f"• Leer un dato que zaelar ya sepa:  {py} -m nucleo.mem_cli recall \"<consulta>\"\n"
        # Entrada de CATÁLOGO, no una orden: el QUÉ y el PORQUÉ viven una sola vez, en «LO QUE AVERIGUAS SE
        # GUARDA» (V2-344). Dejar aquí también un motivo («para no volver a pedirlo») era media instrucción
        # suelta, y dos mitades en dos sitios es como una decisión se separa de sí misma sin avisar.
        f"• GUARDAR un dato que reúnas: {py} -m nucleo.mem_cli remember \"<dato>\" --slot task.<algo>\n\n"
        "⚠️ ESOS son TODOS los subcomandos de `nav_cli` que existen — snapshot, look, navigate, click, type, "
        "select_option, click_at, type_at, scroll, press, extract, visit. NO existen `automate`, `act` ni otro; "
        "invocarlos falla con «invalid choice» y quema un turno entero sin avanzar. `extract` NO lleva texto "
        "de argumento (solo `--limit N` opcional) y `scroll` lleva un número de píxeles, nunca la palabra "
        "'down'/'up'. Usa la sintaxis exacta de arriba, no la que te parezca natural.\n\n"
        + _mesh_first_block(py, browser=True) +
        "MÉTODO — como lo haría una persona competente; entiende la página y AVANZA (no des vueltas):\n"
        + (
            "1) MIRA con `look` (VISIÓN) antes de actuar: abre el PNG con Read y ubica los campos/botones por su "
            "posición en píxeles. La visión es tu camino PRINCIPAL para rellenar formularios, elegir en un "
            "calendario/desplegable o pulsar el botón correcto — el snapshot de texto es solo apoyo cuando los "
            "nombres son claros. Tras CADA acción importante vuelve a `look` para confirmar qué cambió (las "
            "coordenadas cambian al hacer scroll/navegar).\n" if vision else
            "1) MIRA con `look` antes de actuar y trabaja con los ELEMENTOS que te devuelve: tu modelo NO LEE "
            "IMÁGENES, así que la captura no te sirve de nada — no la abras con Read ni uses click_at/type_at, "
            "que piden coordenadas de algo que no puedes ver. Tu camino es el snapshot de texto: `click <ref>` y "
            "`type <ref> «texto»` con el número que sale al lado de cada elemento. Tras CADA acción importante "
            "vuelve a `look` para confirmar qué cambió (los números se REPARTEN de nuevo en cada mirada, así que "
            "un [ref] de antes puede ser ahora otro elemento).\n")
        + "2) DESBLOQUEA lo que tape la página: banner de cookies/consentimiento o aviso modal → ACÉPTALO/ciérralo "
        "(«Aceptar», «Acepto», «Entendido», «Continuar»…) para poder seguir. Si reaparece un par de veces, sigue igual.\n"
        "3) RECONOCE primero, pregunta UNA vez, ejecuta después (para una GESTIÓN: reservar/pedir cita, rellenar y "
        "enviar un formulario, tramitar, contratar):\n"
        "   a. RECON: recorre el flujo hasta VER el formulario real y ENUMERA todos los datos que pedirá (matrícula, "
        "fecha de matriculación, DNI, nombre, email, teléfono, estación, día/hora…). Consulta `mem_cli recall` lo que "
        "zaelar ya sepa.\n"
        "   b. PIDE DE GOLPE lo que falte: una SOLA `worker_bridge ask` con TODOS los datos que te faltan a la vez "
        "(no de uno en uno, no vayas y vengas). Espera la respuesta. NUNCA inventes valores.\n"
        "   c. EJECUTA hasta el FINAL: rellena TODOS los campos con visión, elige opciones, avanza el calendario, "
        "acepta condiciones y ENVÍA/CONFIRMA. Es una acción a TERMINAR, no algo que se le explique al operador.\n"
        + ("   (Si el objetivo es BUSCAR/COMPARAR: llega a la página de RESULTADOS con los filtros exactos "
           "—categoría excluyente, ubicación/orden— y `extract`. NO cierres con los primeros que salgan: esta tarea "
           "trae un BRIEF DE INVESTIGACIÓN al final del prompt que fija cuántos candidatos hay que reunir ANTES de "
           "descartar y con qué baremo verificar a los finalistas. Manda el brief.)\n"
           if brief else
           "   (Si el objetivo es BUSCAR/COMPARAR productos: llega a la página de RESULTADOS con los filtros exactos "
           "—categoría excluyente, ubicación/orden—, `extract`, y concluye con los 2-3 que mejor encajan.)\n")
        +
        "4) SOLO te detienen dos cosas: un CAPTCHA o un LOGIN/pago que exija credenciales que no tienes. Todo lo demás "
        "(entender la página, aceptar cookies, elegir en un desplegable/calendario, rellenar y enviar) lo resuelves TÚ "
        "con visión — no es excusa para parar. Un muro de verdad NO se reintenta: la respuesta de `nav_cli` trae "
        "`wall` cuando la página te ha parado (verificación anti-robot, captcha, error de carga), y en cuanto lo "
        "veas deja de darte contra él. Haz DOS cosas, en este orden: (a) vuelve al PASO 0 y prueba la red con ese "
        "encargo —un agente de la red no tiene captcha—, y (b) si tampoco, PÁRATE y dilo: qué sitio te bloqueó, con "
        "qué, y qué necesitas del operador (que entre él, o probar otro sitio). Insistir contra un muro es lo que "
        "convirtió una corrida entera en once minutos sin nada que entregar.\n"
        "5) NO TE ATASQUES: si repites la misma acción sin avanzar 2-3 veces, cambia de estrategia (otra entrada, otro "
        "botón, `look` de nuevo por si la coordenada cambió). Nunca gires en bucle en silencio. Reporta tu fase en "
        "CADA cambio de etapa. Si te REANUDAN una tarea ya empezada, haz `look` primero para ver dónde te quedaste y "
        "continúa desde ahí — NO reinicies desde cero.\n"
        # V2-303 — the price-filter widget trap, hit in ~half of the measured rounds: typing «150» into a
        # site's price control produced `min_sale_price=750` once and `max_sale_price=850`/`=800` twice — the
        # page's dual-slider binds the typed digits to whichever bound it pleases. The recovery that WORKED in
        # every round that passed is generic (edit the URL parameter), so it stops being a discovery the worker
        # has to make mid-task and becomes part of the recipe.\n
        "5b) LOS FILTROS SE VERIFICAN EN LA URL: la respuesta de cada acción trae la URL y su DELTA (qué "
        "parámetro cambió). Tras aplicar un filtro numérico (precio, año, km), LEE ese delta: si el parámetro "
        "quedó con un número DISTINTO del que pediste (escribes 150 y aparece `max_sale_price=850` o "
        "`min_sale_price=750`), el control de la página te ha traicionado — NO vuelvas a pelearte con él: "
        "corrige la URL directamente con `navigate` cambiando ese parámetro al valor pedido, y sigue. Un "
        "filtro mal puesto no falla con ruido: te llena la hoja de resultados fuera de rango.\n"
        "6) Si una respuesta de un puente trae ⟦NUEVAS INSTRUCCIONES DEL OPERADOR⟧, incorpóralas al objetivo.\n"
        "7) VERIFICA antes de cerrar (V2-057): comprueba de VERDAD que lo que vas a entregar cumple la restricción del "
        "objetivo — si pedía «el último/más reciente», confirma su FECHA (que sea el más nuevo, no uno cualquiera); "
        "si pedía algo «de hoy/actual», que el dato sea de la fecha real de hoy y de aquí en adelante; que sea "
        "EXACTAMENTE lo pedido, no algo parecido. Si no cumple, ITERA (ordena por fecha, afina el filtro, otra "
        "fuente) hasta que cumpla; si no se puede certificar, dilo con honestidad. No des por bueno un resultado sin "
        "confirmarlo.\n"
        # V2-431 — UN «NO» BIEN FUNDADO ES UNA ENTREGA. Medido en `find-concert-tickets__es` (2026-08-28,
        # plató 24/7): no había concierto de Rosalía en Madrid ese mes —una respuesta completa y correcta— y
        # el worker llenó la hoja de eventos que no eran, dejando a la persona SIETE MINUTOS esperando. El
        # paso 7 cubre «no puedo certificarlo»; esto es lo contrario y no estaba: SÍ lo certifiqué, y lo que
        # certifiqué es que no existe. Sin decirlo, el único final que le queda al worker es seguir buscando.
        "8) SI LA RESPUESTA ES QUE NO HAY, ESO ES LA ENTREGA. Buscar bien y encontrar que no existe —ese "
        "concierto no está programado, ese modelo no baja de ese precio, esa cita no tiene hueco— es un "
        "resultado COMPLETO y se entrega como tal, diciendo dónde miraste y qué descartaste. Lo que NUNCA "
        "vale es rellenar con lo que no cumple para no volver con las manos vacías: quien pregunta prefiere "
        "un «no» en dos minutos a siete minutos de cosas que no pidió.\n"
        # V2-344 — LO QUE AVERIGUA SOBREVIVE A QUE LO MATEN. Medido en `search-buy-used-car` (sesión 7575e81a,
        # 2026-08-26): worker 1 llegó a milanuncios y capturó, muerto a los 2 min; worker 2 muerto a los 8; el 3
        # entregó. En la BD del plató, la ÚNICA fila con `source=worker:*` en toda la ventana 13:33-13:54 es la
        # del que entregó — los 21 minutos de los dos primeros no dejaron rastro, y cada relanzamiento renavegó,
        # rebuscó y refiltró desde cero.
        #
        # La capacidad estaba ENTERA: `mem_cli` viaja en los puentes, la ruta exige token por tarea y el gate de
        # precisión PASA hallazgos (probado: «Milanuncios: VW Golf VII 1.6 TDI 2018, 11.400 €» pasa; solo rechaza
        # preguntas reificadas). Lo que faltaba era PEDIRLO: la única orden fuerte de guardar —y decía literalmente
        # «aunque el flujo se reinicie», o sea la protección anti-relanzamiento— vivía dentro del punto 3, acotado
        # en su encabezado a «para una GESTIÓN: reservar, pedir cita, rellenar un formulario, tramitar». Una
        # búsqueda cae en la rama BUSCAR/COMPARAR, que no menciona guardar nada. Misma forma que V2-257: la
        # instrucción correcta existía, en la rama equivocada.
        #
        # UNA instrucción con su bifurcación DENTRO (V2-226), no una por rama — por eso el 3.c de arriba se
        # RETIRA en vez de duplicarse aquí. Y con su límite de volumen dentro del mismo imperativo: guardar las
        # 40 filas de un listado convierte la memoria en ruido, así que la frontera es lo que AVERIGUASTE, nunca
        # lo que HICISTE.
        f"LO QUE AVERIGUAS SE GUARDA, porque a ti pueden matarte y a la memoria no: si te relanzan con este mismo "
        f"encargo, lo que dejaste guardado es TODO lo que el siguiente encuentra — sin ello renavega, rebusca y "
        f"refiltra desde cero. Así que cada vez que confirmes un dato que te ha costado conseguir, guárdalo EN EL "
        f"ACTO con {py} -m nucleo.mem_cli remember \"<el dato>\" --slot task.<algo>, y lo que guardas depende de "
        f"lo que estés haciendo: en una GESTIÓN, cada dato del formulario según lo reúnes (matrícula, DNI, fecha…) "
        f"para no volver a pedírselo al operador; en una BÚSQUEDA, cada candidato que pase tu criterio con su "
        f"nombre y su precio, y el filtro exacto que ya te funcionó. Lo que NO se guarda es lo que HICISTE: «he "
        f"abierto coches.net» o «he aceptado las cookies» no es un hallazgo, es ruido, y llenar la memoria de eso "
        f"la estropea para todos.\n\n"
        # V2-257 — DÓNDE se ve lo que encuentra. Este prompt no nombraba la hoja ni una sola vez (medido:
        # 0 ocurrencias de `widget_cli` y 0 de `results`), así que el worker no tenía forma de saber que existe —
        # mientras `dispatch._sheet_open` se la abría al operador delante, vacía, en cuanto encargaba. Nombrarla
        # tiene además un efecto colateral buscado: `_with_presentation` engancha sola los presupuestos de campo
        # de esa superficie al ver su id en el texto.
        # UNA instrucción con su bifurcación DENTRO (V2-226): «escribe el informe y no las filas», no dos órdenes.
        "DÓNDE SE VE LO QUE ENCUENTRAS — son DOS superficies y no son intercambiables: la TARJETA del navegador "
        "es el monitor (enseña por dónde vas y nada más), y la HOJA `results` es donde el operador mira los "
        "hallazgos; se le abrió delante en cuanto te encargó esto. ESCRIBE en esa hoja el INFORME de cierre "
        "—conclusión, criterios y en qué sitios entraste y qué pasó en cada uno— y NO las filas que ya sacaste "
        "con `extract`: cada extracción viaja sola a la hoja, y repetirla solo la ensucia.\n"
        f"   {py} -m nucleo.widget_cli data results present @informe.json\n"
        "   · SIEMPRE desde fichero con `@`: pegar un JSON de verdad en la línea de comandos se rompe con el "
        "quoting del shell y se queda esperando una aprobación que nadie va a dar.\n\n"
        "8) CIERRE: cuando la gestión esté HECHA y VERIFICADA (cita confirmada, formulario enviado, dato certificado) "
        "o de verdad necesites algo del operador, ESCRIBE tu conclusión/estado final en " + native + ", natural y "
        "humana, SIN jerga interna (nada de refs, comandos, coordenadas ni ids). Tu ÚLTIMA salida de texto es lo que "
        "se le dirá por voz. No inventes: básate en lo que VISTE. Si confirmaste una cita, di el día/hora/estación "
        "exactos."
    )
    if context:
        p += "\n\nCONTEXTO DE MEMORIA (lo que zaelar ya sabe; úsalo si viene a cuento):\n" + context
    if brief:
        block = research.to_prompt_block(brief)
        if block:
            p += "\n\n" + block
    # V2-277 — y las REGLAS DEL CAJÓN, que hasta hoy solo llegaban al worker GENÉRICO: `_with_interpreter` se
    # llama desde `_build_prompt` y este builder no pasa por ahí. Es la asimetría de V2-257 otra vez, en el
    # mismo sitio y con el mismo perjudicado — el worker que abre un navegador es justo el que más shell
    # compone, y era el único que no sabía qué le está permitido. Se le añaden aquí, no moviendo la llamada:
    # `_with_interpreter` además SUSTITUYE `python -m nucleo.` en el texto, y este prompt ya escribe la ruta
    # absoluta en cada línea, así que pasarlo por ahí no haría nada y taparía el motivo.
    return _with_presentation(_drawer_rules() + p)
