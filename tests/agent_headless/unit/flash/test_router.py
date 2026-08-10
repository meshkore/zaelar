"""Tests de nucleo/flash/router.py (V2-004 · T61; worker tools V2-038) — routing por function-calling."""
from nucleo.flash import router
from nucleo.flash.router import ANSWER, CHAT, ESCALATE, INJECT, MUSIC, STOP, STYLE, VIDEO


def test_tools_are_openai_functions():
    names = {t["function"]["name"] for t in router.tools()}
    assert names == {"escalate_to_slowbrain", "set_style_directive", "show_widget", "show_panel", "fullscreen_widget",
                     "manage_widget_alias", "widget_data", "delete_widget",
                     "confirm_widget_delete", "authenticate_web", "login_done", "web_search", "recall",
                     "reveal_secret", "play_music", "play_video", "reply_message", "connect_cluster",
                     "cluster_send", "set_cluster_objective", "send_to_worker", "stop_worker", "answer_worker"}
    for t in router.tools():
        assert t["type"] == "function"
        assert "parameters" in t["function"]


def test_worker_tools_are_situational():
    # V2-038: sin workers vivos NO se ofrecen send/stop; answer_worker solo con un ask pendiente.
    normal = {t["function"]["name"] for t in router.tools(router.tool_context())}
    assert "send_to_worker" not in normal and "stop_worker" not in normal and "answer_worker" not in normal
    with_w = {t["function"]["name"] for t in router.tools(router.tool_context(has_workers=True))}
    assert {"send_to_worker", "stop_worker"} <= with_w and "answer_worker" not in with_w
    with_ask = {t["function"]["name"] for t in router.tools(router.tool_context(has_workers=True, ask_pending=True))}
    assert "answer_worker" in with_ask


def test_cluster_tools_are_always_offered():
    """V2-086 — INVIERTE el gate de V2-064. Aquel exigía tener el widget `cluster-registro` abierto, lo que hacía
    la capacidad INDESCUBRIBLE: para conectar un cluster NUEVO había que saber de antemano que primero tocaba
    abrir un widget concreto. Comprobado en vivo el 2026-08-01 (turno 766): el operador pegó la invitación
    oficial de MeshKore y `connect_cluster` ni siquiera estaba en el set ofrecido — el modelo no podía actuar.
    Ese widget ya no existe (la red es superficie NATIVA) y la protección real contra el disparo espurio es la
    CONFIRMACIÓN Sí/No determinista, no el gate."""
    normal = {t["function"]["name"] for t in router.tools(router.tool_context())}
    assert "connect_cluster" in normal
    assert "set_cluster_objective" in normal


def test_cluster_send_needs_a_live_cluster():
    """`cluster_send` sí es situacional, pero por ESTADO REAL (hay cluster conectado), no por tener una UI
    abierta: sin nadie al otro lado no hay a quién escribir."""
    off = {t["function"]["name"] for t in router.tools(router.tool_context())}
    assert "cluster_send" not in off
    on = {t["function"]["name"] for t in router.tools(router.tool_context(cluster_connected=True))}
    assert "cluster_send" in on


def test_connect_cluster_accepts_a_public_tokenless_cluster():
    """V2-086: MeshKore tiene clusters PÚBLICOS sin token (Commons). El esquema exigía `token`, así que ese caso
    era INEXPRESABLE — el modelo o se inventaba un token o no llamaba. Ahora solo el cluster_id es obligatorio."""
    fn = next(t["function"] for t in router.TOOLS if t["function"]["name"] == "connect_cluster")
    assert fn["parameters"]["required"] == ["cluster_id"]
    assert "vis" in fn["parameters"]["properties"]


def test_show_panel_routes_the_clusters_tab():
    """La RED es la 4ª pestaña nativa del ChatWall (V2-086) — se abre por show_panel, como Procesos/Crons."""
    assert router._canon_panel("clusters") == "clusters"
    for word in ("cluster", "meshkore", "la red", "la malla", "conexiones", "peers"):
        assert router._canon_panel(word) == "clusters", word
    # …y no se ha llevado por delante el ruteo de las otras.
    assert router._canon_panel("crons") == "crons"
    assert router._canon_panel("chat") == "chat"
    assert router._canon_panel("workers") == "procesos"


