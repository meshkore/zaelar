#
# test_a_link_request_is_not_a_charge.py — 2026-09-29, session 81095d8d.
#
# The operator typed «i want to buy Through the Moon (2020), gime the amazon link». Three escalations followed
# and the money gate parked EVERY one of them with «this one moves money, shall I go on?»:
#
#     «Open amazon.es … leave it at the homepage. Do not search for or buy anything yet.»        → parked
#     «Find the Amazon listing where Richard can BUY the book … Do NOT make any purchase.»       → parked
#     «i want to buy Through the Moon (2020), gime the amazon link»                             → parked
#
# The first two are the fast brain's rewrite, and the words that tripped the gate are the ones it added to say
# the OPPOSITE. The third is his, and its order is «give me the link». A verb under a negation is not an order,
# and a first-person wish next to a lookup order is not one either. Two SUBTRACTIONS in `danger.py`, per its
# house rule — nothing added to the verb lists, and every real charge below still parks.
#
# Run: .venv/bin/pytest tests/agent_headless/unit/test_a_link_request_is_not_a_charge.py
#
import pytest

from nucleo import danger

# The three escalations of the session, verbatim.
REWRITE_HOMEPAGE = ('Open amazon.es in a real browser for Richard and show it on screen. He just said "amazon.es" '
                    "with no further instruction — open the site (Spanish Amazon storefront) and leave it at the "
                    "homepage, ready for whatever he wants to do next. Do not search for or buy anything yet.")
REWRITE_LISTING = ('Find the Amazon listing where Richard can BUY the book "Through the Moon (2020)" — and give him '
                   "the direct product link. He wants the URL of the product page where he can buy it, not a "
                   "confirmation, not a summary. Report the direct Amazon product link plus title, price and "
                   "format. Do NOT make any purchase: just locate and report the link.")
HIS_WORDS = "i want to buy Through the Moon (2020), gime the amazon link"


@pytest.mark.parametrize("req", [
    REWRITE_HOMEPAGE, REWRITE_LISTING, HIS_WORDS,
    "quiero comprar el libro Through the Moon, dame el enlace de amazon",
    "quiero comprar una freidora de aire, búscame la más barata que llegue a España",
    "no pagues la factura sin avisarme",
    "find the cheapest original edition I can buy in Spain and tell me the delivery date",
    "I'd like to buy a 27 inch monitor — where is it cheapest?",
])
def test_a_request_for_a_link_or_a_price_is_not_a_charge(req):
    assert danger.is_dangerous(req) is False, req


@pytest.mark.parametrize("req", [
    "buy the book Through the Moon on amazon",
    "quiero comprar el libro Through the Moon",           # a bare wish with no lookup order keeps its imperative
    "paga la factura de la luz",
    "compra el libro y no pagues más de 20 euros",        # a negated cap does not disarm the order beside it
    "transfiere 500 euros a la cuenta de Iván",
    "renuévame la cuota del gimnasio",
    "ve a la tienda para comprar leche",
])
def test_a_real_charge_still_parks(req):
    assert danger.is_dangerous(req) is True, req


def test_the_negation_is_dropped_to_the_end_of_its_sentence_only():
    """«Do not buy anything yet. Then pay the invoice.» — the second sentence is a live order."""
    assert danger.is_dangerous("Do not buy anything yet. Then pay the invoice.") is True


def test_the_wish_is_only_dropped_when_a_lookup_order_is_actually_there():
    assert danger._drop_stated_wish("quiero comprar el libro") == "quiero comprar el libro"
    assert "comprar" not in danger._drop_stated_wish("quiero comprar el libro, dame el enlace")


def test_moves_money_reads_the_same_subtractions():
    """`confirm_line()` and the browser-need guard read `moves_money`; a link request must not be «money» there
    either, or the brain is told it promised to state an amount it never promised."""
    assert danger.moves_money(REWRITE_LISTING) is False
    assert danger.moves_money(HIS_WORDS) is False
    assert danger.moves_money("paga la factura de la luz") is True


def test_the_two_drops_are_wired_into_the_gate():
    """Disarm guard: with either drop turned into a no-op the session's sentences park again."""
    import importlib
    for name in ("_drop_negated_acts", "_drop_stated_wish"):
        original = getattr(danger, name)
        setattr(danger, name, lambda order: order)
        try:
            tripped = danger.is_dangerous(REWRITE_LISTING if name == "_drop_negated_acts" else HIS_WORDS)
        finally:
            setattr(danger, name, original)
        assert tripped is True, f"{name} is not what the gate reads"
    importlib.reload(danger)
    assert danger.is_dangerous(HIS_WORDS) is False
