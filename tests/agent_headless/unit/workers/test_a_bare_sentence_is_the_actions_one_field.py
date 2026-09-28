"""A bare sentence given to an action with ONE declared field is that field (demo pass 30, F1, 2026-09-28).

`widget_cli data documento goto "Bottom line"` died with «el payload (argumento) no es JSON válido». `goto`
declares a single field (`text`) and names it as its `ref`: the sentence could only mean one thing. An action with
several fields still refuses — and now says the shape it wants.
"""
from nucleo import widget_cli as W


def test_a_sentence_goes_to_the_single_declared_field(monkeypatch):
    sent = []
    monkeypatch.setattr(W, "_act", lambda op, body: sent.append(body) or {"ok": True})
    assert W.main(["widget_cli", "data", "documento", "goto", "Bottom line"]) == 0
    assert sent == [{"widget_id": "documento", "action": "goto", "payload": {"text": "Bottom line"}}]


def test_json_still_goes_through_as_json(monkeypatch):
    sent = []
    monkeypatch.setattr(W, "_act", lambda op, body: sent.append(body) or {"ok": True})
    assert W.main(["widget_cli", "data", "documento", "goto", '{"text": "Proof of work"}']) == 0
    assert sent[0]["payload"] == {"text": "Proof of work"}


def test_an_action_with_several_fields_refuses_and_shows_the_shape(monkeypatch, capsys):
    monkeypatch.setattr(W, "_act", lambda op, body: {"ok": True})
    assert W.main(["widget_cli", "data", "documento", "show", "hello"]) == 2
    out = capsys.readouterr().out
    assert '"body"' in out and '"title"' in out
