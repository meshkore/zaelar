"""Tests for nucleo/flash/router.py (V2-004 · T61; worker tools V2-038) — function-calling routing."""
from nucleo.flash import router
from nucleo.flash.router import ANSWER, CHAT, ESCALATE, INJECT, MUSIC, STOP, STYLE, VIDEO


def test_tools_are_openai_functions():
    names = {t["function"]["name"] for t in router.tools()}
    assert names == {"escalate_to_slowbrain", "set_style_directive", "show_widget", "show_panel", "fullscreen_widget", "restore_widget",
                     "manage_widget_alias", "widget_data", "delete_widget",
                     "confirm_widget_delete", "authenticate_web", "login_done", "web_search", "recall",
                     "reveal_secret", "play_music", "play_video", "show_images", "reply_message", "connect_cluster",
                     "cluster_send", "set_cluster_objective", "send_to_worker", "stop_worker", "answer_worker"}
    for t in router.tools():
        assert t["type"] == "function"
        assert "parameters" in t["function"]


def test_worker_tools_are_situational():
    # V2-038: with no live workers, send/stop are NOT offered; answer_worker only appears with a pending ask.
    normal = {t["function"]["name"] for t in router.tools(router.tool_context())}
    assert "send_to_worker" not in normal and "stop_worker" not in normal and "answer_worker" not in normal
    with_w = {t["function"]["name"] for t in router.tools(router.tool_context(has_workers=True))}
    assert {"send_to_worker", "stop_worker"} <= with_w and "answer_worker" not in with_w
    with_ask = {t["function"]["name"] for t in router.tools(router.tool_context(has_workers=True, ask_pending=True))}
    assert "answer_worker" in with_ask


def test_cluster_tools_are_always_offered():
    """V2-086 — REVERSES the V2-064 gate. That one required the `cluster-registro` widget to be open, making
    the capability UNDISCOVERABLE: to connect a NEW cluster, you had to know in advance that you first had to
    open a specific widget. Verified live on 2026-08-01 (turn 766): the operator pasted the official MeshKore
    invitation and `connect_cluster` was not even in the offered set — the model could not act.
    That widget no longer exists (the network is a NATIVE surface), and the real protection against spurious
    triggering is deterministic Yes/No CONFIRMATION, not the gate."""
    normal = {t["function"]["name"] for t in router.tools(router.tool_context())}
    assert "connect_cluster" in normal
    assert "set_cluster_objective" in normal


def test_cluster_send_needs_a_live_cluster():
    """`cluster_send` is indeed situational, but based on REAL STATE (a cluster is connected), not on having a UI
    open: with nobody on the other side, there is no one to write to."""
    off = {t["function"]["name"] for t in router.tools(router.tool_context())}
    assert "cluster_send" not in off
    on = {t["function"]["name"] for t in router.tools(router.tool_context(cluster_connected=True))}
    assert "cluster_send" in on


def test_connect_cluster_accepts_a_public_tokenless_cluster():
    """V2-086: MeshKore has PUBLIC clusters without a token (Commons). The schema required `token`, so that case
    was INEXPRESSIBLE — the model either invented a token or did not call. Now only cluster_id is required."""
    fn = next(t["function"] for t in router.TOOLS if t["function"]["name"] == "connect_cluster")
    assert fn["parameters"]["required"] == ["cluster_id"]
    assert "vis" in fn["parameters"]["properties"]


def test_show_panel_routes_the_clusters_tab():
    """The NETWORK is the ChatWall's 4th native tab (V2-086) — it opens through show_panel, like Processes/Crons."""
    assert router._canon_panel("clusters") == "clusters"
    for word in ("cluster", "meshkore", "la red", "la malla", "conexiones", "peers"):
        assert router._canon_panel(word) == "clusters", word
    # …and it has not broken routing for the others.
    assert router._canon_panel("crons") == "crons"
    assert router._canon_panel("chat") == "chat"
    assert router._canon_panel("workers") == "procesos"


