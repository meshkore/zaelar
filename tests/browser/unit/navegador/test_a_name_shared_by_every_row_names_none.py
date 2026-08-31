"""Nine rows with the SAME template name, and the run announced them as cars (V2-346).

Measured live on 2026-08-26, `search-buy-used-car__es`, session `faadd628` from the ES set. The worker reached
AutoScout24 successfully —coches.net went down and it switched sites on its own—, applied the filters and verified
them in the URL (Madrid 200 km, diesel, from 2016, ≤ 12,000 €, 2,922 cars) and extracted. This is what the full
extraction returned:

    {"title": "",                                                    "price": "€ 10.475", "url": ""}
    {"title": "+ Vehículos del profesional (FLEXICAR SAN SEBASTIAN)", "price": "€ 11.990", "url": ""}
    {"title": "+ Vehículos del profesional (AUTO SPORT MORALEJA)",    "price": "€ 11.900", "url": ""}
    {"title": "+ Vehículos del profesional (OCASIONPLUS ARGANDA)",    "price": "€ 11.565", "url": ""}
    … nueve así, y tres con el título en blanco.

`by_identity` counted NINE as named, because «+ Vehículos del profesional (FLEXICAR…)» contains letters. As a
result, the extraction was accepted, the rows entered the sheet, and the run told the operator, literally: «there
is one for 11,565 euros at OcasionPlus Arganda». The tester —a person— replied as anyone would:
«And what cars exactly? You haven't told me the make, model, year, or mileage». They are not cars:
they are the «see all vehicles from this dealer» link contained in each card.

The criterion is NOT a blacklist of patterns («vehículos del profesional», «ver más», «patrocinado»): tomorrow it
will be another store and another language. It is the STRUCTURAL rule this code already applies inside the DOM, in
`cardWalk` —«data that names all of them names none of them»— raised one level, from nodes to rows: **a name that
several rows share as a template is not the identity of any of them**. The template is detected by common prefix
because that is how it appears (the nine differ only in the final parenthesis), not by exact equality.

With the guard in place, those nine stop counting as named → `found(0)` → «no results on this page»,
which is exactly the signal that makes the worker switch sites instead of announcing dealers as if they were
cars. Losing a legitimate row is cheap; the operator believes a false announcement.
"""
from widgets.navegador import act_api

# The RAW extraction from the run, in its exact order (12 rows, all without a URL — they came from the fallback by
# price sheets, which the contract allows: `dom.py` lets rows with a name and price but no link through).
CRUDO = [
    {"title": "", "price": "€ 10.475", "tel": "", "url": "", "image": ""},
    {"title": "+ Vehículos del profesional (FLEXICAR SAN SEBASTIAN DE LOS REYES)", "price": "€ 11.990",
     "tel": "", "url": "", "image": ""},
    {"title": "+ Vehículos del profesional (AUTO SPORT MORALEJA)", "price": "€ 11.900",
     "tel": "", "url": "", "image": ""},
    {"title": "+ Vehículos del profesional (OCASIONPLUS ARGANDA)", "price": "€ 11.565",
     "tel": "", "url": "", "image": ""},
    {"title": "+ Vehículos del profesional (RIVERO MOTOR)", "price": "€ 11.990",
     "tel": "", "url": "", "image": ""},
    {"title": "+ Vehículos del profesional (CLICARS MADRID)", "price": "€ 10.490",
     "tel": "", "url": "", "image": ""},
    {"title": "", "price": "€ 9.904", "tel": "", "url": "", "image": ""},
    {"title": "+ Vehículos del profesional (FLEXICAR ARGANDA DEL REY)", "price": "€ 11.990",
     "tel": "", "url": "", "image": ""},
    {"title": "+ Vehículos del profesional (FLEXICAR GETAFE-FUENLABRADA)", "price": "€ 11.990",
     "tel": "", "url": "", "image": ""},
    {"title": "+ Vehículos del profesional (GAMBOA OCASION)", "price": "€ 8.794",
     "tel": "", "url": "", "image": ""},
    {"title": "", "price": "€ 11.908", "tel": "", "url": "", "image": ""},
    {"title": "+ Vehículos del profesional (ROES COCHES DIRECT S.L)", "price": "€ 9.500",
     "tel": "", "url": "", "image": ""},
]


