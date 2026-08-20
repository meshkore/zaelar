"""Un caso no se cierra por sacar buena nota: hay que haber leído la auditoría ENTERA.

Regla del operador, 2026-08-20: *«no las vayas dando por cerradas hasta que se completen con éxito y
compruebes cada uno de los pasos, de los eventos, de los procesos internos, leyendo toda su auditoría de
observabilidad»*.

Lo que había medía FAMILIAS: ¿apareció `worker`, apareció `widget`? Esa no es la misma pregunta. La corrida
real del 2026-08-20 10:00 tenía las dos familias esperadas presentes **y** un evento con `is_error: true` en
un paso del worker —*«Exit code 2, no puedo leer el payload de sources.json»*— que no aparecía en el informe
de mecanismo, ni en el prompt del juez, ni en el informe del operador. Por el criterio viejo, mecanismo
correcto.

El fallo que esto guarda es el caro: cerrar un caso archiva un defecto MEDIDO como si no existiera, y nada
sale en rojo.
"""
from __future__ import annotations

from tests.use_cases.e2e.agent import status as ST, verify as V


def _ev(**kw):
    base = {"cat": "worker", "kind": "task", "label": "· paso", "text": "", "rel_ms": 1000}
    base.update(kw)
    return base


def test_an_internal_error_is_surfaced_as_a_fact():
    a = V.audit([_ev(), _ev(label="· paso ⚠️ error", is_error=True, text="Exit code 2 no puedo leer sources.json",
                     span="worker:1")])
    assert not a["clean"]
    clases = [x["clase"] for x in a["anomalies"]]
    assert "error_interno" in clases
    assert all(x["certeza"] == "hecho" for x in a["anomalies"] if x["clase"] == "error_interno"), (
        "un `is_error` del propio sistema no es una interpretación")


def test_a_run_with_no_internal_error_is_clean():
    """La mitad de sensibilidad: sin esto, «audita» y «siempre encuentra algo» pasan igual, y una auditoría
    que nunca sale limpia bloquea todos los casos para siempre."""
    a = V.audit([_ev(evidence=True), _ev(rel_ms=2000, evidence=True)], ["worker"])
    assert a["clean"], a["anomalies"]


def test_evidence_and_the_tools_that_really_ran_are_counted():
    """Lo único que puede hacer verdadera una afirmación sobre el mundo es que el mundo haya contestado."""
    a = V.audit([_ev(evidence=True, tool="WebFetch"), _ev(evidence=True, tool="WebFetch"),
                 _ev(tool="Bash")])
    assert a["n_evidence"] == 2
    assert a["tools_run"] == {"WebFetch": 2, "Bash": 1}


def test_zero_evidence_with_a_worker_expected_is_an_anomaly():
    a = V.audit([_ev(), _ev(rel_ms=2000)], ["Brain Workers"])
    assert "sin_evidencia_externa" in [x["clase"] for x in a["anomalies"]], (
        "cero eventos con evidencia y un worker esperado: nada volvió del mundo exterior")


def test_but_zero_evidence_is_NOT_an_anomaly_for_a_conversational_case():
    a = V.audit([_ev(cat="flash"), _ev(cat="flash", rel_ms=2000)], ["FlashBrain"])
    assert "sin_evidencia_externa" not in [x["clase"] for x in a["anomalies"]]


def test_a_long_silence_is_measured_not_judged():
    a = V.audit([_ev(rel_ms=0), _ev(rel_ms=95_000)])
    sil = [x for x in a["anomalies"] if x["clase"] == "silencio"]
    assert sil and sil[0]["certeza"] == "medida"


def test_the_anomalies_travel_in_the_LEDGER_so_the_tick_can_act_on_them(tmp_path, monkeypatch):
    """El tick decide el cierre en el proceso PADRE, donde el run dict ya no existe. Si esto no viaja en el
    marcador, la puerta de cierre no tiene con qué decidir y todo pasa igual que antes.

    ⚠️ Contra un marcador TEMPORAL. La primera versión llamaba a `record` a pelo y escribió un escenario
    falso («x») en el marcador REAL de la campaña: un test unitario no puede tocar el tablero que el bucle
    está usando para decidir qué re-probar.
    """
    monkeypatch.setattr(ST, "LEDGER_PATH", tmp_path / "status.json")
    monkeypatch.setattr(ST, "BOARD_PATH", tmp_path / "STATUS.md")
    result = {"scenario": "x", "tier": 1,
              "run": {"transcript": [], "mechanism_report": {
                  "audit": {"anomalies": [{"clase": "error_interno", "certeza": "hecho", "que": "boom"}]}}},
              "verdict": {"overall": 5, "scores": {}, "veredicto": "ok"}}
    entry = ST.record([result], sandboxed=True)["scenarios"]["x"]
    assert entry["audit_anomalies"] == [{"clase": "error_interno", "certeza": "hecho", "que": "boom"}]
    assert entry["state"] == "PASS", "la nota del juez es la nota; la auditoría no la reescribe, frena el CIERRE"