def test_capability_tools_are_situational():
    """V2-085: tres gates NUEVOS por CAPACIDAD REAL — sin conector de mensajería no hay a quién responder, sin
    bóveda no hay secreto que revelar, sin widget `youtube` play_video no tiene dónde cargar el vídeo. Ofrecerlas
    en ese estado solo invita al modelo a prometer algo imposible."""
    on = {t["function"]["name"] for t in router.tools(router.tool_context())}
    assert {"reply_message", "reveal_secret", "play_video"} <= on          # default fail-OPEN
    off = {t["function"]["name"] for t in router.tools(
        router.tool_context(messaging_on=False, has_vault=False, has_video_widget=False))}
    assert not ({"reply_message", "reveal_secret", "play_video"} & off)
    # …y podar por capacidad no se lleva por delante nada más.
    assert on - off == {"reply_message", "reveal_secret", "play_video"}


def test_every_tool_belongs_to_a_family():
    """La familia es la unidad con la que se razona el presupuesto de tools de un turno. Una tool nueva sin
    familia caería en 'core' silenciosamente — este test obliga a clasificarla al añadirla."""
    classified = {n for names in router.FAMILIES.values() for n in names}
    catalog = {t["function"]["name"] for t in router.TOOLS}
    assert catalog - classified == set(), f"tools sin familia: {sorted(catalog - classified)}"
    assert classified - catalog == set(), f"familias con tools inexistentes: {sorted(classified - catalog)}"


def test_tools_report_is_observable():
    offered = router.tools(router.tool_context())
    rep = router.tools_report(offered)
    assert rep["n_tools_offered"] == len(offered) and rep["n_tools_total"] == len(router.TOOLS)
    assert rep["sz_tools"] > 0
    assert sum(rep["tool_families"].values()) == len(offered)
    # Lo PODADO también se registra: sin eso no se puede auditar por qué un turno no tuvo una tool.
    # (V2-086: `connect_cluster` dejó de estar aquí a propósito — ya no se gatea.)
    assert "cluster_send" in rep["tools_omitted"] and "send_to_worker" in rep["tools_omitted"]
    assert "connect_cluster" not in rep["tools_omitted"]


def test_tool_catalog_is_constant_sized(monkeypatch):
    """El catálogo de tools es O(1): NO crece con el de widgets (ese es el que se acota en widgets/selection.py).
    Si algún día una tool empieza a enumerar widgets en su descripción, este test lo caza."""
    import json as _json
    from widgets import runtime as _rt
    base = len(_json.dumps(router.tools(router.tool_context()), ensure_ascii=False))
    monkeypatch.setattr(_rt, "_signature", lambda: ("synthetic", 5000))
    monkeypatch.setitem(_rt._cache, "sig", ("synthetic", 5000))
    monkeypatch.setitem(_rt._cache, "list", [{"id": f"w{i}", "title": f"W{i}"} for i in range(5000)])
    grown = len(_json.dumps(router.tools(router.tool_context()), ensure_ascii=False))
    assert grown == base


# Techo del catálogo (2026-08-02). O(1) no basta: la constante puede crecer sola, y ya lo hizo — llegó a 31.647
# chars (~7,9k tokens EN CADA TURNO, incluido «hola»), con el 70% en prosa. Tras compactarlo son 18.926. La norma
# del operador es «las tools, de menos a más»: un modelo de lenguaje ya sabe qué es un reproductor de música, así
# que la descripción solo lleva qué hace + las FRONTERAS contra NUESTRAS otras tools. Este techo obliga a que
# añadir una tool nueva pase por recortar, no por engordar el turno de todos. Si hay que subirlo, que sea una
# decisión con su medición al lado (`tests/agent_headless/e2e/prompt_cost/bench_fast_model.py`, nodo 2.13).
MAX_CATALOG_CHARS = 21_000


# ── "muéstrame una foto de X" tiene que escalar, no narrar (incidente real 2026-08-03) ───────────────────────
# El cerebro pedía a web_search una foto que web_search no puede dar (solo texto) y acababa DESCRIBIENDO la
# imagen de palabra en vez de mostrarla — 6 turnos de "no se ve nada"/disculpas antes de rendirse. Las tools no
# tienen un parámetro para esto (no hay «pedir imagen»): la frontera vive en la DESCRIPCIÓN, así que el test es
# textual — cachea la regresión si alguien recorta esta frase sin darse cuenta de por qué está.
def _desc(name: str) -> str:
    return next(t["function"]["description"] for t in router.TOOLS if t["function"]["name"] == name)


