"""The web worker's brief (`_web_prompt`): drive the browser with a closing criterion and visible milestones.
"""
from __future__ import annotations

from nucleo.workers import brief as research
from nucleo.workers.prompts.context import _mesh_first_block, _recent_conversation_block, _today_block
from nucleo.workers.prompts.drawer import _HUMAN_NAV_GUIDE, _category_lead, _drawer_rules, _with_presentation
from nucleo.workers.prompts.surfaces import worker_language_block

def _web_prompt(goal: str, context: str, brief: dict | None = None, *, vision: bool = True) -> str:
    """Prompt del worker WEB (portado de web_cc/V2-036 al sustrato V2-038): conduce el navegador por hbweb con
    criterio de CIERRE (extraer → concluir → entregar) e hitos visibles. Sin él, el worker deambula.

    Con `brief` (nucleo/workers/brief.py) la BÚSQUEDA deja de ser «filtra y coge los 2-3 primeros»: el atajo de cierre
    rápido que este prompto lleva de serie —correcto para «tráeme el precio de X», ruinoso para «elige lo mejor»—
    se sustituye por el embudo del brief (reunir ancho → filtrar → puntuar → verificar finalistas).

    `vision=False` (V2-289) cuando el modelo que conduce NO lee imágenes. El paso 1 le decía que la VISIÓN es su
    camino PRINCIPAL, y a un modelo de texto eso es una orden que no puede cumplir — la misma clase que ordenar
    «cuéntale QUÉ has encontrado» a un turno que no sostiene nada (V2-284). Medido con el relevo a DeepSeek
    puesto: `Read` de la PNG → «formato no soportado» → «sigo por DOM», dos veces en la misma corrida. La
    alternativa (dejar el prompt igual y que lo descubra chocando) es la que estaba costando la corrida.

    Por DEFECTO hay visión, que es lo de siempre: un «no ve» equivocado deja ciego a un worker que veía."""
    try:
        from nucleo.workers.providers.claude import bridge_python
        py = bridge_python()          # absoluto y permitido; `.venv/bin/python` relativo pedía aprobación
    except Exception:
        py = ".venv/bin/python"
    try:
        from i18n import langs
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
        # V2-677 — this prompt already named the language in step 8, at the very END and only for the closing
        # sentence; every progress line and every question to the operator on the way there is heard too.
        + (worker_language_block() + "\n\n" if worker_language_block() else "")
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
        f"• Leer un dato que zaelar ya sepa:  {py} -m nucleo.mem_cli recall \"<consulta>\" (lo DICHO, literal: mem_cli history \"<tema>\")\n"
        # Entrada de CATÁLOGO, no una orden: el QUÉ y el PORQUÉ viven una sola vez, en «LO QUE AVERIGUAS SE
        # GUARDA» (V2-344). Dejar aquí también un motivo («para no volver a pedirlo») era media instrucción
        # suelta, y dos mitades en dos sitios es como una decisión se separa de sí misma sin avisar.
        f"• GUARDAR un dato que reúnas: {py} -m nucleo.mem_cli remember \"<dato>\" --slot task.<algo>\n\n"
        "⚠️ ESOS son TODOS los subcomandos de `nav_cli` que existen — snapshot, look, navigate, click, type, "
        "select_option, click_at, type_at, scroll, press, extract, visit. NO existen `automate`, `act` ni otro; "
        "invocarlos falla con «invalid choice» y quema un turno entero sin avanzar. `extract` NO lleva texto "
        "de argumento (solo `--limit N` opcional) y `scroll` lleva un número de píxeles, nunca la palabra "
        "'down'/'up'. Usa la sintaxis exacta de arriba, no la que te parezca natural.\n\n"
        + _mesh_first_block(py, browser=True, goal=goal) +
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
        # V2-652 — measured live (session 7f77e2cc): the worker typed the placeholder NIF «12345678Z» into
        # Hacienda's REAL form twice, the census validation refused, and it kept grinding the same modal for
        # minutes instead of asking for the real datum. Recon ends at a validated field.
        "   ⚠ Un formulario REAL se envía de verdad: JAMÁS lo avances con valores inventados o de prueba "
        "(«12345678Z», nombres falsos). Si un paso VALIDA un dato personal (NIF/DNI contra un censo, un "
        "login), el RECON acaba AHÍ: pide el dato real (b) y espera, o entrega el bloqueo nombrando el dato "
        "exacto que falta. Reintentar contra esa validación con datos falsos no es explorar, es fallar en "
        "bucle.\n"
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
