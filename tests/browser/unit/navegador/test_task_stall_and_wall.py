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
    assert "ESTÁ BLOQUEADA: lo que pone arriba de ella" in state


def test_and_neither_is_one_that_stopped_moving():
    tid = tasks.create("Reservar mesa")
    tasks.set_status(tid, "working")
    tasks.update_view(tid, url=REAL_PAGE)
    tasks._tasks[tid]["last_progress"] = time.time() - 673
    state = _live()
    assert "te dará el resultado sola" not in state
    assert "ESTÁ BLOQUEADA: lo que pone arriba de ella" in state


def test_but_a_healthy_task_keeps_the_promise_AND_the_rule_of_V2_152():
    """La sensibilidad, y no es teórica: V2-152 existe porque empujar a parar una tarea sana por falta de
    novedades es un daño REAL y medido. Esa regla no se toca — solo deja de aplicarse donde es mentira."""
    tid = tasks.create("Buscar hotel en Burgos")
    tasks.set_status(tid, "working")
    tasks.update_view(tid, url="https://www.booking.com/searchresults.html?ss=Burgos")
    state = _live()
    assert "te dará el resultado sola" in state
    assert "la falta de parte no significa que esté parada" in state
    assert "ESTÁ BLOQUEADA: lo que pone arriba de ella" not in state


def test_and_the_shared_rules_survive_in_BOTH_states():
    """Lo que es cierto en los dos casos tiene que estar en los dos: un solo navegador, y nunca describir lo que
    la tarea «estaría haciendo». Partir un bloque en dos es justo como se pierde una regla por el camino."""
    for url, walled in ((LOAD_ERROR, True), ("https://www.booking.com/searchresults.html?ss=Burgos", False)):
        tasks._tasks.clear()
        tid = tasks.create("Buscar hotel")
        tasks.set_status(tid, "working")
        tasks.update_view(tid, url=url)
        state = _live()
        assert ("ESTÁ BLOQUEADA: lo que pone arriba de ella" in state) is walled
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
    assert "ESTÁ BLOQUEADA: lo que pone arriba de ella" in state
    assert "te dará el resultado sola" not in state


# ── V2-176 frente 3: esperar a que entre ÉL es lo más parecido a un muro que hay ──────────────────────────
#
# El paraguas lo nombra como el frente más prometedor: «esto necesita tu cuenta, no puedo seguir» es una
# respuesta EXCELENTE, y hoy el agente prefiere inventarse el login. La pieza que faltaba no era detectarlo
# —`awaiting_login` existe, lo escribe el flujo de login real y `active_progress()` lo expone desde V2-167—
# sino que **`prompt.py` no lo leía nunca**. Así que una tarea parada en el login convivía con «Esa tarea
# sigue viva y te dará el resultado sola»: el operador esperando a la tarea, y la tarea esperándole a él.
#
# Es el mismo fallo que V2-185 con la salida cambiada: aquí no hay que ofrecer otro sitio ni dejarlo — hay que
# decirle que entre.
def _awaiting(tid):
    tasks._tasks[tid]["awaiting_login"] = True


def test_a_task_waiting_for_the_operator_to_sign_in_is_not_promised_to_finish_alone():
    tid = tasks.create("Cancelar la suscripción a Netflix")
    tasks.set_status(tid, "working")
    tasks.update_view(tid, url="https://www.netflix.com/login")
    _awaiting(tid)
    state = _live()
    assert "te dará el resultado sola" not in state
    assert "PARADA ESPERANDO A QUE ENTRES TÚ" in state


def test_and_its_way_out_is_that_HE_signs_in_not_that_we_give_up():
    """La salida de un muro es «otro sitio, que entre él, o dejarlo». La de un login es UNA sola cosa, y decir
    «lo dejamos» sobre algo que solo falta que él teclee sería el consejo equivocado."""
    tid = tasks.create("Cancelar la suscripción")
    tasks.set_status(tid, "working")
    tasks.update_view(tid, url="https://www.netflix.com/login")
    _awaiting(tid)
    state = _live()
    assert "SOLO LA DESBLOQUEA ÉL" in state
    assert "NO es un fracaso" in state              # pararse en su login es la conducta CORRECTA
    assert "ESTÁ BLOQUEADA: lo que pone arriba de ella" not in state       # y no se le da la salida genérica del muro


