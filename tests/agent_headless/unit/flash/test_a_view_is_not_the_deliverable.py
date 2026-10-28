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
from nucleo.flash import act_repair, canvas_visibility as cv, card_commission
from nucleo.turn import brief as tb
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


# --- the next live turn (2026-10-27 11:23:54, T61): the verdict unsure, the escalation itself declared the document ---
#: his answer to «¿WhatsApp, correo o los dos?», verbatim; the model's escalation carried `surface = informe`.
T61 = ("Solo solo de solo de correo, en WhatsApp nunca escribo algo tan largo, y si lo hago últimamente ha sido "
       "porque he utilizado la IA. Así que céntrate en el correo y en los mensajes enviados.")
T61_BRIEF = {surfaces.SURFACE_KEY: ("informe", 0.42), tb.CANVAS_KEY: ("neither", 0.96)}


def test_an_unsure_verdict_takes_the_deliverable_the_escalation_declared():
    b = _brief(**T61_BRIEF)
    assert cv.a_view_is_not_the_deliverable("mensajeria", "mail_folder", b, declared="informe")
    assert not cv.a_view_is_not_the_deliverable("mensajeria", "mail_folder", b), "nothing declared → today"
    assert not cv.a_view_is_not_the_deliverable("mensajeria", "mail_folder", b, declared="lista"), "a list may be it"
    sure_list = _brief(**{surfaces.SURFACE_KEY: ("lista", 0.95), tb.CANVAS_KEY: ("neither", 0.9)})
    assert not cv.a_view_is_not_the_deliverable("mensajeria", "mail_folder", sure_list, declared="informe"), \
        "a sure verdict is read as today"
    asked = _brief(**dict(T61_BRIEF, **{tb.CANVAS_KEY: ("show", 0.95)}))
    assert not cv.a_view_is_not_the_deliverable("mensajeria", "mail_folder", asked, declared="informe")


def test_t61_replayed_the_worker_keeps_the_errand(monkeypatch):
    """Red on the released behaviour: `before_worker` ran `mensajeria:mail_folder {sent}`, cleared the escalation
    («🎯 acción declarada en vez de un worker») and the reply «voy con el correo enviado…» had nothing behind it."""
    monkeypatch.setattr(card_commission, "named_or_catalogue", lambda b, t: "mensajeria")

    async def _view(*a, **k):
        return {"kind": "call", "widget_id": "mensajeria", "action": "mail_folder", "payload": {"folder": "sent"}}
    monkeypatch.setattr(act_repair, "call_or_read_for_commission", _view)
    commission = "Analizar su ESTILO DE ESCRITURA usando EXCLUSIVAMENTE los correos ENVIADOS…"
    # the escalation the model made, its surface recorded per request (`tool_executor_calls`)
    esc = {"v": commission, "more": [], "surface": {commission: "informe"}}
    ran: list = []
    got = asyncio.run(card_commission.before_worker(
        esc, {"v": None}, brief=_brief(**T61_BRIEF), operator_text=T61, spec=None, emit=lambda *a, **k: None,
        present=lambda *a, **k: None, apply_widget_data=lambda *a: ran.append(a)))
    assert got == "" and not ran, "no view ran in its place"
    assert esc["v"] == commission, "the escalation survives: the worker starts"
