"""A browser task that STOPPED must be able to say so (V2-167).

Three use-case runs ended with the very same task state — `status="working"`, `phase_active=True`,
`results=None` — after the operator had already given up, and in all three zaelar told the truth and the truth
was useless, because the only truth it had was that the task was alive:

  · `restaurant-tonight-madrid` reached the right page (thefork.es/restaurant/casa-lucio-madrid/r146247) at
    19:28:47 and spent the next eleven minutes there, re-photographing it — `shot_rev` reached 10 over four
    URLs, so anything counting captures would have reported healthy movement while nothing moved.
  · `book-hotel-night-known__es` made ONE navigation in the whole run, to Booking's `chal_t=` anti-bot
    challenge, and reported `awaiting_login: false` — the only field that could have said «me han parado» is
    written exclusively by the real login flow, so it said there was nothing to say.
  · `find-theatre-tickets__es` walked through `chrome-error://chromewebdata/` and Google's `/sorry/index`
    CAPTCHA and came out the other side with `results: null`.

The two facts that were missing are therefore: how long since the task last MOVED, and whether the page it is
sitting on is a wall. Both already existed in the world; neither existed in the registry.
"""
from __future__ import annotations

import time

import pytest

from widgets.navegador import tasks


@pytest.fixture(autouse=True)
def _clean_registry():
    tasks._tasks.clear()
    yield
    tasks._tasks.clear()


# ── el muro ───────────────────────────────────────────────────────────────────────────────────────────────
# Las tres URLs son VERBATIM de los informes de mecanismo, no inventadas para el test.
BOOKING_WALL = ("https://www.booking.com/index.es.html?aid=304142&label=x&chal_t=1787158378677"
                "&force_referer=")
GOOGLE_WALL = "https://www.google.com/sorry/index?continue=https://www.google.com/search%3Fq%3Del%2Brey%2Bleon"
LOAD_ERROR = "chrome-error://chromewebdata/"
REAL_PAGE = "https://www.thefork.es/restaurant/casa-lucio-madrid/r146247"


def test_the_three_walls_that_were_measured_are_recognised():
    assert tasks.wall_reason(BOOKING_WALL)
    assert tasks.wall_reason(GOOGLE_WALL)
    assert tasks.wall_reason(LOAD_ERROR)


def test_and_an_ordinary_page_is_not_a_wall():
    """La otra mitad: sin esto, «detectar muros» y «declarar muro siempre» pasan el mismo test. La ficha del
    restaurante es justo la página donde la tarea SÍ había llegado a su destino."""
    assert tasks.wall_reason(REAL_PAGE) == ""
    assert tasks.wall_reason("https://www.thefork.es/search/madrid/Casa%20Lucio") == ""
    assert tasks.wall_reason("") == ""


def test_the_reason_is_said_in_words_the_operator_can_hear():
    """El campo se lee en voz alta: no puede devolver el token que lo delató."""
    for url in (BOOKING_WALL, GOOGLE_WALL, LOAD_ERROR):
        reason = tasks.wall_reason(url)
        assert "chal_t" not in reason and "sorry" not in reason and "chrome-error" not in reason
        assert len(reason.split()) >= 3


def test_the_task_carries_its_wall_and_drops_it_when_it_moves_on():
    tid = tasks.create("reservar hotel")
    tasks.set_status(tid, "working")
    tasks.update_view(tid, url=BOOKING_WALL, page_title="Booking.com")
    assert tasks.active_progress()[0]["wall"]
    tasks.update_view(tid, url="https://www.booking.com/searchresults.es.html?ss=Madrid")
    assert tasks.active_progress()[0]["wall"] == ""


