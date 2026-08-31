"""V2-323 — a VIRTUALIZED listing has no cards until you approach it, and “zero rows” is not “no results”.

V2-294 taught extraction to look twice when rows were EMPTY (the skeleton cards a listing paints
while hydrating) and deliberately decided not to retry with zero rows:

    “that may indeed be a page with no results, and making every empty search wait two seconds means paying
     for all of them to fix a few”

Sound reasoning, with one blind spot. Measured on 2026-08-25 against the exact URL that a worker had just navigated
to (`autoscout24.es/lst/cit_madrid/ft_diesel?…`):

    without scrolling: 0 listing anchors in the DOM · 1 row (furniture)
    after scrolling  : 40 anchors                  · 19 rows

HTTP 200, correct title, and the page’s own text said “16,752 used diesel cars”. The
run (`search-buy-used-car__es`, 19:11) reported **empty sheet after four minutes of real navigation** — which is
indistinguishable from “the page had nothing”, so nobody could fix it by looking at the report.

THE DISCRIMINATOR IS PAGE HEIGHT, and this does not invalidate V2-294’s cost argument: it respects it. Measured:

    autoscout24 (lazy, WITH results) : height/viewport = 11.5×
    wallapop, impossible search (empty): height/viewport =  0.2×

A results page with nothing does not even reach one screen, so it never pays for this.

⚠️ AND THERE IS A SECOND REQUIREMENT that is not about cleanup: the view must RETURN. The worker’s next `click_at`
uses coordinates from a photo taken BEFORE, and a tool that moves the page underneath would break
clicking to fix extraction. Verified live: materialized cards SURVIVE the return to the top.
"""
from __future__ import annotations

import asyncio

import pytest

pytest.importorskip("playwright.async_api")
from playwright.async_api import async_playwright

from widgets.navegador import lazy
from widgets.navegador.dom import _JS_EXTRACT

# A listing that paints its cards WHEN APPROACHED, which is the measured behavior. Actual height reserved from the start
# (as a virtualized listing does), cards created when scrolling passes the threshold.
_PEREZOSA = """
<html><body style="margin:0">
  <div style="height:6000px" id="relleno">
    <p>Resultados: 16.752 coches</p>
  </div>
  <script>
    let pintado = false;
    addEventListener('scroll', () => {
      if (pintado || scrollY < 400) return;
      pintado = true;
      const zona = document.createElement('div');
      zona.innerHTML = Array.from({length: 6}, (_, i) =>
        `<div class="c"><a href="/anuncios/coche-${i}">Skoda Octavia 2.0TDI ${i}</a>` +
        `<span>${3990 + i} €</span></div>`).join('');
      document.body.appendChild(zona);
    });
  </script>
</body></html>"""

# A genuinely empty search: SHORTER than one screen. This one must pay nothing.
_VACIA = '<html><body style="margin:0"><p>No hemos encontrado resultados.</p></body></html>'


class _Tab:
    """The minimum required: a page. The REAL function is tested, not a copy."""
    def __init__(self, page):
        self.page = page

    async def materialise_below_the_fold(self):
        return await lazy.materialise_below_the_fold(self.page)

    async def extract_listings(self, limit=30):
        return await self.page.evaluate(_JS_EXTRACT, limit) or []


async def _con_pagina(html, fn):
    async with async_playwright() as pw:
        b = await pw.chromium.launch()
        p = await b.new_page(viewport={"width": 1280, "height": 900})
        await p.set_content(html)
        try:
            return await fn(_Tab(p), p)
        finally:
            await b.close()


def test_una_pagina_que_pinta_al_acercarse_pasa_de_CERO_a_filas():
    async def caso(tab, page):
        antes = await tab.extract_listings()
        empujo = await tab.materialise_below_the_fold()
        despues = await tab.extract_listings()
        return len(antes), empujo, len(despues)
    antes, empujo, despues = asyncio.run(_con_pagina(_PEREZOSA, caso))
    assert antes == 0, "el fixture no reproduce: ya había filas antes de empujar"
    assert empujo is True
    assert despues >= 5, f"tras recorrer la página deberían aparecer las fichas, salieron {despues}"


def test_una_busqueda_de_VERDAD_vacia_no_paga_nada():
    """The sensitivity that makes the change legitimate: if this breaks, V2-323 has overridden V2-294’s cost
    argument instead of respecting it, and every empty catalog search starts paying for a traversal."""
    async def caso(tab, page):
        return await tab.materialise_below_the_fold()
    assert asyncio.run(_con_pagina(_VACIA, caso)) is False


def test_la_VISTA_vuelve_a_su_sitio():
    """This is not cleanup: the worker’s next `click_at` uses coordinates from an earlier photo."""
    async def caso(tab, page):
        await page.evaluate("() => window.scrollTo(0, 300)")
        antes = await page.evaluate("() => window.scrollY")
        await tab.materialise_below_the_fold()
        return antes, await page.evaluate("() => window.scrollY")
    antes, despues = asyncio.run(_con_pagina(_PEREZOSA, caso))
    assert antes == 300
    assert despues == pytest.approx(300, abs=2), f"la vista se quedó en {despues}, no en {antes}"


def test_falla_BLANDO_y_nunca_tumba_la_extraccion():
    """Fail-soft like this entire module: if the page dies, False is returned and extraction continues."""
    rota = type("P", (), {"evaluate": staticmethod(
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("página cerrada")))})()
    assert asyncio.run(lazy.materialise_below_the_fold(rota)) is False


def test_el_umbral_deja_HUECO_entre_los_dos_casos_medidos():
    """11.5× versus 0.2×: 2 is far from both. If someone raises it to 12 or lowers it to 0.5, this test says so
    before a run does."""
    assert 0.5 < lazy.FOLD_RATIO < 11.0


def test_la_EXTRACCION_lo_consulta_y_solo_cuando_no_hay_nada_con_nombre():
    """Half of the wiring (V2-199) — and order matters: if it were ALWAYS pushed, every extraction with
    results would pay for a page traversal it does not need."""
    import inspect

    from widgets.navegador import act_api
    src = "\n".join(ln for ln in inspect.getsource(act_api).splitlines() if not ln.strip().startswith("#"))
    i = src.find("materialise_below_the_fold(tb.page)")
    assert i > 0, "la extracción dejó de consultar el mecanismo"
    guarda = src[max(0, i - 120):i]
    assert "not by_identity(items)[0]" in guarda, "se empuja sin comprobar que no hay filas con nombre"