def test_capability_tools_are_situational():
    """V2-085: three NEW gates based on REAL CAPABILITY — without a messaging connector there is nobody to reply to,
    without a vault there is no secret to reveal, and without the `youtube` widget play_video has nowhere to load
    the video. Offering them in that state only invites the model to promise something impossible."""
    on = {t["function"]["name"] for t in router.tools(router.tool_context())}
    assert {"reply_message", "reveal_secret", "play_video"} <= on          # default fail-OPEN
    off = {t["function"]["name"] for t in router.tools(
        router.tool_context(messaging_on=False, has_vault=False, has_video_widget=False))}
    assert not ({"reply_message", "reveal_secret", "play_video"} & off)
    # …and pruning by capability does not remove anything else.
    assert on - off == {"reply_message", "reveal_secret", "play_video"}


def test_every_tool_belongs_to_a_family():
    """The family is the unit used to reason about a turn's tool budget. A new tool without a family would silently
    fall into 'core' — this test requires it to be classified when added."""
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
    # PRUNED tools are also recorded: without that, one cannot audit why a turn did not have a tool.
    # (V2-086: `connect_cluster` was deliberately removed from here — it is no longer gated.)
    assert "cluster_send" in rep["tools_omitted"] and "send_to_worker" in rep["tools_omitted"]
    assert "connect_cluster" not in rep["tools_omitted"]


def test_tool_catalog_is_constant_sized(monkeypatch):
    """The tool catalog is O(1): it does NOT grow with the widget catalog (that is the one bounded in
    widgets/selection.py). If a tool ever starts enumerating widgets in its description, this test catches it."""
    import json as _json
    from widgets import runtime as _rt
    base = len(_json.dumps(router.tools(router.tool_context()), ensure_ascii=False))
    monkeypatch.setattr(_rt, "_signature", lambda: ("synthetic", 5000))
    monkeypatch.setitem(_rt._cache, "sig", ("synthetic", 5000))
    monkeypatch.setitem(_rt._cache, "list", [{"id": f"w{i}", "title": f"W{i}"} for i in range(5000)])
    grown = len(_json.dumps(router.tools(router.tool_context()), ensure_ascii=False))
    assert grown == base


# Catalog ceiling (2026-08-02). O(1) is not enough: the constant can grow on its own, and it did — reaching 31,647
# chars (~7.9k tokens EVERY TURN, including «hola»), with 70% prose. After compaction it was 18,926. The operator's
# rule is «tools from fewest to most»: a language model already knows what a music player is, so the description
# only says what it does + the BOUNDARIES against OUR other tools. This ceiling forces a new tool to be added by
# trimming, not by bloating everyone's turn. If it must be raised, that should be a measured decision alongside it
# (`tests/agent_headless/e2e/prompt_cost/bench_fast_model.py`, node 2.13).
#
# RAISED 21,000 → 21,200 on 2026-08-28 (V2-457, `show_images`), with the measurement alongside as required and
# after trimming, not instead of trimming. Measured with the same request and the same two paths:
#
#     Brain Worker (what the operator received)   355 s   $1.96   10 photos from third-party galleries
#     `show_images` through warm Chromium           3.0 s  ~$0     originals from cdn.ferrari.com, master 3128x2333
#
# The tool weighs 727 chars, and ~170 chars of REAL redundancy were trimmed before raising the ceiling: the photo
# boundary is decided in `show_images` and was redundantly repeated in the YES-list of `escalate_to_slowbrain`,
# `web_search` stated it at length, and `show_panel`'s parentheses were explanatory prose. What was NOT done was
# removing a rule born from an incident to protect a number: each one cost a measured round, and the catalog exists
# to carry them. The increase costs ~50 tokens per turn; what it buys is that showing a photo no longer takes
# a six-minute assignment.
# V2-515 raised 21_200 → 21_800: one genuinely NEW tool (restore_widget), added with its description
# already compacted — the +490 is the tool, not fat.
MAX_CATALOG_CHARS = 21_800