# ── el atasco ─────────────────────────────────────────────────────────────────────────────────────────────
def test_recapturing_the_same_page_is_not_progress():
    """La corrida del restaurante en miniatura: cuatro páginas y luego seis capturas de la última. Si una
    captura contara como avance, la tarea se declararía sana justo mientras se moría."""
    tid = tasks.create("Reservar mesa en Casa Lucio")
    tasks.set_status(tid, "working")
    for url in ("https://www.thefork.es/", "https://www.thefork.es/restaurante/madrid",
                "https://www.thefork.es/search/madrid/Casa%20Lucio", REAL_PAGE):
        tasks.update_view(tid, url=url, page_title="thefork.es")
    tasks._tasks[tid]["last_progress"] = time.time() - 673      # los 11 minutos medidos
    for rev in range(5, 11):                                    # shot_rev 5..10, misma página
        tasks.update_view(tid, url=REAL_PAGE, shot_rev=rev)
    assert tasks.active_progress()[0]["stalled_s"] >= 600


def test_but_a_new_page_clears_it():
    tid = tasks.create("buscar entradas")
    tasks.set_status(tid, "working")
    tasks.update_view(tid, url="https://entradas.com/")
    tasks._tasks[tid]["last_progress"] = time.time() - 400
    tasks.update_view(tid, url="https://entradas.com/musicals/el-rey-leon-madrid-1773394/")
    assert tasks.active_progress()[0]["stalled_s"] < 5


def test_and_so_does_a_reported_step():
    """Un hito es trabajo reportado, aunque la URL no cambie (rellenar un formulario, abrir un desplegable)."""
    tid = tasks.create("reservar mesa")
    tasks.set_status(tid, "working")
    tasks.update_view(tid, url=REAL_PAGE)
    tasks._tasks[tid]["last_progress"] = time.time() - 400
    tasks.add_event(tid, "📋 6 horarios encontrados")
    assert tasks.active_progress()[0]["stalled_s"] < 5


def test_a_task_that_just_started_is_not_stalled():
    """El límite que impide que esto degenere en «todo está atascado»: una tarea recién creada lleva 0."""
    tid = tasks.create("buscar hotel")
    tasks.set_status(tid, "working")
    assert tasks.active_progress()[0]["stalled_s"] < 5


# ── y lo que el cerebro ve ────────────────────────────────────────────────────────────────────────────────
def test_the_brain_is_told_about_the_wall():
    """La prueba de que el hecho LLEGA al prompt: V2-145/V2-150 ya establecieron que en esta casa la verdad suele
    existir en la tarea y no llegar nunca al sitio donde se decide, que es el fallo que se repite."""
    from nucleo.flash import prompt as _p

    tid = tasks.create("Reservar habitación en el hotel")
    tasks.set_status(tid, "working")
    tasks.update_view(tid, url=BOOKING_WALL, page_title="Booking.com")
    state = _p.live_state()
    # «· MURO:» con su viñeta es el HECHO de ESTA tarea; la palabra suelta también aparece en la directiva que
    # dice qué hacer con él, así que comprobarla sin la viñeta pasaría siempre.
    assert "· MURO: " in state
    assert "anti-robot" in state
    assert "Nunca esperes callado sobre un muro." in state


def test_and_about_the_stall_when_there_is_no_wall():
    tid = tasks.create("Reservar mesa en Casa Lucio")
    tasks.set_status(tid, "working")
    tasks.update_view(tid, url=REAL_PAGE, page_title="thefork.es")
    tasks._tasks[tid]["last_progress"] = time.time() - 673
    state = _live()
    assert "· lleva 11 min SIN MOVERSE" in state


def test_but_a_task_that_is_simply_working_says_nothing_of_the_sort():
    """La sensibilidad del hecho anterior: sin esto, «avisa del atasco» y «avisa siempre» pasan igual — y avisar
    siempre reabre justo lo que arregló V2-152, que el turno empuje a parar una tarea que va bien."""
    tid = tasks.create("Reservar mesa en Casa Lucio")
    tasks.set_status(tid, "working")
    tasks.update_view(tid, url=REAL_PAGE, page_title="thefork.es")
    state = _live()
    assert "SIN MOVERSE" not in state.split("AHORA BIEN")[0]
    assert "· MURO: " not in state
    # y la regla de V2-152 sigue entera: la falta de novedades no es una parada
    assert "la falta de parte no significa que esté parada" in state


def _live() -> str:
    from nucleo.flash import prompt as _p
    return _p.live_state()


