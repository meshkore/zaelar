"""V2-457 — the image-results parser, measured against a recorded REAL payload.

Google's payload shape is the fragile part of all this, so it must be testable without a network. The fixture
(`fixtures/google_images_ferrari_amalfi.txt`) is a literal excerpt of the search that prompted the initiative,
recorded on 2026-08-28: if Google changes its format, these cases turn red here rather than during a studio round
three days later.
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
    """The operator asked to see the SOURCE, and the site cannot be deduced from a CDN URL.

    `cdn.ferrari.com` does look like Ferrari, but `hips.hearstapps.com` is Car and Driver and
    `c.encycarpedia.com` is Encycarpedia: guessing from the host would be right for some and wrong for others.
    """
    items = image_search.parse_google_images(_blob())
    con_sitio = [it for it in items if it["site"]]
    assert len(con_sitio) >= 10, "casi todas las filas traen sitio en el payload real"
    ferrari = [it for it in items if it["site"] == "www.ferrari.com"]
    assert ferrari, "la búsqueda real devuelve originales del fabricante"
    assert ferrari[0]["page"].startswith("https://www.ferrari.com/")
    assert "Ferrari Amalfi" in ferrari[0]["title"]


def test_un_titulo_con_comillas_escapadas_no_se_corta_a_medias():
    """A real row is titled `The Ferrari Amalfi, the new \\"Dolce Vita\\"…`.

    A pattern matching `[^"]*` stops at the backslash and returns the title cut off mid-word, with a stray
    backslash at the end — and that is read aloud. The rule consumes the escapes instead of stumbling over them.
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
    """Total by contract: the fallback for «there are no photos» and «the format changed» is the SAME.

    If this raised, a change in Google's format would bring down the entire turn instead of degrading to another index.
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
    # The site is DERIVED from the publishing page's host: Bing does not provide it separately, and an unattributed
    # photo is worse than one attributed to its publisher.
    assert it["site"] == "revista.example"


def test_una_ficha_de_bing_rota_no_se_lleva_a_las_demas():
    html = (
        '<a class="iusc" m="{roto">x</a>'
        '<a class="iusc" m="{&quot;murl&quot;:&quot;https://ok.example/a.jpg&quot;}">y</a>'
    )
    items = image_search.parse_bing_images(html)
    assert len(items) == 1 and items[0]["url"] == "https://ok.example/a.jpg"