# ── "muéstrame una foto de X" must NOT be described in words (real incident 2026-08-03) ─────────────────────
# The brain asked web_search for a photo that web_search cannot provide (text only) and ended up DESCRIBING the
# image instead of showing it — 6 turns of "nothing is visible"/apologies before giving up. The tools have no
# parameter for this (there is no «request image»): the boundary lives in the DESCRIPTION, so the test is textual.
#
# ⚠️ The DESTINATION changed on 2026-08-28 (V2-457), and these tests are rewritten with their rationale, never
# silently. On 2026-08-03 the only available route was ESCALATE, and that was right: there was no other way to get
# a real photo. Today there is, and escalation cost 355 s and $1.96 versus 3.0 s through `show_images` — so the
# boundary now points there. What does NOT change, and is what these tests truly protect, is that a request to SEE
# a photo is never resolved by describing it in words.
def _desc(name: str) -> str:
    return next(t["function"]["description"] for t in router.TOOLS if t["function"]["name"] == name)


def test_web_search_description_sends_a_real_photo_to_the_image_viewer():
    d = _desc("web_search").lower()
    assert "foto" in d or "imagen" in d
    assert "texto" in d           # makes clear that it brings only text, never the image itself
    assert "show_images" in d     # …and NAMES where it goes: without a destination, «not here» leaves the model improvising


def test_escalate_no_longer_claims_showing_a_photo_and_points_at_the_tool():
    """The YES-list no longer claims to show photos; the NO-list sends them to `show_images`.

    Beware the test it replaces: it asked for `"foto" in d` alone, and that would still pass TODAY — the word is in
    the NO-list. In other words, it would certify as correct exactly the rule opposite to what its name claimed.
    That is why the LIST is checked, not the word.
    """
    d = _desc("escalate_to_slowbrain")
    si, no = d.split("NO:", 1)
    assert "foto" not in si.lower() and "imagen" not in si.lower(), (
        "enseñar una foto ya no es motivo para lanzar un worker: es un turno de 3 s por `show_images`")
    assert "show_images" in no, "the NO-list must say where it goes, as it already does for play_video/play_music"


def test_tool_catalog_stays_compact():
    import json as _json
    size = len(_json.dumps(router.TOOLS, ensure_ascii=False))
    assert size <= MAX_CATALOG_CHARS, (
        f"el catálogo de tools ha crecido a {size} chars (techo {MAX_CATALOG_CHARS}). Compacta descripciones "
        f"antes de subir el techo: se paga en CADA turno de voz.")
    # No single tool should monopolize the catalog: escalation is the largest and still fits comfortably.
    worst = max(router.TOOLS, key=lambda t: len(_json.dumps(t, ensure_ascii=False)))
    assert len(_json.dumps(worst, ensure_ascii=False)) <= 2_000, worst["function"]["name"]


def test_decide_worker_tools():
    assert router.decide("send_to_worker", {"which": "la moto", "message": "verde"}).kind == INJECT
    assert router.decide("stop_worker", {"which": "el widget"}).kind == STOP
    assert router.decide("answer_worker", {"answer": "enduro"}).kind == ANSWER


def test_stop_wins_priority():
    # STOP takes precedence over escalate if the model calls both in one turn.
    calls = [("escalate_to_slowbrain", {"request": "x"}), ("stop_worker", {"which": "todo"})]
    assert router.classify(calls).kind == STOP


def test_decide_play_music():
    # V2-041: play_music → MUSIC with normalized query+action (action defaults to 'play').
    d = router.decide("play_music", {"query": "Frank Sinatra", "action": "PLAY"})
    assert d.kind == MUSIC and d.payload == {"query": "Frank Sinatra", "action": "play"}
    d2 = router.decide("play_music", {})
    assert d2.kind == MUSIC and d2.payload == {"query": "", "action": "play"}


def test_decide_play_video():
    # V2-045: play_video → VIDEO with query (SEE in the youtube widget, ≠ play_music audio).
    # Rewritten by V2-402, not reverted: the decision gained `action` (play|list) because SEARCHING for videos is
    # also this tool's job (to the player's LIST, not the spreadsheet). The protected parts —kind and query— remain intact.
    d = router.decide("play_video", {"query": "el gol de la mano de Dios"})
    assert d.kind == VIDEO and d.payload == {"query": "el gol de la mano de Dios", "action": "play"}
    assert router.decide("play_video", {}).kind == VIDEO
    assert router.decide("play_video", {"query": "x", "action": "search"}).payload["action"] == "list"


