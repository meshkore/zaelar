"""Tests de widgets/actions.py — semántica canónica FAST/CONFIRM/ESCALATE (V2-025)."""
from widgets import actions


def test_declared_action_defaults_to_fast():
    # El bug: una data-op trivial (add_meeting) NO puede acabar como trabajo de código. Por defecto = FAST.
    assert actions.classify({"desc": "añade una cita/reunión al día"}, "add_meeting") == actions.FAST
    assert actions.classify({}, "done") == actions.FAST
    assert actions.classify(None, "whatever") == actions.FAST


def test_legacy_safe_never_escalates():
    assert actions.classify({"safe": True}, "done") == actions.FAST
    assert actions.classify({"safe": False}, "add_meeting") == actions.FAST   # antes escalaba; ya NO


def test_explicit_confirm_and_irreversible():
    assert actions.classify({"confirm": True}, "drop_project") == actions.CONFIRM
    assert actions.classify({"irreversible": True}, "wipe") == actions.CONFIRM
    # explícito manda sobre el legacy safe:true
    assert actions.classify({"safe": True, "confirm": True}, "x") == actions.CONFIRM


def test_irreversible_heuristic():
    assert actions.classify({"desc": "paga la factura"}, "pay_invoice") == actions.CONFIRM
    assert actions.classify({"desc": "envía el mensaje al chat"}, "send") == actions.CONFIRM
    assert actions.classify({"desc": "publica el anuncio"}, "publish") == actions.CONFIRM
    # safe:true es una señal explícita de "reversible/trivial" → respeta FAST aunque la desc suene fuerte
    assert actions.classify({"safe": True, "desc": "marca como enviado"}, "mark_sent") == actions.FAST


def test_escape_hatch():
    assert actions.classify({"escalate": True}, "rebuild") == actions.ESCALATE


def test_no_false_positive_on_real_actions():
    # Ninguna acción real de los widgets existentes debe pedir confirmación por accidente.
    for name, desc in [("done", "marca una tarea como hecha"), ("drop", "quita/descarta una tarea"),
                       ("snooze", "aplaza una tarea"), ("hide", "silencia un canal entero, oculta sus mensajes"),
                       ("clear", "limpia todas las líneas y pone el título por defecto"),
                       ("open", "abre una URL o web en el navegador")]:
        assert actions.classify({"desc": desc}, name) == actions.FAST, name


def test_labels():
    assert actions.label(actions.FAST) == "(directa)"
    assert actions.label(actions.CONFIRM) == "(confirmar)"
    assert actions.label(actions.ESCALATE) == "(escala)"
