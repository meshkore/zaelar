# Demo pass in a sandbox, 2026-10-28 — INIT, list step «Save Ethan and Andrew in my contacts: Ethan's Telegram is
# @ethan_demo, and Andrew's email is andrew@example.com.»:
#
#     jev turn-brief   request_type=order · catalog_widget=contactos (1.00)
#     widget data      contactos:add_contact {name: Ethan …}
#     brain            🔁 la orden era sobre otra tarjeta — la llamada, en una segunda pasada  ['contactos'] → mensajeria:send_to
#     widget data      mensajeria:send_to {contact: Andrew, channel: email,
#                        text: "Hi Andrew, just confirming your email address on my side: andrew@example.com. Best, Richard"}
#
# The turn wrote the contact — the order's card, which the verdict named at 1.00 — and the «order on another card»
# pass still ran: its reader of the OTHER card is a grammar (`named_cards`), which read «Telegram» and «email» as
# the messaging card, and the pass that followed asked the model, with no operator in the loop, for «the call it
# owed» on that card. The model composed a mail to a real person and the engine sent it; only the sandbox's empty
# directory stopped it. The recipient was in his words, so the one bound that existed (`recipient_was_named`) held:
# a named recipient is not an ordered send.
#
# THE CLASS: (1) a verdict that puts the order on the card the turn touched — the catalogue's as much as the
# screen's — says there is no other card, and a grammar match cannot refute it; (2) an act that LEAVES the machine,
# composed by a pass whose card came from his words, runs only when the verdict puts the order on that card.
# Fail-closed: with no verdict, no send. Both halves hold in either language and for any card that declares
# `external.send`; acts that stay on the machine are not bound.
from __future__ import annotations

import asyncio
import threading

import pytest

from nucleo.flash import act_repair as _ral, direct_action as _da, repair_grounding as _rg
from nucleo.turn import brief as _tb

EN = "Save Ethan and Andrew in my contacts: Ethan's Telegram is @ethan_demo, and Andrew's email is andrew@example.com."
ES = "guarda a Ethan y a Andrew en mis contactos: el Telegram de Ethan es @ethan_demo y el correo de Andrew es andrew@example.com"
C5 = "send rowan a telegram with the new time"


def _brief(**verdicts):
    ev = threading.Event()
    ev.set()
    return {"event": ev, "turn_id": "t-1", "open_ids": [],
            "result": {k: {"choice": v, "confidence": 0.95} for k, v in verdicts.items()}}


# ── (1) the catalogue verdict on the touched card says there is no other card ───────────────────────────────────

@pytest.mark.parametrize("said", [EN, ES])
def test_the_catalogue_naming_the_card_the_turn_wrote_leaves_no_other_card(said):
    b = _brief(**{_tb.REQUEST_KEY: "order", _tb.CATALOG_KEY: "contactos"})
    assert _da.order_card_after_read(b, said, "contactos") == ""


def test_the_catalogue_naming_another_card_keeps_the_order_on_it():
    """full20 C5, the case the pass exists for: the agenda was read for the time, the order is the message."""
    b = _brief(**{_tb.REQUEST_KEY: "order", _tb.CATALOG_KEY: "mensajeria"})
    assert _da.order_card_after_read(b, C5, "agenda") == "mensajeria"


# ── (2) an act that leaves needs the verdict on its card ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("brief, backed", [
    (None, False),                                                            # no verdict: no send
    (_brief(**{_tb.CATALOG_KEY: "contactos"}), False),                        # the order was on another card
    (_brief(**{_tb.CATALOG_KEY: "mensajeria"}), True),                        # the catalogue puts it here
    (_brief(**{_tb.TARGET_KEY: "mensajeria:send_to"}), True),                 # the screen's target does
])
def test_an_act_that_leaves_is_backed_only_by_a_verdict_on_its_card(brief, backed):
    assert _rg.send_backed_by_verdict(brief, "mensajeria", "send_to") is backed
    assert _rg.send_backed_by_verdict(brief, "mensajeria", "forward") is backed


def test_an_act_that_stays_on_the_machine_is_not_bound():
    assert _rg.send_backed_by_verdict(None, "agenda", "add_meeting") is True


def _after_read(said: str, call: dict, *, brief=None, read="contactos", card="mensajeria"):
    import nucleo.llm.fast_client as fc
    from nucleo.flash import widget_read

    class _Model:
        async def complete(self, messages, *, on_tool_call=None, **kw):
            on_tool_call("widget_data", call)
            return ""
    real_fc, real_read = fc.FastClient, widget_read.read
    fc.FastClient = lambda: _Model()
    widget_read.read = lambda wid, *a, **k: ""
    try:
        return asyncio.run(_ral.call_after_read(said, read, card, brief=brief, window=[]))
    finally:
        fc.FastClient, widget_read.read = real_fc, real_read


_MAIL = {"widget_id": "mensajeria", "action": "send_to",
         "payload": {"contact": "Andrew", "channel": "email", "text": "Hi Andrew, just confirming your email address."}}


@pytest.mark.parametrize("said", [EN, ES])
@pytest.mark.parametrize("brief", [None, _brief(**{_tb.REQUEST_KEY: "order", _tb.CATALOG_KEY: "contactos"})])
def test_the_after_read_pass_never_sends_what_no_verdict_ordered(said, brief):
    assert _after_read(said, _MAIL, brief=brief) is None


def test_the_after_read_pass_still_carries_out_a_send_the_verdict_ordered():
    msg = {"widget_id": "mensajeria", "action": "send_to", "payload": {"contact": "Rowan", "text": "Moved to 16:30"}}
    got = _after_read(C5, msg, brief=_brief(**{_tb.CATALOG_KEY: "mensajeria"}), read="agenda")
    assert got == msg


def test_the_after_read_pass_keeps_a_recipient_nobody_named_out():
    msg = {"widget_id": "mensajeria", "action": "send_to", "payload": {"contact": "zaelar", "text": "Moved to 16:30"}}
    assert _after_read(C5, msg, brief=_brief(**{_tb.CATALOG_KEY: "mensajeria"}), read="agenda") is None
