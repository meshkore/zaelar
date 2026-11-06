"""Consent is decided at the EXIT (the event), never at an errand's birth from its words (V2-857 phase 4).

What he does by hand: «mira cuánto pago de luz este mes, no pagues nada» — the brief's verdict says the errand only
LOOKS, but the money vocabulary (`danger`) read «pago» and the errand was parked with «this moves money, shall I go
on?». And «escríbele a Marta que llego tarde» was asked at birth (`errand.sends_for_him`) AND again at the exit
(`messaging.send_new@whatsapp`): two keys for one event, so his «WhatsApp without asking» rule reached only the
second. Now the errand's class is the brief's verdict alone ("none" with no verdict), only a CRITICAL class (money,
his accounts) asks at birth — through the asker, on its row — and a send is decided once, at its exit door, where his
channel and person rules live. The question a parked money errand hears is chosen by its CLASS, not by its words.
"""
from __future__ import annotations

import pytest

from nucleo import danger
from nucleo.acts import errand

LOOKS = {"es": "mira cuánto pago de luz este mes, no pagues nada",
         "en": "check how much I pay for electricity this month, do not pay anything"}
PAYS = {"es": "paga la factura de la luz de este mes", "en": "pay this month's electricity bill"}


@pytest.fixture
def events(monkeypatch):
    seen: list[tuple] = []
    import voice.observer as _obs
    real = _obs.emit
    monkeypatch.setattr(_obs, "emit", lambda kind, label, text="", role="", extra=None, **kw:
                        seen.append((kind, label, dict(extra or {}))) or real(kind, label, text=text, role=role, extra=extra))
    from nucleo import consent
    consent._reset_for_tests()
    yield seen
    consent._reset_for_tests()


@pytest.mark.parametrize("lang", ["es", "en"])
def test_the_words_no_longer_decide_the_class_only_the_brief_does(events, lang):
    assert danger.is_dangerous(PAYS[lang]), "the vocabulary would have parked this — the premise of the test"
    assert errand.class_of(None, PAYS[lang]) == "none", "with no verdict the words decided the class"
    assert errand.class_of({"choice": "none", "confidence": 0.6}, PAYS[lang]) == "none"
    assert errand.class_of({"choice": "moves_money", "confidence": 0.8}, LOOKS[lang]) == "moves_money"
    assert errand.class_of({"choice": "moves_money", "confidence": 0.4}, PAYS[lang]) == "none", "below the licence"
    kinds = [(k, e.get("errand_class"), e.get("from")) for k, _l, e in events if e.get("errand_class") is not None]
    assert ("task", "none", "no verdict") in kinds and ("task", "moves_money", "verdict") in kinds


def test_only_a_critical_class_asks_at_birth_and_a_send_is_decided_at_its_exit(events):
    assert errand.asks_first("moves_money", confirmed=False)
    assert errand.asks_first("account_change", confirmed=False)
    assert not errand.asks_first("moves_money", confirmed=True)
    before = len([e for e in events if e[0] == "consent"])
    assert not errand.asks_first("sends_for_him", confirmed=False), "a send was asked at birth AND at its exit"
    assert not errand.asks_first("none", confirmed=False)
    assert len([e for e in events if e[0] == "consent"]) == before, "the birth consulted the consent door for a send"
    # the send's one decision, at the exit, with his channel rule
    from nucleo import consent
    v = consent.decide_act("messaging.send_new", channel="whatsapp", licensed=True)
    ev = [e for k, _l, e in events if k == "consent"][-1]
    assert v["verdict"] == "run" and ev["event"] == "messaging.send_new" and ev["channel"] == "whatsapp"


@pytest.mark.parametrize("lang", ["es", "en"])
def test_the_parked_errands_question_is_chosen_by_its_class_not_its_words(lang):
    from i18n import langs
    sp = langs.current_language()                   # the question is said in the interface's language, whatever his words
    assert danger.confirm_question(LOOKS[lang], cls="moves_money") == sp.spend_confirm.format(what=LOOKS[lang])
    assert danger.confirm_question(PAYS[lang], cls="account_change") == sp.irreversible_confirm.format(what=PAYS[lang])
    assert danger.confirm_question(PAYS[lang]) == sp.spend_confirm.format(what=PAYS[lang]), "with no class, the words still choose"


def test_the_birth_gate_reads_the_class_through_the_vocabulary():
    import inspect
    from nucleo.dispatch import confirm as dc, session
    assert "danger.is_dangerous" not in inspect.getsource(errand.class_of)
    assert 'cls=' in inspect.getsource(session) and 'cls=' in inspect.getsource(dc.remember_confirm)
    from nucleo.events import vocabulary as voc
    assert voc.level_of("errand.sends_for_him") != "critical" and voc.level_of("errand.moves_money") == "critical"


def test_disarmed_the_vocabulary_fills_the_class_and_a_look_is_parked_as_money(monkeypatch):
    real = errand.class_of
    monkeypatch.setattr(errand, "class_of", lambda verdict, request: real(verdict, request) if verdict
                        else ("moves_money" if danger.is_dangerous(request) else "none"))
    assert errand.class_of(None, PAYS["es"]) == "moves_money", "the disarm did not take"
    assert errand.asks_first(errand.class_of(None, PAYS["es"]), confirmed=False), "with the words deciding, a look is parked"
