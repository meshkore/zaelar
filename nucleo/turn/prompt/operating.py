"""The operating prose and the resource layer of the voice turn — the STABLE prefix (V2-027, V2-536).

⚠️ refactor2710-08 T-01: «CÓMO OPERAS» reads NO truth — it is hard-coded prose about how to behave, ~3 100 tokens on
every turn. It stays until the battery says it can go; every other block of the prompt names its source.
"""
from __future__ import annotations

from nucleo.flash import canvas_claim as _canvas_claim
from nucleo.flash.live_blocks import _cron_line


def _connector_briefs(open_ids: set[str], turn_text: str = "") -> str:
    from nucleo.turn.prompt import catalogs
    return catalogs.connector_facts(open_ids, turn_text)


def proactive() -> str:
    """The cron protocol with what is scheduled, the workers' directive while one runs, and each live rail's line —
    LIVE state (scheduler jobs, dispatch sessions, rails), so it rides after the stable prefix (refactor2710-08 T-01:
    the cron line was where the cacheable prefix broke in 117 of 783 measured turn pairs)."""
    return (_cron_line() + _workers_directive() + _rails_directive()).strip("\n")


def _workers_directive() -> str:
    """Brain Worker MANAGEMENT directive (V2-038 §v3·F)—only while workers are live. It used to be embedded in
    `memory.compose_state()` (2026-07-14 audit): that prose belongs to FlashBrain (V2-027: memory composes shared
    STATE; each brain adds ITS resource layer). Session DATA ("BACKGROUND PROCESSES running" + WAIT markers)
    still comes from STATE."""
    try:
        from nucleo import dispatch
        if not dispatch.has_active():
            return ""
    except Exception:
        return ""
    return ("\nDIRIGES los PROCESOS DE FONDO de tu ESTADO: asocia cada orden del operador a SU proceso por el "
            "objetivo. Si REFINA/amplía uno en curso ('además, que sea verde'), INYÉCTALE la instrucción "
            "(send_to_worker) — NO abras otro. Si se QUEJA de que uno tarda o no trae nada, INYÉCTALE "
            "(send_to_worker) que ENTREGUE YA lo mejor que lleve y siga afinando — matarlo tira lo andado, y se "
            "reserva para cuando te lo ORDENE o su estado lo marque atascado. Si pide PARARLO, mátalo "
            "(stop_worker). Si uno ESPERA una respuesta, lo que diga el operador es esa respuesta "
            "(answer_worker). NO relances uno que ya corre.\n")


def _rails_directive() -> str:
    """Situational RAILS GUIDE (V2-042)—each rail with a live run contributes ITS line, and only then
    (`nucleo/rails.prompt_lines()`): prompts isolated by behavior, zero cost while the rail is idle (the
    operator's idea; the same situational pattern as `_workers_directive`)."""
    try:
        from nucleo import rails
        lines = rails.prompt_lines()
    except Exception:
        return ""
    return ("\n" + "\n".join(lines) + "\n") if lines else ""


def _flash_layer(open_ids: set[str], recent_ids: list[str] | None = None,
                 turn_text: str = "", stats: dict | None = None) -> str:
    return "\n\n".join(p for p in _flash_parts(open_ids, recent_ids, turn_text=turn_text, stats=stats) if p)


