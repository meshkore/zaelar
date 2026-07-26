"""Tests de nucleo/flash/router.py (V2-004 · T61; worker tools V2-038) — routing por function-calling."""
from nucleo.flash import router
from nucleo.flash.router import ANSWER, CHAT, ESCALATE, INJECT, MUSIC, STOP, STYLE, VIDEO


def test_tools_are_openai_functions():
    names = {t["function"]["name"] for t in router.tools()}
    assert names == {"escalate_to_slowbrain", "set_style_directive", "show_widget", "fullscreen_widget",
                     "widget_data", "delete_widget",
                     "confirm_widget_delete", "authenticate_web", "login_done", "web_search", "recall",
                     "reveal_secret", "play_music", "play_video", "reply_message", "connect_cluster",
                     "set_cluster_objective", "send_to_worker", "stop_worker", "answer_worker"}
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


def test_connect_cluster_is_situational():
    # V2-064: connect_cluster solo se ofrece con el widget cluster-registro abierto delante del operador — no en
    # cada turno normal (sería ruido y superficie de ataque innecesaria si nunca se usa).
    normal = {t["function"]["name"] for t in router.tools(router.tool_context())}
    assert "connect_cluster" not in normal
    with_widget = {t["function"]["name"] for t in router.tools(router.tool_context(cluster_widget_open=True))}
    assert "connect_cluster" in with_widget


def test_set_cluster_objective_is_situational():
    # T-02 (auditoría 2026-07-26): mismo gate que connect_cluster — solo con el widget cluster-registro delante.
    normal = {t["function"]["name"] for t in router.tools(router.tool_context())}
    assert "set_cluster_objective" not in normal
    with_widget = {t["function"]["name"] for t in router.tools(router.tool_context(cluster_widget_open=True))}
    assert "set_cluster_objective" in with_widget


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
