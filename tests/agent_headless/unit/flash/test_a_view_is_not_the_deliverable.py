"""Talking ABOUT a card's content — or an errand that will read it — is not an order to open the card (V2-820).

Measured on a live session: «¿podrías crear un widget que leyera mis mensajes enviados… y fuera componiendo un
archivo que describiera cómo escribo yo?». The brief read `errand_surface = informe` (a document, 0.93) and `canvas`
unsure. The catalogue rung took `mensajeria:mail_folder {folder: sent}` INSTEAD of the worker, and since a lens over
a closed card is presented (`canvas_visibility.present_for_call`), his mail card opened — «no tenía por qué haberlo
hecho». Later, the promise pass kept «le digo al proceso que se limite a tu correo» with `mensajeria:show_view`, and
the card opened again.

The class: a VIEW (an action declared `data.read`) cannot BE an errand whose deliverable has its own box — a
document, pictures. Read from the verdict (surface, canvas) and the action's declaration, never from words: the worker
keeps the errand, the promise pass is judged as having nothing to run on the card. He still sees the card when the
verdict says `canvas = show`, and a view of the deliverable's own box is that deliverable.
"""
from __future__ import annotations

import asyncio
import threading

import pytest

from nucleo import surfaces
from nucleo.flash import act_repair, canvas_visibility as cv, card_commission, turn_brief as tb
from nucleo.turn import promise_kept as pk

#: (his words, the view a rung chose) — es and en; the deliverable is always a written document.
CASES = [
    ("¿Podrías leer mis mensajes enviados y componer un archivo que describa cómo escribo?", "mail_folder"),
    ("Read my sent emails and write me a document describing my writing style", "mail_folder"),
    ("Quiero que mires el email, no WhatsApp", "show_view"),
    ("Look at my email instead of WhatsApp for that report", "show_view"),
]


def _brief(**verdicts):
    ev = threading.Event()
    ev.set()
    return {"event": ev, "turn_id": "t-1", "open_ids": [],
            "result": {k: {"choice": c, "confidence": conf} for k, (c, conf) in verdicts.items()}}


REPORT = {surfaces.SURFACE_KEY: ("informe", 0.93), tb.CANVAS_KEY: ("neither", 0.44)}


@pytest.mark.parametrize("text,action", CASES)
def test_a_lens_on_his_card_is_not_a_document_errand(text, action):
    assert cv.a_view_is_not_the_deliverable("mensajeria", action, _brief(**REPORT))


@pytest.mark.parametrize("text,action", CASES)
def test_he_still_sees_it_when_the_turn_asked_to_see_it(text, action):
    asked = dict(REPORT, **{tb.CANVAS_KEY: ("show", 0.95)})
    assert not cv.a_view_is_not_the_deliverable("mensajeria", action, _brief(**asked))


def test_only_a_view_and_only_against_an_own_box_deliverable():
    assert not cv.a_view_is_not_the_deliverable("mensajeria", "draft", _brief(**REPORT)), "a write is an act"
    assert not cv.a_view_is_not_the_deliverable("documento", "show", _brief(**REPORT)), "the deliverable's own box"
    for surface in ("lista", "item", "widget", "silenciosa"):
        b = _brief(**{surfaces.SURFACE_KEY: (surface, 0.95), tb.CANVAS_KEY: ("neither", 0.4)})
        assert not cv.a_view_is_not_the_deliverable("mensajeria", "mail_folder", b), surface
    unsure = {surfaces.SURFACE_KEY: ("informe", 0.3), tb.CANVAS_KEY: ("neither", 0.4)}
    assert not cv.a_view_is_not_the_deliverable("mensajeria", "mail_folder", _brief(**unsure)), "unsure → today"
    assert not cv.a_view_is_not_the_deliverable("mensajeria", "mail_folder", None), "no brief → today"


@pytest.mark.parametrize("text,action", CASES)
def test_the_catalogue_rung_leaves_the_errand_to_the_worker(text, action, monkeypatch):
    monkeypatch.setattr(card_commission, "named_or_catalogue", lambda b, t: "mensajeria")

    async def _view(*a, **k):
        return {"kind": "call", "widget_id": "mensajeria", "action": action, "payload": {"folder": "sent"}}
    monkeypatch.setattr(act_repair, "call_or_read_for_commission", _view)
    got = asyncio.run(card_commission.commission_call(text, brief=_brief(**REPORT), operator_text=text, spec=None))
    assert got is None, "the worker keeps the errand; his card stays where he left it"
    asked = dict(REPORT, **{tb.CANVAS_KEY: ("show", 0.95)})
    got = asyncio.run(card_commission.commission_call(text, brief=_brief(**asked), operator_text=text, spec=None))
    assert got and got["action"] == action


@pytest.mark.parametrize("text,action", CASES)
def test_the_promise_pass_does_not_keep_a_report_promise_with_a_lens(text, action, monkeypatch):
    async def _view(*a, **k):
        return {"widget_id": "mensajeria", "action": action, "payload": {"platform": "email"}}
    monkeypatch.setattr(act_repair, "call_for_promise", _view)
    outcome: dict = {}
    got = asyncio.run(act_repair.call_for_promise_or_order(text, "Le digo al proceso que mire tu correo.",
                                                           "mensajeria", spec=None, brief=_brief(**REPORT),
                                                           outcome=outcome))
    assert got is None and outcome.get("kind") == pk.JUDGED