# ── el muro se VE en pantalla ─────────────────────────────────────────────────────────────────────────────
#
# Petición del operador (2026-08-19): «ya que tenemos un frontend gráfico… podríamos mostrar la imagen del
# navegador en pantalla y decir "Booking me ha bloqueado" y poner una captura de lo que ha pasado y decirle
# que tú ya no puedes seguir». Un campo que solo existe en el registro no es eso: la captura ya está en disco
# desde el primer momento, lo que faltaba era decirlo y abrir la tarjeta que la enseña.
def test_hitting_a_wall_says_it_in_the_feed():
    tid = tasks.create("Reservar habitación")
    tasks.set_status(tid, "working")
    tasks.update_view(tid, url=BOOKING_WALL, page_title="Booking.com")
    feed = [e["text"] for e in tasks.get(tid)["events"]]
    assert any("no puedo seguir" in t for t in feed)
    assert any("anti-robot" in t for t in feed)


def test_and_the_spinner_stops():
    """Una ruleta girando sobre una página bloqueada es la pantalla diciendo «trabajando» mientras no se
    trabaja — justo la clase de estado que puede mentir."""
    tid = tasks.create("Reservar habitación")
    tasks.set_status(tid, "working")
    tasks.set_phase(tid, "conduciendo el navegador", True)
    tasks.update_view(tid, url=BOOKING_WALL)
    assert tasks.get(tid)["phase_active"] is False
    assert "anti-robot" in tasks.get(tid)["phase"]


def test_and_the_card_is_opened_so_the_capture_can_be_seen():
    from voice import observer
    shown = []
    _orig = observer.emit
    observer.emit = lambda kind, label, **kw: (shown.append((kind, label, kw.get("extra") or {}))
                                               if kind == "widget" else None)
    try:
        tid = tasks.create("Reservar habitación")
        tasks.set_status(tid, "working")
        tasks.update_view(tid, url=BOOKING_WALL)
    finally:
        observer.emit = _orig
    assert any(lbl == "show" and extra.get("id") == tasks.inst_id(tid) for _k, lbl, extra in shown)


def test_but_it_is_announced_ONCE_not_on_every_capture():
    """El hotel hizo 13 revisiones de captura sobre la MISMA página del muro. Un aviso por captura sería la
    tarjeta gritando trece veces lo mismo."""
    tid = tasks.create("Reservar habitación")
    tasks.set_status(tid, "working")
    for rev in range(1, 14):
        tasks.update_view(tid, url=BOOKING_WALL, shot_rev=rev)
    assert len([e for e in tasks.get(tid)["events"] if "⛔" in e["text"]]) == 1


def test_and_an_ordinary_page_announces_nothing():
    tid = tasks.create("Reservar mesa")
    tasks.set_status(tid, "working")
    tasks.set_phase(tid, "conduciendo el navegador", True)
    tasks.update_view(tid, url=REAL_PAGE)
    assert tasks.get(tid)["events"] == []
    assert tasks.get(tid)["phase_active"] is True


# ── el puente tiene que seguir siendo el puente ────────────────────────────────────────────────────────────
def test_the_bridge_route_still_points_at_the_bridge():
    """Caught in a live run, one day after `_with_wall` was added: the helper had been inserted BETWEEN
    `@router.post("/api/navegador/act")` and `navegador_act`, so FastAPI registered the annotator as the
    endpoint. It takes one dict and returns it unchanged, so the route answered 200 with the request echoed
    back — no `ok`, no `error` — and `nav_cli` turned that into «ERROR: desconocido» for every action a Brain
    Worker tried. Every unit test still passed: nothing here had ever asserted WHICH function the path
    resolves to, and a decorator does not care what follows it."""
    from widgets.navegador.act_api import router

    hit = [r for r in router.routes if getattr(r, "path", "") == "/api/navegador/act"]
    assert hit, "la ruta del puente del navegador desapareció"
    assert hit[0].endpoint.__name__ == "navegador_act"
    assert {"task_id", "action", "args"} <= set(hit[0].endpoint.__annotations__)


