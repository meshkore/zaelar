"""The judge receives the two facts that prevent it from blaming the product for something that happened OUTSIDE it.

Measured in `find-concert-tickets__es` (2026-08-25 12:25). Zaelar said, in those words, that it had run out
of quota with the provider for its background processes. The judge read the blank sheet and wrote as blocker #1
“zaelar's inability to recognize and report explicit technical failures (quota exhausted)” — exactly the
opposite of what happened — and assigned `result 1 · mechanism 2`.

The mechanism report is the source of truth for the text (`judge.py`'s docstring), so if the fact is not
IN the report, the judge can do nothing but infer it from the transcript. The two facts:

  · no QUOTA to launch workers → our bill
  · an external RESET halfway through a round → closes the cards and leaves the “cancelled” tab without cancelling anything
"""
from tests.use_cases.e2e.agent.judge import mechanism_facts


def test_sin_los_hechos_no_dice_nada_de_ellos():
    txt = mechanism_facts({"worker_health": {"spawned": 1, "ok": 1}})
    assert "NO HABÍA CUOTA" not in txt
    assert "RESETEÓ EL MOTOR" not in txt


def test_la_cuota_agotada_llega_al_juez_NOMBRADA():
    txt = mechanism_facts({"provider_exhausted": {"deaths": 3, "asleep": 0,
                                                  "providers": ["licencia-claude"], "reset_at": 0}})
    assert "NO HABÍA CUOTA" in txt
    assert "licencia-claude" in txt
    assert "3" in txt


def test_y_con_la_INSTRUCCION_de_no_puntuarlo_contra_el_producto():
    """The isolated fact is not enough: the judge already had the transcript saying it and still scored it. The line tells it
    what to DO with the fact, which is what the rest of this function does with all the others."""
    txt = mechanism_facts({"provider_exhausted": {"deaths": 4, "asleep": 0, "providers": [], "reset_at": 0}})
    low = txt.lower()
    assert "no bajes" in low
    assert "honestidad" in low


def test_la_cadena_dormida_cuenta_aunque_no_muera_nadie():
    """Since V2-314, the dispatcher refuses to launch when the entire chain is asleep: zero deaths, zero round."""
    txt = mechanism_facts({"provider_exhausted": {"deaths": 0, "asleep": 2, "providers": [], "reset_at": 0}})
    assert "NO HABÍA CUOTA" in txt
    assert "cooldown" in txt.lower()


def test_el_reset_ajeno_llega_CON_SU_SEGUNDO():
    """The timing is half the fact: at 12 s it takes down the entire round; at 400 s it may have happened after
    the delivery that mattered."""
    txt = mechanism_facts({"resets_during_round": {"n": 1, "at_s": [12.5]}})
    assert "RESETEÓ EL MOTOR" in txt
    assert "12.5s" in txt


def test_y_explica_POR_QUE_una_pestaña_sale_cancelada_sin_que_nadie_cancele():
    txt = mechanism_facts({"resets_during_round": {"n": 2, "at_s": [30.0, 90.0]}})
    low = txt.lower()
    assert "tarjeta" in low and "cancelada" in low
