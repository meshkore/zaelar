"""V2-227 ámbito B — el caudal de progreso, en frases que entiende una persona.

Operator, 2026-08-20: «necesita ver EN TIEMPO REAL lo que está pasando: entro en esta web, aplico el filtro,
lanzo, tengo resultados, estoy paseando, estoy haciendo triaje». Siete minutos de pantalla en blanco es la
experiencia que se arregla, y no se arregla con más telemetría sino con telemetría que se lee.

La materia prima YA existía: V2-048 le dio a cada `tool_use` un `{where, action, target}`, así que la capa del
navegador sabía desde siempre que estaba en `booking.com`. Lo que no llegaba al operador era esa palabra — la
fase decía «abriendo una página…» con el host justo al lado. Aquí se prueba la mitad que convierte una cosa en
la otra, y que viaja por el carril que ya existe (B4).
"""
import pytest

from nucleo.workers import progress as P
from nucleo.workers.claude_session import _tool_phase


# ── B1: la frase nombra el SITIO y la COSA ───────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("cmd,expected", [
    ("-m nucleo.nav_cli navigate https://www.booking.com/searchresults?ss=Sevilla", "entrando en booking.com…"),
    ("-m nucleo.nav_cli click \"Buscar\"", "pulsando «Buscar»…"),
    ("-m nucleo.nav_cli type \"Sevilla\" --submit", "escribiendo «Sevilla»…"),
    ("-m nucleo.nav_cli scroll down", "recorriendo la página…"),
    ("-m nucleo.nav_cli extract --limit 14", "recogiendo lo que hay en la página…"),
    ("-m nucleo.mem_cli recall \"el coche del operador\"", "buscando «el coche del operador» en la memoria…"),
])
def test_a_bridge_command_becomes_a_sentence(cmd, expected):
    assert _tool_phase("Bash", {"command": cmd}) == expected


def test_the_web_search_says_WHAT_it_searched():
    assert _tool_phase("WebSearch", {"query": "hoteles 4 estrellas Sevilla"}) == "buscando «hoteles 4 estrellas Sevilla»…"


def test_a_snapshot_REF_is_never_shown_to_the_operator():
    """El navegador identifica los elementos por ref de snapshot (`ref12`), que es lo correcto para conducir la
    página y lo contrario de legible: «pulsando «ref12»» dice menos que «pulsando en la página» y además le
    enseña al operador nuestra fontanería."""
    assert _tool_phase("Bash", {"command": "-m nucleo.nav_cli click ref12"}) == "pulsando en la página…"


def test_the_url_is_reduced_to_its_HOST_even_when_it_arrives_decorated():
    """`_nav_target` entrega «→ https://…»; un `host_of` que solo entendiera una URL pelada devolvía la
    decoración entera, que es la cadena de desarrollador que el operador no tenía que leer nunca."""
    assert P.host_of("→ https://www.booking.com/searchresults?ss=Sevilla&checkin=2026-08-28") == "booking.com"
    assert P.host_of("Buscar") == "Buscar"          # el target de un clic es una etiqueta, no una dirección


def test_hbnote_still_sets_its_OWN_phase():
    """Sensibilidad, y el contrato que V2-048 dejó escrito: el reporte del worker es MÁS rico que cualquier cosa
    que podamos derivar de la tool, así que pisarlo con una fase genérica es perder información."""
    assert _tool_phase("Bash", {"command": "python -m nucleo.agent_report phase \"aplicando el filtro\""}) == ""


def test_an_unknown_tool_still_says_something():
    """Fail-open: una fase genérica es peor que una concreta y muchísimo mejor que ninguna — la tarjeta muda es
    justo el fallo que esto arregla."""
    assert _tool_phase("HerramientaQueNoConocemos", {}) != ""


# ── «lanzo, tengo resultados»: el hito que pidió por su nombre ───────────────────────────────────────────────
@pytest.mark.parametrize("n,expected", [
    (12, "12 resultados en la página"), (1, "1 resultado en la página"),
    (0, "sin resultados en esta página"),
])
def test_the_outcome_of_an_extraction_is_a_phase_too(n, expected):
    assert P.found(n) == expected


def test_ZERO_is_said_out_loud():
    """Esconderlo dejaría una página que no dio nada exactamente igual que una que no se llegó a leer, que es la
    familia de silencios que llevamos todo el día cerrando."""
    assert P.found(0) and "sin resultados" in P.found(0)