def test_music_priority_below_worker_ops():
    # STOP/ESCALATE take precedence over MUSIC; MUSIC takes precedence over SEARCH/STYLE/CHAT.
    assert router.classify([("play_music", {}), ("stop_worker", {"which": "x"})]).kind == STOP
    assert router.classify([("play_music", {}), ("web_search", {"query": "x"})]).kind == MUSIC


def test_looks_like_stop_work():
    for yes in ("para eso", "cancela el widget", "deja de buscar", "para todo", "detén el proceso",
                "para la búsqueda", "para de crear el widget", "cancela la tarea del navegador"):
        assert router.looks_like_stop_work(yes), yes
    for no in ("para", "silencio", "qué tal", "ponme una cita para la cena"):
        # Bare 'para' / without a work reference → NO (that is hard_interrupt / something else)
        assert not router.looks_like_stop_work(no), no


def test_stop_work_ignores_ambient_speech():
    """Regression for the 2026-07-14 demo false positive: AMBIENT speech (open microphone, live attention window)
    with PREPOSITIONAL 'para' + 'creando' killed the widget worker. An explanatory monologue is NEVER a stop order;
    a real stop is short and imperative."""
    demo = ("La memoria real que él tiene está aquí. Y entonces estás viendo ahora mismo qué puntos de la "
            "memoria está tocando. Como estuvieron en el cefalograma. Sí, sí, sí. Qué buenísimo. Entonces "
            "maneja su estado. Muy buenísimo. Maneja el corto plazo. Y luego esto es lo que a largo plazo. "
            "Ahora ha reiniciado después de un cambio. Buenísimo. Y entonces aquí va creando su... Esto se va "
            "llenando, se va llenando. Está creando su memoria vectorial, que es lo que necesita para poder "
            "acceder a esa velocidad, porque esto puede crecer de forma gigante.")
    assert not router.looks_like_stop_work(demo)
    # Prepositional 'para' (para que / para poder / para acceder) → never a stop command
    for no in ("lo necesita para poder crear la búsqueda", "es para que el proceso funcione",
               "sirve para buscar cosas en el navegador"):
        assert not router.looks_like_stop_work(no), no
    # A monologue containing imperative verbs does not trigger either (length cap: when in doubt, do not kill)
    largo = ("bueno pues entonces yo creo que igual habría que cancelar el proceso pero primero déjame "
             "explicarte cómo funciona todo esto del navegador y la búsqueda que está haciendo por detrás")
    assert not router.looks_like_stop_work(largo)


def test_stop_work_ignores_short_prepositional_para():
    """Regression for the post-P1/P2 test (2026-07-14): PREPOSITIONAL 'para' in a SHORT sentence (which the cap
    cannot save) — 'hazme un widget PARA el tiempo' automatically killed the newborn worker. A turn that STARTS by
    requesting something, or 'para <noun phrase>' / 'para' mid-sentence, is NOT a stop order."""
    for no in ("quiero que crees un widget para el tiempo", "necesito un widget para la agenda",
               "hazme una búsqueda para el finde", "eso es para la búsqueda de piso",
               "hazme un widget para el tiempo", "prepara un informe para mañana",
               "abre la agenda para ver mis citas", "muéstrame el widget de fútbol"):
        assert not router.looks_like_stop_work(no), no
    # REAL stop orders (including imperative 'para' at the start with a work complement) still work:
    for yes in ("para la búsqueda", "para esa tarea", "para ya con eso", "aborta la búsqueda",
                "deja de crear el widget"):
        assert router.looks_like_stop_work(yes), yes


