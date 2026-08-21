"""DOS búsquedas son DOS hojas — y el arnés tiene que poder CONTAR las cajas, no solo mirar dentro de una.

Regla del operador (2026-08-21): dos encargos a la vez son dos navegadores y dos hojas de resultados, cada una
con su correlation_id; y una hoja terminada NO se reutiliza para el encargo siguiente. El motivo es que
reutilizar la caja BORRA una búsqueda, y una búsqueda borrada no se recupera.

`widget_ops` no puede contestar a esto y no es un descuido suyo: colapsa la instancia a propósito
(`raw.split("::")[0]`) porque la pregunta que contesta es «qué widget se tocó». Aquí la pregunta es «cuántas
CAJAS hubo del mismo widget», y colapsar la instancia la borra — diría «results tocado 9 veces» tanto con una
hoja como con tres, y esa respuesta es igual de creíble en los dos casos.

HOY el motor abre UNA sola hoja (`dispatch._sheet_open()` emite el id pelado y `widgets/results/data.py`
guarda en una clave), así que el lector devuelve `shared: true` — que es la firma exacta del defecto y lo que
convierte la regla de producto en un hecho comprobable. El día que la instanciación aterrice, el mismo lector
devuelve 2 sin tocar una línea.
"""
from __future__ import annotations

from tests.use_cases.e2e.agent import scenarios as SC, verify as V


def _ev(wid: str, label: str = "show", src: str = "") -> dict:
    """La forma REAL del evento, no una inventada: `observer.emit` hace `ev.update(extra)`, así que `id` y
    `src` aterrizan PLANOS en el payload, y el payload llega como cadena JSON desde la API."""
    import json
    return {"payload": json.dumps({"cat": "widget", "label": label, "id": wid, "src": src})}


# ── lo que el motor hace HOY ────────────────────────────────────────────────────────────────────────────
def test_one_box_for_two_errands_is_reported_as_SHARED():
    got = V.sheet_instances([_ev("results", src="worker:t1"), _ev("results", src="worker:t2")])
    assert got["n_sheets"] == 1
    assert got["n_errands"] == 2
    assert got["shared"] is True


def test_reopening_the_same_sheet_is_not_a_second_sheet():
    """Lo que se cuenta son CAJAS, no aperturas. Volver a mostrar la misma hoja no abre ninguna nueva, y
    contar aperturas daría 3 cajas para un solo encargo."""
    got = V.sheet_instances([_ev("results", src="worker:t1")] * 3)
    assert got["n_sheets"] == 1
    assert got["n_opens"] == 3
    assert got["n_errands"] == 1
    assert got["shared"] is False


# ── lo que tiene que dar cuando la pieza exista ────────────────────────────────────────────────────────
def test_two_instances_are_two_sheets_and_carry_their_errand():
    got = V.sheet_instances([_ev("results::c1", src="worker:t1"), _ev("results::c2", src="worker:t2")])
    assert got["n_sheets"] == 2
    assert got["ids"] == ["results::c1", "results::c2"]
    assert got["n_errands"] == 2
    assert got["shared"] is False


def test_a_finished_sheet_is_not_reused_by_the_next_errand():
    """La segunda mitad de la regla: hoja cerrada + encargo nuevo = caja NUEVA, nunca la de antes."""
    got = V.sheet_instances([_ev("results::c1", src="worker:t1"),
                             _ev("results::c1", label="close"),
                             _ev("results::c2", src="worker:t2")])
    assert got["n_sheets"] == 2
    assert got["n_closes"] == 1
    assert got["shared"] is False


# ── contrapesos: lo que NO debe contar ─────────────────────────────────────────────────────────────────
def test_other_widgets_are_not_sheets():
    """SENSIBILIDAD, y es el lado por el que este lector se rompe de más: `navegador::t3` lleva `::` y es
    del MISMO flujo. Un prefijo mal casado convertiría cada pestaña del navegador en una hoja."""
    got = V.sheet_instances([_ev("navegador::t3", src="worker:t1"), _ev("results", src="worker:t1"),
                             _ev("resultados-viejos", src="worker:t2")])
    assert got["ids"] == ["results"]
    assert got["n_sheets"] == 1


def test_an_errand_with_no_src_does_not_invent_one():
    """Sin `src` no se sabe de qué encargo salió la apertura, y un encargo inventado es lo que haría que
    UNA búsqueda pareciera dos compartiendo caja — el defecto reportado al revés."""
    got = V.sheet_instances([_ev("results"), _ev("results")])
    assert got["n_errands"] == 0
    assert got["shared"] is False


def test_a_stream_with_no_widget_events_says_nothing():
    got = V.sheet_instances([{"payload": '{"cat": "worker", "label": "start"}'}, "no soy un dict"])
    assert got == {"n_sheets": 0, "ids": [], "n_opens": 0, "n_errands": 0, "srcs": [], "shared": False,
                   "n_closes": 0}


# ── el lector viaja en el informe de mecanismo, que es lo que lee el juez ───────────────────────────────
def test_the_reader_reaches_the_mechanism_report(monkeypatch):
    monkeypatch.setattr(V, "results_sheet", lambda: {"read": False, "n_items": 0, "titles": [],
                                                     "n_sources": 0})
    monkeypatch.setattr(V, "find_navegador_task_id", lambda _e: "")
    mech = V.mechanism_report([_ev("results", src="worker:t1"), _ev("results", src="worker:t2")], [])
    assert mech["sheet_instances"]["shared"] is True


def test_the_report_names_the_shared_box(tmp_path):
    """El informe que se LEE tiene que decirlo: un hecho que solo vive en el JSON no lo lee el que arregla."""
    from tests.use_cases.e2e.agent import report as reportmod
    mech = {"sheet_instances": {"n_sheets": 1, "ids": ["results"], "n_opens": 2, "n_errands": 2,
                                "srcs": ["worker:t1", "worker:t2"], "shared": True, "n_closes": 0}}
    md = reportmod.build([{"scenario": "x", "tier": 4, "channel": "probe",
                           "run": {"mechanism_report": mech, "transcript": []},
                           "verdict": {"scores": {}, "overall": 3, "findings": [], "improvements": []}}],
                         "stamp", tmp_path)
    text = md.read_text(encoding="utf-8")
    assert "hojas de resultados ABIERTAS: 1 caja(s) para 2 encargo(s)" in text
    assert "DOS ENCARGOS COMPARTIERON CAJA" in text


def test_the_judge_is_told_it_is_a_mechanism_fact_not_a_confused_agent():
    from tests.use_cases.e2e.agent import judge as J
    facts = J.mechanism_facts({"families_observed": ["worker"],
                               "sheet_instances": {"n_sheets": 1, "n_errands": 2, "shared": True}})
    assert "COMPARTIERON UNA SOLA HOJA" in facts
    assert "no lo cuentes como que zaelar se" in facts


# ── el escenario ───────────────────────────────────────────────────────────────────────────────────────
def test_the_scenario_asks_for_the_ambiguous_close():
    """Sin la orden ambigua el caso mediría concurrencia y nada más — el cierre ES la mitad del encargo."""
    s = SC.BY_ID["two-searches-two-sheets"]
    assert s.concurrent_tasks == 2
    assert "cierra los resultados" in s.persona_brief
    assert "sheet_instances" in s.success_checks
    assert "preguntar" in s.success_checks.lower()