# ── V2-185: la promesa tranquilizadora no puede ser incondicional ─────────────────────────────────────────
#
# Corrida real de `book-hotel-night-known__es`, 2026-08-20 01:01. El muro SÍ llegó al turno —zaelar dijo
# «Booking me ha puesto una verificación anti-robot», que es el arreglo de V2-167 funcionando— y acto seguido
# volvió a «sigo con ello» durante CUATRO turnos más mientras la tarea seguía en `chrome-error://chromewebdata/`.
# Diez turnos, cero datos, y el operador esperando: «Vale, espero» · «Vale, sin prisa» · «Vale, me avisas».
#
# No era el modelo siendo perezoso. Este bloque le decía, en cuatro frases ANTES de la salvedad, que «esa tarea
# sigue viva y te dará el resultado sola» y que no empujara al operador a pararla. Las dos son FALSAS delante de
# un muro, iban primero y eran mucho más largas — y el modelo creyó a la mitad larga. La salvedad («AHORA BIEN…»)
# no compite con eso: lo que había que quitar era la afirmación falsa, no añadirle un pero.
def test_a_walled_task_is_not_promised_to_finish_on_its_own():
    tid = tasks.create("Reservar noche en el hotel")
    tasks.set_status(tid, "working")
    tasks.update_view(tid, url=LOAD_ERROR)
    state = _live()
    assert "te dará el resultado sola" not in state
    assert "no le empujes" not in state
    assert "ESTO ESTÁ BLOQUEADO" in state


def test_and_neither_is_one_that_stopped_moving():
    tid = tasks.create("Reservar mesa")
    tasks.set_status(tid, "working")
    tasks.update_view(tid, url=REAL_PAGE)
    tasks._tasks[tid]["last_progress"] = time.time() - 673
    state = _live()
    assert "te dará el resultado sola" not in state
    assert "ESTO ESTÁ BLOQUEADO" in state


def test_but_a_healthy_task_keeps_the_promise_AND_the_rule_of_V2_152():
    """La sensibilidad, y no es teórica: V2-152 existe porque empujar a parar una tarea sana por falta de
    novedades es un daño REAL y medido. Esa regla no se toca — solo deja de aplicarse donde es mentira."""
    tid = tasks.create("Buscar hotel en Burgos")
    tasks.set_status(tid, "working")
    tasks.update_view(tid, url="https://www.booking.com/searchresults.html?ss=Burgos")
    state = _live()
    assert "te dará el resultado sola" in state
    assert "la falta de parte no significa que esté parada" in state
    assert "ESTO ESTÁ BLOQUEADO" not in state


def test_and_the_shared_rules_survive_in_BOTH_states():
    """Lo que es cierto en los dos casos tiene que estar en los dos: un solo navegador, y nunca describir lo que
    la tarea «estaría haciendo». Partir un bloque en dos es justo como se pierde una regla por el camino."""
    for url, walled in ((LOAD_ERROR, True), ("https://www.booking.com/searchresults.html?ss=Burgos", False)):
        tasks._tasks.clear()
        tid = tasks.create("Buscar hotel")
        tasks.set_status(tid, "working")
        tasks.update_view(tid, url=url)
        state = _live()
        assert ("ESTO ESTÁ BLOQUEADO" in state) is walled
        assert "solo hay UN navegador" in state
        assert "rellenando el formulario" in state


# ── V2-186: el atasco también tiene que llegar al WORKER ──────────────────────────────────────────────────
#
# El muro viajaba al worker (`_with_wall`) y el atasco no, así que las dos mitades del mismo hecho acababan en
# sitios distintos: el turno del FlashBrain se enteraba de que una tarea había dejado de moverse, y la única
# parte que podía hacer algo al respecto no.
#
# Medido en `find-theatre-tickets__es` (2026-08-20 01:01): el worker navegó SIETE veces, llegó a la página
# correcta del evento a las 00:40:32, y a partir de ahí hizo CATORCE revisiones de captura de esa misma página
# sin una sola navegación más, durante unos veinte minutos. No estaba bloqueado ni parado: estaba mirando la
# misma página una y otra vez. Nada de lo que le volvía del puente decía «llevas un rato aquí», así que desde
# dentro del bucle cada `look` era tan bueno como el primero.
def test_the_worker_is_told_when_its_own_task_stopped_moving():
    from widgets.navegador import act_api

    tid = tasks.create("Entradas El Rey León")
    tasks.set_status(tid, "working")
    tasks.update_view(tid, url="https://www.entradas.com/teatro-musical/el-rey-leon-t3328")
    tasks._tasks[tid]["last_progress"] = time.time() - 1200
    out = act_api._with_stall(tid, {"url": "https://www.entradas.com/teatro-musical/el-rey-leon-t3328"})
    assert out["stalled_s"] >= 1200
    assert "sin avanzar" in out["hint"] and "extraes" in out["hint"]