def test_web_search_description_excludes_showing_a_real_photo():
    d = _desc("web_search").lower()
    assert "foto" in d or "imagen" in d
    assert "texto" in d           # deja claro que solo trae texto, nunca la imagen en sí


def test_escalate_description_covers_fetching_a_real_photo():
    d = _desc("escalate_to_slowbrain").lower()
    assert "foto" in d or "imagen" in d


def test_tool_catalog_stays_compact():
    import json as _json
    size = len(_json.dumps(router.TOOLS, ensure_ascii=False))
    assert size <= MAX_CATALOG_CHARS, (
        f"el catálogo de tools ha crecido a {size} chars (techo {MAX_CATALOG_CHARS}). Compacta descripciones "
        f"antes de subir el techo: se paga en CADA turno de voz.")
    # Ninguna tool suelta debe acaparar el catálogo: la que más pesa es la de escalada y aun así cabe holgada.
    worst = max(router.TOOLS, key=lambda t: len(_json.dumps(t, ensure_ascii=False)))
    assert len(_json.dumps(worst, ensure_ascii=False)) <= 2_000, worst["function"]["name"]


def test_decide_worker_tools():
    assert router.decide("send_to_worker", {"which": "la moto", "message": "verde"}).kind == INJECT
    assert router.decide("stop_worker", {"which": "el widget"}).kind == STOP
    assert router.decide("answer_worker", {"answer": "enduro"}).kind == ANSWER


def test_stop_wins_priority():
    # STOP manda sobre escalate si el modelo llama a ambos en un turno.
    calls = [("escalate_to_slowbrain", {"request": "x"}), ("stop_worker", {"which": "todo"})]
    assert router.classify(calls).kind == STOP


def test_decide_play_music():
    # V2-041: play_music → MUSIC con query+action normalizados (action def 'play').
    d = router.decide("play_music", {"query": "Frank Sinatra", "action": "PLAY"})
    assert d.kind == MUSIC and d.payload == {"query": "Frank Sinatra", "action": "play"}
    d2 = router.decide("play_music", {})
    assert d2.kind == MUSIC and d2.payload == {"query": "", "action": "play"}


def test_decide_play_video():
    # V2-045: play_video → VIDEO con query (VER en el widget youtube, ≠ play_music audio).
    d = router.decide("play_video", {"query": "el gol de la mano de Dios"})
    assert d.kind == VIDEO and d.payload == {"query": "el gol de la mano de Dios"}
    assert router.decide("play_video", {}).kind == VIDEO


def test_music_priority_below_worker_ops():
    # STOP/ESCALATE mandan sobre MUSIC; MUSIC manda sobre SEARCH/STYLE/CHAT.
    assert router.classify([("play_music", {}), ("stop_worker", {"which": "x"})]).kind == STOP
    assert router.classify([("play_music", {}), ("web_search", {"query": "x"})]).kind == MUSIC


def test_looks_like_stop_work():
    for yes in ("para eso", "cancela el widget", "deja de buscar", "para todo", "detén el proceso",
                "para la búsqueda", "para de crear el widget", "cancela la tarea del navegador"):
        assert router.looks_like_stop_work(yes), yes
    for no in ("para", "silencio", "qué tal", "ponme una cita para la cena"):
        # 'para' a secas / sin referencia a trabajo → NO (eso es hard_interrupt / otra cosa)
        assert not router.looks_like_stop_work(no), no


def test_stop_work_ignores_ambient_speech():
    """Regresión del falso positivo de la demo 2026-07-14: la charla AMBIENTE (micro abierto, ventana de
    atención viva) con 'para' PREPOSICIONAL + 'creando' mató el worker del widget. Una parrafada explicativa
    NUNCA es una orden de parada; un stop real es corto e imperativo."""
    demo = ("La memoria real que él tiene está aquí. Y entonces estás viendo ahora mismo qué puntos de la "
            "memoria está tocando. Como estuvieron en el cefalograma. Sí, sí, sí. Qué buenísimo. Entonces "
            "maneja su estado. Muy buenísimo. Maneja el corto plazo. Y luego esto es lo que a largo plazo. "
            "Ahora ha reiniciado después de un cambio. Buenísimo. Y entonces aquí va creando su... Esto se va "
            "llenando, se va llenando. Está creando su memoria vectorial, que es lo que necesita para poder "
            "acceder a esa velocidad, porque esto puede crecer de forma gigante.")
    assert not router.looks_like_stop_work(demo)
    # 'para' preposicional (para que / para poder / para acceder) → nunca es un mandato de parada
    for no in ("lo necesita para poder crear la búsqueda", "es para que el proceso funcione",
               "sirve para buscar cosas en el navegador"):
        assert not router.looks_like_stop_work(no), no
    # una parrafada CON verbos de mandato dentro tampoco dispara (cap de longitud: con duda, no se mata)
    largo = ("bueno pues entonces yo creo que igual habría que cancelar el proceso pero primero déjame "
             "explicarte cómo funciona todo esto del navegador y la búsqueda que está haciendo por detrás")
    assert not router.looks_like_stop_work(largo)


