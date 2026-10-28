"""Ordering the rows of an extracted page: by identity (a name), by amount, without the template boilerplate every
row shares, and without repeated URLs.
Moved out of `act_api.py`; every module name is read through the package (`_f.<name>`), so a patch on `act_api`
still governs every call.
"""

from widgets.navegador import act_api as _f


def by_identity(items) -> tuple:
    """Split the extracted items into (NAMED, UNNAMED), preserving relative order within each half.

    Una fila sin título no es un resultado: es cromo de navegación —un enlace de categoría, un filtro de precio—
    y sale ANTES que las fichas de producto porque ese es el orden del DOM en cualquier listado, no la mala
    suerte de una tienda concreta. Medido en `cheapest-monitor` (2026-08-20 23:44): el navegador sacó seis filas,
    las tres primeras eran «portátiles hasta 799 €», «móviles menos de 200 €» y «tablets hasta 200 €» sin título,
    y las tres siguientes eran monitores REALES a 99 € con enlace de producto y foto. La nota se llenaba con
    `items[:3]` en orden de DOM, así que al cerebro le llegaron las tres primeras y ninguna de las buenas — y el
    turno describió fielmente lo único que tenía: «lo que ha sacado la página son categorías genéricas de
    portátiles, móviles y tablets, no monitores».

    ES UN PARTIDO, NO UNA ORDENACIÓN, y la diferencia importa: no se juzga cuál es mejor —eso es del cerebro, y
    `observability/evidence.py` prohíbe interpretar por buenas razones—, se separa por un hecho estructural,
    tener nombre o no tenerlo. Y NO se tira nada: lo de abajo se cuenta y se dice.

    Tampoco es una lista negra de patrones. Mañana es otra tienda; «tiene nombre» vale para un hotel, un coche,
    un piso en Los Ángeles o una entrada de teatro, y para el listado que nadie ha escrito todavía.
    """
    named, unnamed = [], []
    for it in (items or []):
        if not isinstance(it, dict):
            continue
        (named if str(it.get("title") or "").strip() else unnamed).append(it)
    # V2-346 — Y UN NOMBRE QUE VARIAS FILAS COMPARTEN COMO PLANTILLA NO ES LA IDENTIDAD DE NINGUNA.
    # The `cardWalk` rule («a datum that names every one names none») lifted from nodes to rows.
    # See `_boilerplate_prefix`. Degraded rows join the unnamed group: they are counted and reported.
    if named:
        _tpl = _f._boilerplate_prefix([str(it.get("title") or "").strip() for it in named])
        if _tpl:
            _keep, _cromo = [], []
            for it in named:
                t = str(it.get("title") or "").strip()
                (_cromo if t.startswith(_tpl) and len(t) > len(_tpl) else _keep).append(it)
            named, unnamed = _keep, unnamed + _cromo
    # V2-375 — y la MISMA regla por el otro extremo: una COLETILLA que llevan todas. Medido en
    # `weekend-plan-barcelona__es` (2026-08-27): los DIECISÉIS candidatos de la hoja acababan en
    # «- Actividad relacionada», así que el operador leía dieciséis veces la etiqueta del módulo de la página
    # en vez de dieciséis planes. Tratamiento DISTINTO al del prefijo, y la diferencia es lo que decide: con
    # el prefijo compartido la fila se queda SIN identidad y se degrada (V2-346); aquí la identidad está
    # entera delante —«Vía Ferrata la Cala del Molí (Sant Feliu de Guíxols)»— y lo que sobra es el rabo. Así
    # que se RECORTA y la fila se queda: degradarla tiraría dieciséis hallazgos buenos.
    if named:
        _cola = _f._boilerplate_suffix([str(it.get("title") or "").strip() for it in named])
        if _cola:
            for it in named:
                t = str(it.get("title") or "").strip()
                if t.endswith(_cola) and len(t) > len(_cola):
                    it["title"] = t[: -len(_cola)].rstrip(" -–—·|,;:")
    return named, unnamed


def _boilerplate_suffix(titles: list) -> str:
    """The suffix shared by at least HALF the titles (and never fewer than three), or «» if there is none.

    Gemela de `_boilerplate_prefix` y con sus mismos dos frenos —longitud mínima y mitad de las filas— por las
    mismas razones: «Kit » lo comparten tres cámaras legítimas, y tres filas sueltas no hacen una plantilla.

    Se implementa dándole la vuelta a las cadenas y reutilizando el mismo buscador: un segundo algoritmo que
    haga lo mismo por el otro lado es un segundo sitio donde los umbrales se separan.
    """
    return _f._boilerplate_prefix([t[::-1] for t in titles if t])[::-1]


