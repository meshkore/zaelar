"""V2-544 — «abre el mensaje de Francisco» must reach the widget's declared action, not show_widget.

Live incident (2026-09-01, 4/4 turns): with the mensajeria card ON SCREEN, «Sí» to the model's own
«¿Quieres que lo abra?», «Abre el mensaje.» and «Abre el mensaje de Francisco.» all produced a bare
show_widget over an unmoved card plus «Aquí lo tienes.» The model was OBEYING its instructions: the
canvas block commanded «"abre X" = [[show:X]], jamás widget_data», widget_data's description claimed
data-MUTATION only and disowned "abrir" wholesale, and its parameter docs cited catalogs («Available
widgets», «ACCIONES POR WIDGET») that do not exist under those names in the built prompt — while the
resources block taught the opposite («abre el chat de X» → open). A prompt that contradicts itself loses
to its own imperative (V2-222: 0/13). These tests pin the un-contradicted mapping.
"""
from __future__ import annotations

import inspect
import pathlib

from nucleo.flash import router

ENGINE = pathlib.Path(__file__).resolve().parents[4]


def _tool(name: str) -> dict:
    return next(t["function"] for t in router.TOOLS if t["function"]["name"] == name)


def _prompt_src() -> str:
    return (ENGINE / "nucleo" / "flash" / "prompt.py").read_text(encoding="utf-8")


# ── The canvas block no longer forbids what the resources block teaches ─────────────────────────────────────

def test_the_prompt_never_says_jamas_widget_data():
    """The absolute that caused the incident: any comeback of «jamás widget_data» re-opens the
    contradiction with the resources catalog («abre el chat de X» → open)."""
    assert "jamás widget_data" not in _prompt_src()


def test_the_canvas_block_teaches_the_inside_with_a_concrete_example():
    src = _prompt_src()
    assert "UN ELEMENTO DE DENTRO" in src and "open " in src, \
        "the widget-vs-inside bifurcation left the canvas block"
    assert "widget_data con la acción" in src, "the inside must be routed to widget_data, by name"


def test_a_yes_to_your_own_offer_is_an_order_to_execute_it():
    """First failure of the night: «Sí.» after «¿Quieres que lo abra?» re-showed the card."""
    src = _prompt_src()
    assert "OFERTA que TÚ acabas de hacer" in src and "no de volver a enseñar la tarjeta" in src


# ── The tool descriptions carry the same map ────────────────────────────────────────────────────────────────

def test_widget_data_owns_in_widget_navigation():
    desc = _tool("widget_data")["description"]
    assert "NAVEGAR DENTRO" in desc and "open {name:" in desc
    assert "WIDGET ENTERO" in desc, "it must disown only the whole-widget open/close, not the inside"


def test_show_widget_points_the_inside_at_widget_data():
    desc = _tool("show_widget")["description"]
    assert "DE DENTRO" in desc and "widget_data" in desc
    assert "repetir show" in desc, "the uselessness of re-showing an on-screen card is the teachable fact"


def test_the_catalogs_the_tool_cites_actually_exist_in_the_resources_block():
    """The parameter docs said «de 'Available widgets'» and «de 'ACCIONES POR WIDGET'» — names the built
    prompt NEVER renders (the real block is «Widgets del canvas» with a «datos:» line per widget). A
    model told to copy exact names from a catalog it cannot find avoids the tool instead."""
    fn = _tool("widget_data")
    params = str(fn["parameters"])
    assert "Available widgets" not in params and "ACCIONES POR WIDGET" not in params
    assert "Widgets del canvas" in params and "datos:" in params
    from widgets.brief import for_prompt
    rendered = for_prompt({"mensajeria"}, ["mensajeria"], query="", stats=None)
    assert "Widgets del canvas" in rendered and "datos:" in rendered, \
        "the names the tool now cites must be the ones the resources block really prints"


def test_mensajeria_open_declares_name_as_its_primary_key():
    """widget_data's `item` convention lands a natural reference in the action's FIRST payload key
    (V2-467). For a voice open, that primary is the NAME."""
    from nucleo.flash.widget_data_turn import _primera_clave
    assert _primera_clave("mensajeria", "open") == "name"


# ── The execution guard that was undoing the model's correct choice ─────────────────────────────────────────

def test_a_show_verb_over_an_inside_element_is_not_a_pure_widget_show():
    """The second half of the incident, and the one the prompt fix cannot reach on its own: the voice rail
    rewrites EVERY `is_pure_show_request` into [[show:widget]], and «abre el mensaje de Francisco» is one
    (show verb, no change verb). So the correct `open {name:'Francisco'}` became a re-show of a card that
    was already on screen. The object of the verb is what tells them apart."""
    assert router.is_pure_show_request("abre el mensaje de Francisco"), \
        "the older guard still classifies it as a pure show — that is precisely why the second one is needed"
    assert router.show_object_is_the_widget("abre la mensajería", "mensajeria")
    assert router.show_object_is_the_widget("enséñame la mensajería, por favor", "mensajeria")
    assert router.show_object_is_the_widget("abre el whatsapp", "mensajeria")
    assert not router.show_object_is_the_widget("abre el mensaje de Francisco", "mensajeria")
    assert not router.show_object_is_the_widget("ábreme el chat de Jose Vicente", "mensajeria")
    assert not router.show_object_is_the_widget("muéstrame la lista principal", "mensajeria")


def test_the_original_hallucination_still_lands_on_show():
    """The guard exists because «abre la agenda» once executed an invented `add_meeting` («Reunión con Axa
    Seguros»). Naming nothing but the widget must keep going to the card, and an unreadable catalog must
    fail CLOSED — the invented data-op is worse than a show that does nothing."""
    assert router.show_object_is_the_widget("abre la agenda", "agenda")
    assert router.show_object_is_the_widget("ponme en pantalla la agenda", "agenda")
    assert router.show_object_is_the_widget("abre la agenda", "widget-que-no-existe")


def test_the_probe_channel_mirrors_the_pure_show_guard():
    """The probe reported `widget_data open {name:'Francisco'}` for the very sentence the voice rail turned
    into a bare show: it mirrors several provider guards but had never mirrored this one, so the test
    channel gave a FALSE GREEN on the defect it was being used to diagnose."""
    src = (ENGINE / "nucleo" / "flash" / "probe.py").read_text(encoding="utf-8")
    assert "show_object_is_the_widget" in src and "is_pure_show_request" in src, \
        "a guard that only one of the two rails carries makes the probe report a decision the product never takes"