def test_stop_work_ignores_short_prepositional_para():
    """Regresión del test post-P1/P2 (2026-07-14): 'para' PREPOSICIONAL en frase CORTA (que el cap no salva) —
    'hazme un widget PARA el tiempo' auto-mataba el worker recién nacido. Un turno que EMPIEZA pidiendo algo, o
    'para <sintagma nominal>' / 'para' a media frase, NO es una orden de parada."""
    for no in ("quiero que crees un widget para el tiempo", "necesito un widget para la agenda",
               "hazme una búsqueda para el finde", "eso es para la búsqueda de piso",
               "hazme un widget para el tiempo", "prepara un informe para mañana",
               "abre la agenda para ver mis citas", "muéstrame el widget de fútbol"):
        assert not router.looks_like_stop_work(no), no
    # las órdenes REALES de parada (incl. 'para' imperativo al inicio con complemento de trabajo) siguen:
    for yes in ("para la búsqueda", "para esa tarea", "para ya con eso", "aborta la búsqueda",
                "deja de crear el widget"):
        assert router.looks_like_stop_work(yes), yes


def test_looks_like_close_guard():
    # V2-045: 'cierra el widget de X' = CLOSE (reversible), no delete. Guard cerrar≠borrar (invariante V2-017).
    for yes in ("cierra el widget de youtube", "ciérrame el reloj", "cierra eso", "close the clock", "oculta la agenda"):
        assert router.looks_like_close(yes), yes
    # con verbo de BORRAR presente → NO es close (es delete de verdad); ni sin verbo de cerrar.
    for no in ("borra el widget del reloj", "elimina la agenda", "borra y cierra todo", "ponme música",
               "abre la agenda"):
        assert not router.looks_like_close(no), no
    # sesión absurda 2026-07-19: cerrar CON queja larga sigue siendo un CLOSE (no escala a código). El guard de
    # texto lo reconoce; la longitud la maneja el backstop del provider (nombre resuelto contra un widget abierto).
    assert router.looks_like_close("cierra el widget de música. has puesto un videoclip de la canción que te he pedido")
    assert not router.looks_like_create_widget("cierra el widget de música. has puesto un videoclip")
    # NEGACIÓN: "no cierres / no lo cierres" NO es un close (no cerrar al revés).
    for neg in ("no cierres el widget de música", "no lo cierres todavía", "don't close the clock"):
        assert not router.looks_like_close(neg), neg


def test_looks_like_rule_removal_guard():
    # V2-046 A1: la MISMA tool añade o retira una user rule; el sentido lo decide este guard sobre el turno.
    for yes in ("olvida esa regla", "olvídate de lo de ser breve", "quita la regla de responder sí o no",
                "ya no hace falta que seas tan directo", "borra esa norma"):
        assert router.looks_like_rule_removal(yes), yes
    for no in ("sé más breve a partir de ahora", "trátame de usted", "responde solo sí o no",
               "cuando te pida una acción hazla sin responder"):
        assert not router.looks_like_rule_removal(no), no


def test_is_messaging_service_guard():
    # V2-045: WhatsApp/Telegram se vinculan por QR en el widget mensajeria, no por navegador.
    assert router.is_messaging_service("", "conéctame a WhatsApp")
    assert router.is_messaging_service("web.whatsapp.com", "")
    assert router.is_messaging_service("", "abre mi Telegram")
    assert not router.is_messaging_service("wallapop.com", "conéctame a Wallapop")
    assert not router.is_messaging_service("", "conéctame a Spotify")


def test_web_auth_tools_are_side_effects_not_routing():
    # authenticate_web / login_done son acciones de efecto lateral (las despacha el provider), no cambian el
    # routing del turno → decide() las trata como charla (el turno sigue siendo chat: zaelar habla).
    assert router.decide("authenticate_web", {"site": "wallapop.com"}).kind == CHAT
    assert router.decide("login_done", {}).kind == CHAT
    assert router.decide("connect_cluster", {"cluster_id": "c_x", "token": "ck_y"}).kind == CHAT


