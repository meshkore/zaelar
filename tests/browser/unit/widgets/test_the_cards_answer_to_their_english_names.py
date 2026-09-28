"""The cards of the demo answer to their names in English too (demo pass 2026-09-28, full24 B3: «nice, close the
pictures» named no card — the viewer's aliases were Spanish only — and the close backstop shut the errand's sheet
instead). Aliases are data, one list for every language the operator may speak."""
import pytest

from widgets import runtime as rt


@pytest.mark.parametrize("said,card", [
    ("nice, close the pictures", "imagenes"), ("close the images", "imagenes"), ("close the gallery", "imagenes"),
    ("close the inbox", "mensajeria"), ("close the messages", "mensajeria"), ("close the calendar", "agenda"),
    ("close the map", "map"), ("close the chart", "markets"), ("close the document", "documento"),
])
def test_the_english_name_finds_the_card(said, card):
    assert rt.identify(said).get("match") == card
