#
# test_the_auditor_knows_which_layer_acted.py — V2-539.
#
# TWO layers resolve turns — the fast brain (a model) and the ACTION MAP (a table, no model at all) — and the
# auditor was told about neither. Measured 2026-09-01 on six real voice turns the map served: the auditor
# concluded, verbatim, «el cerebro rápido ejecutó correctamente cada orden», crediting a model that never ran.
# An auditor that misattributes the LAYER proposes corrections against the wrong one: a map entry pointing at
# the wrong action is a routing FINDING, not a repair_say aimed at the model's wording.
#
# Run: .venv/bin/pytest tests/agent_headless/unit/susurro/test_the_auditor_knows_which_layer_acted.py
#
from nucleo.susurro import catalog
from nucleo.susurro.window import turns_block


def _turn(user, decision, trace="T1"):
    return {"user": user, "decision": decision, "trace": trace}


def test_a_map_turn_is_named_as_the_map_not_as_a_flag_list():
    block = turns_block([_turn("abre el whatsapp",
                               {"action": "canvas:show:mensajeria", "actionmap": 14})])
    assert "MAPA DE ACCIONES" in block
    assert "SIN modelo" in block
    assert "canvas:show:mensajeria" in block
    assert "[entrada 14]" in block


def test_a_model_turn_is_rendered_exactly_as_before():
    """The regression that matters: naming the map must not change how a model turn reads."""
    block = turns_block([_turn("¿qué tal?", {"widget_acted": True, "reply": "bien"})])
    assert "MAPA DE ACCIONES" not in block
    assert "widget_acted=True" in block


def test_both_layers_in_one_window_stay_distinguishable():
    block = turns_block([
        _turn("abre el whatsapp", {"action": "canvas:show:mensajeria", "actionmap": 14}, "T1"),
        _turn("¿tengo mensajes nuevos?", {"widget_acted": True, "reply": "tienes dos"}, "T2"),
    ])
    lines = block.splitlines()
    assert len(lines) == 2
    assert "MAPA DE ACCIONES" in lines[0] and "MAPA DE ACCIONES" not in lines[1]


def test_a_plain_conversational_turn_still_says_charla():
    assert "charla" in turns_block([_turn("hola", {})])


def test_the_system_prompt_teaches_the_two_layers_and_where_a_map_fault_goes():
    """Without this, the auditor has the marker in its window and no idea what it means."""
    assert "MAPA DE ACCIONES" in catalog.SYSTEM
    assert "SIN llamar a ningún modelo" in catalog.SYSTEM
    # A map fault is a different CLASS of fault and must not be blamed on the model. Matched on a single
    # word on purpose: the sentence wraps in the source, and a literal spanning two lines is how a check
    # like this passes while asserting nothing.
    assert "atribuyas" in catalog.SYSTEM
    assert "finding" in catalog.SYSTEM and "routing" in catalog.SYSTEM
