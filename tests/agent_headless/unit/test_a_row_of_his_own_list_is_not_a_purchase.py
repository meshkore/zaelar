#
# test_a_row_of_his_own_list_is_not_a_purchase.py — V2-748.
#
# MEASURED LIVE, session 48e85cd5 (2026-09-21). Four turns of ordinary agenda work, and this is what happened
# on the two that wrote:
#
#   «Y ahora añade una nueva tarea, que sea comprar el pan.»
#       -> `agenda:add_task` DISPATCHED, arbiter «✅ permitiría · payload-in-turn», the row was written
#       -> and 0.0 s later: «🛑 orden irreversible sin escalar → tarea», a Brain Worker, a durable task
#          named «Comprar el pan», and out loud: «Esto mueve dinero (…) no hago ningún cargo sin tu OK».
#   «Borra la tarea. Cuatro de compra del pan.»
#       -> same gate, same canned money question, a second task named «Borrar tarea de compra del pan».
#   «Sí.»
#       -> the confirm-gate released the errand, `errand_kind` called it kind="web", and the BROWSER card
#          opened, titled «Comprar el pan», label «Buscando en la web…».
#
# He asked to delete a row of his own list and the product went shopping for bread on the internet.
#
# TWO CAUSES, and each of them is enough on its own, so both are pinned here:
#
#   1 · `danger.is_dangerous` read the ROW'S TITLE as the order. «comprar», «compra» sit bare in
#       `_DANGER_RE`, and the title of an agenda task is arbitrary text the operator dictates. Since
#       `moves_money` runs the same subtraction chain, the same misread then sent the errand to a browser.
#   2 · the voice backstop fired even though the turn had ALREADY done the work through the widget. A gate
#       that parks what has no funnel (`danger.py` says exactly that next to `_DESTROY_OBJECT_RE`) was
#       overruling the funnel.
#
# The half that is wider than the incident: EVERY sentence about «la compra» — the shopping list, the
# widget's own worked example — was a money-moving web errand. «Hazme una lista de la compra» opened a
# browser.
#
# Run: .venv/bin/pytest tests/agent_headless/unit/test_a_row_of_his_own_list_is_not_a_purchase.py
#
from __future__ import annotations

import ast
import pathlib

import pytest

from nucleo import danger, errand_kind
from nucleo.flash import router_guards

ENGINE = pathlib.Path(__file__).resolve().parents[3]

# His two sentences, verbatim from the session's `transcript` events.
_HIS_TURNS = [
    "Y ahora añade una nueva tarea, que sea comprar el pan.",
    "Borra la tarea. Cuatro de compra del pan.",
]

# ONE natural order per declared action of the agenda card — the operator's own register, not the manifest's
# wording. This is the «todas las órdenes posibles» half he asked for: the point is not that each one routes
# to its action (that is the model's job and it is measured elsewhere), it is that NOT ONE of the thirty ways
# to speak to his own agenda is read as an irreversible order, a charge, or work for a browser.
_AGENDA_ORDERS = {
    "add_meeting": "apúntame una reunión con Iván el jueves a las diez",
    "set_reminder": "ponme un aviso media hora antes de la reunión del jueves",
    "dedupe_meetings": "quita las reuniones repetidas del jueves",
    "cancel_meeting": "cancela la reunión con Iván del jueves",
    "done": "marca como hecha la tarea dos de la compra",
    "drop": "descarta la tarea tres",
    "snooze": "pospón la tarea dos para mañana",
    "not_now": "esa tarea ahora no",
    "drop_project": "abandona el proyecto de la obra",
    "clear_all": "vacía la agenda entera",
    "clear_range": "borra las citas de esta semana",
    "show_day": "enséñame el mes",
    "add_task": "añade una nueva tarea que sea comprar el pan",
    "move_meeting": "mueve la reunión con Iván al viernes",
    "update_meeting": "cambia el sitio de la reunión del jueves a la oficina",
    "invite": "invita a Iván a la reunión del jueves",
    "accept_proposal": "acepta la propuesta de cita",
    "decline_proposal": "rechaza la propuesta de cita",
    "rsvp_meeting": "confirma que voy a la reunión del jueves",
    "connect": "conecta mi calendario de Google",
    "disconnect": "desconecta el calendario de Google",
    "set_default_calendar": "usa mi calendario del trabajo por defecto",
    "update_task": "modifica la tarea número tres y ponle crear la cuenta nueva",
    "delete_task": "borra la tarea cuatro de compra del pan",
    "add_list": "hazme una lista de la compra",
    "rename_list": "llama Obra a la lista dos",
    "clear_list": "vacía la lista de la compra",
    "delete_list": "borra la lista de la compra",
    "show_tasks": "ábreme las tareas de la lista de la obra",
    "restore": "restáuralo, me he equivocado",
}