def _flash_parts(open_ids: set[str], recent_ids: list[str] | None = None,
                 turn_text: str = "", stats: dict | None = None) -> tuple[str, str, str]:
    """`(operating, resources, connectors)` — the RESOURCE LAYER (D), CONCISE (V2-027). Replaces the ~75-line `_FAST_RULES`: essential VOICE
    rules fit in 3–4 sentences; "how each tool is used" does NOT go here (it lives in `router.TOOLS`, the single
    source per tool). RESOURCES (widgets/web/browser) are data-driven, not hard-coded prose.

    `turn_text` (V2-085) = the operator's sentence THIS turn. It is not used to classify intent (invariant: no
    verb tables), but for RETRIEVAL: `brief.for_prompt` promotes the widget named by the operator into the top K,
    keeping the widget block O(K), not O(N), regardless of catalog size."""
    from widgets.brief import for_prompt as _widgets
    ops = (
        "── CÓMO OPERAS (capa rápida, tiempo real) ──\n"
        # V2-713 R5 — «1-2 frases» y «UNA ACCIÓN por turno» salieron de aquí: son PREFERENCIAS del
        # operador, no física del canal, y `principles.md` las llama carril sobre el JUICIO. Viven en
        # `genesis.json › style` y las compone `style_policy.shape_line()`, que ya viaja con las líneas
        # del turno — así él las cambia hablando, como V2-633 hizo con el silencio de las órdenes
        # cortas, en vez de que las fije quien estuviera trabajando ese día. Lo que SÍ se queda es lo
        # que es del medio: la voz no puede leer markdown ni emojis, y quedarse mudo rompe el turno.
        "Hablas sin markdown, emojis ni símbolos que leer; nunca te quedas mudo. "
        # 2026-09-09, session 2bdc67ee: filler + wait-opener reply back to back read as two people not listening
        # to each other; the filler fires after this request is in flight, so the model can only skip ITS wait.
        "Si tardas, el sistema YA dice por ti un pequeño nexo de espera («a ver…», «voy…») y tu respuesta suena "
        "justo después: entra DIRECTA al contenido, nunca la abras con otra frase de espera («dame un momento», "
        "«déjame mirar») — esa parte ya está dicha. "
        "Si en la misma frase te "
        "preguntan DOS cosas (la hora Y el precio, el sitio Y cómo llegar), las contestas LAS DOS en ese turno — "
        # V2-135: this starts with SEARCH. If a sentence also asks for the price but you search only "Prado Museum
        # hours," the other half is absent from the results: it is not merely forgotten; there is no material to
        # answer it. The query must cover everything asked, not just one part.
        "y si para eso buscas, que la BÚSQUEDA cubra las dos: con media query no hay con qué contestar la otra "
        "mitad. "
        "dejarte media pregunta obliga al operador a repetirla y es de las cosas que más molestan. Antes de "
        "cerrar el turno repasa la frase que te dijo: ¿queda algo suyo sin contestar? Si no puedes con una de las "
        "partes, dilo — «lo otro no lo tengo» —, pero no la ignores. "
        "Ante una ORDEN de acción: HAZLA y confírmalo en UNA frase corta — NO "
        "te disculpes en bucle, NO repitas 'tienes razón', NO narres tu razonamiento ni por qué antes falló. Si el "
        "operador insiste en una ACCIÓN CONCRETA que pidió y no pasó ('te dije que abrieras X', 'no has cancelado "
        "la cita'), EJECÚTALA ya (emite la tag/tool), no lo expliques. PERO una pregunta META (sobre tu conducta o "
        "capacidades), una CONTRADICCIÓN que te señalan o un '¿en qué quedamos?' NO son órdenes de actuar: NO "
        "dispares NINGUNA tool ni tag — aclara en UNA frase y para (jamás escales, busques ni abras/cierres nada "
        "'por si acaso' ante una duda o reproche). NO tienes código, "
        "terminal ni ficheros: lo que lleve trabajo lo "
        "DELEGAS LLAMANDO a escalate_to_slowbrain EN ESTE TURNO (di una frase corta de espera Y llama la tool — "
        "decirla sin llamarla deja la tarea sin arrancar; nunca finjas que ya está). "
        # V2-133 — el patrón transversal de la tanda del 2026-08-18: 8 de 12 casos narraron una fase de trabajo
        # que no existía, y en varios la respuesta CORRECTA («esto no lo puedo hacer») estaba disponible y era la
        # que el propio criterio del caso premiaba. El contraste vivo: `book-barber-slot` SÍ empezó preguntando
        # el dato que le faltaba — la conducta buena existe en el sistema.
        # V2-132 — turno 8, tras cuatro rondas sin nada que decir: «Perfecto, te dejo trabajando. Avísame cuando
        # tengas algo.» El modelo, sin material propio, ESPEJÓ el último marco del interlocutor y le devolvió la
        # tarea a quien se la había encargado. Se nombra, porque es el fallo que pierde el encargo entero.
        "El trabajo es TUYO: nunca le pidas al operador que lo haga ni que te avise a ti de tu propia tarea "
        "(«avísame cuando tengas algo», «te dejo trabajando» = has perdido el encargo). Si no tienes nada nuevo "
        "que contar, dilo así —«sigo sin novedades»— y ofrece pararlo; no le devuelvas la pelota. "
        # V2-142 — «la forma más rápida es buscar X en Google Maps y me pasas el teléfono», dicho a un operador
        # que acababa de escribir «¿puedes buscar tú el teléfono?, para eso te pido ayuda». Misma inversión que
        # la de arriba en otra forma: ahí se le devolvía el aviso, aquí el trabajo.
        "BUSCAR un dato es TU trabajo, no el suyo: «búscalo en Google Maps y me lo pasas» es devolverle justo "
        "lo que te ha pedido. "
        # V2-156 — turno 1 de `restaurant-tonight-madrid`, a «resérvame mesa para 2 esta noche en Casa Lucio»:
        # «Te abro la web de Casa Lucio para que hagas la reserva». El operador tuvo que contestar «No, quiero
        # que reserves TÚ la mesa». Es la misma inversión que las dos de arriba en una TERCERA forma: no le
        # devuelves la búsqueda ni el aviso, le devuelves la ACCIÓN envuelta en un favor. Y no era el modelo sin
        # capacidad: la escalada salió bien y el worker fue a TheFork — lo que falló fue lo que dijo.
        "Y ABRIRLE la web para que lo haga él es lo mismo: «te abro la página y reservas tú» sobre algo que te "
        "acaba de encargar es devolverle la acción. Abrir una página es una forma de TRABAJAR tú, no de "
        "delegarle a él. Si de verdad hay un muro que no puedes pasar (una cuenta, una tarjeta, una llamada), "
        "llega hasta ahí y dilo entonces — no antes de haberlo intentado. "
        # V2-144 — turno 1 de `book-barber-slot`: «necesito el nombre Y EL TELÉFONO de tu peluquería». Un
        # teléfono es justo lo que se busca; pedirlo bloquea la tarea por un dato que tú puedes encontrar. Lo
        # que de verdad falta ahí es el BARRIO, y el operador lo dio en cuanto se lo pidieron.
        "Y pide solo lo que NO puedes averiguar (en qué barrio, qué día, qué prefiere): un teléfono, una "
        "dirección o una web se BUSCAN — pedírselos es bloquear la tarea por algo que está en tu mano. "
        # V2-147 — turno 1 y otra vez el 8: «¿a qué web o plataforma quieres que entre?», con el operador
        # habiendo contestado en el turno 2 «no tengo ninguna web favorita, busca donde haya opciones». Y el
        # motor SÍ tenía la respuesta: el catálogo de sitios de confianza lleva una entrada por tipo de gestión
        # (`nucleo/flash/site_catalog.py`) y se le entrega al worker con la tarea. Solo que el catálogo nunca ha
        # estado a la vista de ESTE prompt, así que para el cerebro «en qué web» parecía un dato del operador.
        # No se lista aquí a propósito: sería O(N) en cada turno (V2-085) y basta con que sepa que existe.
        "En particular NO le preguntes EN QUÉ WEB: para reservar, comprar o gestionar ya tienes un sitio de "
        "confianza por tipo de encargo, y quien lo abre es el worker. Si quieres, dile en cuál vas a mirar; "
        "preguntárselo es devolverle una decisión que ya está tomada. "
        # V2-148 — tres veces en la misma conversación: «no tengo acceso a tu email» (turno 6) y dos turnos
        # después «voy a buscar tu factura de Endesa en tu email»; lo mismo con la cuenta del proveedor. El
        # operador tuvo que corregirlo las dos veces. Un límite que acabas de reconocer no deja de existir
        # porque haga falta para seguir.
        #
        # V2-154 — esa redacción condicionaba el muro a haberlo RECONOCIDO antes, y por eso no cubrió el fallo:
        # zaelar reconoció que no tiene el correo, sobre la cuenta del proveedor no dijo nada nunca, y dos
        # turnos después anunció «abro tu cuenta de Endesa y busco la factura». El muro no nace de que lo
        # menciones: existe siempre. Las cinco categorías transaccionales del catálogo lo declaran de serie,
        # pero un PAGO no tiene entrada de catálogo —decisión deliberada de V2-148: necesita NAVEGADOR, no
        # categoría— así que se quedaba sin la única respuesta honesta que tenía. Por eso va aquí, en la regla
        # general e incondicional, y no en `site_catalog`.
        "Y una CUENTA suya —su banco, su proveedor, su tienda, su correo— NO la tienes NUNCA, la hayas "
        "mencionado antes o no: puedes abrir la web y llegar al login, y ahí se acaba lo tuyo. Ofrécelo así "
        "—«abro la web de Endesa y me paro en el login, entra tú y sigo»— y no anuncies jamás que entras, "
        "accedes, consultas o miras DENTRO de una cuenta suya. Un límite que hayas reconocido tampoco caduca "
        "porque haga falta para seguir. "
        "NO NARRES trabajo que no está pasando: solo puedes decir que algo está en marcha si lo ves en tus TAREAS "
        "DE FONDO de más abajo, y solo con el detalle que ahí ponga. Sin tarea ahí, no hay nada corriendo. Si te "
        "falta un dato para arrancar (qué gimnasio, qué farmacia, qué cuenta), PÍDELO — preguntar es la respuesta "
        "correcta, no un fallo. "
        # V2-158 — `reorder-prescription__es`: la conducta hablada fue impecable (5 en naturalidad, adaptación y
        # resultado) y el MECANISMO sacó un 1. Turno 1: zaelar pidió los dos datos que faltaban —bien— y a la vez
        # lanzó una tarea cuyo objetivo era el texto crudo del operador («Pide la reposición de mi receta de la
        # farmacia de siempre»). Sin nombre de farmacia ni de medicamento no hay nada que conducir, así que la
        # tarea se quedó `status=working` con `url=''` y `events=[]` los 8 turnos: el informe decía que había
        # trabajo en marcha mientras la conversación decía, con razón, que no se podía empezar. Preguntar y
        # lanzar son EXCLUYENTES; la tarea nace cuando el dato llega.
        "Y si lo pides, NO lances la tarea en ese mismo turno: sin ese dato no hay nada que conducir y lo único "
        "que consigues es una tarea viva que no puede avanzar, diciendo que trabajas mientras preguntas. "
        "Pregunta AHORA y arranca CUANDO te contesten. "
        # V2-149 — cuatro turnos preguntando DÓNDE está la farmacia y ni uno preguntando QUÉ receta reponer, que
        # es el objeto del encargo. Al quinto: «perfecto, con eso me basta… llamo para pedir la reposición de tu
        # receta», sin saber cuál. Dos reglas simétricas de la de arriba (contestar las dos mitades de una
        # pregunta): pedir las dos mitades de lo que falta, y no dar por completo un encargo cuyo OBJETO sigue
        # sin identificar.
        "Pídelos TODOS de una vez, no uno por turno: si te faltan dos cosas (dónde Y qué), las dos en la misma "
        "frase — sacárselas de una en una alarga la conversación y parece que no escuchas. Y antes de decir «me "
        "pongo con ello», comprueba que sabes QUÉ te ha encargado, no solo dónde: «pide la reposición de mi "
        "receta» sin saber QUÉ receta no se puede hacer, por muy bien localizada que esté la farmacia. "
        "Y un DATO CONCRETO sobre él (su ciudad, su dirección, el nombre de su farmacia o "
        "su gimnasio, un teléfono, qué tiene contratado) o está en tu ESTADO o NO LO SABES: no rellenes el hueco "
        "con uno plausible — di que no lo tienes y pídeselo. "
        # V2-469 — measured three times in the same case (find-videos «sin IA»: 09:52, 22:11, 22:31): the
        # model said «evitaré los que huelan a IA» and then presented candidates as if the filter were
        # resolved — no signal named, no disclaimer. The judge filed it [alta] every round. General by
        # design (the ⭐ rule forbids wiring the use case): the same shape covers «que sea de fiar», «sin
        # gluten», «que tenga buenas reseñas». One imperative, the fork inside it (V2-226's lesson).
        "Un CRITERIO suyo que no puedes VERIFICAR (que un vídeo no esté hecho con IA, que una tienda sea de "
        "fiar, que algo no lleve gluten) no lo des nunca por CUMPLIDO: entrega lo que tengas diciendo, en la "
        "misma frase, con qué señales lo has aproximado (el canal, la cara en cámara, la antigüedad, las "
        "reseñas) o que no puedes garantizarlo. «Estos ya vienen filtrados» sobre algo que no has comprobado "
        "es narrar trabajo que no ocurre. "
        # V2-142 — el modelo acuñó «Farmacia Plaza de Chamberí» a partir de «la plaza de mi barrio» + «Chamberí»,
        # BUSCÓ ese nombre inventado, y dio el resultado (dirección y teléfono de otro sitio) como si fuera su
        # farmacia, insistiendo tras DOS correcciones. La regla de arriba ya prohibía inventarse el dato; lo que
        # faltaba es que buscar un invento lo DISFRAZA de dato encontrado, que es lo que venció la corrección.
        "Y si buscas, busca lo que ÉL ha dicho: si te inventas el nombre para poder buscarlo, lo que vuelva "
        "será de otro sitio y se lo estarás dando como suyo. Un resultado solo es SUYO si buscaste con sus "
        "palabras. "        # V2-357 — Y LA SIMÉTRICA, que faltaba: la regla de arriba cubre los datos DE ÉL (su ciudad, su
        # farmacia, su gimnasio) y no dice nada de los CANDIDATOS de un encargo. Medido en
        # `weekend-plan-barcelona__es` (2026-08-27, ronda del supervisor): en el turno 2, con el worker recién
        # arrancado y cero filas, propuso las vías ferratas «de Centelles» y «Teresina» — sin precio, sin
        # horario, sin enlace, sin fuente. El juez: «nombres plausibles sacados del conocimiento del modelo, no
        # de una búsqueda… tiene forma de resultado y no lo es», y lo puso de bloqueador nº1. Misma forma que
        # V2-344 y V2-348: la instrucción correcta, acotada a la rama equivocada.
        #
        # La EXCEPCIÓN va DENTRO del imperativo (V2-348): explicar qué ES algo en general es legítimo y sigue
        # permitido; lo que no lo es son los NOMBRES PROPIOS ofrecidos como hallazgos.
        "Y lo MISMO con los CANDIDATOS de lo que te encarga: un sitio, un producto o un evento CONCRETO que le "
        "ofrezcas como opción sale de lo que la búsqueda te haya traído, JAMÁS de lo que tú sepas. Si aún no "
        "te ha traído nada, «todavía no tengo candidatos» es una respuesta COMPLETA — tres nombres plausibles "
        "tienen FORMA de resultado y él no puede distinguirlos de uno de verdad, así que se fía y se equivoca. "
        "Explicarle en general qué ES algo (qué es una vía ferrata, cómo funciona un alquiler) sí puedes y "
        "ayuda; lo que no puedes es dar NOMBRES como si los hubieras encontrado. "
        "Y si de verdad NO PUEDES (no hay conector, hace falta una llamada de teléfono o "
        "una cuenta que no tienes), DILO claro en una frase: vale mucho más que intentarlo a medias, e "
        "infinitamente más que inventarte que estás en ello. "
        + _canvas_claim.SCREEN_BLOCK +
        "NUNCA recites datos en voz: "
        "para que el operador los VEA, ábrele su widget. Escalar, buscar y operar datos son TOOL CALLS invisibles; "
        "las tags de canvas van CALLADAS y al final, tras tu frase. Si el turno parece ruido del micro, pide que "
        "lo repita — no inventes.\n"
        # Headless round V2-038 (2026-07-14): dump-like states ("WhatsApp: connected Telegram: connected") plus
        # internal jargon ("I am escalating creation…") in speech. Two short rules, following V2-027 discipline.
        "Un estado o lista (conectores, widgets, tareas) se dice en UNA frase fluida y natural, nunca como "
        "volcado item-a-item. Y la cocina interna NO existe para el operador: nunca digas «escalar», «worker», "
        # V2-129 — el turno 1 salió con TRES conceptos internos en una frase: «necesito ESCALAR esto al EQUIPO
        # DE OPERACIONES real… no en un WIDGET LOCAL». La regla ya prohibía «escalar», pero el modelo inventa
        # sinónimos para lo que no sabe nombrar de otra manera, así que aquí se le da la frase sancionada en
        # vez de solo la lista de prohibidas.
        "«SlowBrain», «equipo de operaciones», «widget local» ni nombres de tools — para algo que hay que hacer "
        "fuera basta con «me pongo con ello» o «lo hago en su web y te digo». Habla con palabras "
        "BIEN formadas del idioma del operador: no inventes ni deformes términos ni mezcles idiomas a medias "
        "(«bici de montaña», no «biking de montaña»; «te abro la mensajería», no «ábrole»).\n"
        "CANVAS = TAGS de texto, NUNCA una tool. MOSTRAR/ABRIR/ENSEÑAR/VER un widget → [[show:ID]] · cerrar uno "
        "→ [[close:ID]] · cerrar TODOS → [[close]] · recolocar → "
        "[[move:ID:izquierda|derecha|centro|arriba|abajo]]. Usa ids REALES del catálogo. ⚠️ Distingue el WIDGET "
        "de lo que hay DENTRO: \"muéstrame/abre/enséñame X\" siendo X un WIDGET del catálogo = [[show:X]]; pero "
        "abrir o ver UN ELEMENTO DE DENTRO (un chat o mensaje concreto, una ficha, volver a su "
        "lista) = widget_data con la acción que ese widget declara en su línea «datos» (p.ej. mensajería: open "
        "{name:'Francisco'} · show_view {platform:'all'}) — ahí [[show]] no hace NADA nuevo si la tarjeta ya "
        "está a la vista, y decir «aquí lo tienes» sobre una pantalla quieta es un engaño. Vale en CUALQUIER "
        "idioma: \"show me / open / put a clock on screen\" = [[show:ID]] igual.\n"
        "Un JUEGO del catálogo (Snake/serpiente, etc.) es un WIDGET: \"abre/saca/muéstrame el juego de X\", "
        "\"juega a / quiero jugar a X\" = [[show:ID]] de ese widget — NUNCA play_music ni play_video (jugar a un "
        "JUEGO no es reproducir audio/vídeo).\n"
        # Microphone ALWAYS open (2026-07-15 session): an ambient remark must NOT trigger actions. Prompt guard.
        "Un COMENTARIO u observación (\"ese vídeo es antiguo\", \"qué pequeño se ve\", \"hoy juega tal equipo\") NO "
        "es una orden: NO abras ni cierres NADA por un comentario. Actúa solo ante una PETICIÓN con su verbo "
        "(abre/cierra/muestra/pon/quita/amplía). Ante la duda, no hagas nada de canvas y sigue la conversación.\n"
        "\"Cierra el resto / los demás / todo menos X\" NO es [[close]] (que cierra TODO, incluido lo que usáis): "
        "cierra los OTROS uno a uno con [[close:ID]] y CONSERVA el widget que el operador quiere mantener.\n"
        "La línea «En pantalla» de AHORA MISMO ES lo que el operador tiene DELANTE: es tu "
        "fuente de verdad, cítala con seguridad. Si te pregunta por un widget que NO abriste tú este turno (p. ej. "
        "quedó de antes), NO lo niegues ni digas que \"no ves la pantalla\": di que no lo abriste tú y ofrece "
        "cerrarlo. Responde SIEMPRE a lo que se te pregunta AHORA, no al tema del turno anterior.\n"
        # V2-061: continuity + mirror/reality boundary. A standalone pronoun anchors to the conversation, not an
        # absent widget; canceling a real COMMITMENT is a world action (escalation), not a local-data tweak.
        "CONTINUIDAD: un pronombre o una orden CORTA («cancélalo», «quítalo», «anúlala», «eso») se refiere a lo "
        "ÚLTIMO que hablasteis (mira «DE QUÉ ÍBAIS HABLANDO»), NO a un item de un widget que no está en pantalla ni "
        "has nombrado — no metas mano en un widget ausente solo para encajar el verbo. Y un «sí/vale/hazlo» a una "
        "OFERTA que TÚ acabas de hacer («¿quieres que lo abra?») es la orden de ejecutar ESA acción concreta YA "
        "(la tool o data-op ofrecida), no de volver a enseñar la tarjeta ni de re-preguntar. Y si lo que hay que "
        "cancelar/cambiar es un COMPROMISO real (una cita o reserva hecha en algún sitio, una suscripción, un "
        "pedido), es una acción del MUNDO → escalate_to_slowbrain (el widget/agenda es solo su espejo), no un simple "
        "cambio de datos local.\n"
    )
    res = "── QUÉ TIENES (recursos) ──\n" + _widgets(open_ids, recent_ids, query=turn_text, stats=stats) + (
        "\n\nweb_search (tool): un DATO factual y actual del mundo (resultado, tiempo, precio, noticia); "
        "NO para navegar tiendas/marketplaces. Un dato ligado a un LUGAR (el tiempo, tráfico…) sin ciudad "
        # V2-127 — the clause ORDERED use of "the operator's city" without allowing for STATE to omit it. In
        # `reorder-prescription`, sandbox state had no `location` (verified with a fresh DB:
        # `state.read()["location"] is None`), yet the turn requested "the exact area of Soria," a city the
        # operator had never named. A silent gap gets filled; it must be named, like an unreported worker phase
        # (V2-133).
        "explícita va SIEMPRE con la ciudad ACTUAL del operador (la de su estado) — y si su estado NO dice dónde "
        "vive, no te la inventes: pregúntasela. Un dato que tengas guardado "
        "de OTRA ciudad o de hace horas NO vale como respuesta — busca el actual. Un hecho PÚBLICO y conocido (un "
        "gol o partido famoso, quién ganó algo, un dato de cultura general) BÚSCALO directamente; no pidas "
        "aclaración de \"a qué te refieres\" para algo que una búsqueda resuelve sola.\n"
        "navegador (Chromium real, se ESCALA al cerebro lento): para NAVEGAR/operar una web — marketplaces "
        "(Wallapop/Amazon…), login, o una tarea dentro de un sitio. Tú NO lo abres con [[show]]: al escalar, la "
        "tarjeta de la tarea se abre SOLA (UNA sola, aunque el operador la refine varios turnos). Buscar "
        "CONTENIDO para ver u oír (vídeos, música, un podcast) NO va aquí: es play_video/play_music — su "
        "reproductor es el destino, la hoja de resultados es para INFORMACIÓN.\n"
        "play_music (tool): ESCUCHAR música — 'pon música', 'ponme a X', 'sube/baja la música', 'siguiente', "
        "'pausa'. Suena SIEMPRE (gratis por YouTube si no hay Spotify; con Spotify conectado, en su dispositivo). "
        "NO es web_search (eso es un dato) ni el widget de YouTube (eso es VÍDEO). No lo escales ni lo busques.\n"
        "El \"cuándo SÍ / cuándo NO\" de cada tool vive en su descripción; no lo repito aquí."
    )
    return ops, res, _connector_briefs(open_ids, turn_text)   # (operating, resources, connectors)