def test_looks_like_close_guard():
    # V2-045: 'cierra el widget de X' = CLOSE (reversible), not delete. cerrar≠borrar guard (V2-017 invariant).
    for yes in ("cierra el widget de youtube", "ciérrame el reloj", "cierra eso", "close the clock", "oculta la agenda"):
        assert router.looks_like_close(yes), yes
    # With a DELETE verb present → NOT close (it is a real delete); nor without a closing verb.
    for no in ("borra el widget del reloj", "elimina la agenda", "borra y cierra todo", "ponme música",
               "abre la agenda"):
        assert not router.looks_like_close(no), no
    # Absurd 2026-07-19 session: closing WITH a long complaint remains CLOSE (does not escalate to code). The text
    # guard recognizes it; the provider backstop handles length (name resolved against an open widget).
    assert router.looks_like_close("cierra el widget de música. has puesto un videoclip de la canción que te he pedido")
    assert not router.looks_like_create_widget("cierra el widget de música. has puesto un videoclip")
    # NEGATION: "no cierres / no lo cierres" is NOT close (do not close, reversed).
    for neg in ("no cierres el widget de música", "no lo cierres todavía", "don't close the clock"):
        assert not router.looks_like_close(neg), neg


def test_looks_like_rule_removal_guard():
    # V2-046 A1: the SAME tool adds or removes a user rule; this turn guard determines the meaning.
    for yes in ("olvida esa regla", "olvídate de lo de ser breve", "quita la regla de responder sí o no",
                "ya no hace falta que seas tan directo", "borra esa norma"):
        assert router.looks_like_rule_removal(yes), yes
    for no in ("sé más breve a partir de ahora", "trátame de usted", "responde solo sí o no",
               "cuando te pida una acción hazla sin responder"):
        assert not router.looks_like_rule_removal(no), no


def test_is_messaging_service_guard():
    # V2-045: WhatsApp/Telegram are linked by QR in the messaging widget, not through the browser.
    assert router.is_messaging_service("", "conéctame a WhatsApp")
    assert router.is_messaging_service("web.whatsapp.com", "")
    assert router.is_messaging_service("", "abre mi Telegram")
    assert not router.is_messaging_service("wallapop.com", "conéctame a Wallapop")
    assert not router.is_messaging_service("", "conéctame a Spotify")


def test_web_auth_tools_are_side_effects_not_routing():
    # authenticate_web / login_done are side-effect actions (dispatched by the provider), and do not change turn
    # routing → decide() treats them as chat (the turn remains chat: zaelar speaks).
    assert router.decide("authenticate_web", {"site": "wallapop.com"}).kind == CHAT
    assert router.decide("login_done", {}).kind == CHAT
    assert router.decide("connect_cluster", {"cluster_id": "c_x", "token": "ck_y"}).kind == CHAT


def test_looks_like_login_request_guard():
    # V2-022, hardened after the 2026-07-23 bug: ONLY the first-person form directed at zaelar ("conéctame"/
    # "conectar mi cuenta") is pure login. `conect(?!ad|or)` matched ANY conjugation of "conectar" — a QUESTION
    # about capability and a third-person narrative opened a browser login nobody requested (to wallapop.com via
    # the unknown-site fallback in `nucleo.py::_start_web_auth`).
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
    # 2026-07-17: SHOWING a widget is a first-class tool (fix for 'jugar'→play_music hijacking). Gated by has_widgets;
    # decide() maps it to SHOW with the widget_id.
    normal = {t["function"]["name"] for t in router.tools(router.tool_context())}
    assert "show_widget" in normal
    nowid = {t["function"]["name"] for t in router.tools(router.tool_context(has_catalog=False))}
    assert "show_widget" not in nowid
    d = router.decide("show_widget", {"widget_id": "juego-serpiente-snake"})
    assert d.kind == router.SHOW and d.payload.get("widget_id") == "juego-serpiente-snake"


def test_looks_like_create_widget_guard():
    # 2026-07-17: CREATING a widget ESCALATES (generator); it is not shown. show_widget guard (tool regression).
    for yes in ("créame un widget de conversor de divisas", "hazme un widget que convierta divisas",
                "quiero un widget nuevo para convertir euros", "hazme un widget contador de días",
                "constrúyeme un widget del tiempo", "genérame un widget nuevo"):
        assert router.looks_like_create_widget(yes), yes
    # SHOWING an existing widget / playing a game is NOT creating (must not redirect to escalate):
    for no in ("abre el juego de la serpiente", "juega al snake", "muéstrame la serpiente",
               "abre el reloj", "quiero jugar a la serpiente", "muéstrame el widget de fútbol"):
        assert not router.looks_like_create_widget(no), no