def test_and_it_is_said_even_if_the_operator_just_said_he_would_wait():
    """El patrón medido en dos casos: «vale, espero» → «sigo con ello». Esperar es justo lo que hará si te
    callas, y aquí la espera no se resuelve sola NUNCA."""
    tid = tasks.create("Renovar la cuota del gimnasio")
    tasks.set_status(tid, "working")
    tasks.update_view(tid, url="https://basic-fit.com/login")
    _awaiting(tid)
    assert "aunque acabe de decir que espera tranquilo" in _live()


def test_but_a_task_that_is_NOT_waiting_on_him_keeps_the_promise():
    tid = tasks.create("Buscar hotel")
    tasks.set_status(tid, "working")
    tasks.update_view(tid, url="https://www.booking.com/searchresults.html")
    state = _live()
    assert "te dará el resultado sola" in state
    assert "ESPERANDO A QUE ENTRES TÚ" not in state


def test_and_a_login_wait_wins_over_a_wall_on_the_same_task():
    """Si además la URL parece un muro, lo que falta sigue siendo que entre él: darle dos salidas distintas
    para la misma pantalla es lo que hace que no tome ninguna."""
    tid = tasks.create("Cancelar la suscripción")
    tasks.set_status(tid, "working")
    tasks.update_view(tid, url="https://www.netflix.com/NotFound")
    _awaiting(tid)
    state = _live()
    assert "SOLO LA DESBLOQUEA ÉL" in state
    assert "ESTÁ BLOQUEADA: lo que pone arriba de ella" not in state


# ── V2-192: tener RESULTADOS gana a cualquier medida de atasco ────────────────────────────────────────────
#
# REGRESIÓN PROPIA, medida el 2026-08-20 02:22 en `find-theatre-tickets__es`, con mis arreglos de esta noche
# ya dentro: «Zaelar ocultó al usuario que había encontrado datos reales y afirmó falsamente que la tarea
# estaba paralizada, resultando en una experiencia de "bla bla bla" sin valor entregado».
#
# Un worker que encuentra los datos y hace una pausa —extrayendo, componiendo, esperando— cruza los 120 s sin
# cambiar de URL, y V2-185 lo declaraba BLOQUEADO. Antes de V2-185 el estado era demasiado OPTIMISTA («te dará
# el resultado sola»); con V2-185 pasó a ser demasiado PESIMISTA. Las dos son falsas cuando lo cierto es que
# ya hay algo que entregar, y la segunda es peor: la primera hace esperar, ésta tira a la basura un resultado
# que ya estaba hecho.
def test_a_task_that_already_found_something_is_not_blocked():
    tid = tasks.create("Entradas El Rey León en Madrid")
    tasks.set_status(tid, "working")
    tasks.update_view(tid, url=REAL_PAGE)
    tasks.set_results(tid, {"conclusion": "3 sesiones", "items": [{"t": "sáb 17:00"}]})
    tasks._tasks[tid]["last_progress"] = time.time() - 400          # y encima lleva 6 min sin moverse
    state = _live()
    assert "YA TIENE RESULTADOS" in state
    assert "ESTÁ BLOQUEADA: lo que pone arriba de ella" not in state
    assert "DÁSELOS en este turno" in state


def test_and_results_win_over_a_WALL_too():
    """Un muro con los datos ya en la mano no es un muro: es una entrega pendiente."""
    tid = tasks.create("Reservar hotel")
    tasks.set_status(tid, "working")
    tasks.update_view(tid, url=BOOKING_WALL)
    tasks.set_results(tid, {"conclusion": "2 hoteles", "items": [{"n": "uno"}]})
    state = _live()
    assert "YA TIENE RESULTADOS" in state
    assert "ESTÁ BLOQUEADA: lo que pone arriba de ella" not in state


def test_but_without_results_a_stall_is_still_a_stall():
    """La sensibilidad, y es la que impide que este arreglo deshaga V2-185: sin nada que entregar, un atasco
    medido sigue siendo un hecho que hay que decir."""
    tid = tasks.create("Reservar mesa")
    tasks.set_status(tid, "working")
    tasks.update_view(tid, url=REAL_PAGE)
    tasks._tasks[tid]["last_progress"] = time.time() - 400
    state = _live()
    assert "ESTÁ BLOQUEADA: lo que pone arriba de ella" in state
    assert "YA TIENE RESULTADOS" not in state


