"""The escalate verdict keeps one-step orders on the spot and sends real errands to a worker — measured live.

Measured 2026-09-27 (demo pass v6): the question told Jev «handle_inline ONLY for what is clearly not an errand …
when in doubt, escalate». It escalated 11 of 11 one-step orders — «Play something by Madonna», «Message Rowan on
Telegram…», «Show me a chart of Apple stock today» (0.99) — and the promise backstop turned each into a 50-60 s
Brain Worker. The question now names what the assistant does with its own cards. Old wording: 5/17. New: 16/17.
V2-794 (2026-10-24): a collection put together for him is an errand; one named item into a list is not.
V2-831 T-26 (2026-10-29): one text from ONE known source is inline (`compose_rung`); research across several is not.

LIVE and opt-in: Run: ZAELAR_LIVE_JEV=1 ZAELAR_TEST_JEV_LIVE=1 .venv/bin/pytest tests/voice/unit/test_a_one_step_order_is_not_a_worker.py -s
"""
from __future__ import annotations

import os

import pytest

INLINE = ["Show me a red Ferrari F40.", "Show me the last month instead.", "Play something by Madonna.",
          "Message Rowan on Telegram and tell him the new meeting time.",
          "Find a five-day period during her vacation when my calendar is clear, and suggest the dates.",
          "Show me a chart of Apple stock today.", "Schedule it as \"Catch up with Rowan\".",
          "Show me only the emails from today that need my attention.",
          "Pon algo de Madonna.", "Mándale un Telegram a Rowan con la nueva hora.",
          # V2-794 — ONE named item into a list is a one-step order
          "Añade esta canción a la lista Favoritos.", "Add Bohemian Rhapsody to my party playlist.",
          # V2-831 T-26 — ONE text from ONE known source is one look-up and one written answer
          "write me a one page summary of the bitcoin whitepaper, in a document",
          "Write me a one-page summary of the Declaration of Independence in a document.",
          "Tradúceme al inglés el documento que tengo abierto."]
ERRANDS = ["Johnny, find me three 27-inch 4K monitors under 400 dollars — show me when you have them.",
           "Johnny, plan a 5-day warm-weather trip for Anna and me from LAX, December 21st to 25th, under 2000 "
           "dollars total — show me when it's ready.",
           "Build me a widget that tracks my expenses.",
           "Búscame un hotel en Bilbao para el viernes por menos de 100 euros.",
           "Research the best electric bikes under 2000 euros and compare them.",
           "research the best laptops and compare them",
           "Write me a report on the state of the European EV market, with sources.",
           # V2-794 — a collection PUT TOGETHER to fit what he describes is an errand, whatever its card
           "Crea una lista de 40 canciones para ambientar un cumpleaños, seremos adultos de 45 a 50.",
           "Somos gente de 45 a 55, amantes del rock, la buena música, poco reguetón, en un local para música "
           "ambiente a medio volumen. Estamos en España, y nos gusta también el pop español y canciones famosas de "
           "fiesta. Monta una lista.",
           "Put together a list of 20 films for a rainy weekend with two kids under ten.",
           "Hazme una lista de 30 restaurantes en Madrid para ir con amigos un sábado."]


def test_the_escalate_question_keeps_one_step_orders_inline():
    if os.environ.get("ZAELAR_LIVE_JEV", "").strip() not in ("1", "true", "yes"):
        pytest.skip("live measurement — set ZAELAR_LIVE_JEV=1 to spend the round trips")
    from nucleo import jev
    from nucleo.flash import escalation_guard as eg
    if not jev.enabled():
        pytest.skip("Jev is off — this node measures nothing without it")
    ctx = "Goals already in flight: none\nWorkers active now: no\nA worker is waiting for the operator's answer: no"
    misses = []
    for want, group in (("handle_inline", INLINE), ("escalate", ERRANDS)):
        for t in group:
            v = jev.choose_sync("escalate_or_inline", t, instructions=eg.ESCALATE_INSTRUCTIONS,
                                criteria=eg.ESCALATE_CHOICE, context=ctx, timeout_s=8,
                                question_id="escalate-measure") or {}
            if not (v.get("choice") == want and float(v.get("confidence") or 0) >= jev.MIN_CONFIDENCE):
                misses.append((want, v.get("choice"), v.get("confidence"), t))
    print("\n".join(map(str, misses)))
    assert len(misses) <= 2, f"{len(misses)} of {len(INLINE) + len(ERRANDS)} misread: {misses}"


#: V2-831 T-26 — the single-source shape and its neighbour, each read RIGHT (no tolerance: the bench above allows two
#: misses across 25, and the old wording missed exactly these two summaries and still passed it).
SINGLE_SOURCE = ["write me a one page summary of the bitcoin whitepaper, in a document",
                 "Write me a one-page summary of the Declaration of Independence in a document."]
RESEARCH = ["research the best laptops and compare them"]


def test_one_text_from_one_known_source_is_inline_and_research_is_a_worker():
    if os.environ.get("ZAELAR_LIVE_JEV", "").strip() not in ("1", "true", "yes"):
        pytest.skip("live measurement — set ZAELAR_LIVE_JEV=1 to spend the round trips")
    from nucleo import jev
    from nucleo.flash import escalation_guard as eg
    if not jev.enabled():
        pytest.skip("Jev is off — this node measures nothing without it")
    ctx = "Goals already in flight: none\nWorkers active now: no\nA worker is waiting for the operator's answer: no"
    got = {t: jev.choose_sync("escalate_or_inline", t, instructions=eg.ESCALATE_INSTRUCTIONS,
                              criteria=eg.ESCALATE_CHOICE, context=ctx, timeout_s=8,
                              question_id="escalate-measure") or {} for t in SINGLE_SOURCE + RESEARCH}
    wrong = [(t, v.get("choice"), v.get("confidence")) for t, v in got.items()
             if v.get("choice") != ("handle_inline" if t in SINGLE_SOURCE else "escalate")]
    assert not wrong, wrong
