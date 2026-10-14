"""search/fragment_words.py — the SHAPES of a page's own chrome read as a row (V2-782 T3.3). Data only, ES + EN.

Read by `search/fragment_fit.py`. Measured 2026-10-14, search-buy-washing-machine US: three browser extractions on an
appliance store landed «Washer Capacity (cu. ft.) 45 to Up», «Minimum Price», «Less than $25», «Dismiss 45 cu ft
and up», «Contact Us», «Shop by Brand» and «ENERGY STAR Certified and 4.0…» as rows. Each is a facet, a filter
or a navigation label: what a page says ABOUT its listing, never one thing on sale. Matched over accent-free
lowercase titles (`asked.norm`).
"""
from __future__ import annotations

#: A whole title that is a navigation or filter label.
WHOLE = (
    r"contact us|contacto|contactanos|shop by \w+(?: \w+)?|comprar por \w+|minimum price|maximum price|precio minimo|"
    r"precio maximo|price range|rango de precios?|(?:less|more) than \$?\d[\d.,]*|(?:menos|mas) de \d[\d.,]*\s?(?:€|eur\w*)?|"
    r"under \$?\d[\d.,]*|over \$?\d[\d.,]*|\$?\d[\d.,]* (?:and|&) (?:up|above|under)|see all|view all|ver todo|"
    r"ver todos|show (?:more|less|all)|ver mas|mostrar mas|load more|cargar mas|next|siguiente|previous|anterior|"
    r"home|inicio|sign in|iniciar sesion|cart|cesta|carrito|menu|categories|categorias|brands?|marcas?|help|ayuda|"
    r"store locator|find a store|tiendas|locations|filters?|filtros?|sort|ordenar|clear(?: all)?|borrar(?: todo)?|"
    r"apply|aplicar|reset|done|ok|close|cerrar|compare|comparar|deals|ofertas|new arrivals|novedades"
)
#: A title that STARTS as a control or a facet header.
PREFIX = (
    r"sort by|ordenar por|filter by|filtrar por|refine by|dismiss|remove filter|quitar filtro|clear filters?|"
    r"borrar filtros?|show more|ver mas|results? for|resultados? (?:para|de la busqueda)|showing \d|mostrando \d|"
    r"\d[\d.,]* (?:results|resultados|items|articulos|productos|products)\b|page \d|pagina \d"
)
#: A facet anywhere in the title: a parenthesised unit header, an open range, a dangling certification list.
INSIDE = (
    r"\bresults? for\b|\bresultados (?:para|de la busqueda)\b",
    r"\((?:cu\.? ?ft\.?|in\.?|inches|lbs?\.?|kg|cm|mm|pulgadas|w|v|hz)\)",
    r"\b\d[\d.,]*(?:\s+[a-z.()]+){0,3}\s+(?:to|a)\s+(?:up|more|max|mas)\b|\b\d[\d.,]*\s*[-–]\s*(?:up|more|max)\b",
    r"\b(?:and|y|&) (?:up|above|mas|superior)\s*$",
    r"\b(?:certified|certificad[oa]s?|rated|compatible) (?:and|or|y|o)\b(?!\s+\w+\s+\w)",
)