def _boilerplate_prefix(titles: list) -> str:
    """The prefix shared by at least HALF the titles (and never fewer than three), or «» if there is none.

    Se busca por prefijo y no por igualdad porque así es como viene la plantilla: los nueve enlaces de
    concesionario de AutoScout24 difieren solo en el paréntesis final. Y se EXIGE que cada fila añada algo detrás
    —el llamante filtra con `len(t) > len(_tpl)`—, porque cuatro títulos IDÉNTICOS son otra cosa: el mismo
    producto en cuatro tiendas de un comparador, donde el nombre sí identifica la cosa.

    Sobre una lista ordenada, las filas que comparten prefijo quedan juntas, así que el prefijo común de un
    bloque es el de sus dos extremos: basta mirar cada ventana del tamaño del mínimo.
    """
    ts = sorted(t for t in titles if t)
    n = len(ts)
    k = max(_f._TPL_MIN_ROWS, (n + 1) // 2)
    if n < k:
        return ""
    best = ""
    for i in range(0, n - k + 1):
        a, b = ts[i], ts[i + k - 1]
        j = 0
        while j < min(len(a), len(b)) and a[j] == b[j]:
            j += 1
        if j > len(best):
            best = a[:j]
    return best if len(best) >= _f._TPL_MIN_CHARS else ""


def by_amount(items) -> tuple:
    """Split NAMED rows into (rows you can act on, hollow ones), keeping the relative order inside each half.

    Sibling of `by_identity`, one layer deeper and for the same reason. That one asked «does this row have a
    name?»; this one asks «does it carry anything to act on?» — a real amount, or a number to call. A row with a
    name, no amount and no phone is a listing whose price never painted, or one that publishes none: it is not a
    candidate for «un monitor de 27 pulgadas por menos de 150 €», and it must not take one of the three slots the
    note offers.

    Measured on the batch of 2026-08-24 14:10, `search-secondhand-monitor__es`: the browser found ten rows, the
    first four priced `0 €` («Monitores», «Monitor SAMSUNG», «Monitor de Hípica», «Baby monitor») and below them
    two real `Monitor MSI MAG 27" 280Hz` at 100 € — both under the cap, both the right size. `head` took the
    first three in DOM order, so what reached the operator was the three without a price, one of them a
    horse-riding monitor, while the two that answered the errand sat under the cut. Same shape in
    `search-buy-bicycle__es` at 14:40: `Bicicleta Orbea 0 €` ranked third, ahead of bikes at 190/180/150 €.

    A ZERO IS NOT A PRICE HERE and that is the whole test: any digit other than zero counts as an amount, which
    needs no locale and survives the decimal separator this extractor deliberately does not reconstruct
    («169 00 €» → digits `16900` → an amount). It is a PARTITION, not a ranking — nothing is dropped, and the
    hollow rows keep their order and still reach the sheet.

    It cannot hurt the class it does not apply to: on a directory of plumbers or barbers no row carries a price,
    so one half comes out empty and the order is exactly what it was. V2-240 stands — a result is a name and a
    way to act on it, never a price — which is why a phone counts as much as an amount.
    """
    withs, hollow = [], []
    for it in (items or []):
        if not isinstance(it, dict):
            continue
        digits = "".join(c for c in str(it.get("price") or "") if c.isdigit())
        actionable = any(c != "0" for c in digits) or bool(str(it.get("tel") or "").strip())
        (withs if actionable else hollow).append(it)
    return withs, hollow


def dedupe_by_url(items) -> tuple:
    """The SAME URL is not two findings. Return (deduplicated list, number collapsed).

    Medido por el arnés en la misma ronda del monitor: la segunda nota llevaba tres filas y las tres eran
    `aax-eu-zaz.amazon.es/x/c/JLv…` — la misma url de anuncio repetida. O sea que las repeticiones no solo
    ensucian: OCUPAN el cupo de tres, así que dos de los tres huecos se gastaban en decir lo mismo.

    No es interpretar (que es lo que `observability/evidence.py` prohíbe, con razón): dos filas con la misma
    dirección son la misma página, y enseñar tres veces la misma no informa tres veces. Se conserva la PRIMERA
    aparición —el orden manda hasta que se demuestre lo contrario— y una fila SIN url no se deduplica contra
    nada: la ausencia de dirección no es una identidad compartida.
    """
    out, seen, dropped = [], set(), 0
    for it in (items or []):
        u = str((it or {}).get("url") or "").strip()
        if u and u in seen:
            dropped += 1
            continue
        if u:
            seen.add(u)
        out.append(it)
    return out, dropped
