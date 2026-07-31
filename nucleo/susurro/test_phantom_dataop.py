"""Tests de la señal de fricción `phantom_dataop` (V2-078): el ESPEJO de risky_decision — el rápido CHARLÓ (cero
tools) pero su respuesta CLAMÓ una acción sobre un widget nombrado con acciones declaradas → data-op fantasma que
Susurro re-rutea off-hot-path. Detección determinista de 3 capas (nada actuó · clama acción · resuelve widget)."""
import pytest

from nucleo.susurro import friction


def test_claims_action_positive():
    assert friction.claims_action("Va en ello, ya la estoy reservando y actualizando la agenda, sigo con ello")
    assert friction.claims_action("Hecho, te la he añadido")
    assert friction.claims_action("lo apunto en la agenda")
    assert friction.claims_action("Done, I've added it to your agenda")


def test_claims_action_negative():
    assert not friction.claims_action("Claro, ¿de qué quieres hablar?")
    assert not friction.claims_action("No estoy seguro de a qué te refieres")
    assert not friction.claims_action("")


def test_nothing_acted_probe_shape():
    assert friction._nothing_acted({"action": "chat", "tool_calls": [], "tags": []})
    assert not friction._nothing_acted({"action": "chat", "tool_calls": ["widget_data"], "tags": []})
    assert not friction._nothing_acted({"action": "widget_data", "tool_calls": [], "tags": []})


def test_nothing_acted_provider_shape():
    assert friction._nothing_acted({"escalated": False, "widget_acted": False, "data_done": False})
    assert not friction._nothing_acted({"escalated": False, "widget_acted": True})
    assert not friction._nothing_acted({"data_done": True})


@pytest.fixture
def widget_ctx(monkeypatch):
    """Simula que 'la agenda' resuelve a un widget con acciones declaradas, sin tocar la BD ni el catálogo real."""
    from memory import api as memapi
    from widgets import runtime
    monkeypatch.setattr(memapi, "state", lambda: {"open_widgets": [], "recent_widgets": []})
    monkeypatch.setattr(runtime, "identify",
                        lambda q, open_ids=None, recent_ids=None: {"match": "agenda"} if "agenda" in q.lower() else {"match": None})
    monkeypatch.setattr(runtime, "get",
                        lambda wid: {"id": "agenda", "actions": {"add_meeting": {"desc": "añade una cita"}}} if wid == "agenda" else None)


def test_phantom_fires_on_confabulated_dataop(widget_ctx):
    dec = {"action": "chat", "tool_calls": [], "tags": [],
           "reply": "Va en ello, ya la estoy añadiendo a la agenda, sigo con ello"}
    assert friction.phantom_dataop("Añade una cita mañana a las cinco en la agenda", dec)


def test_phantom_silent_when_acted(widget_ctx):
    dec = {"action": "widget_data", "tool_calls": ["widget_data"], "tags": [], "reply": "Hecho, te la añado"}
    assert not friction.phantom_dataop("Añade una cita mañana a las cinco en la agenda", dec)


def test_phantom_silent_without_claim(widget_ctx):
    dec = {"action": "chat", "tool_calls": [], "tags": [], "reply": "¿Para qué día quieres la cita?"}
    assert not friction.phantom_dataop("Añade una cita mañana en la agenda", dec)


def test_phantom_silent_without_widget(widget_ctx):
    # "recuérdame comprar pan" no nombra un widget → no es data-op fantasma (recordatorio legítimo sin tool).
    dec = {"action": "chat", "tool_calls": [], "tags": [], "reply": "Vale, lo apunto"}
    assert not friction.phantom_dataop("recuérdame comprar pan mañana", dec)


def test_phantom_silent_on_trivial_turn(widget_ctx):
    dec = {"action": "chat", "tool_calls": [], "tags": [], "reply": "hecho"}
    assert not friction.phantom_dataop("vale", dec)
