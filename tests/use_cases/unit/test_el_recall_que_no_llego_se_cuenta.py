"""V2-453 · «asks what it already knows» has TWO causes, and the report did not distinguish them.

Either the recall DID NOT ARRIVE—the 800 ms budget expires and the turn still has no durable memory, our
failure—or it arrived and the model ignored it—behavior. From the outside they look identical: the turn asks
something the operator already mentioned. It is the same form of confusion that V2-432 closed for the sheet,
in another subsystem.

The engine has said so since V2-311—`memory` row «recall not delivered», with reason and query—and **the
report did not read it**. Measured on 2026-08-28: `weekend-motor-events__es` was filed as an ADAPTATION [high]
failure («asks “what do you like?” when the preferences were already in its memory, seeded and verified»),
with nothing in the report saying whether those preferences reached the prompt. And V2-311 measured that
**21 of 27 live recalls were abandoned when the budget expired**, so our cause is not rare: it is the majority.
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
    """«Zero» and «I did not look» are not the same, and zero is the reassuring one: the signal is always read,
    so here zero DOES mean that no recall was lost."""
    out = verify.recall_not_delivered([{"kind": "flash", "payload": "{}"}])
    assert out["n"] == 0 and out["read"] is True


def test_no_se_confunde_con_otro_evento_de_memoria():
    """The `memory` channel carries many things; counting any of them would inflate the failure with healthy activity."""
    otro = {"kind": "memory", "payload": json.dumps({"label": "píldora escrita", "reason": "x"})}
    assert verify.recall_not_delivered([otro])["n"] == 0


def test_al_juez_se_le_dice_que_NO_lo_puntue_como_fallo_de_memoria():
    txt = judge.mechanism_facts({"recall_not_delivered":
                                 {"n": 2, "read": True, "reasons": {"timeout": 2},
                                  "queries": ["preferencias de motor"]}})
    assert "MEMORIA QUE NO LLEGÓ" in txt
    assert "NO lo" in txt and "adaptación" in txt


def test_y_si_no_se_perdio_ninguno_no_se_le_dice_nada():
    """A line that is always emitted stops being read—and here it would say there is a failure where there is none."""
    txt = judge.mechanism_facts({"recall_not_delivered": {"n": 0, "read": True, "reasons": {}, "queries": []}})
    assert "MEMORIA QUE NO LLEGÓ" not in txt


def test_run_lo_CALCULA():
    from pathlib import Path
    src = Path("tests/use_cases/e2e/agent/run.py").read_text(encoding="utf-8")
    assert 'mech["recall_not_delivered"] = verifymod.recall_not_delivered(all_events)' in src
