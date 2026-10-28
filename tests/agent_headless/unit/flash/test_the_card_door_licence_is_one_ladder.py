"""The vetoes over a `widget_data` call are ONE ladder read against the request (refactor2710-05 T-02, V2-825 F4 class).

Before the card door, thirteen `if`s across `_handle_widget_data_tool` and `_apply_widget_data` each vetoed the
model's call with its own emit and its own way out. `nucleo.acts.card._LADDER` declares them once; every clause has
its case here, run through `card.licence` (the model's call) or through the REAL gate (`tests/widget_data_rig.py`),
and each case is disarmed: with its clause taken out of the ladder the veto is gone, or the case proves nothing.
"""
from __future__ import annotations

import time

import pytest

from nucleo.acts import card
from tests import widget_data_rig as rig


@pytest.fixture
def screen(tmp_path, monkeypatch):
    rig.scene(tmp_path, monkeypatch)
    import server.voice_api as _va
    from memory import api as _memapi
    from nucleo.flash import data_ops as _do, named_target as _nt
    from nucleo.turn import brief as _tb
    opened = ["youtube", "agenda", "mensajeria"]
    monkeypatch.setattr(_va, "open_instances", lambda: list(opened))
    monkeypatch.setattr(_memapi, "state", lambda *a, **k: {"open_widgets": list(opened)})
    monkeypatch.setattr(_memapi, "kv_get", lambda k, *a, **kw: None)
    monkeypatch.setattr(_tb, "owner_still_open", lambda _b, _o: True)
    _nt._PARKED.clear()
    _do._REFUSED["v"] = None
    yield
    _do._REFUSED["v"] = None


_DENTIST = {"title": "Dentista", "date": "2099-01-05", "time": "10:00"}

#: (clause, moment, card, action, payload, his words, brief, what the licence answers)
CASES = [
    (card._pure_show, card.CALL, "agenda", "add_meeting", {"title": "Reunión con Axa Seguros"}, "abre la agenda",
     None, card.SHOW),
    (card._short_close, card.CALL, "youtube", "mute", {}, "Vale, ciérralo", rig.brief(open_ids=("youtube",)),
     card.CLOSE),
    (card._unlicensed_close, card.CALL, "youtube", "close", {}, "Johnny eres tonto", None, card.DROP),
    (card._a_question, card.DECLARED, "agenda", "add_meeting", {"title": "Anna vacation"},
     "When does Anna's vacation start? Show it to me on the calendar.", rig.brief("none", 0.9, open_ids=("agenda",)),
     card.SHOW),
    (card._a_fragment, card.GATE, "youtube", "set_volume", {"volume": 69}, "sesenta y nueve.",
     rig.brief("none", 0.31, kind="answer", open_ids=("youtube",)), card.DROP),
    (card._context_bleed, card.FAST, "agenda", "add_meeting", _DENTIST, "borra el reloj", None, card.DROP),
]


def _known(clause):
    return {"last_dataop": ("agenda", "add_meeting", dict(_DENTIST), time.time())} if clause is card._context_bleed else {}


@pytest.mark.parametrize("clause,at,wid,action,payload,said,brief,verdict", CASES, ids=[c[0].__name__ for c in CASES])
def test_each_clause_vetoes_its_case_and_only_through_the_ladder(screen, monkeypatch, clause, at, wid, action, payload,
                                                                 said, brief, verdict):
    req = {"brief": brief, "text": said}
    lic = card.licence(req, wid, action, payload, at=at, **_known(clause))
    assert (lic.verdict, lic.clause) == (verdict, clause.__name__.strip("_").replace("_", "-")), lic
    assert lic.outcome().verdict == "skipped"
    # disarm: the same case with its clause out of the ladder is not vetoed by it
    monkeypatch.setitem(card._LADDER, at, tuple(c for c in card._LADDER[at] if c is not clause))
    assert card.licence(req, wid, action, payload, at=at, **_known(clause)).clause != lic.clause


def test_a_close_verdict_closes_the_card_at_the_real_gate(screen, monkeypatch):
    """E5 (demo passes 36/42): «close my mail» ran the card's `close` VIEW over a sure close verdict."""
    from nucleo.flash import direct_action as da
    monkeypatch.setattr(da, "sure_canvas", lambda brief: "close")
    out = rig.run("mensajeria", "close", {}, said="close my mail", turn_brief=rig.brief(), monkeypatch=monkeypatch)
    assert out.ran == [] and ("brain", "🔁 data-op «close» sobre un cierre seguro — cierra la tarjeta") in out.events
    monkeypatch.setitem(card._LADDER, card.GATE, (card._a_fragment,))
    out = rig.run("mensajeria", "close", {}, said="close my mail", turn_brief=rig.brief(), monkeypatch=monkeypatch)
    assert ("brain", "🔁 data-op «close» sobre un cierre seguro — cierra la tarjeta") not in out.events


