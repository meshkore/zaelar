"""The guitars a first tail left out ride his next wait; a turn that names rows keeps its answer (node 2.635).

search-buy-guitar ES (2026-10-14, sandbox 015003-es, measured before the delivery fix of that night). Nine acoustic
guitars under 150 € were in the prompt; the first tail named three («Harley Benton CLD-16S…», «Guitarra acústica —
40 €», «Guitarra eléctrica con…») and the rest were never told. Two causes, two nodes: eight more guitars had been
rejected at the door by our own relay's «(Wallapop, Milanuncios…)» (node 2.631), and the turns after the tail were
his questions about rows he named («La Harley Benton de 100€ me llama, y la de 40€…»), which the backstop rightly
leaves to the reply. This pins the merged rule on the round's own rows: a turn of his that waits to be told
(`wants_words=tell`, not routed to a worker) carries rows never announced, whatever the reply says.
"""
from __future__ import annotations

import threading

import pytest

from nucleo.flash import delivery, live_blocks

ERRAND = "Encuéntrame una guitarra acústica de segunda mano para empezar, por menos de 150€."
ROWS = ["Harley Benton CLD-16S Guitarra… — 100 €", "Guitarra acústica — 40 €", "Guitarra eléctrica con… — 125 €",
        "Guitarra Duquesa Estudio C-3901 — 45 €", "Guitarra Española Acústica — 40 €",
        "guitarra acustica soundsation… — 69 €", "guitarra acustica recording king… — 95 €"]
WAIT = "Perfecto, quedo atento."            # no wait wording: the rows are owed by HIS turn, not by the reply


def _brief(words: str) -> dict:
    ev = threading.Event()
    ev.set()
    return {"event": ev, "turn_id": "t", "open_ids": [], "_call_id": "t",
            "result": {"wants_words": {"choice": words, "confidence": 1.0},
                       "escalate_or_inline": {"choice": "handle_inline", "confidence": 1.0}}}


@pytest.fixture
def first_tail(monkeypatch):
    monkeypatch.setattr(live_blocks, "any_stalled_task", lambda: ("", 0, ""))
    monkeypatch.setattr(delivery, "_speaks_en", lambda: False)
    monkeypatch.setattr(live_blocks, "any_live_task_rows", lambda n=3: (ERRAND, ROWS[:n]))
    delivery.forget_announced()
    out = delivery.apply_to_reply("Vale, sigo con la búsqueda y te aviso si sale algo; si no, lo dejamos sin problema.",
                                  [], heard_now="bueno, si al final no sale nada no pasa, lo dejo. Si encuentras "
                                                "algo me dices, gracias.")
    assert "Harley Benton" in out, out


def test_his_next_wait_carries_the_guitars_never_told(first_tail):
    out = delivery.apply_to_reply(WAIT, [], heard_now="vale, quedo pendiente entonces.", brief=_brief("tell"))
    assert "Duquesa" in out and "Española" in out, out
    assert "Harley Benton" not in out, "what was announced is never announced again"


def test_his_question_about_rows_he_named_keeps_the_reply(first_tail):
    said = ("Mira, la eléctrica esa no me sirve, yo busco acústica. La Harley Benton de 100€ me llama, y la de 40€ "
            "también se puede mirar... ¿sabes si están cerca para poder probarlas?")
    reply = "Buena pregunta, pero todavía no sé dónde están; se lo pregunto a la búsqueda."
    assert delivery.apply_to_reply(reply, [], heard_now=said, brief=_brief("tell")) == reply
