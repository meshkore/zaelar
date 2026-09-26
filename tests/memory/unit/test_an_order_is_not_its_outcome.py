"""An ORDER to the assistant is written as a request, never as the outcome (demo run, 2026-09-26).

«Schedule it as “Catch up with Oscar”» — which the agent never did — became the long-term event «His meeting with
Oscar on Sunday 27 September is titled "Catch up with Oscar"», and «Move it 30 minutes later» became «was
rescheduled 30 minutes later». The distiller cannot know whether an order was carried out; the agenda or the
connector that executes it is the record. Measured on the real distiller against nine lines, before → after:
«Schedule it as…» event → result «Asked the assistant to schedule…»; «Move it 30 minutes later» event → result;
controls unchanged: «My dentist appointment is on Tuesday at 5» stays an event, «Oscar asked me to send him the
slides by Friday» stays a fact, and «Play something by Madonna» still yields «Likes Madonna's music».

This is the prompt contract, pinned so it cannot be edited away silently; the measurement is the evidence.
"""
from nucleo import mem_processor as mp


def test_the_distiller_is_told_an_order_is_not_its_outcome():
    s = mp._SYSTEM
    assert "UNA ORDEN NO ES SU RESULTADO" in s
    i = s.index("UNA ORDEN NO ES SU RESULTADO")
    rule = s[i:i + 1200]
    assert "Pidió al asistente que" in rule, "the request form the pill must take"
    assert 'kind="result"' in rule
    assert "INFORMA de algo que ya existe" in rule, "a fact he reports stays a fact"
    assert "le gusta Madonna" in rule, "what an order reveals about him is still inferred"


def test_it_sits_next_to_the_rule_that_keeps_requests():
    s = mp._SYSTEM
    assert s.index("NUNCA descartes PETICIONES") < s.index("UNA ORDEN NO ES SU RESULTADO") \
        < s.index("★ FECHAS RELATIVAS"), "the two request rules must read together"