def test_looks_like_login_request_guard():
    # V2-022, endurecido tras bug 2026-07-23: SOLO la forma dirigida a zaelar en 1a persona ("conéctame"/
    # "conectar mi cuenta") es login puro. `conect(?!ad|or)` casaba CUALQUIER conjugación de "conectar" —
    # una PREGUNTA sobre capacidad y una narración en 3a persona abrían un login de navegador que nadie pidió
    # (a wallapop.com por el fallback de sitio desconocido en `nucleo.py::_start_web_auth`).
    for yes in ("Conéctame a mi cuenta de Wallapop.", "Conectame a mi cuenta de Wallapop",
                "Inicia sesión en mi Gmail", "Vincula mi LinkedIn", "Conecta mi cuenta de Twitter",
                "Quiero conectarme a mi cuenta de Netflix", "Connect me to my Spotify account"):
        assert router.looks_like_login_request(yes), yes
    for no in ("Vale, ¿tienes todavía capacidad para conectarte al cluster privado de MeshCore que "
               "teníamos configurado?",
               "Teníamos un clúster para hablar con un agente que se llamaba Zalo, que también se "
               "conectaba ahí y podíais charlar tranquilamente.",
               "Dime si WhatsApp está conectado", "¿Están los conectores conectados?",
               "Are we still connected to the cluster?"):
        assert not router.looks_like_login_request(no), no


def test_decide_escalate():
    d = router.decide("escalate_to_slowbrain", {"request": "arregla el bug"})
    assert d.kind == ESCALATE
    assert d.payload["request"] == "arregla el bug"


def test_decide_style():
    d = router.decide("set_style_directive", {"directive": "sé directo"})
    assert d.kind == STYLE
    assert d.payload["directive"] == "sé directo"


def test_decide_unknown_is_chat():
    assert router.decide("no_existe", {}).kind == CHAT
    assert router.decide("", None).kind == CHAT


def test_classify_none_is_chat():
    assert router.classify(None).kind == CHAT
    assert router.classify([]).kind == CHAT


def test_classify_escalate_wins_over_style():
    calls = [("set_style_directive", {"directive": "breve"}),
             ("escalate_to_slowbrain", {"request": "recuerda X"})]
    d = router.classify(calls)
    assert d.kind == ESCALATE
    assert d.payload["request"] == "recuerda X"


def test_is_escalation():
    assert router.is_escalation("escalate_to_slowbrain")
    assert not router.is_escalation("set_style_directive")


def test_show_widget_tool(monkeypatch=None):
    # 2026-07-17: MOSTRAR un widget es tool de 1ª clase (fix del secuestro 'jugar'→play_music). Gated por has_widgets;
    # decide() lo mapea a SHOW con el widget_id.
    normal = {t["function"]["name"] for t in router.tools(router.tool_context())}
    assert "show_widget" in normal
    nowid = {t["function"]["name"] for t in router.tools(router.tool_context(has_catalog=False))}
    assert "show_widget" not in nowid
    d = router.decide("show_widget", {"widget_id": "juego-serpiente-snake"})
    assert d.kind == router.SHOW and d.payload.get("widget_id") == "juego-serpiente-snake"


def test_looks_like_create_widget_guard():
    # 2026-07-17: CREAR un widget se ESCALA (generador), no se muestra. Guard de show_widget (regresión de la tool).
    for yes in ("créame un widget de conversor de divisas", "hazme un widget que convierta divisas",
                "quiero un widget nuevo para convertir euros", "hazme un widget contador de días",
                "constrúyeme un widget del tiempo", "genérame un widget nuevo"):
        assert router.looks_like_create_widget(yes), yes
    # MOSTRAR un widget existente / jugar a un juego NO es crear (no debe redirigir a escalate):
    for no in ("abre el juego de la serpiente", "juega al snake", "muéstrame la serpiente",
               "abre el reloj", "quiero jugar a la serpiente", "muéstrame el widget de fútbol"):
        assert not router.looks_like_create_widget(no), no


