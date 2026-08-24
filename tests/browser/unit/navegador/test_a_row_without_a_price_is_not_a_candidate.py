"""The three rows offered to the operator were the three that had no price (V2-295).

V2-234 fixed the layer above this one: a row with no NAME is navigation chrome, so it does not take a slot in
the note's head. This is the same cut one layer deeper, and the harness measured it on the batch of 2026-08-24
14:10, `search-secondhand-monitor__es`. The person had asked for «un monitor de segunda mano de al menos 27
pulgadas por menos de 150 €». The browser found ten rows; these are the real ones, in their real order:

    1. «Monitores»                                  0 €    /item/monitores-1219299001
    2. «Monitor SAMSUNG»                            0 €    /item/monitor-samsung-1113818432
    3. «Monitor de Hípica»                          0 €    /item/monitor-de-hipica-1279141724
    4. «Baby monitor»                               0 €    /item/baby-monitor-881556901
    5. «Monitor MSI MAG 276CXF 27 LED Curvo 280Hz»  100 €  /item/monitor-msi-mag-276cxf-…
    6. «!LIQUIDACIÓN!Monitor MSI MAG 274CF 240Hz»   100 €  /item/monitor-msi-mag-274cf-…

And this is what the mechanism report recorded as offered (`offered.titles`), verbatim:

    ['Monitores', 'Monitor SAMSUNG', 'Monitor de Hípica']

All four leading rows carry a name, so `by_identity` passes them and the head takes the first three in DOM
order. What reached the operator was three rows with no price — one of them a horse-riding monitor — while the
two that answered the errand exactly (27", under the 150 € cap) sat below the cut. Same shape at 14:40 in
`search-buy-bicycle__es`: «Bicicleta Orbea 0 €» ranked third, ahead of bikes at 190, 180 and 150 €.

The criterion is structural, not a blacklist: a zero is not a price, so any digit other than zero counts as an
amount and no locale or decimal separator has to be guessed. Nothing is discarded — the hollow rows keep their
order behind the rest and still reach the sheet — and the class this does not apply to cannot be hurt by it: on
a directory of plumbers no row carries a price, one half comes out empty, and the order is what it always was.
"""
import pytest

from voice import brain_notes
from widgets.navegador import act_api, tasks

# The round's real extraction, in its exact order.
CRUDO = [
    {"title": "Monitores", "price": "0 €", "url": "https://es.wallapop.com/item/monitores-1219299001"},
    {"title": "Monitor SAMSUNG", "price": "0 €", "url": "https://es.wallapop.com/item/monitor-samsung-1113818432"},
    {"title": "Monitor de Hípica", "price": "0 €", "url": "https://es.wallapop.com/item/monitor-de-hipica-1279141724"},
    {"title": "Baby monitor", "price": "0 €", "url": "https://es.wallapop.com/item/baby-monitor-881556901"},
    {"title": 'Monitor MSI MAG 276CXF 27 LED Curvo 280Hz', "price": "100 €",
     "url": "https://es.wallapop.com/item/monitor-msi-mag-276cxf-27-led-curvo-280hz-1294129451"},
    {"title": "!LIQUIDACIÓN!Monitor MSI MAG 274CF X24 240Hz Nuevo", "price": "100 €",
     "url": "https://es.wallapop.com/item/monitor-msi-mag-274cf-x24-240hz-nuevo-1269583404"},
]

# A directory of services: nobody publishes a price and every row has a number to call (V2-240).
FONTANEROS = [
    {"title": "Fontanería Ruiz", "price": "", "tel": "612 34 56 78", "url": "https://dir.invalid/ruiz"},
    {"title": "Desatascos 24h Madrid", "price": "", "tel": "699 11 22 33", "url": "https://dir.invalid/desatascos"},
    {"title": "Instalaciones Vega", "price": "", "tel": "677 88 99 00", "url": "https://dir.invalid/vega"},
]


@pytest.fixture
def task():
    tid = tasks.create("un monitor de segunda mano de al menos 27 pulgadas por menos de 150€")
    act_api._HANDED.pop(tid, None)
    brain_notes.drain()
    yield tid
    act_api._HANDED.pop(tid, None)
    brain_notes.drain()


def _cabecera(task, items) -> str:
    """The head of the note — the part that names rows, before the standing order."""
    act_api._hand_over(task, items)
    notes = brain_notes.drain()
    assert notes, "no note, nothing to measure"
    return notes[0].split("Nadie más lo sabe")[0]


# ── the measured case ────────────────────────────────────────────────────────────────────────────────────────

def test_the_monitor_that_answers_the_errand_reaches_the_brain(task):
    """The bar the harness set: the operator must be able to hear «MSI MAG 276CXF, 100 €» with its link."""
    c = _cabecera(task, CRUDO)
    assert "276CXF" in c
    assert "100 €" in c
    assert "monitor-msi-mag-276cxf" in c


def test_and_the_row_without_a_price_does_not_take_its_slot(task):
    """The other half, and the one that failed the case: with the four hollow rows in front, what the operator
    was offered was a horse-riding monitor with no price."""
    c = _cabecera(task, CRUDO)
    assert "Monitor de Hípica" not in c
    assert "Baby monitor" not in c


def test_nothing_is_thrown_away(task):
    """A partition, not a filter: the rows with no price stay in the task's results and are counted in the note
    («N filas más»), because losing information in silence is what `observability/evidence.py` forbids."""
    act_api._hand_over(task, CRUDO)
    notes = brain_notes.drain()
    guardado = (tasks.get(task) or {}).get("results", {}).get("items") or []
    titulos = [i.get("title") for i in guardado]
    assert "Monitores" in titulos, "the hollow row must survive, only behind the rest"
    assert "filas más" in notes[0] or "fila más" in notes[0]


def test_a_directory_with_no_prices_keeps_its_order(task):
    """The class this must not touch. Nobody publishes a price, everybody has a phone, so the partition leaves
    one half empty — and the first three offered are still the first three the page gave."""
    c = _cabecera(task, FONTANEROS)
    assert c.index("Fontanería Ruiz") < c.index("Desatascos 24h Madrid") < c.index("Instalaciones Vega")
