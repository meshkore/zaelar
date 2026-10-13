"""A form that sends his details goes only to a site he named; any other asks him first (same rule as a message).

The browser half of `best-plumber-same-day__es` (2026-10-14). V2-712 stopped asking for consent on a form that
wants his name, phone and email — «si te digo que reserves mesa en un restaurante, tú ya tienes que saber
quién soy yo» — because such a form is the shape of the order he gave. On an errand that was only «find me a
plumber», a worker filling a plumber's contact form and pressing «Enviar» would hand his identity to a
business he never chose. `click_gate.may_act` now asks `on_his_behalf.form_question` once the form can be
filled: a site his words for the errand name runs as before, any other goes through the yes/no door.
"""
from __future__ import annotations

import asyncio

import pytest

from nucleo import his_words
from widgets.navegador import click_gate as G


def _sig(page, signals="name email tel message", name="Enviar"):
    return {"name": name, "role": "button", "isSubmit": True, "inForm": True, "payment": False,
            "identity": False, "method": "post", "targetUrl": "", "pageUrl": page, "signals": signals,
            "fields": 4}


class _Handle:
    def __init__(self, sig):
        self.sig = sig

    async def evaluate(self, _js):
        return self.sig


@pytest.fixture
def gate(monkeypatch):
    his_words.reset()
    asked: list[str] = []
    answer = {"yes": False}

    async def _confirm(label):
        asked.append(label)
        return answer["yes"]

    monkeypatch.setattr(G, "needs_facts", lambda sig: [])          # his details are on file: V2-712's case
    from nucleo import dispatch
    monkeypatch.setattr(dispatch, "record_by_nav_task", lambda tid: None)

    def run(sig):
        return asyncio.run(G.may_act(None, _Handle(sig), confirm=_confirm, task_id="t1"))
    yield run, asked, answer
    his_words.reset()


def test_a_plumbers_contact_form_he_never_chose_asks(gate):
    run, asked, _ = gate
    his_words.note("necesito un fontanero hoy sí o sí, uno bien valorado")
    his_words.note("Madrid centro")
    ok, why = run(_sig("https://www.fontanerourgente24h.es/contacto"))
    assert ok is False and asked and "fontanerourgente24h" in asked[0], (ok, why, asked)


def test_his_yes_lets_it_through(gate):
    run, asked, answer = gate
    answer["yes"] = True
    ok, _ = run(_sig("https://www.fontanerourgente24h.es/contacto"))
    assert ok is True and asked


def test_the_restaurant_he_named_gets_his_details_without_a_question(gate):
    run, asked, _ = gate
    his_words.note("resérvame mesa en Casa Lucio para dos a las nueve")
    ok, _ = run(_sig("https://www.casalucio.es/contacto"))
    assert ok is True and asked == []


def test_a_search_box_is_not_his_identity(gate):
    run, asked, _ = gate
    ok, _ = run(_sig("https://www.idealista.com/buscar", signals="q text country", name="Buscar"))
    assert ok is True and asked == []