def test_stop_work_bulk_and_false_positive():
    # 2026-07-17 (round 3): MASS stop ("para todas las tareas"/"para todos los workers") was not detected and stop
    # failed silently; and "para todo el mundo es difícil" was a FALSE POSITIVE (killed workers). Both fixed.
    for yes in ("para todas las tareas", "para todos los workers", "para todos los procesos",
                "cancela todas las tareas", "para todo"):
        assert router.looks_like_stop_work(yes), yes
    for no in ("para toda la comida", "para todo el mundo es difícil", "para la cena de mañana"):
        assert not router.looks_like_stop_work(no), no


def test_show_panel_decision_and_canon():
    # V2-079: the show_panel tool opens the native side panel (chat/processes/crons) by voice.
    d = router.decide("show_panel", {"panel": "procesos"})
    assert d.kind == router.PANEL and d.payload.get("panel") == "procesos"
    # _canon_panel normalizes synonyms the model may produce in the ARGUMENT (not in the request):
    assert router._canon_panel("crons") == "crons"
    assert router._canon_panel("chat") == "chat"
    assert router._canon_panel("workers") == "procesos"
    assert router._canon_panel("brain workers") == "procesos"
    assert router._canon_panel("tareas programadas") == "crons"
    assert router._canon_panel("muro de texto") == "chat"
    assert router._canon_panel("") == "procesos"           # default: the most requested case
    # show_panel is in the catalog of tools offered to the model
    assert any(t["function"]["name"] == "show_panel" for t in router.TOOLS)


def test_manage_widget_alias_decision():
    # V2-082: add/remove a widget alias by voice.
    d = router.decide("manage_widget_alias", {"widget_id": "mensajeria", "alias": "WhatsApp"})
    assert d.kind == router.ALIAS and d.payload["widget_id"] == "mensajeria"
    assert d.payload["alias"] == "WhatsApp" and d.payload["op"] == "add"     # add by default
    d = router.decide("manage_widget_alias", {"widget_id": "reloj", "alias": "x", "op": "remove"})
    assert d.payload["op"] == "remove"
    d = router.decide("manage_widget_alias", {"widget_id": "reloj", "alias": "x", "op": "quitar"})
    assert d.payload["op"] == "remove"
    # situational: only with widgets
    assert "manage_widget_alias" in {t["function"]["name"] for t in router.tools(router.tool_context())}


# ── THE NATIVE PANEL ALSO CLOSES BY VOICE (2026-08-10) ────────────────────────────────────────────────────────
# Real failure, the kind that breaks trust. In the operator's session:
#   «Okay, close the chat too.»              → «Okay.»
#   «Close the chatbot too.»                 → «Okay, closed.»
#   «I want you to close the system chat.»   → «Here you go.»
#   «Close the chat window.»                 → (nothing)
#   «Okay, I'll do it myself by pressing the x button. There.»
# Chat is NOT a widget (it is native UI), so [[close]] does not touch it — and `show_panel` only knew how to OPEN.
# The capability therefore did not exist and the turn ended with a false «closed». Saying yes is worse than being unable.
def test_the_panel_tool_can_close_not_only_open():
    d = router.decide("show_panel", {"panel": "chat", "action": "close"})
    assert d.payload["action"] == "close" and d.payload["panel"] == "chat"


def test_opening_stays_the_default_so_a_missing_argument_never_closes_it():
    """A model that omits the argument must not end up closing the panel for the operator."""
    assert router.decide("show_panel", {"panel": "procesos"}).payload["action"] == "open"
    assert router.decide("show_panel", {"panel": "chat", "action": ""}).payload["action"] == "open"


