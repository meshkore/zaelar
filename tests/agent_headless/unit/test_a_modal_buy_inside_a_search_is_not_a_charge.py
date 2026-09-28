"""«…models the operator can buy» inside a search is not an order to buy (demo pass 31, A1, 2026-09-28).

«find me three 27 inch 4k monitors, under 400 bucks» was composed into a worker request ending «present three
concrete models the operator can buy», the money gate read «buy», and the operator was asked «This one moves money
… I don't put a charge through without your OK» over a search. Inside a lookup, a MODAL buy describes what is
looked for; a bare «buy it» keeps its imperative.
"""
import pytest

from nucleo import danger

_A1 = ("Find three 27-inch 4K monitors priced under $400 (roughly, so up to about $420 is acceptable). Compare real "
       "purchasable options with current prices, and present three concrete models the operator can buy, with "
       "price, retailer and link. Keep it to a short comparable list.")


def test_the_monitor_search_is_not_a_charge():
    assert not danger.is_dangerous(_A1)
    assert not danger.moves_money(_A1)


@pytest.mark.parametrize("order", ["buy the cheapest one", "find a monitor and buy it for me",
                                   "find three models he can buy and then buy the cheapest"])
def test_an_order_to_buy_still_stops(order):
    assert danger.is_dangerous(order)
