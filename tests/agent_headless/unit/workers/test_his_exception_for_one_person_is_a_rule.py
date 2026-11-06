"""His exception for ONE person is a rule the doors read (V2-857 phase 2, the `subject:` rung of the cascade).

What he does by hand: «los WhatsApp mándalos sin preguntarme, salvo a Raquel» (or in English). Before, a permission
about one person was a NOTE no gate read, and the engine said so («I can't apply a rule about one person yet»). Now
the shaper is handed the people his sentence names with their ids, writes the general row and the opposite one at
Raquel's subject scope, and every door that knows the person — the one consent rule with a resolved recipient, the
widget's send door, an errand replying to her under its mandate — reads it: WhatsApp to Raquel asks, to Marta runs,
Telegram to Raquel runs (the row names the channel). The decision names its subject on the timeline.
"""
from __future__ import annotations

import json
import re
from types import SimpleNamespace

import pytest

ES = "los WhatsApp mándalos sin preguntarme, salvo a Raquel"
EN = "send WhatsApp messages without asking me, except to Raquel"


def _shaped(_system: str, user: str) -> str:
    """The model's answer, keyed by the id the prompt handed it under PEOPLE NAMED."""
    m = re.search(r"PEOPLE NAMED:\n(\S+) — Raquel", user)
    assert m, "the shaper's message does not name the person with her id"
    return json.dumps({"op": "add", "say": "ok", "remove": [], "doubt": [], "rows": [
        {"scope": "messaging/whatsapp/send_new", "kind": "gate", "key": "consent", "value": "allow", "except": [], "until": None},
        {"scope": f"subject:{m.group(1)}/messaging/whatsapp/send_new", "kind": "gate", "key": "consent", "value": "ask",
         "except": [], "until": None}]})


@pytest.fixture
def world(tmp_path, monkeypatch):
    import rules
    from widgets import directory, store
    from widgets.contactos import data as cd
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    rules._reset_for_tests()
    cd.apply_action("add_contact", {"name": "Raquel Jofre", "phone": "680 762 886"})
    cd.apply_action("add_contact", {"name": "Marta Soler", "phone": "611 222 333"})
    assert directory.note_inbound("whatsapp", {"chatId": "34680762886@s.whatsapp.net", "senderId": "34680762886@s.whatsapp.net", "from": "Raquel"})
    assert directory.note_inbound("whatsapp", {"chatId": "34611222333@s.whatsapp.net", "senderId": "34611222333@s.whatsapp.net", "from": "Marta"})
    ids = {c["name"].split()[0]: c["id"] for c in cd.load_db()["contacts"]}
    seen: list[dict] = []
    import voice.observer as _obs
    real = _obs.emit
    monkeypatch.setattr(_obs, "emit", lambda kind, label, text="", role="", extra=None, **kw:
                        (seen.append(dict(extra or {})) if kind == "consent" else None)
                        or real(kind, label, text=text, role=role, extra=extra))
    yield SimpleNamespace(raquel=ids["Raquel"], marta=ids["Marta"], seen=seen)
    rules._reset_for_tests()


@pytest.mark.parametrize("sentence", [ES, EN])
def test_his_exception_lands_on_her_scope_and_only_her_whatsapp_asks(world, sentence):
    from nucleo import consent
    from nucleo.flash import frontend as fe          # the widget door, as the product reaches it
    from nucleo.errands import mandate
    from rules import labels, shape
    res = shape.write(sentence, chat=_shaped)
    assert {r["scope"] for r in res["stored"]} == {"messaging/whatsapp/send_new",
                                                    f"subject:{world.raquel}/messaging/whatsapp/send_new"}
    # the one consent rule, told who the act is about
    ask = consent.decide_act("messaging.send_new", channel="whatsapp", subject=world.raquel, licensed=True)
    assert ask["verdict"] == "ask_consent" and world.seen[-1]["subject"] == world.raquel
    assert consent.decide_act("messaging.send_new", channel="whatsapp", subject=world.marta, licensed=True)["verdict"] == "run"
    assert consent.decide_act("messaging.send_new", channel="telegram", subject=world.raquel, licensed=True)["verdict"] == "run"
    # the widget's send door resolves the person from the call and reads her rule
    from nucleo.acts import act_policy
    assert act_policy._subject("mensajeria", "send_to", {"contact": "Raquel", "platform": "whatsapp"}) == world.raquel
    assert act_policy._subject("mensajeria", "send_to", {"contact": "nobody known", "platform": "whatsapp"}) == ""
    # an errand replying to her under its mandate reads it too; to Marta it runs
    errand = {"mandate": {"may": ["message"], "channels": ["whatsapp"]}}
    assert mandate.verdict(errand, "whatsapp", "34680762886@s.whatsapp.net")["verdict"] == "ask_consent"
    assert mandate.verdict(errand, "whatsapp", "34611222333@s.whatsapp.net")["verdict"] == "run"
    # the row reads as the person, never as an id
    assert "Raquel" in labels.human(f"subject:{world.raquel}/messaging/whatsapp/send_new")


def test_the_send_door_of_the_card_stops_on_her_rule_and_not_on_martas(world):
    from nucleo.flash import frontend as fe
    from rules import shape
    shape.write(ES, chat=_shaped)
    assert fe._his_rule_holds("mensajeria", "send_to", {"contact": "Raquel", "text": "hola", "platform": "whatsapp"})
    assert not fe._his_rule_holds("mensajeria", "send_to", {"contact": "Marta", "text": "hola", "platform": "whatsapp"})


def test_a_write_that_applied_her_rule_is_not_said_to_be_kept_unapplied(world):
    from nucleo.flash import style_directive as sd
    from rules import shape
    res = shape.write(ES, chat=_shaped)
    assert sd.kept_not_applied(res) == ""


def test_disarmed_without_the_subject_rung_her_exception_is_lost(world, monkeypatch):
    from nucleo import consent
    from rules import shape, vocabulary as rv
    real = rv.declared
    monkeypatch.setattr(rv, "declared", lambda sc: False if str(sc).startswith("subject:") else real(sc))
    res = shape.write(ES, chat=_shaped)
    assert "global" in {r["scope"] for r in res["stored"]}, "the disarm did not take"
    # her row fell to `global`, where the channel's allow outranks it: a WhatsApp to Raquel goes out unasked
    assert consent.decide_act("messaging.send_new", channel="whatsapp", subject=world.raquel, licensed=True)["verdict"] == "run"