def test_the_close_argument_tolerates_what_a_model_actually_writes():
    """The argument is written by a model in the turn's language: 'close', 'cerrar', 'quita', 'oculta'."""
    for v in ("close", "cerrar", "cierra el chat", "quita", "ocultar", "hide"):
        assert router.decide("show_panel", {"panel": "chat", "action": v}).payload["action"] == "close", v


def test_the_tool_says_out_loud_that_the_chat_is_not_a_widget():
    """The underlying confusion: the operator says «cierra el chat» and the model reaches [[close]], which only
    closes canvas cards. The description must disambiguate this, or it will fail silently again."""
    desc = _desc("show_panel")
    assert "close" in desc
    low = desc.lower()
    assert "no es un widget" in low or "nunca show_widget" in low


# ── description contracts born from the 2026-08-18 use cases ────────────────────────────────────────────────
# Same criterion as the two tests above: when the boundary lives in the tool's PROSE (no parameter expresses it),
# the regression can only be caught textually. Each one cites the case that measured it.
def test_escalate_no_longer_teaches_that_a_reminder_needs_no_tool():
    """V2-121 · `remember-and-remind-deadline`. The catalog said «a simple reminder (acknowledge it without a tool,
    your memory stores it)» — that is, it TAUGHT the model to answer «Done» without scheduling anything, exactly the
    compliance hallucination measured by the case. The correct destination exists: [[cron.create]]."""
    d = _desc("escalate_to_slowbrain")
    assert "sin tool" not in d.lower()
    assert "cron.create" in d          # names the real destination, not a «do nothing» instruction


def test_widget_data_says_that_writing_it_down_is_not_warning():
    """V2-121 · the other half of the same case: the operator asked for TWO things (note Thursday, notify
    Wednesday), and they are two subsystems. Confirming one and staying silent about the other is the failure."""
    d = _desc("widget_data")
    assert "cron.create" in d


def test_escalate_says_that_asking_about_a_live_task_is_not_ordering_one():
    """Measured on 2026-08-24 in `search-buy-guitar__es`: ONE guitar search opened THREE assignments.

    The goals, taken from the durable set log:

      16:14:30  web       «Busca en marketplaces de segunda mano … una guitarra acústica…»   ← el encargo
      16:15:48  research  «¿Alguna novedad ya?»                                              ← un worker
      16:16:20  research  «Perfecto, dale. ¿Tienes algo ya?»                                 ← otro worker

    Each had its own card: four cards on screen for one assignment, which is what the operator saw and reported
    («I see a lot of processes in screen»). And they are not DUPLICATES —the duplicate detector correctly considers
    them valid: «¿alguna novedad?» does not resemble «busca una guitarra»— they are conversation turns converted
    into assignments.

    The description already said «if a task is already IN PROGRESS, do not repeat it», and that is the gap: asking
    about it is not READ as repeating it. The answer lives in STATE, which already travels in the prompt — the same
    turn had «BROWSER — ALREADY IN PROGRESS (1)» in front of it.
    """
    d = _desc("escalate_to_slowbrain").lower()
    assert "no es encargarla" in d, "la frontera tiene que estar dicha, no deducible de «no la repitas»"
    assert "estado" in d


def test_escalate_says_several_tasks_mean_several_calls():
    """V2-118 · `three-tasks-at-once`: three assignments in one turn, ONE live task. Half of the mechanism is fixed
    in the provider (it previously executed only the first call); without telling the model too, the new capability
    is not used."""
    d = _desc("escalate_to_slowbrain").lower()
    assert "cada una" in d


def test_escalate_says_a_widget_missing_from_the_catalog_is_the_one_to_build():
    """V2-118 · run turn 1: «it does not exist in the catalog, so it will need custom construction» — it refused to
    build exactly what it was being asked to build."""
    assert "no estar en el catálogo NO es motivo para negarte" in _desc("escalate_to_slowbrain")


def test_web_search_answers_both_halves_of_a_two_part_question():
    """V2-120 · `quick-fact-opening-hours`: the time AND the price were asked for in the same sentence, and it came
    back with half the answer, for two rounds in a row (one half each time)."""
    d = _desc("web_search").lower()
    assert "dos datos" in d and "misma `query`" in d