def test_but_a_task_that_just_arrived_is_told_nothing():
    """La sensibilidad: sin esto, «avisa del atasco» y «avisa siempre» pasan igual — y un aviso en cada `look`
    sería ruido en el contexto del worker en cada paso de una navegación normal."""
    from widgets.navegador import act_api

    tid = tasks.create("Entradas El Rey León")
    tasks.set_status(tid, "working")
    tasks.update_view(tid, url="https://www.entradas.com/")
    out = act_api._with_stall(tid, {"url": "https://www.entradas.com/"})
    assert "hint" not in out and "stalled_s" not in out


def test_and_a_WALL_wins_over_the_stall():
    """Un muro ya trae su propia salida y es más específico; decir las dos cosas a la vez le da al worker dos
    consejos distintos sobre la misma pantalla."""
    from widgets.navegador import act_api

    tid = tasks.create("Reservar hotel")
    tasks.set_status(tid, "working")
    tasks.update_view(tid, url=BOOKING_WALL)
    tasks._tasks[tid]["last_progress"] = time.time() - 1200
    out = act_api._with_stall(tid, act_api._with_wall({"url": BOOKING_WALL}))
    assert out.get("wall") and "hint" not in out


def test_the_two_halves_share_ONE_threshold():
    """El fallo que este motor repite: dos copias del mismo umbral que derivan. Los dos lados leen la misma
    variable de entorno."""
    from widgets.navegador import act_api
    from nucleo.flash import prompt as _p

    assert act_api._STALL_HINT_S == _p._STALLED_S


# ── V2-187: un hecho que no se puede decir en voz alta es un hecho que no llega ───────────────────────────
#
# `restaurant-tonight-madrid`, 2026-08-20 01:01 (3/5, subió desde 1/5). Lo que quedaba, y el juez lo marcó como
# grave: CINCO turnos de «Sigo en ello» seguidos sin una sola información intermedia. El mecanismo dice que la
# tarea estuvo en thefork.es, en su lista de Madrid, en un dominio aparcado y por fin en casalucio.es — o sea
# que sí había algo que contar.
#
# Lo que el estado le ponía delante era «en https://www.thefork.es/restaurantes/madrid», una cadena que nadie
# dice en voz alta, y justo al lado la prohibición de describir lo que la tarea «estaría haciendo». Entre un
# hecho impronunciable y una prohibición, el modelo eligió callar. El host SÍ se dice.
def test_the_state_names_the_site_not_the_url():
    tid = tasks.create("Reservar mesa en Casa Lucio")
    tasks.set_status(tid, "working")
    tasks.update_view(tid, url="https://www.thefork.es/restaurantes/madrid?party=2")
    state = _live()
    assert "en thefork.es" in state
    assert "https://www.thefork.es/restaurantes/madrid" not in state


def test_and_says_out_loud_that_naming_it_is_allowed():
    """La otra mitad, y la que faltaba: el bloque solo PROHIBÍA. Un permiso explícito es lo que separa «no
    inventes» de «no digas nada»."""
    tid = tasks.create("Reservar mesa")
    tasks.set_status(tid, "working")
    tasks.update_view(tid, url="https://www.thefork.es/")
    state = _live()
    assert "eso es un HECHO y se DICE" in state
    # y la prohibición de V2-145 sigue intacta
    assert "NO describas lo que estaría haciendo" in state