def test_the_browser_bridge_ACTUALLY_reports_it():
    """La mitad que lo convierte en conducta. Y por la puerta de `dispatch.session_phase`, la misma que usa
    `hbnote`: B4 dice que el caudal viaja por el carril que existe, nunca por uno paralelo.

    Casa por la LLAMADA y no por la expresión entera al carácter. La primera versión exigía
    `_say_phase(task_id, _progress.found(len(items)))` literal y se puso roja el 2026-08-20 cuando V2-234 pasó a
    contar los resultados CON NOMBRE en vez de las filas crudas — un cambio que no toca en absoluto lo que este
    test dice medir (que el puente reporte, y por el carril que existe). Es la misma trampa que ya se pagó en
    V2-222 con un assert de V2-199: un test pegado a la sintaxis convierte cualquier refactor en un falso rojo, y
    enseña a mirar para otro lado cuando el rojo sí importa. Qué se cuenta lo fija su propio nodo (4.31).
    """
    import inspect
    import re

    from widgets.navegador import act_api
    src = inspect.getsource(act_api)
    assert re.search(r"_say_phase\(task_id,\s*_progress\.found\(", src), "el puente tiene que REPORTAR la fase"
    assert "_d.session_phase(rec.task_id, phrase)" in inspect.getsource(act_api._say_phase)


# ── B2: una fase larga tiene que decir que sigue viva ────────────────────────────────────────────────────────
def test_a_long_phase_says_how_long():
    assert P.still_alive("recorriendo la página", 95) == "recorriendo la página — lleva 1 min"
    assert P.still_alive("leyendo la página…", 20) == "leyendo la página — lleva 20s"


def test_the_heartbeat_does_NOT_rewrite_the_phase():
    """Si el latido guardara su propio texto, el siguiente decoraría la decoración («… lleva 1 min — lleva 2
    min»). Se EMITE y no se guarda: el registro conserva la fase limpia."""
    import time as _t

    from nucleo import dispatch as d

    class _R:
        task_id, kind, phase, status, paused = "1", "web", "recorriendo la página", "running", False
        started = last_event_at = _t.time() - 40
        trace_id = ""
    rec = _R()
    d._SESSIONS["1"] = rec
    try:
        said = d.session_alive("1")
        assert "lleva" in said
        assert rec.phase == "recorriendo la página", "el latido pisó la fase del registro"
    finally:
        d._SESSIONS.pop("1", None)


@pytest.mark.parametrize("status,paused", [("done", False), ("cancelled", False), ("running", True)])
def test_nothing_that_is_not_WORKING_beats(status, paused):
    """Sensibilidad: un latido de una tarea acabada dice que sigue viva, que es exactamente la mentira que este
    día entero ha ido quitando del sistema. Y una PAUSADA (⏻ del operador) no está trabajando: no late."""
    import time as _t

    from nucleo import dispatch as d

    class _R:
        task_id, kind, phase, trace_id = "9", "web", "leyendo", ""
        started = last_event_at = _t.time() - 40
    rec = _R()
    rec.status, rec.paused = status, paused
    d._SESSIONS["9"] = rec
    try:
        assert d.session_alive("9") == ""
    finally:
        d._SESSIONS.pop("9", None)


def test_the_loop_beats_on_a_TIMER_not_every_tick():
    """El bucle corre a ~1 Hz. Sin la marca por tarea emitiría un latido por SEGUNDO y ahogaría el carril que el
    latido existe para hacer legible."""
    import inspect

    from nucleo import loop
    src = inspect.getsource(loop.Loop._supervise_workers if hasattr(loop, "Loop") else loop)
    assert "_BEAT_SECS" in src and "self._last_beat[tid] = now" in src
    assert loop._BEAT_SECS >= 5


def test_the_beat_is_forgotten_when_the_task_dies():
    """Un diccionario indexado por tarea que nadie poda es una fuga, y este bucle vive lo que vive el proceso."""
    import inspect

    from nucleo import loop
    assert "self._last_beat = {k: v for k, v in self._last_beat.items() if k in live_ids}" in inspect.getsource(loop)


# ── la doctrina, hecha test ──────────────────────────────────────────────────────────────────────────────────
def test_the_phrasing_knows_about_BRIDGES_and_not_about_errands():
    """Es un RECURSO: tiene que leerse igual para un hotel, para la lista de tareas de un cohete y para una casa
    en Los Ángeles. Sabe de navegador, memoria, widgets y ficheros; de encargos, nada."""
    # Se mira lo que el operador LEE —las frases del vocabulario— y no el fichero entero: los docstrings citan a
    # propósito los ejemplos del operador (hoteles, una casa en Los Ángeles, `ss=Sevilla` en una URL de muestra)
    # para decir que ninguno de ellos puede aparecer en una frase.
    said = " ".join([f(t) for table in P._SAY.values() for f in table.values() for t in ("", "X")]).lower()
    said += " " + " ".join(P._BY_WHERE.values()).lower()
    said += " " + " ".join([P.found(0), P.found(3), P.still_alive("leyendo", 30)]).lower()
    for domain in ("hotel", "restaurante", "coche", "casa", "vuelo", "wallapop", "sevilla", "booking"):
        assert domain not in said, f"«{domain}» en una frase de progreso: lo general convertido en atajo"
    # Y los LUGARES que conoce son puentes, no encargos.
    assert set(P._SAY) == {"navegador", "web", "memoria", "widget", "zaelar", "archivo", "codigo", "sistema"}
