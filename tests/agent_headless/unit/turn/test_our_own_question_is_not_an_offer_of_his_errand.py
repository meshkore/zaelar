"""Our own question is not an offer of HIS errand (node 2.437).

three-tasks-at-once (ES, 2026-10-11 02:04). The confirmation gate parked the platform game and asked «¿La hago?» as a
[SISTEMA] note. His next turn, «Vale. Del informe quítame los híbridos…», reached the escalation portal with
`asked` = HIS turn — note included — because the text channel passed the operator's text where the voice channel
passes the REPLY. The portal saw «¿La hago?», read it as our permission question, and parked «del informe quítame los
híbridos» as a fresh OFFER. Being newer, that offer became «the» pending confirmation: «Sí, móntalo» was then judged
against it, the game stayed parked, expired, and was later told as «nunca llegaste a confirmarlo».

Three mechanisms, each on its own consequence:
  · the turn passes the reply as `asked` (`turn_after.py`'s `spoken_text`);
  · the portal strips [SISTEMA] notes from `asked` — our notice is nobody's question;
  · a permission question that re-asks an errand ALREADY parked offers that errand, not the turn's other one.
"""
from __future__ import annotations

import time

import pytest

from nucleo import dispatch
from nucleo.dispatch import confirm as dc
from nucleo.acts import errand as esc

GAME = "Crear un NUEVO widget de juego de plataformas tipo Super Mario (saltar, moverse, enemigos)"
NOTE = ("[SISTEMA] Aviso para el operador (zaelar): Si no te he entendido mal, me pides que te CONSTRUYA una tarjeta "
        "nueva («" + GAME[:60] + "…»). Tarda unos minutos y se queda en tu catálogo. ¿La hago? Díselo con tus "
        "palabras DESPUÉS de contestar a lo que te ha pedido — todavía no lo sabe.")
HIS = "Vale. Del informe quítame los híbridos, solo eléctricos puros. ¿Y el monitor qué tal lo llevas?"


@pytest.fixture
def bus(monkeypatch):
    published = []
    monkeypatch.setattr(esc, "_emit_bus", lambda topic, payload: published.append(topic))
    monkeypatch.setattr(dispatch, "pending_summaries", lambda: [])
    monkeypatch.setattr(dc, "_PENDING_CONFIRM", {})
    monkeypatch.setattr(dc, "_EXPIRED_CONFIRM", {})
    return published


def test_our_note_in_his_turn_parks_nothing(bus):
    tid = esc.escalate_to_slowbrain(HIS, context={"src": "probe", "asked": NOTE + "\n\n" + HIS})
    assert tid and bus == ["escalate.requested"], bus
    assert not dc._PENDING_CONFIRM, "his refinement is not an offer of ours"


def test_re_asking_a_parked_errand_does_not_park_another_one(bus):
    dc._PENDING_CONFIRM["7"] = {"request": GAME, "kind": "code", "trusted": True, "context": {}, "sheet": "",
                                "ts": time.time(), "question": "¿La hago?"}
    reply = ("Hecho: al informe le quito los híbridos. Y lo otro: el juego de plataformas hay que construirlo de cero. "
             "¿Quieres que te lo monte?")
    tid = esc.escalate_to_slowbrain(HIS, context={"src": "probe", "asked": reply})
    assert tid and bus == ["escalate.requested"]
    assert list(dc._PENDING_CONFIRM) == ["7"], "the game stays the one waiting on him"


def test_an_offer_of_this_very_errand_is_still_parked(bus):
    tid = esc.escalate_to_slowbrain("buscar vuelos a Roma",
                                    context={"src": "probe", "asked": "¿Quieres que te busque vuelos a Roma?"})
    assert tid == 0 and bus == ["escalate.offered"]