def test_stop_work_bulk_and_false_positive():
    # 2026-07-17 (ronda 3): stop MASIVO ("para todas las tareas"/"para todos los workers") no se captaba y el stop
    # fallaba en silencio; y "para todo el mundo es difícil" era un FALSO POSITIVO (mataba workers). Ambos fijados.
    for yes in ("para todas las tareas", "para todos los workers", "para todos los procesos",
                "cancela todas las tareas", "para todo"):
        assert router.looks_like_stop_work(yes), yes
    for no in ("para toda la comida", "para todo el mundo es difícil", "para la cena de mañana"):
        assert not router.looks_like_stop_work(no), no


def test_show_panel_decision_and_canon():
    # V2-079: la tool show_panel abre el panel nativo lateral (chat/procesos/crons) por voz.
    d = router.decide("show_panel", {"panel": "procesos"})
    assert d.kind == router.PANEL and d.payload.get("panel") == "procesos"
    # _canon_panel normaliza sinónimos que el modelo pueda soltar en el ARGUMENTO (no en la petición):
    assert router._canon_panel("crons") == "crons"
    assert router._canon_panel("chat") == "chat"
    assert router._canon_panel("workers") == "procesos"
    assert router._canon_panel("brain workers") == "procesos"
    assert router._canon_panel("tareas programadas") == "crons"
    assert router._canon_panel("muro de texto") == "chat"
    assert router._canon_panel("") == "procesos"           # default: el caso más pedido
    # show_panel está en el catálogo de tools ofrecido al modelo
    assert any(t["function"]["name"] == "show_panel" for t in router.TOOLS)


def test_manage_widget_alias_decision():
    # V2-082: añadir/quitar un alias de un widget por voz.
    d = router.decide("manage_widget_alias", {"widget_id": "mensajeria", "alias": "WhatsApp"})
    assert d.kind == router.ALIAS and d.payload["widget_id"] == "mensajeria"
    assert d.payload["alias"] == "WhatsApp" and d.payload["op"] == "add"     # add por defecto
    d = router.decide("manage_widget_alias", {"widget_id": "reloj", "alias": "x", "op": "remove"})
    assert d.payload["op"] == "remove"
    d = router.decide("manage_widget_alias", {"widget_id": "reloj", "alias": "x", "op": "quitar"})
    assert d.payload["op"] == "remove"
    # situacional: solo con widgets
    assert "manage_widget_alias" in {t["function"]["name"] for t in router.tools(router.tool_context())}


# ── EL PANEL NATIVO TAMBIÉN SE CIERRA POR VOZ (2026-08-10) ────────────────────────────────────────────────────
# Fallo real, y de los que rompen la confianza. En la sesión del operador:
#   «Vale, cierra también el chat.»          → «Vale.»
#   «Cierra también el chatbot.»             → «Vale, cerrado.»
#   «Quiero que cierres el chat de sistema.» → «Aquí lo tienes.»
#   «Cierra la ventana de chat.»             → (nada)
#   «Vale, lo hago yo apretando el botón de la x. Ya está.»
# El chat NO es un widget (es UI nativa), así que [[close]] no lo toca — y `show_panel` solo sabía ABRIR. O sea que
# la capacidad no existía y el turno acababa en un «cerrado» que era falso. Peor que no poder es decir que sí.
def test_the_panel_tool_can_close_not_only_open():
    d = router.decide("show_panel", {"panel": "chat", "action": "close"})
    assert d.payload["action"] == "close" and d.payload["panel"] == "chat"


def test_opening_stays_the_default_so_a_missing_argument_never_closes_it():
    """Un modelo que se deja el argumento no puede acabar cerrándole el panel al operador."""
    assert router.decide("show_panel", {"panel": "procesos"}).payload["action"] == "open"
    assert router.decide("show_panel", {"panel": "chat", "action": ""}).payload["action"] == "open"


def test_the_close_argument_tolerates_what_a_model_actually_writes():
    """El argumento lo escribe un modelo en el idioma del turno: 'close', 'cerrar', 'quita', 'oculta'."""
    for v in ("close", "cerrar", "cierra el chat", "quita", "ocultar", "hide"):
        assert router.decide("show_panel", {"panel": "chat", "action": v}).payload["action"] == "close", v


def test_the_tool_says_out_loud_that_the_chat_is_not_a_widget():
    """La confusión de fondo: el operador dice «cierra el chat» y el modelo alcanza [[close]], que solo cierra
    tarjetas del canvas. La descripción tiene que desambiguarlo, o vuelve a fallar en silencio."""
    desc = _desc("show_panel")
    assert "close" in desc
    low = desc.lower()
    assert "no es un widget" in low or "nunca show_widget" in low
