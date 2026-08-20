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
