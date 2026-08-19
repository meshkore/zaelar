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
