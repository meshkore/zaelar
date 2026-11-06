"""His sentence about a class of leaving act reaches the exit of that class — and only that class (V2-857 phase 1).

What he does by hand: «no me pidas confirmación para los encargos a los agentes de la red» (or in English); later a
worker sends an errand to a network agent. Before the vocabulary, `errand.mesh_serve` had no genesis row and so no
scope a rule could name: the shaper fell back to `global`, his sentence became «allow EVERYTHING» — or, had the model
kept the words, a note nothing applied. Now every leaving class is a declared event type, the row lands at
`errand/*/mesh_serve`, the exit door runs the send with no question, and the decision is one `consent` event with the
type, the level the vocabulary declared and the winning rule. Nothing else moves: a WhatsApp send keeps its own rule.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from nucleo.events import vocabulary as voc

ES = "no me pidas confirmación para los encargos a los agentes de la red"
EN = "don't ask me before sending an errand to the network's agents"
_SHAPED = ('{"op": "add", "rows": [{"scope": "errand/*/mesh_serve", "kind": "gate", "key": "consent", "value": "allow",'
           ' "except": [], "until": null}], "remove": [], "doubt": [], "say": "ok"}')


@pytest.fixture
def world(monkeypatch):
    import rules
    from connectors.meshkore import security
    from nucleo.workers.prompts import playbook
    rules._reset_for_tests()
    monkeypatch.setattr(security, "enabled", lambda: True)
    monkeypatch.setattr(security, "scan_outbound", lambda t: (t, None))
    monkeypatch.setattr(playbook, "checkpoint_one", lambda rec: "")
    seen: list[dict] = []
    import voice.observer as _obs
    real = _obs.emit
    monkeypatch.setattr(_obs, "emit", lambda kind, label, text="", role="", extra=None, **kw:
                        (seen.append({"kind": kind, "label": label, **(extra or {})}) if kind == "consent" else None)
                        or real(kind, label, text=text, role=role, extra=extra))
    yield SimpleNamespace(seen=seen, rec=SimpleNamespace(task_id="m1", playbook_chosen="errand", uid="", mandate={}))
    rules._reset_for_tests()


@pytest.mark.parametrize("sentence", [ES, EN])
def test_his_sentence_lands_on_the_classs_scope_and_the_exit_runs_without_a_question(world, sentence):
    import rules
    from nucleo import consent
    from nucleo.workers import exit_gate
    from rules import shape
    before = consent.decide_act("errand.mesh_serve", channel="mesh", licensed=True)
    assert before["verdict"] == "run" and before["level"] == "standard" and world.seen[-1]["level_from"] == "declared"
    res = shape.write(sentence, chat=lambda _s, _u: _SHAPED)
    (row,) = res["stored"]
    assert row["scope"] == "errand/*/mesh_serve" and row["key"] == "consent" and row["value"] == "allow"
    out = exit_gate.mesh(world.rec, {"prompt": "find a plumber in Girona", "agent": "ag-1"})
    assert out.question == "" and out.refused == "" and out.payload["prompt"] == "find a plumber in Girona"
    ev = world.seen[-1]
    assert ev["event"] == "errand.mesh_serve" and ev["channel"] == "mesh" and ev["verdict"] == "run"
    assert ev["level"] == "standard" and ev["level_from"] == "declared" and ev["his_yes"] is True
    # only that class moved: a message on WhatsApp still reads its own rule
    assert rules.gate(rules.path(cls="messaging.send_new", channel="whatsapp")) == "allow"   # genesis, untouched
    assert rules.gate(rules.path(cls="payment.authorize")) == "ask"


def test_disarmed_the_class_has_no_scope_and_his_sentence_would_allow_everything(world, monkeypatch):
    from rules import shape, vocabulary as rv
    monkeypatch.setattr(voc, "names", lambda direction="": [])          # the vocabulary no longer declares the classes
    assert not rv.declared("errand/*/mesh_serve")
    res = shape.write(ES, chat=lambda _s, _u: _SHAPED)
    (row,) = res["stored"]
    assert row["scope"] == "global", "with no declared scope his sentence about one class landed on EVERYTHING"