def test_the_dealer_boilerplate_stops_counting_as_nine_cars():
    named, unnamed = act_api.by_identity(CRUDO)
    assert named == [], "nueve enlaces de concesionario contados como coches: es lo que el turno anunció"
    assert len(unnamed) == 12, "no se tira ninguna: se cuentan y se dicen, como las filas sin título"


def test_a_listing_of_real_cars_is_untouched():
    """The opposite case, and the one that matters: the guard must not eat a good listing. Real cars from the
    same site — they share the category word, as is normal, and do NOT share a template."""
    reales = [
        {"title": "BMW Serie 3 320d Touring", "price": "€ 11.900", "url": "https://a.invalid/of/1"},
        {"title": "Volkswagen Golf 1.6 TDI Advance", "price": "€ 10.500", "url": "https://a.invalid/of/2"},
        {"title": "Peugeot 308 1.5 BlueHDi Allure", "price": "€ 9.900", "url": "https://a.invalid/of/3"},
        {"title": "Renault Clio dCi Business", "price": "€ 8.400", "url": "https://a.invalid/of/4"},
    ]
    named, unnamed = act_api.by_identity(reales)
    assert len(named) == 4 and unnamed == []


def test_the_same_product_sold_by_four_shops_is_not_boilerplate():
    """A real comparison-site trap: four rows with the IDENTICAL title are four offers for the same product,
    not a template. The template is recognized because each row adds its own text after the shared prefix; here
    there is no «its own text», so the name DOES identify the item (one per seller)."""
    ofertas = [{"title": "Apple iPhone 13 128GB", "price": f"€ {p}", "url": f"https://c.invalid/{i}"}
               for i, p in enumerate(("529", "545", "559", "570"))]
    named, _ = act_api.by_identity(ofertas)
    assert len(named) == 4, "títulos iguales = mismo producto en varias tiendas, no cromo de navegación"


def test_two_rows_are_never_a_template():
    """Fewer than three rows are not judged to be a template: two cars of the same make share a long prefix
    («Mercedes-Benz Clase A …») without that turning them into chrome."""
    dos = [{"title": "Mercedes-Benz Clase A 180 d Style", "price": "€ 11.500", "url": "https://a.invalid/1"},
           {"title": "Mercedes-Benz Clase A 200 d Urban", "price": "€ 11.900", "url": "https://a.invalid/2"}]
    named, _ = act_api.by_identity(dos)
    assert len(named) == 2


def test_a_minority_sharing_a_prefix_does_not_condemn_the_listing():
    """The template belongs to the PAGE, not to three isolated rows: if most named rows have their own name,
    what a few share is coincidence and the listing remains intact. Otherwise, a listing with three Ford
    Focus cars would lose three good cars."""
    mezcla = [{"title": "Ford Focus 1.5 TDCi Trend", "price": "€ 9.000", "url": "https://a.invalid/1"},
              {"title": "Ford Focus 1.5 TDCi Titanium", "price": "€ 9.500", "url": "https://a.invalid/2"},
              {"title": "Ford Focus 1.5 TDCi ST-Line", "price": "€ 9.900", "url": "https://a.invalid/3"},
              {"title": "Opel Astra 1.6 CDTi", "price": "€ 8.200", "url": "https://a.invalid/4"},
              {"title": "Seat León 1.6 TDI Style", "price": "€ 10.100", "url": "https://a.invalid/5"},
              {"title": "Kia Ceed 1.6 CRDi Drive", "price": "€ 10.900", "url": "https://a.invalid/6"},
              {"title": "Mazda 3 2.2 Skyactiv-D", "price": "€ 11.400", "url": "https://a.invalid/7"}]
    named, _ = act_api.by_identity(mezcla)
    assert len(named) == 7


def test_a_short_shared_prefix_is_not_a_template():
    """The prefix has to be LONG to be a template. «Bici » is five letters and three legitimate bikes share it;
    a navigation template carries along an entire phrase."""
    bicis = [{"title": "Bici de montaña Orbea MX 50", "price": "€ 190", "url": "https://b.invalid/1"},
             {"title": "Bici de carretera Trek Domane", "price": "€ 180", "url": "https://b.invalid/2"},
             {"title": "Bici urbana Decathlon Elops", "price": "€ 150", "url": "https://b.invalid/3"}]
    named, _ = act_api.by_identity(bicis)
    assert len(named) == 3