def test_a_fragment_moves_nothing_at_the_real_gate(screen, monkeypatch):
    """V2-757: «sesenta y nueve.», the tail of a sentence, set the video's volume to 69."""
    b = rig.brief("none", 0.31, kind="answer", open_ids=("youtube",))
    out = rig.run("youtube", "set_volume", {"volume": 69}, said="sesenta y nueve.", turn_brief=b, monkeypatch=monkeypatch)
    assert out.ran == [] and ("brain", "🧩 trozo de frase — no mueve nada en pantalla") in out.events
    monkeypatch.setitem(card._LADDER, card.GATE, (card._close_is_the_card,))
    out = rig.run("youtube", "set_volume", {"volume": 69}, said="sesenta y nueve.", turn_brief=b, monkeypatch=monkeypatch)
    assert ("brain", "🧩 trozo de frase — no mueve nada en pantalla") not in out.events


def test_the_same_refused_op_resent_is_dropped_at_the_real_gate(screen, monkeypatch):
    """V2-773: the model re-read the failure note and re-sent the identical refused op; a corrected one runs."""
    from nucleo.flash import data_ops as _do
    label = ("brain", "🛡️ reintento idéntico de una op rechazada — ignorado")
    _do.remember_refusal("agenda", "add_meeting", dict(_DENTIST))
    out = rig.run("agenda", "add_meeting", dict(_DENTIST), said="apunta el dentista", monkeypatch=monkeypatch)
    assert out.ran == [] and label in out.events
    out = rig.run("agenda", "add_meeting", {**_DENTIST, "time": "11:00"}, said="apunta el dentista",
                  monkeypatch=monkeypatch)
    assert out.ran and label not in out.events, "a corrected retry runs"
    _do.remember_refusal("agenda", "add_meeting", dict(_DENTIST))
    monkeypatch.setitem(card._LADDER, card.FAST, (card._context_bleed,))
    out = rig.run("agenda", "add_meeting", dict(_DENTIST), said="apunta el dentista", monkeypatch=monkeypatch)
    assert label not in out.events and out.ran


def test_a_send_the_verdict_puts_on_another_card_is_dropped_with_its_note(screen, monkeypatch):
    """Demo pass 45, C2→C5: «ok book it» sent two Telegrams to Rowan he never ordered."""
    from nucleo.flash import direct_action as da
    monkeypatch.setattr(da, "verdict_elsewhere", lambda brief, wid: wid == "mensajeria")
    pushed = []
    from voice import brain_notes as _bn
    monkeypatch.setattr(_bn, "push", lambda note, *a, **k: pushed.append(note))
    lic = card.licence({"brief": rig.brief("agenda:find_free"), "text": "find me a free slot"}, "mensajeria",
                       "send_to", {"to": "Rowan"}, at=card.LEAVES)
    assert (lic.verdict, lic.clause) == (card.DROP, "leaves-for-another-card")
    assert pushed and "NO se ejecutó" in pushed[0]
    monkeypatch.setitem(card._LADDER, card.LEAVES, ())
    assert card.licence({"brief": None, "text": ""}, "mensajeria", "send_to", {}, at=card.LEAVES).verdict == card.RUN


def test_an_unreadable_clause_does_not_veto(monkeypatch):
    """CRIT-K2: a reading that cannot be made never contradicts the model."""
    def broken(*_a, **_k):
        raise RuntimeError("no brief")
    monkeypatch.setitem(card._LADDER, card.GATE, (broken,))
    assert card.licence({"brief": None, "text": "x"}, "agenda", "add_meeting", {}, at=card.GATE).verdict == card.RUN


def test_the_gate_emits_each_veto_once():
    """§2b — every veto keeps its event, emitted by the door (`logged`), the label the `if` emitted before."""
    seen = []
    card.logged(card.Licence(card.DROP, "x", "🛡️ label", "agenda:add", {"id": "agenda"}),
                lambda kind, label, **kw: seen.append((kind, label, kw.get("extra"))))
    card.logged(card.Licence(card.DROP, "unlicensed-close"), lambda *a, **k: seen.append(a))
    assert seen == [("brain", "🛡️ label", {"id": "agenda"})], "a clause that logged its own reason is not logged twice"


def test_a_standalone_reminder_reaches_the_agenda_untouched(screen, monkeypatch):
    """Agreed with the message door (refactor2710-06): a notice with no appointment is the agenda's declared
    `add_reminder`; the card door passes its payload as the model wrote it, no slot read off his words."""
    pay = {"notice_at": "2099-01-01 09:00", "commitment": "x"}
    out = rig.run("agenda", "add_reminder", dict(pay), said="remind me on January 1st 2099 at nine about x",
                  monkeypatch=monkeypatch)
    assert out.ran == [("agenda", "add_reminder", pay)] and out.asked == []
