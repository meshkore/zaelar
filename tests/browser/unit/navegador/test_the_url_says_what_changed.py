"""V2-293 — el worker puso un filtro, la página aplicó OTRO, y nada se lo dijo.

Medido en la tanda del 2026-08-24 13:42, `search-buy-guitar__es`, con el escalón que servía la sesión conduciendo
a ciegas (no lee imágenes, V2-289). Los eventos, en orden:

    🧭 navegador | type «guitarra acústica»   → …/search?keywords=guitarra+acústica&order_by=most_relevance
    🧭 navegador | click [29]                 (el filtro de precio)
    🧭 navegador | click [29]
    🧭 navegador | type «150»                 → …/search?**min_sale_price=750**&keywords=guitarra+acústica

Quería precio MÁXIMO 150 € y la página se fue a precio MÍNIMO 750. La ronda acabó ahí con **CERO extracciones**.
Y la respuesta del puente no ocultaba nada —la URL entera venía— pero un parámetro nuevo dentro de una línea
larga, entre el título y los elementos, no se ve.

Lo que se añade es el DELTA, que es lo único que el worker no puede deducir por su cuenta: la dirección de ahora
la tiene, la de antes no (`nav_cli` es un proceso por acción, no recuerda nada).

**Genérico por construcción**, que es lo que lo separa de adaptarse al caso: se comparan los parámetros que haya,
sin saber de qué sitio son ni qué significan. Sirve igual para un filtro de precio, uno de talla, un orden o una
página siguiente — y para el listado que nadie ha escrito todavía. Y NO juzga si el cambio es el que se pedía:
eso lo sabe el worker, que es quien pidió. Aquí se dice lo que la página afirma de sí misma.
"""
from nucleo import nav_cli
from widgets.navegador.act_api import _with_url_change

_ANTES = "https://es.wallapop.com/search?keywords=guitarra+ac%C3%BAstica&order_by=most_relevance"


def _snap(url):
    return {"url": url, "title": "Wallapop"}


def test_the_measured_case_is_named():
    """EL CASO: pidió máximo 150 y la página aplicó mínimo 750."""
    got = _with_url_change(_ANTES, _snap(_ANTES.replace("?", "?min_sale_price=750&")))
    assert got["url_change"] == "min_sale_price=750 (nuevo)"


def test_a_changed_value_is_shown_with_both_sides():
    """«cambió el precio» no sirve: hace falta de qué a qué para saber si es el que se pidió."""
    got = _with_url_change("https://x/s?max=400", _snap("https://x/s?max=150"))
    assert got["url_change"] == "max: 400 → 150"


def test_a_filter_that_disappeared_is_named_too():
    """Perder un filtro cambia los resultados tanto como ganarlo, y en silencio se lee como que sigue puesto."""
    got = _with_url_change("https://x/s?max=150&q=a", _snap("https://x/s?q=a"))
    assert got["url_change"] == "max ya no está"


def test_an_action_that_changed_nothing_says_nothing():
    """Una línea que sale en cada acción deja de leerse — y la mayoría de acciones no tocan la dirección."""
    assert "url_change" not in _with_url_change("https://x/s?q=a", _snap("https://x/s?q=a"))


def test_the_first_action_of_a_tab_says_nothing():
    """Sin dirección anterior no hay delta, y «todo es nuevo» sería ruido en la primera navegación."""
    assert "url_change" not in _with_url_change("", _snap("https://x/s?q=a"))


def test_a_different_page_with_the_same_query_says_nothing():
    """Se comparan PARÁMETROS, no direcciones: entrar en la ficha de un anuncio no es cambiar un filtro."""
    assert "url_change" not in _with_url_change("https://x/s?q=a", _snap("https://x/item/123?q=a"))


def test_it_is_not_tied_to_any_site_or_parameter():
    """La prueba de la norma del operador: cambia el sitio y el nombre del filtro, ¿sigue en pie?"""
    got = _with_url_change("https://otra-tienda.example/buscar?talla=M",
                           _snap("https://otra-tienda.example/buscar?talla=XL&pagina=2"))
    assert "talla: M → XL" in got["url_change"] and "pagina=2 (nuevo)" in got["url_change"]


# ── y el puente lo DICE, que es la mitad que hace falta (contrato del nodo 4.20) ───────────────────────────
def test_the_bridge_prints_the_delta_next_to_the_url(capsys):
    nav_cli._print_state({"ok": True, "url": "https://x/s?min=750", "title": "W",
                          "url_change": "min=750 (nuevo)", "elements": "[29] Precio"})
    out = capsys.readouterr().out
    assert "CAMBIÓ EN LA DIRECCIÓN: min=750 (nuevo)" in out
    assert out.index("CAMBIÓ EN LA DIRECCIÓN") < out.index("ELEMENTOS"), \
        "el worker lee de arriba abajo: una consecuencia de su acción no puede ir tras la lista de elementos"


def test_the_bridge_says_what_to_do_with_it(capsys):
    """Un dato sin salida es un diagnóstico. Lo que hacía falta no era saber la URL —ya venía— sino que el
    filtro que cuenta es el aplicado, no el pedido."""
    nav_cli._print_state({"ok": True, "url": "https://x/s?min=750", "title": "W",
                          "url_change": "min=750 (nuevo)", "elements": ""})
    out = capsys.readouterr().out
    assert "DE VERDAD" in out and "no sigas contando con el que pediste" in out


def test_a_quiet_action_prints_no_extra_line(capsys):
    nav_cli._print_state({"ok": True, "url": "https://x/s?q=a", "title": "W", "elements": "[1] caja"})
    assert "CAMBIÓ EN LA DIRECCIÓN" not in capsys.readouterr().out
