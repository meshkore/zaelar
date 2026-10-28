"""A data-op NAMED «close» over a sure close verdict is the card's own close (demo passes 36/42, 2026-09-29, E5).

«close my mail» — the model called the messaging card's `close` VIEW action (back to the chat list); the canvas
verdict read `close` sure; the card stayed on screen while the reply said the mail was closed, and the next order
found the mail still there."""


def test_a_close_op_under_a_sure_close_verdict_is_the_card(monkeypatch):
    from nucleo.flash import direct_action as da
    monkeypatch.setattr(da, "sure_canvas", lambda brief: "close")
    assert da.close_op_is_the_card(object(), "close")
    assert not da.close_op_is_the_card(object(), "unread"), "only an op named close"
    monkeypatch.setattr(da, "sure_canvas", lambda brief: "")
    assert not da.close_op_is_the_card(object(), "close"), "an unsure verdict keeps the card's own view op"


def test_the_data_op_door_closes_the_card_instead(monkeypatch):
    """The card door's GATE ladder reads it first, and the gate closes the card the licence names."""
    from nucleo.acts import card
    from nucleo.flash import direct_action as da, show_target as st
    monkeypatch.setattr(da, "sure_canvas", lambda brief: "close")
    monkeypatch.setattr(st, "close_target", lambda wid: f"{wid}::1")
    lic = card.licence({"brief": object(), "text": "close my mail"}, "mensajeria", "close", {}, at=card.GATE)
    assert (lic.verdict, lic.clause, lic.card) == (card.CLOSE, "close-is-the-card", "mensajeria::1")
    assert card._LADDER[card.GATE][0] is card._close_is_the_card, "before the fragment rule, as it was"


def _through_the_gate(monkeypatch, said: str, canvas: str):
    """The model's `mensajeria:close` through the REAL data-op gate (`_apply_widget_data`, as `widget_data_rig` drives
    it), with the canvas tags it emits recorded: what the screen was told, and which ops started."""
    import threading
    from types import SimpleNamespace
    from nucleo.flash import frontend, tool_executor_widget as txw, tool_executor_widget_calls as calls
    import server.voice_api as va
    monkeypatch.setattr(va, "open_instances", lambda: ["mensajeria"])
    out = SimpleNamespace(ran=[], tags=[])
    monkeypatch.setattr(txw._data_ops, "start_op", lambda wid, act, pay, **k: out.ran.append((wid, act)))
    ev = threading.Event()
    ev.set()
    result = {"request_type": {"choice": "order", "confidence": 1.0}}
    if canvas:
        result["canvas"] = {"choice": canvas, "confidence": 0.97}
    brief = {"event": ev, "turn_id": "t-gate", "open_ids": ["mensajeria"], "result": result}
    brain = SimpleNamespace(_window=[], _last_dataop=None, _last_spoken="", _last_action="")

    def apply(wid, act, pay, ref=""):
        calls._apply_widget_data(
            wid, act, pay, ref, _apply_widget_data=apply, _brief=brief, _frontend=frontend,
            _request_data_confirm=lambda *a: None, _spawn=lambda *a, **k: None,
            _tag_emit=lambda action, extra: out.tags.append((action, extra.get("id"))), _turn_op_tasks=[],
            acted={"widget": False}, brain=brain, data_done={"v": False}, deduped={"v": False},
            emit=lambda *a, **k: None, escalate_req={"v": None}, text=said)
    apply("mensajeria", "close", {})
    return out


def test_the_gate_tells_the_screen_to_close_the_card_and_runs_no_view(monkeypatch):
    """Another wording, another language: «cierra el correo» over a sure close — the card closes, the view never runs."""
    out = _through_the_gate(monkeypatch, "cierra el correo, ya está", "close")
    assert out.tags == [("close", "mensajeria")] and out.ran == [], (out.tags, out.ran)


def test_without_a_sure_close_the_cards_own_view_op_runs(monkeypatch):
    out = _through_the_gate(monkeypatch, "go back to the chat list", "")
    assert out.tags == [] and out.ran == [("mensajeria", "close")], (out.tags, out.ran)


def test_the_disarm_a_gate_blind_to_the_verdict_runs_the_view_and_leaves_the_card(monkeypatch):
    """E5 restored: with `close_op_is_the_card` off, the same sentence runs the messaging card's `close` VIEW and the
    card stays on screen while the reply says the mail was closed."""
    from nucleo.flash import direct_action as da
    monkeypatch.setattr(da, "close_op_is_the_card", lambda *a, **k: False)
    assert not da.close_op_is_the_card(object(), "close"), "the mutation landed"
    out = _through_the_gate(monkeypatch, "cierra el correo, ya está", "close")
    assert ("close", "mensajeria") not in out.tags and out.ran == [("mensajeria", "close")], (out.tags, out.ran)