def test_and_the_seam_carries_the_fact():
    """`active_progress()` es el sitio por el que la tarea le habla al turno; el dato no existía ahí, así que
    el turno solo podía elegir entre «sigue viva» y «está bloqueada»."""
    tid = tasks.create("Buscar hotel")
    tasks.set_status(tid, "working")
    tasks.update_view(tid, url=REAL_PAGE)
    assert tasks.active_progress()[0]["has_results"] is False
    tasks.set_results(tid, {"items": [1]})
    assert tasks.active_progress()[0]["has_results"] is True


# ── V2-193: con varias tareas vivas, el imperativo tiene que decir CUÁL ───────────────────────────────────
#
# `renew-gym-membership__es`, 2026-08-20 02:28: «desviaciones de atención severas (distracción con tareas de
# navegador no solicitadas) … mezclando dominios (Netflix/Teatro) al preguntar por el gimnasio».
#
# El bloque listaba las tres tareas correctamente y luego soltaba UN imperativo que empezaba por «ESA TAREA»
# — sin decir cuál. Con tres en marcha eso apunta a cualquiera, y el estado acababa MANDANDO entregar los
# resultados del teatro mientras el operador preguntaba por su gimnasio. Con una sola tarea la ambigüedad no
# existe, que es por lo que las cuatro caras se escribieron sin verla.
def _three_live():
    a = tasks.create("Cancelar la suscripción a Netflix")
    tasks.set_status(a, "working")
    tasks.update_view(a, url="https://www.netflix.com/login")
    tasks._tasks[a]["awaiting_login"] = True
    b = tasks.create("Entradas El Rey León")
    tasks.set_status(b, "working")
    tasks.update_view(b, url="https://www.entradas.com/el-rey-leon")
    tasks.set_results(b, {"items": [1]})
    c = tasks.create("Renovar cuota del gimnasio")
    tasks.set_status(c, "working")
    return a, b, c


def test_the_imperative_names_the_task_it_is_about():
    _three_live()
    state = _live()
    assert "«Entradas El Rey León» YA TRAJO ALGO" in state
    assert "ESA TAREA YA TRAJO ALGO" not in state       # la forma ambigua que medía el veredicto


def test_and_the_other_tasks_keep_their_FACTS_without_a_second_order():
    """Los hechos de las demás siguen ahí —el operador puede preguntar por cualquiera— pero no se emiten tres
    órdenes a la vez: un turno con cuatro imperativos es un volcado de estado, no una respuesta."""
    _three_live()
    state = _live()
    assert "PARADA ESPERANDO A QUE ENTRES TÚ" in state          # el hecho del Netflix, listado
    assert state.count("DÁSELOS en este turno") == 1
    assert "SOLO LA DESBLOQUEA ÉL" not in state                 # …pero sin su propio imperativo


def test_a_blocked_task_also_says_which_one():
    tid = tasks.create("Reservar mesa en Casa Lucio")
    tasks.set_status(tid, "working")
    tasks.update_view(tid, url=BOOKING_WALL)
    state = _live()
    assert "«Reservar mesa en Casa Lucio» ESTÁ BLOQUEADA" in state


def test_and_a_login_wait_too():
    tid = tasks.create("Cancelar la suscripción a Netflix")
    tasks.set_status(tid, "working")
    tasks.update_view(tid, url="https://www.netflix.com/login")
    tasks._tasks[tid]["awaiting_login"] = True
    state = _live()
    assert "«Cancelar la suscripción a Netflix» ESTÁ PARADA Y SOLO LA DESBLOQUEA ÉL" in state


