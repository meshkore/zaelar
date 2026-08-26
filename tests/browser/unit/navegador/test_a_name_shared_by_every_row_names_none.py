"""Nueve filas con el MISMO nombre de plantilla, y el turno las anunció como coches (V2-346).

Medido en vivo el 2026-08-26, `search-buy-used-car__es`, sesión `faadd628` del plató ES. El worker llegó bien a
AutoScout24 —coches.net se cayó y cambió de sitio él solo—, aplicó los filtros y los verificó en la URL (Madrid
200 km, diésel, desde 2016, ≤ 12.000 €, 2.922 coches) y extrajo. Esto es lo que devolvió la extracción, entero:

    {"title": "",                                                    "price": "€ 10.475", "url": ""}
    {"title": "+ Vehículos del profesional (FLEXICAR SAN SEBASTIAN)", "price": "€ 11.990", "url": ""}
    {"title": "+ Vehículos del profesional (AUTO SPORT MORALEJA)",    "price": "€ 11.900", "url": ""}
    {"title": "+ Vehículos del profesional (OCASIONPLUS ARGANDA)",    "price": "€ 11.565", "url": ""}
    … nueve así, y tres con el título en blanco.

`by_identity` contó NUEVE con nombre, porque «+ Vehículos del profesional (FLEXICAR…)» tiene letras. Con eso la
extracción se dio por buena, las filas entraron en la hoja y el turno le dijo al operador, literal: «en
OcasionPlus Arganda hay uno por 11.565 euros». El tester —una persona— contestó lo que contestaría cualquiera:
«¿Y qué coches son exactamente? No me has dicho ni marca ni modelo ni el año ni los kilómetros». No son coches:
son el enlace «ver todos los vehículos de este concesionario» que cada tarjeta lleva dentro.

El criterio NO es una lista negra de patrones («vehículos del profesional», «ver más», «patrocinado»): mañana es
otra tienda y otro idioma. Es la regla ESTRUCTURAL que este código ya aplica dentro del DOM, en `cardWalk` —«un
dato que nombra a todas no nombra a ninguna»— subida un nivel, de los nodos a las filas: **un nombre que varias
filas comparten como plantilla no es la identidad de ninguna de ellas**. La plantilla se detecta por prefijo
común porque así es como viene (los nueve difieren solo en el paréntesis final), no por igualdad exacta.

Con la guarda puesta, esas nueve dejan de contar como nombradas → `found(0)` → «sin resultados en esta página»,
que es justo la señal que hace al worker cambiar de sitio en vez de anunciar concesionarios como si fueran
coches. Perder una fila legítima es barato; anunciar una falsa se la cree el operador.
"""
from widgets.navegador import act_api

# La extracción CRUDA de la ronda, en su orden exacto (12 filas, todas sin url — venían del respaldo por
# hojas de precio, que el contrato permite: `dom.py` deja pasar filas con nombre y precio sin enlace).
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
    """El lado contrario, y es el que importa: la guarda no puede comerse un listado bueno. Coches reales del
    mismo sitio — comparten la palabra de la categoría, que es lo normal, y NO comparten plantilla."""
    reales = [
        {"title": "BMW Serie 3 320d Touring", "price": "€ 11.900", "url": "https://a.invalid/of/1"},
        {"title": "Volkswagen Golf 1.6 TDI Advance", "price": "€ 10.500", "url": "https://a.invalid/of/2"},
        {"title": "Peugeot 308 1.5 BlueHDi Allure", "price": "€ 9.900", "url": "https://a.invalid/of/3"},
        {"title": "Renault Clio dCi Business", "price": "€ 8.400", "url": "https://a.invalid/of/4"},
    ]
    named, unnamed = act_api.by_identity(reales)
    assert len(named) == 4 and unnamed == []


def test_the_same_product_sold_by_four_shops_is_not_boilerplate():
    """Trampa real de un comparador: cuatro filas con el título IDÉNTICO son cuatro ofertas del mismo producto,
    no plantilla. La plantilla se reconoce porque cada fila añade lo suyo detrás del prefijo compartido; aquí no
    hay «lo suyo», así que el nombre SÍ identifica la cosa (una por vendedor)."""
    ofertas = [{"title": "Apple iPhone 13 128GB", "price": f"€ {p}", "url": f"https://c.invalid/{i}"}
               for i, p in enumerate(("529", "545", "559", "570"))]
    named, _ = act_api.by_identity(ofertas)
    assert len(named) == 4, "títulos iguales = mismo producto en varias tiendas, no cromo de navegación"


def test_two_rows_are_never_a_template():
    """Por debajo de tres filas no se juzga plantilla: dos coches de la misma marca comparten prefijo largo
    («Mercedes-Benz Clase A …») sin que eso los convierta en cromo."""
    dos = [{"title": "Mercedes-Benz Clase A 180 d Style", "price": "€ 11.500", "url": "https://a.invalid/1"},
           {"title": "Mercedes-Benz Clase A 200 d Urban", "price": "€ 11.900", "url": "https://a.invalid/2"}]
    named, _ = act_api.by_identity(dos)
    assert len(named) == 2


def test_a_minority_sharing_a_prefix_does_not_condemn_the_listing():
    """La plantilla es de la PÁGINA, no de tres filas sueltas: si la mayoría de las nombradas trae nombre propio,
    lo que comparten unas pocas es coincidencia y el listado se queda entero. Si no, un listado con tres Ford
    Focus perdería tres coches buenos."""
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
    """El prefijo tiene que ser LARGO para ser plantilla. «Bici » son cinco letras y las comparten tres bicis
    legítimas; una plantilla de navegación arrastra una frase entera."""
    bicis = [{"title": "Bici de montaña Orbea MX 50", "price": "€ 190", "url": "https://b.invalid/1"},
             {"title": "Bici de carretera Trek Domane", "price": "€ 180", "url": "https://b.invalid/2"},
             {"title": "Bici urbana Decathlon Elops", "price": "€ 150", "url": "https://b.invalid/3"}]
    named, _ = act_api.by_identity(bicis)
    assert len(named) == 3
