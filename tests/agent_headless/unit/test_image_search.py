"""V2-457 — el parser de resultados de imagen, medido contra un payload REAL grabado.

La forma del payload de Google es la parte frágil de todo esto, así que es la parte que tiene que poder
probarse sin red. El fixture (`fixtures/google_images_ferrari_amalfi.txt`) es un recorte literal de la búsqueda
que originó la iniciativa, grabado el 2026-08-28: si Google cambia su formato, estos casos se ponen rojos aquí y
no en una ronda del plató tres días después.
"""
from __future__ import annotations

import os

from nucleo import image_search

_FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "google_images_ferrari_amalfi.txt")


def _blob() -> str:
    with open(_FIXTURE, encoding="utf-8") as fh:
        return fh.read()


def test_saca_las_imagenes_con_su_procedencia():
    items = image_search.parse_google_images(_blob())
    assert len(items) == 12
    for it in items:
        assert it["url"].startswith("http")
        assert it["thumb"].startswith("http")
        assert it["w"] > 0 and it["h"] > 0


def test_la_fuente_de_cada_foto_viaja_con_ella():
    """El operador pidió ver la FUENTE, y el sitio no se puede deducir de la URL de un CDN.

    `cdn.ferrari.com` sí se parece a Ferrari, pero `hips.hearstapps.com` es Car and Driver y
    `c.encycarpedia.com` es Encycarpedia: adivinar por el host acertaría en unos y mentiría en otros.
    """
    items = image_search.parse_google_images(_blob())
    con_sitio = [it for it in items if it["site"]]
    assert len(con_sitio) >= 10, "casi todas las filas traen sitio en el payload real"
    ferrari = [it for it in items if it["site"] == "www.ferrari.com"]
    assert ferrari, "la búsqueda real devuelve originales del fabricante"
    assert ferrari[0]["page"].startswith("https://www.ferrari.com/")
    assert "Ferrari Amalfi" in ferrari[0]["title"]


def test_un_titulo_con_comillas_escapadas_no_se_corta_a_medias():
    """Una fila real se titula `El Ferrari Amalfi, la nueva \\"Dolce Vita\\"…`.

    Un `[^"]*` se para en la barra invertida y devuelve el título cortado a mitad de palabra, con una barra
    suelta al final — y eso se lee en voz alta. La regla consume los escapes en vez de tropezar con ellos.
    """
    items = image_search.parse_google_images(_blob())
    drivek = [it for it in items if it["site"] == "www.drivek.es"]
    assert drivek, "el payload grabado contiene esa fila"
    t = drivek[0]["title"]
    assert '"Dolce Vita"' in t, t
    assert not t.rstrip().endswith("\\"), f"título cortado en el escape: {t!r}"


def test_no_devuelve_la_misma_foto_dos_veces():
    items = image_search.parse_google_images(_blob())
    urls = [it["url"] for it in items]
    assert len(urls) == len(set(urls))


def test_respeta_cuantas_se_le_piden():
    assert len(image_search.parse_google_images(_blob(), k=3)) == 3
    assert len(image_search.parse_google_images(_blob(), k=1)) == 1


def test_un_blob_que_no_entiende_sale_vacio_y_no_revienta():
    """Total por contrato: el plan B de «no hay fotos» y el de «cambió el formato» es el MISMO.

    Si esto lanzara, un cambio de formato de Google tumbaría el turno entero en vez de degradar a otro índice.
    """
    for basura in ("", "   ", "<html>nada</html>", "[[[", '["https://x.jpg",12]'):
        assert image_search.parse_google_images(basura) == []


def test_bing_saca_lo_mismo_con_el_mismo_contrato():
    html = (
        '<a class="iusc" style="" m="{&quot;murl&quot;:&quot;https://ejemplo.com/coche.jpg&quot;,'
        '&quot;turl&quot;:&quot;https://tse.mm.bing.net/th?id=1&quot;,'
        '&quot;purl&quot;:&quot;https://revista.example/articulo&quot;,'
        '&quot;t&quot;:&quot;Un coche muy rojo&quot;}">x</a>'
    )
    items = image_search.parse_bing_images(html)
    assert len(items) == 1
    it = items[0]
    assert it["url"] == "https://ejemplo.com/coche.jpg"
    assert it["thumb"].startswith("https://tse.mm.bing.net/")
    assert it["page"] == "https://revista.example/articulo"
    assert it["title"] == "Un coche muy rojo"
    # El sitio se DERIVA del host de la página publicadora: Bing no lo da suelto, y una foto sin atribución
    # ninguna es peor que una atribuida a quien la publica.
    assert it["site"] == "revista.example"


def test_una_ficha_de_bing_rota_no_se_lleva_a_las_demas():
    html = (
        '<a class="iusc" m="{roto">x</a>'
        '<a class="iusc" m="{&quot;murl&quot;:&quot;https://ok.example/a.jpg&quot;}">y</a>'
    )
    items = image_search.parse_bing_images(html)
    assert len(items) == 1 and items[0]["url"] == "https://ok.example/a.jpg"