# The other half, and the reason the fix is a SUBTRACTION and not a loosened pattern: a false negative here
# costs money. Every one of these must keep stopping — the last three are the ones the new drop could
# plausibly have eaten, and they are the reason it clips at a bare «y» and why «compra» is only excused
# after «de».
_STILL_STOPS = [
    "Paga la factura de la luz",
    "Compra el monitor Dell S2722QC",
    "cómprame el monitor",
    "¿puedes pagarla antes del día 5?",
    "Renueva mi cuota del gimnasio de este mes",
    "cancela mi suscripción a Netflix",
    "borra la cuenta",
    "borra mi cuenta de Spotify",
    "transfiere 500 euros a la cuenta de Iván",
    "pon la lista de la compra y paga la factura de la luz",
    "añade una tarea y paga la factura",
    "confirma la compra",
    "finalizar compra",
]


# ── the two turns he actually said ───────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("turn", _HIS_TURNS)
def test_his_own_turn_is_not_an_irreversible_order(turn):
    assert danger.is_dangerous(turn) is False, turn


@pytest.mark.parametrize("turn", _HIS_TURNS)
def test_his_own_turn_does_not_move_money(turn):
    assert danger.moves_money(turn) is False, turn


@pytest.mark.parametrize("turn", _HIS_TURNS)
def test_his_own_turn_does_not_earn_a_browser(turn):
    """The card he SAW. `errand_kind` reads `money_work_needs_a_browser`, which reads `moves_money`."""
    assert router_guards.money_work_needs_a_browser(turn) is False, turn
    assert errand_kind.classify_kind(turn) != "web", turn


# ── and none of the thirty ways to speak to the agenda ───────────────────────────────────────────────────

@pytest.mark.parametrize("action,order", sorted(_AGENDA_ORDERS.items()))
def test_no_agenda_order_is_read_as_a_purchase(action, order):
    assert danger.is_dangerous(order) is False, f"{action}: {order}"
    assert danger.moves_money(order) is False, f"{action}: {order}"
    assert router_guards.money_work_needs_a_browser(order) is False, f"{action}: {order}"
    assert errand_kind.classify_kind(order) != "web", f"{action}: {order}"


def test_the_corpus_covers_every_action_the_card_declares():
    """A corpus that quietly stops covering the card is a corpus that stops measuring it. Declared actions
    only grow, so this is a floor: a new action must arrive with the sentence that orders it."""
    import json
    man = json.loads((ENGINE / "widgets" / "agenda" / "manifest.json").read_text(encoding="utf-8"))
    declared = set(man.get("actions") or {})
    missing = sorted(declared - set(_AGENDA_ORDERS))
    assert not missing, f"declared with no sentence in the corpus: {missing}"


# ── nothing that costs money was loosened ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("order", _STILL_STOPS)
def test_an_order_that_spends_still_stops(order):
    assert danger.is_dangerous(order) is True, order


def test_the_drop_stops_at_a_bare_conjunction():
    """«pon la lista de la compra Y paga la factura» is one sentence with two orders in it. The agenda drop
    clips at the `y` so the second one survives — the reminder clip, which does not, would have eaten it."""
    assert "paga" in danger._drop_agenda_items("pon la lista de la compra y paga la factura")


def test_compra_is_only_excused_after_de():
    """«de compra» / «de la compra» is the noun. «la compra» on its own is what a checkout says."""
    assert "compra" not in danger._drop_agenda_items("la tarea cuatro de compra del pan")
    assert "compra" in danger._drop_agenda_items("confirma la compra")


# ── the WIRING: the backstop cannot overrule a dispatched data-op ────────────────────────────────────────

def _backstop_condition() -> str:
    """The source of the `if` that guards the `is_dangerous` backstop in the voice provider.

    Read from the AST rather than by matching text near a marker: the first version of this test searched
    the 500 characters before the emit and matched the COMMENT that describes the fix, which is a test that
    passes because the explanation is still there after the code is gone."""
    src = (ENGINE / "voice" / "engine" / "llm" / "providers" / "nucleo.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if not isinstance(node, ast.If):
            continue
        body = ast.unparse(ast.Module(body=node.body, type_ignores=[]))
        if "is_dangerous" in body and "orden irreversible" in body:
            return ast.unparse(node.test)
    raise AssertionError("the irreversible backstop is no longer an `if` in providers/nucleo.py")


def test_the_backstop_does_not_fire_when_the_turn_already_wrote_through_the_widget():
    """`data_done` is set the moment a FAST data-op is dispatched. The measured turn had it True and the
    backstop escalated anyway — so it is the flag, not the wording of `danger.py`, that has to be read."""
    assert "data_done" in _backstop_condition()


def test_the_backstop_still_defers_to_the_three_it_always_deferred_to():
    """A guard is widened by deleting the wrong term as easily as by adding one."""
    cond = _backstop_condition()
    for term in ("escalate_req", "worker_acted", "confirm_state"):
        assert term in cond, f"the backstop stopped reading {term}"