# ── V2-196: una tarea CANCELADA caía en un hueco perfecto ─────────────────────────────────────────────────
#
# `find-theatre-tickets__es`, 2026-08-20 03:11: «el asistente alucina el estado de progreso y desconecta por
# completo de la realidad del sistema (**status cancelled**), manteniendo al usuario en un bucle de espera
# infinito sobre una tarea que ya falló».
#
# `cancelled` era el ÚNICO final que no estaba en ningún sitio: `active_summaries()` filtra por
# queued/working/needs_input, y `recently_finished()` filtraba por done/failed. O sea que el estado no la
# mencionaba EN ABSOLUTO —ni viva ni terminada— y el modelo seguía con lo último que recordaba, que era
# haberla arrancado.
#
# Cuarta vez esta noche del mismo patrón: V2-150 (la tarea que TERMINA), V2-190 (la confirmación que CADUCA),
# V2-176 f2 (la acción DESCARTADA) y ésta. Un hecho que no está en ningún sitio es un hecho que la
# conversación sustituye por su propia memoria.
def test_a_cancelled_task_does_not_vanish_from_the_state():
    tid = tasks.create("Entradas El Rey León en Madrid")
    tasks.set_status(tid, "working")
    tasks.update_view(tid, url="https://www.entradas.com/el-rey-leon")
    tasks.cancel(tid)
    assert tasks.active_summaries() == []                       # ya no está viva…
    assert [r["id"] for r in tasks.recently_finished()] == [tid]  # …pero SÍ es un final
    assert "NAVEGADOR — YA TERMINADO" in _live()


def test_and_it_says_that_it_was_STOPPED_not_that_it_finished_empty():
    """Pararse no es acabar. «Terminó sin traer nada» sobre algo que se canceló invita a esperar un resultado
    que nadie va a producir; decir que se paró invita a preguntar si se retoma, que es lo que el operador
    puede hacer con ese hecho."""
    tid = tasks.create("Entradas El Rey León")
    tasks.set_status(tid, "working")
    tasks.cancel(tid)
    state = _live()
    assert "se PARÓ (cancelada) sin llegar a terminar" in state
    assert "terminó SIN traer nada" not in state


def test_but_a_task_that_really_finished_empty_still_says_so():
    """La sensibilidad: son dos hechos distintos y tienen que seguir sonando distinto."""
    tid = tasks.create("Buscar hotel")
    tasks.set_status(tid, "working")
    tasks.finish(tid, "done", "")
    state = _live()
    assert "terminó SIN traer nada" in state
    assert "se PARÓ (cancelada)" not in state


def test_and_one_that_finished_WITH_results_too():
    tid = tasks.create("Buscar hotel")
    tasks.set_status(tid, "working")
    tasks.set_results(tid, {"items": [1]})
    tasks.finish(tid, "done", "2 hoteles")
    assert "terminó CON resultado" in _live()


# ── V2-200: la cara «YA TIENE RESULTADOS» estaba atada a un campo que nunca es cierto en vivo ─────────────
#
# V2-192 la ató a `results` de la propia tarea. Pero los TRES sitios que llaman a `set_results()` llaman a
# `finish()` acto seguido —`owner.py:660`, `dispatch._finalize_web`, `web_cc`— así que **una tarea ACTIVA con
# resultados no existe en producción**. Sus cuatro tests pasaban porque creaban ese estado a mano.
#
# Es el mismo fallo de V2-199 encontrado con el mismo método —comprobar contra el camino real en vez de contra
# el que uno imaginó— y esta vez el arreglo anterior no estaba roto: estaba MUERTO.
#
# La señal viva de que el worker ya encontró algo sí existe, en el otro registro: la amplitud que él mismo
# reporta (`hbnote considered --kept N`), leída por el seam que ya enlazaba los dos (`record_by_nav_task`).
def _worker_on(nav_tid, *, kept=0):
    from nucleo import dispatch as _d

    rec = _d.SessionRecord(task_id="w9", goal="x", kind="web")
    rec.status, rec.nav_task = "running", nav_tid
    _d._SESSIONS["w9"] = rec
    if kept:
        _d.session_considered("w9", considered=kept * 4, kept=kept)
    return _d


def test_no_production_path_leaves_an_ACTIVE_task_with_results():
    """La aserción que habría evitado V2-192 tal y como se escribió: se recorre el código y se exige que cada
    `set_results()` vaya seguido de un final. Si algún día deja de ser cierto, esta cara se puede volver a
    atar al campo directamente — pero que sea una decisión, no una suposición."""
    import re
    from pathlib import Path

    root = Path(__file__).resolve().parents[4]
    for rel in ("widgets/navegador/owner.py", "nucleo/dispatch.py", "nucleo/agentes/web_cc.py"):
        src = (root / rel).read_text(encoding="utf-8", errors="replace")
        for m in re.finditer(r"set_results\(", src):
            after = src[m.end():m.end() + 700]
            assert re.search(r"\.finish\(|set_status\([^)]*\"(done|failed|cancelled)\"", after), (
                f"{rel}: un `set_results()` que NO termina la tarea a continuación. Si eso pasa a ser posible, "
                "la cara «YA TIENE RESULTADOS» puede volver a leer `has_results` en vez de la amplitud viva.")


