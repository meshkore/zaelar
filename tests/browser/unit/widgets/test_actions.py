"""Tests for widgets/actions.py — canonical FAST/CONFIRM/ESCALATE semantics (V2-025)."""
from widgets import actions


def test_declared_action_defaults_to_fast():
    # The bug: a trivial data-op (add_meeting) must NOT end up as code work. Default = FAST.
    assert actions.classify({"desc": "añade una cita/reunión al día"}, "add_meeting") == actions.FAST
    assert actions.classify({}, "done") == actions.FAST
    assert actions.classify(None, "whatever") == actions.FAST


def test_legacy_safe_never_escalates():
    assert actions.classify({"safe": True}, "done") == actions.FAST
    assert actions.classify({"safe": False}, "add_meeting") == actions.FAST   # it used to escalate; it does NOT anymore


def test_explicit_confirm_and_irreversible():
    assert actions.classify({"confirm": True}, "drop_project") == actions.CONFIRM
    assert actions.classify({"irreversible": True}, "wipe") == actions.CONFIRM
    # explicit takes precedence over legacy safe:true
    assert actions.classify({"safe": True, "confirm": True}, "x") == actions.CONFIRM


def test_irreversible_heuristic():
    assert actions.classify({"desc": "paga la factura"}, "pay_invoice") == actions.CONFIRM
    assert actions.classify({"desc": "envía el mensaje al chat"}, "send") == actions.CONFIRM
    assert actions.classify({"desc": "publica el anuncio"}, "publish") == actions.CONFIRM
    # safe:true is an explicit "reversible/trivial" signal → honor FAST even if the description sounds forceful
    assert actions.classify({"safe": True, "desc": "marca como enviado"}, "mark_sent") == actions.FAST


def test_escape_hatch():
    assert actions.classify({"escalate": True}, "rebuild") == actions.ESCALATE


def test_no_false_positive_on_real_actions():
    # No real action from the existing widgets should accidentally request confirmation.
    for name, desc in [("done", "marca una tarea como hecha"), ("drop", "quita/descarta una tarea"),
                       ("snooze", "aplaza una tarea"), ("hide", "silencia un canal entero, oculta sus mensajes"),
                       ("clear", "limpia todas las líneas y pone el título por defecto"),
                       ("open", "abre una URL o web en el navegador")]:
        assert actions.classify({"desc": desc}, name) == actions.FAST, name


def test_labels():
    assert actions.label(actions.FAST) == "(directa)"
    assert actions.label(actions.CONFIRM) == "(confirmar)"
    assert actions.label(actions.ESCALATE) == "(escala)"
