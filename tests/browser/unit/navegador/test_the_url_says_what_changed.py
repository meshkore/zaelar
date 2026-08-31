"""V2-293 — the worker set one filter, the page applied ANOTHER, and nothing told it so.

Measured in the run on 2026-08-24 13:42, `search-buy-guitar__es`, with the step that served the session driving
blindly (it does not read images, V2-289). The events, in order:

    🧭 navegador | type «guitarra acústica»   → …/search?keywords=guitarra+acústica&order_by=most_relevance
    🧭 navegador | click [29]                 (el filtro de precio)
    🧭 navegador | click [29]
    🧭 navegador | type «150»                 → …/search?**min_sale_price=750**&keywords=guitarra+acústica

It wanted a MAXIMUM price of €150 and the page went to a MINIMUM price of 750. The run ended there with **ZERO extractions**.
And the bridge response hid nothing—the entire URL was present—but a new parameter inside a long line,
between the title and the elements, cannot be seen.

What is added is the DELTA, which is the only thing the worker cannot deduce on its own: it has the current
address, but not the previous one (`nav_cli` is a process per action and remembers nothing).

**Generic by construction**, which is what distinguishes it from adapting to the case: whatever parameters exist
are compared, without knowing which site they belong to or what they mean. It works equally for a price filter, a
size filter, a sort order, or a next page—and for the listing that no one has written yet. And it does NOT judge
whether the change is the one requested: the worker knows that, since it is the one that made the request. Here,
we state what the page says about itself.
"""
from nucleo import nav_cli
from widgets.navegador.act_api import _with_url_change

_ANTES = "https://es.wallapop.com/search?keywords=guitarra+ac%C3%BAstica&order_by=most_relevance"


def _snap(url):
    return {"url": url, "title": "Wallapop"}


def test_the_measured_case_is_named():
    """THE CASE: it requested a maximum of 150 and the page applied a minimum of 750."""
    got = _with_url_change(_ANTES, _snap(_ANTES.replace("?", "?min_sale_price=750&")))
    assert got["url_change"] == "min_sale_price=750 (nuevo)"


def test_a_changed_value_is_shown_with_both_sides():
    """“the price changed” is not enough: we need the change from and to in order to know whether it is the requested one."""
    got = _with_url_change("https://x/s?max=400", _snap("https://x/s?max=150"))
    assert got["url_change"] == "max: 400 → 150"


def test_a_filter_that_disappeared_is_named_too():
    """Losing a filter changes the results just as much as gaining one, and silently it reads as though it were still set."""
    got = _with_url_change("https://x/s?max=150&q=a", _snap("https://x/s?q=a"))
    assert got["url_change"] == "max ya no está"


def test_an_action_that_changed_nothing_says_nothing():
    """A line that appears on every action stops being read—and most actions do not touch the address."""
    assert "url_change" not in _with_url_change("https://x/s?q=a", _snap("https://x/s?q=a"))


def test_the_first_action_of_a_tab_says_nothing():
    """Without a previous address there is no delta, and “everything is new” would be noise on the first navigation."""
    assert "url_change" not in _with_url_change("", _snap("https://x/s?q=a"))


def test_a_different_page_with_the_same_query_says_nothing():
    """PARAMETERS are compared, not addresses: entering an item's detail page is not changing a filter."""
    assert "url_change" not in _with_url_change("https://x/s?q=a", _snap("https://x/item/123?q=a"))


def test_it_is_not_tied_to_any_site_or_parameter():
    """The operator rule test: change the site and the filter name—does it still hold?"""
    got = _with_url_change("https://otra-tienda.example/buscar?talla=M",
                           _snap("https://otra-tienda.example/buscar?talla=XL&pagina=2"))
    assert "talla: M → XL" in got["url_change"] and "pagina=2 (nuevo)" in got["url_change"]


# ── and the bridge SAYS it, which is half of what is needed (node 4.20 contract) ───────────────────────────
def test_the_bridge_prints_the_delta_next_to_the_url(capsys):
    nav_cli._print_state({"ok": True, "url": "https://x/s?min=750", "title": "W",
                          "url_change": "min=750 (nuevo)", "elements": "[29] Precio"})
    out = capsys.readouterr().out
    assert "CAMBIÓ EN LA DIRECCIÓN: min=750 (nuevo)" in out
    assert out.index("CAMBIÓ EN LA DIRECCIÓN") < out.index("ELEMENTOS"), \
        "el worker lee de arriba abajo: una consecuencia de su acción no puede ir tras la lista de elementos"


def test_the_bridge_says_what_to_do_with_it(capsys):
    """A fact without an outcome is a diagnosis. What was needed was not knowing the URL—it was already there—but
    knowing that the filter that counts is the applied one, not the requested one."""
    nav_cli._print_state({"ok": True, "url": "https://x/s?min=750", "title": "W",
                          "url_change": "min=750 (nuevo)", "elements": ""})
    out = capsys.readouterr().out
    assert "DE VERDAD" in out and "no sigas contando con el que pediste" in out


def test_a_quiet_action_prints_no_extra_line(capsys):
    nav_cli._print_state({"ok": True, "url": "https://x/s?q=a", "title": "W", "elements": "[1] caja"})
    assert "CAMBIÓ EN LA DIRECCIÓN" not in capsys.readouterr().out
