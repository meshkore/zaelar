"""The browser is a DIRECT connection: what works, works in seconds (2026-08-24).

Operator rule, with the trace in front of us: *“browsers must not have any kind of waiting… everything is
immediate, and if something fails, it fails within the next few seconds… under no circumstances should it have
ninety-second timeouts.”*

What existed, measured against the live set on a real site: `navigate` 4.2 s · `look` 4.2 s · `extract`
0.05 s — and a **90 s** cap, twenty times the cost. That is not ample headroom: it means a hang consumes
one third of the round before anyone notices.

And the hang did exist, with its exact cause. `page.evaluate` **has no timeout in Playwright**: it waits for an
execution context, and a NAVIGATING page—the Enter key after typing in a search box—does not have one
until the new document is ready. Reproduced in `search-buy-guitar__es`:

    18:03:45  type «guitarra acustica»      ← se escribe
    18:03:48  screenshot                     ← la captura SALE, o sea que la acción funcionó
    18:05:15  ERROR: no ha contestado en 90s ← 90 s de una ronda de 250

The costly part is not the wait: it is what the wait TURNS INTO. The action had worked and the worker received a
FAILURE, so it repeated it. Now a slow read returns whatever it has, SAYING that the view is only partially
loaded, and the action continues to count as what it was.
"""
import inspect

from nucleo import nav_cli
from widgets.navegador import owner


def test_ninguna_espera_llega_a_noventa_segundos():
    """The number forbidden by the rule, in the three places that could impose it."""
    assert nav_cli._ACT_TIMEOUT_S < 90, "el tope del puente era 90 s y es el que se lleva la ronda"
    assert owner._DOM_TIMEOUT_S < 90
    assert owner._NAV_TIMEOUT / 1000.0 < 90


def test_los_topes_son_de_SEGUNDOS_no_de_minutos():
    """Measured: a real action costs ~4 s. A cap is set against the real cost, not against fear."""
    assert nav_cli._ACT_TIMEOUT_S <= 30
    assert owner._DOM_TIMEOUT_S <= 15
    assert owner._NAV_TIMEOUT / 1000.0 <= 20


def test_el_tope_del_PUENTE_es_mayor_que_el_de_dentro():
    """If the bridge cut off before the reads, the worker would see “did not respond” for actions that were
about to respond—the same failure with a different number."""
    assert nav_cli._ACT_TIMEOUT_S > owner._DOM_TIMEOUT_S
    assert nav_cli._ACT_TIMEOUT_S > owner._NAV_TIMEOUT / 1000.0


def test_las_TRES_lecturas_del_DOM_estan_acotadas():
    """None of them did: two fell under the context's default timeout and `evaluate` has none.
Bounding two out of three leaves the hang exactly where it was."""
    # The CODE LINES are inspected. The first version of this test matched the comment that NAMES the three
    # reads and treated the one that was not bounded as bounded—a presence guard certifying the failure it
    # exists to prevent. The second time today that the same trap has slipped through.
    src = "\n".join(l for l in inspect.getsource(owner.TaskBrowser.snapshot_for_agent).splitlines()
                    if not l.strip().startswith("#"))
    for lectura in ("query_selector_all", "_bulk_metas", "page.title()"):
        i = src.find(lectura)
        assert i > 0, f"{lectura} ya no está en la mirada"
        assert "asyncio.wait_for" in src[max(0, i - 120):i], f"{lectura} sin acotar"
    assert src.count("_DOM_TIMEOUT_S") >= 3


def test_una_lectura_lenta_NO_convierte_una_accion_BUENA_en_un_fallo():
    """The heart of the defect. The text had been entered and the worker received “type did not respond,” so
it repeated it. The read returns whatever it has and SAYS so; it does not raise."""
    src = "\n".join(l for l in inspect.getsource(owner.TaskBrowser.snapshot_for_agent).splitlines()
                    if not l.strip().startswith("#"))
    assert '"partial"' in src and '"note"' in src
    assert "La acción SÍ se hizo" in src, (
        "el worker tiene que enterarse de que su acción funcionó, o la repite")
    assert "raise" not in src, "una mirada lenta no puede tumbar la acción que ya salió bien"


def test_la_vista_a_medias_se_NOMBRA_y_dice_como_salir():
    """An incomplete view delivered as though it were the entire page is how a worker concludes “there is
nothing here” about a full listing. Same contract as node 4.20."""
    src = inspect.getsource(owner.TaskBrowser.snapshot_for_agent)
    assert "seguía cargando" in src and "look" in src


