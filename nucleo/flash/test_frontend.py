"""Tests de nucleo/flash/frontend.py (V2-004 · T62) — tags de canvas + gate de gobernanza de widgets."""
from nucleo.flash import frontend
from voice.tag_protocol import strip_tags


def test_show_close_move_tags():
    assert frontend.show("Clock") == "[[show:clock]]"
    assert frontend.close("clock") == "[[close:clock]]"
    assert frontend.close() == "[[close]]"
    assert frontend.move("agenda", "Izquierda") == "[[move:agenda:izquierda]]"
    assert frontend.move("agenda", "diagonal") == ""     # dirección desconocida → sin tag


def test_show_tag_parses_via_tag_protocol():
    """El tag que componemos lo entiende el mismo strip_tags del contrato de voz."""
    events = []
    spoken, rest = strip_tags("Aquí tienes. " + frontend.show("clock"), lambda a, e: events.append((a, e)), True)
    assert ("show", {"id": "clock"}) in events
    assert "Aquí tienes." in spoken and "[[" not in spoken


def test_action_mode_three_ways(monkeypatch):
    """V2-025: toda acción declarada es una data-op del FlashBrain — FAST por defecto, CONFIRM si es
    irreversible, ESCALATE solo con la vía de escape explícita, None si no está declarada."""
    from widgets import actions
    import widgets.runtime as rt
    monkeypatch.setattr(rt, "get", lambda wid: {"actions": {
        "add_meeting": {"desc": "añade una cita"},          # data-op normal → FAST (era el bug: escalaba)
        "done": {"safe": True},                             # legacy safe:true → FAST
        "drop_project": {"confirm": True},                  # irreversible explícito → CONFIRM
        "pagar": {"desc": "paga la factura"},               # heurístico de irreversibilidad → CONFIRM
        "rebuild": {"escalate": True},                      # vía de escape → ESCALATE
    }})
    assert frontend.action_mode("agenda", "add_meeting") == actions.FAST
    assert frontend.action_mode("agenda", "done") == actions.FAST
    assert frontend.action_mode("agenda", "drop_project") == actions.CONFIRM
    assert frontend.action_mode("agenda", "pagar") == actions.CONFIRM
    assert frontend.action_mode("agenda", "rebuild") == actions.ESCALATE
    assert frontend.action_mode("agenda", "inexistente") is None     # no declarada → None (el llamante escala)


def test_is_safe_action_compat(monkeypatch):
    """`is_safe_action` = compat, True SOLO en modo FAST (sin confirmación)."""
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
    assert frontend.widget_action_tag("agenda", "inexistente", {}) is None   # no declarada → None


def test_canvas_verb_maps_pseudo_dataops():
    """Diag sesiones-largas 2026-07-15: a profundidad el modelo cuela el SHOW/CLOSE como pseudo data-op
    (`widget_data(clock, action="show")`). `canvas_verb` da la tag canónica; una acción real devuelve None."""
    assert frontend.canvas_verb("show") == "show"
    assert frontend.canvas_verb("Abrir") == "show"
    assert frontend.canvas_verb("muestra") == "show"
    assert frontend.canvas_verb("enséña") == "show"          # acento-insensible
    assert frontend.canvas_verb("close") == "close"
    assert frontend.canvas_verb("ocultar") == "close"
    assert frontend.canvas_verb("done") is None              # data-op real → no es verbo de canvas
    assert frontend.canvas_verb("add_meeting") is None
    assert frontend.canvas_verb("") is None
    # "quitar"/"borrar" NO son canvas (quitan DATOS o borran el widget — otra ruta): jamás mapear a close.
    assert frontend.canvas_verb("quitar") is None
    assert frontend.canvas_verb("borrar") is None


def test_action_mode_failclosed_on_error(monkeypatch):
    import widgets.runtime as rt
    def boom(wid):
        raise RuntimeError("catálogo roto")
    monkeypatch.setattr(rt, "get", boom)
    assert frontend.action_mode("agenda", "done") is None
    assert not frontend.is_safe_action("agenda", "done")