def test_the_face_now_fires_on_the_LIVE_signal(monkeypatch):
    tid = tasks.create("Entradas El Rey León")
    tasks.set_status(tid, "working")
    tasks.update_view(tid, url=REAL_PAGE)
    tasks._tasks[tid]["last_progress"] = time.time() - 400        # y encima atascada
    d = _worker_on(tid, kept=3)
    try:
        state = _live()
        assert "YA TIENE RESULTADOS" in state
        assert "ESTÁ BLOQUEADA: lo que pone arriba de ella" not in state
    finally:
        d._SESSIONS.clear()


def test_but_a_worker_with_NOTHING_yet_leaves_the_stall_alone():
    """La sensibilidad, y es la que impide deshacer V2-185: sin finalistas, un atasco medido sigue siendo un
    atasco. `kept` a 0 —o no saber— significa «no», nunca «sí»."""
    tid = tasks.create("Reservar mesa")
    tasks.set_status(tid, "working")
    tasks.update_view(tid, url=REAL_PAGE)
    tasks._tasks[tid]["last_progress"] = time.time() - 400
    d = _worker_on(tid, kept=0)
    try:
        assert "ESTÁ BLOQUEADA: lo que pone arriba de ella" in _live()
    finally:
        d._SESSIONS.clear()


def test_and_with_no_worker_at_all_nothing_changes():
    tid = tasks.create("Reservar mesa")
    tasks.set_status(tid, "working")
    tasks.update_view(tid, url=REAL_PAGE)
    tasks._tasks[tid]["last_progress"] = time.time() - 400
    assert "ESTÁ BLOQUEADA: lo que pone arriba de ella" in _live()


# ── el muro que vive en el CUERPO, no en la URL (V2-167, segunda mitad) ────────────────────────────────────
# Medido en una corrida REAL del caso del teatro el 2026-08-19: `entradas.com` contestó la página del evento
# con un «Access Denied» de detección de bots de Akamai. URL normal, status normal, `wall_reason()` ciego. El
# worker lo leyó del snapshot y se re-enrutó solo —así que la tarea NO se atascó— y por eso el agujero llevaba
# invisible: la única prueba de que existía era que el operador no vio nada.
#
# El texto de abajo es la forma de esa página (214 caracteres), no un ejemplo inventado.
AKAMAI_DENIED = ("Access Denied\n\nYou don't have permission to access \"http://www.entradas.com/teatro-musical/"
                 "el-rey-leon-t3328\" on this server.\n\nReference #18.5c7d4f17.1787159442.2b1e9c3\n\n"
                 "https://errors.edgesuite.net/18.5c7d4f17.1787159442.2b1e9c3")
CLOUDFLARE_WAIT = ("Just a moment...\n\nChecking your browser before accessing entradas.com.\n\n"
                   "Please enable JavaScript and cookies to continue.\n\nRay ID: 8f2a1c9d4e7b")


def test_the_body_served_wall_that_was_measured_is_recognised():
    assert tasks.body_wall_reason(AKAMAI_DENIED)
    assert tasks.body_wall_reason(CLOUDFLARE_WAIT)


def test_the_url_of_that_same_page_says_nothing():
    """Es la razón de existir de esta mitad: la URL del muro medido es una URL perfectamente buena, y el
    predicado de URL tiene razón en callarse. Si algún día `wall_reason` empezara a acertar aquí, sería porque
    alguien la ensanchó para leer texto — que es justo lo que este módulo decidió no hacer."""
    assert tasks.wall_reason("https://www.entradas.com/teatro-musical/el-rey-leon-t3328") == ""


def test_a_long_page_that_merely_TALKS_about_being_blocked_is_not_a_wall():
    """El riesgo que V2-167 dejó escrito: «no declarar muro sobre cualquier página que mencione la palabra».
    La defensa es la LONGITUD, así que hay que probarla con un artículo de verdad, largo y con la aguja
    dentro."""
    article = ("Cómo evitar que te bloqueen al comprar entradas online. " * 40
               + " Muchos usuarios reciben un Access Denied o un mensaje de unusual traffic al intentar "
                 "comprar, y algunas webs piden resolver un captcha. " + "Sigue leyendo. " * 40)
    assert len(article) > tasks._WALL_BODY_MAX_CHARS
    assert tasks.body_wall_reason(article) == ""


