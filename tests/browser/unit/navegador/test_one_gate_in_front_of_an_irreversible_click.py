"""V2-711 T1 · ONE gate in front of an irreversible click, and it fails CLOSED.

## What was measured (2026-09-16)

This is the last rail before the engine presses a button on a real website in the operator's name.

**One of four routes was gated.** `owner.py::agent_act` reached the mouse and the keyboard by four paths and
only `click` (by `[ref]`) consulted `_DANGER_RE` — `click_at` (vision), `press` and `type --submit` did not.
And `nucleo/nav_cli.py`, the CLI a Brain Worker drives the browser with, RECOMMENDS the ungated one in its
own usage text: «VISION flow (robust for forms)». The recommended path was the unguarded path.

**It judged the LABEL.** Against 30 real button labels, 21 walked through — «Reservar», «Confirmar reserva»,
«Firmar», «Send money», «Donate», «Transferir», «Book now», «Submit order»… The first example in this
repo's own ⭐ operating rule is *«reservar un hotel o un restaurante»*: the flagship case of the product was
exactly the one the last gate did not cover.

**And it failed OPEN**: `if _describe_el raised → _name = "" → click anyway`.

## What is pinned here

That a label the world spells its own way is caught by CONTEXT instead — a submit inside a form asking for a
card, an IBAN, a password, an identity document, a phone; a target on a checkout/booking/order path — that
an unreadable element ASKS rather than proceeds, that the harmless cases still go through untouched, and
that all four routes go through the one gate.
"""
from __future__ import annotations

import ast
import pathlib

import pytest

from widgets.navegador import click_gate as G

ENGINE = pathlib.Path(__file__).resolve().parents[4]


@pytest.fixture
def _knows_him(monkeypatch):
    """The engine HAS his identity — which is the normal case and the one the operator is describing. The
    facts live in `memory/slots.py` as `operator.name` / `.email` / `.phone` / `.address`."""
    from memory import api as _mem
    monkeypatch.setattr(_mem, "state", lambda: {
        "operator.name": "Ricart", "operator.email": "r@example.com",
        "operator.phone": "600000000", "operator.address": "Calle Falsa 1"})
    # …and the PILL surface too: `operator.phone`/`.email`/`.address` have no `state_field`, so a reader
    # that only stubbed `state()` would still hit the real memory DB and the case would pass or fail
    # depending on whose machine ran it. A lab measures the product, not the machine (V2-502).
    monkeypatch.setattr(_mem, "by_slot_prefix", lambda *a, **k: [])
    yield


def _sig(**kw):
    """`signals` is what `JS_SIGNALS` really emits: the space-joined VALUES of each field's autocomplete,
    name, id, type and placeholder — never `key=value` pairs. Writing the fixture the other way made a
    search box look like an identity form, because the literal word «name» was in the haystack.
    """
    base = {"name": "", "role": "button", "isSubmit": True, "inForm": True, "payment": False,
            "identity": False, "method": "get", "targetUrl": "", "pageUrl": "", "signals": "", "fields": 3}
    base.update(kw)
    return base


# ── 1 · the 30 measured labels ──────────────────────────────────────────────────────────────────────────

_LABELS_THAT_WALKED_THROUGH = [
    "Suscribirse", "Contratar", "Transferir", "Enviar transferencia", "Firmar", "Aceptar y continuar",
    "Reservar", "Reservar ahora", "Book now", "Confirm booking", "Submit order", "Sign", "Accept",
    "Donate", "Donar", "Send money", "Añadir al carrito", "Aceptar", "Confirmar", "Confirmar reserva",
    "Solicitar",
]
_LABELS_THE_OLD_RULE_CAUGHT = [
    "Comprar ahora", "Pagar", "Confirmar pedido", "Realizar pedido", "Tramitar pedido", "Finalizar compra",
    "Place order", "Continuar y pagar", "Publicar oferta",
]


