"""His sentence never fills a payload key declared as a list of RECORDS (`show-real-photo-of-a-new-car__es`).

2026-10-14: the verdict backstop filled `imagenes:show {items: «¿Cómo que no has podido? …»}` — `items` is «lista
de {url, thumb, title, …}», and a sentence can never be one. `payload_fill.fillable_key` now declines such a key,
so the rung is not built from his words (the widget's own `show` is filled by `show_images`).
"""
from nucleo.flash import payload_fill as PF


def test_a_list_of_records_is_not_fillable_by_words():
    assert PF.fillable_key("imagenes", "show") == ""
    assert PF.fillable_key("map", "show") == ""


def test_a_plain_text_key_still_is():
    assert PF.fillable_key("youtube", "search") == "query"