def test_an_ordinary_short_page_is_not_a_wall_either():
    assert tasks.body_wall_reason("") == ""
    assert tasks.body_wall_reason("El Rey León · Teatro Lope de Vega, Madrid · Sábado 20:30 · Desde 39 €") == ""
    assert tasks.body_wall_reason("Casa Lucio. Reserva tu mesa. Cava Baja 35, Madrid.") == ""


def test_the_body_reason_is_also_said_in_words_the_operator_can_hear():
    for text in (AKAMAI_DENIED, CLOUDFLARE_WAIT):
        reason = tasks.body_wall_reason(text)
        assert "Reference #" not in reason and "Ray ID" not in reason and "http" not in reason
        assert len(reason.split()) >= 3


def test_the_task_carries_a_body_served_wall_like_any_other():
    """La prueba que importa: el estado del turno tiene que enterarse. Antes de esto la tarjeta no se abría y
    el operador no veía nada, aunque el worker sí lo supiera."""
    tid = tasks.create("conseguir entradas para El Rey León")
    tasks.set_status(tid, "working")
    tasks.update_view(tid, url="https://www.entradas.com/teatro-musical/el-rey-leon-t3328",
                      page_title="Access Denied", page_text=AKAMAI_DENIED)
    assert tasks.active_progress()[0]["wall"]


def test_and_it_drops_the_wall_when_the_next_page_is_real():
    tid = tasks.create("conseguir entradas")
    tasks.set_status(tid, "working")
    tasks.update_view(tid, url="https://www.entradas.com/teatro-musical/el-rey-leon-t3328",
                      page_text=AKAMAI_DENIED)
    assert tasks.active_progress()[0]["wall"]
    tasks.update_view(tid, url="https://www.ticketmaster.es/artist/el-rey-leon-entradas/4043",
                      page_text="El Rey León. Teatro Lope de Vega. Entradas desde 39 €.")
    assert tasks.active_progress()[0]["wall"] == ""


def test_a_caller_that_has_no_text_keeps_the_url_only_behaviour():
    """Nadie más que la pestaña tiene el cuerpo. Omitir el texto no puede cambiar nada de lo que ya funcionaba,
    ni borrar un muro que la URL sí ve."""
    tid = tasks.create("reservar hotel")
    tasks.set_status(tid, "working")
    tasks.update_view(tid, url=BOOKING_WALL)
    tid2 = tasks.create("otra")
    tasks.set_status(tid2, "working")
    tasks.update_view(tid2, url=REAL_PAGE)
    walls = {r["id"]: r["wall"] for r in tasks.active_progress(limit=9)}
    assert walls[tid], "un muro que la URL ve no puede depender de que le pasen texto"
    assert walls[tid2] == ""


def test_the_peek_size_is_bigger_than_the_gate_that_judges_it():
    """El trampa silenciosa de este arreglo, y la única que invierte la defensa: si quien lee el cuerpo corta
    justo en el límite, un artículo de 50k llega «corto» y la puerta de longitud pasa TODAS las páginas. Por eso
    el tamaño de lectura vive aquí y no en el llamante."""
    assert tasks.WALL_BODY_PEEK_CHARS > tasks._WALL_BODY_MAX_CHARS
    long_article = "Access Denied. " + ("texto de relleno de un artículo real. " * 400)
    truncated_correctly = long_article[:tasks.WALL_BODY_PEEK_CHARS]
    assert tasks.body_wall_reason(truncated_correctly) == ""


def test_the_tab_capture_is_the_one_that_reads_the_body():
    """Guarda de nivel de fuente: el muro del cuerpo solo llega al registro si la pestaña se lo pasa. Un
    predicado nuevo que nadie llama es un arreglo muerto — esta noche ya han aparecido dos."""
    import inspect
    from widgets.navegador import owner
    src = inspect.getsource(owner.TaskBrowser._capture)
    assert "WALL_BODY_PEEK_CHARS" in src, "la pestaña dejó de leer el cuerpo"
    assert "page_text=" in src, "la pestaña lee el cuerpo pero no lo pasa al registro"