@pytest.mark.parametrize("label", _LABELS_THAT_WALKED_THROUGH + _LABELS_THE_OLD_RULE_CAUGHT)
def test_every_measured_button_on_a_payment_form_asks(label):
    """All thirty, once the CONTEXT is read. The nine the label already caught keep being caught by it."""
    ask, why = G.decide(_sig(name=label, signals="cc-number cardnumber text"))
    assert ask is True, f"{label!r} reached the mouse"
    assert why


@pytest.mark.parametrize("label", _LABELS_THAT_WALKED_THROUGH)
def test_a_booking_form_does_NOT_ask_for_permission(label, _knows_him):
    """⚠️ REVERSED ON PURPOSE by V2-712, and this is the whole correction.

    Yesterday this asserted that every one of these labels ASKS on a booking form. The operator read that
    and said, 2026-09-16: «si te digo que reserves mesa en un restaurante, tú ya tienes que saber quién soy
    yo, cuál es mi teléfono, cuál es mi email. Y si no lo sabes, obviamente preguntas. Pero una vez ya lo
    sepas y lo tengas en el estado, no hace falta que preguntes otra vez.»

    He is right, and `principles.md` names the class: a form asking for a name, a phone and an email is the
    NORMAL shape of the order he just gave, so stopping on it is a rail on JUDGEMENT. What survives is the
    mechanism it stood in for — `needs_facts`, tested below — and the rails that are about the CONSEQUENCE:
    payment fields, a checkout URL, an unreadable element.
    """
    ask, _ = G.decide(_sig(name=label, signals="email telefono nombre text"))
    assert ask is False, f"{label!r} still stops a booking he ordered"


def test_but_the_same_form_asks_for_the_DATUM_when_the_engine_does_not_have_it(monkeypatch):
    """«Y si no lo sabes, obviamente preguntas» — and what it asks for is the phone, not a yes/no."""
    from memory import api as _mem
    monkeypatch.setattr(_mem, "state", lambda: {"operator_name": "Ricart", "operator.email": "r@x.com"})
    monkeypatch.setattr(_mem, "by_slot_prefix", lambda *a, **k: [])
    missing = G.needs_facts(_sig(name="Reservar", signals="email telefono nombre text"))
    assert missing == ["operator.phone"], "it must name the ONE thing it lacks, not re-ask for everything"
    assert "teléfono" in G._say_missing(missing)


def test_and_asks_for_NOTHING_once_every_datum_is_on_file(_knows_him):
    assert G.needs_facts(_sig(name="Reservar", signals="email telefono nombre text")) == []


def test_a_postal_address_is_only_required_when_the_form_actually_asks_for_one(monkeypatch):
    """The counterweight to asking for facts: a question for a datum the form never wanted is the same
    friction in a different coat."""
    from memory import api as _mem
    monkeypatch.setattr(_mem, "state", lambda: {"operator.name": "R", "operator.email": "e", "operator.phone": "6"})
    monkeypatch.setattr(_mem, "by_slot_prefix", lambda *a, **k: [])
    assert G.needs_facts(_sig(name="Reservar", signals="email telefono nombre")) == []
    assert G.needs_facts(_sig(name="Comprar", signals="email telefono nombre direccion codigo_postal")) \
        == ["operator.address"]


def test_a_checkout_path_is_enough_on_its_own():
    ask, why = G.decide(_sig(name="Continuar", signals="", targetUrl="https://x.com/checkout/step2"))
    assert ask is True and "compra" in why


def test_the_PAGE_url_counts_too_because_a_confirm_posts_back_to_itself():
    ask, _ = G.decide(_sig(name="Sí", signals="", targetUrl="", pageUrl="https://x.com/booking/confirm"))
    assert ask is True


# ── 2 · it fails CLOSED ─────────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("sig", [None, "not a dict", 42, []])
def test_signals_that_cannot_be_read_ASK(sig):
    """The measured hole: `_describe_el` raised, the name became empty, and the click went ahead."""
    ask, why = G.decide(sig)
    assert ask is True and why, "an element nobody could read used to be clicked anyway"


