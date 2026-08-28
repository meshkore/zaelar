"""V2-453 · «pregunta lo que ya sabe» tiene DOS causas, y el informe no distinguía.

O el recall NO LLEGÓ —el presupuesto de 800 ms vence y el turno sigue sin memoria durable, avería nuestra— o
llegó y el modelo lo ignoró —conducta—. Desde fuera se ven idénticas: el turno pregunta algo que el operador
ya contó. Es la misma forma del confundido que V2-432 cerró para la hoja, en otro subsistema.

El motor lo dice desde V2-311 —fila `memory` «recall sin entregar», con motivo y consulta— y **el informe no
lo leía**. Medido el 2026-08-28: `weekend-motor-events__es` se archivó como fallo de ADAPTACIÓN [alta]
(«pregunta ¿qué te gusta? cuando las preferencias ya estaban en su memoria, sembradas y verificadas») sin
nada en el informe que dijera si esas preferencias llegaron al prompt. Y V2-311 midió que **21 de 27 recalls
vivos se abandonaban al vencer el presupuesto**, así que la causa nuestra no es rara: es la mayoritaria.
"""
import json

from tests.use_cases.e2e.agent import judge, verify


def _ev(reason="timeout", query="preferencias de motor"):
    return {"kind": "memory", "cat": "memory",
            "payload": json.dumps({"kind": "memory", "label": "recall sin entregar",
                                   "reason": reason, "query": query})}


def test_se_cuentan_los_recalls_que_no_llegaron_y_su_MOTIVO():
    out = verify.recall_not_delivered([_ev(), _ev(), _ev("error", "qué le gusta")])
    assert out["n"] == 3 and out["reasons"] == {"timeout": 2, "error": 1}
    assert "preferencias de motor" in out["queries"]


def test_una_ronda_SIN_la_señal_sale_a_cero_y_LEIDA():
    """«Cero» y «no miré» no son lo mismo, y el cero es el que tranquiliza: la señal se lee siempre, así que
    aquí el cero SÍ significa que ningún recall se perdió."""
    out = verify.recall_not_delivered([{"kind": "flash", "payload": "{}"}])
    assert out["n"] == 0 and out["read"] is True


def test_no_se_confunde_con_otro_evento_de_memoria():
    """El canal `memory` lleva muchas cosas; contar cualquiera inflaría la avería con actividad sana."""
    otro = {"kind": "memory", "payload": json.dumps({"label": "píldora escrita", "reason": "x"})}
    assert verify.recall_not_delivered([otro])["n"] == 0


def test_al_juez_se_le_dice_que_NO_lo_puntue_como_fallo_de_memoria():
    txt = judge.mechanism_facts({"recall_not_delivered":
                                 {"n": 2, "read": True, "reasons": {"timeout": 2},
                                  "queries": ["preferencias de motor"]}})
    assert "MEMORIA QUE NO LLEGÓ" in txt
    assert "NO lo" in txt and "adaptación" in txt


def test_y_si_no_se_perdio_ninguno_no_se_le_dice_nada():
    """Una línea que sale siempre deja de leerse — y aquí diría que hay una avería donde no la hay."""
    txt = judge.mechanism_facts({"recall_not_delivered": {"n": 0, "read": True, "reasons": {}, "queries": []}})
    assert "MEMORIA QUE NO LLEGÓ" not in txt


def test_run_lo_CALCULA():
    from pathlib import Path
    src = Path("tests/use_cases/e2e/agent/run.py").read_text(encoding="utf-8")
    assert 'mech["recall_not_delivered"] = verifymod.recall_not_delivered(all_events)' in src
