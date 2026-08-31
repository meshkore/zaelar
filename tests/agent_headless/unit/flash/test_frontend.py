"""Tests for nucleo/flash/frontend.py (V2-004 · T62) — canvas tags + widget governance gate."""
from nucleo.flash import frontend
from voice.tag_protocol import strip_tags


def test_show_close_move_tags():
    assert frontend.show("Clock") == "[[show:clock]]"
    assert frontend.close("clock") == "[[close:clock]]"
    assert frontend.close() == "[[close]]"
    assert frontend.move("agenda", "Izquierda") == "[[move:agenda:izquierda]]"
    assert frontend.move("agenda", "diagonal") == ""     # unknown direction → no tag


def test_show_tag_parses_via_tag_protocol():
    """The tag we compose is understood by the same strip_tags from the voice contract."""
    events = []
    spoken, rest = strip_tags("Aquí tienes. " + frontend.show("clock"), lambda a, e: events.append((a, e)), True)
    assert ("show", {"id": "clock"}) in events
    assert "Aquí tienes." in spoken and "[[" not in spoken


def test_action_mode_three_ways(monkeypatch):
    """V2-025: every declared action is a FlashBrain data-op — FAST by default, CONFIRM if it is
    irreversible, ESCALATE only through the explicit escape hatch, None if it is undeclared."""
    from widgets import actions
    import widgets.runtime as rt
    monkeypatch.setattr(rt, "get", lambda wid: {"actions": {
        "add_meeting": {"desc": "añade una cita"},          # normal data-op → FAST (the bug was that it escalated)
        "done": {"safe": True},                             # legacy safe:true → FAST
        "drop_project": {"confirm": True},                  # explicitly irreversible → CONFIRM
        "pagar": {"desc": "paga la factura"},               # irreversibility heuristic → CONFIRM
        "rebuild": {"escalate": True},                      # escape hatch → ESCALATE
    }})
    assert frontend.action_mode("agenda", "add_meeting") == actions.FAST
    assert frontend.action_mode("agenda", "done") == actions.FAST
    assert frontend.action_mode("agenda", "drop_project") == actions.CONFIRM
    assert frontend.action_mode("agenda", "pagar") == actions.CONFIRM
    assert frontend.action_mode("agenda", "rebuild") == actions.ESCALATE
    assert frontend.action_mode("agenda", "inexistente") is None     # undeclared → None (the caller escalates)


def test_is_safe_action_compat(monkeypatch):
    """`is_safe_action` = compatibility; True ONLY in FAST mode (without confirmation)."""
    import widgets.runtime as rt
    monkeypatch.setattr(rt, "get", lambda wid: {"actions": {"done": {}, "drop_project": {"confirm": True}}})
    assert frontend.is_safe_action("agenda", "done")                 # FAST
    assert not frontend.is_safe_action("agenda", "drop_project")     # CONFIRM ≠ FAST
    assert not frontend.is_safe_action("agenda", "inexistente")


def test_widget_action_tag_for_data_ops(monkeypatch):
    import widgets.runtime as rt
    monkeypatch.setattr(rt, "get", lambda wid: {"actions": {"done": {}, "drop_project": {"confirm": True},
                                                            "rebuild": {"escalate": True}}})
    tag = frontend.widget_action_tag("agenda", "done", {"taskId": "t1"})
    assert tag.startswith("[[widget.data:agenda]]") and '"action": "done"' in tag
    assert frontend.widget_action_tag("agenda", "drop_project", {}).startswith("[[widget.data:agenda]]")  # CONFIRM
    assert frontend.widget_action_tag("agenda", "rebuild", {}) is None       # ESCALATE → None
    assert frontend.widget_action_tag("agenda", "inexistente", {}) is None   # undeclared → None


def test_canvas_verb_maps_pseudo_dataops():
    """Long-session diagnostic 2026-07-15: deep in the model, SHOW/CLOSE slips through as a pseudo data-op
    (`widget_data(clock, action="show")`). `canvas_verb` returns the canonical tag; a real action returns None."""
    assert frontend.canvas_verb("show") == "show"
    assert frontend.canvas_verb("Abrir") == "show"
    assert frontend.canvas_verb("muestra") == "show"
    assert frontend.canvas_verb("enséña") == "show"          # accent-insensitive
    assert frontend.canvas_verb("close") == "close"
    assert frontend.canvas_verb("ocultar") == "close"
    assert frontend.canvas_verb("done") is None              # real data-op → not a canvas verb
    assert frontend.canvas_verb("add_meeting") is None
    assert frontend.canvas_verb("") is None
    # "quitar"/"borrar" are NOT canvas (they remove DATA or delete the widget — another route): never map to close.
    assert frontend.canvas_verb("quitar") is None
    assert frontend.canvas_verb("borrar") is None


def test_action_mode_failclosed_on_error(monkeypatch):
    import widgets.runtime as rt
    def boom(wid):
        raise RuntimeError("catálogo roto")
    monkeypatch.setattr(rt, "get", boom)
    assert frontend.action_mode("agenda", "done") is None
    assert not frontend.is_safe_action("agenda", "done")


def test_probe_deictic_show_uses_recent_conversation(monkeypatch):
    from nucleo.flash import probe, show_target

    # patched on show_target (the defining module) — probe re-exports these names since the extraction
    monkeypatch.setattr(show_target, "_identify_ctx",
                        lambda _runtime, text: "meteo-soria" if "tiempo" in text.lower() else None)
    context = [{"role": "user", "content": "¿Qué tiempo hará mañana aquí?"}]
    assert probe._show_target("Vale, pues muéstramelo.", context) == "meteo-soria"