def test_the_audit_reads_the_shape_the_API_actually_serves():
    """El fallo más caro que ha tenido esta auditoría, y duró una hora.

    `observer.emit` hace `ev.update(extra)`, así que los campos caen PLANOS en el payload — y el payload llega
    de la API de observabilidad como una CADENA JSON. La primera versión de `audit` leía `e.get("evidence")`
    directamente, así que devolvía CERO evidencia siempre, y de ahí `sin_evidencia_externa` en todos los casos
    con worker esperado.

    El 2026-08-20 12:2x eso le puso a TRES casos distintos (`find-theatre`, `restaurant`, `cheapest-monitor`)
    la anomalía «el mundo exterior no trajo nada» — mientras el timeline de esa misma tanda llevaba **60
    eventos con `evidence`, 26 de ellos del navegador**. Estaba a punto de entregarse al agente que arregla
    como hecho medido. Una auditoría que INVENTA una anomalía es peor que no tenerla: manda a alguien a buscar
    un defecto que es mío.

    Y el aviso estaba escrito: el docstring de `_fields` lo dice literalmente. No basta con documentarlo.
    """
    import json

    from tests.use_cases.e2e.agent import verify as V

    api_shape = [
        {"cat": "worker", "kind": "navegador",
         "payload": json.dumps({"label": "🏁 hito", "evidence": True, "rel_ms": 100, "span": "worker:1"})},
        {"cat": "worker", "kind": "task",
         "payload": json.dumps({"label": "paso", "is_error": True, "text": "boom", "tool": "Bash",
                                "rel_ms": 200, "span": "worker:1"})},
    ]
    a = V.audit(api_shape, ["Brain Workers"])

    assert a["n_evidence"] == 1, "los campos vienen dentro del payload como cadena JSON"
    assert len(a["errors"]) == 1 and "boom" in a["errors"][0]["text"]
    assert a["tools_run"] == {"Bash": 1}
    assert "sin_evidencia_externa" not in [x["clase"] for x in a["anomalies"]], (
        "esta es la anomalía inventada: había evidencia y el lector no la veía")
    assert a["spans"]["worker:1"]["errors"] == 1, "el span también se lee del payload"


def test_an_agenda_write_is_VISIBLE_in_the_mechanism_report():
    """Devuelto por el agente que arregla el 2026-08-20, y tenía razón.

    El criterio de `remember-and-remind-deadline` dice literalmente «juzga por … data-ops de agenda», y el
    informe de mecanismo NO traía ninguna: solo familias (`widget` aparece, pero no QUÉ widget ni qué se hizo)
    y el bloque `scheduled_jobs`, que es de CRONS. Así que un hallazgo como «no existe ni el evento de agenda
    ni el trigger» se apoyaba, para la mitad de la agenda, en un lector que no cubre agendas. En su
    reproducción la cita SÍ se escribía.

    Misma clase que el fallo de `evidence` unas horas antes: un lector que mira donde no está no falla,
    RESPONDE — y responde una ausencia, que es la respuesta más creíble y más dañina.
    """
    from tests.use_cases.e2e.agent import verify as V

    evs = [{"cat": "widget", "kind": "widget", "label": "data", "id": "agenda::ev1"},
           {"cat": "widget", "kind": "widget", "label": "show", "id": "agenda::ev1"},
           {"cat": "widget", "kind": "widget", "label": "data", "id": "navegador::t2"},
           {"cat": "flash", "kind": "trace", "label": "turno"}]
    ops = V.widget_ops(evs)
    assert ops["agenda"] == {"data": 1, "show": 1}, "una escritura en agenda tiene que ser VISIBLE y contable"
    assert ops["navegador"] == {"data": 1}
    assert "flash" not in ops, "solo la familia widget"


def test_the_judge_is_told_not_to_infer_a_missing_appointment_from_the_crons():
    """La mitad que evita el hallazgo falso: los disparadores durables son CRONS, la cita es un data-op. Sin
    decírselo, el juez vuelve a concluir «no hay cita» leyendo un bloque que no habla de citas."""
    from tests.use_cases.e2e.agent import judge as J

    prose = J.mechanism_facts({"families_observed": ["widget"], "expected_signals": ["memory"],
                               "widget_ops": {"agenda": {"data": 1}},
                               "scheduled_jobs": {"readable": True, "created": []}})
    assert "agenda (data×1)" in prose, "la escritura de agenda tiene que llegarle en PROSA, no solo en el JSON"
    assert "CRONS, no de agendas" in prose


def test_and_the_report_actually_WIRES_it():
    """La mitad que faltaba, y el mismo hueco que ya me comí con la auditoría: los dos tests de arriba llaman a
    `widget_ops` a pelo o le pasan el dict al juez ya hecho, así que los dos PASAN aunque
    `mechanism_report` deje de incluirlo (comprobado: sustituir la llamada por `{}` no los pone rojos).
    Una constante puede quedarse sin cablear; lo que hay que afirmar es lo que RECIBE el consumidor.
    """
    from tests.use_cases.e2e.agent import verify as V

    mech = V.mechanism_report([{"cat": "widget", "kind": "widget", "label": "data", "id": "agenda::ev1"}],
                              ["memory"])
    assert mech.get("widget_ops") == {"agenda": {"data": 1}}, (
        "el informe no lleva las operaciones de widget: el juez vuelve a quedarse sin ver la cita")