# ── 3 · the counterweight: ordinary browsing is untouched ───────────────────────────────────────────────

def test_a_plain_search_box_submit_does_not_ask():
    """The whole point of a gate is that it does not fire on the ninety-nine ordinary actions. A search
    form has one text field and no identity in it."""
    ask, _ = G.decide(_sig(name="Buscar", isSubmit=True, inForm=True,
                           signals="q search Buscar", fields=1,
                           pageUrl="https://es.wallapop.com/search"))
    assert ask is False


def test_a_link_that_is_not_in_a_form_does_not_ask():
    ask, _ = G.decide(_sig(name="Siguiente", role="link", isSubmit=False, inForm=False,
                           signals="", pageUrl="https://es.wallapop.com/items"))
    assert ask is False


def test_a_login_form_asks_because_a_password_is_an_identity_field():
    ask, _ = G.decide(_sig(name="Entrar", payment=True, signals="password user"))
    assert ask is True


def test_a_newsletter_box_no_longer_stops_the_turn_either(_knows_him):
    """Yesterday this case was ACCEPTED collateral: «a question he can answer is cheaper than a subscription
    he did not make». Measured against his actual complaint, that trade was wrong — the cost was paid on
    every ordinary form, and the thing being protected was an email signup. The rails that remain are the
    ones about money and about pages that cannot be read."""
    ask, _ = G.decide(_sig(name="Suscribirme", signals="email email"))
    assert ask is False


# ── 4 · the third layer rides along without arming ──────────────────────────────────────────────────────

def test_a_POST_form_is_reported_in_SHADOW_not_stopped():
    sig = _sig(name="Siguiente", method="post", signals="q search", inForm=True, isSubmit=True)
    assert G.decide(sig)[0] is False, "the shadow layer must not stop anything yet"
    assert G.shadow_reason(sig) == "un formulario que envía por POST"


def test_a_click_that_is_ALREADY_stopping_reports_no_shadow():
    """A second reason for a click that is already being asked about measures nothing."""
    assert G.shadow_reason(_sig(name="Pagar", signals="cardnumber")) == ""


def test_a_GET_form_reports_nothing():
    assert G.shadow_reason(_sig(name="Buscar", method="get", signals="q search")) == ""


# ── 5 · all four routes go through the one gate ─────────────────────────────────────────────────────────

def _agent_act_source() -> str:
    src = (ENGINE / "widgets" / "navegador" / "owner.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "agent_act":
            return ast.get_source_segment(src, node) or ""
    raise AssertionError("agent_act not found")


def test_no_route_reaches_the_mouse_or_the_keyboard_without_the_gate():
    """Structural, and it is the half that actually failed: every rule in this file was already true of the
    `click` branch and false of the other three. Counted here so a FIFTH route cannot be added ungated."""
    body = _agent_act_source()
    gated = body.count("_may_act(")
    assert gated >= 4, (
        f"only {gated} calls to the gate in `agent_act`: the four routes that reach the mouse or the "
        f"keyboard (click, click_at, press, --submit) each need one BEFORE they move anything")


def test_the_gate_is_consulted_BEFORE_the_mouse_moves():
    body = _agent_act_source()
    for mover in ("_human_click_handle(", "_human_click_at("):
        assert body.index("_may_act(") < body.index(mover), f"{mover} runs before the gate"


def test_the_vision_route_is_gated_where_the_worker_is_told_to_use_it():
    """`nav_cli.py` recommends the vision flow «robust for forms» — so the vision branch is the one that
    must never be the unguarded one again."""
    body = _agent_act_source()
    branch = body[body.index('if action in ("click_at", "type_at")'):]
    assert "_may_act(" in branch.split("_human_click_at(")[0], "click_at reaches the mouse ungated"
