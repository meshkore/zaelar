"""V2-323 — un listado VIRTUALIZADO no tiene sus fichas hasta que te acercas, y «cero filas» no es «sin resultados».

V2-294 enseñó a la extracción a mirar dos veces cuando las filas venían HUECAS (las tarjetas esqueleto que pinta
un listado mientras hidrata) y decidió A PROPÓSITO no reintentar con cero filas:

    «esa sí puede ser una página sin resultados, y hacerle esperar dos segundos a cada búsqueda vacía es pagar
     por todas para arreglar unas pocas»

Razonamiento bueno, con un punto ciego. Medido el 2026-08-25 contra la URL exacta que acababa de conducir un
worker (`autoscout24.es/lst/cit_madrid/ft_diesel?…`):

    sin desplazarse : 0 anclas de anuncio en el DOM · 1 fila (mobiliario)
    tras desplazarse: 40 anclas                     · 19 filas

HTTP 200, título correcto, y el texto de la propia página decía «16.752 coches de segunda mano diésel». La
ronda (`search-buy-used-car__es`, 19:11) reportó **hoja vacía tras cuatro minutos de navegación real** — que es
indistinguible de «la página no tenía nada», y por eso nadie podía arreglarlo mirando el informe.

EL DISCRIMINADOR ES EL ALTO DE LA PÁGINA, y no invalida el argumento de coste de V2-294: lo respeta. Medido:

    autoscout24 (perezosa, CON resultados) : alto/viewport = 11,5×
    wallapop, búsqueda imposible (vacía)   : alto/viewport =  0,2×

Una página de resultados sin nada no llega ni a una pantalla, así que nunca paga por esto.

⚠️ Y HAY UN SEGUNDO REQUISITO que no es de limpieza: la vista tiene que VOLVER. El siguiente `click_at` del
worker lleva coordenadas de una foto tomada ANTES, y una herramienta que mueve la página por debajo rompería el
clicar para arreglar el extraer. Comprobado en vivo: las fichas materializadas SOBREVIVEN a la vuelta arriba.
"""
from __future__ import annotations

import asyncio

import pytest

pytest.importorskip("playwright.async_api")
from playwright.async_api import async_playwright

from widgets.navegador import lazy
from widgets.navegador.dom import _JS_EXTRACT

# Un listado que pinta sus fichas AL ACERCARSE, que es la forma medida. Alto real reservado desde el principio
# (como hace un listado virtualizado), fichas creadas cuando el scroll pasa del umbral.
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

# Una búsqueda de verdad vacía: MÁS CORTA que una pantalla. Es la que no debe pagar nada.
_VACIA = '<html><body style="margin:0"><p>No hemos encontrado resultados.</p></body></html>'


class _Tab:
    """Lo mínimo que hace falta: una página. Se prueba la función REAL, no una copia."""
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
    """La sensibilidad que hace legítimo el cambio: si esto se rompe, V2-323 ha pisado el argumento de coste de
    V2-294 en vez de respetarlo, y toda búsqueda vacía del catálogo empieza a pagar un recorrido."""
    async def caso(tab, page):
        return await tab.materialise_below_the_fold()
    assert asyncio.run(_con_pagina(_VACIA, caso)) is False


def test_la_VISTA_vuelve_a_su_sitio():
    """No es limpieza: el `click_at` siguiente del worker lleva coordenadas de una foto anterior."""
    async def caso(tab, page):
        await page.evaluate("() => window.scrollTo(0, 300)")
        antes = await page.evaluate("() => window.scrollY")
        await tab.materialise_below_the_fold()
        return antes, await page.evaluate("() => window.scrollY")
    antes, despues = asyncio.run(_con_pagina(_PEREZOSA, caso))
    assert antes == 300
    assert despues == pytest.approx(300, abs=2), f"la vista se quedó en {despues}, no en {antes}"


def test_falla_BLANDO_y_nunca_tumba_la_extraccion():
    """Fail-soft como todo este módulo: si la página se muere, se devuelve False y la extracción sigue."""
    rota = type("P", (), {"evaluate": staticmethod(
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("página cerrada")))})()
    assert asyncio.run(lazy.materialise_below_the_fold(rota)) is False


def test_el_umbral_deja_HUECO_entre_los_dos_casos_medidos():
    """11,5× frente a 0,2×: el 2 está lejos de ambos. Si alguien lo sube a 12 o lo baja a 0,5, este test lo dice
    antes de que lo diga una ronda."""
    assert 0.5 < lazy.FOLD_RATIO < 11.0


def test_la_EXTRACCION_lo_consulta_y_solo_cuando_no_hay_nada_con_nombre():
    """La mitad de cableado (V2-199) — y el orden importa: si se empujara SIEMPRE, cada extracción con
    resultados pagaría un recorrido de página que no necesita."""
    import inspect

    from widgets.navegador import act_api
    src = "\n".join(ln for ln in inspect.getsource(act_api).splitlines() if not ln.strip().startswith("#"))
    i = src.find("materialise_below_the_fold(tb.page)")
    assert i > 0, "la extracción dejó de consultar el mecanismo"
    guarda = src[max(0, i - 120):i]
    assert "not by_identity(items)[0]" in guarda, "se empuja sin comprobar que no hay filas con nombre"
