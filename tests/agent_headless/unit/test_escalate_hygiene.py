"""What may become a TASK, and what may not (V2-118 ronda 2, 2026-08-18).

Two things the second run of `three-tasks-at-once` measured in the live task registry, both below the model:

  · Of the SEVEN tasks the registry recorded, THREE had «[SISTEMA] Brain worker · Tarea completada: …» as their
    goal — a worker spawned to "do" the previous worker's delivery message. Every escalation route has a
    fallback «if the model left `request` empty, use the turn text», and that text already carries the system
    note glued in front. Both channels keep an `operator_text` precisely to avoid this, and both say in their
    own comments that a note is «NUNCA parte de lo que el operador pidió» — the fallbacks just never used it.

  · Not a single task of kind `code` appeared across FOURTEEN turns, while the turn said «te cargo un juego de
    plataformas». `looks_like_create_widget` on that opening line is True and `_classify_kind` answers `code`,
    so nothing was ambiguous: the model simply called the tool once (for the report) and the widget request
    fell on the floor. The existing create-widget guard only fired when the turn had triggered NOTHING.
"""
from __future__ import annotations

from nucleo.flash import escalate, router_guards

_NOTE = "[SISTEMA] Brain worker · Tarea completada: No he podido encontrar monitores de segunda mano ≤150€"
_OPENING = ("Oye, tengo tres cosas. Hazme un informe sobre coches eléctricos para ciudad, búscame un monitor "
            "barato de segunda mano, y móntame un widget de un juego de plataformas tipo Super Mario.")


def test_a_system_note_is_stripped_from_a_task_goal():
    assert escalate.strip_system_notes(f"{_NOTE}\n\nVale, ¿qué tal lo llevas?") == "Vale, ¿qué tal lo llevas?"
    assert escalate.strip_system_notes(f"{_NOTE}\n[SISTEMA] otra\n\nhola") == "hola"


def test_a_turn_with_no_note_is_untouched():
    assert escalate.strip_system_notes(_OPENING) == _OPENING


def test_a_turn_that_is_ONLY_a_system_note_never_becomes_a_task(monkeypatch):
    """This is the worker-chasing-the-worker case: nothing the operator asked for is in there."""
    published: list = []
    monkeypatch.setattr(escalate, "_emit_bus", lambda topic, payload: published.append((topic, payload)))
    assert escalate.escalate_to_slowbrain(f"{_NOTE}\n") == 0
    assert published == []


def test_a_real_request_still_escalates_with_its_note_removed(monkeypatch):
    published: list = []
    monkeypatch.setattr(escalate, "_emit_bus", lambda topic, payload: published.append((topic, payload)))
    tid = escalate.escalate_to_slowbrain(f"{_NOTE}\n\nbúscame un monitor de segunda mano")
    assert tid > 0
    assert len(published) == 1
    topic, payload = published[0]
    assert topic == "escalate.requested"
    assert payload["request"] == "búscame un monitor de segunda mano"
    assert "[SISTEMA]" not in payload["request"]


# ── el hueco del guard de crear-widget ───────────────────────────────────────────────────────────────────
def test_the_opening_line_unambiguously_asks_to_build_a_widget():
    """Si esto fuera ambiguo, el backstop sería una adivinanza. No lo es: el clasificador determinista dice que
    sí, y el dispatcher lo mandaría al generador."""
    from nucleo import dispatch
    assert router_guards.looks_like_create_widget(_OPENING) is True
    assert dispatch._classify_kind(_OPENING) == "code"


def test_the_three_requests_split_into_three_different_kinds():
    """Lo que el caso pide medir: concurrencia REAL de kinds distintos. Cada petición por separado tiene su
    destino correcto — el fallo nunca fue de clasificación, fue que dos de las tres no llegaban a lanzarse."""
    from nucleo import dispatch
    assert dispatch._classify_kind("Investiga y redacta un informe sobre coches eléctricos para ciudad") == "generic"
    assert dispatch._classify_kind("Busca en Wallapop monitores baratos de segunda mano") == "web"
    assert dispatch._classify_kind("Monta un widget de un juego de plataformas tipo Super Mario") == "code"


def test_a_request_that_already_covers_the_widget_needs_no_backstop():
    """El backstop solo rellena un hueco: si el modelo YA pidió el widget, no se duplica."""
    assert router_guards.looks_like_create_widget("Monta un widget de un juego de plataformas") is True
    assert router_guards.looks_like_create_widget("Investiga coches eléctricos para ciudad") is False


# ── V2-155: el backstop detectaba el widget y el DEDUP se lo comía ────────────────────────────────────────
#
# Ronda del 18:10 sobre `three-tasks-at-once`: `max_concurrent=2`, `distinct_kinds=['web']` — la tercera tarea
# nunca existió, y zaelar acabó diciendo «no me consta que hayas pedido un juego». El backstop de V2-118 SÍ
# disparaba (`looks_like_create_widget(_OPENING)` es True, arriba). Lo que hacía era añadir el TURNO ENTERO como
# petición, y un turno que encarga tres cosas lleva las otras dos dentro: con «informe» en la frase,
# `dispatch._target_widget` le da destino `results` —el mismo que la tarea del informe— y `find_duplicate` la
# descarta por su señal MÁS FUERTE, la de mismo widget destino. Se detectaba y se deduplicaba contra la tarea
# con la que tenía que convivir.
_GOAL_INFORME = ("Elaborar un informe detallado sobre coches eléctricos para ciudad: autonomía, precio, "
                 "tamaño compacto, facilidad de aparcamiento y carga.")


class _Live:
    def __init__(self, goal):
        self.goal, self.status = goal, "running"


def test_the_backstop_appends_only_the_clause_that_asks_for_the_widget():
    got = router_guards.create_widget_request(_OPENING)
    assert "Super Mario" in got
    assert "informe" not in got.lower()
    assert "monitor" not in got.lower()


def test_and_that_is_what_stops_the_report_from_swallowing_it(monkeypatch):
    """La prueba de que el recorte no es cosmético: es exactamente lo que cambia el veredicto del dedup.

    V2-158 — la primera versión de este test leía el catálogo de widgets REAL a través de `_target_widget`, y una
    corrida en vivo que crea un widget (`widgets/juego-plataformas-tipo/` apareció y desapareció durante la
    tanda) cambiaba el resultado: verde con orden fijo, rojo con orden aleatorio. Un test de regresión no puede
    depender de qué widgets haya en disco cuando corre. Se fija el mapeo MEDIDO en la corrida —turno entero →
    `results`, cláusula del juego → sin destino— y se comprueba lo único que este arreglo cambia: la ENTRADA que
    recibe `find_duplicate`."""
    from nucleo import dispatch
    measured = {_OPENING: "results", _GOAL_INFORME: "results"}
    monkeypatch.setattr(dispatch, "_target_widget", lambda t: measured.get(t, ""))
    monkeypatch.setattr(dispatch, "_SESSIONS", {"informe": _Live(_GOAL_INFORME)})
    assert dispatch.find_duplicate(_OPENING, "code") == "informe"              # lo que corría antes
    assert dispatch.find_duplicate(router_guards.create_widget_request(_OPENING), "code") is None


def test_a_lone_widget_request_is_untouched():
    """Sin separadores no hay nada que recortar: el comportamiento de siempre no cambia."""
    assert router_guards.create_widget_request("móntame un widget de la bolsa") == "móntame un widget de la bolsa"


def test_and_a_turn_that_asks_for_no_widget_yields_nothing():
    assert router_guards.create_widget_request("búscame un monitor barato de segunda mano") == ""
    assert router_guards.create_widget_request("") == ""
