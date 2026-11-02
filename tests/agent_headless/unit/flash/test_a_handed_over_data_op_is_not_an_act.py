"""A data-op handed to a worker is not an act: the commission it opened survives a confident `handle_inline` (node 2.402).

V2-834 T04, use case `dentist-appointment-into-agenda` (sandbox, 2026-11-02): the appointment was written two turns
earlier with its reminder at 13:00; «mejor avísame ese día a mediodía». The model called
`widget_data(agenda, set_reminder)` with no item, on an agenda that was not on screen. The misroute guard escalated the
turn RAW so a worker could resolve «ese día» from the window — and in the same breath set `acted["widget"] = True`.
`settle_commission` read that flag as «the turn acted», ruled `handled_inline` (why: acted) and cleared the escalation:
nothing moved the reminder, and the reply «Lo muevo a las doce» stood over nothing.

Mechanism pinned here: the misroute branch opens the commission and leaves `acted` false, so the commission settle
keeps it (`annulment_verdict` annuls only on evidence) — the promise has real work behind it.
"""
from __future__ import annotations

import types

from nucleo.flash import escalation_guard as eg
from nucleo.flash import tool_executor_widget_calls as T


def _run(monkeypatch, said):
    from widgets import refs, runtime
    from nucleo.acts import card
    monkeypatch.setattr(runtime, "get", lambda wid: {"id": wid})
    monkeypatch.setattr(card, "licence", lambda *a, **k: types.SimpleNamespace(verdict=card.RUN, card="agenda"))
    monkeypatch.setattr(card, "logged", lambda lic, emit: lic)
    monkeypatch.setattr(refs, "resolve", lambda *a, **k: types.SimpleNamespace(ok=False, needs="", candidates=[],
                                                                               payload={}))
    fe = types.SimpleNamespace(payload_ref=lambda *a, **k: "", action_mode=lambda *a: "data",
                               absent_widget_misroute=lambda *a, **k: True)
    from nucleo.flash import router
    monkeypatch.setattr(router, "is_pure_show_request", lambda t: False)
    acted, escalate_req, events = {"widget": False}, {"v": None}, []
    T._handle_widget_data_tool(
        {"widget_id": "agenda", "action": "set_reminder", "payload": {"remindAt": "12:00"}},
        _apply_widget_data=None, _brief=None, _frontend=fe, _identify=lambda t: "", _repeat_repair=None,
        _say=None, _tag_emit=lambda *a, **k: None, acted=acted, brain=None, clarify={"msg": None},
        deduped={"v": False}, emit=lambda fam, label, **k: events.append(label), escalate_req=escalate_req, text=said)
    return acted, escalate_req, events


def test_the_handed_over_op_opens_a_commission_and_is_not_an_act(monkeypatch):
    said = "Perfecto. Oye, mejor avísame ese día a mediodía, que por la mañana estoy liado."
    acted, escalate_req, events = _run(monkeypatch, said)
    assert any("escala con contexto" in e for e in events), events
    assert escalate_req["v"] == said
    assert acted["widget"] is False, "an escalation is not an act on a card"


def test_a_confident_inline_verdict_keeps_that_commission(monkeypatch):
    """What the flag fed: with `acted` false and nothing running, `handle_inline` has no evidence to annul on."""
    monkeypatch.setattr(eg, "reply_promises", lambda *a, **k: False)
    monkeypatch.setattr(eg, "covered_by_live_work", lambda *a, **k: False)
    v = eg.annulment_verdict("handle_inline", reply="Lo muevo a las doce del mediodía de ese día.", acted=False,
                             anything_running=False, commission="mejor avísame ese día a mediodía")
    assert v["annul"] is False, v
    assert eg.annulment_verdict("handle_inline", reply="", acted=True, anything_running=False)["why"] == "acted"