def test_el_barrido_de_BANNERS_es_por_navegacion_no_por_mirada():
    """The fixed toll that made it impossible to “open tabs and assess listings one by one.”

    `_dismiss_overlays` waits 2.5 s for a known CMP to appear and, if it does not, sweeps ALL frames × ALL
    selectors—and a website with ad iframes has many frames. The full cost was paid on every `look`.
    Measured against the live set on es.wallapop.com, same page and without a banner:

        antes:  look 11,17 s · 11,23 s · 11,45 s   (tres miradas seguidas)
        ahora:  look  0,42 s ·  0,42 s ·  0,41 s   con los MISMOS 60 elementos

    It was not the cost of accepting cookies once: it was a toll per action. The sweep happens when CHANGING
    pages, which is when a new banner may appear; if it appears late on the same URL, it shows up in the
    screenshot and the worker can click it—a bit of automation is lost, not the output.
    """
    src = "\n".join(l for l in inspect.getsource(owner.TaskBrowser.snapshot_for_agent).splitlines()
                    if not l.strip().startswith("#"))
    i = src.find("_dismiss_overlays")
    assert i > 0, "el barrido sigue haciendo falta al cambiar de página"
    # The check changed from URL to DOMAIN after measuring that `type --submit` changes the URL and swept
    # everything again; the intent of this test—that there is no sweep on every read—is unchanged.
    assert "_overlays_host" in src[:i], (
        "el barrido tiene que ir detrás de una comprobación, no correr en cada mirada")
    assert "self._overlays_host = " in src[i:], "y hay que recordar para qué sitio se hizo"


def test_el_barrido_NO_se_paga_DOS_VECES_por_navegacion():
    """`_goto` sweeps and, immediately afterward, the following read used to sweep again—because the URL had
    just changed, which is exactly the condition that triggers the sweep. The same toll, collected at the other door.

    Measured against the live set (es.wallapop.com), before and after recording the swept URL in `_goto`:

        navigate #1  36,6 s → 7,2 s
        navigate #2  24,7 s → 11,4 s
        look          15,5 s → 0,35 s
    """
    src = "\n".join(l for l in inspect.getsource(owner.TaskBrowser._goto).splitlines()
                    if not l.strip().startswith("#"))
    i = src.find("_dismiss_overlays")
    assert i > 0, "una navegación sí tiene que barrer: es cuando puede haber banner nuevo"
    assert "self._overlays_host" in src[i:], (
        "hay que apuntar para qué sitio se barrió, o la mirada siguiente lo repite entero")


def test_el_consentimiento_es_por_DOMINIO_no_por_URL():
    """A `type --submit` in a search box CHANGES the URL, and with the URL guard the following read used to
    sweep everything again. Measured in the 19:39 run on `search-buy-guitar__es`: `type` worked—at
    19:39:07 the screenshot was already from `/search?keywords=guitarra+acustica`—and the bridge still
    reported a timeout at 25 s, three times in a row. A CMP is domain-specific: once accepted on wallapop.com,
    it does not reappear while moving within that domain.

        type --submit   25 s (timeout) → 3,84 s
        navigate                       → 4,85 s
        snapshot                       → 0,38 s
    """
    src = "\n".join(l for l in inspect.getsource(owner.TaskBrowser.snapshot_for_agent).splitlines()
                    if not l.strip().startswith("#"))
    assert "_host_of" in src, "por URL vuelve a barrer en cada página del mismo sitio"
    assert "_overlays_host" in src
    assert owner._host_of("https://es.wallapop.com/search?keywords=x") == "es.wallapop.com"
    assert owner._host_of("https://es.wallapop.com/") == owner._host_of("https://es.wallapop.com/app/search?k=1")


def test_OTRO_dominio_si_vuelve_a_barrer():
    """Sensitivity in the opposite direction: remembering the domain cannot turn into never sweeping—the
    worker constantly changes sites and each one brings its own banner."""
    assert owner._host_of("https://www.milanuncios.com/x") != owner._host_of("https://es.wallapop.com/x")


def test_el_barrido_hace_UNA_consulta_por_frame_no_una_por_selector():
    """It was N frames × M selectors back and forth, and a results page with ad iframes has many frames: the
    full sweep cost ~15–20 s. The selectors are combined, just as the earlier step in the same function already did."""
    src = "\n".join(l for l in inspect.getsource(owner._dismiss_overlays).splitlines()
                    if not l.strip().startswith("#"))
    i = src.find("for fr in page.frames")
    assert i > 0
    tramo = src[i:]
    assert "for sel in" not in tramo, "un bucle por selector dentro del bucle de frames es el coste que se quitó"
    assert "_combined" in tramo
