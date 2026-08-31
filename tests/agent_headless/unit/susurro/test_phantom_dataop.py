"""Tests for the `phantom_dataop` friction signal (V2-078): the MIRROR of risky_decision — the fast one CHATTED (zero
tools) but its response CLAIMED an action on a named widget with declared actions → phantom data-op that
Susurro reroutes off-hot-path. Deterministic 3-layer detection (nothing acted · claims action · resolves widget)."""
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
    """Simulates that 'la agenda' resolves to a widget with declared actions, without touching the DB or the real catalog."""
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
    # "recuérdame comprar pan" does not name a widget → it is not a phantom data-op (legitimate reminder without a tool).
    dec = {"action": "chat", "tool_calls": [], "tags": [], "reply": "Vale, lo apunto"}
    assert not friction.phantom_dataop("recuérdame comprar pan mañana", dec)


def test_phantom_silent_on_trivial_turn(widget_ctx):
    dec = {"action": "chat", "tool_calls": [], "tags": [], "reply": "hecho"}
    assert not friction.phantom_dataop("vale", dec)