def test_a_bare_navigation_milestone_is_not_repeated_as_the_last_step():
    """«último: 🌐 abrió https://www.thefork.es/…» sobre el sitio que se acaba de nombrar no añade nada y mete
    una segunda URL impronunciable delante del turno."""
    tid = tasks.create("Reservar mesa")
    tasks.set_status(tid, "working")
    tasks.update_view(tid, url="https://www.thefork.es/restaurantes/madrid")
    tasks.add_event(tid, "🌐 abrió https://www.thefork.es/restaurantes/madrid")
    assert "· último:" not in _live()


def test_but_a_REAL_milestone_survives():
    """La sensibilidad, y no es teórica: V2-150 existe porque «Casa Lucio solo acepta reservas por teléfono»
    estaba en la tarea desde el principio y al cerebro le llegaba un contador de pasos. Un número no se puede
    decir en voz alta; eso sí."""
    tid = tasks.create("Reservar mesa")
    tasks.set_status(tid, "working")
    tasks.update_view(tid, url="https://www.thefork.es/restaurantes/madrid")
    tasks.add_event(tid, "📋 Casa Lucio solo acepta reservas por teléfono")
    state = _live()
    assert "· último: 📋 Casa Lucio solo acepta reservas por teléfono" in state


def test_and_a_navigation_to_a_DIFFERENT_site_still_counts():
    """Un salto de sitio sí es novedad: es justo el dato con el que el turno puede decir «he pasado a la web
    oficial» en vez de «sigo en ello»."""
    tid = tasks.create("Reservar mesa")
    tasks.set_status(tid, "working")
    tasks.update_view(tid, url="https://casalucio.es/reservas/")
    tasks.add_event(tid, "🌐 abrió https://www.thefork.es/restaurantes/madrid")
    assert "· último: 🌐" in _live()


# ── V2-188: la página de error del PROPIO sitio también es un muro ────────────────────────────────────────
#
# `cancel-subscription-before-charge__es`, V2-176 ronda 3. La tarea acabó en
# `https://www.netflix.com/NotFound?prev=https%3A%2F%2Fwww.netflix.com%2Fes-es%2FContactUs` y zaelar le dijo al
# operador, dos veces, que «la página no se ha abierto del todo», y después que el login estaba listo para que
# metiera sus credenciales. El juez lo llamó gaslighting. No lo era: **nada en el estado decía que aquello era
# una página de error**, así que «aún cargando» era lo más razonable que le quedaba por decir.
#
# Es el muro más silencioso de todos porque el navegador lo reporta como una navegación PERFECTA — y lo es:
# status 200, host real, la página renderiza. Solo que no es la página.
NETFLIX_404 = "https://www.netflix.com/NotFound?prev=https%3A%2F%2Fwww.netflix.com%2Fes-es%2FContactUs"


def test_a_sites_own_error_page_is_a_wall():
    assert "error" in tasks.wall_reason(NETFLIX_404)
    assert tasks.wall_reason("https://x.com/404")
    assert tasks.wall_reason("https://x.com/es/page-not-found")


def test_but_matched_as_a_whole_path_SEGMENT_and_never_as_a_substring():
    """«/notfound» es una página de error; «404 formas de cocinar huevos» no. Y la query se excluye a
    propósito: la URL medida arrastra `?prev=https://www.netflix.com/es-es/ContactUs`, así que buscar en la URL
    entera dispararía sobre la página BUENA de la que venía."""
    assert tasks.wall_reason("https://www.recetas.com/articles/404-ways-to-cook-eggs") == ""
    assert tasks.wall_reason("https://www.netflix.com/es-es/ContactUs") == ""
    assert tasks.wall_reason("https://www.thefork.es/restaurantes/madrid") == ""


def test_and_it_reaches_the_turn_as_a_BLOCKED_task():
    """Lo que de verdad cambia la conversación: con el hecho delante, el bloque deja de prometer que la tarea
    terminará sola (V2-185) — que es lo que sostenía «la página no se ha abierto del todo»."""
    tid = tasks.create("Cancelar la suscripción a Netflix")
    tasks.set_status(tid, "working")
    tasks.update_view(tid, url=NETFLIX_404)
    state = _live()
    assert "· MURO: " in state and "página de error" in state
    assert "ESTO ESTÁ BLOQUEADO" in state
    assert "te dará el resultado sola" not in state
