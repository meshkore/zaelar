"""V2-132 — a promise whose request was made a turn or two back.

`find-theatre-tickets__es` described the task across TWO turns: «consígueme dos entradas para el musical de El
Rey León» and then, after zaelar correctly asked for the missing detail, «este sábado, la sesión de tarde». The
promise («dame un momento que lo miro») landed on the second one, whose text on its own describes no task — so
the promise backstop, which only ever looked at THIS turn, could not fire. Eight turns of narrating a search
that had never started, with `signals: empty` in the mechanism report.

Two independent gaps, both measured on the transcript before touching anything:
  · `_PROMISE_RE` did not know «me pongo A», «estoy con ello», «sigo con ello» — the plainest ways to say it.
  · buying tickets had no category in the site catalog, so the task classified as `generic`: a worker with NO
    browser, which is why the `widget` signal could not possibly fire.
"""
import pytest

from nucleo.flash import router_guards as g
from nucleo.flash import site_catalog as sc
from nucleo import dispatch


@pytest.mark.parametrize("reply", [
    "Vale, dame un momento que lo miro.",
    "Me pongo a buscarte las dos entradas para El Rey León en Madrid este sábado.",
    "Todavía estoy con ello. La búsqueda de entradas lleva su tiempo.",
    "Vale, tranquilo. Sigo con ello y te digo cuando tenga algo.",
    "Perfecto, te aviso en cuanto tenga novedades.",
])
def test_the_plainest_promises_are_recognised_as_promises(reply):
    assert g.promises_action(reply) is True


def test_the_goal_is_recovered_from_the_window_when_this_turn_has_none():
    window = [
        {"role": "user", "content": "Consígueme dos entradas para el musical de El Rey León en Madrid para el sábado."},
        {"role": "assistant", "content": "¿Qué sábado? ¿Qué sesión prefieres? ¿Presupuesto por entrada?"},
    ]
    goal = g.escalate_goal_from_window(window, "Este sábado, la sesión de tarde si hay. Dos entradas en zona media.")
    assert "El Rey León" in goal          # the request itself
    assert "sesión de tarde" in goal      # and the detail that completes it


def test_plain_small_talk_recovers_no_goal():
    """The resolver must come back empty on a conversation that describes no task — it gates an ESCALATION."""
    window = [{"role": "user", "content": "hola, qué tal"}, {"role": "assistant", "content": "bien, ¿y tú?"}]
    assert g.escalate_goal_from_window(window, "vale, gracias") == ""


def test_this_turns_own_request_still_wins():
    window = [{"role": "user", "content": "Consígueme dos entradas para el musical de El Rey León."}]
    assert g.escalate_goal_from_window(window, "busca coches de segunda mano en coches.net") == \
        "busca coches de segunda mano en coches.net"


@pytest.mark.parametrize("text", [
    "Consígueme dos entradas para el musical de El Rey León en Madrid para el sábado.",
    "busca entradas para el concierto del sábado",
    "compra dos entradas para el teatro",
    "get me two tickets for the show on Saturday",
])
def test_buying_tickets_needs_a_browser(text):
    assert sc.category_of(text) == "event_tickets"
    assert sc.category_of(text) in sc.TRANSACTIONAL_CATEGORIES
    assert dispatch._classify_kind(text) == "web"
    assert g.looks_like_escalate_task(text) is True


@pytest.mark.parametrize("text", [
    "de primero pedimos entradas para compartir",   # a starter on a menu
    "guárdame el ticket de la compra",              # a receipt
])
def test_the_other_meanings_of_entrada_and_ticket_stay_out(text):
    assert sc.category_of(text) is None


def test_the_escalate_guard_reuses_the_catalog_instead_of_a_second_verb_list():
    """The `kind` classifier and this guard decide the same thing (does this need a browser?) — two lists is
    how they end up disagreeing, which is exactly what this case measured."""
    for text in ["reserva mesa en Casa Lucio esta noche",
                 "resérvame una noche de hotel en Burgos el 20 de septiembre",
                 "consígueme dos entradas para el musical del sábado"]:
        assert g.looks_like_escalate_task(text) is True
        assert dispatch._classify_kind(text) == "web"
